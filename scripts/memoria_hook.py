#!/usr/bin/env python3
"""Punto de entrada único de los hooks de memoria contextual.

Claude Code entrega el evento como JSON por stdin y lee JSON por stdout. Este
script despacha por evento, escribe en la memoria y —en ``SessionStart``—
devuelve el contexto compacto de reanudación.

Uso (desde .claude/settings.json):
  python scripts/memoria_hook.py <evento>

Contrato de fallo seguro (etapa 7G):

* **Siempre sale con código 0.** Un hook que devuelve error puede interrumpir el
  turno; la memoria es auxiliar y jamás debe hacerlo.
* **stdout lleva JSON válido o nada.** Cualquier otra cosa contaminaría el
  contexto del modelo. Los diagnósticos van a la bitácora, no a stdout.
* Un fallo de SQLite, un payload malformado o un disco lleno degradan la
  funcionalidad —no se recuerda ese evento— y el agente continúa.
"""
from __future__ import annotations

import json

import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# La consola de Windows usa cp1252 y no codifica los emoji del snapshot (🚨 ⚖️ ➡️):
# sin esto, `SessionStart` moría con UnicodeEncodeError y la restauración no se
# entregaba nunca. Se fuerza antes de cualquier escritura, igual que hacen
# OpenNotebook.py y vvca_full.py.
for _flujo in (sys.stdout, sys.stderr):
    if hasattr(_flujo, "reconfigure"):
        try:
            _flujo.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001 — si no se puede, el fallo seguro cubre
            pass

#: Techo del bloque que se inyecta al reanudar. La continuidad no puede costar
#: más que lo que hace continuar.
PRESUPUESTO_RESTAURACION = 2048

EVENTOS_CAPTURA = {"PostToolUse", "PostToolUseFailure", "UserPromptSubmit"}
EVENTOS_SNAPSHOT = {"PreCompact", "SessionEnd", "Stop"}


def _leer_payload() -> dict:
    """Lee el payload del hook decodificando UTF-8 explícitamente.

    En Windows `sys.stdin.encoding` es cp1252 y el JSON del hook llega en UTF-8:
    leer por texto convertía "todavía" en "todavÃ­a" y esa corrupción se
    persistía en la memoria. Se lee el búfer binario y se decodifica a mano, que
    además no depende de que `reconfigure` esté disponible.
    """
    try:
        binario = getattr(sys.stdin, "buffer", None)
        crudo = (binario.read().decode("utf-8", errors="replace") if binario
                 else sys.stdin.read())
    except Exception:  # noqa: BLE001
        return {}
    if not crudo or not crudo.strip():
        return {}
    try:
        datos = json.loads(crudo)
    except (json.JSONDecodeError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _emitir(evento: str, contexto: str) -> None:
    """Inyecta contexto de vuelta al modelo. Única escritura permitida a stdout."""
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": evento,
            "additionalContext": contexto,
        },
        "suppressOutput": True,
    }, ensure_ascii=False))


def _capturar(payload: dict, evento: str) -> dict:
    from itosturre.memoria.hooks import procesar
    return procesar(payload, evento, raiz=REPO)


def _snapshot(payload: dict, evento: str) -> dict:
    """Condensa el estado antes de perder contexto (etapas 7C y 7E).

    Idempotente: si el snapshot vigente de esta sesión ya coincide con el que se
    construiría ahora, no se guarda otro. Dos ``PreCompact`` seguidos sin trabajo
    entre medias no deben dejar dos filas.
    """
    inicio = time.perf_counter()
    diag = {"evento": evento, "hook": "snapshot", "accion": "descartado"}
    try:
        from itosturre.memoria import construir_snapshot
        from itosturre.memoria.hooks import habilitado
        from itosturre.memoria.store import MemoriaStore

        if not habilitado():
            diag["motivo"] = "hooks desactivados"
            return diag

        with MemoriaStore(raiz=REPO, session_id=payload.get("session_id") or None) as store:
            eventos = store.recall("", limite=80, max_bytes=10 ** 7)["eventos"]
            texto = construir_snapshot(
                eventos,
                project_id=store.project_id,
                session_id=store.session_id,
                total_en_memoria=store._total(),
                max_bytes=PRESUPUESTO_RESTAURACION,
            )
            if store.ultimo_snapshot() == texto:
                diag["motivo"] = "idéntico al vigente"
                return diag
            store.guardar_snapshot(texto)
        diag["accion"] = "almacenado"
        diag["bytes"] = len(texto.encode("utf-8"))
    except Exception as e:  # noqa: BLE001 — frontera de fallo seguro
        diag["accion"] = "error"
        diag["error"] = f"{type(e).__name__}: {e}"[:200]
    finally:
        diag["ms"] = round((time.perf_counter() - inicio) * 1000, 2)
    return diag


