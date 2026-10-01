"""Clasificación y captura automática de eventos desde los hooks de Claude Code.

Este módulo decide **qué merece recordarse**. Es la pieza que separa una memoria
útil de un vertedero: la mayoría de lo que ocurre en una sesión —leer archivos,
listar directorios, buscar texto— no tiene valor persistente y registrarlo
degradaría la recuperación de lo que sí lo tiene.

Regla de oro: **se guarda el hecho, no la salida.** "Editó `vvca_full.py`" es un
hecho; los 4 KB del diff son ruido que ya está en git.

Dos propiedades que el módulo garantiza:

* **Camino caliente barato.** ``clasificar`` es puro y no importa SQLite. La
  inmensa mayoría de los eventos se descartan antes de tocar la base.
* **Nunca propaga un fallo.** ``procesar`` devuelve un resultado describiendo lo
  ocurrido; jamás lanza. La memoria es auxiliar (etapa 7G): si falla, el agente
  sigue trabajando.
"""
from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .redaccion import redactar

#: Interruptor general. `off` desactiva toda captura y restauración.
ENV_HOOKS = "ITOSTURRE_MEMORIA_HOOKS"
#: Captura de prompts del usuario. Ver `capturar_prompt` para el porqué del opt-out.
ENV_PROMPTS = "ITOSTURRE_MEMORIA_PROMPTS"
#: Bitácora de diagnóstico (etapa 7K).
ENV_LOG = "ITOSTURRE_MEMORIA_LOG"

#: Tope del resumen persistido. Un evento es un hecho, no un transcript.
MAX_RESUMEN = 200
#: Un prompt (o lo que queda de él sin el texto pegado) más corto que esto no
#: expresa una decisión que valga la pena recordar.
MIN_PROMPT = 12
#: Tope de la bitácora antes de rotar.
MAX_LOG_BYTES = 512 * 1024


def habilitado() -> bool:
    return (os.getenv(ENV_HOOKS) or "on").strip().lower() not in ("0", "off", "false", "no")


# ─────────────────────────────────────────
# Clasificación de comandos de shell
# ─────────────────────────────────────────

#: Comandos triviales: navegar, mirar, listar. Nunca se registran.
_TRIVIAL = re.compile(
    r"^\s*(ls|ll|dir|cd|pwd|cat|head|tail|less|more|echo|printf|which|type|"
    r"whoami|date|clear|wc|find|grep|rg|sed|awk|sort|uniq|cut|tr|env|export|"
    r"git\s+(status|diff|log|show|branch\s*$|remote|config)|"
    r"python\s+-c|node\s+-e|true|false|sleep|touch|mkdir|test)\b",
    re.IGNORECASE,
)

_GIT_COMMIT = re.compile(r"\bgit\s+commit\b", re.IGNORECASE)
_GIT_RAMA = re.compile(r"\bgit\s+(?:checkout\s+-b|switch\s+-c|branch)\s+(\S+)", re.IGNORECASE)
_GIT_MERGE = re.compile(r"\bgit\s+(merge|rebase|cherry-pick)\b", re.IGNORECASE)
_PRUEBAS = re.compile(
    r"\b(unittest|pytest|vitest|jest|npm\s+(run\s+)?test|"
    r"evaluate_gold_set|run_regression|check_agent_surfaces|"
    r"check_sensitive_paths|test_scraper_offline|verificar_migracion)\b",
    re.IGNORECASE,
)
_DEPENDENCIAS = re.compile(
    r"\b(pip\s+install|pip3\s+install|npm\s+(i|install|ci)|pnpm\s+(add|install)|"
    r"yarn\s+add|poetry\s+add)\b",
    re.IGNORECASE,
)
_CONFIG = re.compile(
    r"(settings\.json|\.gitignore|requirements\.txt|package\.json|pyproject\.toml|"
    r"data-policy\.json|ci\.yml)",
    re.IGNORECASE,
)
#: Señales de fallo en la salida de una prueba. Se busca en la respuesta, no se supone.
_FALLO = re.compile(r"\b(FAILED|FAIL:|ERROR:|Traceback|AssertionError|\bfailures=[1-9])",
                    re.IGNORECASE)
_EXITO = re.compile(r"\b(OK|PASSED|🟢|✅|passed)\b")

