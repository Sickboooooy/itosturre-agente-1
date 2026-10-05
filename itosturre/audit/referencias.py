"""Extracción de referencias a artículos y resolución del ordenamiento citado (R4b).

Funciones puras (solo biblioteca estándar): no leen el corpus ni el modelo. ``OpenNotebook``
las usa con su catálogo de leyes (``LAW_SOURCE_MAP`` y ``LAW_ALIASES``).

Designación del artículo
  Se conservan el ordinal y los sufijos tal como se escribieron: ``247 Ter``, ``2o. Bis``,
  ``4o.-A``, ``29-A``, ``32-B Quáter``. El signo de grado (``259°``) no forma parte de la
  designación, como antes. Ronda 2 de la re-ingesta (4-oct-2026), gramática ÚNICA de
  extracción, encabezado exacto, variantes, inexistencia e ingesta: subnúmero pegado "N-M" con
  M < N (``58-1``; con M ≥ N es un rango), número tras el sufijo latino (``65 Bis 1``),
  sufijos latinos más allá de "decies" y "quintus" (``LATINOS``, ``patron_latinos``,
  ``canon_latino``), y falla cerrada: una designación que el texto continúa sin extraerse
  entera queda como cobertura incompleta.

Enumeraciones y rangos
  ``arts. 14, 16 y 19`` produce una referencia por artículo; ``467 a 471`` y ``155–157`` se
  expanden hasta ``MAX_RANGO`` artículos. Un rango mayor conserva sus extremos y deja una
  referencia de COBERTURA INCOMPLETA (``coverage_gap``) que ``audit`` reporta 🟡. Las
  enumeraciones con leyes intercaladas se leen por segmentos, cada uno con SU ley ("los
  artículos 14 de la CPEUM y 42 del CFF"; "16 y 19 de la CPEUM, así como 167 del CNPP").
  Un número ligado a una ley que no se puede extraer con certeza tampoco desaparece: queda
  como cobertura incompleta.

Resolución del ordenamiento: solo por VÍNCULO SINTÁCTICO acreditable
  - A la derecha, pegado al precepto: "artículo 16 de la/del …", "art. 16 CPEUM",
    "16 constitucional", tras fracción/párrafo/inciso del mismo precepto. Una ley que
    solo aparece más adelante en la oración no se asocia.
  - A la izquierda, pegado a la cabeza ("La Ley de Amparo, en su artículo 16", "CFF Art. 42")
    o por posesivo con un único ordenamiento previo en la oración ("La Ley de Amparo regula
    el juicio, y en su artículo 217…").
  - Varias leyes para un grupo solo se reparten con "respectivamente" y el mismo número de
    leyes que de artículos; si no, el grupo queda sin ley.
  - Coordinación pura ("el artículo 14 y el artículo 16 de la CPEUM") comparte el vínculo;
    "ambos"/"todos" lo comparten también tras "así como" o "en relación con".
  - Si hay vínculos en conflicto (izquierda y derecha distintas) o un ordenamiento concreto
    fuera del catálogo ("Código de Comercio", "Código Penal para el Estado de México"), la
    ley queda NO IDENTIFICADA, con su motivo.
  - Sin vínculo: contexto previo (oraciones anteriores, ≤ ``VENTANA_PREVIA`` caracteres hacia
    atrás; ``law_inferred=True``). Si la mención está en otro párrafo y no es un encabezado
    inequívoco (línea que es solo la denominación), la referencia pide confirmar la ley
    (``law_requires_confirmation=True``; ``audit`` la limita a 🟡).
  Las coincidencias son por palabra o abreviatura completa ("Olivares" no es LIVA);
  "constitución" sola no identifica la CPEUM y "constitucional" solo cuenta junto al
  precepto. Un genérico ligado ("de la ley", "del código") exige un antecedente único de
  tipo compatible.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Mapping, NamedTuple, Optional

MAX_RANGO = 20            # un rango de más artículos conserva solo sus extremos (y avisa)
VENTANA_DERECHA = 250     # tope de distancia (caracteres) dentro de la oración
VENTANA_IZQUIERDA = 250
VENTANA_PREVIA = 600      # contexto previo y antecedentes (la ventana "sticky" de siempre)

# Claves del catálogo que dependen del contexto y nunca se buscan como mención libre:
# "constitución" sola es genérica (R4-D04); "constitucional" solo junto al precepto; "Carta
# Magna" se trata como "la Constitución" sin denominación (criterio del responsable,
# 1-oct-2026: 🟡 hasta confirmar, nunca CPEUM automática).
CLAVES_CONTEXTUALES = frozenset({"constitución", "constitucional", "carta magna"})
CLAVE_CONSTITUCIONAL = "constitucional"

# Sufijos latinos de la numeración, en su forma CANÓNICA (minúsculas, sin acentos ni blancos)
# y en el orden de la numeración. Ronda 2 de la re-ingesta (4-oct-2026): más allá de "decies"
# (la Ley de Hacienda de Jalisco tiene "67 Undecies … Quaterdecies") y la grafía "quintus"
# (CPF "199 Quintus", LFDO "12 Quintus", LFPC "63 QUINTUS"), que ocupa el lugar de "quinquies"
# en el orden pero no se confunde con él al cotejar (la designación se compara tal cual).
LATINOS = (
    "bis", "ter", "quater", "quinquies", "quintus", "sexies", "septies", "octies", "nonies",
    "decies", "undecies", "duodecies", "terdecies", "quaterdecies", "quindecies",
    "sexiesdecies", "septiesdecies", "octiesdecies", "noviesdecies", "vicies",
)
# Grafías de cada forma canónica (``{s}`` = el blanco admitido entre palabras): "Sexies Decies",
# "Sexdecies", "Novies Decies"… Se prueban de la más larga a la más corta.
_GRAFIAS_LATINAS = {
    "quater": r"qu[aá]ter",
    "quaterdecies": r"qu[aá]ter{s}*decies",
    "sexiesdecies": r"sex(?:ies)?{s}*decies",
    "septiesdecies": r"septies{s}*decies",
    "octiesdecies": r"octies{s}*decies",
    "noviesdecies": r"no(?:v|n)ies{s}*decies",
}
# Rango en el orden de la numeración (bis = 1); "quintus" comparte el de "quinquies".
_RANGO_LATINO = {latino: indice + 1 for indice, latino in enumerate(
    ("bis", "ter", "quater", "quinquies", "sexies", "septies", "octies", "nonies", "decies",
     "undecies", "duodecies", "terdecies", "quaterdecies", "quindecies", "sexiesdecies",
     "septiesdecies", "octiesdecies", "noviesdecies", "vicies")
)}
_RANGO_LATINO["quintus"] = _RANGO_LATINO["quinquies"]


def patron_latinos(espacio: str = r"\s") -> str:
    """Alternativa (sin grupo de captura) de TODOS los sufijos latinos en cualquiera de sus
    grafías, de la más larga a la más corta ("terdecies" antes que "ter", "sexies decies" antes
    que "sexies"). Para texto sin acentos o con ellos, con IGNORECASE. Gramática única:
    extracción, encabezado exacto, variantes con sufijo, prueba de inexistencia y ingesta."""
    grafias = [_GRAFIAS_LATINAS.get(latino, latino).replace("{s}", espacio) for latino in LATINOS]
    return "(?:" + "|".join(sorted(grafias, key=len, reverse=True)) + ")"


def patron_latino(latino: str, espacio: str = r"\s") -> str:
    """Grafías de UN sufijo latino canónico ("sexiesdecies" → "sex(?:ies)?\\s*decies")."""
    return "(?:" + _GRAFIAS_LATINAS.get(latino, re.escape(latino)).replace("{s}", espacio) + ")"


def canon_latino(texto: str) -> str:
    """Forma canónica de un sufijo latino escrito ("Sexies Decies" → "sexiesdecies",
    "Quáter" → "quater", "Sexdecies" → "sexiesdecies"); "" si no es uno."""
    plano = re.sub(r"\s+", "", sin_acentos(texto or "").lower())
    for latino in LATINOS:
        if re.fullmatch(patron_latino(latino, r"\s"), plano, re.IGNORECASE):
            return latino
    return ""


def rango_latino(latino: str) -> int:
    """Lugar del sufijo latino canónico en la numeración (0 si no hay)."""
    return _RANGO_LATINO.get(latino, 0)

# Métodos de resolución de la ley (campo ``law_method`` de cada referencia).
METODO_DERECHA = "adyacente_derecha"
METODO_IZQUIERDA = "adyacente_izquierda"
METODO_POSESIVO = "posesivo"
METODO_ANTECEDENTE = "antecedente"
METODO_PREVIO = "contexto_previo"
METODO_ENCABEZADO = "encabezado"
METODO_PREVIO_OTRO_PARRAFO = "contexto_previo_otro_parrafo"

MOTIVO_SIN_MENCION = (
    "el texto no liga el artículo a un ordenamiento (ni a su derecha ni a su izquierda) "
    "ni lo nombra en las oraciones previas"
)
MOTIVO_CONFIRMAR = "ley inferida de otro párrafo: confirmar el ordenamiento"


def sin_acentos(texto: str) -> str:
    """NFD sin marcas diacríticas; conserva mayúsculas y longitud por carácter base."""
    descompuesto = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


# ─────────────────────────────────────────
# DESIGNACIÓN DEL ARTÍCULO
# ─────────────────────────────────────────
# Todas las expresiones se compilan con IGNORECASE; ``(?-i:…)`` exige minúscula u otra caja.
_FIN_PALABRA = r"(?![^\W\d_])"   # no lo sigue una letra (sí un dígito, signo o espacio)
_LATINO_ALT = patron_latinos(r"\s")
_ORDINAL = rf"(?:(?-i:[oa]){_FIN_PALABRA}|[ºª])"
# Letra: "-A" / ".-A" (con guion; cualquier caja; no un inciso "-a)") o "A" pegada al número
# (solo mayúscula).
_LETRA = rf"(?:\.?-[A-Za-z]{_FIN_PALABRA}(?!\))|(?-i:[A-Z]){_FIN_PALABRA})"
_LATINO = rf"(?:\.?\s*-?\s*{_LATINO_ALT}{_FIN_PALABRA})"
# Ordinales (3-oct-2026, ronda 2): "°" seguido de un sufijo ("4°-A", "1°. Bis") es el ordinal
# del número y se conserva con el sufijo; solo el grado final ("259°") se descarta. Antes
# "CFF Art. 4°-A." se extraía como "4" (la letra se perdía) y "artículo 1°. Bis del CFF" como
# "1" sin ley: una referencia truncada que podía acreditarse contra el artículo base.
_ORDINAL_O_GRADO = rf"(?:{_ORDINAL}|°(?=(?:{_LETRA}|{_LATINO})))"
_DESIGNACION = rf"\d+{_ORDINAL_O_GRADO}?{_LETRA}?{_LATINO}?"
# Fracción. R4c (ronda 2): la palabra clave no puede seguir dentro de otra palabra
# ("frente a" ya no es la fracción "ente") y admite "fracc." ("fracc. III" ya no es "acc.").
_CLAVE_FRACCION = r"(?:fracci[oó]n(?![^\W\d_])|fracc?(?:\.|(?![^\W\d_]))|fr(?:\.|(?![^\W\d_])))"
_FRACCION = rf"(?:\s*[,;]?\s*{_CLAVE_FRACCION}\s*([\w\.]+))?"
# Cabeza: "art", "arts", "artículo(s)"; no dentro de otra palabra ("Smart 5", "apart. 3").
_CABEZA = r"(?<![^\W_])art[íi]?(?:culo)?s?\.?\s*"

# Compatibilidad: grupo 1 = designación (con sufijos), grupo 2 = fracción, como el antiguo
# ``ARTICLE_RE`` de OpenNotebook (que solo veía el primer artículo de una enumeración).
ARTICULO_RE = re.compile(_CABEZA + rf"({_DESIGNACION})(?:°)?" + _FRACCION, re.IGNORECASE)

# Cabezas de referencia: "artículo(s)" y, desde la ronda 3, "numeral(es)" y "precepto(s)"
# seguidos de número ("el numeral 16 de la Carta Magna"). Tras otro número o una letra de
# apartado ("artículo 9, numeral 2"), "numeral" es un calificador del precepto, no una cabeza.
_CABEZA_RE = re.compile(
    r"(?<![^\W_])(?:art[íi]?(?:culo)?s?\.?|numeral(?:es)?|preceptos?)\s*(?=\d)",
    re.IGNORECASE,
)
_CALIFICADOR_PREVIO_RE = re.compile(
    r"(?:\d[\w°º.\-]*|(?<![^\W_])[IVXLC]{1,6}|(?<![^\W_])[A-Z]|(?<![^\W_])[a-z]\))[\s,;()]*$"
)
# Ronda 2 de la re-ingesta (4-oct-2026) — Dos formas más de designación:
# - SUBNÚMERO pegado con guion: "58-1" (LFPCA "ARTÍCULO 58-1.-"). "N-M" pegado es designación
#   si M < N; si M ≥ N sigue siendo un rango ("14-16" → 14, 15, 16). La comparación numérica la
#   hace ``_item`` (la expresión no compara números).
# - NÚMERO tras el sufijo latino: "65 Bis 1", "211 bis 7", "343 Ter 2" (LFPC, CPF, CCJ…).
_SUBNUMERO = r"[-–—](?P<sub>\d{1,3})(?!\d)"
_NUMERO_LATINO = r"[ \t]*-?[ \t]*(?P<latnum>\d{1,2})(?![\d/])"


def _item_re(*, subnumero: bool, numero_latino: bool) -> re.Pattern:
    sub = rf"(?:{_SUBNUMERO}|" if subnumero else "(?:"
    latnum = rf"(?:{_NUMERO_LATINO})?" if numero_latino else ""
    return re.compile(
        rf"(?P<num>\d+){sub}(?P<ord>{_ORDINAL_O_GRADO})?(?P<letra>{_LETRA})?)"
        rf"(?:(?P<latino>{_LATINO}){latnum})?"
        rf"(?P<grado>°)?"
        rf"(?:\s*[,;]?\s*{_CLAVE_FRACCION}\s*(?P<fraccion>[\w\.]+))?",
        re.IGNORECASE,
    )


_ITEM_RE = _item_re(subnumero=True, numero_latino=True)
_ITEM_SIN_SUB_RE = _item_re(subnumero=False, numero_latino=True)
_ITEM_SIN_LATNUM_RE = _item_re(subnumero=True, numero_latino=False)
_ITEM_SIMPLE_RE = _item_re(subnumero=False, numero_latino=False)
# Continuación de una enumeración: "14, 16 y 19" · rango: "467 a 471", "155–157", "247-250".
_LISTA_RE = re.compile(r"(?:\s*,\s*(?:(?:y|e)\s+)?|\s+(?:y|e)\s+)(?=\d)", re.IGNORECASE)
_RANGO_RE = re.compile(r"\s*(?:[-–—]|\s(?:a|al)\s)\s*(?=\d)", re.IGNORECASE)
# Nuevo segmento tras la ley de otro: "14 de la CPEUM y 42 del CFF", ", así como 167 del …".
_CONTINUACION_RE = re.compile(
    r"(?:\s*,\s*(?:(?:y|e)\s+)?(?:as[íi]\s+como\s+)?|\s+(?:y|e)\s+|\s+as[íi]\s+como\s+)"
    r"(?:(?:el|los)\s+)?(?=\d)",
    re.IGNORECASE,
)
_CONTINUACION_PYC_RE = re.compile(
    r"\s*;\s*(?:(?:y|e)\s+)?(?:as[íi]\s+como\s+)?(?:(?:el|los)\s+)?(?=\d)", re.IGNORECASE
)
_MESES = (r"enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|"
          r"noviembre|diciembre")
# Un número seguido de una unidad o de un mes no es artículo: "471, 3 días", "10 de junio".
_UNIDAD_RE = re.compile(
    r"\s*(?:d[ií]as?|mes(?:es)?|a[ñn]os?|horas?|semanas?|veces|%|por\s+ciento|fojas?"
    rf"|de\s+(?:{_MESES}))" + _FIN_PALABRA,
    re.IGNORECASE,
)
_NUMERO_RE = re.compile(r"(?<![\w/.\-])\d{1,4}(?![\d/])")
# Un ordinal seguido de "párrafo", "fracción"… es un adjetivo ("2o. párrafo"), no un artículo.
_ORDINAL_ADJETIVO_RE = re.compile(
    r"\.?\s*(?:p[aá]rrafo|fracci[oó]n|apartado|inciso|base|numeral)", re.IGNORECASE
)

_PARTES_RE = re.compile(
    r"^\s*(?P<num>\d+)(?:\s*[-–—]\s*(?P<sub>\d{1,3})|(?P<ord>(?-i:[oa])(?![^\W\d_])|[ºª°])?"
    r"(?:\s*\.?\s*-?\s*(?P<letra>[A-Za-z])(?![^\W\d_]))?)"
    rf"(?:\s*\.?\s*-?\s*(?P<latino>{_LATINO_ALT})(?![^\W\d_])"
    r"(?:\s*-?\s*(?P<latnum>\d{1,2}))?)?"
    r"\s*\.?\s*$",
    re.IGNORECASE,
)


class PartesArticulo(NamedTuple):
    numero: str
    ordinal: str          # "o", "a", "º", "ª", "°" o ""
    letra: str            # "A" (en mayúscula) o ""
    latino: str           # "bis", "ter", "quater"… (forma canónica de ``LATINOS``) o ""
    # Ronda 2 de la re-ingesta (4-oct-2026), campos añadidos con valor por omisión:
    subnumero: str = ""       # "1" en "58-1" (guion y número menor que el artículo)
    numero_latino: str = ""   # "1" en "65 Bis 1"

    @property
    def base(self) -> str:
        """Número con su ordinal, como etiqueta el chunker al número base ("4o", "247")."""
        return self.numero + self.ordinal

    @property
    def con_sufijo(self) -> bool:
        return bool(self.letra or self.latino or self.subnumero)


def partes_articulo(articulo: str) -> Optional[PartesArticulo]:
    """Descompone una designación ("4o.-A", "247 Ter", "32-B Quáter", "58-1", "65 Bis 1",
    "67 Terdecies"); None si no se puede."""
    m = _PARTES_RE.match(sin_acentos(articulo or ""))
    if not m:
        return None
    if m.group("sub") and int(m.group("sub")) >= int(m.group("num")):
        return None   # "14-16" es un rango, no una designación
    return PartesArticulo(
        numero=m.group("num"),
        ordinal=m.group("ord") or "",
        letra=(m.group("letra") or "").upper(),
        latino=canon_latino(m.group("latino") or ""),
        subnumero=m.group("sub") or "",
        numero_latino=m.group("latnum") or "",
    )


def articulo_con_sufijo(articulo: str) -> bool:
    """True si la designación trae letra ("29-A"), sufijo latino ("247 Ter") o subnúmero
    ("58-1")."""
    partes = partes_articulo(articulo)
    return bool(partes and partes.con_sufijo)


def canon_caja(designacion: str) -> str:
    """Misma caja para etiquetas y candidatos (ronda 2, 4-oct-2026): el ordinal pegado al
    número se conserva ("1o", "4o", "1º"); lo demás va en mayúsculas ("29-a" → "29-A",
    "247bis" → "247BIS")."""
    # El indicador ordinal va pegado al número y no lo sigue una minúscula ("1o", "4o-A",
    # "1004oA"); "247bis" no tiene ordinal.
    m = re.match(r"(\d+(?:[oaºª](?![^\W\dA-Z_])|°)?)(.*)", designacion or "", re.DOTALL)
    if not m:
        return (designacion or "").upper()
    return m.group(1) + m.group(2).upper()


# Ordinales (3-oct-2026) — El indicador ordinal masculino no cambia el artículo: "1" ≡ "1o" ≡
# "1º" ≡ "1°" (la CPEUM, el CFF y el CNPP escriben "Artículo 1o.", el Código Civil de Jalisco
# "Artículo 1º.-" y la Ley del ISSSTE "Artículo 1."; el escrito puede citar cualquiera). Solo
# el indicador: el número se compara completo ("1" nunca es "10" ni "11") y los sufijos siguen
# exigiéndose exactos ("1" no es "1o.-A"; "4o.-A" no es "4"). El femenino ("1a", "1ª") no se
# usa en la numeración de artículos: solo coincide consigo mismo.
ORDINALES_MASCULINOS = ("", "o", "º", "°")
ORDINALES_FEMENINOS = ("a", "ª")


def ordinales_equivalentes(ordinal: str) -> tuple[str, ...]:
    """Indicadores ordinales equivalentes al de una designación (incluido él mismo)."""
    if ordinal in ORDINALES_FEMENINOS:
        return ORDINALES_FEMENINOS
    return ORDINALES_MASCULINOS


# Cualquier indicador ordinal, para impedir que una expresión "salte" el que no consumió
# ("1" frente a "1a."; "4" frente a "4o.-A" para esquivar la exclusión del sufijo).
_CUALQUIER_ORDINAL = r"(?:(?-i:[oa])(?![^\W\d_])|[ºª°])"


def _patron_ordinal(ordinal: str) -> str:
    """Expresión del indicador ordinal por equivalencia: el masculino es opcional (o, º, °
    o ninguno) y el femenino obligatorio (a, ª). En ambos casos no puede quedar otro
    indicador sin consumir tras lo reconocido."""
    if ordinal in ORDINALES_FEMENINOS:
        return rf"(?:(?-i:a)(?![^\W\d_])|ª)(?!{_CUALQUIER_ORDINAL})"
    return rf"(?:(?-i:o)(?![^\W\d_])|[º°])?(?!{_CUALQUIER_ORDINAL})"


def _sufijo_letra(espacio: str) -> str:
    # Letra pegada al guion, en cualquier caja ("4o.-A.-", "4o.-a.-", "29-B."), que no es el
    # inicio del cuerpo: "4o.- a) …" (espacio), "4o.-a) …" (inciso) o "4o.- Las …" no lo son.
    return rf"{espacio}*\.?-[A-Za-z](?![^\W\d_])(?!\))"


def _sufijo_latino(espacio: str) -> str:
    return rf"{espacio}*\.?{espacio}*-?{espacio}*{patron_latinos(espacio)}(?![^\W\d_])"


# Ronda 2 de la re-ingesta (4-oct-2026) — Subnúmero pegado ("58-1") y número tras el sufijo
# latino ("65 Bis 1"). El blanco del número latino es solo de la misma línea: "Artículo 65
# Bis\n1. Texto" es el 65 Bis con su fracción o párrafo 1, no el 65 Bis 1.
_SUFIJO_SUBNUMERO = r"[-–—]\d"
_SUFIJO_NUMERO_LATINO = r"[ \t]*-?[ \t]*\d"


def patron_articulo(
    articulo: str,
    *,
    ordinal_estricto: bool = True,
    ordinal_equivalente: bool = False,
    espacio: str = r"[ \t]",
) -> Optional[str]:
    """Expresión (para texto SIN acentos, con IGNORECASE) que reconoce exactamente la
    designación pedida: el número, su ordinal y SOLO los sufijos pedidos.

    "4o" no reconoce "4o.-A" ni "4o.-a"; "29" no reconoce "29-B" ni "29 Bis"; "247 Ter"
    exige el "Ter". Por defecto el ordinal se compara tal como se pidió.
    ``ordinal_equivalente=True`` (ordinales, 3-oct-2026; se activa explícitamente donde se
    necesita: encabezado exacto, variantes con sufijo, cuerpo del precepto) compara el ordinal
    por EQUIVALENCIA (``ordinales_equivalentes``): "1" reconoce "Artículo 1o.", "1º" y "1°",
    y "1o" reconoce "Artículo 1."; nunca "10", "11" ni "1o.-A".
    ``ordinal_estricto=False`` acepta además cualquier otro indicador, también el femenino
    (uso tolerante de las capturas y de la prueba de inexistencia). None si la designación
    no se puede descomponer.

    Ronda 2 de la re-ingesta (4-oct-2026): "58" no reconoce "58-1" y "58-1" exige el "-1";
    "65 Bis" no reconoce "65 Bis 1" y "65 Bis 1" exige el "1" (nunca "65 Bis 10"); los
    sufijos latinos se comparan por su forma canónica en cualquiera de sus grafías ("67
    Terdecies", "Sexies Decies").
    """
    partes = partes_articulo(articulo)
    if partes is None:
        return None
    s = espacio
    patron = rf"(?<!\d){partes.numero}(?!\d)"
    if ordinal_estricto and not ordinal_equivalente:
        patron += re.escape(partes.ordinal)
    elif ordinal_estricto:
        patron += _patron_ordinal(partes.ordinal)
    else:
        # Ordinal opcional; si no se consume, el siguiente carácter no puede ser un ordinal
        # (impide "saltar" la "o" de "4o.-A" para esquivar la exclusión de sufijos).
        patron += rf"{_CUALQUIER_ORDINAL}?(?!{_CUALQUIER_ORDINAL})"
    if partes.subnumero:
        patron += rf"[-–—]{partes.subnumero}(?!\d)"
    elif partes.letra:
        patron += rf"{s}*\.?{s}*-?{s}*{partes.letra}(?![^\W\d_])"
    else:
        patron += rf"(?!{_sufijo_letra(s)})(?!{_SUFIJO_SUBNUMERO})"
    if partes.latino:
        patron += rf"{s}*\.?{s}*-?{s}*{patron_latino(partes.latino, s)}(?![^\W\d_])"
        if partes.numero_latino:
            patron += rf"[ \t]*-?[ \t]*{partes.numero_latino}(?!\d)"
        else:
            patron += rf"(?!{_SUFIJO_NUMERO_LATINO})"
    else:
        patron += rf"(?!{_sufijo_latino(s)})"
    return patron


def patron_designacion_cualquiera(espacio: str = r"[ \t]") -> str:
    """Expresión (texto SIN acentos, con IGNORECASE) de la designación de CUALQUIER artículo
    con la gramática de ``patron_articulo``: número completo y, o bien un subnúmero pegado
    ("58-1"), o bien a lo sumo un indicador ordinal (que no puede quedar sin consumir) y una
    letra; luego a lo sumo un sufijo latino con su número ("65 Bis 1"). Lo que no consume no
    puede seguirlo sin consumir (la misma exclusión que ``patron_articulo`` aplica a un número
    pedido sin sufijo): "4o.-A, fracción II" no se lee como "4o" con "A, fracción…" detrás.

    Re-ingesta por fuente (4-oct-2026): la usan el reconocimiento GENÉRICO del encabezado
    auténtico (``itosturre.audit.evidence.encabezados_autenticos``, con el que la ingesta corta
    y etiqueta) y el encabezado de cualquier artículo que corta el cuerpo del precepto
    (``evidence._ENCABEZADO_SIGUIENTE``, también en la prueba de inexistencia)."""
    s = espacio
    return (
        rf"(?<!\d)\d+(?!\d)"
        rf"(?:[-–—]\d{{1,3}}(?!\d)"
        rf"|{_CUALQUIER_ORDINAL}?(?!{_CUALQUIER_ORDINAL})"
        rf"(?:{s}*\.?{s}*-?{s}*[A-Za-z](?![^\W\d_])|(?!{_sufijo_letra(s)})(?!{_SUFIJO_SUBNUMERO})))"
        rf"(?:{_sufijo_latino(s)}(?:[ \t]*-?[ \t]*\d{{1,2}}(?!\d)|(?!{_SUFIJO_NUMERO_LATINO}))"
        rf"|(?!{_sufijo_latino(s)}))"
    )


def patron_variante_con_sufijo(
    articulo: str, *, ordinal_equivalente: bool = False, espacio: str = r"[ \t]"
) -> Optional[str]:
    """Expresión que reconoce el mismo número y ordinal seguido de CUALQUIER sufijo
    ("4o" → "4o.-A", "29" → "29 Bis", "58" → "58-1"; ronda 2: "65 Bis" → "65 Bis 1"). Sirve
    para saber si el índice solo ofreció variantes. ``ordinal_equivalente=True`` (ordinales,
    3-oct-2026): el ordinal por equivalencia, como en ``patron_articulo`` ("4" → "4o.-A")."""
    partes = partes_articulo(articulo)
    if partes is None:
        return None
    s = espacio
    ordinal = (
        _patron_ordinal(partes.ordinal) if ordinal_equivalente else re.escape(partes.ordinal)
    )
    variantes = rf"{_sufijo_letra(s)}|{_sufijo_latino(s)}|{_SUFIJO_SUBNUMERO}"
    if partes.latino and not partes.numero_latino and not (partes.letra or partes.subnumero):
        # "65 Bis" → su variante "65 Bis 1".
        variantes += (
            rf"|{s}*\.?{s}*-?{s}*{patron_latino(partes.latino, s)}(?![^\W\d_])"
            rf"{_SUFIJO_NUMERO_LATINO}"
        )
    return rf"(?<!\d){partes.numero}(?!\d){ordinal}(?:{variantes})"


# ─────────────────────────────────────────
# CATÁLOGO DE LEYES
# ─────────────────────────────────────────

@dataclass(frozen=True)
class EntradaLey:
    clave: str                 # clave de LAW_SOURCE_MAP o nombre de LAW_ALIASES
    fuente: Optional[str]      # archivo del corpus (None: alias sin fuente)
    patron: re.Pattern
    alias: bool                # True: proviene de LAW_ALIASES (sensible a mayúsculas)


@dataclass(frozen=True)
class CatalogoLeyes:
    entradas: tuple[EntradaLey, ...]
    # Fuente de "constitucional" junto al precepto ("artículo 16 constitucional").
    fuente_constitucional: Optional[str] = None

    @property
    def del_mapa(self) -> tuple[EntradaLey, ...]:
        return tuple(e for e in self.entradas if not e.alias)


def _patron_clave(clave: str, *, ignorar_mayusculas: bool) -> re.Pattern:
    """Palabra o abreviatura completa; los espacios internos admiten cualquier blanco
    (incluido un salto de línea: "Constitución Política de los Estados\\nUnidos")."""
    cuerpo = r"\s+".join(re.escape(token) for token in clave.split())
    flags = re.IGNORECASE if ignorar_mayusculas else 0
    return re.compile(rf"(?<![^\W_]){cuerpo}(?![^\W_])", flags)


def construir_catalogo(
    mapa: Mapping[str, str], alias: Mapping[str, str]
) -> CatalogoLeyes:
    """Catálogo de menciones explícitas. Las claves del mapa no distinguen mayúsculas (como
    antes); los alias que el mapa no cubre se buscan con su caja exacta (como antes)."""
    entradas = [
        EntradaLey(clave, fuente, _patron_clave(clave, ignorar_mayusculas=True), False)
        for clave, fuente in mapa.items()
        if clave not in CLAVES_CONTEXTUALES
    ]
    provisional = CatalogoLeyes(tuple(entradas))
    claves = {clave.lower() for clave in mapa}
    for nombre_alias, nombre_ley in alias.items():
        if nombre_alias.lower() in claves or nombre_alias.lower() in CLAVES_CONTEXTUALES:
            continue
        # La fuente del alias, como antes: la ley del mapa que aparece en el propio alias.
        _, fuente = primera_mencion(nombre_alias.lower(), provisional)
        entradas.append(EntradaLey(
            nombre_ley, fuente, _patron_clave(nombre_alias, ignorar_mayusculas=False), True,
        ))
    return CatalogoLeyes(tuple(entradas), mapa.get(CLAVE_CONSTITUCIONAL))


@dataclass(frozen=True)
class Mencion:
    inicio: int
    fin: int
    clave: str
    fuente: Optional[str]
    alias: bool


def menciones_explicitas(
    texto: str, catalogo: CatalogoLeyes, *, solo_mapa: bool = False
) -> list[Mencion]:
    """Menciones explícitas de ordenamientos, ordenadas, sin las contenidas en otra mayor
    ("Delincuencia Organizada" dentro de "Ley Federal de Delincuencia Organizada")."""
    entradas = catalogo.del_mapa if solo_mapa else catalogo.entradas
    crudas = [
        Mencion(m.start(), m.end(), e.clave, e.fuente, e.alias)
        for e in entradas
        for m in e.patron.finditer(texto)
    ]
    # Mayor alcance primero; a igual alcance, la entrada del mapa y luego la clave más larga.
    crudas.sort(key=lambda x: (x.inicio, -x.fin, x.alias, -len(x.clave)))
    resultado: list[Mencion] = []
    fin_maximo = -1
    for mencion in crudas:
        if mencion.fin <= fin_maximo:
            continue  # contenida en (o idéntica a) una mención ya aceptada
        resultado.append(mencion)
        fin_maximo = mencion.fin
    return resultado


def primera_mencion(texto: str, catalogo: CatalogoLeyes) -> tuple[Optional[str], Optional[str]]:
    """La mención del mapa que aparece primero; a igual posición, la clave más larga."""
    mejor: Optional[Mencion] = None
    for e in catalogo.del_mapa:
        m = e.patron.search(texto)
        if not m:
            continue
        if mejor is None or m.start() < mejor.inicio or (
            m.start() == mejor.inicio and len(e.clave) > len(mejor.clave)
        ):
            mejor = Mencion(m.start(), m.end(), e.clave, e.fuente, False)
    return (mejor.clave, mejor.fuente) if mejor else (None, None)


def ultima_mencion(texto: str, catalogo: CatalogoLeyes) -> tuple[Optional[str], Optional[str]]:
    """La mención del mapa más cercana al final del texto (la que empieza más tarde)."""
    menciones = menciones_explicitas(texto, catalogo, solo_mapa=True)
    if not menciones:
        return (None, None)
    mejor = max(menciones, key=lambda x: (x.inicio, len(x.clave)))
    return (mejor.clave, mejor.fuente)


def tipo_fuente(nombre_archivo: Optional[str]) -> str:
    """Tipo de ordenamiento por el nombre del archivo: constitucion, codigo, ley, reglamento,
    tratado u otro. Sirve para resolver genéricos ("de la ley" no remite a un código)."""
    nombre = sin_acentos(nombre_archivo or "").upper().replace("_", " ").strip()
    if nombre.startswith("CONSTITUCION"):
        return "constitucion"
    if nombre.startswith("CODIGO"):
        return "codigo"
    if nombre.startswith("REG"):
        return "reglamento"
    if nombre.startswith("LEY"):
        return "ley"
    if nombre.startswith(("CONVENCION", "PACTO", "TRATADO")):
        return "tratado"
    return "otro"


# ─────────────────────────────────────────
# ORACIONES Y PÁRRAFOS
# ─────────────────────────────────────────
_CORTE_PARRAFO_RE = re.compile(r"\n[ \t]*\n\s*")
# Inicio de un elemento de lista, encabezado, cita o fila de tabla en Markdown.
_CORTE_LINEA_RE = re.compile(r"\n(?=[ \t]*(?:[-*+•>#]+[ \t]|\||\d{1,3}[.)][ \t]))")
_CORTE_SIGNO_RE = re.compile(r"[;?!|]")
_PUNTO_RE = re.compile(r"\.")
_ABREVIATURAS = frozenset({
    "art", "arts", "fr", "frac", "fracc", "parr", "pag", "pags", "num", "no", "inc", "ap",
    "apdo", "lic", "licda", "sr", "sra", "srta", "dr", "dra", "mtro", "mtra", "ing", "cfr",
    "op", "cit", "vid", "etc", "ed", "vol", "cap", "sec", "tit", "sigs", "ss", "fs", "fol",
    "exp", "reg", "pte", "ref",
})
# Ordinales (3-oct-2026, ronda 2): también "1º." y "1ª." (antes "1º. Bis del CFF" cortaba la
# oración tras el ordinal y la ley quedaba sin vínculo).
_ORDINAL_PALABRA_RE = re.compile(r"\d+[oaºª]")
_SUFIJO_TRAS_PUNTO_RE = re.compile(rf"\s*-?\s*{_LATINO_ALT}{_FIN_PALABRA}", re.IGNORECASE)


def _es_fin_de_oracion(texto: str, i: int) -> bool:
    """¿El punto en ``texto[i]`` cierra la oración? Exige un blanco y luego mayúscula (o fin
    del texto) y que no cierre una abreviatura ("Art.", "Fr.", "C.P.F.", "1o.")."""
    n = len(texto)
    j = i + 1
    while j < n and texto[j] in " \t\r\n":
        j += 1
    if j < n:
        if j == i + 1:
            return False
        siguiente = texto[j]
        if not (siguiente.isupper() or siguiente in "¿¡\"“«(*_#"):
            return False
    k = i
    while k > 0 and texto[k - 1].isalnum():
        k -= 1
    palabra = sin_acentos(texto[k:i]).lower()
    if not palabra:
        # Ronda 2: el punto tras el grado usado como ordinal de una designación con sufijo
        # ("artículo 1°. Bis del CFF") no cierra la oración; antes la ley a la derecha quedaba
        # fuera y el artículo sin ley. Sin sufijo ("artículo 19°. Los hechos…") sí la cierra.
        return not (
            i >= 2 and texto[i - 1] == "°" and texto[i - 2].isdigit()
            and _SUFIJO_TRAS_PUNTO_RE.match(texto, i + 1)
        )
    if palabra in _ABREVIATURAS or (len(palabra) == 1 and palabra.isalpha()):
        return False
    if _ORDINAL_PALABRA_RE.fullmatch(palabra):
        return False
    return True


class _Cortes:
    """Límites de oración y de párrafo de un texto."""

    def __init__(self, texto: str) -> None:
        parrafos = [(m.start(), m.end()) for m in _CORTE_PARRAFO_RE.finditer(texto)]
        spans = list(parrafos)
        spans += [(m.start(), m.start() + 1) for m in _CORTE_LINEA_RE.finditer(texto)]
        spans += [(m.start(), m.end()) for m in _CORTE_SIGNO_RE.finditer(texto)]
        spans += [
            (m.start(), m.end()) for m in _PUNTO_RE.finditer(texto)
            if _es_fin_de_oracion(texto, m.start())
        ]
        spans.sort()
        self._inicios = [a for a, _ in spans]
        # Igual, pero sin el punto y coma: una enumeración de preceptos puede seguir tras él.
        self._inicios_frase = [a for a, _ in spans if texto[a] != ";"]
        self._fines = sorted(b for _, b in spans)
        self._fines_parrafo = [b for _, b in parrafos]
        self._n = len(texto)

    def oracion(self, inicio: int, fin: int) -> tuple[int, int]:
        """(comienzo, final) de la oración que contiene ``texto[inicio:fin]``."""
        k = bisect.bisect_right(self._fines, inicio)
        comienzo = self._fines[k - 1] if k else 0
        k = bisect.bisect_left(self._inicios, fin)
        final = self._inicios[k] if k < len(self._inicios) else self._n
        return comienzo, final

    def fin_frase(self, posicion: int) -> int:
        """Primer corte (que no sea punto y coma) en o después de ``posicion``."""
        k = bisect.bisect_left(self._inicios_frase, posicion)
        return self._inicios_frase[k] if k < len(self._inicios_frase) else self._n

    def parrafo(self, posicion: int) -> int:
        """Número de párrafo (separados por una línea en blanco) de una posición."""
        return bisect.bisect_right(self._fines_parrafo, posicion)


# ─────────────────────────────────────────
# GENÉRICOS, NOMBRES CONCRETOS Y VÍNCULOS
# ─────────────────────────────────────────
_GENERICO_RE = re.compile(
    r"(?<![^\W_])(?P<g>carta\s+magna|leyes|ley|c[óo]digos?|constituci[óo]n|ordenamientos?|"
    r"reglamentos?|tratados?|convenci[óo]n|pacto|norma)(?![^\W_])",
    re.IGNORECASE,
)
_CONSTITUCIONAL_RE = re.compile(r"(?<![^\W_])constitucional(?:es)?(?![^\W_])", re.IGNORECASE)
_TIPOS_GENERICO = {
    "ley": {"ley"}, "leyes": {"ley"},
    "codigo": {"codigo"}, "codigos": {"codigo"},
    "constitucion": {"constitucion"}, "carta magna": {"constitucion"},
    "reglamento": {"reglamento"}, "reglamentos": {"reglamento"},
    "tratado": {"tratado"}, "tratados": {"tratado"},
    "convencion": {"tratado"}, "pacto": {"tratado"},
    "ordenamiento": None, "ordenamientos": None, "norma": None,   # None = cualquier tipo
}
# Calificadores del mismo precepto entre el artículo y su ley ("fracción V", "párrafo
# segundo", "inciso a)", "apartado B", "último párrafo", "in fine").
_CALIFICADORES = frozenset({
    "fraccion", "fracciones", "fr", "frac", "fracc", "parrafo", "parrafos", "parr",
    "apartado", "apartados", "ap", "inciso", "incisos", "inc", "base", "bases", "numeral",
    "numerales", "letra", "parte", "final", "in", "fine",
    "primer", "primero", "primera", "segundo", "segunda", "tercer", "tercero", "tercera",
    "cuarto", "cuarta", "quinto", "quinta", "sexto", "sexta", "septimo", "septima",
    "octavo", "octava", "noveno", "novena", "decimo", "decima", "ultimo", "ultima",
    "penultimo", "penultima",
    *LATINOS, "novies", "sex",
})
_DETERMINANTES = frozenset({
    "la", "el", "los", "las", "esta", "este", "estos", "estas", "dicha", "dicho", "dichas",
    "dichos", "citada", "citado", "citadas", "citados", "referida", "referido", "misma",
    "mismo", "propia", "propio", "presente", "aludida", "aludido", "invocada", "invocado",
    "mencionada", "mencionado", "senalada", "senalado", "nuestra", "nuestro",
})
_DISTRIBUTIVOS = frozenset({"ambos", "ambas", "todos", "todas"})
_PREVIAS_A_LETRA = frozenset({"inciso", "incisos", "inc", "letra", "apartado", "apartados", "ap"})
_FUNCIONALES_DE_UNA_LETRA = frozenset({"y", "e", "o", "u", "a"})
# Entre la ley y la cabeza a su izquierda: "La Ley de Amparo, en su artículo 16", "CFF Art. 42".
_ENLACE_IZQUIERDO = frozenset({"en", "su", "sus", "el", "los", "la", "las", "al", "a"})
# Brecha que comparte el vínculo entre artículos coordinados ("el 14 y el artículo 16 de …").
_COORDINACION = frozenset({"y", "e", "el", "los", "la", "las"})
_COORDINACION_DISTRIBUTIVA = _COORDINACION | {
    "asi", "como", "en", "relacion", "con", "al", "igual", "que", "del", "de",
}
_ROMANO_RE = re.compile(r"[ivxlcdm]+")
# Tras el genérico, estas palabras lo convierten en un ordenamiento concreto ("ley fiscal",
# "Constitución local"): no es una remisión a un antecedente.
_MODIFICADORES = frozenset({
    "local", "locales", "estatal", "estatales", "federal", "federales", "general",
    "generales", "nacional", "nacionales", "organica", "organico", "reglamentaria",
    "secundaria", "fiscal", "fiscales", "tributaria", "tributario", "penal", "penales",
    "civil", "civiles", "mercantil", "mercantiles", "laboral", "agraria", "agrario",
    "procesal", "adjetiva", "adjetivo", "sustantiva", "sustantivo", "punitivo", "electoral",
    "administrativa", "administrativo", "aduanera", "bancaria", "militar", "municipal",
    "politica", "internacional", "americana", "interamericana", "sanitaria", "ambiental",
    "burocratica", "abrogada", "anterior", "interior", "interno",
})
_CONECTORES_NOMBRE = frozenset({
    "de", "del", "para", "sobre", "en", "la", "las", "los", "el", "y", "e", "contra",
})
_REMISIONES = ("la materia", "referencia", "cita")
_ENTIDADES = frozenset({"estado", "ciudad", "municipio", "entidad"})
_TOKEN_RE = re.compile(r"\s+([^\W\d_]+)")
_RESPECTIVAMENTE_RE = re.compile(r"\s*,?\s*respectivamente(?![^\W_])", re.IGNORECASE)
_POSESIVO_RE = re.compile(r"(?<![^\W_])sus?\s*$", re.IGNORECASE)


def _palabras(texto: str) -> list[str]:
    """Palabras (sin acentos, minúsculas); la letra de un ordinal ("2o", "1a") no cuenta."""
    return re.findall(r"(?<!\d)[^\W\d_]+", sin_acentos(texto).lower())


def _es_calificador(palabras: list[str], i: int) -> bool:
    palabra = palabras[i]
    if palabra in _CALIFICADORES or _ROMANO_RE.fullmatch(palabra):
        return True
    if len(palabra) == 1:
        # Letra de inciso ("inciso a)"); "y", "e", "a" sueltas son palabras, no incisos.
        return palabra not in _FUNCIONALES_DE_UNA_LETRA or (
            i > 0 and palabras[i - 1] in _PREVIAS_A_LETRA
        )
    return False


def _vinculo_derecho(entre: str, *, sin_preposicion: bool = False) -> Optional[bool]:
    """¿El tramo entre el artículo y una ley a su derecha es un vínculo sintáctico?

    Gramática: calificadores del precepto → "ambos"/"todos" opcional → "de"/"del" opcional →
    determinantes (solo tras la preposición). Devuelve None si no hay vínculo; si lo hay,
    True cuando es distributivo ("…, ambos de la CPEUM"). ``sin_preposicion``: solo admite
    el vínculo pegado ("16 constitucional").
    """
    palabras = _palabras(entre)
    i, n = 0, len(palabras)
    while i < n:
        if _es_calificador(palabras, i):
            i += 1
            continue
        if palabras[i] in ("y", "e") and i + 1 < n and _es_calificador(palabras, i + 1):
            i += 1
            continue
        break
    compartido = i < n and palabras[i] in _DISTRIBUTIVOS
    if compartido:
        i += 1
    preposicion = i < n and palabras[i] in ("de", "del")
    if preposicion:
        i += 1
    determinantes = 0
    while i < n and palabras[i] in _DETERMINANTES:
        i += 1
        determinantes += 1
    if i != n or (determinantes and not preposicion):
        return None
    if sin_preposicion and (preposicion or determinantes):
        return None
    return compartido


def _union_de_leyes(entre: str, *, sin_preposicion: bool = False) -> bool:
    """Entre dos leyes de un mismo grupo: "y del", ", de la", "y de los"… Un número en medio
    abre otro segmento ("de la CPEUM y 42 del CFF"), no une leyes. ``sin_preposicion``
    admite además "y el", ", la" (solo se usa si el grupo termina en "respectivamente")."""
    if re.search(r"\d", entre):
        return False
    palabras = _palabras(entre)
    i, n = 0, len(palabras)
    coordinada = i < n and palabras[i] in ("y", "e")
    if coordinada:
        i += 1
    if i < n and palabras[i] in ("de", "del"):
        i += 1
    elif not sin_preposicion or not (coordinada or "," in entre):
        return False
    while i < n and palabras[i] in _DETERMINANTES:
        i += 1
    return i == n


def _es_brecha(entre: str, permitidas: frozenset) -> bool:
    return all(p in permitidas for p in _palabras(entre))


def _tramo_concreto(texto: str, fin_generico: int) -> Optional[tuple[str, int]]:
    """Si tras el genérico sigue un nombre propio ("Ley General de Salud") o un modificador
    ("ley fiscal", "Constitución local"), devuelve (tramo, fin): es un ordenamiento concreto.
    None si el genérico remite a un antecedente ("de la ley establece", "de dicho código")."""
    m = _TOKEN_RE.match(texto, fin_generico)
    if not m:
        return None   # puntuación o fin: remisión
    primero = m.group(1)
    normal = sin_acentos(primero).lower()
    if primero[0].isupper() and normal not in _CONECTORES_NOMBRE:
        pass
    elif normal in _MODIFICADORES:
        pass
    elif normal in {"de", "del", "para", "sobre"}:
        siguiente = sin_acentos(texto[m.end():m.end() + 30]).lower().lstrip()
        if any(siguiente.startswith(r) for r in _REMISIONES):
            return None
    else:
        return None
    # Tramo del nombre: palabras con mayúscula, modificadores y conectores (máx. 12).
    partes: list[tuple[str, int]] = []
    posicion = fin_generico
    while len(partes) < 12:
        t = _TOKEN_RE.match(texto, posicion)
        if not t:
            break
        palabra = t.group(1)
        normal = sin_acentos(palabra).lower()
        if not (palabra[0].isupper() or normal in _MODIFICADORES or normal in _CONECTORES_NOMBRE):
            break
        partes.append((palabra, t.end()))
        posicion = t.end()
    while partes and sin_acentos(partes[-1][0]).lower() in _CONECTORES_NOMBRE:
        partes.pop()
    if not partes:
        # Conectores y el primer sustantivo, como contexto: "de la sociedad", "del estado".
        posicion = fin_generico
        while True:
            t = _TOKEN_RE.match(texto, posicion)
            if not t:
                break
            partes.append((t.group(1), t.end()))
            posicion = t.end()
            if sin_acentos(t.group(1)).lower() not in _CONECTORES_NOMBRE:
                break
    if not partes:
        return None
    return " ".join(p for p, _ in partes), partes[-1][1]


def _entidad_ajena(texto: str, fin: int) -> Optional[int]:
    """Si tras una mención del catálogo sigue "del Estado de México", "para el Estado de …",
    "de la Ciudad de México"…, es otro ordenamiento homónimo: devuelve el fin de ese tramo."""
    t = _TOKEN_RE.match(texto, fin)
    if not t or sin_acentos(t.group(1)).lower() not in {"del", "para", "de"}:
        return None
    posicion, ajena, ultimo = fin, False, fin
    for _ in range(12):
        t = _TOKEN_RE.match(texto, posicion)
        if not t:
            break
        palabra = t.group(1)
        normal = sin_acentos(palabra).lower()
        if not (palabra[0].isupper() or normal in _CONECTORES_NOMBRE or normal in _ENTIDADES):
            break
        ajena = ajena or normal in _ENTIDADES
        posicion = t.end()
        if normal not in _CONECTORES_NOMBRE:
            ultimo = posicion
    return ultimo if ajena else None


@dataclass(frozen=True)
class _Elemento:
    """Una ley candidata en el texto: explícita, "constitucional", concreta (fuera del
    catálogo) o genérica (remisión a un antecedente)."""
    inicio: int
    fin: int
    tipo: str
    mencion: Optional[Mencion] = None
    nombre: str = ""


_PRIORIDAD = {"explicita": 0, "concreta": 1, "constitucional": 2, "generica": 3}


class _Menciones:
    """Menciones explícitas indexadas por posición; las calificadas por otra entidad
    ("… del Estado de México") se tratan como ordenamientos concretos fuera del catálogo."""

    def __init__(self, texto: str, menciones: list[Mencion]) -> None:
        self.texto = texto
        self.todas = menciones                       # ordenadas por inicio
        self.inicios = [m.inicio for m in menciones]
        self.ajenas: dict[tuple[int, int], int] = {}
        for m in menciones:
            fin = _entidad_ajena(texto, m.fin)
            if fin:
                self.ajenas[(m.inicio, m.fin)] = fin

    def cubre(self, posicion: int) -> bool:
        """¿La posición cae dentro de una mención explícita? ("Ley" de "Ley de Amparo")."""
        k = bisect.bisect_right(self.inicios, posicion)
        return any(m.inicio <= posicion < m.fin for m in self.todas[max(0, k - 3):k])

    def elementos(self, desde: int, hasta: int) -> list[_Elemento]:
        """Leyes candidatas que empiezan en ``[desde, hasta)``, en orden."""
        texto = self.texto
        elementos: list[_Elemento] = []
        k = bisect.bisect_left(self.inicios, desde)
        for m in self.todas[k:bisect.bisect_left(self.inicios, hasta)]:
            fin_ajena = self.ajenas.get((m.inicio, m.fin))
            if fin_ajena:
                elementos.append(_Elemento(m.inicio, fin_ajena, "concreta",
                                           nombre=texto[m.inicio:fin_ajena]))
            else:
                elementos.append(_Elemento(m.inicio, m.fin, "explicita", mencion=m))
        for c in _CONSTITUCIONAL_RE.finditer(texto, desde, hasta):
            elementos.append(_Elemento(c.start(), c.end(), "constitucional", nombre=c.group(0)))
        for g in _GENERICO_RE.finditer(texto, desde, hasta):
            if self.cubre(g.start()):
                continue
            tramo = _tramo_concreto(texto, g.end())
            if tramo:
                elementos.append(_Elemento(g.start(), tramo[1], "concreta",
                                           nombre=f"{g.group(0)} {tramo[0]}"))
            else:
                elementos.append(_Elemento(g.start(), g.end(), "generica", nombre=g.group(0)))
        elementos.sort(key=lambda e: (e.inicio, _PRIORIDAD[e.tipo]))
        return elementos

    def mapa_entre(self, desde: int, hasta: int) -> list[Mencion]:
        """Menciones del mapa (no alias, no de otra entidad) completas en ``[desde, hasta)``."""
        k = bisect.bisect_left(self.inicios, desde)
        return [
            m for m in self.todas[k:bisect.bisect_left(self.inicios, hasta)]
            if m.fin <= hasta and not m.alias and (m.inicio, m.fin) not in self.ajenas
        ]


@dataclass(frozen=True)
class _Enlace:
    """Ley(es) ligadas a la derecha de un segmento."""
    elementos: tuple[_Elemento, ...]
    fin: int
    compartido: bool          # "…, ambos de la CPEUM"
    respectivamente: bool


def _enlace_derecho(texto: str, desde: int, tope: int, menciones: _Menciones) -> Optional[_Enlace]:
    """La ley pegada al precepto a su derecha (y las que la siguen unidas por "y de/del"),
    o None si la primera ley de la oración no está ligada al artículo."""
    alcance = min(tope, desde + VENTANA_DERECHA)
    candidatos = menciones.elementos(desde, alcance)
    if not candidatos:
        return None
    primero = candidatos[0]
    compartido = _vinculo_derecho(
        texto[desde:primero.inicio], sin_preposicion=primero.tipo == "constitucional"
    )
    if compartido is None:
        return None
    def encadenar(sin_preposicion: bool) -> tuple[list[_Elemento], int]:
        cadena, posicion = [primero], primero.fin
        if primero.tipo == "constitucional":
            return cadena, posicion
        for siguiente in menciones.elementos(posicion, tope):
            if siguiente.inicio < posicion:
                continue
            if siguiente.tipo == "constitucional" or not _union_de_leyes(
                texto[posicion:siguiente.inicio], sin_preposicion=sin_preposicion
            ):
                break
            cadena.append(siguiente)
            posicion = siguiente.fin
        return cadena, posicion

    cadena, posicion = encadenar(False)
    respectivamente = _RESPECTIVAMENTE_RE.match(texto, posicion)
    if not respectivamente:
        # "de la CPEUM y el CFF, respectivamente": sin repetir "de/del" solo si el grupo
        # termina en "respectivamente" (si no, "y el CFF" puede ser otro sujeto).
        amplia, fin_amplia = encadenar(True)
        reparto = _RESPECTIVAMENTE_RE.match(texto, fin_amplia)
        if reparto and len(amplia) > len(cadena):
            cadena, posicion, respectivamente = amplia, fin_amplia, reparto
    fin = respectivamente.end() if respectivamente else posicion
    return _Enlace(tuple(cadena), fin, compartido, bool(respectivamente))


@dataclass(frozen=True)
class Resolucion:
    clave: str                 # clave o nombre de la ley ("desconocido" si no se identificó)
    fuente: Optional[str]
    inferida: bool
    metodo: Optional[str]
    motivo: Optional[str]      # solo si la ley no se identificó
    confirmar: bool = False    # ley inferida de otro párrafo: el semáforo se limita a 🟡


def _no_identificada(motivo: str) -> Resolucion:
    return Resolucion("desconocido", None, False, None, motivo)


def _es_encabezado(texto: str, mencion: Mencion) -> bool:
    """¿La línea de la mención es solo la denominación de la ley (encabezado inequívoco)?
    "## Constitución Política de los Estados Unidos Mexicanos", "**LEY DE AMPARO**",
    "II. Código Fiscal de la Federación (CFF)". No lo es "### A. Orden constitucional (CPEUM)"."""
    inicio_linea = texto.rfind("\n", 0, mencion.inicio) + 1
    fin_linea = texto.find("\n", mencion.fin)
    fin_linea = len(texto) if fin_linea == -1 else fin_linea
    antes = texto[inicio_linea:mencion.inicio]
    if not re.fullmatch(
        r"[ \t]*(?:[#>|•*+\-_]+[ \t]*)*(?:(?:\d{1,3}|[IVXLC]{1,6}|[A-Za-z])[.)][ \t]+)?[*_]*",
        antes,
    ):
        return False
    despues = texto[mencion.fin:fin_linea]
    return bool(re.fullmatch(
        r"(?:[ \t]+(?:[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ]*|de|del|la|las|los|y|e)){0,4}"
        r"[ \t]*(?:\([ \t]*[A-ZÁÉÍÓÚÑ][\wÁÉÍÓÚÑáéíóúñ. ]{0,20}\))?[ \t*_:.|]*",
        despues,
    ))


def _resolver_previa(
    texto: str, mencion: Mencion, posicion: int, cortes: _Cortes, metodo_mismo: str
) -> Resolucion:
    """Ley inferida de una mención anterior: en el mismo párrafo, como siempre; desde otro
    párrafo, solo sin confirmación si la mención es un encabezado inequívoco."""
    if cortes.parrafo(mencion.inicio) == cortes.parrafo(posicion):
        return Resolucion(mencion.clave, mencion.fuente, True, metodo_mismo, None)
    if _es_encabezado(texto, mencion):
        return Resolucion(mencion.clave, mencion.fuente, True, METODO_ENCABEZADO, None)
    metodo = METODO_ANTECEDENTE if metodo_mismo == METODO_ANTECEDENTE else METODO_PREVIO_OTRO_PARRAFO
    return Resolucion(mencion.clave, mencion.fuente, True, metodo, None, confirmar=True)


def _resolver_generico(
    texto: str, elemento: _Elemento, menciones: _Menciones, fin_busqueda: int, cortes: _Cortes
) -> Resolucion:
    """Genérico ligado ("de la ley", "dicha ley, en su artículo"): exige un antecedente único
    de tipo compatible en el contexto previo."""
    palabra = re.sub(r"\s+", " ", elemento.nombre)
    tipos = _TIPOS_GENERICO.get(sin_acentos(palabra).lower())
    inicio = max(0, fin_busqueda - VENTANA_PREVIA)
    candidatas = [
        m for m in menciones.mapa_entre(inicio, fin_busqueda)
        if m.fuente and (tipos is None or tipo_fuente(m.fuente) in tipos)
    ]
    # Los ordenamientos concretos fuera del catálogo ("la Ley General de Salud") también son
    # antecedentes posibles (ronda 3): con uno de ellos y una ley del catálogo, "la ley" es
    # ambigua; si el único antecedente está fuera del catálogo, la ley no se identifica.
    concretas = [
        e for e in menciones.elementos(inicio, fin_busqueda)
        if e.tipo == "concreta" and e.fin <= fin_busqueda
        and (tipos is None or tipo_fuente(e.nombre) in tipos)
    ]
    identidades = {m.fuente for m in candidatas} | {
        "¿" + sin_acentos(re.sub(r"\s+", " ", e.nombre)).lower() for e in concretas
    }
    if len(identidades) == 1 and candidatas:
        elegida = max(candidatas, key=lambda x: (x.inicio, len(x.clave)))
        return _resolver_previa(texto, elegida, fin_busqueda, cortes, METODO_ANTECEDENTE)
    if len(identidades) == 1:
        return _no_identificada(
            f"el antecedente de '{palabra}' es {_motivo_concreto(concretas[-1].nombre)}"
        )
    if not identidades:
        if sin_acentos(palabra).lower() in ("constitucion", "carta magna"):
            return _no_identificada(
                f"'{palabra}' sin denominación ('Constitución Política de los Estados Unidos "
                "Mexicanos', 'Constitución Federal') ni abreviatura (CPEUM) no identifica el "
                "ordenamiento, y no hay un antecedente inequívoco"
            )
        return _no_identificada(
            f"'{palabra}' no tiene un antecedente inequívoco: antes no se nombra ningún "
            "ordenamiento compatible"
        )
    nombres = sorted({m.clave for m in candidatas} | {e.nombre for e in concretas})
    return _no_identificada(
        f"'{palabra}' es ambiguo: antes se nombran varios ordenamientos compatibles "
        f"({', '.join(nombres)})"
    )


def _motivo_concreto(nombre: str) -> str:
    return (
        f"ordenamiento fuera del catálogo: '{nombre}' (no es una ley del corpus, es de otra "
        "entidad o su denominación está incompleta)"
    )


def _resolver_elemento(
    texto: str, elemento: _Elemento, metodo: str, catalogo: CatalogoLeyes,
    menciones: _Menciones, posicion: int, cortes: _Cortes,
) -> Resolucion:
    if elemento.tipo == "explicita":
        m = elemento.mencion
        return Resolucion(m.clave, m.fuente, False, metodo, None)
    if elemento.tipo == "constitucional":
        if not catalogo.fuente_constitucional:
            return _no_identificada("'constitucional' sin fuente asociada en el catálogo")
        return Resolucion(CLAVE_CONSTITUCIONAL, catalogo.fuente_constitucional, False, metodo, None)
    if elemento.tipo == "concreta":
        return _no_identificada(_motivo_concreto(elemento.nombre))
    return _resolver_generico(texto, elemento, menciones, posicion, cortes)


def _identidad(resolucion: Resolucion) -> str:
    return resolucion.fuente or resolucion.clave + "|" + (resolucion.motivo or "")


# ─────────────────────────────────────────
# EXTRACCIÓN
# ─────────────────────────────────────────

@dataclass(frozen=True)
class _Item:
    articulo: str
    fraccion: str
    fin_raw: int     # fin del tramo citado para ``raw`` (un rango comparte el del extremo final)
    # Ronda 2 (falla cerrada): lo que continúa la designación sin haberse extraído, o None.
    incompleta: Optional[str] = None


@dataclass
class _Unidad:
    """Segmento de una enumeración: artículos seguidos (o no) de su propia ley."""
    grupo: int
    primera: bool          # primer segmento del grupo (admite la ley a la izquierda)
    cabeza: int            # inicio de la cabeza del grupo
    inicio: int            # inicio del segmento (cabeza, o separador de la continuación)
    items_inicio: int      # inicio del primer artículo (tras la cabeza o el separador)
    fin: int               # fin del último artículo del segmento
    items: list[_Item]
    excedidos: list[tuple[int, int, int]]   # rangos recortados: (desde, hasta, artículos)
    oracion: tuple[int, int]
    enlace: Optional[_Enlace] = None
    resolucion: Optional[Resolucion] = None
    por_item: Optional[list[Resolucion]] = None
    huerfanos: list[tuple[str, int, int, Resolucion]] = field(default_factory=list)


def _grupo(m: re.Match, nombre: str) -> Optional[str]:
    """Grupo ``nombre`` de ``m`` o None si la expresión no lo tiene (variantes de ``_item``)."""
    return m.group(nombre) if nombre in m.re.groupindex else None


def _designacion(m: re.Match) -> str:
    """Designación tal como se escribió (blancos internos normalizados), sin el grado. Ronda 2:
    con su subnúmero ("58-1") y el número tras el sufijo latino ("65 Bis 1")."""
    articulo = m.group("num") + (m.group("ord") or "") + (m.group("letra") or "")
    if _grupo(m, "sub"):
        articulo += "-" + _grupo(m, "sub")
    if m.group("latino"):
        articulo += re.sub(r"\s+", " ", m.group("latino"))
        if _grupo(m, "latnum"):
            articulo += " " + _grupo(m, "latnum")
    return articulo


def _es_simple(m: re.Match) -> bool:
    return not (m.group("letra") or m.group("latino") or m.group("fraccion") or _grupo(m, "sub"))


def _item(texto: str, posicion: int) -> Optional[re.Match]:
    """Artículo que empieza en ``posicion`` (ronda 2 de la re-ingesta, 4-oct-2026).

    "N-M" pegado es una designación solo si M < N ("58-1"); con M ≥ N se relee sin subnúmero
    para que el guion sea un rango ("14-16"). El número tras el sufijo latino ("65 Bis 1") no
    se toma si lo sigue una unidad o un mes ("5 bis 10 días"): se relee sin él (y
    ``_continuacion_no_extraida`` lo marca)."""
    m = _ITEM_RE.match(texto, posicion)
    if m is None:
        return None
    sub_valido = not _grupo(m, "sub") or int(_grupo(m, "sub")) < int(m.group("num"))
    latnum_valido = not _grupo(m, "latnum") or not _UNIDAD_RE.match(texto, m.end("latnum"))
    if sub_valido and latnum_valido:
        return m
    if sub_valido:
        return _ITEM_SIN_LATNUM_RE.match(texto, posicion)
    otra = _ITEM_SIN_SUB_RE.match(texto, posicion)
    if otra is not None and _grupo(otra, "latnum") and _UNIDAD_RE.match(texto, otra.end("latnum")):
        otra = _ITEM_SIMPLE_RE.match(texto, posicion)
    return otra


# Ronda 2 (falla cerrada) — Lo que sigue a la designación extraída y la CONTINÚA sin haberse
# extraído: un número tras el sufijo latino que no se tomó ("65 Bis 123", "5 bis 10 días"), un
# segundo subnúmero ("58-1-2"), un rango tras el número latino ("65 Bis 1-3") o una palabra con
# forma de sufijo latino que la gramática no conoce ("247 Undevicies"). Esa cita nunca se
# acredita contra una designación truncada: queda como cobertura incompleta (🟡).
_CONTINUA_TRAS_LATINO = re.compile(r"[ \t]*-?[ \t]*\d")
_CONTINUA_TRAS_NUMERO = re.compile(r"[-–—]\d|[ \t]+al?[ \t]+\d", re.IGNORECASE)
_PALABRA_SIGUIENTE = re.compile(r"[ \t]*\.?[ \t]*-?[ \t]*([^\W\d_]+(?:[ \t]+decies)?)", re.IGNORECASE)


def _continuacion_no_extraida(texto: str, m: re.Match) -> Optional[str]:
    """Fragmento que continúa la designación de ``m`` sin haberse extraído, o None."""
    fin = max(m.end(g) for g in ("num", "sub", "ord", "letra", "latino", "latnum")
              if _grupo(m, g) is not None)

    def fragmento(hasta: int) -> str:
        return " ".join(texto[m.start("num"):hasta].split("\n")[0].split())

    if m.group("latino") and not _grupo(m, "latnum"):
        sigue = _CONTINUA_TRAS_LATINO.match(texto, fin)
        if sigue:
            return fragmento(sigue.end() + 3)
    if (_grupo(m, "sub") or _grupo(m, "latnum")):
        sigue = _CONTINUA_TRAS_NUMERO.match(texto, fin)
        if sigue:
            return fragmento(sigue.end())
    palabra = _PALABRA_SIGUIENTE.match(texto, fin)
    if palabra:
        escrita = sin_acentos(palabra.group(1)).lower()
        # Un sufijo latino conocido que la gramática no consumió (un segundo sufijo: "247 Bis
        # Ter") o una palabra con forma de sufijo latino que no conoce ("Undevicies").
        if canon_latino(escrita) or re.search(r"(?:ies|us)$", escrita):
            return fragmento(palabra.end())
    return None


def _continuacion_valida(texto: str, m: Optional[re.Match]) -> bool:
    if not m or len(m.group("num")) > 4:
        return False
    if texto[m.end("num"):m.end("num") + 1] == "/":   # "3/2019" no es artículo
        return False
    if m.group("ord") and _ORDINAL_ADJETIVO_RE.match(texto, m.end("ord")):
        return False
    return not _UNIDAD_RE.match(texto, m.end("num"))


def _leer_segmento(
    texto: str, desde: int, *, continuacion: bool
) -> Optional[tuple[list[_Item], int, list[tuple[int, int, int]]]]:
    """Artículos de un segmento que empieza en ``desde``: (artículos, fin, rangos recortados)."""
    primero = _item(texto, desde)
    if not primero or (continuacion and not _continuacion_valida(texto, primero)):
        return None
    crudos: list[tuple[re.Match, Optional[re.Match]]] = [(primero, None)]
    posicion = primero.end()
    while True:
        anterior = crudos[-1][1] or crudos[-1][0]
        # El punto de un ordinal no corta la enumeración ni el rango: "artículos 1o. y 2o.",
        # "1o.-25o.".
        desde_lista = posicion
        if anterior.group("ord") and texto[posicion:posicion + 1] == ".":
            desde_lista += 1
        rango = _RANGO_RE.match(texto, desde_lista)
        if rango and _es_simple(anterior) and crudos[-1][1] is None:
            final = _item(texto, rango.end())
            # Con ordinal o grado ("1º-25º", "1°-25°") es un rango igual que sin ellos.
            if _continuacion_valida(texto, final) and _es_simple(final):
                crudos[-1] = (crudos[-1][0], final)
                posicion = final.end()
                continue
        lista = _LISTA_RE.match(texto, desde_lista)
        if lista:
            siguiente = _item(texto, lista.end())
            if _continuacion_valida(texto, siguiente):
                crudos.append((siguiente, None))
                posicion = siguiente.end()
                continue
        break

    items: list[_Item] = []
    excedidos: list[tuple[int, int, int]] = []
    for inicio_item, final_item in crudos:
        if final_item is None:
            fraccion = (inicio_item.group("fraccion") or "").strip()
            items.append(_Item(_designacion(inicio_item), fraccion, inicio_item.end(),
                               _continuacion_no_extraida(texto, inicio_item)))
            continue
        a, b = int(inicio_item.group("num")), int(final_item.group("num"))
        if a < b and b - a + 1 <= MAX_RANGO:
            # Los extremos como se escribieron; los intermedios con el mismo ordinal si ambos
            # extremos lo comparten ("1º-5º" → 1º, 2º, … 5º), sin él en otro caso.
            marca = inicio_item.group("ord") or ""
            if marca != (final_item.group("ord") or ""):
                marca = ""
            numeros = (
                [_designacion(inicio_item)]
                + [f"{n}{marca}" for n in range(a + 1, b)]
                + [_designacion(final_item)]
            )
        else:   # rango invertido o demasiado largo: solo sus extremos
            numeros = [_designacion(inicio_item), _designacion(final_item)]
            if a < b:   # con o sin ordinales, lo no auditado queda como cobertura incompleta
                excedidos.append((a, b, b - a + 1))
        for numero in numeros:
            items.append(_Item(numero, "", final_item.end(),
                               _continuacion_no_extraida(texto, final_item)))
    return items, posicion, excedidos


def _cabezas(texto: str) -> list[re.Match]:
    """Cabezas de referencia; "numeral"/"precepto" tras otro número o una letra de apartado
    ("artículo 9, numeral 2", "apartado A, numeral 3") es un calificador, no una cabeza."""
    cabezas = []
    for cabeza in _CABEZA_RE.finditer(texto):
        palabra = sin_acentos(cabeza.group(0)).lower()
        if not palabra.startswith("art") and _CALIFICADOR_PREVIO_RE.search(
            texto, max(0, cabeza.start() - 40), cabeza.start()
        ):
            continue
        cabezas.append(cabeza)
    return cabezas


def _unidades(texto: str, cortes: _Cortes, menciones: _Menciones) -> list[_Unidad]:
    """Grupos (cabeza "artículo", "numeral", "precepto") divididos en segmentos, cada uno con
    su enlace derecho."""
    cabezas = _cabezas(texto)
    unidades: list[_Unidad] = []
    fin_anterior = -1
    grupo = -1
    for indice, cabeza in enumerate(cabezas):
        if cabeza.start() < fin_anterior:
            continue   # cabeza dentro del tramo de una enumeración ya leída
        grupo += 1
        oracion = cortes.oracion(cabeza.start(), cabeza.end())
        siguiente = next((c.start() for c in cabezas[indice + 1:] if c.start() >= cabeza.end()),
                         len(texto))
        tope = min(oracion[1], siguiente)
        # La enumeración de preceptos puede seguir tras un punto y coma (ronda 3).
        tope_frase = min(cortes.fin_frase(cabeza.end()), siguiente)
        leido = _leer_segmento(texto, cabeza.end(), continuacion=False)
        items, fin, excedidos = leido
        unidad = _Unidad(grupo, True, cabeza.start(), cabeza.start(), cabeza.end(), fin, items,
                         excedidos, oracion)
        while True:
            unidad.enlace = _enlace_derecho(texto, unidad.fin, tope, menciones)
            unidades.append(unidad)
            posicion = unidad.enlace.fin if unidad.enlace else unidad.fin
            fin_anterior = posicion
            continuacion = _CONTINUACION_RE.match(texto, posicion)
            tras_punto_y_coma = False
            if not continuacion or continuacion.end() >= tope:
                continuacion = _CONTINUACION_PYC_RE.match(texto, posicion)
                if not continuacion or continuacion.end() >= tope_frase:
                    break
                tras_punto_y_coma = True
            leido = _leer_segmento(texto, continuacion.end(), continuacion=True)
            if leido is None:
                break
            items, fin, excedidos = leido
            if tras_punto_y_coma:
                # "14 de la CPEUM; 42 del CFF": nueva oración, mismo grupo, pero solo si el
                # segmento trae su propia ley pegada (un número suelto tras ";" no es seguro).
                oracion = cortes.oracion(continuacion.end(), continuacion.end())
                tope = min(oracion[1], siguiente)
                if fin > tope or _enlace_derecho(texto, fin, tope, menciones) is None:
                    break
            elif fin > tope:
                break
            unidad = _Unidad(grupo, False, cabeza.start(), posicion, continuacion.end(), fin,
                             items, excedidos, oracion)
        # Números ligados a una ley que la enumeración no alcanzó (también tras un punto y
        # coma): cobertura incompleta, nunca una cita que desaparece.
        for numero in _NUMERO_RE.finditer(texto, fin_anterior, tope_frase):
            if numero.start() < fin_anterior or menciones.cubre(numero.start()):
                continue
            item = _item(texto, numero.start())
            if not _continuacion_valida(texto, item):
                continue
            enlace = _enlace_derecho(texto, item.end(), tope_frase, menciones)
            if enlace:
                unidad.huerfanos.append((_designacion(item), numero.start(), enlace.fin, enlace))
                fin_anterior = max(fin_anterior, enlace.fin)
    return unidades


def _resolver_enlace_simple(
    texto: str, unidad: _Unidad, catalogo: CatalogoLeyes, menciones: _Menciones, cortes: _Cortes
) -> Resolucion:
    return _resolver_elemento(
        texto, unidad.enlace.elementos[0], METODO_DERECHA, catalogo, menciones,
        unidad.cabeza, cortes,
    )


def _resolver_izquierda(
    texto: str, unidad: _Unidad, catalogo: CatalogoLeyes, menciones: _Menciones,
    cortes: _Cortes, reclamadas: set[tuple[int, int]],
) -> Optional[Resolucion]:
    """Ley a la izquierda de la cabeza: pegada ("La Ley de Amparo, en su artículo 16") o por
    posesivo con un único ordenamiento previo en la oración ("…, y en su artículo 217")."""
    s_ini = unidad.oracion[0]
    cabeza = unidad.cabeza
    candidatos = [
        e for e in menciones.elementos(max(s_ini, cabeza - VENTANA_IZQUIERDA), cabeza)
        if e.fin <= cabeza and e.tipo != "constitucional"
        and not (e.tipo == "explicita" and (e.mencion.inicio, e.mencion.fin) in reclamadas)
    ]
    if candidatos:
        cercano = max(candidatos, key=lambda e: (e.fin, -_PRIORIDAD[e.tipo]))
        if _es_brecha(texto[cercano.fin:cabeza], _ENLACE_IZQUIERDO):
            return _resolver_elemento(texto, cercano, METODO_IZQUIERDA, catalogo, menciones,
                                      cercano.inicio, cortes)
    if not _POSESIVO_RE.search(texto, s_ini, cabeza):
        return None
    poseedores = [e for e in candidatos if e.tipo != "generica"]
    if not poseedores:
        return None
    identidades = {
        e.mencion.fuente if e.tipo == "explicita" else "¿" + e.nombre for e in poseedores
    }
    if len(identidades) > 1:
        nombres = ", ".join(sorted({
            e.mencion.clave if e.tipo == "explicita" else e.nombre for e in poseedores
        }))
        return _no_identificada(
            f"el posesivo 'su artículo' es ambiguo: la oración nombra varios ordenamientos "
            f"({nombres})"
        )
    poseedor = max(poseedores, key=lambda e: e.fin)
    return _resolver_elemento(texto, poseedor, METODO_POSESIVO, catalogo, menciones,
                              poseedor.inicio, cortes)


def _resolver_previo(
    texto: str, unidad: _Unidad, menciones: _Menciones, cortes: _Cortes
) -> Resolucion:
    """Contexto previo: oraciones anteriores (nunca la misma oración ni hacia adelante)."""
    s_ini = unidad.oracion[0]
    previas = menciones.elementos(max(0, unidad.cabeza - VENTANA_PREVIA), s_ini)
    # Explícitas del mapa y nombres propios fuera del catálogo ("el Código de Comercio"): un
    # genérico en prosa con modificador ("la ley fiscal") no bloquea la inferencia.
    previas = [
        e for e in previas if e.fin <= s_ini and (
            (e.tipo == "explicita" and not e.mencion.alias)
            or (e.tipo == "concreta" and e.nombre[:1].isupper())
        )
    ]
    if not previas:
        return _no_identificada(MOTIVO_SIN_MENCION)
    cercana = max(previas, key=lambda e: (e.inicio, -_PRIORIDAD[e.tipo]))
    if cercana.tipo == "concreta":
        return _no_identificada(
            f"el ordenamiento nombrado antes es {_motivo_concreto(cercana.nombre)}"
        )
    # D10 (ronda 2): si la oración de la mención más cercana nombra más de un ordenamiento
    # ("La Ley de Amparo regula la jurisprudencia y la CPEUM fija sus bases. El artículo 217
    # …"), el contexto previo es ambiguo: la ley queda no identificada, no la última mención.
    comienzo, final = cortes.oracion(cercana.inicio, cercana.fin)
    en_la_oracion = [
        e for e in menciones.elementos(comienzo, final)
        if e.fin <= final and e.tipo in ("explicita", "concreta")
    ]
    identidades = {
        (e.mencion.fuente or "¿" + e.mencion.clave) if e.tipo == "explicita"
        else "¿" + sin_acentos(re.sub(r"\s+", " ", e.nombre)).lower()
        for e in en_la_oracion
    }
    if len(identidades) > 1:
        nombres = ", ".join(sorted({
            e.mencion.clave if e.tipo == "explicita" else e.nombre for e in en_la_oracion
        }))
        return _no_identificada(
            f"el contexto previo es ambiguo: la oración anterior nombra varios ordenamientos "
            f"({nombres})"
        )
    return _resolver_previa(texto, cercana.mencion, unidad.cabeza, cortes, METODO_PREVIO)


def _resolver_unidades(
    texto: str, unidades: list[_Unidad], catalogo: CatalogoLeyes, menciones: _Menciones,
    cortes: _Cortes,
) -> None:
    n = len(unidades)
    reclamadas: set[tuple[int, int]] = set()
    for u in unidades:
        if u.enlace:
            for e in u.enlace.elementos:
                if e.tipo == "explicita":
                    reclamadas.add((e.mencion.inicio, e.mencion.fin))

    # 0. Izquierda (por grupo): pegada a la cabeza o posesiva.
    izquierdas: dict[int, Optional[Resolucion]] = {}
    for u in unidades:
        if u.primera:
            izquierdas[u.grupo] = _resolver_izquierda(texto, u, catalogo, menciones, cortes,
                                                      reclamadas)

    # 1. Dueño del enlace derecho: la propia unidad o, por coordinación pura dentro de la
    #    oración, la siguiente que lo tenga ("el artículo 14 y el artículo 16 de la CPEUM").
    #    Un segmento cuyo grupo ya está ligado por la izquierda no toma la ley de otro.
    duenos: list[Optional[int]] = [None] * n
    for k in range(n - 1, -1, -1):
        u = unidades[k]
        if u.enlace:
            duenos[k] = k
            continue
        if izquierdas.get(u.grupo) is not None:
            continue
        if k + 1 < n and duenos[k + 1] is not None:
            siguiente = unidades[k + 1]
            dueno = unidades[duenos[k + 1]]
            permitidas = (_COORDINACION_DISTRIBUTIVA if dueno.enlace.compartido
                          else _COORDINACION)
            hasta = siguiente.inicio if siguiente.primera else siguiente.items_inicio
            if siguiente.inicio < u.oracion[1] and _es_brecha(texto[u.fin:hasta], permitidas):
                duenos[k] = duenos[k + 1]

    # 2. Resolución por la derecha (una ley, o varias repartidas con "respectivamente").
    for k, u in enumerate(unidades):
        if duenos[k] is None:
            continue
        dueno = unidades[duenos[k]]
        elementos = dueno.enlace.elementos
        if len(elementos) == 1 and not dueno.enlace.respectivamente:
            u.resolucion = _resolver_enlace_simple(texto, dueno, catalogo, menciones, cortes)
            continue
        miembros = [unidades[j] for j in range(n) if duenos[j] == duenos[k]]
        total = sum(len(m.items) for m in miembros)
        nombres = ", ".join(e.mencion.clave if e.tipo == "explicita" else e.nombre
                            for e in elementos)
        if not dueno.enlace.respectivamente or total != len(elementos):
            # Nunca la primera ley para todos: si el reparto no cuadra, el grupo queda sin ley.
            motivo = (
                f"'respectivamente' reparte {len(elementos)} ordenamiento(s) ({nombres}) "
                f"entre {total} artículo(s): no cuadra"
                if dueno.enlace.respectivamente
                else f"el grupo nombra varios ordenamientos ({nombres}) sin 'respectivamente': "
                     "no se sabe cuál corresponde a cada artículo"
            )
            u.resolucion = _no_identificada(motivo)
            continue
        posicion = sum(len(m.items) for m in miembros[:miembros.index(u)])
        u.por_item = [
            _resolver_elemento(texto, elementos[posicion + i], METODO_DERECHA, catalogo,
                               menciones, u.cabeza, cortes)
            for i in range(len(u.items))
        ]

    # 3. Izquierda: cubre los segmentos del grupo sin ley propia; si choca con la ley a la
    #    derecha del primer segmento, la ley queda no identificada.
    for k, u in enumerate(unidades):
        izquierda = izquierdas.get(u.grupo)
        if izquierda is None:
            continue
        if u.resolucion is None and u.por_item is None:
            u.resolucion = izquierda
        elif u.primera and duenos[k] == k:
            derechas = u.por_item or [u.resolucion]
            if any(_identidad(d) != _identidad(izquierda) for d in derechas):
                motivo = (
                    "vínculos en conflicto: a la izquierda "
                    f"'{izquierda.clave if izquierda.fuente else izquierda.motivo}' y a la "
                    "derecha "
                    + ", ".join(f"'{d.clave if d.fuente else d.motivo}'" for d in derechas)
                )
                u.resolucion, u.por_item = _no_identificada(motivo), None

    # 4. Coordinación con un grupo anterior ligado por la izquierda ("CFF Art. 42 y Art. 43").
    for k in range(1, n):
        u, anterior = unidades[k], unidades[k - 1]
        if u.resolucion is not None or u.por_item is not None:
            continue
        r = anterior.resolucion
        if (r is not None and r.metodo in (METODO_IZQUIERDA, METODO_POSESIVO)
                and u.inicio < anterior.oracion[1]
                and _es_brecha(texto[anterior.fin:u.inicio], _COORDINACION)):
            u.resolucion = r

    # 5. Contexto previo y, si no, ley no identificada.
    for u in unidades:
        if u.resolucion is None and u.por_item is None:
            u.resolucion = _resolver_previo(texto, u, menciones, cortes)


# ── Unidad citada (R4c, ronda 2) ───────────────────────────────────────────────────────
# Calificadores pegados al artículo que designan una unidad del precepto: "fracción I",
# "fracciones I y II", "párrafo segundo" / "segundo párrafo" / "párrafo 2°", "inciso a)",
# "apartado B", "in fine", "parte final", "base V", "numeral 3". La auditoría coteja la
# unidad en la evidencia: una cita de fracción no se acredita con el encabezado del artículo.
# Ajuste previo al commit: el punto de un ordinal ("artículo 1o., párrafo tercero") también
# separa el artículo de su unidad.
_SEP_UNIDAD = r"[\s,;().]*(?:(?:y|e)\s+)?"
_ROMANO_UNIDAD = r"(?-i:[IVXLC]+)(?![^\W\d_])"
_ORDINAL_SIMPLE = (
    r"primer[oa]?|segund[oa]|tercer[oa]?|cuart[oa]|quint[oa]|sext[oa]|s[eé]ptim[oa]"
    r"|octav[oa]|noven[oa]"
)
_ORDINAL_PARRAFO = (
    rf"(?:d[eé]cim[oa](?:\s+(?:{_ORDINAL_SIMPLE}))?|{_ORDINAL_SIMPLE}"
    r"|[uú]ltim[oa]|pen[uú]ltim[oa]"
    r"|\d{1,2}\s*(?:[°ºª]|[oa](?![^\W\d_])\.?)?)(?![^\W\d_])"
)
_UNIDADES_RE = (
    ("fraccion", re.compile(
        _SEP_UNIDAD + rf"fracciones\s+(?P<v>{_ROMANO_UNIDAD}(?:\s*(?:,\s*(?:y|e)?|y|e)\s*"
        rf"{_ROMANO_UNIDAD})*)", re.IGNORECASE)),
    ("fraccion", re.compile(
        _SEP_UNIDAD + _CLAVE_FRACCION + rf"\s*(?P<v>{_ROMANO_UNIDAD}|\d{{1,2}}(?!\d))\.?",
        re.IGNORECASE)),
    ("parrafo", re.compile(
        _SEP_UNIDAD + rf"(?:(?:p[aá]rrafos?|p[aá]rr\.)\s*(?P<v>{_ORDINAL_PARRAFO})"
        rf"|(?P<w>{_ORDINAL_PARRAFO})\s+p[aá]rrafos?(?![^\W\d_]))", re.IGNORECASE)),
    ("inciso", re.compile(
        _SEP_UNIDAD + r"(?:incisos?|inc\.)\s*(?P<v>[a-z])\)?(?![^\W\d_])", re.IGNORECASE)),
    ("apartado", re.compile(
        _SEP_UNIDAD + r"(?:apartados?|ap\.)\s*(?P<v>(?-i:[A-Z]))(?![^\W\d_])", re.IGNORECASE)),
    ("otra", re.compile(
        _SEP_UNIDAD + r"(?P<v>in\s+fine|parte\s+final|base\s+(?-i:[IVXLC]+)|numeral\s+\d+)"
        r"(?![^\W\d_])", re.IGNORECASE)),
)


# Unidad que PRECEDE al artículo: "párrafo tercero del artículo 1o.", "fracción II del
# artículo 31", "inciso a) de la fracción III del artículo 107", "último párrafo del artículo
# 16". La cadena de unidades (unidas por "de la"/"del") debe terminar pegada a la cabeza con
# "del"/"de la"/"de los": una unidad de otro contexto ("el 2o. párrafo de la sentencia …
# el artículo 16") o de una ley ("fracción II de la Ley de Amparo") no se asocia.
_UNIDAD_SUELTA = (
    rf"(?:fracci[oó]n(?:es)?\s+{_ROMANO_UNIDAD}(?:\s*(?:,\s*(?:y|e)?|y|e)\s*{_ROMANO_UNIDAD})*"
    rf"|fracc?\.\s*{_ROMANO_UNIDAD}"
    rf"|fr\.\s*{_ROMANO_UNIDAD}"
    rf"|(?:p[aá]rrafos?|p[aá]rr\.)\s*{_ORDINAL_PARRAFO}|{_ORDINAL_PARRAFO}\s+p[aá]rrafos?"
    r"|(?:incisos?|inc\.)\s*[a-z]\)?|(?:apartados?|ap\.)\s*(?-i:[A-Z])"
    rf"|in\s+fine|parte\s+final|base\s+{_ROMANO_UNIDAD}|numeral\s+\d+)(?![^\W\d_])"
)
_CONECTOR_UNIDAD = r"\s*,?\s*(?:de\s+la|del|de)\s+"
_CADENA_PREVIA_RE = re.compile(
    rf"(?<![^\W_])(?P<cadena>{_UNIDAD_SUELTA}(?:{_CONECTOR_UNIDAD}{_UNIDAD_SUELTA})*)"
    r"\s*,?\s*(?:de\s+los|de\s+la|del|de)\s*$",
    re.IGNORECASE,
)
_CONECTOR_UNIDAD_RE = re.compile(_CONECTOR_UNIDAD, re.IGNORECASE)


def unidades_previas(texto: str, cabeza: int) -> list[dict]:
    """Unidades citadas inmediatamente ANTES de la cabeza del artículo ("párrafo tercero
    del artículo 1o."). [] si la cabeza no está precedida por una cadena de unidades."""
    ventana_inicio = max(0, cabeza - 200)
    m = _CADENA_PREVIA_RE.search(texto, ventana_inicio, cabeza)
    if not m:
        return []
    return unidades_citadas(texto, m.start("cadena"), m.end("cadena"), conectores=True)


def unidades_citadas(
    texto: str, desde: int, hasta: int, *, conectores: bool = False
) -> list[dict]:
    """Unidades del precepto nombradas en ``texto[desde:hasta]`` justo tras el artículo
    (calificadores consecutivos; se detiene en la primera palabra que no lo es). Con
    ``conectores`` admite "de la"/"del" entre unidades (cadena previa al artículo)."""
    unidades: list[dict] = []
    posicion = desde
    while posicion < hasta:
        if conectores and unidades:
            conector = _CONECTOR_UNIDAD_RE.match(texto, posicion, hasta)
            if conector:
                posicion = conector.end()
        for tipo, patron in _UNIDADES_RE:
            m = patron.match(texto, posicion, hasta)
            if m and m.end() > posicion:
                break
        else:
            break
        valor = (m.group("v") if "w" not in patron.groupindex else (m.group("v") or m.group("w")))
        valor = re.sub(r"\s+", " ", valor.strip())
        if tipo == "fraccion" and re.search(r"[\s,]", valor):
            unidades.extend({"tipo": "fraccion", "valor": v}
                            for v in re.findall(r"[IVXLC]+", valor))
        else:
            unidades.append({"tipo": tipo, "valor": valor.lower() if tipo == "inciso" else valor})
        posicion = m.end()
    return unidades


def _unidad_del_item(texto: str, u: _Unidad, i: int, item: _Item) -> list[dict]:
    """Unidad citada de un artículo: la que precede a la cabeza ("párrafo tercero del
    artículo 1o.", para los artículos del primer segmento), su fracción pegada y, para el
    último del segmento, los calificadores entre él y su ley ("artículo 107, fracción V,
    inciso a), de la …")."""
    unidades = unidades_previas(texto, u.cabeza) if u.primera else []
    if item.fraccion.strip().rstrip(".,;"):
        unidades.append({"tipo": "fraccion", "valor": item.fraccion.strip().rstrip(".,;")})
    if i == len(u.items) - 1:
        if u.enlace:
            hasta = u.enlace.elementos[0].inicio
        else:
            # Sin ley a la derecha: hasta el fin de la oración o la siguiente cabeza.
            siguiente = _CABEZA_RE.search(texto, u.fin)
            hasta = min(u.oracion[1], u.fin + 160, len(texto),
                        siguiente.start() if siguiente else len(texto))
        unidades.extend(unidades_citadas(texto, u.fin, max(u.fin, hasta)))
    return unidades


def _referencia(
    texto: str, u: _Unidad, articulo: str, fraccion: str, fin_raw: int, r: Resolucion,
    group_raw: str, *, cobertura: Optional[str] = None, unidad: Optional[list[dict]] = None,
) -> dict:
    return {
        "type": "article",
        "article": articulo,
        "fraction": fraccion,
        "law": r.clave,
        "source_file": r.fuente,
        "law_inferred": r.inferida,
        "raw": texto[u.cabeza:fin_raw].strip(),
        "law_method": r.metodo,
        "law_unidentified_reason": r.motivo,
        "group_raw": group_raw,
        "law_requires_confirmation": r.confirmar,
        "coverage_gap": cobertura,
        # R4c (ronda 2): unidad del precepto citada ([] = el artículo completo).
        "unidad_citada": unidad or [],
    }


def extraer_articulos(texto: str, catalogo: CatalogoLeyes) -> list[dict]:
    """Referencias a artículos, una por artículo, con la ley resuelta de su segmento.

    Cada referencia conserva las claves de siempre (``type``, ``article``, ``fraction``,
    ``law``, ``source_file``, ``law_inferred``, ``raw``) y añade ``law_method``,
    ``law_unidentified_reason``, ``group_raw`` (el tramo completo de la enumeración),
    ``law_requires_confirmation`` (ley inferida de otro párrafo) y ``coverage_gap`` (motivo,
    solo en las referencias de COBERTURA INCOMPLETA: rangos recortados y números ligados a
    una ley que no se extrajeron con certeza).
    """
    texto = texto or ""
    if not _CABEZA_RE.search(texto):
        return []
    cortes = _Cortes(texto)
    menciones = _Menciones(texto, menciones_explicitas(texto, catalogo))
    unidades = _unidades(texto, cortes, menciones)
    _resolver_unidades(texto, unidades, catalogo, menciones, cortes)

    fin_grupo: dict[int, int] = {}   # ``group_raw``: de la cabeza al último artículo del grupo
    for u in unidades:
        fin_grupo[u.grupo] = max(fin_grupo.get(u.grupo, 0), u.fin)
    refs: list[dict] = []
    for u in unidades:
        group_raw = texto[u.cabeza:fin_grupo[u.grupo]].strip()
        for i, item in enumerate(u.items):
            r = u.por_item[i] if u.por_item else u.resolucion
            refs.append(_referencia(
                texto, u, item.articulo, item.fraccion, item.fin_raw, r, group_raw,
                unidad=_unidad_del_item(texto, u, i, item),
                # Ronda 2 (falla cerrada): designación que el texto continúa sin extraerse.
                cobertura=(
                    f"la designación continúa en el texto ('{item.incompleta}') y no se extrajo "
                    f"completa: no se audita como el artículo {item.articulo}"
                    if item.incompleta else None
                ),
            ))
        for a, b, total in u.excedidos:
            refs.append(_referencia(
                texto, u, f"{a + 1} a {b - 1}", "", u.fin, u.por_item[0] if u.por_item
                else u.resolucion, group_raw,
                cobertura=(
                    f"rango de {total} artículos ({a} a {b}): solo se auditaron los extremos; "
                    f"los {total - 2} intermedios no se auditaron"
                ),
            ))
        for articulo, inicio, fin, enlace in u.huerfanos:
            nombres = ", ".join(e.mencion.clave if e.tipo == "explicita" else e.nombre
                                for e in enlace.elementos)
            refs.append(_referencia(
                texto, u, articulo, "", fin, _no_identificada(
                    f"'{texto[inicio:fin].strip()}' parece un artículo ligado a '{nombres}', "
                    "pero no se extrajo con certeza de la enumeración"
                ), group_raw,
                cobertura=(
                    f"posible artículo {articulo} ('{texto[inicio:fin].strip()}') sin cabeza "
                    "'artículo' reconocible: no se auditó"
                ),
            ))
    return refs


def designaciones_articulo(texto: str, catalogo: Optional[CatalogoLeyes] = None) -> list[str]:
    """Designaciones citadas (con enumeraciones, segmentos y sufijos), sin repetir, en orden.
    Con el catálogo se leen también los segmentos tras una ley ("14 de la CPEUM y 42 …")."""
    texto = texto or ""
    vistos: list[str] = []
    if not _CABEZA_RE.search(texto):
        return vistos
    cortes = _Cortes(texto)
    menciones = _Menciones(texto, menciones_explicitas(texto, catalogo or CatalogoLeyes(())))
    for u in _unidades(texto, cortes, menciones):
        for item in u.items:
            if item.articulo not in vistos:
                vistos.append(item.articulo)
    return vistos
