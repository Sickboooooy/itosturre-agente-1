"""Almacén de memoria contextual: escritura, recuperación y sesiones.

Contrato de la clase (informe §3):

* Todo lo que entra pasa antes por :mod:`redaccion` — sin excepción y sin
  posibilidad de saltárselo desde fuera.
* ``project_id`` participa en **todas** las consultas. El aislamiento entre
  expedientes no es una opción de llamada que alguien pueda olvidar.
* ``recall`` devuelve un bloque con techo en bytes. La base puede tener cien mil
  eventos; lo que sale de aquí no crece con ella.
* La memoria es un caché reconstruible, no la fuente de verdad. Los JSON de
  ``auditorias/`` siguen siendo canónicos; si esta base se pierde, se reconstruye.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import ranking, redaccion
from .esquema import (
    MemoriaNoDisponible,
    conectar,
    project_id as derivar_project_id,
    reconstruir_fts,
    ruta_base,
)
from .hooks import procedencia_no_humana as _procedencia_no_humana

#: Tipo del evento de auditoría que deja ``olvidar``. Nunca se purga a sí mismo.
TIPO_PURGA = "memoria_purga"

_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Multiplicador del conjunto de candidatos antes de repuntuar y recortar.
#: Se pide más de lo que se devolverá porque BM25 ordena por coincidencia léxica
#: y el reordenamiento por importancia y recencia puede subir a un candidato que
#: BM25 dejó en el puesto 30.
_FACTOR_CANDIDATOS = 8
_MAX_CANDIDATOS = 400

#: Pesos de columna de BM25: el resumen se escribió para ser leído, los detalles
#: son carga útil. Rankear por el resumen da resultados más legibles.
_PESOS_BM25 = (5.0, 1.0, 1.0)


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _session_por_defecto() -> str:
    """Identidad de sesión: la del anfitrión si la publica, si no una propia.

    Claude Code expone ``CLAUDE_SESSION_ID`` en algunos contextos. Cuando no
    está, se sintetiza una por proceso para que los eventos de una misma corrida
    de CLI queden agrupados.
    """
    for var in ("ITOSTURRE_SESSION_ID", "CLAUDE_SESSION_ID"):
        valor = os.getenv(var)
        if valor:
            return valor.strip()
    semilla = f"{os.getpid()}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
    return "cli-" + hashlib.sha256(semilla.encode("utf-8")).hexdigest()[:12]


class MemoriaStore:
    """Acceso a la memoria de un proyecto. Usar como contexto o cerrar a mano."""

    def __init__(
        self,
        *,
        db_path: str | os.PathLike[str] | None = None,
        pid: str | None = None,
        raiz: str | os.PathLike[str] | None = None,
        session_id: str | None = None,
    ) -> None:
        self.raiz = Path(raiz).resolve() if raiz else Path.cwd().resolve()
        self.project_id = pid or derivar_project_id(self.raiz)
        self.db_path = Path(db_path) if db_path else ruta_base(self.project_id, self.raiz)
        self.session_id = session_id or _session_por_defecto()
        self.con = conectar(self.db_path)
        self._asegurar_sesion()

    # ── ciclo de vida ────────────────────────────────────────────────────
    def __enter__(self) -> "MemoriaStore":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.cerrar()

    def cerrar(self) -> None:
        try:
            self.con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        self.con.close()

    def _asegurar_sesion(self) -> None:
        self.con.execute(
            "INSERT INTO sesiones (session_id, project_id, iniciada_en, ultima_en) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(session_id) DO NOTHING",
            (self.session_id, self.project_id, _ahora(), _ahora()),
        )

    # ── escritura ────────────────────────────────────────────────────────
    def record(
        self,
        event_type: str,
        summary: str,
        *,
        details: Any = None,
        file_path: str | None = None,
        importance: int | None = None,
        metadata: Mapping[str, Any] | None = None,
        session_id: str | None = None,
        timestamp: str | None = None,
        dedupe_key: str | None = None,
    ) -> dict[str, Any]:
        """Persiste un evento y devuelve la fila escrita (o la ya existente).

        Idempotente por ``event_uid``: el mismo hecho registrado dos veces no se
        duplica. Reutiliza el criterio de ``traceability.build_trace_record`` —
        el identificador no depende de cuándo se registró, sino de qué se
        registró.

        ``dedupe_key`` cambia esa identidad para los eventos que llegan de un
        hook. Sin ella, la marca de tiempo entra en el hash y veinte ediciones
        del mismo archivo en una sesión producirían veinte eventos idénticos
        salvo el segundo — justo el ruido que enterraría lo que importa. Con
        ella, la identidad es ``(proyecto, sesión, tipo, clave)``: el hecho se
        registra una vez por sesión, se le actualiza la fecha y se lleva la
        cuenta de repeticiones. Se acota a la sesión a propósito — trabajar hoy
        sobre un archivo es un hecho distinto de haberlo hecho el mes pasado.
        """
        tipo = ranking.canonizar(event_type)
        if not summary or not summary.strip():
            raise ValueError("El resumen del evento no puede estar vacío")

        resumen_limpio, red_resumen = redaccion.redactar(" ".join(summary.split()))
        detalles_limpios, red_detalles = redaccion.redactar(details)
        meta_limpia, red_meta = redaccion.redactar(dict(metadata or {}))
        redactado = red_resumen or red_detalles or red_meta

        ruta = redaccion.ruta_relativa(file_path, self.raiz)
        marca = timestamp or _ahora()
        sesion = session_id or self.session_id
        nivel = int(importance) if importance is not None else ranking.importancia_por_defecto(tipo)
        nivel = min(4, max(1, nivel))

        detalles_txt = _serializar(detalles_limpios)
        meta_txt = _serializar(meta_limpia) if meta_limpia else None

        if dedupe_key:
            identidad = {"p": self.project_id, "sid": sesion, "t": tipo, "k": dedupe_key}
        else:
            identidad = {
                "p": self.project_id,
                "t": tipo,
                "s": resumen_limpio,
                "d": detalles_txt,
                "f": ruta,
                "ts": marca,
            }
        uid = hashlib.sha256(
            json.dumps(identidad, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:24]

        cur = self.con.execute(
            "INSERT INTO eventos (event_uid, session_id, project_id, timestamp, event_type,"
            " summary, details, file_path, importance, metadata, redacted)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(event_uid) DO NOTHING",
            (uid, sesion, self.project_id, marca, tipo, resumen_limpio,
             detalles_txt, ruta, nivel, meta_txt, int(redactado)),
        )
        if cur.rowcount:
            self.con.execute(
                "UPDATE sesiones SET n_eventos = n_eventos + 1, ultima_en = ?"
                " WHERE session_id = ?",
                (marca, sesion),
            )
        elif dedupe_key:
            # Repetición de un hecho ya conocido: no se duplica la fila, se
            # refresca su fecha (la recencia debe reflejar la última vez) y se
            # lleva la cuenta, que informa de cuánto se ha tocado algo.
            self.con.execute(
                "UPDATE eventos SET timestamp = ?,"
                " metadata = json_set(COALESCE(metadata, '{}'), '$.veces',"
                "   COALESCE(json_extract(metadata, '$.veces'), 1) + 1)"
                " WHERE event_uid = ?",
                (marca, uid),
            )
        fila = self.con.execute(
            "SELECT * FROM eventos WHERE event_uid = ?", (uid,)
        ).fetchone()
        return dict(fila) if fila else {}

    def record_lote(self, eventos: Iterable[Mapping[str, Any]]) -> int:
        """Registra varios eventos en una transacción. Devuelve cuántos son nuevos."""
        nuevos = 0
        self.con.execute("BEGIN")
        try:
            antes = self._total()
            for ev in eventos:
                self.record(
                    ev["event_type"],
                    ev["summary"],
                    details=ev.get("details"),
                    file_path=ev.get("file_path"),
                    importance=ev.get("importance"),
                    metadata=ev.get("metadata"),
                    session_id=ev.get("session_id"),
                    timestamp=ev.get("timestamp"),
                )
            nuevos = self._total() - antes
            self.con.execute("COMMIT")
        except Exception:
            self.con.execute("ROLLBACK")
            raise
        return nuevos

    def _total(self) -> int:
        return self.con.execute(
            "SELECT COUNT(*) FROM eventos WHERE project_id = ?", (self.project_id,)
        ).fetchone()[0]

    # ── recuperación ─────────────────────────────────────────────────────
    def recall(
        self,
        consulta: str = "",
        *,
        limite: int = 12,
        max_bytes: int = ranking.PRESUPUESTO_BYTES,
        tipos: Sequence[str] | None = None,
        desde: str | None = None,
        con_detalles: bool = False,
    ) -> dict[str, Any]:
        """Recupera los eventos relevantes para ``consulta`` dentro del presupuesto.

        Sin consulta textual cae a orden cronológico inverso — que es lo correcto
        al arrancar una sesión, cuando aún no hay pregunta que hacer.
        """
        inicio = datetime.now(timezone.utc)
        expresion = redaccion.consulta_fts(consulta)
        tipos_canon = [ranking.canonizar(t) for t in (tipos or [])]

        if expresion:
            candidatos = self._buscar_fts(expresion, tipos_canon, desde, limite)
            modo = "bm25"
        else:
            candidatos = self._recientes(tipos_canon, desde, limite)
            modo = "reciente"

        elegidos, bytes_usados = ranking.recortar_por_presupuesto(
            candidatos[:limite], max_bytes, con_detalles=con_detalles
        )
        ms = (datetime.now(timezone.utc) - inicio).total_seconds() * 1000
        return {
            "consulta": consulta,
            "modo": modo,
            "expresion_fts": expresion,
            "project_id": self.project_id,
            "eventos": elegidos,
            "n_candidatos": len(candidatos),
            "n_devueltos": len(elegidos),
            "bytes": bytes_usados,
            "max_bytes": max_bytes,
            "ms": round(ms, 2),
            "total_en_memoria": self._total(),
        }

    def _buscar_fts(
        self,
        expresion: str,
        tipos: Sequence[str],
        desde: str | None,
        limite: int,
    ) -> list[dict[str, Any]]:
        tope = min(_MAX_CANDIDATOS, max(limite * _FACTOR_CANDIDATOS, limite))
        sql = (
            "SELECT e.*, bm25(eventos_fts, ?, ?, ?) AS bm25_raw"
            " FROM eventos_fts JOIN eventos e ON e.id = eventos_fts.rowid"
            " WHERE eventos_fts MATCH ? AND e.project_id = ?"
        )
        params: list[Any] = [*_PESOS_BM25, expresion, self.project_id]
        if tipos:
            sql += f" AND e.event_type IN ({','.join('?' * len(tipos))})"
            params.extend(tipos)
        if desde:
            sql += " AND e.timestamp >= ?"
            params.append(desde)
        sql += " ORDER BY bm25_raw LIMIT ?"
        params.append(tope)

        try:
            filas = [dict(f) for f in self.con.execute(sql, params).fetchall()]
        except sqlite3.OperationalError:
            # Una expresión MATCH sintácticamente válida pero vacía de términos
            # indexados no es un error del usuario: se devuelve lo reciente.
            return self._recientes(tipos, desde, limite)

        normalizados = ranking.normalizar_bm25([f["bm25_raw"] for f in filas])
        ahora = datetime.now(timezone.utc)
        for fila, norm in zip(filas, normalizados):
            fila["bm25_norm"] = round(norm, 4)
            fila["score"] = round(
                ranking.puntuar(
                    bm25_norm=norm,
                    event_type=fila["event_type"],
                    importance=fila["importance"],
                    timestamp=fila["timestamp"],
                    ahora=ahora,
                ),
                4,
            )
        filas.sort(key=lambda f: f["score"], reverse=True)
        return filas

    def _recientes(
        self,
        tipos: Sequence[str],
        desde: str | None,
        limite: int,
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM eventos WHERE project_id = ?"
        params: list[Any] = [self.project_id]
        if tipos:
            sql += f" AND event_type IN ({','.join('?' * len(tipos))})"
            params.extend(tipos)
        if desde:
            sql += " AND timestamp >= ?"
            params.append(desde)
        # Se ordena por importancia antes que por fecha: al reanudar, una alerta
        # procesal de la semana pasada pesa más que un commit de hace una hora.
        sql += " ORDER BY importance ASC, timestamp DESC LIMIT ?"
        params.append(max(limite * 2, limite))
        filas = [dict(f) for f in self.con.execute(sql, params).fetchall()]
        for fila in filas:
            fila["bm25_norm"] = 0.0
            fila["score"] = round(
                ranking.bono_tipo(fila["event_type"])
                * ranking.decaimiento_recencia(fila["timestamp"]),
                4,
            )
        return filas

    # ── sesiones y snapshots ─────────────────────────────────────────────
    def guardar_snapshot(self, texto: str, *, session_id: str | None = None) -> int:
        sesion = session_id or self.session_id
        cur = self.con.execute(
            "INSERT INTO snapshots (session_id, project_id, snapshot, creado_en)"
            " VALUES (?, ?, ?, ?)",
            (sesion, self.project_id, texto, _ahora()),
        )
        self.con.execute(
            "UPDATE sesiones SET n_compact = n_compact + 1 WHERE session_id = ?", (sesion,)
        )
        return int(cur.lastrowid or 0)

    def consumir_snapshot(self, *, session_id: str | None = None) -> str | None:
        """Devuelve el último snapshot sin consumir y lo marca como consumido.

        La bandera evita el bucle de reinyección: restaurar el mismo estado en
        cada arranque llenaría el contexto con lo que el modelo ya sabe.
        """
        sesion = session_id or self.session_id
        fila = self.con.execute(
            "SELECT id, snapshot FROM snapshots"
            " WHERE project_id = ? AND (session_id = ? OR ? = '')"
            "   AND consumido = 0 ORDER BY id DESC LIMIT 1",
            (self.project_id, sesion, ""),
        ).fetchone()
        if not fila:
            return None
        self.con.execute("UPDATE snapshots SET consumido = 1 WHERE id = ?", (fila["id"],))
        return str(fila["snapshot"])

    def ultimo_snapshot(self) -> str | None:
        fila = self.con.execute(
            "SELECT snapshot FROM snapshots WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (self.project_id,),
        ).fetchone()
        return str(fila["snapshot"]) if fila else None

    # ── introspección ────────────────────────────────────────────────────
    def estadisticas(self) -> dict[str, Any]:
        por_tipo = {
            f["event_type"]: f["n"]
            for f in self.con.execute(
                "SELECT event_type, COUNT(*) AS n FROM eventos WHERE project_id = ?"
                " GROUP BY event_type ORDER BY n DESC",
                (self.project_id,),
            ).fetchall()
        }
        rango = self.con.execute(
            "SELECT MIN(timestamp) AS a, MAX(timestamp) AS b FROM eventos WHERE project_id = ?",
            (self.project_id,),
        ).fetchone()
        return {
            "project_id": self.project_id,
            "db": str(self.db_path),
            "db_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            "total": self._total(),
            "redactados": self.con.execute(
                "SELECT COUNT(*) FROM eventos WHERE project_id = ? AND redacted = 1",
                (self.project_id,),
            ).fetchone()[0],
            "sesiones": self.con.execute(
                "SELECT COUNT(*) FROM sesiones WHERE project_id = ?", (self.project_id,)
            ).fetchone()[0],
            "snapshots": self.con.execute(
                "SELECT COUNT(*) FROM snapshots WHERE project_id = ?", (self.project_id,)
            ).fetchone()[0],
            "por_tipo": por_tipo,
            "desde": rango["a"] if rango else None,
            "hasta": rango["b"] if rango else None,
        }

    def reindexar(self) -> None:
        reconstruir_fts(self.con)

    def borrar_por_origen(self, origen: str) -> int:
        """Borra los eventos importados bajo un ``metadata.origen``. Devuelve cuántos.

        Existe para reejecutar una importación cuando cambia el criterio de
        conversión: el ``event_uid`` depende del contenido, así que reimportar con
        otra clasificación crearía duplicados en vez de sustituir.

        Alcance acotado a propósito: solo toca filas que la propia importación
        etiquetó con ese origen, y solo dentro de este proyecto. No hay forma de
        llamar a esto y llevarse por delante un evento registrado a mano.
        """
        cur = self.con.execute(
            "DELETE FROM eventos WHERE project_id = ?"
            " AND json_extract(metadata, '$.origen') = ?",
            (self.project_id, origen),
        )
        return int(cur.rowcount or 0)

    # ── purga selectiva ──────────────────────────────────────────────────
    def olvidar(
        self,
        *,
        tipos: Sequence[str] | None = None,
        desde: str | None = None,
        hasta: str | None = None,
        contiene: str | None = None,
        procedencia_no_humana: bool = False,
        aplicar: bool = False,
    ) -> dict[str, Any]:
        """Selecciona eventos de este proyecto y, solo con ``aplicar=True``, los borra.

        Los filtros se combinan con Y lógico:

        * ``tipos`` — tipos de evento (se canonizan como en ``record``).
        * ``desde`` / ``hasta`` — días ``AAAA-MM-DD``, ambos inclusive.
        * ``contiene`` — subcadena literal en el resumen o en los detalles,
          insensible a mayúsculas y acentos (mismo criterio que el índice FTS).
        * ``procedencia_no_humana`` — el texto guardado no lo escribió el
          operador, según el mismo detector que filtra la captura de prompts.

        Garantías:

        * **Simulación por defecto.** Sin ``aplicar`` no se modifica nada.
        * **Al menos un filtro.** Sin filtros se lanza ``ValueError``: no hay
          forma de "borrar todo" por omisión.
        * **Solo este ``project_id``.** Igual que el resto de consultas.
        * **Índice coherente.** El borrado pasa por el disparador
          ``eventos_ad`` de ``esquema.py``, que retira cada fila del índice FTS
          externo con sus valores originales.
        * **Sin reinyección de lo borrado.** Se marcan como consumidos los
          snapshots pendientes del proyecto: el siguiente ``SessionStart`` se
          reconstruye desde los eventos que quedan.
        * **Rastro sin contenido.** Se registra un ``memoria_purga`` con cuántos
          eventos se borraron y qué filtros se usaron; de ``contiene`` solo
          consta que se usó, nunca el texto (podría ser justo el dato que se
          quiere hacer desaparecer). Los ``memoria_purga`` nunca se seleccionan.

        Todo ocurre en una transacción: o se borra y se audita, o nada.
        """
        filtros = filtros_de_olvido(
            tipos=tipos, desde=desde, hasta=hasta, contiene=contiene,
            procedencia_no_humana=procedencia_no_humana,
        )
        aguja = _plegar(contiene.strip()) if filtros["contiene"] else None

        borrados = consumidos = 0
        if aplicar:
            self.con.execute("BEGIN IMMEDIATE")
        try:
            coincidencias = self._seleccionar_olvido(
                filtros["tipos"] or [], filtros["desde"], filtros["hasta"], aguja,
                filtros["procedencia_no_humana"],
            )
            if aplicar and coincidencias:
                cur = self.con.executemany(
                    "DELETE FROM eventos WHERE id = ? AND project_id = ?",
                    [(f["id"], self.project_id) for f in coincidencias],
                )
                borrados = int(cur.rowcount or 0)
                por_sesion = Counter(f["session_id"] for f in coincidencias)
                self.con.executemany(
                    "UPDATE sesiones SET n_eventos = MAX(0, n_eventos - ?)"
                    " WHERE session_id = ? AND project_id = ?",
                    [(n, sesion, self.project_id) for sesion, n in por_sesion.items()],
                )
                consumidos = int(self.con.execute(
                    "UPDATE snapshots SET consumido = 1 WHERE project_id = ? AND consumido = 0",
                    (self.project_id,),
                ).rowcount or 0)
                self.record(
                    TIPO_PURGA,
                    f"Purga de memoria con olvidar: {borrados} evento(s) borrado(s)",
                    details={"borrados": borrados, "snapshots_consumidos": consumidos,
                             "filtros": filtros},
                )
            if aplicar:
                self.con.execute("COMMIT")
        except Exception:
            if self.con.in_transaction:
                self.con.execute("ROLLBACK")
            raise

        return {
            "project_id": self.project_id,
            "aplicado": bool(aplicar),
            "filtros": filtros,
            "coincidencias": [
                {k: f[k] for k in ("id", "timestamp", "event_type", "summary")}
                for f in coincidencias
            ],
            "borrados": borrados,
            "snapshots_consumidos": consumidos,
        }

    def _seleccionar_olvido(
        self,
        tipos: Sequence[str],
        desde: str | None,
        hasta: str | None,
        aguja: str | None,
        procedencia_no_humana: bool,
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT id, session_id, timestamp, event_type, summary, details FROM eventos"
            " WHERE project_id = ? AND event_type != ?"
        )
        params: list[Any] = [self.project_id, TIPO_PURGA]
        if tipos:
            sql += f" AND event_type IN ({','.join('?' * len(tipos))})"
            params.extend(tipos)
        # Se compara el día (los diez primeros caracteres) y no la marca entera:
        # así ``hasta`` incluye el día completo, sea cual sea el formato horario.
        if desde:
            sql += " AND substr(timestamp, 1, 10) >= ?"
            params.append(desde)
        if hasta:
            sql += " AND substr(timestamp, 1, 10) <= ?"
            params.append(hasta)
        sql += " ORDER BY timestamp, id"
        filas = [dict(f) for f in self.con.execute(sql, params).fetchall()]

        # Texto y procedencia se filtran en Python: subcadena literal sin
        # comodines de LIKE y el mismo detector que usa el hook de captura.
        if aguja:
            filas = [
                f for f in filas
                if aguja in _plegar(f["summary"] or "") or aguja in _plegar(f["details"] or "")
            ]
        if procedencia_no_humana:
            filas = [
                f for f in filas
                if _procedencia_no_humana(f["summary"] or "")
                or _procedencia_no_humana(f["details"] or "")
            ]
        return filas


def filtros_de_olvido(
    *,
    tipos: Sequence[str] | None = None,
    desde: str | None = None,
    hasta: str | None = None,
    contiene: str | None = None,
    procedencia_no_humana: bool = False,
) -> dict[str, Any]:
    """Valida y normaliza los filtros de ``olvidar``. Pura: no toca la base.

    Lanza ``ValueError`` si no hay ningún filtro, si una fecha no es
    ``AAAA-MM-DD`` o si el rango está invertido. El diccionario devuelto es el
    que queda en el evento de auditoría: de ``contiene`` solo guarda si se usó.
    """
    tipos_canon = sorted({ranking.canonizar(t) for t in (tipos or []) if t and t.strip()})
    desde = validar_fecha(desde) if desde else None
    hasta = validar_fecha(hasta) if hasta else None
    con_texto = bool(contiene and contiene.strip())
    if not (tipos_canon or desde or hasta or con_texto or procedencia_no_humana):
        raise ValueError(
            "olvidar exige al menos un filtro (--tipos, --desde, --hasta, --contiene"
            " o --procedencia-no-humana); nunca borra todo por omisión"
        )
    if desde and hasta and desde > hasta:
        raise ValueError(f"Rango vacío: --desde {desde} es posterior a --hasta {hasta}")
    return {
        "tipos": tipos_canon or None,
        "desde": desde,
        "hasta": hasta,
        "contiene": con_texto,
        "procedencia_no_humana": bool(procedencia_no_humana),
    }


def validar_fecha(valor: str) -> str:
    """Devuelve la fecha si es un día real en formato ``AAAA-MM-DD``; si no, ``ValueError``.

    Se exige el formato exacto (``date.fromisoformat`` acepta otros en Python
    3.11+) porque la comparación con la marca guardada es por texto.
    """
    texto = (valor or "").strip()
    if not _FECHA_RE.match(texto):
        raise ValueError(f"Fecha inválida '{valor}': se espera AAAA-MM-DD")
    date.fromisoformat(texto)  # rechaza 2026-02-30
    return texto


def _plegar(texto: str) -> str:
    """Minúsculas y sin diacríticos, para comparar como lo hace el índice FTS."""
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").casefold()


def _serializar(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        return valor
    try:
        return json.dumps(valor, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(valor)


# ─────────────────────────────────────────
# Fachada tolerante a fallos
# ─────────────────────────────────────────

def registrar_seguro(
    event_type: str,
    summary: str,
    *,
    raiz: str | os.PathLike[str] | None = None,
    **campos: Any,
) -> bool:
    """Registra un evento sin propagar jamás un fallo. Devuelve si lo consiguió.

    Es la única puerta que deben usar los pipelines de producción
    (``vvca_full.py``, ``OpenNotebook.py``). Un problema de memoria —SQLite sin
    FTS5, disco lleno, base bloqueada— **nunca** puede tumbar una auditoría en
    curso: la memoria es accesoria y el trabajo del abogado no lo es.
    """
    try:
        with MemoriaStore(raiz=raiz) as store:
            store.record(event_type, summary, **campos)
        return True
    except (MemoriaNoDisponible, sqlite3.Error, OSError, ValueError):
        return False