#: Archivos cuyo cambio no dice nada: artefactos, cachés, temporales.
_RUTA_IRRELEVANTE = re.compile(
    r"(^|/)(__pycache__|node_modules|venv|chroma_db|\.git|graphify-out)/|"
    r"\.(pyc|pyo|log|tmp|bak|lock)$|(^|/)(temp|debug)/",
    re.IGNORECASE,
)


def _recortar(texto: str, tope: int = MAX_RESUMEN) -> str:
    limpio = " ".join(str(texto or "").split())
    if len(limpio) <= tope:
        return limpio
    corte = limpio.rfind(" ", 0, tope)
    return limpio[: corte if corte > tope // 2 else tope].rstrip() + "…"


def _mensaje_commit(comando: str) -> str:
    """Extrae el asunto de un `git commit -m` sin arrastrar el cuerpo entero."""
    for patron in (r"-m\s+'([^']+)'", r'-m\s+"([^"]+)"', r"-m\s+(\S+)"):
        m = re.search(patron, comando)
        if m:
            return _recortar(m.group(1).splitlines()[0], 120)
    return "(sin asunto en línea)"


#: Separadores de encadenamiento. Un comando de agente casi nunca es uno solo.
#:
#: **Sin salto de línea a propósito.** Partir por `\n` metía dentro del
#: clasificador el cuerpo de los heredocs, y una línea de código Python que
#: mencionaba `unittest` acabó registrada como "Pruebas en rojo". Los comandos
#: encadenados de verdad usan `&&`, `||`, `;` o tubería; el salto de línea casi
#: siempre delimita datos, no comandos.
_CADENA = re.compile(r"\s*(?:&&|\|\||;|(?<!\|)\|(?!\|))\s*")


def clasificar_bash(comando: str, respuesta: str) -> dict[str, Any] | None:
    """Decide si un comando de shell deja huella. Función pura.

    **Clasifica por segmentos, no por el primer token.** En uso real casi toda
    llamada a Bash del agente es compuesta —``cd /repo && git commit -m …``— y
    mirar solo el principio descartaba el comando entero por empezar con `cd`.
    Eso se comió commits, corridas de pruebas e instalaciones en la primera
    prueba de humo real; la prueba sintética no lo vio porque pasaba comandos
    sueltos. Se descarta solo si **todos** los segmentos son triviales.

    Se apoya en la respuesta solo para distinguir prueba en verde de prueba en
    rojo: el resto se deduce del comando. Nunca se guarda la salida completa.
    """
    if not comando or not comando.strip():
        return None

    segmentos = [s for s in _CADENA.split(comando) if s and s.strip()]
    if len(segmentos) > 1:
        for segmento in segmentos:
            resultado = _clasificar_segmento(segmento, respuesta)
            if resultado is not None:
                return resultado
        return None
    return _clasificar_segmento(comando, respuesta)


def _clasificar_segmento(comando: str, respuesta: str) -> dict[str, Any] | None:
    if _TRIVIAL.match(comando):
        return None

    if _GIT_COMMIT.search(comando):
        return {
            "event_type": "git_commit",
            "summary": f"Commit: {_mensaje_commit(comando)}",
            "importance": 2,
            "dedupe": f"commit:{_mensaje_commit(comando)}",
        }

    if _GIT_MERGE.search(comando):
        accion = _GIT_MERGE.search(comando).group(1)
        return {"event_type": "git_branch", "summary": f"Git {accion} ejecutado",
                "importance": 2, "dedupe": f"git:{accion}:{comando[:60]}"}

    m = _GIT_RAMA.search(comando)
    if m:
        return {"event_type": "git_branch", "summary": f"Rama de trabajo: {m.group(1)}",
                "importance": 3, "dedupe": f"rama:{m.group(1)}"}

    if _PRUEBAS.search(comando):
        fallo = bool(_FALLO.search(respuesta or ""))
        # Una prueba en verde solo se registra si cierra un fallo previo; en
        # solitario es la clase de ruido que entierra lo que sí importa.
        if not fallo:
            if not _EXITO.search(respuesta or ""):
                return None
            return {
                "event_type": "error_resolved",
                "summary": f"Pruebas en verde: {_recortar(comando, 90)}",
                "importance": 3,
                "dedupe": f"test-ok:{_recortar(comando, 60)}",
            }
        return {
            "event_type": "test_failed",
            "summary": f"Pruebas en rojo: {_recortar(comando, 90)}",
            "details": {"señal": _recortar((_FALLO.search(respuesta or "") or [""])[0], 120)},
            "importance": 2,
            "dedupe": f"test-fail:{_recortar(comando, 60)}",
        }

    if _DEPENDENCIAS.search(comando):
        return {"event_type": "dependency_changed",
                "summary": f"Dependencias: {_recortar(comando, 120)}",
                "importance": 2, "dedupe": f"dep:{_recortar(comando, 80)}"}

    return None


def clasificar_archivo(ruta: str, herramienta: str) -> dict[str, Any] | None:
    """Un cambio de archivo relevante. Los artefactos y cachés se descartan."""
    if not ruta or _RUTA_IRRELEVANTE.search(ruta.replace("\\", "/")):
        return None
    nombre = Path(ruta).name
    tipo = "configuration_changed" if _CONFIG.search(nombre) else "file_modified"
    return {
        "event_type": tipo,
        "summary": f"{'Creó' if herramienta == 'Write' else 'Modificó'} {nombre}",
        "file_path": ruta,
        "importance": 2 if tipo == "configuration_changed" else 3,
        # Deduplicado por archivo: veinte ediciones al mismo archivo en una sesión
        # son un hecho ("se trabajó en X"), no veinte.
        "dedupe": f"file:{ruta}",
    }


# ─────────────────────────────────────────
# Prompts del usuario
# ─────────────────────────────────────────

#: Marcadores de decisión o corrección. Solo estos prompts se capturan.
_MARCADOR = re.compile(
    r"\b(no,|en realidad|corrige|correccion|corrigiendo|equivocado|esta mal|"
    r"mejor usa|usa .{1,30} en vez de|en lugar de|decidimos|decidido|aprobado|"
    r"apruebo|autorizado|rechazo|no hagas|nunca (hagas|uses)|siempre (haz|usa)|"
    r"a partir de ahora|de ahora en adelante|recuerda que|ten en cuenta que|"
    r"actually|instead of|don't|never do|always do|approved|corrected)\b",
    re.IGNORECASE,
)
#: Correcciones de criterio jurídico: mismo patrón estrecho que el importador.
_CRITERIO = re.compile(
    r"(la via correcta es|no es (la via|apelacion|procedente)|criterio (PJF|de Fabian)|"
    r"correccion (clave|de criterio))",
    re.IGNORECASE,
)


def _sin_acentos(texto: str) -> str:
    """Quita diacríticos solo para comparar; el texto guardado conserva los suyos.

    En la práctica se escribe "la via correcta" tan a menudo como "la vía
    correcta", y un patrón que exija la tilde deja pasar la mitad de las
    correcciones de criterio. Mismo criterio que el tokenizador FTS del índice.
    """
    descompuesto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


# ─────────────────────────────────────────
# Procedencia del prompt
# ─────────────────────────────────────────

#: Marcas de contenido que llega por el canal del prompt sin haberlo escrito el
#: operador: informes de subagentes, notificaciones del arnés, mensajes entre
#: sesiones, canales externos y comandos expandidos.
#:
#: **Por qué existe.** ``UserPromptSubmit`` no distingue quién escribió el
#: texto. En la base real (1-oct-2026), de 21 eventos de corrección, 14 eran informes de
#: subagentes que contenían "a partir de ahora" o "recuerda que" y se
#: reinyectaban en cada arranque como si fueran criterio del operador (regla
#: absoluta 6). Un marcador de decisión solo significa algo si lo escribió el
#: humano: por eso la procedencia se mira **antes** que los marcadores.
#:
#: Los mensajes de canales externos (Telegram) quedan en **cuarentena**: pueden
#: venir de cualquiera que alcance el bot y nunca se capturan como corrección.
#: Cada entrada lleva el motivo que se anota en la bitácora; nunca el contenido.
_NO_HUMANO: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mensaje de subagente", re.compile(r"<agent-message\b", re.IGNORECASE)),
    ("informe de subagente", re.compile(r"\[Subagent hand-back\]", re.IGNORECASE)),
    ("notificación de tarea", re.compile(r"<task-notification\b", re.IGNORECASE)),
    ("recordatorio del sistema", re.compile(r"<system-reminder\b", re.IGNORECASE)),
    ("notificación del sistema", re.compile(r"\[SYSTEM NOTIFICATION", re.IGNORECASE)),
    ("mensaje entre sesiones", re.compile(r"<cross-session-message\b", re.IGNORECASE)),
    ("canal externo en cuarentena", re.compile(r"<channel\s+source\s*=", re.IGNORECASE)),
    ("comando expandido", re.compile(r"<command-(?:name|message)\b", re.IGNORECASE)),
)

