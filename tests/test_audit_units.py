from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fetch_tesis_detalle
from itosturre.audit import (
    build_trace_record,
    classify_fuerza_vinculante,
    disclaimer_graduado,
    rubro_keywords,
    traceability_bundle,
    vvca_contextualizacion,
    vvca_score,
    vvca_semaforo,
)
from scripts.evaluate_gold_set import GoldSetValidationError, evaluate_gold_set


class PolicyTests(unittest.TestCase):
    def test_score_respects_source_penalties(self) -> None:
        self.assertEqual(vvca_score(0.10, True, True), 90)
        self.assertEqual(vvca_score(0.10, False, False), 65)

    def test_semaforo_thresholds(self) -> None:
        self.assertEqual(vvca_semaforo(85), "🟢")
        self.assertEqual(vvca_semaforo(60), "🟡")
        self.assertEqual(vvca_semaforo(59), "🔴")

    def test_disclaimer_blocks_red_documents(self) -> None:
        result = disclaimer_graduado({"semaforo": "🔴", "razon": "cita falsa"})
        self.assertTrue(result["requiere_acuse"])
        self.assertIn("NO PRESENTAR", result["encabezado"])


class JurisprudenceTests(unittest.TestCase):
    def test_binding_force_taxonomy(self) -> None:
        cases = {
            "P./J. 89/2026 (12a.)": "[J-PLENO]",
            "1a./J. 68/2022 (11a.)": "[J-SALA]",
            "PR.A.CS. J/1 A (11a.)": "[PR]",
            "PC.III.P. J/7 P": "[PC]",
            "I.1o.P. J/7": "[J-TCC]",
            "1a. CCCXL/2015": "[SCJN-P]",
            "I.5o.C.220 C (11a.)": "[TA]",
        }
        for key, expected in cases.items():
            with self.subTest(key=key):
                self.assertEqual(classify_fuerza_vinculante(key)["sello"], expected)

    def test_rubro_keywords_omits_stop_words(self) -> None:
        words = rubro_keywords("PRISIÓN PREVENTIVA PARA PERSONAS IMPUTADAS")
        self.assertIn("prisión", words)
        self.assertNotIn("para", words)


class ContextTests(unittest.TestCase):
    def test_known_and_unknown_sources(self) -> None:
        self.assertIn("Constitucional", vvca_contextualizacion("CPEUM_2026.pdf"))
        self.assertIn("Verificar", vvca_contextualizacion("fuente_desconocida.pdf"))


class TraceabilityTests(unittest.TestCase):
    def test_trace_is_stable_and_distinguishes_unavailable_from_refuted(self) -> None:
        common = {
            "reference": "Registro digital SYN-001",
            "ref_type": "jurisprudencia",
            "method": "corpus_local",
            "reason": "Fuente ausente del corpus de prueba",
            "semaforo": "🟡",
            "source_file": "jurisprudencia_seed.json",
            "checked_at": "2026-07-31T00:00:00Z",
        }
        first = build_trace_record(status="not_verifiable", **common)
        second = build_trace_record(status="not_verifiable", **common)
        self.assertEqual(first["trace_id"], second["trace_id"])
        self.assertEqual(first["verification"]["status"], "not_verifiable")
        self.assertTrue(first["human_review_required"])

        bundle = traceability_bundle([first])
        self.assertEqual(bundle["summary"]["by_status"]["refuted"], 0)
        self.assertEqual(bundle["summary"]["by_status"]["not_verifiable"], 1)


