# =============================================================================
# processor/auditoria.py — Cruzamento BU auditado vs. totalização TSE
# Detecta divergências entre os votos dos BUs físicos e a totalização oficial
# =============================================================================

import logging
from typing import List, Dict, Any, Optional

from config import CARGOS
from storage.database import (
    get_votos_auditados_por_candidato,
    get_ultimo_snapshot,
)

logger = logging.getLogger(__name__)

# Tolerância para divergência (0 = zero tolerância)
TOLERANCIA_VOTOS = 0


# ---------------------------------------------------------------------------
# Auditoria por cargo
# ---------------------------------------------------------------------------

def auditar_cargo(cargo_cod: str) -> Dict[str, Any]:
    """
    Cruza votos dos Boletins de Urna (auditados) com a totalização TSE.

    Retorna:
    {
        "cargo_cod": str,
        "status": "ok" | "divergencia" | "sem_bu" | "sem_totalizacao",
        "candidatos": [
            {
                "numero": int,
                "nome_urna": str,
                "votos_totalizados": int,
                "votos_auditados": int,
                "divergencia": int,       # auditados - totalizados
                "divergente": bool,
            },
            ...
        ],
        "total_divergencias": int,
    }
    """
    # Votos auditados do BU
    rows_bu = get_votos_auditados_por_candidato(cargo_cod)
    bu_map: Dict[int, int] = {
        int(row["candidato_num"]): int(row["total_votos_auditados"])
        for row in rows_bu
    }

    # Votos totalizados (último snapshot TSE)
    rows_tse = get_ultimo_snapshot(cargo_cod)
    tse_map: Dict[int, Dict] = {
        int(row["numero"]): dict(row)
        for row in rows_tse
    }

    if not bu_map:
        return {
            "cargo_cod":          cargo_cod,
            "status":             "sem_bu",
            "candidatos":         [],
            "total_divergencias": 0,
            "mensagem":           "Boletins de Urna ainda não importados.",
        }

    if not tse_map:
        return {
            "cargo_cod":          cargo_cod,
            "status":             "sem_totalizacao",
            "candidatos":         [],
            "total_divergencias": 0,
            "mensagem":           "Dados de totalização TSE não disponíveis.",
        }

    # Cruzamento
    numeros = set(bu_map.keys()) | set(tse_map.keys())
    candidatos_auditados = []
    total_divergencias   = 0

    for numero in sorted(numeros):
        votos_bu  = bu_map.get(numero, 0)
        votos_tse = tse_map.get(numero, {}).get("votos_nom", 0)
        diff      = votos_bu - votos_tse
        divergente = abs(diff) > TOLERANCIA_VOTOS

        if divergente:
            total_divergencias += 1
            logger.warning(
                "DIVERGÊNCIA | Cargo: %s | Cand: %d | BU: %d | TSE: %d | Diff: %+d",
                cargo_cod, numero, votos_bu, votos_tse, diff
            )

        candidatos_auditados.append({
            "numero":             numero,
            "nome_urna":          tse_map.get(numero, {}).get("nome_urna", str(numero)),
            "sigla_partido":      tse_map.get(numero, {}).get("sigla_partido", ""),
            "votos_totalizados":  votos_tse,
            "votos_auditados":    votos_bu,
            "divergencia":        diff,
            "divergente":         divergente,
        })

    # Ordena por votos totalizados (desc)
    candidatos_auditados.sort(key=lambda x: x["votos_totalizados"], reverse=True)

    status = "divergencia" if total_divergencias > 0 else "ok"

    return {
        "cargo_cod":          cargo_cod,
        "status":             status,
        "candidatos":         candidatos_auditados,
        "total_divergencias": total_divergencias,
        "mensagem":           f"{total_divergencias} divergência(s) detectada(s)." if total_divergencias else "✅ Auditoria OK — sem divergências.",
    }


# ---------------------------------------------------------------------------
# Auditoria completa (todos os cargos)
# ---------------------------------------------------------------------------

def auditar_todos() -> Dict[str, Dict]:
    """
    Executa auditoria para todos os cargos.
    Retorna dict {cargo_cod: resultado_auditoria}.
    """
    resultados = {}
    for cargo_cod in CARGOS:
        logger.info("Auditando cargo: %s", cargo_cod)
        resultados[cargo_cod] = auditar_cargo(cargo_cod)

    # Log resumido
    for cargo_cod, res in resultados.items():
        status = res["status"]
        divs   = res["total_divergencias"]
        logger.info("Cargo %-10s | Status: %-20s | Divergências: %d", cargo_cod, status, divs)

    return resultados


# ---------------------------------------------------------------------------
# Execução direta
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    print("=== Auditoria: BU vs. Totalização TSE ===\n")
    resultados = auditar_todos()

    for cargo, res in resultados.items():
        print(f"\n{'='*60}")
        print(f"Cargo: {cargo} | Status: {res['status']} | {res['mensagem']}")
        if res["candidatos"]:
            print(f"  {'Nome':<30} {'TSE':>10} {'BU':>10} {'Diff':>8}")
            print(f"  {'-'*60}")
            for c in res["candidatos"][:10]:
                flag = " ⚠️" if c["divergente"] else ""
                print(f"  {c['nome_urna']:<30} {c['votos_totalizados']:>10,} "
                      f"{c['votos_auditados']:>10,} {c['divergencia']:>+8,}{flag}")
