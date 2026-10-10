"""Contrato de corrida de las rutinas de vigilancia (itosturre/vigilancia/rutina.py).

Offline. Protege tres reglas:
  1. Las salidas nunca caen dentro del paquete itosturre/: en macOS y Windows
     (sistemas de archivos sin distinción de mayúsculas) `Itosturre/` ES
     `itosturre/`, y la regla de .gitignore que las ocultaba ocultaba también
     cualquier módulo nuevo del paquete.
  2. La fecha operativa es la de la Ciudad de México, no la del servidor.
  3. El generador de contenido solo ve briefs vigentes (últimos 7 días).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from itosturre.vigilancia import rutina as r

REPO = Path(__file__).resolve().parent.parent


class TestSalidaFueraDelPaquete(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict("os.environ", {}, clear=False)
        self._env.start()
        os.environ.pop("ITOSTURRE_SALIDA", None)

    def tearDown(self):
        self._env.stop()

    def test_salida_por_omision_es_salidas_en_la_raiz(self):
        self.assertEqual(r.salida_dir(), REPO / "salidas")

    def test_variable_de_entorno_absoluta_reubica_la_salida(self):
        with TemporaryDirectory() as tmp:
            os.environ["ITOSTURRE_SALIDA"] = tmp
            self.assertEqual(r.salida_dir(), Path(tmp))

    def test_variable_relativa_se_resuelve_desde_la_raiz_no_desde_el_cwd(self):
        os.environ["ITOSTURRE_SALIDA"] = "otra_salida"
        self.assertEqual(r.salida_dir(), REPO / "otra_salida")

    def test_variable_vacia_no_apunta_al_directorio_actual(self):
        os.environ["ITOSTURRE_SALIDA"] = "   "
        self.assertEqual(r.salida_dir(), REPO / "salidas")

    def test_la_salida_por_omision_no_esta_dentro_del_paquete(self):
        r.validar_salida(r.salida_dir())  # no debe lanzar

    def test_validar_salida_rechaza_el_paquete_con_cualquier_mayuscula(self):
        for ruta in (
            REPO / "itosturre",
            REPO / "Itosturre" / "Vigilancia",
            REPO / "ITOSTURRE" / "Jurisprudencia",
            REPO / "itosturre" / "vigilancia" / "eventos.jsonl",
        ):
            with self.subTest(ruta=ruta), self.assertRaises(ValueError):
                r.validar_salida(ruta)

    def test_validar_salida_acepta_salidas_y_rutas_externas(self):
        r.validar_salida(REPO / "salidas" / "Vigilancia")
        with TemporaryDirectory() as tmp:
            r.validar_salida(Path(tmp) / "Vigilancia")

    def test_validar_salida_no_confunde_prefijos_del_nombre(self):
        r.validar_salida(REPO / "itosturre_salidas" / "Vigilancia")


class TestGitignoreNoTapaElPaquete(unittest.TestCase):
    """Regresión: `/Itosturre/` en .gitignore ignoraba, sin distinguir
    mayúsculas, los archivos NUEVOS de itosturre/ — un módulo nuevo del paquete
    nunca habría llegado al repo (verificado en macOS con core.ignorecase=true).
    Se fuerza core.ignorecase=true para que la prueba muerda también en Linux."""

    def setUp(self):
        if shutil.which("git") is None or not (REPO / ".git").exists():
            self.skipTest("requiere git y un checkout del repositorio")

    def _ignorado(self, ruta: str) -> bool:
        res = subprocess.run(
            ["git", "-c", "core.ignorecase=true", "check-ignore", "--no-index", "-q", ruta],
            cwd=REPO, capture_output=True, text=True,
        )
        if res.returncode not in (0, 1):
            self.skipTest(f"git check-ignore no disponible: {res.stderr.strip()}")
        return res.returncode == 0

    def test_ningun_archivo_nuevo_del_paquete_se_ignora(self):
        for ruta in (
            "itosturre/modulo_nuevo.py",
            "itosturre/vigilancia/modulo_nuevo.py",
            "itosturre/audit/modulo_nuevo.py",
        ):
            with self.subTest(ruta=ruta):
                self.assertFalse(self._ignorado(ruta), f"{ruta} quedaría fuera del repo")

    def test_las_salidas_de_las_rutinas_si_se_ignoran(self):
        self.assertTrue(self._ignorado("salidas/Vigilancia/2026-10-10.md"))
        self.assertTrue(self._ignorado("salidas/eventos.jsonl"))


class TestFechaCiudadDeMexico(unittest.TestCase):
    def test_hoy_mx_usa_la_hora_de_la_ciudad_de_mexico(self):
        # 03:00 UTC del 11-oct = 21:00 del 10-oct en la Ciudad de México (UTC-6).
        instante = datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(r.hoy_mx(instante), date(2026, 10, 10))

    def test_respaldo_sin_base_de_zonas_es_utc_menos_6(self):
        """Windows sin el paquete tzdata no trae la base IANA: la Ciudad de
        México no tiene horario de verano desde 2022, así que UTC-6 fijo da la
        misma fecha."""
        with mock.patch.object(r, "ZoneInfo", side_effect=r.ZoneInfoNotFoundError("sin base")):
            zona = r._zona_mx()
        self.assertEqual(zona.utcoffset(None), timedelta(hours=-6))
        instante = datetime(2026, 10, 11, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(instante.astimezone(zona).date(), date(2026, 10, 10))


class TestBriefsVigentes(unittest.TestCase):
    def test_fecha_de_nombre(self):
        self.assertEqual(r.fecha_de_nombre("2026-10-01.md"), date(2026, 10, 1))
        # Informe semanal: el domingo de la semana ISO, último día que cubre.
        self.assertEqual(r.fecha_de_nombre("semana-2026-W40.md"), date(2026, 10, 4))
        self.assertIsNone(r.fecha_de_nombre("notas.md"))
        self.assertIsNone(r.fecha_de_nombre("semana-2026-W99.md"))
        self.assertIsNone(r.fecha_de_nombre("borrador-2026-10-01.md"))

    def test_descarta_viejos_y_lo_que_no_es_brief(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            for nombre in ("2026-09-01.md", "2026-09-29.md", "2026-10-01.md",
                           "2026-10-01.json", "2026-10-01.estado.json", "notas.md"):
                (d / nombre).write_text("x", encoding="utf-8")
            vigentes = [p.name for p in r.briefs_vigentes(d, date(2026, 10, 1))]
        self.assertEqual(vigentes, ["2026-10-01.md", "2026-09-29.md"])

    def test_incluye_el_informe_de_la_semana_en_curso(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "semana-2026-W40.md").write_text("x", encoding="utf-8")
            (d / "semana-2026-W35.md").write_text("x", encoding="utf-8")
            vigentes = [p.name for p in r.briefs_vigentes(d, date(2026, 10, 1))]
        self.assertEqual(vigentes, ["semana-2026-W40.md"])

    def test_directorio_inexistente_no_falla(self):
        self.assertEqual(r.briefs_vigentes(Path("/no/existe/nunca"), date(2026, 10, 1)), [])


class TestEstadoDeCorrida(unittest.TestCase):
    def test_codigos_de_salida_por_estado(self):
        self.assertEqual(r.codigo_salida(r.OK), r.EXIT_OK)
        self.assertEqual(r.codigo_salida(r.PARCIAL), r.EXIT_OK)
        self.assertEqual(r.codigo_salida(r.FUENTE_INACCESIBLE), r.EXIT_FUENTE_INACCESIBLE)
        self.assertEqual(r.codigo_salida(r.SIN_INSUMOS), r.EXIT_SIN_INSUMOS)
        self.assertEqual((r.EXIT_OK, r.EXIT_FUENTE_INACCESIBLE, r.EXIT_SIN_INSUMOS), (0, 2, 3))

    def test_registrar_estado_escribe_json_con_codigo_y_hora_de_mexico(self):
        with TemporaryDirectory() as tmp:
            ruta = r.registrar_estado(Path(tmp) / "Vigilancia", "2026-10-10", r.PARCIAL,
                                      fuente_faltante="SAT")
            datos = json.loads(ruta.read_text(encoding="utf-8"))
        self.assertEqual(ruta.name, "2026-10-10.estado.json")
        self.assertEqual(datos["clave"], "2026-10-10")
        self.assertEqual(datos["estado"], r.PARCIAL)
        self.assertEqual(datos["codigo_salida"], r.EXIT_OK)
        self.assertEqual(datos["fuente_faltante"], "SAT")
        self.assertTrue(datos["registrado"].endswith("-06:00"), datos["registrado"])

    def test_registrar_estado_rechaza_un_estado_desconocido(self):
        with TemporaryDirectory() as tmp, self.assertRaises(ValueError):
            r.registrar_estado(Path(tmp), "2026-10-10", "YA_EXISTIA")

    def test_registrar_estado_rechaza_escribir_dentro_del_paquete(self):
        destino = REPO / "Itosturre" / "_prueba_no_debe_existir"
        try:
            with self.assertRaises(ValueError):
                r.registrar_estado(destino, "2026-10-10", r.OK)
            self.assertFalse(destino.exists())
        finally:
            shutil.rmtree(destino, ignore_errors=True)


class TestModelo(unittest.TestCase):
    def setUp(self):
        self._env = mock.patch.dict("os.environ", {}, clear=False)
        self._env.start()
        os.environ.pop("ITOSTURRE_MODELO", None)

    def tearDown(self):
        self._env.stop()

    def test_modelo_por_omision(self):
        self.assertEqual(r.modelo(), r.MODELO_POR_OMISION)

    def test_modelo_configurable_por_entorno(self):
        os.environ["ITOSTURRE_MODELO"] = "modelo-de-prueba"
        self.assertEqual(r.modelo(), "modelo-de-prueba")

    def test_ningun_agente_fija_el_modelo_en_el_codigo(self):
        for ruta in sorted((REPO / "agentes").glob("*.py")):
            with self.subTest(ruta=ruta.name):
                self.assertNotRegex(ruta.read_text(encoding="utf-8"), r"model\s*=\s*[\"']")


if __name__ == "__main__":
    unittest.main()
