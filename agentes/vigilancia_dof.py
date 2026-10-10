"""
vigilancia_dof.py — Módulo de Vigilancia DOF Diaria · Itosturre

Revisa dof.gob.mx y publicaciones SAT del día (fecha de la Ciudad de México).
Identifica: (1) listados 69-B, (2) reformas CFF/LISR/LIVA/RMF, (3) criterios SAT.
Guarda en salidas/Vigilancia/ (raíz: $ITOSTURRE_SALIDA): el brief YYYY-MM-DD.md,
el contrato crudo YYYY-MM-DD.json y el estado de la corrida YYYY-MM-DD.estado.json
(ver docs/VIGILANCIA_LEGAL.md).

Contrato de salida (itosturre/vigilancia/rutina.py):
  0 → brief escrito: OK, o PARCIAL si el SAT no respondió (el brief lo dice).
  2 → el DOF no respondió: NO se escribe brief — un brief sin la fuente primaria
      se leería como "sin publicaciones" y bloquearía el reintento del día.

Requiere que ESTE proceso corra en un entorno con egress autorizado hacia
dof.gob.mx y sat.gob.mx. Si corre en un entorno cuya política de red bloquea
esas conexiones (p. ej. un sandbox cloud de Claude Code), el resultado por
fuente queda en SOURCE_UNAVAILABLE — el módulo NUNCA rellena hallazgos ni
redacta un "sin novedades" para disfrazar que no pudo consultar la fuente.

Uso:
    python agentes/vigilancia_dof.py
    ANTHROPIC_API_KEY=sk-... python agentes/vigilancia_dof.py
"""

import json
import os
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from itosturre.vigilancia import (  # noqa: E402
    SUCCESS,
    ResultadoFuente,
    clasificar_excepcion_red,
    guardar_sidecar,
    registrar_evento,
    rutina,
)

# ── Rutas ─────────────────────────────────────────────────────────────────────

OUTPUT_DIR = rutina.SALIDA_DIR / "Vigilancia"
DATE_STR = rutina.hoy_mx().strftime("%Y-%m-%d")
OUTPUT_FILE = OUTPUT_DIR / f"{DATE_STR}.md"

# ── Configuración de búsqueda ─────────────────────────────────────────────────

KEYWORDS = [
    "69-B", "69 B", "presuntos", "definitivos",
    "Código Fiscal", "CFF",
    "ISR", "LISR", "LIVA",
    "Resolución Miscelánea", "RMF",
    "listado de contribuyentes",
    "cancelación de CSD", "restricción de CSD", "CSD",
    "criterios SAT", "criterios del SAT",
    "defensa fiscal",
    "acuerdo SAT", "regla miscelánea",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
        "Itosturre-Bot/1.0"
    ),
    "Accept-Language": "es-MX,es;q=0.9",
}

# Sin "www": el certificado del portal solo ampara dof.gob.mx (verificado el
# 10-oct-2026; con www la verificación TLS falla por nombre). Nunca desactivar
# la verificación TLS para "arreglarlo".
DOF_BASE = "https://dof.gob.mx"
SAT_NOTICIAS_URL = "https://www.sat.gob.mx/articulo/87284/comunicados-y-noticias"


# ── Scraping ───────────────────────────────────────────────────────────────────

def _match_keywords(text: str) -> list[str]:
    t = text.upper()
    return [kw for kw in KEYWORDS if kw.upper() in t]


