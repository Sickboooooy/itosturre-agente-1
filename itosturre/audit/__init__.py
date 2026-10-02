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
from .jurisprudence import (
    classify_fuerza_vinculante,
    cotejar_rubro,
    diferencias_polaridad,
    extraer_rubro_invocado,
    extraer_rubro_posterior,
    normalizar_rubro,
    normalizar_vigencia,
    rubro_keywords,
)
from .policy import (
    ALCANCE_JURISPRUDENCIA,
    ALCANCE_JURISPRUDENCIA_SIN_RUBRO,
    ALCANCE_NORMATIVA,
    SEMAFORO_SIN_CITAS,
    alcance_jurisprudencia,
    disclaimer_graduado,
    semaforo_dimension,
    vvca_score,
    vvca_semaforo,
)
from .traceability import build_trace_record, traceability_bundle

__all__ = [
    "ALCANCE_JURISPRUDENCIA",
    "ALCANCE_JURISPRUDENCIA_SIN_RUBRO",
    "ALCANCE_NORMATIVA",
    "SEMAFORO_SIN_CITAS",
    "alcance_jurisprudencia",
    "clasificar_derogacion",
    "classify_fuerza_vinculante",
    "cotejar_rubro",
    "cotejar_precepto",
    "diferencias_polaridad",
    "disclaimer_graduado",
    "extraer_rubro_invocado",
    "extraer_rubro_posterior",
    "has_exact_article_heading",
    "has_suffixed_variant_heading",
    "normalizar_rubro",
    "normalizar_vigencia",
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
