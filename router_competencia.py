"""
router_competencia.py — Router determinista de competencia orgánica (Post-Reforma PJF 2021).

Motor del MENÚ 8. Dado (tipo de asunto, materia, autoridad federal/local, circuito), determina
el TIPO de órgano competente, la vía, el recurso, el plazo y el fundamento — de forma
determinista y CONSERVADORA.

Filosofía anti-alucinación (REGLA #5 — impacto procesal grave):
  - Encoda solo la ESTRUCTURA que está grounded en CLAUDE.md (MENÚ 8) y en las tablas de
    plazos del repo. NUNCA inventa la clave específica de un TCC (p. ej. "I.1o.P. J/7"),
    ni qué número de Pleno Regional ni su sede exacta — eso se confirma en el Acuerdo 5/2021.
  - Su misión principal es evitar el ERROR #1 de los LLM: mandar a la SCJN lo que resuelve el
    Pleno Regional (contradicciones) o el TCC (amparo directo). La SCJN solo aparece como
    ATRACCIÓN discrecional (importancia y trascendencia), nunca como ruta automática.
  - Todo lo discrecional o no verificable se marca requiere_capa2=True (decide el abogado).

El abogado verifica el fundamento y el órgano vigente antes de presentar.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List

# Entradas admitidas (se normalizan con acentos/sinónimos).
TIPOS = {
    "amparo_indirecto", "amparo_directo", "revision", "contradiccion",
    "queja", "reclamacion", "extincion_dominio", "incidente_suspension",
}
MATERIAS = {"penal", "civil", "administrativa", "laboral", "constitucional", "otra"}

_TIPO_ALIAS = {
    "amparo indirecto": "amparo_indirecto", "indirecto": "amparo_indirecto",
    "amparo directo": "amparo_directo", "directo": "amparo_directo",
    "revisión": "revision", "recurso de revision": "revision", "recurso de revisión": "revision",
    "contradicción": "contradiccion", "contradiccion de tesis": "contradiccion",
    "contradicción de tesis": "contradiccion", "contradiccion de criterios": "contradiccion",
    "reclamación": "reclamacion", "extinción de dominio": "extincion_dominio",
    "extincion de dominio": "extincion_dominio", "suspension": "incidente_suspension",
    "suspensión": "incidente_suspension", "incidente de suspension": "incidente_suspension",
}
_MATERIA_ALIAS = {
    "administrativo": "administrativa", "mercantil": "civil", "civil/mercantil": "civil",
    "común": "constitucional", "comun": "constitucional", "fiscal": "administrativa",
}

_MATERIA_LABEL = {
    "penal": "Penal", "civil": "Civil", "administrativa": "Administrativa",
    "laboral": "Laboral", "constitucional": "Constitucional/Común", "otra": "(por definir)",
}

# Advertencia transversal — se añade a TODA resolución (reforma en curso + deber de verificar).
_ADV_REFORMA = (
    "Reforma Judicial 2024-2025: la reestructuración de órganos puede alterar competencias, "
    "sedes y turnado; confirmar el órgano y el fundamento vigentes antes de presentar."
)


@dataclass
class Competencia:
    tipo: str
    materia: str
    organo: str
    especializacion: str
    sede: str
    via: str
    recurso: str
    plazo: str
    fundamento: List[str]
    turnado: str
    advertencias: List[str] = field(default_factory=list)
    requiere_capa2: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _norm(valor: str, alias: dict) -> str:
    v = (valor or "").strip().lower()
    return alias.get(v, v)


def resolver(
    tipo_asunto: str,
    materia: str = "otra",
    autoridad_federal: bool = True,
    circuito: int = 3,
) -> Competencia:
    """Resuelve el TIPO de órgano competente de forma determinista y conservadora."""
    tipo = _norm(tipo_asunto, _TIPO_ALIAS)
    mat = _norm(materia, _MATERIA_ALIAS)
    if mat not in MATERIAS:
        mat = "otra"
    mat_label = _MATERIA_LABEL[mat]
    circ_label = "Tercer Circuito (Jalisco)" if circuito == 3 else f"{circuito}º Circuito"
    sede = "Guadalajara, Jalisco" if circuito == 3 else f"sede del {circ_label}"

    adv: List[str] = []
    capa2 = False

    if tipo == "amparo_indirecto":
        organo = f"Juzgado de Distrito especializado en materia {mat_label}"
        via = "Demanda de amparo indirecto (contra acto de autoridad)"
        recurso = "Recurso de revisión ante el Tribunal Colegiado de Circuito"
        plazo = "15 días hábiles desde el surtimiento de efectos de la notificación (art. 17 LA)"
        fundamento = ["art. 107 CPEUM", "arts. 107 y 108 Ley de Amparo (procedencia)", "LOPJF"]
        turnado = "Turno automático del PJF (oficialía de partes)"
        if not autoridad_federal:
            adv.append(
                "El amparo (aun contra autoridad local de Jalisco) se promueve ante Juzgado de "
                "Distrito FEDERAL. Si el acto no es 'de autoridad' para efectos del amparo, la vía "
                "puede ser local (p. ej. TJA Jalisco) — verificar (Capa 2)."
            )
            capa2 = True

    elif tipo == "amparo_directo":
        organo = f"Tribunal Colegiado de Circuito especializado en materia {mat_label} del {circ_label}"
        via = "Demanda de amparo directo (contra sentencia o resolución definitiva)"
        recurso = "Revisión ante la SCJN SOLO si procede por atracción (no automática)"
        plazo = "15 días hábiles desde la notificación de la resolución (art. 17 LA)"
        fundamento = ["art. 107 CPEUM", "art. 170 Ley de Amparo (amparo directo)", "LOPJF"]
        turnado = "Distribución por especialización (Acuerdo del Pleno Regional)"
        adv.append(
            "🚨 NO va directo a la SCJN: el amparo directo lo resuelve el Tribunal Colegiado. "
            "La SCJN solo interviene por ATRACCIÓN o revisión excepcional (importancia y "
            "trascendencia, art. 107 CPEUM), que NO es automática y decide la propia SCJN — "
            "decisión estratégica del abogado (Capa 2)."
        )
        capa2 = True

    elif tipo == "revision":
        organo = ("Tribunal Colegiado de Circuito (si se revisa una sentencia de amparo "
                  "INDIRECTO dictada por un Juzgado de Distrito)")
        via = "Recurso de revisión"
        recurso = "—"
        plazo = "10 días hábiles (art. 86 LA)"
        fundamento = ["art. 107 CPEUM", "arts. 81 y 86 Ley de Amparo", "LOPJF"]
        turnado = "Turno del TCC del circuito"
        adv.append(
            "Si la revisión es de una sentencia de amparo DIRECTO (dictada por un TCC), solo "
            "procede ante la SCJN por excepción —cuando subsiste un tema de constitucionalidad "
            "de importancia y trascendencia—, nunca de forma automática (Capa 2)."
        )
        capa2 = True

    elif tipo == "contradiccion":
        organo = "Pleno Regional que corresponde al Tercer Circuito"
        via = "Denuncia de contradicción de tesis / criterios"
        recurso = "En su caso, atracción por la SCJN (excepcional)"
        plazo = "Denunciable en cualquier tiempo (sin plazo fatal) — confirmar en la LA vigente"
        fundamento = ["art. 107 fr. XIII CPEUM",
                      "Acuerdo General 5/2021 del CJF (Plenos Regionales)", "Ley de Amparo"]
        turnado = "Turno del Pleno Regional (Acuerdo del CJF)"
        adv.append(
            "🚨 NO corresponde a la SCJN: post-Reforma 2021 las contradicciones por circuito las "
            "resuelve el PLENO REGIONAL, no la SCJN. Este es el error #1 a evitar."
        )
        adv.append("La jurisprudencia del Pleno Regional [PR] es obligatoria en su región, no nacional.")
        adv.append("Confirmar qué Pleno Regional y sede corresponden al Tercer Circuito en el "
                   "Acuerdo General 5/2021 vigente (el router no fija ese dato).")
        capa2 = True

    elif tipo == "queja":
        organo = "Tribunal Colegiado de Circuito (según el supuesto del art. 97 LA)"
        via = "Recurso de queja"
        recurso = "—"
        plazo = "2 o 5 días hábiles según el supuesto (art. 98 LA)"
        fundamento = ["arts. 97 y 98 Ley de Amparo"]
        turnado = "Turno del TCC del circuito"

    elif tipo == "reclamacion":
        organo = "El propio órgano (TCC o SCJN) que dictó el acuerdo de trámite recurrido"
        via = "Recurso de reclamación"
        recurso = "—"
        plazo = "3 días hábiles (art. 104 LA)"
        fundamento = ["art. 104 Ley de Amparo"]
        turnado = "El mismo órgano que emitió el acuerdo"

    elif tipo == "extincion_dominio":
        organo = "Juzgado de Distrito especializado en Extinción de Dominio (juicio autónomo)"
        via = "Juicio de extinción de dominio (NO es amparo)"
        recurso = "Apelación / recursos conforme a la LNEDo; en su caso, amparo"
        plazo = "Conforme a la LNEDo (varía por etapa) — verificar"
        fundamento = ["art. 22 CPEUM", "Ley Nacional de Extinción de Dominio"]
        turnado = "Turno del PJF"
        adv.append("Juicio autónomo (no penal ni amparo); carga probatoria y reglas propias. "
                   "Verificar cobertura de la LNEDo en el corpus (gap conocido).")
        capa2 = True

    elif tipo == "incidente_suspension":
        organo = "El mismo órgano que conoce del amparo (Juzgado de Distrito o TCC)"
        via = "Incidente de suspensión (dentro del amparo)"
        recurso = "Recursos conforme a la Ley de Amparo (revisión de la suspensión)"
        plazo = "Se tramita dentro del amparo (no es vía autónoma)"
        fundamento = ["arts. 125 a 158 Ley de Amparo"]
        turnado = "El órgano que conoce del amparo"

    else:
        organo = "No determinable automáticamente por el router"
        via = "—"
        recurso = "—"
        plazo = "—"
        fundamento = []
        turnado = "—"
        adv.append(f"Tipo de asunto '{tipo_asunto}' no tipificado en el router — resolver con "
                   "criterio del abogado (Capa 2).")
        capa2 = True

    adv.append(_ADV_REFORMA)

    return Competencia(
        tipo=tipo, materia=mat, organo=organo,
        especializacion=mat_label if tipo in ("amparo_indirecto", "amparo_directo") else "—",
        sede=sede, via=via, recurso=recurso, plazo=plazo,
        fundamento=fundamento, turnado=turnado, advertencias=adv, requiere_capa2=capa2,
    )


def formato_menu8(c: Competencia) -> str:
    """Bloque de salida estilo MENÚ 8 (para el agente)."""
    fund = " · ".join(c.fundamento) if c.fundamento else "[VERIFICAR]"
    cab = "🚨 REQUIERE CRITERIO DEL ABOGADO (Capa 2)" if c.requiere_capa2 else "🟢 Ruta determinista"
    lineas = [
        "════════════════════════════════════════════════",
        "  🏛️  COMPETENCIA ORGÁNICA (Post-Reforma PJF 2021)",
        "════════════════════════════════════════════════",
        f"  Asunto        : {c.tipo} · materia {c.especializacion}",
        f"  Órgano        : {c.organo}",
        f"  Sede          : {c.sede}",
        f"  Vía           : {c.via}",
        f"  Recurso       : {c.recurso}",
        f"  Plazo         : {c.plazo}",
        f"  Turnado       : {c.turnado}",
        f"  Fundamento    : {fund}",
        f"  Estado        : {cab}",
    ]
    if c.advertencias:
        lineas.append("  ── Advertencias ──")
        for a in c.advertencias:
            lineas.append(f"   • {a}")
    lineas += [
        "════════════════════════════════════════════════",
        "⚠️ El router indica el TIPO de órgano y la vía; NO fija la clave del",
        "   tribunal ni sustituye la verificación del fundamento por el abogado.",
    ]
    return "\n".join(lineas)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Demo de los casos frontera clave (incl. el error #1: contradicción NO va a la SCJN).
    for t, m in [("amparo_directo", "penal"), ("contradiccion", "civil"),
                 ("amparo_indirecto", "administrativa"), ("revision", "penal")]:
        print(formato_menu8(resolver(t, m)))
        print()
