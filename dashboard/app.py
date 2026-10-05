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
from storage.database import setup_database, get_ultima_meta, get_ultimo_timestamp_snapshot
from processor.eleitos import enriquecer_resultado
from processor.auditoria import auditar_cargo
from collector.tse_api import coletar_resultados

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

    # Inicializa estado do cargo ativo se não existir
    if "cargo_ativo" not in st.session_state:
        st.session_state["cargo_ativo"] = "PR"

    # --- VERIFICAÇÃO AUTOMÁTICA DO SNAPSHOT (A CADA 20 MINUTOS) ---
    ultimo_ts_str = get_ultimo_timestamp_snapshot()
    precisa_coletar_auto = False

    if not ultimo_ts_str:
        precisa_coletar_auto = True
    else:
        try:
            ultimo_dt = datetime.fromisoformat(ultimo_ts_str)
            if ultimo_dt.tzinfo is None:
                ultimo_dt = ultimo_dt.replace(tzinfo=timezone.utc)
            minutos_passados = (datetime.now(tz=timezone.utc) - ultimo_dt).total_seconds() / 60
            if minutos_passados >= 20:
                precisa_coletar_auto = True
        except Exception:
            pass

    if precisa_coletar_auto:
        with st.spinner("📥 Mais de 20 min desde o último snapshot. Coletando novas parciais do TSE..."):
            try:
                coletar_resultados()
                st.cache_data.clear()
            except Exception as e:
                logger.error("Erro na auto-coleta de 20 min: %s", e)

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Controles")

        # Botão de coleta direta no Streamlit
        if st.button("📥 Coletar dados do TSE agora", use_container_width=True, type="primary"):
            with st.spinner("Conectando ao centro de dados do TSE..."):
                try:
                    totais = coletar_resultados()
                    total_cand = sum(totais.values())
                    st.cache_data.clear()
                    st.success(f"Coleta concluída! {total_cand} candidatos atualizados.")
                    time.sleep(1)
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao coletar: {e}")

        auto_refresh = st.toggle("🔄 Atualização automática", value=True)
        refresh_interval = st.slider("Intervalo de tela (segundos)", 30, 600, 60, step=30)

        st.divider()
        st.markdown("### 📋 Navegação Rápida")
        st.caption("Clique no cargo para ir direto à visão:")

        for k, v in CARGOS.items():
            label = f"{POLO_ICONS.get(k,'')} {v['nome']}"
            is_active = (st.session_state["cargo_ativo"] == k)
            btn_type = "primary" if is_active else "secondary"
            if st.button(label, key=f"nav_btn_{k}", use_container_width=True, type=btn_type):
                st.session_state["cargo_ativo"] = k
                st.rerun()

        st.divider()
        if st.button("🔄 Atualizar tela agora", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.caption("Fonte: TSE · Dados Oficiais · Eleições 2026")

    # Lista de chaves dos cargos
    lista_cargos = list(CARGOS.keys())
    indice_ativo = lista_cargos.index(st.session_state["cargo_ativo"]) if st.session_state["cargo_ativo"] in lista_cargos else 0

    # Seletor superior sincronizado com o menu lateral
    cargo_cod = st.radio(
        "Navegue entre os cargos:",
        options=lista_cargos,
        format_func=lambda k: CARGO_LABELS[k],
        index=indice_ativo,
        horizontal=True,
        label_visibility="collapsed",
        key="radio_cargo_selector",
    )

    # Mantém o session_state sempre atualizado com a escolha do radio
    if cargo_cod != st.session_state["cargo_ativo"]:
        st.session_state["cargo_ativo"] = cargo_cod
        st.rerun()

    # Dados do cargo selecionado
    df = carregar_resultado(cargo_cod)

    # Identifica candidato em destaque para exibir no Card (baseado no filtro de busca ou 1º colocado)
    cand_destaque = None
    termo_busca = st.session_state.get(f"nome_{cargo_cod}", "").strip().upper()
    num_busca = st.session_state.get(f"num_{cargo_cod}", "").strip()

    if not df.empty:
        df_match = df.copy()
        if termo_busca:
            mask = df_match["nome_urna"].str.upper().str.contains(termo_busca, na=False)
            if "nome" in df_match.columns:
                mask = mask | df_match["nome"].str.upper().str.contains(termo_busca, na=False)
            df_match = df_match[mask]
        if num_busca:
            df_match = df_match[df_match["numero"].astype(str).str.startswith(num_busca)]

        if not df_match.empty:
            cand_destaque = df_match.iloc[0].to_dict()
        else:
            cand_destaque = df.iloc[0].to_dict()

    # --- CABEÇALHO COM CARD DE FOTO À DIREITA ---
    header_col_esq, header_col_dir = st.columns([1.5, 1])

    with header_col_esq:
        st.subheader(f"{POLO_ICONS.get(cargo_cod,'')} {CARGOS[cargo_cod]['nome']}")
        render_progress_bar(cargo_cod)

    with header_col_dir:
        if cand_destaque:
            with st.container(border=True):
                c_card_foto, c_card_info = st.columns([1, 2])
                with c_card_foto:
                    foto_path = cand_destaque.get("foto_url")
                    if foto_path and Path(foto_path).exists():
                        st.image(str(foto_path), use_container_width=True)
                    else:
                        st.markdown("<div style='font-size:3.5rem; text-align:center;'>👤</div>", unsafe_allow_html=True)

                with c_card_info:
                    st.markdown(f"### {cand_destaque.get('nome_urna', '—')}")
                    st.markdown(f"**Partido:** {cand_destaque.get('sigla_partido', '—')} · **Nº** `{cand_destaque.get('numero', '—')}`")
                    votos_str = formatar_numero(cand_destaque.get('votos_nom', 0))
                    pct_str = f"{cand_destaque.get('pct_votos_validos', 0):.2f}%"
                    sit_str = cand_destaque.get('situacao_display', '⏳ Aguardando')
                    if cand_destaque.get('votos_nom', 0) > 0:
                        st.markdown(f"**Votos:** {votos_str} ({pct_str}) · {sit_str}")
                    else:
                        st.markdown(f"**Status:** {sit_str}")

    st.divider()

    # Tabelas e Gráficos
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
