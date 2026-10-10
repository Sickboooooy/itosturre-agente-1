"""
vigilancia_jurisprudencial.py — Módulo de Vigilancia Jurisprudencial · Itosturre

Consulta el microservicio oficial del SJF sobre 5 temas de defensa fiscal:
  1. Cancelación/restricción de CSD (arts. 17-H y 17-H Bis CFF)
  2. Art. 69-B CFF — Operaciones inexistentes
  3. Suspensión en amparo fiscal
  4. Materialidad de operaciones
  5. Facultades de comprobación

Flujo por tema:
  POST /tesis → lista con IUS → GET /tesis/{ius} → ficha JSON completa

Protocolo Itosturre (innegociable):
  - TODOS los datos de localización (IUS, época, sala, fecha, tipo) vienen
    ÚNICAMENTE del JSON de la API.  El LLM SOLO redacta el análisis sobre
    esos datos. Si la API no devuelve un campo, viaja vacío y marcado ⚠️.
  - El hash SHA-256 se captura por criterio (cadena de custodia).
  - Sin ANTHROPIC_API_KEY: modo degradado — datos crudos, sin análisis LLM.
  - Un tema cuya búsqueda NO PUDO CONSULTARSE (SOURCE_UNAVAILABLE/TIMEOUT/
    PARSER_ERROR) se reporta como tal — NUNCA como "sin criterios esta semana".
    Confundir "no hubo novedades" con "no pude consultar la fuente" es el
    error de fondo que este módulo existe para evitar (docs/SJF_OPERATIVA.md).

Endpoints (microservicio oficial, público, sin WAF ni navegador):
  BASE: https://sjf2.scjn.gob.mx/services/sjftesismicroservice/api/public
  POST /tesis           — búsqueda (body JSON)
  POST /tesis/ids       — solo IUS para iterar
  GET  /tesis/{ius}     — ficha completa JSON

Rate: 1 req/seg + retry exponencial (2 s, 4 s, 8 s) — salvo que el error se
clasifique como bloqueo de política de red del entorno, en cuyo caso NO se
reintenta ni se consultan los temas restantes: fallarían igual en el mismo
entorno (ver itosturre.vigilancia.contrato.es_bloqueo_politica).

Salidas en salidas/Jurisprudencia/ (raíz: $ITOSTURRE_SALIDA): el informe
semana-YYYY-Www.md, las fichas crudas con su SHA-256 en semana-YYYY-Www.json y
el estado de la corrida en semana-YYYY-Www.estado.json.

Contrato de salida (itosturre/vigilancia/rutina.py):
  0 → informe escrito: OK, o PARCIAL si algún tema no se pudo consultar (❌).
  2 → ningún tema respondió: NO se escribe informe — queda el estado con la
      causa y una corrida posterior de la misma semana puede reintentar.

Uso:
    python agentes/vigilancia_jurisprudencial.py
"""

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import requests

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from itosturre.vigilancia import (  # noqa: E402
    PARSER_ERROR,
    SOURCE_UNAVAILABLE,
    SUCCESS,
    ResultadoFuente,
    clasificar_excepcion_red,
    es_bloqueo_politica,
    guardar_sidecar,
    registrar_evento,
    rutina,
)

# ── Rutas ─────────────────────────────────────────────────────────────────────

OUTPUT_DIR = rutina.SALIDA_DIR / "Jurisprudencia"
TODAY = rutina.hoy_mx()
FECHA_INICIO = TODAY - timedelta(days=7)   # ventana "última semana" (criterios nuevos)
YEAR, WEEK_NUM, _ = TODAY.isocalendar()
WEEK_STR = f"{YEAR}-W{WEEK_NUM:02d}"
OUTPUT_FILE = OUTPUT_DIR / f"semana-{WEEK_STR}.md"

# ── Configuración API SJF ─────────────────────────────────────────────────────

