"""Pipeline local: ingesta tabular, normalización, supresión y exportación estable."""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .classify import classify_fiscal_lead
from .models import OUTPUT_FIELDS, LeadRecord
from .normalize import normalize_domain, normalize_phone, normalize_search_text, normalize_state, parse_bool


ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("name", "business_name", "nombre", "despacho"),
    "category": ("category", "place_type", "categoria", "categoría", "tipo"),
    "address": ("address", "direccion", "dirección", "domicilio"),
    "website": ("website", "site", "sitio", "pagina_web", "página_web"),
    "phone": ("phone_e164", "phone_number", "phone", "telefono", "teléfono", "celular"),
    "services_text": ("services_text", "services", "servicios", "description", "introduction", "descripcion", "descripción"),
    "source_url": ("source_url", "maps_url", "url", "google_maps_url"),
    "source_record_id": ("source_record_id", "place_id", "google_place_id"),
    "source_query": ("source_query", "search_query", "consulta"),
    "captured_at": ("captured_at", "scraped_at", "fecha_captura"),
    "manual_segment": ("manual_segment", "icp_override", "segmento_manual"),
    "whatsapp_available": ("whatsapp_available", "has_whatsapp", "wa_available", "tiene_whatsapp"),
    "whatsapp_opt_in": ("whatsapp_opt_in", "wa_opt_in", "opt_in", "consentimiento_whatsapp"),
    "public_business_number": ("public_business_number", "numero_empresarial_publico", "tel_publico"),
    "repep_status": ("repep_status", "estado_repep"),
    "mexican_law_status": ("mexican_law_status", "estado_legal_mx"),
    "do_not_contact": ("do_not_contact", "dnc", "no_contactar", "bloqueado"),
    "dnc_reason": ("dnc_reason", "motivo_baja", "motivo_no_contactar"),
    "dnc_at": ("dnc_at", "fecha_baja", "fecha_no_contactar"),
}


@dataclass(frozen=True)
class PipelineSummary:
    input_rows: int
    output_rows: int
    invalid_rows: int
    duplicates_merged: int
    do_not_contact: int
    fiscal_priority: int
    permission_required: int
    eligible_for_human_review: int
    manual_contact_candidates: int

    def to_dict(self) -> dict[str, int]:
        return {
            "input_rows": self.input_rows,
            "output_rows": self.output_rows,
            "invalid_rows": self.invalid_rows,
            "duplicates_merged": self.duplicates_merged,
            "do_not_contact": self.do_not_contact,
            "fiscal_priority": self.fiscal_priority,
            "permission_required": self.permission_required,
            "eligible_for_human_review": self.eligible_for_human_review,
            "manual_contact_candidates": self.manual_contact_candidates,
        }


class SuppressionIndex:
    def __init__(self) -> None:
        self.phones: dict[str, tuple[str, str]] = {}
        self.domains: dict[str, tuple[str, str]] = {}

    def add(self, row: Mapping[str, object], default_country_code: str) -> None:
        normalized = _normalized_row(row)
        phone = normalize_phone(_pick(normalized, *ALIASES["phone"]), default_country_code)
        website = _pick(normalized, *ALIASES["website"], "domain", "dominio")
        domain = normalize_domain(website)
        reason = _pick(normalized, *ALIASES["dnc_reason"], "reason", "motivo") or "Lista de exclusión"
        recorded_at = _pick(normalized, *ALIASES["dnc_at"], "recorded_at", "fecha")
        if phone:
            self.phones[phone] = (reason, recorded_at)
        if domain:
            self.domains[domain] = (reason, recorded_at)

    def match(self, record: LeadRecord) -> tuple[str, str] | None:
        if record.phone_e164 and record.phone_e164 in self.phones:
            return self.phones[record.phone_e164]
        if record.website_domain and record.website_domain in self.domains:
            return self.domains[record.website_domain]
        return None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        return []
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [dict(row) for row in csv.DictReader(text.splitlines(), dialect=dialect)]