#: Bloque pegado completo: ``<pasted_content …>…</pasted_content …>``.
_PEGADO = re.compile(
    r"<pasted_content\b[^>]*>.*?</pasted_content\b[^>]*>", re.IGNORECASE | re.DOTALL
)
#: Bloque pegado sin cierre: se considera pegado hasta el final del texto. Cubre
#: el prompt cortado y, sobre todo, el resumen ya guardado, que ``MAX_RESUMEN``
#: pudo recortar antes de la etiqueta de cierre.
_PEGADO_ABIERTO = re.compile(r"<pasted_content\b.*\Z", re.IGNORECASE | re.DOTALL)


def _tiene_pegado(texto: str) -> bool:
    return "<pasted_content" in texto.lower()


def texto_de_usuario(texto: str) -> str:
    """El texto que escribió el operador, sin los bloques pegados. Función pura.

    Lo pegado es de terceros —un escrito de la contraparte, un informe, un
    correo— aunque llegue en el prompt del operador: sus "a partir de ahora" no
    son decisiones de nadie en este proyecto. Se elimina cada bloque
    ``<pasted_content …>…</pasted_content …>`` y, si queda uno sin cerrar, todo
    lo que sigue a su apertura. Sin bloques pegados el texto se devuelve intacto.
    """
    if not texto or not _tiene_pegado(texto):
        return texto or ""
    sin_bloques = _PEGADO_ABIERTO.sub(" ", _PEGADO.sub(" ", texto))
    return sin_bloques.strip()