SJF_API = "https://sjf2.scjn.gob.mx/services/sjftesismicroservice/api/public"
SJF_DETAIL_WEB = "https://sjf2.scjn.gob.mx/detalle/tesis"
# NO se hardcodea idEpoca: la vigente es la DUODÉCIMA (no la Undécima). La barrida
# cubre todas las épocas y se filtra por ventana de fecha de publicación; cada ficha
# guarda su época como metadato. No se excluye Undécima/Décima (siguen obligatorias
# si no están superadas). El catálogo de épocas vive en /tesis/epocas (contrato por
# documentar con el skill scjn-api).
TAMANO_PAGINA = 10      # resultados por búsqueda (max 100)
MAX_DETALLE = 8         # fichas completas máximas por tema

HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    # Origin + Referer son OBLIGATORIOS: sin ellos el microservicio responde
    # 403 "Acceso denegado: Formato inválido" (verificado en vivo). No es WAF
    # anti-bot — es validación de origen; con estos headers responde JSON normal.
    "Origin": "https://sjf2.scjn.gob.mx",
    "Referer": "https://sjf2.scjn.gob.mx/busqueda-principal-tesis",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "es-MX,es;q=0.9",
}

# 5 temas de defensa fiscal
TEMAS = [
    {
        "id": "csd",
        "label": "Arts. 17-H / 17-H Bis CFF — Cancelación y restricción de CSD",
        "expresion": "cancelación restricción certificado sello digital 17-H",
    },
    {
        "id": "69b",
        "label": "Art. 69-B CFF — Operaciones inexistentes",
        "expresion": "operaciones inexistentes 69-B",
    },
    {
        "id": "suspension",
        "label": "Suspensión en amparo fiscal",
        "expresion": "suspensión amparo fiscal contribuyente",
    },
    {
        "id": "materialidad",
        "label": "Materialidad de operaciones",
        "expresion": "materialidad operaciones actos jurídicos",
    },
    {
        "id": "facultades",
        "label": "Facultades de comprobación",
        "expresion": "facultades comprobación SAT revisión",
    },
]


# ── HTTP con rate-limit y retry exponencial (con corte ante bloqueo de política) ─

_LAST_REQUEST: float = 0.0


def _throttle() -> None:
    """Garantiza mínimo 1 segundo entre peticiones."""
    global _LAST_REQUEST
    elapsed = time.monotonic() - _LAST_REQUEST
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _LAST_REQUEST = time.monotonic()


@dataclass
class _HttpOutcome:
    """Resultado de _http(): `response` es None solo cuando NINGÚN intento obtuvo
    respuesta — en ese caso status/retryable/error describen por qué, ya
    clasificados (ver clasificar_excepcion_red)."""

    response: Optional[requests.Response]
    status: str = SUCCESS
    retryable: bool = False
    error: str = ""
    bloqueo_politica: bool = False


def _http(method: str, url: str, **kwargs) -> _HttpOutcome:
    """
    Petición HTTP con throttle + retry exponencial 2s/4s/8s.
    Si la respuesta es 429 (Too Many Requests), siempre reintenta.
    Si la excepción se clasifica como bloqueo de política de red del entorno
    (ver clasificar_excepcion_red), NO reintenta — sería gastar 14 s en algo
    que reintentar en el mismo entorno nunca resuelve.
    """
    delays = [2, 4, 8]
    ultimo = _HttpOutcome(response=None, status="UNKNOWN_ERROR", retryable=True, error="sin intentos realizados")
    for attempt, backoff in enumerate([0] + delays):
        if backoff:
            print(f"      ↩ reintento {attempt}/{len(delays)} en {backoff} s...")
            time.sleep(backoff)
        _throttle()
        try:
            resp = requests.request(method, url, headers=HEADERS, timeout=20, **kwargs)
            if resp.status_code == 429:
                ultimo = _HttpOutcome(response=None, status="TIMEOUT", retryable=True, error="HTTP 429 (rate limit)")
                continue
            return _HttpOutcome(response=resp)
        except requests.RequestException as exc:
            status, retryable, mensaje = clasificar_excepcion_red(exc)
            print(f"      ⚠ conexión: {mensaje}")
            ultimo = _HttpOutcome(
                response=None, status=status, retryable=retryable, error=mensaje,
                bloqueo_politica=es_bloqueo_politica(exc),
            )
            if not retryable:
                break
    return ultimo


