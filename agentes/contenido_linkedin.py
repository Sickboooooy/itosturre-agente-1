"""
contenido_linkedin.py — Módulo Generador de Contenido LinkedIn · Itosturre

Lee los briefs más recientes de Itosturre/Vigilancia e Itosturre/Jurisprudencia
y redacta 1 borrador de post para LinkedIn.

Tono: técnico-práctico, SIN alarmismo, SIN prometer resultados.
Framing: "20 años de experiencia en el PJF".
Audiencia: contadores y empresarios PYME.
NO publica — deja el borrador en Itosturre/Contenido/ para revisión.

Uso:
    python agentes/contenido_linkedin.py
"""

import os
import sys
from pathlib import Path
from datetime import date
from typing import Optional

import anthropic

# ── Rutas ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
VIGILANCIA_DIR = BASE_DIR / "Itosturre" / "Vigilancia"
JURISPRUDENCIA_DIR = BASE_DIR / "Itosturre" / "Jurisprudencia"
OUTPUT_DIR = BASE_DIR / "Itosturre" / "Contenido"
DATE_STR = date.today().strftime("%Y-%m-%d")
OUTPUT_FILE = OUTPUT_DIR / f"borrador-{DATE_STR}.md"


# ── Lectura de briefs ─────────────────────────────────────────────────────────

def leer_archivo_mas_reciente(directorio: Path, extension: str = ".md") -> Optional[tuple[str, str]]:
    """Lee el archivo más reciente en el directorio. Devuelve (nombre, contenido) o None."""
    archivos = sorted(
        [f for f in directorio.glob(f"*{extension}") if f.name != ".gitkeep"],
        reverse=True,
    )
    if not archivos:
        return None
    archivo = archivos[0]
    try:
        return archivo.name, archivo.read_text(encoding="utf-8")
    except OSError:
        return None


def obtener_contexto() -> dict[str, str]:
    """Recopila el contenido de los briefs más recientes."""
    contexto: dict[str, str] = {}

    resultado_vig = leer_archivo_mas_reciente(VIGILANCIA_DIR)
    if resultado_vig:
        contexto["vigilancia_nombre"], contexto["vigilancia_contenido"] = resultado_vig
    else:
        contexto["vigilancia_nombre"] = "sin datos"
        contexto["vigilancia_contenido"] = (
            "No hay briefs de vigilancia DOF disponibles. "
            "Ejecuta primero `python agentes/vigilancia_dof.py`."
        )

    resultado_jur = leer_archivo_mas_reciente(JURISPRUDENCIA_DIR)
    if resultado_jur:
        contexto["jurisprudencia_nombre"], contexto["jurisprudencia_contenido"] = resultado_jur
    else:
        contexto["jurisprudencia_nombre"] = "sin datos"
        contexto["jurisprudencia_contenido"] = (
            "No hay informes de jurisprudencia disponibles. "
            "Ejecuta primero `python agentes/vigilancia_jurisprudencial.py`."
        )

    return contexto


# ── Generación con Claude ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el módulo de contenido de Itosturre, especializado en comunicación legal-fiscal
para contadores y empresarios PYME en México.

Voz y tono:
- Técnico-práctico: explicas con precisión, sin jerga innecesaria
- Sin alarmismo: informas, no asustas
- Sin promesas de resultados: orientas, no garantizas
- Framing: "20 años de experiencia en el Poder Judicial Federal" (no "desde adentro")
- Cercano pero profesional; puedes usar "te" para hablar directamente al lector

