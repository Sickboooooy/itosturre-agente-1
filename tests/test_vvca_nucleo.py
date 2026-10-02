"""Caracterización del núcleo VVCA (R4a): extracción, resolución de ley y veredicto.

Corre sin dependencias (Python 3.11 del CI): ``OpenNotebook`` carga ChromaDB, el modelo
e5 y PyMuPDF solo al usarlos, y aquí se inyectan una colección y un codificador falsos
(``tests/vvca_falsos.py``). Ningún caso lee el corpus, el modelo ni la jurisprudencia
local del operador.

Las pruebas fijan el comportamiento ACTUAL, incluidos los defectos conocidos. Cada
defecto tiene un ID en ``DEFECTOS_CONOCIDOS`` (PR que lo corrige, descripción y
comportamiento correcto esperado) y su prueba lleva el ID en el nombre: el PR que lo
corrija (R4b, R4c, R4d o D10) cambia esa prueba a sabiendas. No hay ``expectedFailure``.

R4b corrigió R4-D01 a R4-D06 (``"corregido": "R4b"`` en el registro), R4c, R4-D08,
R4-D09, R4-D11 y R4-D12 (``"corregido": "R4c"``), R4d, R4-D07, R4-D13 y R4-D14
(``"corregido": "R4d"``) y D10, R4-D10 con el criterio del responsable (2-oct-2026, opción
C; ``"corregido": "D10"``): sus pruebas ya no fijan el defecto sino el comportamiento correcto.
Ningún defecto del registro sigue abierto.

Las entradas mencionan leyes y artículos reales como TEXTO A AUDITAR, no como citas que se
afirmen. Los registros de tesis son ficticios (0000001…) y sus rubros dicen FICTICIO o
SINTÉTICO; los fragmentos del corpus falso son texto sintético. Las únicas tesis reales son
las de ``tests/fixtures/evidencia/`` (registros 2006224 y 2032506), con su rubro copiado
literalmente del fixture (la prueba lo comprueba).
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
from itosturre.audit.evidence import (
    DEROGACION_AMBIGUA,
    DEROGADO,
    clasificar_derogacion,
    cotejar_precepto,
    cotejar_unidad,
    cuerpo_suficiente,
    has_exact_article_heading,
    has_suffixed_variant_heading,
    precepto_derogado,
)
from itosturre.audit.jurisprudence import (
    cotejar_rubro,
    diferencias_polaridad,
    extraer_rubro_invocado,
    normalizar_rubro,
    normalizar_vigencia,
)
from itosturre.audit.policy import (
    ALCANCE_JURISPRUDENCIA,
    ALCANCE_NORMATIVA,
    SEMAFORO_SIN_CITAS,
    disclaimer_graduado,
)
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
        "corregido": "R4d",
        "origen": "lista R4",
        "descripcion": (
            "La detección de registros distingue mayúsculas: 'REGISTRO DIGITAL: 0000001' y "
            "'Registro Digital: 0000002' no se detectan y la tesis desaparece de la auditoría."
        ),
        "correcto": "Detectar sin distinguir mayúsculas; una tesis invocada nunca se omite.",
    },
    "R4-D08": {
        "pr": "R4c",
        "corregido": "R4c",
        "origen": "lista R4",
        "descripcion": "Un fragmento '(Se deroga)' con encabezado exacto sale 🟢 verified.",
        "correcto": "Un precepto derogado nunca es 🟢; alerta de vigencia según la regla de R4c.",
    },
    "R4-D09": {
        "pr": "R4c",
        "corregido": "R4c",
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
        # Decisión del responsable jurídico (2-oct-2026): opción C. La corrige su propio PR
        # (rama propuesta fix/vvca-inexistencia-acreditada), no R4c.
        "pr": "D10",
        "corregido": "D10",
        "origen": "lista R4",
        "descripcion": (
            "Sin coincidencia confiable en una fuente indexada → 'refuted' y '🔴 … Posible "
            "alucinación' / 'Alucinación detectada', que bloquea el documento aunque solo "
            "acredita que el corpus no lo localizó."
        ),
        "correcto": "'No localizado' es no verificable (🟡) salvo prueba positiva de discrepancia.",
        "criterio": (
            "Opción C (2-oct-2026): 🔴 solo con prueba positiva de inexistencia en el cuerpo de "
            "la ley indexada (vecinos en el mismo fragmento o número muy superior al último "
            "artículo del cuerpo completo de la versión indexada); sin ella, 🟡 NO LOCALIZADO. "
            "Ronda 2: la prueba se abstiene ante cualquier ambigüedad"
        ),
    },
    "R4-D11": {
        "pr": "R4c",
        "corregido": "R4c",
        "origen": "lista R4",
        "descripcion": "El 🟢 dice 'Normativa y jurisprudencia verificadas' aunque no haya tesis.",
        "correcto": "La razón enuncia solo lo verificado (p. ej. 'Normativa verificada; sin tesis').",
    },
    "R4-D12": {
        "pr": "R4c",
        "corregido": "R4c",
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
        "corregido": "R4d",
        "origen": "lista R4",
        "descripcion": (
            "El cotejo de rubro es léxico y sin NFD: el mismo rubro sin acentos queda bajo "
            "el 40 % de coincidencia y se bloquea como discrepante (falso 🔴)."
        ),
        "correcto": "Normalizar NFD y mayúsculas antes de comparar (Regla 1 de CLAUDE.md).",
    },
    "R4-D14": {
        "pr": "R4d",
        "corregido": "R4d",
        "origen": "lista R4",
        "descripcion": (
            "El cotejo de rubro ignora palabras de menos de 5 letras: el rubro con el "
            "sentido invertido ('NO ES COMPUTABLE') coincide al 100 % y pasa 🟢."
        ),
        "correcto": "Detectar negaciones o exigir coincidencia literal normalizada del rubro.",
        # R4c (ronda 2): mientras D13/D14 siguieran abiertos, un escrito con SOLO tesis no sale
        # 🟢 (scoring_vvca.RETENER_VERDE_SOLO_TESIS). R4d los corrigió, pero la retención se
        # mantiene por adjudicación (2-oct-2026) hasta validar el cotejo con más tesis.
        "condiciona": (
            "R4c retiene el 🟢 de escritos con solo tesis (RETENER_VERDE_SOLO_TESIS); R4d "
            "corrigió D13/D14 y la retención se mantiene hasta validar el cotejo con un corpus "
            "de tesis mayor"
        ),
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
              confirmar: bool = False, cobertura: str | None = None,
              unidad: list | None = None) -> dict:
    """Referencia esperada. Por omisión: ley a la derecha (o del contexto previo si es
    inferida), sin motivo, sin cobertura incompleta, con ``group_raw`` igual a ``raw`` y como
    unidad citada solo la fracción (R4c, ronda 2)."""
    if unidad is None:
        unidad = [{"tipo": "fraccion", "valor": fraccion}] if fraccion else []
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
        # Campo añadido en R4c (ronda 2).
        "unidad_citada": unidad,
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
                self.assertIn(defecto["pr"], {"R4b", "R4c", "R4d", "D10"})
                self.assertIn(defecto["origen"], {"lista R4", "hallazgo R4a"})
                self.assertTrue(defecto["descripcion"] and defecto["correcto"])
                # Solo el PR asignado puede marcarlo corregido.
                self.assertIn(defecto.get("corregido"), {None, defecto["pr"]})
                marca = id_.replace("-", "_")
                self.assertTrue(
                    any(marca in nombre for nombre in nombres),
                    f"ninguna prueba lleva {marca} en el nombre",
                )

    def test_estado_tras_D10(self) -> None:
        corregidos = {id_ for id_, d in DEFECTOS_CONOCIDOS.items() if d.get("corregido")}
        self.assertEqual(corregidos, set(DEFECTOS_CONOCIDOS))
        self.assertEqual(
            {id_ for id_, d in DEFECTOS_CONOCIDOS.items() if d.get("corregido") == "R4d"},
            {"R4-D07", "R4-D13", "R4-D14"},
        )
        # R4-D10: decisión del responsable (2-oct-2026, opción C), que toca la Regla 4 de
        # CLAUDE.md; la corrige su propio PR.
        self.assertEqual(DEFECTOS_CONOCIDOS["R4-D10"]["corregido"], "D10")
        self.assertIn("Opción C", DEFECTOS_CONOCIDOS["R4-D10"]["criterio"])
        # D14 condiciona la retención transitoria del 🟢 de "solo tesis" (ronda 2 de R4c).
        # Adjudicación de R4d (2-oct-2026): cerrados D13 y D14, la retención SE MANTIENE.
        import scoring_vvca
        self.assertIn("RETENER_VERDE_SOLO_TESIS", DEFECTOS_CONOCIDOS["R4-D14"]["condiciona"])
        self.assertTrue(scoring_vvca.RETENER_VERDE_SOLO_TESIS)


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

    def test_R4_D08_unidad_citada_se_extrae_con_el_articulo(self) -> None:
        fr = lambda v: {"tipo": "fraccion", "valor": v}   # noqa: E731
        casos = {
            "El artículo 31, fracción I, del Código Civil Federal se invoca.": [fr("I")],
            "El artículo 107, fracción V, inciso a), de la Ley de Amparo dispone.":
                [fr("V"), {"tipo": "inciso", "valor": "a"}],
            "El artículo 16, primer párrafo, de la CPEUM exige.":
                [{"tipo": "parrafo", "valor": "primer"}],
            "El artículo 19 párrafo 2° de la CPEUM.": [{"tipo": "parrafo", "valor": "2°"}],
            "El artículo 42, fracciones I y III, del CFF.": [fr("I"), fr("III")],
            "El artículo 42, fracc. III, del CFF.": [fr("III")],
            "CFF Art. 42, párrafo segundo.": [{"tipo": "parrafo", "valor": "segundo"}],
            "El artículo 123, apartado B, fracción XIII, de la CPEUM.":
                [{"tipo": "apartado", "valor": "B"}, fr("XIII")],
            "El artículo 16 de la CPEUM exige fundamentación.": [],
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual(ref["unidad_citada"], esperado)
        # Ajuste previo al commit: ordinal con punto antes de la unidad, ordinales en palabra,
        # "décimo primero", "in fine" y unidades que PRECEDEN al artículo.
        constitucion = "la Constitución Política de los Estados Unidos Mexicanos"
        parrafo = lambda v: [{"tipo": "parrafo", "valor": v}]   # noqa: E731
        previas = {
            f"El artículo 1o., párrafo tercero, de {constitucion}.": parrafo("tercero"),
            f"El artículo 1o., tercer párrafo, de {constitucion}.": parrafo("tercer"),
            f"El párrafo tercero del artículo 1o. de {constitucion}.": parrafo("tercero"),
            "El último párrafo del artículo 16 de la CPEUM.": parrafo("último"),
            "El artículo 16, párrafo décimo primero, de la CPEUM.": parrafo("décimo primero"),
            "El artículo 16, in fine, de la CPEUM.": [{"tipo": "otra", "valor": "in fine"}],
            "La fracción II del artículo 31 del Código Civil Federal dispone.": [fr("II")],
            "Las fracciones I y II del artículo 31 del Código Civil Federal.": [fr("I"), fr("II")],
            f"El inciso a) de la fracción III del artículo 107 de {constitucion}.":
                [{"tipo": "inciso", "valor": "a"}, fr("III")],
            "El artículo 16, 2o. párrafo, de la CPEUM.": parrafo("2o."),
            # Unidades de otro contexto o de una ley: no son del artículo.
            "En el 2o. párrafo de la sentencia se cita el artículo 16 de la CPEUM.": [],
            "La fracción II de la Ley de Amparo y el artículo 16 de la CPEUM.": [],
            "El artículo 16 dispone. En el segundo párrafo se dice algo.": [],
        }
        for texto, esperado in previas.items():
            with self.subTest(texto=texto):
                refs = [r for r in ON.extract_references(texto) if r["article"] in ("1o", "16",
                                                                                   "31", "107")]
                self.assertEqual(len(refs), 1, refs)
                self.assertEqual(refs[0]["unidad_citada"], esperado)
        # "2o. párrafo" no abre un artículo 2o.
        self.assertEqual([r["article"] for r in ON.extract_references(
            "El artículo 16, 2o. párrafo, de la CPEUM.")], ["16"])
        # La palabra clave de fracción no vive dentro de otra palabra ("frente a").
        (ref,) = ON.extract_references("El artículo 5 frente a la ley.")
        self.assertEqual((ref["fraction"], ref["unidad_citada"]), ("", []))
        # En una enumeración, el calificador final solo es del último artículo.
        refs = ON.extract_references("El artículo 14 y el artículo 16, último párrafo, de la CPEUM.")
        self.assertEqual([r["unidad_citada"] for r in refs],
                         [[], [{"tipo": "parrafo", "valor": "último"}]])

    def test_R4_D07_registro_en_cualquier_caja_se_detecta(self) -> None:
        # Antes solo se detectaba "Registro: 0000004": las dos primeras tesis desaparecían.
        refs = ON.extract_references(
            "Tesis de prueba con REGISTRO DIGITAL: 0000001 (registro ficticio).\n"
            "Tesis de prueba con Registro Digital: 0000002 (registro ficticio).\n"
            "Tesis de prueba con Registro: 0000004 (registro ficticio)."
        )
        self.assertEqual([r["registro"] for r in refs], ["0000001", "0000002", "0000004"])
        self.assertEqual([r["raw"] for r in refs],
                         ["REGISTRO DIGITAL: 0000001", "Registro Digital: 0000002",
                          "Registro: 0000004"])
        # El contexto de cada registro no cruza el anterior (no hereda su rubro).
        self.assertEqual([r["ctx_invocado"] for r in refs],
                         ["Tesis de prueba con", "(registro ficticio).\nTesis de prueba con",
                          "(registro ficticio).\nTesis de prueba con"])

    def test_R4_D07_otras_formas_del_registro(self) -> None:
        casos = {
            "Registro digital 0000005 (sin dos puntos).": ("0000005", "Registro digital 0000005"),
            "registro IUS 0000006 ficticio.": ("0000006", "registro IUS 0000006"),
            "Tesis ficticia, IUS: 0000007.": ("0000007", "IUS: 0000007"),
            "Tesis ficticia (Reg. 0000008).": ("0000008", "Reg. 0000008"),
            "Tesis ficticia, registro número 0000009.": ("0000009", "registro número 0000009"),
        }
        for texto, (registro, raw) in casos.items():
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual((ref["type"], ref["registro"], ref["raw"]),
                                 ("jurisprudencia", registro, raw))
        # No son registros: "ius" dentro de otra palabra o sin número, ni un número largo.
        for texto in ("El ius puniendi 0000001.", "Marius 0000001.", "Registro 123456789."):
            with self.subTest(texto=texto):
                self.assertEqual(ON.extract_references(texto), [])

    def test_R4_D07_numeros_que_no_son_registros_de_tesis(self) -> None:
        # Ronda 2: un expediente "N/AAAA", un número de 8 dígitos (fecha o folio) y "Registro",
        # "Reg." o "IUS" sin contexto de tesis en el párrafo no son tesis.
        for texto in (
            "En el expediente Reg. 2006224/2026 se dictó el acuerdo.",
            "Registro: 20261002 de la oficialía de partes.",
            "Registro 1234567 de la oficialía de partes.",
            "Inventario del almacén: IUS 1234567, escritorio.",
            "La tesis ficticia del expediente Reg. 2006224/2026.",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(ON.extract_references(texto), [])
        # Con contexto de tesis las mismas cabezas sí cuentan.
        (ref,) = ON.extract_references("Tesis ficticia, IUS 1234567.")
        self.assertEqual(ref["registro"], "1234567")

    def test_R4_D07_enumeraciones_nunca_solo_el_primero(self) -> None:
        for texto in ("Tesis ficticias, registros digitales 0000010 / 0000011.",
                      "Tesis ficticias, registros digitales 0000010/0000011.",
                      "Tesis ficticias, registros digitales 0000010 y/o 0000011.",
                      "Tesis ficticias, registros digitales 0000010 o 0000011."):
            with self.subTest(texto=texto):
                refs = ON.extract_references(texto)
                self.assertEqual([r["registro"] for r in refs], ["0000010", "0000011"])
                self.assertTrue(all(r["registro_en_enumeracion"] for r in refs))
        # Conector no reconocido: el segundo número queda como cobertura incompleta.
        primera, segunda = ON.extract_references(
            "Tesis ficticia con registro digital 0000010 así como 0000011.")
        self.assertEqual((primera["registro"], primera.get("coverage_gap")), ("0000010", None))
        self.assertEqual(segunda["registro"], "0000011")
        self.assertIn("conector no reconocido («así como»)", segunda["coverage_gap"])

    def test_R4_D07_registros_enumerados_no_se_omiten(self) -> None:
        refs = ON.extract_references(
            "Tesis ficticias de rubros «UNO SINTÉTICO DE PRUEBA» y «DOS SINTÉTICO DE "
            "PRUEBA», registros digitales 0000010 y 0000011."
        )
        self.assertEqual([r["registro"] for r in refs], ["0000010", "0000011"])
        # En una enumeración el rubro de cada tesis no se asocia con certeza.
        self.assertEqual({r["ctx_invocado"] for r in refs}, {""})
        self.assertTrue(all(r["registro_en_enumeracion"] for r in refs))


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

    def test_R4_D08_precepto_derogado_solo_tras_su_encabezado(self) -> None:
        # Fórmulas conservadoras justo tras el encabezado exacto del precepto citado.
        for texto, articulo in (
            ("Artículo 64.- (Se deroga).", "64"),
            ("Artículo 2o. (Se deroga).\nArtículo derogado DOF 21-11-1991.", "2o"),
            ("Artículo 209 Bis.- (Se deroga).", "209 Bis"),
            ("Artículo 2o.-C. (Se deroga).", "2o.-C"),
            ("Artículo 9.- Se deroga.", "9"),
            ("ARTÍCULO 136.-\n(Derogado)", "136"),
            ("Artículo 135.- Texto sintético.\nArtículo 136.- (Se deroga).", "136"),
            # Ronda 2: variantes inequívocas (con/sin paréntesis, punto dentro o fuera,
            # mayúsculas, género y número) y ruido de página entre encabezado y fórmula.
            ("Artículo 64.- DEROGADO.", "64"),
            ("Artículo 64.- (Se deroga.)", "64"),
            ("Artículo 64.- Derogado.", "64"),
            ("Artículo 64.- Derogado", "64"),
            ("Artículo 64.- Se deroga", "64"),
            ("Artículo 64.- (Derogada)", "64"),
            ("Artículo 64.- (DEROGADO)", "64"),
            ("Artículo 64.- Se derogan.", "64"),
            ("Artículo 64.- (Derogado).", "64"),
            ("Artículo 85.- (DEROGADO, P.O. 5 DE SEPTIEMBRE DE 2009)", "85"),
            ("Artículo 64.- (Se deroga). Artículo derogado DOF 05-01-1988", "64"),
            ("Artículo 64.-\n\nCÓDIGO FISCAL DE LA FEDERACIÓN\nCÁMARA DE DIPUTADOS DEL H. "
             "CONGRESO DE LA UNIÓN\nSecretaría General\n127 de 380\n(Se deroga).", "64"),
        ):
            with self.subTest(texto=texto, articulo=articulo):
                self.assertTrue(precepto_derogado(texto, articulo))
                self.assertEqual(cotejar_precepto(texto, None, articulo)["derogacion"], DEROGADO)
        for texto, articulo in (
            # Otro artículo del mismo fragmento derogado: el citado sigue vigente.
            ("Artículo 135.- Texto sintético.\nArtículo 136.- (Se deroga).", "135"),
            # Una fracción derogada no deroga el precepto.
            ("Artículo 31.- Se reputa domicilio legal:\nI.\n(Se deroga).\nII. Texto.", "31"),
            # Derogación parcial ("primer párrafo") tampoco.
            ("Artículo 122.- (Se deroga primer párrafo).\nTexto sintético.", "122"),
            # Sin encabezado exacto (remisión) o con sufijo no pedido: no se ubicó el precepto.
            ("conforme al artículo 64 (Se deroga).", "64"),
            ("Artículo 209 Bis.- (Se deroga).", "209"),
            ("Artículo 64.- Texto sintético que se deroga más adelante.", "64"),
            ("Artículo 64.- Quedan derogadas las disposiciones que se opongan.", "64"),
        ):
            with self.subTest(texto=texto, articulo=articulo):
                self.assertFalse(precepto_derogado(texto, articulo))
        # Ronda 2: una fórmula de derogación junto al encabezado que no es inequívoca no se
        # ignora: es ambigua (🟡 en la auditoría).
        for cuerpo in (" (Se deroga primer párrafo).", " Se derogan los artículos 10 y 11.",
                       " (Derogado por decreto sintético)"):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(clasificar_derogacion(cuerpo), DEROGACION_AMBIGUA)
        for cuerpo in (" Texto sintético vigente.", " Quedan derogadas las disposiciones.", ""):
            with self.subTest(cuerpo=cuerpo):
                self.assertIsNone(clasificar_derogacion(cuerpo))

    def test_R4_D08_unidad_citada_se_coteja_en_el_cuerpo(self) -> None:
        cuerpo = (" Se reputa domicilio legal:\nI.\n(Se deroga).\nFracción derogada DOF "
                  "03-06-2019\nII. Del menor de edad, el de su tutor;\nIII.- Texto sintético:\n"
                  "a) Inciso sintético vigente;\nb) (Se deroga).\nIV. (Se deroga primer párrafo).")
        casos = [
            ([{"tipo": "fraccion", "valor": "I"}], "derogada"),
            ([{"tipo": "fraccion", "valor": "1"}], "derogada"),       # arábigo → romano
            ([{"tipo": "fraccion", "valor": "II"}], "cotejada"),
            ([{"tipo": "fraccion", "valor": "III"}, {"tipo": "inciso", "valor": "a"}], "cotejada"),
            ([{"tipo": "fraccion", "valor": "III"}, {"tipo": "inciso", "valor": "b"}], "derogada"),
            ([{"tipo": "fraccion", "valor": "IV"}], "ambigua"),
            ([{"tipo": "fraccion", "valor": "IX"}], "no_cotejada"),   # no está en el texto
            ([{"tipo": "fraccion", "valor": "ente"}], "no_cotejada"),  # no reconocible
            ([{"tipo": "parrafo", "valor": "segundo"}], "no_cotejada"),
            ([{"tipo": "apartado", "valor": "B"}], "no_cotejada"),
        ]
        for unidades, estado in casos:
            with self.subTest(unidades=unidades):
                self.assertEqual(cotejar_unidad(cuerpo, unidades)["estado"], estado)
        # Una marca repetida (p. ej. dos apartados con su propia fracción I) no es inequívoca.
        repetida = " Apartado A:\nI. Texto sintético.\nApartado B:\nI. Otro texto sintético."
        self.assertEqual(
            cotejar_unidad(repetida, [{"tipo": "fraccion", "valor": "I"}])["estado"],
            "no_cotejada",
        )

    def test_R4_D08_cuerpo_suficiente_y_continuacion_del_mismo_precepto(self) -> None:
        self.assertFalse(cuerpo_suficiente(""))
        self.assertFalse(cuerpo_suficiente(" Las"))
        self.assertFalse(cuerpo_suficiente("\nCÓDIGO FISCAL DE LA FEDERACIÓN\n127 de 380\n"))
        self.assertTrue(cuerpo_suficiente(" (Se deroga)."))
        self.assertTrue(cuerpo_suficiente(" Se crea el fondo."))
        meta = {"source": CFF, "article": "64", "chunk_index": "10"}
        # El fragmento termina en el encabezado; la continuación (mismo precepto, índice
        # consecutivo) trae la fórmula de derogación.
        candidatos = [
            ("[LEY 64]\n(Se deroga).\nArtículo 65.- Texto sintético.",
             {"source": CFF, "article": "64", "chunk_index": "11"}),
            ("Artículo 64.- Texto de OTRA ley.", {"source": CPEUM, "article": "64",
                                                  "chunk_index": "11"}),
        ]
        cotejo = cotejar_precepto("Texto sintético.\nArtículo 64.-", meta, "64", (), candidatos)
        self.assertEqual((cotejo["derogacion"], cotejo["completo"], cotejo["continuaciones"]),
                         (DEROGADO, True, 1))
        # Sin continuación localizable: evidencia incompleta (no 🟢).
        cotejo = cotejar_precepto("Texto sintético.\nArtículo 64.-", meta, "64")
        self.assertEqual((cotejo["derogacion"], cotejo["completo"]), (None, False))
        # Un candidato no consecutivo o de otra etiqueta no es continuación.
        lejano = [("(Se deroga).", {"source": CFF, "article": "64", "chunk_index": "13"}),
                  ("(Se deroga).", {"source": CFF, "article": "65", "chunk_index": "11"})]
        cotejo = cotejar_precepto("Artículo 64.-", meta, "64", (), lejano)
        self.assertEqual((cotejo["completo"], cotejo["continuaciones"]), (False, 0))

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

    def test_R4_D10_distancia_alta_sin_metadata_nunca_es_roja(self) -> None:
        # D10 (opción C, 2-oct-2026): antes "Coincidencia débil — posible alucinación" y, con
        # distancia > 0.40, un puntaje bajo 60 (🔴) sin prueba de inexistencia. Ahora 60–84.
        vvca = ON.build_vvca(self.ref, 0.40, True, CPEUM, "19", article_heading_verified=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (60, "🟡"))
        self.assertEqual(
            vvca["V_verificacion"],
            "Coincidencia débil: el texto recuperado coincide poco con la cita "
            "(dist=0.400, umbral=0.25)",
        )
        for encabezado in (True, False, None):
            with self.subTest(encabezado=encabezado):
                vvca = ON.build_vvca(self.ref, 0.90, True, CPEUM, "19",
                                     article_heading_verified=encabezado)
                self.assertEqual((vvca["score"], vvca["semaforo"]), (60, "🟡"))
                self.assertNotIn("alucinaci", vvca["V_verificacion"].lower())
        vvca = ON.build_vvca(self.ref, 0.55, True, CPEUM, "19", article_heading_verified=False,
                             no_localizado=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (60, "🟡"))
        self.assertEqual(
            vvca["V_verificacion"],
            "No localizado: el fragmento no contiene el encabezado exacto del artículo y no se "
            "acredita su inexistencia (dist=0.550, umbral=0.25)",
        )
        self.assertTrue(vvca["explicabilidad"]["no_localizado"])

    def test_R4_D09_fuente_distinta_es_amarilla_en_ambos_sentidos(self) -> None:
        # −15 de vvca_score (desde R4c audit() sí llega con False) y límite 60–84: la
        # evidencia de otro ordenamiento no acredita la cita (nunca 🟢) ni la refuta (nunca 🔴).
        for distancia, esperado in ((0.10, 75), (0.0, 84), (0.60, 60)):
            with self.subTest(distancia=distancia):
                vvca = ON.build_vvca(self.ref, distancia, False, CFF, "3",
                                     article_heading_verified=True)
                self.assertEqual((vvca["score"], vvca["semaforo"]), (esperado, "🟡"))
                self.assertFalse(vvca["explicabilidad"]["coincide_fuente"])
                self.assertTrue(vvca["V_verificacion"].startswith("Evidencia de otro ordenamiento"))
                self.assertEqual(
                    vvca["V_validacion"],
                    f"Fuente distinta: se encontró en '{CFF}', se esperaba '{CPEUM}'",
                )

    def test_R4_D08_derogado_nunca_verde_ni_rojo(self) -> None:
        for distancia, metadata, esperado in ((0.05, True, 84), (0.60, False, 60)):
            with self.subTest(distancia=distancia):
                vvca = ON.build_vvca(self.ref, distancia, True, CPEUM, "19",
                                     metadata_verificado=metadata,
                                     article_heading_verified=True, derogado=True)
                self.assertEqual((vvca["score"], vvca["semaforo"]), (esperado, "🟡"))
                self.assertTrue(vvca["explicabilidad"]["precepto_derogado"])
                self.assertTrue(vvca["V_verificacion"].startswith("Precepto derogado"))
        # Sin derogación la explicabilidad no cambia de forma (campo solo si es True).
        vvca = ON.build_vvca(self.ref, 0.05, True, CPEUM, "19", article_heading_verified=True)
        self.assertNotIn("precepto_derogado", vvca["explicabilidad"])


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
        # R4d: sin dato de vigencia ya no se asume "vigente".
        self.assertEqual(vvca["estado_vigencia"], "no_consultada")
        self.assertEqual(vvca["explicabilidad"]["overlap_rubro"], 1.0)
        self.assertEqual(vvca["cotejo_rubro"], "coincide")

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
        # R4d: un valor desconocido ya no se lee como "vigente" (antes "rara" → "vigente").
        casos = {"SUPERADA ": "superada", "interrumpida": "interrumpida",
                 "Sustituida": "sustituida", "Vigente": "vigente", "rara": "no_reconocida",
                 "": "no_consultada", None: "no_consultada"}
        for crudo, esperado in casos.items():
            with self.subTest(estado=crudo):
                vvca = ON.build_vvca_tesis(
                    self._ref("RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE"),
                    _tesis_ficticia(estado_vigencia=crudo),
                    "tesis_ficticias.json",
                )
                self.assertEqual(vvca["estado_vigencia"], esperado)

    def test_R4_D13_rubro_sin_acentos_coincide(self) -> None:
        # Antes: traslape 0.2 y 🔴 bloqueante (falso rojo) por no normalizar NFD.
        item = _tesis_ficticia(rubro="PETICIÓN SINTÉTICA. NOTIFICACIÓN Y RESOLUCIÓN FICTICIAS")
        for invocado in ("PETICIÓN SINTÉTICA. NOTIFICACIÓN Y RESOLUCIÓN FICTICIAS",
                         "PETICION SINTETICA. NOTIFICACION Y RESOLUCION FICTICIAS",
                         "de rubro: «Petición sintética. Notificación y resolución ficticias.»"):
            with self.subTest(invocado=invocado):
                vvca = ON.build_vvca_tesis(self._ref(invocado), item, "f.json")
                self.assertEqual((vvca["score"], vvca["semaforo"], vvca["rubro_mismatch"]),
                                 (95, "🟢", False))
                self.assertEqual(vvca["cotejo_rubro"], "coincide")
                self.assertEqual(vvca["explicabilidad"]["overlap_rubro"], 1.0)
                # Se muestra el rubro original (con acentos), no la forma normalizada.
                self.assertEqual(vvca["explicabilidad"]["rubro_real"],
                                 "PETICIÓN SINTÉTICA. NOTIFICACIÓN Y RESOLUCIÓN FICTICIAS")

    def test_R4d_tesis_real_del_fixture(self) -> None:
        # Registro, clave, tipo y rubro reales de tests/fixtures/evidencia/sjf_2006224.txt.
        item = {"registro": "2006224", "rubro": RUBRO_2006224, "tipo_tesis": "Jurisprudencia",
                "numero_tesis": "P./J. 20/2014 (10a.)", "sala": "Pleno",
                "epoca": "Décima Época", "materia": "Constitucional"}
        casos = {
            f"de rubro: «{RUBRO_2006224}»": (95, "🟢", "coincide"),
            f"de rubro: «{normalizar_rubro(RUBRO_2006224)}»": (95, "🟢", "coincide"),
            "de rubro: «DERECHOS HUMANOS CONTENIDOS EN LA CONSTITUCIÓN Y EN LOS TRATADOS "
            "INTERNACIONALES. …»": (84, "🟡", "parcial"),
            f"de rubro: «{RUBRO_2006224.replace('CONSTITUYEN EL', 'NO CONSTITUYEN EL')}»":
                (0, "🔴", "invertido"),
            "Se invoca la jurisprudencia P./J. 20/2014 (10a.), con": (84, "🟡",
                                                                      "sin_rubro_invocado"),
        }
        for contexto, esperado in casos.items():
            with self.subTest(contexto=contexto[:50]):
                vvca = ON.build_vvca_tesis(self._ref(contexto, "2006224"), item, "f.json")
                self.assertEqual((vvca["score"], vvca["semaforo"], vvca["cotejo_rubro"]),
                                 esperado)
                self.assertEqual(vvca["fuerza_vinculante"]["sello"], "[J-PLENO]")
                self.assertEqual(vvca["explicabilidad"]["rubro_real"], RUBRO_2006224)

    def test_R4d_ninguna_diferencia_concede_verde(self) -> None:
        # Jurisprudencia (base 95): todo lo que no es igualdad literal queda en 84 o menos.
        for contexto in (
            "RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE EN DÍAS",
            "RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO…",
            "Se invoca la tesis con",
        ):
            with self.subTest(contexto=contexto):
                vvca = ON.build_vvca_tesis(self._ref(contexto), _tesis_ficticia(), "f.json")
                self.assertEqual((vvca["score"], vvca["semaforo"]), (84, "🟡"))
                self.assertFalse(vvca["rubro_mismatch"])
        # Sin rubro en la fuente tampoco.
        vvca = ON.build_vvca_tesis(self._ref(self.RUBRO), _tesis_ficticia(rubro=""), "f.json")
        self.assertEqual((vvca["score"], vvca["cotejo_rubro"]), (84, "sin_rubro_fuente"))
        # Registro en una enumeración: no se le asocia rubro.
        ref = {**self._ref(self.RUBRO), "registro_en_enumeracion": True}
        vvca = ON.build_vvca_tesis(ref, _tesis_ficticia(), "f.json")
        self.assertEqual((vvca["score"], vvca["cotejo_rubro"]), (84, "sin_rubro_invocado"))
        self.assertIn("enumeración", vvca["V_verificacion"])

    RUBRO = "RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE"

    def test_R4_D14_rubro_con_sentido_invertido_se_bloquea(self) -> None:
        # Antes: traslape 1.0 (las palabras de menos de 5 letras no contaban) y 🟢 95.
        vvca = ON.build_vvca_tesis(
            self._ref("RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO NO ES COMPUTABLE"),
            _tesis_ficticia(),
            "tesis_ficticias.json",
        )
        self.assertEqual((vvca["score"], vvca["semaforo"]), (0, "🔴"))
        self.assertTrue(vvca["rubro_mismatch"])
        self.assertEqual(vvca["cotejo_rubro"], "invertido")
        # El traslape sigue siendo total: solo la polaridad distingue los dos rubros.
        self.assertEqual(vvca["explicabilidad"]["overlap_rubro"], 1.0)
        self.assertEqual(vvca["explicabilidad"]["polaridad"],
                         ["negaciones (no, ni, sin, nunca…): 1 en el rubro invocado y 0 en el "
                          "real"])
        self.assertTrue(vvca["V_verificacion"].startswith("⚠️ DISCREPANCIA: Reg. 0000001"))
        # Al revés (el real niega y el invocado no) también.
        invertido = ON.build_vvca_tesis(
            self._ref("RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE"),
            _tesis_ficticia(rubro="RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO NO ES "
                                  "COMPUTABLE"),
            "tesis_ficticias.json",
        )
        self.assertEqual((invertido["score"], invertido["cotejo_rubro"]), (0, "invertido"))


FIXTURES_EVIDENCIA = REPO / "tests" / "fixtures" / "evidencia"
# Rubros REALES copiados literalmente de los fixtures oficiales del SJF (la prueba
# ``test_rubros_reales_copiados_literalmente`` lo comprueba). No se inventa ninguno.
RUBRO_2006224 = (
    "DERECHOS HUMANOS CONTENIDOS EN LA CONSTITUCIÓN Y EN LOS TRATADOS INTERNACIONALES. "
    "CONSTITUYEN EL PARÁMETRO DE CONTROL DE REGULARIDAD CONSTITUCIONAL, PERO CUANDO EN LA "
    "CONSTITUCIÓN HAYA UNA RESTRICCIÓN EXPRESA AL EJERCICIO DE AQUÉLLOS, SE DEBE ESTAR A LO "
    "QUE ESTABLECE EL TEXTO CONSTITUCIONAL."
)
RUBRO_2032506 = (
    "SUSPENSIÓN PROVISIONAL EN AMPARO INDIRECTO. ES IMPROCEDENTE CONTRA EL SISTEMA NORMATIVO "
    "CONFORMADO POR EL ARTÍCULO 162, FRACCIÓN VI, PÁRRAFOS SEGUNDO Y TERCERO, DE LA LEY "
    "ADUANERA, Y LA REGLA 1.4.14. DE LAS REGLAS GENERALES DE COMERCIO EXTERIOR PARA 2026."
)


def _cotejo(contexto: str, real: str, **opciones) -> dict:
    return cotejar_rubro(extraer_rubro_invocado(contexto, **opciones), real)


class CotejoRubroTests(unittest.TestCase):
    """R4d: extracción del rubro invocado y cotejo determinista (funciones puras)."""

    REAL = "RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE"

    def test_rubros_reales_copiados_literalmente(self) -> None:
        for registro, rubro in (("2006224", RUBRO_2006224), ("2032506", RUBRO_2032506)):
            with self.subTest(registro=registro):
                fixture = (FIXTURES_EVIDENCIA / f"sjf_{registro}.txt").read_text(encoding="utf-8")
                self.assertIn(f"Registro digital: {registro}", fixture)
                self.assertIn(rubro, fixture)

    def test_normalizacion_regla_1(self) -> None:
        self.assertEqual(normalizar_rubro("  «PETICIÓN»,  Notificación;\nY RESOLUCIÓN. "),
                         "peticion notificacion y resolucion")
        self.assertEqual(normalizar_rubro("ARTÍCULO 1º."), normalizar_rubro("artículo 1o"))
        self.assertEqual(normalizar_rubro("ARTÍCULO 1°."), normalizar_rubro("artículo 1o"))
        self.assertEqual(normalizar_rubro(RUBRO_2006224),
                         normalizar_rubro(RUBRO_2006224.lower().rstrip(".")))

    def test_solo_la_igualdad_literal_coincide(self) -> None:
        for contexto in (RUBRO_2006224, normalizar_rubro(RUBRO_2006224).upper(),
                         f"de rubro: «{RUBRO_2006224.lower()}»"):
            with self.subTest(contexto=contexto[:30]):
                self.assertEqual(_cotejo(contexto, RUBRO_2006224)["resultado"], "coincide")
        # Mismas palabras en otro orden o con una de más: nunca "coincide" (ningún traslape
        # concede 🟢).
        desordenado = ("CONSTITUYEN EL PARÁMETRO DE CONTROL DE REGULARIDAD CONSTITUCIONAL. "
                       "DERECHOS HUMANOS CONTENIDOS EN LA CONSTITUCIÓN Y EN LOS TRATADOS "
                       "INTERNACIONALES.")
        cotejo = _cotejo(desordenado, RUBRO_2006224)
        self.assertEqual(cotejo["resultado"], "no_literal")
        self.assertEqual(cotejo["traslape"], 1.0)

    def test_truncado_explicito_es_parcial_solo_si_encaja(self) -> None:
        for marca in ("…", "...", "[…]", "[...]", "(…)"):
            with self.subTest(marca=marca):
                contexto = ("de rubro: «DERECHOS HUMANOS CONTENIDOS EN LA CONSTITUCIÓN Y EN LOS "
                            f"TRATADOS INTERNACIONALES. {marca}»")
                self.assertEqual(_cotejo(contexto, RUBRO_2006224)["resultado"], "parcial")
        # Supresión en medio y al inicio.
        self.assertEqual(_cotejo("DERECHOS HUMANOS […] SE DEBE ESTAR A LO QUE ESTABLECE EL "
                                 "TEXTO CONSTITUCIONAL.", RUBRO_2006224)["resultado"], "parcial")
        self.assertEqual(_cotejo("… SE DEBE ESTAR A LO QUE ESTABLECE EL TEXTO CONSTITUCIONAL",
                                 RUBRO_2006224)["resultado"], "parcial")
        # La marca al final no autoriza a omitir el INICIO: "ES COMPUTABLE…" no es el inicio
        # de "…NO ES COMPUTABLE" y la negación omitida invierte el sentido.
        real = "EL PLAZO SINTÉTICO NO ES COMPUTABLE EN DÍAS FICTICIOS"
        cotejo = _cotejo("EL PLAZO SINTÉTICO ES COMPUTABLE…", real)
        self.assertEqual(cotejo["resultado"], "invertido")
        # Sin marca, un tramo literal del rubro no es "parcial": 🟡 no literal.
        self.assertEqual(_cotejo("DERECHOS HUMANOS CONTENIDOS EN LA CONSTITUCIÓN Y EN LOS "
                                 "TRATADOS INTERNACIONALES.", RUBRO_2006224)["resultado"],
                         "no_literal")

    def test_polaridad_lista_cerrada(self) -> None:
        # Negación añadida o suprimida.
        invertido = RUBRO_2006224.replace("CONSTITUYEN EL", "NO CONSTITUYEN EL")
        self.assertEqual(_cotejo(invertido, RUBRO_2006224)["resultado"], "invertido")
        # Antónimo por prefijo: IMPROCEDENTE ↔ PROCEDENTE (rubro real de 2032506).
        procedente = RUBRO_2032506.replace("ES IMPROCEDENTE", "ES PROCEDENTE")
        cotejo = _cotejo(procedente, RUBRO_2032506)
        self.assertEqual(cotejo["resultado"], "invertido")
        self.assertEqual(cotejo["polaridad"], [
            "«improcedente» (antónimo de «procedente»): 0 en el rubro invocado y 1 en el real"
        ])
        inconstitucional = RUBRO_2006224.replace("EL TEXTO CONSTITUCIONAL",
                                                 "EL TEXTO INCONSTITUCIONAL")
        self.assertEqual(_cotejo(inconstitucional, RUBRO_2006224)["resultado"], "invertido")
        # Par simétrico: conceder ↔ negar.
        self.assertEqual(
            diferencias_polaridad("LA SUSPENSIÓN SINTÉTICA DEBE NEGARSE AL QUEJOSO FICTICIO",
                                  "LA SUSPENSIÓN SINTÉTICA DEBE CONCEDERSE AL QUEJOSO FICTICIO"),
            ["«conceder» y «negar»: el rubro invocado dice «negar» y el real «conceder»"],
        )
        # "NO … NI …" frente a "NO … NO …": misma polaridad (cuentan en total).
        self.assertEqual(diferencias_polaridad("NO ES X NI Y FICTICIOS", "NO ES X NO Y FICTICIOS"),
                         [])

    def test_traslape_bajo_es_discrepante_y_cuenta_las_palabras_cortas(self) -> None:
        cotejo = _cotejo("de rubro: «OTRO ENUNCIADO FICTICIO SOBRE NOTIFICACIONES SIMULADAS»",
                         self.REAL)
        self.assertEqual((cotejo["resultado"], cotejo["traslape"]), ("discrepante", 0.2))
        # Las palabras cortas con contenido cuentan (antes solo las de 5+ letras); las vacías
        # ("de", "la", "el") no.
        self.assertEqual(_cotejo("de rubro: «LEY ACTO PENA FICTICIOS»",
                                 "LEY ACTO PENA SINTÉTICOS")["traslape"], 0.75)

    def test_sin_rubro_identificable(self) -> None:
        for contexto in (
            "",
            "Tesis de prueba con",
            # Comillas en minúsculas sin marcador: suele ser el texto de la tesis o de la norma.
            "La Sala dijo que \"el plazo sintético no es computable\" en la tesis con",
            # Datos de publicación en mayúsculas: no son un rubro.
            "Tesis P./J. 20/2014 (10a.), Gaceta, Libro 5, con",
        ):
            with self.subTest(contexto=contexto[:30]):
                self.assertIsNone(extraer_rubro_invocado(contexto))
                self.assertEqual(_cotejo(contexto, self.REAL)["resultado"],
                                 "sin_rubro_invocado")
        self.assertEqual(cotejar_rubro({"texto": self.REAL, "metodo": "marcador",
                                        "truncado": False}, "")["resultado"],
                         "sin_rubro_fuente")

    def test_extraccion_del_rubro_invocado(self) -> None:
        casos = {
            # contexto: (texto extraído, método)
            'la jurisprudencia P./J. 3/2019, de rubro: "PRISIÓN SINTÉTICA. SU\nVALIDEZ '
            'FICTICIA", ': ("PRISIÓN SINTÉTICA. SU VALIDEZ FICTICIA", "marcador"),
            "de título y subtítulo: “Plazo sintético. Es computable en días ficticios.”":
                ("Plazo sintético. Es computable en días ficticios.", "marcador"),
            "RUBRO: PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS. Tesis": (
                "PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS.", "marcador"),
            "de rubro y texto siguientes: «PLAZO SINTÉTICO FICTICIO»": (
                "PLAZO SINTÉTICO FICTICIO", "marcador"),
            "**1.** La tesis **PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS.**, ": (
                "PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS.", "comillas"),
            # La clave y la época que siguen al rubro no forman parte de él.
            "Tesis I.1o.P. J/7 PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS. P./J. 1/2020 "
            "(10a.), ": ("PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS.", "mayusculas"),
            # Solo el párrafo del registro.
            "## III. JURISPRUDENCIA APLICABLE\n\nSe invoca la tesis con": None,
            # La línea de un encabezado no es un rubro, aunque no la separe una línea en blanco;
            # lo que sigue en otra línea sí puede serlo. Una numeración arábiga solo se recorta.
            "III. JURISPRUDENCIA APLICABLE AL CASO\nSirve de apoyo la tesis con": None,
            "## IV. TESIS\nPLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS.\nRegistro": (
                "PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS.", "mayusculas"),
            "1. PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS, ": (
                "PLAZO SINTÉTICO. ES COMPUTABLE EN DÍAS FICTICIOS,", "mayusculas"),
        }
        for contexto, esperado in casos.items():
            with self.subTest(contexto=contexto[:40]):
                invocado = extraer_rubro_invocado(contexto)
                self.assertEqual(invocado and (invocado["texto"], invocado["metodo"]), esperado)

    def test_rubro_pegado_a_la_derecha_del_registro(self) -> None:
        # Formato frecuente: "…, registro digital N, de rubro y texto: «…»". El rubro de la
        # derecha es de ESA tesis y no cuenta como contexto de la siguiente.
        texto = (
            "Sirve de apoyo la jurisprudencia 2a./J. 1/2020, Época ficticia, registro digital "
            "0000001, de rubro y texto: \"RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO NO "
            "ES COMPUTABLE.\" (texto ficticio) y la diversa con registro digital: 0000002."
        )
        primera, segunda = ON.extract_references(texto)
        self.assertEqual(primera["ctx_posterior"],
                         ', de rubro y texto: "RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO '
                         'SINTÉTICO NO ES COMPUTABLE."')
        self.assertNotIn("ctx_posterior", segunda)
        self.assertEqual(segunda["ctx_invocado"], "(texto ficticio) y la diversa con")
        vvca = ON.build_vvca_tesis(primera, _tesis_ficticia(), "f.json")
        self.assertEqual((vvca["cotejo_rubro"], vvca["semaforo"]), ("invertido", "🔴"))
        self.assertEqual(vvca["explicabilidad"]["rubro_invocado_metodo"], "marcador_posterior")
        vvca = ON.build_vvca_tesis(segunda, _tesis_ficticia(registro="0000002"), "f.json")
        self.assertEqual(vvca["cotejo_rubro"], "sin_rubro_invocado")
        # Solo un marcador PEGADO: tras un punto ya es otra oración.
        (ref,) = ON.extract_references("Registro digital: 0000001. De rubro: «OTRO RUBRO "
                                       "FICTICIO DE PRUEBA SINTÉTICA».")
        self.assertNotIn("ctx_posterior", ref)

    def test_ventana_recortada_no_concede_verde_ni_rojo_por_lo_no_visto(self) -> None:
        # Si el contexto se recortó y el rubro empieza en el borde, pudo empezar antes.
        real = "EL PLAZO NO ES COMPUTABLE. SUSPENSIÓN SINTÉTICA EN DÍAS FICTICIOS"
        invocado = extraer_rubro_invocado("SUSPENSIÓN SINTÉTICA EN DÍAS FICTICIOS", recortado=True)
        self.assertTrue(invocado["truncado"])
        self.assertEqual(cotejar_rubro(invocado, real)["resultado"], "parcial")
        self.assertEqual(
            cotejar_rubro(extraer_rubro_invocado("SUSPENSIÓN SINTÉTICA EN DÍAS FICTICIOS"),
                          real)["resultado"],
            "invertido",
        )

    def test_vigencia_nunca_vigente_sin_fuente(self) -> None:
        def estado(item: dict) -> tuple:
            vigencia = normalizar_vigencia(item)
            return vigencia["estado"], vigencia["registrado"], vigencia["conflicto"]

        self.assertEqual(estado({}), ("no_consultada", None, False))
        self.assertEqual(estado({"estado_vigencia": "  "}), ("no_consultada", None, False))
        self.assertEqual(estado({"vigencia": "Superada"}), ("superada", "Superada", False))
        self.assertEqual(estado({"estado_vigencia": "rara"}), ("no_reconocida", "rara", False))
        # Ronda 2: la primera palabra de pérdida cuenta ("superada por contradicción").
        self.assertEqual(estado({"estado_vigencia": "superada por contradicción"}),
                         ("superada", "superada por contradicción", False))
        self.assertEqual(estado({"estado_vigencia": "no superada"}),
                         ("no_reconocida", "no superada", False))

    def test_vigencia_perdida_en_cualquier_campo_prevalece(self) -> None:
        # Ronda 2 (punto 5): antes {"estado_vigencia": "no_consultada", "vigencia":
        # "superada"} no bloqueaba (solo se leía el primer campo con valor).
        casos = [
            ({"estado_vigencia": "no_consultada", "vigencia": "superada"},
             ("superada", "superada", False)),
            ({"estado_vigencia": "rara", "vigencia": "interrumpida"},
             ("interrumpida", "interrumpida", True)),
            ({"estado_vigencia": "vigente", "vigencia": "sustituida"},
             ("sustituida", "sustituida", True)),
            ({"estado_vigencia": "vigente", "vigencia": "rara"},
             ("en_conflicto", "estado_vigencia=vigente; vigencia=rara", True)),
            ({"estado_vigencia": "vigente", "vigencia": "Vigente"}, ("vigente", "vigente", False)),
        ]
        for item, esperado in casos:
            with self.subTest(item=item):
                vigencia = normalizar_vigencia(item)
                self.assertEqual((vigencia["estado"], vigencia["registrado"],
                                  vigencia["conflicto"]), esperado)

    def test_promover_tesis_no_escribe_vigente_sin_fuente(self) -> None:
        from scripts.promover_tesis import item_corpus

        base = {"registro": "0000001", "rubro": self.REAL}
        self.assertEqual(item_corpus(base)["estado_vigencia"], "no_consultada")
        self.assertEqual(item_corpus({**base, "estado_vigencia": "Vigente"})["estado_vigencia"],
                         "vigente")
        self.assertEqual(item_corpus({**base, "estado_vigencia": "SUPERADA"})["estado_vigencia"],
                         "superada")
        self.assertEqual(item_corpus({**base, "estado_vigencia": "rara "})["estado_vigencia"],
                         "rara")


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
            "alerts", "alerts_count",
            # R4d (campos añadidos).
            "avisos", "avisos_count",
            "cosine_threshold", "retrieved_sources", "status",
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
        # R4c (campos añadidos por referencia).
        self.assertFalse(fuente["precepto_derogado"])
        self.assertEqual(fuente["alcance_verificacion"], ALCANCE_NORMATIVA)
        self.assertEqual(
            self.estados(resultado),
            [("artículo 16", "verified", "corpus_metadata")],
        )
        self.assertEqual(fuente["trace_id"], resultado["traceability"]["records"][0]["trace_id"])

        resumen = resultado["vvca_summary"]
        self.assertEqual(sorted(resumen), [
            "alcance_verificacion", "alcance_verificacion_tesis",
            "amarillos", "articulos_ok", "articulos_total", "disclaimer",
            "normativa_no_verificable", "normativa_refutada", "rag_sin_citas", "rojos",
            "score_rag", "score_sjf", "semaforo_rag", "semaforo_sjf", "sjf_sin_citas",
            "tesis_mismatch", "tesis_no_encontradas", "tesis_ok", "tesis_parciales",
            # R4d (campos añadidos).
            "tesis_por_cotejo_rubro",
            "tesis_por_fuerza",
            # R4d (campo añadido).
            "tesis_por_vigencia",
            "tesis_rojas", "tesis_superadas", "tesis_total", "verdes",
            "veredicto",
        ])
        self.assertEqual((resumen["verdes"], resumen["amarillos"], resumen["rojos"]), (1, 0, 0))
        # R4-D11 (corregido en R4c): la razón enuncia solo lo verificado.
        self.assertEqual(resumen["veredicto"], {
            "apto": True,
            "semaforo": "🟢",
            "razon": "Normativa verificada; sin tesis citadas",
            "accion": "Proceder con revisión de pertinencia procesal por el operador",
        })
        # R4-D12 (corregido en R4c): sin tesis, la dimensión SJF es "sin citas" (valor nulo y
        # semáforo neutro), no 0.0 🔴.
        self.assertEqual((resumen["score_sjf"], resumen["semaforo_sjf"]),
                         (None, SEMAFORO_SIN_CITAS))
        self.assertEqual((resumen["rag_sin_citas"], resumen["sjf_sin_citas"]), (False, True))
        self.assertEqual(
            resultado["summary"],
            "RAG 92.0 🟢 (1 arts) · SJF sin citas · "
            "Veredicto: 🟢 Normativa verificada; sin tesis citadas",
        )
        # Alcance explícito: el texto del 🟢 al abogado dice qué acredita y qué no.
        self.assertEqual(resumen["alcance_verificacion"], ALCANCE_NORMATIVA)
        self.assertEqual(resumen["alcance_verificacion_tesis"], ALCANCE_JURISPRUDENCIA)
        texto = resumen["disclaimer"]["texto"]
        self.assertIn("(Normativa verificada; sin tesis citadas)", texto)
        self.assertIn(f"Alcance del 🟢: {ALCANCE_NORMATIVA}", texto)
        self.assertIn("no significa que lo citado diga lo que el escrito afirma", texto)

    def test_R4_D08_articulo_derogado_es_amarillo_nunca_verde(self) -> None:
        consulta = "Artículo 64 código fiscal de la federación"
        self.coleccion.agregar("Artículo 64.- (Se deroga).",
                               {"source": CFF, "article": "64", "page": "127"},
                               eje=self.codificador.eje(consulta), distancia=0.10)
        resultado = self.auditar("El artículo 64 del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["retrieved_text"], "Artículo 64.- (Se deroga).")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (84, "🟡"))
        self.assertTrue(fuente["precepto_derogado"])
        self.assertTrue(fuente["vvca"]["explicabilidad"]["precepto_derogado"])
        self.assertEqual(self.estados(resultado), [("artículo 64", "partial", "corpus_metadata")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 PRECEPTO DEROGADO (score 84): 'artículo 64' — en '{CFF}' (pág. 127) el artículo "
            "64 dice que se deroga: el texto vigente no contiene norma. Verificar si el escrito "
            "cita una versión anterior del precepto o un régimen transitorio aplicable antes de "
            "citar."
        ])
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["verdes"], resumen["amarillos"], resumen["rojos"]), (0, 1, 0))
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")
        self.assertEqual(resumen["veredicto"]["razon"],
                         "1 cita(s) normativa(s) con evidencia parcial o no verificable")
        self.assertEqual(resultado["summary"],
                         "RAG 84.0 🟡 (1 arts; 1 no verificable) · SJF sin citas · Veredicto: 🟡 "
                         "1 cita(s) normativa(s) con evidencia parcial o no verificable")

    def test_R4_D08_derogado_con_distancia_alta_no_es_rojo(self) -> None:
        # El precepto se ubicó (encabezado exacto) y su texto vigente es la derogación: 🟡,
        # nunca la rama "sin coincidencia confiable" (🔴) aunque la distancia sea alta.
        consulta = "Artículo 209 Bis código fiscal de la federación"
        self.coleccion.agregar("Artículo 209 Bis.- (Se deroga).",
                               {"source": CFF, "article": "209", "page": "241"},
                               eje=self.codificador.eje(consulta), distancia=0.45)
        resultado = self.auditar(
            "El artículo 209 Bis del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (70, "🟡"))
        self.assertEqual([e[1] for e in self.estados(resultado)], ["partial"])
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith("🟡 PRECEPTO DEROGADO (score 70): 'artículo 209 Bis'"))
        self.assertEqual(resultado["vvca_summary"]["rojos"], 0)

    def test_R4_D08_derogacion_de_otro_articulo_o_de_una_fraccion_no_cuenta(self) -> None:
        consulta = "Artículo 135 ley federal de protección al consumidor"
        lfpc = ON.LAW_SOURCE_MAP["lfpc"]
        self.coleccion.agregar(
            "Artículo 135.- Texto sintético vigente.\nI. (Se deroga).\nII. Texto.\n"
            "Artículo 136.- (Se deroga).",
            {"source": lfpc, "article": "135", "page": "70"},
            eje=self.codificador.eje(consulta), distancia=0.10,
        )
        resultado = self.auditar(
            "El artículo 135 de la Ley Federal de Protección al Consumidor se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertFalse(fuente["precepto_derogado"])
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (90, "🟢"))
        self.assertEqual(resultado["alerts"], [])

    def test_R4_D08_derogado_y_ley_por_confirmar_conservan_ambas_alertas(self) -> None:
        consulta = "Artículo 64 cff"
        self.coleccion.agregar("Artículo 64.- (Se deroga).",
                               {"source": CFF, "article": "64", "page": "127"},
                               eje=self.codificador.eje(consulta), distancia=0.05)
        resultado = self.auditar("El CFF regula la materia.\n\nEl artículo 64 dispone.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertTrue(fuente["precepto_derogado"])
        self.assertTrue(fuente["law_requires_confirmation"])
        self.assertEqual([a.split(" (score")[0].split(":")[0] for a in resultado["alerts"]],
                         ["🟡 LEY POR CONFIRMAR", "🟡 PRECEPTO DEROGADO"])
        self.assertEqual([e[1] for e in self.estados(resultado)], ["partial"])

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

    def test_R4_D10_sin_coincidencia_confiable_y_sin_prueba_es_no_localizado(self) -> None:
        # D10 (opción C, 2-oct-2026). Antes: traza "refuted" y "🔴 ALERTA ALTA (score 60) …
        # Posible alucinación". El fragmento no trae chunk_index: no hay cuerpo que examinar
        # ni prueba positiva de inexistencia, así que el artículo solo queda NO LOCALIZADO.
        consulta = "Artículo 9999 código fiscal de la federación"
        self.coleccion.agregar("Artículo 1.- Texto sintético.",
                               {"source": CFF, "article": "1", "page": "1"},
                               eje=self.codificador.eje(consulta), distancia=0.40)
        resultado = self.auditar("El artículo 9999 del Código Fiscal de la Federación se invoca.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (60, "🟡"))
        self.assertTrue(fuente["vvca"]["V_verificacion"].startswith("No localizado: "))
        self.assertEqual(fuente["vvca"]["explicabilidad"]["inexistencia_no_acreditada"],
                         "fragmento sin chunk_index entero o sin texto")
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "not_verifiable", "corpus_semantic")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 NO LOCALIZADO (score 60): 'artículo 9999' — no se encontró el art. 9999 en la "
            f"ley indexada '{CFF}'; no se acredita que no exista (puede ser un hueco del "
            f"índice): cotejar en la fuente oficial."
        ])
        self.assertNotIn("alucinaci", " ".join(resultado["alerts"]).lower())
        self.assertEqual(resultado["vvca_summary"]["veredicto"], {
            "apto": False,
            "semaforo": "🟡",
            "razon": "1 cita(s) normativa(s) con evidencia parcial o no verificable",
            "accion": "Cotejar el precepto en la fuente oficial antes de uso procesal",
        })

    def test_R4_D10_consulta_sin_vecinos_y_sin_prueba_es_no_localizado(self) -> None:
        # D10 (opción C). Antes: "🔴 ALERTA CRÍTICA … Alucinación detectada" (refuted).
        coleccion = FakeCollection(vaciar_consultas=True)
        consulta = "Artículo 9999 código fiscal de la federación"
        coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"},
                          eje=self.codificador.eje(consulta), distancia=0.40)
        resultado = self.auditar(
            "El artículo 9999 del Código Fiscal de la Federación se invoca.", coleccion=coleccion
        )
        self.assertEqual(resultado["retrieved_sources"], [])
        self.assertEqual(resultado["alerts"], [
            f"🟡 NO LOCALIZADO: 'artículo 9999' — no se encontró el art. 9999 en la ley "
            f"indexada '{CFF}'; no se acredita que no exista (puede ser un hueco del índice): "
            f"cotejar en la fuente oficial."
        ])
        (traza,) = resultado["traceability"]["records"]
        self.assertEqual(traza["verification"]["status"], "not_verifiable")
        self.assertEqual(traza["verification"]["semaforo"], "🟡")
        self.assertEqual(
            traza["verification"]["reason"],
            "Artículo no localizado en una fuente que sí está indexada; no se acredita su "
            "inexistencia: fragmento sin chunk_index entero o sin texto",
        )
        self.assertTrue(traza["metadata"]["no_localizado"])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")
        self.assertEqual(resultado["vvca_summary"]["rojos"], 0)

    def test_R4_D09_respaldo_sin_filtro_prefiere_la_fuente_esperada(self) -> None:
        # Antes de R4c: el respaldo borraba expected_source y el art. 16 del CFF (más cercano)
        # salía 🟢 95 "Fuente correcta". Ahora se prefiere la evidencia de la ley citada.
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
        self.assertEqual((fuente["source_file"], fuente["page"]), (CPEUM, "19"))
        self.assertEqual(fuente["expected_source"], CPEUM)
        explicabilidad = fuente["vvca"]["explicabilidad"]
        self.assertTrue(explicabilidad["coincide_fuente"])
        self.assertTrue(explicabilidad["filtro_fuente_fallido"])
        self.assertEqual(explicabilidad["fuente_esperada"], CPEUM)
        self.assertEqual(fuente["vvca"]["V_validacion"], f"Fuente correcta: {CPEUM}")
        # Distancia 0.30 > umbral: metadata + encabezado conservan el piso 🟡 (COTEJAR).
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (70, "🟡"))
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_R4_D09_evidencia_de_otro_ordenamiento_nunca_es_verde(self) -> None:
        coleccion = FakeCollection(fallar_consultas_filtradas=True)
        consulta = "Artículo 16 constitución política de los estados unidos"
        eje = self.codificador.eje(consulta)
        # La CPEUM está indexada (cobertura completa), pero su fragmento queda fuera de los
        # tres vecinos de la consulta sin filtro: solo llega evidencia de otros ordenamientos.
        coleccion.agregar("Artículo 16. Texto sintético de la Constitución.",
                          {"source": CPEUM, "article": "16", "page": "19"})
        coleccion.agregar("Artículo 16.- (Se deroga).",
                          {"source": CFF, "article": "16", "page": "7"},
                          eje=eje, distancia=0.0)
        for pagina in ("8", "9"):
            coleccion.agregar("Texto sintético de otro ordenamiento.",
                              {"source": LIVA, "article": "3", "page": pagina},
                              eje=eje, distancia=0.20)
        resultado = self.auditar(
            "El artículo 16 de la Constitución Política de los Estados Unidos Mexicanos "
            "exige fundamentación.",
            coleccion=coleccion,
        )
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["source_file"], fuente["expected_source"]), (CFF, CPEUM))
        # 100 − 15 = 85 sería 🟢: la evidencia de otro ordenamiento se limita a 🟡 (84).
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (84, "🟡"))
        self.assertFalse(fuente["vvca"]["explicabilidad"]["coincide_fuente"])
        self.assertFalse(fuente["vvca"]["explicabilidad"]["match_metadata"])
        self.assertEqual(fuente["vvca"]["V_validacion"],
                         f"Fuente distinta: se encontró en '{CFF}', se esperaba '{CPEUM}'")
        # La derogación de un fragmento de OTRO ordenamiento no se atribuye a la cita.
        self.assertFalse(fuente["precepto_derogado"])
        self.assertEqual(self.estados(resultado),
                         [("artículo 16", "not_verifiable", "corpus_semantic")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 EVIDENCIA DE OTRO ORDENAMIENTO (score 84): 'artículo 16' — el fragmento "
            f"recuperado es de '{CFF}', no de '{CPEUM}' (el filtro por fuente falló). No acredita "
            "ni refuta la cita: cotejar el precepto en la ley citada."
        ])
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["verdes"], resumen["amarillos"], resumen["rojos"]), (0, 1, 0))
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")

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
        # R4d: la tesis localizada no registra vigencia → aviso informativo aparte (no cambia
        # el semáforo ni cuenta en ``alerts_count``).
        self.assertEqual(resultado["avisos"], [
            "ℹ️ VIGENCIA NO CONSULTADA: Registro digital 0000001 — ni el corpus local ni el "
            "scraper registran la vigencia del criterio; no se asume vigente. No cambia el "
            "semáforo: verificar en sjf2.scjn.gob.mx (notas y ejecutorias) que no esté "
            "superado, interrumpido o sustituido.",
        ])
        self.assertEqual((resultado["alerts_count"], resultado["avisos_count"]), (1, 1))
        resumen = resultado["vvca_summary"]
        # V1 (piloto PEN-01, corregido): la tesis no encontrada es 🟡 NO VERIFICABLE, no
        # "roja"; antes ``tesis_rojas`` valía 1 aquí con veredicto 🟡 y ``rojos`` 0.
        self.assertEqual(
            (resumen["tesis_total"], resumen["tesis_ok"], resumen["tesis_no_encontradas"],
             resumen["tesis_rojas"], resumen["rojos"], resumen["tesis_por_fuerza"]),
            (2, 1, 1, 0, 0, {"[J-TCC]": 1}),
        )
        self.assertEqual((resumen["tesis_por_cotejo_rubro"], resumen["tesis_por_vigencia"]),
                         ({"coincide": 1}, {"no_consultada": 1}))
        self.assertEqual(resumen["veredicto"]["razon"],
                         "1/2 tesis no verificables (ausentes del corpus local — no "
                         "confirmadas como falsas)")

    def test_R4_D12_solo_tesis_verificadas_sin_articulos_no_es_insuficiencia(self) -> None:
        # Antes de R4c: "RAG 0.0 🔴" y 🟡 "Artículos con verificación insuficiente (RAG: 0.0)"
        # sin artículos citados. Ronda 2 de R4c: la razón ya no habla de artículos, pero el 🟢
        # se RETIENE (🟡 transitorio). R4d corrigió D13/D14, pero la retención se mantiene
        # (adjudicación del 2-oct-2026) hasta validar el cotejo con un corpus de tesis mayor.
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        self.guardar_tesis([_tesis_ficticia()])
        texto = ("Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
                 "COMPUTABLE, registro digital: 0000001.")
        resultado = self.auditar(texto)
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["score_rag"], resumen["semaforo_rag"]),
                         (None, SEMAFORO_SIN_CITAS))
        self.assertTrue(resumen["rag_sin_citas"])
        self.assertEqual((resumen["score_sjf"], resumen["semaforo_sjf"]), (95.0, "🟢"))
        self.assertEqual(self.estados(resultado),
                         [("registro digital: 0000001", "verified", "corpus_jurisprudencia")])
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")
        self.assertEqual(resumen["veredicto"]["razon"],
                         "Jurisprudencia localizada; 🟢 de solo tesis retenido (transitorio) "
                         "hasta validar el cotejo del rubro con un corpus de tesis mayor")
        self.assertEqual(resultado["summary"],
                         "RAG sin citas · SJF 95.0 🟢 (1/1 tesis ok) · Veredicto: 🟡 "
                         "Jurisprudencia localizada; 🟢 de solo tesis retenido (transitorio) "
                         "hasta validar el cotejo del rubro con un corpus de tesis mayor")
        (tesis,) = resultado["retrieved_sources"]
        self.assertEqual(tesis["alcance_verificacion"], ALCANCE_JURISPRUDENCIA)
        self.assertEqual(resumen["alcance_verificacion_tesis"], ALCANCE_JURISPRUDENCIA)
        # Cuando se libere la retención (bandera en False) el escrito sería 🟢 con su razón.
        import scoring_vvca
        with mock.patch.object(scoring_vvca, "RETENER_VERDE_SOLO_TESIS", False):
            veredicto = self.auditar(texto)["vvca_summary"]["veredicto"]
        self.assertEqual((veredicto["semaforo"], veredicto["razon"]),
                         ("🟢", "Jurisprudencia verificada; sin artículos citados"))

    def test_R4_D12_dimension_sin_puntaje_no_es_cero_rojo(self) -> None:
        # Todas las citas normativas no verificables: antes "RAG 0.0 🔴 (0 arts)".
        self.coleccion.agregar("Artículo 5.- Texto sintético.",
                               {"source": CFF, "article": "5", "page": "3"})
        resultado = self.auditar("Art. 5 establece la regla general.")
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["score_rag"], resumen["semaforo_rag"]), (None, "🟡"))
        self.assertEqual(resultado["summary"],
                         "RAG — 🟡 (1 arts; 1 no verificable) · SJF sin citas · Veredicto: 🟡 1 "
                         "cita(s) normativa(s) con evidencia parcial o no verificable")
        # Tesis invocadas y ninguna en el corpus local: 🟡, no 0.0 🔴.
        resultado = self.auditar("Tesis con registro digital: 0000009 (registro ficticio).")
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["score_sjf"], resumen["semaforo_sjf"]), (None, "🟡"))
        self.assertTrue(resultado["summary"].startswith(
            "RAG sin citas · SJF — 🟡 (0/1 tesis ok), 1 no encontradas (🟡 no verificables) · "
            "Veredicto: 🟡"))

    def test_R4_D12_subpuntaje_verde_dice_cuantas_quedaron_sin_verificar(self) -> None:
        consulta = "Artículo 16 cpeum"
        self.coleccion.agregar("Artículo 16. Texto sintético.",
                               {"source": CPEUM, "article": "16", "page": "19"},
                               eje=self.codificador.eje(consulta), distancia=0.08)
        resultado = self.auditar(
            "Art. 16 CPEUM. El artículo 5 de la Ley General de Salud dispone.")
        resumen = resultado["vvca_summary"]
        # El promedio solo cuenta la cita con evidencia (🟢), pero el subpuntaje dice cuántas
        # quedaron sin verificar; el veredicto sigue la peor traza (🟡).
        self.assertEqual((resumen["score_rag"], resumen["semaforo_rag"]), (92.0, "🟢"))
        self.assertTrue(resultado["summary"].startswith(
            "RAG 92.0 🟢 (2 arts; 1 no verificable) · SJF sin citas · Veredicto: 🟡"))

    def test_R4_D12_sin_citas_no_es_verde_vacio(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        resultado = self.auditar("Texto sin citas: el plazo vence mañana.")
        resumen = resultado["vvca_summary"]
        self.assertEqual(
            (resumen["score_rag"], resumen["semaforo_rag"], resumen["score_sjf"],
             resumen["semaforo_sjf"]),
            (None, SEMAFORO_SIN_CITAS, None, SEMAFORO_SIN_CITAS),
        )
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")
        self.assertEqual(resumen["veredicto"]["razon"],
                         "Sin citas detectadas: no hay normativa ni jurisprudencia que verificar")
        self.assertEqual(resultado["summary"],
                         "RAG sin citas · SJF sin citas · Veredicto: 🟡 Sin citas detectadas: no "
                         "hay normativa ni jurisprudencia que verificar")

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

    def test_V1_tesis_rojas_solo_cuenta_rojas_reales(self) -> None:
        # Piloto PEN-01 (V1): ``tesis_rojas`` sumaba las tesis no encontradas, que son 🟡 NO
        # VERIFICABLE ("🟡 no es 🔴"), y no contaba la vigencia perdida. Ahora cuenta solo
        # rubro discrepante o invertido y vigencia perdida, una vez por tesis; el veredicto se
        # calcula con los conteos de siempre y no cambia.
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        literal = ("Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
                   "COMPUTABLE, registro digital: 0000001.")
        invertido = ("Se invoca RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO NO ES COMPUTABLE, "
                     "registro digital: 0000001.")
        casos = (
            # (vigencia registrada, texto, tesis_rojas, semáforo del veredicto)
            ("superada", literal, 1, "🔴"),
            ("vigente", invertido, 1, "🔴"),
            ("superada", invertido, 1, "🔴"),  # la misma tesis no cuenta dos veces
            ("vigente", "Tesis con registro digital: 0000009 (registro ficticio).", 0, "🟡"),
        )
        for vigencia, texto, rojas, semaforo in casos:
            with self.subTest(vigencia=vigencia, texto=texto[:30]):
                self.guardar_tesis([_tesis_ficticia(estado_vigencia=vigencia)])
                resultado = self.auditar(texto)
                resumen = resultado["vvca_summary"]
                self.assertEqual(resumen["tesis_rojas"], rojas)
                self.assertEqual(resumen["veredicto"]["semaforo"], semaforo)
        resultado = self.auditar(literal.replace("0000001", "0000009"))
        self.assertIn("no encontradas (🟡 no verificables)", resultado["summary"])
        self.guardar_tesis([_tesis_ficticia(estado_vigencia="superada")])
        self.assertIn("1 con vigencia perdida", self.auditar(literal)["summary"])

    def test_R4_D07_tesis_en_mayusculas_entra_a_la_auditoria(self) -> None:
        # Antes la tesis desaparecía: 0 referencias, ninguna traza y 🟡 "Sin citas detectadas".
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        resultado = self.auditar("Tesis de prueba con REGISTRO DIGITAL: 0000001 (registro ficticio).")
        self.assertEqual(resultado["total_references_found"], 1)
        self.assertEqual(self.estados(resultado), [
            ("REGISTRO DIGITAL: 0000001", "not_verifiable", "corpus_jurisprudencia"),
        ])
        veredicto = resultado["vvca_summary"]["veredicto"]
        self.assertEqual((veredicto["semaforo"], veredicto["razon"]),
                         ("🟡", "1/1 tesis no verificables (ausentes del corpus local — no "
                                "confirmadas como falsas)"))
        # Localizada en el corpus, con su rubro literal: verificada como cualquier otra.
        self.guardar_tesis([_tesis_ficticia()])
        resultado = self.auditar(
            "Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
            "COMPUTABLE, REGISTRO DIGITAL: 0000001.")
        self.assertEqual(self.estados(resultado), [
            ("REGISTRO DIGITAL: 0000001", "verified", "corpus_jurisprudencia"),
        ])

    # ── R4d: cotejo del rubro y vigencia en la auditoría ──────────────────────────────
    def test_R4d_alertas_del_cotejo_muestran_el_rubro_original(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        real = "RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE"
        self.guardar_tesis([_tesis_ficticia(estado_vigencia="vigente")])
        casos = (
            # (texto, estado de la traza, semáforo, inicio de la alerta)
            ("Se invoca RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO NO ES COMPUTABLE, "
             "registro digital: 0000001.", "refuted", "🔴",
             "🔴 RUBRO DISCREPANTE — SENTIDO INVERTIDO: Registro digital 0000001. Diferencia "
             "de polaridad: negaciones"),
            ("Se invoca OTRO ENUNCIADO FICTICIO SOBRE NOTIFICACIONES SIMULADAS, registro "
             "digital: 0000001.", "refuted", "🔴",
             "🔴 RUBRO DISCREPANTE: Registro digital 0000001 existe en el corpus local, pero "
             "el rubro invocado no coincide con el real (traslape 20 %, menor a 40 %)."),
            ("La tesis de rubro: \"RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO…\", registro "
             "digital: 0000001.", "partial", "🟡", "🟡 RUBRO PARCIAL: Registro digital 0000001"),
            ("Se invoca RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE EN "
             "DÍAS HÁBILES, registro digital: 0000001.", "partial", "🟡",
             "🟡 RUBRO NO COINCIDE LITERALMENTE: Registro digital 0000001"),
            ("Se invoca una tesis con registro digital: 0000001.", "partial", "🟡",
             "🟡 SIN RUBRO INVOCADO: Registro digital 0000001"),
        )
        for texto, estado, semaforo, alerta in casos:
            with self.subTest(texto=texto[:40]):
                resultado = self.auditar(texto)
                self.assertEqual(self.estados(resultado),
                                 [("registro digital: 0000001", estado, "corpus_jurisprudencia")])
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], semaforo)
                (aviso,) = resultado["alerts"]
                self.assertTrue(aviso.startswith(alerta), aviso)
                # Siempre con el rubro real original, acentos incluidos (Regla 1).
                self.assertIn(f"Rubro real: «{real}»", aviso)

    def test_R4d_sin_rubro_invocado_dice_su_alcance(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        self.guardar_tesis([_tesis_ficticia(estado_vigencia="vigente")])
        resultado = self.auditar("Se invoca una tesis con registro digital: 0000001.")
        (tesis,) = resultado["retrieved_sources"]
        self.assertEqual((tesis["vvca"]["score"], tesis["vvca"]["cotejo_rubro"]),
                         (84, "sin_rubro_invocado"))
        self.assertIn("solo acredita la existencia del registro", tesis["vvca"]["V_verificacion"])
        self.assertEqual(tesis["alcance_verificacion"], ON.ALCANCE_JURISPRUDENCIA_SIN_RUBRO)
        resumen = resultado["vvca_summary"]
        self.assertEqual(resumen["alcance_verificacion_tesis"],
                         f"{ALCANCE_JURISPRUDENCIA}; 1 tesis sin cotejo del rubro: solo "
                         f"existencia del registro")
        self.assertEqual((resumen["tesis_ok"], resumen["tesis_parciales"]), (0, 1))
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")

    def test_R4d_una_tesis_no_hereda_el_rubro_de_la_anterior(self) -> None:
        # Antes los 400 caracteres previos podían incluir el rubro de otra tesis.
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        self.guardar_tesis([
            _tesis_ficticia(estado_vigencia="vigente"),
            _tesis_ficticia(registro="0000002", estado_vigencia="vigente",
                            rubro="SEGUNDO RUBRO SINTÉTICO SOBRE NOTIFICACIONES FICTICIAS"),
        ])
        resultado = self.auditar(
            "Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
            "COMPUTABLE, registro digital: 0000001, y la de registro digital: 0000002."
        )
        cotejos = [s["vvca"]["cotejo_rubro"] for s in resultado["retrieved_sources"]]
        self.assertEqual(cotejos, ["coincide", "sin_rubro_invocado"])
        self.assertEqual(resultado["vvca_summary"]["tesis_mismatch"], 0)

    def test_R4d_vigencia_perdida_sigue_bloqueando_y_sin_dato_no_cambia_el_semaforo(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        texto = ("Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
                 "COMPUTABLE, registro digital: 0000001.")
        for estado in ("superada", "interrumpida", "sustituida"):
            with self.subTest(estado=estado):
                self.guardar_tesis([_tesis_ficticia(estado_vigencia=estado)])
                resumen = self.auditar(texto)["vvca_summary"]
                self.assertEqual((resumen["tesis_superadas"], resumen["veredicto"]["semaforo"]),
                                 (1, "🔴"))
                self.assertEqual(resumen["tesis_por_vigencia"], {estado: 1})
        # Sin dato o con un valor desconocido: aviso ℹ️ aparte; la tesis y el veredicto quedan
        # igual que con la vigencia registrada como "vigente".
        self.guardar_tesis([_tesis_ficticia(estado_vigencia="vigente")])
        con_vigencia = self.auditar(texto)
        self.assertEqual(con_vigencia["avisos"], [])
        for estado, aviso in ((None, "ℹ️ VIGENCIA NO CONSULTADA"),
                              ("rara", "ℹ️ VIGENCIA NO RECONOCIDA")):
            with self.subTest(estado=estado):
                self.guardar_tesis([_tesis_ficticia(estado_vigencia=estado)])
                resultado = self.auditar(texto)
                self.assertEqual(resultado["vvca_summary"]["veredicto"],
                                 con_vigencia["vvca_summary"]["veredicto"])
                self.assertEqual(resultado["retrieved_sources"][0]["vvca"]["score"], 95)
                self.assertEqual(resultado["vvca_summary"]["tesis_superadas"], 0)
                self.assertEqual(resultado["alerts"], [])
                (texto_aviso,) = resultado["avisos"]
                self.assertTrue(texto_aviso.startswith(aviso), texto_aviso)
                if estado:
                    self.assertIn("«rara»", texto_aviso)
                # Telegram: el aviso informativo va agrupado y sin el signo de advertencia.
                telegram = ON.formato_telegram(resultado)
                self.assertIn("\n" + aviso + " (no cambia el semáforo", telegram)
                self.assertNotIn("⚠️ ℹ️", telegram)


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
                "entre 3 artículo(s): no cuadra",
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


class RondaTresTests(AuditoriaBase):
    """Ronda 3 de R4b (segunda revisión de Codex). Cada prueba fija artículo, ley,
    ``law_method``, banderas y el semáforo de la traza en ``audit()``."""

    def _refs(self, texto: str) -> list[tuple]:
        return [(r["article"], r["law"], r["source_file"], r["law_method"],
                 r["law_requires_confirmation"], bool(r["coverage_gap"]))
                for r in ON.extract_references(texto) if r["type"] == "article"]

    def _semaforos(self, resultado: dict) -> list[str]:
        return [t["verification"]["semaforo"] for t in resultado["traceability"]["records"]]

    def _fragmento(self, consulta: str, texto: str, fuente: str, articulo: str,
                   distancia: float = 0.05) -> None:
        self.coleccion.agregar(texto, {"source": fuente, "article": articulo, "page": "1"},
                               eje=self.codificador.eje(consulta), distancia=distancia)

    # ── P2: "respectivamente" sin repetir la preposición ───────────────────────────────
    def test_r3_p2_respectivamente_con_leyes_coordinadas_sin_preposicion(self) -> None:
        texto = "Los artículos 14 y 16 de la CPEUM y el CFF, respectivamente."
        self.assertEqual(self._refs(texto), [
            ("14", "cpeum", CPEUM, "adyacente_derecha", False, False),
            ("16", "cff", CFF, "adyacente_derecha", False, False),
        ])
        self._fragmento("Artículo 14 cpeum", "Artículo 14. Texto sintético.", CPEUM, "14")
        self._fragmento("Artículo 16 cff", "Artículo 16.- Texto sintético.", CFF, "16")
        resultado = self.auditar(texto)
        self.assertEqual([e[1:] for e in self.estados(resultado)],
                         [("verified", "corpus_metadata")] * 2)
        self.assertEqual(self._semaforos(resultado), ["🟢", "🟢"])

    def test_r3_p2_reparto_que_no_cuadra_deja_el_grupo_sin_ley(self) -> None:
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        for texto in (
            "Los artículos 14 y 16 de la CPEUM, el CFF y la LISR, respectivamente.",
            "Los artículos 14 y 16 de la CPEUM, respectivamente.",
        ):
            with self.subTest(texto=texto):
                refs = ON.extract_references(texto)
                self.assertEqual([(r["source_file"], r["law_method"]) for r in refs],
                                 [(None, None)] * 2)
                self.assertTrue(all("no cuadra" in r["law_unidentified_reason"] for r in refs))
                self.assertEqual(self._semaforos(self.auditar(texto)), ["🟡", "🟡"])
        # Sin "respectivamente", "y el CFF" es otro sujeto: el 16 sigue siendo de la CPEUM.
        self.assertEqual(
            self._refs("El artículo 16 de la CPEUM y el CFF establecen reglas."),
            [("16", "cpeum", CPEUM, "adyacente_derecha", False, False)],
        )

    # ── P6: rangos con ordinales o grado ───────────────────────────────────────────────
    def test_r3_p6_rango_largo_con_ordinales_deja_cobertura_incompleta(self) -> None:
        for texto, extremos in (
            ("Arts. 1º-25º del CFF.", ("1º", "25º")),
            ("Arts. 1o.-25o. CFF.", ("1o", "25o")),
            ("Arts. 1°-25° CFF.", ("1", "25")),
        ):
            with self.subTest(texto=texto):
                self.assertEqual([r[0] for r in self._refs(texto)], [*extremos, "2 a 24"])
                self.assertEqual([r[5] for r in self._refs(texto)], [False, False, True])
        self._fragmento("Artículo 1º cff", "Artículo 1º.- Texto sintético.", CFF, "1º")
        self._fragmento("Artículo 25º cff", "Artículo 25º.- Texto sintético.", CFF, "25º")
        resultado = self.auditar("Arts. 1º-25º del CFF.")
        self.assertEqual([e[2] for e in self.estados(resultado)],
                         ["corpus_metadata", "corpus_metadata", "cobertura_extraccion"])
        self.assertEqual(self._semaforos(resultado), ["🟢", "🟢", "🟡"])
        self.assertTrue(any("rango de 25 artículos" in a for a in resultado["alerts"]))
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")
        # Un rango corto con ordinales se expande con el mismo ordinal.
        self.assertEqual([r[0] for r in self._refs("Arts. 1o. a 4o. del CFF.")],
                         ["1o", "2o", "3o", "4o"])

    # ── P7: punto y coma dentro de la enumeración ─────────────────────────────────────
    def test_r3_p7_punto_y_coma_no_hace_desaparecer_un_miembro(self) -> None:
        texto = "Los artículos 14 de la CPEUM; 42 del CFF."
        self.assertEqual(self._refs(texto), [
            ("14", "cpeum", CPEUM, "adyacente_derecha", False, False),
            ("42", "cff", CFF, "adyacente_derecha", False, False),
        ])
        self._fragmento("Artículo 14 cpeum", "Artículo 14. Texto sintético.", CPEUM, "14")
        self._fragmento("Artículo 42 cff", "Artículo 42.- Texto sintético.", CFF, "42")
        resultado = self.auditar(texto)
        self.assertEqual(self._semaforos(resultado), ["🟢", "🟢"])
        # Si no se puede extraer con certeza, queda como cobertura incompleta (🟡).
        refs = self._refs("El artículo 14 de la CPEUM; también el 42 del CFF.")
        self.assertEqual([(r[0], r[2], r[5]) for r in refs],
                         [("14", CPEUM, False), ("42", None, True)])
        # Un número que no está ligado a una ley tras ";" no es un artículo.
        self.assertEqual([r[0] for r in self._refs(
            "El artículo 14 de la CPEUM; el plazo es de 16 días.")], ["14"])

    # ── N1: ordenamientos fuera del catálogo como antecedentes ───────────────────────
    def test_r3_n1_antecedente_fuera_del_catalogo_cuenta(self) -> None:
        self.coleccion.agregar("Artículo 5.- Texto sintético.", {"source": LAMP, "article": "5"})
        casos = {
            "La Ley de Amparo y la Ley General de Salud rigen. El artículo 5 de la ley dispone.":
                "es ambiguo",
            "La Ley General de Salud rige. El artículo 5 de la ley dispone.":
                "fuera del catálogo: 'Ley General de Salud'",
        }
        for texto, motivo in casos.items():
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual((ref["source_file"], ref["law_method"],
                                  ref["law_requires_confirmation"]), (None, None, False))
                self.assertIn(motivo, ref["law_unidentified_reason"])
                self.assertEqual(self._semaforos(self.auditar(texto)), ["🟡"])
        self.assertEqual(
            self._refs("La Ley de Amparo rige. El artículo 5 de la ley dispone."),
            [("5", "ley de amparo", LAMP, "antecedente", False, False)],
        )

    # ── N3: "numeral" y "precepto" como cabeza; "Carta Magna" como "la Constitución" ──
    def test_r3_n3_numeral_y_precepto_abren_referencia(self) -> None:
        self.coleccion.agregar("Artículo 16. Texto sintético.", {"source": CPEUM, "article": "16"})
        texto = "Se vulnera el numeral 16 de la Carta Magna."
        (ref,) = ON.extract_references(texto)
        self.assertEqual((ref["article"], ref["raw"], ref["source_file"], ref["law_method"]),
                         ("16", "numeral 16", None, None))
        self.assertIn("'Carta Magna' sin denominación", ref["law_unidentified_reason"])
        resultado = self.auditar(texto)
        self.assertEqual(self.estados(resultado),
                         [("numeral 16", "not_verifiable", "resolucion_ley")])
        self.assertEqual(self._semaforos(resultado), ["🟡"])
        casos = {
            "La Constitución Política de los Estados Unidos Mexicanos rige. Se vulnera el "
            "numeral 16 de la Carta Magna.":
                [("16", "constitución política de los estados unidos", CPEUM, "antecedente",
                  False, False)],
            "Se invocan los numerales 14 y 16 constitucionales.":
                [("14", "constitucional", CPEUM, "adyacente_derecha", False, False),
                 ("16", "constitucional", CPEUM, "adyacente_derecha", False, False)],
            "El precepto 17 de la Ley de Amparo dispone.":
                [("17", "ley de amparo", LAMP, "adyacente_derecha", False, False)],
            # Tras otro número o un apartado, "numeral" es un calificador del precepto.
            "El artículo 16, apartado A, numeral 3 de la CPEUM.":
                [("16", "cpeum", CPEUM, "adyacente_derecha", False, False)],
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(self._refs(texto), esperado)

    def test_criterio_del_responsable_1oct2026_constitucion_sin_denominacion(self) -> None:
        """Criterio del responsable (1-oct-2026): "de la Constitución", "Carta Magna", "Ley
        Fundamental" o "Norma Suprema" sin la denominación completa ni antecedente
        inequívoco quedan 🟡 hasta confirmar; nunca CPEUM automática."""
        self.coleccion.agregar("Artículo 16. Texto sintético.", {"source": CPEUM, "article": "16"})
        for denominacion in ("la Constitución", "la Carta Magna", "la Ley Fundamental",
                             "la Norma Suprema"):
            texto = f"El artículo 16 de {denominacion} exige fundamentación."
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertIsNone(ref["source_file"])
                self.assertNotEqual(ref["law"], "cpeum")
                resultado = self.auditar(texto)
                self.assertEqual(self.estados(resultado),
                                 [("artículo 16", "not_verifiable", "resolucion_ley")])
                self.assertEqual(self._semaforos(resultado), ["🟡"])


class RondaDosR4cTests(AuditoriaBase):
    """Ronda 2 de R4c (revisión de Codex y del coordinador). Cada prueba fija el semáforo por
    referencia, la traza y el veredicto global."""

    CCF = ON.LAW_SOURCE_MAP["ccf"]
    ART31 = ("Artículo 31.- Se reputa domicilio legal:\nI.\n(Se deroga).\nFracción derogada DOF "
             "03-06-2019\nII. Del menor de edad no emancipado, el de quien ejerza la patria "
             "potestad;\nIII. Texto sintético de la tercera fracción.")

    def _resultado(self, texto: str) -> tuple[dict, dict, dict]:
        resultado = self.auditar(texto)
        (fuente,) = resultado["retrieved_sources"]
        (traza,) = resultado["traceability"]["records"]
        return resultado, fuente, traza

    def _articulo31(self, consulta: str) -> None:
        self.coleccion.agregar(self.ART31, {"source": self.CCF, "article": "31", "page": "5",
                                            "chunk_index": "30"},
                               eje=self.codificador.eje(consulta), distancia=0.10)

    # ── Punto 1: fracción derogada ─────────────────────────────────────────────────────
    def test_p1_fraccion_derogada_es_amarilla_sin_derogar_el_articulo(self) -> None:
        self._articulo31("Artículo 31 fracción I código civil federal")
        resultado, fuente, traza = self._resultado(
            "El artículo 31, fracción I, del Código Civil Federal se invoca.")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (84, "🟡"))
        self.assertFalse(fuente["precepto_derogado"])
        self.assertEqual(fuente["unidad_derogada"], "fracción I")
        self.assertFalse(fuente["unidad_cotejada"])
        self.assertEqual(traza["verification"]["status"], "partial")
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith(
            "🟡 PRECEPTO DEROGADO (score 84): 'artículo 31, fracción I' — en "
            f"'{self.CCF}' (pág. 5) la fracción I del artículo 31 dice que se deroga (el resto "
            "del artículo no se declara derogado)"))
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_p1_fraccion_vigente_cotejada_y_articulo_completo_siguen_verdes(self) -> None:
        for texto, consulta, unidad in (
            ("El artículo 31, fracción II, del Código Civil Federal se invoca.",
             "Artículo 31 fracción II código civil federal", True),
            ("El artículo 31 del Código Civil Federal se invoca.",
             "Artículo 31 código civil federal", None),
        ):
            with self.subTest(texto=texto):
                self.coleccion = FakeCollection()
                self._articulo31(consulta)
                resultado, fuente, traza = self._resultado(texto)
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                                 (90, "🟢"))
                self.assertEqual(fuente["unidad_cotejada"], unidad)
                self.assertEqual(traza["verification"]["status"], "verified")
                self.assertEqual(resultado["alerts"], [])
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟢")

    def test_p1_unidad_no_ubicable_no_es_verde(self) -> None:
        for texto, consulta, motivo in (
            ("El artículo 31, fracción IX, del Código Civil Federal se invoca.",
             "Artículo 31 fracción IX código civil federal",
             "la fracción IX no se ubica de forma inequívoca"),
            ("El artículo 31, párrafo segundo, del Código Civil Federal se invoca.",
             "Artículo 31 código civil federal",
             "la unidad citada (párrafo segundo) no se puede ubicar con certeza"),
        ):
            with self.subTest(texto=texto):
                self.coleccion = FakeCollection()
                self._articulo31(consulta)
                resultado, fuente, traza = self._resultado(texto)
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                                 (84, "🟡"))
                self.assertIn(motivo, fuente["unidad_no_cotejada"])
                self.assertEqual(traza["verification"]["status"], "partial")
                (alerta,) = resultado["alerts"]
                self.assertTrue(alerta.startswith("🟡 UNIDAD CITADA NO COTEJADA (score 84)"))
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_p1_unidad_previa_u_ordinal_en_palabra_se_coteja(self) -> None:
        # Ajuste previo al commit: la unidad que precede al artículo, o que sigue a un ordinal
        # con punto ("1o., párrafo tercero"), se coteja igual que la pegada a la derecha.
        constitucion = "la Constitución Política de los Estados Unidos Mexicanos"
        cpeum = "constitución política de los estados unidos"
        art1 = ("Artículo 1o. Texto sintético del primer párrafo.\n\nTexto sintético del "
                "segundo párrafo.\n\nTexto sintético del tercer párrafo.")
        art107 = ("Artículo 107. Texto sintético:\nIII.- Texto sintético de la fracción:\n"
                  "a) Inciso sintético vigente de la fracción tercera;\nb) (Se deroga).\n"
                  "IV.- Texto sintético de la cuarta fracción.")
        casos = [
            # (texto, consulta, fragmento, metadata, semáforo, score, estado, alerta)
            (f"El artículo 1o., párrafo tercero, de {constitucion}.", f"Artículo 1o {cpeum}",
             art1, {"source": CPEUM, "article": "1o"}, "🟡", 84, "partial",
             "🟡 UNIDAD CITADA NO COTEJADA"),
            (f"El artículo 1o., tercer párrafo, de {constitucion}.", f"Artículo 1o {cpeum}",
             art1, {"source": CPEUM, "article": "1o"}, "🟡", 84, "partial",
             "🟡 UNIDAD CITADA NO COTEJADA"),
            (f"El párrafo tercero del artículo 1o. de {constitucion}.", f"Artículo 1o {cpeum}",
             art1, {"source": CPEUM, "article": "1o"}, "🟡", 84, "partial",
             "🟡 UNIDAD CITADA NO COTEJADA"),
            (f"El artículo 1o. de {constitucion} se invoca.", f"Artículo 1o {cpeum}",
             art1, {"source": CPEUM, "article": "1o"}, "🟢", 90, "verified", None),
            ("La fracción II del artículo 31 del Código Civil Federal dispone.",
             "Artículo 31 código civil federal", self.ART31,
             {"source": self.CCF, "article": "31"}, "🟢", 90, "verified", None),
            ("La fracción I del artículo 31 del Código Civil Federal dispone.",
             "Artículo 31 código civil federal", self.ART31,
             {"source": self.CCF, "article": "31"}, "🟡", 84, "partial",
             "🟡 PRECEPTO DEROGADO"),
            (f"El inciso a) de la fracción III del artículo 107 de {constitucion}.",
             f"Artículo 107 {cpeum}", art107, {"source": CPEUM, "article": "107"}, "🟢", 90,
             "verified", None),
            (f"El inciso b) de la fracción III del artículo 107 de {constitucion}.",
             f"Artículo 107 {cpeum}", art107, {"source": CPEUM, "article": "107"}, "🟡", 84,
             "partial", "🟡 PRECEPTO DEROGADO"),
        ]
        for texto, consulta, fragmento, metadata, semaforo, score, estado, alerta in casos:
            with self.subTest(texto=texto):
                self.coleccion = FakeCollection()
                self.coleccion.agregar(fragmento, dict(metadata, page="1"),
                                       eje=self.codificador.eje(consulta), distancia=0.10)
                resultado, fuente, traza = self._resultado(texto)
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                                 (score, semaforo))
                self.assertEqual(traza["verification"]["status"], estado)
                if alerta:
                    (aviso,) = resultado["alerts"]
                    self.assertTrue(aviso.startswith(alerta), aviso)
                else:
                    self.assertEqual(resultado["alerts"], [])
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], semaforo)

    # ── Punto 2: variantes de la fórmula y fórmula ambigua ────────────────────────────
    def test_p2_variantes_de_derogacion_y_formula_ambigua(self) -> None:
        for cuerpo, alerta_esperada in (
            ("DEROGADO.", "🟡 PRECEPTO DEROGADO (score 84)"),
            ("(Se deroga.)", "🟡 PRECEPTO DEROGADO (score 84)"),
            ("Derogado.", "🟡 PRECEPTO DEROGADO (score 84)"),
            ("(Se deroga primer párrafo).\nTexto sintético del segundo párrafo.",
             "🟡 POSIBLE DEROGACIÓN (score 84)"),
        ):
            with self.subTest(cuerpo=cuerpo):
                self.coleccion = FakeCollection()
                self.coleccion.agregar(
                    f"Artículo 64.- {cuerpo}", {"source": CFF, "article": "64", "page": "127"},
                    eje=self.codificador.eje("Artículo 64 código fiscal de la federación"),
                    distancia=0.10)
                resultado, fuente, traza = self._resultado(
                    "El artículo 64 del Código Fiscal de la Federación se invoca.")
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                                 (84, "🟡"))
                self.assertEqual(traza["verification"]["status"], "partial")
                (alerta,) = resultado["alerts"]
                self.assertTrue(alerta.startswith(alerta_esperada))
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    # ── Punto 3: evidencia incompleta y continuación ─────────────────────────────────
    def test_p3_encabezado_sin_cuerpo_resuelve_la_continuacion_o_queda_amarillo(self) -> None:
        consulta = "Artículo 64 código fiscal de la federación"
        for continuacion, alerta_esperada, derogado in (
            ("[LEY 64]\n(Se deroga).", "🟡 PRECEPTO DEROGADO (score 84)", True),
            (None, "🟡 EVIDENCIA INCOMPLETA (score 84)", False),
        ):
            with self.subTest(continuacion=continuacion):
                self.coleccion = FakeCollection()
                eje = self.codificador.eje(consulta)
                self.coleccion.agregar(
                    "Texto sintético del artículo anterior.\nArtículo 64.-",
                    {"source": CFF, "article": "64", "page": "127", "chunk_index": "450"},
                    eje=eje, distancia=0.10)
                if continuacion:
                    self.coleccion.agregar(
                        continuacion,
                        {"source": CFF, "article": "64", "page": "127", "chunk_index": "451"},
                        eje=eje, distancia=0.30)
                resultado, fuente, traza = self._resultado(
                    "El artículo 64 del Código Fiscal de la Federación se invoca.")
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                                 (84, "🟡"))
                self.assertEqual(fuente["precepto_derogado"], derogado)
                self.assertEqual(fuente["evidencia_incompleta"], not derogado)
                self.assertEqual(traza["verification"]["status"], "partial")
                (alerta,) = resultado["alerts"]
                self.assertTrue(alerta.startswith(alerta_esperada))
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_p3_continuacion_vigente_completa_el_precepto(self) -> None:
        consulta = "Artículo 64 código fiscal de la federación"
        eje = self.codificador.eje(consulta)
        self.coleccion.agregar(
            "Texto sintético del artículo anterior.\nArtículo 64.-",
            {"source": CFF, "article": "64", "page": "127", "chunk_index": "450"},
            eje=eje, distancia=0.10)
        self.coleccion.agregar(
            "[LEY 64]\nLas autoridades sintéticas podrán ejercer facultades de prueba.",
            {"source": CFF, "article": "64", "page": "128", "chunk_index": "451"},
            eje=eje, distancia=0.30)
        resultado, fuente, traza = self._resultado(
            "El artículo 64 del Código Fiscal de la Federación se invoca.")
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (90, "🟢"))
        self.assertEqual(fuente["vvca"]["explicabilidad"]["fragmentos_continuacion"], 1)
        self.assertEqual(traza["verification"]["status"], "verified")
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟢")

    # ── Punto 4: tesis parciales cuentan en el veredicto ─────────────────────────────
    def test_p4_tesis_aislada_parcial_no_deja_verde_el_documento(self) -> None:
        self.coleccion.agregar("Artículo 16. Texto sintético.",
                               {"source": CPEUM, "article": "16", "page": "19"},
                               eje=self.codificador.eje("Artículo 16 cpeum"), distancia=0.08)
        self.guardar_tesis([_tesis_ficticia(tipo_tesis="Aislada", numero_tesis="CLAVE-FICTICIA 1")])
        invoca = ("Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
                  "COMPUTABLE, registro digital: 0000001.")
        for texto, estados in (
            (invoca, [("registro digital: 0000001", "partial", "corpus_jurisprudencia")]),
            ("Art. 16 CPEUM.\n\n" + invoca,
             [("Art. 16", "verified", "corpus_metadata"),
              ("registro digital: 0000001", "partial", "corpus_jurisprudencia")]),
        ):
            with self.subTest(texto=texto[:20]):
                resultado = self.auditar(texto)
                tesis = [s for s in resultado["retrieved_sources"]
                         if s["ref_type"] == "jurisprudencia"][0]
                self.assertEqual((tesis["vvca"]["score"], tesis["vvca"]["semaforo"]), (72, "🟡"))
                self.assertEqual(self.estados(resultado), estados)
                resumen = resultado["vvca_summary"]
                self.assertEqual((resumen["tesis_ok"], resumen["tesis_parciales"]), (0, 1))
                self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")
                self.assertEqual(resumen["veredicto"]["razon"],
                                 "1/1 tesis con verificación parcial (localizadas con puntaje "
                                 "menor a 85, p. ej. tesis aislada)")
                self.assertIn("SJF 72.0 🟡 (0/1 tesis ok), 1 parcial", resultado["summary"])

    def test_e_el_flujo_real_pasa_articulos_total_y_tesis_parciales(self) -> None:
        # Adjudicación (e): ``articulos_total`` es opcional en veredicto_global, pero audit()
        # siempre lo pasa (la llamada sin él conserva la regla anterior; ver VeredictoTests).
        self.coleccion.agregar("Artículo 1.- Texto sintético.", {"source": CFF, "article": "1"})
        with mock.patch.object(ON, "veredicto_global", wraps=ON.veredicto_global) as espia:
            self.auditar("Texto sin citas.")
        (_, nombrados), = [(c.args, c.kwargs) for c in espia.call_args_list]
        self.assertEqual((nombrados["articulos_total"], nombrados["tesis_parciales"]), (0, 0))

    # ── Punto 6: alcance en la salida Telegram ───────────────────────────────────────
    def test_p6_telegram_muestra_el_alcance_de_cada_dimension(self) -> None:
        self.coleccion.agregar("Artículo 16. Texto sintético.",
                               {"source": CPEUM, "article": "16", "page": "19"},
                               eje=self.codificador.eje("Artículo 16 cpeum"), distancia=0.08)
        self.guardar_tesis([_tesis_ficticia()])
        invoca = ("Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
                  "COMPUTABLE, registro digital: 0000001.")
        ambos = ON.formato_telegram(self.auditar("Art. 16 CPEUM.\n\n" + invoca))
        self.assertIn(f"Alcance (normas): {ALCANCE_NORMATIVA}", ambos)
        self.assertIn(f"Alcance (tesis): {ALCANCE_JURISPRUDENCIA}", ambos)
        normas = ON.formato_telegram(self.auditar("Art. 16 CPEUM."))
        self.assertIn("Alcance (normas):", normas)
        self.assertNotIn("Alcance (tesis):", normas)
        self.assertIn("SJF: sin citas", normas)
        # Un 🟡 no lleva la línea de alcance del 🟢.
        self.assertNotIn("Alcance", ON.formato_telegram(self.auditar(invoca)))


TESIS_2006224 = {
    # Datos reales de tests/fixtures/evidencia/sjf_2006224.txt (sin vigencia registrada).
    "registro": "2006224", "rubro": RUBRO_2006224, "tipo_tesis": "Jurisprudencia",
    "numero_tesis": "P./J. 20/2014 (10a.)", "sala": "Pleno", "epoca": "Décima Época",
    "materia": "Constitucional",
}
TESIS_2032506 = {
    # Datos reales de tests/fixtures/evidencia/sjf_2032506.txt (sin vigencia registrada).
    "registro": "2032506", "rubro": RUBRO_2032506, "tipo_tesis": "Aislada",
    "numero_tesis": "VI.3o.A.55 A (12a.)", "materia": "Administrativa, Común",
}


class RondaDosR4dTests(AuditoriaBase):
    """Ronda 2 de R4d (rechazo de Codex y del coordinador). Cada prueba fija el resultado del
    cotejo, el semáforo de la tesis y el veredicto del escrito. El escrito cita además un
    artículo verificado (🟢), para que el veredicto dependa solo de la tesis: con la tesis
    🟢 el veredicto es 🟢 "Normativa y jurisprudencia verificadas"."""

    ART16 = "Art. 16 CPEUM.\n\n"

    def setUp(self) -> None:
        super().setUp()
        self.coleccion.agregar("Artículo 16. Texto sintético.",
                               {"source": CPEUM, "article": "16", "page": "19"},
                               eje=self.codificador.eje("Artículo 16 cpeum"), distancia=0.08)
        self.guardar_tesis([
            TESIS_2006224, TESIS_2032506,
            _tesis_ficticia(registro="0000005",
                            rubro="RUBRO SINTÉTICO. LA REGLA FICTICIA 1.4.14. Y LA CLAVE "
                                  "69-B SON APLICABLES"),
        ])

    def _auditar(self, texto: str) -> tuple[dict, dict]:
        resultado = self.auditar(self.ART16 + texto)
        (tesis,) = [s for s in resultado["retrieved_sources"] if s["ref_type"] == "jurisprudencia"]
        return resultado, tesis

    def comprobar(self, texto: str, cotejo: str, puntaje: int, semaforo: str,
                  veredicto: str) -> dict:
        resultado, tesis = self._auditar(texto)
        self.assertEqual((tesis["vvca"]["cotejo_rubro"], tesis["vvca"]["score"],
                          tesis["vvca"]["semaforo"]), (cotejo, puntaje, semaforo))
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], veredicto)
        return resultado

    def test_control_rubro_literal_es_verde(self) -> None:
        resultado = self.comprobar(f"La jurisprudencia de rubro: «{RUBRO_2006224}», registro "
                                   f"digital: 2006224.", "coincide", 95, "🟢", "🟢")
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["razon"],
                         "Normativa y jurisprudencia verificadas")

    def test_p1_texto_omitido_tras_el_marcador_impide_coincidir(self) -> None:
        # Antes: "coincide" 🟢 aunque el escrito niegue el rubro.
        for texto in (
            f"La jurisprudencia de rubro: no es cierto que {RUBRO_2006224}, registro digital: "
            f"2006224.",
            f"La jurisprudencia de rubro: no es cierto que «{RUBRO_2006224}», registro digital: "
            f"2006224.",
        ):
            with self.subTest(texto=texto[:60]):
                resultado = self.comprobar(texto, "no_literal", 84, "🟡", "🟡")
                alerta = [a for a in resultado["alerts"] if "2006224" in a][0]
                self.assertIn("«no es cierto que»", alerta)
        # Las fórmulas introductorias de la lista cerrada sí se admiten.
        for formula in ("de rubro y texto siguientes:", "cuyo rubro es:", "de rubro, que a la "
                        "letra dice:", "intitulada", "de título y subtítulo:"):
            with self.subTest(formula=formula):
                self.comprobar(f"La jurisprudencia {formula} «{RUBRO_2006224}», registro "
                               f"digital: 2006224.", "coincide", 95, "🟢", "🟢")

    def test_p2_marca_de_supresion_nunca_coincide(self) -> None:
        # Antes: "coincide" 🟢, porque la normalización borraba el "…".
        for marca in ("…", "...", "[…]"):
            with self.subTest(marca=marca):
                self.comprobar(f"La jurisprudencia de rubro: «{RUBRO_2006224} {marca}», "
                               f"registro digital: 2006224.", "parcial", 84, "🟡", "🟡")
        # La ventana recortada también marca la supresión al inicio.
        invocado = extraer_rubro_invocado(RUBRO_2006224, recortado=True)
        self.assertTrue(invocado["truncado"])
        self.assertEqual(cotejar_rubro(invocado, RUBRO_2006224)["resultado"], "parcial")

    def test_p3_numeros_y_designaciones_se_conservan(self) -> None:
        # Antes: "1.4.14." y "1/4/14." se normalizaban igual y la tesis salía "coincide".
        cambiado = RUBRO_2032506.replace("1.4.14.", "1/4/14.")
        self.assertNotEqual(normalizar_rubro(cambiado), normalizar_rubro(RUBRO_2032506))
        self.assertEqual(_cotejo(f"de rubro: «{cambiado}»", RUBRO_2032506)["resultado"],
                         "no_literal")
        self.comprobar(f"La tesis de rubro: «{cambiado}», registro digital: 2032506.",
                       "no_literal", 72, "🟡", "🟡")
        real = "RUBRO SINTÉTICO. LA REGLA FICTICIA 1.4.14. Y LA CLAVE 69-B SON APLICABLES"
        self.comprobar(f"La tesis de rubro: «{real}», registro digital: 0000005.",
                       "coincide", 95, "🟢", "🟢")
        for variante in (real.replace("1.4.14.", "1/4/14."), real.replace("69-B", "69 B"),
                         real.replace("69-B", "96-B")):
            with self.subTest(variante=variante[-40:]):
                self.comprobar(f"La tesis de rubro: «{variante}», registro digital: 0000005.",
                               "no_literal", 84, "🟡", "🟡")

    def test_p4_otra_mencion_de_tesis_corta_el_vinculo(self) -> None:
        # Antes: "coincide" 🟢 con el rubro de OTRA tesis.
        resultado = self.comprobar(
            f"La tesis A lleva por título «{RUBRO_2006224}»; se invoca otra tesis con registro "
            f"digital 2006224.", "rubro_no_asociado", 84, "🟡", "🟡")
        self.assertTrue(any(a.startswith("🟡 RUBRO NO ASOCIADO CON CERTEZA: Registro digital "
                                         "2006224") for a in resultado["alerts"]))
        # Asociación incierta: tampoco 🔴 aunque el rubro sea de otra tesis.
        self.comprobar(f"La tesis A lleva por título «{RUBRO_2032506}»; se invoca otra tesis "
                       f"con registro digital 2006224.", "rubro_no_asociado", 84, "🟡", "🟡")
        # La etiqueta de la clave o del tipo no es otra tesis.
        self.comprobar(f"La jurisprudencia de rubro: «{RUBRO_2006224}», tesis P./J. 20/2014 "
                       f"(10a.), Tipo: Jurisprudencia, registro digital 2006224.",
                       "coincide", 95, "🟢", "🟢")
        # Varios rubros en el párrafo: tampoco se asocia.
        self.comprobar(f"Las tesis de rubros «{RUBRO_2032506}» y «{RUBRO_2006224}», registro "
                       f"digital 2006224.", "rubro_no_asociado", 84, "🟡", "🟡")

    def test_p5_vigencia_registrada_en_cualquier_campo(self) -> None:
        texto = f"La jurisprudencia de rubro: «{RUBRO_2006224}», registro digital: 2006224."
        casos = (
            # (campos de vigencia, estado, puntaje, semáforo de la tesis, veredicto)
            ({"estado_vigencia": "no_consultada", "vigencia": "superada"},
             "superada", 95, "🟢", "🔴"),
            ({"estado_vigencia": "vigente", "vigencia": "interrumpida"},
             "interrumpida", 95, "🟢", "🔴"),
            ({"estado_vigencia": "vigente", "vigencia": "rara"}, "en_conflicto", 84, "🟡", "🟡"),
        )
        for campos, estado, puntaje, semaforo, veredicto in casos:
            with self.subTest(campos=campos):
                self.guardar_tesis([{**TESIS_2006224, **campos}])
                resultado, tesis = self._auditar(texto)
                self.assertEqual((tesis["vvca"]["estado_vigencia"], tesis["vvca"]["score"],
                                  tesis["vvca"]["semaforo"]), (estado, puntaje, semaforo))
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], veredicto)
                self.assertEqual(resultado["avisos"], [])
        self.assertTrue(any(a.startswith("🟡 VIGENCIA EN CONFLICTO: Registro digital 2006224")
                            for a in resultado["alerts"]))

    def test_p6_encabezado_u_organo_nunca_es_rubro_rojo(self) -> None:
        # Antes: el órgano se tomaba como rubro → 🔴 discrepante (falso rojo).
        for texto in (
            f"{RUBRO_2006224}\n\nSUPREMA CORTE DE JUSTICIA DE LA NACIÓN\nRegistro digital: "
            f"2006224",
            "PRIMER TRIBUNAL COLEGIADO EN MATERIA PENAL DEL TERCER CIRCUITO\nSirve de apoyo "
            "la tesis con registro digital: 2006224.",
            "III. JURISPRUDENCIA APLICABLE AL CASO\nSirve de apoyo la tesis con registro "
            "digital: 2006224.",
        ):
            with self.subTest(texto=texto[-60:]):
                self.comprobar(texto, "sin_rubro_invocado", 84, "🟡", "🟡")

    def test_p7_telegram_muestra_todas_las_alertas_y_avisos_aparte(self) -> None:
        self.guardar_tesis([_tesis_ficticia(registro=f"000000{n}") for n in range(1, 5)])
        texto = (
            "Se invoca la tesis RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO NO ES "
            "COMPUTABLE, registro digital: 0000001.\n\n"
            "Se invoca una tesis con registro digital: 0000002.\n\n"
            "La tesis de rubro: «RUBRO FICTICIO DE PRUEBA VVCA. …», registro digital: 0000003."
            "\n\nSe invoca RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES COMPUTABLE, "
            "registro digital: 0000004."
        )
        resultado = self.auditar(texto)
        self.assertEqual((resultado["alerts_count"], resultado["avisos_count"]), (3, 3))
        telegram = ON.formato_telegram(resultado)
        self.assertIn("· 3 alertas · 3 avisos", telegram)
        for alerta in resultado["alerts"]:
            # Completa: con el rubro real, sin el recorte de 120 caracteres.
            self.assertIn(f"⚠️ {alerta}", telegram)
            self.assertIn("Rubro real: «RUBRO FICTICIO DE PRUEBA VVCA. EL PLAZO SINTÉTICO ES "
                          "COMPUTABLE»", alerta)
        self.assertIn("ℹ️ VIGENCIA NO CONSULTADA (no cambia el semáforo; verificar en "
                      "sjf2.scjn.gob.mx): Reg. 0000002, 0000003, 0000004", telegram)
        # Si no caben, lo dice y remite al JSON.
        muchas = dict(resultado, alerts=[f"🟡 ALERTA SINTÉTICA {n}: " + "x" * 200
                                         for n in range(40)])
        telegram = ON.formato_telegram(muchas)
        self.assertLessEqual(len(telegram), ON.LIMITE_TELEGRAM)
        self.assertRegex(telegram, r"… y \d+ alerta\(s\) más: el texto completo, con los "
                                   r"rubros, está en el JSON de la auditoría")

    def test_p0_el_puente_de_memoria_no_bloquea_por_vigencia_no_consultada(self) -> None:
        # Punto 0: con el auditor real, una tesis literal sin vigencia registrada ya no queda en
        # la memoria como "cita_bloqueada … criterio no_consultada".
        from itosturre.memoria.puente import eventos_desde_auditoria

        resultado, tesis = self._auditar(f"La jurisprudencia de rubro: «{RUBRO_2006224}», "
                                         f"registro digital: 2006224.")
        self.assertEqual(tesis["vvca"]["estado_vigencia"], "no_consultada")
        tipos = [e["event_type"] for e in eventos_desde_auditoria(resultado, caso="sintetico")]
        self.assertEqual(tipos, ["vvca_veredicto"])
        # Un rubro invertido sí se registra, con su motivo.
        invertido = RUBRO_2006224.replace("CONSTITUYEN EL", "NO CONSTITUYEN EL")
        resultado, _ = self._auditar(f"La jurisprudencia de rubro: «{invertido}», registro "
                                     f"digital: 2006224.")
        bloqueadas = [e for e in eventos_desde_auditoria(resultado)
                      if e["event_type"] == "cita_bloqueada"]
        self.assertEqual(len(bloqueadas), 1)
        self.assertIn("sentido invertido", bloqueadas[0]["summary"])

    def test_p8_cobertura_incompleta_de_un_registro_no_se_calla(self) -> None:
        resultado = self.auditar(f"La jurisprudencia de rubro: «{RUBRO_2006224}», registro "
                                 f"digital 2006224 así como 2032506.")
        self.assertEqual(
            [estado for estado in self.estados(resultado) if estado[0] != "Art. 16"],
            [("registro digital 2006224", "verified", "corpus_jurisprudencia"),
             ("registro digital 2006224 así como 2032506", "not_verifiable",
              "cobertura_extraccion")],
        )
        self.assertTrue(any(a.startswith("🟡 COBERTURA INCOMPLETA: 'registro digital 2006224 "
                                         "así como 2032506'") for a in resultado["alerts"]))
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")


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

    def test_R4_D11_verde_enuncia_solo_lo_verificado(self) -> None:
        # Antes: "Normativa y jurisprudencia verificadas" aunque no hubiera tesis.
        for posicionales in ((92.0, None, 0, 0, 0), (92.0, 0.0, 0, 0, 0)):
            with self.subTest(posicionales=posicionales):
                veredicto = veredicto_global(*posicionales, articulos_total=1)
                self.assertEqual((veredicto["semaforo"], veredicto["razon"]),
                                 ("🟢", "Normativa verificada; sin tesis citadas"))
        # Sin el dato nuevo (llamada anterior a R4c) la razón también es honesta.
        self.assertEqual(veredicto_global(92.0, 0.0, 0, 0, 0)["razon"],
                         "Normativa verificada; sin tesis citadas")
        self.assertEqual(veredicto_global(92.0, 95.0, 0, 0, 2, articulos_total=1)["razon"],
                         "Normativa y jurisprudencia verificadas")
        # El 🟢 al abogado dice su alcance.
        disclaimer = disclaimer_graduado(veredicto_global(92.0, None, 0, 0, 0, articulos_total=1))
        self.assertEqual(disclaimer["nivel"], "🟢")
        self.assertIn("no significa que lo citado diga lo que el escrito afirma",
                      disclaimer["texto"])

    def test_R4_D12_sin_articulos_no_es_insuficiencia(self) -> None:
        # Con articulos_total=0 la dimensión normativa no tiene citas: no hay insuficiencia.
        # Ronda 2 de R4c: el 🟢 de "solo tesis" queda retenido (🟡); R4d lo mantiene
        # (adjudicación del 2-oct-2026) hasta validar el cotejo con un corpus de tesis mayor.
        veredicto = veredicto_global(None, 95.0, 0, 0, 1, articulos_total=0)
        self.assertEqual(
            (veredicto["apto"], veredicto["semaforo"], veredicto["razon"]),
            (False, "🟡", "Jurisprudencia localizada; 🟢 de solo tesis retenido (transitorio) "
                          "hasta validar el cotejo del rubro con un corpus de tesis mayor"),
        )
        import scoring_vvca
        with mock.patch.object(scoring_vvca, "RETENER_VERDE_SOLO_TESIS", False):
            veredicto = veredicto_global(None, 95.0, 0, 0, 1, articulos_total=0)
        self.assertEqual((veredicto["apto"], veredicto["semaforo"], veredicto["razon"]),
                         (True, "🟢", "Jurisprudencia verificada; sin artículos citados"))
        # Sin artículos ni tesis no hay nada verificado: 🟡 con su razón verdadera (no un 🟢
        # vacío; antes, "RAG 0.0" insuficiente).
        veredicto = veredicto_global(None, None, 0, 0, 0, articulos_total=0)
        self.assertEqual(
            (veredicto["apto"], veredicto["semaforo"], veredicto["razon"]),
            (False, "🟡",
             "Sin citas detectadas: no hay normativa ni jurisprudencia que verificar"),
        )
        # Artículos sin puntaje (llamada directa): insuficiencia explícita, nunca 🟢.
        veredicto = veredicto_global(None, None, 0, 0, 0, articulos_total=2)
        self.assertEqual((veredicto["semaforo"], veredicto["razon"]),
                         ("🟡", "Artículos con verificación insuficiente (RAG: sin puntaje)"))
        # Compatibilidad: sin ``articulos_total`` no se distingue "sin artículos" de "0
        # puntos" y la regla anterior se conserva (Gold Set v1).
        veredicto = veredicto_global(0.0, 95.0, 0, 0, 1)
        self.assertEqual((veredicto["semaforo"], veredicto["razon"]),
                         ("🟡", "Artículos con verificación insuficiente (RAG: 0.0)"))


if __name__ == "__main__":
    unittest.main()