# ── Consulta microservicio SJF ────────────────────────────────────────────────

# Clasificadores del buscador OFICIAL, capturados por interceptación del sitio
# sjf2.scjn.gob.mx (16-Jun-2026). idEpoca: códigos internos de las épocas recientes
# (210/200/100/5 — NO "11"; cubre Duodécima/Undécima/Décima/Novena). tipoDocumento
# "1" = tesis. Sin estos clasificadores el POST devuelve toda la base (311k) sin filtrar.
SJF_CLASSIFIERS = [
    {"name": "idEpoca", "value": ["210", "200", "100", "5"], "allSelected": False, "visible": False, "isMatrix": False},
    {"name": "numInstancia", "value": ["6", "60", "7", "70", "80", "1", "2", "50"], "allSelected": False, "visible": False, "isMatrix": False},
    {"name": "tipoDocumento", "value": ["1"], "allSelected": False, "visible": False, "isMatrix": False},
]


def _search_body(expresion: str) -> dict:
    """Body del POST /tesis con el contrato real (classifiers + searchTerms)."""
    return {
        "classifiers": SJF_CLASSIFIERS,
        "searchTerms": [{
            "expression": expresion,
            "fields": ["localizacionBusqueda", "rubro", "texto"],
            "operator": 0,
            "operatorUser": "Y",
            "lsFields": [],
            "esInicial": True,
            "esNRD": False,
        }],
        "bFacet": True,
    }


def buscar_tesis(expresion: str) -> tuple[Optional[list[int]], Optional[dict]]:
    """
    Búsqueda con el CONTRATO REAL del buscador oficial: POST /tesis?page=0&size=N,
    body con classifiers + searchTerms (keyword en expression sobre
    localizacionBusqueda/rubro/texto). La paginación va en la URL, no en el body.

    Devuelve (ids, None) si la búsqueda se pudo ejecutar (ids puede ser [] si
    genuinamente no hay resultados). Devuelve (None, info_error) si la fuente NO
    pudo consultarse: None ≠ [] — "no pude preguntar" no es "no hay nada".
    """
    outcome = _http("POST", f"{SJF_API}/tesis?page=0&size={TAMANO_PAGINA}", json=_search_body(expresion))
    if outcome.response is None:
        return None, {
            "status": outcome.status, "retryable": outcome.retryable, "error": outcome.error,
            "bloqueo_politica": outcome.bloqueo_politica,
        }
    if not outcome.response.ok:
        return None, {
            "status": SOURCE_UNAVAILABLE,
            "retryable": outcome.response.status_code >= 500,
            "error": f"HTTP {outcome.response.status_code} en POST /tesis",
        }
    try:
        docs = outcome.response.json().get("documents", [])
        ids = [int(d["ius"]) for d in docs if str(d.get("ius", "")).isdigit()][:TAMANO_PAGINA]
        return ids, None
    except (ValueError, TypeError, AttributeError) as exc:
        return None, {"status": PARSER_ERROR, "retryable": False, "error": f"respuesta no parseable: {exc}"}


def _campo(data: dict, *keys, default: str = "") -> str:
    """Extrae el primer key que exista con valor no vacío; retorna default si ninguno."""
    for k in keys:
        val = data.get(k)
        if val is not None and str(val).strip():
            return str(val).strip()
    return default


def clasificar(ta_tj, tipo: str, formas: list) -> str:
    """
    Clasifica por ta_tj (0=tesis aislada, 1=jurisprudencia) + tipoTesis (texto
    real, p.ej. "Tesis Aisladas"/"Jurisprudencia") + formasIntegracion. NO asume
    códigos "J"/"TA" (el API no los usa en la ficha de detalle). Una jurisprudencia
    obligatoria requiere una forma de integración válida.
    """
    nombres = [
        str(f.get("formaIntegracion", f) if isinstance(f, dict) else f)
        for f in (formas or [])
    ]
    FORMAS_OBLIGATORIAS = {
        "Reiteración de criterios",
        "Contradicción de tesis",
        "Sustitución de jurisprudencia",
        "Unificación de criterios",
    }
    t = (tipo or "").lower()
    es_juris = (ta_tj == 1) or ("jurisprudencia" in t)
    es_aislada = (ta_tj == 0) or ("aislada" in t)
    if es_juris:
        if any(n in FORMAS_OBLIGATORIAS for n in nombres):
            return "Jurisprudencia obligatoria"
        if nombres:
            return f"Jurisprudencia ({', '.join(nombres)})"
        return "Jurisprudencia (forma de integración ⚠️ no especificada)"
    if es_aislada:
        return "Tesis aislada"
    return "⚠️ tipo no disponible" if not tipo else f"Otro — {tipo}"


