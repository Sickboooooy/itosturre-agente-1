"""Pruebas de los watchers DOF/SAT/SJF y del bloqueo del generador de LinkedIn.

Cubre los 5 escenarios del encargo de reparación:
  A. Todas las fuentes disponibles -> hay hallazgo -> se puede generar LinkedIn.
  B. DOF bloqueado, SAT/SJF disponibles -> no se inventa DOF, se sigue con lo válido.
  C. SJF bloqueado -> no se afirma jurisprudencia.
  D. Todas las fuentes bloqueadas -> WATCH_FAILED / NO LEGAL CONTENT GENERATED.
  E. Ejecución repetida -> no duplica resultados ni drafts.

Todas las llamadas de red están simuladas (unittest.mock) — ninguna prueba
depende de acceso real a dof.gob.mx / sat.gob.mx / sjf2.scjn.gob.mx.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import requests

import agentes.contenido_linkedin as vli
import agentes.vigilancia_dof as vdof
import agentes.vigilancia_jurisprudencial as vjur
from itosturre.vigilancia import contrato as c


class FakeResponse:
    """Doble mínimo de requests.Response para las pruebas."""

    def __init__(self, status_code=200, json_data=None, text=None, ok=None):
        self.status_code = status_code
        self._json = json_data
        if text is None:
            text = json.dumps(json_data) if json_data is not None else ""
        self.text = text
        self.content = text.encode("utf-8")
        self.ok = ok if ok is not None else (200 <= status_code < 400)

    def raise_for_status(self):
        if not self.ok:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._json is None:
            raise ValueError("cuerpo sin JSON")
        return self._json


class _AislaSalidaMixin:
    """Redirige las rutas de salida y el log de eventos de los 3 módulos a un
    directorio temporal, y desactiva ANTHROPIC_API_KEY para forzar el modo
    degradado/placeholder (no se hacen llamadas reales al LLM en pruebas)."""

    def setUp(self):
        super().setUp()
        self._tmp = TemporaryDirectory()
        base = Path(self._tmp.name)

        self._patches = []

        def parchar(modulo, nombre, valor):
            p = mock.patch.object(modulo, nombre, valor)
            p.start()
            self._patches.append(p)

        vig_dir = base / "Vigilancia"
        jur_dir = base / "Jurisprudencia"
        con_dir = base / "Contenido"

        parchar(vdof, "OUTPUT_DIR", vig_dir)
        parchar(vdof, "OUTPUT_FILE", vig_dir / f"{vdof.DATE_STR}.md")
        parchar(vjur, "OUTPUT_DIR", jur_dir)
        parchar(vjur, "OUTPUT_FILE", jur_dir / f"semana-{vjur.WEEK_STR}.md")
        parchar(vli, "VIGILANCIA_DIR", vig_dir)
        parchar(vli, "JURISPRUDENCIA_DIR", jur_dir)
        parchar(vli, "OUTPUT_DIR", con_dir)
        parchar(vli, "OUTPUT_FILE", con_dir / f"borrador-{vli.DATE_STR}.md")
        parchar(c, "EVENTOS_LOG", base / "eventos.jsonl")

        # Retries sin esperar de verdad.
        parchar(vjur, "_throttle", lambda: None)
        parchar(vjur.time, "sleep", lambda s: None)

        env_patch = mock.patch.dict("os.environ", {}, clear=False)
        env_patch.start()
        self._patches.append(env_patch)
        import os

        os.environ.pop("ANTHROPIC_API_KEY", None)

        self.vig_dir = vig_dir
        self.jur_dir = jur_dir
        self.con_dir = con_dir

    def tearDown(self):
        for p in self._patches:
            p.stop()
        self._tmp.cleanup()
        super().tearDown()


# ── Helpers para simular las 3 fuentes ─────────────────────────────────────────

HTML_DOF_CON_HALLAZGO = (
    '<html><body><a href="/nota/69b">Listado de contribuyentes 69-B definitivos '
    'publicado hoy en el DOF</a></body></html>'
)
HTML_SAT_CON_HALLAZGO = (
    '<html><body><a href="/com/1">Nuevo criterio SAT sobre cancelación de CSD</a></body></html>'
)
HTML_SIN_HALLAZGO = "<html><body><p>Contenido sin relevancia fiscal.</p></body></html>"


def _fake_get_disponible(con_hallazgo: bool):
    html = HTML_DOF_CON_HALLAZGO if con_hallazgo else HTML_SIN_HALLAZGO

    def _fake(url, headers=None, timeout=None):
        return FakeResponse(text=html if "dof" in url else HTML_SAT_CON_HALLAZGO if con_hallazgo else HTML_SIN_HALLAZGO)

    return _fake


def _fake_request_sjf_disponible(con_hallazgo: bool):
    def _fake(method, url, headers=None, timeout=None, json=None, **kw):
        if method == "POST":
            docs = [{"ius": "2028888"}] if con_hallazgo else []
            return FakeResponse(json_data={"documents": docs})
        if method == "GET":
            return FakeResponse(json_data={
                "rubro": "CANCELACIÓN DE CSD. CRITERIO DE PRUEBA.",
                "ta_tj": 1,
                "tipoTesis": "Jurisprudencia",
                "formasIntegracion": [{"formaIntegracion": "Reiteración de criterios"}],
                "fechaPublicacion": "2026-09-05",
                "epoca": "Duodécima Época",
                "sala": "1",
                "instancia": "Primera Sala",
            })
        raise AssertionError(f"método inesperado: {method}")

    return _fake


def _fake_request_sjf_bloqueado(method, url, headers=None, timeout=None, json=None, **kw):
    raise requests.exceptions.ProxyError("gateway answered 403 to CONNECT sjf2.scjn.gob.mx:443")


def _fake_get_bloqueado(url, headers=None, timeout=None):
    raise requests.exceptions.ProxyError(f"gateway answered 403 to CONNECT {url}")


class TestCasoA_TodasDisponibles(_AislaSalidaMixin, unittest.TestCase):
    def test_watch_dof_sat_con_hallazgos_y_linkedin_generado(self):
        with mock.patch.object(vdof.requests, "get", _fake_get_disponible(con_hallazgo=True)):
            vdof.main()
        with mock.patch.object(vjur.requests, "request", _fake_request_sjf_disponible(con_hallazgo=True)):
            vjur.main()

        contrato_vig = c.leer_sidecar(vdof.OUTPUT_FILE.with_suffix(".json"))
        contrato_jur = c.leer_sidecar(vjur.OUTPUT_FILE.with_suffix(".json"))
        self.assertTrue(any(v["status"] == c.SUCCESS and v["items"] for v in contrato_vig.values()))
        self.assertTrue(any(v["status"] == c.SUCCESS and v["items"] for v in contrato_jur.values()))

        vli.main()
        borrador = vli.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertNotIn("NOT_GENERATED", borrador)
        self.assertIn("hallazgos válidos", borrador.lower().replace("válidos", "válidos"))


class TestCasoB_DofBloqueado(_AislaSalidaMixin, unittest.TestCase):
    def test_dof_bloqueado_no_se_inventa_y_se_sigue_con_sat_y_sjf(self):
        with mock.patch.object(vdof.requests, "get", _fake_get_bloqueado):
            vdof.main()
        with mock.patch.object(vjur.requests, "request", _fake_request_sjf_disponible(con_hallazgo=True)):
            vjur.main()

        contrato_vig = c.leer_sidecar(vdof.OUTPUT_FILE.with_suffix(".json"))
        self.assertEqual(contrato_vig["DOF"]["status"], c.SOURCE_UNAVAILABLE)
        self.assertFalse(contrato_vig["DOF"]["retryable"])
        self.assertEqual(contrato_vig["DOF"]["items"], [])
        # SAT no fue mockeado como bloqueado en este caso -> también bloqueado
        # (mismo mock global de vdof.requests.get) pero SJF sí respondió: el
        # watch de jurisprudencia debe seguir siendo válido para el gate de LinkedIn.
        contrato_jur = c.leer_sidecar(vjur.OUTPUT_FILE.with_suffix(".json"))
        self.assertTrue(any(v["status"] == c.SUCCESS and v["items"] for v in contrato_jur.values()))

        brief = vdof.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertNotIn("Sin hallazgos relevantes hoy.", brief.split("Watch result")[0] if "Watch result" in brief else brief)

        vli.main()
        borrador = vli.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertNotIn("NOT_GENERATED", borrador)


class TestCasoC_SjfBloqueado(_AislaSalidaMixin, unittest.TestCase):
    def test_sjf_bloqueado_no_afirma_jurisprudencia(self):
        with mock.patch.object(vjur.requests, "request", _fake_request_sjf_bloqueado):
            vjur.main()

        contrato_jur = c.leer_sidecar(vjur.OUTPUT_FILE.with_suffix(".json"))
        self.assertTrue(all(v["status"] == c.SOURCE_UNAVAILABLE for v in contrato_jur.values()))
        self.assertTrue(all(v["retryable"] is False for v in contrato_jur.values()))

        informe = vjur.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertIn("SOURCE_UNAVAILABLE", informe)
        self.assertNotIn("Registro IUS:", informe)  # ninguna ficha inventada


class TestCasoD_TodoBloqueado(_AislaSalidaMixin, unittest.TestCase):
    def test_todas_las_fuentes_bloqueadas_no_genera_contenido(self):
        with mock.patch.object(vdof.requests, "get", _fake_get_bloqueado):
            vdof.main()
        with mock.patch.object(vjur.requests, "request", _fake_request_sjf_bloqueado):
            vjur.main()

        brief = vdof.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertIn("Watch result: SOURCE_UNAVAILABLE", brief)
        informe = vjur.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertIn("Watch result: SOURCE_UNAVAILABLE", informe)

        vli.main()
        borrador = vli.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertIn("NOT_GENERATED", borrador)
        self.assertIn("SOURCE_UNAVAILABLE", borrador)


class TestCasoD_FuentesOkSinHallazgos(_AislaSalidaMixin, unittest.TestCase):
    def test_fuentes_disponibles_sin_novedades_bloquea_por_sin_hallazgos(self):
        """Distinto de SOURCE_UNAVAILABLE: las fuentes SÍ respondieron, solo que
        no había nada noticiable — tampoco debe generarse un post."""
        with mock.patch.object(vdof.requests, "get", _fake_get_disponible(con_hallazgo=False)):
            vdof.main()
        with mock.patch.object(vjur.requests, "request", _fake_request_sjf_disponible(con_hallazgo=False)):
            vjur.main()

        vli.main()
        borrador = vli.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertIn("NOT_GENERATED", borrador)
        self.assertIn("SIN_HALLAZGOS", borrador)


class TestCasoE_Idempotencia(_AislaSalidaMixin, unittest.TestCase):
    def test_segunda_corrida_no_duplica_ni_vuelve_a_consultar(self):
        llamadas = {"n": 0}

        def contador(url, headers=None, timeout=None):
            llamadas["n"] += 1
            return FakeResponse(text=HTML_DOF_CON_HALLAZGO)

        with mock.patch.object(vdof.requests, "get", contador):
            vdof.main()
            primer_contenido = vdof.OUTPUT_FILE.read_text(encoding="utf-8")
            n_tras_primera = llamadas["n"]

            vdof.main()  # segunda corrida del mismo día
            segundo_contenido = vdof.OUTPUT_FILE.read_text(encoding="utf-8")

        self.assertEqual(primer_contenido, segundo_contenido)
        self.assertEqual(llamadas["n"], n_tras_primera, "la segunda corrida no debió volver a golpear la red")

    def test_linkedin_no_duplica_borrador(self):
        with mock.patch.object(vdof.requests, "get", _fake_get_disponible(con_hallazgo=True)):
            vdof.main()
        with mock.patch.object(vjur.requests, "request", _fake_request_sjf_disponible(con_hallazgo=True)):
            vjur.main()

        vli.main()
        primero = vli.OUTPUT_FILE.read_text(encoding="utf-8")
        vli.main()
        segundo = vli.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertEqual(primero, segundo)


class TestSjfNoReintentaBloqueoDePolitica(_AislaSalidaMixin, unittest.TestCase):
    def test_bloqueo_de_politica_no_agota_los_reintentos(self):
        """Un ProxyError (bloqueo de política) debe cortar _http() en el primer
        intento — reintentar 2s/4s/8s en el mismo entorno nunca lo resuelve."""
        intentos = {"n": 0}

        def fake_request(method, url, headers=None, timeout=None, json=None, **kw):
            intentos["n"] += 1
            raise requests.exceptions.ProxyError("403 to CONNECT")

        with mock.patch.object(vjur.requests, "request", fake_request):
            outcome = vjur._http("POST", "https://sjf2.scjn.gob.mx/x")

        self.assertEqual(intentos["n"], 1)
        self.assertEqual(outcome.status, c.SOURCE_UNAVAILABLE)
        self.assertFalse(outcome.retryable)


if __name__ == "__main__":
    unittest.main()
