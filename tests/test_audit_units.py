from __future__ import annotations

import unittest

import fetch_tesis_detalle
from itosturre.audit import (
    classify_fuerza_vinculante,
    disclaimer_graduado,
    rubro_keywords,
    vvca_contextualizacion,
    vvca_score,
    vvca_semaforo,
)


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


class LegacyFetchTests(unittest.TestCase):
    def test_rejects_invalid_register_before_external_call(self) -> None:
        with self.assertWarns(DeprecationWarning):
            with self.assertRaises(ValueError):
                fetch_tesis_detalle.fetch("registro-invalido")


if __name__ == "__main__":
    unittest.main()
