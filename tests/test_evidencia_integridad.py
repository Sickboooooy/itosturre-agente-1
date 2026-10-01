"""Pruebas de ``comprobar_integridad`` (``itosturre/evidencia/integridad.py``).

``validar_registro`` es estructural: un registro con huellas inventadas o metadatos
alterados puede tener forma válida. Estas pruebas fijan que esos registros validan en
``[]`` (por diseño) y que la comprobación de integridad los rechaza. Sin red ni
dependencias externas.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from itosturre.evidencia import comprobar_integridad, validar_registro
from itosturre.evidencia.esquema import crear_extracto
from itosturre.evidencia.fuentes import url_leyesbiblio, url_tesis_sjf
from itosturre.evidencia.huellas import sha256_bytes, sha256_texto
from itosturre.evidencia.leyesbiblio import limpiar_documento
from itosturre.evidencia.leyesbiblio import registro_evidencia as registro_ley
from itosturre.evidencia.sjf import derivado_canonico, parsear_tesis
from itosturre.evidencia.sjf import registro_evidencia as registro_tesis

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "evidencia"
# PDF sintético: el original real no se versiona; estos bytes no son ningún PDF oficial.
PDF_SINTETICO = b"%PDF sintetico de prueba: no es un documento oficial\n"


def tesis_2031931() -> tuple[dict, bytes, str]:
    original = (FIXTURES / "sjf_2031931.txt").read_bytes()
    registro = registro_tesis(
        original,
        url=url_tesis_sjf("2031931"),
        fecha_consulta="2026-10-01T19:57Z",
        registro_esperado="2031931",
    )
    derivado = derivado_canonico(parsear_tesis(original.decode("utf-8")))
    return registro, original, derivado


def ley_cnpp() -> tuple[dict, str, str]:
    datos = json.loads((FIXTURES / "leyesbiblio_CNPP.json").read_text(encoding="utf-8"))
    documento = limpiar_documento(
        [p["texto"] for p in datos["paginas"]],
        numeros=[p["numero"] for p in datos["paginas"]],
        total_paginas=datos["total_paginas_pdf"],
    )
    registro = registro_ley(
        documento,
        archivo="CNPP.pdf",
        url=url_leyesbiblio("CNPP.pdf"),
        fecha_consulta="1800-01-01",  # sintética: la descarga real no registró fecha
        original_sha256=sha256_bytes(PDF_SINTETICO),
        original_bytes=len(PDF_SINTETICO),
        extractor="PyMuPDF fitz.Page.get_text() (modo por omisión)",
        version_extractor="PyMuPDF 1.28.0 / MuPDF 1.29.0",
        extracto=crear_extracto("Artículo 167. Causas de procedencia", "p. 52, l. 17"),
    )
    return registro, documento.texto, documento.texto_extraido


class IntegridadTesisTests(unittest.TestCase):
    def test_registro_integro(self) -> None:
        registro, original, derivado = tesis_2031931()
        self.assertEqual(comprobar_integridad(registro, original=original, derivado=derivado), [])

    def test_huella_inventada_valida_en_forma_pero_no_en_integridad(self) -> None:
        registro, original, derivado = tesis_2031931()
        falso = copy.deepcopy(registro)
        falso["original"]["sha256"] = "0" * 64
        falso["derivado"]["sha256"] = "0" * 64
        self.assertEqual(validar_registro(falso), [])  # estructural: por diseño no lo ve
        problemas = comprobar_integridad(falso, original=original, derivado=derivado)
        self.assertTrue(any(p.startswith("original.sha256") for p in problemas))
        self.assertTrue(any(p.startswith("derivado.sha256") for p in problemas))

    def test_metadatos_alterados(self) -> None:
        registro, original, derivado = tesis_2031931()
        alterado = copy.deepcopy(registro)
        # "Corregir" la discrepancia real de época: forma válida, contenido falso.
        alterado["metadatos"]["epoca"] = "Undécima Época"
        self.assertEqual(validar_registro(alterado), [])
        problemas = comprobar_integridad(alterado, original=original, derivado=derivado)
        self.assertTrue(any(p.startswith("metadatos.epoca") for p in problemas), problemas)

    def test_advertencia_borrada(self) -> None:
        registro, original, derivado = tesis_2031931()
        sin_aviso = copy.deepcopy(registro)
        sin_aviso["advertencias"] = []
        self.assertEqual(validar_registro(sin_aviso), [])
        problemas = comprobar_integridad(sin_aviso, original=original, derivado=derivado)
        self.assertTrue(any(p.startswith("advertencias") for p in problemas))

    def test_original_o_derivado_distintos(self) -> None:
        registro, original, derivado = tesis_2031931()
        otro = (FIXTURES / "sjf_2032506.txt").read_bytes()
        self.assertTrue(comprobar_integridad(registro, original=otro, derivado=derivado))
        lf = original.replace(b"\r\n", b"\n")  # mismo texto, otros bytes: no es lo capturado
        self.assertTrue(any(p.startswith("original.sha256") for p in comprobar_integridad(registro, original=lf, derivado=derivado)))
        self.assertTrue(comprobar_integridad(registro, original=original, derivado=derivado + " "))

    def test_extracto_que_no_esta_en_la_fuente(self) -> None:
        registro, original, derivado = tesis_2031931()
        ajeno = copy.deepcopy(registro)
        ajeno["extracto"] = crear_extracto("RUBRO SINTÉTICO DE PRUEBA.", "rubro")
        self.assertEqual(validar_registro(ajeno), [])
        problemas = comprobar_integridad(ajeno, original=original, derivado=derivado)
        self.assertTrue(any(p.startswith("extracto.texto") for p in problemas))

    def test_tipos_de_argumento(self) -> None:
        registro, original, derivado = tesis_2031931()
        with self.assertRaises(TypeError):
            comprobar_integridad(registro, original=original.decode("utf-8"), derivado=derivado)


class IntegridadLeyTests(unittest.TestCase):
    def test_registro_integro_con_texto_extraido(self) -> None:
        registro, derivado, extraido = ley_cnpp()
        self.assertEqual(validar_registro(registro), [])
        self.assertEqual(
            comprobar_integridad(registro, original=PDF_SINTETICO, derivado=derivado, texto_extraido=extraido),
            [],
        )

    def test_derivado_y_metadatos_alterados(self) -> None:
        registro, derivado, extraido = ley_cnpp()
        problemas = comprobar_integridad(
            registro, original=PDF_SINTETICO, derivado=derivado.replace("167", "168"), texto_extraido=extraido
        )
        self.assertTrue(any(p.startswith("derivado") for p in problemas))
        alterado = copy.deepcopy(registro)
        alterado["metadatos"]["ultima_reforma_dof"] = "1800-01-01"
        self.assertEqual(validar_registro(alterado), [])
        problemas = comprobar_integridad(alterado, original=PDF_SINTETICO, derivado=derivado, texto_extraido=extraido)
        self.assertTrue(any(p.startswith("metadatos.ultima_reforma_dof") for p in problemas))

    def test_texto_extraido_ajeno(self) -> None:
        registro, derivado, extraido = ley_cnpp()
        problemas = comprobar_integridad(
            registro, original=PDF_SINTETICO, derivado=derivado, texto_extraido=extraido + " "
        )
        self.assertTrue(any(p.startswith("metadatos.sha256_texto_extraido") for p in problemas))

    def test_original_distinto(self) -> None:
        registro, derivado, _ = ley_cnpp()
        problemas = comprobar_integridad(registro, original=PDF_SINTETICO + b"x", derivado=derivado)
        self.assertTrue(any(p.startswith("original.sha256") for p in problemas))
        self.assertTrue(any(p.startswith("original.bytes") for p in problemas))
        self.assertEqual(sha256_texto(derivado), registro["derivado"]["sha256"])


if __name__ == "__main__":
    unittest.main()
