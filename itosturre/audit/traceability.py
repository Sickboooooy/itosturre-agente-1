"""Trazabilidad estructurada y reproducible para verificaciones VVCA.

Las funciones de este módulo son puras salvo por la fecha UTC predeterminada. No leen el
corpus ni realizan llamadas de red: convierten el resultado de una verificación en un
registro uniforme que pueda revisarse y conservarse junto con el expediente.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Iterable


TRACE_SCHEMA_VERSION = "1.0"
TRACE_STATUSES = {"verified", "partial", "not_verifiable", "refuted"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _digest(text: str | None) -> str | None:
    if not text:
        return None
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def build_trace_record(
    *,
    reference: str,
    ref_type: str,
    status: str,
    method: str,
    reason: str,
    score: float | int | None = None,
    semaforo: str | None = None,
    source_file: str | None = None,
    source_url: str | None = None,
    locator: str | int | None = None,
    evidence_text: str | None = None,
    metadata: dict[str, Any] | None = None,
    checked_at: str | None = None,
) -> dict[str, Any]:
    """Construye una traza VVCA con identificador estable y evidencia verificable.

    ``trace_id`` no depende de la fecha: el mismo hallazgo produce el mismo identificador.
    El hash de evidencia permite detectar cambios sin duplicar el texto completo en la
    traza; el fragmento continúa disponible en ``retrieved_sources`` cuando corresponda.
    """
    if status not in TRACE_STATUSES:
        raise ValueError(f"Estado de trazabilidad no soportado: {status}")
    if not reference.strip():
        raise ValueError("La referencia no puede estar vacía")
    if not method.strip():
        raise ValueError("El método de obtención no puede estar vacío")

    evidence_sha256 = _digest(evidence_text)
    identity = {
        "reference": reference,
        "ref_type": ref_type,
        "status": status,
        "method": method,
        "source_file": source_file,
        "source_url": source_url,
        "locator": str(locator) if locator is not None else None,
        "evidence_sha256": evidence_sha256,
    }
    trace_id = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:20]

    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_id": trace_id,
        "claim": {
            "reference": reference,
            "type": ref_type,
        },
        "source": {
            "file": source_file,
            "url": source_url,
            "locator": str(locator) if locator is not None else None,
        },
        "retrieval": {
            "method": method,
            "checked_at": checked_at or _utc_now(),
        },
        "verification": {
            "status": status,
            "score": score,
            "semaforo": semaforo,
            "reason": reason,
            "evidence_sha256": evidence_sha256,
        },
        "metadata": metadata or {},
        # La automatización cubre Capa 1; cualquier producto jurídico exige Capa 2.
        "human_review_required": True,
    }


def traceability_bundle(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Agrupa trazas y resume su estado sin convertir ausencia de fuente en refutación."""
    materialized = list(records)
    counts = {status: 0 for status in sorted(TRACE_STATUSES)}
    for record in materialized:
        status = record.get("verification", {}).get("status")
        if status in counts:
            counts[status] += 1
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "records": materialized,
        "summary": {
            "total": len(materialized),
            "by_status": counts,
            "human_review_required": bool(materialized),
        },
    }
