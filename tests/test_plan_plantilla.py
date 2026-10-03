"""Pruebas de la plantilla de ledger (``itosturre/plan/plantilla.py`` y ``plan_audit.py plantilla``).

Todo es sintético: sin red, sin corpus, sin LLM y sin datos de clientes. La plantilla nunca
contiene datos jurídicos: solo marcadores ``[ASIGNAR]`` que el lint debe señalar.
"""
from __future__ import annotations

import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import plan_audit
from itosturre.plan import ESTADOS_VERIFICACION, cargar_ledger, esta_bloqueado, extraer_menciones, lint_ledger
from itosturre.plan.ledger import CAMPOS_CRITERIO, SCHEMA_VERSION, TIPOS_AFIRMACION, validar_esquema
from itosturre.plan.plantilla import IDS_EJEMPLO, NOTAS, ledger_plantilla, problemas_parametros

REPO = Path(__file__).resolve().parent.parent
PLAN_AUDIT = REPO / "plan_audit.py"
PLAN_ID = "PLAN-SINTETICO"
TITULO = "Plan sintético de prueba"
FECHA = "2026-10-02"


def _sin_notas(valor: object) -> object:
    """El ledger sin las llaves de notas (``_instrucciones``), que el auditor ignora."""
    if isinstance(valor, dict):
        return {k: _sin_notas(v) for k, v in valor.items() if not str(k).startswith("_")}
    if isinstance(valor, list):
        return [_sin_notas(v) for v in valor]
    return valor


class LedgerPlantillaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = ledger_plantilla(PLAN_ID, TITULO, FECHA)

    def test_cumple_el_esquema_con_secciones_vacias(self) -> None:
        self.assertEqual(validar_esquema(self.ledger), [])
        self.assertEqual(self.ledger["schema_version"], SCHEMA_VERSION)
        self.assertEqual(
            self.ledger["plan"], {"id": PLAN_ID, "titulo": TITULO, "fecha_documento": FECHA}
        )
        for coleccion in ("evidencias", "contradicciones", "decisiones"):
            with self.subTest(coleccion=coleccion):
                self.assertEqual(self.ledger[coleccion], [])

    def test_un_ejemplo_por_tipo_rotulado_asignar(self) -> None:
        afirmaciones = self.ledger["afirmaciones"]
        self.assertEqual([a["id"] for a in afirmaciones], list(IDS_EJEMPLO))
        self.assertEqual(sorted(a["tipo"] for a in afirmaciones), sorted(TIPOS_AFIRMACION))
        for afirmacion in afirmaciones:
            with self.subTest(afirmacion=afirmacion["id"]):
                self.assertTrue(afirmacion["texto"].startswith("[ASIGNAR"))
                self.assertEqual(afirmacion["verificacion"]["estado"], "[ASIGNAR]")
                self.assertEqual(afirmacion["verificacion"]["evidencias"], [])
                self.assertIsNone(afirmacion["aprobacion"])
                self.assertEqual(afirmacion["autor"], "agente")  # la opción más estricta (PL-009)
                self.assertTrue(afirmacion[NOTAS])
                for referencia in afirmacion["referencias"]:
                    self.assertTrue(referencia.startswith("[ASIGNAR"))
        criterio = next(a for a in afirmaciones if a["tipo"] == "criterio_judicial")
        identificacion = criterio["identificacion_criterio"]
        self.assertEqual(identificacion["tipo_fuente"], "tesis_sjf")
        self.assertEqual({identificacion[c] for c in CAMPOS_CRITERIO}, {"[ASIGNAR]"})

    def test_ningun_dato_juridico(self) -> None:
        """Sin artículos, tesis, URLs, fechas de consulta ni cifras: nada que pueda pasar por dato."""
        contenido = json.dumps(_sin_notas(self.ledger), ensure_ascii=False)
        sin_plan = contenido.replace(SCHEMA_VERSION, "").replace(FECHA, "").replace(PLAN_ID, "")
        self.assertIsNone(re.search(r"\d", sin_plan), "la plantilla no debe contener números")
        self.assertNotIn("http", json.dumps(self.ledger, ensure_ascii=False))
        textos = [
            texto
            for afirmacion in self.ledger["afirmaciones"]
            for texto in (afirmacion["texto"], *afirmacion["referencias"])
        ]
        self.assertEqual(extraer_menciones("\n".join(textos)), [])
        # Las notas tampoco traen cifras (fuera de los nombres de reglas, del menú y del campo
        # contenido_sha256) ni URLs.
        notas = json.dumps(
            [self.ledger[NOTAS], [a[NOTAS] for a in self.ledger["afirmaciones"]]], ensure_ascii=False
        )
        self.assertIsNone(re.search(r"\d", re.sub(r"PL-\d{3}|MENÚ 16|sha256", "", notas)))
        self.assertNotIn("http", notas)

    def test_las_notas_enumeran_el_vocabulario_vigente(self) -> None:
        notas = " ".join(self.ledger[NOTAS])
        for estado in ESTADOS_VERIFICACION:
            with self.subTest(estado=estado):
                self.assertIn(estado, notas)
        self.assertIn("solo lo firma una persona", notas)

    def test_el_lint_marca_cada_ejemplo_y_bloquea(self) -> None:
        hallazgos = lint_ledger(self.ledger)
        self.assertTrue(esta_bloqueado(hallazgos))
        self.assertEqual({h["regla"] for h in hallazgos}, {"PL-001"})
        self.assertEqual(sorted(h["objetivo"] for h in hallazgos), sorted(IDS_EJEMPLO))
        for hallazgo in hallazgos:
            with self.subTest(objetivo=hallazgo["objetivo"]):
                self.assertEqual(hallazgo["severidad"], "BLOQUEANTE")
                self.assertIn("[ASIGNAR]", hallazgo["mensaje"])

    def test_sin_los_ejemplos_el_ledger_queda_limpio(self) -> None:
        """Retirar los ejemplos deja un ledger válido y sin hallazgos: la plantilla no añade nada más."""
        self.ledger["afirmaciones"] = []
        self.assertEqual(validar_esquema(self.ledger), [])
        self.assertEqual(lint_ledger(self.ledger), [])
        self.assertEqual(plan_audit.marcadores_pendientes(self.ledger), [])

    def test_determinista_y_sin_reloj(self) -> None:
        self.assertEqual(ledger_plantilla(PLAN_ID, TITULO, FECHA), self.ledger)
        otra = ledger_plantilla(PLAN_ID, TITULO, "2020-01-31")
        self.assertEqual(otra["plan"]["fecha_documento"], "2020-01-31")

    def test_recorta_espacios(self) -> None:
        ledger = ledger_plantilla(f"  {PLAN_ID} ", f" {TITULO}  ", f" {FECHA} ")
        self.assertEqual(ledger["plan"], {"id": PLAN_ID, "titulo": TITULO, "fecha_documento": FECHA})

    def test_parametros_invalidos(self) -> None:
        casos = {
            "id_vacio": ("  ", TITULO, FECHA, "--plan-id"),
            "id_marcador": ("[ASIGNAR]", TITULO, FECHA, "--plan-id"),
            "titulo_vacio": (PLAN_ID, "", FECHA, "--titulo"),
            "titulo_marcador": (PLAN_ID, "[COMPLETAR título]", FECHA, "--titulo"),
            "fecha_imposible": (PLAN_ID, TITULO, "2026-13-01", "--fecha"),
            "fecha_otro_formato": (PLAN_ID, TITULO, "02/10/2026", "--fecha"),
            "fecha_compacta": (PLAN_ID, TITULO, "20261002", "--fecha"),
            "fecha_vacia": (PLAN_ID, TITULO, "", "--fecha"),
        }
        for nombre, (plan_id, titulo, fecha, parametro) in casos.items():
            with self.subTest(caso=nombre):
                problemas = problemas_parametros(plan_id, titulo, fecha)
                self.assertEqual(len(problemas), 1, problemas)
                self.assertTrue(problemas[0].startswith(parametro))
                with self.assertRaises(ValueError):
                    ledger_plantilla(plan_id, titulo, fecha)
        self.assertEqual(problemas_parametros(PLAN_ID, TITULO, FECHA), [])


