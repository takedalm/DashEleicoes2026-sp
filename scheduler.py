# =============================================================================
# scheduler.py — Loop de polling automático durante o pleito (8h–18h)
# Executa coleta a cada 5 minutos enquanto o pleito estiver ativo
# =============================================================================

import logging
import time
from datetime import datetime, timezone, timedelta

import schedule

from config import (
    POLL_INTERVAL_SEC,
    PLEITO_START_HOUR,
    PLEITO_END_HOUR,
    LOG_LEVEL,
    LOG_FILE,
)
from storage.database import setup_database
from collector.tse_api import coletar_resultados, descobrir_codigo_pleito

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Fuso horário de Brasília (UTC-3)
TZ_BRASILIA = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# Funções de controle
# ---------------------------------------------------------------------------

def _agora_brasilia() -> datetime:
    return datetime.now(tz=TZ_BRASILIA)


def _pleito_ativo() -> bool:
    """Retorna True se o horário atual estiver dentro do período do pleito."""
    agora = _agora_brasilia()
    return PLEITO_START_HOUR <= agora.hour < PLEITO_END_HOUR


def _segundos_ate_inicio() -> float:
    """Calcula quantos segundos faltam para o início do pleito."""
    agora = _agora_brasilia()
    inicio = agora.replace(hour=PLEITO_START_HOUR, minute=0, second=0, microsecond=0)
    if agora >= inicio:
        return 0.0
    delta = (inicio - agora).total_seconds()
    return delta


# ---------------------------------------------------------------------------
# Job de coleta
# ---------------------------------------------------------------------------

_ciclo_contador = 0


def job_coleta() -> None:
    """Job executado a cada ciclo pelo scheduler."""
    global _ciclo_contador

    if not _pleito_ativo():
        hora = _agora_brasilia().strftime("%H:%M")
        logger.info("Pleito não ativo no momento (%s BRT). Pulando coleta.", hora)
        return

    _ciclo_contador += 1
    inicio = time.monotonic()
    logger.info("=== Ciclo de coleta #%d ===", _ciclo_contador)

    try:
        totais = coletar_resultados()
        duracao = time.monotonic() - inicio

        for cargo, n in totais.items():
            logger.info("  %-10s → %d candidatos atualizados", cargo, n)

        logger.info("Ciclo #%d concluído em %.1fs", _ciclo_contador, duracao)

    except Exception as e:
        logger.exception("Erro no ciclo de coleta #%d: %s", _ciclo_contador, e)


# ---------------------------------------------------------------------------
# Pré-checagem: descobrir código do pleito
# ---------------------------------------------------------------------------

def pre_check() -> None:
    """Verifica conectividade com TSE e descobre código de pleito."""
    logger.info("=== PRÉ-CHECAGEM ===")
    cod = descobrir_codigo_pleito()
    if cod:
        import os
        os.environ["TSE_PLEITO_1T"] = cod
        logger.info("✅ Código do pleito 2026 descoberto: %s", cod)
    else:
        logger.warning(
            "⚠️  Não foi possível descobrir o código do pleito via config.json. "
            "Usando valor padrão do config.py. "
            "Defina a variável de ambiente TSE_PLEITO_1T se necessário."
        )


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def run() -> None:
    """Inicia o scheduler de polling."""
    logger.info("="*60)
    logger.info("Scheduler iniciado — Eleições 2026 SP")
    logger.info("Período ativo: %dh–%dh (BRT)", PLEITO_START_HOUR, PLEITO_END_HOUR)
    logger.info("Intervalo de coleta: %d segundos", POLL_INTERVAL_SEC)
    logger.info("="*60)

    # Setup do banco
    setup_database()
    logger.info("Banco de dados pronto.")

    # Pré-checagem
    pre_check()

    # Aguarda início do pleito se necessário
    segundos = _segundos_ate_inicio()
    if segundos > 0:
        logger.info(
            "⏰ Pleito começa em %.0f minutos (%.0fs). Aguardando...",
            segundos / 60, segundos
        )
        time.sleep(segundos)

    # Agenda o job
    intervalo_min = POLL_INTERVAL_SEC // 60
    if intervalo_min >= 1:
        schedule.every(intervalo_min).minutes.do(job_coleta)
    else:
        schedule.every(POLL_INTERVAL_SEC).seconds.do(job_coleta)

    logger.info("Job agendado a cada %d minutos.", intervalo_min or 1)

    # Primeiro ciclo imediato
    job_coleta()

    # Loop
    try:
        while True:
            agora = _agora_brasilia()

            # Encerra após o fim do período
            if agora.hour >= PLEITO_END_HOUR:
                logger.info(
                    "Pleito encerrado (%s BRT). Executando último ciclo e encerrando.",
                    agora.strftime("%H:%M")
                )
                job_coleta()
                break

            schedule.run_pending()
            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Scheduler interrompido pelo usuário (Ctrl+C).")

    logger.info("Scheduler finalizado. Total de ciclos: %d", _ciclo_contador)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
    run()
