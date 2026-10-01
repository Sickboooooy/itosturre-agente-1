"""Caracterización del núcleo VVCA (R4a): extracción, resolución de ley y veredicto.

Corre sin dependencias (Python 3.11 del CI): ``OpenNotebook`` carga ChromaDB, el modelo
e5 y PyMuPDF solo al usarlos, y aquí se inyectan una colección y un codificador falsos
(``tests/vvca_falsos.py``). Ningún caso lee el corpus, el modelo ni la jurisprudencia
local del operador.

Las pruebas fijan el comportamiento ACTUAL, incluidos los defectos conocidos. Cada
defecto tiene un ID en ``DEFECTOS_CONOCIDOS`` (PR que lo corrige, descripción y
comportamiento correcto esperado) y su prueba lleva el ID en el nombre: el PR que lo
corrija (R4b, R4c o R4d) cambia esa prueba a sabiendas. No hay ``expectedFailure``.

Las entradas mencionan leyes y artículos reales como TEXTO A AUDITAR, no como citas que se
afirmen. Los registros de tesis son ficticios (0000001…) y sus rubros dicen FICTICIO o
SINTÉTICO; los fragmentos del corpus falso son texto sintético.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scoring_vvca import veredicto_global
from itosturre.audit.evidence import has_exact_article_heading
from tests.vvca_falsos import (
    CodificadorFalso,
    FakeCollection,
    UsoNoEmulado,
    importar_opennotebook,
)

ON = importar_opennotebook()

REPO = Path(__file__).resolve().parent.parent
CFF = ON.LAW_SOURCE_MAP["cff"]
CPEUM = ON.LAW_SOURCE_MAP["cpeum"]
LIVA = ON.LAW_SOURCE_MAP["liva"]
LGV = ON.LAW_SOURCE_MAP["lgv"]
CPF = ON.LAW_SOURCE_MAP["cpf"]
LFDO = ON.LAW_SOURCE_MAP["lfdo"]
MODULOS_PESADOS = ("fitz", "chromadb", "langchain_text_splitters", "sentence_transformers")

# Registro de defectos conocidos. "origen": lista de R4 (crítica externa) o hallazgo de la
# caracterización R4a. Cada ID debe aparecer en el nombre de al menos una prueba.
DEFECTOS_CONOCIDOS = {
    "R4-D01": {
        "pr": "R4b",
        "origen": "lista R4",
        "descripcion": (
            "ARTICLE_RE pierde los sufijos Ter/Quáter y la letra de '4o.-A': "
            "'artículo 247 Ter' se extrae como '247' (en el corpus real se verifica 🟢 "
            "contra el art. 247)."
        ),
        "correcto": "Conservar el sufijo ('247 Ter', '2 Quáter', '4o.-A') y buscar ese precepto.",
    },
    "R4-D02": {
        "pr": "R4b",
        "origen": "lista R4",
        "descripcion": (
            "Las enumeraciones solo extraen el primer artículo ('arts. 14, 16 y 19' → '14'); "
            "extract_article_numbers no reconoce 'arts.'."
        ),
        "correcto": "Una referencia por artículo enumerado, cada una con la ley del grupo.",
    },
    "R4-D03": {
        "pr": "R4b",
        "origen": "lista R4",
        "descripcion": "La ley se resuelve por subcadena: 'Olivares' contiene 'liva' → LIVA.",
        "correcto": "Coincidencia por palabra o abreviatura completa; si no, ley no identificada.",
    },
    "R4-D04": {
        "pr": "R4b",
        "origen": "lista R4",
        "descripcion": "'constitución de la sociedad' resuelve a la CPEUM ('constitución' es alias).",
        "correcto": "'constitución' sin denominación ni abreviatura no identifica la CPEUM.",
    },
    "R4-D05": {
        "pr": "R4b",
        "origen": "hallazgo R4a",
        "descripcion": (
            "La ventana derecha (100 caracteres) tiene prioridad y cruza párrafos: en "
            "'CFF Art. 42.' seguido de un párrafo sobre la Constitución, el art. 42 se "
            "resuelve a la CPEUM; un 'Art. 5' suelto toma la ley del párrafo siguiente."
        ),
        "correcto": "Prevalece la ley adyacente dentro de la misma oración; no cruzar párrafos.",
    },
    "R4-D06": {
        "pr": "R4b",
        "origen": "lista R4",
        "descripcion": (
            "has_exact_article_heading acepta 'Artículo 4o.-A.-' (y '1004-A.-', '29-B.') "
            "como encabezado de '4o' ('1004', '29'); el chunker etiqueta esos fragmentos con "
            "el número base, así que entran como candidatos por metadata y pueden verificar "
            "otro precepto."
        ),
        "correcto": "Tras el número solo cabe el cierre del encabezado, nunca un sufijo de letra.",
    },
    "R4-D07": {
        "pr": "R4d",
        "origen": "lista R4",
        "descripcion": (
            "La detección de registros distingue mayúsculas: 'REGISTRO DIGITAL: 0000001' y "
            "'Registro Digital: 0000002' no se detectan y la tesis desaparece de la auditoría."
        ),
        "correcto": "Detectar sin distinguir mayúsculas; una tesis invocada nunca se omite.",
    },
    "R4-D08": {
        "pr": "R4c",
        "origen": "lista R4",
        "descripcion": "Un fragmento '(Se deroga)' con encabezado exacto sale 🟢 verified.",
        "correcto": "Un precepto derogado nunca es 🟢; alerta de vigencia según la regla de R4c.",
    },
    "R4-D09": {
        "pr": "R4c",
        "origen": "lista R4",
        "descripcion": (
            "source_match es True por construcción en audit(): la consulta filtra por la "
            "fuente esperada y, si el filtro falla, se borra expected_source y la evidencia "
            "de otro ordenamiento sale 🟢 con 'Fuente correcta'. La penalización −15 y la "
            "alerta 'Posible confusión entre ordenamientos' son inalcanzables."
        ),
        "correcto": "Comparar la fuente recuperada con la esperada sin borrarla nunca.",
    },
    "R4-D10": {
        "pr": "R4c",
        "origen": "lista R4",
        "descripcion": (
            "Sin coincidencia confiable en una fuente indexada → 'refuted' y '🔴 … Posible "
            "alucinación' / 'Alucinación detectada', que bloquea el documento aunque solo "
            "acredita que el corpus no lo localizó."
        ),
        "correcto": "'No localizado' es no verificable (🟡) salvo prueba positiva de discrepancia.",
    },
    "R4-D11": {
        "pr": "R4c",
        "origen": "lista R4",
        "descripcion": "El 🟢 dice 'Normativa y jurisprudencia verificadas' aunque no haya tesis.",
        "correcto": "La razón enuncia solo lo verificado (p. ej. 'Normativa verificada; sin tesis').",
    },
    "R4-D12": {
        "pr": "R4c",
        "origen": "hallazgo R4a",
        "descripcion": (
            "Una dimensión sin citas se califica como si hubiera fallado: sin tesis, "
            "semaforo_sjf es 🔴 y el resumen dice 'SJF 0.0 🔴 (0/0 tesis ok)'; sin artículos, "
            "el veredicto es 🟡 'Artículos con verificación insuficiente (RAG: 0.0)' aunque "
            "las tesis estén verificadas."
        ),
        "correcto": "Reportar 'sin citas' en esa dimensión, sin score 0 rojo ni insuficiencia.",
    },
    "R4-D13": {
        "pr": "R4d",
        "origen": "lista R4",
        "descripcion": (
            "El cotejo de rubro es léxico y sin NFD: el mismo rubro sin acentos queda bajo "
            "el 40 % de coincidencia y se bloquea como discrepante (falso 🔴)."
        ),
        "correcto": "Normalizar NFD y mayúsculas antes de comparar (Regla 1 de CLAUDE.md).",
    },
    "R4-D14": {
        "pr": "R4d",
        "origen": "lista R4",
        "descripcion": (
            "El cotejo de rubro ignora palabras de menos de 5 letras: el rubro con el "
            "sentido invertido ('NO ES COMPUTABLE') coincide al 100 % y pasa 🟢."
        ),
        "correcto": "Detectar negaciones o exigir coincidencia literal normalizada del rubro.",
    },
}


def _ref(texto: str) -> dict:
    """La única referencia que ``extract_references`` encuentra en ``texto``."""
    refs = ON.extract_references(texto)
    if len(refs) != 1:
        raise AssertionError(f"se esperaba una referencia y hubo {len(refs)}: {refs}")
    return refs[0]


def _articulo(articulo: str, ley: str, fuente: str | None, raw: str, *,
              fraccion: str = "", inferida: bool = False) -> dict:
    return {
        "type": "article",
        "article": articulo,
        "fraction": fraccion,
        "law": ley,
        "source_file": fuente,
        "law_inferred": inferida,
        "raw": raw,
    }


class RegistroDefectosTests(unittest.TestCase):
    def test_registro_completo_y_cada_defecto_tiene_prueba(self) -> None:
        nombres = {
            nombre
            for clase in (
                ExtraccionTests, ResolucionLeyTests, EvidenciaTests, ConstruccionVvcaTests,
                ConstruccionVvcaTesisTests, AuditoriaTests, VeredictoTests,
            )
            for nombre in dir(clase)
            if nombre.startswith("test_")
        }
        for id_, defecto in DEFECTOS_CONOCIDOS.items():
            with self.subTest(defecto=id_):
                self.assertIn(defecto["pr"], {"R4b", "R4c", "R4d"})
                self.assertIn(defecto["origen"], {"lista R4", "hallazgo R4a"})
                self.assertTrue(defecto["descripcion"] and defecto["correcto"])
                marca = id_.replace("-", "_")
                self.assertTrue(
                    any(marca in nombre for nombre in nombres),
                    f"ninguna prueba lleva {marca} en el nombre",
                )


class ImportacionPerezosaTests(unittest.TestCase):
    """``import OpenNotebook`` no exige paquetes; usarlos sin instalarlos falla claro."""

    def _python(self, codigo: str, *args: str) -> subprocess.CompletedProcess:
        entorno = dict(os.environ, PYTHONIOENCODING="utf-8")
        return subprocess.run(
            [sys.executable, "-c", codigo, *args],
            cwd=REPO,
            env=entorno,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )

    def _bloqueo(self) -> str:
        # Un None en sys.modules hace fallar el import como si el paquete no existiera:
        # reproduce el CI sin dependencias aunque el venv local sí las tenga.
        return "".join(f"sys.modules[{m!r}] = None\n" for m in MODULOS_PESADOS)

    def test_importar_no_carga_dependencias_pesadas(self) -> None:
        resultado = self._python(
            "import sys\n"
            + self._bloqueo()
            + "import OpenNotebook as ON\n"
            "refs = ON.extract_references('Art. 19 CPEUM')\n"
            "print(refs[0]['source_file'])\n"
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), CPEUM)

    def test_importar_sin_bloqueo_tampoco_carga_las_dependencias(self) -> None:
        resultado = self._python(
            "import sys, json\n"
            "import OpenNotebook\n"
            f"print(json.dumps([m for m in {MODULOS_PESADOS!r} if m in sys.modules]))\n"
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(json.loads(resultado.stdout), [])

    def test_dependencia_faltante_da_mensaje_claro(self) -> None:
        with mock.patch.object(ON, "_DEPENDENCIAS_CACHE", None), \
                mock.patch.dict(sys.modules, {m: None for m in MODULOS_PESADOS}):
            with self.assertRaises(ON.DependenciaFaltante) as ctx:
                ON._cargar_dependencias()
        error = ctx.exception
        self.assertIsInstance(error, ModuleNotFoundError)
        self.assertEqual(error.name, "fitz")
        self.assertIn("PyMuPDF", str(error))
        self.assertIn("python -m pip install -r requirements.txt", str(error))
        self.assertIsNone(ON._DEPENDENCIAS_CACHE)

    def test_cli_audit_sin_dependencias_sale_con_codigo_1(self) -> None:
        resultado = self._python(
            "import sys, runpy\n"
            + self._bloqueo()
            + "sys.argv = ['OpenNotebook.py', 'audit', '--text', 'Art. 19 CPEUM']\n"
            "runpy.run_path('OpenNotebook.py', run_name='__main__')\n"
        )
        self.assertEqual(resultado.returncode, 1)
        self.assertEqual(resultado.stdout, "")
        self.assertIn("❌ OpenNotebook necesita el paquete 'PyMuPDF'", resultado.stderr)
        self.assertNotIn("Traceback", resultado.stderr)

    def test_cli_ayuda_no_exige_dependencias(self) -> None:
        resultado = self._python(
            "import sys, runpy\n"
            + self._bloqueo()
            + "sys.argv = ['OpenNotebook.py', '--help']\n"
            "runpy.run_path('OpenNotebook.py', run_name='__main__')\n"
        )
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("OpenNotebook v4.0", resultado.stdout)


class ExtraccionTests(unittest.TestCase):
    """``extract_references``: artículos, ley resuelta y registros de tesis."""

    def test_articulo_con_abreviatura(self) -> None:
        self.assertEqual(
            _ref("Art. 19 CPEUM"),
            _articulo("19", "cpeum", CPEUM, "Art. 19"),
        )

    def test_articulo_con_fraccion_y_denominacion_completa(self) -> None:
        self.assertEqual(
            _ref("El artículo 107 fracción V de la Constitución Política de los Estados "
                 "Unidos Mexicanos establece la procedencia."),
            _articulo("107", "constitución política de los estados unidos", CPEUM,
                      "artículo 107 fracción V", fraccion="V"),
        )

    def test_sufijo_bis_y_grado(self) -> None:
        self.assertEqual(
            _ref("El artículo 209 Bis del Código Fiscal de la Federación se invoca."),
            _articulo("209 Bis", "código fiscal de la federación", CFF, "artículo 209 Bis"),
        )
        self.assertEqual(
            _ref("Art. 259° del Código Penal Federal"),
            _articulo("259", "código penal federal", CPF, "Art. 259°"),
        )

    def test_articulo_sin_ley_queda_desconocido(self) -> None:
        self.assertEqual(
            _ref("Art. 5 establece la regla general."),
            _articulo("5", "desconocido", None, "Art. 5"),
        )

    def test_ley_por_encabezado_lejano_se_marca_inferida(self) -> None:
        texto = (
            "### A. Orden constitucional mexicano (CPEUM)\n\n"
            "Texto de relleno para alejar el encabezado de la cita más de cien caracteres "
            "hacia atrás en el documento de prueba.\n"
            "- Art. 16 — legalidad."
        )
        self.assertEqual(_ref(texto), _articulo("16", "cpeum", CPEUM, "Art. 16", inferida=True))

    def test_encabezado_cercano_resuelve_por_ventana_amplia_sin_inferencia(self) -> None:
        texto = "### A. Orden constitucional mexicano (CPEUM)\n\n- Art. 16 — legalidad."
        self.assertEqual(_ref(texto), _articulo("16", "constitucional", CPEUM, "Art. 16"))

    def test_registro_digital_en_minusculas(self) -> None:
        refs = ON.extract_references(
            "Tesis de prueba con registro digital: 0000003 (registro ficticio)."
        )
        self.assertEqual(refs, [{
            "type": "jurisprudencia",
            "registro": "0000003",
            "raw": "registro digital: 0000003",
            "ctx_invocado": "Tesis de prueba con",
        }])

    def test_R4_D01_sufijos_ter_quater_y_letra_se_pierden(self) -> None:
        casos = {
            "El artículo 247 Ter del Código Penal Federal se invoca.":
                _articulo("247", "código penal federal", CPF, "artículo 247"),
            "El artículo 2 Quáter de la Ley Federal de Delincuencia Organizada se invoca.":
                _articulo("2", "ley federal de delincuencia organizada", LFDO, "artículo 2"),
            "El artículo 4o.-A del Código Fiscal de la Federación se invoca.":
                _articulo("4o", "código fiscal de la federación", CFF, "artículo 4o"),
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(_ref(texto), esperado)

    def test_R4_D02_enumeracion_solo_extrae_el_primero(self) -> None:
        refs = ON.extract_references(
            "Los arts. 14, 16 y 19 de la Constitución Política de los Estados Unidos Mexicanos."
        )
        self.assertEqual(refs, [
            _articulo("14", "constitución política de los estados unidos", CPEUM, "arts. 14"),
        ])
        self.assertEqual(ON.extract_article_numbers("arts. 14, 16 y 19"), [])

    def test_R4_D03_olivares_resuelve_a_liva(self) -> None:
        self.assertEqual(
            _ref("El artículo 10, según el dictamen del perito Olivares, resulta aplicable."),
            _articulo("10", "liva", LIVA, "artículo 10"),
        )

    def test_R4_D04_constitucion_de_la_sociedad_resuelve_a_cpeum(self) -> None:
        self.assertEqual(
            _ref("El artículo 2 regula la constitución de la sociedad mercantil."),
            _articulo("2", "constitución", CPEUM, "artículo 2"),
        )

    def test_R4_D05_ventana_derecha_cruza_parrafos(self) -> None:
        refs = ON.extract_references(
            "Art. 5 establece la regla general.\n\n"
            "CFF Art. 42.\n\n"
            "El artículo 16 de la Constitución Política de los Estados Unidos Mexicanos exige "
            "fundamentación."
        )
        cpeum = "constitución política de los estados unidos"
        self.assertEqual(refs, [
            _articulo("5", "cff", CFF, "Art. 5"),
            _articulo("42", cpeum, CPEUM, "Art. 42"),
            _articulo("16", cpeum, CPEUM, "artículo 16"),
        ])

    def test_R4_D07_registro_en_mayusculas_no_se_detecta(self) -> None:
        refs = ON.extract_references(
            "Tesis de prueba con REGISTRO DIGITAL: 0000001 (registro ficticio).\n"
            "Tesis de prueba con Registro Digital: 0000002 (registro ficticio).\n"
            "Tesis de prueba con Registro: 0000004 (registro ficticio)."
        )
        self.assertEqual([r["registro"] for r in refs], ["0000004"])


class ResolucionLeyTests(unittest.TestCase):
    def test_resolve_law_source_primera_aparicion_y_empate_por_longitud(self) -> None:
        self.assertEqual(
            ON.resolve_law_source(" del Código Fiscal de la Federación"),
            ("código fiscal de la federación", CFF),
        )
        self.assertEqual(ON.resolve_law_source("cff y cpeum"), ("cff", CFF))
        self.assertEqual(ON.resolve_law_source("sin ordenamiento"), (None, None))

    def test_R4_D03_resolve_law_source_por_subcadena(self) -> None:
        self.assertEqual(ON.resolve_law_source("olivares"), ("liva", LIVA))

    def test_R4_D04_resolve_law_source_constitucion_generica(self) -> None:
        self.assertEqual(
            ON.resolve_law_source("la constitución de la sociedad"),
            ("constitución", CPEUM),
        )

    def test_resolve_law_source_backward_toma_la_mas_cercana(self) -> None:
        self.assertEqual(
            ON.resolve_law_source_backward("### A. CPEUM\n... Ley de Amparo ...\n- Art."),
            ("ley de amparo", ON.LAW_SOURCE_MAP["ley de amparo"]),
        )

    def test_resolve_law_alias(self) -> None:
        casos = {
            "cpeum": CPEUM,
            "CPEUM": CPEUM,
            "Ley de Amparo": ON.LAW_SOURCE_MAP["ley de amparo"],
            CFF: CFF,
            "código civil de jalisco": "código civil de jalisco",
            "inexistente": "inexistente",
            "": "",
        }
        for alias, esperado in casos.items():
            with self.subTest(alias=alias):
                self.assertEqual(ON.resolve_law_alias(alias), esperado)

    def test_extract_article_numbers(self) -> None:
        self.assertEqual(ON.extract_article_numbers("artículo 294 y art. 82"), ["294", "82"])
        self.assertEqual(ON.extract_article_numbers("Art.5 y art. 5"), ["5"])
        self.assertEqual(ON.extract_article_numbers("artículo 247 Ter"), ["247"])

    def test_article_candidates(self) -> None:
        casos = {
            "247 Bis": ["247", "247 Bis", "247Bis"],
            "1004-A": ["1004-A"],
            "19": ["19"],
            "4o": ["4o"],
            "  7 ": ["7"],
            "": [],
        }
        for articulo, esperado in casos.items():
            with self.subTest(articulo=articulo):
                self.assertEqual(sorted(ON._article_candidates(articulo)), esperado)


class EvidenciaTests(unittest.TestCase):
    def test_encabezado_exacto_y_remision(self) -> None:
        self.assertTrue(has_exact_article_heading("Artículo 42.- Texto sintético.", "42"))
        self.assertFalse(has_exact_article_heading("conforme al artículo 42, fracción XIII", "42"))
        self.assertFalse(has_exact_article_heading("Artículo 209 Bis.- (Se deroga).", "209"))

    def test_R4_D06_encabezado_con_letra_cuenta_como_el_numero_base(self) -> None:
        self.assertTrue(has_exact_article_heading("Artículo 4o.-A.- Texto sintético.", "4o"))
        self.assertTrue(has_exact_article_heading("Artículo 1004-A.- Texto sintético.", "1004"))
        self.assertTrue(has_exact_article_heading("Artículo 29-B. (Se deroga).", "29"))


class ConstruccionVvcaTests(unittest.TestCase):
    """``build_vvca`` (función pura)."""

    def setUp(self) -> None:
        parche = mock.patch.object(ON, "COSINE_THRESHOLD", 0.25)
        parche.start()
        self.addCleanup(parche.stop)
        self.ref = _articulo("16", "cpeum", CPEUM, "Art. 16")

    def test_metadata_y_encabezado_verificados(self) -> None:
        vvca = ON.build_vvca(self.ref, 0.08, True, CPEUM, "19",
                             metadata_verificado=True, article_heading_verified=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (92, "🟢"))
        self.assertEqual(
            vvca["V_verificacion"],
            "Artículo confirmado por metadata y encabezado exacto en corpus oficial (dist=0.080)",
        )
        self.assertEqual(vvca["V_validacion"], f"Fuente correcta: {CPEUM}")
        self.assertEqual(vvca["A_auditabilidad"], f"Art. 16 · cpeum · pág. 19 · corpus: {CPEUM}")
        self.assertEqual(vvca["explicabilidad"], {
            "coseno": 0.08, "umbral": 0.25, "aprobado_umbral": True,
            "match_metadata": True, "encabezado_articulo": True, "coincide_fuente": True,
            "fuente_encontrada": CPEUM, "fuente_esperada": CPEUM, "ley_inferida": False,
        })

    def test_sin_encabezado_se_capa_a_84(self) -> None:
        vvca = ON.build_vvca(self.ref, 0.05, True, CPEUM, "19", article_heading_verified=False)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (84, "🟡"))
        self.assertTrue(vvca["V_verificacion"].startswith("Evidencia insuficiente"))

    def test_sin_ley_identificada_se_capa_a_84(self) -> None:
        ref = _articulo("5", "desconocido", None, "Art. 5")
        vvca = ON.build_vvca(ref, 0.02, True, CFF, "3", article_heading_verified=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (84, "🟡"))

    def test_metadata_con_distancia_alta_conserva_piso_70(self) -> None:
        vvca = ON.build_vvca(self.ref, 0.60, True, CPEUM, "19",
                             metadata_verificado=True, article_heading_verified=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (70, "🟡"))

    def test_distancia_alta_sin_metadata(self) -> None:
        vvca = ON.build_vvca(self.ref, 0.40, True, CPEUM, "19", article_heading_verified=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (60, "🟡"))
        self.assertEqual(
            vvca["V_verificacion"],
            "Coincidencia débil — posible alucinación (dist=0.400, umbral=0.25)",
        )

    def test_fuente_distinta_penaliza_solo_si_se_le_pide(self) -> None:
        # La función pura sí aplica −15; desde audit() nunca llega False (R4-D09).
        vvca = ON.build_vvca(self.ref, 0.10, False, CFF, "3", article_heading_verified=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (75, "🟡"))
        self.assertEqual(
            vvca["V_validacion"],
            f"Fuente distinta: se encontró en '{CFF}', se esperaba '{CPEUM}'",
        )


def _tesis_ficticia(**cambios) -> dict:
    item = {
        "registro": "0000001",
        "rubro": "RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE",
        "tipo_tesis": "Jurisprudencia",
        "numero_tesis": "CLAVE-FICTICIA J/1",
        "sala": "Órgano ficticio",
        "epoca": "Época ficticia",
        "materia": "Prueba",
        "texto": "Texto ficticio de prueba.",
    }
    item.update(cambios)
    return item


class ConstruccionVvcaTesisTests(unittest.TestCase):
    """``build_vvca_tesis`` (función pura) con registros y rubros ficticios."""

    def _ref(self, invocado: str, registro: str = "0000001") -> dict:
        return {
            "type": "jurisprudencia",
            "registro": registro,
            "raw": f"registro digital: {registro}",
            "ctx_invocado": invocado,
        }

    def test_jurisprudencia_con_rubro_coincidente(self) -> None:
        vvca = ON.build_vvca_tesis(
            self._ref("Se invoca RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE,"),
            _tesis_ficticia(),
            "tesis_ficticias.json",
        )
        self.assertEqual((vvca["score"], vvca["semaforo"]), (95, "🟢"))
        self.assertFalse(vvca["rubro_mismatch"])
        self.assertEqual(vvca["V_validacion"], "Jurisprudencia obligatoria")
        self.assertEqual(vvca["fuerza_vinculante"]["sello"], "[J-TCC]")
        self.assertEqual(vvca["estado_vigencia"], "vigente")
        self.assertEqual(vvca["explicabilidad"]["overlap_rubro"], 1.0)

    def test_tesis_aislada_y_rubro_discrepante(self) -> None:
        aislada = ON.build_vvca_tesis(
            self._ref("RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE"),
            _tesis_ficticia(tipo_tesis="Aislada", numero_tesis="CLAVE-FICTICIA 1"),
            "tesis_ficticias.json",
        )
        self.assertEqual((aislada["score"], aislada["semaforo"]), (72, "🟡"))
        self.assertEqual(aislada["fuerza_vinculante"]["sello"], "[TA]")

        discrepante = ON.build_vvca_tesis(
            self._ref("OTRO ENUNCIADO FICTICIO SOBRE NOTIFICACIONES SIMULADAS"),
            _tesis_ficticia(),
            "tesis_ficticias.json",
        )
        self.assertEqual((discrepante["score"], discrepante["semaforo"]), (0, "🔴"))
        self.assertTrue(discrepante["rubro_mismatch"])
        self.assertTrue(discrepante["V_verificacion"].startswith("⚠️ DISCREPANCIA: Reg. 0000001"))

    def test_estado_de_vigencia_normalizado(self) -> None:
        casos = {"SUPERADA ": "superada", "interrumpida": "interrumpida", "rara": "vigente"}
        for crudo, esperado in casos.items():
            with self.subTest(estado=crudo):
                vvca = ON.build_vvca_tesis(
                    self._ref("RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE"),
                    _tesis_ficticia(estado_vigencia=crudo),
                    "tesis_ficticias.json",
                )
                self.assertEqual(vvca["estado_vigencia"], esperado)

    def test_R4_D13_rubro_sin_acentos_se_bloquea_como_discrepante(self) -> None:
        item = _tesis_ficticia(rubro="PETICIÓN SINTÉTICA. NOTIFICACIÓN Y RESOLUCIÓN FICTICIAS")
        con_acentos = ON.build_vvca_tesis(
            self._ref("PETICIÓN SINTÉTICA. NOTIFICACIÓN Y RESOLUCIÓN FICTICIAS"), item, "f.json"
        )
        sin_acentos = ON.build_vvca_tesis(
            self._ref("PETICION SINTETICA. NOTIFICACION Y RESOLUCION FICTICIAS"), item, "f.json"
        )
        self.assertEqual((con_acentos["score"], con_acentos["rubro_mismatch"]), (95, False))
        self.assertEqual((sin_acentos["score"], sin_acentos["semaforo"]), (0, "🔴"))
        self.assertTrue(sin_acentos["rubro_mismatch"])
        self.assertEqual(sin_acentos["explicabilidad"]["overlap_rubro"], 0.2)

    def test_R4_D14_rubro_con_sentido_invertido_pasa(self) -> None:
        vvca = ON.build_vvca_tesis(
            self._ref("RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO NO ES COMPUTABLE"),
            _tesis_ficticia(),
            "tesis_ficticias.json",
        )
        self.assertEqual((vvca["score"], vvca["semaforo"]), (95, "🟢"))
        self.assertFalse(vvca["rubro_mismatch"])
        self.assertEqual(vvca["explicabilidad"]["overlap_rubro"], 1.0)


class CoberturaCorpusTests(unittest.TestCase):
    def test_fuentes_ausentes_ordenadas_y_sin_duplicados(self) -> None:
        coleccion = FakeCollection()
        coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        refs = [
            {"source_file": CFF}, {"source_file": LGV}, {"source_file": CPEUM},
            {"source_file": LGV}, {"source_file": None}, {},
        ]
        self.assertEqual(ON.check_corpus_coverage(refs, coleccion), sorted([CPEUM, LGV]))
        self.assertIn(
            ("get", {"where": {"source": CFF}, "limit": 1, "include": []}), coleccion.llamadas
        )

    def test_error_de_la_coleccion_cuenta_como_ausente(self) -> None:
        class ColeccionRota(FakeCollection):
            def get(self, **_):
                raise RuntimeError("fallo simulado")

        self.assertEqual(
            ON.check_corpus_coverage([{"source_file": CFF}], ColeccionRota()), [CFF]
        )


class AuditoriaBase(unittest.TestCase):
    """``audit`` con colección y codificador inyectados; el camino por defecto no se toca."""

    def setUp(self) -> None:
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.jurisprudencia = Path(temporal.name) / "jurisprudencia"
        self.jurisprudencia.mkdir()
        parches = [
            mock.patch.object(ON, "COSINE_THRESHOLD", 0.25),
            mock.patch.object(ON, "JURISPRUDENCIA_PATH", str(self.jurisprudencia)),
            mock.patch.object(ON, "CHROMA_PATH", str(Path(temporal.name) / "sin_chroma")),
        ]
        # UsoNoEmulado deriva de BaseException: audit() no puede tragárselo en sus
        # bloques ``except Exception``.
        for nombre in ("get_embedder", "get_collection", "encode_query"):
            parches.append(mock.patch.object(
                ON, nombre,
                side_effect=UsoNoEmulado(f"{nombre} no debe usarse con colección inyectada"),
            ))
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)
        self.coleccion = FakeCollection()
        self.codificador = CodificadorFalso()

    def auditar(self, texto: str, *, coleccion: FakeCollection | None = None, **opciones) -> dict:
        opciones.setdefault("allow_incomplete_corpus", True)
        return ON.audit(
            texto,
            collection=coleccion or self.coleccion,
            encode=self.codificador,
            **opciones,
        )

    def guardar_tesis(self, items: list[dict]) -> None:
        (self.jurisprudencia / "tesis_ficticias.json").write_text(
            json.dumps(items, ensure_ascii=False), encoding="utf-8"
        )

    def estados(self, resultado: dict) -> list[tuple[str, str, str]]:
        return [
            (t["claim"]["reference"], t["verification"]["status"], t["retrieval"]["method"])
            for t in resultado["traceability"]["records"]
        ]


class AuditoriaTests(AuditoriaBase):
    def test_coleccion_vacia(self) -> None:
        self.assertEqual(self.auditar("Art. 19 CPEUM"), {
            "status": "error",
            "message": "La colección está vacía. Ejecuta primero el comando ingest.",
            "alerts": [],
            "retrieved_sources": [],
        })

    def test_corpus_incompleto_se_detiene_sin_force(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        resultado = self.auditar(
            "El artículo 7 de la Ley General de Víctimas reconoce derechos.",
            allow_incomplete_corpus=False,
        )
        self.assertEqual(resultado["status"], "corpus_incomplete")
        self.assertEqual(resultado["missing_sources"], [LGV])
        self.assertEqual(resultado["alerts"], [])
        self.assertEqual(
            self.estados(resultado), [("artículo 7", "not_verifiable", "corpus_coverage_gate")]
        )
        self.assertEqual(self.codificador.llamadas, [])

    def test_corpus_incompleto_con_force_marca_no_verificable(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        resultado = self.auditar("El artículo 7 de la Ley General de Víctimas reconoce derechos.")
        self.assertEqual(resultado["status"], "ok")
        self.assertEqual(resultado["alerts"], [
            f"🟡 NO VERIFICABLE: 'artículo 7' — la ley '{LGV}' no está indexada en el corpus. "
            "NO es alucinación: el corpus no la contiene. Indexar la ley o verificar en "
            "fuente oficial antes de citar."
        ])
        self.assertEqual(
            resultado["corpus_warning"],
            "⚠️  Auditoría ejecutada con corpus parcial. Ley(es) no verificadas por ausencia "
            f"en ChromaDB: {LGV}",
        )
        self.assertEqual(self.estados(resultado), [("artículo 7", "not_verifiable", "corpus_local")])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_R4_D11_R4_D12_articulo_verificado_por_metadata(self) -> None:
        consulta = "Artículo 16 constitución política de los estados unidos"
        eje = self.codificador.eje(consulta)
        self.coleccion.agregar("Artículo 16. Texto sintético de prueba.",
                               {"source": CPEUM, "article": "16", "page": "19"},
                               eje=eje, distancia=0.08)
        # Mismo número en otro ordenamiento y más cercano: el filtro por fuente lo excluye.
        self.coleccion.agregar("Artículo 16.- Texto sintético de otro ordenamiento.",
                               {"source": CFF, "article": "16", "page": "7"},
                               eje=eje, distancia=0.01)
        resultado = self.auditar(
            "El artículo 16 de la Constitución Política de los Estados Unidos Mexicanos "
            "exige fundamentación."
        )

        self.assertEqual(self.codificador.llamadas, [consulta])
        filtro = {"$and": [{"source": CPEUM}, {"article": {"$in": ["16"]}}]}
        self.assertIn(("get", {"where": filtro, "limit": None, "include": ["documents"]}),
                      self.coleccion.llamadas)
        self.assertIn(("query", {"n_results": 3, "where": filtro, "include": None}),
                      self.coleccion.llamadas)

        self.assertEqual(sorted(resultado), [
            "alerts", "alerts_count", "cosine_threshold", "retrieved_sources", "status",
            "summary", "total_references_found", "traceability", "verified", "vvca_summary",
        ])
        self.assertEqual(resultado["alerts"], [])
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["source_file"], CPEUM)
        self.assertEqual(fuente["expected_source"], CPEUM)
        self.assertEqual(fuente["page"], "19")
        self.assertEqual(fuente["relevance_score"], 0.92)
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (92, "🟢"))
        self.assertTrue(fuente["vvca"]["explicabilidad"]["coincide_fuente"])
        self.assertEqual(
            self.estados(resultado),
            [("artículo 16", "verified", "corpus_metadata")],
        )
        self.assertEqual(fuente["trace_id"], resultado["traceability"]["records"][0]["trace_id"])

        resumen = resultado["vvca_summary"]
        self.assertEqual(sorted(resumen), [
            "amarillos", "articulos_ok", "articulos_total", "disclaimer",
            "normativa_no_verificable", "normativa_refutada", "rojos", "score_rag",
            "score_sjf", "semaforo_rag", "semaforo_sjf", "tesis_mismatch",
            "tesis_no_encontradas", "tesis_ok", "tesis_por_fuerza", "tesis_rojas",
            "tesis_superadas", "tesis_total", "verdes", "veredicto",
        ])
        self.assertEqual((resumen["verdes"], resumen["amarillos"], resumen["rojos"]), (1, 0, 0))
        # R4-D11: la razón menciona jurisprudencia aunque no se citó ninguna tesis.
        self.assertEqual(resumen["veredicto"], {
            "apto": True,
            "semaforo": "🟢",
            "razon": "Normativa y jurisprudencia verificadas",
            "accion": "Proceder con revisión de pertinencia procesal por el operador",
        })
        # R4-D12: sin tesis, la dimensión SJF sale 0.0 🔴.
        self.assertEqual((resumen["score_sjf"], resumen["semaforo_sjf"]), (0.0, "🔴"))
        self.assertEqual(
            resultado["summary"],
            "RAG 92.0 🟢 (1 arts) · SJF 0.0 🔴 (0/0 tesis ok) · "
            "Veredicto: 🟢 Normativa y jurisprudencia verificadas",
        )

    def test_R4_D08_articulo_derogado_sale_verde(self) -> None:
        consulta = "Artículo 64 código fiscal de la federación"
        self.coleccion.agregar("Artículo 64.- (Se deroga).",
                               {"source": CFF, "article": "64", "page": "127"},
                               eje=self.codificador.eje(consulta), distancia=0.10)
        resultado = self.auditar("El artículo 64 del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["retrieved_text"], "Artículo 64.- (Se deroga).")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (90, "🟢"))
        self.assertEqual(self.estados(resultado), [("artículo 64", "verified", "corpus_metadata")])
        self.assertEqual(resultado["alerts"], [])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟢")

    def test_R4_D06_articulo_con_letra_verifica_el_numero_base(self) -> None:
        consulta = "Artículo 4o código fiscal de la federación"
        eje = self.codificador.eje(consulta)
        self.coleccion.agregar("Artículo 4o.-A.- Texto sintético del artículo con letra.",
                               {"source": CFF, "article": "4o", "page": "3"},
                               eje=eje, distancia=0.05)
        self.coleccion.agregar("Artículo 4o.- Texto sintético del artículo base.",
                               {"source": CFF, "article": "4o", "page": "2"},
                               eje=eje, distancia=0.10)
        resultado = self.auditar("El artículo 4o. del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertTrue(fuente["retrieved_text"].startswith("Artículo 4o.-A.-"))
        self.assertEqual(fuente["page"], "3")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (95, "🟢"))
        self.assertEqual(self.estados(resultado), [("artículo 4o", "verified", "corpus_metadata")])

    def test_sin_encabezado_exacto_queda_parcial(self) -> None:
        consulta = "Artículo 42 código fiscal de la federación"
        self.coleccion.agregar("[LEY 42]\nconforme al artículo 42, fracción XIII, texto sintético.",
                               {"source": CFF, "article": "42", "page": "105"},
                               eje=self.codificador.eje(consulta), distancia=0.10)
        resultado = self.auditar("El artículo 42 del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (84, "🟡"))
        self.assertEqual(self.estados(resultado), [("artículo 42", "partial", "corpus_semantic")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 EVIDENCIA INSUFICIENTE (score 84): 'artículo 42' — el fragmento recuperado en "
            f"'{CFF}' no contiene el encabezado exacto del artículo 42. Puede ser una remisión "
            "interna; cotejar el precepto auténtico."
        ])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["razon"],
                         "1 cita(s) normativa(s) con evidencia parcial o no verificable")

    def test_metadata_con_distancia_alta_pide_cotejar(self) -> None:
        consulta = "Artículo 42 código fiscal de la federación"
        self.coleccion.agregar("Artículo 42.- Texto sintético.",
                               {"source": CFF, "article": "42", "page": "91"},
                               eje=self.codificador.eje(consulta), distancia=0.40)
        resultado = self.auditar("El artículo 42 del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (70, "🟡"))
        self.assertEqual(self.estados(resultado), [("artículo 42", "partial", "corpus_metadata")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 COTEJAR: 'artículo 42' — artículo confirmado por metadata en '{CFF}', pero el "
            "texto recuperado coincide poco (dist=0.400): puede ser otra porción del artículo. "
            "Cotejar el texto citado contra el precepto."
        ])

    def test_ley_no_identificada(self) -> None:
        consulta = "Artículo 5"
        self.coleccion.agregar("Artículo 5.- Texto sintético.",
                               {"source": CFF, "article": "5", "page": "3"},
                               eje=self.codificador.eje(consulta), distancia=0.10)
        resultado = self.auditar("Art. 5 establece la regla general.")
        self.assertIn(("query", {"n_results": 3, "where": None, "include": None}),
                      self.coleccion.llamadas)
        (fuente,) = resultado["retrieved_sources"]
        self.assertIsNone(fuente["expected_source"])
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (80, "🟡"))
        self.assertEqual(self.estados(resultado), [("Art. 5", "partial", "corpus_semantic")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 LEY NO IDENTIFICADA: 'Art. 5' — coincidencia por número de artículo contra "
            f"'{CFF}'. El contexto no nombró el ordenamiento; verificar que sea la ley correcta "
            "antes de citar."
        ])

    def test_R4_D10_sin_coincidencia_confiable_se_refuta(self) -> None:
        consulta = "Artículo 9999 código fiscal de la federación"
        self.coleccion.agregar("Artículo 1.- Texto sintético.",
                               {"source": CFF, "article": "1", "page": "1"},
                               eje=self.codificador.eje(consulta), distancia=0.40)
        resultado = self.auditar("El artículo 9999 del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (60, "🟡"))
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "refuted", "corpus_semantic")])
        self.assertEqual(resultado["alerts"], [
            "🔴 ALERTA ALTA (score 60): 'artículo 9999' — sin coincidencia confiable "
            "(dist=0.400, umbral=0.25). Posible alucinación. Verificar en fuente oficial."
        ])
        self.assertEqual(resultado["vvca_summary"]["veredicto"], {
            "apto": False,
            "semaforo": "🔴",
            "razon": "1 cita(s) normativa(s) refutada(s) — USO PROCESAL PROHIBIDO",
            "accion": "Corregir o sustituir las citas normativas antes de cualquier uso procesal",
        })

    def test_R4_D10_consulta_sin_vecinos_se_declara_alucinacion(self) -> None:
        coleccion = FakeCollection(vaciar_consultas=True)
        consulta = "Artículo 9999 código fiscal de la federación"
        coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"},
                          eje=self.codificador.eje(consulta), distancia=0.40)
        resultado = self.auditar(
            "El artículo 9999 del Código Fiscal de la Federación se invoca.", coleccion=coleccion
        )
        self.assertEqual(resultado["retrieved_sources"], [])
        self.assertEqual(resultado["alerts"], [
            "🔴 ALERTA CRÍTICA: 'artículo 9999' — no encontrado en el corpus. Alucinación "
            "detectada. Verificar en fuente oficial ANTES de usar."
        ])
        (traza,) = resultado["traceability"]["records"]
        self.assertEqual(traza["verification"]["status"], "refuted")
        self.assertEqual(traza["verification"]["reason"],
                         "No se encontró coincidencia en una fuente que sí está indexada")
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🔴")

    def test_R4_D09_respaldo_sin_filtro_presenta_otra_fuente_como_correcta(self) -> None:
        coleccion = FakeCollection(fallar_consultas_filtradas=True)
        consulta = "Artículo 16 constitución política de los estados unidos"
        eje = self.codificador.eje(consulta)
        coleccion.agregar("Artículo 16. Texto sintético de la Constitución.",
                          {"source": CPEUM, "article": "16", "page": "19"},
                          eje=eje, distancia=0.30)
        coleccion.agregar("Artículo 16.- Texto sintético de otro ordenamiento.",
                          {"source": CFF, "article": "16", "page": "7"},
                          eje=eje, distancia=0.05)
        resultado = self.auditar(
            "El artículo 16 de la Constitución Política de los Estados Unidos Mexicanos "
            "exige fundamentación.",
            coleccion=coleccion,
        )
        # Metadata (falla) → filtro por fuente (falla) → consulta sin filtro.
        self.assertEqual(self.codificador.llamadas, [consulta] * 3)
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["source_file"], CFF)
        self.assertIsNone(fuente["expected_source"])
        explicabilidad = fuente["vvca"]["explicabilidad"]
        self.assertTrue(explicabilidad["coincide_fuente"])
        self.assertTrue(explicabilidad["match_metadata"])
        self.assertEqual(explicabilidad["fuente_esperada"], CPEUM)
        self.assertEqual(fuente["vvca"]["V_validacion"], f"Fuente correcta: {CFF}")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (95, "🟢"))
        self.assertEqual(resultado["alerts"], [])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟢")

    def test_tesis_encontrada_y_no_encontrada(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        self.guardar_tesis([_tesis_ficticia()])
        resultado = self.auditar(
            "Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
            "COMPUTABLE, registro digital: 0000001.\n"
            "También la tesis con registro digital: 0000009 (registro ficticio)."
        )
        self.assertEqual(self.estados(resultado), [
            ("registro digital: 0000001", "verified", "corpus_jurisprudencia"),
            ("registro digital: 0000009", "not_verifiable", "corpus_jurisprudencia"),
        ])
        (tesis,) = resultado["retrieved_sources"]
        self.assertEqual(tesis["source_file"], "tesis_ficticias.json")
        self.assertEqual((tesis["vvca"]["score"], tesis["vvca"]["semaforo"]), (95, "🟢"))
        self.assertEqual(resultado["alerts"], [
            "🟡 NO VERIFICABLE: Registro digital 0000009 no encontrado en el corpus de "
            "jurisprudencia local (no confirmado como falso). Verificar en sjf2.scjn.gob.mx "
            "antes de citar."
        ])
        resumen = resultado["vvca_summary"]
        self.assertEqual(
            (resumen["tesis_total"], resumen["tesis_ok"], resumen["tesis_no_encontradas"],
             resumen["tesis_rojas"], resumen["tesis_por_fuerza"]),
            (2, 1, 1, 1, {"[J-TCC]": 1}),
        )
        self.assertEqual(resumen["veredicto"]["razon"],
                         "1/2 tesis no verificables (ausentes del corpus local — no "
                         "confirmadas como falsas)")

    def test_R4_D12_solo_tesis_verificadas_sale_amarillo_por_rag_cero(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        self.guardar_tesis([_tesis_ficticia()])
        resultado = self.auditar(
            "Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
            "COMPUTABLE, registro digital: 0000001."
        )
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["score_rag"], resumen["semaforo_rag"]), (0.0, "🔴"))
        self.assertEqual((resumen["score_sjf"], resumen["semaforo_sjf"]), (95.0, "🟢"))
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")
        self.assertEqual(resumen["veredicto"]["razon"],
                         "Artículos con verificación insuficiente (RAG: 0.0)")

    def test_tesis_superada_bloquea(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        self.guardar_tesis([_tesis_ficticia(estado_vigencia="superada")])
        resultado = self.auditar(
            "Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
            "COMPUTABLE, registro digital: 0000001."
        )
        resumen = resultado["vvca_summary"]
        self.assertEqual(resumen["tesis_superadas"], 1)
        self.assertEqual(resumen["veredicto"]["semaforo"], "🔴")
        self.assertEqual(resumen["disclaimer"]["nivel"], "🔴")

    def test_R4_D07_tesis_en_mayusculas_no_entra_a_la_auditoria(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        resultado = self.auditar("Tesis de prueba con REGISTRO DIGITAL: 0000001 (registro ficticio).")
        self.assertEqual(resultado["total_references_found"], 0)
        self.assertEqual(resultado["traceability"]["records"], [])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["razon"],
                         "Artículos con verificación insuficiente (RAG: 0.0)")


class AuditoriaCaminoPorDefectoTests(unittest.TestCase):
    """Sin inyección, ``audit`` sigue el camino de siempre: modelo → CHROMA_PATH → colección."""

    def setUp(self) -> None:
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.temporal = Path(temporal.name)
        for nombre, valor in (
            ("COSINE_THRESHOLD", 0.25),
            ("JURISPRUDENCIA_PATH", str(self.temporal / "jurisprudencia")),
        ):
            parche = mock.patch.object(ON, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def test_sin_base_vectorial_carga_el_modelo_y_devuelve_error(self) -> None:
        modelo = object()
        with mock.patch.object(ON, "CHROMA_PATH", str(self.temporal / "no_existe")), \
                mock.patch.object(ON, "get_embedder", return_value=modelo) as embedder, \
                mock.patch.object(ON, "get_collection") as coleccion:
            resultado = ON.audit("Art. 19 CPEUM")
        embedder.assert_called_once_with()
        coleccion.assert_not_called()
        self.assertEqual(resultado, {
            "status": "error",
            "message": "Base vectorial no encontrada. Ejecuta primero: python OpenNotebook.py "
                       "ingest --directory /ruta/pdfs/",
            "alerts": [],
            "retrieved_sources": [],
        })

    def test_con_base_vectorial_usa_la_coleccion_y_el_codificador_por_defecto(self) -> None:
        modelo = object()
        falsa = FakeCollection()
        codificador = CodificadorFalso()
        consulta = "Artículo 19 cpeum"
        falsa.agregar("Artículo 19. Texto sintético.",
                      {"source": CPEUM, "article": "19", "page": "20"},
                      eje=codificador.eje(consulta), distancia=0.05)
        with mock.patch.object(ON, "CHROMA_PATH", str(self.temporal)), \
                mock.patch.object(ON, "get_embedder", return_value=modelo), \
                mock.patch.object(ON, "get_collection", return_value=falsa) as coleccion, \
                mock.patch.object(ON, "encode_query", side_effect=codificador):
            resultado = ON.audit("Art. 19 CPEUM")
        coleccion.assert_called_once_with(modelo)
        self.assertEqual(codificador.llamadas, [consulta])
        self.assertEqual(resultado["status"], "ok")
        self.assertEqual(resultado["retrieved_sources"][0]["vvca"]["score"], 95)


class FakeCollectionTests(unittest.TestCase):
    """El doble falla ruidosamente ante usos que no emula."""

    def test_uso_no_emulado(self) -> None:
        coleccion = FakeCollection()
        with self.assertRaises(UsoNoEmulado):
            coleccion.add(ids=["x"], documents=["y"])
        with self.assertRaises(UsoNoEmulado):
            coleccion.get(where={"$or": [{"a": 1}, {"b": 2}]})
        with self.assertRaises(UsoNoEmulado):
            coleccion.get(where={"article": {"$ne": "1"}})
        with self.assertRaises(UsoNoEmulado):
            coleccion.get(include=["embeddings"])
        with self.assertRaises(TypeError):
            coleccion.get(ids=["x"])
        with self.assertRaises(UsoNoEmulado):
            CodificadorFalso()("consulta sin registrar")

    def test_entradas_que_chromadb_tambien_rechaza(self) -> None:
        coleccion = FakeCollection()
        with self.assertRaises(ValueError):
            coleccion.get(where={"$and": [{"source": "x"}]})
        with self.assertRaises(ValueError):
            coleccion.get(where={"source": "x", "article": "1"})
        with self.assertRaises(ValueError):
            coleccion.query(query_embeddings=[[1.0]], n_results=0)

    def test_exact_article_chunks_con_la_coleccion_falsa(self) -> None:
        coleccion = FakeCollection()
        coleccion.agregar("Artículo 294. Texto sintético.", {"source": CFF, "page": "9"})
        coleccion.agregar("Artículo 2945. Texto sintético.", {"source": CFF, "page": "9"})
        coleccion.agregar("Artículo 294. Otro ordenamiento.", {"source": CPEUM, "page": "1"})
        self.assertEqual(ON.exact_article_chunks(coleccion, CFF, "294"), [
            {"source": CFF, "page": "9", "snippet": "Artículo 294. Texto sintético."},
        ])


class VeredictoTests(unittest.TestCase):
    """``scoring_vvca.veredicto_global``: precedencia de reglas."""

    def test_precedencia(self) -> None:
        casos = [
            ((90, 95, 1, 1, 3), {"tesis_superadas": 1, "normativa_refutada": 1},
             "🔴", "1/3 tesis con rubro discrepante — USO PROCESAL PROHIBIDO"),
            ((90, 95, 0, 1, 3), {"tesis_superadas": 1, "normativa_refutada": 1},
             "🔴", "1/3 tesis con criterio superado o interrumpido — VIGENCIA PERDIDA (falso "
                   "verde: registro y rubro reales, pero el criterio ya no rige)"),
            ((90, 95, 0, 1, 3), {"normativa_refutada": 2},
             "🔴", "2 cita(s) normativa(s) refutada(s) — USO PROCESAL PROHIBIDO"),
            ((90, 95, 0, 1, 3), {"normativa_no_verificable": 1},
             "🟡", "1/3 tesis no verificables (ausentes del corpus local — no confirmadas "
                   "como falsas)"),
            ((90, 95, 0, 0, 3), {"normativa_no_verificable": 1},
             "🟡", "1 cita(s) normativa(s) con evidencia parcial o no verificable"),
            ((69.9, 95, 0, 0, 3), {},
             "🟡", "Artículos con verificación insuficiente (RAG: 69.9)"),
            ((70, 95, 0, 0, 3), {}, "🟢", "Normativa y jurisprudencia verificadas"),
        ]
        for posicionales, nombrados, semaforo, razon in casos:
            with self.subTest(razon=razon):
                veredicto = veredicto_global(*posicionales, **nombrados)
                self.assertEqual((veredicto["semaforo"], veredicto["razon"]), (semaforo, razon))
                self.assertEqual(veredicto["apto"], semaforo == "🟢")

    def test_R4_D11_verde_sin_tesis_menciona_jurisprudencia(self) -> None:
        veredicto = veredicto_global(92.0, 0.0, 0, 0, 0)
        self.assertEqual(veredicto["semaforo"], "🟢")
        self.assertEqual(veredicto["razon"], "Normativa y jurisprudencia verificadas")

    def test_R4_D12_sin_articulos_es_insuficiente(self) -> None:
        veredicto = veredicto_global(0.0, 95.0, 0, 0, 1)
        self.assertEqual(veredicto["semaforo"], "🟡")
        self.assertEqual(veredicto["razon"], "Artículos con verificación insuficiente (RAG: 0.0)")


if __name__ == "__main__":
    unittest.main()