class MarcadoresPendientesTests(unittest.TestCase):
    def test_rutas_por_id_y_sin_notas(self) -> None:
        ledger = ledger_plantilla(PLAN_ID, TITULO, FECHA)
        rutas = plan_audit.marcadores_pendientes(ledger)
        self.assertIn("afirmaciones[EJEMPLO-TN].texto", rutas)
        self.assertIn("afirmaciones[EJEMPLO-TN].verificacion.estado", rutas)
        self.assertIn("afirmaciones[EJEMPLO-CJ].identificacion_criterio.alcance", rutas)
        self.assertFalse(any(NOTAS in ruta for ruta in rutas))
        # Una nota con marcador no cuenta; un dato con marcador, sí.
        ledger["afirmaciones"] = []
        ledger["decisiones"] = [
            {"id": "DEC-1", "_nota": "[ASIGNAR]", "pregunta": "¿Pregunta sintética?",
             "responsable": "[ASIGNAR]", "estado": "REQUIERE DECISIÓN HUMANA"}
        ]
        self.assertEqual(plan_audit.marcadores_pendientes(ledger), ["decisiones[DEC-1].responsable"])


class CliPlantillaTests(unittest.TestCase):
    def _ejecutar(self, *argumentos: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(PLAN_AUDIT), *argumentos],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def _plantilla(self, *extra: str) -> subprocess.CompletedProcess:
        return self._ejecutar(
            "plantilla", "--plan-id", PLAN_ID, "--titulo", TITULO, "--fecha", FECHA, *extra
        )

    def test_escribe_un_ledger_que_carga_y_que_lint_marca(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            destino = Path(temp) / "asunto-sintetico" / "plan" / "ledger.json"  # carpetas nuevas
            resultado = self._plantilla("--salida", str(destino))
            self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
            self.assertIn("Plantilla escrita", resultado.stdout)
            self.assertIn("MENÚ 16", resultado.stdout)
            crudo = destino.read_bytes()
            self.assertNotIn(b"\r\n", crudo)
            self.assertFalse(crudo.startswith(b"\xef\xbb\xbf"))
            self.assertEqual(cargar_ledger(destino), ledger_plantilla(PLAN_ID, TITULO, FECHA))

            lint = self._ejecutar("lint", "--ledger", str(destino))
            self.assertEqual(lint.returncode, 1, lint.stdout + lint.stderr)
            self.assertIn("Resultado: BLOQUEADO", lint.stdout)
            for id_ in IDS_EJEMPLO:
                with self.subTest(afirmacion=id_):
                    self.assertIn(f"[BLOQUEANTE] PL-001 {id_}: Estado '[ASIGNAR]'", lint.stdout)
            self.assertIn("Marcadores pendientes ([ASIGNAR]…)", lint.stdout)
            self.assertIn("afirmaciones[EJEMPLO-TN].texto", lint.stdout)

    def test_nunca_sobrescribe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            destino = Path(temp) / "ledger.json"
            destino.write_text('{"ledger": "del operador"}', encoding="utf-8")
            resultado = self._plantilla("--salida", str(destino))
            self.assertEqual(resultado.returncode, 2, resultado.stdout + resultado.stderr)
            self.assertIn("ya existe", resultado.stderr)
            self.assertNotIn("Traceback", resultado.stderr)
            self.assertEqual(destino.read_text(encoding="utf-8"), '{"ledger": "del operador"}')

            resultado = self._plantilla("--salida", temp)
            self.assertEqual(resultado.returncode, 2)
            self.assertIn("directorio", resultado.stderr)

    def test_dentro_del_repositorio_solo_en_zona_ignorada(self) -> None:
        self.assertIsNotNone(plan_audit.motivo_ruta_paquete(REPO / "ledger.json", objeto="el ledger"))
        self.assertIsNone(
            plan_audit.motivo_ruta_paquete(
                REPO / "auditorias" / "asunto-sintetico" / "plan" / "ledger.json", objeto="el ledger"
            )
        )
        destino = REPO / "tests" / "plantilla-sintetica-no-crear" / "ledger.json"
        resultado = self._plantilla("--salida", str(destino))
        if destino.parent.exists():  # no debería ocurrir; limpiar antes de fallar
            for archivo in destino.parent.iterdir():
                archivo.unlink()
            destino.parent.rmdir()
        self.assertEqual(resultado.returncode, 2, resultado.stdout + resultado.stderr)
        self.assertIn("el ledger", resultado.stderr)
        self.assertIn("zona ignorada", resultado.stderr)

    def test_sin_salida_imprime_el_json_y_la_guia_va_a_stderr(self) -> None:
        resultado = self._plantilla()
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(json.loads(resultado.stdout), ledger_plantilla(PLAN_ID, TITULO, FECHA))
        self.assertIn("Siguientes pasos", resultado.stderr)

    def test_entrada_invalida_sale_2_sin_escribir(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            destino = Path(temp) / "ledger.json"
            casos = {
                "fecha": ("plantilla", "--plan-id", PLAN_ID, "--titulo", TITULO, "--fecha", "2026-02-30"),
                "id_marcador": ("plantilla", "--plan-id", "[ASIGNAR]", "--titulo", TITULO, "--fecha", FECHA),
                "salida_vacia": ("plantilla", "--plan-id", PLAN_ID, "--titulo", TITULO, "--fecha", FECHA,
                                 "--salida", " "),
            }
            for nombre, argumentos in casos.items():
                with self.subTest(caso=nombre):
                    extra = () if nombre == "salida_vacia" else ("--salida", str(destino))
                    resultado = self._ejecutar(*argumentos, *extra)
                    self.assertEqual(resultado.returncode, 2, resultado.stdout + resultado.stderr)
                    self.assertIn("Entrada inválida", resultado.stderr)
                    self.assertFalse(destino.exists())

    def test_error_de_escritura_devuelve_2_sin_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            errores = io.StringIO()
            with (
                patch("pathlib.Path.open", side_effect=PermissionError("denegado")),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(errores),
            ):
                codigo = plan_audit.main([
                    "plantilla", "--plan-id", PLAN_ID, "--titulo", TITULO, "--fecha", FECHA,
                    "--salida", str(Path(temp) / "ledger.json"),
                ])
            self.assertEqual(codigo, 2)
            self.assertIn("no se pudo escribir", errores.getvalue())


if __name__ == "__main__":
    unittest.main()
