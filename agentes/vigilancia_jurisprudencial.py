"""
vigilancia_jurisprudencial.py — Módulo de Vigilancia Jurisprudencial · Itosturre

Consulta el microservicio oficial del SJF sobre 5 temas de defensa fiscal:
  1. Cancelación/restricción de CSD (arts. 17-H y 17-H Bis CFF)
  2. Art. 69-B CFF — Operaciones inexistentes
  3. Suspensión en amparo fiscal
  4. Materialidad de operaciones
  5. Facultades de comprobación

Flujo por tema:
  POST /tesis (todas las páginas, de 100 en 100) → ficha por documento de la
  búsqueda → (opcional) GET /tesis/{ius} para el texto completo de las nuevas

Protocolo Itosturre (innegociable):
  - TODOS los datos de localización (IUS, época, sala, fecha, tipo) vienen
    ÚNICAMENTE del JSON de la API.  El LLM SOLO redacta el análisis sobre
    esos datos. Si la API no devuelve un campo, viaja vacío y marcado ⚠️.
  - El hash SHA-256 se captura por criterio (cadena de custodia): sobre el
    documento de la búsqueda en JSON canónico (hash_documento) y, si el detalle
    responde, también sobre los bytes del detalle.
  - Sin ANTHROPIC_API_KEY: modo degradado — datos crudos, sin análisis LLM.
  - Un tema cuya búsqueda NO PUDO CONSULTARSE (SOURCE_UNAVAILABLE/TIMEOUT/
    PARSER_ERROR) se reporta como tal — NUNCA como "sin criterios esta semana".
    Confundir "no hubo novedades" con "no pude consultar la fuente" es el
    error de fondo que este módulo existe para evitar (docs/SJF_OPERATIVA.md).

Endpoints (microservicio oficial, público). Verificado el 10-oct-2026: el POST
de búsqueda responde JSON y cada documento ya trae la localización completa
(rubro, clave, época, órgano, fecha y texto de publicación, [J]/[TA]); el GET de
detalle devuelve el desafío anti-bots de Incapsula (HTML). Por eso las fichas
salen de la búsqueda y el detalle es solo un extra (texto completo, formas de
integración): un intento por corrida, sin insistir ni evadir el control. La vía
con navegador del repo para el texto es services/itosturre-scraper (vvca_audit.ts).
  BASE: https://sjf2.scjn.gob.mx/services/sjftesismicroservice/api/public
  POST /tesis?page=N&size=100 — búsqueda paginada (body JSON)
  GET  /tesis/{ius}           — ficha completa JSON (hoy tras el anti-bots)

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
# Antes se pedían 10 resultados por relevancia y una tesis de la semana fuera de
# esos 10 no se veía; los temas tienen pocas decenas de resultados (10-oct-2026).
TAMANO_PAGINA = 100     # resultados por página (máximo del microservicio)
MAX_PAGINAS = 5         # tope por tema (500 resultados); si se alcanza, se declara "truncada"
MAX_DETALLE = 8         # detalles (texto completo) a intentar por corrida, solo tesis nuevas
MAX_CONTEXTO = 5        # fichas de contexto por tema en el informe; el resto queda en el .json

AVISO_SIN_RESULTADOS = (
    "la expresión de búsqueda no devuelve ningún resultado en el SJF (en ninguna de las "
    "épocas consultadas): no acredita ausencia de criterios — revisar la expresión del tema"
)

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
        # Decisión del operador (10-oct-2026): la expresión anterior, de 6 palabras
        # unidas por Y, daba 1 resultado en todo el SJF; esta da 21.
        "expresion": "certificado de sello digital",
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
        # Decisión del operador (10-oct-2026): "materialidad operaciones actos
        # jurídicos" daba 0 resultados en todo el SJF; esta da 30.
        "expresion": "materialidad operaciones",
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


def _error_busqueda(outcome: _HttpOutcome) -> Optional[dict]:
    """Error de una página de búsqueda, o None si la respuesta es utilizable."""
    if outcome.response is None:
        return {
            "status": outcome.status, "retryable": outcome.retryable, "error": outcome.error,
            "bloqueo_politica": outcome.bloqueo_politica,
        }
    if not outcome.response.ok:
        return {
            "status": SOURCE_UNAVAILABLE,
            "retryable": outcome.response.status_code >= 500,
            "error": f"HTTP {outcome.response.status_code} en POST /tesis",
        }
    return None


def buscar_documentos(expresion: str) -> tuple[Optional[list[dict]], Optional[dict], dict]:
    """
    Búsqueda con el CONTRATO REAL del buscador oficial: POST /tesis?page=N&size=100,
    body con classifiers + searchTerms (keyword en expression sobre
    localizacionBusqueda/rubro/texto). La paginación va en la URL, no en el body.

    Recorre las páginas hasta reunir el `total` que informa el SJF (tope:
    MAX_PAGINAS; si se alcanza, meta["truncado"] es True). Devuelve:
      (docs, None, meta)        la búsqueda se ejecutó completa — docs puede ser [];
      (None, info_error, meta)  no se pudo consultar, o falló una página posterior:
                                una búsqueda a medias no acredita ausencia.
    meta = {"total": int, "recuperados": int, "truncado": bool}.
    """
    docs: list[dict] = []
    vistos: set[str] = set()
    total: Optional[int] = None
    truncado = False
    for pagina in range(MAX_PAGINAS):
        outcome = _http(
            "POST", f"{SJF_API}/tesis?page={pagina}&size={TAMANO_PAGINA}", json=_search_body(expresion)
        )
        error = _error_busqueda(outcome)
        if error is None:
            try:
                cuerpo = outcome.response.json()
                lote = cuerpo.get("documents") or []
                if isinstance(cuerpo.get("total"), int):
                    total = cuerpo["total"]
            except (ValueError, TypeError, AttributeError) as exc:
                error = {"status": PARSER_ERROR, "retryable": False, "error": f"respuesta no parseable: {exc}"}
        if error is not None:
            if pagina:
                error["error"] = f"página {pagina + 1} de la búsqueda: {error['error']} (búsqueda incompleta)"
            return None, error, {"total": total, "recuperados": len(docs), "truncado": False}
        for doc in lote:
            clave = str(doc.get("ius", ""))
            if clave.isdigit() and clave not in vistos:
                vistos.add(clave)
                docs.append(doc)
        if len(lote) < TAMANO_PAGINA or (total is not None and len(docs) >= total):
            break
    else:
        truncado = True
    meta = {"total": total if total is not None else len(docs), "recuperados": len(docs), "truncado": truncado}
    return docs, None, meta


def buscar_tesis(expresion: str) -> tuple[Optional[list[int]], Optional[dict]]:
    """IUS de la búsqueda completa. (ids, None) si se pudo ejecutar — ids puede
    ser [] si genuinamente no hay resultados —; (None, info_error) si la fuente
    NO pudo consultarse: None ≠ [] — "no pude preguntar" no es "no hay nada"."""
    docs, error, _ = buscar_documentos(expresion)
    if docs is None:
        return None, error
    return [int(doc["ius"]) for doc in docs], None


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


def hash_documento(doc: dict) -> str:
    """SHA-256 del documento tal como lo entregó POST /tesis, en JSON canónico
    (claves ordenadas, separadores compactos, UTF-8). Reproducible: repetir la
    búsqueda, localizar el documento por su IUS y recalcular
    hashlib.sha256(json.dumps(doc, ensure_ascii=False, sort_keys=True,
    separators=(",", ":")).encode("utf-8")).hexdigest(). Cualquier cambio en el
    documento cambia la huella."""
    canonico = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def ficha_de_busqueda(doc: dict) -> dict[str, Any]:
    """Ficha normalizada a partir de un documento de la búsqueda.

    La búsqueda trae la localización (rubro, clave, época, órgano, fecha y texto
    de publicación, [J]/[TA]) pero no el texto completo ni las formas de
    integración: esos campos quedan vacíos (⚠️ no disponible) hasta que el
    detalle los aporte (enriquecer_nuevas). Nunca se completan de memoria.
    En la búsqueda 'sala' trae el NOMBRE del órgano y 'tipoTesis' un código; en
    el detalle 'sala' es un código interno: se distingue por si es numérico.
    """
    ius = int(doc["ius"])
    sala = _campo(doc, "sala")
    organo = sala if sala and not sala.isdigit() else _campo(doc, "instancia", "sInstancia")
    localizacion = _campo(doc, "localizacion")
    tipo_texto = _campo(doc, "tipoTesis")
    if tipo_texto.isdigit():  # código en la búsqueda: se toma la marca [J]/[TA] de la localización
        tipo_texto = ("Jurisprudencia" if localizacion.startswith("[J]")
                      else "Tesis aislada" if localizacion.startswith("[TA]") else "")
    fecha_pub = _campo(doc, "fechaPublicacion")
    en_ventana = _en_ventana(fecha_pub)
    return {
        # — Localización: SOLO del documento de la búsqueda —
        "ius":               ius,
        "rubro":             _campo(doc, "rubro"),
        "clave_tesis":       _campo(doc, "claveTesis"),
        "epoca":             _campo(doc, "epoca", "epocaAbr"),
        "sala_codigo":       sala if sala.isdigit() else "",
        "instancia":         organo,
        "instancia_abr":     _campo(doc, "instanciaAbr"),
        "localizacion":      localizacion,
        "tipo_raw":          tipo_texto,
        "ta_tj":             doc.get("ta_tj"),
        "tipo_clasificado":  clasificar(doc.get("ta_tj"), tipo_texto, []),
        "formas_integracion": [],
        "fecha_publicacion": fecha_pub,
        # texto_publicacion trae VERBATIM la publicación (y la obligatoriedad, si es J)
        "texto_publicacion": _campo(doc, "textoPublicacion"),
        "en_ventana_semana": en_ventana,
        # Para el generador de contenido: solo una tesis publicada en la ventana es novedad.
        "novedad":           en_ventana,
        "texto":             (_campo(doc, "texto") or "")[:1500],
        "hash_sha256":       hash_documento(doc),
        "hash_sobre":        "documento de la respuesta de POST /tesis (JSON canónico)",
        "origen":            "busqueda",
        # — Localización auditable —
        "url_sjf":           f"{SJF_DETAIL_WEB}/{ius}",
        "url_api":           f"{SJF_API}/tesis/{ius}",
    }


def _diagnostico_no_json(resp) -> tuple[str, bool]:
    """Por qué la ficha no llegó como JSON, dicho de forma accionable, y si
    reintentar por HTTP en el mismo entorno podría resolverlo."""
    tipo = (getattr(resp, "headers", None) or {}).get("content-type", "sin content-type")
    if "_Incapsula_Resource" in (resp.text or ""):
        return (
            f"desafío anti-bots (Incapsula) en lugar de la ficha JSON (HTTP {resp.status_code}, "
            f"{tipo}): el detalle no se puede leer por HTTP directo y no se evade; la vía con "
            "navegador es services/itosturre-scraper (vvca_audit.ts)",
            False,
        )
    return f"respuesta no JSON (HTTP {resp.status_code}, {tipo})", True


def obtener_detalle(ius: int) -> dict[str, Any]:
    """
    GET /tesis/{ius} → ficha completa en JSON.
    Normaliza campos; los ausentes quedan "" (nunca se inventan).
    """
    outcome = _http("GET", f"{SJF_API}/tesis/{ius}")
    resp = outcome.response
    if resp is None:
        return {"ius": ius, "_error": outcome.error, "_reintentable": outcome.retryable}
    if not resp.ok:
        return {"ius": ius, "_error": f"HTTP {resp.status_code}", "_reintentable": resp.status_code >= 500}
    body_bytes = resp.content  # cuerpo crudo de la respuesta HTTP (para custodia)
    try:
        raw: dict = resp.json()
    except ValueError:
        diagnostico, reintentable = _diagnostico_no_json(resp)
        return {"ius": ius, "_error": diagnostico, "_reintentable": reintentable}

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
    """Búsqueda completa de los 5 temas; las fichas salen de la búsqueda.

    Cada tema queda con status SUCCESS (búsqueda ejecutada completa — 'fichas'
    puede estar vacía) o con el status/errors que explican por qué no se pudo
    consultar. Ante un bloqueo de política de red los temas restantes no se
    consultan (fallarían igual) y quedan marcados. Un tema sin ningún resultado
    en todo el SJF lleva `sin_resultados_sjf`: señala la expresión, no acredita
    ausencia de criterios."""
    resultado: dict[str, dict] = {}
    for i, tema in enumerate(TEMAS):
        print(f"    🔎 {tema['label'][:65]}...")
        registrar_evento("source_requested", source="SJF", tema=tema["id"])
        docs, error_info, meta = buscar_documentos(tema["expresion"])
        if docs is None:
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
        fichas = [ficha_de_busqueda(doc) for doc in docs]
        nuevas = sum(1 for f in fichas if f["novedad"])
        print(f"       → {len(fichas)} de {meta['total']} resultados del SJF ({nuevas} nuevos en la ventana)")
        registrar_evento(
            "source_success", source="SJF", tema=tema["id"], n_items=len(fichas), total=meta["total"]
        )
        resultado[tema["label"]] = {
            "status": SUCCESS, "retryable": False, "errors": [], "fichas": fichas,
            "total": meta["total"], "truncado": meta["truncado"],
            "sin_resultados_sjf": meta["total"] == 0,
        }
    return resultado


def _combinar_detalle(ficha: dict, detalle: dict) -> None:
    """Suma a la ficha de la búsqueda lo que solo trae el detalle. La
    localización de la búsqueda se conserva; el detalle solo llena vacíos."""
    for clave in ("rubro", "clave_tesis", "epoca", "instancia", "fecha_publicacion", "texto_publicacion"):
        if not ficha.get(clave) and detalle.get(clave):
            ficha[clave] = detalle[clave]
    ficha["texto"] = detalle.get("texto", "")
    ficha["formas_integracion"] = detalle.get("formas_integracion", [])
    ficha["tipo_clasificado"] = detalle.get("tipo_clasificado") or ficha["tipo_clasificado"]
    ficha["hash_sha256_detalle"] = detalle.get("hash_sha256", "")
    ficha["origen"] = "busqueda+detalle"


def enriquecer_nuevas(resultados: dict[str, dict]) -> Optional[str]:
    """Intenta el detalle (texto completo y formas de integración) de las fichas
    NUEVAS, una vez por IUS y hasta MAX_DETALLE por corrida. Si el SJF responde
    con el desafío anti-bots (no reintentable), no se insiste en esta corrida:
    las fichas se quedan con los datos de la búsqueda. Devuelve la nota para el
    informe y el estado, o None si no faltó nada."""
    por_ius: dict[int, list[dict]] = {}
    for tema in resultados.values():
        if tema["status"] == SUCCESS:
            for ficha in tema["fichas"]:
                if ficha.get("novedad"):
                    por_ius.setdefault(ficha["ius"], []).append(ficha)
    fallos: list[str] = []
    for ius in list(por_ius)[:MAX_DETALLE]:
        print(f"         GET /tesis/{ius} (texto completo)")
        detalle = obtener_detalle(ius)
        if detalle.get("_error"):
            if not detalle.get("_reintentable", True):
                return f"Texto completo no disponible: {detalle['_error']}."
            fallos.append(f"IUS {ius}: {detalle['_error']}")
            continue
        for ficha in por_ius[ius]:
            _combinar_detalle(ficha, detalle)
    notas = []
    if fallos:
        notas.append("Texto completo no disponible para " + "; ".join(fallos))
    if len(por_ius) > MAX_DETALLE:
        notas.append(f"texto completo solo de {MAX_DETALLE} de {len(por_ius)} tesis nuevas (MAX_DETALLE)")
    return ". ".join(notas) + "." if notas else None


def contrato_tema(label: str, tema: dict) -> ResultadoFuente:
    """ResultadoFuente del tema: todas las fichas legibles (cada una con su marca
    `novedad`) y, como evidencia, el alcance de la búsqueda."""
    validas = [f for f in tema["fichas"] if not f.get("_error")]
    exito = tema["status"] == SUCCESS
    return ResultadoFuente(
        source=f"SJF:{label}",
        status=tema["status"],
        items=validas if exito else [],
        evidence=[{"busqueda": {
            "total": tema.get("total"), "recuperados": len(validas), "truncado": tema.get("truncado", False),
        }}] if exito else [],
        errors=tema["errors"],
        retryable=tema["retryable"],
    )


def alcance_tema(tema: dict) -> dict:
    """Lo que el estado de la corrida necesita saber de la búsqueda de un tema."""
    return {
        "total_sjf": tema.get("total"),
        "truncado": tema.get("truncado", False),
        "sin_resultados_sjf": tema.get("sin_resultados_sjf", False),
        "nuevas_en_ventana": sum(1 for f in tema["fichas"] if f.get("novedad")),
    }


def advertencias_de(resultados: dict[str, dict]) -> list[str]:
    """Avisos que no son fallas de la fuente pero limitan lo que el informe acredita."""
    avisos = []
    for label, tema in resultados.items():
        if tema.get("sin_resultados_sjf"):
            avisos.append(f"{label}: {AVISO_SIN_RESULTADOS}")
        if tema.get("truncado"):
            avisos.append(
                f"{label}: búsqueda truncada — se revisaron {len(tema['fichas'])} de "
                f"{tema['total']} resultados (orden de relevancia del SJF)"
            )
    return avisos


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
7. En cada tema, "nuevas" son los criterios publicados en la ventana de la
   semana y "contexto" son anteriores: van en la subsección "Contexto (fuera de
   ventana)". El órgano emisor es el campo "instancia" (texto); "sala_codigo"
   es un código interno — nunca lo escribas como "Sala N".
8. Si el campo "texto" viene vacío, la síntesis se basa solo en el rubro: dilo
   ("síntesis basada en el rubro") y no supongas el contenido del criterio.
9. Si un tema trae "sin_resultados_sjf": true, escribe que la expresión de
   búsqueda no devuelve ningún resultado en el SJF y que eso no acredita
   ausencia de criterios; si trae "truncado": true, di cuántos resultados se
   revisaron ("recuperados") de cuántos ("total_sjf")."""


