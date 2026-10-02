"""Reporte Markdown del auditor de planes.

El reporte resume por severidad y por estado mostrado y cierra con la tabla de
seguimiento ``| ID | Hallazgo / decisión | Evidencia | Estado | Responsable | Bloquea |
Acción siguiente |``. "Sin hallazgos bloqueantes" no equivale a aprobación jurídica:
la pertinencia al caso sigue siendo decisión del abogado.

Con un cotejo de identidad (``cotejo=``) se agrega la sección "Cotejo de identidad":
conteo por resultado y una tabla por par (afirmación, evidencia) con resultado, paso,
motivos, documento y versión de la fuente y si requiere decisión humana. Sin cotejo, el
reporte es el de PR-1 (con la fila ``ADVERTENCIA`` del resumen por severidad en 0). Las
notas del agregado incluyen los artículos remitidos sin cotejar (PL-019) y la evidencia
citada sin cotejar (PL-018).
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
from .identidad import (
    CAMPO_DECISION_ADVERTENCIAS,
    NO_COTEJADO_CAMPO,
    OBSERVACION,
    PASOS,
    RESULTADOS,
    CotejoLedger,
    ResultadoPar,
    decision_atiende,
)
from .lint import ACCIONES, BLOQUEANTE, SEVERIDADES, resumen_severidades

ASIGNAR = "[ASIGNAR]"
_ORDEN_ESTADOS = (APROBADO, *ESTADOS_VERIFICACION, ESTADO_INVALIDO)


def _celda(valor: object) -> str:
    texto = " ".join(str(valor).split()) if valor not in (None, "") else "—"
    return texto.replace("|", "\\|")


def _responsable(valor: object) -> str:
    return valor.strip() if isinstance(valor, str) and valor.strip() else ASIGNAR


def _fuente_del_par(par: ResultadoPar) -> str:
    partes = [par.documento_fuente or "—"]
    if par.version_fuente:
        partes.append(f"última reforma DOF {par.version_fuente}")
    if par.fecha_consulta_fuente:
        partes.append(f"consulta {par.fecha_consulta_fuente}")
    return " · ".join(partes)


def _notas(motivos) -> list[str]:
    return [
        ("no cotejado — " if m.clase == NO_COTEJADO_CAMPO else "observación — ") + m.resumen()
        for m in motivos
        if m.clase in (NO_COTEJADO_CAMPO, OBSERVACION)
    ]


def _fila(valores: tuple, *, crudas: tuple[int, ...] = ()) -> str:
    return "| " + " | ".join(
        valor if indice in crudas else _celda(valor) for indice, valor in enumerate(valores)
    ) + " |"


def _decision_del_par(par: ResultadoPar, decisiones: list[dict], verificada: bool) -> str:
    if not par.requiere_decision_humana:
        return "—"
    texto = f"requerida ({', '.join(par.codigos_advertencia)})"
    atienden = [d["id"] for d in decisiones if decision_atiende(d, par, aprobada=verificada)]
    return texto + (f" · atendida por {', '.join(atienden)}" if atienden else " · sin decisión que la atienda")


def seccion_cotejo(cotejo: CotejoLedger, decisiones: list[dict] | None = None, estados: dict | None = None) -> list[str]:
    """Líneas Markdown de la sección "Cotejo de identidad".

    ``decisiones`` (del ledger) permiten indicar qué decisión humana atiende cada par que
    la requiere; ``estados`` (ID → estado canónico) distinguen si hace falta APROBADA.
    """
    decisiones = list(decisiones or [])
    estados = estados or {}
    resumen = cotejo.resumen()
    lineas = [
        "",
        "## Cotejo de identidad",
        "",
        "El cotejo informa: no aprueba ni cambia estados (D3). Comprueba que cada evidencia "
        "citada es el documento oficial registrado en el paquete, que sus datos "
        "identificatorios y su extracto coinciden y que la afirmación menciona ese documento; "
        "no compara lo que la afirmación dice con lo que dice la fuente (fidelidad).",
        "",
        f"- Huella del ledger cotejado: `{cotejo.huella_ledger}`",
        f"- Huella del paquete: `{cotejo.huella_paquete}`",
        "",
        "| Resultado | Pares |",
        "|---|---|",
    ]
    lineas += [f"| {resultado} | {resumen[resultado]} |" for resultado in RESULTADOS]
    lineas.append(f"| Requieren decisión humana | {resumen['requieren_decision_humana']} |")
    lineas.append(f"| Afirmaciones con hallazgo | {resumen['afirmaciones_con_hallazgo']} |")
    if cotejo.problemas_paquete:
        lineas.append("")
        lineas += [f"- Problema del paquete: {_celda(p)}" for p in cotejo.problemas_paquete]
    lineas += [
        "",
        "| Afirmación | Evidencia | Resultado | Paso | Motivos | Fuente (documento · versión · consulta) | Decisión humana |",
        "|---|---|---|---|---|---|---|",
    ]
    for par in cotejo.pares:
        motivos = [m.resumen() for m in par.motivos] + _notas(par.notas)
        paso = f"{par.paso} · {PASOS[par.paso]}" if par.paso in PASOS else "—"
        decision = _decision_del_par(par, decisiones, estados.get(par.afirmacion) == "VERIFICADO")
        lineas.append(_fila(
            (par.afirmacion, par.evidencia, par.resultado, paso,
             "<br>".join(_celda(m) for m in motivos) or "—", _fuente_del_par(par), decision),
            crudas=(4,),
        ))
    if not cotejo.pares:
        lineas.append("| — | — | Sin evidencias citadas que cotejar | — | — | — | — |")
    lineas += [
        "",
        "| Afirmación | Estado declarado | Resultado agregado | Sostiene a lo sumo | Hallazgo | Motivos y notas |",
        "|---|---|---|---|---|---|",
    ]
    for agregado in cotejo.afirmaciones:
        textos = [m.resumen() for m in agregado.motivos] + _notas(agregado.notas)
        lineas.append(_fila(
            (agregado.afirmacion, agregado.estado_declarado or "ESTADO INVÁLIDO", agregado.resultado,
             agregado.estado_sostenible or "—", "sí" if agregado.es_hallazgo else "no",
             "<br>".join(_celda(t) for t in textos) or "—"),
            crudas=(5,),
        ))
    return lineas


def _describir_decision(decision: dict) -> str:
    datos = decision.get(CAMPO_DECISION_ADVERTENCIAS)
    if not isinstance(datos, dict):
        return ""
    sha = datos.get("sha256_documento") or datos.get("huella_registro")
    codigos = datos.get("codigos")
    return (
        f" · Atiende advertencias de la fuente de {datos.get('evidencia') or '—'}"
        f" ({', '.join(codigos) if isinstance(codigos, list) else '—'};"
        f" fuente {str(sha)[:16] + '…' if isinstance(sha, str) else '—'};"
        f" resolución: {datos.get('resolucion') or '—'})"
    )


def reporte_markdown(
    ledger: dict, hallazgos: Iterable[dict], cotejo: CotejoLedger | None = None
) -> str:
    """Construye el reporte Markdown de un ledger ya validado y sus hallazgos.

    Con ``cotejo`` (``identidad.cotejar_ledger``) agrega la sección de cotejo de identidad.
    """
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
    if cotejo is not None:
        estados = {a["id"]: normalizar_estado(a["verificacion"].get("estado")) for a in afirmaciones}
        lineas += seccion_cotejo(cotejo, decisiones, estados)

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
            f"Decisión: {decision['pregunta']}{_describir_decision(decision)}",
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
