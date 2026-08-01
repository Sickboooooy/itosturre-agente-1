"""Clasificación explicable del perfil fiscal ideal (ICP)."""
from __future__ import annotations

from dataclasses import dataclass

from .normalize import normalize_search_text


POSITIVE_RULES: tuple[tuple[str, int], ...] = (
    ("defensa fiscal", 70),
    ("litigio fiscal", 70),
    ("abogado fiscal", 60),
    ("derecho fiscal", 60),
    ("69 b", 60),
    ("tributario", 55),
    ("materialidad", 40),
    ("impuestos", 35),
    ("sat", 35),
    ("fiscal", 30),
    ("auditoria", 20),
    ("contador", 20),
    ("contable", 20),
)

NEGATIVE_RULES: tuple[tuple[str, int], ...] = (
    ("no llevo fiscal", 100),
    ("no llevamos fiscal", 100),
    ("no maneja fiscal", 100),
    ("defensor de oficio", 80),
    ("dependencia publica", 70),
    ("derecho familiar", 45),
    ("divorcio", 45),
    ("inmobiliario", 40),
    ("inquilinos", 40),
    ("derecho laboral", 40),
    ("abogado laboral", 40),
    ("derecho penal", 35),
    ("abogado penal", 35),
    ("migratorio", 35),
    ("patentes", 30),
)

ALLOWED_MANUAL_SEGMENTS = {
    "fiscal_prioritario",
    "fiscal_posible",
    "revision_manual",
    "no_objetivo",
}


@dataclass(frozen=True)
class Qualification:
    segment: str
    score: int
    positive_evidence: tuple[str, ...]
    negative_evidence: tuple[str, ...]


def classify_fiscal_lead(
    *,
    name: str,
    category: str = "",
    services_text: str = "",
    manual_segment: str = "",
) -> Qualification:
    haystack = normalize_search_text(" ".join((name, category, services_text)))
    positives = tuple(term for term, _ in POSITIVE_RULES if term in haystack)
    negatives = tuple(term for term, _ in NEGATIVE_RULES if term in haystack)
    positive_score = sum(weight for term, weight in POSITIVE_RULES if term in haystack)
    negative_score = sum(weight for term, weight in NEGATIVE_RULES if term in haystack)
    score = max(0, min(100, positive_score - negative_score))

    override = normalize_search_text(manual_segment).replace(" ", "_")
    if override in ALLOWED_MANUAL_SEGMENTS:
        segment = override
    elif positives and score >= 55:
        segment = "fiscal_prioritario"
    elif positives and score >= 30:
        segment = "fiscal_posible"
    elif negatives:
        segment = "no_objetivo"
    else:
        segment = "revision_manual"

    return Qualification(segment, score, positives, negatives)
