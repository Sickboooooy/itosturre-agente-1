"""Contrato de datos y observabilidad compartidos por los watchers de fuentes
jurídicas (DOF, SAT, SJF) y por el generador de contenido que consume sus
resultados.

Ver docs/VIGILANCIA_LEGAL.md — Legal Data Availability Contract.
"""
from itosturre.vigilancia.contrato import (
    AUTH_REQUIRED,
    ESTADOS_VALIDOS,
    PARSER_ERROR,
    SOURCE_UNAVAILABLE,
    SUCCESS,
    TIMEOUT,
    UNKNOWN_ERROR,
    VALIDATION_FAILED,
    ResultadoFuente,
    clasificar_excepcion_red,
    guardar_sidecar,
    leer_sidecar,
    registrar_evento,
)

__all__ = [
    "SUCCESS",
    "SOURCE_UNAVAILABLE",
    "AUTH_REQUIRED",
    "PARSER_ERROR",
    "VALIDATION_FAILED",
    "TIMEOUT",
    "UNKNOWN_ERROR",
    "ESTADOS_VALIDOS",
    "ResultadoFuente",
    "clasificar_excepcion_red",
    "registrar_evento",
    "guardar_sidecar",
    "leer_sidecar",
]
