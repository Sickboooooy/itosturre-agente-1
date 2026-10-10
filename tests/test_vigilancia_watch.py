"""Pruebas de los watchers DOF/SAT/SJF y del generador de contenido.

Escenarios (red simulada con unittest.mock: ninguna prueba toca dof.gob.mx,
sat.gob.mx, sjf2.scjn.gob.mx ni la API de Anthropic):
  A.  Todas las fuentes disponibles -> brief, informe y borrador.
  B.  DOF caído -> sin brief (salida 2, se puede reintentar); el SJF sigue y
      el borrador se apoya solo en él.
  B2. SAT caído -> brief PARCIAL que lo dice; nunca "sin criterios SAT".
  C.  SJF caído -> sin informe (salida 2), una sola petición (corte por
      bloqueo de política), ninguna ficha inventada.
  C2. Un tema del SJF caído -> informe PARCIAL; ese tema no dice "sin criterios".
  D.  Todo caído -> ningún brief, informe ni borrador (salidas 2, 2 y 3).
  D2. Fuentes disponibles sin novedades -> sin borrador (SIN_HALLAZGOS).
  E.  Ejecución repetida -> no duplica, no vuelve a consultar, no pisa el estado.
  F.  Pozo envenenado: una corrida fallida no bloquea el reintento.
"""
from __future__ import annotations

import json
import os
import sys
import types
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import mock
from urllib.parse import urlparse

import requests

import agentes.contenido_linkedin as vli
import agentes.vigilancia_dof as vdof
import agentes.vigilancia_jurisprudencial as vjur
from itosturre.vigilancia import contrato as c
from itosturre.vigilancia import rutina as r


class FakeResponse:
    """Doble mínimo de requests.Response para las pruebas."""

    def __init__(self, status_code=200, json_data=None, text=None, ok=None, headers=None):
        self.status_code = status_code
        self.headers = headers or {}
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


# ── Dobles de red ──────────────────────────────────────────────────────────────

HTML_DOF_CON_HALLAZGO = (
    '<html><body><a href="/nota/69b">Listado de contribuyentes 69-B definitivos '
    'publicado hoy en el DOF</a></body></html>'
)
HTML_SAT_CON_HALLAZGO = (
    '<html><body><a href="/com/1">Nuevo criterio SAT sobre cancelación de CSD</a></body></html>'
)
HTML_SIN_HALLAZGO = "<html><body><p>Contenido sin relevancia fiscal.</p></body></html>"
HTML_INCAPSULA = (
    '<html style="height:100%"><head><META NAME="ROBOTS" CONTENT="NOINDEX, NOFOLLOW">'
    '<script type="text/javascript" src="/_Incapsula_Resource?SWJIYLWA=x"></script></head></html>'
)


class RedDofSat:
    """Doble de requests.get: cada fuente 'hallazgo', 'vacio' o 'bloqueado'.
    Cuenta las llamadas por fuente."""

    def __init__(self, dof="hallazgo", sat="hallazgo"):
        self.modo = {"DOF": dof, "SAT": sat}
        self.llamadas = {"DOF": 0, "SAT": 0}

    def __call__(self, url, headers=None, timeout=None):
        fuente = "DOF" if "dof.gob.mx" in url else "SAT"
        self.llamadas[fuente] += 1
        modo = self.modo[fuente]
        if modo == "bloqueado":
            raise requests.exceptions.ProxyError(f"gateway answered 403 to CONNECT {url}")
        if modo == "hallazgo":
            return FakeResponse(text=HTML_DOF_CON_HALLAZGO if fuente == "DOF" else HTML_SAT_CON_HALLAZGO)
        return FakeResponse(text=HTML_SIN_HALLAZGO)


FICHA_SJF = {
    "rubro": "CANCELACIÓN DE CSD. CRITERIO DE PRUEBA.",
    "claveTesis": "PR.A.C.CN. 1 A (12a.)",
    "ta_tj": 1,
    "tipoTesis": "Jurisprudencia",
    "formasIntegracion": [{"formaIntegracion": "Reiteración de criterios"}],
    "fechaPublicacion": "2026-09-05",
    "epoca": "Duodécima Época",
    "sala": "1",
    "instancia": "Primera Sala",
}


