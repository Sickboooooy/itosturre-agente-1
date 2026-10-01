"""Pruebas del cotejo de identidad (C9): paquete de evidencia, ``identidad.py``, reglas
PL-015 … PL-017, reporte y CLI (``cotejar`` y ``evidencia agregar-*``).

Los paquetes se arman en directorios temporales a partir de los fixtures oficiales
reales de ``tests/fixtures/evidencia/`` (no se crean fixtures nuevos). Los datos reales
se copian literalmente de esos fixtures y una prueba comprueba que lo están; las
variantes sintéticas van rotuladas y son obviamente falsas (registro ``0000001``, clave
``P./J. 0/0000``, ``RUBRO SINTÉTICO DE PRUEBA``, fechas de 1800, PDF sintéticos). Los
PDF de las leyes no se versionan: el "extractor sintético de prueba" que se inyecta
devuelve las páginas del fixture para el PDF sintético de cada ley. Sin red ni
dependencias (la prueba con PyMuPDF se omite si no está instalado).
"""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import plan_audit
from itosturre.evidencia.fuentes import url_leyesbiblio, url_tesis_sjf
from itosturre.evidencia.huellas import json_canonico, sha256_bytes
from itosturre.evidencia.leyesbiblio import limpiar_documento
from itosturre.evidencia.leyesbiblio import registro_evidencia as registro_ley
from itosturre.evidencia.paquete import (
    DIR_OBJETOS,
    DIR_REGISTROS,
    ErrorPaquete,
    ObjetoCorrupto,
    RegistroRechazado,
    _crear_exclusivo,
    cargar_paquete,
    crear_paquete,
    es_enlace,
    guardar_evidencia,
    guardar_registro,
)
from itosturre.evidencia.sjf import derivado_canonico, parsear_tesis
from itosturre.evidencia.sjf import registro_evidencia as registro_tesis
from itosturre.plan import (
    CONFORME,
    DISCREPANTE,
    ESTADO_SOSTENIBLE,
    NO_COTEJADO,
    REGLAS,
    REGLAS_COTEJO,
    SIN_EVIDENCIA,
    Extractor,
    cotejar_ledger,
    esta_bloqueado,
    lint_ledger,
    reporte_markdown,
)
from itosturre.plan.identidad import (
    articulo_de_ubicacion,
    clave_articulo,
    fechas_declaradas,
    forma_rubro,
    ordenamiento_de,
    rotulado_como_sintetico,
)
from itosturre.plan.lint import ALTA, BLOQUEANTE
from scripts.evaluate_plan_gold_set import evaluar_gold_set

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "evidencia"
PLAN_AUDIT = REPO / "plan_audit.py"
GOLD_SET = REPO / "tests" / "fixtures" / "plan_gold_set_v1.json"
HUMANO = "Lic. Persona Ficticia"
FECHA_SINTETICA = "1800-01-01"  # las capturas de 2006224 y de las leyes no registraron fecha
FECHA_2031931 = "2026-10-01T19:57Z"  # aportada por el operador (manifiesto de fixtures)

# PDF sintéticos (los originales reales no se versionan): bytes que no son ningún PDF oficial.
PDF_SINTETICO = {
    nombre: f"%PDF sintetico de prueba ({nombre}): no es un documento oficial\n".encode("ascii")
    for nombre in ("CNPP", "CPF", "OTRA")
}
EXTRACTOR_PRUEBA = "extractor sintético de prueba (PDF sintético → páginas del fixture)"
VERSION_PRUEBA = "0"

# ── Literales copiados de los fixtures oficiales (una prueba verifica que lo son) ──
RUBRO_2006224 = (
    "DERECHOS HUMANOS CONTENIDOS EN LA CONSTITUCIÓN Y EN LOS TRATADOS INTERNACIONALES. "
    "CONSTITUYEN EL PARÁMETRO DE CONTROL DE REGULARIDAD CONSTITUCIONAL, PERO CUANDO EN LA "
    "CONSTITUCIÓN HAYA UNA RESTRICCIÓN EXPRESA AL EJERCICIO DE AQUÉLLOS, SE DEBE ESTAR A LO "
    "QUE ESTABLECE EL TEXTO CONSTITUCIONAL."
)
RUBRO_2031931 = (
    "RECURSO DE REVOCACIÓN CONTRA LA RESOLUCIÓN FINAL PREVISTA EN EL ARTÍCULO 69-B, PÁRRAFO "
    "CUARTO, DEL CÓDIGO FISCAL DE LA FEDERACIÓN. EL PLAZO PARA INTERPONERLO COMIENZA A PARTIR "
    "DE SU NOTIFICACIÓN A TRAVÉS DEL BUZÓN TRIBUTARIO."
)
RUBRO_2032506 = (
    "SUSPENSIÓN PROVISIONAL EN AMPARO INDIRECTO. ES IMPROCEDENTE CONTRA EL SISTEMA NORMATIVO "
    "CONFORMADO POR EL ARTÍCULO 162, FRACCIÓN VI, PÁRRAFOS SEGUNDO Y TERCERO, DE LA LEY "
    "ADUANERA, Y LA REGLA 1.4.14. DE LAS REGLAS GENERALES DE COMERCIO EXTERIOR PARA 2026."
)
LITERALES_TESIS = {
    "2006224": {
        "rubro": RUBRO_2006224,
        "fragmento_texto": "los derechos humanos, en su conjunto, constituyen el parámetro",
        "clave": "P./J. 20/2014 (10a.)",
        "epoca": "Décima Época",
        "tipo": "Jurisprudencia",
        "instancia": "Pleno",
        "publicacion": "viernes 25 de abril de 2014",
        "obligatoriedad": "lunes 28 de abril de 2014",
    },
    "2031931": {
        "rubro": RUBRO_2031931,
        "fragmento_texto": "artículo 69-B del Código Fiscal de la Federación",
        "clave": "I.24o.A.22 A (11a.)",
        "epoca": "Duodécima Época",
        "tipo": "Aislada",
        "instancia": "Tribunales Colegiados de Circuito",
    },
    "2032506": {
        "rubro": RUBRO_2032506,
        "clave": "VI.3o.A.55 A (12a.)",
        "epoca": "Duodécima Época",
        "tipo": "Aislada",
        "instancia": "Tribunales Colegiados de Circuito",
    },
}
# Código Nacional de Procedimientos Penales, página 1 del compilado (fixture).
CNPP_ART_1O = "Las disposiciones de este Código son de orden público y de observancia general en toda la República"
CNPP_ART_2O = (
    "Este Código tiene por objeto establecer las normas que han de observarse en la "
    "investigación, el procesamiento y la sanción de los delitos"
)
CNPP_ART_3O = "Para los efectos de este Código, según corresponda, se entenderá por:"
CNPP_ULTIMA_REFORMA = "2025-11-28"
# Código Penal Federal, página 1 (fixture). El "ARTICULO 1°.-" de la p. 151 es de un decreto.
CPF_ART_1O = "Este Código se aplicará en toda la República para los delitos del orden federal."


# ── Extractor sintético y constructores ──────────────────────────────────────


def paginas_fixture(nombre: str) -> dict:
    return json.loads((FIXTURES / f"leyesbiblio_{nombre}.json").read_text(encoding="utf-8"))


def paginas_completas(nombre: str) -> list[str]:
    """Todas las páginas del PDF: las del fixture en su lugar y vacías las demás."""
    datos = paginas_fixture(nombre)
    paginas = [""] * datos["total_paginas_pdf"]
    for pagina in datos["paginas"]:
        paginas[pagina["numero"] - 1] = pagina["texto"]
    return paginas


def extraer_prueba(original: bytes) -> list[str]:
    for nombre in ("CNPP", "CPF"):
        if original == PDF_SINTETICO[nombre]:
            return paginas_completas(nombre)
    if original == PDF_SINTETICO["OTRA"]:
        return paginas_completas("CPF")  # "otro PDF": páginas que no son las del CNPP
    raise ValueError("no es un PDF sintético de prueba")


EXTRACTORES = (Extractor(EXTRACTOR_PRUEBA, VERSION_PRUEBA, extraer_prueba),)


def agregar_tesis(raiz: Path, registro: str, fecha: str = FECHA_SINTETICA) -> dict:
    """Registra en el paquete el render real del fixture; devuelve el registro."""
    original = (FIXTURES / f"sjf_{registro}.txt").read_bytes()
    evidencia = registro_tesis(original, url=url_tesis_sjf(registro), fecha_consulta=fecha,
                               registro_esperado=registro)
    derivado = derivado_canonico(parsear_tesis(original.decode("utf-8")))
    guardar_evidencia(raiz, evidencia, original=original, derivado=derivado)
    return evidencia


def documento_ley(nombre: str):
    datos = paginas_fixture(nombre)
    return limpiar_documento(
        [p["texto"] for p in datos["paginas"]],
        numeros=[p["numero"] for p in datos["paginas"]],
        total_paginas=datos["total_paginas_pdf"],
    )


def agregar_ley(raiz: Path, nombre: str = "CNPP", fecha: str = FECHA_SINTETICA, *,
                archivo: str | None = None, pdf: bytes | None = None) -> dict:
    documento = documento_ley(nombre)
    archivo = archivo or f"{nombre}.pdf"
    pdf = pdf if pdf is not None else PDF_SINTETICO[nombre]
    evidencia = registro_ley(
        documento,
        archivo=archivo,
        url=url_leyesbiblio(archivo),
        fecha_consulta=fecha,
        original_sha256=sha256_bytes(pdf),
        original_bytes=len(pdf),
        extractor=EXTRACTOR_PRUEBA,
        version_extractor=VERSION_PRUEBA,
    )
    guardar_evidencia(raiz, evidencia, original=pdf, derivado=documento.texto,
                      texto_extraido=documento.texto_extraido)
    return evidencia


def identificacion(numero: str, /, **cambios: object) -> dict:
    """``identificacion_criterio`` con los datos literales del fixture."""
    literal = LITERALES_TESIS[numero]
    datos = {
        "rubro": literal["rubro"],
        "clave": literal["clave"],
        "organo": literal["instancia"],
        "epoca": literal["epoca"],
        "registro": numero,
        "integracion": "Dato sintético de prueba (no cotejado)",
        "publicacion": literal.get("publicacion", "Dato sintético de prueba (no cotejado)"),
        "obligatoriedad": literal.get("obligatoriedad", "No aplica (dato sintético de prueba)"),
        "fuerza_vinculante": "[J] Obligatoria" if literal["tipo"] == "Jurisprudencia" else "[TA] Orientadora",
        "alcance": "Dato sintético de prueba (no cotejado)",
    }
    datos.update(cambios)
    return datos


def evidencia_tesis(id_: str, registro: dict, **cambios: object) -> dict:
    metadatos = registro["metadatos"]
    datos = {
        "id": id_,
        "naturaleza": "portal_oficial",
        "url": registro["fuente"]["url"],
        "ubicacion": f"Registro digital {metadatos['registro']}",
        "extracto": metadatos["rubro"],
        "fecha_consulta": registro["fuente"]["fecha_consulta"][:10],
        "sha256_documento": registro["original"]["sha256"],
        "consulta": None,
        "resultados": None,
    }
    datos.update(cambios)
    return datos


