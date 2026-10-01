"""Pruebas del registro ``evidencia/1.0``, huellas, fuentes y procedencia de fixtures.

También fija las reglas de arquitectura de la capa (D2 y "capa pura"): solo
biblioteca estándar, sin importar ``plan``/``audit``/``memoria``, sin red, sin reloj y
sin E/S de archivos salvo en ``paquete.py`` (almacén del paquete de evidencia). Sin red
ni dependencias externas.
"""
from __future__ import annotations

import ast
import copy
import json
import sys
import unittest
import unicodedata
from pathlib import Path

import itosturre.evidencia as evidencia
import itosturre.plan as plan
import itosturre.plan.estados as plan_estados
import itosturre.plan.lint as plan_lint
from itosturre.evidencia import esquema, fuentes, huellas
from itosturre.evidencia.esquema import (
    TIPO_TESIS_SJF,
    TIPOS,
    TipoEvidencia,
    construir_registro,
    crear_extracto,
    fecha_consulta_valida,
    validar_registro,
)
from itosturre.evidencia.huellas import (
    huella_registro,
    json_canonico,
    normalizar_para_cotejo,
    sha256_bytes,
    sha256_texto,
)
from itosturre.evidencia.sjf import registro_evidencia

REPO = Path(__file__).resolve().parent.parent
PAQUETE = REPO / "itosturre" / "evidencia"
FIXTURES = REPO / "tests" / "fixtures" / "evidencia"
HEX_A = "a" * 64


def registro_valido() -> dict:
    """Registro real de la tesis 2032506 (render y fecha de consulta del operador)."""
    return registro_evidencia(
        (FIXTURES / "sjf_2032506.txt").read_bytes(),
        url=fuentes.url_tesis_sjf("2032506"),
        fecha_consulta="2026-10-01T19:57Z",
        registro_esperado="2032506",
    )


def problemas_con(**cambios) -> list[str]:
    """Problemas tras aplicar cambios; la ruta usa ``__`` (``fuente__url`` → fuente.url)."""
    registro = copy.deepcopy(registro_valido())
    for ruta, valor in cambios.items():
        destino = registro
        *padres, hoja = ruta.split("__")
        for parte in padres:
            destino = destino[parte]
        if valor is _BORRAR:
            del destino[hoja]
        else:
            destino[hoja] = valor
    return validar_registro(registro)


_BORRAR = object()


class FuentesTests(unittest.TestCase):
    def test_urls_oficiales(self) -> None:
        for url in (
            "https://dof.gob.mx/nota_detalle.php?codigo=1",
            "https://www.diputados.gob.mx/LeyesBiblio/pdf/CNPP.pdf",
            "https://sjf2.scjn.gob.mx/detalle/tesis/2006224",
            "https://sjf2.scjn.gob.mx:443/detalle/tesis/2006224",
        ):
            with self.subTest(url=url):
                self.assertTrue(fuentes.url_oficial(url))
                self.assertIsNone(fuentes.motivo_url_no_oficial(url))

    def test_urls_rechazadas_con_motivo(self) -> None:
        casos = {
            "https://www.dof.gob.mx/nota_detalle.php?codigo=1": "usar dof.gob.mx",
            "http://dof.gob.mx/nota_detalle.php?codigo=1": "https",
            "https://dof.gob.mx@otro.example/x": "credenciales",
            "https://dof.gob.mx:8443/x": "puerto",
            "https://dof.gob.mx.example.com/x": "fuera de la lista",
            "": "vacía",
        }
        for url, motivo in casos.items():
            with self.subTest(url=url):
                self.assertFalse(fuentes.url_oficial(url))
                self.assertIn(motivo, fuentes.motivo_url_no_oficial(url))
        self.assertFalse(fuentes.url_oficial(None))

    def test_constructores_de_url(self) -> None:
        self.assertEqual(
            fuentes.url_leyesbiblio("CNPP.pdf"), "https://www.diputados.gob.mx/LeyesBiblio/pdf/CNPP.pdf"
        )
        self.assertEqual(fuentes.url_tesis_sjf("2006224"), "https://sjf2.scjn.gob.mx/detalle/tesis/2006224")
        for malo in ("", "../x.pdf", "a/b.pdf"):
            with self.subTest(malo=malo), self.assertRaises(ValueError):
                fuentes.url_leyesbiblio(malo)
        with self.assertRaises(ValueError):
            fuentes.url_tesis_sjf("20O6224")

    def test_plan_reexporta_la_fuente_unica(self) -> None:
        self.assertIs(plan_lint.url_oficial, fuentes.url_oficial)
        self.assertIs(plan.url_oficial, fuentes.url_oficial)
        self.assertIs(plan_lint.HOSTS_OFICIALES, fuentes.HOSTS_OFICIALES)
        self.assertIs(plan.HOSTS_OFICIALES, fuentes.HOSTS_OFICIALES)
        self.assertIs(plan_lint.HOSTS_CANONICOS, fuentes.HOSTS_CANONICOS)
        self.assertIs(plan_estados.es_marcador_pendiente, esquema.es_marcador_pendiente)
        self.assertIs(plan_estados.MARCADORES_PENDIENTES, esquema.MARCADORES_PENDIENTES)