def redactar_informe_llm(resultados: dict[str, dict], nota_detalle: Optional[str] = None) -> str:
    """
    Pasa a Claude la vista del informe (_vista_informe) para redactar el análisis.
    Todos los campos de localización vienen del JSON — el LLM solo escribe prose.
    """
    try:
        import anthropic
    except ImportError:
        return _informe_degradado(resultados, "librería anthropic no instalada", nota_detalle)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _informe_degradado(resultados, "ANTHROPIC_API_KEY no configurada", nota_detalle)

    client = anthropic.Anthropic(api_key=api_key)
    datos_str = json.dumps(_vista_informe(resultados), ensure_ascii=False, indent=2)
    nota_str = (
        f"\nNOTA SOBRE EL TEXTO COMPLETO (transcríbela en la Trazabilidad): {nota_detalle}\n"
        if nota_detalle else ""
    )
    semana_inicio = TODAY - timedelta(days=TODAY.weekday())
    semana_fin = semana_inicio + timedelta(days=6)

    prompt = f"""{_PROHIBICION_LLM}

Eres el módulo de inteligencia jurisprudencial de Itosturre.
Semana: {WEEK_STR}  ({semana_inicio} al {semana_fin})
Fuente: microservicio oficial sjf2.scjn.gob.mx/services/sjftesismicroservice

JSON CON TODOS LOS TEMAS (única fuente de verdad — no inventes nada; cada tema
lleva su "status": SUCCESS con "nuevas" y "contexto", o un estado de error con
"errors"):
{datos_str}
{nota_str}
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
- Si sin_resultados_sjf es true → la advertencia de la regla 9, nada más.
- Si "nuevas" está vacío → "Sin criterios publicados en la ventana."
- Si hay "nuevas" → "Nuevos esta semana", un bloque completo por criterio.
- "contexto" → lista breve (IUS, rubro, fecha) bajo "Contexto (fuera de
  ventana)"; si contexto_omitido > 0, indica cuántos más hay en el .json.]

Por cada criterio nuevo, usa este bloque (copia los valores del JSON, sin
modificar):

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
**Síntesis:** [2-4 oraciones basadas en el campo texto; si viene vacío, en el rubro, y dilo]
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
        return _informe_degradado(resultados, str(e), nota_detalle)


def _marca(valor: str) -> str:
    return valor if valor else "⚠️ no disponible"


def _bloque_ficha(f: dict) -> list[str]:
    lineas = [
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
        f"**Hash SHA-256 (búsqueda):** {_marca(f.get('hash_sha256', ''))}",
    ]
    if f.get("hash_sha256_detalle"):
        lineas.append(f"**Hash SHA-256 (detalle):** {f['hash_sha256_detalle']}")
    lineas += [f"**URL SJF:** {f.get('url_sjf', '')}", ""]
    return lineas


def _orden_reciente(f: dict) -> tuple:
    return (f.get("fecha_publicacion") or "", f.get("ius") or 0)


def _vista_informe(resultados: dict[str, dict]) -> dict[str, dict]:
    """Lo que ve el informe (y el LLM): por tema, todas las fichas nuevas y solo
    las MAX_CONTEXTO de contexto más recientes; el resto queda en el .json."""
    vista: dict[str, dict] = {}
    for label, tema in resultados.items():
        if tema["status"] != SUCCESS:
            vista[label] = {"status": tema["status"], "retryable": tema["retryable"], "errors": tema["errors"]}
            continue
        legibles = sorted((f for f in tema["fichas"] if not f.get("_error")), key=_orden_reciente, reverse=True)
        nuevas = [f for f in legibles if f.get("en_ventana_semana")]
        contexto = [f for f in legibles if not f.get("en_ventana_semana")]
        vista[label] = {
            "status": SUCCESS,
            "total_sjf": tema.get("total", len(legibles)),
            "recuperados": len(legibles),
            "truncado": tema.get("truncado", False),
            "sin_resultados_sjf": tema.get("sin_resultados_sjf", False),
            "nuevas": nuevas,
            "contexto": contexto[:MAX_CONTEXTO],
            "contexto_omitido": max(0, len(contexto) - MAX_CONTEXTO),
        }
    return vista


def _informe_degradado(
    resultados: dict[str, dict], motivo: str = "", nota_detalle: Optional[str] = None,
) -> str:
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
    vista = _vista_informe(resultados)
    exitosos = [v for v in vista.values() if v["status"] == SUCCESS]
    fallidos = [label for label, v in vista.items() if v["status"] != SUCCESS]
    lines += [
        f"**Total fichas recuperadas:** {sum(v['recuperados'] for v in exitosos)} · **Nuevas en la "
        f"ventana {FECHA_INICIO} a {TODAY}:** {sum(len(v['nuevas']) for v in exitosos)}",
        "",
    ]
    if fallidos:
        lines += [f"> ❌ {len(fallidos)} tema(s) sin consultar — ver cada sección.", ""]
    if nota_detalle:
        lines += [
            f"> ⚠️ {nota_detalle} Las fichas se arman con los datos de la búsqueda; el texto "
            "completo puede leerse en la URL SJF o con services/itosturre-scraper (vvca_audit.ts).",
            "",
        ]

    for label, v in vista.items():
        lines += [f"## {label}", ""]
        if v["status"] != SUCCESS:
            lines += [
                f"❌ **Consulta fallida ({v['status']})** — no equivale a \"sin criterios\".",
                f"- Reintentable: {'sí' if v['retryable'] else 'no'}",
                f"- Detalle: {'; '.join(v['errors']) or 'sin detalle'}",
                "",
            ]
            continue
        if v["sin_resultados_sjf"]:
            lines += [f"⚠️ {AVISO_SIN_RESULTADOS[0].upper()}{AVISO_SIN_RESULTADOS[1:]}.", ""]
            continue
        if v["truncado"]:
            lines += [
                f"> ⚠️ Búsqueda truncada: se revisaron {v['recuperados']} de {v['total_sjf']} resultados "
                "(orden de relevancia del SJF); una tesis nueva fuera de ellos no aparecería aquí.",
                "",
            ]
        if not v["nuevas"] and not v["contexto"]:
            lines += ["Sin criterios encontrados (búsqueda ejecutada).", ""]
            continue
        lines += ["### Nuevos esta semana", ""]
        if not v["nuevas"]:
            lines += ["Sin criterios publicados en la ventana.", ""]
        for f in v["nuevas"]:
            lines += _bloque_ficha(f)
        if v["contexto"]:
            lines += ["### Contexto (fuera de ventana)", ""]
            for f in v["contexto"]:
                lines += _bloque_ficha(f)
            if v["contexto_omitido"]:
                lines += [f"_… y {v['contexto_omitido']} más en {OUTPUT_FILE.with_suffix('.json').name}._", ""]

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
    nota_detalle = enriquecer_nuevas(resultados)
    if nota_detalle:
        print(f"  ⚠️ {nota_detalle}")
    contratos = {label: contrato_tema(label, tema) for label, tema in resultados.items()}
    temas = {label: {**r.resumen(), **alcance_tema(resultados[label])} for label, r in contratos.items()}
    advertencias = advertencias_de(resultados)
    for aviso in advertencias:
        print(f"  ⚠️ {aviso}")

    exitosos = sum(1 for r in contratos.values() if r.ok)
    total_fichas = sum(len(r.items) for r in contratos.values())
    nuevas = sum(1 for r in contratos.values() for f in r.items if f.get("novedad"))
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
    informe = redactar_informe_llm(resultados, nota_detalle)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(informe, encoding="utf-8")
    ruta_json = guardar_sidecar(OUTPUT_FILE, contratos)
    estado = rutina.OK if exitosos == len(contratos) else rutina.PARCIAL
    ruta_estado = rutina.registrar_estado(
        OUTPUT_DIR, OUTPUT_FILE.stem, estado,
        informe=OUTPUT_FILE.name, fichas=total_fichas, nuevas_en_ventana=nuevas, temas=temas,
        advertencias=advertencias, **({"detalle": nota_detalle} if nota_detalle else {}),
    )
    kb = OUTPUT_FILE.stat().st_size // 1024
    print(f"  💾 → {OUTPUT_FILE} ({kb} KB)")
    print(f"  💾 Fichas y contrato → {ruta_json}")
    print(f"  📋 Estado {estado} → {ruta_estado}")
    return rutina.codigo_salida(estado)


if __name__ == "__main__":
    sys.exit(main())
