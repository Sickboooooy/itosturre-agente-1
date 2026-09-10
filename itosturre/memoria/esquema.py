"""Esquema SQLite de la memoria contextual y apertura de conexiones.

Diseño (ver docs/auditoria-memoria-contextual-10sep2026.md §3.2):

* ``eventos`` es la tabla de verdad. ``eventos_fts`` es un índice FTS5 **externo**
  (``content='eventos'``): no duplica el texto, lo referencia por ``rowid``. La
  sincronización va por disparadores, que es el contrato documentado de SQLite
  para índices externos.
* El tokenizador es ``unicode61 remove_diacritics 2``, no ``porter``: el stemmer
  porter solo entiende inglés y sin ``remove_diacritics`` una búsqueda de
  "revocacion" no encontraría "revocación" — inaceptable en texto jurídico
  mexicano.
* La base vive **fuera del repositorio** (``~/.itosturre/memoria/``). Los
  expedientes son work product con datos de cliente y la regla absoluta #8 de
  CLAUDE.md prohíbe versionarlos; una base dentro del árbol sería un accidente
  esperando a ocurrir.

Este módulo no importa nada fuera de la biblioteca estándar.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from pathlib import Path

ESQUEMA_VERSION = 1

#: Variable de entorno para reubicar el directorio de bases (pruebas, respaldos).
ENV_DIR = "ITOSTURRE_MEMORIA_DIR"
#: Variable de entorno para fijar una base concreta, ignorando el project_id.
ENV_DB = "ITOSTURRE_MEMORIA_DB"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


class MemoriaNoDisponible(RuntimeError):
    """La memoria no puede operar (por ejemplo, SQLite sin FTS5 compilado).

    Se usa para degradar sin romper: quien la capture debe continuar su trabajo
    sin memoria, nunca abortar la tarea del usuario.
    """


# ─────────────────────────────────────────
# Identidad de proyecto
# ─────────────────────────────────────────

def project_id(raiz: str | os.PathLike[str] | None = None) -> str:
    """Identificador estable y legible del proyecto, derivado de su ruta.

    Combina el nombre del directorio (legible al inspeccionar el disco) con un
    hash corto de la ruta absoluta normalizada (evita que dos clones distintos
    del mismo repositorio compartan memoria). ``os.path.normcase`` absorbe la
    diferencia de mayúsculas de Windows: ``C:\\Users`` y ``c:\\users`` son el
    mismo proyecto.
    """
    ruta = Path(raiz) if raiz is not None else Path.cwd()
    absoluta = ruta.resolve()
    normal = os.path.normcase(str(absoluta)).replace("\\", "/")
    digest = hashlib.sha256(normal.encode("utf-8")).hexdigest()[:8]
    slug = _SLUG_RE.sub("-", absoluta.name.lower()).strip("-") or "proyecto"
    return f"{slug}-{digest}"


def ruta_base(pid: str | None = None, raiz: str | os.PathLike[str] | None = None) -> Path:
    """Ruta del archivo SQLite para un proyecto.

    Prioridad: ``ITOSTURRE_MEMORIA_DB`` (base explícita) → ``ITOSTURRE_MEMORIA_DIR``
    → ``~/.itosturre/memoria/``. Siempre fuera del repositorio.
    """
    explicita = os.getenv(ENV_DB)
    if explicita:
        return Path(explicita).expanduser()
    directorio = Path(os.getenv(ENV_DIR) or (Path.home() / ".itosturre" / "memoria")).expanduser()
    return directorio / f"{pid or project_id(raiz)}.db"


# ─────────────────────────────────────────
# DDL
# ─────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS eventos (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  event_uid    TEXT    NOT NULL UNIQUE,
  session_id   TEXT    NOT NULL,
  project_id   TEXT    NOT NULL,
  timestamp    TEXT    NOT NULL,
  event_type   TEXT    NOT NULL,
  summary      TEXT    NOT NULL,
  details      TEXT,
  file_path    TEXT,
  importance   INTEGER NOT NULL DEFAULT 2,
  metadata     TEXT,
  redacted     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_ev_proj_ts   ON eventos(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_ev_proj_tipo ON eventos(project_id, event_type);
CREATE INDEX IF NOT EXISTS idx_ev_sesion    ON eventos(session_id);

CREATE VIRTUAL TABLE IF NOT EXISTS eventos_fts USING fts5(
  summary,
  details,
  file_path,
  content='eventos',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS eventos_ai AFTER INSERT ON eventos BEGIN
  INSERT INTO eventos_fts(rowid, summary, details, file_path)
  VALUES (new.id, new.summary, new.details, new.file_path);
END;

CREATE TRIGGER IF NOT EXISTS eventos_ad AFTER DELETE ON eventos BEGIN
  INSERT INTO eventos_fts(eventos_fts, rowid, summary, details, file_path)
  VALUES ('delete', old.id, old.summary, old.details, old.file_path);
END;

CREATE TRIGGER IF NOT EXISTS eventos_au AFTER UPDATE ON eventos BEGIN
  INSERT INTO eventos_fts(eventos_fts, rowid, summary, details, file_path)
  VALUES ('delete', old.id, old.summary, old.details, old.file_path);
  INSERT INTO eventos_fts(rowid, summary, details, file_path)
  VALUES (new.id, new.summary, new.details, new.file_path);
END;

CREATE TABLE IF NOT EXISTS sesiones (
  session_id  TEXT    PRIMARY KEY,
  project_id  TEXT    NOT NULL,
  iniciada_en TEXT    NOT NULL,
  ultima_en   TEXT,
  n_eventos   INTEGER NOT NULL DEFAULT 0,
  n_compact   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS snapshots (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT    NOT NULL,
  project_id TEXT    NOT NULL,
  snapshot   TEXT    NOT NULL,
  creado_en  TEXT    NOT NULL,
  consumido  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_snap_sesion ON snapshots(session_id, consumido);
"""


