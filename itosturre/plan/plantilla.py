"""Plantilla de ledger ``plan-ledger/1.0`` (piloto PEN-01: construir el ledger entero a mano,
sin ningún andamiaje, fue el paso más costoso).

``ledger_plantilla`` devuelve un ledger estructuralmente válido con ``evidencias``,
``contradicciones`` y ``decisiones`` vacías y una afirmación de ejemplo por tipo
(``EJEMPLO-*``), rotulada ``[ASIGNAR]``. Su estado de verificación es el marcador
``[ASIGNAR]``, fuera del vocabulario único, así que ``lint`` la marca BLOQUEANTE (PL-001)
mientras no se sustituya o se retire: un ejemplo olvidado nunca pasa en silencio.

Los ejemplos no contienen ningún dato jurídico: ni artículos, ni tesis, ni URLs, ni fechas
de consulta, ni números. Solo marcadores y notas de llenado en llaves ``_instrucciones``,
que el esquema ignora (llaves desconocidas, compatibilidad hacia adelante). El autor de
los ejemplos es ``agente``, la opción más estricta (PL-009 impide que una inferencia o
propuesta del agente quede VERIFICADO).

Función pura: sin E/S, sin red y sin reloj (la fecha del documento la da el operador).
La escritura del archivo, con la política de rutas D7, vive en ``plan_audit.py plantilla``.
"""
from __future__ import annotations

from typing import Any

from ..evidencia.esquema import es_marcador_pendiente
from .estados import ESTADOS_VERIFICACION
from .ledger import CAMPOS_CRITERIO, SCHEMA_VERSION, TESIS_SJF, fecha_iso, validar_esquema

ASIGNAR = "[ASIGNAR]"
NOTAS = "_instrucciones"

# (id, tipo, texto, referencias, nota de llenado). Ningún dato jurídico: solo marcadores.
_EJEMPLOS: tuple[tuple[str, str, str, tuple[str, ...], str], ...] = (
    (
        "EJEMPLO-TN",
        "texto_normativo",
        "[ASIGNAR: lo que el plan afirma que dispone una norma, copiado literal del documento del plan]",
        ("[ASIGNAR: art. N SIGLA]",),
        "texto_normativo: lo que dice una norma. Referencias en la forma «art. N SIGLA» (la ley a la "
        "derecha del número). Su evidencia es el PDF de LeyesBiblio registrado con «evidencia "
        "agregar-ley»; el extracto es una subcadena literal del texto que imprime «evidencia articulo».",
    ),
    (
        "EJEMPLO-CJ",
        "criterio_judicial",
        "[ASIGNAR: el criterio judicial que el plan invoca, copiado literal del documento del plan]",
        ("[ASIGNAR: registro digital de la tesis]",),
        "criterio_judicial: tesis del SJF. «evidencia agregar-tesis» imprime los datos de la fuente para "
        "identificacion_criterio; lo que la fuente no muestra (órgano, integración, alcance) lo asigna el "
        "abogado y nunca se completa de memoria. Para una sentencia de la Corte IDH: tipo_fuente "
        "«sentencia_internacional» con caso, serie_numero, fecha y parrafo (su cotejo de identidad aún "
        "no está soportado).",
    ),
    (
        "EJEMPLO-HA",
        "hecho_aportado",
        "[ASIGNAR: hecho que el plan da por cierto (del asunto o de una fuente), copiado literal del "
        "documento del plan]",
        (),
        "hecho_aportado: un hecho, no una norma ni un criterio. Solo sostiene VERIFICADO con evidencia "
        "oficial cotejada; si no la hay, CANDIDATO, NO VERIFICABLE o REQUIERE DECISIÓN HUMANA.",
    ),
    (
        "EJEMPLO-INF",
        "inferencia",
        "[ASIGNAR: conclusión que el plan deriva de normas o criterios, copiada literal del documento "
        "del plan]",
        ("[ASIGNAR: art. N SIGLA de la norma de la que se infiere]",),
        "inferencia: conclusión derivada. Si la redactó el agente (autor «agente») nunca queda VERIFICADO "
        "(PL-009): CANDIDATO o REQUIERE DECISIÓN HUMANA hasta que una persona la apruebe. Sus "
        "referencias «art. N SIGLA» permiten el cotejo de fidelidad contra el texto oficial.",
    ),
    (
        "EJEMPLO-PROP",
        "propuesta",
        "[ASIGNAR: acción o regla que el plan propone, copiada literal del documento del plan]",
        ("[ASIGNAR: art. N SIGLA en que se apoya]",),
        "propuesta: lo que el plan recomienda hacer. Igual que la inferencia: si es del agente, nunca "
        "VERIFICADO (PL-009); la decide y la aprueba una persona.",
    ),
)

