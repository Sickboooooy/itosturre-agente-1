#!/usr/bin/env python3
"""Fachada DEPRECADA para consultar una tesis por registro IUS.

La implementación Playwright duplicada fue retirada. Nuevos consumidores deben invocar
`services/itosturre-scraper/vvca_audit.ts` o el pipeline `vvca_full.py`.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent
SCRAPER_DIR = REPO / "services" / "itosturre-scraper"
SCRAPER = SCRAPER_DIR / "vvca_audit.ts"
REPLACEMENT = (
    "cd services/itosturre-scraper && "
    "npx ts-node --esm vvca_audit.ts --out <directorio> --no-cache <registro>"
)


def fetch(registro: str) -> dict:
    """Consulta mediante el scraper consolidado y adapta su resultado al formato legacy."""
    warnings.warn(
        "fetch_tesis_detalle.fetch() está deprecado; usa vvca_audit.ts o vvca_full.py",
        DeprecationWarning,
        stacklevel=2,
    )
    if not re.fullmatch(r"\d{6,8}", registro):
        raise ValueError("El registro IUS debe contener entre 6 y 8 dígitos")
    if not SCRAPER.is_file():
        raise RuntimeError("Falta el submódulo services/itosturre-scraper")

    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if not npx:
        raise RuntimeError("No se encontró npx; instala Node.js y las dependencias del scraper")

    with tempfile.TemporaryDirectory(prefix="itosturre-tesis-") as tmp:
        result = subprocess.run(
            [
                npx,
                "ts-node",
                "--esm",
                str(SCRAPER),
                "--out",
                tmp,
                "--no-cache",
                registro,
            ],
            cwd=SCRAPER_DIR,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(f"vvca_audit.ts terminó con código {result.returncode}")

        output = Path(tmp) / "auditoria_vvca.json"
        payload = json.loads(output.read_text(encoding="utf-8"))
        verified = payload.get("verificados", [])
        if not verified:
            raise RuntimeError("El scraper no devolvió una tesis verificada")
        item = dict(verified[0])
        # La captura vive en el directorio temporal y deja de ser válida al regresar.
        item["screenshot"] = ""
        return {
            "registro": registro,
            "url": item.get("url", f"https://sjf2.scjn.gob.mx/detalle/tesis/{registro}"),
            "body_text": item.get("texto_completo", ""),
            "deprecated": True,
            "replacement": REPLACEMENT,
            "vvca": item,
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compatibilidad temporal; usa el scraper SJF consolidado.",
        epilog=f"Reemplazo: {REPLACEMENT}",
    )
    parser.add_argument("registro", help="registro digital IUS (6–8 dígitos)")
    parser.add_argument("salida", nargs="?", help="JSON de salida")
    args = parser.parse_args()

    print("⚠️ DEPRECADO: fetch_tesis_detalle.py delega en vvca_audit.ts.", file=sys.stderr)
    data = fetch(args.registro)
    output = Path(args.salida or f"tesis_{args.registro}_raw.json")
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK -> {output} ({len(data['body_text'])} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
