"""Pruebas unitarias del contrato de datos de vigilancia legal.

Ver docs/VIGILANCIA_LEGAL.md — Legal Data Availability Contract.
"""
from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import requests

from itosturre.vigilancia import contrato as c


class TestResultadoFuente(unittest.TestCase):
    def test_status_invalido_rechazado(self):
        with self.assertRaises(ValueError):
            c.ResultadoFuente(source="DOF", status="NO_EXISTE")

    def test_status_no_success_con_items_rechazado(self):
        """Invariante dura del contrato: un estado que no es SUCCESS nunca lleva
        hallazgos — evita que un collector 'rellene' items pese a haber fallado."""
        with self.assertRaises(ValueError):
            c.ResultadoFuente(source="DOF", status=c.SOURCE_UNAVAILABLE, items=[{"x": 1}])

    def test_success_sin_items_es_valido(self):
        """SUCCESS con items=[] es 'se consultó y no hubo novedades' — válido."""
        r = c.ResultadoFuente(source="DOF", status=c.SUCCESS, items=[])
        self.assertTrue(r.ok)
        self.assertEqual(r.items, [])

    def test_to_dict_serializable(self):
        r = c.ResultadoFuente(source="SAT", status=c.SUCCESS, items=[{"a": 1}])
        d = r.to_dict()
        json.dumps(d)  # no debe lanzar
        self.assertEqual(d["source"], "SAT")


class TestClasificarExcepcionRed(unittest.TestCase):
    def test_proxy_error_no_reintentable(self):
        status, retryable, mensaje = c.clasificar_excepcion_red(
            requests.exceptions.ProxyError("403 to CONNECT dof.gob.mx:443")
        )
        self.assertEqual(status, c.SOURCE_UNAVAILABLE)
        self.assertFalse(retryable)
        self.assertIn("política de red", mensaje)

    def test_connection_error_con_403_no_reintentable(self):
        status, retryable, _ = c.clasificar_excepcion_red(
            requests.exceptions.ConnectionError("gateway answered 403 to CONNECT")
        )
        self.assertEqual(status, c.SOURCE_UNAVAILABLE)
        self.assertFalse(retryable)

    def test_connection_error_generico_reintentable(self):
        """Un ConnectionError SIN evidencia de bloqueo de política se trata como
        falla transitoria genérica (conservador: no se asume bloqueo sin evidencia)."""
        status, retryable, _ = c.clasificar_excepcion_red(
            requests.exceptions.ConnectionError("Name or service not known")
        )
        self.assertEqual(status, c.SOURCE_UNAVAILABLE)
        self.assertTrue(retryable)

    def test_timeout_reintentable(self):
        status, retryable, _ = c.clasificar_excepcion_red(requests.exceptions.Timeout("timed out"))
        self.assertEqual(status, c.TIMEOUT)
        self.assertTrue(retryable)

    def test_timeout_de_conexion_al_proxy_no_es_bloqueo_de_politica(self):
        """ConnectTimeout hereda de ConnectionError Y de Timeout: que el mensaje
        mencione el proxy no lo vuelve un bloqueo — es transitorio."""
        exc = requests.exceptions.ConnectTimeout("Connection to proxy timed out")
        self.assertFalse(c.es_bloqueo_politica(exc))
        status, retryable, _ = c.clasificar_excepcion_red(exc)
        self.assertEqual(status, c.TIMEOUT)
        self.assertTrue(retryable)

    def test_es_bloqueo_politica(self):
        self.assertTrue(c.es_bloqueo_politica(requests.exceptions.ProxyError("403 to CONNECT")))
        self.assertTrue(c.es_bloqueo_politica(
            requests.exceptions.ConnectionError("Tunnel connection failed: 403 Forbidden")))
        self.assertFalse(c.es_bloqueo_politica(
            requests.exceptions.ConnectionError("Name or service not known")))
        self.assertFalse(c.es_bloqueo_politica(ValueError("403")))

    def test_mensaje_de_bloqueo_dice_como_resolverlo(self):
        _, _, mensaje = c.clasificar_excepcion_red(requests.exceptions.ProxyError("403 to CONNECT"))
        self.assertIn("autorizar el dominio", mensaje)