def _en_ventana(fecha_pub: str) -> bool:
    """True si fechaPublicacion cae en la última semana (criterio 'nuevo').
    Solo MARCA; no excluye nada — las fichas fuera de ventana se conservan."""
    if not fecha_pub:
        return False
    try:
        norm = fecha_pub.replace("Z", "").replace("T", " ")[:10]
        return datetime.strptime(norm, "%Y-%m-%d").date() >= FECHA_INICIO
    except (ValueError, TypeError):
        return False


def obtener_detalle(ius: int) -> dict[str, Any]:
    """
    GET /tesis/{ius} → ficha completa en JSON.
    Normaliza campos; los ausentes quedan "" (nunca se inventan).
    """
    outcome = _http("GET", f"{SJF_API}/tesis/{ius}")
    resp = outcome.response
    if resp is None or not resp.ok:
        detalle = outcome.error if resp is None else f"HTTP {resp.status_code}"
        return {"ius": ius, "_error": detalle}
    body_bytes = resp.content  # cuerpo crudo de la respuesta HTTP (para custodia)
    try:
        raw: dict = resp.json()
    except ValueError:
        return {"ius": ius, "_error": "JSON inválido"}

    # CADENA DE CUSTODIA: el API NO devuelve campo de hash (verificado contra las
    # 37 claves reales de la ficha). Se COMPUTA SHA-256 sobre los bytes crudos del
    # response body de GET /tesis/{ius}. Reproducible:
    #     hashlib.sha256(requests.get(url, headers=...).content).hexdigest()
    sha = hashlib.sha256(body_bytes).hexdigest()

    formas_integracion = raw.get("formasIntegracion") or []
    ta_tj = raw.get("ta_tj")  # 0 = tesis aislada, 1 = jurisprudencia
    tipo_texto = _campo(raw, "tipoTesis", "tipo", "tipoDecision")
    fecha_pub = _campo(raw, "fechaPublicacion", "fecha")

    return {
        # — Localización: SOLO de la API —
        "ius":               ius,
        "rubro":             _campo(raw, "rubro", "titulo", "denominacion"),
        "clave_tesis":       _campo(raw, "claveTesis"),
        "epoca":             _campo(raw, "epoca", "nombreEpoca"),
        # 'sala' viene como CÓDIGO interno (p.ej. 7 = TCC); la instancia es el texto.
        # No escribir "Sala N" para una instancia que es Tribunal Colegiado.
        "sala_codigo":       _campo(raw, "sala"),
        "instancia":         _campo(raw, "instancia", "sInstancia"),
        "tipo_raw":          tipo_texto,
        "ta_tj":             ta_tj,
        "tipo_clasificado":  clasificar(ta_tj, tipo_texto, formas_integracion),
        "formas_integracion": [
            str(f.get("formaIntegracion", f) if isinstance(f, dict) else f)
            for f in formas_integracion
        ],
        "fecha_publicacion": fecha_pub,
        # texto_publicacion trae VERBATIM la fecha de obligatoriedad (lunes sig.)
        "texto_publicacion": _campo(raw, "textoPublicacion"),
        "en_ventana_semana": _en_ventana(fecha_pub),
        "hash_sha256":       sha,
        # — Contenido (truncado para el prompt) —
        "texto":             (_campo(raw, "texto", "contenido") or "")[:1500],
        # — Localización auditable —
        "url_sjf":           f"{SJF_DETAIL_WEB}/{ius}",
        "url_api":           f"{SJF_API}/tesis/{ius}",
        # — Auditoría —
        "_raw_keys":         list(raw.keys()),
    }


