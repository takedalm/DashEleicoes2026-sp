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
# TSE — Endpoints Oficiais
# ---------------------------------------------------------------------------
TSE_CDN_BASE         = "https://resultados.tse.jus.br/oficial"
TSE_DADOS_ABERTOS    = "https://dadosabertos.tse.jus.br"
TSE_DIVULGA_CAND     = "https://divulgacandcontas.tse.jus.br/divulga"

# Ciclo eleitoral e pleito oficial
CICLO = "ele2026"
PLEITO_1T = "3220"

# Códigos de eleição oficiais conforme Resolução TSE 23.751/2026:
# 6257: Eleição Geral Federal (Presidente)
# 6259: Eleições Gerais Estaduais (SP: Governador, Senador, Dep. Federal, Dep. Estadual)
ELEICAO_FEDERAL  = "6257"
ELEICAO_ESTADUAL = "6259"

# ---------------------------------------------------------------------------
# Localização — São Paulo
# ---------------------------------------------------------------------------
UF              = "sp"
UF_UPPER        = "SP"
UF_BR           = "br"
COD_MUNICIPIO   = "71072"   # São Paulo (5 dígitos com zero)
NOME_MUNICIPIO  = "SÃO PAULO"

# ---------------------------------------------------------------------------
# Cargos monitorados
# Padrão EA20 do TSE: Presidente (BR), demais cargos (SP)
# ---------------------------------------------------------------------------
CARGOS = {
    "PR": {
        "cod_tse": "1",
        "cd_cargo": "0001",
        "nome": "Presidente da República",
        "eleicao": ELEICAO_FEDERAL,
        "abrangencia": UF_BR,
        "abrev": "PR",
    },
    "GOV": {
        "cod_tse": "3",
        "cd_cargo": "0003",
        "nome": "Governador",
        "eleicao": ELEICAO_ESTADUAL,
        "abrangencia": UF,
        "abrev": "GOV",
    },
    "SEN": {
        "cod_tse": "5",
        "cd_cargo": "0005",
        "nome": "Senador",
        "eleicao": ELEICAO_ESTADUAL,
        "abrangencia": UF,
        "abrev": "SEN",
    },
    "DEP_FED": {
        "cod_tse": "6",
        "cd_cargo": "0006",
        "nome": "Deputado Federal",
        "eleicao": ELEICAO_ESTADUAL,
        "abrangencia": UF,
        "abrev": "DEP_FED",
    },
    "DEP_EST": {
        "cod_tse": "7",
        "cd_cargo": "0007",
        "nome": "Deputado Estadual",
        "eleicao": ELEICAO_ESTADUAL,
        "abrangencia": UF,
        "abrev": "DEP_EST",
    },
}

# Mapeamento inverso: cod_tse → chave
COD_TSE_PARA_CARGO = {v["cod_tse"]: k for k, v in CARGOS.items()}

# Cabeçalhos padrão de navegador para evitar bloqueios WAF/CDN
HEADERS_BROWSER = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://resultados.tse.jus.br/oficial/app/index.html",
    "Origin": "https://resultados.tse.jus.br",
}

# ---------------------------------------------------------------------------
# Scheduler — Polling
# ---------------------------------------------------------------------------
POLL_INTERVAL_SEC  = 300     # 5 minutos
PLEITO_START_HOUR  = 8       # 08:00 BRT
PLEITO_END_HOUR    = 23      # 23:00 BRT (cobre a apuração completa até o final da noite)

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
