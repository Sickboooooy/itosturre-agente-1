"""Extractor determinista de menciones verificables (regla PL-014 de cobertura).

Reconoce tres tipos de mención en un documento:

* **Registros digitales** — ``registro digital: 2006224``, ``Registro 2006224``,
  ``reg. 2006224``, ``IUS 2006224`` (6 a 8 dígitos, sin distinguir mayúsculas).
* **Claves de tesis** — ``P./J. 20/2014``, ``1a./J. 68/2022``, aisladas de la SCJN
  (``2a. XXI/2014``), Plenos Regionales y de Circuito (``PR.A.CS. J/1 A``,
  ``PC.III.P. J/12 P``) y jurisprudencia de TCC (``I.3o.C. J/12``). Se conservan
  la letra de materia y la época: ``PR.A.CS. J/1 P (11a.)`` ≠ ``PR.A.CS. J/1 A (11a.)``.
* **Artículos** — con límite de palabra (``apart. 3`` y ``Smart 5`` no cuentan),
  enumeraciones (``artículos 14, 16 y 17`` → 14, 16 y 17), rangos (``arts. 105,
  108-112 y 114`` → 105, 108, 109, 110, 111, 112 y 114), sufijos
  ``bis``/``ter``/``quáter``/``quinquies``… (``art. 19 Ter`` ≠ ``art. 19``) y el
  ordenamiento si aparece a la derecha (≤ 40 caracteres) con una sigla o nombre del
  diccionario ``LEYES`` (``art. 19 CNPP`` ≠ ``art. 19 CPEUM``).
* **Citas "SIGLA número"** (piloto PEN-01, D4) — ``CNPP 167``, ``CFF 113 Bis``,
  ``CPEUM 1º``, ``LAmp 217``: la sigla del diccionario ``LEYES`` seguida del número del
  artículo, sin "art.", es una mención de ese artículo **de esa ley**. Para no confundir
  siglas ni números que no son artículos: solo siglas del diccionario (``DOF``, ``SAT`` o
  ``IUS`` nunca cuentan) y nunca ``LA`` (es también el artículo "la" en mayúsculas: usar
  ``LAmp``); de 1 a 3 dígitos (``CFF 2026`` es un año); nunca una fecha (``CNPP
  28-11-2025``), un monto o decimal (``CFF 1,500``, ``CFF 10.5``), una fracción (``LGS
  3/2019``), un número seguido de unidad o de mes (``CNPP 3 días``, ``CPEUM 19 de
  junio``), una letra pegada (``LA 1A.``) ni un número precedido de "folio", "oficio",
  "expediente", "número"… Admite enumeraciones y rangos como la forma con "art.".
* **Letra del artículo** (ronda 2) — ``29-A`` y ``4o.-A`` (mayúscula pegada al guion) son
  otros artículos: ``art. 29-A`` ≠ ``art. 29``, en ambas formas. Cada número de una
  enumeración o extremo de rango pasa la misma validación que el primero (fecha, unidad,
  decimal, miles, letra suelta): "CFF 28, 29-A y 30" da tres menciones y "CFF 28, 10.5"
  solo una.

Rangos (PEN-01 D5): el contrato es el del VVCA (``itosturre/audit/referencias.py``): se
expanden hasta ``MAX_RANGO`` artículos (el mismo valor; una prueba lo comprueba); uno
mayor conserva sus extremos y deja una mención ``RANGO`` de **cobertura incompleta**
con los intermedios (nunca desaparecen en silencio); un rango invertido conserva sus
extremos. Solo entre números simples (sin sufijo) y nunca si el extremo final va
seguido de una unidad ("16 a 20 días").

Cobertura: una mención del documento queda cubierta por una mención de una
afirmación con el mismo tipo y clave si cada calificador que trae el documento
(ordenamiento, materia, época) coincide. Lo que el documento no especifica no se
exige: ``art. 19`` sin ley lo cubre cualquier ``art. 19``; si nadie lo cubre, el
hallazgo se marca como ambiguo. Una mención ``RANGO`` solo la cubre el mismo rango.

Es independiente de ``ARTICLE_RE`` de ``OpenNotebook.py`` a propósito (ese patrón
tiene defectos conocidos y pertenece al pipeline VVCA).

Limitaciones conocidas: solo se reconoce el ordenamiento escrito a la derecha del
artículo o la sigla pegada a su izquierda ("CNPP 167"), no ``la Ley de Amparo, en su
artículo 217`` ni ``CPEUM art. 19`` (decisión pendiente del responsable), y solo las
leyes del diccionario; una enumeración se corta en ``fracción``, ``párrafo`` o ``;``
("CFF 108; 92 fr. I" solo da el 108); no se reconocen artículos escritos con letra.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

ARTICULO = "articulo"
REGISTRO = "registro"
CLAVE = "clave"
# Intermedios de un rango de más de ``MAX_RANGO`` artículos: cobertura incompleta.
RANGO = "rango"

VENTANA_LEY = 40
# Tope de expansión de un rango: mismo contrato que el VVCA
# (``itosturre.audit.referencias.MAX_RANGO``). No se importa de ``audit`` para no crear
# la dependencia plan → audit (D2); una prueba comprueba que los dos valores coinciden.
MAX_RANGO = 20


@dataclass(frozen=True)
class Mencion:
    """Mención localizada en un texto.

    ``clave`` es la forma base que se compara (``art. 19 ter``, ``registro 2006224``,
    ``pr.a.cs. j/1``, ``arts. 2 a 99``). Los calificadores ``ley`` (artículos y rangos),
    ``materia`` y ``epoca`` (claves de tesis) se comparan aparte para decidir la
    cobertura. ``detalle`` explica una mención ``RANGO`` (cobertura incompleta).
    """

    tipo: str
    clave: str
    epoca: str | None
    original: str
    linea: int
    materia: str | None = None
    ley: str | None = None
    detalle: str | None = None
    # Índice en el texto original donde empieza la cita (la cabeza de su enumeración):
    # permite leer qué la precede ("remite al art. …"). No se compara para la cobertura.
    posicion: int | None = None

    @property
    def calificadores(self) -> tuple[str | None, str | None, str | None]:
        return (self.ley, self.materia, self.epoca)

    @property
    def ambigua(self) -> bool:
        """Artículo (o rango) sin ordenamiento identificable."""
        return self.tipo in (ARTICULO, RANGO) and self.ley is None

    @property
    def normalizada(self) -> str:
        if self.tipo in (ARTICULO, RANGO):
            return f"{self.clave} {self.ley}" if self.ley else self.clave
        if self.tipo == CLAVE:
            texto = self.clave
            if self.materia:
                texto += f" {self.materia.lower()}"
            if self.epoca:
                texto += f" ({self.epoca}a.)"
            return texto
        return self.clave


def _normalizar_con_mapa(texto: str) -> tuple[str, list[int]]:
    """NFD sin diacríticos y, para cada carácter resultante, su índice en el original."""
    salida: list[str] = []
    mapa: list[int] = []
    for indice, caracter in enumerate(texto or ""):
        for parte in unicodedata.normalize("NFD", caracter):
            if unicodedata.category(parte) != "Mn":
                salida.append(parte)
                mapa.append(indice)
    return "".join(salida), mapa


def normalizar_texto(texto: str) -> str:
    """NFD sin marcas diacríticas, conservando mayúsculas y saltos de línea."""
    return _normalizar_con_mapa(texto)[0]


# ── Ordenamientos ────────────────────────────────────────────────────────────
# Siglas: sensibles a mayúsculas. Nombres: sin acentos ni mayúsculas.
LEYES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "CPEUM": (
        ("CPEUM",),
        (
            "constitucion politica de los estados unidos mexicanos",
            "constitucion federal",
            "constitucional",
        ),
    ),
    "CNPP": (("CNPP",), ("codigo nacional de procedimientos penales",)),
    "CPF": (("CPF",), ("codigo penal federal",)),
    "CFF": (("CFF",), ("codigo fiscal de la federacion",)),
    # "LAmp": abreviatura del archivo de LeyesBiblio, usual en la cita "LAmp 217".
    "LA": (("LA", "LAmp"), ("ley de amparo",)),
    "LNEP": (("LNEP",), ("ley nacional de ejecucion penal",)),
    "LNMASCMP": (
        ("LNMASCMP",),
        (
            "ley nacional de mecanismos alternativos de solucion de controversias "
            "en materia penal",
        ),
    ),
    "LFDO": (("LFDO", "LFCDO"), ("ley federal contra la delincuencia organizada",)),
    "LGS": (("LGS",), ("ley general de salud",)),
    "CADH": (
        ("CADH",),
        ("convencion americana sobre derechos humanos", "convencion americana"),
    ),
}


def _patron_sigla(sigla: str) -> str:
    # "LA" solo cuenta como Ley de Amparo si no la sigue otra palabra en mayúsculas:
    # en "ARTÍCULO 19 DE LA CONSTITUCIÓN" es un artículo determinado.
    cola = r"(?![ \t]+[A-Z])" if sigla == "LA" else ""
    return rf"(?<![A-Za-z]){re.escape(sigla)}(?![A-Za-z]){cola}"


def _patron_nombre(nombre: str) -> str:
    return r"(?<![a-z])" + r"\s+".join(map(re.escape, nombre.split())) + r"(?![a-z])"


_LEY_PATRONES = tuple(
    (
        ley,
        re.compile("|".join(_patron_sigla(s) for s in siglas)),
        re.compile("|".join(_patron_nombre(n) for n in nombres), re.IGNORECASE),
    )
    for ley, (siglas, nombres) in LEYES.items()
)
# El ordenamiento no se busca más allá de un salto de línea, un punto y coma o el
# final de una oración.
_CORTE_RE = re.compile(r"\n|;|\.\s+(?=[A-Z])")


# ── Artículos ────────────────────────────────────────────────────────────────
_SUFIJOS = "bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies"
_NUM_ARTICULO = (
    r"(?P<num>\d{1,4})(?![\d/])"
    r"(?P<ord>\s*[°º]\.?|o(?![a-z0-9])\.?)?"
    # Letra pegada al guion y en mayúscula ("29-A", "4o.-A"): otro artículo, no el 29 ni
    # el 4 (ronda 2, D4). Con espacio ("1o.- A quien…") o en minúscula es texto.
    r"(?P<letra>\.?[-‐‑–](?-i:[A-Z])(?![A-Za-z])(?!\)))?"
    rf"(?:\s*[-‐-–]?\s*(?P<suf>{_SUFIJOS})(?![a-z]))?"
)
_ARTICULO_RE = re.compile(
    r"(?<!\w)(?:articulos?|arts?\.?)\s*" + _NUM_ARTICULO, re.IGNORECASE
)
_CONTINUACION_RE = re.compile(
    r"(?:\s*,\s*(?:(?:y|e)\s+)?|\s+(?:y|e)\s+)" + _NUM_ARTICULO, re.IGNORECASE
)
_ITEM_RE = re.compile(_NUM_ARTICULO, re.IGNORECASE)
# Rango entre dos números: "108-112", "155–157", "467 a 471", "19 al 21" (como el VVCA).
_RANGO_RE = re.compile(r"\s*(?:[-‐‑–—]|\s(?:a|al)\s)\s*(?=\d)", re.IGNORECASE)
_MESES = (
    "enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|"
    "noviembre|diciembre"
)
# Un número seguido de una unidad o de un mes no es artículo: "artículo 471, 3 días" no
# menciona el artículo 3, ni "CPEUM 19 de junio" el 19 (misma lista que el VVCA).
_UNIDAD_RE = re.compile(
    r"\s*(?:dias?|mes(?:es)?|anos?|horas?|semanas?|veces|fojas?|%|por\s+ciento"
    rf"|de\s+(?:{_MESES}))(?![a-z])",
    re.IGNORECASE,
)
# Una fecha numérica ("28-11-2025", "01/04/2025") nunca es un artículo ni un rango.
_FECHA_NUMERICA_RE = re.compile(r"\d{1,2}[-/.‐‑–]\d{1,2}[-/.‐‑–]\d{2,4}(?!\d)")
# Un ordinal seguido de "párrafo", "fracción"… es un adjetivo ("2o. párrafo"), no un
# artículo (como el VVCA). Solo se aplica a continuaciones y a la forma "SIGLA número".
_ORDINAL_ADJETIVO_RE = re.compile(
    r"\.?\s*(?:parrafo|fraccion|apartado|inciso|base|numeral)", re.IGNORECASE
)

# ── Citas "SIGLA número" (PEN-01 D4) ────────────────────────────────────────────────
# "LA" no: en mayúsculas también es el artículo "la" ("DE LA 2A. SALA").
_SIGLAS_CORTAS = {
    sigla: ley for ley, (siglas, _) in LEYES.items() for sigla in siglas if sigla != "LA"
}
_SIGLA_NUMERO_RE = re.compile(
    r"(?<![A-Za-z0-9])(?P<sigla>"
    + "|".join(re.escape(s) for s in sorted(_SIGLAS_CORTAS, key=len, reverse=True))
    + r")[ \t" + chr(0xA0) + r"]+(?=\d)"  # espacio, tabulador o espacio duro (U+00A0)
)
_DIGITOS_SIGLA = 3  # "CFF 2026" es un año: ninguna ley del diccionario llega a 1000 artículos
# Tras cada número de una cita "SIGLA número" y de cada continuación o extremo de rango:
# nada de letras pegadas ("1A.", "2a."), decimales o miles ("10.5", "1,500") ni una letra
# tras el guion que no sea la de un artículo con letra ("29-a", "29- A"). La letra en
# mayúscula pegada al guion ("29-A") ya la consumió el número: es otro artículo.
_COLA_INVALIDA = re.compile(r"[A-Za-z]|[.,]\d|\.?[-‐‑–]\s?[A-Za-z](?![A-Za-z])")
# Palabras que, justo antes de la sigla, convierten el número en folio, oficio o número.
_PREVIO_NO_ARTICULO = re.compile(
    r"(?:\bfolios?|\boficios?|\bexpedientes?|\bexp\.|\bnumeros?|\bnum\.|\bno\.|\bclaves?"
    r"|\btomos?|\blibros?|\bpaginas?|\bpag\.)\s*:?\s*$",
    re.IGNORECASE,
)

# ── Registros digitales ──────────────────────────────────────────────────────
_REGISTRO_RE = re.compile(
    r"(?<!\w)(?:registros?(?:\s+digital(?:es)?)?(?:\s+ius)?|reg\.|ius)"
    r"\s*(?:(?:no|num|numero)\.?\s*)?[:#.]?\s*(?P<num>\d{6,8})(?!\d)",
    re.IGNORECASE,
)

# ── Claves de tesis ──────────────────────────────────────────────────────────
# Letra(s) de materia opcional ("J/1 A (11a.)") —solo si las sigue la época, un signo
# de puntuación o el fin de línea, para no confundir "J/1 A la fecha"— y época opcional.
_SUFIJO_CLAVE = (
    r"(?:\s+(?P<materia>[A-Z]{1,2})(?=\s*\(|[ \t]*[.,;:)\]]|[ \t]*(?:\n|$)))?"
    r"(?:\s*\(\s*(?P<epoca>\d{1,2})\s*[aA]\.?\s*\))?"
)
_CLAVE_RES = (
    # Jurisprudencia SCJN: P./J. 20/2014, 1a./J. 68/2022
    re.compile(
        r"(?<![\w.])(?P<pre>P|[12][aA])\.\s*/\s*J\.\s*(?P<num>\d{1,4})\s*/\s*"
        r"(?P<anio>\d{4})(?!\d)" + _SUFIJO_CLAVE
    ),
    # Tesis aislada SCJN: P. XXI/2014, 2a. CCLXX/2015
    re.compile(
        r"(?<![\w.])(?P<pre>P|[12][aA])\.\s+(?P<num>[IVXLCDM]{1,12})\s*/\s*"
        r"(?P<anio>\d{4})(?!\d)" + _SUFIJO_CLAVE
    ),
    # Plenos Regionales y de Circuito: PR.A.CS. J/1 A, PC.III.P. J/12 P
    re.compile(
        r"(?<![\w.])(?P<pre>P[RC]\.(?:[A-Z]{1,6}\.)+)\s*J\s*/\s*(?P<num>\d{1,4})(?!\d)"
        + _SUFIJO_CLAVE
    ),
    # Jurisprudencia de TCC: I.3o.C. J/12, XVII.1o.P.A. J/9, XXII.P.A. J/2
    re.compile(
        r"(?<![\w.(])(?P<pre>[IVXLC]{1,6}\.(?:\d{1,2}o\.)?(?:[A-Z]{1,3}\.){1,3})"
        r"\s*J\s*/\s*(?P<num>\d{1,4})(?!\d)" + _SUFIJO_CLAVE
    ),
)


def _linea(texto: str, posicion: int) -> int:
    return texto.count("\n", 0, posicion) + 1


def _ley_a_la_derecha(norma: str, anclaje: int) -> str | None:
    """Ordenamiento que empieza a ≤ ``VENTANA_LEY`` caracteres a la derecha del artículo.

    La ventana se corta en un salto de línea, un punto y coma, un fin de oración o la
    siguiente mención de artículo (para no robarle su ley).
    """
    limite = anclaje + VENTANA_LEY
    corte = _CORTE_RE.search(norma, anclaje, limite + 1)
    if corte:
        limite = min(limite, corte.start())
    siguiente = _ARTICULO_RE.search(norma, anclaje, limite + 1)
    if siguiente:
        limite = min(limite, siguiente.start())
    fin_busqueda = limite + 120  # deja terminar nombres largos que empiezan en la ventana
    mejor: tuple[int, str] | None = None
    for ley, siglas, nombres in _LEY_PATRONES:
        for patron in (siglas, nombres):
            coincidencia = patron.search(norma, anclaje, fin_busqueda)
            if coincidencia and coincidencia.start() <= limite:
                if mejor is None or coincidencia.start() < mejor[0]:
                    mejor = (coincidencia.start(), ley)
    return mejor[1] if mejor else None


# Nombres que solo identifican un ordenamiento pegados a un artículo ("19 constitucional"):
# sueltos en el texto no lo nombran ("control constitucional").
_NOMBRES_CONTEXTUALES = frozenset({"constitucional"})
_LEY_PATRONES_LIBRES = tuple(
    (
        ley,
        re.compile("|".join(_patron_sigla(s) for s in siglas)),
        re.compile(
            "|".join(_patron_nombre(n) for n in nombres if n not in _NOMBRES_CONTEXTUALES),
            re.IGNORECASE,
        ),
    )
    for ley, (siglas, nombres) in LEYES.items()
)


# Palabra genérica de un ordenamiento; seguida de un nombre propio ("Código Civil del
# Estado de Jalisco", "Ley General contra la Extorsión") es una denominación concreta.
_GENERICO_ORDENAMIENTO = re.compile(
    r"\b(?:codigos?|leyes|ley|constitucion|reglamentos?|decretos?|estatutos?|convencion|pacto|"
    r"tratados?)\b",
    re.IGNORECASE,
)
_PALABRA = re.compile(r"[ \t]+([^\W\d_]+)")
_CONECTORES_NOMBRE = frozenset({"de", "del", "la", "las", "los", "el", "para", "sobre", "contra", "en", "y"})


@dataclass(frozen=True)
class OrdenamientosDelTexto:
    """Ordenamientos que un texto nombra: siglas de ``LEYES`` (sigla o nombre, en orden) y
    denominaciones concretas que no son del diccionario (``ajenos``, texto sin acentos)."""

    reconocidos: tuple[str, ...]
    ajenos: tuple[str, ...]
    # Tramos (inicio, fin) de los reconocidos en ``normalizar_texto(texto)``.
    tramos: tuple[tuple[int, int], ...] = ()


def ordenamientos_del_texto(texto: str) -> OrdenamientosDelTexto:
    """Ordenamientos nombrados en cualquier parte del texto (PEN-01 D3, ronda 2).

    Para las afirmaciones sobre un documento entero (el encabezado de un compilado), que
    nombran la ley sin citar un artículo ("CPEUM: última reforma…"). "constitucional" suelto
    no cuenta. Una palabra genérica ("Código", "Ley"…) fuera de un nombre del diccionario y
    seguida de un nombre propio es un ordenamiento **ajeno** al catálogo: su identidad no se
    puede acreditar con la cabecera de otro.
    """
    norma = normalizar_texto(texto or "")
    tramos: list[tuple[int, int]] = []
    encontradas: list[tuple[int, str]] = []
    for ley, siglas, nombres in _LEY_PATRONES_LIBRES:
        for patron in (siglas, nombres):
            if not patron.pattern:
                continue
            for coincidencia in patron.finditer(norma):
                tramos.append((coincidencia.start(), coincidencia.end()))
                encontradas.append((coincidencia.start(), ley))
    ajenos: list[str] = []
    for generico in _GENERICO_ORDENAMIENTO.finditer(norma):
        if any(inicio <= generico.start() < fin for inicio, fin in tramos):
            continue
        posicion, fin_nombre = generico.end(), None
        for _ in range(4):  # conectores y, después, el nombre propio
            palabra = _PALABRA.match(norma, posicion)
            if not palabra:
                break
            posicion = palabra.end()
            if palabra.group(1)[0].isupper():
                fin_nombre = posicion
                break
            if palabra.group(1).lower() not in _CONECTORES_NOMBRE:
                break
        if fin_nombre is not None:
            while (palabra := _PALABRA.match(norma, fin_nombre)) and (
                palabra.group(1)[0].isupper() or palabra.group(1).lower() in _CONECTORES_NOMBRE
            ):
                fin_nombre = palabra.end()
            ajenos.append(norma[generico.start():fin_nombre].strip())
    return OrdenamientosDelTexto(
        tuple(dict.fromkeys(ley for _, ley in sorted(encontradas))),
        tuple(dict.fromkeys(ajenos)),
        tuple(sorted(tramos)),
    )


def ordenamientos_mencionados(texto: str) -> list[str]:
    """Siglas de ``LEYES`` que el texto nombra en cualquier parte (sigla o nombre), en orden."""
    return list(ordenamientos_del_texto(texto).reconocidos)


def _clave_articulo(coincidencia: re.Match) -> str:
    """``art. 29``, ``art. 29-A``, ``art. 113 bis``, ``art. 32-B quater``: el número, la
    letra (si la trae) y el sufijo latino; el ordinal no distingue ("1" y "1o.")."""
    clave = f"art. {int(coincidencia.group('num'))}"
    if coincidencia.group("letra"):
        clave += f"-{coincidencia.group('letra')[-1].upper()}"
    if coincidencia.group("suf"):
        clave += f" {coincidencia.group('suf').lower()}"
    return clave


def _simple(coincidencia: re.Match) -> bool:
    """Sin letra ni sufijo latino: solo los números simples forman rangos."""
    return not (coincidencia.group("letra") or coincidencia.group("suf"))


@dataclass(frozen=True)
class _Articulo:
    """Un artículo leído de una enumeración: posición, clave y fin del tramo citado."""

    lugar: int
    clave: str
    fin: int


@dataclass(frozen=True)
class _RangoLargo:
    """Rango de más de ``MAX_RANGO`` artículos: solo se extraen sus extremos."""

    lugar: int
    desde: int
    hasta: int
    fin: int


def _item_valido(norma: str, item: re.Match | None, max_digitos: int | None) -> bool:
    """¿El número de una continuación, de un extremo de rango o de una cita "SIGLA número" es
    un artículo? No si es una fecha, si lo sigue una unidad o un mes, si excede
    ``max_digitos`` (forma "SIGLA número") o si lo sigue una cola inválida (letra pegada,
    decimal, miles o letra tras el guion que no es la de un artículo con letra). La
    validación se aplica a **cada** número, no solo al primero (ronda 2, D4)."""
    if item is None:
        return False
    if max_digitos is not None and len(item.group("num")) > max_digitos:
        return False
    if _FECHA_NUMERICA_RE.match(norma, item.start("num")):
        return False
    if item.group("ord") and _ORDINAL_ADJETIVO_RE.match(norma, item.end("ord")):
        return False
    if _COLA_INVALIDA.match(norma, item.end()):
        return False
    return not _UNIDAD_RE.match(norma, item.end())


def _leer_enumeracion(
    norma: str, primero: re.Match, *, max_digitos: int | None = None
) -> tuple[list[_Articulo], list[_RangoLargo], int]:
    """Artículos de una enumeración que empieza en ``primero`` (", N", " y N" y rangos).

    Devuelve los artículos, los rangos demasiado largos y el fin de la enumeración. Un
    rango (PEN-01 D5) solo une números simples y se expande hasta ``MAX_RANGO``; uno mayor
    conserva sus extremos y queda en la lista de rangos largos (cobertura incompleta).
    """
    articulos = [_Articulo(primero.start("num"), _clave_articulo(primero), primero.end())]
    largos: list[_RangoLargo] = []
    anterior = primero
    en_rango = False  # el anterior ya cerró un rango ("108-112-115" no encadena)
    posicion = primero.end()
    while True:
        rango = _RANGO_RE.match(norma, posicion)
        if (rango and not en_rango and _simple(anterior)
                and not _FECHA_NUMERICA_RE.match(norma, anterior.start("num"))):
            final = _ITEM_RE.match(norma, rango.end())
            if _item_valido(norma, final, max_digitos) and _simple(final):
                a, b = int(anterior.group("num")), int(final.group("num"))
                if a < b and b - a + 1 <= MAX_RANGO:
                    # Los intermedios comparten el tramo del extremo final (como el VVCA).
                    articulos += [_Articulo(final.start("num"), f"art. {n}", final.end())
                                  for n in range(a + 1, b)]
                elif a < b:
                    largos.append(_RangoLargo(anterior.start("num"), a, b, final.end()))
                articulos.append(_Articulo(final.start("num"), _clave_articulo(final), final.end()))
                anterior, en_rango, posicion = final, True, final.end()
                continue
        continuacion = _CONTINUACION_RE.match(norma, posicion)
        if continuacion and _item_valido(norma, continuacion, max_digitos):
            articulos.append(
                _Articulo(continuacion.start("num"), _clave_articulo(continuacion), continuacion.end())
            )
            anterior, en_rango, posicion = continuacion, False, continuacion.end()
            continue
        return articulos, largos, posicion


def _sigla_numero(norma: str, coincidencia: re.Match) -> re.Match | None:
    """Primer número de una cita "SIGLA número" si lo es (``None`` si no: ver el módulo)."""
    if _PREVIO_NO_ARTICULO.search(norma, max(0, coincidencia.start() - 24), coincidencia.start()):
        return None
    item = _ITEM_RE.match(norma, coincidencia.end())
    return item if _item_valido(norma, item, _DIGITOS_SIGLA) else None


def _clave_tesis(coincidencia: re.Match) -> str:
    prefijo = re.sub(r"\s+", "", coincidencia.group("pre")).lower()
    numero = coincidencia.group("num")
    grupos = coincidencia.groupdict()
    if grupos.get("anio"):
        if numero.isdigit():  # jurisprudencia SCJN
            return f"{prefijo}./j. {int(numero)}/{grupos['anio']}"
        return f"{prefijo}. {numero.lower()}/{grupos['anio']}"  # aislada SCJN
    return f"{prefijo} j/{int(numero)}"


def extraer_menciones(texto: str) -> list[Mencion]:
    """Extrae artículos, registros digitales y claves de tesis, en orden de aparición.

    La comparación se hace sobre el texto sin acentos, pero ``Mencion.original``
    conserva el fragmento tal como aparece (con acentos) para el reporte.
    """
    texto = texto or ""
    norma, mapa = _normalizar_con_mapa(texto)
    encontradas: list[tuple[int, Mencion]] = []

    def original(inicio: int, fin: int) -> str:
        if fin <= inicio:
            return ""
        return texto[mapa[inicio] : mapa[fin - 1] + 1].strip()

    def agregar_articulos(inicio: int, articulos: list[_Articulo], largos: list[_RangoLargo],
                          ley: str | None) -> None:
        linea = _linea(norma, inicio)
        posicion = mapa[inicio] if inicio < len(mapa) else None
        for articulo in articulos:
            encontradas.append(
                (articulo.lugar,
                 Mencion(ARTICULO, articulo.clave, None, original(inicio, articulo.fin), linea, ley=ley,
                         posicion=posicion))
            )
        for rango in largos:
            total = rango.hasta - rango.desde + 1
            encontradas.append((rango.lugar, Mencion(
                RANGO, f"arts. {rango.desde + 1} a {rango.hasta - 1}", None,
                original(inicio, rango.fin), linea, ley=ley,
                detalle=(f"rango de {total} artículos ({rango.desde} a {rango.hasta}): solo se "
                         f"extraen los extremos; los {total - 2} intermedios no se cubren "
                         "(cobertura incompleta)"),
                posicion=posicion,
            )))

    tramos: list[tuple[int, int]] = []  # tramos ya leídos con "art.": la sigla no los repite
    for cabeza in _ARTICULO_RE.finditer(norma):
        articulos, largos, posicion = _leer_enumeracion(norma, cabeza)
        # El ordenamiento escrito tras la enumeración aplica a todos sus artículos.
        agregar_articulos(cabeza.start(), articulos, largos, _ley_a_la_derecha(norma, posicion))
        tramos.append((cabeza.start(), posicion))

    # Citas "SIGLA número" (PEN-01 D4): la ley es la sigla, a la izquierda del número.
    for sigla in _SIGLA_NUMERO_RE.finditer(norma):
        if any(inicio <= sigla.start() < fin for inicio, fin in tramos):
            continue
        primero = _sigla_numero(norma, sigla)
        if primero is None:
            continue
        articulos, largos, posicion = _leer_enumeracion(norma, primero, max_digitos=_DIGITOS_SIGLA)
        agregar_articulos(sigla.start(), articulos, largos, _SIGLAS_CORTAS[sigla.group("sigla")])
        tramos.append((sigla.start(), posicion))

    for coincidencia in _REGISTRO_RE.finditer(norma):
        encontradas.append(
            (
                coincidencia.start(),
                Mencion(
                    REGISTRO,
                    f"registro {int(coincidencia.group('num'))}",
                    None,
                    original(coincidencia.start(), coincidencia.end()),
                    _linea(norma, coincidencia.start()),
                ),
            )
        )

    for patron in _CLAVE_RES:
        for coincidencia in patron.finditer(norma):
            epoca = coincidencia.group("epoca")
            materia = coincidencia.group("materia")
            encontradas.append(
                (
                    coincidencia.start(),
                    Mencion(
                        CLAVE,
                        _clave_tesis(coincidencia),
                        str(int(epoca)) if epoca else None,
                        original(coincidencia.start(), coincidencia.end()),
                        _linea(norma, coincidencia.start()),
                        materia=materia.upper() if materia else None,
                    ),
                )
            )

    encontradas.sort(key=lambda par: par[0])
    return [mencion for _, mencion in encontradas]


IndiceCobertura = dict[tuple[str, str], set[tuple[str | None, str | None, str | None]]]


def indice_cobertura(textos: Iterable[str]) -> IndiceCobertura:
    """Índice ``(tipo, clave) → {(ley, materia, época)}`` de referencias y textos."""
    indice: IndiceCobertura = {}
    for texto in textos:
        for mencion in extraer_menciones(texto):
            indice.setdefault((mencion.tipo, mencion.clave), set()).add(mencion.calificadores)
    return indice


def esta_cubierta(mencion: Mencion, indice: IndiceCobertura) -> bool:
    """``True`` si alguna afirmación cubre la mención.

    Cada calificador que trae la mención (ordenamiento, materia, época) debe coincidir;
    los que no trae no se exigen.
    """
    for calificadores in indice.get((mencion.tipo, mencion.clave), ()):
        if all(
            propio is None or propio == ajeno
            for propio, ajeno in zip(mencion.calificadores, calificadores)
        ):
            return True
    return False
