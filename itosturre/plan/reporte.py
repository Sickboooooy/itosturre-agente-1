"""Reporte Markdown del auditor de planes.

El reporte resume por severidad y por estado mostrado y cierra con la tabla de
seguimiento ``| ID | Hallazgo / decisión | Evidencia | Estado | Responsable | Bloquea |
Acción siguiente |``. "Sin hallazgos bloqueantes" no equivale a aprobación jurídica:
la pertinencia al caso sigue siendo decisión del abogado.
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from .estados import (
    APROBADO,
    ESTADO_INVALIDO,
    ESTADOS_VERIFICACION,
    estado_mostrado,
    normalizar_estado,
    responsable_humano,
)
from .lint import ACCIONES, BLOQUEANTE, SEVERIDADES, resumen_severidades

ASIGNAR = "[ASIGNAR]"
_ORDEN_ESTADOS = (APROBADO, *ESTADOS_VERIFICACION, ESTADO_INVALIDO)


def _celda(valor: object) -> str:
    texto = " ".join(str(valor).split()) if valor not in (None, "") else "—"
    return texto.replace("|", "\\|")


def _responsable(valor: object) -> str:
    return valor.strip() if isinstance(valor, str) and valor.strip() else ASIGNAR


def reporte_markdown(ledger: dict, hallazgos: Iterable[dict]) -> str:
    """Construye el reporte Markdown de un ledger ya validado y sus hallazgos."""
    hallazgos = list(hallazgos)
    plan = ledger["plan"]
    afirmaciones = ledger.get("afirmaciones") or []
    contradicciones = ledger.get("contradicciones") or []
    decisiones = ledger.get("decisiones") or []
    por_id_afirmacion = {a["id"]: a for a in afirmaciones}
    por_id_contradiccion = {c["id"]: c for c in contradicciones}
    por_id_decision = {d["id"]: d for d in decisiones}

    severidades = resumen_severidades(hallazgos)
    bloqueantes = severidades[BLOQUEANTE]
    lineas = [
        f"# Auditoría de plan · {plan['titulo']}",
        "",
        f"- **Plan:** `{plan['id']}` · fecha del documento {plan['fecha_documento']}",
        f"- **Esquema:** `{ledger['schema_version']}`",
        (
            f"- **Resultado:** BLOQUEADO — {bloqueantes} hallazgo(s) bloqueante(s)."
            if bloqueantes
            else "- **Resultado:** sin hallazgos bloqueantes. No equivale a aprobación "
            "jurídica: la pertinencia al caso es decisión del abogado."
        ),
        "",
        "## Resumen por severidad",
        "",
        "| Severidad | Hallazgos |",
        "|---|---|",
    ]
    lineas += [f"| {severidad} | {severidades[severidad]} |" for severidad in SEVERIDADES]

    conteo_estados = Counter(estado_mostrado(a) for a in afirmaciones)
    lineas += [
        "",
        "## Afirmaciones por estado mostrado",
        "",
        "| Estado | Afirmaciones |",
        "|---|---|",
    ]
    lineas += [
        f"| {estado} | {conteo_estados[estado]} |"
        for estado in _ORDEN_ESTADOS
        if conteo_estados[estado] or estado != ESTADO_INVALIDO
    ]

    responsable_por_objetivo: dict[str, str] = {}
    for decision in decisiones:
        if not responsable_humano(decision.get("responsable")):
            continue
        for objetivo in decision.get("bloquea") or []:
            responsable_por_objetivo.setdefault(objetivo, decision["responsable"].strip())

    lineas += [
        "",
        "## Hallazgos y decisiones",
        "",
        "| ID | Hallazgo / decisión | Evidencia | Estado | Responsable | Bloquea | Acción siguiente |",
        "|---|---|---|---|---|---|---|",
    ]
    for hallazgo in hallazgos:
        objetivo = hallazgo["objetivo"]
        evidencia = "—"
        estado = "—"
        if objetivo in por_id_afirmacion:
            afirmacion = por_id_afirmacion[objetivo]
            evidencia = ", ".join(afirmacion["verificacion"].get("evidencias") or []) or "—"
            estado = estado_mostrado(afirmacion)
        elif objetivo in por_id_contradiccion:
            estado = por_id_contradiccion[objetivo]["estado"]
        elif objetivo in por_id_decision:
            estado = por_id_decision[objetivo]["estado"]
        fila = (
            objetivo,
            f"**{hallazgo['regla']}** [{hallazgo['severidad']}] {hallazgo['mensaje']}",
            evidencia,
            estado,
            responsable_por_objetivo.get(objetivo, ASIGNAR),
            "plan" if hallazgo["severidad"] == BLOQUEANTE else "—",
            ACCIONES.get(hallazgo["regla"], "—"),
        )
        lineas.append("| " + " | ".join(_celda(valor) for valor in fila) + " |")

    for decision in decisiones:
        aprobada = normalizar_estado(decision["estado"], admitir_aprobado=True) == APROBADO
        fila = (
            decision["id"],
            f"Decisión: {decision['pregunta']}",
            "—",
            decision["estado"],
            _responsable(decision.get("responsable")),
            ", ".join(decision.get("bloquea") or []) or "—",
            "—" if aprobada else "Resolver y registrar la decisión humana.",
        )
        lineas.append("| " + " | ".join(_celda(valor) for valor in fila) + " |")

    if not hallazgos and not decisiones:
        lineas.append("| — | Sin hallazgos ni decisiones pendientes | — | — | — | — | — |")
    return "\n".join(lineas) + "\n"
