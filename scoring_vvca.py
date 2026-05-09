"""
scoring_vvca.py — Score compuesto VVCA para documentos legales Itosturre.

Reemplaza el promedio plano de artículos con una ponderación que refleja
el peso procesal real de cada dimensión. Con 5/5 tesis falsas el score
global no puede ser 90.
"""

from __future__ import annotations

PESOS: dict[str, float] = {
    "normativa":      0.25,   # Arts. CPEUM, CNPP, Ley de Amparo
    "jurisprudencia": 0.50,   # Tesis SJF — núcleo del argumento
    "estrategia":     0.15,   # Coherencia procesal de la propuesta
    "auditabilidad":  0.10,   # Trazabilidad de fuentes (registros completos)
}


def _semaforo(score: float) -> str:
    if score >= 85:
        return "🟢"
    if score >= 70:
        return "🟡"
    if score >= 50:
        return "🟠"
    return "🔴"


def _penalizacion_tesis(tesis_rojas: int, tesis_total: int) -> float:
    if tesis_total == 0:
        return 0.0
    ratio = tesis_rojas / tesis_total
    if ratio == 1.0:
        return 45.0
    if ratio >= 0.6:
        return 30.0
    if ratio >= 0.4:
        return 15.0
    if ratio > 0.0:
        return 8.0
    return 0.0


def calcular_score_global(
    score_normativa: float,
    score_jurisprudencia: float,
    tesis_rojas: int,
    tesis_total: int,
    score_estrategia: float = 75.0,
    score_auditabilidad: float = 60.0,
) -> dict:
    """
    Devuelve score global ponderado con penalización por tesis falsas.

    Args:
        score_normativa: promedio VVCA de artículos verificados (0-100)
        score_jurisprudencia: promedio VVCA de tesis verificadas (0=ninguna verificada)
        tesis_rojas: cantidad de tesis con alerta (no verificadas o falsas)
        tesis_total: total de tesis invocadas en el documento
        score_estrategia: coherencia procesal (default 75 si no se calcula)
        score_auditabilidad: completitud de auditabilidad (default 60)

    Returns:
        dict con score_global, semaforo, apto_para_uso_procesal, detalle
    """
    ponderado = (
        score_normativa      * PESOS["normativa"]
        + score_jurisprudencia * PESOS["jurisprudencia"]
        + score_estrategia     * PESOS["estrategia"]
        + score_auditabilidad  * PESOS["auditabilidad"]
    )

    penalizacion = _penalizacion_tesis(tesis_rojas, tesis_total)
    score_final = max(0.0, ponderado - penalizacion)

    semaforo = _semaforo(score_final)
    apto = score_final >= 70

    return {
        "score_global": round(score_final, 1),
        "semaforo": semaforo,
        "apto_para_uso_procesal": apto,
        "label": "APTO" if apto else "USO PROCESAL PROHIBIDO",
        "detalle": {
            "score_normativa":      round(score_normativa, 1),
            "score_jurisprudencia": round(score_jurisprudencia, 1),
            "score_estrategia":     round(score_estrategia, 1),
            "score_auditabilidad":  round(score_auditabilidad, 1),
            "ponderado_bruto":      round(ponderado, 1),
            "penalizacion_tesis":   round(penalizacion, 1),
            "tesis_rojas":          tesis_rojas,
            "tesis_total":          tesis_total,
        },
    }