def evidencia_ley(id_: str, ubicacion: str, extracto: str | None, nombre: str = "CNPP", *,
                  archivo: str | None = None, **cambios: object) -> dict:
    datos = {
        "id": id_,
        "naturaleza": "compilado_oficial",
        "url": url_leyesbiblio(archivo or f"{nombre}.pdf"),
        "ubicacion": ubicacion,
        "extracto": extracto,
        "fecha_consulta": FECHA_SINTETICA,
        "sha256_documento": sha256_bytes(PDF_SINTETICO[nombre]),
        "consulta": None,
        "resultados": None,
    }
    datos.update(cambios)
    return datos


def afirmacion(id_: str, evidencias: list[str], *, tipo: str = "texto_normativo",
               estado: str = "VERIFICADO", ident: dict | None = None, texto: str | None = None,
               referencias: list[str] | None = None) -> dict:
    datos = {
        "id": id_,
        "texto": texto or f"Afirmación sintética de prueba {id_}.",
        "tipo": tipo,
        "autor": "humano",
        "referencias": referencias or [],
        "verificacion": {"estado": estado, "evidencias": evidencias, "motivo": ""},
        "aprobacion": None,
    }
    if ident is not None:
        datos["identificacion_criterio"] = ident
    return datos


def ledger(afirmaciones: list[dict], evidencias: list[dict], decisiones: list[dict] | None = None) -> dict:
    return {
        "schema_version": "plan-ledger/1.0",
        "plan": {"id": "PLAN-C9", "titulo": "Plan sintético de cotejo", "fecha_documento": "2026-10-01"},
        "afirmaciones": afirmaciones,
        "evidencias": evidencias,
        "contradicciones": [],
        "decisiones": decisiones or [],
    }


def _campos(par) -> list[str]:
    return [m.campo for m in par.motivos]


def _detalles(motivos) -> str:
    return " | ".join(m.detalle for m in motivos)


class _ConPaquete(unittest.TestCase):
    def setUp(self) -> None:
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.base = Path(temporal.name)
        self.raiz = self.base / "paquete"

    def nuevo(self) -> None:
        """Paquete nuevo y vacío dentro de la misma prueba."""
        self.raiz = Path(tempfile.mkdtemp(dir=self.base)) / "paquete"

    def paquete(self):
        return cargar_paquete(self.raiz)

    def cotejar(self, libro: dict, extractores=EXTRACTORES):
        return cotejar_ledger(libro, self.paquete(), extractores=extractores)

    def cotejar_tesis(self, registro: str, ident: dict | None, *, fecha: str = FECHA_SINTETICA,
                      texto: str | None = None, referencias: list[str] | None = None,
                      tipo: str = "criterio_judicial", **cambios_evidencia: object):
        evidencia = agregar_tesis(self.raiz, registro, fecha)
        libro = ledger(
            [afirmacion("A1", ["E1"], tipo=tipo, ident=ident, texto=texto, referencias=referencias)],
            [evidencia_tesis("E1", evidencia, **cambios_evidencia)],
        )
        return self.cotejar(libro).pares[0]

    def cotejar_ley(self, ubicacion: str, extracto: str | None, nombre: str = "CNPP", *,
                    texto: str | None = None, extractores=EXTRACTORES, **cambios: object):
        agregar_ley(self.raiz, nombre)
        libro = ledger([afirmacion("A1", ["E1"], texto=texto)],
                       [evidencia_ley("E1", ubicacion, extracto, nombre, **cambios)])
        return self.cotejar(libro, extractores).pares[0]


# ── Fixtures y literales ─────────────────────────────────────────────────────


class LiteralesTests(unittest.TestCase):
    def test_los_literales_vienen_de_los_fixtures(self) -> None:
        for registro, literal in LITERALES_TESIS.items():
            texto = (FIXTURES / f"sjf_{registro}.txt").read_bytes().decode("utf-8")
            for campo, valor in literal.items():
                with self.subTest(registro=registro, campo=campo):
                    self.assertIn(valor, texto)
        for nombre, extractos in (("CNPP", (CNPP_ART_1O, CNPP_ART_3O)), ("CPF", (CPF_ART_1O,))):
            primera = paginas_fixture(nombre)["paginas"][0]["texto"]
            for extracto in extractos:
                with self.subTest(ley=nombre, extracto=extracto[:30]):
                    self.assertIn(extracto, primera)
        primera = paginas_fixture("CNPP")["paginas"][0]["texto"]
        self.assertIn(" ".join(CNPP_ART_2O.split()), " ".join(primera.split()))
        self.assertIn("Última Reforma DOF 28-11-2025", primera)


# ── Paquete de evidencia ─────────────────────────────────────────────────────