# ── Orquestación ──────────────────────────────────────────────────────────────

def _tema_fallido(status: str, retryable: bool, errores: list[str]) -> dict:
    return {"status": status, "retryable": retryable, "errors": errores, "fichas": []}


def consultar_todos() -> dict[str, dict]:
    """Flujo completo: búsqueda → IUS → ficha completa para los 5 temas.

    Cada tema queda con status SUCCESS (búsqueda ejecutada — 'fichas' puede
    estar vacía si genuinamente no hubo resultados) o con el status/errors que
    explican por qué NO hay criterio verificado: la búsqueda falló, o devolvió
    IUS pero ninguna ficha se pudo leer. Ante un bloqueo de política de red los
    temas restantes no se consultan (fallarían igual) y quedan marcados."""
    resultado: dict[str, dict] = {}
    for i, tema in enumerate(TEMAS):
        print(f"    🔎 {tema['label'][:65]}...")
        registrar_evento("source_requested", source="SJF", tema=tema["id"])
        ids, error_info = buscar_tesis(tema["expresion"])
        if ids is None:
            print(f"       ❌ {error_info['status']} — {error_info['error']}")
            registrar_evento(
                "source_unavailable", source="SJF", tema=tema["id"],
                status=error_info["status"], retryable=error_info["retryable"],
            )
            resultado[tema["label"]] = _tema_fallido(
                error_info["status"], error_info["retryable"], [error_info["error"]]
            )
            if error_info.get("bloqueo_politica"):
                for resto in TEMAS[i + 1:]:
                    registrar_evento(
                        "source_unavailable", source="SJF", tema=resto["id"],
                        status=error_info["status"], retryable=False, omitido=True,
                    )
                    resultado[resto["label"]] = _tema_fallido(error_info["status"], False, [
                        f"no consultado: bloqueo de política de red detectado en el tema "
                        f"'{tema['id']}' (mismo entorno)"
                    ])
                break
            continue
        print(f"       → {len(ids)} IUS obtenidos")
        registrar_evento("source_success", source="SJF", tema=tema["id"], n_ids=len(ids))
        fichas = []
        for ius in ids[:MAX_DETALLE]:
            print(f"         GET /tesis/{ius}")
            fichas.append(obtener_detalle(ius))
        errores = [f"detalle IUS {f['ius']}: {f['_error']}" for f in fichas if f.get("_error")]
        if fichas and len(errores) == len(fichas):
            # Hubo IUS pero ninguna ficha legible: no hay criterio verificado.
            resultado[tema["label"]] = {
                "status": SOURCE_UNAVAILABLE, "retryable": True, "errors": errores, "fichas": fichas,
            }
        else:
            resultado[tema["label"]] = {
                "status": SUCCESS, "retryable": False, "errors": errores, "fichas": fichas,
            }
    return resultado


def contrato_tema(label: str, tema: dict) -> ResultadoFuente:
    """ResultadoFuente del tema: solo las fichas legibles cuentan como hallazgos."""
    validas = [f for f in tema["fichas"] if not f.get("_error")]
    return ResultadoFuente(
        source=f"SJF:{label}",
        status=tema["status"],
        items=validas if tema["status"] == SUCCESS else [],
        errors=tema["errors"],
        retryable=tema["retryable"],
    )


# ── Generación del informe ────────────────────────────────────────────────────

