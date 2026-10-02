#!/usr/bin/env python3
"""Evalúa Gold Sets VVCA y emite métricas reproducibles de calibración."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from itosturre.audit import vvca_score, vvca_semaforo  # noqa: E402
from scoring_vvca import veredicto_global  # noqa: E402

DEFAULT_GOLD_SET = REPO / "tests" / "fixtures" / "vvca_gold_set_v1.json"
SUPPORTED_STATUSES = {
    "seed_synthetic",
    "curation_template",
    "curation_draft",
    "operator_curated",
}
SEMAFOROS = ("🟢", "🟡", "🔴")
SEVERITY = {semaforo: index for index, semaforo in enumerate(SEMAFOROS)}


class GoldSetValidationError(ValueError):
    """El dataset no cumple el contrato estructural del Gold Set."""


def _require_mapping(value: Any, location: str) -> dict:
    if not isinstance(value, dict):
        raise GoldSetValidationError(f"{location} debe ser un objeto JSON")
    return value


def _require_text(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoldSetValidationError(f"{location} debe ser texto no vacío")
    return value.strip()


def _validate_ground_truth(case: dict, location: str) -> None:
    truth = _require_mapping(case.get("ground_truth"), f"{location}.ground_truth")
    review_status = _require_text(
        truth.get("review_status"), f"{location}.ground_truth.review_status"
    )
    if review_status not in {"pending", "approved", "rejected"}:
        raise GoldSetValidationError(
            f"{location}.ground_truth.review_status no es un estado admitido"
        )
    if review_status != "approved":
        return

    for field in ("source_type", "source_locator", "verified_at", "reviewed_by"):
        _require_text(truth.get(field), f"{location}.ground_truth.{field}")


def _require_number(value: Any, location: str, *, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoldSetValidationError(f"{location} debe ser numérico")
    number = float(value)
    if not math.isfinite(number) or not minimum <= number <= maximum:
        raise GoldSetValidationError(
            f"{location} debe estar entre {minimum:g} y {maximum:g}"
        )
    return number


def _require_nonnegative_int(value: Any, location: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoldSetValidationError(f"{location} debe ser entero no negativo")
    return value


def _validate_case_contract(
    case: dict, component: str, location: str, schema_version: str
) -> None:
    inputs = _require_mapping(case.get("input"), f"{location}.input")
    expected = _require_mapping(case.get("expected"), f"{location}.expected")
    if component == "score":
        _require_number(inputs.get("distance"), f"{location}.input.distance", minimum=0, maximum=1)
        for field in ("source_match", "has_source_file"):
            if not isinstance(inputs.get(field), bool):
                raise GoldSetValidationError(f"{location}.input.{field} debe ser booleano")
        score = expected.get("score")
        if schema_version == "1.0" or score is not None:
            if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 100:
                raise GoldSetValidationError(
                    f"{location}.expected.score debe ser entero entre 0 y 100"
                )
    else:
        for field in (
            "tesis_discrepantes",
            "tesis_no_encontradas",
            "tesis_total",
            "tesis_superadas",
        ):
            _require_nonnegative_int(inputs.get(field), f"{location}.input.{field}")
        # R4c: campos opcionales del veredicto (si vienen, enteros no negativos).
        for field in ("articulos_total", "tesis_parciales", "normativa_refutada",
                      "normativa_no_verificable"):
            if field in inputs:
                _require_nonnegative_int(inputs.get(field), f"{location}.input.{field}")
        # R4c (R4-D12): un puntaje nulo solo donde el caso declara "sin citas" en esa
        # dimensión (``articulos_total: 0`` para score_rag; ``tesis_total: 0`` para score_sjf).
        sin_citas = {
            "score_rag": inputs.get("articulos_total") == 0,
            "score_sjf": inputs.get("tesis_total") == 0,
        }
        for field in ("score_rag", "score_sjf"):
            if inputs.get(field) is None and field in inputs and sin_citas[field]:
                continue
            _require_number(
                inputs.get(field), f"{location}.input.{field}", minimum=0, maximum=100
            )
        if not isinstance(expected.get("apto"), bool):
            raise GoldSetValidationError(f"{location}.expected.apto debe ser booleano")


def validate_dataset(data: dict) -> dict:
    """Valida el contrato común y las exigencias adicionales del esquema 2.0."""
    _require_mapping(data, "raíz")
    schema_version = _require_text(data.get("schema_version"), "schema_version")
    status = _require_text(data.get("status"), "status")
    if schema_version not in {"1.0", "2.0"}:
        raise GoldSetValidationError(
            f"schema_version no soportado: {schema_version!r}"
        )
    if status not in SUPPORTED_STATUSES:
        raise GoldSetValidationError(f"status no soportado: {status!r}")

    cases = data.get("cases")
    if not isinstance(cases, list):
        raise GoldSetValidationError("cases debe ser una lista")

    seen: set[str] = set()
    for index, case_value in enumerate(cases):
        location = f"cases[{index}]"
        case = _require_mapping(case_value, location)
        case_id = _require_text(case.get("id"), f"{location}.id")
        if case_id in seen:
            raise GoldSetValidationError(f"id duplicado: {case_id}")
        seen.add(case_id)
        _require_text(case.get("category"), f"{location}.category")
        component = _require_text(case.get("component"), f"{location}.component")
        if component not in {"score", "verdict"}:
            raise GoldSetValidationError(
                f"{location}.component no soportado: {component!r}"
            )
        _validate_case_contract(case, component, location, schema_version)
        expected = case["expected"]
        expected_semaforo = expected.get("semaforo")
        if expected_semaforo not in SEMAFOROS:
            raise GoldSetValidationError(
                f"{location}.expected.semaforo debe ser uno de {SEMAFOROS}"
            )
        if schema_version == "2.0":
            _validate_ground_truth(case, location)

    if schema_version == "2.0":
        curation = _require_mapping(data.get("curation"), "curation")
        minimum_cases = curation.get("minimum_cases")
        if not isinstance(minimum_cases, int) or minimum_cases < 1:
            raise GoldSetValidationError("curation.minimum_cases debe ser entero positivo")
        target = _require_mapping(
            curation.get("target_distribution"), "curation.target_distribution"
        )
        target_total = 0
        for semaforo in SEMAFOROS:
            count = _require_nonnegative_int(
                target.get(semaforo), f"curation.target_distribution.{semaforo}"
            )
            target_total += count
        if target_total != minimum_cases:
            raise GoldSetValidationError(
                "curation.target_distribution debe sumar curation.minimum_cases"
            )

    return data


def evaluate_case(case: dict) -> dict:
    component = case["component"]
    inputs = case["input"]
    if component == "score":
        score = vvca_score(**inputs)
        actual = {"score": score, "semaforo": vvca_semaforo(score)}
    elif component == "verdict":
        verdict = veredicto_global(**inputs)
        actual = {"apto": verdict["apto"], "semaforo": verdict["semaforo"]}
    else:  # El contrato ya se validó; defensa por uso programático directo.
        raise GoldSetValidationError(
            f"Componente Gold Set no soportado: {component}"
        )
    expected = case["expected"]
    return {
        "id": case["id"],
        "category": case["category"],
        "component": component,
        "passed": all(actual.get(key) == value for key, value in expected.items()),
        "expected": expected,
        "actual": actual,
        "review_status": (case.get("ground_truth") or {}).get("review_status"),
    }


def _classification_metrics(results: list[dict]) -> dict:
    confusion = {
        expected: {actual: 0 for actual in SEMAFOROS}
        for expected in SEMAFOROS
    }
    false_green = 0
    false_red = 0
    underclassified = 0
    overclassified = 0
    for item in results:
        expected = item["expected"].get("semaforo")
        actual = item["actual"].get("semaforo")
        if expected not in SEVERITY or actual not in SEVERITY:
            continue
        confusion[expected][actual] += 1
        if actual == "🟢" and expected != "🟢":
            false_green += 1
        if actual == "🔴" and expected == "🟢":
            false_red += 1
        if SEVERITY[actual] < SEVERITY[expected]:
            underclassified += 1
        elif SEVERITY[actual] > SEVERITY[expected]:
            overclassified += 1
    return {
        "confusion_matrix": confusion,
        "false_green": false_green,
        "false_red": false_red,
        "underclassified": underclassified,
        "overclassified": overclassified,
    }


def _category_metrics(results: list[dict]) -> dict:
    grouped: dict[str, Counter] = defaultdict(Counter)
    for item in results:
        grouped[item["category"]]["total"] += 1
        grouped[item["category"]]["passed" if item["passed"] else "failed"] += 1
    return {category: dict(counts) for category, counts in sorted(grouped.items())}


def _review_metrics(data: dict, total: int) -> dict:
    if data["schema_version"] == "1.0":
        return {
            "applicable": False,
            "approved": 0,
            "pending": 0,
            "rejected": 0,
            "minimum_cases": None,
            "dataset_ready_for_calibration": False,
        }

    statuses = Counter(
        case["ground_truth"]["review_status"] for case in data["cases"]
    )
    minimum_cases = data["curation"]["minimum_cases"]
    target = data["curation"]["target_distribution"]
    approved_distribution = Counter(
        case["expected"]["semaforo"]
        for case in data["cases"]
        if case["ground_truth"]["review_status"] == "approved"
    )
    distribution_ready = all(
        approved_distribution[semaforo] >= target[semaforo]
        for semaforo in SEMAFOROS
    )
    ready = (
        data["status"] == "operator_curated"
        and total >= minimum_cases
        and statuses["approved"] == total
        and distribution_ready
    )
    return {
        "applicable": True,
        "approved": statuses["approved"],
        "pending": statuses["pending"],
        "rejected": statuses["rejected"],
        "minimum_cases": minimum_cases,
        "target_distribution": target,
        "approved_distribution": {
            semaforo: approved_distribution[semaforo] for semaforo in SEMAFOROS
        },
        "distribution_ready": distribution_ready,
        "dataset_ready_for_calibration": ready,
    }


def evaluate_gold_set(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GoldSetValidationError(f"no se pudo leer {path}: {exc}") from exc
    data = validate_dataset(raw)
    results = [evaluate_case(case) for case in data["cases"]]
    passed = sum(item["passed"] for item in results)
    classification = _classification_metrics(results)
    review = _review_metrics(data, len(results))
    regression_gate_passed = bool(results) and passed == len(results)
    release_ready = (
        review["dataset_ready_for_calibration"]
        and regression_gate_passed
        and classification["false_green"] == 0
    )
    return {
        "gold_set": str(path),
        "schema_version": data["schema_version"],
        "dataset_status": data["status"],
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "accuracy": round(passed / len(results), 4) if results else 0.0,
        "regression_gate_passed": regression_gate_passed,
        "release_ready": release_ready,
        "classification": classification,
        "review": review,
        "by_category": _category_metrics(results),
        "results": results,
    }


def _print_report(report: dict) -> None:
    print(f"Gold Set VVCA: {report['passed']}/{report['total']} casos correctos")
    print(f"Estado del dataset: {report['dataset_status']}")
    for item in report["results"]:
        print(f"  {'✅' if item['passed'] else '❌'} {item['id']}")
    metrics = report["classification"]
    print(
        "Métricas críticas: "
        f"falsos verdes={metrics['false_green']} · "
        f"falsos rojos={metrics['false_red']}"
    )
    if report["dataset_status"] == "seed_synthetic":
        print("⚠️  Semilla sintética: aún no calibra empíricamente los umbrales.")
    elif report["dataset_status"] in {"curation_template", "curation_draft"}:
        review = report["review"]
        print(
            "⚠️  Dataset en curaduría: "
            f"{review['approved']}/{review['minimum_cases']} casos aprobados mínimos."
        )
    elif not report["review"]["dataset_ready_for_calibration"]:
        print("❌ Dataset marcado como curado, pero no satisface el contrato de revisión.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluar Gold Set VVCA")
    parser.add_argument("--file", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--json", action="store_true", help="Emitir el reporte como JSON")
    args = parser.parse_args()
    try:
        report = evaluate_gold_set(args.file)
    except GoldSetValidationError as exc:
        print(f"❌ Gold Set inválido: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_report(report)

    if report["dataset_status"] == "seed_synthetic":
        return 0 if report["regression_gate_passed"] else 1
    if report["dataset_status"] == "operator_curated":
        return 0 if report["release_ready"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
