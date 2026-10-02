"""Pruebas del envío opt-in a Telegram y de la redacción del token, sin red.

``capturar_rag`` importa playwright, PyMuPDF y requests dentro de las funciones que los
usan, de modo que estas pruebas corren en CI sin esas dependencias. La captura y el
envío se sustituyen en el borde del sistema.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

import capturar_rag

TOKEN_FALSO = "123456789:AAFAKE-token_sintetico-sin-valor-real-000000"
ITEMS = [{"reference": "Art. 1 LEY SINTÉTICA", "article": "1", "semaforo": "🟡"}]


class TelegramOptInTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.items = self.root / "articulos_popup.json"
        self.items.write_text(json.dumps(ITEMS, ensure_ascii=False), encoding="utf-8")

    def run_popup(self, *extra: str):
        resultados = [{"path": str(self.root / "art_01.png"), "caption": "🟡 Art. 1"}]
        with (
            patch("capturar_rag.capturar_articulos", return_value=resultados),
            patch("capturar_rag.enviar_lote_telegram",
                  return_value={"enviado": True}) as envio,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            capturar_rag.main(
                ["--modo", "popup", "--items", str(self.items),
                 "--out", str(self.root), *extra]
            )
        return envio

    def test_popup_mode_does_not_send_by_default(self) -> None:
        self.assertFalse(self.run_popup().called)

    def test_legacy_no_telegram_flag_does_not_send(self) -> None:
        self.assertFalse(self.run_popup("--no-telegram").called)

    def test_explicit_opt_in_sends_once(self) -> None:
        self.assertEqual(self.run_popup("--telegram").call_count, 1)

    def test_cobertura_pendiente_se_avisa_en_el_resumen_del_envio(self) -> None:
        # R4b ronda 3: lo no auditado no tiene captura, pero el envío lo dice.
        envio = self.run_popup("--telegram", "--cobertura-pendiente", "2")
        (_resultados, resumen), _ = envio.call_args
        self.assertIn("2 referencia(s) con cobertura pendiente", resumen)
        sin_cobertura = self.run_popup("--telegram")
        (_resultados, resumen), _ = sin_cobertura.call_args
        self.assertNotIn("cobertura pendiente", resumen)

    def test_requested_delivery_failure_exits_with_code_3(self) -> None:
        resultados = [{"path": str(self.root / "art_01.png"), "caption": "🟡 Art. 1"}]
        with (
            patch("capturar_rag.capturar_articulos", return_value=resultados),
            patch("capturar_rag.enviar_lote_telegram",
                  return_value={"enviado": False, "razon": "credenciales no configuradas"}),
            patch("sys.stdout", new_callable=io.StringIO),
            patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as raised,
        ):
            capturar_rag.main(
                ["--modo", "popup", "--items", str(self.items), "--out",
                 str(self.root), "--telegram"]
            )
        self.assertEqual(raised.exception.code, 3)

    def test_conflicting_flags_are_rejected_before_capturing(self) -> None:
        with (
            patch("capturar_rag.capturar_articulos") as captura,
            patch("sys.stderr", new_callable=io.StringIO),
            self.assertRaises(SystemExit) as raised,
        ):
            capturar_rag.main(
                ["--modo", "popup", "--items", str(self.items), "--out",
                 str(self.root), "--telegram", "--no-telegram"]
            )
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(captura.called)


class TokenRedactionTests(unittest.TestCase):
    def failing_requests(self) -> types.ModuleType:
        """Doble de ``requests`` cuyo error repite la URL, como hace urllib3."""
        fake = types.ModuleType("requests")

        def post(url, **_kwargs):
            raise ConnectionError(
                f"HTTPSConnectionPool(host='api.telegram.org', port=443): "
                f"Max retries exceeded with url: {url.split('.org', 1)[1]}"
            )

        fake.post = post
        return fake

    def test_send_text_failure_never_prints_token(self) -> None:
        stderr = io.StringIO()
        with patch.dict(sys.modules, {"requests": self.failing_requests()}):
            with redirect_stderr(stderr):
                enviado = capturar_rag.enviar_texto(TOKEN_FALSO, "1", "hola")
        self.assertFalse(enviado)
        self.assertNotIn(TOKEN_FALSO, stderr.getvalue())
        self.assertIn("[REDACTADO]", stderr.getvalue())
        self.assertIn("Max retries exceeded", stderr.getvalue())

    def test_send_photo_failure_never_prints_token(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        foto = Path(temp.name) / "art.png"
        foto.write_bytes(b"synthetic-png")
        stderr = io.StringIO()
        with patch.dict(sys.modules, {"requests": self.failing_requests()}):
            with redirect_stderr(stderr):
                enviado = capturar_rag.enviar_foto(TOKEN_FALSO, "1", str(foto))
        self.assertFalse(enviado)
        self.assertNotIn(TOKEN_FALSO, stderr.getvalue())

    def test_redaction_covers_tokens_not_passed_explicitly(self) -> None:
        texto = f"error en /bot{TOKEN_FALSO}/sendPhoto"
        self.assertNotIn(TOKEN_FALSO, capturar_rag._redactar(texto))

    def test_photo_path_containing_token_is_redacted(self) -> None:
        stderr = io.StringIO()
        ruta = str(Path(tempfile.gettempdir()) / f"inexistente-{TOKEN_FALSO}.png")
        with redirect_stderr(stderr):
            enviado = capturar_rag.enviar_foto(TOKEN_FALSO, "1", ruta)
        self.assertFalse(enviado)
        self.assertNotIn(TOKEN_FALSO, stderr.getvalue())


class BatchDeliveryTests(unittest.TestCase):
    """El lote solo reporta éxito si llegaron el resumen y todas las fotos."""

    def test_partial_photo_failure_is_not_success(self) -> None:
        resultados = [{"path": "a.png", "caption": "a"}, {"path": "b.png", "caption": "b"}]
        with (
            patch("capturar_rag._load_telegram_env", return_value=(TOKEN_FALSO, "1")),
            patch.dict(sys.modules, {"requests": types.ModuleType("requests")}),
            patch("capturar_rag.enviar_texto", return_value=True),
            patch("capturar_rag.enviar_foto", side_effect=[True, False]),
        ):
            envio = capturar_rag.enviar_lote_telegram(resultados, "resumen")
        self.assertFalse(envio["enviado"])
        self.assertEqual(envio["fotos_enviadas"], 1)

    def test_missing_requests_is_reported_not_hidden(self) -> None:
        with (
            patch("capturar_rag._load_telegram_env", return_value=(TOKEN_FALSO, "1")),
            patch.dict(sys.modules, {"requests": None}),
        ):
            envio = capturar_rag.enviar_lote_telegram([], "resumen")
        self.assertFalse(envio["enviado"])
        self.assertIn("requests", envio["razon"])


class MissingDependencyTests(unittest.TestCase):
    def test_missing_pymupdf_propagates_instead_of_hiding_the_page(self) -> None:
        with patch.dict(sys.modules, {"fitz": None}):
            with self.assertRaises(ImportError):
                capturar_rag.render_pdf_page_b64(Path("cualquiera.pdf"), "1")


class ArticleHeaderTests(unittest.TestCase):
    """El pop-up solo muestra la página del PDF como prueba si el texto trae el artículo
    citado con su sufijo (R4b): el índice agrupa "4o.-A" o "247 Bis" bajo el número base."""

    def test_numero_simple_conserva_la_tolerancia_de_siempre(self) -> None:
        texto = "Artículo 1o. Texto sintético; véase el artículo 16 y el artículo 160."
        self.assertTrue(capturar_rag._contains_article_header(texto, "1"))
        self.assertTrue(capturar_rag._contains_article_header(texto, "16"))
        self.assertFalse(capturar_rag._contains_article_header(texto, "8"))
        self.assertTrue(capturar_rag._contains_article_header(texto, ""))
        self.assertTrue(capturar_rag._contains_article_header(texto, "Único"))

    def test_sufijo_pedido_y_no_pedido(self) -> None:
        base = "Artículo 247.- Texto sintético del artículo base."
        variante = "Artículo 4o.-A.- Texto sintético del artículo con letra."
        self.assertFalse(capturar_rag._contains_article_header(base, "247 Ter"))
        self.assertTrue(capturar_rag._contains_article_header(
            "Artículo 247 Ter.- Texto sintético.", "247 Ter"))
        self.assertFalse(capturar_rag._contains_article_header(variante, "4o"))
        self.assertTrue(capturar_rag._contains_article_header(variante, "4o.-A"))
        # Sufijo en minúscula (ronda 2) sin confundir el cuerpo del artículo.
        self.assertFalse(capturar_rag._contains_article_header("Artículo 4o.-a.- Texto.", "4o"))
        self.assertTrue(capturar_rag._contains_article_header("Artículo 4o.- a) Texto.", "4o"))

    def test_popup_de_sufijo_no_confirmado_no_muestra_la_pagina(self) -> None:
        html = capturar_rag.build_popup_html({
            "reference": "artículo 247 Ter",
            "article": "247 Ter",
            "semaforo": "🟡",
            "source_file": "CODIGO SINTETICO.pdf",
            "expected_source": "CODIGO SINTETICO.pdf",
            "coincide_fuente": True,
            "ley_identificada": True,
            "retrieved_text_full": "Artículo 247.- Texto sintético del artículo base.",
        })
        self.assertIn("NÚMERO DE ARTÍCULO NO CONFIRMADO", html)
        self.assertNotIn("page-img", html.split("</style>")[1])

    def test_popup_de_ley_por_confirmar_lleva_advertencia_visible(self) -> None:
        item = {
            "reference": "artículo 42",
            "article": "42",
            "semaforo": "🟡",
            "source_file": "CODIGO SINTETICO.pdf",
            "expected_source": "CODIGO SINTETICO.pdf",
            "coincide_fuente": True,
            "ley_identificada": True,
            "retrieved_text_full": "Artículo 42.- Texto sintético.",
        }
        normal = capturar_rag.build_popup_html(item)
        self.assertNotIn("LEY POR CONFIRMAR", normal)
        por_confirmar = capturar_rag.build_popup_html(dict(
            item, ley_por_confirmar=True,
            motivo_ley="ley inferida de otro párrafo: confirmar el ordenamiento",
        ))
        cuerpo = por_confirmar.split("</style>")[1]
        self.assertIn("⚠️ LEY POR CONFIRMAR — ley inferida de otro párrafo", cuerpo)
        self.assertIn("no que el escrito cite ese ordenamiento", cuerpo)
        self.assertIn("UBICACIÓN", cuerpo)   # la página se sigue mostrando (con advertencia)


if __name__ == "__main__":
    unittest.main()