Restricciones absolutas:
- NO prometras resultados ni éxito garantizado
- NO uses tono de urgencia manipuladora ("¡actúa ya antes de que sea tarde!")
- NO inventes datos normativos; si un hallazgo no tiene base, no lo uses
- NO publiques: solo genera el borrador para revisión humana"""


def generar_borrador(contexto: dict[str, str]) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _borrador_placeholder(contexto)

    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Tienes acceso a los siguientes materiales de inteligencia normativa de Itosturre:

---
BRIEF DE VIGILANCIA DOF/SAT ({contexto['vigilancia_nombre']}):
{contexto['vigilancia_contenido'][:3000]}

---
INFORME JURISPRUDENCIAL ({contexto['jurisprudencia_nombre']}):
{contexto['jurisprudencia_contenido'][:3000]}

---

Con base en el hallazgo MÁS RELEVANTE de estos materiales, redacta 1 borrador de post para LinkedIn.

ESTRUCTURA DEL POST (máx. 1,200 caracteres, sin emojis excesivos):

**GANCHO (primera línea)**
Una oración que detenga el scroll. Orientada al problema real del contador o empresario PYME.
No usar "¿Sabías que...?" ni "¡ATENCIÓN!". Puede ser una afirmación directa o una pregunta genuina.

**CUERPO — 3 puntos de valor**
Punto 1: Qué cambió / cuál es el criterio / cuál es el riesgo real
Punto 2: Por qué le importa a un contador o empresario PYME
Punto 3: Qué se puede hacer al respecto (orientación, no promesa)

**CIERRE CON CTA**
Invita a agendar una consulta o conversación vía WhatsApp: wa.me/[número]
Firma: Lic. Jorge Fabián Martínez | Itosturre LegalTech | 20 años PJF

---

TAMBIÉN incluye al final del archivo (fuera del post visible):

## Metadatos del borrador
- Fecha: {DATE_STR}
- Fuente principal: [nombre del brief o informe usado]
- Hallazgo base: [qué dato normativo/jurisprudencial motivó el post]
- Temas: [hashtags sugeridos, máx. 5]
- Status: BORRADOR — pendiente de revisión por Lic. Jorge Fabián Martínez

## Variante alternativa (opcional)
[Una segunda versión del gancho si el primero es muy formal o muy coloquial]"""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        borrador = response.content[0].text
        return f"# Borrador LinkedIn — {DATE_STR}\n\n{borrador}"
    except anthropic.APIError as e:
        print(f"  ⚠️ Error API Claude: {e}")
        return _borrador_placeholder(contexto)


def _borrador_placeholder(contexto: dict[str, str]) -> str:
    return f"""# Borrador LinkedIn — {DATE_STR}

> ⚠️ Borrador generado sin LLM (ANTHROPIC_API_KEY no configurada)
> Para generar el post completo, configura la variable de entorno.

## Fuentes disponibles

- Vigilancia DOF/SAT: {contexto['vigilancia_nombre']}
- Jurisprudencia SJF: {contexto['jurisprudencia_nombre']}

## Estructura sugerida para el post

**GANCHO:** [Identificar el hallazgo más relevante de los briefs y abrir con él]

**Punto 1:** ¿Qué cambió normativamente o jurisprudencialmente?
**Punto 2:** ¿Por qué le importa a contadores/empresarios PYME?
**Punto 3:** ¿Qué medida práctica se puede tomar?

**CIERRE:** Agenda tu consulta → wa.me/[número]
Lic. Jorge Fabián Martínez | Itosturre LegalTech | 20 años PJF

## Metadatos
- Fecha: {DATE_STR}
- Status: BORRADOR — pendiente de revisión
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"✍️  Generador de Contenido LinkedIn — {DATE_STR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_FILE.exists():
        print(f"  ✅ Borrador del día ya existe: {OUTPUT_FILE.name}")
        return 0

    print("  📖 Leyendo briefs disponibles...")
    contexto = obtener_contexto()
    print(f"     → Vigilancia: {contexto['vigilancia_nombre']}")
    print(f"     → Jurisprudencia: {contexto['jurisprudencia_nombre']}")

    print("  🤖 Redactando borrador con Claude...")
    borrador = generar_borrador(contexto)

    OUTPUT_FILE.write_text(borrador, encoding="utf-8")
    size = OUTPUT_FILE.stat().st_size
    print(f"  💾 Borrador guardado → Itosturre/Contenido/{OUTPUT_FILE.name} ({size} bytes)")
    print()
    print("  ⚠️  RECUERDA: Este es un BORRADOR. Revísalo antes de publicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