class HuellasTests(unittest.TestCase):
    def test_vectores_conocidos(self) -> None:
        self.assertEqual(
            sha256_texto("abc"), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
        self.assertEqual(
            sha256_bytes(b""), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_huella_de_texto_sin_normalizar(self) -> None:
        compuesta = unicodedata.normalize("NFC", "Época")
        descompuesta = unicodedata.normalize("NFD", "Época")
        self.assertNotEqual(compuesta, descompuesta)
        self.assertNotEqual(sha256_texto(compuesta), sha256_texto(descompuesta))
        self.assertNotEqual(sha256_texto("Época"), sha256_texto("Época "))
        # Solo el cotejo las iguala.
        self.assertEqual(normalizar_para_cotejo(compuesta), normalizar_para_cotejo(descompuesta))

    def test_normalizacion_para_cotejo(self) -> None:
        self.assertEqual(normalizar_para_cotejo("  Décima \n ÉPOCA "), "decima epoca")
        with self.assertRaises(TypeError):
            normalizar_para_cotejo(None)
        with self.assertRaises(TypeError):
            sha256_texto(b"bytes")
        with self.assertRaises(TypeError):
            sha256_bytes("texto")

    def test_json_canonico(self) -> None:
        self.assertEqual(json_canonico({"b": 1, "a": [True, None, "é"]}), '{"a":[true,null,"é"],"b":1}')
        self.assertEqual(json_canonico({"b": 1, "a": 2}), json_canonico({"a": 2, "b": 1}))
        for invalido in ({"x": 1.5}, {"x": {1, 2}}, {1: "llave no textual"}, {"x": b"bytes"}):
            with self.subTest(invalido=invalido), self.assertRaises(ValueError):
                json_canonico(invalido)

    def test_huella_del_registro(self) -> None:
        registro = registro_valido()
        reordenado = dict(reversed(list(registro.items())))
        self.assertEqual(huella_registro(registro), huella_registro(reordenado))
        cambiado = copy.deepcopy(registro)
        cambiado["metadatos"]["rubro"] += " "
        self.assertNotEqual(huella_registro(registro), huella_registro(cambiado))


class EsquemaTests(unittest.TestCase):
    def test_registros_validos(self) -> None:
        self.assertEqual(validar_registro(registro_valido()), [])
        self.assertEqual(problemas_con(campo_desconocido="se ignora"), [])

    def test_raiz_y_version(self) -> None:
        self.assertEqual(validar_registro([]), ["raíz: debe ser un objeto"])
        self.assertTrue(any(p.startswith("esquema:") for p in problemas_con(esquema="evidencia/0.9")))
        self.assertTrue(any(p.startswith("tipo:") for p in problemas_con(tipo="tipo_inventado")))

    def test_url_no_oficial(self) -> None:
        casos = {
            "https://example.com/detalle/tesis/2032506": "no es una URL oficial",
            "https://www.dof.gob.mx/nota_detalle.php?codigo=1": "usar dof.gob.mx",
            "http://sjf2.scjn.gob.mx/detalle/tesis/2032506": "https",
            "https://www.diputados.gob.mx/LeyesBiblio/pdf/CNPP.pdf": "debe venir de sjf2.scjn.gob.mx",
            "https://sjf2.scjn.gob.mx/detalle/tesis/2031931": "no corresponde al registro digital",
        }
        for url, mensaje in casos.items():
            with self.subTest(url=url):
                problemas = problemas_con(fuente__url=url)
                self.assertTrue(any(mensaje in p for p in problemas), problemas)

    def test_url_de_ley_debe_corresponder_al_archivo(self) -> None:
        tipo = TIPOS["ley_leyesbiblio"]
        self.assertIsNone(
            tipo.validar_url("https://www.diputados.gob.mx/LeyesBiblio/pdf/CNPP.pdf", {"archivo": "CNPP.pdf"})
        )
        self.assertIn(
            "no corresponde al archivo",
            tipo.validar_url("https://www.diputados.gob.mx/LeyesBiblio/pdf/CPF.pdf", {"archivo": "CNPP.pdf"}),
        )
        self.assertIn(
            "/LeyesBiblio/pdf/",
            tipo.validar_url("https://www.diputados.gob.mx/otro/CNPP.pdf", {"archivo": "CNPP.pdf"}),
        )

    def test_fecha_de_consulta(self) -> None:
        for valida in ("2026-10-01", "2026-10-01T19:57Z", "2026-10-01T19:57:00-06:00"):
            with self.subTest(valida=valida):
                self.assertTrue(fecha_consulta_valida(valida))
        for invalida in ("2026-10-01T19:57", "2026-13-01", "20261001", "2026-10-01T25:00Z", "[VERIFICAR]", None):
            with self.subTest(invalida=invalida):
                self.assertFalse(fecha_consulta_valida(invalida))
                self.assertTrue(any("fecha_consulta" in p for p in problemas_con(fuente__fecha_consulta=invalida)))

    def test_medio_fuera_de_vocabulario(self) -> None:
        self.assertTrue(any("fuente.medio" in p for p in problemas_con(fuente__medio="captura_de_pantalla")))

    def test_hashes_malformados(self) -> None:
        for malo in ("A" * 64, "a" * 63, "g" * 64, "", None):
            with self.subTest(malo=malo):
                self.assertTrue(any("original.sha256" in p for p in problemas_con(original__sha256=malo)))
                self.assertTrue(any("derivado.sha256" in p for p in problemas_con(derivado__sha256=malo)))

    def test_original_y_derivado(self) -> None:
        for malo in (0, -1, True, "10"):
            with self.subTest(bytes=malo):
                self.assertTrue(any("original.bytes" in p for p in problemas_con(original__bytes=malo)))
        self.assertTrue(any("media_type" in p for p in problemas_con(original__media_type="pdf")))
        self.assertTrue(any("derivado.extractor" in p for p in problemas_con(derivado__extractor=" ")))
        self.assertTrue(any("transformacion" in p for p in problemas_con(derivado__transformacion="x")))
        self.assertTrue(
            any("transformacion.version" in p for p in problemas_con(derivado__transformacion={"nombre": "x"}))
        )

    def test_metadatos_de_tesis(self) -> None:
        self.assertTrue(any("metadatos.epoca" in p for p in problemas_con(metadatos__epoca="Época Sintética")))
        self.assertTrue(any("metadatos.registro" in p for p in problemas_con(metadatos__registro="20O25O6")))
        self.assertTrue(any("metadatos.materias" in p for p in problemas_con(metadatos__materias="Común")))
        self.assertTrue(any("metadatos.clave" in p for p in problemas_con(metadatos__clave=_BORRAR)))
        self.assertTrue(
            any("metadatos.fecha_publicacion" in p for p in problemas_con(metadatos__fecha_publicacion="14-08-2026"))
        )
        # null es válido: "la fuente no lo dice".
        self.assertEqual(problemas_con(metadatos__fecha_obligatoriedad=None), [])

    def test_extracto_con_huella_que_no_cuadra(self) -> None:
        extracto = crear_extracto("Texto sintético de prueba", "rubro")
        self.assertEqual(problemas_con(extracto=extracto), [])
        extracto["sha256"] = HEX_A
        self.assertTrue(any("no coincide con el texto" in p for p in problemas_con(extracto=extracto)))
        self.assertTrue(any("extracto" in p for p in problemas_con(extracto="texto suelto")))

    def test_marcadores_pendientes_nunca_son_valor(self) -> None:
        problemas = problemas_con(metadatos__rubro="[VERIFICAR EN SJF]", metadatos__instancia="[ASIGNAR]")
        self.assertTrue(any("registro.metadatos.rubro: marcador pendiente" in p for p in problemas))
        self.assertTrue(any("registro.metadatos.instancia: marcador pendiente" in p for p in problemas))
        self.assertTrue(any("marcador pendiente" in p for p in problemas_con(advertencias=[{"codigo": "x", "mensaje": "[COMPLETAR]"}])))

    def test_advertencias(self) -> None:
        self.assertTrue(any(p.startswith("advertencias:") for p in problemas_con(advertencias=None)))
        self.assertTrue(any("advertencias[0]" in p for p in problemas_con(advertencias=["texto"])))

    def test_catalogo_de_tipos_extensible_sin_mutar_el_global(self) -> None:
        with self.assertRaises(TypeError):
            TIPOS["otro"] = None  # type: ignore[index]
        propio = TipoEvidencia(
            "documento_sintetico",
            validar_url=lambda url, metadatos: None,
            validar_metadatos=lambda metadatos, ruta, problemas: None,
        )
        registro = construir_registro(
            tipo="documento_sintetico",
            url="https://dof.gob.mx/nota_detalle.php?codigo=1",
            fecha_consulta="1800-01-01",
            medio="descarga_https",
            original_sha256=HEX_A,
            original_bytes=1,
            media_type="text/plain",
            derivado_sha256=HEX_A,
            extractor="extractor sintético",
            version_extractor="0",
            metadatos={},
        )
        self.assertTrue(any(p.startswith("tipo:") for p in validar_registro(registro)))
        self.assertEqual(validar_registro(registro, tipos={**TIPOS, "documento_sintetico": propio}), [])
        self.assertNotIn("documento_sintetico", TIPOS)
        self.assertIn(TIPO_TESIS_SJF, TIPOS)


class ArquitecturaTests(unittest.TestCase):
    """Reglas de la capa pura, comprobadas sobre el código fuente."""

    PROHIBIDOS = ("itosturre.plan", "itosturre.audit", "itosturre.memoria", "itosturre.leads")
    RED = {"socket", "ssl", "requests", "httpx", "urllib3", "playwright", "subprocess", "http", "ftplib", "smtplib"}
    RELOJ = {"now", "today", "utcnow", "time", "monotonic"}
    ESCRITURA = {"open", "write_text", "write_bytes", "mkdir", "unlink", "remove", "rename", "fdopen", "mkstemp"}
    LECTURA = {"read_text", "read_bytes", "iterdir", "glob", "rglob", "listdir", "scandir", "walk", "is_file", "is_dir", "exists"}
    MODULOS_ARCHIVO = {"os", "pathlib", "tempfile", "shutil", "io", "glob"}
    # Único módulo con E/S de archivos (almacén del paquete de evidencia). Sigue sin red
    # ni reloj: esas prohibiciones aplican a todo el paquete, también a este módulo.
    CON_ARCHIVOS = "paquete.py"

    def _arboles(self):
        for ruta in sorted(PAQUETE.glob("*.py")):
            yield ruta, ast.parse(ruta.read_text(encoding="utf-8"), filename=str(ruta))

    @staticmethod
    def _llamadas(arbol):
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            yield (
                nodo.func.attr
                if isinstance(nodo.func, ast.Attribute)
                else nodo.func.id
                if isinstance(nodo.func, ast.Name)
                else ""
            )

    def test_solo_biblioteca_estandar_y_sin_dependencias_hacia_arriba(self) -> None:
        estandar = set(sys.stdlib_module_names)
        for ruta, arbol in self._arboles():
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.ImportFrom):
                    if nodo.level:
                        # Relativo: solo dentro del paquete (nivel 1).
                        self.assertEqual(nodo.level, 1, f"{ruta.name}: import relativo fuera del paquete")
                        continue
                    modulos = [nodo.module or ""]
                elif isinstance(nodo, ast.Import):
                    modulos = [alias.name for alias in nodo.names]
                else:
                    continue
                for modulo in modulos:
                    with self.subTest(archivo=ruta.name, modulo=modulo):
                        self.assertFalse(modulo.startswith(self.PROHIBIDOS))
                        raiz = modulo.split(".")[0]
                        self.assertIn(raiz, estandar | {"__future__"})
                        self.assertNotIn(raiz, self.RED)
                        self.assertNotEqual(modulo, "urllib.request")

    def test_sin_reloj_ni_escritura(self) -> None:
        for ruta, arbol in self._arboles():
            prohibidas = self.RELOJ if ruta.name == self.CON_ARCHIVOS else self.RELOJ | self.ESCRITURA | self.LECTURA
            for nombre in self._llamadas(arbol):
                with self.subTest(archivo=ruta.name, llamada=nombre):
                    self.assertNotIn(nombre, prohibidas)

    def test_solo_el_paquete_importa_modulos_de_archivos(self) -> None:
        importadores = set()
        for ruta, arbol in self._arboles():
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    raices = {alias.name.split(".")[0] for alias in nodo.names}
                elif isinstance(nodo, ast.ImportFrom) and not nodo.level:
                    raices = {(nodo.module or "").split(".")[0]}
                else:
                    continue
                if raices & self.MODULOS_ARCHIVO:
                    importadores.add(ruta.name)
        self.assertEqual(importadores, {self.CON_ARCHIVOS})

    def test_el_paquete_tampoco_usa_reloj_ni_red(self) -> None:
        # La exención del paquete es solo para archivos: reloj y red siguen prohibidos.
        arbol = ast.parse((PAQUETE / self.CON_ARCHIVOS).read_text(encoding="utf-8"))
        self.assertFalse(set(self._llamadas(arbol)) & self.RELOJ)
        self.assertTrue(set(self._llamadas(arbol)) & self.ESCRITURA)  # la exención se usa

    def test_exportaciones_publicas(self) -> None:
        for nombre in evidencia.__all__:
            with self.subTest(nombre=nombre):
                self.assertTrue(hasattr(evidencia, nombre))


class ProcedenciaFixturesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifiesto = json.loads((FIXTURES / "manifiesto.json").read_text(encoding="utf-8"))
        self.entradas = {f["archivo"]: f for f in self.manifiesto["fixtures"]}

    def test_manifiesto_y_carpeta_coinciden(self) -> None:
        en_carpeta = {ruta.name for ruta in FIXTURES.iterdir() if ruta.name != "manifiesto.json"}
        self.assertEqual(en_carpeta, set(self.entradas))

    def test_huellas_y_tamano_de_cada_fixture(self) -> None:
        for nombre, entrada in self.entradas.items():
            datos = (FIXTURES / nombre).read_bytes()
            with self.subTest(fixture=nombre):
                self.assertEqual(sha256_bytes(datos), entrada["sha256_archivo"])
                self.assertLess(len(datos), 60_000)

    def test_procedencia_completa_o_declarada_como_no_registrada(self) -> None:
        for nombre, entrada in self.entradas.items():
            with self.subTest(fixture=nombre):
                self.assertIsNone(fuentes.motivo_url_no_oficial(entrada["url_oficial"]))
                original = entrada["original"]
                self.assertTrue(huellas.es_sha256(original["sha256"]))
                self.assertGreater(original["bytes"], 0)
                self.assertTrue(entrada["extractor"].strip())
                self.assertTrue(entrada["version_extractor"].strip())
                if entrada["fecha_consulta"] is None:
                    self.assertTrue(entrada["nota_fecha"].startswith("no registrada"))
                else:
                    self.assertTrue(fecha_consulta_valida(entrada["fecha_consulta"]))
                tipo = TIPOS[entrada["tipo"]]
                metadatos = (
                    {"archivo": original["archivo"]}
                    if entrada["tipo"] == "ley_leyesbiblio"
                    else {"registro": nombre[len("sjf_") : -len(".txt")]}
                )
                self.assertIsNone(tipo.validar_url(entrada["url_oficial"], metadatos))

    def test_paginas_de_leyesbiblio(self) -> None:
        for nombre, entrada in self.entradas.items():
            if entrada["tipo"] != "ley_leyesbiblio":
                continue
            datos = json.loads((FIXTURES / nombre).read_text(encoding="utf-8"))
            with self.subTest(fixture=nombre):
                self.assertEqual(datos["archivo"], entrada["original"]["archivo"])
                self.assertEqual(datos["total_paginas_pdf"], entrada["original"]["paginas_pdf"])
                self.assertEqual([p["numero"] for p in datos["paginas"]], entrada["paginas"])
                for pagina in datos["paginas"]:
                    self.assertEqual(sha256_texto(pagina["texto"]), pagina["sha256_texto"])

    def test_renders_sjf_son_el_original_byte_a_byte(self) -> None:
        for nombre, entrada in self.entradas.items():
            if entrada["tipo"] != "tesis_sjf":
                continue
            with self.subTest(fixture=nombre):
                self.assertEqual(entrada["original"]["sha256"], entrada["sha256_archivo"])
                crudo = (FIXTURES / nombre).read_bytes()
                lf = entrada["original"]["sha256_innertext_lf"]
                self.assertEqual(lf["valor"], sha256_bytes(crudo.replace(b"\r\n", b"\n")))
                if lf["sha256_impresa_en_captura"] is None:
                    self.assertEqual(lf["origen"], "reconstruida (CRLF→LF); sin huella de captura registrada")
                else:
                    self.assertEqual(lf["sha256_impresa_en_captura"], lf["valor"])
                    self.assertEqual(
                        lf["origen"],
                        "reconstruida (CRLF→LF) y coincidente con la huella impresa en la captura",
                    )

    def test_huellas_de_captura_conocidas(self) -> None:
        capturas = {
            nombre: entrada["original"]["sha256_innertext_lf"]["sha256_impresa_en_captura"]
            for nombre, entrada in self.entradas.items()
            if entrada["tipo"] == "tesis_sjf"
        }
        self.assertEqual(
            capturas,
            {
                "sjf_2006224.txt": None,
                "sjf_2031931.txt": "4fa85f1c1ae4b347d668595ac787e3f9bc67711cd6094ce47b36e02ee9b1b00e",
                "sjf_2032506.txt": "821674b6e0613567003d19f0022cd4d77f7d9dbf8dcc37d7b71526e3b21ccb89",
            },
        )

    def test_politica_de_datos_autoriza_cada_fixture(self) -> None:
        politica = json.loads((REPO / "config" / "data-policy.json").read_text(encoding="utf-8"))
        autorizados = set(politica["tracked_validation_fixtures"])
        for ruta in FIXTURES.iterdir():
            with self.subTest(fixture=ruta.name):
                self.assertIn(f"tests/fixtures/evidencia/{ruta.name}", autorizados)

    def test_fixtures_sin_conversion_de_fin_de_linea(self) -> None:
        reglas = (REPO / ".gitattributes").read_text(encoding="utf-8").splitlines()
        self.assertIn("tests/fixtures/evidencia/** -text", reglas)


if __name__ == "__main__":
    unittest.main()