class RedSjf:
    """Doble de requests.request para el microservicio del SJF.

    busqueda: 'hallazgo' | 'vacia' | 'bloqueado'; detalle: 'ok' | '500' |
    'incapsula' (desafío anti-bots en HTML, como el observado el 10-oct-2026);
    temas_caidos: expresiones cuya búsqueda responde HTTP 500."""

    def __init__(self, busqueda="hallazgo", detalle="ok", temas_caidos=()):
        self.busqueda = busqueda
        self.detalle = detalle
        self.temas_caidos = set(temas_caidos)
        self.llamadas = 0

    def __call__(self, method, url, headers=None, timeout=None, json=None, **kw):
        self.llamadas += 1
        if self.busqueda == "bloqueado":
            raise requests.exceptions.ProxyError("gateway answered 403 to CONNECT sjf2.scjn.gob.mx:443")
        if method == "POST":
            if json["searchTerms"][0]["expression"] in self.temas_caidos:
                return FakeResponse(status_code=500, text="error interno")
            docs = [{"ius": "2028888"}] if self.busqueda == "hallazgo" else []
            return FakeResponse(json_data={"documents": docs})
        if method == "GET":
            if self.detalle == "500":
                return FakeResponse(status_code=500, text="error interno")
            if self.detalle == "incapsula":
                return FakeResponse(text=HTML_INCAPSULA, headers={"content-type": "text/html"})
            return FakeResponse(json_data=FICHA_SJF)
        raise AssertionError(f"método inesperado: {method}")


def _anthropic_falso(texto="TEXTO DEL MODELO"):
    """Módulo `anthropic` falso: registra cada llamada y devuelve un texto fijo."""
    llamadas: list[dict] = []

    class APIError(Exception):
        pass

    class _Mensajes:
        def create(self, **kw):
            llamadas.append(kw)
            return SimpleNamespace(content=[SimpleNamespace(text=texto)])

    class Anthropic:
        def __init__(self, api_key=None):
            self.messages = _Mensajes()

    modulo = types.ModuleType("anthropic")
    modulo.Anthropic = Anthropic
    modulo.APIError = APIError
    return modulo, llamadas


class _AislaSalidaMixin:
    """Redirige las salidas y el log de eventos de los 3 módulos a un directorio
    temporal y limpia las variables de entorno: sin ANTHROPIC_API_KEY los
    módulos corren sin LLM (ninguna llamada real en pruebas)."""

    def setUp(self):
        super().setUp()
        self._tmp = TemporaryDirectory()
        base = Path(self._tmp.name)
        self._patches = []

        def parchar(modulo, nombre, valor):
            p = mock.patch.object(modulo, nombre, valor)
            p.start()
            self._patches.append(p)

        self.vig_dir = base / "Vigilancia"
        self.jur_dir = base / "Jurisprudencia"
        self.con_dir = base / "Contenido"

        parchar(vdof, "OUTPUT_DIR", self.vig_dir)
        parchar(vdof, "OUTPUT_FILE", self.vig_dir / f"{vdof.DATE_STR}.md")
        parchar(vjur, "OUTPUT_DIR", self.jur_dir)
        parchar(vjur, "OUTPUT_FILE", self.jur_dir / f"semana-{vjur.WEEK_STR}.md")
        parchar(vli, "VIGILANCIA_DIR", self.vig_dir)
        parchar(vli, "JURISPRUDENCIA_DIR", self.jur_dir)
        parchar(vli, "OUTPUT_DIR", self.con_dir)
        parchar(vli, "OUTPUT_FILE", self.con_dir / f"borrador-{vli.DATE_STR}.md")
        parchar(c, "EVENTOS_LOG", base / "eventos.jsonl")

        # Reintentos sin esperar de verdad.
        parchar(vjur, "_throttle", lambda: None)
        parchar(vjur.time, "sleep", lambda s: None)

        env_patch = mock.patch.dict("os.environ", {}, clear=False)
        env_patch.start()
        self._patches.append(env_patch)
        for variable in ("ANTHROPIC_API_KEY", "ITOSTURRE_WHATSAPP", "ITOSTURRE_MODELO"):
            os.environ.pop(variable, None)

    def tearDown(self):
        for p in reversed(self._patches):
            p.stop()
        self._tmp.cleanup()
        super().tearDown()

    @staticmethod
    def _estado(ruta_salida: Path) -> dict:
        return json.loads(ruta_salida.with_name(f"{ruta_salida.stem}.estado.json").read_text(encoding="utf-8"))

    def _correr_dof(self, red) -> int:
        with mock.patch.object(vdof.requests, "get", red):
            return vdof.main()

    def _correr_sjf(self, red) -> int:
        with mock.patch.object(vjur.requests, "request", red):
            return vjur.main()


