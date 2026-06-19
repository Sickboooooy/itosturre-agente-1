"""
scoring_vvca.py — Validación VVCA para documentos legales Itosturre.

Dos scores independientes (no promediados):
  - score_rag:  artículos citados contra el corpus de leyes (ChromaDB)
  - score_sjf:  tesis CITADAS en el documento contra el corpus local de jurisprudencia
                (detección de citas falsas/discrepantes — anti-alucinación)

NOTA: el scraper SJF en vivo (services/itosturre-scraper/vvca_audit.ts) es una
herramienta ESTRATÉGICA aparte — consulta el SJF en tiempo real para comparar y proponer
tesis que refuercen la planeación legal; NO alimenta este veredicto de citas.

El veredicto global es una decisión binaria con razón explícita,
no un número compuesto.

Distinción crítica entre tipos de problema en tesis:
  - tesis_discrepantes: tesis encontradas pero con rubro que no coincide → 🔴 BLOQUEANTE
    (indica alucinación o cita maliciosa — USO PROCESAL PROHIBIDO)
  - tesis_no_encontradas: tesis no localizadas en el corpus local → 🟡 ADVERTENCIA
    (el corpus puede estar incompleto, no necesariamente es una cita falsa)
"""

from __future__ import annotations


def veredicto_global(
    score_rag: float,
    score_sjf: float,
    tesis_discrepantes: int,
    tesis_no_encontradas: int,
    tesis_total: int,
) -> dict:
    """
    Veredicto binario con razón explícita. No promedia los dos scores.

    Reglas de precedencia (se evalúan en orden):
      1. tesis_discrepantes > 0  → ROJO bloqueante (rubro falsificado o equivocado)
      2. tesis_no_encontradas > 0 → AMARILLO (corpus incompleto, no necesariamente error)
      3. RAG < 70                → AMARILLO (artículos con verificación insuficiente)
      4. Sin problemas           → VERDE

    Args:
        score_rag:              promedio VVCA de artículos verificados (0-100)
        score_sjf:              promedio VVCA de tesis verificadas (0 si ninguna ok)
        tesis_discrepantes:     tesis con rubro que NO coincide con el corpus SJF real
        tesis_no_encontradas:   tesis invocadas que no se encontraron en el corpus local
        tesis_total:            total de tesis invocadas en el documento

    Returns:
        dict con apto, semaforo, razon, accion
    """
    if tesis_discrepantes > 0:
        return {
            "apto": False,
            "semaforo": "🔴",
            "razon": (
                f"{tesis_discrepantes}/{tesis_total} tesis con rubro discrepante — "
                "USO PROCESAL PROHIBIDO"
            ),
            "accion": "Sustituir tesis antes de cualquier uso procesal",
        }

    if tesis_no_encontradas > 0:
        return {
            "apto": False,
            "semaforo": "🟡",
            "razon": (
                f"{tesis_no_encontradas}/{tesis_total} tesis no verificables "
                "(ausentes del corpus local — no confirmadas como falsas)"
            ),
            "accion": "Verificar manualmente en SJF o ampliar el corpus antes de uso procesal",
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
