#!/usr/bin/env python3
"""Verifica que datos sensibles y artefactos locales no sean candidatos a versionarse."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
POLICY_FILE = REPO / "config" / "data-policy.json"


def git_candidates() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()}


def main() -> int:
    policy = json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    errors: list[str] = []

    ignore_rules = {
        line.strip()
        for line in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    for rule in policy["required_gitignore_rules"]:
        if rule not in ignore_rules:
            errors.append(f"falta regla de .gitignore: {rule}")

    candidates = git_candidates()
    forbidden_files = set(policy["forbidden_tracked_files"])
    forbidden_prefixes = tuple(policy["forbidden_tracked_prefixes"])
    allowed_fixtures = set(policy["tracked_case_fixtures"])
    allowed_validation_fixtures = set(policy.get("tracked_validation_fixtures", []))

    for path in sorted(candidates):
        if path in forbidden_files or path.startswith(forbidden_prefixes):
            errors.append(f"ruta sensible candidata a Git: {path}")
        if path.startswith("corpus/") and path.lower().endswith(".pdf"):
            errors.append(f"PDF del corpus candidato a Git: {path}")
        if path.startswith("casos_de_prueba/") and path not in allowed_fixtures:
            errors.append(f"fixture no autorizado en casos_de_prueba: {path}")
        if path.startswith("tests/fixtures/") and path not in allowed_validation_fixtures:
            errors.append(f"fixture de validación no autorizado: {path}")

    missing_validation = [
        path for path in sorted(allowed_validation_fixtures) if not (REPO / path).is_file()
    ]
    if missing_validation:
        errors.append(f"faltan fixtures de validación autorizados: {missing_validation}")

    regression = set(policy["regression_case_fixtures"])
    allowed_names = {Path(path).name for path in allowed_fixtures}
    if not regression <= allowed_names:
        errors.append("regression_case_fixtures contiene archivos no autorizados")

    if errors:
        print("❌ Política de datos incumplida:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("🟢 Política de datos: rutas sensibles fuera de Git y fixtures autorizados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