# ── Escenarios ─────────────────────────────────────────────────────────────────


class TestCasoA_TodasDisponibles(_AislaSalidaMixin, unittest.TestCase):
    def test_brief_informe_y_borrador(self):
        self.assertEqual(self._correr_dof(RedDofSat()), r.EXIT_OK)
        self.assertEqual(self._correr_sjf(RedSjf()), r.EXIT_OK)

        contrato_vig = c.leer_sidecar(vdof.OUTPUT_FILE.with_suffix(".json"))
        self.assertTrue(all(v["status"] == c.SUCCESS for v in contrato_vig.values()))
        self.assertTrue(contrato_vig["DOF"]["items"] and contrato_vig["SAT"]["items"])
        estado_vig = self._estado(vdof.OUTPUT_FILE)
        self.assertEqual((estado_vig["estado"], estado_vig["codigo_salida"]), (r.OK, r.EXIT_OK))

        contrato_jur = c.leer_sidecar(vjur.OUTPUT_FILE.with_suffix(".json"))
        self.assertTrue(all(v["status"] == c.SUCCESS and v["items"] for v in contrato_jur.values()))
        self.assertEqual(self._estado(vjur.OUTPUT_FILE)["estado"], r.OK)

        self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertIn("hallazgos válidos", vli.OUTPUT_FILE.read_text(encoding="utf-8"))
        self.assertEqual(self._estado(vli.OUTPUT_FILE)["estado"], r.OK)


class TestCasoB_DofCaido(_AislaSalidaMixin, unittest.TestCase):
    def test_dof_caido_no_escribe_brief_y_el_sjf_sostiene_el_borrador(self):
        red = RedDofSat(dof="bloqueado")
        self.assertEqual(self._correr_dof(red), r.EXIT_FUENTE_INACCESIBLE)

        self.assertFalse(vdof.OUTPUT_FILE.exists())
        self.assertFalse(vdof.OUTPUT_FILE.with_suffix(".json").exists())
        self.assertEqual(red.llamadas["SAT"], 0, "sin DOF no hay brief: el SAT ni se consulta")
        estado = self._estado(vdof.OUTPUT_FILE)
        self.assertEqual(estado["estado"], r.FUENTE_INACCESIBLE)
        self.assertEqual(estado["codigo_salida"], r.EXIT_FUENTE_INACCESIBLE)
        self.assertEqual(estado["fuentes"]["DOF"]["status"], c.SOURCE_UNAVAILABLE)
        self.assertFalse(estado["fuentes"]["DOF"]["retryable"])

        self.assertEqual(self._correr_sjf(RedSjf()), r.EXIT_OK)
        self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertTrue(vli.OUTPUT_FILE.exists())


class TestCasoB2_SatCaido(_AislaSalidaMixin, unittest.TestCase):
    def test_sat_caido_da_brief_parcial_que_lo_dice(self):
        self.assertEqual(self._correr_dof(RedDofSat(sat="bloqueado")), r.EXIT_OK)

        brief = vdof.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertIn("❌ SAT", brief)
        self.assertIn("SOURCE_UNAVAILABLE", brief)
        contrato = c.leer_sidecar(vdof.OUTPUT_FILE.with_suffix(".json"))
        self.assertEqual(contrato["SAT"]["status"], c.SOURCE_UNAVAILABLE)
        self.assertEqual(contrato["SAT"]["items"], [])
        self.assertTrue(contrato["DOF"]["items"])
        estado = self._estado(vdof.OUTPUT_FILE)
        self.assertEqual((estado["estado"], estado["codigo_salida"]), (r.PARCIAL, r.EXIT_OK))
        self.assertEqual(estado["fuentes"]["SAT"]["status"], c.SOURCE_UNAVAILABLE)


