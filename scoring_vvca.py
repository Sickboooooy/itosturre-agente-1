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
  - tesis_discrepantes: tesis encontradas pero con rubro que no coincide o con el sentido
    invertido (R4d: cotejo literal normalizado y polaridad) → 🔴 BLOQUEANTE
    (indica alucinación o cita maliciosa — USO PROCESAL PROHIBIDO)
  - tesis_no_encontradas: tesis no localizadas en el corpus local → 🟡 ADVERTENCIA
    (el corpus puede estar incompleto, no necesariamente es una cita falsa)
"""

from __future__ import annotations

from typing import Optional

# R4c (ronda 2) introdujo esta retención TRANSITORIA: con el cotejo léxico del rubro (R4-D13,
# R4-D14: un rubro con el sentido invertido coincidía al 100 %), un escrito que SOLO cita tesis
# no podía salir 🟢. R4d corrigió D13/D14 (cotejo literal normalizado y polaridad), pero la
# retención SE MANTIENE (adjudicación del 2-oct-2026): el cotejo se validó contra un corpus de
# solo 10 tesis; se reconsiderará con un corpus mayor. Mientras sea True, un escrito con solo
# tesis queda 🟡 aunque cada rubro coincida literalmente.
RETENER_VERDE_SOLO_TESIS = True


def veredicto_global(
    score_rag: Optional[float],
    score_sjf: Optional[float],
    tesis_discrepantes: int,
    tesis_no_encontradas: int,
    tesis_total: int,
    tesis_superadas: int = 0,
    normativa_refutada: int = 0,
    normativa_no_verificable: int = 0,
    articulos_total: Optional[int] = None,
    tesis_parciales: int = 0,
    normativa_no_vigente: int = 0,
) -> dict:
    """
    Veredicto binario con razón explícita. No promedia los dos scores.

    Reglas de precedencia (se evalúan en orden):
      1. tesis_discrepantes > 0  → ROJO bloqueante (rubro falsificado o equivocado)
      2. tesis_superadas > 0     → ROJO bloqueante (falso verde: cita real, criterio muerto)
      3. normativa_refutada > 0  → ROJO bloqueante (cita normativa refutada)
      4. tesis_no_encontradas > 0 → AMARILLO (corpus incompleto, no necesariamente error)
      4b. tesis_parciales > 0    → AMARILLO (tesis localizada sin verificación plena, p. ej.
         aislada; R4c ronda 2: cuentan como las normativas parciales)
      5. normativa_no_verificable > 0 → AMARILLO (evidencia parcial o insuficiente)
      6. RAG < 70 (o sin puntaje) → AMARILLO (artículos con verificación insuficiente); no
         aplica si ``articulos_total == 0``: una dimensión sin citas no es insuficiente
         (R4-D12, R4c)
      7. Sin artículos ni tesis  → AMARILLO (no hubo citas que verificar; R4c)
      7b. Solo tesis, sin artículos → AMARILLO transitorio mientras
         ``RETENER_VERDE_SOLO_TESIS`` (se mantiene tras R4d hasta validar el cotejo del rubro
         con un corpus de tesis mayor)
      8. Sin problemas           → VERDE, con una razón que enuncia solo lo verificado
         ("Normativa verificada; sin tesis citadas"; R4-D11, R4c)

    Args:
        score_rag:              promedio VVCA de artículos con evidencia (0-100); None si
                                ningún artículo tuvo evidencia evaluable (R4c)
        score_sjf:              promedio VVCA de tesis encontradas (0-100); None si ninguna
                                se encontró en el corpus local (R4c)
        tesis_discrepantes:     tesis con rubro que NO coincide con el corpus SJF real
        tesis_no_encontradas:   tesis invocadas que no se encontraron en el corpus local
        tesis_total:            total de tesis invocadas en el documento
        tesis_superadas:        tesis cuyo criterio fue superado/interrumpido/sustituido
                                (rubro correcto pero criterio ya no vigente — "falso verde").
                                Default 0: sin dato de vigencia el veredicto no cambia.
        normativa_refutada:     artículos cuya traza quedó refutada. Un solo caso bloquea.
        normativa_no_verificable: artículos parciales o no verificables. Exigen revisión.
        articulos_total:        referencias normativas auditadas (R4c). Con 0, la dimensión
                                normativa no tiene citas y la regla 6 no aplica. None
                                (omitido) conserva el comportamiento anterior: sin el dato no
                                se distingue "sin artículos" de "artículos con 0 puntos".
        tesis_parciales:        tesis localizadas cuya traza quedó ``partial`` (puntaje < 85,
                                p. ej. aislada). Default 0 (llamadas anteriores a la ronda 2).
        normativa_no_vigente:   de las normativas no verificables, las que lo son porque el
                                reporte de vigencia dice que la versión indexada de su ley ya no
                                es la vigente (``itosturre.audit.vigencia``). Solo precisa la
                                razón y la acción de la regla 5; default 0.

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

    if tesis_superadas > 0:
        return {
            "apto": False,
            "semaforo": "🔴",
            "razon": (
                f"{tesis_superadas}/{tesis_total} tesis con criterio superado o "
                "interrumpido — VIGENCIA PERDIDA (falso verde: registro y rubro reales, "
                "pero el criterio ya no rige)"
            ),
            "accion": "Sustituir por criterio vigente antes de cualquier uso procesal",
        }

    if normativa_refutada > 0:
        return {
            "apto": False,
            "semaforo": "🔴",
            "razon": (
                f"{normativa_refutada} cita(s) normativa(s) refutada(s) — "
                "USO PROCESAL PROHIBIDO"
            ),
            "accion": "Corregir o sustituir las citas normativas antes de cualquier uso procesal",
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

    # R4c (ronda 2): una tesis localizada sin verificación plena no es "verificada".
    if tesis_parciales > 0:
        return {
            "apto": False,
            "semaforo": "🟡",
            "razon": (
                f"{tesis_parciales}/{tesis_total} tesis con verificación parcial "
                "(localizadas con puntaje menor a 85, p. ej. tesis aislada)"
            ),
            "accion": "Cotejar la tesis en el SJF y valorar su fuerza vinculante antes de uso procesal",
        }

    if normativa_no_verificable > 0:
        razon = (
            f"{normativa_no_verificable} cita(s) normativa(s) con evidencia "
            "parcial o no verificable"
        )
        accion = "Cotejar el precepto en la fuente oficial antes de uso procesal"
        if normativa_no_vigente > 0:
            # Vigencia del corpus: la versión indexada de la ley ya no es la vigente.
            razon += f" ({normativa_no_vigente} por versión indexada no vigente)"
            accion += (" (Regla 8: python scripts/cotejo_manual.py articulo <ley> "
                       "<artículo>)")
        return {
            "apto": False,
            "semaforo": "🟡",
            "razon": razon,
            "accion": accion,
        }

    # R4c (R4-D12): sin artículos citados la dimensión normativa no tiene nada que verificar;
    # antes se calificaba "RAG 0.0" como verificación insuficiente aunque las tesis estuvieran
    # verificadas. Sin el dato (articulos_total=None) se conserva la regla anterior.
    sin_articulos = articulos_total == 0
    if not sin_articulos and (score_rag is None or score_rag < 70):
        puntaje = score_rag if score_rag is not None else "sin puntaje"
        return {
            "apto": False,
            "semaforo": "🟡",
            "razon": f"Artículos con verificación insuficiente (RAG: {puntaje})",
            "accion": "Revisar referencias normativas contra corpus oficial",
        }

    # R4c: sin artículos ni tesis no hay nada verificado; un 🟢 sería vacío. Se conserva el 🟡
    # que antes producía el "RAG 0.0", ahora con su razón verdadera.
    if sin_articulos and tesis_total == 0:
        return {
            "apto": False,
            "semaforo": "🟡",
            "razon": "Sin citas detectadas: no hay normativa ni jurisprudencia que verificar",
            "accion": (
                "Confirmar que el texto no cita normas ni tesis; la extracción automática "
                "puede omitir formatos no reconocidos"
            ),
        }

    # R4c (ronda 2) — TRANSITORIO: solo tesis y todas verificadas. R4d corrigió el cotejo del
    # rubro, pero la retención se mantiene hasta validarlo con un corpus de tesis mayor.
    if sin_articulos and RETENER_VERDE_SOLO_TESIS:
        return {
            "apto": False,
            "semaforo": "🟡",
            "razon": (
                "Jurisprudencia localizada; 🟢 de solo tesis retenido (transitorio) hasta "
                "validar el cotejo del rubro con un corpus de tesis mayor"
            ),
            "accion": (
                "Cotejar en el SJF que el rubro y el criterio de cada tesis respalden lo "
                "afirmado antes de uso procesal"
            ),
        }

    # R4c (R4-D11): la razón enuncia solo lo verificado.
    if sin_articulos:
        razon = "Jurisprudencia verificada; sin artículos citados"
    elif tesis_total == 0:
        razon = "Normativa verificada; sin tesis citadas"
    else:
        razon = "Normativa y jurisprudencia verificadas"
    return {
        "apto": True,
        "semaforo": "🟢",
        "razon": razon,
        "accion": "Proceder con revisión de pertinencia procesal por el operador",
    }
