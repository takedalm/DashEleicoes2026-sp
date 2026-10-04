# =============================================================================
# storage/database.py — Gerenciamento do banco de dados SQLite
# =============================================================================

import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Generator, List, Dict, Any, Optional

from config import DB_PATH
from storage.models import ALL_DDL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Conexão
# ---------------------------------------------------------------------------

@contextmanager
def get_conn() -> Generator[sqlite3.Connection, None, None]:
    """Context manager para conexão SQLite com row_factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup_database() -> None:
    """Cria todas as tabelas se não existirem."""
    with get_conn() as conn:
        for ddl in ALL_DDL:
            conn.execute(ddl)
    logger.info("Banco de dados inicializado em %s", DB_PATH)


# ---------------------------------------------------------------------------
# Candidatos
# ---------------------------------------------------------------------------

def upsert_candidato(cand: Dict[str, Any]) -> None:
    """Insere ou atualiza um candidato pelo campo 'id'."""
    sql = """
        INSERT INTO candidatos
            (id, cargo_cod, cargo_nome, numero, nome, nome_urna,
             partido, sigla_partido, foto_url, situacao_cand)
        VALUES
            (:id, :cargo_cod, :cargo_nome, :numero, :nome, :nome_urna,
             :partido, :sigla_partido, :foto_url, :situacao_cand)
        ON CONFLICT(id) DO UPDATE SET
            cargo_cod      = excluded.cargo_cod,
            cargo_nome     = excluded.cargo_nome,
            numero         = excluded.numero,
            nome           = excluded.nome,
            nome_urna      = excluded.nome_urna,
            partido        = excluded.partido,
            sigla_partido  = excluded.sigla_partido,
            foto_url       = excluded.foto_url,
            situacao_cand  = excluded.situacao_cand
    """
    with get_conn() as conn:
        conn.execute(sql, cand)


def upsert_candidatos_bulk(candidatos: List[Dict[str, Any]]) -> None:
    """Upsert em lote para lista de candidatos."""
    sql = """
        INSERT INTO candidatos
            (id, cargo_cod, cargo_nome, numero, nome, nome_urna,
             partido, sigla_partido, foto_url, situacao_cand)
        VALUES
            (:id, :cargo_cod, :cargo_nome, :numero, :nome, :nome_urna,
             :partido, :sigla_partido, :foto_url, :situacao_cand)
        ON CONFLICT(id) DO UPDATE SET
            cargo_cod      = excluded.cargo_cod,
            cargo_nome     = excluded.cargo_nome,
            numero         = excluded.numero,
            nome           = excluded.nome,
            nome_urna      = excluded.nome_urna,
            partido        = excluded.partido,
            sigla_partido  = excluded.sigla_partido,
            foto_url       = excluded.foto_url,
            situacao_cand  = excluded.situacao_cand
    """
    with get_conn() as conn:
        conn.executemany(sql, candidatos)
    logger.info("Upsert de %d candidatos concluído.", len(candidatos))


def get_candidatos(cargo_cod: Optional[str] = None) -> List[sqlite3.Row]:
    """Retorna candidatos, opcionalmente filtrados por cargo."""
    with get_conn() as conn:
        if cargo_cod:
            return conn.execute(
                "SELECT * FROM candidatos WHERE cargo_cod = ? ORDER BY numero",
                (cargo_cod,)
            ).fetchall()
        return conn.execute(
            "SELECT * FROM candidatos ORDER BY cargo_cod, numero"
        ).fetchall()


# ---------------------------------------------------------------------------
# Resultados (snapshots)
# ---------------------------------------------------------------------------

def insert_resultados_bulk(resultados: List[Dict[str, Any]]) -> None:
    """Insere um snapshot de resultados em lote."""
    sql = """
        INSERT INTO resultados
            (snapshot_ts, cargo_cod, candidato_id, numero, nome_urna,
             sigla_partido, votos_nom, votos_legenda, percentual,
             urnas_apuradas, urnas_total, pct_urnas, situacao)
        VALUES
            (:snapshot_ts, :cargo_cod, :candidato_id, :numero, :nome_urna,
             :sigla_partido, :votos_nom, :votos_legenda, :percentual,
             :urnas_apuradas, :urnas_total, :pct_urnas, :situacao)
    """
    with get_conn() as conn:
        conn.executemany(sql, resultados)
    logger.debug("Inseridos %d registros de resultado.", len(resultados))


def get_ultimo_snapshot(cargo_cod: str) -> List[sqlite3.Row]:
    """Retorna o snapshot mais recente para um cargo, incluindo foto_url do candidato."""
    sql = """
        SELECT r.*, c.foto_url, c.nome
        FROM resultados r
        LEFT JOIN candidatos c ON (r.candidato_id = c.id OR (r.numero = c.numero AND r.cargo_cod = c.cargo_cod))
        WHERE r.cargo_cod = ?
          AND r.snapshot_ts = (
              SELECT MAX(snapshot_ts) FROM resultados WHERE cargo_cod = ?
          )
        ORDER BY r.votos_nom DESC
    """
    with get_conn() as conn:
        return conn.execute(sql, (cargo_cod, cargo_cod)).fetchall()


def get_historico_votos(cargo_cod: str, candidato_num: int) -> List[sqlite3.Row]:
    """Retorna o histórico de votos de um candidato ao longo do tempo."""
    sql = """
        SELECT snapshot_ts, votos_nom, percentual, pct_urnas
        FROM resultados
        WHERE cargo_cod = ? AND numero = ?
        ORDER BY snapshot_ts
    """
    with get_conn() as conn:
        return conn.execute(sql, (cargo_cod, candidato_num)).fetchall()


# ---------------------------------------------------------------------------
# Boletins de Urna
# ---------------------------------------------------------------------------

def insert_boletins_urna_bulk(bus: List[Dict[str, Any]]) -> None:
    """Insere boletins de urna em lote (dados auditados)."""
    sql = """
        INSERT OR IGNORE INTO boletins_urna
            (zona, secao, cargo_cod, candidato_num, votos_bu, importado_em, auditado)
        VALUES
            (:zona, :secao, :cargo_cod, :candidato_num, :votos_bu,
             :importado_em, :auditado)
    """
    with get_conn() as conn:
        conn.executemany(sql, bus)
    logger.info("Inseridos %d boletins de urna.", len(bus))


def get_votos_auditados_por_candidato(cargo_cod: str) -> List[sqlite3.Row]:
    """Soma os votos auditados (BUs) por candidato para um cargo."""
    sql = """
        SELECT candidato_num, SUM(votos_bu) AS total_votos_auditados
        FROM boletins_urna
        WHERE cargo_cod = ?
        GROUP BY candidato_num
        ORDER BY total_votos_auditados DESC
    """
    with get_conn() as conn:
        return conn.execute(sql, (cargo_cod,)).fetchall()


# ---------------------------------------------------------------------------
# Snapshots Meta (totais por cargo)
# ---------------------------------------------------------------------------

def upsert_snapshot_meta(meta: Dict[str, Any]) -> None:
    """Insere metadados do snapshot (votos brancos, nulos, total)."""
    sql = """
        INSERT INTO snapshots_meta
            (cargo_cod, snapshot_ts, urnas_apuradas, urnas_total,
             votos_validos, votos_brancos, votos_nulos, total_votos)
        VALUES
            (:cargo_cod, :snapshot_ts, :urnas_apuradas, :urnas_total,
             :votos_validos, :votos_brancos, :votos_nulos, :total_votos)
    """
    with get_conn() as conn:
        conn.execute(sql, meta)


def get_ultima_meta(cargo_cod: str) -> Optional[sqlite3.Row]:
    """Retorna os metadados mais recentes do snapshot para um cargo."""
    sql = """
        SELECT * FROM snapshots_meta
        WHERE cargo_cod = ?
        ORDER BY snapshot_ts DESC
        LIMIT 1
    """
    with get_conn() as conn:
        return conn.execute(sql, (cargo_cod,)).fetchone()