class GoldSetTests(unittest.TestCase):
    def test_seed_gold_set_passes(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "vvca_gold_set_v1.json"
        report = evaluate_gold_set(fixture)
        self.assertEqual(report["failed"], 0)
        self.assertEqual(report["dataset_status"], "seed_synthetic")
        self.assertTrue(report["regression_gate_passed"])
        self.assertFalse(report["release_ready"])

    def test_v2_green_candidates_are_valid_but_not_calibration_ready(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "vvca_gold_set_v2.json"
        report = evaluate_gold_set(fixture)
        self.assertEqual(report["total"], 10)
        self.assertEqual(report["passed"], 10)
        self.assertEqual(report["review"]["pending"], 10)
        self.assertEqual(report["review"]["approved"], 0)
        self.assertEqual(report["dataset_status"], "curation_draft")
        self.assertTrue(report["regression_gate_passed"])
        self.assertFalse(report["review"]["dataset_ready_for_calibration"])
        self.assertFalse(report["release_ready"])

    def test_v2_reports_false_green_and_false_red(self) -> None:
        data = {
            "schema_version": "2.0",
            "status": "curation_draft",
            "curation": {
                "minimum_cases": 2,
                "target_distribution": {"🟢": 1, "🟡": 0, "🔴": 1},
            },
            "cases": [
                {
                    "id": "falso_verde",
                    "category": "riesgo_subestimado",
                    "component": "score",
                    "input": {
                        "distance": 0.1,
                        "source_match": True,
                        "has_source_file": True,
                    },
                    "expected": {"semaforo": "🔴"},
                    "ground_truth": {"review_status": "pending"},
                },
                {
                    "id": "falso_rojo",
                    "category": "riesgo_sobreestimado",
                    "component": "score",
                    "input": {
                        "distance": 0.6,
                        "source_match": True,
                        "has_source_file": True,
                    },
                    "expected": {"semaforo": "🟢"},
                    "ground_truth": {"review_status": "pending"},
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "gold.json"
            fixture.write_text(json.dumps(data), encoding="utf-8")
            report = evaluate_gold_set(fixture)
        self.assertEqual(report["classification"]["false_green"], 1)
        self.assertEqual(report["classification"]["false_red"], 1)
        self.assertEqual(report["classification"]["underclassified"], 1)
        self.assertEqual(report["classification"]["overclassified"], 1)

    def test_v2_approved_case_requires_provenance(self) -> None:
        data = {
            "schema_version": "2.0",
            "status": "operator_curated",
            "curation": {
                "minimum_cases": 1,
                "target_distribution": {"🟢": 1, "🟡": 0, "🔴": 0},
            },
            "cases": [
                {
                    "id": "sin_procedencia",
                    "category": "cita_verdadera",
                    "component": "score",
                    "input": {
                        "distance": 0.1,
                        "source_match": True,
                        "has_source_file": True,
                    },
                    "expected": {"semaforo": "🟢"},
                    "ground_truth": {"review_status": "approved"},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "gold.json"
            fixture.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(GoldSetValidationError):
                evaluate_gold_set(fixture)

    def test_v2_operator_curated_case_can_be_release_ready(self) -> None:
        data = {
            "schema_version": "2.0",
            "status": "operator_curated",
            "curation": {
                "minimum_cases": 1,
                "target_distribution": {"🟢": 1, "🟡": 0, "🔴": 0},
            },
            "cases": [
                {
                    "id": "cita_confirmada",
                    "category": "cita_verdadera",
                    "component": "score",
                    "input": {
                        "distance": 0.1,
                        "source_match": True,
                        "has_source_file": True,
                    },
                    "expected": {"semaforo": "🟢"},
                    "ground_truth": {
                        "source_type": "corpus_oficial",
                        "source_locator": "fixture público sintético",
                        "verified_at": "2026-09-16",
                        "reviewed_by": "operador_prueba",
                        "review_status": "approved",
                    },
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "gold.json"
            fixture.write_text(json.dumps(data), encoding="utf-8")
            report = evaluate_gold_set(fixture)
        self.assertTrue(report["review"]["dataset_ready_for_calibration"])
        self.assertTrue(report["release_ready"])

    def test_v2_rejects_invalid_score_input(self) -> None:
        data = {
            "schema_version": "2.0",
            "status": "curation_draft",
            "curation": {
                "minimum_cases": 1,
                "target_distribution": {"🟢": 0, "🟡": 0, "🔴": 1},
            },
            "cases": [
                {
                    "id": "distancia_invalida",
                    "category": "contrato_invalido",
                    "component": "score",
                    "input": {
                        "distance": 4,
                        "source_match": True,
                        "has_source_file": True,
                    },
                    "expected": {"semaforo": "🔴"},
                    "ground_truth": {"review_status": "pending"},
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temp:
            fixture = Path(temp) / "gold.json"
            fixture.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(GoldSetValidationError):
                evaluate_gold_set(fixture)


class LegacyFetchTests(unittest.TestCase):
    def test_rejects_invalid_register_before_external_call(self) -> None:
        with self.assertWarns(DeprecationWarning):
            with self.assertRaises(ValueError):
                fetch_tesis_detalle.fetch("registro-invalido")


if __name__ == "__main__":
    unittest.main()
