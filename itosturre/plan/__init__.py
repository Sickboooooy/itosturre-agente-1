"""Auditor determinista de planes sobre ledger (``plan-ledger/1.0``).

Separado de ``itosturre.audit`` (VVCA): aquí no se consulta corpus, SJF ni LLM. Se
validan reglas observables sobre un ledger de afirmaciones, evidencias,
contradicciones y decisiones, la cobertura de las menciones de un documento y, con un
paquete de evidencia, el cotejo de identidad de cada evidencia citada (``identidad``).
"""

from .estados import (
    APROBADO,
    ESTADOS_VERIFICACION,
    aprobacion_valida,
    contenido_sha256,
    estado_mostrado,
    normalizar_estado,
    problema_persona,
    problemas_aprobacion,
    responsable_no_humano,
)
from .identidad import (
    CONFORME,
    DISCREPANTE,
    ESTADO_SOSTENIBLE,
    NO_COTEJADO,
    SIN_EVIDENCIA,
    CotejoLedger,
    Extractor,
    ResultadoAfirmacion,
    ResultadoPar,
    cotejar_ledger,
    huella_ledger,
)
from .ledger import SCHEMA_VERSION, LedgerInvalido, cargar_ledger, validar_esquema
from .lint import (
    HOSTS_OFICIALES,
    REGLAS,
    REGLAS_COTEJO,
    esta_bloqueado,
    lint_ledger,
    resumen_severidades,
    url_oficial,
)
from .menciones import Mencion, extraer_menciones
from .reporte import reporte_markdown

__all__ = [
    "APROBADO",
    "CONFORME",
    "DISCREPANTE",
    "ESTADOS_VERIFICACION",
    "ESTADO_SOSTENIBLE",
    "HOSTS_OFICIALES",
    "NO_COTEJADO",
    "REGLAS",
    "REGLAS_COTEJO",
    "SCHEMA_VERSION",
    "SIN_EVIDENCIA",
    "CotejoLedger",
    "Extractor",
    "LedgerInvalido",
    "Mencion",
    "ResultadoAfirmacion",
    "ResultadoPar",
    "aprobacion_valida",
    "cargar_ledger",
    "contenido_sha256",
    "cotejar_ledger",
    "huella_ledger",
    "esta_bloqueado",
    "estado_mostrado",
    "extraer_menciones",
    "lint_ledger",
    "normalizar_estado",
    "problema_persona",
    "problemas_aprobacion",
    "reporte_markdown",
    "responsable_no_humano",
    "resumen_severidades",
    "url_oficial",
    "validar_esquema",
]
