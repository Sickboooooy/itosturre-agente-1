"""Contrato de datos estable para el pipeline de prospectos."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


SCHEMA_VERSION = "1.1"


@dataclass
class LeadRecord:
    """Registro normalizado; todos los campos se exportan en cada ejecución."""

    schema_version: str = SCHEMA_VERSION
    record_id: str = ""
    source_type: str = "manual_import"
    source_query: str = ""
    source_url: str = ""
    source_record_id: str = ""
    captured_at: str = ""
    name: str = ""
    category: str = ""
    address: str = ""
    website: str = ""
    website_domain: str = ""
    phone_raw: str = ""
    phone_e164: str = ""
    public_business_number: str = "unknown"
    services_text: str = ""
    manual_segment: str = ""
    icp_segment: str = "revision_manual"
    icp_score: int = 0
    icp_positive_evidence: str = "[]"
    icp_negative_evidence: str = "[]"
    whatsapp_available: str = "unknown"
    whatsapp_opt_in: str = "unknown"
    wa_policy_status: str = "not_assessed"
    repep_status: str = "unchecked"
    mexican_law_status: str = "not_assessed"
    do_not_contact: bool = False
    dnc_reason: str = ""
    dnc_at: str = ""
    contact_status: str = "permission_required"
    contact_eligible: bool = False
    manual_contact_candidate: bool = False
    eligibility_reason: str = "No existe consentimiento verificable."

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


OUTPUT_FIELDS = list(LeadRecord.__dataclass_fields__)