def prepare_leads(
    rows: Iterable[Mapping[str, object]],
    *,
    suppression_rows: Iterable[Mapping[str, object]] = (),
    source_type: str = "manual_import",
    source_query: str = "",
    default_country_code: str = "52",
    captured_at: str | None = None,
) -> tuple[list[LeadRecord], PipelineSummary]:
    suppression = SuppressionIndex()
    for row in suppression_rows:
        suppression.add(row, default_country_code)

    timestamp = captured_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    records_by_key: dict[str, LeadRecord] = {}
    input_count = 0
    valid_count = 0
    for row in rows:
        input_count += 1
        record = _build_record(
            row,
            source_type=source_type,
            source_query=source_query,
            default_country_code=default_country_code,
            captured_at=timestamp,
        )
        if not record.name and not record.source_record_id:
            continue
        valid_count += 1
        key = _dedupe_key(record)
        if key in records_by_key:
            record = _merge_records(records_by_key[key], record)
        records_by_key[key] = record

    records = []
    for record in records_by_key.values():
        match = suppression.match(record)
        if match:
            record.do_not_contact = True
            record.dnc_reason, record.dnc_at = match
        _finalize(record)
        records.append(record)
    records.sort(key=lambda item: (-item.icp_score, normalize_search_text(item.name), item.record_id))

    summary = PipelineSummary(
        input_rows=input_count,
        output_rows=len(records),
        invalid_rows=input_count - valid_count,
        duplicates_merged=valid_count - len(records),
        do_not_contact=sum(record.do_not_contact for record in records),
        fiscal_priority=sum(record.icp_segment == "fiscal_prioritario" for record in records),
        permission_required=sum(record.contact_status == "permission_required" for record in records),
        eligible_for_human_review=sum(record.contact_eligible for record in records),
        manual_contact_candidates=sum(record.manual_contact_candidate for record in records),
    )
    return records, summary


