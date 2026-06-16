"""
scoring_vvca.py — Validación VVCA para documentos legales Itosturre.

Dos scores independientes (no promediados):
  - score_rag:  validación ESTÁTICA  — artículos contra corpus ChromaDB
  - score_sjf:  validación DINÁMICA  — tesis contra SJF en tiempo real

El veredicto global es una decisión binaria con razón explícita,
no un número compuesto. Las tesis rojas son bloqueantes por sí solas.
"""

from __future__ import annotations


def veredicto_global(
    score_rag: float,
    score_sjf: float,
    tesis_rojas: int,
    tesis_total: int,
) -> dict:
    """
    Veredicto binario con razón explícita. No promedia los dos scores.

    Reglas de precedencia (se evalúan en orden):
      1. Cualquier tesis roja → ROJO bloqueante (independiente del RAG)
      2. RAG < 70             → AMARILLO (advertencia, no bloqueo)
      3. Sin problemas        → VERDE

    Args:
        score_rag:     promedio VVCA de artículos verificados (0-100)
        score_sjf:     promedio VVCA de tesis verificadas (0 si ninguna ok)
        tesis_rojas:   tesis con mismatch de rubro o no encontradas
        tesis_total:   total de tesis invocadas en el documento

    Returns:
        dict con apto, semaforo, razon, accion
    """
    if tesis_rojas > 0:
        return {
            "apto": False,
            "semaforo": "🔴",
            "razon": (
                f"{tesis_rojas}/{tesis_total} tesis con rubro discrepante — "
                "USO PROCESAL PROHIBIDO"
            ),
            "accion": "Sustituir tesis antes de cualquier uso procesal",
        }

    if score_rag < 70:
        return {
            "apto": False,
            "semaforo": "🟡",
            "razon": f"Artículos con verificación insuficiente (RAG: {score_rag})",
            "accion": "Revisar referencias normativas contra corpus oficial",
        }

    return {
        "apto": True,
        "semaforo": "🟢",
        "razon": "Normativa y jurisprudencia verificadas",
        "accion": "Proceder con revisión de pertinencia procesal por el operador",
    }
