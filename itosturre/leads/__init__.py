"""Preparación local y responsable de prospectos B2B.

El paquete transforma fuentes tabulares ya obtenidas legítimamente. No recolecta datos
desde portales ni envía comunicaciones.
"""

from .classify import Qualification, classify_fiscal_lead
from .models import OUTPUT_FIELDS, SCHEMA_VERSION, LeadRecord
from .pipeline import PipelineSummary, prepare_leads

__all__ = [
    "LeadRecord",
    "OUTPUT_FIELDS",
    "PipelineSummary",
    "Qualification",
    "SCHEMA_VERSION",
    "classify_fiscal_lead",
    "prepare_leads",
]