class PaqueteTests(_ConPaquete):
    def test_direccionado_por_contenido_y_carga(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        archivos = list((self.raiz / DIR_REGISTROS).iterdir())
        self.assertEqual(len(archivos), 1)
        datos = archivos[0].read_bytes()
        self.assertEqual(datos, json_canonico(registro).encode("utf-8"))
        self.assertEqual(archivos[0].name, f"{sha256_bytes(datos)}.json")
        objetos = {ruta.name for ruta in (self.raiz / DIR_OBJETOS).iterdir()}
        self.assertIn(registro["original"]["sha256"], objetos)
        self.assertIn(registro["derivado"]["sha256"], objetos)
        paquete = self.paquete()
        self.assertEqual(paquete.problemas, ())
        self.assertEqual(len(paquete.buscar(registro["original"]["sha256"], registro["fuente"]["url"])), 1)
        self.assertEqual(paquete.objeto(registro["original"]["sha256"]),
                         (FIXTURES / "sjf_2006224.txt").read_bytes())

    def test_guardar_dos_veces_es_inofensivo(self) -> None:
        agregar_tesis(self.raiz, "2006224")
        agregar_tesis(self.raiz, "2006224")
        self.assertEqual(len(list((self.raiz / DIR_REGISTROS).iterdir())), 1)

    def test_nunca_sobrescribe_un_objeto_con_otro_contenido(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        ruta = self.raiz / DIR_OBJETOS / registro["original"]["sha256"]
        ruta.write_bytes(b"contenido alterado sintetico")
        with self.assertRaises(ObjetoCorrupto):
            agregar_tesis(self.raiz, "2006224")
        self.assertEqual(ruta.read_bytes(), b"contenido alterado sintetico")

    def test_lectura_verifica_la_huella(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        paquete = self.paquete()
        self.assertIsNone(paquete.objeto("0" * 64))
        with self.assertRaises(ValueError):
            paquete.objeto("../registros")
        (self.raiz / DIR_OBJETOS / registro["derivado"]["sha256"]).write_bytes(b"x")
        with self.assertRaises(ObjetoCorrupto):
            paquete.objeto(registro["derivado"]["sha256"])

    def test_registro_sin_integridad_no_se_guarda(self) -> None:
        original = (FIXTURES / "sjf_2031931.txt").read_bytes()
        registro = registro_tesis(original, url=url_tesis_sjf("2031931"), fecha_consulta=FECHA_2031931)
        registro["metadatos"]["epoca"] = "Undécima Época"  # "corregir" la fuente: contenido falso
        derivado = derivado_canonico(parsear_tesis(original.decode("utf-8")))
        with self.assertRaises(RegistroRechazado) as contexto:
            guardar_evidencia(self.raiz, registro, original=original, derivado=derivado)
        self.assertTrue(any(p.startswith("metadatos.epoca") for p in contexto.exception.problemas))
        self.assertFalse((self.raiz / DIR_REGISTROS).exists() and any((self.raiz / DIR_REGISTROS).iterdir()))

    def test_ley_sin_texto_extraido_no_se_guarda(self) -> None:
        documento = documento_ley("CNPP")
        registro = registro_ley(
            documento, archivo="CNPP.pdf", url=url_leyesbiblio("CNPP.pdf"), fecha_consulta=FECHA_SINTETICA,
            original_sha256=sha256_bytes(PDF_SINTETICO["CNPP"]), original_bytes=len(PDF_SINTETICO["CNPP"]),
            extractor=EXTRACTOR_PRUEBA, version_extractor=VERSION_PRUEBA,
        )
        with self.assertRaises(RegistroRechazado):
            guardar_evidencia(self.raiz, registro, original=PDF_SINTETICO["CNPP"], derivado=documento.texto)

    def test_segundo_registro_del_mismo_documento_se_rechaza(self) -> None:
        agregar_tesis(self.raiz, "2006224", "1800-01-01")
        with self.assertRaises(RegistroRechazado):
            agregar_tesis(self.raiz, "2006224", "1800-01-02")

    def test_registro_editado_a_mano_queda_marcado(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        ruta = next((self.raiz / DIR_REGISTROS).iterdir())
        ruta.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
        paquete = self.paquete()
        self.assertTrue(paquete.problemas)
        self.assertFalse(paquete.registros[0].integro)

    def test_archivos_ajenos_y_temporales(self) -> None:
        agregar_tesis(self.raiz, "2006224")
        (self.raiz / DIR_REGISTROS / "nota.txt").write_text("x", encoding="utf-8")
        (self.raiz / DIR_REGISTROS / ".tmp-huerfano").write_bytes(b"")
        problemas = self.paquete().problemas
        self.assertTrue(any("ajeno" in p for p in problemas))
        self.assertTrue(any("temporal" in p for p in problemas))

    def test_rutas_que_no_son_paquete(self) -> None:
        with self.assertRaises(ErrorPaquete):
            cargar_paquete(self.raiz / "no-existe")
        self.raiz.mkdir(parents=True)
        with self.assertRaises(ErrorPaquete):
            cargar_paquete(self.raiz)

    # Punto 8: publicación que falla si el destino existe, sin comprobar-y-reemplazar.
    def test_publicacion_exclusiva_sin_reemplazo(self) -> None:
        with patch("itosturre.evidencia.paquete.os.replace", side_effect=AssertionError("no se reemplaza")):
            registro = agregar_tesis(self.raiz, "2006224")
        self.assertEqual(self.paquete().objeto(registro["original"]["sha256"]),
                         (FIXTURES / "sjf_2006224.txt").read_bytes())
        destino = self.raiz / DIR_OBJETOS / ("a" * 64)
        self.assertTrue(_crear_exclusivo(destino, b"uno"))
        self.assertFalse(_crear_exclusivo(destino, b"dos"))  # O_EXCL: ya existe
        self.assertEqual(destino.read_bytes(), b"uno")

    def test_publicacion_sin_enlaces_duros_usa_creacion_exclusiva(self) -> None:
        with patch("itosturre.evidencia.paquete.os.link", side_effect=OSError("sin enlaces duros")):
            registro = agregar_tesis(self.raiz, "2006224")
            ruta = self.raiz / DIR_OBJETOS / registro["original"]["sha256"]
            self.assertEqual(ruta.read_bytes(), (FIXTURES / "sjf_2006224.txt").read_bytes())
            ruta.write_bytes(b"contenido alterado sintetico")
            with self.assertRaises(ObjetoCorrupto):
                agregar_tesis(self.raiz, "2006224")
        self.assertEqual(ruta.read_bytes(), b"contenido alterado sintetico")
        self.assertFalse([r for r in (self.raiz / DIR_OBJETOS).iterdir() if r.name.startswith(".tmp-")])


# ── Punto 2: enlaces simbólicos y puntos de reanálisis ───────────────────────


def _quitar_enlace(ruta: Path) -> None:
    if os.path.lexists(ruta):
        try:
            os.unlink(ruta)
        except OSError:
            os.rmdir(ruta)  # junction de Windows


class EnlacesTests(_ConPaquete):
    def _enlace_archivo(self, enlace: Path, objetivo: Path) -> None:
        try:
            os.symlink(objetivo, enlace)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"el sistema no permite crear enlaces simbólicos de archivo ({error})")
        self.addCleanup(_quitar_enlace, enlace)

    def _enlace_directorio(self, enlace: Path, objetivo: Path) -> None:
        try:
            os.symlink(objetivo, enlace, target_is_directory=True)
        except (OSError, NotImplementedError):
            try:
                import _winapi  # junction: no exige privilegios en Windows

                _winapi.CreateJunction(str(objetivo), str(enlace))
            except Exception as error:  # noqa: BLE001
                self.skipTest(f"el sistema no permite crear enlaces de directorio ({error})")
        self.addCleanup(_quitar_enlace, enlace)

    def test_detecta_enlaces_de_directorio(self) -> None:
        objetivo = self.base / "objetivo"
        objetivo.mkdir()
        enlace = self.base / "enlace"
        self._enlace_directorio(enlace, objetivo)
        self.assertTrue(es_enlace(enlace))
        self.assertFalse(es_enlace(objetivo))
        self.assertFalse(es_enlace(self.base / "no-existe"))

    def test_raiz_enlazada_se_rechaza(self) -> None:
        agregar_tesis(self.raiz, "2006224")
        enlace = self.base / "paquete-enlace"
        self._enlace_directorio(enlace, self.raiz)
        with self.assertRaisesRegex(ErrorPaquete, "enlace"):
            cargar_paquete(enlace)
        with self.assertRaisesRegex(ErrorPaquete, "enlace"):
            crear_paquete(enlace)
        with self.assertRaises(ErrorPaquete):
            agregar_tesis(enlace, "2031931", FECHA_2031931)

    def test_registros_u_objetos_enlazados_se_rechazan(self) -> None:
        for carpeta in (DIR_REGISTROS, DIR_OBJETOS):
            with self.subTest(carpeta=carpeta):
                self.nuevo()
                agregar_tesis(self.raiz, "2006224")
                fuera = self.raiz.parent / f"fuera-{carpeta}"
                (self.raiz / carpeta).rename(fuera)
                self._enlace_directorio(self.raiz / carpeta, fuera)
                with self.assertRaisesRegex(ErrorPaquete, "enlace"):
                    cargar_paquete(self.raiz)
                with self.assertRaisesRegex(ErrorPaquete, "enlace"):
                    crear_paquete(self.raiz)
                ledger_ruta = self.raiz.parent / "ledger.json"
                ledger_ruta.write_text(json.dumps(ledger([afirmacion("A1", [])], [])), encoding="utf-8")
                resultado = subprocess.run(
                    [sys.executable, str(PLAN_AUDIT), "cotejar", "--ledger", str(ledger_ruta),
                     "--paquete", str(self.raiz)],
                    cwd=REPO, capture_output=True, text=True, encoding="utf-8", check=False,
                )
                self.assertEqual(resultado.returncode, 2, resultado.stdout)
                self.assertIn("enlace", resultado.stderr)

    def test_objeto_enlazado_es_discrepante(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        ruta = self.raiz / DIR_OBJETOS / registro["derivado"]["sha256"]
        fuera = self.base / "copia-fuera"
        fuera.write_bytes(ruta.read_bytes())  # mismo contenido: la huella sola no lo delata
        ruta.unlink()
        self._enlace_archivo(ruta, fuera)
        with self.assertRaisesRegex(ObjetoCorrupto, "enlace"):
            self.paquete().objeto(registro["derivado"]["sha256"])
        par = self.cotejar(ledger([afirmacion("A1", ["E1"], tipo="criterio_judicial",
                                              ident=identificacion("2006224"))],
                                  [evidencia_tesis("E1", registro)])).pares[0]
        self.assertEqual((par.resultado, par.paso, _campos(par)), (DISCREPANTE, "c", ["derivado"]))
        self.assertIn("enlace", par.motivos[0].detalle)

    def test_registro_enlazado_no_se_lee(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        ruta = next((self.raiz / DIR_REGISTROS).iterdir())
        fuera = self.base / "registro-fuera.json"
        fuera.write_bytes(ruta.read_bytes())
        ruta.unlink()
        self._enlace_archivo(ruta, fuera)
        paquete = self.paquete()
        self.assertEqual(paquete.registros, ())
        self.assertTrue(any("enlace" in p for p in paquete.problemas))
        par = self.cotejar(ledger([afirmacion("A1", ["E1"], tipo="criterio_judicial",
                                              ident=identificacion("2006224"))],
                                  [evidencia_tesis("E1", registro)])).pares[0]
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "a"))

    def test_no_se_publica_sobre_un_enlace(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        ruta = self.raiz / DIR_OBJETOS / registro["original"]["sha256"]
        ruta.unlink()
        fuera = self.base / "victima.txt"
        fuera.write_bytes(b"archivo ajeno sintetico")
        self._enlace_archivo(ruta, fuera)
        with self.assertRaisesRegex(ObjetoCorrupto, "enlace"):
            agregar_tesis(self.raiz, "2006224")
        self.assertEqual(fuera.read_bytes(), b"archivo ajeno sintetico")


# ── Cotejo de tesis ──────────────────────────────────────────────────────────


class CotejoTesisTests(_ConPaquete):
    def test_2006224_conforme_con_identificacion_literal(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"),
                                 texto="Afirmación sintética sobre el registro digital 2006224.")
        self.assertEqual(par.resultado, CONFORME, par.motivos)
        self.assertIsNone(par.paso)
        self.assertEqual(par.motivos, ())
        self.assertFalse(par.requiere_decision_humana)
        self.assertEqual(par.advertencias_fuente, ())
        self.assertEqual(par.documento_fuente, "registro digital 2006224")
        no_cotejados = {nota.campo for nota in par.notas}
        self.assertTrue({"organo", "integracion", "alcance"} <= no_cotejados)
        self.assertNotIn("publicacion", no_cotejados)  # fecha interpretable: sí se cotejó
        self.assertNotIn("obligatoriedad", no_cotejados)

    def test_registro_distinto_es_discrepante_antes_de_mirar_el_rubro(self) -> None:
        ident = identificacion("2006224", registro="0000001", rubro="RUBRO SINTÉTICO DE PRUEBA.")
        par = self.cotejar_tesis("2006224", ident)
        self.assertEqual(par.resultado, DISCREPANTE)
        self.assertEqual(par.paso, "d")
        self.assertEqual(_campos(par), ["registro"])

    def test_rubro_con_un_caracter_cambiado(self) -> None:
        # Variante sintética: una "X" en lugar de la "O" final de "PARÁMETRO".
        alterado = RUBRO_2006224.replace("PARÁMETRO", "PARÁMETRX")
        par = self.cotejar_tesis("2006224", identificacion("2006224", rubro=alterado))
        self.assertEqual(par.resultado, DISCREPANTE)
        self.assertEqual(par.paso, "f")
        self.assertEqual(_campos(par), ["rubro"])

    def test_rubro_con_acentos_mayusculas_comillas_o_sin_punto_final(self) -> None:
        sin_acentos = RUBRO_2006224.lower().replace("ó", "o").replace("á", "a").replace("é", "e")
        for variante in (sin_acentos, RUBRO_2006224.rstrip("."), f"“{RUBRO_2006224}”"):
            with self.subTest(variante=variante[:40]):
                self.nuevo()
                par = self.cotejar_tesis("2006224", identificacion("2006224", rubro=variante))
                self.assertEqual(par.resultado, CONFORME, par.motivos)

    def test_solo_se_ignora_el_punto_final(self) -> None:
        sin_punto_interno = RUBRO_2006224.replace("INTERNACIONALES. CONSTITUYEN", "INTERNACIONALES CONSTITUYEN")
        par = self.cotejar_tesis("2006224", identificacion("2006224", rubro=sin_punto_interno))
        self.assertEqual(par.resultado, DISCREPANTE)
        self.assertEqual(forma_rubro("ABC."), forma_rubro("abc"))

    def test_2031931_conforme_requiere_decision_humana(self) -> None:
        par = self.cotejar_tesis("2031931", identificacion("2031931"), fecha=FECHA_2031931)
        self.assertEqual(par.resultado, CONFORME, par.motivos)
        self.assertTrue(par.requiere_decision_humana)
        self.assertIn("epoca_discrepante", [a["codigo"] for a in par.advertencias_fuente])

    def test_2031931_epoca_de_la_clave_se_acepta_con_reserva(self) -> None:
        par = self.cotejar_tesis("2031931", identificacion("2031931", epoca="Undécima Época"), fecha=FECHA_2031931)
        self.assertEqual(par.resultado, CONFORME)
        self.assertTrue(par.requiere_decision_humana)
        self.assertIn("epoca", [n.campo for n in par.notas if n.clase == "observacion"])
        self.nuevo()
        par = self.cotejar_tesis("2031931", identificacion("2031931", epoca="Décima Época"), fecha=FECHA_2031931)
        self.assertEqual(par.resultado, DISCREPANTE)

    def test_tipo_J_frente_a_aislada(self) -> None:
        par = self.cotejar_tesis("2032506", identificacion("2032506", fuerza_vinculante="[J] Obligatoria"),
                                 fecha=FECHA_2031931)
        self.assertEqual(par.resultado, DISCREPANTE)
        self.assertEqual(_campos(par), ["fuerza_vinculante"])

    def test_fuerza_vinculante_no_interpretable(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224", fuerza_vinculante="[PR] criterio orientador"))
        self.assertEqual(par.resultado, SIN_EVIDENCIA)
        self.assertEqual(_campos(par), ["fuerza_vinculante"])

    def test_clave_sin_sufijo_de_epoca_no_es_conforme(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224", clave="P./J. 20/2014"))
        self.assertEqual((par.resultado, _campos(par)), (SIN_EVIDENCIA, ["clave"]))
        par = self.cotejar_tesis("2006224", identificacion("2006224", clave="P./J.20/2014(10a.)"))
        self.assertEqual(par.resultado, CONFORME)  # espacios no cuentan

    def test_campos_criticos_ausentes_o_pendientes(self) -> None:
        ident = identificacion("2006224")
        del ident["clave"]
        self.assertEqual(self.cotejar_tesis("2006224", ident).resultado, SIN_EVIDENCIA)
        ident = identificacion("2006224", rubro="[VERIFICAR EN SJF]")
        self.assertEqual(self.cotejar_tesis("2006224", ident).resultado, SIN_EVIDENCIA)
        self.assertEqual(self.cotejar_tesis("2006224", None).resultado, SIN_EVIDENCIA)

    def test_fechas_de_publicacion_y_obligatoriedad(self) -> None:
        self.assertEqual(
            self.cotejar_tesis("2006224", identificacion("2006224", publicacion="2014-04-25")).resultado, CONFORME
        )
        par = self.cotejar_tesis("2006224", identificacion("2006224", publicacion="1800-01-01"))
        self.assertEqual((par.resultado, _campos(par)), (DISCREPANTE, ["publicacion"]))
        par = self.cotejar_tesis("2006224", identificacion("2006224", obligatoriedad="martes 28 de abril de 2014"))
        self.assertEqual((par.resultado, _campos(par)), (DISCREPANTE, ["obligatoriedad"]))  # fue lunes
        par = self.cotejar_tesis("2006224", identificacion("2006224", publicacion="Gaceta (dato sintético)"))
        self.assertEqual(par.resultado, CONFORME)
        self.assertIn("publicacion", [n.campo for n in par.notas])

    # Punto 5: varias fechas declaradas.
    def test_varias_fechas_declaradas(self) -> None:
        for campo, coincide in (("publicacion", "2014-04-25"), ("obligatoriedad", "lunes 28 de abril de 2014")):
            with self.subTest(campo=campo):
                par = self.cotejar_tesis("2006224", identificacion("2006224", **{campo: "1800-01-01 o 1800-01-02"}))
                self.assertEqual((par.resultado, _campos(par)), (DISCREPANTE, [campo]))
                self.assertIn("ninguna fecha", par.motivos[0].detalle)
                par = self.cotejar_tesis("2006224", identificacion("2006224", **{campo: f"{coincide} o 1800-01-02"}))
                self.assertEqual((par.resultado, _campos(par)), (SIN_EVIDENCIA, [campo]))
                self.assertIn("ambiguo", par.motivos[0].detalle)

    def test_sin_sha256_documento(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), sha256_documento=None)
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "a"))

    def test_url_distinta_con_el_mismo_hash(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), url=url_tesis_sjf("2032506"))
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "a"))

    def test_naturaleza_no_oficial_y_tipo_no_soportado(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), naturaleza="secundaria")
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "a"))
        par = self.cotejar_tesis("2006224", identificacion("2006224"),
                                 url="https://dof.gob.mx/nota_detalle.php?codigo=0000001")
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "a"))
        self.assertIn("no soportado", par.motivos[0].detalle)

    def _cotejar_registrado(self, registro: dict):
        return self.cotejar(ledger([afirmacion("A1", ["E1"], tipo="criterio_judicial",
                                               ident=identificacion("2006224"))],
                                   [evidencia_tesis("E1", registro)])).pares[0]

    def test_objeto_faltante(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        (self.raiz / DIR_OBJETOS / registro["derivado"]["sha256"]).unlink()
        par = self._cotejar_registrado(registro)
        self.assertEqual((par.resultado, par.paso, _campos(par)), (SIN_EVIDENCIA, "c", ["derivado"]))

    def test_objeto_alterado(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        ruta = self.raiz / DIR_OBJETOS / registro["original"]["sha256"]
        ruta.write_bytes(ruta.read_bytes().replace(b"Pleno", b"Plena"))
        par = self._cotejar_registrado(registro)
        self.assertEqual((par.resultado, par.paso), (DISCREPANTE, "c"))

    def test_registro_alterado_en_disco(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224")
        ruta = next((self.raiz / DIR_REGISTROS).iterdir())
        alterado = copy.deepcopy(registro)
        alterado["fuente"]["fecha_consulta"] = "1800-01-02"
        ruta.write_bytes(json_canonico(alterado).encode("utf-8"))  # mismo nombre, otro contenido
        par = self.cotejar(ledger([afirmacion("A1", ["E1"], tipo="criterio_judicial",
                                              ident=identificacion("2006224"))],
                                  [evidencia_tesis("E1", alterado)])).pares[0]
        self.assertEqual((par.resultado, par.paso), (DISCREPANTE, "c"))

    def test_fecha_de_consulta_distinta(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), fecha_consulta="1800-01-02")
        self.assertEqual((par.resultado, par.paso), (DISCREPANTE, "d"))
        par = self.cotejar_tesis("2031931", identificacion("2031931"), fecha=FECHA_2031931,
                                 fecha_consulta="2026-10-01")
        self.assertEqual(par.resultado, CONFORME)  # el día de "2026-10-01T19:57Z"

    def test_ubicacion_con_otro_registro(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), ubicacion="Registro digital 2032506")
        self.assertEqual((par.resultado, par.paso), (DISCREPANTE, "e"))

    def test_extracto_sintetico_o_pendiente_nunca_es_conforme(self) -> None:
        for extracto in ("Extracto sintético de prueba con más de veinte caracteres.", "[VERIFICAR EN SJF] rubro"):
            with self.subTest(extracto=extracto):
                par = self.cotejar_tesis("2006224", identificacion("2006224"), extracto=extracto)
                self.assertEqual((par.resultado, _campos(par)), (SIN_EVIDENCIA, ["extracto"]))

    def test_extracto_ajeno_a_la_tesis(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), extracto=CNPP_ART_1O)
        self.assertEqual((par.resultado, _campos(par)), (DISCREPANTE, ["extracto"]))
        par = self.cotejar_tesis("2006224", identificacion("2006224"),
                                 extracto=LITERALES_TESIS["2006224"]["fragmento_texto"])
        self.assertEqual(par.resultado, CONFORME)  # fragmento literal del texto de la tesis

    def test_dos_registros_del_mismo_documento_son_ambiguos(self) -> None:
        registro = agregar_tesis(self.raiz, "2006224", "1800-01-01")
        otro = copy.deepcopy(registro)
        otro["fuente"]["fecha_consulta"] = "1800-01-02"
        guardar_registro(self.raiz, otro)  # sin el control de guardar_evidencia
        par = self._cotejar_registrado(registro)
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "a"))
        self.assertIn("ambiguo", par.motivos[0].detalle)