def write_csv(records: Iterable[LeadRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(record.to_dict())


def _normalized_row(row: Mapping[str, object]) -> dict[str, object]:
    return {str(key).strip().casefold(): value for key, value in row.items() if key is not None}


def _pick(row: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = row.get(key.casefold())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _build_record(
    row: Mapping[str, object],
    *,
    source_type: str,
    source_query: str,
    default_country_code: str,
    captured_at: str,
) -> LeadRecord:
    data = _normalized_row(row)
    phone_raw = _pick(data, *ALIASES["phone"])
    website = _pick(data, *ALIASES["website"])
    record = LeadRecord(
        source_type=source_type,
        source_query=_pick(data, *ALIASES["source_query"]) or source_query,
        source_url=_pick(data, *ALIASES["source_url"]),
        source_record_id=_pick(data, *ALIASES["source_record_id"]),
        captured_at=_pick(data, *ALIASES["captured_at"]) or captured_at,
        name=_pick(data, *ALIASES["name"]),
        category=_pick(data, *ALIASES["category"]),
        address=_pick(data, *ALIASES["address"]),
        website=website,
        website_domain=normalize_domain(website),
        phone_raw=phone_raw,
        phone_e164=normalize_phone(phone_raw, default_country_code),
        public_business_number=normalize_state(_pick(data, *ALIASES["public_business_number"])),
        services_text=_pick(data, *ALIASES["services_text"]),
        manual_segment=_pick(data, *ALIASES["manual_segment"]),
        whatsapp_available=normalize_state(_pick(data, *ALIASES["whatsapp_available"])),
        whatsapp_opt_in=normalize_state(_pick(data, *ALIASES["whatsapp_opt_in"])),
        repep_status=_pick(data, *ALIASES["repep_status"]) or "unchecked",
        mexican_law_status=_pick(data, *ALIASES["mexican_law_status"]) or "not_assessed",
        do_not_contact=parse_bool(_pick(data, *ALIASES["do_not_contact"])),
        dnc_reason=_pick(data, *ALIASES["dnc_reason"]),
        dnc_at=_pick(data, *ALIASES["dnc_at"]),
    )
    record.record_id = _record_id(record)
    return record


def _identity_parts(record: LeadRecord) -> list[str]:
    if record.source_record_id:
        return ["source", record.source_type, record.source_record_id]
    name = normalize_search_text(record.name)
    if record.phone_e164:
        return ["name_phone", name, record.phone_e164]
    if record.website_domain:
        return ["name_domain", name, record.website_domain]
    return ["name_address", name, normalize_search_text(record.address)]


def _record_id(record: LeadRecord) -> str:
    raw = "|".join(_identity_parts(record))
    return "lead_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _dedupe_key(record: LeadRecord) -> str:
    return "|".join(_identity_parts(record))


def _merge_state(first: str, second: str) -> str:
    if "no" in (first, second):
        return "no"
    if "yes" in (first, second):
        return "yes"
    return "unknown"


def _merge_records(first: LeadRecord, second: LeadRecord) -> LeadRecord:
    for field in (
        "source_query", "source_url", "source_record_id", "name", "category", "address",
        "website", "website_domain", "phone_raw", "phone_e164", "services_text", "manual_segment",
        "repep_status", "mexican_law_status",
    ):
        if not getattr(first, field) and getattr(second, field):
            setattr(first, field, getattr(second, field))
    first.whatsapp_available = _merge_state(first.whatsapp_available, second.whatsapp_available)
    first.whatsapp_opt_in = _merge_state(first.whatsapp_opt_in, second.whatsapp_opt_in)
    first.public_business_number = _merge_state(first.public_business_number, second.public_business_number)
    if second.do_not_contact:
        first.do_not_contact = True
        first.dnc_reason = second.dnc_reason or first.dnc_reason
        first.dnc_at = second.dnc_at or first.dnc_at
    return first


def _finalize(record: LeadRecord) -> None:
    qualification = classify_fiscal_lead(
        name=record.name,
        category=record.category,
        services_text=record.services_text,
        manual_segment=record.manual_segment,
    )
    record.icp_segment = qualification.segment
    record.icp_score = qualification.score
    record.icp_positive_evidence = json.dumps(qualification.positive_evidence, ensure_ascii=False)
    record.icp_negative_evidence = json.dumps(qualification.negative_evidence, ensure_ascii=False)

    if record.whatsapp_opt_in == "yes":
        record.wa_policy_status = "opt_in_recorded"
    elif record.whatsapp_opt_in == "no" or record.do_not_contact:
        record.wa_policy_status = "opt_out_or_dnc"
    elif record.whatsapp_available == "yes":
        record.wa_policy_status = "opt_in_missing"
    else:
        record.wa_policy_status = "channel_unverified"

    record.manual_contact_candidate = bool(
        record.phone_e164
        and record.public_business_number == "yes"
        and record.whatsapp_available == "yes"
        and record.icp_segment in {"fiscal_prioritario", "fiscal_posible"}
        and not record.do_not_contact
        and record.whatsapp_opt_in != "no"
    )

    if record.do_not_contact or record.whatsapp_opt_in == "no":
        record.do_not_contact = True
        record.contact_status = "do_not_contact"
        record.contact_eligible = False
        record.eligibility_reason = record.dnc_reason or "Baja, bloqueo o negativa registrada."
    elif record.icp_segment == "no_objetivo":
        record.contact_status = "not_icp"
        record.contact_eligible = False
        record.eligibility_reason = "El perfil no corresponde al segmento fiscal objetivo."
    elif record.icp_segment not in {"fiscal_prioritario", "fiscal_posible"}:
        record.contact_status = "qualification_required"
        record.contact_eligible = False
        record.eligibility_reason = "Falta evidencia suficiente de práctica fiscal."
    elif record.whatsapp_opt_in != "yes":
        record.contact_status = "permission_required"
        record.contact_eligible = False
        record.eligibility_reason = "No existe consentimiento verificable para WhatsApp."
    elif record.whatsapp_available != "yes":
        record.contact_status = "channel_unverified"
        record.contact_eligible = False
        record.eligibility_reason = "El canal de WhatsApp no está confirmado."
    else:
        record.contact_status = "ready_for_human_review"
        record.contact_eligible = True
        record.eligibility_reason = "ICP, canal y consentimiento confirmados; requiere aprobación humana."
