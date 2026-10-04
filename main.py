# =============================================================================
# main.py — Entrypoint principal do projeto Eleições 2026 SP
# =============================================================================

"""
Uso:
    python main.py candidatos        # Coleta candidatos (executar HOJE)
    python main.py scheduler         # Inicia polling (executar amanhã às 8h)
    python main.py dashboard         # Abre a dashboard Streamlit
    python main.py bu                # Importa Boletins de Urna (pós-17h)
    python main.py auditoria         # Executa auditoria BU vs TSE
    python main.py setup             # Apenas inicializa o banco de dados
    python main.py check             # Testa conectividade com TSE
"""

import sys
import subprocess
import logging
from pathlib import Path

# Força stdout/stderr em UTF-8 no Windows (evita UnicodeEncodeError com emojis)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Garante root no path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from config import LOG_LEVEL, LOG_FILE
from storage.database import setup_database

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


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def cmd_setup() -> None:
    """Inicializa o banco de dados."""
    logger.info("Inicializando banco de dados...")
    setup_database()
    print("✅ Banco de dados inicializado.")


def cmd_candidatos() -> None:
    """Coleta candidatos do DivulgaCandContas e salva no banco."""
    from collector.candidatos import coletar_todos_candidatos
    setup_database()
    n = coletar_todos_candidatos()
    print(f"✅ {n} candidatos coletados e salvos.")


def cmd_check() -> None:
    """Testa conectividade com a CDN do TSE."""
    from collector.tse_api import descobrir_codigo_pleito, coletar_resultados
    print("🔍 Testando conectividade com TSE CDN...\n")
    cod = descobrir_codigo_pleito()
    if cod:
        print(f"✅ Código do pleito 2026: {cod}")
    else:
        print("⚠️  Não foi possível descobrir o código do pleito.")
        print("   → Defina TSE_PLEITO_1T=<codigo> como variável de ambiente.")

    print("\n🔍 Testando coleta de resultados...")
    setup_database()
    totais = coletar_resultados()
    print("\nResultados por cargo:")
    for cargo, n in totais.items():
        status = f"{n} candidatos" if n > 0 else "sem dados (pleito não iniciado)"
        print(f"  {cargo:<12} → {status}")


def cmd_scheduler() -> None:
    """Inicia o loop de polling automático."""
    from scheduler import run
    run()


def cmd_dashboard() -> None:
    """Inicia a dashboard Streamlit."""
    app_path = ROOT / "dashboard" / "app.py"
    print(f"🚀 Iniciando dashboard: {app_path}")
    print("   → Acesse: http://localhost:8501\n")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", str(app_path)],
        check=True,
    )


def cmd_bu() -> None:
    """Importa Boletins de Urna do Portal de Dados Abertos do TSE."""
    from collector.dados_abertos import importar_bu_zip, descobrir_url_bu_via_ckan, URL_BU_ZIP
    setup_database()
    print("📥 Importando Boletins de Urna — SP 2026...")
    url = URL_BU_ZIP
    url_ckan = descobrir_url_bu_via_ckan()
    if url_ckan:
        print(f"   → URL CKAN encontrada: {url_ckan}")
        url = url_ckan
    else:
        print(f"   → Usando URL padrão: {url}")

    total = importar_bu_zip(url)
    print(f"\n✅ {total} registros de BU importados.")


def cmd_auditoria() -> None:
    """Executa auditoria BU vs. Totalização TSE."""
    from processor.auditoria import auditar_todos
    print("🔍 Executando auditoria...\n")
    resultados = auditar_todos()

    print(f"\n{'='*70}")
    print(f"{'CARGO':<12} {'STATUS':<20} {'DIVERGÊNCIAS':>14}")
    print(f"{'─'*70}")
    for cargo, res in resultados.items():
        print(f"{cargo:<12} {res['status']:<20} {res['total_divergencias']:>14}")

    total_divs = sum(r["total_divergencias"] for r in resultados.values())
    print(f"{'─'*70}")
    print(f"{'TOTAL':<12} {'':20} {total_divs:>14}")

    if total_divs == 0:
        print("\n✅ Auditoria concluída: NENHUMA DIVERGÊNCIA encontrada.")
    else:
        print(f"\n⚠️  Auditoria concluída: {total_divs} DIVERGÊNCIA(S) detectada(s).")
        print("   Consulte os logs para detalhes.")


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

COMMANDS = {
    "setup":     cmd_setup,
    "candidatos": cmd_candidatos,
    "check":     cmd_check,
    "scheduler": cmd_scheduler,
    "dashboard": cmd_dashboard,
    "bu":        cmd_bu,
    "auditoria": cmd_auditoria,
}

HELP = __doc__


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(HELP)
        print("Comandos disponíveis:")
        for cmd in COMMANDS:
            print(f"  python main.py {cmd}")
        sys.exit(0)

    cmd = sys.argv[1].lower()
    if cmd not in COMMANDS:
        print(f"❌ Comando desconhecido: '{cmd}'\n")
        print(HELP)
        sys.exit(1)

    try:
        COMMANDS[cmd]()
    except KeyboardInterrupt:
        print("\n⚠️  Interrompido pelo usuário.")
        sys.exit(0)
    except Exception as e:
        logger.exception("Erro ao executar comando '%s': %s", cmd, e)
        sys.exit(1)


if __name__ == "__main__":
    main()
