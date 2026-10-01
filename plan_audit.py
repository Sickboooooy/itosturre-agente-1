#!/usr/bin/env python3
"""plan_audit.py — auditor determinista de planes sobre ledger ``plan-ledger/1.0``.

Valida reglas observables (PL-001 … PL-014) sobre el ledger de afirmaciones,
evidencias, contradicciones y decisiones de un plan y, si se pasa el documento,
que cada artículo, registro digital o clave de tesis mencionado esté cubierto por
una afirmación. Sin red y sin LLM: no sustituye la verificación VVCA ni la decisión
del abogado.

Uso:
  python plan_audit.py lint --ledger plan.ledger.json
  python plan_audit.py lint --ledger plan.ledger.json --documento plan.md \\
      --json hallazgos.json --md reporte.md
  python plan_audit.py hash --ledger plan.ledger.json [--afirmacion A1]

Códigos de salida de ``lint``: 0 sin hallazgos BLOQUEANTES · 1 con BLOQUEANTES ·
2 entrada inválida (archivo ilegible, JSON roto, esquema inválido, --json/--md que
coinciden entre sí o con una entrada, o destino no escribible).

``hash`` imprime el ``contenido_sha256`` vigente de cada afirmación, que es el valor
que debe registrar la persona que la aprueba (``aprobacion.contenido_sha256``).

En Windows anteponer el intérprete del venv: ``./venv/Scripts/python.exe``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.plan import (  # noqa: E402
    LedgerInvalido,
    cargar_ledger,
    contenido_sha256,
    esta_bloqueado,
    lint_ledger,
    reporte_markdown,
    resumen_severidades,
)

SALIDA_OK = 0
SALIDA_BLOQUEADO = 1
SALIDA_ENTRADA_INVALIDA = 2


def _utf8() -> None:
    # Consola Windows (cp1252) no codifica acentos ni símbolos: forzar UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def _entrada_invalida(errores: list[str], titulo: str = "Entrada inválida") -> int:
    print(f"❌ {titulo}:", file=sys.stderr)
    for error in errores:
        print(f"  - {error}", file=sys.stderr)
    return SALIDA_ENTRADA_INVALIDA


def _misma_ruta(primera: str, segunda: str) -> bool:
    """Compara rutas resueltas (sin distinguir mayúsculas en Windows) o, si ambas
    existen, con ``os.path.samefile`` (detecta enlaces y alias)."""
    a, b = Path(primera), Path(segunda)
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return os.path.normcase(os.path.abspath(primera)) == os.path.normcase(
            os.path.abspath(segunda)
        )


def _validar_destinos(args: argparse.Namespace) -> list[str]:
    """Errores de --json/--md: colisiones entre sí o con las entradas, y destinos no
    escribibles. Se valida todo antes de escribir el primer archivo."""
    entradas = [
        (nombre, ruta)
        for nombre, ruta in (("--ledger", args.ledger), ("--documento", args.documento))
        if ruta
    ]
    salidas = [
        (nombre, ruta) for nombre, ruta in (("--json", args.json), ("--md", args.md)) if ruta
    ]
    errores: list[str] = []
    if len(salidas) == 2 and _misma_ruta(salidas[0][1], salidas[1][1]):
        errores.append("--json y --md apuntan al mismo archivo")
    for salida, ruta_salida in salidas:
        for entrada, ruta_entrada in entradas:
            if _misma_ruta(ruta_salida, ruta_entrada):
                errores.append(f"{salida} coincide con {entrada}: sobrescribiría la entrada")
        destino = Path(ruta_salida)
        if destino.is_dir():
            errores.append(f"{salida} apunta a un directorio: {ruta_salida}")
        elif not destino.parent.is_dir():
            errores.append(f"{salida}: no existe el directorio {destino.parent}")
    return errores


def cmd_lint(args: argparse.Namespace) -> int:
    errores = _validar_destinos(args)
    if errores:
        return _entrada_invalida(errores)
    try:
        ledger = cargar_ledger(args.ledger)
    except LedgerInvalido as exc:
        return _entrada_invalida(exc.errores)

    documento = None
    if args.documento:
        try:
            documento = Path(args.documento).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            return _entrada_invalida([f"no se pudo leer el documento {args.documento}: {exc}"])

    hallazgos = lint_ledger(ledger, documento=documento)
    bloqueado = esta_bloqueado(hallazgos)
    severidades = resumen_severidades(hallazgos)

    escrituras: list[tuple[str, str]] = []
    if args.json:
        salida = {
            "schema_version": ledger["schema_version"],
            "plan": ledger["plan"],
            "documento": args.documento,
            "bloqueado": bloqueado,
            "resumen": severidades,
            "hallazgos": hallazgos,
        }
        escrituras.append((args.json, json.dumps(salida, ensure_ascii=False, indent=2) + "\n"))
    if args.md:
        escrituras.append((args.md, reporte_markdown(ledger, hallazgos)))
    for destino, contenido in escrituras:
        try:
            Path(destino).write_text(contenido, encoding="utf-8")
        except OSError as exc:
            return _entrada_invalida([f"no se pudo escribir {destino}: {exc}"], "Error de escritura")

    conteo = " · ".join(f"{severidad}={n}" for severidad, n in severidades.items())
    print(f"Auditoría de plan {ledger['plan']['id']}: {len(hallazgos)} hallazgo(s) · {conteo}")
    for hallazgo in hallazgos:
        print(
            f"  [{hallazgo['severidad']}] {hallazgo['regla']} {hallazgo['objetivo']}: "
            f"{hallazgo['mensaje']}"
        )
    if documento is None:
        print("  (PL-014 de cobertura no evaluada: no se pasó --documento)")
    print(
        "Resultado: BLOQUEADO"
        if bloqueado
        else "Resultado: sin hallazgos bloqueantes (no equivale a aprobación jurídica)"
    )
    return SALIDA_BLOQUEADO if bloqueado else SALIDA_OK


def cmd_hash(args: argparse.Namespace) -> int:
    try:
        ledger = cargar_ledger(args.ledger)
    except LedgerInvalido as exc:
        return _entrada_invalida(exc.errores)
    afirmaciones = ledger["afirmaciones"]
    if args.afirmacion:
        afirmaciones = [a for a in afirmaciones if a["id"] == args.afirmacion]
        if not afirmaciones:
            return _entrada_invalida([f"no existe la afirmación {args.afirmacion}"])
    for afirmacion in afirmaciones:
        print(f"{afirmacion['id']}\t{contenido_sha256(afirmacion)}")
    return SALIDA_OK


def main(argv: list[str] | None = None) -> int:
    _utf8()
    parser = argparse.ArgumentParser(
        description="Auditor determinista de planes sobre ledger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    lint = sub.add_parser("lint", help="Aplicar las reglas PL-001 … PL-014")
    lint.add_argument("--ledger", required=True, help="Ledger JSON plan-ledger/1.0")
    lint.add_argument("--documento", help="Documento del plan (.md/.txt) para PL-014")
    lint.add_argument("--json", help="Escribir los hallazgos en este archivo JSON")
    lint.add_argument("--md", help="Escribir el reporte Markdown en este archivo")
    lint.set_defaults(func=cmd_lint)

    hash_ = sub.add_parser("hash", help="Calcular el contenido_sha256 de las afirmaciones")
    hash_.add_argument("--ledger", required=True, help="Ledger JSON plan-ledger/1.0")
    hash_.add_argument("--afirmacion", help="ID de una sola afirmación")
    hash_.set_defaults(func=cmd_hash)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
