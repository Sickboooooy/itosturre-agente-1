"""Caracterización del núcleo VVCA (R4a): extracción, resolución de ley y veredicto.

Corre sin dependencias (Python 3.11 del CI): ``OpenNotebook`` carga ChromaDB, el modelo
e5 y PyMuPDF solo al usarlos, y aquí se inyectan una colección y un codificador falsos
(``tests/vvca_falsos.py``). Ningún caso lee el corpus, el modelo ni la jurisprudencia
local del operador.

Las pruebas fijan el comportamiento ACTUAL, incluidos los defectos conocidos. Cada
defecto tiene un ID en ``DEFECTOS_CONOCIDOS`` (PR que lo corrige, descripción y
comportamiento correcto esperado) y su prueba lleva el ID en el nombre: el PR que lo
corrija (R4b, R4c o R4d) cambia esa prueba a sabiendas. No hay ``expectedFailure``.

R4b corrigió R4-D01 a R4-D06 (``"corregido": "R4b"`` en el registro): sus pruebas ya no
fijan el defecto sino el comportamiento correcto. R4-D07 a R4-D14 siguen fijando el
comportamiento actual hasta R4c y R4d.

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
from itosturre.audit.evidence import has_exact_article_heading, has_suffixed_variant_heading
from itosturre.audit.referencias import MAX_RANGO, MOTIVO_SIN_MENCION
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
CNPP = ON.LAW_SOURCE_MAP["cnpp"]
LAMP = ON.LAW_SOURCE_MAP["ley de amparo"]
CPEJ = ON.LAW_SOURCE_MAP["constitución política del estado de jalisco"]
MODULOS_PESADOS = ("fitz", "chromadb", "langchain_text_splitters", "sentence_transformers")

# Registro de defectos conocidos. "origen": lista de R4 (crítica externa) o hallazgo de la
# caracterización R4a. Cada ID debe aparecer en el nombre de al menos una prueba.
# "corregido": PR que ya lo corrigió (su prueba fija el comportamiento correcto). La
# "descripcion" conserva el defecto tal como se caracterizó en R4a, para la historia.
DEFECTOS_CONOCIDOS = {
    "R4-D01": {
        "pr": "R4b",
        "corregido": "R4b",
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
        "corregido": "R4b",
        "origen": "lista R4",
        "descripcion": (
            "Las enumeraciones solo extraen el primer artículo ('arts. 14, 16 y 19' → '14'); "
            "extract_article_numbers no reconoce 'arts.'."
        ),
        "correcto": "Una referencia por artículo enumerado, cada una con la ley del grupo.",
    },
    "R4-D03": {
        "pr": "R4b",
        "corregido": "R4b",
        "origen": "lista R4",
        "descripcion": "La ley se resuelve por subcadena: 'Olivares' contiene 'liva' → LIVA.",
        "correcto": "Coincidencia por palabra o abreviatura completa; si no, ley no identificada.",
    },
    "R4-D04": {
        "pr": "R4b",
        "corregido": "R4b",
        "origen": "lista R4",
        "descripcion": "'constitución de la sociedad' resuelve a la CPEUM ('constitución' es alias).",
        "correcto": "'constitución' sin denominación ni abreviatura no identifica la CPEUM.",
    },
    "R4-D05": {
        "pr": "R4b",
        "corregido": "R4b",
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
        "corregido": "R4b",
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


_SIN_DEFINIR = object()


def _articulo(articulo: str, ley: str, fuente: str | None, raw: str, *,
              fraccion: str = "", inferida: bool = False, metodo=_SIN_DEFINIR,
              motivo: str | None = None, grupo: str | None = None,
              confirmar: bool = False, cobertura: str | None = None) -> dict:
    """Referencia esperada. Por omisión: ley a la derecha (o del contexto previo si es
    inferida), sin motivo, sin cobertura incompleta y con ``group_raw`` igual a ``raw``."""
    if metodo is _SIN_DEFINIR:
        if ley == "desconocido":
            metodo = None
        else:
            metodo = "contexto_previo" if inferida else "adyacente_derecha"
    if ley == "desconocido" and motivo is None:
        motivo = MOTIVO_SIN_MENCION
    return {
        "type": "article",
        "article": articulo,
        "fraction": fraccion,
        "law": ley,
        "source_file": fuente,
        "law_inferred": inferida,
        "raw": raw,
        # Campos añadidos en R4b.
        "law_method": metodo,
        "law_unidentified_reason": motivo,
        "group_raw": raw if grupo is None else grupo,
        "law_requires_confirmation": confirmar,
        "coverage_gap": cobertura,
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
                # Solo el PR asignado puede marcarlo corregido.
                self.assertIn(defecto.get("corregido"), {None, defecto["pr"]})
                marca = id_.replace("-", "_")
                self.assertTrue(
                    any(marca in nombre for nombre in nombres),
                    f"ninguna prueba lleva {marca} en el nombre",
                )

    def test_estado_tras_R4b(self) -> None:
        corregidos = {id_ for id_, d in DEFECTOS_CONOCIDOS.items() if d.get("corregido")}
        self.assertEqual(corregidos, {f"R4-D0{n}" for n in range(1, 7)})


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
        # Ronda 2 de R4b: el encabezado no es solo la denominación de la ley ("Orden
        # constitucional mexicano (CPEUM)") y está en otro párrafo: ley por confirmar (🟡).
        texto = (
            "### A. Orden constitucional mexicano (CPEUM)\n\n"
            "Texto de relleno para alejar el encabezado de la cita más de cien caracteres "
            "hacia atrás en el documento de prueba.\n"
            "- Art. 16 — legalidad."
        )
        self.assertEqual(_ref(texto), _articulo(
            "16", "cpeum", CPEUM, "Art. 16", inferida=True,
            metodo="contexto_previo_otro_parrafo", confirmar=True,
        ))

    def test_R4_D05_encabezado_en_otro_parrafo_se_infiere_por_contexto_previo(self) -> None:
        # Antes de R4b la ventana amplia (±100 caracteres) cruzaba el párrafo y resolvía
        # "constitucional" sin marcarla inferida. Ahora la ley del encabezado llega solo por
        # el contexto previo (sticky-law): la misma CPEUM, por su sigla y marcada inferida.
        # Ronda 2: desde otro párrafo y sin encabezado inequívoco, además pide confirmación.
        texto = "### A. Orden constitucional mexicano (CPEUM)\n\n- Art. 16 — legalidad."
        self.assertEqual(_ref(texto), _articulo(
            "16", "cpeum", CPEUM, "Art. 16", inferida=True,
            metodo="contexto_previo_otro_parrafo", confirmar=True,
        ))
        # Un encabezado que es solo la denominación de la ley sí basta (sin confirmación).
        texto = ("## Constitución Política de los Estados Unidos Mexicanos\n\n"
                 "- Art. 16 — legalidad.")
        self.assertEqual(_ref(texto), _articulo(
            "16", "constitución política de los estados unidos", CPEUM, "Art. 16",
            inferida=True, metodo="encabezado",
        ))

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

    def test_cabeza_de_articulo_no_dentro_de_otra_palabra(self) -> None:
        # R4b endurece la misma expresión: "art" dentro de otra palabra no es una cita.
        self.assertEqual(ON.extract_references("Smart 5 y apart. 3 no son artículos."), [])

    def test_R4_D01_sufijos_ter_quater_y_letra_se_conservan(self) -> None:
        casos = {
            "El artículo 247 Ter del Código Penal Federal se invoca.":
                _articulo("247 Ter", "código penal federal", CPF, "artículo 247 Ter"),
            "El artículo 2 Quáter de la Ley Federal de Delincuencia Organizada se invoca.":
                _articulo("2 Quáter", "ley federal de delincuencia organizada", LFDO,
                          "artículo 2 Quáter"),
            "El artículo 4o.-A del Código Fiscal de la Federación se invoca.":
                _articulo("4o.-A", "código fiscal de la federación", CFF, "artículo 4o.-A"),
            "El artículo 2o. Bis de la LFDO se invoca.":
                _articulo("2o. Bis", "lfdo", LFDO, "artículo 2o. Bis"),
            "El artículo 32-B Quáter del CFF se invoca.":
                _articulo("32-B Quáter", "cff", CFF, "artículo 32-B Quáter"),
            "Art. 17-H Bis CFF.": _articulo("17-H Bis", "cff", CFF, "Art. 17-H Bis"),
            "Art. 5A CFF.": _articulo("5A", "cff", CFF, "Art. 5A"),
            # El punto del ordinal sin sufijo no forma parte de la designación (como antes).
            "El artículo 4o. del Código Fiscal de la Federación se invoca.":
                _articulo("4o", "código fiscal de la federación", CFF, "artículo 4o"),
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(_ref(texto), esperado)
        # ARTICLE_RE conserva su contrato: grupo 1 = designación, grupo 2 = fracción.
        m = ON.ARTICLE_RE.search("artículo 247 Ter, fracción II")
        self.assertEqual((m.group(1), m.group(2)), ("247 Ter", "II"))

    def test_R4_D02_enumeracion_extrae_cada_articulo_con_la_ley_del_grupo(self) -> None:
        cpeum = "constitución política de los estados unidos"
        grupo = "arts. 14, 16 y 19"
        refs = ON.extract_references(
            "Los arts. 14, 16 y 19 de la Constitución Política de los Estados Unidos Mexicanos."
        )
        self.assertEqual(refs, [
            _articulo("14", cpeum, CPEUM, "arts. 14", grupo=grupo),
            _articulo("16", cpeum, CPEUM, "arts. 14, 16", grupo=grupo),
            _articulo("19", cpeum, CPEUM, "arts. 14, 16 y 19", grupo=grupo),
        ])
        self.assertEqual(ON.extract_article_numbers("arts. 14, 16 y 19"), ["14", "16", "19"])

    def test_R4_D02_rangos_y_fraccion_por_articulo(self) -> None:
        refs = ON.extract_references("Arts. 155–157, 164–165, 169 Fr. II CNPP")
        self.assertEqual(
            [(r["article"], r["fraction"], r["raw"]) for r in refs],
            [
                ("155", "", "Arts. 155–157"),
                ("156", "", "Arts. 155–157"),
                ("157", "", "Arts. 155–157"),
                ("164", "", "Arts. 155–157, 164–165"),
                ("165", "", "Arts. 155–157, 164–165"),
                ("169", "II", "Arts. 155–157, 164–165, 169 Fr. II"),
            ],
        )
        self.assertEqual({r["source_file"] for r in refs}, {CNPP})
        self.assertEqual(
            [r["article"] for r in ON.extract_references("Los artículos 467 a 471 del CNPP.")],
            ["467", "468", "469", "470", "471"],
        )
        # Un rango mayor que MAX_RANGO conserva sus extremos y deja constancia de la cobertura
        # incompleta (ronda 2 de R4b: el veredicto no puede ser 🟢).
        refs = ON.extract_references(f"Arts. 1-{MAX_RANGO + 5} CFF.")
        self.assertEqual([r["article"] for r in refs], ["1", str(MAX_RANGO + 5), f"2 a {MAX_RANGO + 4}"])
        self.assertEqual([r["coverage_gap"] is not None for r in refs], [False, False, True])

    def test_R4_D02_numero_con_unidad_no_continua_la_enumeracion(self) -> None:
        refs = ON.extract_references("El artículo 471, 3 días después de la notificación.")
        self.assertEqual([r["article"] for r in refs], ["471"])

    def test_R4_D03_olivares_no_identifica_la_liva(self) -> None:
        self.assertEqual(
            _ref("El artículo 10, según el dictamen del perito Olivares, resulta aplicable."),
            _articulo("10", "desconocido", None, "artículo 10"),
        )
        # La abreviatura completa sí la identifica; "inconstitucional" no es "constitucional".
        self.assertEqual(_ref("El artículo 10 de la LIVA se invoca."),
                         _articulo("10", "liva", LIVA, "artículo 10"))
        self.assertEqual(
            _ref("El acto es inconstitucional conforme al artículo 22."),
            _articulo("22", "desconocido", None, "artículo 22"),
        )

    def test_R4_D04_constitucion_sin_denominacion_no_identifica_la_cpeum(self) -> None:
        self.assertEqual(
            _ref("El artículo 2 regula la constitución de la sociedad mercantil."),
            _articulo("2", "desconocido", None, "artículo 2"),
        )
        generica = _ref("El artículo 14 de la Constitución garantiza la audiencia previa.")
        self.assertIsNone(generica["source_file"])
        self.assertIn("sin denominación", generica["law_unidentified_reason"])
        local = _ref("El artículo 7 de la Constitución local se invoca.")
        self.assertIsNone(local["source_file"])
        self.assertIn("Constitución local", local["law_unidentified_reason"])

    def test_R4_D04_denominaciones_y_precepto_constitucional(self) -> None:
        casos = {
            "El artículo 16 constitucional exige fundamentación.":
                ("constitucional", CPEUM, "adyacente_derecha", False),
            "Los artículos 14 y 16 constitucionales consagran la seguridad jurídica.":
                ("constitucional", CPEUM, "adyacente_derecha", False),
            "El artículo 1o. de la Constitución Federal reconoce los derechos humanos.":
                ("constitución federal", CPEUM, "adyacente_derecha", False),
            "El artículo 4 de la Constitución Política del Estado de Jalisco se invoca.":
                ("constitución política del estado de jalisco", CPEJ, "adyacente_derecha", False),
            "La CPEUM es la norma suprema. El artículo 133 de la Constitución lo establece.":
                ("cpeum", CPEUM, "antecedente", True),
        }
        for texto, (ley, fuente, metodo, inferida) in casos.items():
            with self.subTest(texto=texto):
                refs = ON.extract_references(texto)
                self.assertTrue(refs)
                for ref in refs:
                    self.assertEqual(
                        (ref["law"], ref["source_file"], ref["law_method"], ref["law_inferred"]),
                        (ley, fuente, metodo, inferida),
                    )
        ambigua = _ref("La CPEUM y la Constitución Política del Estado de Jalisco rigen. "
                       "El artículo 4 de la Constitución se invoca.")
        self.assertIsNone(ambigua["source_file"])
        self.assertIn("ambiguo", ambigua["law_unidentified_reason"])

    def test_R4_D05_la_ley_no_cruza_parrafos_y_prevalece_la_adyacente(self) -> None:
        refs = ON.extract_references(
            "Art. 5 establece la regla general.\n\n"
            "CFF Art. 42.\n\n"
            "El artículo 16 de la Constitución Política de los Estados Unidos Mexicanos exige "
            "fundamentación."
        )
        cpeum = "constitución política de los estados unidos"
        self.assertEqual(refs, [
            _articulo("5", "desconocido", None, "Art. 5"),
            _articulo("42", "cff", CFF, "Art. 42", metodo="adyacente_izquierda"),
            _articulo("16", cpeum, CPEUM, "artículo 16"),
        ])

    def test_R4_D05_la_ley_generica_exige_un_antecedente_inequivoco(self) -> None:
        sin_antecedente = _ref("El artículo 5 de la ley establece el plazo.\n\n"
                               "La Ley de Amparo regula el juicio.")
        self.assertIsNone(sin_antecedente["source_file"])
        self.assertIn("antecedente inequívoco", sin_antecedente["law_unidentified_reason"])

        con_antecedente = _ref("La Ley de Amparo regula el juicio.\n\n"
                               "El artículo 5 de la ley establece el plazo.")
        self.assertEqual(
            con_antecedente,
            _articulo("5", "ley de amparo", LAMP, "artículo 5", inferida=True,
                      metodo="antecedente", confirmar=True),   # antecedente en otro párrafo
        )
        ambigua = _ref("La Ley de Amparo y la LISR rigen. El artículo 5 de la ley establece "
                       "el plazo.")
        self.assertIsNone(ambigua["source_file"])
        self.assertIn("ambiguo", ambigua["law_unidentified_reason"])
        # "la ley" no remite a un código.
        incompatible = _ref("El CFF regula la materia. El artículo 5 de la ley fija el plazo.")
        self.assertIsNone(incompatible["source_file"])
        # Un ordenamiento concreto fuera del catálogo no se sustituye por otro.
        concreta = _ref("La Ley de Amparo rige. El artículo 5 de la Ley General de Salud dispone.")
        self.assertIsNone(concreta["source_file"])
        self.assertIn("'Ley General de Salud'", concreta["law_unidentified_reason"])

    def test_R4_D05_ley_a_la_izquierda_en_cadena_y_reclamada(self) -> None:
        self.assertEqual(
            _ref("La Ley de Amparo regula el juicio, y en su artículo 217 dispone la "
                 "obligatoriedad de la jurisprudencia."),
            _articulo("217", "ley de amparo", LAMP, "artículo 217", metodo="posesivo"),
        )
        self.assertEqual(
            [(r["article"], r["source_file"], r["law_method"])
             for r in ON.extract_references("CFF Art. 42 y Art. 43.")],
            [("42", CFF, "adyacente_izquierda"), ("43", CFF, "adyacente_izquierda")],
        )
        # Entre ambos artículos solo median conectores: comparten la ley del segundo.
        self.assertEqual(
            [(r["article"], r["source_file"], r["law_method"])
             for r in ON.extract_references("El artículo 14 y el artículo 16 de la CPEUM.")],
            [("14", CPEUM, "adyacente_derecha"), ("16", CPEUM, "adyacente_derecha")],
        )
        # La CPEUM ya es la ley del artículo 16 y el 5 no está ligado a ella; una ley que solo
        # aparece en la misma oración no se asocia (ronda 2): ley no identificada.
        self.assertEqual(
            [(r["article"], r["law_method"], r["law_inferred"], r["source_file"])
             for r in ON.extract_references(
                 "El artículo 16 de la CPEUM y el artículo 5 establecen reglas.")],
            [("16", "adyacente_derecha", False, CPEUM), ("5", None, False, None)],
        )
        # En una oración anterior del mismo párrafo, el contexto previo sigue como antes.
        self.assertEqual(
            [(r["article"], r["law_method"], r["law_inferred"], r["law_requires_confirmation"])
             for r in ON.extract_references(
                 "El artículo 16 de la CPEUM exige fundamentación. El artículo 5 fija reglas.")],
            [("16", "adyacente_derecha", False, False), ("5", "contexto_previo", True, False)],
        )

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

    def test_R4_D03_resolve_law_source_por_palabra_completa(self) -> None:
        self.assertEqual(ON.resolve_law_source("olivares"), (None, None))
        self.assertEqual(ON.resolve_law_source("el perito Olivares y la LIVA"), ("liva", LIVA))
        # Cualquier blanco entre palabras de la denominación ("Estados\nUnidos").
        self.assertEqual(
            ON.resolve_law_source("de la Constitución Política de los Estados\nUnidos Mexicanos"),
            ("constitución política de los estados unidos", CPEUM),
        )

    def test_R4_D04_resolve_law_source_constitucion_generica(self) -> None:
        self.assertEqual(ON.resolve_law_source("la constitución de la sociedad"), (None, None))
        self.assertEqual(ON.resolve_law_source("el orden constitucional"), (None, None))
        # --law conserva la clave explícita: quien la escribe la pide a propósito.
        self.assertEqual(ON.resolve_law_alias("constitución"), CPEUM)

    def test_resolve_law_source_backward_toma_la_mas_cercana(self) -> None:
        self.assertEqual(
            ON.resolve_law_source_backward("### A. CPEUM\n... Ley de Amparo ...\n- Art."),
            ("ley de amparo", ON.LAW_SOURCE_MAP["ley de amparo"]),
        )
        # Una clave contenida en otra mayor no cuenta aparte.
        self.assertEqual(
            ON.resolve_law_source_backward("la Ley Federal de Delincuencia Organizada"),
            ("ley federal de delincuencia organizada", LFDO),
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
        # R4-D01: el sufijo se conserva (antes "247").
        self.assertEqual(ON.extract_article_numbers("artículo 247 Ter"), ["247 Ter"])

    def test_article_candidates(self) -> None:
        casos = {
            "247 Bis": ["247", "247 Bis", "247Bis"],
            "1004-A": ["1004-A"],
            "19": ["19"],
            "4o": ["4o"],
            "  7 ": ["7"],
            "": [],
            # Etiquetas del chunker para designaciones con sufijo (número base incluido).
            "4o.-A": ["4o", "4o.-A"],
            "2o. Bis": ["2o", "2o. Bis", "2o.Bis"],
            "32-B Quáter": ["32-B", "32-B Quáter", "32-BQuáter"],
        }
        for articulo, esperado in casos.items():
            with self.subTest(articulo=articulo):
                self.assertEqual(sorted(ON._article_candidates(articulo)), esperado)


class EvidenciaTests(unittest.TestCase):
    def test_encabezado_exacto_y_remision(self) -> None:
        self.assertTrue(has_exact_article_heading("Artículo 42.- Texto sintético.", "42"))
        self.assertFalse(has_exact_article_heading("conforme al artículo 42, fracción XIII", "42"))
        self.assertFalse(has_exact_article_heading("Artículo 209 Bis.- (Se deroga).", "209"))

    def test_R4_D06_tras_el_numero_solo_cabe_el_cierre_del_encabezado(self) -> None:
        # Sufijo no pedido: no es el encabezado del número base.
        for texto, articulo in (
            ("Artículo 4o.-A.- Texto sintético.", "4o"),
            ("Artículo 1004-A.- Texto sintético.", "1004"),
            ("Artículo 29-B. (Se deroga).", "29"),
            ("Artículo 2o. Bis.- Texto sintético.", "2o"),
            ("Artículo 209-Bis.- (Se deroga).", "209"),
            ("Artículo 17-H Bis. Texto sintético.", "17-H"),
        ):
            with self.subTest(texto=texto, articulo=articulo):
                self.assertFalse(has_exact_article_heading(texto, articulo))
        # Sufijo pedido: coincide, también con otra grafía del separador o sin acento.
        for texto, articulo in (
            ("Artículo 4o.-A.- Texto sintético.", "4o.-A"),
            ("Artículo 4o.-A.- Texto sintético.", "4o-A"),
            ("Artículo 1004-A.- Texto sintético.", "1004-A"),
            ("Artículo 29-B. (Se deroga).", "29-B"),
            ("Artículo 2o. Bis.- Texto sintético.", "2o. Bis"),
            ("Artículo 32-B Quáter. Texto sintético.", "32-B Quater"),
            ("Artículo 247 Ter.- Texto sintético.", "247 Ter"),
        ):
            with self.subTest(texto=texto, articulo=articulo):
                self.assertTrue(has_exact_article_heading(texto, articulo))
        # Un sufijo pedido no coincide con el artículo base ni con otro sufijo.
        self.assertFalse(has_exact_article_heading("Artículo 247.- Texto sintético.", "247 Ter"))
        self.assertFalse(has_exact_article_heading("Artículo 247 Bis.- Texto.", "247 Ter"))
        self.assertFalse(has_exact_article_heading("Artículo 4o.-B.- Texto.", "4o.-A"))
        # El ordinal se compara como antes; "5o. A ninguna…" sigue siendo el encabezado del 5o.
        self.assertTrue(has_exact_article_heading("Artículo 5o. A ninguna persona podrá.", "5o"))
        self.assertFalse(has_exact_article_heading("Artículo 4o.- Texto.", "4"))
        self.assertTrue(
            has_exact_article_heading("Artículo 4o.-A.- Otro.\nArtículo 4o.- Texto.", "4o")
        )

    def test_R4_D06_sufijo_en_minuscula_sin_confundir_el_cuerpo(self) -> None:
        # Ronda 2: la exclusión del sufijo no distingue mayúsculas…
        self.assertFalse(has_exact_article_heading("Artículo 4o.-a.- Texto", "4o"))
        self.assertFalse(has_exact_article_heading("Artículo 29-b. (Se deroga).", "29"))
        self.assertTrue(has_exact_article_heading("Artículo 4o.-a.- Texto", "4o.-A"))
        # …pero el cuerpo del artículo no es un sufijo.
        for texto in ("Artículo 4o.- a) Los contribuyentes…", "Artículo 4o.-a) Los…",
                      "Artículo 4o.- Las autoridades…", "Artículo 4o.-Las autoridades…"):
            with self.subTest(texto=texto):
                self.assertTrue(has_exact_article_heading(texto, "4o"))
                self.assertFalse(has_suffixed_variant_heading(texto, "4o"))

    def test_R4_D06_variante_con_sufijo(self) -> None:
        self.assertTrue(has_suffixed_variant_heading("Artículo 4o.-A.- Texto.", "4o"))
        self.assertFalse(
            has_suffixed_variant_heading("Artículo 4o.- Texto.\nArtículo 4o.-A.- Otro.", "4o")
        )
        self.assertTrue(has_suffixed_variant_heading("Artículo 247 Bis.- Texto.", "247 Ter"))
        self.assertFalse(has_suffixed_variant_heading("Artículo 247.- Texto.", "247 Ter"))
        self.assertFalse(has_suffixed_variant_heading("Artículo 42.- Texto.", "42"))


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

    def test_R4_D06_articulo_base_no_se_verifica_con_la_variante_con_letra(self) -> None:
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
        self.assertTrue(fuente["retrieved_text"].startswith("Artículo 4o.- "))
        self.assertEqual(fuente["page"], "2")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (90, "🟢"))
        self.assertEqual(self.estados(resultado), [("artículo 4o", "verified", "corpus_metadata")])

    def test_R4_D01_precepto_con_sufijo_se_verifica_con_su_encabezado(self) -> None:
        consulta = "Artículo 4o.-A código fiscal de la federación"
        eje = self.codificador.eje(consulta)
        # Ambos llevan la etiqueta base "4o" (así los etiqueta el chunker real).
        self.coleccion.agregar("Artículo 4o.- Texto sintético del artículo base.",
                               {"source": CFF, "article": "4o", "page": "2"},
                               eje=eje, distancia=0.05)
        self.coleccion.agregar("Artículo 4o.-A.- Texto sintético del artículo con letra.",
                               {"source": CFF, "article": "4o", "page": "3"},
                               eje=eje, distancia=0.10)
        resultado = self.auditar("El artículo 4o.-A del Código Fiscal de la Federación se invoca.")
        self.assertEqual(self.codificador.llamadas, [consulta])
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["article"], "4o.-A")
        self.assertTrue(fuente["retrieved_text"].startswith("Artículo 4o.-A.-"))
        self.assertEqual(fuente["page"], "3")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (90, "🟢"))
        self.assertEqual(self.estados(resultado),
                         [("artículo 4o.-A", "verified", "corpus_metadata")])
        self.assertEqual(resultado["alerts"], [])

    def test_R4_D01_precepto_con_sufijo_ausente_es_no_verificable_nunca_rojo(self) -> None:
        consulta = "Artículo 247 Ter código penal federal"
        eje = self.codificador.eje(consulta)
        # El corpus solo tiene el 247 y el 247 Bis, lejos de la consulta: antes de R4b el
        # "247 Ter" se auditaba como 247; sin la regla de R4b, la distancia lo tacharía de 🔴.
        self.coleccion.agregar("Artículo 247.- Texto sintético.",
                               {"source": CPF, "article": "247", "page": "94"},
                               eje=eje, distancia=0.40)
        self.coleccion.agregar("Artículo 247 Bis.- Texto sintético.",
                               {"source": CPF, "article": "247", "page": "94"},
                               eje=eje, distancia=0.45)
        resultado = self.auditar("El artículo 247 Ter del Código Penal Federal se invoca.")
        self.assertEqual(resultado["retrieved_sources"], [])
        self.assertEqual(self.estados(resultado),
                         [("artículo 247 Ter", "not_verifiable", "corpus_metadata")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 NO VERIFICABLE: 'artículo 247 Ter' — el artículo 247 Ter no aparece con su "
            f"encabezado exacto en la evidencia recuperada de '{CPF}' (el índice agrupa los "
            "preceptos con letra o sufijo bajo el número base '247'). NO es alucinación: el "
            "corpus no permite localizar el precepto. Cotejarlo en la fuente oficial antes de "
            "citar."
        ])
        (traza,) = resultado["traceability"]["records"]
        self.assertEqual(traza["verification"]["semaforo"], "🟡")
        self.assertEqual(traza["source"]["locator"], "página 94 · artículo 247 Ter")
        self.assertTrue(traza["metadata"]["sufijo_solicitado"])
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["verdes"], resumen["amarillos"], resumen["rojos"]), (0, 1, 0))
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")

    def test_R4_D06_solo_variantes_con_sufijo_es_no_verificable_nunca_rojo(self) -> None:
        consulta = "Artículo 4o código fiscal de la federación"
        # Solo la variante "4o.-A", lejos de la consulta. Antes de R4b verificaba el 4o
        # (🟡 COTEJAR por metadata); con solo el arreglo del encabezado sería 🔴.
        self.coleccion.agregar("Artículo 4o.-A.- Texto sintético del artículo con letra.",
                               {"source": CFF, "article": "4o", "page": "3"},
                               eje=self.codificador.eje(consulta), distancia=0.40)
        resultado = self.auditar("El artículo 4o. del Código Fiscal de la Federación se invoca.")
        self.assertEqual(resultado["retrieved_sources"], [])
        self.assertEqual(self.estados(resultado),
                         [("artículo 4o", "not_verifiable", "corpus_metadata")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 NO VERIFICABLE: 'artículo 4o' — en '{CFF}' solo se localizaron variantes con "
            "letra o sufijo del artículo 4o (p. ej. '4o-A' o '4o Bis'), no su encabezado "
            "exacto. NO es alucinación: el corpus no permite localizar el precepto. Cotejarlo "
            "en la fuente oficial antes de citar."
        ])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_R4_D02_enumeracion_audita_cada_articulo(self) -> None:
        consultas = [
            f"Artículo {n} constitución política de los estados unidos" for n in ("14", "16")
        ]
        for numero, consulta in zip(("14", "16"), consultas):
            self.coleccion.agregar(f"Artículo {numero}. Texto sintético.",
                                   {"source": CPEUM, "article": numero, "page": "19"},
                                   eje=self.codificador.eje(consulta), distancia=0.08)
        resultado = self.auditar(
            "Los arts. 14 y 16 de la Constitución Política de los Estados Unidos Mexicanos "
            "se invocan."
        )
        self.assertEqual(self.codificador.llamadas, consultas)
        self.assertEqual(self.estados(resultado), [
            ("arts. 14", "verified", "corpus_metadata"),
            ("arts. 14 y 16", "verified", "corpus_metadata"),
        ])
        self.assertEqual([s["article"] for s in resultado["retrieved_sources"]], ["14", "16"])
        self.assertEqual(
            {s["law_method"] for s in resultado["retrieved_sources"]}, {"adyacente_derecha"}
        )

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

    def test_ley_no_identificada_es_no_verificable_sin_buscar_por_numero(self) -> None:
        # R4b: antes se buscaba el "Art. 5" por número en todo el corpus y se mostraba el de
        # otra ley (🟡 parcial, o 🔴 con distancia alta). Ahora no se adivina la ley: 🟡 NO
        # VERIFICABLE con el motivo, por el mismo camino que la ley no indexada.
        self.coleccion.agregar("Artículo 5.- Texto sintético.",
                               {"source": CFF, "article": "5", "page": "3"})
        resultado = self.auditar("Art. 5 establece la regla general.")
        self.assertEqual(self.codificador.llamadas, [])
        self.assertFalse([c for c in self.coleccion.llamadas if c[0] == "query"])
        self.assertEqual(resultado["retrieved_sources"], [])
        self.assertEqual(self.estados(resultado), [("Art. 5", "not_verifiable", "resolucion_ley")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'Art. 5' (artículo 5) — "
            f"{MOTIVO_SIN_MENCION}. NO es alucinación: sin el ordenamiento no se puede cotejar "
            "el precepto. Precisar la ley junto al artículo o verificar en fuente oficial antes "
            "de citar."
        ])
        (traza,) = resultado["traceability"]["records"]
        self.assertEqual(traza["verification"]["reason"],
                         f"Ley no identificada: {MOTIVO_SIN_MENCION}")
        self.assertEqual(traza["verification"]["semaforo"], "🟡")
        self.assertEqual(traza["metadata"], {
            "ley_no_identificada": True, "motivo": MOTIVO_SIN_MENCION,
            "law": "desconocido", "law_method": None,
        })
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["verdes"], resumen["amarillos"], resumen["rojos"]), (0, 1, 0))
        self.assertEqual(resumen["veredicto"]["razon"],
                         "1 cita(s) normativa(s) con evidencia parcial o no verificable")

    def test_R4_D04_constitucion_generica_reporta_su_motivo(self) -> None:
        self.coleccion.agregar("Artículo 14. Texto sintético.",
                               {"source": CPEUM, "article": "14", "page": "19"})
        resultado = self.auditar("El artículo 14 de la Constitución garantiza la audiencia.")
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith("🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: "
                                          "'artículo 14' (artículo 14) — 'Constitución' sin "
                                          "denominación"))
        self.assertEqual(self.estados(resultado),
                         [("artículo 14", "not_verifiable", "resolucion_ley")])

    def test_alias_sin_fuente_es_no_verificable(self) -> None:
        # "Ejecución Penal" es alias de LAW_ALIASES sin archivo en LAW_SOURCE_MAP.
        self.coleccion.agregar("Artículo 9.- Texto sintético.",
                               {"source": CFF, "article": "9", "page": "3"})
        resultado = self.auditar("Conforme a Ejecución Penal, art. 9 se resuelve.")
        (alerta,) = resultado["alerts"]
        self.assertIn("el ordenamiento 'Ley Nacional de Ejecución Penal' no tiene fuente "
                      "asociada en el corpus", alerta)
        self.assertEqual(self.estados(resultado), [("art. 9", "not_verifiable", "resolucion_ley")])

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


class VinculoSintacticoTests(AuditoriaBase):
    """Ronda 2 de R4b: una ley solo se asocia a un artículo por vínculo sintáctico.

    Cada prueba fija artículo, ley, ``law_method`` y el semáforo de la traza en ``audit()``.
    """

    def _leyes(self, texto: str) -> list[tuple]:
        return [(r["article"], r["law"], r["source_file"], r["law_method"])
                for r in ON.extract_references(texto) if r["type"] == "article"]

    def _semaforos(self, resultado: dict) -> list[str]:
        return [t["verification"]["semaforo"] for t in resultado["traceability"]["records"]]

    def _fragmento(self, consulta: str, texto: str, fuente: str, articulo: str,
                   distancia: float = 0.05, pagina: str = "1") -> None:
        self.coleccion.agregar(texto, {"source": fuente, "article": articulo, "page": pagina},
                               eje=self.codificador.eje(consulta), distancia=distancia)

    # ── Punto 1 ────────────────────────────────────────────────────────────────────────
    def test_p1_ley_a_la_izquierda_prevalece_sobre_mencion_posterior_no_ligada(self) -> None:
        texto = ("La Ley de Amparo, en su artículo 16, establece una regla cuyo alcance debe "
                 "examinarse junto con la CPEUM.")
        self.assertEqual(self._leyes(texto),
                         [("16", "ley de amparo", LAMP, "adyacente_izquierda")])
        self._fragmento("Artículo 16 ley de amparo", "Artículo 16.- Texto sintético.", LAMP, "16")
        resultado = self.auditar(texto)
        self.assertEqual(self.estados(resultado),
                         [("artículo 16", "verified", "corpus_metadata")])
        self.assertEqual(self._semaforos(resultado), ["🟢"])

    def test_p1_conflicto_o_ley_no_ligada_es_no_identificada(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        casos = {
            "La Ley de Amparo, en su artículo 16 de la CPEUM, establece.": "vínculos en conflicto",
            "El artículo 5 establece que conforme a la Ley de Amparo procede.": MOTIVO_SIN_MENCION,
        }
        for texto, motivo in casos.items():
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual((ref["source_file"], ref["law_method"]), (None, None))
                self.assertIn(motivo, ref["law_unidentified_reason"])
                resultado = self.auditar(texto)
                self.assertEqual([e[1:] for e in self.estados(resultado)],
                                 [("not_verifiable", "resolucion_ley")])
                self.assertEqual(self._semaforos(resultado), ["🟡"])

    # ── Punto 2 ────────────────────────────────────────────────────────────────────────
    def test_p2_respectivamente_reparte_las_leyes(self) -> None:
        texto = "Los artículos 14 y 16, de la CPEUM y del CFF, respectivamente."
        self.assertEqual(self._leyes(texto), [
            ("14", "cpeum", CPEUM, "adyacente_derecha"),
            ("16", "cff", CFF, "adyacente_derecha"),
        ])
        self._fragmento("Artículo 14 cpeum", "Artículo 14. Texto sintético.", CPEUM, "14")
        self._fragmento("Artículo 16 cff", "Artículo 16.- Texto sintético.", CFF, "16")
        resultado = self.auditar(texto)
        self.assertEqual(self.estados(resultado), [
            ("artículos 14", "verified", "corpus_metadata"),
            ("artículos 14 y 16", "verified", "corpus_metadata"),
        ])
        self.assertEqual(self._semaforos(resultado), ["🟢", "🟢"])

    def test_p2_varias_leyes_sin_reparto_dejan_el_grupo_sin_ley(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        casos = {
            "Los artículos 14 y 16 de la CPEUM y del CFF.": "sin 'respectivamente'",
            "Los artículos 14, 16 y 19, de la CPEUM y del CFF, respectivamente.":
                "no coincide con el de artículos",
        }
        for texto, motivo in casos.items():
            with self.subTest(texto=texto):
                refs = ON.extract_references(texto)
                self.assertTrue(refs)
                for ref in refs:
                    self.assertEqual((ref["source_file"], ref["law_method"]), (None, None))
                    self.assertIn(motivo, ref["law_unidentified_reason"])
                resultado = self.auditar(texto)
                self.assertEqual(set(self._semaforos(resultado)), {"🟡"})
                self.assertEqual({e[1] for e in self.estados(resultado)}, {"not_verifiable"})

    # ── Punto 3 ────────────────────────────────────────────────────────────────────────
    def test_p3_ordenamiento_concreto_fuera_del_catalogo_bloquea_la_inferencia(self) -> None:
        self.coleccion.agregar("Artículo 5.- Texto sintético.", {"source": LAMP, "article": "5"})
        for texto in (
            "La Ley de Amparo rige.\n\nEl Código de Comercio, en su artículo 5, dispone.",
            "La Ley de Amparo rige.\n\nEl artículo 5 del Código de Comercio dispone.",
        ):
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual((ref["article"], ref["source_file"], ref["law_method"]),
                                 ("5", None, None))
                self.assertTrue(ref["law_unidentified_reason"].startswith(
                    "ordenamiento fuera del catálogo: 'Código de Comercio'"))
                resultado = self.auditar(texto)
                self.assertEqual([e[1:] for e in self.estados(resultado)],
                                 [("not_verifiable", "resolucion_ley")])
                self.assertEqual(self._semaforos(resultado), ["🟡"])
        self.assertEqual(self.codificador.llamadas, [])

    # ── Punto 4 ────────────────────────────────────────────────────────────────────────
    def test_p4_variante_con_letra_minuscula_no_es_el_articulo_base(self) -> None:
        consulta = "Artículo 4o código fiscal de la federación"
        self._fragmento(consulta, "Artículo 4o.-a.- Texto sintético con letra minúscula.",
                        CFF, "4o", 0.05, "3")
        self._fragmento(consulta, "Artículo 4o.- a) Texto sintético del artículo base.",
                        CFF, "4o", 0.10, "2")
        resultado = self.auditar("El artículo 4o. del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["article"], fuente["page"]), ("4o", "2"))
        self.assertEqual(self.estados(resultado), [("artículo 4o", "verified", "corpus_metadata")])
        self.assertEqual(self._semaforos(resultado), ["🟢"])

    # ── Punto 5 ────────────────────────────────────────────────────────────────────────
    def test_p5_ordenamiento_de_otra_entidad_no_identifica_el_de_jalisco(self) -> None:
        self.coleccion.agregar("Artículo 42.- Texto sintético.",
                               {"source": ON.LAW_SOURCE_MAP["cpj"], "article": "42"})
        for texto, nombre in (
            ("Artículo 42 del Código Penal para el Estado de México.",
             "'Código Penal para el Estado de México'"),
            ("El artículo 5 de la Ley de Carrera Judicial del Estado de Jalisco.",
             "'Ley de Carrera Judicial del Estado de Jalisco'"),
        ):
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual((ref["source_file"], ref["law_method"]), (None, None))
                self.assertIn(nombre, ref["law_unidentified_reason"])
                resultado = self.auditar(texto)
                self.assertEqual(self._semaforos(resultado), ["🟡"])
        self.assertEqual(
            self._leyes("El artículo 42 del Código Penal para el Estado Libre y Soberano de "
                        "Jalisco se invoca."),
            [("42", "código penal para el estado libre y soberano de jalisco",
              ON.LAW_SOURCE_MAP["cpj"], "adyacente_derecha")],
        )

    def test_p5_claves_estatales_exigen_la_entidad(self) -> None:
        genericas = {"código penal para el estado", "ley de movilidad y transporte",
                     "reglamento de movilidad", "reglamento orgánico del poder judicial"}
        self.assertFalse(genericas & set(ON.LAW_SOURCE_MAP))
        for clave in ON.LAW_SOURCE_MAP:
            if ("del estado" in clave or "para el estado" in clave) and \
                    "al servicio del estado" not in clave:
                with self.subTest(clave=clave):
                    self.assertIn("jalisco", clave)

    # ── Punto 6 ────────────────────────────────────────────────────────────────────────
    def test_p6_rango_largo_audita_extremos_y_deja_cobertura_incompleta(self) -> None:
        texto = "Arts. 14-40 CPEUM."
        refs = ON.extract_references(texto)
        self.assertEqual([(r["article"], r["source_file"], r["law_method"]) for r in refs], [
            ("14", CPEUM, "adyacente_derecha"), ("40", CPEUM, "adyacente_derecha"),
            ("15 a 39", CPEUM, "adyacente_derecha"),
        ])
        self._fragmento("Artículo 14 cpeum", "Artículo 14. Texto sintético.", CPEUM, "14")
        self._fragmento("Artículo 40 cpeum", "Artículo 40. Texto sintético.", CPEUM, "40")
        resultado = self.auditar(texto)
        self.assertEqual(self.estados(resultado), [
            ("Arts. 14-40", "verified", "corpus_metadata"),
            ("Arts. 14-40", "verified", "corpus_metadata"),
            ("Arts. 14-40", "not_verifiable", "cobertura_extraccion"),
        ])
        self.assertEqual(self._semaforos(resultado), ["🟢", "🟢", "🟡"])
        self.assertEqual(resultado["alerts"], [
            "🟡 COBERTURA INCOMPLETA: 'Arts. 14-40' — rango de 27 artículos (14 a 40): solo se "
            "auditaron los extremos; los 25 intermedios no se auditaron. Auditar esos artículos "
            "por separado o verificarlos en fuente oficial antes de citar."
        ])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    # ── Punto 7 ────────────────────────────────────────────────────────────────────────
    def test_p7_enumeraciones_con_leyes_intercaladas(self) -> None:
        casos = {
            "Los artículos 14 de la CPEUM y 42 del CFF.": [
                ("14", "cpeum", CPEUM, "adyacente_derecha"),
                ("42", "cff", CFF, "adyacente_derecha"),
            ],
            "Se violan los artículos 17 de la Ley de Amparo y 107 constitucional.": [
                ("17", "ley de amparo", LAMP, "adyacente_derecha"),
                ("107", "constitucional", CPEUM, "adyacente_derecha"),
            ],
            "Se invocan los artículos 16 y 19 de la CPEUM, así como 167 del Código Nacional "
            "de Procedimientos Penales.": [
                ("16", "cpeum", CPEUM, "adyacente_derecha"),
                ("19", "cpeum", CPEUM, "adyacente_derecha"),
                ("167", "código nacional de procedimientos penales", CNPP, "adyacente_derecha"),
            ],
            "Los artículos 1o., 14 y 16 constitucionales, y 8o. de la Convención Americana "
            "sobre Derechos Humanos.": [
                ("1o", "constitucional", CPEUM, "adyacente_derecha"),
                ("14", "constitucional", CPEUM, "adyacente_derecha"),
                ("16", "constitucional", CPEUM, "adyacente_derecha"),
                ("8o", "convención americana", ON.LAW_SOURCE_MAP["cadh"], "adyacente_derecha"),
            ],
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(self._leyes(texto), esperado)
        self._fragmento("Artículo 17 ley de amparo", "Artículo 17.- Texto sintético.", LAMP, "17")
        self._fragmento("Artículo 107 constitucional", "Artículo 107. Texto sintético.",
                        CPEUM, "107")
        resultado = self.auditar(
            "Se violan los artículos 17 de la Ley de Amparo y 107 constitucional.")
        self.assertEqual([e[1:] for e in self.estados(resultado)],
                         [("verified", "corpus_metadata"), ("verified", "corpus_metadata")])
        self.assertEqual(self._semaforos(resultado), ["🟢", "🟢"])

    def test_p7_miembro_no_extraido_con_certeza_queda_como_cobertura_incompleta(self) -> None:
        texto = "Los artículos 14 de la CPEUM, al igual que el 42 del CFF."
        refs = ON.extract_references(texto)
        self.assertEqual([(r["article"], r["source_file"], bool(r["coverage_gap"]))
                          for r in refs], [("14", CPEUM, False), ("42", None, True)])
        self._fragmento("Artículo 14 cpeum", "Artículo 14. Texto sintético.", CPEUM, "14")
        resultado = self.auditar(texto)
        self.assertEqual([e[1:] for e in self.estados(resultado)], [
            ("verified", "corpus_metadata"), ("not_verifiable", "cobertura_extraccion"),
        ])
        self.assertEqual(self._semaforos(resultado), ["🟢", "🟡"])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    # ── Punto 8 ────────────────────────────────────────────────────────────────────────
    def test_p8_ley_inferida_de_otro_parrafo_se_limita_a_amarillo(self) -> None:
        texto = "El CFF regula la materia.\n\nEl artículo 42 dispone las facultades."
        (ref,) = ON.extract_references(texto)
        self.assertEqual(
            (ref["law"], ref["source_file"], ref["law_method"], ref["law_requires_confirmation"]),
            ("cff", CFF, "contexto_previo_otro_parrafo", True),
        )
        self._fragmento("Artículo 42 cff", "Artículo 42.- Texto sintético.", CFF, "42", 0.05, "91")
        resultado = self.auditar(texto)
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (84, "🟡"))
        self.assertTrue(fuente["vvca"]["explicabilidad"]["ley_por_confirmar"])
        self.assertEqual(self.estados(resultado), [("artículo 42", "partial", "corpus_metadata")])
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith(
            "🟡 LEY POR CONFIRMAR (score 84): 'artículo 42' — ley inferida de otro párrafo: "
            "confirmar el ordenamiento"))
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_p8_ley_por_confirmar_nunca_es_roja(self) -> None:
        texto = "El CFF regula la materia.\n\nEl artículo 9999 dispone las facultades."
        self._fragmento("Artículo 9999 cff", "Artículo 1.- Texto sintético.", CFF, "1", 0.60)
        resultado = self.auditar(texto)
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "partial", "corpus_semantic")])
        self.assertEqual(self._semaforos(resultado), ["🟡"])
        self.assertEqual(resultado["vvca_summary"]["rojos"], 0)

    def test_p8_encabezado_inequivoco_o_mismo_parrafo_no_piden_confirmacion(self) -> None:
        casos = {
            "## Código Fiscal de la Federación\n\nEl artículo 42 dispone las facultades.":
                ("código fiscal de la federación", "encabezado"),
            "El CFF regula la materia. El artículo 42 dispone las facultades.":
                ("cff", "contexto_previo"),
        }
        for texto, (ley, metodo) in casos.items():
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual((ref["law"], ref["law_method"], ref["law_requires_confirmation"]),
                                 (ley, metodo, False))
                coleccion = FakeCollection()
                coleccion.agregar("Artículo 42.- Texto sintético.",
                                  {"source": CFF, "article": "42", "page": "91"},
                                  eje=self.codificador.eje(f"Artículo 42 {ley}"), distancia=0.05)
                resultado = self.auditar(texto, coleccion=coleccion)
                self.assertEqual(self.estados(resultado),
                                 [("artículo 42", "verified", "corpus_metadata")])
                self.assertEqual(self._semaforos(resultado), ["🟢"])


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
        # R4b: la designación se compara con su sufijo.
        coleccion.agregar("Artículo 4o.-A. Texto sintético con letra.", {"source": CFF, "page": "3"})
        self.assertEqual(ON.exact_article_chunks(coleccion, CFF, "4o"), [])
        self.assertEqual(
            [h["page"] for h in ON.exact_article_chunks(coleccion, CFF, "4o.-A")], ["3"]
        )


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
