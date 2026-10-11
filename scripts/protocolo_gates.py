#!/usr/bin/env python3
"""Corre los gates G1–G4 sobre un protocolo de materia y deja el reporte en JSON.

Uso:
  python scripts/protocolo_gates.py <protocolo.json> [--ficha fichas.json]
         [--evidencia evidencia.json] [--sin-rag] [--salida reporte.json]

  --ficha      JSON {materia: {"codigo", "etapas", "principios", "estandar"}}: la ficha
               procesal del simulador de destino (vive fuera de este repo). Sin ella, G2
               no comprueba que el protocolo no la repita y lo avisa.
  --evidencia  JSON {"tesis": [...]} con la verificación del scraper en el SJF. Por
               omisión, <protocolo>.evidencia.json si existe.
  --sin-rag    no corre G3 (útil sin índice); el resultado queda INCOMPLETO.

G3 usa el índice de CHROMA_PATH y el intérprete actual (el del venv con el corpus).

Salida: 0 todos los gates corridos y sin ERROR · 1 algún ERROR · 2 uso o archivo
inválido · 3 sin ERROR pero con algún gate sin correr.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.protocolos.contrato import ERROR, canonizar  # noqa: E402
from itosturre.protocolos.gates import GATES, correr_gates  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _leer_json(ruta: Path, que: str):
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"❌ No se pudo leer {que} ({ruta}): {exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gates G1–G4 de un protocolo de materia")
    parser.add_argument("protocolo", type=Path)
    parser.add_argument("--ficha", type=Path)
    parser.add_argument("--evidencia", type=Path)
    parser.add_argument("--sin-rag", action="store_true")
    parser.add_argument("--salida", type=Path)
    args = parser.parse_args(argv)

    try:
        protocolo = _leer_json(args.protocolo, "el protocolo")
        fichas = _leer_json(args.ficha, "la ficha") if args.ficha else None
        ruta_evidencia = args.evidencia or args.protocolo.with_name(f"{args.protocolo.stem}.evidencia.json")
        evidencia = _leer_json(ruta_evidencia, "la evidencia") if ruta_evidencia.exists() else None
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2

    ficha = None
    if isinstance(fichas, dict) and isinstance(protocolo, dict):
        ficha = fichas.get(canonizar(protocolo).get("materia", ""))
    reporte = correr_gates(protocolo, ficha=ficha, evidencia=evidencia, con_rag=not args.sin_rag)
    datos = reporte.to_dict()
    texto = json.dumps(datos, ensure_ascii=False, indent=2)
    if args.salida:
        args.salida.write_text(texto, encoding="utf-8")
    else:
        print(texto)

    estados = " · ".join(f"{g} {datos['gates'][g]}" for g in GATES)
    errores = sum(1 for h in reporte.hallazgos if h.severidad == ERROR)
    avisos = len(reporte.hallazgos) - errores
    print(f"{'🟢' if reporte.ok else '🔴'} {datos['clave'] or '(sin clave)'} — {estados} — "
          f"{errores} error(es), {avisos} aviso(s) — sha256 {datos['sha256'][:12]}", file=sys.stderr)
    if not reporte.ok:
        return 1
    if any(datos["gates"][g] == "NO_CORRIDO" for g in GATES):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