def fetch_dof() -> ResultadoFuente:
    """Extrae entradas del DOF del día con keywords fiscales.

    Devuelve SIEMPRE un ResultadoFuente: SUCCESS con items (incluso vacíos, si
    de verdad no hubo coincidencias) o SOURCE_UNAVAILABLE/TIMEOUT/UNKNOWN_ERROR
    si la fuente no pudo consultarse. Nunca mezcla ambos casos.
    """
    try:
        resp = requests.get(DOF_BASE, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        status, retryable, mensaje = clasificar_excepcion_red(exc)
        print(f"  ⚠️ DOF no accesible: {mensaje}")
        return ResultadoFuente(source="DOF", status=status, retryable=retryable, errors=[mensaje])

    soup = BeautifulSoup(resp.text, "html.parser")
    items: list[dict] = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if len(text) < 15:
            continue
        matched = _match_keywords(text)
        if matched:
            url = urljoin(f"{DOF_BASE}/", a["href"])
            items.append({
                "fuente": "DOF",
                "titulo": text[:200],
                "url": url,
                "keywords_detectados": matched,
                "verificacion": "⚠️ por confirmar — URL requiere validación manual",
                "novedad": True,  # portada del día
            })

    for td in soup.find_all(["td", "li", "p"]):
        text = td.get_text(" ", strip=True)
        if len(text) < 20 or len(text) > 300:
            continue
        matched = _match_keywords(text)
        if matched:
            existing = [r["titulo"] for r in items]
            if text[:80] not in " ".join(existing):
                items.append({
                    "fuente": "DOF",
                    "titulo": text[:200],
                    "url": DOF_BASE,
                    "keywords_detectados": matched,
                    "verificacion": "⚠️ por confirmar — sin URL directa",
                    "novedad": True,  # portada del día
                })

    return ResultadoFuente(source="DOF", status=SUCCESS, items=items)


def fetch_sat() -> ResultadoFuente:
    """Extrae comunicados recientes del SAT con keywords fiscales. Ver fetch_dof()."""
    try:
        resp = requests.get(SAT_NOTICIAS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        status, retryable, mensaje = clasificar_excepcion_red(exc)
        print(f"  ⚠️ SAT no accesible: {mensaje}")
        return ResultadoFuente(source="SAT", status=status, retryable=retryable, errors=[mensaje])

    soup = BeautifulSoup(resp.text, "html.parser")
    items: list[dict] = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        if len(text) < 15:
            continue
        matched = _match_keywords(text)
        if matched:
            url = urljoin(SAT_NOTICIAS_URL, a["href"])
            items.append({
                "fuente": "SAT",
                "titulo": text[:200],
                "url": url,
                "keywords_detectados": matched,
                "verificacion": "⚠️ por confirmar",
                "novedad": True,  # comunicados recientes
            })

    return ResultadoFuente(source="SAT", status=SUCCESS, items=items)


# ── Generación con Claude ─────────────────────────────────────────────────────

def generar_brief(dof: ResultadoFuente, sat: ResultadoFuente) -> str:
    """Redacta el brief SOLO con hallazgos de fuentes SUCCESS. Una fuente
    SOURCE_UNAVAILABLE se reporta como tal — nunca se disfraza de 'sin novedades'.
    Sin ninguna fuente disponible no hay brief que redactar (falla cerrado)."""
    disponibles = [r for r in (dof, sat) if r.ok]
    indisponibles = [r for r in (dof, sat) if not r.ok]

    if not disponibles:
        raise ValueError("ninguna fuente respondió: no se redacta brief (ver main())")

    hallazgos = [item for r in disponibles for item in r.items]
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _brief_sin_llm(hallazgos, indisponibles, "ANTHROPIC_API_KEY no configurada")
    try:
        import anthropic
    except ImportError:
        return _brief_sin_llm(hallazgos, indisponibles, "librería anthropic no instalada")

    client = anthropic.Anthropic(api_key=api_key)
    hallazgos_str = (
        json.dumps(hallazgos, ensure_ascii=False, indent=2)
        if hallazgos else "Sin hallazgos con keywords fiscales en las fuentes disponibles hoy."
    )
    nota_indisponibles = (
        "\n".join(f"- {r.source}: {r.status} — {'; '.join(r.errors) or 'sin detalle'}" for r in indisponibles)
        or "(todas las fuentes configuradas respondieron)"
    )

    prompt = f"""Eres el módulo de vigilancia normativa de Itosturre.
Protocolo Itosturre: NO inventes números de publicación ni denominaciones exactas.
Si no puedes confirmar un dato con la URL proporcionada, márcalo ⚠️.

Fecha: {DATE_STR}

HALLAZGOS RAW de fuentes que SÍ respondieron (extraídos por scraping):
{hallazgos_str}

FUENTES QUE NO PUDIERON CONSULTARSE hoy (SOURCE_UNAVAILABLE — no reportes nada
sobre ellas como si las hubieras revisado; solo menciona que no se pudieron
consultar):
{nota_indisponibles}

Redacta un brief ejecutivo de vigilancia normativa (máx. 600 palabras, formato Markdown):

# Vigilancia DOF/SAT — {DATE_STR}

## 1. Listados 69-B (presuntos / definitivos)
[hallazgos o "Sin publicaciones identificadas hoy en las fuentes disponibles"]

## 2. Reformas o modificaciones: CFF · LISR · LIVA · RMF
[hallazgos o "Sin reformas identificadas hoy en las fuentes disponibles"]

## 3. Acuerdos o criterios SAT — Defensa fiscal federal
[hallazgos o "Sin criterios nuevos identificados hoy en las fuentes disponibles"]

## Fuentes consultadas
[Para cada fuente: nombre, URL, y si respondió o quedó SOURCE_UNAVAILABLE]

## Nota metodológica
[breve nota sobre límites de la vigilancia automatizada, la necesidad de
confirmación humana, y — si aplica — qué fuentes no pudieron consultarse hoy]

Reglas de marcado:
- ✅ fuente a la vista (URL directa en los hallazgos)
- ⚠️ por confirmar (sin URL directa)
- ❌ SOURCE_UNAVAILABLE (la fuente no pudo consultarse; nunca lo confundas con "sin novedades")

No inventes datos. Si un hallazgo es ambiguo, descríbelo como "posible" y remite a la fuente."""

    try:
        response = client.messages.create(
            model=rutina.modelo(),
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except anthropic.APIError as e:
        print(f"  ⚠️ Error API Claude: {e}")
        return _brief_sin_llm(hallazgos, indisponibles, f"error de la API: {e}")


def _brief_sin_llm(hallazgos: list[dict], indisponibles: list[ResultadoFuente], motivo: str) -> str:
    lines = [
        f"# Vigilancia DOF/SAT — {DATE_STR}",
        "",
        f"> ⚠️ Brief generado sin LLM ({motivo})",
        "",
    ]
    for r in indisponibles:
        lines += [
            f"> ❌ {r.source}: {r.status} — {'; '.join(r.errors) or 'sin detalle'}",
            f"> La ausencia de hallazgos de {r.source} NO significa que no hubo publicaciones:",
            "> la fuente no se pudo consultar; revisarla manualmente.",
            "",
        ]
    lines += ["## Hallazgos con keywords fiscales (solo fuentes disponibles)", ""]
    if not hallazgos:
        lines.append("Sin hallazgos relevantes hoy en las fuentes disponibles.")
    else:
        for h in hallazgos:
            kw = ", ".join(h["keywords_detectados"])
            lines.append(f"- **{h['fuente']}** | {h['verificacion']}")
            lines.append(f"  - Título: {h['titulo']}")
            lines.append(f"  - Keywords: {kw}")
            lines.append(f"  - URL: {h['url']}")
            lines.append("")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def _consultar(nombre: str, fetch) -> ResultadoFuente:
    print(f"  📥 Consultando {nombre}...")
    registrar_evento("source_requested", source=nombre)
    resultado = fetch()
    if resultado.ok:
        print(f"     → {len(resultado.items)} entradas con keywords fiscales")
        registrar_evento("source_success", source=nombre, n_items=len(resultado.items))
    else:
        registrar_evento(
            "source_unavailable", source=nombre, status=resultado.status, retryable=resultado.retryable
        )
    return resultado


def main() -> int:
    print(f"🔍 Vigilancia DOF/SAT — {DATE_STR}")
    rutina.validar_salida(OUTPUT_DIR)
    registrar_evento("watch_started", watch="dof_sat", fecha=DATE_STR)

    if OUTPUT_FILE.exists():
        # El estado de la corrida que escribió el brief se conserva tal cual.
        print(f"  ✅ Brief del día ya existe: {OUTPUT_FILE.name} — no se vuelve a consultar")
        return rutina.EXIT_OK

    registrar_evento("collector_started", watch="dof_sat")
    dof_result = _consultar("DOF", fetch_dof)
    if not dof_result.ok:
        # Sin DOF no hay brief: escribirlo dejaría un "sin novedades" falso y,
        # además, la guarda de arriba bloquearía el reintento del día.
        ruta = rutina.registrar_estado(
            OUTPUT_DIR, OUTPUT_FILE.stem, rutina.FUENTE_INACCESIBLE,
            fuente="DOF", fuentes={"DOF": dof_result.resumen()}, no_consultadas=["SAT"],
        )
        print(f"  🛑 Sin brief: el DOF no se pudo consultar ({dof_result.status}). Estado → {ruta}")
        return rutina.EXIT_FUENTE_INACCESIBLE

    sat_result = _consultar("SAT", fetch_sat)

    print("  🤖 Redactando brief...")
    brief = generar_brief(dof_result, sat_result)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(brief, encoding="utf-8")
    ruta_json = guardar_sidecar(OUTPUT_FILE, {"DOF": dof_result, "SAT": sat_result})
    estado = rutina.OK if sat_result.ok else rutina.PARCIAL
    ruta_estado = rutina.registrar_estado(
        OUTPUT_DIR, OUTPUT_FILE.stem, estado,
        brief=OUTPUT_FILE.name,
        hallazgos=len(dof_result.items) + len(sat_result.items),
        fuentes={"DOF": dof_result.resumen(), "SAT": sat_result.resumen()},
    )
    size = OUTPUT_FILE.stat().st_size
    print(f"  💾 Brief guardado → {OUTPUT_FILE} ({size} bytes)")
    print(f"  💾 Contrato guardado → {ruta_json}")
    print(f"  📋 Estado {estado} → {ruta_estado}")
    return rutina.codigo_salida(estado)


if __name__ == "__main__":
    sys.exit(main())