class TestCasoC_SjfCaido(_AislaSalidaMixin, unittest.TestCase):
    def test_sjf_caido_no_escribe_informe_ni_insiste(self):
        red = RedSjf(busqueda="bloqueado")
        self.assertEqual(self._correr_sjf(red), r.EXIT_FUENTE_INACCESIBLE)

        self.assertEqual(red.llamadas, 1, "ni reintentos ni los otros 4 temas")
        self.assertFalse(vjur.OUTPUT_FILE.exists())
        estado = self._estado(vjur.OUTPUT_FILE)
        self.assertEqual((estado["estado"], estado["codigo_salida"]),
                         (r.FUENTE_INACCESIBLE, r.EXIT_FUENTE_INACCESIBLE))
        self.assertEqual(len(estado["temas"]), len(vjur.TEMAS))
        for tema in estado["temas"].values():
            self.assertEqual(tema["status"], c.SOURCE_UNAVAILABLE)
            self.assertFalse(tema["retryable"])

    def test_detalle_caido_no_cuenta_como_criterio(self):
        """La búsqueda responde con IUS pero ninguna ficha se puede leer: no hay
        criterio verificado — el tema no es 'SUCCESS con hallazgos'."""
        self.assertEqual(self._correr_sjf(RedSjf(detalle="500")), r.EXIT_FUENTE_INACCESIBLE)
        self.assertFalse(vjur.OUTPUT_FILE.exists())
        for tema in self._estado(vjur.OUTPUT_FILE)["temas"].values():
            self.assertEqual(tema["status"], c.SOURCE_UNAVAILABLE)
            self.assertTrue(tema["retryable"], "un HTTP 500 del detalle puede ser transitorio")
            self.assertTrue(any("2028888" in e for e in tema["errors"]))


class TestCasoC2_UnTemaCaido(_AislaSalidaMixin, unittest.TestCase):
    def test_un_tema_caido_da_informe_parcial_sin_falso_negativo(self):
        caido = vjur.TEMAS[1]
        self.assertEqual(self._correr_sjf(RedSjf(temas_caidos={caido["expresion"]})), r.EXIT_OK)

        informe = vjur.OUTPUT_FILE.read_text(encoding="utf-8")
        seccion = informe.split(f"## {caido['label']}")[1].split("\n## ")[0]
        self.assertIn("❌", seccion)
        self.assertNotIn("Sin criterios", seccion)
        estado = self._estado(vjur.OUTPUT_FILE)
        self.assertEqual((estado["estado"], estado["codigo_salida"]), (r.PARCIAL, r.EXIT_OK))
        self.assertEqual(estado["temas"][caido["label"]]["status"], c.SOURCE_UNAVAILABLE)
        contrato = c.leer_sidecar(vjur.OUTPUT_FILE.with_suffix(".json"))
        self.assertEqual(contrato[caido["label"]]["status"], c.SOURCE_UNAVAILABLE)
        self.assertEqual(contrato[caido["label"]]["items"], [])


class TestCasoD_TodoCaido(_AislaSalidaMixin, unittest.TestCase):
    def test_todo_caido_no_genera_nada(self):
        self.assertEqual(self._correr_dof(RedDofSat(dof="bloqueado", sat="bloqueado")),
                         r.EXIT_FUENTE_INACCESIBLE)
        self.assertEqual(self._correr_sjf(RedSjf(busqueda="bloqueado")), r.EXIT_FUENTE_INACCESIBLE)
        self.assertEqual(vli.main(), r.EXIT_SIN_INSUMOS)

        self.assertEqual(list(self.vig_dir.glob("*.md")), [])
        self.assertEqual(list(self.jur_dir.glob("*.md")), [])
        self.assertFalse(vli.OUTPUT_FILE.exists())
        estado = self._estado(vli.OUTPUT_FILE)
        self.assertEqual((estado["estado"], estado["codigo_salida"]), (r.SIN_INSUMOS, r.EXIT_SIN_INSUMOS))
        self.assertIn("vigente", estado["motivo"])


