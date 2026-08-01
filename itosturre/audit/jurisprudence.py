"""Normalización de rubros y clasificación de fuerza vinculante."""
from __future__ import annotations

import re


def rubro_keywords(text: str) -> set[str]:
    """Extrae palabras significativas de un rubro para comparar la cita con el corpus."""
    stop = {
        "para", "como", "ante", "debe", "este", "esta", "dicho", "dicha",
        "donde", "cuando", "aunque", "entre", "sino", "cuyo", "cuya",
        "desde", "hasta", "sobre", "bajo", "cuales", "mismo", "misma",
    }
    return {
        word.lower()
        for word in re.findall(r"[A-Za-záéíóúÁÉÍÓÚüÜñÑ]{5,}", text)
        if word.lower() not in stop
    }


def _fuerza(
    sello: str,
    organo: str,
    obligatoria: bool,
    ambito: str,
    fundamento: str,
) -> dict:
    return {
        "sello": sello,
        "organo": organo,
        "obligatoria": obligatoria,
        "ambito": ambito,
        "fundamento": fundamento,
    }


_ROMANO = r"[IVXLCDM]+"


def classify_fuerza_vinculante(numero_tesis: str, tipo_tesis: str = "") -> dict:
    """Clasifica fuerza vinculante desde la clave, sin afirmar votaciones no verificadas."""
    up = (numero_tesis or "").strip().upper()
    es_jur = bool(re.search(r"/J\.|J/\d", up)) or bool(
        re.search(r"jurisprudencia", tipo_tesis or "", re.I)
    )

    if re.match(r"P\./J\.", up):
        return _fuerza(
            "[J-PLENO]", "Pleno de la SCJN", True, "nacional",
            "art. 217 LA — jurisprudencia obligatoria (Pleno de la SCJN)",
        )
    if re.match(r"[1-4]A\./J\.", up):
        return _fuerza(
            "[J-SALA]", "Sala de la SCJN", True, "nacional",
            "art. 217 LA — jurisprudencia obligatoria (Sala de la SCJN)",
        )
    if re.match(r"PR\.", up):
        return _fuerza(
            "[PR]", "Pleno Regional", True, "regional",
            "Acuerdo General 5/2021 — obligatoria en la región (Pleno Regional)",
        )
    if re.match(r"PC\.", up):
        return _fuerza(
            "[PC]", "Pleno de Circuito", True, "circuito",
            "art. 217 LA — obligatoria en el circuito (Pleno de Circuito)",
        )
    if es_jur:
        return _fuerza(
            "[J-TCC]", "Tribunal Colegiado de Circuito", True, "circuito",
            "art. 217 LA — jurisprudencia de TCC (obligatoria en su circuito)",
        )
    if re.match(r"(?:[1-4]A|P)\.\s*" + _ROMANO + r"\b", up):
        return _fuerza(
            "[SCJN-P]", "SCJN — tesis aislada / posible precedente", False, "orientadora",
            "Tesis aislada de la SCJN — orientadora; verificar si es precedente "
            "obligatorio por mayoría calificada (reforma art. 94 CPEUM 2021)",
        )
    return _fuerza(
        "[TA]", "Tesis aislada", False, "orientadora",
        "Tesis aislada — orientadora, no obligatoria (art. 217 LA a contrario)",
    )