class TestResumenFuente(unittest.TestCase):
    def test_resumen_sin_items_para_el_estado_de_corrida(self):
        r = c.ResultadoFuente(source="DOF", status=c.SUCCESS, items=[{"a": 1}, {"b": 2}])
        resumen = r.resumen()
        self.assertEqual(resumen["status"], c.SUCCESS)
        self.assertEqual(resumen["n_items"], 2)
        self.assertNotIn("items", resumen)
        for clave in ("retryable", "errors", "retrieved_at", "execution_environment"):
            self.assertIn(clave, resumen)
        json.dumps(resumen)  # serializable


class TestObservabilidad(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._log = Path(self._tmp.name) / "eventos.jsonl"
        self._patch = mock.patch.object(c, "EVENTOS_LOG", self._log)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self._tmp.cleanup()

    def test_evento_no_reconocido_rechazado(self):
        with self.assertRaises(ValueError):
            c.registrar_evento("evento_inventado")

    def test_evento_se_anexa_como_jsonl(self):
        c.registrar_evento("watch_started", watch="dof_sat")
        c.registrar_evento("source_success", source="DOF", n_items=3)
        lineas = self._log.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lineas), 2)
        primero = json.loads(lineas[0])
        self.assertEqual(primero["evento"], "watch_started")
        self.assertEqual(primero["watch"], "dof_sat")
        self.assertIn("ts", primero)


class TestEventosFueraDelPaquete(unittest.TestCase):
    """El log de eventos vivía en <repo>/Itosturre/eventos.jsonl, que en macOS y
    Windows es el paquete itosturre/ (mismo directorio sin distinguir mayúsculas)."""

    def test_log_por_omision_no_esta_dentro_del_paquete(self):
        from itosturre.vigilancia import rutina

        rutina.validar_salida(c.EVENTOS_LOG.parent)  # no debe lanzar

    def test_registrar_evento_se_niega_a_escribir_dentro_del_paquete(self):
        repo = Path(__file__).resolve().parent.parent
        destino = repo / "Itosturre" / "_prueba_no_debe_existir"
        try:
            with mock.patch.object(c, "EVENTOS_LOG", destino / "eventos.jsonl"), \
                 self.assertRaises(ValueError):
                c.registrar_evento("watch_started", watch="dof_sat")
            self.assertFalse(destino.exists())
        finally:
            shutil.rmtree(destino, ignore_errors=True)


class TestSidecar(unittest.TestCase):
    def test_guardar_y_leer_sidecar_roundtrip(self):
        with TemporaryDirectory() as tmp:
            ruta_md = Path(tmp) / "2026-09-11.md"
            resultados = {
                "DOF": c.ResultadoFuente(source="DOF", status=c.SUCCESS, items=[{"titulo": "x"}]),
                "SAT": c.ResultadoFuente(source="SAT", status=c.SOURCE_UNAVAILABLE, errors=["bloqueado"]),
            }
            ruta_json = c.guardar_sidecar(ruta_md, resultados)
            self.assertEqual(ruta_json, ruta_md.with_suffix(".json"))
            leido = c.leer_sidecar(ruta_json)
            self.assertEqual(leido["DOF"]["status"], c.SUCCESS)
            self.assertEqual(leido["SAT"]["status"], c.SOURCE_UNAVAILABLE)
            self.assertEqual(leido["SAT"]["items"], [])

    def test_leer_sidecar_inexistente_devuelve_none(self):
        self.assertIsNone(c.leer_sidecar(Path("/no/existe/nunca.json")))


if __name__ == "__main__":
    unittest.main()
