"""Validaciones puras de evidencia normativa recuperada del corpus."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from .referencias import (
    patron_articulo,
    patron_designacion_cualquiera,
    patron_latinos,
    patron_variante_con_sufijo,
)


def _without_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


# Línea con forma de encabezado: "Artículo 42.", "Artículo 38.-", "Art. 1004-A.-".
# Ronda 2 de la re-ingesta (4-oct-2026) — Encabezado PARTIDO entre líneas: "ARTICULO\n508.-"
# (CFPC), "Artículo\n367.-" (LFPPI), "Artículo\n341." y "Artículo\n9." (reglamentos de
# movilidad). Solo si "Artículo"/"ARTÍCULO" queda SOLO al final de su línea y la siguiente
# empieza con la designación y su cierre (el cierre se exige siempre en esta forma; una
# remisión en minúscula no es auténtica).
_SEPARADOR_MISMA_LINEA = r"[ \t]+"
_SEPARADOR_PARTIDO = r"[ \t]*\n[ \t]*"
_PREFIJO_ENCABEZADO = (
    rf"^[ \t]*art(?:iculo)?\.?(?:{_SEPARADOR_MISMA_LINEA}|{_SEPARADOR_PARTIDO})"
)
_CIERRE_ENCABEZADO = r"[ \t]*(?:\.\-|[.\-:])"
# Ordinales (3-oct-2026, ronda 2) — Sufijo partido entre líneas: "Artículo 1o.\nBis.- …" o
# "Artículo 1o.\n-A.- …" son el encabezado del 1o Bis o del 1o-A, no del 1o. Solo un sufijo
# latino o "-Letra", con su cierre, al inicio de la línea siguiente; nunca una letra suelta:
# "Artículo 26.\nA. El Estado…", "Artículo 37.\nA) Ningún…" o "Artículo 185.\nA efecto de…"
# (apartados, incisos o texto) siguen siendo el encabezado del 26, el 37 o el 185.
_LATINOS_EN_LINEA = patron_latinos(r"[ \t]")   # fuera de la f-string (Python 3.11)
_SUFIJO_EN_LINEA_SIGUIENTE = (
    rf"[ \t]*\n[ \t]*(?:-[ \t]*[A-Za-z]|{_LATINOS_EN_LINEA})(?![^\W\d_])"
    rf"{_CIERRE_ENCABEZADO}"
)
# Ronda 2 — Encabezado AUTÉNTICO: con "A" mayúscula ("Artículo", "ARTÍCULO", "Art.") y un
# cierre que no sigue con "," ni ";". "artículo 41." que el PDF dejó al inicio de una línea es
# una remisión (el chunker la toma por encabezado y etiqueta el fragmento con el 41), y
# "Artículo 2o., fracción I, inciso H." una cita capitalizada: ninguna acredita el precepto.
_SIGUE_REMISION = re.compile(r"[ \t]*[,;]")


# Línea anterior que deja abierta la oración (11-oct-2026, Código Civil de Jalisco): "…la parte
# final del" / "Artículo 1595." es una remisión partida, no un encabezado. Misma lista que
# ``itosturre.evidencia.leyesbiblio._ABRE_ORACION`` (D2: ``audit`` no importa esa capa).
_ABRE_ORACION = re.compile(
    r"(?:,|(?<![^\W_])(?:de|del|al|a|el|la|los|las|lo|y|e|o|u|en|por|para|con|sin|que|segun"
    r"|conforme|sobre|entre|hasta|desde|como))[ \t]*$",
    re.IGNORECASE,
)


def _remision_partida(normalizado: str, inicio: int) -> bool:
    """¿La línea con contenido anterior a ``inicio`` deja abierta la oración? Sin línea anterior
    (inicio del texto o del fragmento) no hay remisión que descartar."""
    previo = normalizado[:inicio].rstrip()
    return bool(previo) and bool(_ABRE_ORACION.search(previo.rsplit("\n", 1)[-1]))


def _es_autentico(normalizado: str, inicio: int, fin: int) -> bool:
    """¿El encabezado ``normalizado[inicio:fin]`` (texto sin acentos, terminado en su cierre)
    es AUTÉNTICO? "A" mayúscula en el prefijo, cierre no seguido de "," ni ";", y la línea
    anterior no deja abierta la oración (remisión partida, 11-oct-2026).

    Definición ÚNICA (re-ingesta por fuente, 4-oct-2026): la usan ``ocurrencias_encabezado``
    (el encabezado exacto que acredita un precepto) y ``encabezados_autenticos`` (con el que la
    ingesta corta y etiqueta los fragmentos), para que lo que la ingesta toma por encabezado y
    lo que la auditoría acepta como tal no diverjan."""
    return (
        normalizado[inicio:fin].lstrip()[:1] == "A"
        and not _SIGUE_REMISION.match(normalizado, fin)
        and not _remision_partida(normalizado, inicio)
    )


# Re-ingesta por fuente (4-oct-2026) — Encabezado auténtico de CUALQUIER artículo, para cortar
# y etiquetar la ingesta: el prefijo y el cierre de ``_encabezado_exacto`` con la designación
# genérica de ``patron_designacion_cualquiera`` (misma gramática que ``patron_articulo``), o
# bien la designación sola al final de su línea (grupo ``cierre`` vacío): los tratados (PIDCP,
# CADH, CDN) escriben "Artículo 51" / "ARTÍCULO 51" solo en su línea, sin cierre.
# Ronda 2: también el encabezado partido entre líneas (grupo ``partido``), que EXIGE el cierre
# (condición en la propia expresión, para que nunca se quede con la forma "fin de línea").
_ENCABEZADO_CUALQUIERA = re.compile(
    rf"^[ \t]*art(?:iculo)?\.?(?:{_SEPARADOR_MISMA_LINEA}|(?P<partido>{_SEPARADOR_PARTIDO}))"
    rf"(?P<designacion>{patron_designacion_cualquiera()})"
    rf"(?(partido)(?P<cierre_partido>{_CIERRE_ENCABEZADO})"
    rf"|(?:(?P<cierre>{_CIERRE_ENCABEZADO})|[ \t]*$))",
    re.IGNORECASE | re.MULTILINE,
)
# Primera línea con contenido tras un encabezado al final de su línea: si empieza con
# minúscula, "," o ";", la línea "Artículo 51" es el corte de una oración ("conforme al
# Artículo 51\nde esta Ley…"), no un encabezado.
_CONTINUA_ORACION = re.compile(r"\s*[,;a-z]")

FORMA_CIERRE = "cierre"
FORMA_FIN_DE_LINEA = "fin_de_linea"


# ─────────────────────────────────────────
# TRATADOS INTERNACIONALES (criterio del responsable jurídico, 4-oct-2026, opción A)
# ─────────────────────────────────────────
# El encabezado "Artículo N" / "ARTÍCULO N" / "Artículo Nº" SOLO al final de su línea, sin
# punto ni guion (``FORMA_FIN_DE_LINEA``), es auténtico ÚNICAMENTE en los tratados
# internacionales que el CATÁLOGO registra (``OpenNotebook.TRATADOS_INTERNACIONALES``; nunca
# por el nombre del archivo): la CADH, la CDN y el PIDCP del corpus no cierran sus
# encabezados. Las leyes nacionales siguen exigiendo el cierre. La auditoría activa esta forma
# con ``fin_de_linea=True`` según la fuente esperada (selección de evidencia, ubicación en el
# cuerpo, cuerpo del precepto, cotejo de la unidad y existencia en D10); por omisión, nada
# cambia. Es la misma forma que ya admitía la ingesta (``encabezados_autenticos``) y con la
# misma salvaguarda (``_fin_de_linea_autentico``).

def _fin_de_linea_autentico(normalizado: str, inicio: int, fin: int) -> bool:
    """¿La designación sola al final de su línea (``normalizado[inicio:fin]``, texto sin
    acentos, sin cierre) es un encabezado AUTÉNTICO? "A" mayúscula en el prefijo y la siguiente
    línea con contenido no continúa una oración (minúscula, "," o ";"). Definición ÚNICA de la
    forma de los tratados: la usan la ingesta (``encabezados_autenticos``) y la auditoría
    (``ocurrencias_encabezado`` con ``fin_de_linea=True``). El prefijo y la designación van en
    la misma línea: el encabezado partido ("Artículo\\n51") exige el cierre."""
    return (
        normalizado[inicio:fin].lstrip()[:1] == "A"
        and not _CONTINUA_ORACION.match(normalizado, fin)
    )


def encabezados_autenticos(texto: str, *, fin_de_linea: bool = False) -> list[dict[str, Any]]:
    """Encabezados AUTÉNTICOS de cualquier artículo en ``texto``, en su orden: ``inicio`` y
    ``fin`` (posiciones del texto SIN acentos; el inicio es el de su línea), ``designacion``
    (sin acentos, espacios normalizados: "4o.-A", "247 Bis", "1º") y ``forma``.

    Con cierre (``FORMA_CIERRE``) rige ``_es_autentico``, la misma definición que
    ``ocurrencias_encabezado``: "ARTICULO 496.-", "Artículo 1o.-", "Artículo 75.Quedan…" y
    "Artículo 26." (con "A. El Estado…" en la línea siguiente) lo son; "artículo 41." (remisión
    en minúscula), "Artículo 2o., fracción I" (cita) y "Artículo 51 de esta Ley…" (sin cierre)
    no. ``fin_de_linea=True`` admite además la designación sola al final de su línea con "A"
    mayúscula (``FORMA_FIN_DE_LINEA``: "Artículo 51", "ARTÍCULO 1"), salvo que la siguiente
    línea con contenido continúe una oración (minúscula, "," o ";"): ``_fin_de_linea_autentico``.
    La ingesta la admite en todo documento; la auditoría solo en los tratados internacionales
    registrados (4-oct-2026; en las leyes exige el cierre). Ronda 2: el encabezado partido entre
    líneas ("ARTICULO\n508.-") cuenta, con cierre, para ambas."""
    normalizado = _without_accents(texto)
    hallados: list[dict[str, Any]] = []
    for m in _ENCABEZADO_CUALQUIERA.finditer(normalizado):
        if m.group("cierre") is not None or m.group("cierre_partido") is not None:
            if not _es_autentico(normalizado, m.start(), m.end()):
                continue
            forma = FORMA_CIERRE
        else:
            if (
                not fin_de_linea
                or m.group("partido") is not None
                or not _fin_de_linea_autentico(normalizado, m.start(), m.end())
            ):
                continue
            forma = FORMA_FIN_DE_LINEA
        hallados.append({
            "inicio": m.start(),
            "fin": m.end(),
            "designacion": " ".join(m.group("designacion").split()),
            "forma": forma,
        })
    return hallados


def _patron_literal(article: str) -> str | None:
    """Designación no descomponible: el texto literal (comportamiento anterior a R4b)."""
    normalized_article = " ".join(_without_accents(article).strip().split())
    if not normalized_article:
        return None
    return re.escape(normalized_article).replace(r"\ ", r"[ \t]+")


def has_exact_article_heading(
    text: str, article: str, *, ordinal_literal: bool = False, fin_de_linea: bool = False
) -> bool:
    """Indica si ``text`` contiene el encabezado del artículo solicitado.

    Una remisión como ``artículo 42, fracción XIII`` no cuenta. Para acreditar la
    identidad del fragmento se exige una línea con forma de encabezado, por ejemplo
    ``Artículo 42.``, ``Artículo 38.-`` o ``Art. 1004-A.-``.

    Tras el número solo cabe el cierre del encabezado (R4-D06): ``Artículo 4o.-A.-`` no es
    el encabezado del artículo ``4o``, ni ``Artículo 29-B.`` el del ``29``, ni
    ``Artículo 209 Bis.-`` el del ``209``. Un sufijo de letra o latino solo coincide si se
    pidió (``4o.-A``, ``29-B``, ``209 Bis``).

    Ordinales (3-oct-2026): el ordinal se compara por equivalencia (``patron_articulo`` con
    ``ordinal_equivalente=True``): ``Artículo 1o.``, ``Artículo 1º`` y ``Artículo 1.`` son el
    encabezado del ``1`` y del ``1o``; nunca del ``10`` ni del ``11``, y ``Artículo 1o.-A.-``
    sigue sin ser el del ``1``, tampoco con el sufijo en la línea siguiente (``Artículo
    1o.\\nBis.-``). Antes se comparaba el ordinal tal como se pidió ("CPEUM Art. 1." no veía
    "Artículo 1o."); ``ordinal_literal=True`` conserva esa comparación. La caja del prefijo no
    se exige aquí (D10 no cambia): el encabezado AUTÉNTICO lo distingue
    ``ocurrencias_encabezado``.

    Tratados (4-oct-2026): ``fin_de_linea=True`` (fuente esperada registrada como tratado
    internacional) admite además "Artículo 8º" / "ARTÍCULO 8" solo al final de su línea, pero
    solo si es auténtico (``_fin_de_linea_autentico``): esa forma nunca cuenta como remisión.
    """
    return bool(_coincidencias(text, article, ordinal_literal=ordinal_literal,
                               fin_de_linea=fin_de_linea)[1])


def _patron_designacion(article: str, *, ordinal_literal: bool = False) -> str | None:
    return (
        patron_articulo(article, ordinal_equivalente=not ordinal_literal)
        or _patron_literal(article)
    )


def _encabezado_exacto(article: str, *, ordinal_literal: bool = False) -> re.Pattern | None:
    article_pattern = _patron_designacion(article, ordinal_literal=ordinal_literal)
    if not article_pattern:
        return None
    return re.compile(
        rf"{_PREFIJO_ENCABEZADO}{article_pattern}{_CIERRE_ENCABEZADO}"
        rf"(?!{_SUFIJO_EN_LINEA_SIGUIENTE})",
        re.IGNORECASE | re.MULTILINE,
    )


def _encabezado_fin_de_linea(article: str, *, ordinal_literal: bool = False) -> re.Pattern | None:
    """Tratados (4-oct-2026): el encabezado del artículo solo al final de su línea, sin cierre
    ("Artículo 8º", "ARTÍCULO 8"): prefijo y designación en la MISMA línea (como la forma
    ``FORMA_FIN_DE_LINEA`` de ``_ENCABEZADO_CUALQUIERA``) y, como el encabezado con cierre, sin
    un sufijo en la línea siguiente ("Artículo 1\\nBis.-" no es el del 1). Si es auténtico lo
    decide ``_fin_de_linea_autentico``."""
    article_pattern = _patron_designacion(article, ordinal_literal=ordinal_literal)
    if not article_pattern:
        return None
    return re.compile(
        rf"^[ \t]*art(?:iculo)?\.?{_SEPARADOR_MISMA_LINEA}{article_pattern}[ \t]*$"
        rf"(?!{_SUFIJO_EN_LINEA_SIGUIENTE})",
        re.IGNORECASE | re.MULTILINE,
    )


def _coincidencias(
    text: str, article: str, *, ordinal_literal: bool = False, fin_de_linea: bool = False
) -> tuple[str, list[tuple[int, int, str]]]:
    """Texto sin acentos y cada encabezado exacto del artículo en él, en orden: (inicio, fin,
    forma). Con cierre (``FORMA_CIERRE``), auténtico o no; sin cierre (``FORMA_FIN_DE_LINEA``,
    solo con ``fin_de_linea=True``), únicamente el auténtico."""
    normalizado = _without_accents(text)
    heading = _encabezado_exacto(article, ordinal_literal=ordinal_literal)
    if heading is None:
        return normalizado, []
    hallados = [(m.start(), m.end(), FORMA_CIERRE) for m in heading.finditer(normalizado)]
    if fin_de_linea:
        sin_cierre = _encabezado_fin_de_linea(article, ordinal_literal=ordinal_literal)
        hallados += [
            (m.start(), m.end(), FORMA_FIN_DE_LINEA) for m in sin_cierre.finditer(normalizado)
            if _fin_de_linea_autentico(normalizado, m.start(), m.end())
        ]
        hallados.sort()
    return normalizado, hallados


def ocurrencias_encabezado(
    text: str, article: str, *, fin_de_linea: bool = False
) -> list[dict[str, Any]]:
    """Cada encabezado exacto del artículo en ``text`` (sin acentos): ``inicio``, ``fin``, si
    es AUTÉNTICO (ronda 2): "A" mayúscula en el prefijo y cierre no seguido de "," ni ";", y
    ``forma`` (``FORMA_CIERRE`` o, en un tratado, ``FORMA_FIN_DE_LINEA``; campo añadido el
    4-oct-2026). Las posiciones son del texto sin acentos (las mismas que usa
    ``reconstruir_cuerpo``). La autenticidad la deciden ``_es_autentico`` y, con
    ``fin_de_linea=True``, ``_fin_de_linea_autentico``: las mismas definiciones con que la
    ingesta corta y etiqueta (``encabezados_autenticos``)."""
    normalizado, hallados = _coincidencias(text, article, fin_de_linea=fin_de_linea)
    return [
        {
            "inicio": inicio,
            "fin": fin,
            "autentico": forma == FORMA_FIN_DE_LINEA or _es_autentico(normalizado, inicio, fin),
            "forma": forma,
        }
        for inicio, fin, forma in hallados
    ]


def encabezado_autentico(text: str, article: str, *, fin_de_linea: bool = False) -> bool:
    """¿``text`` trae un encabezado AUTÉNTICO del artículo (no una remisión)? Ronda 2.
    ``fin_de_linea``: fuente registrada como tratado internacional (4-oct-2026)."""
    return any(
        o["autentico"] for o in ocurrencias_encabezado(text, article, fin_de_linea=fin_de_linea)
    )


# ─────────────────────────────────────────
# R4c — CUERPO DEL PRECEPTO, DEROGACIÓN Y UNIDAD CITADA
# ─────────────────────────────────────────
# Todo opera sobre texto SIN acentos (como ``has_exact_article_heading``).

# Encabezado de CUALQUIER artículo, para cortar el cuerpo del precepto citado: "Artículo"
# con mayúscula inicial, número (con ordinal y sufijo) y cierre ("Artículo 43.-",
# "ARTÍCULO 69.", "Artículo 2o.-B."). Una remisión que el PDF dejó al inicio de una línea
# ("artículo 42, fracción XIII", "Artículo 42 de esta Ley") no corta: va en minúscula o
# sin cierre. R4-D10: el grupo ``designacion`` (número, ordinal y sufijos) no cambia qué se
# reconoce; lo usa ``itosturre.audit.inexistencia`` para ordenar los encabezados del cuerpo.
# Ronda 2 de la re-ingesta (4-oct-2026): la designación es la de la gramática única
# (``patron_designacion_cualquiera``: subnúmero "58-1", "65 Bis 1", sufijos latinos más allá de
# "decies") y el prefijo admite el encabezado partido entre líneas ("ARTICULO\n508.-").
_ENCABEZADO_SIGUIENTE = re.compile(
    rf"^[ \t]*(?-i:A)rt(?:iculo)?\.?(?:{_SEPARADOR_MISMA_LINEA}|{_SEPARADOR_PARTIDO})"
    rf"(?P<designacion>{patron_designacion_cualquiera()})"
    r"[ \t]*(?:\.\-|\.(?=\s)|\.$|-(?=\s)|:)",
    re.IGNORECASE | re.MULTILINE,
)

# Frontera del cuerpo: la línea "TRANSITORIOS" / "ARTÍCULOS TRANSITORIOS" (con o sin ":" o
# "."; también "… DE DECRETOS DE REFORMA"). Mismo criterio que
# ``itosturre.evidencia.leyesbiblio.es_frontera_transitorios`` (D2: ``audit`` no importa la
# capa de evidencia; una prueba compara ambas). Ronda 2 de la re-ingesta: vive aquí (antes en
# ``inexistencia``, que la reexporta) para que el cuerpo del precepto se detenga en ella.
_FRONTERA_RE = re.compile(r"^(?:articulos? )?transitorios?(?: de decretos de reforma)?$")


def es_frontera_transitorios(linea: str) -> bool:
    """True si la línea es el título "TRANSITORIOS" (o "ARTÍCULOS TRANSITORIOS")."""
    normalizada = " ".join(_without_accents(linea or "").casefold().split()).rstrip(":. ")
    return bool(_FRONTERA_RE.match(normalizada))


# Tratados (4-oct-2026, ronda 2) — En un tratado el cuerpo se detiene ante CUALQUIER línea
# candidata a encabezado, auténtica o no: "Artículo"/"ARTÍCULO"/"Art." con mayúscula inicial y
# un número en la misma línea o en la siguiente ("Artículo 9º", "Artículo 9 de…", el partido
# "Artículo⏎9"). Una remisión en minúscula al inicio de línea ("artículo 48.") no corta.
_CANDIDATO_TRATADO = re.compile(
    r"^[ \t]*(?-i:A)rt(?:iculos?|s)?\.?[ \t]*(?:\n[ \t]*)?\d", re.IGNORECASE | re.MULTILINE
)


def _siguiente_encabezado(texto: str, fin_de_linea: bool = False) -> int | None:
    """Inicio del encabezado de otro artículo en ``texto`` (sin acentos), o None. En un tratado
    (``fin_de_linea``, 4-oct-2026) también el auténtico sin cierre ("Artículo 9º" solo en su
    línea), con la definición única de ``encabezados_autenticos``, y desde la ronda 2 cualquier
    línea candidata (``_CANDIDATO_TRATADO``), aunque no se autentique."""
    siguiente = _ENCABEZADO_SIGUIENTE.search(texto)
    posicion = siguiente.start() if siguiente else None
    if fin_de_linea:
        sin_cierre = next(
            (h["inicio"] for h in encabezados_autenticos(texto, fin_de_linea=True)
             if h["forma"] == FORMA_FIN_DE_LINEA),
            None,
        )
        candidato = _CANDIDATO_TRATADO.search(texto)
        for otra in (sin_cierre, candidato.start() if candidato else None):
            if otra is not None and (posicion is None or otra < posicion):
                posicion = otra
    return posicion


def _corte_del_cuerpo(texto: str, fin_de_linea: bool = False) -> int | None:
    """Dónde termina el cuerpo de un precepto en ``texto`` (lo que sigue a su encabezado): el
    encabezado de otro artículo o, ronda 2 de la re-ingesta (4-oct-2026), la línea
    TRANSITORIOS, la que llegue antes. Así una fracción de un transitorio ("ARTÍCULO
    PRIMERO.-\nI. …") nunca se toma como fracción del último artículo del cuerpo. En un tratado
    (``fin_de_linea``) el siguiente encabezado puede no llevar cierre."""
    siguiente = _siguiente_encabezado(texto, fin_de_linea)
    tope = siguiente if siguiente is not None else len(texto)
    posicion = 0
    for linea in texto[:tope].split("\n"):
        if posicion and es_frontera_transitorios(linea):
            return posicion
        posicion += len(linea) + 1
    return siguiente


# Tratados (4-oct-2026) — Línea de TÍTULO tras el encabezado ("Artículo 1º ⏎ Obligación de
# Respetar los Derechos ⏎ 1. Los Estados…", CADH): la línea que sigue de inmediato a un
# encabezado sin texto en su línea, corta, sin puntuación final y con todas sus palabras con
# mayúscula inicial salvo los conectores. No es cuerpo: sin descontarla, un encabezado con
# título y sin texto ("Artículo 8º ⏎ Garantías Judiciales" al final del fragmento) pasaría por
# un cuerpo suficiente. Una fórmula de derogación nunca es título.
_CONECTORES_TITULO = frozenset({
    "a", "al", "ante", "con", "contra", "de", "del", "e", "el", "en", "entre", "la", "las",
    "los", "o", "para", "por", "sin", "sobre", "u", "y",
})
# Ronda 2: también con líneas en blanco entre el encabezado y el título ("Artículo 1º ⏎ ⏎
# Obligación de Respetar los Derechos").
_LINEA_TRAS_ENCABEZADO = re.compile(r"[ \t]*\n(?:[ \t]*\n)*([^\n]*)")
MAX_TITULO = 80


def _es_titulo(linea: str) -> bool:
    palabras = linea.split()
    if not palabras or len(linea) > MAX_TITULO or linea[-1] in ".:;,":
        return False
    if _DEROGACION_AMBIGUA.match(linea):
        return False
    if not palabras[0][:1].isupper():
        return False
    return all(
        re.fullmatch(r"[^\W\d_]+", palabra)
        and (palabra[:1].isupper() or palabra.lower() in _CONECTORES_TITULO)
        for palabra in palabras
    )


def _inicio_tras_titulo(normalizado: str, fin: int) -> int:
    """Inicio del cuerpo de un tratado tras su encabezado (``fin``): tras la línea de título si
    la sigue de inmediato (``_es_titulo``); si no, ``fin``."""
    m = _LINEA_TRAS_ENCABEZADO.match(normalizado, fin)
    if m and _es_titulo(m.group(1).strip()):
        return m.end(1)
    return fin


def cuerpo_suficiente_tratado(cuerpo: str) -> bool:
    """Suficiencia del cuerpo de un TRATADO (ronda 2, adjudicado): un título solo nunca completa
    la evidencia, aunque ``_es_titulo`` no lo reconozca (no es la única salvaguarda). La primera
    línea con contenido que no termina en puntuación de cierre (".", ":", ";", ")") se separa de
    forma conservadora como posible título, y el resto debe bastar (``cuerpo_suficiente``).
    Una fórmula de derogación es contenido completo, como en las leyes."""
    if clasificar_derogacion(cuerpo):
        return True
    lineas = [
        linea.strip() for linea in _without_accents(cuerpo or "").split("\n")
        if linea.strip() and not _RUIDO_PAGINA.match(linea.strip())
    ]
    if lineas and not re.search(r"[.:;)]$", lineas[0]):
        lineas = lineas[1:]
    return cuerpo_suficiente("\n".join(lineas))


# Prefijo que la ingesta inyecta en los subfragmentos de un precepto largo ("[LEY 42]").
_PREFIJO_SUBFRAGMENTO = re.compile(r"\A\s*\[[^\]\n]*\][ \t]*\n?")
# Ruido de página que el PDF intercala entre el encabezado y su texto: cabeceras de la
# Cámara de Diputados, "Última Reforma DOF …", "127 de 380", la denominación de la ley en
# mayúsculas o el prefijo de subfragmento. Nunca una línea con "derog".
_RUIDO_PAGINA = re.compile(
    r"^(?!.*derog)(?:camara de diputados\b.*|secretaria general|secretaria de servicios "
    r"parlamentarios|ultima reforma\b.*|\d+\s+de\s+\d+|\[[^\]]*\]"
    r"|(?-i:[A-Z0-9][A-Z0-9 ,.;\-]{10,}))$",
    re.IGNORECASE,
)

# R4c (R4-D08, ronda 2) — Fórmulas INEQUÍVOCAS de derogación del precepto (o de la unidad
# citada): la primera línea con contenido tras el encabezado es SOLO la fórmula, con o sin
# paréntesis, punto dentro o fuera, en cualquier caja y en singular o plural: "(Se deroga).",
# "(Se deroga.)", "Se deroga", "Se derogan.", "DEROGADO.", "(Derogada)", "(DEROGADO, P.O. 5
# DE SEPTIEMBRE DE 2009)". Puede seguirla, en la misma línea, la nota de reforma ("Artículo
# derogado DOF …").
_NOTA_REFORMA = (
    r"(?:(?:articulo|fraccion|parrafo|inciso|apartado|base)\s+"
    r"(?:derogad|reformad|adicionad)\w*\b.*)?"
)
_DEROGACION_PLENA = re.compile(
    r"^(?:\(\s*(?:se\s+derogan?|derogad[oa]s?)\s*(?:,[^)\n]*)?\.?\s*\)\s*\.?"
    r"|(?:se\s+derogan?|derogad[oa]s?)\s*\.?)\s*" + _NOTA_REFORMA + r"$",
    re.IGNORECASE,
)
# Fórmula de derogación junto al encabezado que NO es inequívoca ("(Se deroga primer
# párrafo).", "Se derogan los artículos …", "(Derogado por …"): 🟡, nunca se ignora.
_DEROGACION_AMBIGUA = re.compile(r"^\(?\s*(?:se\s+derog|derogad)", re.IGNORECASE)

DEROGADO = "derogado"
DEROGACION_AMBIGUA = "ambigua"

# Unidades del precepto que se cotejan en el texto: fracción (romano al inicio de línea:
# "I.", "II.-", "III)") e inciso ("a)"). Párrafo, apartado, base, "in fine"… no se pueden
# ubicar con certeza en el texto extraído del PDF y nunca se dan por cotejados.
_MARCA_FRACCION = re.compile(
    r"^[ \t]*(?P<valor>(?-i:[IVXLC]+))[ \t]*(?:\.-|\.|-|\))", re.MULTILINE
)
_MARCA_INCISO = re.compile(r"^[ \t]*(?P<valor>(?-i:[a-z]))\)", re.MULTILINE)
# Tratados (4-oct-2026) — Párrafo numerado ("artículo 8.1", "artículo 8, numeral 1"): la
# línea que empieza con el número y un punto seguido de un blanco o del fin de la línea
# ("1. Toda persona…", "3.  ⏎ a) Nadie…"); no "1.e." ni "1.1" ni "2016.". Solo uno o dos
# dígitos.
_MARCA_PARRAFO = re.compile(r"^[ \t]*(?P<valor>\d{1,2})\.(?=[ \t]|$)", re.MULTILINE)
MAX_CONTINUACIONES = 8   # subfragmentos consecutivos del mismo precepto que se reúnen


def _primera_linea(texto: str) -> str | None:
    """Primera línea con contenido (sin ruido de página) de un texto sin acentos."""
    for linea in (texto or "").split("\n"):
        limpia = linea.strip()
        if limpia and not _RUIDO_PAGINA.match(limpia):
            return limpia
    return None


def clasificar_derogacion(texto: str) -> str | None:
    """``DEROGADO`` si la primera línea con contenido es una fórmula inequívoca de
    derogación; ``DEROGACION_AMBIGUA`` si empieza con una fórmula de derogación que no lo es;
    None en otro caso. ``texto`` es el cuerpo (o la unidad) que sigue a su encabezado."""
    linea = _primera_linea(_without_accents(texto))
    if linea is None:
        return None
    if _DEROGACION_PLENA.match(linea):
        return DEROGADO
    if _DEROGACION_AMBIGUA.match(linea):
        return DEROGACION_AMBIGUA
    return None


def cuerpo_suficiente(cuerpo: str) -> bool:
    """¿El cuerpo recuperado tras el encabezado basta para cotejar el precepto? Un
    encabezado sin texto ("Artículo 64.-" al final del fragmento) o con un trozo sin cerrar
    ("Artículo 64.- Las") no basta: la derogación o el contenido pueden estar en la
    continuación. Una fórmula de derogación es contenido completo."""
    if clasificar_derogacion(cuerpo):
        return True
    lineas = [
        linea.strip() for linea in _without_accents(cuerpo or "").split("\n")
        if linea.strip() and not _RUIDO_PAGINA.match(linea.strip())
    ]
    texto = " ".join(lineas)
    letras = sum(1 for caracter in texto if caracter.isalpha())
    if letras == 0:
        return False
    return letras >= 20 or bool(re.search(r"[.:;)]\s*$", texto))


def _indice(metadata: Mapping[str, Any] | None) -> int | None:
    try:
        return int(str((metadata or {}).get("chunk_index")))
    except (TypeError, ValueError):
        return None


def reconstruir_cuerpo(
    document: str,
    metadata: Mapping[str, Any] | None,
    article: str,
    candidatos: Iterable[tuple[str, Mapping[str, Any] | None]] = (),
    *,
    solo_autentico: bool = False,
    fin_de_linea: bool = False,
) -> dict[str, Any] | None:
    """Cuerpo del precepto citado: lo que sigue a su encabezado exacto hasta el encabezado
    de otro artículo. Si el fragmento termina antes (``cerrado`` False), se reúne la
    continuación entre los ``candidatos`` del MISMO precepto: misma fuente, misma etiqueta
    de artículo y ``chunk_index`` consecutivo (así guarda la ingesta los subfragmentos de un
    texto largo). Sin esos datos no se adivina la continuación. None sin encabezado exacto.

    Ronda 2: ``solo_autentico`` parte del primer encabezado AUTÉNTICO del fragmento (la misma
    ocurrencia que eligió ``select_article_evidence``), no de una remisión anterior.

    Tratados (4-oct-2026): con ``fin_de_linea`` el encabezado del precepto y el del siguiente
    artículo pueden no llevar cierre, y el cuerpo empieza tras la línea de título que sigue al
    encabezado, si la hay (``_inicio_tras_titulo``; CADH). Ronda 2: el cuerpo se detiene en
    cualquier línea candidata a encabezado (``_CANDIDATO_TRATADO``) y la continuación se une
    sin su solapamiento COMPROBADO con el fragmento anterior (``_solapamiento``: el prefijo de la
    continuación que repite exactamente el final de lo reunido), así que una línea repetida por
    la ingesta cuenta una vez y una repetida en otro lugar sigue siendo una repetición.
    """
    ocurrencias = [
        o for o in ocurrencias_encabezado(document, article, fin_de_linea=fin_de_linea)
        if o["autentico"] or not solo_autentico
    ]
    if not ocurrencias:
        return None
    normalized = _without_accents(document)
    inicio = ocurrencias[0]["fin"]
    if fin_de_linea:
        inicio = _inicio_tras_titulo(normalized, inicio)
    resto = normalized[inicio:]
    siguiente = _corte_del_cuerpo(resto, fin_de_linea)
    cuerpo, cerrado = (resto[:siguiente], True) if siguiente is not None else (resto, False)
    usados = 0
    indice = _indice(metadata)
    if not cerrado and indice is not None:
        fuente = (metadata or {}).get("source")
        etiqueta = (metadata or {}).get("article")
        por_indice: dict[int, str] = {}
        for doc, meta in candidatos:
            meta = meta or {}
            otro = _indice(meta)
            if otro is not None and meta.get("source") == fuente and meta.get("article") == etiqueta:
                por_indice.setdefault(otro, doc)
        actual = indice + 1
        while actual in por_indice and usados < MAX_CONTINUACIONES:
            texto = _PREFIJO_SUBFRAGMENTO.sub("", _without_accents(por_indice[actual]), count=1)
            usados += 1
            union = "\n"
            if fin_de_linea:
                solapado = _solapamiento(cuerpo, texto)
                if solapado:
                    # El resto continúa la misma línea del fragmento anterior.
                    texto, union = texto[solapado:], ""
            corte = _corte_del_cuerpo("\n" + texto, fin_de_linea)
            if corte is not None:
                cuerpo += (union + texto)[:corte - 1 + len(union)]
                cerrado = True
                break
            cuerpo += union + texto
            actual += 1
    return {"cuerpo": cuerpo, "cerrado": cerrado, "continuaciones": usados}


# Tratados (4-oct-2026, ronda 2) — Solapamiento de los subfragmentos de la ingesta (divisor de
# respaldo con 200 caracteres de solapamiento): solo se descuenta el COMPROBADO, el prefijo más
# largo de la continuación (de MIN_SOLAPAMIENTO a MAX_SOLAPAMIENTO caracteres) que es
# exactamente el final del texto reunido.
MIN_SOLAPAMIENTO = 20
MAX_SOLAPAMIENTO = 400


def _solapamiento(reunido: str, continuacion: str) -> int:
    """Caracteres del inicio de ``continuacion`` que repiten el final de ``reunido`` (0 si no
    hay un solapamiento comprobado)."""
    maximo = min(len(reunido), len(continuacion), MAX_SOLAPAMIENTO)
    for largo in range(maximo, MIN_SOLAPAMIENTO - 1, -1):
        if reunido.endswith(continuacion[:largo]):
            return largo
    return 0


def precepto_derogado(text: str, article: str, *, fin_de_linea: bool = False) -> bool:
    """Indica si ``text`` trae el encabezado exacto del precepto seguido de una fórmula
    INEQUÍVOCA de derogación: el texto vigente del corpus no contiene norma en ese precepto.

    Se examina el primer encabezado exacto (el mismo que acredita ``has_exact_article_heading``)
    y solo lo que lo sigue de inmediato; nunca el texto de otro artículo ni el de una
    fracción o un párrafo derogados dentro del cuerpo. ``fin_de_linea``: tratado (4-oct-2026).
    """
    reconstruido = reconstruir_cuerpo(text, None, article, fin_de_linea=fin_de_linea)
    return bool(reconstruido) and clasificar_derogacion(reconstruido["cuerpo"]) == DEROGADO


# ── Unidad citada (fracción, inciso, párrafo…) ─────────────────────────────────────────

_ROMANOS = ((100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"),
            (4, "IV"), (1, "I"))


def _romano(valor: str) -> str | None:
    limpio = (valor or "").strip().strip(".").strip()
    if re.fullmatch(r"[IVXLC]+", limpio, re.IGNORECASE):
        return limpio.upper()
    if limpio.isdigit() and 0 < int(limpio) < 400:
        numero, salida = int(limpio), ""
        for cantidad, simbolo in _ROMANOS:
            while numero >= cantidad:
                salida += simbolo
                numero -= cantidad
        return salida
    return None


def describir_unidad(unidad: Mapping[str, str]) -> str:
    tipo, valor = unidad.get("tipo"), unidad.get("valor", "")
    if tipo == "fraccion":
        return f"fracción {_romano(valor) or valor}"
    if tipo == "inciso":
        return f"inciso {valor})"
    if tipo == "parrafo":
        # "primer párrafo" → "párrafo primero"; "2°" se conserva.
        completo = {"primer": "primero", "tercer": "tercero"}.get(str(valor).lower(), valor)
        return f"párrafo {completo}"
    if tipo == "apartado":
        return f"apartado {valor}"
    if tipo == "parrafo_numerado":
        return f"párrafo numerado {valor}"
    return str(valor)


def _ubicar(texto: str, patron: re.Pattern, valor: str) -> str | None:
    """Texto de la unidad ``valor`` si su marca aparece UNA sola vez (si no, no es cierto)."""
    marcas = list(patron.finditer(texto))
    propias = [marca for marca in marcas if marca.group("valor") == valor]
    if len(propias) != 1:
        return None
    marca = propias[0]
    fin = next((otra.start() for otra in marcas if otra.start() > marca.start()), len(texto))
    return texto[marca.end():fin]


# Tratados (4-oct-2026, ronda 2) — Línea de notas tras el texto del artículo ("Nota", "Notas",
# "NOTAS", "Notas explicativas"): el párrafo numerado debe estar ANTES de ella; las marcas "1."
# de una nota no son párrafos del artículo.
_LINEA_NOTA = re.compile(r"^[ \t]*(?:Notas?|NOTAS?)(?![^\W\d_])", re.MULTILINE)


def _ubicar_parrafo_numerado(cuerpo: str, valor: str) -> tuple[str | None, str]:
    """Texto del párrafo numerado ``valor`` en el cuerpo (sin acentos), o None y el motivo.

    Se exige, para no tomar por párrafo una lista o un número suelto: la marca citada aparece
    UNA sola vez; las marcas del cuerpo, en su orden, son exactamente 1, 2, 3… (sin saltos ni
    repeticiones); y antes de la marca "1." no hay ninguna marca de fracción ni de inciso (las
    listas "1. … 2. …" dentro de una fracción no son párrafos del artículo). El texto llega
    hasta la siguiente marca de párrafo. Ronda 2: solo cuenta lo anterior a la primera línea de
    notas (``_LINEA_NOTA``), y una línea repetida es una repetición (el solapamiento de la
    ingesta ya lo descontó ``reconstruir_cuerpo`` solo donde está comprobado)."""
    nota = _LINEA_NOTA.search(cuerpo)
    if nota:
        cuerpo = cuerpo[:nota.start()]
    marcas = list(_MARCA_PARRAFO.finditer(cuerpo))
    numeros = [int(marca.group("valor")) for marca in marcas]
    if not numeros:
        return None, (f"el texto recuperado del artículo no tiene párrafos numerados "
                      f"(ninguna línea empieza con «{valor}.»)")
    if numeros != list(range(1, len(numeros) + 1)):
        return None, (
            f"la numeración de los párrafos del texto recuperado no es la secuencia 1, 2, 3… "
            f"({', '.join(map(str, numeros[:12]))}): el párrafo {valor} no se ubica de forma "
            f"inequívoca"
        )
    previo = cuerpo[:marcas[0].start()]
    if _MARCA_FRACCION.search(previo) or _MARCA_INCISO.search(previo):
        return None, (
            "antes del párrafo 1 hay fracciones o incisos: la numeración no es la de los "
            "párrafos del artículo"
        )
    propias = [marca for marca in marcas if int(marca.group("valor")) == int(valor)]
    if len(propias) != 1:
        return None, (
            f"el párrafo {valor} no se ubica en el texto recuperado del artículo (ninguna línea "
            f"empieza con «{valor}.»)"
        )
    marca = propias[0]
    fin = next((otra.start() for otra in marcas if otra.start() > marca.start()), len(cuerpo))
    return cuerpo[marca.end():fin], ""


def cotejar_unidad(
    cuerpo: str, unidades: Iterable[Mapping[str, str]], *, parrafos_numerados: bool = False
) -> dict[str, Any]:
    """Coteja la unidad citada en el cuerpo del precepto.

    ``estado``: "cotejada" (se ubicó de forma inequívoca y no está derogada), "derogada"
    (su texto es una fórmula inequívoca de derogación), "ambigua" (fórmula de derogación no
    inequívoca) o "no_cotejada" (no se pudo ubicar con certeza, con ``motivo``). Todas las
    unidades citadas deben cotejarse ("incisos c), d) y f)": las tres).

    Tratados (4-oct-2026): también el párrafo numerado ("artículo 8.1", "artículo 8, numeral
    1"; ``_ubicar_parrafo_numerado``), y el inciso dentro de él ("artículo 8.2, inciso h)"). Si
    la línea no se ubica, la cita queda 🟡 UNIDAD CITADA NO COTEJADA: nunca 🟢 del artículo
    completo. Ronda 2 (adjudicado): el cotejo POSITIVO del párrafo numerado solo con
    ``parrafos_numerados=True`` (fuente registrada como tratado internacional); en una ley
    nacional "párrafo 1" suele ser el primer párrafo por posición y queda no cotejado, también
    en cualquier llamada que no lo active.
    """
    unidades = list(unidades)
    descripcion = ", ".join(describir_unidad(u) for u in unidades)

    def no_cotejada(motivo: str) -> dict[str, Any]:
        return {"estado": "no_cotejada", "descripcion": descripcion, "motivo": motivo}

    soportadas = ("fraccion", "inciso") + (("parrafo_numerado",) if parrafos_numerados else ())
    otras = [u for u in unidades if u.get("tipo") not in soportadas]
    if otras:
        if otras[0].get("tipo") == "parrafo_numerado":
            return no_cotejada(
                f"el {describir_unidad(otras[0])} solo se coteja en los tratados internacionales "
                "registrados: en una ley, \"párrafo N\" puede ser el párrafo por posición, que no "
                "se ubica con certeza en el texto del corpus"
            )
        return no_cotejada(
            f"la unidad citada ({describir_unidad(otras[0])}) no se puede ubicar con certeza en el texto del "
            "corpus (solo se cotejan fracciones e incisos y, en los tratados, párrafos numerados)"
        )
    cuerpo = _without_accents(cuerpo or "")
    ubicadas: list[tuple[str, str]] = []
    parrafos = [u for u in unidades if u.get("tipo") == "parrafo_numerado"]
    if parrafos and any(u.get("tipo") == "fraccion" for u in unidades):
        return no_cotejada("se citan a la vez una fracción y un párrafo numerado del artículo: no "
                           "se ubican con certeza")
    for parrafo in parrafos:
        valor = str(parrafo.get("valor") or "").strip()
        if not valor.isdigit():
            return no_cotejada(f"el párrafo numerado '{valor}' no es reconocible")
        texto, motivo = _ubicar_parrafo_numerado(cuerpo, valor)
        if texto is None:
            return no_cotejada(motivo)
        ubicadas.append((f"párrafo numerado {int(valor)}", texto))
    fracciones = [u for u in unidades if u.get("tipo") == "fraccion"]
    for fraccion in fracciones:
        romano = _romano(fraccion.get("valor", ""))
        if romano is None:
            return no_cotejada(f"la fracción '{fraccion.get('valor')}' no es reconocible")
        texto = _ubicar(cuerpo, _MARCA_FRACCION, romano)
        if texto is None:
            return no_cotejada(
                f"la fracción {romano} no se ubica de forma inequívoca en el texto recuperado "
                "del artículo"
            )
        ubicadas.append((f"fracción {romano}", texto))
    incisos = [u for u in unidades if u.get("tipo") == "inciso"]
    if incisos:
        if len(ubicadas) > 1:
            return no_cotejada("inciso citado con varias fracciones o párrafos: no se sabe de "
                               "cuál es")
        prefijo, base = (ubicadas[0][0] + ", ", ubicadas[0][1]) if ubicadas else ("", cuerpo)
        ubicadas = []
        for inciso in incisos:
            letra = (inciso.get("valor") or "").strip().lower()
            texto = _ubicar(base, _MARCA_INCISO, letra)
            if texto is None:
                return no_cotejada(
                    f"el inciso {letra}) no se ubica de forma inequívoca en el texto recuperado"
                )
            ubicadas.append((f"{prefijo}inciso {letra})", texto))
    derogadas, ambiguas = [], []
    for nombre, texto in ubicadas:
        clase = clasificar_derogacion(texto)
        if clase == DEROGADO:
            derogadas.append(nombre)
        elif clase == DEROGACION_AMBIGUA:
            ambiguas.append(nombre)
        elif not cuerpo_suficiente(texto):
            return no_cotejada(f"el texto de la {nombre} recuperado está incompleto")
    if derogadas:
        return {"estado": "derogada", "descripcion": descripcion, "derogadas": derogadas,
                "motivo": None}
    if ambiguas:
        return {"estado": "ambigua", "descripcion": descripcion, "ambiguas": ambiguas,
                "motivo": None}
    return {"estado": "cotejada", "descripcion": descripcion, "motivo": None}


def cotejar_precepto(
    document: str,
    metadata: Mapping[str, Any] | None,
    article: str,
    unidades: Iterable[Mapping[str, str]] = (),
    candidatos: Iterable[tuple[str, Mapping[str, Any] | None]] = (),
    *,
    solo_autentico: bool = False,
    fin_de_linea: bool = False,
) -> dict[str, Any] | None:
    """Coteja el precepto ubicado (encabezado exacto): derogación del precepto completo,
    suficiencia del cuerpo (con su continuación, si la hay) y la unidad citada.

    Devuelve None si el fragmento no trae el encabezado exacto. Con un precepto derogado
    por completo la unidad citada no se coteja (todo el precepto carece de norma).
    ``solo_autentico`` (ronda 2): coteja desde el encabezado auténtico elegido.
    ``fin_de_linea`` (4-oct-2026): la fuente esperada es un tratado internacional registrado;
    solo entonces se coteja el párrafo numerado, y (ronda 2) un título solo no completa el
    cuerpo (``cuerpo_suficiente_tratado``).
    """
    reconstruido = reconstruir_cuerpo(document, metadata, article, candidatos,
                                      solo_autentico=solo_autentico, fin_de_linea=fin_de_linea)
    if reconstruido is None:
        return None
    cuerpo = reconstruido["cuerpo"]
    derogacion = clasificar_derogacion(cuerpo)
    unidades = [dict(u) for u in unidades]
    unidad = None
    if unidades and derogacion != DEROGADO:
        unidad = cotejar_unidad(cuerpo, unidades, parrafos_numerados=fin_de_linea)
    return {
        "derogacion": derogacion,
        "completo": (
            cuerpo_suficiente_tratado(cuerpo) if fin_de_linea else cuerpo_suficiente(cuerpo)
        ),
        "cerrado": reconstruido["cerrado"],
        "continuaciones": reconstruido["continuaciones"],
        "unidad": unidad,
    }


def has_suffixed_variant_heading(text: str, article: str, *, fin_de_linea: bool = False) -> bool:
    """Indica si ``text`` trae el encabezado de una variante con sufijo del mismo número
    (``Artículo 4o.-A.-`` para ``4o``; ``Artículo 247 Bis.-`` para ``247``).

    El chunker etiqueta esos fragmentos con el número base, así que la búsqueda por
    metadata los ofrece como candidatos del artículo base. Que el índice solo devuelva
    variantes no prueba nada sobre el precepto pedido: la cita queda no verificable.
    ``fin_de_linea`` (tratado, 4-oct-2026): el encabezado exacto sin cierre también descarta
    la variante.
    """
    variant_pattern = patron_variante_con_sufijo(article, ordinal_equivalente=True)
    if not variant_pattern:
        return False
    # Ronda 2: también la variante con el sufijo partido en la línea siguiente
    # ("Artículo 4o.\n-A.-", "Artículo 1o.\nBis.-").
    base = patron_articulo(article, ordinal_equivalente=True)
    partida = (
        rf"|{base}{_CIERRE_ENCABEZADO}(?={_SUFIJO_EN_LINEA_SIGUIENTE})" if base else ""
    )
    heading = re.compile(
        rf"{_PREFIJO_ENCABEZADO}(?:{variant_pattern}{partida})", re.IGNORECASE | re.MULTILINE
    )
    return bool(heading.search(_without_accents(text))) and not has_exact_article_heading(
        text, article, fin_de_linea=fin_de_linea
    )


def _primera_aparicion(indices: list[int], metadatas: list) -> int:
    """De los resultados ``indices`` (en orden de ranking) con el encabezado exacto, el de
    menor ``chunk_index`` si todos son de la misma fuente y lo traen entero; si no, el mejor
    rankeado (el primero)."""
    fuentes, claves = set(), []
    for posicion, index in enumerate(indices):
        metadata = metadatas[index] if index < len(metadatas) else None
        chunk = _indice(metadata)
        if chunk is None:
            return indices[0]
        fuentes.add((metadata or {}).get("source"))
        claves.append((chunk, posicion, index))
    if len(fuentes) != 1:
        return indices[0]
    return min(claves)[2]


def select_article_evidence(
    results: Mapping[str, Any] | None,
    article: str,
    *,
    preferido: int | None = None,
    fin_de_linea: bool = False,
) -> dict[str, Any] | None:
    """Elige el resultado mejor rankeado que muestre el encabezado exacto.

    Si una remisión interna tiene menor distancia que el encabezado auténtico, se
    prefiere el encabezado. Si ninguno lo contiene, se conserva el primer resultado
    para auditabilidad, pero se marca como no corroborado; ``variant_heading`` indica
    entonces si algún resultado era una variante con sufijo del mismo número.

    Ordinales y verde determinista (3-oct-2026): si VARIOS fragmentos de la misma fuente
    traen el encabezado exacto, se elige la primera aparición en el documento (menor
    ``chunk_index``), no la de menor distancia: el cuerpo de la ley precede a sus
    transitorios, y con la equivalencia ordinal "Artículo 1o.-" del cuerpo convive, p. ej.,
    con "Artículo 1º.- Esta Ley entrará en vigor…" de los transitorios (LFT) o con "Artículo
    1.- Se reforma…" de un decreto (CCF). Desde que la distancia no decide el 🟢 de una cita
    con evidencia completa, la ubicación no puede depender de qué fragmento se parece más a
    la consulta. Sin ``chunk_index`` entero en todos ellos, o con fuentes distintas, decide
    el ranking como antes.

    Ronda 2: antes de la primera aparición se prefieren los encabezados AUTÉNTICOS
    (``ocurrencias_encabezado``): la remisión "artículo 41." al inicio de una línea suele
    estar en el fragmento del 40 y, sin esta preferencia, ganaba al "Artículo 41." del
    cuerpo. ``heading_authentic`` dice si el elegido es auténtico y ``autenticos`` lista los
    resultados que lo son (para ``itosturre.audit.ubicacion``). ``preferido`` fuerza el
    resultado (un índice de ``autenticos``) cuando la frontera del cuerpo lo decide.

    Tratados (4-oct-2026): ``fin_de_linea`` (la fuente esperada es un tratado internacional
    registrado) admite el encabezado auténtico sin cierre ("Artículo 8º" solo en su línea);
    ``heading_fin_de_linea`` dice si el elegido es de esa forma.
    """
    if not results:
        return None
    documents_batches = results.get("documents") or []
    if not documents_batches or not documents_batches[0]:
        return None

    documents = documents_batches[0]
    metadatas_batches = results.get("metadatas") or []
    distances_batches = results.get("distances") or []
    metadatas = metadatas_batches[0] if metadatas_batches else []
    distances = distances_batches[0] if distances_batches else []

    selected_index = 0
    con_encabezado = [
        index for index, document in enumerate(documents)
        if has_exact_article_heading(document, article, fin_de_linea=fin_de_linea)
    ]
    autenticos = [
        index for index in con_encabezado
        if encabezado_autentico(documents[index], article, fin_de_linea=fin_de_linea)
    ]
    heading_verified = bool(con_encabezado)
    if preferido is not None and preferido in autenticos:
        selected_index = preferido
    elif autenticos:
        selected_index = _primera_aparicion(autenticos, metadatas)
    elif con_encabezado:
        selected_index = _primera_aparicion(con_encabezado, metadatas)

    variant_heading = not heading_verified and any(
        has_suffixed_variant_heading(document, article, fin_de_linea=fin_de_linea)
        for document in documents
    )
    metadata = metadatas[selected_index] if selected_index < len(metadatas) else {}
    distance = distances[selected_index] if selected_index < len(distances) else 1.0
    forma_elegida = next(
        (o["forma"] for o in ocurrencias_encabezado(
            documents[selected_index], article, fin_de_linea=fin_de_linea) if o["autentico"]),
        None,
    ) if selected_index in autenticos else None
    return {
        "document": documents[selected_index],
        "metadata": metadata or {},
        "distance": float(distance),
        "heading_verified": heading_verified,
        # Ronda 2 (campos añadidos): el elegido es un encabezado auténtico, y los resultados
        # con encabezado auténtico (índices en ``results``).
        "heading_authentic": selected_index in autenticos,
        "autenticos": autenticos,
        # Ordinales (3-oct-2026, campo añadido): el encabezado elegido coincide también con el
        # ordinal tal como se citó; False si solo coincide por la equivalencia ("2" frente a
        # "ARTÍCULO 2o.-"). ``audit`` lo usa en la ruta semántica (sin metadata).
        "heading_literal": heading_verified and has_exact_article_heading(
            documents[selected_index], article, ordinal_literal=True, fin_de_linea=fin_de_linea
        ),
        # Tratados (4-oct-2026, campo añadido): el encabezado auténtico elegido no lleva cierre
        # ("Artículo 8º" solo en su línea); solo posible con ``fin_de_linea``.
        "heading_fin_de_linea": forma_elegida == FORMA_FIN_DE_LINEA,
        "variant_heading": variant_heading,
        "rank": selected_index + 1,
    }
