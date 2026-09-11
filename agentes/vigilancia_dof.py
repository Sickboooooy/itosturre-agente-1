"""
vigilancia_dof.py — Módulo de Vigilancia DOF Diaria · Itosturre

Revisa dof.gob.mx y publicaciones SAT del día.
Identifica: (1) listados 69-B, (2) reformas CFF/LISR/LIVA/RMF, (3) criterios SAT.
Guarda brief en Itosturre/Vigilancia/YYYY-MM-DD.md + contrato crudo en
Itosturre/Vigilancia/YYYY-MM-DD.json (ver docs/VIGILANCIA_LEGAL.md).

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
from datetime import date

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from itosturre.vigilancia import (  # noqa: E402
    SOURCE_UNAVAILABLE,
    ResultadoFuente,
    clasificar_excepcion_red,
    guardar_sidecar,
    registrar_evento,
)

# ── Rutas ─────────────────────────────────────────────────────────────────────

OUTPUT_DIR = BASE_DIR / "Itosturre" / "Vigilancia"
DATE_STR = date.today().strftime("%Y-%m-%d")
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

DOF_BASE = "https://www.dof.gob.mx"
SAT_NOTICIAS_URL = "https://www.sat.gob.mx/articulo/87284/comunicados-y-noticias"
SAT_BASE = "https://www.sat.gob.mx"


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
            href = a["href"]
            url = href if href.startswith("http") else f"{DOF_BASE}{href}"
            items.append({
                "fuente": "DOF",
                "titulo": text[:200],
                "url": url,
                "keywords_detectados": matched,
                "verificacion": "⚠️ por confirmar — URL requiere validación manual",
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
                })

    return ResultadoFuente(source="DOF", status="SUCCESS", items=items)


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
            href = a["href"]
            url = href if href.startswith("http") else f"{SAT_BASE}{href}"
            items.append({
                "fuente": "SAT",
                "titulo": text[:200],
                "url": url,
                "keywords_detectados": matched,
                "verificacion": "⚠️ por confirmar",
            })

    return ResultadoFuente(source="SAT", status="SUCCESS", items=items)


# ── Generación con Claude ─────────────────────────────────────────────────────

def generar_brief(dof: ResultadoFuente, sat: ResultadoFuente) -> str:
    """Redacta el brief SOLO con hallazgos de fuentes SUCCESS. Una fuente
    SOURCE_UNAVAILABLE se reporta como tal — nunca se disfraza de 'sin novedades'."""
    disponibles = [r for r in (dof, sat) if r.ok]
    indisponibles = [r for r in (dof, sat) if not r.ok]

    if not disponibles:
        return _brief_todas_indisponibles(indisponibles)

    hallazgos = [item for r in disponibles for item in r.items]
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _brief_sin_llm(hallazgos, indisponibles)

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    hallazgos_str = (
        json.dumps(hallazgos, ensure_ascii=False, indent=2)
        if hallazgos else "Sin hallazgos con keywords fiscales en las fuentes disponibles hoy."
    )
    nota_indisponibles = (
        "\n".join(f"- {r.source}: SOURCE_UNAVAILABLE — {'; '.join(r.errors) or 'sin detalle'}" for r in indisponibles)
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
            model="claude-sonnet-4-6",
            max_tokens=1200,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except anthropic.APIError as e:
        print(f"  ⚠️ Error API Claude: {e}")
        return _brief_sin_llm(hallazgos, indisponibles)


def _brief_sin_llm(hallazgos: list[dict], indisponibles: list[ResultadoFuente]) -> str:
    lines = [
        f"# Vigilancia DOF/SAT — {DATE_STR}",
        "",
        "> ⚠️ Brief generado sin LLM (ANTHROPIC_API_KEY no configurada)",
        "",
    ]
    for r in indisponibles:
        lines.append(f"> ❌ {r.source}: SOURCE_UNAVAILABLE — {'; '.join(r.errors) or 'sin detalle'}")
    lines += ["", "## Hallazgos con keywords fiscales (solo fuentes disponibles)", ""]
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


def _brief_todas_indisponibles(indisponibles: list[ResultadoFuente]) -> str:
    """Ninguna fuente respondió: NO se genera ningún contenido jurídico —
    ni siquiera vía LLM — porque no hay nada verificado sobre lo cual escribir."""
    lines = [
        f"# Vigilancia DOF/SAT — {DATE_STR}",
        "",
        "## Watch result: SOURCE_UNAVAILABLE",
        "",
        "Ninguna fuente pudo consultarse hoy. No se generó ningún análisis ni",
        "resumen jurídico — hacerlo sin datos verificados violaría el protocolo",
        "anti-alucinación de Itosturre.",
        "",
    ]
    for r in indisponibles:
        lines += [
            f"### {r.source}",
            f"- Estado: {r.status}",
            f"- Reintentable: {'sí' if r.retryable else 'no'}",
            f"- Entorno de ejecución: {r.execution_environment}",
            f"- Detalle: {'; '.join(r.errors) or 'sin detalle'}",
            "",
        ]
    lines += [
        "## Siguiente paso",
        "Ejecutar este watch en un entorno con egress autorizado hacia dof.gob.mx",
        "y sat.gob.mx (ver docs/VIGILANCIA_LEGAL.md). Reintentar en el mismo entorno",
        "no resuelve un bloqueo de política de red.",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"🔍 Vigilancia DOF/SAT — {DATE_STR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    registrar_evento("watch_started", watch="dof_sat", fecha=DATE_STR)

    if OUTPUT_FILE.exists():
        print(f"  ✅ Brief del día ya existe: {OUTPUT_FILE.name}")
        return 0

    registrar_evento("collector_started", watch="dof_sat")

    print("  📥 Consultando DOF portada...")
    registrar_evento("source_requested", source="DOF")
    dof_result = fetch_dof()
    if dof_result.ok:
        print(f"     → {len(dof_result.items)} entradas con keywords fiscales")
        registrar_evento("source_success", source="DOF", n_items=len(dof_result.items))
    else:
        registrar_evento(
            "source_unavailable", source="DOF", status=dof_result.status, retryable=dof_result.retryable
        )

    print("  📥 Consultando SAT comunicados...")
    registrar_evento("source_requested", source="SAT")
    sat_result = fetch_sat()
    if sat_result.ok:
        print(f"     → {len(sat_result.items)} entradas relevantes")
        registrar_evento("source_success", source="SAT", n_items=len(sat_result.items))
    else:
        registrar_evento(
            "source_unavailable", source="SAT", status=sat_result.status, retryable=sat_result.retryable
        )

    print("  🤖 Redactando brief...")
    brief = generar_brief(dof_result, sat_result)

    OUTPUT_FILE.write_text(brief, encoding="utf-8")
    ruta_json = guardar_sidecar(OUTPUT_FILE, {"DOF": dof_result, "SAT": sat_result})
    size = OUTPUT_FILE.stat().st_size
    print(f"  💾 Brief guardado → Itosturre/Vigilancia/{OUTPUT_FILE.name} ({size} bytes)")
    print(f"  💾 Contrato guardado → {ruta_json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
