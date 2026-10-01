#!/usr/bin/env python3
"""Evalúa el Gold Set del auditor de planes y reporta el recall por regla.

Cada caso declara las reglas que *deben* emitirse (``reglas_esperadas``), las que
*no deben* emitirse (``reglas_prohibidas``) y si el plan debe quedar bloqueado. Un
falso negativo es una regla esperada que no se emitió; un falso positivo, una regla
prohibida que sí se emitió.

Códigos de salida: 0 todos los casos pasan y cada regla PL-001…PL-014 tiene al menos
un caso (más uno limpio) · 1 algún caso falla o falta cobertura · 2 dataset inválido.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from itosturre.plan import LedgerInvalido, esta_bloqueado, lint_ledger  # noqa: E402
from itosturre.plan.lint import REGLAS  # noqa: E402

DEFAULT_GOLD_SET = REPO / "tests" / "fixtures" / "plan_gold_set_v1.json"
SCHEMA_VERSION = "plan-gold-set/1.0"
SUPPORTED_STATUSES = {"seed_synthetic", "operator_curated"}


class PlanGoldSetInvalido(ValueError):
    """El dataset no cumple el contrato del Gold Set de planes."""


def _texto(valor: Any, ubicacion: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise PlanGoldSetInvalido(f"{ubicacion} debe ser texto no vacío")
    return valor


def _reglas(valor: Any, ubicacion: str) -> list[str]:
    if not isinstance(valor, list) or not all(isinstance(r, str) for r in valor):
        raise PlanGoldSetInvalido(f"{ubicacion} debe ser una lista de reglas")
    desconocidas = sorted(set(valor) - set(REGLAS))
    if desconocidas:
        raise PlanGoldSetInvalido(f"{ubicacion} contiene reglas desconocidas: {desconocidas}")
    return valor


def validar_dataset(data: Any) -> dict:
    """Valida la forma del dataset (no el contenido de los ledgers)."""
    if not isinstance(data, dict):
        raise PlanGoldSetInvalido("la raíz debe ser un objeto JSON")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise PlanGoldSetInvalido(
            f"schema_version no soportado: {data.get('schema_version')!r}"
        )
    if data.get("status") not in SUPPORTED_STATUSES:
        raise PlanGoldSetInvalido(f"status no soportado: {data.get('status')!r}")
    casos = data.get("cases")
    if not isinstance(casos, list) or not casos:
        raise PlanGoldSetInvalido("cases debe ser una lista no vacía")

    vistos: set[str] = set()
    for indice, caso in enumerate(casos):
        ubicacion = f"cases[{indice}]"
        if not isinstance(caso, dict):
            raise PlanGoldSetInvalido(f"{ubicacion} debe ser un objeto")
        caso_id = _texto(caso.get("id"), f"{ubicacion}.id")
        if caso_id in vistos:
            raise PlanGoldSetInvalido(f"id duplicado: {caso_id}")
        vistos.add(caso_id)
        _texto(caso.get("descripcion"), f"{ubicacion}.descripcion")
        if not isinstance(caso.get("ledger"), dict):
            raise PlanGoldSetInvalido(f"{ubicacion}.ledger debe ser un objeto")
        if caso.get("documento") is not None and not isinstance(caso["documento"], str):
            raise PlanGoldSetInvalido(f"{ubicacion}.documento debe ser texto o null")
        esperadas = _reglas(caso.get("reglas_esperadas"), f"{ubicacion}.reglas_esperadas")
        prohibidas = _reglas(caso.get("reglas_prohibidas"), f"{ubicacion}.reglas_prohibidas")
        if set(esperadas) & set(prohibidas):
            raise PlanGoldSetInvalido(
                f"{ubicacion}: una regla no puede ser esperada y prohibida a la vez"
            )
        if not isinstance(caso.get("bloqueado_esperado"), bool):
            raise PlanGoldSetInvalido(f"{ubicacion}.bloqueado_esperado debe ser booleano")
    return data


def evaluar_caso(caso: dict) -> dict:
    """Ejecuta el lint de un caso y lo compara con lo esperado."""
    resultado = {
        "id": caso["id"],
        "passed": False,
        "emitidas": [],
        "falsos_negativos": [],
        "falsos_positivos": [],
        "bloqueado": None,
        "bloqueado_esperado": caso["bloqueado_esperado"],
        "error": None,
    }
    try:
        hallazgos = lint_ledger(caso["ledger"], documento=caso.get("documento"))
    except LedgerInvalido as exc:
        resultado["error"] = f"ledger inválido: {exc}"
        resultado["falsos_negativos"] = list(caso["reglas_esperadas"])
        return resultado

    emitidas = sorted({h["regla"] for h in hallazgos})
    bloqueado = esta_bloqueado(hallazgos)
    resultado.update(
        emitidas=emitidas,
        bloqueado=bloqueado,
        falsos_negativos=sorted(set(caso["reglas_esperadas"]) - set(emitidas)),
        falsos_positivos=sorted(set(caso["reglas_prohibidas"]) & set(emitidas)),
    )
    resultado["passed"] = (
        not resultado["falsos_negativos"]
        and not resultado["falsos_positivos"]
        and bloqueado == caso["bloqueado_esperado"]
    )
    return resultado


def evaluar_gold_set(ruta: Path) -> dict:
    """Evalúa todos los casos y calcula recall por regla y cobertura del dataset."""
    try:
        data = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PlanGoldSetInvalido(f"no se pudo leer {ruta}: {exc}") from exc
    validar_dataset(data)

    resultados = [evaluar_caso(caso) for caso in data["cases"]]
    recall: dict[str, dict] = {}
    for regla in sorted(REGLAS):
        esperados = [
            (caso, res)
            for caso, res in zip(data["cases"], resultados)
            if regla in caso["reglas_esperadas"]
        ]
        detectados = sum(regla in res["emitidas"] for _, res in esperados)
        recall[regla] = {
            "esperados": len(esperados),
            "detectados": detectados,
            "recall": round(detectados / len(esperados), 4) if esperados else None,
        }

    reglas_sin_caso = [regla for regla, datos in recall.items() if not datos["esperados"]]
    casos_limpios = sum(not caso["reglas_esperadas"] for caso in data["cases"])
    aprobados = sum(res["passed"] for res in resultados)
    return {
        "gold_set": str(ruta),
        "dataset_status": data["status"],
        "total": len(resultados),
        "passed": aprobados,
        "failed": len(resultados) - aprobados,
        "recall_por_regla": recall,
        "falsos_negativos": [
            {"caso": r["id"], "reglas": r["falsos_negativos"]}
            for r in resultados
            if r["falsos_negativos"]
        ],
        "falsos_positivos": [
            {"caso": r["id"], "reglas": r["falsos_positivos"]}
            for r in resultados
            if r["falsos_positivos"]
        ],
        "reglas_sin_caso": reglas_sin_caso,
        "casos_limpios": casos_limpios,
        "gate_passed": aprobados == len(resultados) and not reglas_sin_caso and casos_limpios > 0,
        "results": resultados,
    }


def _imprimir(reporte: dict) -> None:
    print(f"Gold Set de planes: {reporte['passed']}/{reporte['total']} casos correctos")
    print(f"Estado del dataset: {reporte['dataset_status']}")
    for resultado in reporte["results"]:
        marca = "✅" if resultado["passed"] else "❌"
        detalle = ""
        if not resultado["passed"]:
            partes = []
            if resultado["error"]:
                partes.append(resultado["error"])
            if resultado["falsos_negativos"]:
                partes.append(f"faltan {resultado['falsos_negativos']}")
            if resultado["falsos_positivos"]:
                partes.append(f"sobran {resultado['falsos_positivos']}")
            if resultado["bloqueado"] != resultado["bloqueado_esperado"]:
                partes.append(
                    f"bloqueado={resultado['bloqueado']} "
                    f"(esperado {resultado['bloqueado_esperado']})"
                )
            detalle = " — " + "; ".join(partes)
        print(f"  {marca} {resultado['id']}{detalle}")
    print("Recall por regla:")
    for regla, datos in reporte["recall_por_regla"].items():
        valor = "sin caso" if datos["recall"] is None else f"{datos['recall']:.2f}"
        print(f"  {regla}: {datos['detectados']}/{datos['esperados']} · recall {valor}")
    print(
        f"Falsos negativos: {len(reporte['falsos_negativos'])} caso(s) · "
        f"falsos positivos: {len(reporte['falsos_positivos'])} caso(s) · "
        f"casos limpios: {reporte['casos_limpios']}"
    )
    if reporte["reglas_sin_caso"]:
        print(f"❌ Reglas sin caso en el Gold Set: {reporte['reglas_sin_caso']}")
    if reporte["dataset_status"] == "seed_synthetic":
        print("⚠️  Semilla sintética: mide regresión de reglas, no precisión en planes reales.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluar el Gold Set del auditor de planes")
    parser.add_argument("--file", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--json", action="store_true", help="Emitir el reporte como JSON")
    args = parser.parse_args()
    try:
        reporte = evaluar_gold_set(args.file)
    except PlanGoldSetInvalido as exc:
        print(f"❌ Gold Set de planes inválido: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(reporte, ensure_ascii=False, indent=2))
    else:
        _imprimir(reporte)
    return 0 if reporte["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
