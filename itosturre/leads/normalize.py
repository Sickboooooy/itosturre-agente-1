"""Normalización conservadora de texto, dominios, estados y teléfonos mexicanos."""
from __future__ import annotations

import re
import unicodedata
from urllib.parse import urlsplit


TRUE_VALUES = {"1", "true", "yes", "y", "si", "sí", "s", "available", "disponible"}
FALSE_VALUES = {"0", "false", "no", "n", "unavailable", "no disponible"}


def normalize_search_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.casefold())
    return " ".join(text.split())


def normalize_state(value: object) -> str:
    text = str(value or "").strip().casefold()
    if text in TRUE_VALUES:
        return "yes"
    if text in FALSE_VALUES:
        return "no"
    return "unknown"


def parse_bool(value: object) -> bool:
    text = str(value or "").strip().casefold()
    return normalize_state(value) == "yes" or text in {"blocked", "bloqueado", "opt_out", "baja"}


def normalize_phone(value: str, default_country_code: str = "52") -> str:
    """Devuelve E.164 cuando el número es inequívoco; en otro caso, cadena vacía.

    Para México admite diez dígitos locales, +52 y el antiguo prefijo móvil +521.
    No intenta completar números cortos o ambiguos.
    """

    digits = re.sub(r"\D", "", value or "")
    country = re.sub(r"\D", "", default_country_code)
    if country == "52":
        if len(digits) == 13 and digits.startswith("521"):
            digits = "52" + digits[3:]
        elif len(digits) == 10:
            digits = "52" + digits
        if len(digits) == 12 and digits.startswith("52"):
            return f"+{digits}"
        return ""
    if digits.startswith(country) and 8 <= len(digits) - len(country) <= 12:
        return f"+{digits}"
    if 8 <= len(digits) <= 12 and country:
        return f"+{country}{digits}"
    return ""


def normalize_domain(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    hostname = (parsed.hostname or "").casefold().rstrip(".")
    if hostname.startswith("www."):
        hostname = hostname[4:]
    return hostname