# ── Punto 0: la afirmación menciona el documento de su evidencia ─────────────


class MencionesAfirmacionTests(_ConPaquete):
    # Variantes sintéticas obviamente falsas: registro 0000001 y clave P./J. 0/0000.
    def test_tesis_mencionada_distinta_es_discrepante(self) -> None:
        casos = {
            "registro_y_clave": "Criterio sintético P./J. 0/0000 (10a.), registro digital 0000001.",
            "solo_registro": "Criterio sintético con registro digital 0000001.",
            "solo_clave": "Criterio sintético P./J. 0/0000 (10a.).",
        }
        for nombre, texto in casos.items():
            with self.subTest(caso=nombre):
                self.nuevo()
                par = self.cotejar_tesis("2006224", identificacion("2006224"), texto=texto)
                self.assertEqual((par.resultado, par.paso, _campos(par)), (DISCREPANTE, "d", ["afirmacion"]))
                self.assertIn("otro registro digital o clave", par.motivos[0].detalle)

    def test_tesis_mencionada_en_referencias(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), referencias=["registro 0000001"])
        self.assertEqual((par.resultado, _campos(par)), (DISCREPANTE, ["afirmacion"]))
        par = self.cotejar_tesis("2006224", identificacion("2006224"), referencias=["P./J. 20/2014 (10a.)"])
        self.assertEqual(par.resultado, CONFORME)

    def test_tesis_mencionada_coincide(self) -> None:
        for texto in ("Criterio del registro digital 2006224 (sintético).",
                      "La P./J. 20/2014 (10a.) (afirmación sintética).",
                      "La P./J. 20/2014 (afirmación sintética)."):
            with self.subTest(texto=texto):
                par = self.cotejar_tesis("2006224", identificacion("2006224"), texto=texto)
                self.assertEqual(par.resultado, CONFORME, par.motivos)

    def test_clave_con_otra_epoca_es_discrepante(self) -> None:
        par = self.cotejar_tesis("2006224", identificacion("2006224"), texto="La P./J. 20/2014 (11a.) (sintético).")
        self.assertEqual((par.resultado, _campos(par)), (DISCREPANTE, ["afirmacion"]))

    def test_clave_de_tcc_que_menciones_no_reconoce(self) -> None:
        # I.24o.A.22 A es una aislada de TCC: menciones.py no la reconoce, se busca literal.
        par = self.cotejar_tesis("2031931", identificacion("2031931"), fecha=FECHA_2031931,
                                 texto="Según la tesis I.24o.A.22 A (11a.) (afirmación sintética).")
        self.assertEqual(par.resultado, CONFORME, par.motivos)
        self.nuevo()
        par = self.cotejar_tesis("2031931", identificacion("2031931"), fecha=FECHA_2031931,
                                 texto="Según la tesis P./J. 0/0000 (afirmación sintética).")
        self.assertEqual((par.resultado, _campos(par)), (DISCREPANTE, ["afirmacion"]))

    def test_tesis_no_cubierta_por_ninguna_evidencia(self) -> None:
        evidencia = agregar_tesis(self.raiz, "2006224")
        libro = ledger([afirmacion("A1", ["E1"], tipo="criterio_judicial", ident=identificacion("2006224"),
                                   texto="Registro digital 2006224 y registro digital 0000001 (sintético).")],
                       [evidencia_tesis("E1", evidencia)])
        agregado = self.cotejar(libro).afirmaciones[0]
        self.assertEqual(agregado.pares[0].resultado, CONFORME)
        self.assertEqual(agregado.resultado, SIN_EVIDENCIA)
        self.assertIn("registro 1", agregado.motivos[0].ledger)
        self.assertIn("ninguna evidencia CONFORME cubre", agregado.motivos[0].detalle)

    def test_articulo_mencionado_distinto_es_discrepante(self) -> None:
        casos = {
            "otro_articulo": "Lo dispone el art. 1o. CNPP (afirmación sintética).",
            "otro_ordenamiento": "Lo dispone el art. 2o. CPF (afirmación sintética).",
            "sin_ley_otro_articulo": "Lo dispone el art. 3o. (afirmación sintética).",
        }
        for nombre, texto in casos.items():
            with self.subTest(caso=nombre):
                self.nuevo()
                par = self.cotejar_ley("Artículo 2o.", CNPP_ART_2O, texto=texto)
                self.assertEqual((par.resultado, par.paso, _campos(par)), (DISCREPANTE, "e", ["afirmacion"]))
                self.assertIn("art. 2o CNPP", par.motivos[0].fuente)

    def test_articulo_mencionado_coincide(self) -> None:
        for texto in ("Lo dispone el art. 2o. CNPP (sintético).", "Lo dispone el artículo 2 (sintético).",
                      "Según el artículo 2o. del Código Nacional de Procedimientos Penales (sintético)."):
            with self.subTest(texto=texto):
                self.nuevo()
                par = self.cotejar_ley("Artículo 2o.", CNPP_ART_2O, texto=texto)
                self.assertEqual(par.resultado, CONFORME, par.motivos)
                self.assertEqual(par.ordenamiento_fuente, "CNPP")

    def test_articulo_sin_correspondencia_de_ordenamiento(self) -> None:
        # Mismas páginas registradas con un archivo sin correspondencia (URL sintética).
        agregar_ley(self.raiz, "CNPP", archivo="SINTETICO.pdf")
        libro = ledger([afirmacion("A1", ["E1"], texto="Art. 2o. CNPP (afirmación sintética).")],
                       [evidencia_ley("E1", "Artículo 2o.", CNPP_ART_2O, archivo="SINTETICO.pdf")])
        par = self.cotejar(libro).pares[0]
        self.assertEqual((par.resultado, par.paso, _campos(par)), (SIN_EVIDENCIA, "e", ["afirmacion"]))
        self.assertIn("sin correspondencia", par.motivos[0].detalle)
        self.assertIsNone(par.ordenamiento_fuente)

    def test_mas_articulos_mencionados_de_los_cubiertos(self) -> None:
        agregar_ley(self.raiz)
        libro = ledger([afirmacion("A1", ["E1"], texto="Arts. 2o. y 3o. CNPP (afirmación sintética).")],
                       [evidencia_ley("E1", "Artículo 2o.", CNPP_ART_2O)])
        agregado = self.cotejar(libro).afirmaciones[0]
        self.assertEqual(agregado.pares[0].resultado, CONFORME)
        self.assertEqual(agregado.resultado, SIN_EVIDENCIA)
        self.assertIn("art. 3 CNPP", agregado.motivos[0].ledger)
        libro["afirmaciones"][0]["verificacion"]["evidencias"].append("E2")
        libro["evidencias"].append(evidencia_ley("E2", "Artículo 3o.", CNPP_ART_3O))
        self.assertEqual(self.cotejar(libro).afirmaciones[0].resultado, CONFORME)

    def test_criterio_que_menciona_articulos_sin_citar_leyes(self) -> None:
        texto = f"La tesis I.24o.A.22 A (11a.) interpreta el {LITERALES_TESIS['2031931']['fragmento_texto']}."
        evidencia = agregar_tesis(self.raiz, "2031931", FECHA_2031931)
        libro = ledger([afirmacion("A1", ["E1"], tipo="criterio_judicial", ident=identificacion("2031931"),
                                   texto=texto)], [evidencia_tesis("E1", evidencia)])
        agregado = self.cotejar(libro).afirmaciones[0]
        self.assertEqual(agregado.resultado, CONFORME, agregado.motivos)
        self.assertIn("artículos mencionados sin cotejar", " ".join(n.detalle for n in agregado.notas))
        libro["afirmaciones"][0]["tipo"] = "texto_normativo"  # ahora los artículos sí se exigen
        agregado = self.cotejar(libro).afirmaciones[0]
        self.assertEqual(agregado.resultado, SIN_EVIDENCIA)

    def test_sin_menciones_deja_nota_visible(self) -> None:
        agregar_ley(self.raiz)
        libro = ledger([afirmacion("A1", ["E1"])], [evidencia_ley("E1", "Artículo 2o.", CNPP_ART_2O)])
        agregado = self.cotejar(libro).afirmaciones[0]
        self.assertEqual(agregado.resultado, CONFORME)
        self.assertIn("no menciona ningún registro, clave ni artículo", agregado.notas[0].detalle)
        self.assertIn("no menciona un artículo identificable", _detalles(agregado.pares[0].notas))