class TestCasoD2_FuentesOkSinHallazgos(_AislaSalidaMixin, unittest.TestCase):
    def test_fuentes_disponibles_sin_novedades_no_genera_borrador(self):
        """Distinto de una fuente caída: las fuentes SÍ respondieron, solo que no
        había nada noticiable — tampoco se escribe un post."""
        self.assertEqual(self._correr_dof(RedDofSat(dof="vacio", sat="vacio")), r.EXIT_OK)
        self.assertEqual(self._correr_sjf(RedSjf(busqueda="vacia")), r.EXIT_OK)
        self.assertEqual(self._estado(vdof.OUTPUT_FILE)["estado"], r.OK)

        informe = vjur.OUTPUT_FILE.read_text(encoding="utf-8")
        for tema in vjur.TEMAS:
            seccion = informe.split(f"## {tema['label']}")[1].split("\n## ")[0]
            self.assertIn("Sin criterios", seccion)

        self.assertEqual(vli.main(), r.EXIT_SIN_INSUMOS)
        self.assertFalse(vli.OUTPUT_FILE.exists())
        self.assertTrue(self._estado(vli.OUTPUT_FILE)["motivo"].startswith("SIN_HALLAZGOS"))


class TestCasoE_Idempotencia(_AislaSalidaMixin, unittest.TestCase):
    def test_segunda_corrida_no_consulta_ni_pisa_el_estado(self):
        red = RedDofSat()
        self.assertEqual(self._correr_dof(red), r.EXIT_OK)
        brief = vdof.OUTPUT_FILE.read_text(encoding="utf-8")
        estado = self._estado(vdof.OUTPUT_FILE)
        llamadas = dict(red.llamadas)

        self.assertEqual(self._correr_dof(red), r.EXIT_OK)
        self.assertEqual(vdof.OUTPUT_FILE.read_text(encoding="utf-8"), brief)
        self.assertEqual(red.llamadas, llamadas, "la segunda corrida no debió volver a golpear la red")
        self.assertEqual(self._estado(vdof.OUTPUT_FILE), estado, "el estado de la corrida real se conserva")

    def test_borrador_no_se_duplica(self):
        self._correr_dof(RedDofSat())
        self._correr_sjf(RedSjf())
        self.assertEqual(vli.main(), r.EXIT_OK)
        primero = vli.OUTPUT_FILE.read_text(encoding="utf-8")
        self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertEqual(vli.OUTPUT_FILE.read_text(encoding="utf-8"), primero)


class TestCasoF_ReintentoTrasFuenteCaida(_AislaSalidaMixin, unittest.TestCase):
    """Pozo envenenado: la guarda 'si el archivo existe, termina' junto con
    escribir siempre el archivo dejaba el día sin vigilancia y sin reintento."""

    def test_dof_caido_no_bloquea_el_reintento_del_dia(self):
        self.assertEqual(self._correr_dof(RedDofSat(dof="bloqueado")), r.EXIT_FUENTE_INACCESIBLE)
        self.assertEqual(self._correr_dof(RedDofSat()), r.EXIT_OK)
        self.assertTrue(vdof.OUTPUT_FILE.exists())
        self.assertEqual(self._estado(vdof.OUTPUT_FILE)["estado"], r.OK)

    def test_sjf_caido_no_bloquea_el_reintento_de_la_semana(self):
        self.assertEqual(self._correr_sjf(RedSjf(busqueda="bloqueado")), r.EXIT_FUENTE_INACCESIBLE)
        self.assertEqual(self._correr_sjf(RedSjf()), r.EXIT_OK)
        self.assertTrue(vjur.OUTPUT_FILE.exists())

    def test_borrador_bloqueado_no_impide_generarlo_despues(self):
        self.assertEqual(vli.main(), r.EXIT_SIN_INSUMOS)
        self._correr_dof(RedDofSat())
        self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertTrue(vli.OUTPUT_FILE.exists())


