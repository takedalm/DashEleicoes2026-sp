# =============================================================================
# config.py — Configurações e constantes globais
# Eleições 2026 · São Paulo
# =============================================================================

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Diretórios
# ---------------------------------------------------------------------------
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
DB_PATH    = DATA_DIR / "eleicoes2026.db"
LOG_DIR    = BASE_DIR / "logs"
EXPORT_DIR = DATA_DIR / "exports"

for _d in (DATA_DIR, LOG_DIR, EXPORT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# TSE — Endpoints
# ---------------------------------------------------------------------------
TSE_CDN_BASE         = "https://resultados.tse.jus.br"
TSE_DADOS_ABERTOS    = "https://dadosabertos.tse.jus.br"
TSE_DIVULGA_CAND     = "https://divulgacandcontas.tse.jus.br/divulga"

# Ciclo eleitoral (ex: "ele2026")
CICLO = "ele2026"

# Código do pleito 1º turno 2026 (confirmar via config.json antes das 8h)
# Referência: 2022 = 544 (1T), 2024 = 452 (1T) — estimativa para 2026:
PLEITO_1T = os.environ.get("TSE_PLEITO_1T", "3220")

# ---------------------------------------------------------------------------
# Localização — São Paulo
# ---------------------------------------------------------------------------
UF              = "sp"
UF_UPPER        = "SP"
COD_MUNICIPIO   = "71072"   # São Paulo (5 dígitos com zero)
NOME_MUNICIPIO  = "SÃO PAULO"

# ---------------------------------------------------------------------------
# Cargos monitorados
# Códigos TSE: PR=1, SEN=5, GOV=3, DEP_FED=6, DEP_EST=7
# ---------------------------------------------------------------------------
CARGOS = {
    "PR":      {"cod_tse": "1",  "nome": "Presidente da República", "abrev": "PR"},
    "GOV":     {"cod_tse": "3",  "nome": "Governador",              "abrev": "GOV"},
    "SEN":     {"cod_tse": "5",  "nome": "Senador",                 "abrev": "SEN"},
    "DEP_FED": {"cod_tse": "6",  "nome": "Deputado Federal",        "abrev": "DEP_FED"},
    "DEP_EST": {"cod_tse": "7",  "nome": "Deputado Estadual",       "abrev": "DEP_EST"},
}

# Mapeamento inverso: cod_tse → chave
COD_TSE_PARA_CARGO = {v["cod_tse"]: k for k, v in CARGOS.items()}

# ---------------------------------------------------------------------------
# Scheduler — Polling
# ---------------------------------------------------------------------------
POLL_INTERVAL_SEC  = 300     # 5 minutos
PLEITO_START_HOUR  = 8       # 08:00 BRT
PLEITO_END_HOUR    = 18      # 18:00 BRT (margem após encerramento às 17h)

# ---------------------------------------------------------------------------
# HTTP — Rate limiting
# ---------------------------------------------------------------------------
MAX_CONCURRENT_REQUESTS = 10
REQUEST_TIMEOUT_SEC     = 30
MAX_RETRIES             = 5
RETRY_BACKOFF_BASE      = 2    # segundos (exponencial)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE  = LOG_DIR / "eleicoes2026.log"
