"""Pruebas de ``scripts/vigencia_corpus.py``: ¿el corpus indexado sigue vigente?

Sin red. Las páginas oficiales son fragmentos HTML sintéticos con la forma de los portales
(índices de LeyesBiblio, listado de la Biblioteca Virtual del Congreso de Jalisco) y el índice
es un sqlite mínimo con las tablas de Chroma que lee el script. Datos rotulados como
sintéticos ("LEY SINTÉTICA DE PRUEBA", artículos 9999, fechas de 1800-1802): nunca un dato
normativo inventado con apariencia real.

Lo que se fija: un cotejo sin evidencia oficial nunca da 🟢 ni 🔴 (es 🟡 NO VERIFICABLE),
dos ordenamientos distintos no se comparan por fecha y solo se consulta una URL oficial.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import vigencia_corpus as vc

BASE_LEYES = "https://www.diputados.gob.mx/LeyesBiblio/index.htm"
BASE_REGLAMENTOS = "https://www.diputados.gob.mx/LeyesBiblio/regla.htm"
BASE_JALISCO = "https://congresoweb.congresojal.gob.mx/BibliotecaVirtual/busquedasleyes/Listado%272.cfm"

INDICE_LEYES = """<table>
<tr><td>1</td><td><a href="ref/lsp.htm">LEY SINTÉTICA DE PRUEBA</a> DOF 01/01/1800</td>
<td>DOF 15/03/1801</td><td><a href="pdf/LSP.pdf">PDF</a></td></tr>
<tr><td>2</td><td>LEY SINTÉTICA SIN REFORMAS DOF 02/02/1800</td><td>Sin reforma</td>
<td><a href="pdf/LSSR.pdf">PDF</a></td></tr>
<tr><td>3</td><td>LEY SINTÉTICA ABROGADA (Abrogada DOF 03/03/1802)</td><td>DOF 01/06/1801</td>
<td><a href="pdf/LSA.pdf">PDF</a></td></tr>
</table>"""
INDICE_REGLAMENTOS = """<table>
<tr><td>1</td><td>REGLAMENTO de la Ley Sintética de Prueba Original DOF 01/01/1800
Reformas DOF 02/02/1801, 03/03/1802</td><td></td><td><a href="regla/Reg_LSP.pdf">PDF</a></td></tr>
</table>"""
LISTADO_JALISCO = """<table>
<tr><td class="leyreg">Ley Sintética de Prueba del Estado de Jalisco</td><td>15/03/1801</td>
<td><a href="../legislacion/Ley%20Sintetica.pdf">PDF</a></td><td>12345</td></tr>
<tr><td class="leyreg">Código Sintético de Prueba</td><td>01/06/1801</td>
<td><a href="../legislacion/Codigo.pdf">PDF</a></td><td>A.I. 99/1801</td></tr>
</table>"""

LEY = "LEY SINTÉTICA DE PRUEBA.pdf"
LEY_JAL = "Ley Sintética de Prueba del Estado de Jalisco.pdf"
ENTRADA_FED = {"tipo": "federal", "clave": "LSP"}
ENTRADA_JAL = {"tipo": "jalisco", "nombre_oficial": "Ley Sintética de Prueba del Estado de Jalisco"}


def chunk0_federal(titulo: str = "LEY SINTÉTICA DE PRUEBA", sello: str = "Última Reforma DOF 15-03-1801") -> str:
    return (
        f"{titulo}\nCÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN\nSecretaría General\n"
        f"Secretaría de Servicios Parlamentarios\n{sello}\n1 de 9\nArtículo 9999.- Texto sintético."
    )


def info(chunk0: str = "", **extra) -> dict:
    datos = {
        "chunks": 10, "indexado_utc": "2026-01-01 10:00:00", "indexado_min_utc": "2026-01-01 09:58:00",
        "chunk0": chunk0, "tabla_max": None, "decretos": set(), "resoluciones": set(), "mixta": False,
    }
    datos.update(extra)
    return datos


def oficiales() -> dict:
    return {
        "federal": vc.parse_leyesbiblio(INDICE_LEYES, BASE_LEYES, "leyes"),
        "federal_reglamento": vc.parse_leyesbiblio(INDICE_REGLAMENTOS, BASE_REGLAMENTOS, "reglamentos"),
        "jalisco": vc.parse_jalisco(LISTADO_JALISCO, BASE_JALISCO),
    }


class FuentesOficialesTests(unittest.TestCase):
    def test_indice_de_leyes(self) -> None:
        leyes = vc.parse_leyesbiblio(INDICE_LEYES, BASE_LEYES, "leyes")
        self.assertEqual(set(leyes), {"LSP", "LSSR", "LSA"})
        lsp = leyes["LSP"]
        self.assertEqual(lsp["nombre"], "LEY SINTÉTICA DE PRUEBA")
        self.assertEqual(lsp["ultima"], dt.date(1801, 3, 15))
        self.assertEqual(lsp["url_pdf"], "https://www.diputados.gob.mx/LeyesBiblio/pdf/LSP.pdf")
        self.assertEqual(lsp["url_historial"], "https://www.diputados.gob.mx/LeyesBiblio/ref/lsp.htm")
        self.assertEqual(lsp["abrogado"], "")
        # "Sin reforma": cuenta la publicación original.
        self.assertEqual(leyes["LSSR"]["ultima"], dt.date(1800, 2, 2))
        self.assertIn("Sin reforma", leyes["LSSR"]["ultima_txt"])
        self.assertIn("Abrogada", leyes["LSA"]["abrogado"])

    def test_indice_de_reglamentos(self) -> None:
        reglamentos = vc.parse_leyesbiblio(INDICE_REGLAMENTOS, BASE_REGLAMENTOS, "reglamentos")
        reglamento = reglamentos["Reg_LSP"]
        self.assertEqual(reglamento["nombre"], "REGLAMENTO de la Ley Sintética de Prueba")
        self.assertEqual(reglamento["ultima"], dt.date(1802, 3, 3))

    def test_listado_de_jalisco(self) -> None:
        listado = vc.parse_jalisco(LISTADO_JALISCO, BASE_JALISCO)
        ley = listado[vc.norm("Ley Sintética de Prueba del Estado de Jalisco")]
        self.assertEqual(ley["ultima"], dt.date(1801, 3, 15))
        self.assertEqual(ley["decreto"], "12345")
        self.assertEqual(ley["ultima_txt"], "P.O. 15/03/1801 · decreto 12345")
        self.assertTrue(vc.es_fuente_oficial(ley["url_pdf"]))
        codigo = listado[vc.norm("Código Sintético de Prueba")]
        self.assertEqual((codigo["decreto"], codigo["resolucion"]), ("", "99/1801"))

    def test_solo_se_consulta_una_url_oficial(self) -> None:
        self.assertTrue(all(vc.es_fuente_oficial(url) for _, url in vc.PAGINAS.values()))
        for url in ("file:///tmp/index.htm", "http://www.diputados.gob.mx/LeyesBiblio/index.htm",
                    "https://www.diputados.gob.mx.example.com/LeyesBiblio/index.htm"):
            with self.subTest(url=url):
                self.assertFalse(vc.es_fuente_oficial(url))
        paginas = dict(vc.PAGINAS, federal=("Espejo sintético", "file:///tmp/index.htm"))
        with mock.patch.object(vc, "PAGINAS", paginas), \
                mock.patch.object(vc, "descargar", side_effect=AssertionError("no debe descargar")):
            datos, errores = vc.consultar_oficiales({"federal"})
        self.assertEqual(datos, {})
        self.assertIn("no es una URL https de un host oficial", errores["federal"])
        fila = vc.clasificar(LEY, info(chunk0_federal()), ENTRADA_FED, datos, errores)
        self.assertEqual((fila["estado"], vc.SEMAFORO[fila["estado"]]), ("NO_VERIFICABLE", vc.AMARILLO))

    def test_pagina_sin_filas_no_es_sin_hallazgos(self) -> None:
        with mock.patch.object(vc, "descargar", return_value="<html>mantenimiento</html>"):
            datos, errores = vc.consultar_oficiales({"federal"})
        self.assertEqual(datos, {})
        self.assertIn("no trajo filas reconocibles", errores["federal"])


class ClasificacionTests(unittest.TestCase):
    def clasificar(self, fuente=LEY, datos=None, entrada=ENTRADA_FED, errores=None) -> dict:
        return vc.clasificar(fuente, datos, entrada, oficiales(), errores or {})

    def test_version_indexada_federal(self) -> None:
        fecha, texto, clase, confianza = vc.version_indexada(info(chunk0_federal()), "federal")
        self.assertEqual((fecha, texto, clase, confianza),
                         (dt.date(1801, 3, 15), "Última Reforma DOF 15-03-1801", "reforma", "alta"))

    def test_vigente(self) -> None:
        fila = self.clasificar(datos=info(chunk0_federal()))
        self.assertEqual(fila["estado"], "VIGENTE")
        self.assertTrue(fila["identidad_confirmada"])

    def test_desactualizada(self) -> None:
        fila = self.clasificar(datos=info(chunk0_federal(sello="Última Reforma DOF 01-01-1801")))
        self.assertEqual(fila["estado"], "DESACTUALIZADA")
        self.assertEqual(fila["rezago_dias"], 73)
        self.assertIn("transitorios", fila["detalle"])

    # LeyesBiblio cuenta como última modificación el acuerdo anual que actualiza montos y multas
    # (p. ej. el de la LFPC), y el PDF que lo incorpora lo anota bajo el sello de la última reforma.
    MONTOS = "Actualización de montos de operaciones y multas por Acuerdo DOF {}"

    def test_acuerdo_de_montos_del_encabezado_es_la_version_indexada(self) -> None:
        sello = "Última Reforma DOF 01-01-1801\n" + self.MONTOS.format("15-03-1801")
        fecha, texto, clase, _ = vc.version_indexada(info(chunk0_federal(sello=sello)), "federal")
        self.assertEqual(fecha, dt.date(1801, 3, 15))
        self.assertEqual(clase, "reforma")
        self.assertIn("Última Reforma DOF 01-01-1801", texto)
        self.assertIn("Acuerdo DOF 15-03-1801", texto)

    def test_acuerdo_de_montos_al_dia_es_vigente(self) -> None:
        sello = "Última Reforma DOF 01-01-1801\n" + self.MONTOS.format("15-03-1801")
        fila = self.clasificar(datos=info(chunk0_federal(sello=sello)))
        self.assertEqual(fila["estado"], "VIGENTE")

    def test_acuerdo_de_montos_anterior_a_la_ultima_oficial_sigue_desactualizada(self) -> None:
        sello = "Última Reforma DOF 01-01-1801\n" + self.MONTOS.format("01-02-1801")
        fila = self.clasificar(datos=info(chunk0_federal(sello=sello)))
        self.assertEqual(fila["estado"], "DESACTUALIZADA")
        self.assertEqual(fila["rezago_dias"], 42)

    def test_acuerdo_de_montos_viejo_no_cambia_la_version(self) -> None:
        sello = "Última Reforma DOF 15-03-1801\n" + self.MONTOS.format("01-01-1801")
        fecha, texto, _, _ = vc.version_indexada(info(chunk0_federal(sello=sello)), "federal")
        self.assertEqual((fecha, texto), (dt.date(1801, 3, 15), "Última Reforma DOF 15-03-1801"))

    def test_otro_ordenamiento_no_se_compara_por_fecha(self) -> None:
        fila = self.clasificar(datos=info(chunk0_federal(titulo="LEY DISTINTA DE PRUEBA",
                                                         sello="Última Reforma DOF 01-01-1800")))
        self.assertEqual(fila["estado"], "NO_VERIFICABLE")
        self.assertIn("LEY DISTINTA DE PRUEBA", fila["detalle"])

    def test_version_oficial_mas_vieja_que_la_indexada_es_anomalia(self) -> None:
        fila = self.clasificar(datos=info(chunk0_federal(sello="Última Reforma DOF 01-01-1802")))
        self.assertEqual(fila["estado"], "NO_VERIFICABLE")

    def test_sin_fuente_oficial_o_sin_fila_no_es_rojo(self) -> None:
        caida = self.clasificar(datos=info(chunk0_federal()), errores={"federal": "sin red"})
        sin_fila = self.clasificar(datos=info(chunk0_federal()), entrada={"tipo": "federal", "clave": "NADA"})
        sin_sello = self.clasificar(datos=info("LEY SINTÉTICA DE PRUEBA sin sello"))
        for fila in (caida, sin_fila, sin_sello):
            self.assertEqual(fila["estado"], "NO_VERIFICABLE")

    def test_abrogada(self) -> None:
        fila = self.clasificar(datos=info(chunk0_federal(titulo="LEY SINTÉTICA ABROGADA")),
                               entrada={"tipo": "federal", "clave": "LSA"})
        self.assertEqual(fila["estado"], "ABROGADA")
        self.assertEqual(vc.SEMAFORO[fila["estado"]], vc.AMARILLO)

    def test_indexacion_mixta_no_acredita_vigencia(self) -> None:
        fila = self.clasificar(datos=info(chunk0_federal(), mixta=True))
        self.assertEqual(fila["estado"], "NO_VERIFICABLE")
        self.assertTrue(any("mixta" in alerta for alerta in fila["alertas"]))

    def test_estados_sin_cotejo(self) -> None:
        self.assertEqual(self.clasificar(entrada={"tipo": "descartado"}, datos=info())["estado"], "DESCARTADA")
        self.assertEqual(self.clasificar(entrada={"tipo": "descartado"})["estado"], "NO_APLICA")
        self.assertEqual(self.clasificar(entrada={"tipo": "tratado"}, datos=info())["estado"], "NO_APLICA")
        self.assertEqual(self.clasificar(entrada={"tipo": "manual"}, datos=info())["estado"], "MANUAL")
        self.assertEqual(self.clasificar()["estado"], "NO_INDEXADA")
        self.assertEqual(self.clasificar(entrada={}, datos=info())["estado"], "NO_VERIFICABLE")

    def test_reglamento_por_nombre_oficial(self) -> None:
        entrada = {"tipo": "federal_reglamento", "nombre_oficial": "REGLAMENTO de la Ley Sintética de Prueba"}
        chunk0 = chunk0_federal(titulo="REGLAMENTO DE LA LEY SINTÉTICA DE PRUEBA", sello="Última Reforma DOF 03-03-1802")
        self.assertEqual(self.clasificar(datos=info(chunk0), entrada=entrada)["estado"], "VIGENTE")

    def test_jalisco_dos_senales(self) -> None:
        casos = {
            # (fecha de la tabla de reformas, decretos citados): (estado, confianza)
            (dt.date(1801, 3, 15), frozenset({"12345"})): ("VIGENTE", "alta"),
            (dt.date(1801, 1, 1), frozenset()): ("DESACTUALIZADA", "alta"),
            (None, frozenset({"12345"})): ("VIGENTE", "alta"),
            # La fecha dice "vieja" pero el texto cita el decreto de la última reforma: 🟡.
            (dt.date(1801, 1, 1), frozenset({"12345"})): ("NO_VERIFICABLE", "alta"),
        }
        for (tabla_max, decretos), (estado, confianza) in casos.items():
            with self.subTest(tabla_max=tabla_max, decretos=set(decretos)):
                fila = self.clasificar(LEY_JAL, info(tabla_max=tabla_max, decretos=set(decretos)), ENTRADA_JAL)
                self.assertEqual((fila["estado"], fila["confianza"]), (estado, confianza))


def crear_indice(carpeta: Path, chunks: list[tuple[str, int, str, str]], coleccion: str = vc.COLLECTION_NAME) -> Path:
    """sqlite con las tablas de Chroma que lee el script; chunks = (fuente, índice, texto, created_at)."""
    chroma = carpeta / "chroma_db"
    chroma.mkdir()
    con = sqlite3.connect(chroma / "chroma.sqlite3")
    con.executescript("""
        CREATE TABLE collections (id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE segments (id TEXT PRIMARY KEY, collection TEXT NOT NULL);
        CREATE TABLE embeddings (id INTEGER PRIMARY KEY, segment_id TEXT NOT NULL, created_at TIMESTAMP NOT NULL);
        CREATE TABLE embedding_metadata (id INTEGER, key TEXT NOT NULL, string_value TEXT, PRIMARY KEY (id, key));
    """)
    con.execute("INSERT INTO collections VALUES ('c1', ?)", (coleccion,))
    con.execute("INSERT INTO segments VALUES ('s1', 'c1')")
    for i, (fuente, indice, texto, creado) in enumerate(chunks, 1):
        con.execute("INSERT INTO embeddings VALUES (?, 's1', ?)", (i, creado))
        con.executemany("INSERT INTO embedding_metadata VALUES (?, ?, ?)",
                        [(i, "source", fuente), (i, "chunk_index", str(indice)), (i, "chroma:document", texto)])
    con.commit()
    con.close()
    return chroma


class IndiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.carpeta = Path(self.tmp.name)

    def test_tabla_de_reformas_solo_de_la_cola(self) -> None:
        # Una fecha en el articulado (chunk 1) no es la versión; la de la tabla final (chunk 9) sí.
        chunks = [(LEY_JAL, i, f"Artículo 9999.- Texto sintético {i}.", "2026-01-01 10:00:00") for i in range(10)]
        chunks[1] = (LEY_JAL, 1, "Artículo 9999.- Vigente desde Dic. 31 de 1801.", "2026-01-01 10:00:00")
        chunks[9] = (LEY_JAL, 9, "TABLA DE REFORMAS Ene. 20 de 1801 sec. II · 12345/LXII/01", "2026-01-01 10:00:00")
        chroma = crear_indice(self.carpeta, chunks)
        # Con el piso real (1917) las fechas sintéticas de 1801 no cuentan como reforma.
        self.assertIsNone(vc.leer_indice(chroma)[LEY_JAL]["tabla_max"])
        with mock.patch.object(vc, "FECHA_MINIMA_TABLA", dt.date(1800, 1, 1)):
            indice = vc.leer_indice(chroma)
        self.assertEqual(indice[LEY_JAL]["tabla_max"], dt.date(1801, 1, 20))
        self.assertEqual(indice[LEY_JAL]["decretos"], {"12345"})
        self.assertFalse(indice[LEY_JAL]["mixta"])
        self.assertEqual(indice[LEY_JAL]["chunks"], 10)

    def test_indexacion_mixta(self) -> None:
        chunks = [(LEY, 0, chunk0_federal(), "2026-01-01 10:00:00"), (LEY, 1, "Cola", "2026-03-01 10:00:00")]
        indice = vc.leer_indice(crear_indice(self.carpeta, chunks))
        self.assertTrue(indice[LEY]["mixta"])
        self.assertEqual(indice[LEY]["indexado_min_utc"], "2026-01-01 10:00:00")

    def test_otra_coleccion_no_cuenta(self) -> None:
        chroma = crear_indice(self.carpeta, [(LEY, 0, chunk0_federal(), "2026-01-01 10:00:00")], coleccion="otra")
        self.assertEqual(vc.leer_indice(chroma), {})

    def test_verificacion_completa(self) -> None:
        gemelo = "Copia sintética.pdf"
        chunks = [(LEY, 0, chunk0_federal(sello="Última Reforma DOF 01-01-1801"), "2026-01-01 10:00:00"),
                  (gemelo, 0, chunk0_federal(sello="Última Reforma DOF 01-01-1801"), "2026-01-01 10:00:00")]
        chroma = crear_indice(self.carpeta, chunks)
        manifiesto = {"fuentes": {LEY: ENTRADA_FED, gemelo: {"tipo": "federal", "clave": "LSSR"},
                                  "No indexada.pdf": {"tipo": "federal", "clave": "LSA"}}}
        with mock.patch.object(vc, "consultar_oficiales", return_value=(oficiales(), {})):
            r = vc.verificar(chroma, self.carpeta / "corpus", manifiesto)
        filas = {f["fuente"]: f for f in r["filas"]}
        self.assertEqual(r["estado_corrida"], "completa")
        self.assertEqual(r["veredicto"], vc.ROJO)  # basta una desactualizada: no se promedia
        self.assertEqual(filas[LEY]["estado"], "DESACTUALIZADA")
        # El gemelo dice ser otra ley pero su texto es el de LSP: la alerta recae en él, no en LSP.
        self.assertEqual(filas[gemelo]["estado"], "NO_VERIFICABLE")
        self.assertTrue(any("Contenido idéntico" in a for a in filas[gemelo]["alertas"]))
        self.assertEqual(filas[LEY]["alertas"], [])
        self.assertEqual(filas["No indexada.pdf"]["estado"], "NO_INDEXADA")
        # La actualización propuesta es la re-ingesta por fuente, simulada primero; nunca un
        # comando que borre la colección entera.
        pasos = vc.pasos_actualizacion(r)
        self.assertIn(f'--fuente "{LEY}" --simular', pasos["simular"])
        self.assertNotIn(gemelo, pasos["reingestar"])
        self.assertFalse(any("--reingest" in c or "--clear" in c for c in pasos.values()))
        self.assertIn("## Cómo actualizar", vc.reporte_md(r))

    def test_sin_desactualizadas_no_hay_pasos_de_actualizacion(self) -> None:
        chroma = crear_indice(self.carpeta, [(LEY, 0, chunk0_federal(), "2026-01-01 10:00:00")])
        with mock.patch.object(vc, "consultar_oficiales", return_value=(oficiales(), {})):
            r = vc.verificar(chroma, self.carpeta / "corpus", {"fuentes": {LEY: ENTRADA_FED}})
        self.assertEqual(r["veredicto"], vc.VERDE)
        self.assertNotIn("## Cómo actualizar", vc.reporte_md(r))

    def test_indice_ilegible_es_amarillo(self) -> None:
        r = vc.verificar(self.carpeta / "no_existe", self.carpeta / "corpus", {"fuentes": {}})
        self.assertEqual((r["estado_corrida"], r["veredicto"]), ("fallida", vc.AMARILLO))
        self.assertTrue(r["razon"].startswith("NO SE PUDO VERIFICAR"))


class ManifiestoTests(unittest.TestCase):
    """El manifiesto de fuentes oficiales acompaña al catálogo del resolutor (CONTRIBUTING §4)."""

    def test_toda_ley_del_resolutor_tiene_fuente_oficial_y_ninguna_descartada(self) -> None:
        import json
        import unicodedata

        import OpenNotebook

        def nfc(texto: str) -> str:
            return unicodedata.normalize("NFC", texto)

        manifiesto = json.loads((vc.REPO / "scripts" / "fuentes_oficiales.json").read_text(encoding="utf-8"))
        fuentes = {nfc(k): v for k, v in manifiesto["fuentes"].items()}
        for pdf in sorted({nfc(v) for v in OpenNotebook.LAW_SOURCE_MAP.values()}):
            with self.subTest(pdf=pdf):
                self.assertIn(pdf, fuentes, "agrega su entrada a scripts/fuentes_oficiales.json")
                self.assertNotEqual(fuentes[pdf]["tipo"], "descartado", "una fuente descartada no se mapea")
        for pdf, entrada in fuentes.items():
            with self.subTest(pdf=pdf):
                self.assertIn(entrada["tipo"], {"federal", "federal_reglamento", "jalisco", "tratado",
                                                "manual", "descartado"})
                if entrada["tipo"] == "federal":
                    self.assertRegex(entrada["clave"], r"^[A-Za-z_]+$")
                if entrada["tipo"] in {"federal_reglamento", "jalisco"}:
                    self.assertTrue(entrada["nombre_oficial"])


class AgendaTests(unittest.TestCase):
    def test_cada_cuanto_toca(self) -> None:
        chroma = Path("/indice/sintetico")
        hoy = dt.date(1801, 3, 1)
        self.assertEqual(vc.motivo_para_correr({}, hoy, 60, chroma), "primera verificación")
        estado = {"ultima_completa": "1801-01-15", "chroma": str(chroma)}
        self.assertEqual(vc.motivo_para_correr(estado, hoy, 60, chroma), "")
        self.assertEqual(vc.motivo_para_correr(estado, dt.date(1801, 3, 16), 60, chroma), "pasaron 60 días")
        self.assertEqual(vc.motivo_para_correr(estado, hoy, 60, Path("/otro")), "cambió el índice vigilado")


if __name__ == "__main__":
    unittest.main()