# ── Cotejo de leyes ──────────────────────────────────────────────────────────


class CotejoLeyTests(_ConPaquete):
    def test_articulo_unico_en_el_cuerpo_con_extracto_literal(self) -> None:
        par = self.cotejar_ley("Artículo 2o.", CNPP_ART_2O)
        self.assertEqual(par.resultado, CONFORME, par.motivos)
        self.assertEqual(par.version_fuente, CNPP_ULTIMA_REFORMA)
        self.assertEqual(par.documento_fuente, "CNPP.pdf")
        self.assertEqual(par.articulo_fuente, "2o")
        self.assertIn("ultima_reforma_dof", [n.campo for n in par.notas])  # versión expuesta

    def test_version_declarada_que_coincide(self) -> None:
        par = self.cotejar_ley("Artículo 2o. Objeto del Código", CNPP_ART_2O, ultima_reforma_dof=CNPP_ULTIMA_REFORMA)
        self.assertEqual(par.resultado, CONFORME)
        self.assertNotIn("ultima_reforma_dof", [n.campo for n in par.notas])

    def test_extracto_de_otro_articulo_de_la_misma_ley(self) -> None:
        par = self.cotejar_ley("Artículo 2o.", CNPP_ART_1O)
        self.assertEqual((par.resultado, par.paso), (DISCREPANTE, "f"))
        self.assertIn("otra parte del documento", par.motivos[0].detalle)

    def test_articulo_en_zona_indeterminada(self) -> None:
        # p. 52 sin las páginas 2 a 51: no se sabe si es cuerpo o transitorio.
        par = self.cotejar_ley("Artículo 167", "Extracto que no se llega a comparar en este caso")
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "e"))
        self.assertIn("zona_indeterminada", [a["codigo"] for a in par.advertencias_ubicacion])

    def test_ultima_reforma_distinta_o_no_interpretable(self) -> None:
        par = self.cotejar_ley("Artículo 2o.", CNPP_ART_2O, ultima_reforma_dof="1800-01-01")
        self.assertEqual((par.resultado, par.paso), (DISCREPANTE, "d"))
        par = self.cotejar_ley("Artículo 2o.", CNPP_ART_2O, ultima_reforma_dof="28-11-2025")
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "d"))

    def test_ubicacion_no_interpretable(self) -> None:
        for ubicacion in ("p. 1, l. 50", "Artículos 1o. y 2o.", "[ASIGNAR: Artículo N]"):
            with self.subTest(ubicacion=ubicacion):
                par = self.cotejar_ley(ubicacion, CNPP_ART_2O)
                self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "e"))

    # Punto 6: rangos, enumeraciones y plurales en la ubicación.
    def test_rango_o_enumeracion_en_la_ubicacion(self) -> None:
        for ubicacion in ("Artículos 2o. a 3o.", "Artículo 2o. a 3o.", "Artículo 2o. al 3o.",
                          "Artículo 2o.-3o.", "Artículo 2o., 3o.", "Artículo 2o. y 3o."):
            with self.subTest(ubicacion=ubicacion):
                par = self.cotejar_ley(ubicacion, CNPP_ART_2O)
                self.assertEqual((par.resultado, par.paso, _campos(par)), (SIN_EVIDENCIA, "e", ["ubicacion"]))
                self.assertIn("rangos", par.motivos[0].detalle)

    def test_el_ordinal_cuenta(self) -> None:
        par = self.cotejar_ley("Artículo 2", CNPP_ART_2O)  # el encabezado es "2o."
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "e"))

    def test_articulo_que_puede_continuar_en_paginas_no_incluidas(self) -> None:
        self.assertEqual(self.cotejar_ley("Artículo 3o.", CNPP_ART_3O).resultado, CONFORME)
        par = self.cotejar_ley("Artículo 3o.", CNPP_ART_1O)
        self.assertEqual(par.resultado, SIN_EVIDENCIA)  # no DISCREPANTE: el texto está truncado

    def test_cuerpo_frente_a_transitorios(self) -> None:
        par = self.cotejar_ley("Artículo 1o.", CPF_ART_1O, nombre="CPF")
        self.assertEqual(par.resultado, CONFORME, par.motivos)
        self.assertEqual(par.ordenamiento_fuente, "CPF")

    def test_extracto_requerido_y_suficiente(self) -> None:
        self.assertEqual(self.cotejar_ley("Artículo 2o.", None).resultado, SIN_EVIDENCIA)
        self.assertEqual(self.cotejar_ley("Artículo 2o.", "Objeto del Código").resultado, SIN_EVIDENCIA)
        self.assertEqual(
            self.cotejar_ley("Artículo 2o.", "Extracto sintético de prueba con más de veinte caracteres.").resultado,
            SIN_EVIDENCIA,
        )

    # Punto 1: relación original–texto.
    def test_relacion_original_texto(self) -> None:
        otra_version = (Extractor(EXTRACTOR_PRUEBA, "1", extraer_prueba),)

        def falla(_: bytes) -> list[str]:
            raise RuntimeError("PDF ilegible (sintético)")

        casos = {
            "sin_extractor": ((), SIN_EVIDENCIA, "no comprobable"),
            "otra_version": (otra_version, SIN_EVIDENCIA, "no comprobable"),
            "falla": ((Extractor(EXTRACTOR_PRUEBA, VERSION_PRUEBA, falla),), SIN_EVIDENCIA, "falló"),
            "otro_texto": ((Extractor(EXTRACTOR_PRUEBA, VERSION_PRUEBA, lambda _: paginas_completas("CPF")),),
                           DISCREPANTE, "no proviene"),
        }
        for nombre, (extractores, esperado, frase) in casos.items():
            with self.subTest(caso=nombre):
                self.nuevo()
                par = self.cotejar_ley("Artículo 2o.", CNPP_ART_2O, extractores=extractores)
                self.assertEqual((par.resultado, par.paso, _campos(par)), (esperado, "c", ["texto_extraido"]))
                self.assertIn(frase, par.motivos[0].detalle)

    def test_texto_de_otro_pdf_no_es_conforme(self) -> None:
        # El PDF registrado es "otro" (su re-extracción da las páginas del CPF) y el texto
        # declarado es el del CNPP: la integridad de PR-2 no lo ve; la re-extracción sí.
        agregar_ley(self.raiz, "CNPP", pdf=PDF_SINTETICO["OTRA"])
        libro = ledger([afirmacion("A1", ["E1"])],
                       [evidencia_ley("E1", "Artículo 2o.", CNPP_ART_2O,
                                      sha256_documento=sha256_bytes(PDF_SINTETICO["OTRA"]))])
        par = self.cotejar(libro).pares[0]
        self.assertEqual((par.resultado, par.paso, _campos(par)), (DISCREPANTE, "c", ["texto_extraido"]))


