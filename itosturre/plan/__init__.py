"""Auditor determinista de planes sobre ledger (``plan-ledger/1.0``).

Separado de ``itosturre.audit`` (VVCA): aquí no se consulta corpus, SJF ni LLM. Se
validan reglas observables sobre un ledger de afirmaciones, evidencias,
contradicciones y decisiones, y la cobertura de las menciones de un documento.
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
from .ledger import SCHEMA_VERSION, LedgerInvalido, cargar_ledger, validar_esquema
from .lint import (
    HOSTS_OFICIALES,
    REGLAS,
    esta_bloqueado,
    lint_ledger,
    resumen_severidades,
    url_oficial,
)
from .menciones import Mencion, extraer_menciones
from .reporte import reporte_markdown

__all__ = [
    "APROBADO",
    "ESTADOS_VERIFICACION",
    "HOSTS_OFICIALES",
    "REGLAS",
    "SCHEMA_VERSION",
    "LedgerInvalido",
    "Mencion",
    "aprobacion_valida",
    "cargar_ledger",
    "contenido_sha256",
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
