#!/usr/bin/env python3
"""Prepara una base local de prospectos sin recolectar ni enviar mensajes."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.leads.pipeline import prepare_leads, read_csv_rows, write_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Normaliza, deduplica y clasifica prospectos con guardas de consentimiento."
    )
    parser.add_argument("input", type=Path, help="CSV/TSV de entrada")
    parser.add_argument("--output", type=Path, required=True, help="CSV normalizado de salida")
    parser.add_argument("--suppression", type=Path, help="CSV de exclusiones por teléfono o dominio")
    parser.add_argument("--source-type", default="manual_import", help="Origen declarado de los datos")
    parser.add_argument("--source-query", default="", help="Consulta o criterio de procedencia")
    parser.add_argument("--country-code", default="52", help="Código telefónico predeterminado")
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args()
    rows = read_csv_rows(args.input)
    suppression_rows = read_csv_rows(args.suppression) if args.suppression else []
    records, summary = prepare_leads(
        rows,
        suppression_rows=suppression_rows,
        source_type=args.source_type,
        source_query=args.source_query,
        default_country_code=args.country_code,
    )
    write_csv(records, args.output)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    print("Salida local creada. No se enviaron mensajes ni se consultaron servicios externos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