# ── Piezas sueltas ─────────────────────────────────────────────────────────────


class TestBuscarTesis(_AislaSalidaMixin, unittest.TestCase):
    def test_busqueda_fallida_es_none_no_lista_vacia(self):
        with mock.patch.object(vjur.requests, "request", RedSjf(busqueda="bloqueado")):
            ids, error = vjur.buscar_tesis("69-B")
        self.assertIsNone(ids)
        self.assertEqual(error["status"], c.SOURCE_UNAVAILABLE)

    def test_busqueda_sin_resultados_es_lista_vacia(self):
        with mock.patch.object(vjur.requests, "request", RedSjf(busqueda="vacia")):
            ids, error = vjur.buscar_tesis("69-B")
        self.assertEqual(ids, [])
        self.assertIsNone(error)


class TestSjfNoReintentaBloqueoDePolitica(_AislaSalidaMixin, unittest.TestCase):
    def test_bloqueo_de_politica_no_agota_los_reintentos(self):
        """Un ProxyError (bloqueo de política) debe cortar _http() en el primer
        intento — reintentar 2s/4s/8s en el mismo entorno nunca lo resuelve."""
        red = RedSjf(busqueda="bloqueado")
        with mock.patch.object(vjur.requests, "request", red):
            outcome = vjur._http("POST", "https://sjf2.scjn.gob.mx/x")
        self.assertEqual(red.llamadas, 1)
        self.assertEqual(outcome.status, c.SOURCE_UNAVAILABLE)
        self.assertFalse(outcome.retryable)
        self.assertTrue(outcome.bloqueo_politica)


class TestHallazgosDeLaCorridaReal(_AislaSalidaMixin, unittest.TestCase):
    """Defectos que aparecieron al correr los scripts contra las fuentes reales
    (10-oct-2026) y que la red simulada no mostraba."""

    def test_el_dof_se_consulta_en_el_host_que_ampara_su_certificado(self):
        """El certificado del portal solo cubre dof.gob.mx: con www la
        verificación TLS falla por nombre (nunca se desactiva la verificación)."""
        self.assertEqual(urlparse(vdof.DOF_BASE).hostname, "dof.gob.mx")

    def test_enlaces_relativos_del_dof_quedan_absolutos(self):
        html = (
            '<html><body>'
            '<a href="nota_detalle.php?codigo=5712345&fecha=10/10/2026">Listado de contribuyentes '
            '69-B definitivos publicado hoy</a>'
            '<a href="http://dof.gob.mx/index.php">Resolución Miscelánea Fiscal para 2027</a>'
            '</body></html>'
        )
        with mock.patch.object(vdof.requests, "get", lambda url, headers=None, timeout=None: FakeResponse(text=html)):
            resultado = vdof.fetch_dof()
        urls = [item["url"] for item in resultado.items[:2]]
        self.assertEqual(urls, [
            "https://dof.gob.mx/nota_detalle.php?codigo=5712345&fecha=10/10/2026",
            "http://dof.gob.mx/index.php",
        ])

    def test_enlaces_relativos_del_sat_se_resuelven_contra_la_pagina(self):
        html = ('<html><body><a href="/com/1">Nuevo criterio SAT sobre cancelación de CSD</a>'
                '<a href="regla-miscelanea">Acuerdo SAT: regla miscelánea modificada</a></body></html>')
        with mock.patch.object(vdof.requests, "get", lambda url, headers=None, timeout=None: FakeResponse(text=html)):
            resultado = vdof.fetch_sat()
        self.assertEqual([item["url"] for item in resultado.items], [
            "https://www.sat.gob.mx/com/1",
            "https://www.sat.gob.mx/articulo/87284/regla-miscelanea",
        ])

    def test_detalle_tras_anti_bots_se_diagnostica_y_no_cuenta(self):
        self.assertEqual(self._correr_sjf(RedSjf(detalle="incapsula")), r.EXIT_FUENTE_INACCESIBLE)
        self.assertFalse(vjur.OUTPUT_FILE.exists())
        for tema in self._estado(vjur.OUTPUT_FILE)["temas"].values():
            self.assertEqual(tema["status"], c.SOURCE_UNAVAILABLE)
            self.assertFalse(tema["retryable"], "reintentar por HTTP no resuelve el anti-bots")
            self.assertTrue(all("Incapsula" in e for e in tema["errors"]), tema["errors"])

    def test_el_mismo_diagnostico_se_agrupa_por_causa(self):
        temas = {"ius": ["101", "102", "103"]}

        class _Red(RedSjf):
            def __call__(self, method, url, headers=None, timeout=None, json=None, **kw):
                if method == "POST":
                    return FakeResponse(json_data={"documents": [{"ius": i} for i in temas["ius"]]})
                return FakeResponse(text=HTML_INCAPSULA, headers={"content-type": "text/html"})

        self._correr_sjf(_Red())
        errores = next(iter(self._estado(vjur.OUTPUT_FILE)["temas"].values()))["errors"]
        self.assertEqual(len(errores), 1, errores)
        self.assertIn("101, 102, 103", errores[0])

    def test_respuesta_no_json_sin_anti_bots_dice_que_llego(self):
        with mock.patch.object(vjur.requests, "request",
                               lambda *a, **k: FakeResponse(text="<html>mantenimiento</html>",
                                                            headers={"content-type": "text/html"})):
            ficha = vjur.obtener_detalle(2027452)
        self.assertIn("no JSON", ficha["_error"])
        self.assertIn("text/html", ficha["_error"])
        self.assertNotIn("Incapsula", ficha["_error"])


