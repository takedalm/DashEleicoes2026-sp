# =============================================================================
# dashboard/app.py — Dashboard Streamlit · Eleições 2026 SP
# =============================================================================

import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timezone

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Garante que o root do projeto está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CARGOS, COD_MUNICIPIO, NOME_MUNICIPIO
from storage.database import setup_database, get_ultima_meta
from processor.eleitos import enriquecer_resultado
from processor.auditoria import auditar_cargo

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Eleições 2026 — São Paulo",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS customizado
# ---------------------------------------------------------------------------

st.markdown("""
<style>
    .eleito-badge    { background:#1a7a1a; color:white; padding:3px 10px; border-radius:12px; font-size:0.85rem; }
    .naoeeleito-badge{ background:#c0392b; color:white; padding:3px 10px; border-radius:12px; font-size:0.85rem; }
    .apurando-badge  { background:#7f8c8d; color:white; padding:3px 10px; border-radius:12px; font-size:0.85rem; }
    .segundo-badge   { background:#e67e22; color:white; padding:3px 10px; border-radius:12px; font-size:0.85rem; }
    .divergente-row  { background:#fff3cd !important; }
    .metric-card     { background:#f8f9fa; border-radius:8px; padding:12px; }
    h1               { color:#1a3c6e; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Inicialização
# ---------------------------------------------------------------------------

setup_database()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

POLO_ICONS = {
    "PR":      "🏛️",
    "GOV":     "🏢",
    "SEN":     "🎙️",
    "DEP_FED": "🏠",
    "DEP_EST": "🏛",
}

CARGO_LABELS = {k: f"{POLO_ICONS.get(k,'')} {v['nome']}" for k, v in CARGOS.items()}


@st.cache_data(ttl=60)   # atualiza cache a cada 60 segundos
def carregar_resultado(cargo_cod: str) -> pd.DataFrame:
    """Carrega e retorna o snapshot mais recente para um cargo."""
    dados = enriquecer_resultado(cargo_cod)
    if not dados:
        return pd.DataFrame()
    return pd.DataFrame(dados)


@st.cache_data(ttl=60)
def carregar_auditoria(cargo_cod: str) -> dict:
    """Carrega resultado da auditoria BU vs TSE para um cargo."""
    return auditar_cargo(cargo_cod)


@st.cache_data(ttl=60)
def carregar_meta(cargo_cod: str) -> dict:
    """Carrega metadados do snapshot mais recente."""
    row = get_ultima_meta(cargo_cod)
    return dict(row) if row else {}


def formatar_numero(n: int) -> str:
    """Formata número com separador de milhar."""
    return f"{n:,.0f}".replace(",", ".")


def cor_barra(situacao: str) -> str:
    """Retorna cor da barra conforme situação."""
    s = situacao.lower()
    if "eleito" in s and "não" not in s and "2º" not in s:
        return "#1a7a1a"
    if "2º turno" in s:
        return "#e67e22"
    return "#c0392b"


# ---------------------------------------------------------------------------
# Componentes de UI
# ---------------------------------------------------------------------------

def render_progress_bar(cargo_cod: str) -> None:
    """Exibe barra de progresso da apuração."""
    meta = carregar_meta(cargo_cod)
    if not meta:
        st.info("⏳ Aguardando início da apuração...")
        return

    apuradas = meta.get("urnas_apuradas", 0)
    total    = meta.get("urnas_total", 0)
    pct      = round(apuradas / total * 100, 1) if total else 0.0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("🗳️ Urnas Apuradas", f"{formatar_numero(apuradas)} / {formatar_numero(total)}")
    col2.metric("📊 % Apurado", f"{pct:.1f}%")
    col3.metric("✅ Votos Válidos",  formatar_numero(meta.get("votos_validos", 0)))
    col4.metric("Total de Votos",    formatar_numero(meta.get("total_votos", 0)))

    st.progress(pct / 100)


def render_tabela_resultados(df: pd.DataFrame, cargo_cod: str) -> None:
    """Exibe tabela de resultados por candidato com filtros de busca."""
    if df.empty:
        st.warning("Nenhum candidato ou resultado disponível ainda.")
        return

    # Auditoria para o cargo
    aud = carregar_auditoria(cargo_cod)
    aud_map = {c["numero"]: c for c in aud.get("candidatos", [])}

    # --- BARRA DE FILTROS INTERATIVOS ---
    with st.expander("🔍 **Filtros de Candidatos (Nome, Número, Partido, Situação)**", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns([2, 1, 2, 2])

        with f_col1:
            busca_nome = st.text_input("Buscar por Nome", key=f"nome_{cargo_cod}", placeholder="Ex: Tarcísio, Lula, Boulos...")

        with f_col2:
            busca_numero = st.text_input("Número", key=f"num_{cargo_cod}", placeholder="Ex: 22, 13...")

        with f_col3:
            todos_partidos = sorted(list(set(df["sigla_partido"].dropna().unique())))
            filtro_partidos = st.multiselect("Filtrar Partido", todos_partidos, key=f"part_{cargo_cod}", placeholder="Todos os partidos")

        with f_col4:
            todas_situacoes = sorted(list(set(df["situacao_display"].dropna().unique())))
            filtro_situacao = st.multiselect("Filtrar Situação", todas_situacoes, key=f"sit_{cargo_cod}", placeholder="Todas as situações")

    # Aplicação dos filtros no DataFrame
    df_filtrado = df.copy()

    if busca_nome:
        term = busca_nome.strip().upper()
        # Busca no nome_urna ou no nome completo se disponível
        mask = df_filtrado["nome_urna"].str.upper().str.contains(term, na=False)
        if "nome" in df_filtrado.columns:
            mask = mask | df_filtrado["nome"].str.upper().str.contains(term, na=False)
        df_filtrado = df_filtrado[mask]

    if busca_numero:
        num_clean = "".join(filter(str.isdigit, busca_numero))
        if num_clean:
            df_filtrado = df_filtrado[df_filtrado["numero"].astype(str).str.startswith(num_clean)]

    if filtro_partidos:
        df_filtrado = df_filtrado[df_filtrado["sigla_partido"].isin(filtro_partidos)]

    if filtro_situacao:
        df_filtrado = df_filtrado[df_filtrado["situacao_display"].isin(filtro_situacao)]

    st.caption(f"Mostrando **{len(df_filtrado)}** de **{len(df)}** candidatos encontrados.")

    if df_filtrado.empty:
        st.info("Nenhum candidato encontrado com os filtros selecionados.")
        return

    rows_html = []
    for _, row in df_filtrado.iterrows():
        numero    = int(row.get("numero", 0))
        nome      = row.get("nome_urna", "—")
        partido   = row.get("sigla_partido", "—")
        votos     = int(row.get("votos_nom", 0))
        pct       = float(row.get("pct_votos_validos", 0))
        situacao  = row.get("situacao_display", "⏳ Apurando...")

        # Votos auditados (BU)
        aud_info  = aud_map.get(numero, {})
        votos_bu  = aud_info.get("votos_auditados", "—")
        divergente= aud_info.get("divergente", False)
        diff      = aud_info.get("divergencia", 0)

        if isinstance(votos_bu, int):
            votos_bu_str = formatar_numero(votos_bu)
            diff_str     = f"{diff:+,}".replace(",", ".") if divergente else "✅"
        else:
            votos_bu_str = "Aguardando BU"
            diff_str     = "—"

        rows_html.append({
            "🏅 #":         numero,
            "Candidato":    nome,
            "Partido":      partido,
            "Votos":        formatar_numero(votos),
            "% Votos Vál.": f"{pct:.2f}%",
            "Votos (BU ✓)": votos_bu_str,
            "Diff. Audit.": diff_str,
            "Situação":     situacao,
        })

    df_display = pd.DataFrame(rows_html)

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Situação": st.column_config.TextColumn("Situação", width="medium"),
        },
    )


def render_grafico_barras(df: pd.DataFrame, cargo_cod: str) -> None:
    """Gráfico de barras horizontal por candidato."""
    if df.empty:
        return

    # Top 20 candidatos para cargos com muitos concorrentes
    df_plot = df.nlargest(20, "votos_nom").copy()
    df_plot["label"] = df_plot["nome_urna"] + " (" + df_plot["sigla_partido"] + ")"
    df_plot["cor"]   = df_plot["situacao_display"].apply(cor_barra)

    fig = px.bar(
        df_plot,
        x="votos_nom",
        y="label",
        orientation="h",
        color="cor",
        color_discrete_map="identity",
        text=df_plot["pct_votos_validos"].apply(lambda x: f"{x:.1f}%"),
        labels={"votos_nom": "Votos", "label": "Candidato"},
        title=f"Top {len(df_plot)} candidatos — {CARGOS[cargo_cod]['nome']}",
    )
    fig.update_layout(
        showlegend=False,
        yaxis={"categoryorder": "total ascending"},
        height=max(400, len(df_plot) * 30 + 100),
        plot_bgcolor="white",
    )
    fig.update_traces(textposition="outside")

    st.plotly_chart(fig, use_container_width=True)


def render_status_auditoria(cargo_cod: str) -> None:
    """Exibe painel de status da auditoria."""
    aud = carregar_auditoria(cargo_cod)
    status = aud.get("status", "sem_bu")

    if status == "sem_bu":
        st.info("🔍 **Auditoria:** Boletins de Urna ainda não importados. "
                "Execute `collector/dados_abertos.py` após as 17h.")
    elif status == "ok":
        st.success(f"✅ **Auditoria OK** — {aud['mensagem']}")
    elif status == "divergencia":
        st.error(f"⚠️ **DIVERGÊNCIA DETECTADA** — {aud['mensagem']}")

        # Tabela de divergências
        divs = [c for c in aud["candidatos"] if c["divergente"]]
        if divs:
            df_div = pd.DataFrame(divs)[["numero", "nome_urna", "votos_totalizados",
                                          "votos_auditados", "divergencia"]]
            df_div.columns = ["Número", "Candidato", "Votos TSE", "Votos BU", "Diferença"]
            st.dataframe(df_div, use_container_width=True, hide_index=True)
    else:
        st.warning(f"⚠️ Status: {status}")


# ---------------------------------------------------------------------------
# Layout principal
# ---------------------------------------------------------------------------

def main() -> None:
    # Cabeçalho
    st.title("🗳️ Eleições 2026 — São Paulo")
    st.markdown(
        f"**Município:** {NOME_MUNICIPIO} (código `{COD_MUNICIPIO}`) · "
        f"**Atualização automática:** a cada 60s · "
        f"**Última atualização:** `{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}`"
    )
    st.divider()

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Controles")
        auto_refresh = st.toggle("🔄 Atualização automática", value=True)
        refresh_interval = st.slider("Intervalo (segundos)", 30, 600, 60, step=30)

        st.divider()
        st.markdown("### 📋 Cargos monitorados")
        for k, v in CARGOS.items():
            st.markdown(f"- {POLO_ICONS.get(k,'')} **{v['nome']}**")

        st.divider()
        if st.button("🔄 Atualizar agora"):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.caption("Fonte: TSE · Dados Oficiais · Eleições 2026")

    # Abas por cargo
    tabs = st.tabs([CARGO_LABELS[k] for k in CARGOS])

    for tab, cargo_cod in zip(tabs, CARGOS.keys()):
        with tab:
            st.subheader(f"{POLO_ICONS.get(cargo_cod,'')} {CARGOS[cargo_cod]['nome']}")

            # Progresso da apuração
            render_progress_bar(cargo_cod)
            st.divider()

            # Dados
            df = carregar_resultado(cargo_cod)

            col_table, col_chart = st.columns([1, 1])

            with col_table:
                st.markdown("#### 📋 Resultados por Candidato")
                render_tabela_resultados(df, cargo_cod)

            with col_chart:
                st.markdown("#### 📊 Votos por Candidato")
                render_grafico_barras(df, cargo_cod)

            st.divider()
            st.markdown("#### 🔍 Status da Auditoria (BU vs. Totalização)")
            render_status_auditoria(cargo_cod)

    # Auto-refresh
    if auto_refresh:
        time.sleep(refresh_interval)
        st.cache_data.clear()
        st.rerun()


if __name__ == "__main__":
    main()
