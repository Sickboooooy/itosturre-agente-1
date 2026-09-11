#!/usr/bin/env python3
"""Verifica frase a frase que nada de CLAUDE.md se perdió al adelgazarlo.

Compara el CLAUDE.md **original** contra la unión de sus destinos:

    CLAUDE.md nuevo
  + .claude/skills/menu-itosturre/  (SKILL.md + references/)
  + docs/ENTORNO.md, docs/SJF_OPERATIVA.md
  + las skills que emiten la advertencia fija

Toda línea con contenido del original debe aparecer en algún destino. Las que no,
tienen que estar declaradas en ``SUPRESIONES`` con su motivo: son los recortes
deliberados (changelog, notas de plataforma equivocadas, texto duplicado).

**Cualquier línea que no aparezca y no esté declarada aborta con código 1.** Un
archivo de 857 líneas no se poda a ojo: si esto no pasa en verde, no se borra
nada.

Uso:
  python scripts/verificar_migracion_claude_md.py
  python scripts/verificar_migracion_claude_md.py --original CLAUDE.md --nuevo CLAUDE.md.nuevo
"""
from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Líneas puramente decorativas: marcos, separadores, viñetas sueltas.
_DECORATIVA = re.compile(r"^[\s─═━\-–—=_·•|│┌┐└┘├┤┬┴┼╔╗╚╝║╠╣╦╩╬>*`\[\]()]*$")

#: Recortes deliberados. Cada patrón necesita un motivo: si algo no aparece en
#: ningún destino y tampoco está aquí, es una pérdida y el verificador aborta.
SUPRESIONES: list[tuple[str, str]] = [
    (r"^# v2\.1 \(16-jul-2026\)", "Changelog de versión: es historia de git, no instrucción"),
    (r"fusionadas reglas de un borrador de arquitectura externo",
     "Changelog v2.1"),
    (r"umbrales reales de semáforo, principio de corpus parcial, dato de privacidad",
     "Changelog v2.1"),
    (r"^# 100% local, notas operativas SJF y enriquecimiento del protocolo de citas",
     "Changelog v2.1"),
    (r"Se descartaron del borrador", "Changelog v2.1; además SQLite ya está implementado"),
    (r"--strict-penal, --corpus-parcial, SQLite, Qdrant",
     "Changelog v2.1 — obsoleto: SQLite se implementó en itosturre/memoria/"),
    (r"quedan como ideas de roadmap, no como comandos reales",
     "Changelog v2.1"),
    (r"^# Versión 2\.1 · Julio 2026", "Sustituido por la cabecera v3.0"),
    (r"^\*Prompt v2\.0 · Itosturre-Agente · Junio 2026", "Sustituido por el pie v3.0"),
    (r"^\*Comandos verificados contra el código real del repo\. \(OpenNotebook",
     "Sustituido por el pie v3.0"),
    # ── Entorno: obsoleto y corregido en docs/ENTORNO.md ──
    (r"ENTORNO PYTHON DE ESTE EQUIPO \(macOS", "OBSOLETO: el equipo es Windows → docs/ENTORNO.md"),
    (r"venv/bin/python", "OBSOLETO en Windows (es venv/Scripts/python.exe) → docs/ENTORNO.md"),
    (r"En este Mac \*\*NO existe el binario", "OBSOLETO: aquí `python` global sí existe"),
    (r"`python` global\*\* \(solo `python3`\)", "OBSOLETO: aquí `python3` NO existe"),
    (r"llamadas de shell del IDE \(cada Bash arranca limpio\)", "Movido a docs/ENTORNO.md"),
    (r"^> - Setup desde clon limpio", "Movido a docs/ENTORNO.md"),
    (r"^> - `requirements\.txt` incluye", "Movido a docs/ENTORNO.md"),
    (r"OpenNotebook\.py que faltaban y abortaban el `ingest`", "Movido a docs/ENTORNO.md"),
    (r"`ModuleNotFoundError`, reinstala requirements en el venv", "Movido a docs/ENTORNO.md"),
    (r"Corpus: 47 PDFs del Drive", "OBSOLETO: son 48 → docs/ENTORNO.md"),
    (r"en `chroma_db/` tras el bootstrap; verifica con", "Movido a docs/ENTORNO.md"),
    (r"^> ⚙️ \*\*ENTORNO", "Movido a docs/ENTORNO.md"),
    (r"^> - Las dependencias viven en un \*\*venv\*\*", "Movido a docs/ENTORNO.md"),
    (r"^> - \*\*Por eso, ejecuta SIEMPRE", "Movido a docs/ENTORNO.md"),
    (r"^> - Corpus: 47 PDFs", "OBSOLETO → docs/ENTORNO.md"),
    (r"PYTHON=\"\$\(pwd\)/venv/bin/python\"", "OBSOLETO en Windows → docs/ENTORNO.md"),
    (r"pip install -r requirements\.txt gdown", "Movido a docs/ENTORNO.md"),
    (r"python3 -m venv venv", "Movido a docs/ENTORNO.md"),
    (r"en este equipo: anteponer \./venv/bin/ a cada",
     "OBSOLETO: sobrevivía dentro del bloque bash; el intérprete correcto está en la nota"),
    # ── Catálogo de skills: duplicaba lo que ya se auto-carga ──
    (r"^# Skills de LITIGIO \(se invocan por nombre",
     "Duplicaba la description de cada skill, que ya se carga sola en cada sesión"),
    (r"^#\s+(cronologia-expediente|escrito-judicial|prep-testigos|review-contract|"
     r"triage-nda|medios-defensa-fiscal)\s+→ MENÚ",
     "Duplicaba la description de la skill; el mapa menú→skill está en menu-itosturre/SKILL.md"),
    (r"^# Skills CORPORATIVO / COMERCIAL \(B2B\):", "Duplicaba descriptions de skills"),
    (r"^# Skill FISCAL:", "Duplicaba descriptions de skills"),
    (r"^# Apoyos: skill `pdf` \(OCR\), skill `docx`",
     "Duplicaba descriptions de skills; se conserva en una línea condensada"),
]

