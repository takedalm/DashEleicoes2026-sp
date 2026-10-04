# =============================================================================
# collector/tse_api.py — Client de polling da API de resultados do TSE (CDN)
# Coleta dados em tempo real durante o pleito (8h–17h)
# =============================================================================

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

import aiohttp

from config import (
    TSE_CDN_BASE,
    CICLO,
    PLEITO_1T,
    UF,
    COD_MUNICIPIO,
    CARGOS,
    MAX_CONCURRENT_REQUESTS,
    REQUEST_TIMEOUT_SEC,
    MAX_RETRIES,
    RETRY_BACKOFF_BASE,
)
from storage.database import (
    insert_resultados_bulk,
    upsert_snapshot_meta,
    get_candidatos,
)

logger = logging.getLogger(__name__)

# Semáforo para limitar requisições concorrentes
_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_semaphore() -> asyncio.Semaphore:
    global _SEMAPHORE
    if _SEMAPHORE is None:
        _SEMAPHORE = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    return _SEMAPHORE


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def url_config_pleito() -> str:
    """URL do arquivo de configuração do pleito (descobre o código real)."""
    return f"{TSE_CDN_BASE}/{CICLO}/config.json"


def url_resultado_cargo(cargo_cod: str) -> str:
    """
    URL do JSON de resultado em tempo real por cargo + município São Paulo.
    Padrão TSE: /ele2026/{pleito}/dados-simplificados/{uf}/{mun}/{mun}-c{cargo}-e{pleito}-r.json
    """
    cod_tse = CARGOS[cargo_cod]["cod_tse"]
    pleito  = PLEITO_1T.zfill(6)   # zero-padded conforme padrão TSE
    return (
        f"{TSE_CDN_BASE}/{CICLO}/{pleito}"
        f"/dados-simplificados/{UF}/{COD_MUNICIPIO}"
        f"/{COD_MUNICIPIO}-c{cod_tse}-e{pleito}-r.json"
    )


# ---------------------------------------------------------------------------
# HTTP async helpers
# ---------------------------------------------------------------------------

async def _fetch_json(
    session: aiohttp.ClientSession,
    url: str,
) -> Optional[Any]:
    """Fetch assíncrono com retry exponencial e semáforo de rate limiting."""
    sem = _get_semaphore()
    for tentativa in range(1, MAX_RETRIES + 1):
        async with sem:
            try:
                timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SEC)
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.json(content_type=None)
                    elif resp.status in (429, 503):
                        logger.warning("Rate limit/serviço indisponível (HTTP %d) — URL: %s", resp.status, url)
                    elif resp.status == 404:
                        logger.debug("404 — dados ainda não disponíveis: %s", url)
                        return None
                    else:
                        logger.warning("HTTP %d — URL: %s", resp.status, url)
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.warning("Erro de rede (tentativa %d/%d): %s — %s", tentativa, MAX_RETRIES, e, url)

        if tentativa < MAX_RETRIES:
            backoff = RETRY_BACKOFF_BASE ** tentativa
            await asyncio.sleep(backoff)

    return None


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def _parse_resultado_cargo(
    data: Dict[str, Any],
    cargo_cod: str,
    snapshot_ts: datetime,
    candidatos_db: Dict[int, int],  # numero → id do banco
) -> Tuple[List[Dict], Dict]:
    """
    Extrai lista de resultados e metadados a partir do JSON de resultado TSE.

    Retorna: (lista_resultados, meta_dict)
    """
    resultados = []
    meta       = {}

    try:
        # Metadados gerais do cargo
        urnas_apuradas = int(data.get("s", 0))   # secoes apuradas
        urnas_total    = int(data.get("st", 0))   # total de secoes
        pct_urnas      = round(urnas_apuradas / urnas_total * 100, 2) if urnas_total else 0.0

        votos_validos  = int(data.get("vv", 0))
        votos_brancos  = int(data.get("vb", 0))
        votos_nulos    = int(data.get("vn", 0))
        total_votos    = votos_validos + votos_brancos + votos_nulos

        meta = {
            "cargo_cod":       cargo_cod,
            "snapshot_ts":     snapshot_ts.isoformat(),
            "urnas_apuradas":  urnas_apuradas,
            "urnas_total":     urnas_total,
            "votos_validos":   votos_validos,
            "votos_brancos":   votos_brancos,
            "votos_nulos":     votos_nulos,
            "total_votos":     total_votos,
        }

        # Lista de candidatos no JSON
        for cand in data.get("cands", []):
            numero        = int(cand.get("n", 0))
            votos_nom     = int(cand.get("v", 0))
            votos_legenda = int(cand.get("vl", 0))
            percentual    = round(float(cand.get("pvv", 0.0)), 2)
            nome_urna     = cand.get("nm", "").strip().upper()
            sigla_partido = cand.get("sg", "").strip().upper()
            situacao      = cand.get("st", "")   # 'Eleito', 'Não eleito', etc.

            resultados.append({
                "snapshot_ts":    snapshot_ts.isoformat(),
                "cargo_cod":      cargo_cod,
                "candidato_id":   candidatos_db.get(numero),
                "numero":         numero,
                "nome_urna":      nome_urna,
                "sigla_partido":  sigla_partido,
                "votos_nom":      votos_nom,
                "votos_legenda":  votos_legenda,
                "percentual":     percentual,
                "urnas_apuradas": urnas_apuradas,
                "urnas_total":    urnas_total,
                "pct_urnas":      pct_urnas,
                "situacao":       situacao,
            })

    except (KeyError, TypeError, ValueError) as e:
        logger.error("Erro ao parsear resultado do cargo %s: %s", cargo_cod, e)

    return resultados, meta


