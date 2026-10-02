"""Scoring por cita, semáforo y advertencia graduada del protocolo VVCA."""
from __future__ import annotations

from typing import Optional

# R4c — Alcance explícito de la verificación automatizada (Capa 1). Un 🟢 acredita SOLO esto:
# no que el precepto diga lo que el escrito afirma ni que sea pertinente al caso (Capa 2).
ALCANCE_NORMATIVA = "existencia y ubicación del precepto en el corpus local"
# R4d: el rubro ya no se coteja por coincidencia léxica sino por igualdad literal normalizada
# (NFKD sin acentos, mayúsculas ni signos). Sin rubro invocado no hay cotejo del rubro.
ALCANCE_JURISPRUDENCIA = (
    "existencia del registro en el corpus local de jurisprudencia y coincidencia literal "
    "(normalizada) del rubro invocado"
)
ALCANCE_JURISPRUDENCIA_SIN_RUBRO = (
    "existencia del registro en el corpus local de jurisprudencia; sin cotejo del rubro (el "
    "escrito no lo transcribe o la fuente no lo registra)"
)
# R4c (R4-D12) — Semáforo neutro de una dimensión sin citas: ni 🟢 ni 🔴 (no hubo qué verificar).
SEMAFORO_SIN_CITAS = "⚪"


def alcance_jurisprudencia(sin_cotejo_rubro: int = 0) -> str:
    """Alcance de la verificación de tesis del resumen (R4d): el de siempre o, si alguna tesis
    localizada quedó sin cotejo del rubro, cuántas solo acreditan la existencia del registro."""
    if not sin_cotejo_rubro:
        return ALCANCE_JURISPRUDENCIA
    return (
        f"{ALCANCE_JURISPRUDENCIA}; {sin_cotejo_rubro} tesis sin cotejo del rubro: solo "
        f"existencia del registro"
    )


def vvca_score(distance: float, source_match: bool, has_source_file: bool) -> int:
    """Calcula score 0–100 desde distancia coseno y coincidencia de fuente."""
    base = round((1 - min(distance, 1.0)) * 100)
    if not source_match:
        base -= 15
    if not has_source_file:
        base -= 10
    return max(0, min(100, base))


def vvca_semaforo(score: int) -> str:
    if score >= 85:
        return "🟢"
    if score >= 60:
        return "🟡"
    return "🔴"


def semaforo_dimension(score: Optional[float], citas: int, refutadas: int = 0) -> str:
    """Semáforo de una dimensión (artículos o tesis) del resumen (R4-D12).

    Sin citas en la dimensión → semáforo neutro (no un 0 rojo: no hubo nada que verificar).
    Con citas pero sin ninguna evaluada (todas no verificables o refutadas sin evidencia) → 🔴
    si alguna quedó refutada y 🟡 si no: "no pude verificar" no es "está mal". Con puntaje, el
    semáforo del promedio de siempre (los umbrales 85/60 no cambian).
    """
    if citas == 0:
        return SEMAFORO_SIN_CITAS
    if score is None:
        return "🔴" if refutadas else "🟡"
    return vvca_semaforo(score)


def disclaimer_graduado(veredicto: dict) -> dict:
    """Devuelve una advertencia proporcional al riesgo del veredicto."""
    base = (
        "Borrador generado por Itosturre (IA). La verificación de citas (Capa 1) es "
        "automatizada y NO garantiza la pertinencia procesal ni la vigencia definitiva; "
        "la Capa 2 es criterio del abogado firmante, responsable de la versión final."
    )
    nivel = veredicto.get("semaforo", "🟡")
    razon = veredicto.get("razon", "")
    accion = veredicto.get("accion", "")
    if nivel == "🔴":
        return {
            "nivel": "🔴",
            "encabezado": "🚨 DOCUMENTO BLOQUEADO — NO PRESENTAR SIN CORREGIR",
            "texto": f"{razon}. {accion}. {base}",
            "requiere_acuse": True,
        }
    if nivel == "🟡":
        return {
            "nivel": "🟡",
            "encabezado": "⚠️ BORRADOR CON ADVERTENCIAS — REVISAR ANTES DE PRESENTAR",
            "texto": f"{razon}. {accion}. {base}",
            "requiere_acuse": True,
        }
    # R4c — El 🟢 dice qué verificó (la razón ya no menciona lo que no se citó, R4-D11) y su
    # alcance: existencia y ubicación, no que lo citado respalde lo que el escrito afirma.
    detalle = f" ({razon})" if razon else ""
    return {
        "nivel": "🟢",
        "encabezado": "✅ CITAS VERIFICADAS (Capa 1) — PENDIENTE PERTINENCIA (Capa 2)",
        "texto": (
            f"Verificación automatizada sin discrepancias{detalle}. Alcance del 🟢: "
            f"{ALCANCE_NORMATIVA} (en tesis, registro y rubro literal); no significa que lo citado "
            f"diga lo que el escrito afirma. {base}"
        ),
        "requiere_acuse": False,
    }