def procedencia_no_humana(texto: str) -> str | None:
    """Motivo por el que el texto no es del operador, o ``None`` si lo es. Pura.

    Se aplica al texto propio del usuario (``texto_de_usuario``): una marca
    dentro de un bloque pegado es contenido de terceros que el operador decidió
    pegar, no un mensaje del arnés. Un prompt que, quitado lo pegado, se queda
    sin texto propio suficiente tampoco es del operador.

    No hay corte por longitud: un informe largo no es sospechoso por largo, sino
    por su procedencia, y una corrección larga del operador sigue siendo suya.

    Reutilizable sobre texto ya guardado (``memoria_cli.py olvidar
    --procedencia-no-humana``): el resumen persistido conserva el principio del
    prompt, que es donde viven estas marcas.
    """
    if not texto:
        return None
    propio = texto_de_usuario(texto)
    for motivo, patron in _NO_HUMANO:
        if patron.search(propio):
            return motivo
    if _tiene_pegado(texto) and len(propio.strip()) < MIN_PROMPT:
        return "contenido pegado sin texto propio"
    return None


def clasificar_prompt(texto: str) -> dict[str, Any] | None:
    """Captura solo prompts del operador que expresan una decisión o corrección.

    **Por qué es tan restrictivo.** Un prompt de este proyecto puede contener un
    expediente con datos de cliente. Guardar todos sería desproporcionado y
    chocaría con el espíritu de la regla absoluta #8, así que se capturan solo
    los que llevan un marcador explícito de decisión, recortados a
    ``MAX_RESUMEN`` y pasados por el redactor.

    **Procedencia primero.** Antes de buscar marcadores se descarta lo que no
    escribió el operador (``procedencia_no_humana``) y se clasifica solo su
    texto propio (``texto_de_usuario``): lo pegado ni dispara la captura ni se
    guarda.

    Desactivable por completo con ``ITOSTURRE_MEMORIA_PROMPTS=off``.
    """
    if (os.getenv(ENV_PROMPTS) or "on").strip().lower() in ("0", "off", "false", "no"):
        return None
    if not texto or procedencia_no_humana(texto):
        return None
    propio = texto_de_usuario(texto)
    if len(propio.strip()) < MIN_PROMPT:
        return None
    plano = _sin_acentos(propio)
    if _CRITERIO.search(plano):
        tipo, importancia = "correccion_criterio_pjf", 1
    elif _MARCADOR.search(plano):
        tipo, importancia = "user_correction", 1
    else:
        return None
    return {
        "event_type": tipo,
        "summary": _recortar(propio),
        "importance": importancia,
        "dedupe": f"prompt:{_recortar(propio, 120)}",
    }


