"""Pruebas de integración del orquestador VVCA, sin corpus ni red.

Los subprocesos se simulan en el borde del sistema. Las pruebas ejercen el CLI real,
la persistencia de ``vvca_full.json`` y la política de fallo cerrado.
"""
from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import vvca_full


VALID_AUDIT = {
    "status": "ok",
    "vvca_summary": {
        "veredicto": {"apto": True, "semaforo": "🟢"},
    },
    "retrieved_sources": [],
    "traceability": {
        "schema_version": "1.0",
        "records": [],
        "summary": {"total": 0},
    },
}

VALID_SJF = {
    "schema_version": "2.0",
    "verificados": [],
    "propuestas": [],
    "consultas_busqueda": [],
}


def audit_with_normative_chunk() -> dict:
    payload = json.loads(json.dumps(VALID_AUDIT, ensure_ascii=False))
    payload["retrieved_sources"] = [
        {
            "ref_type": "normativa",
            "reference": "Art. 1 LEY SINTÉTICA",
            "vvca": {
                "C_contextualizacion": "Fixture sintético",
                "score": 90,
            },
        }
    ]
    return payload


class FakeSubprocesses:
    def __init__(
        self,
        *,
        missing: list[str] | None = None,
        corpus_returncode: int | None = None,
        corpus_stdout: str | None = None,
        audit_returncode: int = 0,
        audit_stdout: str | None = None,
        scraper_returncode: int = 0,
        sjf_output: str = "valid",
        capture_returncode: int = 0,
        capture_output: bool = True,
        corpus_oserror: bool = False,
    ) -> None:
        self.missing = missing or []
        self.corpus_returncode = (
            corpus_returncode
            if corpus_returncode is not None
            else (1 if self.missing else 0)
        )
        self.corpus_stdout = corpus_stdout
        self.audit_returncode = audit_returncode
        self.audit_stdout = audit_stdout
        self.scraper_returncode = scraper_returncode
        self.sjf_output = sjf_output
        self.capture_returncode = capture_returncode
        self.capture_output = capture_output
        self.corpus_oserror = corpus_oserror
        self.calls: list[list[str]] = []

    def __call__(self, cmd: list, **_kwargs) -> subprocess.CompletedProcess:
        parts = [str(part) for part in cmd]
        self.calls.append(parts)
        joined = " ".join(parts)

        if "check_corpus.py" in joined:
            if self.corpus_oserror:
                raise OSError("intérprete no disponible")
            stdout = self.corpus_stdout
            if stdout is None:
                stdout = json.dumps({"missing": self.missing})
            return subprocess.CompletedProcess(
                parts, self.corpus_returncode, stdout=stdout, stderr=""
            )

        if "OpenNotebook.py" in joined:
            stdout = self.audit_stdout
            if stdout is None:
                stdout = json.dumps(VALID_AUDIT, ensure_ascii=False)
            return subprocess.CompletedProcess(
                parts,
                self.audit_returncode,
                stdout=stdout,
                stderr="fallo RAG" if self.audit_returncode else "",
            )

        if "vvca_audit.ts" in joined:
            if self.scraper_returncode == 0 and self.sjf_output != "missing":
                out_index = parts.index("--out") + 1
                output = Path(parts[out_index]) / "auditoria_vvca.json"
                if self.sjf_output == "invalid":
                    output.write_text("no-json", encoding="utf-8")
                elif self.sjf_output == "wrong-schema":
                    output.write_text(
                        json.dumps({"schema_version": "1.0"}), encoding="utf-8"
                    )
                else:
                    output.write_text(
                        json.dumps(VALID_SJF, ensure_ascii=False), encoding="utf-8"
                    )
            return subprocess.CompletedProcess(
                parts,
                self.scraper_returncode,
                stdout="",
                stderr="fallo SJF" if self.scraper_returncode else "",
            )

        if "capturar_rag.py" in joined:
            if self.capture_returncode == 0 and self.capture_output:
                out_index = parts.index("--out") + 1
                output = Path(parts[out_index]) / "rag_chunks.png"
                output.write_bytes(b"synthetic-png")
            return subprocess.CompletedProcess(
                parts,
                self.capture_returncode,
                stdout="",
                stderr="fallo captura" if self.capture_returncode else "",
            )

        raise AssertionError(f"Subproceso inesperado: {joined}")


