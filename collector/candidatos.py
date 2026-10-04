# =============================================================================
# collector/candidatos.py — Coleta candidatos registrados via Dados Abertos TSE
# Baixa e processa o arquivo oficial consulta_cand_2026.zip
# =============================================================================

import io
import csv
import zipfile
import logging
from typing import List, Dict, Any, Optional

import requests

from config import (
    CARGOS,
    EXPORT_DIR,
    REQUEST_TIMEOUT_SEC,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
)
from storage.database import upsert_candidatos_bulk

logger = logging.getLogger(__name__)

URL_CAND_ZIP = "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/consulta_cand_2026.zip"

COD_TSE_PARA_CARGO = {
    "1": ("PR", "Presidente da República"),
    "3": ("GOV", "Governador"),
    "5": ("SEN", "Senador"),
    "6": ("DEP_FED", "Deputado Federal"),
    "7": ("DEP_EST", "Deputado Estadual"),
}


def _download_zip(url: str) -> Optional[bytes]:
    """Baixa o arquivo zip com retry e logs claros."""
    import time
    for tentativa in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Baixando arquivo oficial de candidatos: %s (tentativa %d/%d)", url, tentativa, MAX_RETRIES)
            resp = requests.get(url, timeout=REQUEST_TIMEOUT_SEC * 4, stream=True)
            if resp.status_code == 200:
                logger.info("Download concluído com sucesso!")
                return resp.content
            logger.warning("HTTP %d ao baixar %s", resp.status_code, url)
        except Exception as e:
            logger.warning("Falha no download (tentativa %d/%d): %s", tentativa, MAX_RETRIES, e)

        if tentativa < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_BASE ** tentativa)

    logger.error("Não foi possível baixar o arquivo de candidatos.")
    return None


def _processar_csv_candidatos(conteudo_csv: str) -> List[Dict[str, Any]]:
    """Parseia linhas do CSV de candidatos do TSE filtrando SP e PR."""
    candidatos = []
    reader = csv.DictReader(io.StringIO(conteudo_csv), delimiter=";")
    if not reader.fieldnames:
        return []

    for row in reader:
        try:
            sg_uf = row.get("SG_UF", "").strip().upper()
            cd_cargo = str(row.get("CD_CARGO", "")).strip()

            # Aceita Presidente (BR) ou cargos do Estado de SP
            if cd_cargo == "1":
                if sg_uf not in ("BR", "SP"):
                    continue
            else:
                if sg_uf != "SP":
                    continue

            if cd_cargo not in COD_TSE_PARA_CARGO:
                continue

            cargo_cod, cargo_nome = COD_TSE_PARA_CARGO[cd_cargo]
            sq_cand = row.get("SQ_CANDIDATO", "").strip()
            nr_cand = row.get("NR_CANDIDATO", "").strip()

            if not sq_cand or not nr_cand:
                continue

            candidato = {
                "id": int(sq_cand),
                "cargo_cod": cargo_cod,
                "cargo_nome": cargo_nome,
                "numero": int(nr_cand),
                "nome": row.get("NM_CANDIDATO", "").strip().upper(),
                "nome_urna": row.get("NM_URNA_CANDIDATO", "").strip().upper(),
                "partido": row.get("NM_PARTIDO", "").strip().upper(),
                "sigla_partido": row.get("SG_PARTIDO", "").strip().upper(),
                "foto_url": "",
                "situacao_cand": row.get("DS_SITUACAO_CANDIDATURA", "").strip(),
            }
            candidatos.append(candidato)
        except Exception:
            continue

    return candidatos


def coletar_todos_candidatos() -> int:
    """Baixa o pacote de candidaturas e salva os candidatos de SP no SQLite."""
    logger.info("Iniciando importação de candidatos via Dados Abertos...")
    conteudo = _download_zip(URL_CAND_ZIP)
    if not conteudo:
        logger.error("Falha ao obter dados abertos de candidatos.")
        return 0

    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
            csv_files = [f for f in zf.namelist() if f.lower().endswith(".csv")]
            # Filtra os arquivos de SP e BR se estiverem separados, ou processa todos
            alvos = [f for f in csv_files if "_SP." in f.upper() or "_BR." in f.upper()] or csv_files
            logger.info("Encontrados %d arquivos CSV para processar.", len(alvos))

            for filename in alvos:
                logger.info("Processando arquivo: %s", filename)
                with zf.open(filename) as f:
                    csv_text = f.read().decode("latin-1")
                cands = _processar_csv_candidatos(csv_text)
                if cands:
                    upsert_candidatos_bulk(cands)
                    total += len(cands)
                    logger.info("Importados %d candidatos do arquivo %s", len(cands), filename)

    except Exception as e:
        logger.exception("Erro ao extrair/processar zip de candidatos: %s", e)

    logger.info("Total final de candidatos importados para o banco: %d", total)
    return total


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from storage.database import setup_database
    setup_database()
    n = coletar_todos_candidatos()
    print(f"\n✅ {n} candidatos importados com sucesso!")
