"""Extractor determinista de menciones verificables (regla PL-014 de cobertura).

Reconoce tres tipos de mención en un documento:

* **Registros digitales** — ``registro digital: 2006224``, ``Registro 2006224``,
  ``reg. 2006224``, ``IUS 2006224`` (6 a 8 dígitos, sin distinguir mayúsculas).
* **Claves de tesis** — ``P./J. 20/2014``, ``1a./J. 68/2022``, aisladas de la SCJN
  (``2a. XXI/2014``), Plenos Regionales y de Circuito (``PR.A.CS. J/1 A``,
  ``PC.III.P. J/12 P``) y jurisprudencia de TCC (``I.3o.C. J/12``). Se conservan
  la letra de materia y la época: ``PR.A.CS. J/1 P (11a.)`` ≠ ``PR.A.CS. J/1 A (11a.)``.
* **Artículos** — con límite de palabra (``apart. 3`` y ``Smart 5`` no cuentan),
  enumeraciones (``artículos 14, 16 y 17`` → 14, 16 y 17), sufijos
  ``bis``/``ter``/``quáter``/``quinquies``… (``art. 19 Ter`` ≠ ``art. 19``) y el
  ordenamiento si aparece a la derecha (≤ 40 caracteres) con una sigla o nombre del
  diccionario ``LEYES`` (``art. 19 CNPP`` ≠ ``art. 19 CPEUM``).

Cobertura: una mención del documento queda cubierta por una mención de una
afirmación con el mismo tipo y clave si cada calificador que trae el documento
(ordenamiento, materia, época) coincide. Lo que el documento no especifica no se
exige: ``art. 19`` sin ley lo cubre cualquier ``art. 19``; si nadie lo cubre, el
hallazgo se marca como ambiguo.

Es independiente de ``ARTICLE_RE`` de ``OpenNotebook.py`` a propósito (ese patrón
tiene defectos conocidos y pertenece al pipeline VVCA).

Limitaciones conocidas: solo se reconoce el ordenamiento escrito a la derecha del
artículo (no ``la Ley de Amparo, en su artículo 217``) y solo las leyes del
diccionario; no se expanden rangos (``artículos 14 a 17``); una enumeración se corta
en ``fracción`` o ``párrafo``; no se reconocen artículos escritos con letra.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

ARTICULO = "articulo"
REGISTRO = "registro"
CLAVE = "clave"

VENTANA_LEY = 40


@dataclass(frozen=True)
class Mencion:
    """Mención localizada en un texto.

    ``clave`` es la forma base que se compara (``art. 19 ter``, ``registro 2006224``,
    ``pr.a.cs. j/1``). Los calificadores ``ley`` (artículos), ``materia`` y ``epoca``
    (claves de tesis) se comparan aparte para decidir la cobertura.
    """

    tipo: str
    clave: str
    epoca: str | None
    original: str
    linea: int
    materia: str | None = None
    ley: str | None = None

    @property
    def calificadores(self) -> tuple[str | None, str | None, str | None]:
        return (self.ley, self.materia, self.epoca)

    @property
    def ambigua(self) -> bool:
        """Artículo sin ordenamiento identificable."""
        return self.tipo == ARTICULO and self.ley is None

    @property
    def normalizada(self) -> str:
        if self.tipo == ARTICULO:
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
    "LA": (("LA",), ("ley de amparo",)),
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
    r"(?:\s*[°º]\.?|o(?![a-z0-9])\.?)?"
    rf"(?:\s*[-‐-–]?\s*(?P<suf>{_SUFIJOS})(?![a-z]))?"
)
_ARTICULO_RE = re.compile(
    r"(?<!\w)(?:articulos?|arts?\.?)\s*" + _NUM_ARTICULO, re.IGNORECASE
)
_CONTINUACION_RE = re.compile(
    r"(?:\s*,\s*(?:(?:y|e)\s+)?|\s+(?:y|e)\s+)" + _NUM_ARTICULO, re.IGNORECASE
)
# Un número tras una coma seguido de una unidad no es artículo:
# "artículo 471, 3 días" no menciona el artículo 3.
_UNIDAD_RE = re.compile(
    r"\s*(?:dias?|mes(?:es)?|anos?|horas?|semanas?|%|por\s+ciento)(?![a-z])",
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


def _clave_articulo(coincidencia: re.Match) -> str:
    numero = str(int(coincidencia.group("num")))
    sufijo = coincidencia.group("suf")
    return f"art. {numero} {sufijo.lower()}" if sufijo else f"art. {numero}"


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

    for cabeza in _ARTICULO_RE.finditer(norma):
        inicio = cabeza.start()
        numeros = [(inicio, cabeza)]
        posicion = cabeza.end()
        while True:
            continuacion = _CONTINUACION_RE.match(norma, posicion)
            if not continuacion or _UNIDAD_RE.match(norma, continuacion.end()):
                break
            numeros.append((continuacion.start("num"), continuacion))
            posicion = continuacion.end()
        # El ordenamiento escrito tras la enumeración aplica a todos sus artículos.
        ley = _ley_a_la_derecha(norma, posicion)
        for lugar, coincidencia in numeros:
            encontradas.append(
                (
                    lugar,
                    Mencion(
                        ARTICULO,
                        _clave_articulo(coincidencia),
                        None,
                        original(inicio, coincidencia.end()),
                        _linea(norma, inicio),
                        ley=ley,
                    ),
                )
            )

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