# ---------------------------------------------------------------------------
# Coleta de um ciclo completo (todos os cargos)
# ---------------------------------------------------------------------------

async def coletar_resultados_async() -> Dict[str, int]:
    """
    Coleta resultados de todos os cargos monitorados de forma assíncrona.
    Persiste snapshots no banco SQLite.
    Retorna dict com total de registros inseridos por cargo.
    """
    snapshot_ts = datetime.now(tz=timezone.utc)
    totais: Dict[str, int] = {}

    # Mapeia numero → candidato_id para cruzamento
    candidatos_db: Dict[str, Dict[int, int]] = {}
    for cargo_cod in CARGOS:
        cands = get_candidatos(cargo_cod)
        candidatos_db[cargo_cod] = {row["numero"]: row["id"] for row in cands}

    urls = {
        cargo_cod: url_resultado_cargo(cargo_cod)
        for cargo_cod in CARGOS
    }

    async with aiohttp.ClientSession() as session:
        tasks = {
            cargo_cod: asyncio.create_task(_fetch_json(session, url))
            for cargo_cod, url in urls.items()
        }

        for cargo_cod, task in tasks.items():
            data = await task
            if not data:
                logger.warning("Sem dados para cargo %s no snapshot %s",
                               cargo_cod, snapshot_ts.isoformat())
                totais[cargo_cod] = 0
                continue

            resultados, meta = _parse_resultado_cargo(
                data, cargo_cod, snapshot_ts, candidatos_db.get(cargo_cod, {})
            )

            if resultados:
                insert_resultados_bulk(resultados)
                totais[cargo_cod] = len(resultados)
                logger.info("Cargo %s: %d candidatos atualizados | %s%%  urnas",
                            cargo_cod, len(resultados),
                            meta.get("pct_urnas", "?"))

            if meta:
                upsert_snapshot_meta(meta)

    return totais


def coletar_resultados() -> Dict[str, int]:
    """Wrapper síncrono para chamar a versão assíncrona."""
    return asyncio.run(coletar_resultados_async())


# ---------------------------------------------------------------------------
# Descoberta do código de pleito via config.json
# ---------------------------------------------------------------------------

def descobrir_codigo_pleito() -> Optional[str]:
    """
    Acessa resultados.tse.jus.br/ele2026/config.json e retorna o código
    do pleito ativo (1º turno).
    """
    import requests

    url = url_config_pleito()
    logger.info("Descobrindo código do pleito via: %s", url)
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        # Estrutura típica: {"pr": [{"cd": "3220", ...}], ...}
        # Ou lista de pleitos com 'cd' e 'dt'
        pleitos = data.get("el", data.get("pleitos", []))
        if pleitos:
            # Pega o primeiro ativo (menor número = mais recente em 2026)
            cod = pleitos[0].get("cd") or pleitos[0].get("codigo")
            logger.info("Código do pleito descoberto: %s", cod)
            return str(cod)
    except Exception as e:
        logger.error("Erro ao descobrir código do pleito: %s", e)
    return None


# ---------------------------------------------------------------------------
# Execução direta (teste de conectividade)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    print("=== Testando conectividade com TSE CDN ===\n")

    cod = descobrir_codigo_pleito()
    print(f"Código do pleito 2026: {cod or 'não encontrado (usar variável TSE_PLEITO_1T)'}")

    print("\n=== Coletando snapshot de resultados ===\n")
    totais = coletar_resultados()
    for cargo, n in totais.items():
        print(f"  {cargo}: {n} candidatos")
