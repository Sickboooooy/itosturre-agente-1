"""Gate G2 — "complemento, no sustituto".

La plantilla del protocolo de materia prohíbe cuatro cosas, porque compiten con lo que
el agente de destino ya trae y le dan instrucciones dobles o contradictorias:

  R1  definir el rol del agente ("Eres el Juez…");
  R2  redefinir el formato de salida o sus campos (faseActual, tipoDeObjecion, …);
  R3  repetir el protocolo anti-alucinación genérico ("no inventes…"); solo van las
      fuentes DONDE verificar, propias de la materia;
  R4  repetir la ficha procesal de la materia (código aplicable, etapas, estándar
      probatorio), que ya existe como pieza aparte.
  R5  nombrar una entidad federativa (enfoque nacional, 11-oct-2026): el protocolo vale para
      todo el país; lo local se remite a «la entidad del asunto» con [VERIFICAR EN: …].

R1–R3 son reglas de texto. R4 compara cada oración del protocolo con la ficha de la
materia (que se recibe como dato, no vive en este repositorio) por solapamiento de
palabras de contenido. Todo es determinista: el lint reprueba sin opinar.
"""
from __future__ import annotations

import re
from typing import Optional

from itosturre.protocolos.contrato import AVISO, ERROR, Hallazgo, entidades_mencionadas, norm, textos

# R1 — rol del agente. Se busca al inicio de una oración (tras normalizar).
_ROL = re.compile(
    r"(?:^|[.:;!?¿¡]\s*|\n\s*)(?:eres|seras|actua como|actuaras como|tu rol es|tu papel es|"
    r"te comportas como|asumes el rol)\b"
)
# R2 — formato de salida del simulador: identificadores tal cual (sensibles a mayúsculas)
# y frases que redefinen la salida.
_CAMPOS_SALIDA = ("faseActual", "tipoDeObjecion", "calificacionTurno")
_CAMPO_SALIDA_RE = re.compile(r"\b(" + "|".join(_CAMPOS_SALIDA) + r")\b")
_FORMATO_SALIDA_RE = re.compile(
    r"\"mensaje\"\s*:|formato de salida|responde (?:solo |unicamente )?en (?:formato )?json|"
    r"devuelve (?:un |el )?json|estructura de (?:tu|la) respuesta json"
)
# R3 — protocolo anti-alucinación genérico (la regla de no inventar ya existe en el agente).
_ANTIALUCINACION_RE = re.compile(
    r"\b(?:no|nunca|jamas)\s+(?:inventes|inventar|inventaras|alucines|alucinar|fabriques|fabricar)\b|"
    r"protocolo anti-?alucinacion"
)

# R4 — similitud con la ficha procesal.
_STOP = set(
    "a al ante bajo con contra de del desde durante e el en entre la las lo los o para por "
    "que se segun sin so sobre su sus tras un una unas unos y ya u le les esta este estas estos "
    "como mas muy si no es son ser sera cuando donde cual cuales cada todo toda todos todas".split()
)
UMBRAL_FICHA = 0.6        # fracción de las palabras de contenido de un campo de la ficha
MIN_CONTENIDO_FICHA = 4   # campos de ficha más cortos no se comparan (darían falsos positivos)
CAMPOS_FICHA_ERROR = ("etapas", "estandar")  # reglas de conducción: repetirlas es duplicar
# Nombrar el código (p. ej. en la cadena de jerarquía) no es repetir la regla, y la sección II
# puede rozar los principios: en ambos casos decide el abogado.
CAMPOS_FICHA_AVISO = ("codigo", "principios")


def _contenido(texto: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9ñ]+", norm(texto)) if len(w) > 2 and w not in _STOP}


def _oraciones(texto: str) -> list[str]:
    return [o.strip() for o in re.split(r"(?<=[.;:])\s+", texto) if o.strip()]


def _h(severidad: str, codigo: str, mensaje: str, ruta: str) -> Hallazgo:
    return Hallazgo("G2", severidad, codigo, mensaje, ruta)


def lint(protocolo: dict, ficha: Optional[dict] = None) -> list[Hallazgo]:
    """Hallazgos de G2. `ficha` = {"codigo", "etapas", "principios", "estandar"} de la
    materia en el simulador de destino; sin ficha, R4 no se evalúa y se avisa."""
    hallazgos: list[Hallazgo] = []
    for ruta, texto in textos(protocolo):
        normal = norm(texto)
        if _ROL.search(normal):
            hallazgos.append(_h(ERROR, "R1_ROL",
                                "define el rol del agente ('Eres…', 'actúa como…'): ese rol ya existe en el "
                                "agente; el protocolo solo aporta conocimiento de la materia", ruta))
        campo = _CAMPO_SALIDA_RE.search(texto)
        if campo or _FORMATO_SALIDA_RE.search(normal):
            detalle = f"'{campo.group(1)}'" if campo else "una instrucción sobre el formato de salida"
            hallazgos.append(_h(ERROR, "R2_FORMATO_SALIDA",
                                f"menciona {detalle}: el formato de salida y sus campos los define el "
                                "sistema; cambiarlos rompe la integración", ruta))
        if _ANTIALUCINACION_RE.search(normal):
            hallazgos.append(_h(ERROR, "R3_ANTIALUCINACION_GENERICA",
                                "repite la regla genérica de no inventar: ya existe en los agentes; aquí solo "
                                "van las fuentes DONDE verificar, propias de la materia", ruta))
        entidades = entidades_mencionadas(texto)
        if entidades:
            hallazgos.append(_h(ERROR, "R5_ENTIDAD_FEDERATIVA",
                                f"nombra {', '.join(entidades)}: el protocolo es nacional y no distingue por el "
                                "código de una entidad; remite a «la entidad del asunto» con [VERIFICAR EN: …]",
                                ruta))

    if ficha is None:
        hallazgos.append(_h(AVISO, "R4_SIN_FICHA",
                            "no se recibió la ficha procesal de la materia: no se comprobó que el protocolo "
                            "no la repita", ""))
        return hallazgos

    campos_ficha = {
        campo: _contenido(ficha.get(campo, ""))
        for campo in CAMPOS_FICHA_ERROR + CAMPOS_FICHA_AVISO
    }
    for ruta, texto in textos(protocolo):
        for oracion in _oraciones(texto):
            palabras = _contenido(oracion)
            for campo, contenido in campos_ficha.items():
                if len(contenido) < MIN_CONTENIDO_FICHA:
                    continue
                cobertura = len(palabras & contenido) / len(contenido)
                if cobertura >= UMBRAL_FICHA:
                    severidad = ERROR if campo in CAMPOS_FICHA_ERROR else AVISO
                    hallazgos.append(_h(
                        severidad, f"R4_FICHA_{campo.upper()}",
                        f"repite el '{campo}' de la ficha procesal ({cobertura:.0%} de sus palabras): "
                        f"«{oracion[:120]}»", ruta))
    return hallazgos
