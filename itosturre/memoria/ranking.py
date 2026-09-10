"""Puntuación, taxonomía y presupuesto de contexto. Módulo puro y sin E/S.

La fórmula (informe §3.4) es deliberadamente aritmética y auditable:

    score = bm25_norm(consulta)
          × peso_importancia[importance]
          × decaimiento_recencia(timestamp)
          + bono_tipo[event_type]

Nada aquí "aprende" ni se ajusta solo. En un sistema cuyo veredicto puede
decidir si se presenta un escrito, un ranking que no se pueda explicar frente al
abogado no sirve, por bueno que sea su promedio.

Dos decisiones que se apartan de lo habitual en herramientas de código:

* **El decaimiento tiene suelo (0.3), no llega a cero.** Una corrección de
  criterio del PJF de hace un año sigue siendo derecho vigente. Aquí la recencia
  informa, no manda — al contrario que en un repositorio de software, donde lo
  viejo suele estar muerto.
* **El recorte es por bytes, no por número de filas.** El contrato con el modelo
  es un techo de contexto, y un techo en filas no lo garantiza: diez eventos
  largos pesan más que treinta cortos.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

#: Presupuesto por defecto del bloque que se entrega al modelo.
PRESUPUESTO_BYTES = 4096

#: Semivida del decaimiento por recencia, en días.
SEMIVIDA_DIAS = 30.0

#: Suelo del decaimiento: lo antiguo pierde peso, nunca lo pierde todo.
SUELO_RECENCIA = 0.3

#: Peso por nivel de importancia (1 = crítico … 4 = rutina).
PESO_IMPORTANCIA: Mapping[int, float] = {1: 1.5, 2: 1.2, 3: 1.0, 4: 0.7}


class Tipo:
    """Taxonomía de eventos (informe §3.3).

    ``bono`` implementa el orden de prioridad que pide la Fase 5 del encargo:
    decisiones arquitectónicas y correcciones de criterio primero; después
    instrucciones del usuario, tareas abiertas, archivos tocados, errores y
    soluciones previas.

    ``importancia`` es solo el valor por defecto cuando quien registra no opina.
    """

    __slots__ = ("nombre", "bono", "importancia", "descripcion")

    def __init__(self, nombre: str, bono: float, importancia: int, descripcion: str) -> None:
        self.nombre = nombre
        self.bono = bono
        self.importancia = importancia
        self.descripcion = descripcion


def _t(nombre: str, bono: float, importancia: int, descripcion: str) -> tuple[str, Tipo]:
    return nombre, Tipo(nombre, bono, importancia, descripcion)


TIPOS: Mapping[str, Tipo] = dict(
    (
        # ── Criterio jurídico: el activo más valioso del sistema ──
        _t("correccion_criterio_pjf", 0.35, 1,
           "Corrección de criterio del operador jurídico (regla absoluta #6)"),
        _t("alerta_procesal", 0.32, 1,
           "Riesgo de pérdida de instancia, nulidad o prescripción (regla #7)"),
        _t("cita_bloqueada", 0.30, 1,
           "Cita 🔴 por rubro discrepante: bloquea el documento (regla #2)"),
        _t("plazo_detectado", 0.30, 1, "Plazo procesal con fecha límite"),
        _t("corpus_gap", 0.12, 3, "Ordenamiento citado y ausente del índice (regla 7)"),
        _t("vvca_veredicto", 0.10, 2, "Veredicto de una auditoría VVCA"),
        # ── Decisiones e instrucciones ──
        _t("architecture_decision", 0.30, 1, "Decisión de arquitectura y su porqué"),
        _t("user_correction", 0.25, 1, "El usuario corrigió un enfoque o resultado"),
        _t("user_decision", 0.22, 2, "El usuario eligió entre alternativas"),
        _t("important_context", 0.15, 2, "Contexto que no se deduce del código"),
        # ── Estado de trabajo ──
        _t("task_started", 0.18, 2, "Tarea iniciada (pendiente hasta que se cierre)"),
        _t("task_completed", 0.05, 3, "Tarea terminada"),
        # ── Fallos y sus soluciones ──
        _t("error_detected", 0.15, 2, "Error detectado"),
        _t("error_resolved", 0.15, 2, "Error resuelto y cómo"),
        _t("test_failed", 0.12, 2, "Prueba en rojo"),
        # ── Cambios materiales ──
        _t("dependency_changed", 0.10, 2, "Dependencia añadida, quitada o versionada"),
        _t("configuration_changed", 0.10, 2, "Cambio de configuración"),
        _t("file_modified", 0.08, 3, "Archivo creado, modificado o borrado"),
        _t("git_commit", 0.06, 3, "Commit"),
        _t("git_branch", 0.04, 3, "Rama creada o cambiada"),
        # ── Continuidad ──
        _t("session_snapshot", 0.0, 3, "Instantánea de continuidad de sesión"),
    )
)

#: Alias hacia la taxonomía canónica. `test_passed` solo se conserva cuando
#: cierra un fallo previo: registrar cada prueba verde contamina el índice con
#: lo que nunca se consulta.
ALIAS: Mapping[str, str] = {
    "file_created": "file_modified",
    "file_deleted": "file_modified",
    "file_write": "file_modified",
    "test_passed": "error_resolved",
    "decision": "user_decision",
    "correction": "user_correction",
}


def canonizar(event_type: str) -> str:
    """Normaliza un tipo a la taxonomía canónica. Los desconocidos se conservan."""
    limpio = (event_type or "").strip().lower()
    return ALIAS.get(limpio, limpio)


def tipo_valido(event_type: str) -> bool:
    return canonizar(event_type) in TIPOS


def importancia_por_defecto(event_type: str) -> int:
    tipo = TIPOS.get(canonizar(event_type))
    return tipo.importancia if tipo else 3


def bono_tipo(event_type: str) -> float:
    tipo = TIPOS.get(canonizar(event_type))
    return tipo.bono if tipo else 0.0


def peso_importancia(importance: int | None) -> float:
    return PESO_IMPORTANCIA.get(int(importance or 3), 1.0)


# ─────────────────────────────────────────
# Recencia
# ─────────────────────────────────────────

def _a_datetime(valor: str | datetime | None) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not valor:
        return None
    texto = str(valor).strip().replace(" ", "T")
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        fecha = datetime.fromisoformat(texto)
    except ValueError:
        return None
    return fecha if fecha.tzinfo else fecha.replace(tzinfo=timezone.utc)


def decaimiento_recencia(
    timestamp: str | datetime | None,
    ahora: datetime | None = None,
    *,
    semivida_dias: float = SEMIVIDA_DIAS,
    suelo: float = SUELO_RECENCIA,
) -> float:
    """Factor en ``[suelo, 1.0]`` según la antigüedad del evento.

    Una marca de tiempo ilegible devuelve el suelo en vez de reventar: un evento
    con fecha corrupta debe poder recuperarse, solo que sin premio por reciente.
    """
    fecha = _a_datetime(timestamp)
    if fecha is None:
        return suelo
    referencia = ahora or datetime.now(timezone.utc)
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=timezone.utc)
    dias = (referencia - fecha).total_seconds() / 86400.0
    if dias <= 0:
        return 1.0
    return max(suelo, 0.5 ** (dias / semivida_dias))


# ─────────────────────────────────────────
# BM25
# ─────────────────────────────────────────

def normalizar_bm25(brutos: Sequence[float]) -> list[float]:
    """Lleva las puntuaciones BM25 de SQLite a ``[0, 1]``, mayor es mejor.

    ``bm25()`` de FTS5 devuelve valores negativos donde más negativo es mejor
    match. Se invierte el signo y se divide por el máximo del conjunto de
    candidatos: normalizar dentro del conjunto mantiene comparables consultas de
    longitudes muy distintas, que es lo que ocurre al mezclar "art. 294" con una
    pregunta en prosa.
    """
    if not brutos:
        return []
    invertidos = [-float(b) for b in brutos]
    techo = max(invertidos)
    if techo <= 0:
        return [1.0 for _ in invertidos]
    return [max(0.0, v / techo) for v in invertidos]


def puntuar(
    *,
    bm25_norm: float,
    event_type: str,
    importance: int | None,
    timestamp: str | datetime | None,
    ahora: datetime | None = None,
) -> float:
    """Combina los cuatro factores en la puntuación final."""
    return (
        bm25_norm
        * peso_importancia(importance)
        * decaimiento_recencia(timestamp, ahora)
        + bono_tipo(event_type)
    )


# ─────────────────────────────────────────
# Formato y presupuesto
# ─────────────────────────────────────────

def formato_evento(evento: Mapping[str, Any], *, con_detalles: bool = False) -> str:
    """Una línea compacta por evento, pensada para que la lea el modelo.

    Se emite la fecha en día (no al segundo: la hora casi nunca aporta y cuesta
    bytes), el tipo, el resumen y, si existe, la ruta. Los detalles quedan fuera
    salvo petición expresa — están en la base para quien los pida, que es todo el
    punto de "memoria grande, contexto pequeño".
    """
    fecha = str(evento.get("timestamp") or "")[:10]
    tipo = evento.get("event_type") or "?"
    resumen = " ".join(str(evento.get("summary") or "").split())
    linea = f"[{fecha}] {tipo}: {resumen}"
    ruta = evento.get("file_path")
    if ruta:
        linea += f" ({ruta})"
    if con_detalles and evento.get("details"):
        detalles = " ".join(str(evento["details"]).split())
        linea += f"\n    {detalles}"
    return linea


def recortar_por_presupuesto(
    eventos: Iterable[Mapping[str, Any]],
    max_bytes: int = PRESUPUESTO_BYTES,
    *,
    con_detalles: bool = False,
) -> tuple[list[dict[str, Any]], int]:
    """Toma eventos ya ordenados y devuelve los que caben, con los bytes usados.

    El corte es por tamaño real del texto renderizado en UTF-8. Se para en el
    primer evento que no cabe en lugar de seguir buscando uno más pequeño: el
    orden es por relevancia y saltárselo entregaría material peor puntuado que
    el omitido.
    """
    elegidos: list[dict[str, Any]] = []
    usados = 0
    for evento in eventos:
        linea = formato_evento(evento, con_detalles=con_detalles)
        coste = len(linea.encode("utf-8")) + 1  # + salto de línea
        if usados + coste > max_bytes:
            break
        elegidos.append(dict(evento))
        usados += coste
    return elegidos, usados
