"""Contrato de datos para collectors de fuentes jurídicas primarias (DOF, SAT, SJF).

Por qué existe: los watchers (`agentes/vigilancia_dof.py`,
`agentes/vigilancia_jurisprudencial.py`) y el generador de contenido
(`agentes/contenido_linkedin.py`) necesitan distinguir, de forma máquina-legible,
"consultamos la fuente y no había novedades" de "no pudimos consultar la fuente".
Confundir ambos casos es exactamente el error que el protocolo anti-alucinación
de Itosturre prohíbe (CLAUDE.md, Regla 4 y Regla 7): un silencio no verificado no
es lo mismo que una ausencia verificada.

Este módulo NUNCA decide si un dato jurídico es correcto — solo transporta el
estado de la consulta. La verificación de citas sigue viviendo en OpenNotebook.py
(corpus RAG) y en vigilancia_jurisprudencial.py (API pública del SJF).
"""
from __future__ import annotations

import json
import os
import platform
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from itosturre.vigilancia.rutina import salida_dir, validar_salida

# ── Estados mínimos del contrato (item 4 del encargo de reparación) ───────────

SUCCESS = "SUCCESS"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
AUTH_REQUIRED = "AUTH_REQUIRED"
PARSER_ERROR = "PARSER_ERROR"
VALIDATION_FAILED = "VALIDATION_FAILED"
TIMEOUT = "TIMEOUT"
UNKNOWN_ERROR = "UNKNOWN_ERROR"

ESTADOS_VALIDOS = {
    SUCCESS,
    SOURCE_UNAVAILABLE,
    AUTH_REQUIRED,
    PARSER_ERROR,
    VALIDATION_FAILED,
    TIMEOUT,
    UNKNOWN_ERROR,
}


def _entorno_ejecucion() -> str:
    """Identificador best-effort de dónde corrió el collector.

    Se puede fijar explícitamente con ITOSTURRE_EXEC_ENV (recomendado en el
    entorno del operador vs. un entorno cloud efímero) para que quede trazable
    en qué máquina se intentó la consulta.
    """
    return os.environ.get("ITOSTURRE_EXEC_ENV") or f"{platform.system()}/{platform.node()}"


@dataclass
class ResultadoFuente:
    """Resultado de UN collector para UNA fuente (DOF, SAT, o un tema del SJF).

    Regla dura: cuando `status` no es SUCCESS, `items` queda vacío. Nunca se
    completa con inferencia ni con el último resultado bueno conocido — eso
    sería fabricar la apariencia de una consulta que no ocurrió.
    """

    source: str
    status: str
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    items: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    execution_environment: str = field(default_factory=_entorno_ejecucion)
    retryable: bool = False

    def __post_init__(self) -> None:
        if self.status not in ESTADOS_VALIDOS:
            raise ValueError(f"status inválido: {self.status!r} (usar uno de {sorted(ESTADOS_VALIDOS)})")
        if self.status != SUCCESS and self.items:
            raise ValueError(
                f"ResultadoFuente inconsistente: status={self.status!r} pero items no está vacío "
                "(un estado que no es SUCCESS nunca lleva hallazgos)"
            )

    @property
    def ok(self) -> bool:
        return self.status == SUCCESS

    def to_dict(self) -> dict:
        return asdict(self)

    def resumen(self) -> dict:
        """Estado de la fuente sin los hallazgos, para el estado de la corrida."""
        return {
            "status": self.status,
            "retryable": self.retryable,
            "errors": list(self.errors),
            "n_items": len(self.items),
            "retrieved_at": self.retrieved_at,
            "execution_environment": self.execution_environment,
        }


def es_bloqueo_politica(exc: BaseException) -> bool:
    """True si la excepción delata el bloqueo de política de egress del entorno:
    un ProxyError, o un ConnectionError cuyo mensaje muestra el rechazo del
    CONNECT (403) por el proxy. Un timeout nunca lo es, aunque mencione el
    proxy (ConnectTimeout hereda de ConnectionError y de Timeout)."""
    import requests

    if isinstance(exc, requests.exceptions.Timeout):
        return False
    if isinstance(exc, requests.exceptions.ProxyError):
        return True
    return isinstance(exc, requests.exceptions.ConnectionError) and any(
        s in str(exc).lower() for s in ("403", "proxy", "connect_rejected", "policy")
    )