def _restaurar(payload: dict, evento: str) -> dict:
    """Reconstruye el contexto compacto al iniciar o reanudar (etapa 7D).

    Orden: proyecto → sesión → snapshot sin consumir → si no hay, se construye
    uno de los eventos recientes. **Nunca se vuelca el historial completo**: lo
    que sale de aquí está acotado a ``PRESUPUESTO_RESTAURACION``.
    """
    inicio = time.perf_counter()
    diag = {"evento": evento, "hook": "restauracion", "accion": "descartado"}
    try:
        from itosturre.memoria import construir_snapshot
        from itosturre.memoria.hooks import habilitado
        from itosturre.memoria.store import MemoriaStore

        if not habilitado():
            diag["motivo"] = "hooks desactivados"
            return diag

        with MemoriaStore(raiz=REPO, session_id=payload.get("session_id") or None) as store:
            diag["project_id"] = store.project_id
            total = store._total()
            if total == 0:
                diag["motivo"] = "memoria vacía"
                return diag

            texto = store.consumir_snapshot()
            origen = "snapshot"
            if texto is None:
                # Sin snapshot previo (primera sesión tras instalar los hooks, o
                # ya consumido): se sintetiza uno de lo más relevante reciente.
                eventos = store.recall("", limite=60, max_bytes=10 ** 7)["eventos"]
                texto = construir_snapshot(
                    eventos,
                    project_id=store.project_id,
                    total_en_memoria=total,
                    max_bytes=PRESUPUESTO_RESTAURACION,
                )
                origen = "reconstruido"

        if len(texto.encode("utf-8")) > PRESUPUESTO_RESTAURACION * 2:
            diag["accion"] = "error"
            diag["error"] = "snapshot fuera de presupuesto; no se inyecta"
            return diag

        _emitir(evento, texto)
        diag["accion"] = "inyectado"
        diag["origen"] = origen
        diag["bytes"] = len(texto.encode("utf-8"))
    except Exception as e:  # noqa: BLE001 — frontera de fallo seguro
        diag["accion"] = "error"
        diag["error"] = f"{type(e).__name__}: {e}"[:200]
    finally:
        diag["ms"] = round((time.perf_counter() - inicio) * 1000, 2)
    return diag


def main() -> int:
    evento = sys.argv[1] if len(sys.argv) > 1 else ""
    diag: dict = {"evento": evento, "accion": "ignorado"}
    try:
        payload = _leer_payload()
        if evento == "SessionStart":
            diag = _restaurar(payload, evento)
        elif evento in EVENTOS_SNAPSHOT:
            diag = _snapshot(payload, evento)
        elif evento in EVENTOS_CAPTURA:
            diag = _capturar(payload, evento)
        else:
            diag["motivo"] = "evento no manejado"
    except Exception as e:  # noqa: BLE001 — nada sale de aquí como excepción
        diag = {"evento": evento, "accion": "error",
                "error": f"{type(e).__name__}: {e}"[:200]}

    try:
        from itosturre.memoria.hooks import registrar_diagnostico
        registrar_diagnostico(diag)
    except Exception:  # noqa: BLE001
        pass

    # Siempre 0: un código distinto puede cortar el turno del usuario.
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 — última red antes del proceso
        sys.exit(0)