class RunContractTests(unittest.TestCase):
    def test_run_raises_for_checked_nonzero_result(self) -> None:
        completed = subprocess.CompletedProcess(["tool"], 9, stdout="", stderr="boom")
        with patch("vvca_full.subprocess.run", return_value=completed):
            with self.assertRaises(vvca_full.PipelineStepError) as raised:
                vvca_full.run(["tool"], step="demo", check=True)
        self.assertEqual(raised.exception.step, "demo")
        self.assertEqual(raised.exception.result.returncode, 9)


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.draft = self.root / "borrador.md"
        self.draft.write_text("Caso enteramente sintético.", encoding="utf-8")
        self.case = self.root / "caso"

    def run_pipeline(
        self,
        fake: FakeSubprocesses,
        *extra: str,
        npx: str | None = "npx.cmd",
        memory_error: Exception | None = None,
    ) -> tuple[int, dict]:
        memory_side_effect = memory_error
        with (
            patch("vvca_full.subprocess.run", side_effect=fake),
            patch("vvca_full.shutil.which", return_value=npx),
            patch(
                "itosturre.memoria.puente.registrar_auditoria",
                return_value=0,
                side_effect=memory_side_effect,
            ),
        ):
            code = vvca_full.main(
                [
                    "--caso",
                    str(self.case),
                    "--borrador",
                    str(self.draft),
                    "--no-popup-articulos",
                    *extra,
                ]
            )
        summary = json.loads((self.case / "vvca_full.json").read_text(encoding="utf-8"))
        return code, summary

    def test_success_writes_ok_summary(self) -> None:
        code, summary = self.run_pipeline(FakeSubprocesses())
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["pasos"]["rag_audit"]["status"], "ok")
        self.assertEqual(summary["pasos"]["sjf"]["status"], "not_requested")
        self.assertTrue((self.case / "audit_rag.json").exists())

    def test_audit_nonzero_fails_closed(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(audit_returncode=7)
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["errors"][0]["step"], "rag_audit")
        self.assertFalse((self.case / "audit_rag.json").exists())

    def test_invalid_audit_json_fails_closed(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(audit_stdout="no-json")
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertIn("JSON válido", summary["errors"][0]["message"])

    def test_non_ok_audit_status_fails_closed(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(audit_stdout=json.dumps({"status": "corpus_incomplete"}))
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertIn("no utilizable", summary["errors"][0]["message"])

    def test_incomplete_corpus_blocks_without_force(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(missing=["LEY SINTÉTICA"])
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["errors"][0]["step"], "check_corpus")

    def test_corpus_launcher_error_is_persisted(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(corpus_oserror=True)
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["errors"][0]["step"], "check_corpus")
        self.assertIn("no se pudo iniciar", summary["errors"][0]["message"])

    def test_force_authorizes_partial_corpus(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(missing=["LEY SINTÉTICA"]), "--force"
        )
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["pasos"]["check_corpus"]["status"], "partial")

    def test_requested_sjf_without_npx_fails_closed(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(), "--registros", "2000001", npx=None
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["errors"][0]["step"], "sjf")

    def test_requested_sjf_can_be_explicitly_partial(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(),
            "--registros",
            "2000001",
            "--allow-partial-sjf",
            npx=None,
        )
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["pasos"]["sjf"]["status"], "partial")

    def test_scraper_nonzero_fails_closed(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(scraper_returncode=4), "--registros", "2000001"
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["errors"][0]["returncode"], 4)

    def test_scraper_must_create_fresh_output(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(sjf_output="missing"), "--registros", "2000001"
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertIn("no produjo", summary["errors"][0]["message"])

    def test_scraper_output_must_match_contract(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(sjf_output="wrong-schema"), "--registros", "2000001"
        )
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertIn("schema_version", summary["errors"][0]["message"])

    def test_valid_scraper_output_completes(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(), "--registros", "2000001"
        )
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["pasos"]["sjf"]["schema_version"], "2.0")

    def test_explicit_no_sjf_is_auditable_skip(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(), "--registros", "2000001", "--no-sjf"
        )
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["pasos"]["sjf"]["status"], "skipped")

    def test_memory_failure_is_warning_not_pipeline_failure(self) -> None:
        code, summary = self.run_pipeline(
            FakeSubprocesses(), memory_error=RuntimeError("memoria no disponible")
        )
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["pasos"]["memoria"]["status"], "warning")
        self.assertEqual(summary["warnings"][0]["step"], "memoria")

    def test_rag_capture_failure_is_blocking(self) -> None:
        fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_normative_chunk(), ensure_ascii=False),
            capture_returncode=5,
        )
        code, summary = self.run_pipeline(fake)
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertEqual(summary["errors"][0]["step"], "rag_capture")

    def test_rag_capture_must_produce_png(self) -> None:
        fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_normative_chunk(), ensure_ascii=False),
            capture_output=False,
        )
        code, summary = self.run_pipeline(fake)
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertIn("rag_chunks.png", summary["errors"][0]["message"])

    def test_rag_capture_rejects_stale_png(self) -> None:
        self.case.mkdir(parents=True)
        stale = self.case / "rag_chunks.png"
        stale.write_bytes(b"stale-png")
        fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_normative_chunk(), ensure_ascii=False),
            capture_output=False,
        )
        code, summary = self.run_pipeline(fake)
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")
        self.assertIn("nuevo", summary["errors"][0]["message"])

    def test_rag_capture_can_be_explicitly_skipped(self) -> None:
        fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_normative_chunk(), ensure_ascii=False)
        )
        code, summary = self.run_pipeline(fake, "--no-rag-capture")
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["pasos"]["rag_capture"]["status"], "skipped")
        self.assertFalse(any("capturar_rag.py" in " ".join(c) for c in fake.calls))

    def test_rag_capture_success_requires_png(self) -> None:
        fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_normative_chunk(), ensure_ascii=False)
        )
        code, summary = self.run_pipeline(fake)
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "ok")
        self.assertEqual(summary["pasos"]["rag_capture"]["status"], "ok")