def clasificar_excepcion_red(exc: Exception) -> tuple[str, bool, str]:
    """Clasifica una excepción de red en (status, retryable, mensaje).

    Distingue el caso documentado del bloqueo de política de egress del entorno
    (visible como un ProxyError, o un ConnectionError cuyo mensaje delata un
    rechazo de CONNECT/403 del proxy) de una falla transitoria genuina:

    - Timeout -> TIMEOUT, retryable=True (se evalúa primero: un timeout hacia
      el proxy es transitorio, no un bloqueo).
    - Bloqueo de política (es_bloqueo_politica) -> SOURCE_UNAVAILABLE,
      retryable=False. Reintentar en el MISMO entorno nunca lo resuelve: hace
      falta autorizar el dominio en la política de red del entorno o correr el
      collector donde exista acceso autorizado (ver docs/VIGILANCIA_LEGAL.md).
    - Cualquier otro error de requests -> SOURCE_UNAVAILABLE, retryable=True
      (conservador: puede ser transitorio, no se asume bloqueo de política sin
      evidencia).
    """
    import requests

    texto = str(exc)
    if isinstance(exc, requests.exceptions.Timeout):
        return TIMEOUT, True, f"Timeout de conexión: {texto}"
    if es_bloqueo_politica(exc):
        return (
            SOURCE_UNAVAILABLE,
            False,
            "Bloqueo de política de red del entorno de ejecución (egress denegado a la "
            "fuente). No reintentar en este mismo entorno: autorizar el dominio en la "
            "política de red del entorno o ejecutar el collector donde exista acceso "
            "autorizado (ver docs/VIGILANCIA_LEGAL.md). Detalle: " + texto,
        )
    if isinstance(exc, requests.exceptions.RequestException):
        return SOURCE_UNAVAILABLE, True, f"Error de red: {texto}"
    return UNKNOWN_ERROR, True, f"Error no clasificado: {texto}"


# ── Persistencia del contrato (sidecar JSON junto al .md legible) ─────────────


def _a_dict(resultados: Any) -> Any:
    if isinstance(resultados, ResultadoFuente):
        return resultados.to_dict()
    if isinstance(resultados, dict):
        return {k: _a_dict(v) for k, v in resultados.items()}
    if isinstance(resultados, list):
        return [_a_dict(v) for v in resultados]
    return resultados


def guardar_sidecar(ruta_md: Path, resultados: Any) -> Path:
    """Guarda el contrato crudo (JSON) junto al .md legible, mismo nombre + .json.

    `contenido_linkedin.py` (y cualquier consumidor automatizado) lee este JSON
    para decidir si hay hallazgo validado — nunca debe re-derivar el estado
    parseando el Markdown escrito para humanos.
    """
    ruta_json = ruta_md.with_suffix(".json")
    ruta_json.write_text(
        json.dumps(_a_dict(resultados), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return ruta_json


def leer_sidecar(ruta_json: Path) -> Any:
    """Lee un sidecar de contrato. Devuelve None si no existe o es ilegible
    (nunca se sustituye por un valor inventado)."""
    try:
        return json.loads(ruta_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ── Observabilidad (item 11 del encargo) ───────────────────────────────────────

# Junto a las salidas de las rutinas ($ITOSTURRE_SALIDA o salidas/), nunca
# dentro del paquete: <repo>/Itosturre/ ES itosturre/ en macOS y Windows.
EVENTOS_LOG = salida_dir() / "eventos.jsonl"

EVENTOS_VALIDOS = {
    "watch_started",
    "collector_started",
    "source_requested",
    "source_success",
    "source_unavailable",
    "validation_started",
    "validation_passed",
    "validation_failed",
    "draft_generated",
    "draft_blocked",
}


def registrar_evento(evento: str, **datos: Any) -> None:
    """Anexa un evento JSONL a EVENTOS_LOG (salidas/eventos.jsonl) para diagnóstico.

    Nunca recibe ni escribe secretos/credenciales — solo identificadores de
    fuente, estado y metadatos operativos (ver docs/VIGILANCIA_LEGAL.md).
    """
    if evento not in EVENTOS_VALIDOS:
        raise ValueError(f"evento no reconocido: {evento!r} (usar uno de {sorted(EVENTOS_VALIDOS)})")
    validar_salida(EVENTOS_LOG.parent)
    EVENTOS_LOG.parent.mkdir(parents=True, exist_ok=True)
    registro = {"ts": datetime.now(timezone.utc).isoformat(), "evento": evento, **datos}
    with EVENTOS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
