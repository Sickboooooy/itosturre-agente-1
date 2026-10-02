"""Políticas puras de auditoría VVCA, sin dependencias de ChromaDB ni del modelo."""

from .context import vvca_contextualizacion
from .evidence import (
    clasificar_derogacion,
    cotejar_precepto,
    has_exact_article_heading,
    has_suffixed_variant_heading,
    precepto_derogado,
    select_article_evidence,
)
from .jurisprudence import classify_fuerza_vinculante, rubro_keywords
from .policy import (
    ALCANCE_JURISPRUDENCIA,
    ALCANCE_NORMATIVA,
    SEMAFORO_SIN_CITAS,
    disclaimer_graduado,
    semaforo_dimension,
    vvca_score,
    vvca_semaforo,
)
from .traceability import build_trace_record, traceability_bundle

__all__ = [
    "ALCANCE_JURISPRUDENCIA",
    "ALCANCE_NORMATIVA",
    "SEMAFORO_SIN_CITAS",
    "clasificar_derogacion",
    "classify_fuerza_vinculante",
    "cotejar_precepto",
    "disclaimer_graduado",
    "has_exact_article_heading",
    "has_suffixed_variant_heading",
    "precepto_derogado",
    "rubro_keywords",
    "select_article_evidence",
    "semaforo_dimension",
    "vvca_contextualizacion",
    "vvca_score",
    "vvca_semaforo",
    "build_trace_record",
    "traceability_bundle",
]