IDS_EJEMPLO = tuple(ejemplo[0] for ejemplo in _EJEMPLOS)


def _instrucciones_generales() -> list[str]:
    return [
        "Plantilla de «plan_audit.py plantilla». Las llaves «_instrucciones» son notas: el auditor las "
        "ignora y se pueden borrar.",
        "Cada afirmación EJEMPLO-* muestra un tipo: duplicarla por cada proposición del plan (id propio, "
        "texto literal del plan, tipo, autor, referencias, estado) y borrar los ejemplos que no se usen. "
        "Mientras su estado sea [ASIGNAR], lint la marca BLOQUEANTE (PL-001).",
        "autor: «agente» (lo redactó un modelo o el agente), «humano» (lo aportó una persona) o «fuente» "
        "(transcripción de la fuente). La plantilla pone «agente», la opción más estricta.",
        "Estados de verificación: " + ", ".join(ESTADOS_VERIFICACION) + ". Si el plan no declara estado, "
        "no se inventa: se deja [ASIGNAR] y se pregunta al responsable. APROBADO no es un estado: va en "
        "«aprobacion» {por, en, contenido_sha256} y solo lo firma una persona identificada "
        "(«plan_audit.py hash» da el contenido_sha256).",
        "evidencias[]: pegar los bloques que imprimen «evidencia agregar-ley» y «evidencia agregar-tesis» "
        "y asignarles id; el extracto literal sale de «evidencia articulo». Ningún dato jurídico se "
        "teclea de memoria.",
        "decisiones[]: los bloques de advertencias de la fuente («cotejar») y de fidelidad («fidelidad») "
        "los completa un responsable que sea una persona identificada, nunca el agente.",
        "Orden de la auditoría: cotejar → fidelidad → lint --paquete --documento --md (MENÚ 16).",
    ]


def _afirmacion_ejemplo(
    id_: str, tipo: str, texto: str, referencias: tuple[str, ...], nota: str
) -> dict[str, Any]:
    afirmacion: dict[str, Any] = {
        "id": id_,
        NOTAS: nota,
        "texto": texto,
        "tipo": tipo,
        "autor": "agente",
        "referencias": list(referencias),
        "verificacion": {"estado": ASIGNAR, "evidencias": [], "motivo": ""},
        "aprobacion": None,
    }
    if tipo == "criterio_judicial":
        afirmacion["identificacion_criterio"] = {
            "tipo_fuente": TESIS_SJF,
            **{campo: ASIGNAR for campo in CAMPOS_CRITERIO},
        }
    return afirmacion


def problemas_parametros(plan_id: Any, titulo: Any, fecha_documento: Any) -> list[str]:
    """Motivos por los que los datos del plan no sirven para la plantilla (``[]`` si sirven)."""
    problemas: list[str] = []
    for nombre, valor in (("--plan-id", plan_id), ("--titulo", titulo)):
        if not isinstance(valor, str) or not valor.strip():
            problemas.append(f"{nombre}: debe ser texto no vacío")
        elif es_marcador_pendiente(valor):
            problemas.append(f"{nombre} {valor!r}: es un marcador pendiente; el dato lo da el operador")
    if fecha_iso(fecha_documento) is None:
        problemas.append(
            f"--fecha {fecha_documento!r}: se espera la fecha del documento del plan, AAAA-MM-DD válida "
            "(la da el operador; nunca se toma del reloj)"
        )
    return problemas


def ledger_plantilla(plan_id: str, titulo: str, fecha_documento: str) -> dict[str, Any]:
    """Ledger ``plan-ledger/1.0`` válido con colecciones vacías y ejemplos rotulados ``[ASIGNAR]``.

    Lanza ``ValueError`` si los datos del plan no sirven (``problemas_parametros``).
    """
    problemas = problemas_parametros(plan_id, titulo, fecha_documento)
    if problemas:
        raise ValueError("; ".join(problemas))
    ledger: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        NOTAS: _instrucciones_generales(),
        "plan": {
            "id": plan_id.strip(),
            "titulo": titulo.strip(),
            "fecha_documento": fecha_documento.strip(),
        },
        "afirmaciones": [_afirmacion_ejemplo(*ejemplo) for ejemplo in _EJEMPLOS],
        "evidencias": [],
        "contradicciones": [],
        "decisiones": [],
    }
    errores = validar_esquema(ledger)
    if errores:  # invariante: la plantilla siempre cumple el esquema
        raise RuntimeError("la plantilla no cumple plan-ledger/1.0: " + "; ".join(errores))
    return ledger