# Inyectada literalmente en el prompt — el LLM no puede ignorarla
_PROHIBICION_LLM = """\
REGLA ABSOLUTA — Protocolo Itosturre (no negociable):
1. Tienes PROHIBIDO completar, inferir o rellenar ningún campo de localización
   (IUS, época, sala, fecha, tipo, hash) más allá de lo que figura en el JSON.
2. Si un campo viene vacío "" o ausente, escribe exactamente: ⚠️ no disponible
3. Tu única tarea es redactar el resumen prose y el análisis estratégico
   usando EXCLUSIVAMENTE los valores que el JSON te proporciona.
4. Nunca afirmes que un criterio es "de esta semana" si fechaPublicacion no
   aparece en el JSON.
5. Copia los valores de IUS, época, sala, fecha y hash textualmente del JSON.
   No los reformules ni los inventes.
6. Un tema cuyo "status" no sea "SUCCESS" NO tuvo búsqueda válida: escribe
   exactamente "❌ Consulta fallida — no equivale a 'sin criterios'" y NUNCA
   "sin criterios esta semana" (son afirmaciones distintas: la segunda implica
   que sí se consultó).
7. Solo las fichas con "en_ventana_semana": true son criterios NUEVOS de la
   semana; las demás son contexto y van en la subsección "Contexto (fuera de
   ventana)". El órgano emisor es el campo "instancia" (texto); "sala_codigo"
   es un código interno — nunca lo escribas como "Sala N"."""


