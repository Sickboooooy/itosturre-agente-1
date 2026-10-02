"""Validaciones puras de evidencia normativa recuperada del corpus."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable, Mapping

from .referencias import patron_articulo, patron_variante_con_sufijo


def _without_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


# Línea con forma de encabezado: "Artículo 42.", "Artículo 38.-", "Art. 1004-A.-".
_PREFIJO_ENCABEZADO = r"^[ \t]*art(?:iculo)?\.?[ \t]+"
_CIERRE_ENCABEZADO = r"[ \t]*(?:\.\-|[.\-:])"


def _patron_literal(article: str) -> str | None:
    """Designación no descomponible: el texto literal (comportamiento anterior a R4b)."""
    normalized_article = " ".join(_without_accents(article).strip().split())
    if not normalized_article:
        return None
    return re.escape(normalized_article).replace(r"\ ", r"[ \t]+")


def has_exact_article_heading(text: str, article: str) -> bool:
    """Indica si ``text`` contiene el encabezado del artículo solicitado.

    Una remisión como ``artículo 42, fracción XIII`` no cuenta. Para acreditar la
    identidad del fragmento se exige una línea con forma de encabezado, por ejemplo
    ``Artículo 42.``, ``Artículo 38.-`` o ``Art. 1004-A.-``.

    Tras el número solo cabe el cierre del encabezado (R4-D06): ``Artículo 4o.-A.-`` no es
    el encabezado del artículo ``4o``, ni ``Artículo 29-B.`` el del ``29``, ni
    ``Artículo 209 Bis.-`` el del ``209``. Un sufijo de letra o latino solo coincide si se
    pidió (``4o.-A``, ``29-B``, ``209 Bis``). El ordinal se compara tal como se pidió.
    """
    heading = _encabezado_exacto(article)
    if heading is None:
        return False
    return bool(heading.search(_without_accents(text)))


def _encabezado_exacto(article: str) -> re.Pattern | None:
    article_pattern = patron_articulo(article) or _patron_literal(article)
    if not article_pattern:
        return None
    return re.compile(
        rf"{_PREFIJO_ENCABEZADO}{article_pattern}{_CIERRE_ENCABEZADO}",
        re.IGNORECASE | re.MULTILINE,
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
_SUFIJO_GENERICO = (
    r"(?:[ \t]*\.?[ \t]*-?[ \t]*(?:(?-i:[A-Z])|bis|ter|quater|quinquies|sexies|septies"
    r"|octies|nonies|decies)(?![^\W\d_]))"
)
_ENCABEZADO_SIGUIENTE = re.compile(
    rf"^[ \t]*(?-i:A)rt(?:iculo)?\.?[ \t]+"
    rf"(?P<designacion>\d+(?:[oaºª°](?![^\W\d_]))?{_SUFIJO_GENERICO}*)"
    r"[ \t]*(?:\.\-|\.(?=\s)|\.$|-(?=\s)|:)",
    re.IGNORECASE | re.MULTILINE,
)
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
) -> dict[str, Any] | None:
    """Cuerpo del precepto citado: lo que sigue a su encabezado exacto hasta el encabezado
    de otro artículo. Si el fragmento termina antes (``cerrado`` False), se reúne la
    continuación entre los ``candidatos`` del MISMO precepto: misma fuente, misma etiqueta
    de artículo y ``chunk_index`` consecutivo (así guarda la ingesta los subfragmentos de un
    texto largo). Sin esos datos no se adivina la continuación. None sin encabezado exacto.
    """
    heading = _encabezado_exacto(article)
    if heading is None:
        return None
    normalized = _without_accents(document)
    match = heading.search(normalized)
    if not match:
        return None
    resto = normalized[match.end():]
    siguiente = _ENCABEZADO_SIGUIENTE.search(resto)
    cuerpo, cerrado = (resto[:siguiente.start()], True) if siguiente else (resto, False)
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
            corte = _ENCABEZADO_SIGUIENTE.search(texto)
            if corte:
                cuerpo += "\n" + texto[:corte.start()]
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
) -> dict[str, Any] | None:
    """Coteja el precepto ubicado (encabezado exacto): derogación del precepto completo,
    suficiencia del cuerpo (con su continuación, si la hay) y la unidad citada.

    Devuelve None si el fragmento no trae el encabezado exacto. Con un precepto derogado
    por completo la unidad citada no se coteja (todo el precepto carece de norma).
    """
    reconstruido = reconstruir_cuerpo(document, metadata, article, candidatos)
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
    variant_pattern = patron_variante_con_sufijo(article)
    if not variant_pattern:
        return False
    heading = re.compile(
        rf"{_PREFIJO_ENCABEZADO}{variant_pattern}", re.IGNORECASE | re.MULTILINE
    )
    return bool(heading.search(_without_accents(text))) and not has_exact_article_heading(
        text, article
    )


def select_article_evidence(
    results: Mapping[str, Any] | None, article: str
) -> dict[str, Any] | None:
    """Elige el resultado mejor rankeado que muestre el encabezado exacto.

    Si una remisión interna tiene menor distancia que el encabezado auténtico, se
    prefiere el encabezado. Si ninguno lo contiene, se conserva el primer resultado
    para auditabilidad, pero se marca como no corroborado; ``variant_heading`` indica
    entonces si algún resultado era una variante con sufijo del mismo número.
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
    heading_verified = False
    for index, document in enumerate(documents):
        if has_exact_article_heading(document, article):
            selected_index = index
            heading_verified = True
            break

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
        "variant_heading": variant_heading,
        "rank": selected_index + 1,
    }
