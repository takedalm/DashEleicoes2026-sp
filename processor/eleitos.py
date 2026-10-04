# =============================================================================
# processor/eleitos.py — Regras de eleição por cargo
# Calcula quem foi eleito com base no snapshot mais recente
# =============================================================================

import logging
from typing import List, Dict, Any, Optional

from config import CARGOS
from storage.database import get_ultimo_snapshot, get_ultima_meta

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Resultados enriquecidos
# ---------------------------------------------------------------------------

def enriquecer_resultado(cargo_cod: str) -> List[Dict[str, Any]]:
    """
    Retorna o snapshot mais recente de um cargo com colunas calculadas:
    - votos_auditados (do BU, se disponível)
    - eleito (bool)
    - situacao_calculada (texto amigável)
    - pct_votos_validos
    """
    rows = get_ultimo_snapshot(cargo_cod)
    if not rows:
        # Fallback pré-pleito: se ainda não houver apuração, exibe os candidatos cadastrados
        from storage.database import get_candidatos
        cands = get_candidatos(cargo_cod)
        if not cands:
            return []
        resultado = []
        for c in cands:
            c = dict(c)
            resultado.append({
                "numero": c["numero"],
                "nome_urna": c["nome_urna"],
                "nome": c["nome"],
                "sigla_partido": c["sigla_partido"],
                "partido": c["partido"],
                "foto_url": c.get("foto_url", ""),
                "votos_nom": 0,
                "percentual": 0.0,
                "pct_votos_validos": 0.0,
                "situacao": c.get("situacao_cand", "Registrado"),
                "situacao_display": "⏳ Aguardando Apuração",
                "eleito": False,
            })
        return resultado

    meta = get_ultima_meta(cargo_cod)
    votos_validos = meta["votos_validos"] if meta and meta["votos_validos"] else 0

    resultado = []
    for row in rows:
        d = dict(row)
        # Percentual sobre votos válidos (recalculado localmente se necessário)
        if votos_validos > 0:
            d["pct_votos_validos"] = round(d["votos_nom"] / votos_validos * 100, 2)
        else:
            d["pct_votos_validos"] = d.get("percentual", 0.0)

        # Situação já vem do TSE — normaliza o texto
        sit = (d.get("situacao") or "").strip().lower()
        d["eleito"] = _is_eleito(sit)
        d["situacao_display"] = _situacao_display(sit)

        resultado.append(d)

    # Aplica regra de eleição local para cargos majoritários (como fallback)
    resultado = _aplicar_regra_majoritaria(cargo_cod, resultado, votos_validos)

    return resultado


# ---------------------------------------------------------------------------
# Determinação de eleito
# ---------------------------------------------------------------------------

def _is_eleito(situacao_raw: str) -> bool:
    """Retorna True se a situação indica eleição."""
    return "eleito" in situacao_raw and "não" not in situacao_raw


def _situacao_display(situacao_raw: str) -> str:
    """Normaliza a string de situação para exibição na dashboard."""
    s = situacao_raw.lower()
    if "eleito por qe" in s or ("eleito" in s and "não" not in s):
        return "✅ Eleito"
    if "2º turno" in s or "segundo turno" in s:
        return "🔄 2º Turno"
    if "não eleito" in s or "nao eleito" in s:
        return "❌ Não eleito"
    if s == "":
        return "⏳ Apurando..."
    return s.title()


# ---------------------------------------------------------------------------
# Regras específicas por cargo (fallback quando TSE não indica situacao)
# ---------------------------------------------------------------------------

def _aplicar_regra_majoritaria(
    cargo_cod: str,
    resultado: List[Dict],
    votos_validos: int,
) -> List[Dict]:
    """
    Para cargos majoritários (PR, GOV, SEN), aplica a regra localmente
    como fallback — útil quando a apuração ainda está em curso e o TSE
    ainda não preencheu o campo 'situacao'.
    """
    if cargo_cod not in ("PR", "GOV", "SEN"):
        return resultado   # proporcionais: confiar apenas no TSE

    if votos_validos == 0:
        return resultado   # sem dados suficientes

    # Já tem situação definida pelo TSE?
    if any(r["situacao"].strip() for r in resultado):
        return resultado

    # Ordena por votos
    resultado_ord = sorted(resultado, key=lambda x: x["votos_nom"], reverse=True)

    if cargo_cod in ("PR", "GOV"):
        # Maioria absoluta = mais de 50% dos votos válidos
        lider = resultado_ord[0]
        if lider["votos_nom"] > votos_validos * 0.5:
            lider["eleito"]          = True
            lider["situacao_display"] = "✅ Eleito"
        else:
            # Sem maioria absoluta → possível 2º turno
            for r in resultado_ord[:2]:
                r["situacao_display"] = "🔄 Possível 2º Turno"
            for r in resultado_ord[2:]:
                r["situacao_display"] = "❌ Eliminado"

    elif cargo_cod == "SEN":
        # Maioria simples: 1 vaga em 2026 (SP) → mais votado
        resultado_ord[0]["eleito"]          = True
        resultado_ord[0]["situacao_display"] = "✅ Eleito"
        for r in resultado_ord[1:]:
            r["situacao_display"] = "❌ Não eleito"

    return resultado_ord


# ---------------------------------------------------------------------------
# Resumo geral (todos os cargos)
# ---------------------------------------------------------------------------

def resumo_eleitos() -> Dict[str, List[Dict]]:
    """Retorna dict {cargo_cod: [candidatos_enriquecidos]} para a dashboard."""
    return {cargo_cod: enriquecer_resultado(cargo_cod) for cargo_cod in CARGOS}