class TestInformeDegradadoSjf(unittest.TestCase):
    def test_separa_nuevos_de_contexto_y_usa_la_instancia(self):
        temas = [t["label"] for t in vjur.TEMAS]
        nueva = {"ius": 1, "rubro": "R", "instancia": "Segunda Sala", "sala_codigo": "2",
                 "en_ventana_semana": True}
        vieja = {"ius": 2, "rubro": "V", "instancia": "Pleno Regional", "en_ventana_semana": False}
        resultados = {
            temas[0]: {"status": c.SUCCESS, "retryable": False, "errors": [], "fichas": [nueva, vieja]},
            temas[1]: {"status": c.SOURCE_UNAVAILABLE, "retryable": True, "errors": ["HTTP 500"], "fichas": []},
            temas[2]: {"status": c.SUCCESS, "retryable": False, "errors": [], "fichas": []},
        }
        texto = vjur._informe_degradado(resultados, motivo="prueba")

        self.assertIn("Segunda Sala", texto)  # antes imprimía el código interno de 'sala'
        self.assertIn("### Nuevos esta semana", texto)
        self.assertIn("### Contexto (fuera de ventana)", texto)
        fallido = texto.split(f"## {temas[1]}")[1].split("\n## ")[0]
        self.assertIn('no equivale a "sin criterios"', fallido)
        vacio = texto.split(f"## {temas[2]}")[1].split("\n## ")[0]
        self.assertIn("Sin criterios", vacio)


