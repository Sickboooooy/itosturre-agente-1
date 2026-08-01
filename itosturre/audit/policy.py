"""Scoring por cita, semáforo y advertencia graduada del protocolo VVCA."""
from __future__ import annotations


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
    return {
        "nivel": "🟢",
        "encabezado": "✅ CITAS VERIFICADAS (Capa 1) — PENDIENTE PERTINENCIA (Capa 2)",
        "texto": f"Verificación automatizada sin discrepancias. {base}",
        "requiere_acuse": False,
    }

