# =============================================================================
# collector/dados_abertos.py — Download de Boletins de Urna (BUs) auditados
# Portal de Dados Abertos do TSE — executar pós-pleito (a partir das 17h)
# =============================================================================

import io
import logging
import zipfile
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

import requests

from config import (
    TSE_DADOS_ABERTOS,
    UF_UPPER,
    COD_MUNICIPIO,
    CARGOS,
    COD_TSE_PARA_CARGO,
    PLEITO_1T,
    EXPORT_DIR,
    REQUEST_TIMEOUT_SEC,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
)
from storage.database import insert_boletins_urna_bulk

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Padrões de URL do Portal de Dados Abertos TSE
# ---------------------------------------------------------------------------
# Download de BU por UF (arquivo ZIP com CSVs)
# Exemplo 2022: https://cdn.tse.jus.br/estatistica/sead/odsele/resultado_boletim_urna/rbu_SP_2022.zip
CDN_TSE      = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_BU_ZIP   = f"{CDN_TSE}/resultado_boletim_urna/rbu_{UF_UPPER}_2026.zip"

# Fallback: API CKAN do portal de dados abertos
CKAN_API     = f"{TSE_DADOS_ABERTOS}/api/3/action"
CKAN_DATASET = "boletim-de-urna-2026"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _download_bytes(url: str) -> Optional[bytes]:
    """Faz download de um arquivo, retorna bytes ou None em falha."""
    import time
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Baixando: %s (tentativa %d/%d)", url, tentativa, MAX_RETRIES)
            resp = requests.get(
                url,
                timeout=120,   # BUs são arquivos grandes
                stream=True,
            )
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.HTTPError as e:
            logger.warning("HTTP %d — tentativa %d/%d", e.response.status_code, tentativa, MAX_RETRIES)
        except requests.exceptions.RequestException as e:
            logger.warning("Erro de rede: %s — tentativa %d/%d", e, tentativa, MAX_RETRIES)

        if tentativa < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_BASE ** tentativa)

    logger.error("Falha no download após %d tentativas: %s", MAX_RETRIES, url)
    return None


def _get_json(url: str) -> Optional[Any]:
    """GET JSON simples com timeout."""
    import time
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SEC)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.warning("Erro GET JSON: %s (tentativa %d)", e, tentativa)
            if tentativa < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_BASE ** tentativa)
    return None


# ---------------------------------------------------------------------------
# Parser de BU (CSV do TSE)
# ---------------------------------------------------------------------------

# Colunas esperadas no CSV de BU do TSE (2022/2024 — pode variar em 2026)
# Referência: leiame do Dados Abertos do TSE
COLUNAS_BU = {
    "NR_ZONA":            "zona",
    "NR_SECAO":           "secao",
    "CD_CARGO":           "cargo_tse",
    "NR_VOTAVEL":         "candidato_num",
    "QT_VOTOS":           "votos_bu",
}


def _parse_bu_csv(conteudo_csv: str) -> List[Dict[str, Any]]:
    """
    Parseia CSV de BU retornado pelo TSE.
    Filtra apenas São Paulo (município) e cargos monitorados.
    """
    registros: List[Dict[str, Any]] = []
    agora = datetime.now(tz=timezone.utc).isoformat()

    reader = csv.DictReader(
        io.StringIO(conteudo_csv),
        delimiter=";",
    )

    # Detecta nomes de colunas (TSE usa MAIÚSCULAS)
    if reader.fieldnames is None:
        logger.warning("CSV sem cabeçalho detectado.")
        return []

    # Monta mapa de colunas disponíveis
    colunas_disponiveis = {f.strip().upper(): f for f in reader.fieldnames}

    for row in reader:
        try:
            # Filtro por município São Paulo
            cod_mun = row.get("CD_MUNICIPIO", row.get("SG_UF_MUN", "")).strip()
            if cod_mun and cod_mun != COD_MUNICIPIO:
                continue

            # Filtro por cargo monitorado
            cod_cargo_tse = str(row.get("CD_CARGO", "")).strip()
            cargo_cod = COD_TSE_PARA_CARGO.get(cod_cargo_tse)
            if cargo_cod is None:
                continue

            zona        = str(row.get("NR_ZONA", "")).strip().zfill(4)
            secao       = str(row.get("NR_SECAO", "")).strip().zfill(4)
            cand_num    = int(row.get("NR_VOTAVEL", 0) or 0)
            votos       = int(row.get("QT_VOTOS", 0) or 0)

            if cand_num <= 0:
                continue   # voto branco/nulo tem NR_VOTAVEL <= 0 ou específico

            registros.append({
                "zona":          zona,
                "secao":         secao,
                "cargo_cod":     cargo_cod,
                "candidato_num": cand_num,
                "votos_bu":      votos,
                "importado_em":  agora,
                "auditado":      1,
            })

        except (ValueError, KeyError) as e:
            logger.debug("Linha ignorada: %s", e)
            continue

    return registros