class TestContenidoSoloBriefsVigentes(_AislaSalidaMixin, unittest.TestCase):
    def _brief(self, nombre: str, items: list[dict]) -> None:
        self.vig_dir.mkdir(parents=True, exist_ok=True)
        ruta = self.vig_dir / nombre
        ruta.write_text(f"# Vigilancia DOF/SAT — {ruta.stem}\n", encoding="utf-8")
        c.guardar_sidecar(ruta, {"DOF": c.ResultadoFuente(source="DOF", status=c.SUCCESS, items=items)})

    def test_brief_viejo_no_se_recicla(self):
        self._brief("2026-08-01.md", [{"titulo": "hallazgo de agosto"}])
        with mock.patch.object(vli, "HOY", date(2026, 10, 1)):
            self.assertEqual(vli.main(), r.EXIT_SIN_INSUMOS)
        self.assertFalse(vli.OUTPUT_FILE.exists())

    def test_brief_de_la_semana_si_se_usa(self):
        self._brief("2026-09-29.md", [{"titulo": "hallazgo vigente"}])
        with mock.patch.object(vli, "HOY", date(2026, 10, 1)):
            self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertIn("2026-09-29.md", vli.OUTPUT_FILE.read_text(encoding="utf-8"))

    def test_fichas_con_error_no_cuentan_como_hallazgo(self):
        contrato = {"SJF:x": {"source": "SJF:x", "status": c.SUCCESS,
                              "items": [{"ius": 1, "_error": "HTTP 500"}]}}
        total, _ = vli._items_validados(contrato)
        self.assertEqual(total, 0)

    def test_cta_toma_el_numero_de_la_variable_de_entorno(self):
        os.environ["ITOSTURRE_WHATSAPP"] = "5213300000000"
        self._brief(f"{vli.DATE_STR}.md", [{"titulo": "hallazgo"}])
        self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertIn("wa.me/5213300000000", vli.OUTPUT_FILE.read_text(encoding="utf-8"))

    def test_cta_sin_variable_deja_el_marcador(self):
        self._brief(f"{vli.DATE_STR}.md", [{"titulo": "hallazgo"}])
        self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertIn("wa.me/[número]", vli.OUTPUT_FILE.read_text(encoding="utf-8"))


class TestRedaccionConModelo(_AislaSalidaMixin, unittest.TestCase):
    """La rama con LLM, con un módulo `anthropic` falso: usa el modelo
    configurado, pasa los avisos de fuente caída y no revienta sin la librería."""

    def setUp(self):
        super().setUp()
        os.environ["ANTHROPIC_API_KEY"] = "sk-prueba"
        os.environ["ITOSTURRE_MODELO"] = "modelo-de-prueba"

    def test_dof_usa_el_modelo_configurado_y_avisa_del_sat(self):
        modulo, llamadas = _anthropic_falso()
        with mock.patch.dict(sys.modules, {"anthropic": modulo}):
            self.assertEqual(self._correr_dof(RedDofSat(sat="bloqueado")), r.EXIT_OK)
        self.assertEqual(llamadas[0]["model"], "modelo-de-prueba")
        prompt = llamadas[0]["messages"][0]["content"]
        self.assertIn("SAT: SOURCE_UNAVAILABLE", prompt)
        self.assertIn("TEXTO DEL MODELO", vdof.OUTPUT_FILE.read_text(encoding="utf-8"))

    def test_sjf_usa_el_modelo_configurado(self):
        modulo, llamadas = _anthropic_falso()
        with mock.patch.dict(sys.modules, {"anthropic": modulo}):
            self.assertEqual(self._correr_sjf(RedSjf()), r.EXIT_OK)
        self.assertEqual(llamadas[0]["model"], "modelo-de-prueba")
        self.assertIn("TEXTO DEL MODELO", vjur.OUTPUT_FILE.read_text(encoding="utf-8"))

    def test_linkedin_usa_el_modelo_y_el_cta(self):
        os.environ["ITOSTURRE_WHATSAPP"] = "5213300000000"
        self._correr_dof(RedDofSat())
        modulo, llamadas = _anthropic_falso()
        with mock.patch.dict(sys.modules, {"anthropic": modulo}):
            self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertEqual(llamadas[0]["model"], "modelo-de-prueba")
        self.assertIn("wa.me/5213300000000", llamadas[0]["messages"][0]["content"])

    def test_sin_libreria_anthropic_cae_al_modo_sin_llm(self):
        with mock.patch.dict(sys.modules, {"anthropic": None}):
            self.assertEqual(self._correr_dof(RedDofSat()), r.EXIT_OK)
            self._correr_sjf(RedSjf())
            self.assertEqual(vli.main(), r.EXIT_OK)
        self.assertIn("sin LLM", vdof.OUTPUT_FILE.read_text(encoding="utf-8"))
        self.assertIn("Modo degradado", vjur.OUTPUT_FILE.read_text(encoding="utf-8"))
        self.assertIn("sin LLM", vli.OUTPUT_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