# ─────────────────────────────────────────
# Despacho
# ─────────────────────────────────────────

def clasificar(payload: Mapping[str, Any], evento: str) -> dict[str, Any] | None:
    """Traduce el payload de un hook a un evento de memoria, o ``None`` si se descarta."""
    if evento == "UserPromptSubmit":
        return clasificar_prompt(str(payload.get("prompt") or ""))

    if evento in ("PostToolUse", "PostToolUseFailure"):
        herramienta = str(payload.get("tool_name") or "")
        entrada = payload.get("tool_input") or {}
        if not isinstance(entrada, Mapping):
            return None

        if herramienta in ("Write", "Edit", "NotebookEdit"):
            return clasificar_archivo(str(entrada.get("file_path") or ""), herramienta)

        if herramienta in ("Bash", "PowerShell"):
            respuesta = payload.get("tool_response")
            texto_resp = json.dumps(respuesta, ensure_ascii=False)[:4000] if respuesta else ""
            resultado = clasificar_bash(str(entrada.get("command") or ""), texto_resp)
            if resultado and evento == "PostToolUseFailure":
                resultado["event_type"] = "error_detected"
                resultado["summary"] = "Falló: " + resultado["summary"]
                resultado["importance"] = 2
            return resultado

    return None


def procesar(payload: Mapping[str, Any], evento: str, *, raiz: str | os.PathLike[str]) -> dict:
    """Clasifica y persiste. **Nunca lanza** (etapa 7G).

    Devuelve un diccionario de diagnóstico con lo ocurrido: qué evento, qué se
    hizo, por qué se descartó y cuánto tardó (etapa 7K).
    """
    inicio = time.perf_counter()
    diag: dict[str, Any] = {"evento": evento, "hook": "memoria", "accion": "descartado"}
    try:
        if not habilitado():
            diag["motivo"] = "hooks desactivados (ITOSTURRE_MEMORIA_HOOKS)"
            return diag

        propuesta = clasificar(payload, evento)
        if propuesta is None:
            # El descarte por procedencia se anota con su motivo (nunca con el
            # texto): es lo que permite auditar en hooks.log que un informe de
            # subagente o un mensaje de canal no entró como corrección.
            motivo = None
            if evento == "UserPromptSubmit":
                motivo = procedencia_no_humana(str(payload.get("prompt") or ""))
            diag["motivo"] = f"procedencia {motivo}" if motivo else "sin valor persistente"
            return diag

        # SQLite solo se importa cuando de verdad hay algo que guardar: el camino
        # de descarte, que es la inmensa mayoría, no paga ese coste.
        from .store import MemoriaStore

        dedupe = propuesta.pop("dedupe", None)
        with MemoriaStore(raiz=raiz, session_id=payload.get("session_id") or None) as store:
            fila = store.record(
                propuesta.pop("event_type"),
                propuesta.pop("summary"),
                dedupe_key=dedupe,
                **propuesta,
            )
        diag["accion"] = "almacenado"
        diag["tipo"] = fila.get("event_type")
        diag["redactado"] = bool(fila.get("redacted"))
    except Exception as e:  # noqa: BLE001 — frontera de fallo seguro
        diag["accion"] = "error"
        diag["error"] = f"{type(e).__name__}: {e}"[:200]
    finally:
        diag["ms"] = round((time.perf_counter() - inicio) * 1000, 2)
    return diag


# ─────────────────────────────────────────
# Bitácora (etapa 7K)
# ─────────────────────────────────────────

def ruta_log() -> Path:
    explicita = os.getenv(ENV_LOG)
    if explicita:
        return Path(explicita).expanduser()
    return Path.home() / ".itosturre" / "memoria" / "hooks.log"


def registrar_diagnostico(diag: Mapping[str, Any]) -> None:
    """Escribe una línea JSON de diagnóstico. Silencioso ante cualquier fallo.

    El diccionario pasa por el redactor antes de escribirse: una bitáracora de
    depuración es exactamente donde un token acabaría filtrándose si nadie lo
    impidiera (etapa 7H).
    """
    try:
        destino = ruta_log()
        destino.parent.mkdir(parents=True, exist_ok=True)
        if destino.exists() and destino.stat().st_size > MAX_LOG_BYTES:
            destino.replace(destino.with_suffix(".log.1"))
        limpio, _ = redactar(dict(diag))
        limpio["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with destino.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(limpio, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — la bitácora nunca puede romper un hook
        pass