class LectoresTests(unittest.TestCase):
    def test_articulo_de_ubicacion(self) -> None:
        casos = {
            "Artículo 2o.": "2o",
            "Artículo 471, párrafo primero": "471",
            "art. 19 Ter CPEUM": "19 Ter",
            "Artículo 4o.-A": "4o.-A",
            "Artículo 69-B": "69-B",
            "Artículo 1o.- A quien (texto sintético)": "1o",
            "CNPP, artículo 167": "167",
            "Artículos 14 y 16": None,
            "Artículos 167 a 170": None,
            "Artículo 167 a 170": None,
            "artículo 167 al 170": None,
            "Artículo 167-170": None,
            "Artículo 167, 168": None,
            "p. 52": None,
            None: None,
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertEqual(articulo_de_ubicacion(valor), esperado)

    def test_clave_articulo(self) -> None:
        casos = {"1o": "art. 1", "167": "art. 167", "19 Ter": "art. 19 ter", "10 Octies": "art. 10 octies",
                 "427 Quinquies": "art. 427 quinquies", "4o.-A": None, "Único": None}
        for identificador, esperado in casos.items():
            with self.subTest(identificador=identificador):
                self.assertEqual(clave_articulo(identificador), esperado)

    def test_ordenamiento_de(self) -> None:
        self.assertEqual(ordenamiento_de("CNPP.pdf", "CÓDIGO NACIONAL DE PROCEDIMIENTOS PENALES")[0], "CNPP")
        titulo_lamp = ("LEY DE AMPARO, REGLAMENTARIA DE LOS ARTÍCULOS 103 Y 107 DE LA CONSTITUCIÓN "
                       "POLÍTICA DE LOS ESTADOS UNIDOS MEXICANOS")
        self.assertEqual(ordenamiento_de("LAmp.pdf", titulo_lamp)[0], "LA")
        self.assertIsNone(ordenamiento_de("CPF.pdf", "CÓDIGO NACIONAL DE PROCEDIMIENTOS PENALES")[0])
        self.assertIsNone(ordenamiento_de("SINTETICO.pdf", "CÓDIGO NACIONAL DE PROCEDIMIENTOS PENALES")[0])
        self.assertIsNone(ordenamiento_de("CNPP.pdf", None)[0])

    def test_fechas_declaradas(self) -> None:
        fechas, problemas = fechas_declaradas("Esta tesis se publicó el viernes 25 de abril de 2014 a las 09:32 horas")
        self.assertEqual([f.isoformat() for f in fechas], ["2014-04-25"])
        self.assertEqual(problemas, [])
        self.assertTrue(fechas_declaradas("martes 28 de abril de 2014")[1])
        self.assertEqual(fechas_declaradas("Libro 5, Abril de 2014")[0], [])

    def test_rotulo_sintetico(self) -> None:
        self.assertTrue(rotulado_como_sintetico("RUBRO SINTÉTICO DE PRUEBA"))
        self.assertTrue(rotulado_como_sintetico("Notificado el día 25 (ficticio)."))
        self.assertFalse(rotulado_como_sintetico("sustancias sintéticas y medios de prueba"))


# ── Agregado y contrato ──────────────────────────────────────────────────────


class AgregadoTests(_ConPaquete):
    def _libro(self) -> dict:
        agregar_ley(self.raiz)
        tesis = agregar_tesis(self.raiz, "2006224")
        return ledger(
            [
                afirmacion("A1", ["E1", "E2"]),  # CONFORME + DISCREPANTE
                afirmacion("A2", ["E1", "E3"]),  # CONFORME + SIN_EVIDENCIA
                afirmacion("A3", ["E3"]),  # solo SIN_EVIDENCIA
                afirmacion("A4", ["E1"], estado="INEXISTENTE"),
                afirmacion("A5", ["E9"]),  # evidencia inexistente
                afirmacion("A6", []),  # VERIFICADO sin evidencias
                afirmacion("A7", ["E4"], tipo="criterio_judicial", ident=identificacion("2006224")),
                afirmacion("A8", [], estado="CANDIDATO", tipo="propuesta"),
            ],
            [
                evidencia_ley("E1", "Artículo 2o.", CNPP_ART_2O),
                evidencia_ley("E2", "Artículo 2o.", CNPP_ART_1O),
                evidencia_ley("E3", "Artículo 167", CNPP_ART_2O),
                evidencia_tesis("E4", tesis),
            ],
        )

    def test_agregado_por_afirmacion(self) -> None:
        cotejo = self.cotejar(self._libro())
        resultados = {a.afirmacion: a.resultado for a in cotejo.afirmaciones}
        self.assertEqual(
            resultados,
            {"A1": DISCREPANTE, "A2": CONFORME, "A3": SIN_EVIDENCIA, "A4": NO_COTEJADO,
             "A5": SIN_EVIDENCIA, "A6": SIN_EVIDENCIA, "A7": CONFORME, "A8": SIN_EVIDENCIA},
        )
        self.assertEqual(ESTADO_SOSTENIBLE[SIN_EVIDENCIA], "NO VERIFICABLE")
        self.assertEqual(cotejo.afirmaciones[2].estado_sostenible, "NO VERIFICABLE")
        self.assertFalse(cotejo.todo_conforme)
        self.assertEqual(cotejo.resumen()[NO_COTEJADO], 1)
        hallazgos = {a.afirmacion for a in cotejo.afirmaciones if a.es_hallazgo}
        self.assertEqual(hallazgos, {"A1", "A3", "A4", "A5", "A6"})  # A8: CANDIDATO sin evidencias

    # Punto 7: un agregado sin pares cuenta como hallazgo.
    def test_verificado_sin_evidencias_no_es_todo_conforme(self) -> None:
        tesis = agregar_tesis(self.raiz, "2006224")
        base = [afirmacion("A1", ["E1"], tipo="criterio_judicial", ident=identificacion("2006224"))]
        libro = ledger(base, [evidencia_tesis("E1", tesis)])
        self.assertTrue(self.cotejar(libro).todo_conforme)
        for estado in ("VERIFICADO", "INEXISTENTE"):
            with self.subTest(estado=estado):
                libro = ledger(base + [afirmacion("A2", [], estado=estado)], [evidencia_tesis("E1", tesis)])
                cotejo = self.cotejar(libro)
                self.assertFalse(cotejo.todo_conforme)
                self.assertTrue(cotejo.afirmaciones[1].es_hallazgo)
                self.assertEqual(cotejo.resumen()["afirmaciones_con_hallazgo"], 1)
        libro = ledger(base + [afirmacion("A2", [], estado="VERIFICADO")], [evidencia_tesis("E1", tesis)])
        self.assertIn("no cita evidencias", self.cotejar(libro).afirmaciones[1].motivos[0].detalle)
        libro = ledger(base + [afirmacion("A2", [], estado="CANDIDATO", tipo="propuesta")],
                       [evidencia_tesis("E1", tesis)])
        self.assertTrue(self.cotejar(libro).todo_conforme)

    def test_id_de_evidencia_duplicado_es_ambiguo(self) -> None:
        libro = self._libro()
        libro["evidencias"].append(copy.deepcopy(libro["evidencias"][0]))
        par = self.cotejar(libro).afirmaciones[0].pares[0]
        self.assertEqual((par.resultado, par.paso), (SIN_EVIDENCIA, "a"))

    def test_el_cotejo_no_modifica_el_ledger(self) -> None:
        libro = self._libro()
        antes = copy.deepcopy(libro)
        cotejo = self.cotejar(libro)
        self.assertEqual(libro, antes)
        json.dumps(cotejo.como_dict(), ensure_ascii=False)  # serializable

    # Punto 4: el cotejo lleva la huella de lo que coteja.
    def test_cotejo_lleva_huellas_y_detecta_otro_contenido(self) -> None:
        libro = self._libro()
        paquete = self.paquete()
        cotejo = cotejar_ledger(libro, paquete, extractores=EXTRACTORES)
        self.assertEqual(cotejo.problemas_correspondencia(libro, paquete), [])
        self.assertEqual(cotejo.huella_paquete, paquete.huella())
        cambiado = copy.deepcopy(libro)
        cambiado["evidencias"][0]["extracto"] = CNPP_ART_1O
        self.assertTrue(cotejo.problemas_correspondencia(cambiado))
        agregar_tesis(self.raiz, "2031931", FECHA_2031931)
        self.assertTrue(cotejo.problemas_correspondencia(libro, self.paquete()))


# ── Integración con el linter y el reporte ───────────────────────────────────


def decision_advertencias(par_sha: str | None, *, estado: str = "APROBADO", responsable: str = HUMANO,
                          evidencia: str = "E1", codigos: list[str] | None = None,
                          resolucion: str | None = "Se adopta la época del campo de época (decisión sintética).",
                          pregunta: str = "¿Qué época consta? (sintético)", con_campo: bool = True) -> dict:
    decision = {"id": "D1", "pregunta": pregunta, "responsable": responsable, "estado": estado, "bloquea": ["E1"]}
    if con_campo:
        decision["advertencias_fuente"] = {
            "evidencia": evidencia,
            "sha256_documento": par_sha,
            "codigos": ["epoca_discrepante"] if codigos is None else codigos,
            "resolucion": resolucion,
        }
    return decision


class LintConCotejoTests(_ConPaquete):
    def _libro_tesis(self, registro: str, *, estado: str = "VERIFICADO", fecha: str = FECHA_SINTETICA,
                     ident: dict | None = None, decisiones: list[dict] | None = None, **cambios) -> dict:
        evidencia = agregar_tesis(self.raiz, registro, fecha)
        return ledger(
            [afirmacion("A1", ["E1"], tipo="criterio_judicial", estado=estado,
                        ident=ident if ident is not None else identificacion(registro))],
            [evidencia_tesis("E1", evidencia, **cambios)],
            decisiones,
        )

    def _hallazgos(self, libro: dict) -> list[dict]:
        return lint_ledger(libro, paquete=self.paquete(), extractores=EXTRACTORES)

    def _reglas(self, libro: dict) -> dict[str, str]:
        return {h["regla"]: h["severidad"] for h in self._hallazgos(libro)}

    def test_lint_sin_paquete_no_cambia(self) -> None:
        reporte = evaluar_gold_set(GOLD_SET)
        self.assertTrue(reporte["gate_passed"])
        self.assertEqual(reporte["passed"], reporte["total"])
        datos = json.loads(GOLD_SET.read_text(encoding="utf-8"))
        for caso in datos["cases"]:
            with self.subTest(caso=caso["id"]):
                hallazgos = lint_ledger(caso["ledger"], documento=caso.get("documento"))
                self.assertEqual(hallazgos, lint_ledger(caso["ledger"], documento=caso.get("documento"),
                                                        paquete=None, cotejo=None))
                self.assertFalse({h["regla"] for h in hallazgos} - set(REGLAS))
        self.assertFalse(set(REGLAS) & set(REGLAS_COTEJO))

    def test_verificado_conforme_sin_reglas_nuevas(self) -> None:
        hallazgos = self._hallazgos(self._libro_tesis("2006224"))
        self.assertEqual(hallazgos, [], hallazgos)
        self.assertFalse(esta_bloqueado(hallazgos))

    def test_pl015_y_pl016_con_evidencia_discrepante(self) -> None:
        reglas = self._reglas(self._libro_tesis("2006224", ident=identificacion("2006224", registro="0000001")))
        self.assertEqual(reglas.get("PL-015"), BLOQUEANTE)
        self.assertEqual(reglas.get("PL-016"), BLOQUEANTE)

    def test_pl016_sin_ningun_conforme(self) -> None:
        reglas = self._reglas(self._libro_tesis("2006224", sha256_documento=None))
        self.assertEqual(reglas.get("PL-016"), BLOQUEANTE)
        self.assertNotIn("PL-015", reglas)

    def test_pl016_por_menciones_no_cubiertas(self) -> None:
        libro = self._libro_tesis("2006224")
        libro["afirmaciones"][0]["texto"] = "Registro digital 2006224 y registro digital 0000001 (sintético)."
        hallazgos = self._hallazgos(libro)
        pl016 = [h for h in hallazgos if h["regla"] == "PL-016"]
        self.assertEqual(len(pl016), 1)
        self.assertIn("ninguna evidencia CONFORME cubre", pl016[0]["mensaje"])

    def test_reglas_nuevas_solo_para_verificado(self) -> None:
        libro = self._libro_tesis("2006224", estado="CANDIDATO", sha256_documento=None)
        self.assertFalse(set(self._reglas(libro)) & set(REGLAS_COTEJO))

    # Punto 3: la decisión debe declarar evidencia, fuente vigente, códigos y resolución.
    def test_pl017_verificado_exige_decision_completa_y_aprobada(self) -> None:
        sha = sha256_bytes((FIXTURES / "sjf_2031931.txt").read_bytes())
        casos = {
            "sin_decision": (None, BLOQUEANTE, "sin una decisión humana APROBADA"),
            "aprobada_ajena_solo_con_bloquea": (
                [decision_advertencias(sha, pregunta="¿Autorizar presupuesto? (sintético)", con_campo=False)],
                BLOQUEANTE, "no declara advertencias_fuente"),
            "pendiente": ([decision_advertencias(sha, estado="REQUIERE DECISIÓN HUMANA")], BLOQUEANTE,
                          "no está APROBADA"),
            "aprobada_por_agente": ([decision_advertencias(sha, responsable="Claude")], BLOQUEANTE,
                                    "responsable no válido"),
            "otra_evidencia": ([decision_advertencias(sha, evidencia="E9")], BLOQUEANTE, "declara la evidencia"),
            "fuente_no_vigente": ([decision_advertencias("0" * 64)], BLOQUEANTE, "vigentes"),
            "sin_codigos": ([decision_advertencias(sha, codigos=[])], BLOQUEANTE, "epoca_discrepante"),
            "sin_resolucion": ([decision_advertencias(sha, resolucion="")], BLOQUEANTE, "resolución vacío"),
            "completa": ([decision_advertencias(sha)], None, None),
        }
        for nombre, (decisiones, esperado, frase) in casos.items():
            with self.subTest(caso=nombre):
                self.nuevo()
                libro = self._libro_tesis("2031931", fecha=FECHA_2031931, decisiones=decisiones)
                pl017 = [h for h in self._hallazgos(libro) if h["regla"] == "PL-017"]
                self.assertEqual(pl017[0]["severidad"] if pl017 else None, esperado)
                if frase:
                    self.assertIn(frase, pl017[0]["mensaje"])

    def test_pl017_huella_del_registro_tambien_vale(self) -> None:
        libro = self._libro_tesis("2031931", fecha=FECHA_2031931)
        huella = cotejar_ledger(libro, self.paquete()).pares[0].huella_registro
        decision = decision_advertencias(None)
        del decision["advertencias_fuente"]["sha256_documento"]
        decision["advertencias_fuente"]["huella_registro"] = huella
        libro["decisiones"] = [decision]
        self.assertNotIn("PL-017", self._reglas(libro))

    def test_pl017_otros_estados_basta_decision_registrada(self) -> None:
        sha = sha256_bytes((FIXTURES / "sjf_2031931.txt").read_bytes())
        libro = self._libro_tesis("2031931", estado="CANDIDATO", fecha=FECHA_2031931)
        self.assertEqual(self._reglas(libro).get("PL-017"), ALTA)
        self.nuevo()
        libro = self._libro_tesis("2031931", estado="CANDIDATO", fecha=FECHA_2031931, decisiones=[
            decision_advertencias(sha, estado="REQUIERE DECISIÓN HUMANA", resolucion=None, codigos=[])])
        self.assertNotIn("PL-017", self._reglas(libro))
        self.nuevo()
        libro = self._libro_tesis("2031931", estado="CANDIDATO", fecha=FECHA_2031931, decisiones=[
            decision_advertencias(sha, estado="REQUIERE DECISIÓN HUMANA", con_campo=False)])
        self.assertEqual(self._reglas(libro).get("PL-017"), ALTA)  # solo "bloquea" no basta

    def test_paquete_y_cotejo_son_excluyentes_y_el_cotejo_debe_ser_del_ledger(self) -> None:
        libro = self._libro_tesis("2006224")
        paquete = self.paquete()
        with self.assertRaises(ValueError):
            lint_ledger(libro, paquete=paquete, cotejo=cotejar_ledger(libro, paquete))
        otro = copy.deepcopy(libro)
        otro["afirmaciones"][0]["id"] = "A9"
        with self.assertRaises(ValueError):
            lint_ledger(libro, cotejo=cotejar_ledger(otro, paquete))

    # Punto 4: un cotejo anterior no se reutiliza tras cambiar el ledger.
    def test_cotejo_anterior_con_otro_contenido_se_rechaza(self) -> None:
        libro = self._libro_tesis("2006224")
        cotejo = cotejar_ledger(libro, self.paquete())
        self.assertEqual(lint_ledger(libro, cotejo=cotejo), [])
        libro["afirmaciones"][0]["identificacion_criterio"]["clave"] = "P./J. 0/0000 (10a.)"  # sintética
        with self.assertRaisesRegex(ValueError, "otro contenido"):
            lint_ledger(libro, cotejo=cotejo)
        self.assertIn("PL-015", self._reglas(libro))  # recotejado: la clave es DISCREPANTE

    def test_reporte_con_seccion_de_cotejo(self) -> None:
        sha = sha256_bytes((FIXTURES / "sjf_2031931.txt").read_bytes())
        libro = self._libro_tesis("2031931", fecha=FECHA_2031931)
        cotejo = cotejar_ledger(libro, self.paquete())
        hallazgos = lint_ledger(libro, cotejo=cotejo)
        reporte = reporte_markdown(libro, hallazgos, cotejo)
        self.assertIn("## Cotejo de identidad", reporte)
        self.assertIn("| A1 | E1 | CONFORME |", reporte)
        self.assertIn("requerida (epoca_discrepante) · sin decisión que la atienda", reporte)
        self.assertIn("no aprueba ni cambia estados", reporte)
        self.assertIn(cotejo.huella_ledger, reporte)
        self.assertIn("| Afirmación | Estado declarado | Resultado agregado |", reporte)
        self.assertNotIn("Cotejo de identidad", reporte_markdown(libro, hallazgos))
        libro["decisiones"] = [decision_advertencias(sha)]
        cotejo = cotejar_ledger(libro, self.paquete())
        reporte = reporte_markdown(libro, lint_ledger(libro, cotejo=cotejo), cotejo)
        self.assertIn("atendida por D1", reporte)
        self.assertIn("Atiende advertencias de la fuente de E1 (epoca_discrepante;", reporte)
        self.assertIn("resolución: Se adopta la época del campo de época", reporte)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _bloque(salida: str, titulo: str) -> dict:
    inicio = salida.index("{", salida.index(titulo))
    return json.JSONDecoder().raw_decode(salida[inicio:])[0]


def _extractores_de_prueba() -> list[Extractor]:
    return list(EXTRACTORES)


class CliCotejoTests(unittest.TestCase):
    def setUp(self) -> None:
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.carpeta = Path(temporal.name)
        self.paquete = self.carpeta / "paquete"

    def _ejecutar(self, *argumentos: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(PLAN_AUDIT), *argumentos],
            cwd=REPO, capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def _en_proceso(self, *argumentos: str, extractores=_extractores_de_prueba) -> tuple[int, str, str]:
        salida, errores = io.StringIO(), io.StringIO()
        with patch.object(plan_audit, "_extractores_disponibles", extractores), \
                contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
            codigo = plan_audit.main(list(argumentos))
        return codigo, salida.getvalue(), errores.getvalue()

    def _agregar_tesis(self, registro: str = "2006224", fecha: str = FECHA_SINTETICA, *extra: str):
        return self._ejecutar(
            "evidencia", "agregar-tesis", "--paquete", str(self.paquete),
            "--archivo", str(FIXTURES / f"sjf_{registro}.txt"),
            "--url", url_tesis_sjf(registro), "--fecha-consulta", fecha, *extra,
        )

    def _escribir_ledger(self, libro: dict, nombre: str = "ledger.json") -> Path:
        ruta = self.carpeta / nombre
        ruta.write_text(json.dumps(libro, ensure_ascii=False), encoding="utf-8")
        return ruta

    def test_agregar_tesis_y_cotejar_de_punta_a_punta(self) -> None:
        resultado = self._agregar_tesis("2006224", FECHA_SINTETICA, "--registro", "2006224")
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        salida = resultado.stdout
        original = (FIXTURES / "sjf_2006224.txt").read_bytes()
        self.assertIn(f"sha256_documento: {sha256_bytes(original)}", salida)
        evidencia = _bloque(salida, "Bloque de evidencia")
        ident = _bloque(salida, "Datos de la fuente")
        self.assertEqual(ident["rubro"], RUBRO_2006224)
        evidencia["id"] = "E1"
        ident.update(organo="Pleno (dato sintético de prueba)", integracion="Dato sintético de prueba",
                     alcance="Dato sintético de prueba")
        ruta = self._escribir_ledger(ledger([afirmacion(
            "A1", ["E1"], tipo="criterio_judicial", ident=ident,
            texto="Afirmación sintética sobre la tesis con registro digital 2006224.")], [evidencia]))

        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete))
        self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
        self.assertIn("[CONFORME] A1 ← E1", resultado.stdout)
        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete), "--json")
        self.assertEqual(resultado.returncode, 0)
        datos = json.loads(resultado.stdout)
        self.assertEqual(datos["resumen"][CONFORME], 1)
        self.assertTrue(datos["todo_conforme"])
        self.assertTrue(datos["huella_ledger"])

        salida_json, salida_md = self.carpeta / "h.json", self.carpeta / "r.md"
        resultado = self._ejecutar("lint", "--ledger", str(ruta), "--paquete", str(self.paquete),
                                   "--json", str(salida_json), "--md", str(salida_md))
        self.assertEqual(resultado.returncode, 0, resultado.stdout)
        self.assertIn("cotejo", json.loads(salida_json.read_text(encoding="utf-8")))
        self.assertIn("## Cotejo de identidad", salida_md.read_text(encoding="utf-8"))
        resultado = self._ejecutar("lint", "--ledger", str(ruta), "--json", str(salida_json))
        self.assertNotIn("cotejo", json.loads(salida_json.read_text(encoding="utf-8")))

        objeto = self.paquete / DIR_OBJETOS / evidencia["sha256_documento"]
        objeto.write_bytes(objeto.read_bytes() + b" ")
        self.assertEqual(self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete)).returncode, 1)
        self.assertEqual(self._ejecutar("lint", "--ledger", str(ruta), "--paquete", str(self.paquete)).returncode, 1)

    def test_cotejar_codigos_de_salida(self) -> None:
        self.assertEqual(self._agregar_tesis("2031931", FECHA_2031931).returncode, 0)
        evidencia = {
            "id": "E1", "naturaleza": "portal_oficial", "url": url_tesis_sjf("2031931"),
            "ubicacion": "Registro digital 2031931", "extracto": RUBRO_2031931, "fecha_consulta": "2026-10-01",
            "sha256_documento": sha256_bytes((FIXTURES / "sjf_2031931.txt").read_bytes()),
        }
        ruta = self._escribir_ledger(ledger([afirmacion("A1", ["E1"], tipo="criterio_judicial",
                                                        ident=identificacion("2031931"))], [evidencia]))
        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete))
        self.assertEqual(resultado.returncode, 1)  # CONFORME pero requiere decisión humana
        self.assertIn("requiere decisión humana: epoca_discrepante", resultado.stdout)
        roto = self.carpeta / "roto.json"
        roto.write_text("{ no es json", encoding="utf-8")
        self.assertEqual(self._ejecutar("cotejar", "--ledger", str(roto), "--paquete", str(self.paquete)).returncode, 2)
        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.carpeta / "no-existe"))
        self.assertEqual(resultado.returncode, 2)
        self.assertNotIn("Traceback", resultado.stderr)
        self.assertEqual(
            self._ejecutar("lint", "--ledger", str(ruta), "--paquete", str(self.carpeta / "no-existe")).returncode, 2
        )

    # Punto 7 (CLI): VERIFICADO sin evidencias → salida 1.
    def test_cotejar_verificado_sin_evidencias_sale_1(self) -> None:
        self.assertEqual(self._agregar_tesis("2006224").returncode, 0)
        ruta = self._escribir_ledger(ledger([afirmacion("A1", [])], []))
        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete))
        self.assertEqual(resultado.returncode, 1, resultado.stdout)
        self.assertIn("sin evidencias citadas · HALLAZGO", resultado.stdout)
        datos = json.loads(self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete),
                                          "--json").stdout)
        self.assertFalse(datos["todo_conforme"])
        self.assertEqual(datos["resumen"]["afirmaciones_con_hallazgo"], 1)

    # Punto 8 (CLI): ninguna salida dentro del paquete.
    def test_salidas_de_lint_dentro_del_paquete_se_rechazan(self) -> None:
        self.assertEqual(self._agregar_tesis("2006224").returncode, 0)
        ruta = self._escribir_ledger(ledger([afirmacion("A1", [])], []))
        sha = sha256_bytes((FIXTURES / "sjf_2006224.txt").read_bytes())
        objeto = self.paquete / DIR_OBJETOS / sha
        antes = objeto.read_bytes()
        for opcion, destino in (("--json", objeto), ("--md", self.paquete / "reporte.md"),
                                ("--json", self.paquete / DIR_REGISTROS / "x.json")):
            with self.subTest(opcion=opcion, destino=destino.name):
                resultado = self._ejecutar("lint", "--ledger", str(ruta), "--paquete", str(self.paquete),
                                           opcion, str(destino))
                self.assertEqual(resultado.returncode, 2, resultado.stdout)
                self.assertIn("dentro del paquete", resultado.stderr)
        self.assertEqual(objeto.read_bytes(), antes)
        self.assertEqual(sha256_bytes(objeto.read_bytes()), sha)
        self.assertFalse((self.paquete / "reporte.md").exists())

    def test_agregar_tesis_entradas_invalidas(self) -> None:
        casos = {
            "registro_distinto": self._agregar_tesis("2006224", FECHA_SINTETICA, "--registro", "2032506"),
            "fecha_no_iso": self._agregar_tesis("2006224", "hoy"),
            "hora_sin_zona": self._agregar_tesis("2006224", "2026-10-01T19:57"),
        }
        for nombre, resultado in casos.items():
            with self.subTest(caso=nombre):
                self.assertEqual(resultado.returncode, 2, resultado.stdout)
                self.assertNotIn("Traceback", resultado.stderr)
        resultado = self._ejecutar(
            "evidencia", "agregar-tesis", "--paquete", str(self.paquete),
            "--archivo", str(FIXTURES / "sjf_2006224.txt"), "--url", url_tesis_sjf("2032506"),
            "--fecha-consulta", FECHA_SINTETICA,
        )
        self.assertEqual(resultado.returncode, 2)  # la URL no corresponde al registro del texto
        self.assertEqual(self._agregar_tesis("2006224", "1800-01-01").returncode, 0)
        self.assertEqual(self._agregar_tesis("2006224", "1800-01-02").returncode, 2)  # sería ambiguo

    def _agregar_ley(self, pdf: bytes, paginas_json: Path, url: str, *extra: str) -> tuple[int, str, str]:
        ruta_pdf = self.carpeta / "documento.pdf"
        ruta_pdf.write_bytes(pdf)
        return self._en_proceso(
            "evidencia", "agregar-ley", "--paquete", str(self.paquete), "--pdf", str(ruta_pdf),
            "--url", url, "--fecha-consulta", FECHA_SINTETICA, "--paginas-json", str(paginas_json),
            "--extractor", EXTRACTOR_PRUEBA, "--version-extractor", VERSION_PRUEBA, *extra,
        )

    # Punto 1 (CLI): el texto declarado debe provenir del PDF.
    def test_agregar_ley_rechaza_paginas_de_otro_pdf(self) -> None:
        codigo, _, errores = self._agregar_ley(PDF_SINTETICO["OTRA"], FIXTURES / "leyesbiblio_CNPP.json",
                                               url_leyesbiblio("CNPP.pdf"))
        self.assertEqual(codigo, 2)
        self.assertIn("no provienen de ese PDF", errores)
        self.assertFalse(self.paquete.exists() and any((self.paquete / DIR_REGISTROS).iterdir()))
        codigo, salida, errores = self._agregar_ley(PDF_SINTETICO["CNPP"], FIXTURES / "leyesbiblio_CNPP.json",
                                                    url_leyesbiblio("CNPP.pdf"))
        self.assertEqual(codigo, 0, errores)
        self.assertIn("Origen del texto: declarado", salida)
        registro = cargar_paquete(self.paquete).registros[0].registro
        self.assertEqual(registro["metadatos"]["origen_texto"], "declarado")

    def test_agregar_ley_rechaza_titulo_que_no_es_el_de_la_url(self) -> None:
        paginas = paginas_fixture("CNPP")
        del paginas["archivo"]
        ruta = self.carpeta / "paginas.json"
        ruta.write_text(json.dumps(paginas, ensure_ascii=False), encoding="utf-8")
        codigo, _, errores = self._agregar_ley(PDF_SINTETICO["CNPP"], ruta, url_leyesbiblio("CPF.pdf"))
        self.assertEqual(codigo, 2)
        self.assertIn("no corresponde al archivo CPF.pdf", errores)

    def test_agregar_ley_con_paginas_json_sin_extractor_comprobable(self) -> None:
        pdf = self.carpeta / "CNPP.pdf"
        pdf.write_bytes(PDF_SINTETICO["CNPP"])
        base = ["evidencia", "agregar-ley", "--paquete", str(self.paquete), "--pdf", str(pdf),
                "--url", url_leyesbiblio("CNPP.pdf"), "--fecha-consulta", FECHA_SINTETICA,
                "--paginas-json", str(FIXTURES / "leyesbiblio_CNPP.json")]
        resultado = self._ejecutar(*base)
        self.assertEqual(resultado.returncode, 2)  # el JSON no declara el extractor
        self.assertIn("--extractor", resultado.stderr)
        resultado = self._ejecutar(*base, "--extractor", EXTRACTOR_PRUEBA, "--version-extractor", VERSION_PRUEBA)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("relación original–texto no comprobable", resultado.stdout)
        evidencia = _bloque(resultado.stdout, "Bloque de evidencia")
        self.assertEqual(evidencia["sha256_documento"], sha256_bytes(PDF_SINTETICO["CNPP"]))
        self.assertEqual(evidencia["ultima_reforma_dof"], CNPP_ULTIMA_REFORMA)
        evidencia.update(id="E1", ubicacion="Artículo 2o.", extracto=CNPP_ART_2O)
        ruta = self._escribir_ledger(ledger([afirmacion("A1", ["E1"])], [evidencia]))
        # Subproceso: no tiene el extractor sintético → nunca CONFORME.
        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete))
        self.assertEqual(resultado.returncode, 1, resultado.stdout)
        self.assertIn("[SIN_EVIDENCIA] A1 ← E1 (paso c", resultado.stdout)
        self.assertIn("relación original–texto no comprobable", resultado.stdout)
        # En proceso, con el extractor sintético inyectado → CONFORME.
        codigo, salida, _ = self._en_proceso("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete))
        self.assertEqual(codigo, 0, salida)

        paginas = paginas_fixture("CNPP")
        paginas["paginas"][0]["texto"] += " "  # la huella declarada ya no corresponde
        alterado = self.carpeta / "alterado.json"
        alterado.write_text(json.dumps(paginas, ensure_ascii=False), encoding="utf-8")
        base[-1] = str(alterado)
        resultado = self._ejecutar(*base, "--extractor", "x", "--version-extractor", "y")
        self.assertEqual(resultado.returncode, 2)

    def test_agregar_ley_sin_pymupdf_da_error_claro(self) -> None:
        pdf = self.carpeta / "CNPP.pdf"
        pdf.write_bytes(PDF_SINTETICO["CNPP"])
        errores = io.StringIO()
        with patch.dict(sys.modules, {"fitz": None}), contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(errores):
            codigo = plan_audit.main([
                "evidencia", "agregar-ley", "--paquete", str(self.paquete), "--pdf", str(pdf),
                "--url", url_leyesbiblio("CNPP.pdf"), "--fecha-consulta", FECHA_SINTETICA,
            ])
        self.assertEqual(codigo, 2)
        self.assertIn("PyMuPDF", errores.getvalue())
        self.assertFalse(self.paquete.exists())

    @unittest.skipUnless(importlib.util.find_spec("fitz"), "PyMuPDF no instalado (CI sin dependencias)")
    def test_agregar_ley_con_pymupdf_de_punta_a_punta(self) -> None:
        import fitz

        lineas = [  # encabezado con la forma de LeyesBiblio; contenido sintético y rotulado
            "LEY SINTÉTICA DE PRUEBA",
            "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN",
            "Secretaría General",
            "Secretaría de Servicios Parlamentarios",
            "Última Reforma DOF 01-01-1800",
            "1 de 1",
            "Artículo 1o. Este texto existe solo para probar el cotejo de identidad.",
            "Artículo 2o. Este otro texto también existe solo para probar el cotejo.",
        ]
        documento = fitz.open()
        pagina = documento.new_page()
        for indice, linea in enumerate(lineas):
            pagina.insert_text((72, 72 + 14 * indice), linea)
        pdf = self.carpeta / "SINTETICA.pdf"
        pdf.write_bytes(documento.tobytes())
        documento.close()
        url = url_leyesbiblio("SINTETICA.pdf")
        resultado = self._ejecutar("evidencia", "agregar-ley", "--paquete", str(self.paquete), "--pdf", str(pdf),
                                   "--url", url, "--fecha-consulta", FECHA_SINTETICA)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertIn("Origen del texto: extraido", resultado.stdout)
        evidencia = _bloque(resultado.stdout, "Bloque de evidencia")
        self.assertEqual(evidencia["sha256_documento"], sha256_bytes(pdf.read_bytes()))
        self.assertEqual(evidencia["ultima_reforma_dof"], "1800-01-01")
        evidencia.update(id="E1", ubicacion="Artículo 1o.",
                         extracto="Este texto existe solo para probar el cotejo de identidad")
        ruta = self._escribir_ledger(ledger([afirmacion("A1", ["E1"], texto="El artículo 1o. lo dispone.")],
                                            [evidencia]))
        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete))
        self.assertEqual(resultado.returncode, 0, resultado.stdout)
        self.assertIn("[CONFORME] A1 ← E1", resultado.stdout)
        registro = cargar_paquete(self.paquete).registros[0].registro
        self.assertTrue(registro["derivado"]["extractor"].startswith("PyMuPDF"))
        self.assertEqual(registro["metadatos"]["origen_texto"], "extraido")
        # Con otro artículo mencionado, la identidad no se sostiene.
        ruta = self._escribir_ledger(ledger([afirmacion("A1", ["E1"], texto="El artículo 2o. lo dispone.")],
                                            [evidencia]), "otro.json")
        resultado = self._ejecutar("cotejar", "--ledger", str(ruta), "--paquete", str(self.paquete))
        self.assertEqual(resultado.returncode, 1)
        self.assertIn("[DISCREPANTE] A1 ← E1 (paso e", resultado.stdout)

    def test_paquete_dentro_del_repositorio_solo_en_zona_ignorada(self) -> None:
        self.assertIsNone(plan_audit.motivo_ruta_paquete(self.carpeta / "paquete"))
        self.assertIsNone(plan_audit.motivo_ruta_paquete(REPO / "auditorias" / "asunto-sintetico" / "plan"))
        self.assertIsNotNone(plan_audit.motivo_ruta_paquete(REPO))
        self.assertIsNotNone(plan_audit.motivo_ruta_paquete(REPO / "tests" / "paquete-sintetico"))
        destino = REPO / "tests" / "paquete-sintetico-no-crear"
        resultado = self._ejecutar(
            "evidencia", "agregar-tesis", "--paquete", str(destino),
            "--archivo", str(FIXTURES / "sjf_2006224.txt"), "--url", url_tesis_sjf("2006224"),
            "--fecha-consulta", FECHA_SINTETICA,
        )
        if destino.exists():  # no debería ocurrir; limpiar antes de fallar
            shutil.rmtree(destino)
        self.assertEqual(resultado.returncode, 2)
        self.assertIn("zona ignorada", resultado.stderr)


if __name__ == "__main__":
    unittest.main()
