"""
vigilancia_dof.py — Módulo de Vigilancia DOF Diaria · Itosturre

Revisa dof.gob.mx y publicaciones SAT del día.
Identifica: (1) listados 69-B, (2) reformas CFF/LISR/LIVA/RMF, (3) criterios SAT.
Guarda brief en Itosturre/Vigilancia/YYYY-MM-DD.md

Uso:
    python agentes/vigilancia_dof.py
    ANTHROPIC_API_KEY=sk-... python agentes/vigilancia_dof.py
"""

import os
import json
import sys
from pathlib import Path
from datetime import date

import requests
from bs4 import BeautifulSoup
import anthropic

# ── Rutas ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
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


def fetch_dof() -> list[dict]:
    """Extrae entradas del DOF del día con keywords fiscales."""
    results: list[dict] = []
    try:
        resp = requests.get(DOF_BASE, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if len(text) < 15:
                continue
            matched = _match_keywords(text)
            if matched:
                href = a["href"]
                url = href if href.startswith("http") else f"{DOF_BASE}{href}"
                results.append({
                    "fuente": "DOF",
                    "titulo": text[:200],
                    "url": url,
                    "keywords_detectados": matched,
                    "verificacion": "⚠️ por confirmar — URL requiere validación manual",
                })

        # También buscar en tablas de contenido del DOF
        for td in soup.find_all(["td", "li", "p"]):
            text = td.get_text(" ", strip=True)
            if len(text) < 20 or len(text) > 300:
                continue
            matched = _match_keywords(text)
            if matched:
                existing = [r["titulo"] for r in results]
                if text[:80] not in " ".join(existing):
                    results.append({
                        "fuente": "DOF",
                        "titulo": text[:200],
                        "url": DOF_BASE,
                        "keywords_detectados": matched,
                        "verificacion": "⚠️ por confirmar — sin URL directa",
                    })

    except requests.RequestException as e:
        print(f"  ⚠️ DOF no accesible: {e}")
        results.append({
            "fuente": "DOF",
            "titulo": "ERROR — portal DOF no respondió",
            "url": DOF_BASE,
            "keywords_detectados": [],
            "verificacion": "⚠️ error de conexión",
        })
    return results


def fetch_sat() -> list[dict]:
    """Extrae comunicados recientes del SAT con keywords fiscales."""
    results: list[dict] = []
    try:
        resp = requests.get(SAT_NOTICIAS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if len(text) < 15:
                continue
            matched = _match_keywords(text)
            if matched:
                href = a["href"]
                url = href if href.startswith("http") else f"{SAT_BASE}{href}"
                results.append({
                    "fuente": "SAT",
                    "titulo": text[:200],
                    "url": url,
                    "keywords_detectados": matched,
                    "verificacion": "⚠️ por confirmar",
                })
    except requests.RequestException as e:
        print(f"  ⚠️ SAT no accesible: {e}")
    return results


# ── Generación con Claude ─────────────────────────────────────────────────────

def generar_brief(hallazgos: list[dict]) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _brief_sin_llm(hallazgos)

    client = anthropic.Anthropic(api_key=api_key)

    if hallazgos:
        hallazgos_str = json.dumps(hallazgos, ensure_ascii=False, indent=2)
    else:
        hallazgos_str = "Sin hallazgos con keywords fiscales en DOF ni SAT hoy."

    prompt = f"""Eres el módulo de vigilancia normativa de Itosturre.
Protocolo Itosturre: NO inventes números de publicación ni denominaciones exactas.
Si no puedes confirmar un dato con la URL proporcionada, márcalo ⚠️.

Fecha: {DATE_STR}
Fuentes: dof.gob.mx, sat.gob.mx

HALLAZGOS RAW (extraídos por scraping):
{hallazgos_str}

Redacta un brief ejecutivo de vigilancia normativa (máx. 600 palabras, formato Markdown):

# Vigilancia DOF/SAT — {DATE_STR}

## 1. Listados 69-B (presuntos / definitivos)
[hallazgos o "Sin publicaciones identificadas hoy"]

## 2. Reformas o modificaciones: CFF · LISR · LIVA · RMF
[hallazgos o "Sin reformas identificadas hoy"]

## 3. Acuerdos o criterios SAT — Defensa fiscal federal
[hallazgos o "Sin criterios nuevos identificados hoy"]

## Fuentes consultadas
- DOF: {DOF_BASE} ({DATE_STR}) [nivel verificación]
- SAT: {SAT_NOTICIAS_URL} ({DATE_STR}) [nivel verificación]

## Nota metodológica
[breve nota sobre límites de la vigilancia automatizada y necesidad de confirmación]

Reglas de marcado:
- ✅ fuente a la vista (URL directa en los hallazgos)
- ⚠️ por confirmar (sin URL directa o no accesible)
- ❌ error de conexión (cuando el portal no respondió)

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
        return _brief_sin_llm(hallazgos)


def _brief_sin_llm(hallazgos: list[dict]) -> str:
    lines = [
        f"# Vigilancia DOF/SAT — {DATE_STR}",
        "",
        "> ⚠️ Brief generado sin LLM (ANTHROPIC_API_KEY no configurada)",
        "",
        "## Hallazgos con keywords fiscales",
        "",
    ]
    if not hallazgos:
        lines.append("Sin hallazgos relevantes hoy.")
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

def main() -> int:
    print(f"🔍 Vigilancia DOF/SAT — {DATE_STR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_FILE.exists():
        print(f"  ✅ Brief del día ya existe: {OUTPUT_FILE.name}")
        return 0

    print("  📥 Consultando DOF portada...")
    dof_items = fetch_dof()
    print(f"     → {len(dof_items)} entradas con keywords fiscales")

    print("  📥 Consultando SAT comunicados...")
    sat_items = fetch_sat()
    print(f"     → {len(sat_items)} entradas relevantes")

    hallazgos = dof_items + sat_items
    print(f"  🤖 Redactando brief ({len(hallazgos)} hallazgos)...")
    brief = generar_brief(hallazgos)

    OUTPUT_FILE.write_text(brief, encoding="utf-8")
    size = OUTPUT_FILE.stat().st_size
    print(f"  💾 Brief guardado → Itosturre/Vigilancia/{OUTPUT_FILE.name} ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
