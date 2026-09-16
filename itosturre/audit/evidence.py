"""Validaciones puras de evidencia normativa recuperada del corpus."""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Mapping


def _without_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value or "")
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def has_exact_article_heading(text: str, article: str) -> bool:
    """Indica si ``text`` contiene el encabezado del artículo solicitado.

    Una remisión como ``artículo 42, fracción XIII`` no cuenta. Para acreditar la
    identidad del fragmento se exige una línea con forma de encabezado, por ejemplo
    ``Artículo 42.``, ``Artículo 38.-`` o ``Art. 1004-A.-``.
    """
    normalized_article = " ".join(_without_accents(article).strip().split())
    if not normalized_article:
        return False
    article_pattern = re.escape(normalized_article).replace(r"\ ", r"[ \t]+")
    heading = re.compile(
        rf"^[ \t]*art(?:iculo)?\.?[ \t]+{article_pattern}[ \t]*(?:\.\-|[.\-:])",
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(heading.search(_without_accents(text)))


def select_article_evidence(
    results: Mapping[str, Any] | None, article: str
) -> dict[str, Any] | None:
    """Elige el resultado mejor rankeado que muestre el encabezado exacto.

    Si una remisión interna tiene menor distancia que el encabezado auténtico, se
    prefiere el encabezado. Si ninguno lo contiene, se conserva el primer resultado
    para auditabilidad, pero se marca como no corroborado.
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

    metadata = metadatas[selected_index] if selected_index < len(metadatas) else {}
    distance = distances[selected_index] if selected_index < len(distances) else 1.0
    return {
        "document": documents[selected_index],
        "metadata": metadata or {},
        "distance": float(distance),
        "heading_verified": heading_verified,
        "rank": selected_index + 1,
    }
