#!/usr/bin/env python3
"""Evalúa el Gold Set sintético de políticas VVCA y emite métricas reproducibles."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from itosturre.audit import vvca_score, vvca_semaforo  # noqa: E402
from scoring_vvca import veredicto_global  # noqa: E402

DEFAULT_GOLD_SET = REPO / "tests" / "fixtures" / "vvca_gold_set_v1.json"


def evaluate_case(case: dict) -> dict:
    component = case["component"]
    inputs = case["input"]
    if component == "score":
        score = vvca_score(**inputs)
        actual = {"score": score, "semaforo": vvca_semaforo(score)}
    elif component == "verdict":
        verdict = veredicto_global(**inputs)
        actual = {"apto": verdict["apto"], "semaforo": verdict["semaforo"]}
    else:
        raise ValueError(f"Componente Gold Set no soportado: {component}")
    expected = case["expected"]
    return {
        "id": case["id"],
        "category": case["category"],
        "passed": all(actual.get(key) == value for key, value in expected.items()),
        "expected": expected,
        "actual": actual,
    }


def evaluate_gold_set(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in data["cases"]]
    passed = sum(item["passed"] for item in results)
    return {
        "gold_set": str(path),
        "schema_version": data["schema_version"],
        "dataset_status": data["status"],
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "accuracy": round(passed / len(results), 4) if results else 0.0,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluar Gold Set VVCA")
    parser.add_argument("--file", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--json", action="store_true", help="Emitir el reporte como JSON")
    args = parser.parse_args()
    report = evaluate_gold_set(args.file)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"Gold Set VVCA: {report['passed']}/{report['total']} casos correctos")
        print(f"Estado del dataset: {report['dataset_status']}")
        for item in report["results"]:
            print(f"  {'✅' if item['passed'] else '❌'} {item['id']}")
        if report["dataset_status"] == "seed_synthetic":
            print("⚠️  Semilla sintética: aún no calibra empíricamente los umbrales.")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
