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


def _es_autentico(normalizado: str, inicio: int, fin: int) -> bool:
    """¿El encabezado ``normalizado[inicio:fin]`` (texto sin acentos, terminado en su cierre)
    es AUTÉNTICO? "A" mayúscula en el prefijo y cierre no seguido de "," ni ";".

    Definición ÚNICA (re-ingesta por fuente, 4-oct-2026): la usan ``ocurrencias_encabezado``
    (el encabezado exacto que acredita un precepto) y ``encabezados_autenticos`` (con el que la
    ingesta corta y etiqueta los fragmentos), para que lo que la ingesta toma por encabezado y
    lo que la auditoría acepta como tal no diverjan."""
    return (
        normalizado[inicio:fin].lstrip()[:1] == "A"
        and not _SIGUE_REMISION.match(normalizado, fin)
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


def encabezados_autenticos(texto: str, *, fin_de_linea: bool = False) -> list[dict[str, Any]]:
    """Encabezados AUTÉNTICOS de cualquier artículo en ``texto``, en su orden: ``inicio`` y
    ``fin`` (posiciones del texto SIN acentos; el inicio es el de su línea), ``designacion``
    (sin acentos, espacios normalizados: "4o.-A", "247 Bis", "1º") y ``forma``.

    Con cierre (``FORMA_CIERRE``) rige ``_es_autentico``, la misma definición que
    ``ocurrencias_encabezado``: "ARTICULO 496.-", "Artículo 1o.-", "Artículo 75.Quedan…" y
    "Artículo 26." (con "A. El Estado…" en la línea siguiente) lo son; "artículo 41." (remisión
    en minúscula), "Artículo 2o., fracción I" (cita) y "Artículo 51 de esta Ley…" (sin cierre)
    no. ``fin_de_linea=True`` (solo la ingesta) admite además la designación sola al final de
    su línea con "A" mayúscula (``FORMA_FIN_DE_LINEA``: "Artículo 51", "ARTÍCULO 1"), salvo
    que la siguiente línea con contenido continúe una oración (minúscula, "," o ";"). La
    auditoría no acepta esa forma como encabezado exacto (exige el cierre). Ronda 2: el
    encabezado partido entre líneas ("ARTICULO\n508.-") cuenta, con cierre, para ambas."""
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
                or normalizado[m.start():m.end()].lstrip()[:1] != "A"
                or _CONTINUA_ORACION.match(normalizado, m.end())
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


def has_exact_article_heading(text: str, article: str, *, ordinal_literal: bool = False) -> bool:
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
    """
    heading = _encabezado_exacto(article, ordinal_literal=ordinal_literal)
    if heading is None:
        return False
    return bool(heading.search(_without_accents(text)))


def _encabezado_exacto(article: str, *, ordinal_literal: bool = False) -> re.Pattern | None:
    article_pattern = (
        patron_articulo(article, ordinal_equivalente=not ordinal_literal)
        or _patron_literal(article)
    )
    if not article_pattern:
        return None
    return re.compile(
        rf"{_PREFIJO_ENCABEZADO}{article_pattern}{_CIERRE_ENCABEZADO}"
        rf"(?!{_SUFIJO_EN_LINEA_SIGUIENTE})",
        re.IGNORECASE | re.MULTILINE,
    )


def ocurrencias_encabezado(text: str, article: str) -> list[dict[str, Any]]:
    """Cada encabezado exacto del artículo en ``text`` (sin acentos): ``inicio``, ``fin`` y si
    es AUTÉNTICO (ronda 2): "A" mayúscula en el prefijo y cierre no seguido de "," ni ";".
    Las posiciones son del texto sin acentos (las mismas que usa ``reconstruir_cuerpo``).
    La autenticidad la decide ``_es_autentico``, la misma definición con que la ingesta corta
    y etiqueta (``encabezados_autenticos``)."""
    heading = _encabezado_exacto(article)
    if heading is None:
        return []
    normalizado = _without_accents(text)
    return [
        {
            "inicio": m.start(),
            "fin": m.end(),
            "autentico": _es_autentico(normalizado, m.start(), m.end()),
        }
        for m in heading.finditer(normalizado)
    ]


def encabezado_autentico(text: str, article: str) -> bool:
    """¿``text`` trae un encabezado AUTÉNTICO del artículo (no una remisión)? Ronda 2."""
    return any(o["autentico"] for o in ocurrencias_encabezado(text, article))


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


def _corte_del_cuerpo(texto: str) -> int | None:
    """Dónde termina el cuerpo de un precepto en ``texto`` (lo que sigue a su encabezado): el
    encabezado de otro artículo o, ronda 2 de la re-ingesta (4-oct-2026), la línea
    TRANSITORIOS, la que llegue antes. Así una fracción de un transitorio ("ARTÍCULO
    PRIMERO.-\nI. …") nunca se toma como fracción del último artículo del cuerpo."""
    siguiente = _ENCABEZADO_SIGUIENTE.search(texto)
    tope = siguiente.start() if siguiente else len(texto)
    posicion = 0
    for linea in texto[:tope].split("\n"):
        if posicion and es_frontera_transitorios(linea):
            return posicion
        posicion += len(linea) + 1
    return siguiente.start() if siguiente else None
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
) -> dict[str, Any] | None:
    """Cuerpo del precepto citado: lo que sigue a su encabezado exacto hasta el encabezado
    de otro artículo. Si el fragmento termina antes (``cerrado`` False), se reúne la
    continuación entre los ``candidatos`` del MISMO precepto: misma fuente, misma etiqueta
    de artículo y ``chunk_index`` consecutivo (así guarda la ingesta los subfragmentos de un
    texto largo). Sin esos datos no se adivina la continuación. None sin encabezado exacto.

    Ronda 2: ``solo_autentico`` parte del primer encabezado AUTÉNTICO del fragmento (la misma
    ocurrencia que eligió ``select_article_evidence``), no de una remisión anterior.
    """
    ocurrencias = [
        o for o in ocurrencias_encabezado(document, article)
        if o["autentico"] or not solo_autentico
    ]
    if not ocurrencias:
        return None
    normalized = _without_accents(document)
    resto = normalized[ocurrencias[0]["fin"]:]
    siguiente = _corte_del_cuerpo(resto)
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
            corte = _corte_del_cuerpo("\n" + texto)
            if corte is not None:
                cuerpo += ("\n" + texto)[:corte]
                cerrado = True
                break
            cuerpo += "\n" + texto
            actual += 1
    return {"cuerpo": cuerpo, "cerrado": cerrado, "continuaciones": usados}


def precepto_derogado(text: str, article: str) -> bool:
    """Indica si ``text`` trae el encabezado exacto del precepto seguido de una fórmula
    INEQUÍVOCA de derogación: el texto vigente del corpus no contiene norma en ese precepto.

    Se examina el primer encabezado exacto (el mismo que acredita ``has_exact_article_heading``)
    y solo lo que lo sigue de inmediato; nunca el texto de otro artículo ni el de una
    fracción o un párrafo derogados dentro del cuerpo.
    """
    reconstruido = reconstruir_cuerpo(text, None, article)
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


def cotejar_unidad(cuerpo: str, unidades: Iterable[Mapping[str, str]]) -> dict[str, Any]:
    """Coteja la unidad citada en el cuerpo del precepto.

    ``estado``: "cotejada" (se ubicó de forma inequívoca y no está derogada), "derogada"
    (su texto es una fórmula inequívoca de derogación), "ambigua" (fórmula de derogación no
    inequívoca) o "no_cotejada" (no se pudo ubicar con certeza, con ``motivo``).
    """
    unidades = list(unidades)
    descripcion = ", ".join(describir_unidad(u) for u in unidades)

    def no_cotejada(motivo: str) -> dict[str, Any]:
        return {"estado": "no_cotejada", "descripcion": descripcion, "motivo": motivo}

    otras = [u for u in unidades if u.get("tipo") not in ("fraccion", "inciso")]
    if otras:
        return no_cotejada(
            f"la unidad citada ({describir_unidad(otras[0])}) no se puede ubicar con certeza en el texto del "
            "corpus (solo se cotejan fracciones e incisos)"
        )
    cuerpo = _without_accents(cuerpo or "")
    ubicadas: list[tuple[str, str]] = []
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
            return no_cotejada("inciso citado con varias fracciones: no se sabe de cuál es")
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
) -> dict[str, Any] | None:
    """Coteja el precepto ubicado (encabezado exacto): derogación del precepto completo,
    suficiencia del cuerpo (con su continuación, si la hay) y la unidad citada.

    Devuelve None si el fragmento no trae el encabezado exacto. Con un precepto derogado
    por completo la unidad citada no se coteja (todo el precepto carece de norma).
    ``solo_autentico`` (ronda 2): coteja desde el encabezado auténtico elegido.
    """
    reconstruido = reconstruir_cuerpo(document, metadata, article, candidatos,
                                      solo_autentico=solo_autentico)
    if reconstruido is None:
        return None
    cuerpo = reconstruido["cuerpo"]
    derogacion = clasificar_derogacion(cuerpo)
    unidades = [dict(u) for u in unidades]
    unidad = None
    if unidades and derogacion != DEROGADO:
        unidad = cotejar_unidad(cuerpo, unidades)
    return {
        "derogacion": derogacion,
        "completo": cuerpo_suficiente(cuerpo),
        "cerrado": reconstruido["cerrado"],
        "continuaciones": reconstruido["continuaciones"],
        "unidad": unidad,
    }


