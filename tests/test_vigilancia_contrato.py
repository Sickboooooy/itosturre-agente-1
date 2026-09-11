"""Pruebas unitarias del contrato de datos de vigilancia legal.

Ver docs/VIGILANCIA_LEGAL.md — Legal Data Availability Contract.
"""
from __future__ import annotations

import json
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