def redactar_informe_llm(resultados: dict[str, dict]) -> str:
    """
    Pasa el JSON completo a Claude para redacción del análisis.
    Todos los campos de localización vienen del JSON — el LLM solo escribe prose.
    """
    try:
        import anthropic
    except ImportError:
        return _informe_degradado(resultados, motivo="librería anthropic no instalada")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _informe_degradado(resultados, motivo="ANTHROPIC_API_KEY no configurada")

    client = anthropic.Anthropic(api_key=api_key)
    datos_str = json.dumps(resultados, ensure_ascii=False, indent=2)
    semana_inicio = TODAY - timedelta(days=TODAY.weekday())
    semana_fin = semana_inicio + timedelta(days=6)

    prompt = f"""{_PROHIBICION_LLM}

Eres el módulo de inteligencia jurisprudencial de Itosturre.
Semana: {WEEK_STR}  ({semana_inicio} al {semana_fin})
Fuente: microservicio oficial sjf2.scjn.gob.mx/services/sjftesismicroservice

JSON CON TODOS LOS TEMAS (única fuente de verdad — no inventes nada; cada tema
lleva su "status": SUCCESS con 'fichas', o un estado de error con 'errors'):
{datos_str}

Redacta el informe en Markdown con esta estructura exacta:

# Vigilancia Jurisprudencial SJF — {WEEK_STR}

## Resumen ejecutivo
[2-3 líneas: total criterios de temas con status SUCCESS, temas con mayor
actividad, implicación estratégica. Si algún tema quedó SOURCE_UNAVAILABLE,
dilo explícitamente aquí.]

## Criterios por tema

[Una sección ### por cada uno de los 5 temas.
- Si status != SUCCESS → escribe únicamente:
  "❌ Consulta fallida — no equivale a 'sin criterios'. Detalle: [errors del JSON]."
- Si status == SUCCESS y fichas está vacío → "Sin criterios esta semana."
- Si status == SUCCESS y hay fichas → "Nuevos esta semana" (en_ventana_semana
  true) y "Contexto (fuera de ventana)" (el resto), un bloque por criterio.]

Por cada criterio (solo temas con status SUCCESS), usa este bloque (copia los
valores del JSON, sin modificar):

---
**Registro IUS:** [del JSON — o ⚠️ no disponible]
**Rubro:** [del JSON — o ⚠️ no disponible]
**Clave:** [clave_tesis del JSON — o ⚠️ no disponible]
**Tipo:** [del JSON — Jurisprudencia obligatoria / Tesis aislada / Criterio orientador]
**Época:** [del JSON — o ⚠️ no disponible]
**Instancia/Órgano:** [instancia del JSON — o ⚠️ no disponible]
**Fecha publicación:** [del JSON — o ⚠️ no disponible]
**Publicación (verbatim SJF):** [texto_publicacion del JSON — o ⚠️ no disponible]
**Hash SHA-256:** [del JSON — o ⚠️ no disponible]
**URL SJF:** [del JSON]
**Síntesis:** [2-4 oraciones tuyas basadas en el campo texto del JSON]
---

## Impacto estratégico
[Por cada tema con status SUCCESS y criterios: ¿qué cambia en la estrategia
de defensa fiscal? Si no hay criterios nuevos: "Sin nuevos criterios en la
ventana de la última semana." Los temas SOURCE_UNAVAILABLE no se analizan.]

## Trazabilidad
- Microservicio: {SJF_API}
- Filtro: ventana de publicación {FECHA_INICIO} a {TODAY} (todas las épocas; época por ficha)
- Fecha de consulta: {TODAY}
- Módulo: vigilancia_jurisprudencial.py v3 — Itosturre"""

    try:
        resp = client.messages.create(
            model=rutina.modelo(),
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        print(f"  ⚠️ Error API Claude: {e}")
        return _informe_degradado(resultados, motivo=str(e))


def _marca(valor: str) -> str:
    return valor if valor else "⚠️ no disponible"


def _bloque_ficha(f: dict) -> list[str]:
    return [
        "---",
        f"**Registro IUS:** {_marca(str(f['ius']))}",
        f"**Rubro:** {_marca(f.get('rubro', '')[:120])}",
        f"**Clave:** {_marca(f.get('clave_tesis', ''))}",
        f"**Tipo:** {_marca(f.get('tipo_clasificado', ''))}",
        f"**Época:** {_marca(f.get('epoca', ''))}",
        # 'sala_codigo' es un código interno (p. ej. 7 = TCC): el órgano es 'instancia'.
        f"**Instancia/Órgano:** {_marca(f.get('instancia', ''))}",
        f"**Fecha publicación:** {_marca(f.get('fecha_publicacion', ''))}",
        f"**Publicación (verbatim SJF):** {_marca(f.get('texto_publicacion', ''))}",
        f"**Hash SHA-256:** {_marca(f.get('hash_sha256', ''))}",
        f"**URL SJF:** {f.get('url_sjf', '')}",
        "",
    ]


def _informe_degradado(resultados: dict[str, dict], motivo: str = "") -> str:
    """Modo degradado: datos crudos de la API, sin análisis LLM."""
    semana_inicio = TODAY - timedelta(days=TODAY.weekday())
    semana_fin = semana_inicio + timedelta(days=6)
    lines = [
        f"# Vigilancia Jurisprudencial SJF — {WEEK_STR}",
        "",
        f"> ⚠️ Modo degradado — sin análisis LLM ({motivo})",
        "> Datos íntegros de la API, sin redacción automatizada.",
        f"> Semana: {semana_inicio} al {semana_fin}",
        "",
    ]
    validas = [f for v in resultados.values() for f in v["fichas"] if not f.get("_error")]
    nuevas = sum(1 for f in validas if f.get("en_ventana_semana"))
    fallidos = [label for label, v in resultados.items() if v["status"] != SUCCESS]
    lines += [
        f"**Total fichas recuperadas:** {len(validas)} · **Nuevas en la ventana "
        f"{FECHA_INICIO} a {TODAY}:** {nuevas}",
        "",
    ]
    if fallidos:
        lines += [f"> ❌ {len(fallidos)} tema(s) sin consultar — ver cada sección.", ""]

    for label, tema in resultados.items():
        lines += [f"## {label}", ""]
        if tema["status"] != SUCCESS:
            lines += [
                f"❌ **Consulta fallida ({tema['status']})** — no equivale a \"sin criterios\".",
                f"- Reintentable: {'sí' if tema['retryable'] else 'no'}",
                f"- Detalle: {'; '.join(tema['errors']) or 'sin detalle'}",
                "",
            ]
            continue
        fichas = tema["fichas"]
        if not fichas:
            lines += ["Sin criterios encontrados (búsqueda ejecutada).", ""]
            continue
        for f in fichas:
            if f.get("_error"):
                lines += [f"- IUS {f['ius']}: ❌ {f['_error']}", ""]
        legibles = [f for f in fichas if not f.get("_error")]
        en_ventana = [f for f in legibles if f.get("en_ventana_semana")]
        fuera = [f for f in legibles if not f.get("en_ventana_semana")]
        lines += ["### Nuevos esta semana", ""]
        if not en_ventana:
            lines += ["Sin criterios publicados en la ventana.", ""]
        for f in en_ventana:
            lines += _bloque_ficha(f)
        if fuera:
            lines += ["### Contexto (fuera de ventana)", ""]
            for f in fuera:
                lines += _bloque_ficha(f)

    lines += [
        "## Trazabilidad",
        f"- Microservicio: {SJF_API}",
        f"- Filtro: ventana de publicación {FECHA_INICIO} a {TODAY} (todas las épocas)",
        f"- Fecha de consulta: {TODAY}",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def dump_raw() -> int:
    """Imprime el JSON CRUDO del API (búsqueda + un detalle), SIN normalizar."""
    expr = TEMAS[1]["expresion"]  # 69-B
    print(f"# POST /tesis (contrato real) · expression='{expr}'")
    outcome = _http("POST", f"{SJF_API}/tesis?page=0&size=3", json=_search_body(expr))
    print((outcome.response.text if outcome.response is not None else f"(sin respuesta: {outcome.error})")[:1500])
    ids, _ = buscar_tesis(expr)
    ius = ids[0] if ids else None
    print(f"\n# GET /tesis/{ius}")
    if ius:
        d = _http("GET", f"{SJF_API}/tesis/{ius}")
        print((d.response.text if d.response is not None else f"(sin respuesta: {d.error})")[:2800])
    return 0


def main() -> int:
    if "--dump-raw" in sys.argv:
        return dump_raw()
    print(f"⚖️  Vigilancia Jurisprudencial SJF — {WEEK_STR}")
    rutina.validar_salida(OUTPUT_DIR)
    registrar_evento("watch_started", watch="sjf_jurisprudencia", semana=WEEK_STR)

    if OUTPUT_FILE.exists():
        # El estado de la corrida que escribió el informe se conserva tal cual.
        print(f"  ✅ Informe de la semana ya existe: {OUTPUT_FILE.name} — no se vuelve a consultar")
        return rutina.EXIT_OK

    registrar_evento("collector_started", watch="sjf_jurisprudencia")
    print("  📥 Consultando microservicio SJF (API REST, sin navegador)...")
    resultados = consultar_todos()
    contratos = {label: contrato_tema(label, tema) for label, tema in resultados.items()}
    temas = {label: r.resumen() for label, r in contratos.items()}

    exitosos = sum(1 for r in contratos.values() if r.ok)
    total_fichas = sum(len(r.items) for r in contratos.values())
    nuevas = sum(1 for r in contratos.values() for f in r.items if f.get("en_ventana_semana"))
    print(f"  📊 {exitosos}/{len(contratos)} temas consultados con éxito "
          f"({total_fichas} fichas, {nuevas} nuevas en la ventana)")

    if exitosos == 0:
        # Sin informe: uno escrito se leería como "sin criterios" y la guarda de
        # arriba bloquearía el reintento de la semana.
        ruta = rutina.registrar_estado(
            OUTPUT_DIR, OUTPUT_FILE.stem, rutina.FUENTE_INACCESIBLE, fuente="SJF", temas=temas,
        )
        print(f"  🛑 Sin informe: ningún tema del SJF pudo consultarse. Estado → {ruta}")
        return rutina.EXIT_FUENTE_INACCESIBLE

    print("  🤖 Redactando informe...")
    informe = redactar_informe_llm(resultados)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(informe, encoding="utf-8")
    ruta_json = guardar_sidecar(OUTPUT_FILE, contratos)
    estado = rutina.OK if exitosos == len(contratos) else rutina.PARCIAL
    ruta_estado = rutina.registrar_estado(
        OUTPUT_DIR, OUTPUT_FILE.stem, estado,
        informe=OUTPUT_FILE.name, fichas=total_fichas, nuevas_en_ventana=nuevas, temas=temas,
    )
    kb = OUTPUT_FILE.stat().st_size // 1024
    print(f"  💾 → {OUTPUT_FILE} ({kb} KB)")
    print(f"  💾 Fichas y contrato → {ruta_json}")
    print(f"  📋 Estado {estado} → {ruta_estado}")
    return rutina.codigo_salida(estado)


if __name__ == "__main__":
    sys.exit(main())