def has_suffixed_variant_heading(text: str, article: str) -> bool:
    """Indica si ``text`` trae el encabezado de una variante con sufijo del mismo número
    (``Artículo 4o.-A.-`` para ``4o``; ``Artículo 247 Bis.-`` para ``247``).

    El chunker etiqueta esos fragmentos con el número base, así que la búsqueda por
    metadata los ofrece como candidatos del artículo base. Que el índice solo devuelva
    variantes no prueba nada sobre el precepto pedido: la cita queda no verificable.
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
        text, article
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
    results: Mapping[str, Any] | None, article: str, *, preferido: int | None = None
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
        if has_exact_article_heading(document, article)
    ]
    autenticos = [
        index for index in con_encabezado if encabezado_autentico(documents[index], article)
    ]
    heading_verified = bool(con_encabezado)
    if preferido is not None and preferido in autenticos:
        selected_index = preferido
    elif autenticos:
        selected_index = _primera_aparicion(autenticos, metadatas)
    elif con_encabezado:
        selected_index = _primera_aparicion(con_encabezado, metadatas)

    variant_heading = not heading_verified and any(
        has_suffixed_variant_heading(document, article) for document in documents
    )
    metadata = metadatas[selected_index] if selected_index < len(metadatas) else {}
    distance = distances[selected_index] if selected_index < len(distances) else 1.0
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
            documents[selected_index], article, ordinal_literal=True
        ),
        "variant_heading": variant_heading,
        "rank": selected_index + 1,
    }