def audit_with_yellow_article() -> dict:
    payload = audit_with_normative_chunk()
    payload["retrieved_sources"][0]["article"] = "1"
    payload["retrieved_sources"][0]["vvca"]["semaforo"] = "🟡"
    return payload


class _StderrCapturado(io.StringIO):
    """stderr capturado que admite el ``reconfigure`` que hace ``vvca_full.main``."""

    def reconfigure(self, **_opciones) -> None:
        return None


class TelegramOptInTests(unittest.TestCase):
    """El envío a Telegram es opt-in (docs/POLITICA_DATOS.md, principio 4)."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.draft = self.root / "borrador.md"
        self.draft.write_text("Caso enteramente sintético.", encoding="utf-8")
        self.case = self.root / "caso"
        self.fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_yellow_article(), ensure_ascii=False)
        )

    def run_with_popups(self, *extra: str) -> tuple[int, dict, list[str]]:
        with (
            patch("vvca_full.subprocess.run", side_effect=self.fake),
            patch("vvca_full.shutil.which", return_value="npx.cmd"),
            patch("itosturre.memoria.puente.registrar_auditoria", return_value=0),
        ):
            code = vvca_full.main(
                ["--caso", str(self.case), "--borrador", str(self.draft),
                 "--no-rag-capture", *extra]
            )
        summary = json.loads((self.case / "vvca_full.json").read_text(encoding="utf-8"))
        popup_calls = [c for c in self.fake.calls if "popup" in c]
        self.assertEqual(len(popup_calls), 1)
        return code, summary, popup_calls[0]

    def test_popups_do_not_request_telegram_by_default(self) -> None:
        code, summary, popup = self.run_with_popups()
        self.assertEqual(code, 0)
        self.assertNotIn("--telegram", popup)
        self.assertEqual(
            summary["pasos"]["rag_popup_articulos"]["telegram"], "no_solicitado"
        )

    def test_telegram_requires_explicit_opt_in(self) -> None:
        code, summary, popup = self.run_with_popups("--telegram")
        self.assertEqual(code, 0)
        self.assertIn("--telegram", popup)
        self.assertEqual(
            summary["pasos"]["rag_popup_articulos"]["telegram"], "solicitado"
        )

    def test_legacy_no_telegram_flag_is_accepted_and_sends_nothing(self) -> None:
        _code, _summary, popup = self.run_with_popups("--no-telegram")
        self.assertNotIn("--telegram", popup)

    def test_failed_requested_delivery_is_partial_not_failure(self) -> None:
        self.fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_yellow_article(), ensure_ascii=False),
            capture_returncode=3,
        )
        code, summary, _popup = self.run_with_popups("--telegram")
        self.assertEqual(code, 0)
        self.assertEqual(summary["status"], "partial")
        paso = summary["pasos"]["rag_popup_articulos"]
        self.assertEqual(paso["status"], "partial")
        self.assertEqual(paso["telegram"], "fallido")

    def test_popup_failure_without_telegram_still_fails_closed(self) -> None:
        self.fake = FakeSubprocesses(
            audit_stdout=json.dumps(audit_with_yellow_article(), ensure_ascii=False),
            capture_returncode=3,
        )
        code, summary, _popup = self.run_with_popups()
        self.assertEqual(code, 1)
        self.assertEqual(summary["status"], "failed")

    def test_ley_por_confirmar_llega_al_popup(self) -> None:
        # R4b ronda 3: la ley inferida de otro párrafo viaja al pop-up con su motivo.
        payload = audit_with_yellow_article()
        payload["retrieved_sources"][0]["expected_source"] = "LEY SINTETICA.pdf"
        payload["retrieved_sources"][0]["law_requires_confirmation"] = True
        self.fake = FakeSubprocesses(audit_stdout=json.dumps(payload, ensure_ascii=False))
        code, summary, _popup = self.run_with_popups()
        self.assertEqual(code, 0)
        (item,) = json.loads((self.case / "articulos_popup.json").read_text(encoding="utf-8"))
        self.assertTrue(item["ley_identificada"])
        self.assertTrue(item["ley_por_confirmar"])
        self.assertEqual(item["motivo_ley"], vvca_full.MOTIVO_CONFIRMAR)
        self.assertEqual(summary["pasos"]["rag_popup_articulos"]["ley_por_confirmar"], 1)

    def test_cobertura_pendiente_es_visible_sin_captura_falsa(self) -> None:
        payload = audit_with_yellow_article()
        payload["traceability"]["records"] = [{
            "claim": {"reference": "Arts. 14-40", "type": "normativa"},
            "retrieval": {"method": "cobertura_extraccion"},
            "verification": {"status": "not_verifiable",
                             "reason": "Cobertura incompleta: rango de 27 artículos"},
        }]
        self.fake = FakeSubprocesses(audit_stdout=json.dumps(payload, ensure_ascii=False))
        with patch("sys.stderr", new_callable=_StderrCapturado) as stderr:
            code, summary, popup = self.run_with_popups()
        self.assertEqual(code, 0)
        self.assertEqual(summary["cobertura_pendiente"], [{
            "referencia": "Arts. 14-40",
            "motivo": "Cobertura incompleta: rango de 27 artículos",
        }])
        self.assertTrue(any(w["step"] == "cobertura" for w in summary["warnings"]))
        self.assertIn("Cobertura pendiente", stderr.getvalue())
        self.assertEqual(popup[popup.index("--cobertura-pendiente") + 1], "1")
        # Ninguna captura nueva por lo no auditado: el pop-up sigue siendo el del artículo.
        (item,) = json.loads((self.case / "articulos_popup.json").read_text(encoding="utf-8"))
        self.assertEqual(item["reference"], "Art. 1 LEY SINTÉTICA")
        self.assertEqual(summary["pasos"]["rag_popup_articulos"]["cobertura_pendiente"], 1)

    def test_conflicting_telegram_flags_are_rejected(self) -> None:
        with patch("sys.stderr"), self.assertRaises(SystemExit) as raised:
            vvca_full.main(
                ["--caso", str(self.case), "--borrador", str(self.draft),
                 "--telegram", "--no-telegram"]
            )
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(self.fake.calls, [])


if __name__ == "__main__":
    unittest.main()