#: Destinos donde puede haber aterrizado el contenido.
def destinos(nuevo: Path) -> list[Path]:
    rutas = [
        nuevo,
        REPO / "docs" / "ENTORNO.md",
        REPO / "docs" / "SJF_OPERATIVA.md",
        REPO / ".claude" / "skills" / "menu-itosturre" / "SKILL.md",
    ]
    rutas += sorted((REPO / ".claude" / "skills" / "menu-itosturre" / "references").glob("*.md"))
    # La advertencia fija ya vivía, textual, en las skills que generan el escrito.
    rutas += sorted((REPO / "services" / "itosturre-skills" / "skills").glob("*/SKILL.md"))
    rutas += sorted((REPO / ".claude" / "skills").glob("*/SKILL.md"))
    return [r for r in rutas if r.exists()]


def normalizar(linea: str) -> str:
    """Normaliza para comparar: acentos NFC, espacios colapsados, nivel de título fuera.

    Cambiar `## MENÚ 1` por `# MENÚ 1` al mover una sección a su propio archivo no
    es pérdida de contenido; cambiar el texto sí lo sería.
    """
    texto = unicodedata.normalize("NFC", linea).strip()
    texto = re.sub(r"^#{1,6}\s*", "", texto)
    return re.sub(r"\s+", " ", texto)


def suprimida(linea: str) -> str | None:
    for patron, motivo in SUPRESIONES:
        if re.search(patron, linea):
            return motivo
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # Sin valor por defecto a propósito: apuntar `--original` al CLAUDE.md actual
    # lo compararía consigo mismo y pasaría en verde sin verificar nada. El
    # original hay que sacarlo de git:
    #   git show <commit-previo>:CLAUDE.md > /tmp/CLAUDE.md.original
    ap.add_argument("--original", required=True,
                    help="CLAUDE.md ANTERIOR a la migración (extraído de git)")
    ap.add_argument("--nuevo", default=str(REPO / "CLAUDE.md"),
                    help="CLAUDE.md resultante (por defecto, el del árbol)")
    ap.add_argument("--verbose", action="store_true", help="Listar también lo suprimido")
    args = ap.parse_args()

    original = Path(args.original)
    nuevo = Path(args.nuevo)
    if not nuevo.exists():
        print(f"❌ No existe el CLAUDE.md nuevo: {nuevo}", file=sys.stderr)
        return 2

    rutas = destinos(nuevo)
    corpus: set[str] = set()
    for ruta in rutas:
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            n = normalizar(linea)
            if n:
                corpus.add(n)

    print("═" * 74)
    print("  VERIFICADOR DE MIGRACIÓN — CLAUDE.md")
    print("═" * 74)
    print(f"  Original : {original}")
    print(f"  Destinos : {len(rutas)} archivos, {len(corpus):,} líneas únicas")
    print()

    perdidas: list[tuple[int, str]] = []
    suprimidas: list[tuple[int, str, str]] = []
    migradas = decorativas = 0

    for numero, linea in enumerate(original.read_text(encoding="utf-8").splitlines(), 1):
        if _DECORATIVA.match(linea):
            decorativas += 1
            continue
        n = normalizar(linea)
        if not n:
            decorativas += 1
            continue
        if n in corpus:
            migradas += 1
            continue
        motivo = suprimida(linea)
        if motivo:
            suprimidas.append((numero, linea.strip(), motivo))
        else:
            perdidas.append((numero, linea.strip()))

    print(f"  ✅ Migradas          : {migradas:,}")
    print(f"  ⚪ Decorativas        : {decorativas:,}  (marcos, separadores, vacías)")
    print(f"  🗑️  Suprimidas         : {len(suprimidas):,}  (declaradas con motivo)")
    print(f"  ❌ NO MIGRADAS       : {len(perdidas):,}")
    print()

    if args.verbose and suprimidas:
        print("── Suprimidas deliberadamente ──")
        for numero, texto, motivo in suprimidas:
            print(f"  L{numero:<4} {texto[:64]}")
            print(f"        → {motivo}")
        print()

    if perdidas:
        print("── ❌ CONTENIDO NO MIGRADO NI DECLARADO ──")
        for numero, texto in perdidas:
            print(f"  L{numero:<4} {texto[:100]}")
        print()
        print("🔴 ABORTAR: no se borra nada de CLAUDE.md hasta clasificar lo anterior.")
        print("   Cada línea debe migrarse a un destino o declararse en SUPRESIONES.")
        return 1

    print("🟢 Sin pérdidas. Todo el contenido está migrado o suprimido con motivo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
