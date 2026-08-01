from __future__ import annotations

import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from itosturre.leads import OUTPUT_FIELDS, classify_fiscal_lead, prepare_leads
from itosturre.leads.normalize import normalize_domain, normalize_phone
from itosturre.leads.pipeline import write_csv


REPO = Path(__file__).resolve().parent.parent


class LeadNormalizationTests(unittest.TestCase):
    def test_mexican_phone_normalization_is_conservative(self) -> None:
        self.assertEqual(normalize_phone("33 1136 7858"), "+523311367858")
        self.assertEqual(normalize_phone("+52 1 33 1136 7858"), "+523311367858")
        self.assertEqual(normalize_phone("12345"), "")

    def test_domain_normalization(self) -> None:
        self.assertEqual(normalize_domain("https://www.Example.mx/ruta"), "example.mx")


class LeadQualificationTests(unittest.TestCase):
    def test_fiscal_specialist_is_prioritized(self) -> None:
        result = classify_fiscal_lead(name="Firma de Defensa Fiscal y 69-B")
        self.assertEqual(result.segment, "fiscal_prioritario")
        self.assertGreaterEqual(result.score, 55)
        self.assertIn("defensa fiscal", result.positive_evidence)

    def test_explicit_non_fiscal_statement_is_excluded(self) -> None:
        result = classify_fiscal_lead(
            name="Corporativo Osorio",
            services_text="No llevo fiscal; mi práctica es derecho laboral",
        )
        self.assertEqual(result.segment, "no_objetivo")
        self.assertEqual(result.score, 0)


class LeadPipelineTests(unittest.TestCase):
    def test_dnc_overrides_score_channel_and_consent(self) -> None:
        rows = [{
            "name": "Defensa Fiscal Centro",
            "phone": "33 1111 2222",
            "whatsapp_available": "sí",
            "whatsapp_opt_in": "sí",
        }]
        suppression = [{
            "phone": "+52 33 1111 2222",
            "reason": "Solicitó no ser molestado",
            "recorded_at": "2026-07-15",
        }]
        records, summary = prepare_leads(rows, suppression_rows=suppression)
        record = records[0]
        self.assertTrue(record.do_not_contact)
        self.assertFalse(record.contact_eligible)
        self.assertEqual(record.contact_status, "do_not_contact")
        self.assertEqual(summary.do_not_contact, 1)

    def test_no_opt_in_means_permission_required(self) -> None:
        records, _ = prepare_leads([{
            "name": "Abogados Fiscales Occidente",
            "phone": "3312345678",
            "public_business_number": "sí",
            "whatsapp_available": "sí",
        }])
        self.assertEqual(records[0].contact_status, "permission_required")
        self.assertFalse(records[0].contact_eligible)
        self.assertTrue(records[0].manual_contact_candidate)
        self.assertEqual(records[0].wa_policy_status, "opt_in_missing")
        _, summary = prepare_leads([{
            "name": "Abogados Fiscales Occidente",
            "phone": "3312345678",
            "public_business_number": "sí",
            "whatsapp_available": "sí",
        }])
        self.assertEqual(summary.manual_contact_candidates, 1)

    def test_unqualified_record_cannot_become_eligible(self) -> None:
        records, _ = prepare_leads([{
            "name": "Corporativo sin especialidad",
            "whatsapp_available": "sí",
            "whatsapp_opt_in": "sí",
        }])
        self.assertEqual(records[0].contact_status, "qualification_required")
        self.assertFalse(records[0].contact_eligible)
        self.assertFalse(records[0].manual_contact_candidate)

    def test_blank_rows_are_reported_not_merged(self) -> None:
        records, summary = prepare_leads([{}, {"name": "Abogado fiscal"}])
        self.assertEqual(len(records), 1)
        self.assertEqual(summary.invalid_rows, 1)
        self.assertEqual(summary.duplicates_merged, 0)

    def test_duplicates_merge_and_csv_schema_never_changes(self) -> None:
        rows = [
            {"name": "Fiscal MX", "phone": "3312345678", "category": "Abogado fiscal"},
            {"name": "Fiscal MX", "phone": "+52 33 1234 5678", "website": "fiscal.mx"},
        ]
        records, summary = prepare_leads(rows, captured_at="2026-08-01T00:00:00+00:00")
        self.assertEqual(summary.duplicates_merged, 1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].website_domain, "fiscal.mx")

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "normalized.csv"
            write_csv(records, output)
            with output.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle)
                self.assertEqual(reader.fieldnames, OUTPUT_FIELDS)
                self.assertEqual(len(list(reader)), 1)


class LeadCliTests(unittest.TestCase):
    def test_cli_is_runnable_from_repository_root(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/prepare_leads.py", "--help"],
            cwd=REPO,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Normaliza, deduplica", result.stdout)


if __name__ == "__main__":
    unittest.main()