# ---------------------------------------------------------------------------
# Download e importação do ZIP de BUs
# ---------------------------------------------------------------------------

def importar_bu_zip(url: str = URL_BU_ZIP) -> int:
    """
    Baixa o ZIP de Boletins de Urna do TSE para SP,
    extrai os CSVs e importa para o banco.
    Retorna o total de registros importados.
    """
    conteudo = _download_bytes(url)
    if not conteudo:
        logger.error("Não foi possível baixar o arquivo de BUs: %s", url)
        return 0

    # Salva o ZIP localmente para auditoria
    zip_path = EXPORT_DIR / f"rbu_SP_2026_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path.write_bytes(conteudo)
    logger.info("ZIP salvo em: %s (%d bytes)", zip_path, len(conteudo))

    total_importados = 0

    with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
        arquivos_csv = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        logger.info("ZIP contém %d arquivo(s) CSV.", len(arquivos_csv))

        for nome_arquivo in arquivos_csv:
            logger.info("Processando: %s", nome_arquivo)
            with zf.open(nome_arquivo) as f:
                # TSE usa encoding latin-1 (ISO-8859-1)
                conteudo_csv = f.read().decode("latin-1")

            registros = _parse_bu_csv(conteudo_csv)
            if registros:
                insert_boletins_urna_bulk(registros)
                total_importados += len(registros)
                logger.info(
                    "  → %s: %d registros importados para SP.",
                    nome_arquivo, len(registros)
                )
            else:
                logger.warning("  → %s: nenhum registro relevante encontrado.", nome_arquivo)

    logger.info("Total de BUs importados: %d", total_importados)
    return total_importados


# ---------------------------------------------------------------------------
# Descoberta de URL via API CKAN (fallback)
# ---------------------------------------------------------------------------

def descobrir_url_bu_via_ckan() -> Optional[str]:
    """
    Consulta a API CKAN do portal de dados abertos para descobrir
    a URL de download mais recente do arquivo de BUs de 2026 para SP.
    """
    url_search = f"{CKAN_API}/package_show?id={CKAN_DATASET}"
    data = _get_json(url_search)
    if not data or not data.get("success"):
        logger.warning("API CKAN não retornou dados para dataset '%s'.", CKAN_DATASET)
        return None

    resources = data.get("result", {}).get("resources", [])
    for res in resources:
        name  = (res.get("name") or "").lower()
        url   = res.get("url") or ""
        if UF_UPPER.lower() in name and url.endswith(".zip"):
            logger.info("URL de BU encontrada via CKAN: %s", url)
            return url

    return None


# ---------------------------------------------------------------------------
# Execução direta
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    from storage.database import setup_database
    setup_database()

    print("=== Importando Boletins de Urna — SP 2026 ===\n")

    # Tenta URL padrão, depois CKAN como fallback
    url = URL_BU_ZIP
    url_ckan = descobrir_url_bu_via_ckan()
    if url_ckan:
        url = url_ckan

    total = importar_bu_zip(url)
    print(f"\n✅ Total de BUs importados: {total} registros.")
