#!/usr/bin/env python3
"""Compila y ejecuta las pruebas offline de vigencia y resiliencia del scraper SJF.

Se compila a un directorio temporal dentro del submódulo para que Node pueda resolver
sus dependencias. Esto evita la incompatibilidad de resolución ESM de `ts-node` observada
en Node 24 y no modifica archivos versionados del scraper.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
SCRAPER = REPO / "services" / "itosturre-scraper"


def main() -> int:
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    node = shutil.which("node.exe") or shutil.which("node")
    if not npx or not node:
        print("❌ Se requieren Node.js y npx para probar el scraper.")
        return 2

    with tempfile.TemporaryDirectory(prefix=".vigencia-test-", dir=SCRAPER) as tmp:
        out_dir = Path(tmp)
        compile_result = subprocess.run(
            [
                npx,
                "tsc",
                "--outDir",
                str(out_dir),
                "--module",
                "NodeNext",
                "--moduleResolution",
                "NodeNext",
                "--allowImportingTsExtensions",
                "--rewriteRelativeImportExtensions",
                "--target",
                "ES2022",
                "--esModuleInterop",
                "--skipLibCheck",
                "vigencia.test.ts",
                "resilience.test.ts",
                "vvca_audit.ts",
                "sjf_resilience.ts",
            ],
            cwd=SCRAPER,
            check=False,
        )
        if compile_result.returncode:
            return compile_result.returncode

        for test_file in ("vigencia.test.js", "resilience.test.js"):
            result = subprocess.run(
                [node, str(out_dir / test_file)],
                cwd=SCRAPER,
                check=False,
            )
            if result.returncode:
                return result.returncode
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