def fts5_disponible(con: sqlite3.Connection) -> bool:
    """¿Trae FTS5 este SQLite? Verificación real, no inferencia por versión."""
    try:
        con.execute(
            "CREATE VIRTUAL TABLE temp.__fts_probe USING fts5(a, tokenize='unicode61')"
        )
        con.execute("DROP TABLE temp.__fts_probe")
        return True
    except sqlite3.Error:
        return False


def conectar(db_path: str | os.PathLike[str]) -> sqlite3.Connection:
    """Abre (creando si hace falta) la base con WAL y espera ante bloqueo.

    WAL permite lector y escritor concurrentes; ``busy_timeout`` absorbe la
    contención en lugar de propagar ``SQLITE_BUSY`` al usuario. El uso real es de
    un solo operador, así que esto va sobrado — la intención es no fallar nunca
    por concurrencia, no exprimir rendimiento.
    """
    ruta = Path(db_path)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    _restringir_permisos(ruta.parent)

    con = sqlite3.connect(str(ruta), timeout=5.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    con.execute("PRAGMA busy_timeout = 5000")
    con.execute("PRAGMA foreign_keys = ON")

    if not fts5_disponible(con):
        con.close()
        raise MemoriaNoDisponible(
            "Este SQLite no trae FTS5 compilado; la memoria contextual no puede operar. "
            "Verifica con: python -c \"import sqlite3;"
            "sqlite3.connect(':memory:').execute('CREATE VIRTUAL TABLE t USING fts5(a)')\""
        )

    con.executescript(_DDL)
    _migrar(con)
    return con


def _restringir_permisos(directorio: Path) -> None:
    """Restringe el directorio de memoria al usuario donde el SO lo soporta.

    En POSIX aplica 0o700. En Windows los permisos POSIX no tienen efecto real y
    el control lo lleva la ACL del perfil del usuario: no se simula una garantía
    que el sistema no da (riesgo E6 del informe, documentado y aceptado en equipo
    monousuario).
    """
    if os.name == "posix":
        try:
            directorio.chmod(0o700)
        except OSError:
            pass


def _migrar(con: sqlite3.Connection) -> None:
    """Migración idempotente basada en ``PRAGMA user_version``.

    Hoy solo sella la versión inicial. El punto de extensión existe desde el
    primer día para que añadir una columna más adelante no exija reconstruir la
    base ni perder historia.
    """
    version = con.execute("PRAGMA user_version").fetchone()[0]
    if version < ESQUEMA_VERSION:
        con.execute(f"PRAGMA user_version = {ESQUEMA_VERSION}")


def reconstruir_fts(con: sqlite3.Connection) -> None:
    """Reconstruye el índice FTS desde la tabla de verdad.

    Útil tras una importación masiva o si el índice externo quedara desalineado.
    """
    con.execute("INSERT INTO eventos_fts(eventos_fts) VALUES ('rebuild')")
