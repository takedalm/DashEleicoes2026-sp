# =============================================================================
# storage/models.py — Definições das tabelas SQLite (SQL DDL)
# =============================================================================

DDL_CANDIDATOS = """
CREATE TABLE IF NOT EXISTS candidatos (
    id              INTEGER PRIMARY KEY,
    cargo_cod       TEXT NOT NULL,
    cargo_nome      TEXT NOT NULL,
    numero          INTEGER NOT NULL,
    nome            TEXT NOT NULL,
    nome_urna       TEXT NOT NULL,
    partido         TEXT NOT NULL,
    sigla_partido   TEXT NOT NULL,
    foto_url        TEXT,
    situacao_cand   TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

DDL_RESULTADOS = """
CREATE TABLE IF NOT EXISTS resultados (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_ts     TIMESTAMP NOT NULL,
    cargo_cod       TEXT NOT NULL,
    candidato_id    INTEGER REFERENCES candidatos(id),
    numero          INTEGER NOT NULL,
    nome_urna       TEXT NOT NULL,
    sigla_partido   TEXT NOT NULL,
    votos_nom       INTEGER NOT NULL DEFAULT 0,
    votos_legenda   INTEGER DEFAULT 0,
    percentual      REAL DEFAULT 0.0,
    urnas_apuradas  INTEGER DEFAULT 0,
    urnas_total     INTEGER DEFAULT 0,
    pct_urnas       REAL DEFAULT 0.0,
    situacao        TEXT DEFAULT ''
);
"""

DDL_BOLETINS_URNA = """
CREATE TABLE IF NOT EXISTS boletins_urna (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    zona            TEXT NOT NULL,
    secao           TEXT NOT NULL,
    cargo_cod       TEXT NOT NULL,
    candidato_num   INTEGER NOT NULL,
    votos_bu        INTEGER NOT NULL,
    importado_em    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    auditado        INTEGER DEFAULT 1
);
"""

DDL_SNAPSHOTS_META = """
CREATE TABLE IF NOT EXISTS snapshots_meta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cargo_cod       TEXT NOT NULL,
    snapshot_ts     TIMESTAMP NOT NULL,
    urnas_apuradas  INTEGER DEFAULT 0,
    urnas_total     INTEGER DEFAULT 0,
    votos_validos   INTEGER DEFAULT 0,
    votos_brancos   INTEGER DEFAULT 0,
    votos_nulos     INTEGER DEFAULT 0,
    total_votos     INTEGER DEFAULT 0
);
"""

ALL_DDL = [
    DDL_CANDIDATOS,
    DDL_RESULTADOS,
    DDL_BOLETINS_URNA,
    DDL_SNAPSHOTS_META,
]
