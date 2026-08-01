#!/usr/bin/env python3
"""Verifica o regenera las superficies Claude/Codex del repositorio.

Fuentes canónicas:
  - CLAUDE.md para la política operativa compartida.
  - .claude/skills/ para las skills vendorizadas.

Derivados:
  - AGENTS.md, con dos sustituciones de encabezado para Codex.
  - .agents/skills/, espejo con adaptaciones de plataforma acotadas.

Uso:
  python scripts/check_agent_surfaces.py
  python scripts/check_agent_surfaces.py --write
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


REPO = Path(__file__).resolve().parent.parent
CLAUDE_MD = REPO / "CLAUDE.md"
AGENTS_MD = REPO / "AGENTS.md"
CLAUDE_SKILLS = REPO / ".claude" / "skills"
AGENT_SKILLS = REPO / ".agents" / "skills"


def adapt_root(text: str) -> str:
    """Aplica únicamente las diferencias de plataforma permitidas en AGENTS.md."""
    return text.replace(
        "Sistema Prompt para Claude Code",
        "Sistema Prompt para Codex",
        1,
    ).replace(
        "Claude Code lee este archivo automáticamente al iniciar cada sesión.",
        "Codex lee este archivo automáticamente al iniciar cada sesión.",
        1,
    )


def adapt_skill(relative: Path, content: bytes) -> bytes:
    """Adapta solo los entrypoints que contienen identidad o rutas de plataforma."""
    rel = relative.as_posix()
    if rel not in {
        "docx/SKILL.md",
        "itosturre/SKILL.md",
        "playwright-skill/SKILL.md",
    }:
        return content

    text = content.decode("utf-8")
    if rel == "itosturre/SKILL.md":
        text = text.replace("Claude", "Codex").replace("claude", "Codex")
        text = text.replace("Codex Code (terminal)", "Codex (terminal)")
    elif rel == "docx/SKILL.md":
        text = text.replace("Claude", "Codex")
    else:
        text = text.replace(".claude", ".Codex").replace("Claude:", "Codex:")
    return text.encode("utf-8")


def canonical_files() -> dict[Path, bytes]:
    return {
        path.relative_to(CLAUDE_SKILLS): adapt_skill(
            path.relative_to(CLAUDE_SKILLS), path.read_bytes()
        )
        for path in CLAUDE_SKILLS.rglob("*")
        if path.is_file()
    }


def check() -> list[str]:
    errors: list[str] = []

    expected_root = adapt_root(CLAUDE_MD.read_text(encoding="utf-8"))
    if not AGENTS_MD.exists():
        errors.append("falta AGENTS.md")
    elif AGENTS_MD.read_text(encoding="utf-8") != expected_root:
        errors.append("AGENTS.md divergió de CLAUDE.md fuera del encabezado permitido")

    expected = canonical_files()
    actual_paths = (
        {
            path.relative_to(AGENT_SKILLS)
            for path in AGENT_SKILLS.rglob("*")
            if path.is_file()
        }
        if AGENT_SKILLS.exists()
        else set()
    )

    missing = sorted(set(expected) - actual_paths)
    extra = sorted(actual_paths - set(expected))
    errors.extend(f"falta .agents/skills/{path.as_posix()}" for path in missing)
    errors.extend(f"sobra .agents/skills/{path.as_posix()}" for path in extra)

    for relative in sorted(set(expected) & actual_paths):
        if (AGENT_SKILLS / relative).read_bytes() != expected[relative]:
            errors.append(f"divergió .agents/skills/{relative.as_posix()}")

    return errors


def write() -> None:
    AGENTS_MD.write_text(
        adapt_root(CLAUDE_MD.read_text(encoding="utf-8")),
        encoding="utf-8",
    )

    expected = canonical_files()
    AGENT_SKILLS.mkdir(parents=True, exist_ok=True)
    for path in sorted(AGENT_SKILLS.rglob("*"), reverse=True):
        if path.is_file() and path.relative_to(AGENT_SKILLS) not in expected:
            path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass

    for relative, content in expected.items():
        target = AGENT_SKILLS / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="regenera AGENTS.md y .agents/skills desde las fuentes canónicas",
    )
    args = parser.parse_args()

    if args.write:
        write()

    errors = check()
    if errors:
        print("❌ Superficies de agente inconsistentes:")
        for error in errors:
            print(f"  - {error}")
        print("Ejecuta: python scripts/check_agent_surfaces.py --write")
        return 1

    print("🟢 Superficies de agente consistentes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
