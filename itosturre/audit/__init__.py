"""Políticas puras de auditoría VVCA, sin dependencias de ChromaDB ni del modelo."""

from .context import vvca_contextualizacion
from .evidence import (
    has_exact_article_heading,
    has_suffixed_variant_heading,
    select_article_evidence,
)
from .jurisprudence import classify_fuerza_vinculante, rubro_keywords
from .policy import disclaimer_graduado, vvca_score, vvca_semaforo
from .traceability import build_trace_record, traceability_bundle

__all__ = [
    "classify_fuerza_vinculante",
    "disclaimer_graduado",
    "has_exact_article_heading",
    "has_suffixed_variant_heading",
    "rubro_keywords",
    "select_article_evidence",
    "vvca_contextualizacion",
    "vvca_score",
    "vvca_semaforo",
    "build_trace_record",
    "traceability_bundle",
]
