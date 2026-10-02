"""Validaciones puras de evidencia normativa recuperada del corpus."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping

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
    article_pattern = patron_articulo(article) or _patron_literal(article)
    if not article_pattern:
        return False
    heading = re.compile(
        rf"{_PREFIJO_ENCABEZADO}{article_pattern}{_CIERRE_ENCABEZADO}",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(heading.search(_without_accents(text)))


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
