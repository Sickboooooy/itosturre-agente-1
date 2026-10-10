"""Vigencia del corpus en el veredicto VVCA y en la ruta ``query`` (rama fix/vvca-query-vigencia).

El 🟢 normativo acredita existencia y ubicación en la VERSIÓN INDEXADA (verde determinista,
3-oct-2026). Con un reporte de ``scripts/vigencia_corpus.py`` hecho sobre el mismo índice que
dice que esa versión ya no es la vigente (DESACTUALIZADA o ABROGADA):

- una cita localizada no sale 🟢 (tope 84, traza ``partial``);
- la prueba positiva de inexistencia (D10, criterio C) no sale 🔴: prueba que el artículo no
  está en ESA versión, no en la vigente (el 873-K de la LFT, adicionado en 2019, frente a un
  texto de 2015);
- nunca 🔴 por vigencia; sin reporte aplicable nada cambia.

La ruta ``query`` deja de dar 🟢 por similitud: un artículo nombrado recibe el veredicto de
``audit`` (misma cita, mismo semáforo) y los pasajes cercanos quedan como contexto (⚪), nunca
como si fueran el artículo.

Corre sin dependencias con la colección y el codificador falsos de ``tests/vvca_falsos.py``.
Fragmentos SINTÉTICOS (texto de relleno con la forma de los que guarda la ingesta); las leyes
reales aparecen solo como texto a auditar y la ley de inexistencia es la de
``tests/test_vvca_inexistencia.py`` (reforma ficticia del 01-01-2099). Los reportes de vigencia
son sintéticos: fechas de 1800-1801.
"""
from __future__ import annotations

import json
import unicodedata
import unittest
from pathlib import Path
from unittest import mock

from itosturre.audit import vigencia as vg
from scoring_vvca import veredicto_global
from tests import test_vvca_inexistencia as inexistencia
from tests.test_vvca_nucleo import AuditoriaBase, _articulo
from tests.test_vvca_verde_determinista import consulta_de
from tests.vvca_falsos import FakeCollection, importar_opennotebook

ON = importar_opennotebook()
CNPP = ON.LAW_SOURCE_MAP["cnpp"]
CFF = ON.LAW_SOURCE_MAP["cff"]
FECHA = "1800-01-01"
MOTIVO_CNPP = (
    "la versión indexada de CNPP (Última Reforma DOF 01-01-1800) no es la vigente: la fuente "
    "oficial publicó DOF 02/01/1801 (reporte de vigencia del 1800-01-01)"
)


def fila(fuente: str, estado: str, chunks: int, etiqueta: str = "CNPP") -> dict:
    return {
        "fuente": fuente, "estado": estado, "chunks": chunks, "etiqueta": etiqueta,
        "version_indexada": "Última Reforma DOF 01-01-1800", "version_oficial": "DOF 02/01/1801",
        "url_pdf": "https://www.diputados.gob.mx/LeyesBiblio/pdf/SINTETICA.pdf",
    }


def reporte(chroma: str, *filas: dict) -> dict:
    return {"fecha": FECHA, "chroma": chroma, "filas": list(filas)}


# ─────────────────────────────────────────
# Política pura
# ─────────────────────────────────────────

class PoliticaVigenciaTests(unittest.TestCase):
    def cargar(self, *filas: dict) -> vg.ReporteVigencia:
        return vg.cargar_reporte(reporte("/indice", *filas), "/reportes/vigencia_1800-01-01.json")

    def test_cargar_reporte_exige_su_forma(self) -> None:
        r = self.cargar(fila(CNPP, "VIGENTE", 3))
        self.assertEqual((r.fecha, r.chroma, list(r.filas)), (FECHA, "/indice", [CNPP]))
        for datos in ({}, {"filas": []}, {"fecha": FECHA, "chroma": "/x"}, [],
                      {"fecha": FECHA, "filas": []}):
            with self.subTest(datos=datos), self.assertRaises(ValueError):
                vg.cargar_reporte(datos, "x.json")

    def test_desactualizada_con_el_indice_intacto_no_es_vigente(self) -> None:
        estado = vg.vigencia_de_fuente(self.cargar(fila(CNPP, "DESACTUALIZADA", 3)), CNPP, 3)
        self.assertEqual(estado["estado"], vg.FUENTE_NO_VIGENTE)
        self.assertEqual(estado["motivo"], MOTIVO_CNPP)
        self.assertEqual((estado["etiqueta"], estado["reporte"]), ("CNPP", FECHA))

    def test_abrogada(self) -> None:
        estado = vg.vigencia_de_fuente(self.cargar(fila(CNPP, "ABROGADA", 3)), CNPP, 3)
        self.assertEqual(estado["estado"], vg.FUENTE_NO_VIGENTE)
        self.assertEqual(estado["motivo"], "CNPP está abrogada según la fuente oficial "
                                           "(DOF 02/01/1801; reporte de vigencia del 1800-01-01)")

    def test_otros_estados(self) -> None:
        casos = {
            # (estado del reporte, fragmentos hoy): estado de la fuente
            ("VIGENTE", 3): vg.FUENTE_VIGENTE,
            ("MANUAL", 3): vg.FUENTE_SIN_DATO,
            ("NO_VERIFICABLE", 3): vg.FUENTE_SIN_DATO,
            # Re-ingestada (o sin conteo) después del reporte: ya no la describe.
            ("DESACTUALIZADA", 4): vg.FUENTE_INDICE_CAMBIADO,
            ("DESACTUALIZADA", None): vg.FUENTE_INDICE_CAMBIADO,
        }
        for (estado_reporte, fragmentos), esperado in casos.items():
            with self.subTest(estado=estado_reporte, fragmentos=fragmentos):
                r = self.cargar(fila(CNPP, estado_reporte, 3))
                self.assertEqual(vg.vigencia_de_fuente(r, CNPP, fragmentos)["estado"], esperado)
        self.assertEqual(vg.vigencia_de_fuente(None, CNPP, 3), {"estado": vg.FUENTE_SIN_DATO})
        self.assertEqual(vg.vigencia_de_fuente(self.cargar(), CNPP, 3)["estado"], vg.FUENTE_SIN_DATO)

    def test_nombre_en_nfd_coincide(self) -> None:
        fuente = "Código Sintético de Prueba.pdf"
        r = self.cargar(fila(unicodedata.normalize("NFD", fuente), "DESACTUALIZADA", 2))
        self.assertEqual(vg.vigencia_de_fuente(r, fuente, 2)["estado"], vg.FUENTE_NO_VIGENTE)

    def test_instruccion_de_cotejo(self) -> None:
        self.assertEqual(vg.instruccion_cotejo({"etiqueta": "LFT"}, "873-K"),
                         "cotéjalo en el PDF oficial antes de citarlo: python "
                         "scripts/cotejo_manual.py articulo LFT 873-K")
        self.assertTrue(vg.instruccion_cotejo({"etiqueta": "Código Sintético"}, "1").endswith(
            'articulo "Código Sintético" 1'))


class ConstruccionVigenciaTests(unittest.TestCase):
    def setUp(self) -> None:
        parche = mock.patch.object(ON, "COSINE_THRESHOLD", 0.25)
        parche.start()
        self.addCleanup(parche.stop)
        self.ref = _articulo("109", "cnpp", CNPP, "Art. 109", metodo="adyacente_izquierda")

    def construir(self, distancia: float, **opciones) -> dict:
        return ON.build_vvca(self.ref, distancia, True, CNPP, "29", metadata_verificado=True,
                             article_heading_verified=True, **opciones)

    def test_version_no_vigente_impide_el_verde(self) -> None:
        vvca = self.construir(0.17, version_no_vigente=MOTIVO_CNPP)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (84, "🟡"))
        # La existencia y ubicación en la versión indexada siguen acreditadas (dato).
        self.assertTrue(vvca["explicabilidad"]["verde_determinista"])
        self.assertEqual(vvca["explicabilidad"]["version_no_vigente"], MOTIVO_CNPP)
        self.assertTrue(vvca["V_verificacion"].endswith(f"; {MOTIVO_CNPP}"))

    def test_el_tope_no_sube_un_puntaje_menor_ni_cambia_sin_motivo(self) -> None:
        self.assertEqual(self.construir(0.30, version_no_vigente=MOTIVO_CNPP)["score"], 70)
        sin = self.construir(0.17)
        self.assertEqual((sin["score"], sin["semaforo"]), (85, "🟢"))
        self.assertNotIn("version_no_vigente", sin["explicabilidad"])


class VeredictoVigenciaTests(unittest.TestCase):
    def test_razon_con_versiones_no_vigentes(self) -> None:
        veredicto = veredicto_global(84.0, None, 0, 0, 0, normativa_no_verificable=2,
                                     articulos_total=2, normativa_no_vigente=1)
        self.assertEqual(veredicto["semaforo"], "🟡")
        self.assertEqual(veredicto["razon"], "2 cita(s) normativa(s) con evidencia parcial o no "
                                             "verificable (1 por versión indexada no vigente)")
        self.assertIn("scripts/cotejo_manual.py", veredicto["accion"])
        # Sin el dato, la razón de siempre.
        anterior = veredicto_global(84.0, None, 0, 0, 0, normativa_no_verificable=2,
                                    articulos_total=2)
        self.assertEqual(anterior["razon"],
                         "2 cita(s) normativa(s) con evidencia parcial o no verificable")


# ─────────────────────────────────────────
# audit() y query con la colección falsa
# ─────────────────────────────────────────

class ConReporteBase(AuditoriaBase):
    """Reporte de vigencia controlado por la prueba (nunca el de ``reportes/`` del equipo)."""

    def setUp(self) -> None:
        super().setUp()
        self.carpeta = self.jurisprudencia.parent / "reportes"
        self.carpeta.mkdir()
        for nombre, valor in (("VIGENCIA_REPORTE", ""), ("VIGENCIA_REPORTES_DIR", str(self.carpeta))):
            parche = mock.patch.object(ON, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)

    def con_reporte(self, *filas: dict, chroma: str | None = None) -> Path:
        ruta = self.carpeta / "vigencia_1800-01-01.json"
        ruta.write_text(json.dumps(reporte(chroma or ON.CHROMA_PATH, *filas), ensure_ascii=False),
                        encoding="utf-8")
        return ruta

    def indexar_109(self, texto: str = "CNPP Art. 109.") -> None:
        self.coleccion.agregar(
            "Artículo 109. Texto sintético de prueba del artículo.",
            {"source": CNPP, "article": "109", "page": "29", "chunk_index": "120"},
            eje=self.codificador.eje(consulta_de(texto)), distancia=0.17,
        )


class AuditoriaVigenciaTests(ConReporteBase):
    def test_sin_reporte_nada_cambia(self) -> None:
        self.indexar_109()
        resultado = self.auditar("CNPP Art. 109.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["vvca"]["semaforo"], "🟢")
        self.assertNotIn("vigencia_fuente", fuente)
        self.assertEqual(resultado["vvca_summary"]["vigencia_corpus"]["estado"], vg.REPORTE_AUSENTE)
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟢")

    def test_version_no_vigente_es_amarilla_y_lo_dice(self) -> None:
        self.indexar_109()
        ruta = self.con_reporte(fila(CNPP, "DESACTUALIZADA", 1))
        resultado = self.auditar("CNPP Art. 109.")
        (fuente,) = resultado["retrieved_sources"]
        (traza,) = resultado["traceability"]["records"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (84, "🟡"))
        self.assertEqual(traza["verification"]["status"], "partial")
        self.assertEqual(fuente["vigencia_fuente"]["estado"], vg.FUENTE_NO_VIGENTE)
        self.assertEqual(resultado["alerts"], [
            f"🟡 VERSIÓN INDEXADA NO VIGENTE (score 84): 'Art. 109' — {MOTIVO_CNPP}; cotéjalo en "
            f"el PDF oficial antes de citarlo: python scripts/cotejo_manual.py articulo CNPP 109"
        ])
        resumen = resultado["vvca_summary"]
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")
        self.assertIn("1 por versión indexada no vigente", resumen["veredicto"]["razon"])
        self.assertEqual(resumen["vigencia_corpus"], {
            "estado": vg.REPORTE_APLICADO, "reporte": FECHA, "ruta": str(ruta),
            "normativa_version_no_vigente": 1,
        })

    def test_vigente_conserva_el_verde(self) -> None:
        self.indexar_109()
        self.con_reporte(fila(CNPP, "VIGENTE", 1))
        resultado = self.auditar("CNPP Art. 109.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (85, "🟢"))
        self.assertEqual(fuente["vigencia_fuente"]["estado"], vg.FUENTE_VIGENTE)
        self.assertEqual(resultado["alerts"], [])

    def test_reporte_de_otro_indice_o_fuente_reingestada_no_se_aplica(self) -> None:
        self.indexar_109()
        self.con_reporte(fila(CNPP, "DESACTUALIZADA", 1), chroma="/otro/chroma_db")
        resultado = self.auditar("CNPP Art. 109.")
        self.assertEqual(resultado["retrieved_sources"][0]["vvca"]["semaforo"], "🟢")
        self.assertEqual(resultado["vvca_summary"]["vigencia_corpus"]["estado"],
                         vg.REPORTE_OTRO_INDICE)
        # El reporte registró 7 fragmentos y hoy hay 1: la fuente se re-ingestó después.
        self.con_reporte(fila(CNPP, "DESACTUALIZADA", 7))
        resultado = self.auditar("CNPP Art. 109.")
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["vvca"]["semaforo"], "🟢")
        self.assertEqual(fuente["vigencia_fuente"]["estado"], vg.FUENTE_INDICE_CAMBIADO)

    def test_reporte_ilegible(self) -> None:
        self.indexar_109()
        (self.carpeta / "vigencia_1800-01-02.json").write_text("{no es json", encoding="utf-8")
        resultado = self.auditar("CNPP Art. 109.")
        self.assertEqual(resultado["retrieved_sources"][0]["vvca"]["semaforo"], "🟢")
        self.assertEqual(resultado["vvca_summary"]["vigencia_corpus"]["estado"], vg.REPORTE_ILEGIBLE)


class InexistenciaEnVersionNoVigenteTests(ConReporteBase):
    """La prueba de D10 sobre una versión que ya no rige no acredita la inexistencia."""

    def cargar(self) -> None:
        eje = self.codificador.eje(inexistencia.AuditoriaInexistenciaTests.CONSULTA_9999)
        for posicion, (texto, metadata) in enumerate(inexistencia.fragmentos()):
            if posicion == 1:
                self.coleccion.agregar(texto, metadata, eje=eje, distancia=0.10)
            else:
                self.coleccion.agregar(texto, metadata)

    def test_no_vigente_baja_el_rojo_a_amarillo(self) -> None:
        self.cargar()
        self.con_reporte(fila(CFF, "DESACTUALIZADA", len(inexistencia.LEY), etiqueta="CFF"))
        resultado = self.auditar(inexistencia.AuditoriaInexistenciaTests.TEXTO_9999)
        (fuente,) = resultado["retrieved_sources"]
        (traza,) = resultado["traceability"]["records"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (60, "🟡"))
        self.assertEqual((traza["verification"]["status"], traza["retrieval"]["method"]),
                         ("not_verifiable", "corpus_estructura"))
        self.assertNotIn("inexistencia_acreditada", fuente)
        self.assertEqual(fuente["inexistencia_version_indexada"]["tipo"],
                         inexistencia.PRUEBA_NUMERO_MAYOR)
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith(
            f"🟡 INEXISTENTE EN UNA VERSIÓN NO VIGENTE (score 60): 'artículo 9999' — el cuerpo de "
            f"'{CFF}' (versión indexada: {inexistencia.VERSION}) termina en el art. 6o"), alerta)
        self.assertIn("no acredita que el artículo no exista en la ley vigente", alerta)
        self.assertTrue(alerta.endswith("python scripts/cotejo_manual.py articulo CFF 9999"))
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["rojos"], resumen["amarillos"]), (0, 1))
        self.assertEqual(resumen["veredicto"]["semaforo"], "🟡")
        self.assertEqual(resumen["vigencia_corpus"]["normativa_version_no_vigente"], 1)

    def test_vigente_conserva_el_rojo(self) -> None:
        self.cargar()
        self.con_reporte(fila(CFF, "VIGENTE", len(inexistencia.LEY), etiqueta="CFF"))
        resultado = self.auditar(inexistencia.AuditoriaInexistenciaTests.TEXTO_9999)
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual(fuente["vvca"]["semaforo"], "🔴")
        self.assertEqual(fuente["inexistencia_acreditada"]["tipo"], inexistencia.PRUEBA_NUMERO_MAYOR)
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🔴")


class ConsultaTests(ConReporteBase):
    """``consultar_corpus``: la ruta ``query`` sin 🟢 por similitud."""

    def consultar(self, texto: str, **opciones) -> list[dict]:
        return ON.consultar_corpus(texto, collection=self.coleccion, encode=self.codificador,
                                   **opciones)

    def vecino(self, texto: str, distancia: float = 0.05) -> None:
        """Otro artículo muy parecido a la consulta semántica (antes salía 🟢 95)."""
        self.coleccion.agregar(
            "Artículo 110. Texto sintético del artículo vecino.",
            {"source": CNPP, "article": "110", "page": "29", "chunk_index": "121"},
            eje=self.codificador.eje(ON.normalize_legal_text(texto)), distancia=distancia,
        )

    def test_articulo_nombrado_recibe_el_veredicto_de_audit(self) -> None:
        texto = "CNPP Art. 109."
        self.indexar_109(texto)
        self.vecino(texto)
        resultados = self.consultar(texto, n=3)
        primero = resultados[0]
        self.assertEqual((primero["match"], primero["semaforo"], primero["score"]),
                         ("articulo_citado", "🟢", 85))
        self.assertEqual((primero["source"], primero["page"], primero["articulo"]), (CNPP, "29", "109"))
        self.assertIn("Artículo 109.", primero["snippet"])
        self.assertTrue(primero["detalle"].startswith("Verificación determinista"))
        contexto = [r for r in resultados if r["match"] == "contexto"]
        self.assertTrue(contexto)
        # Ningún pasaje de contexto se presenta como veredicto, por parecido que sea.
        self.assertEqual({r["semaforo"] for r in contexto}, {"⚪"})
        self.assertIn(95, [r["score"] for r in contexto])
        self.assertNotIn("Artículo 109.", " ".join(r["snippet"] for r in contexto))

    def test_version_no_vigente_en_query(self) -> None:
        texto = "CNPP Art. 109."
        self.indexar_109(texto)
        self.vecino(texto)
        self.con_reporte(fila(CNPP, "DESACTUALIZADA", 2))
        primero = self.consultar(texto)[0]
        self.assertEqual((primero["semaforo"], primero["score"]), ("🟡", 84))
        self.assertIn(MOTIVO_CNPP, primero["detalle"])

    def test_inexistente_acreditado_en_query(self) -> None:
        texto = inexistencia.AuditoriaInexistenciaTests.TEXTO_9999
        eje = self.codificador.eje(inexistencia.AuditoriaInexistenciaTests.CONSULTA_9999)
        for posicion, (doc, metadata) in enumerate(inexistencia.fragmentos()):
            if posicion == 1:
                self.coleccion.agregar(doc, metadata, eje=eje, distancia=0.10)
            else:
                self.coleccion.agregar(doc, metadata)
        self.codificador.eje(ON.normalize_legal_text(texto))
        primero = self.consultar(texto)[0]
        self.assertEqual((primero["match"], primero["semaforo"], primero["score"]),
                         ("articulo_citado", "🔴", 0))
        self.assertTrue(primero["detalle"].startswith("Artículo inexistente acreditado"))

    def test_ley_por_parametro(self) -> None:
        texto = "Art. 109"
        compuesto = f"{texto} cnpp"
        self.indexar_109(compuesto)
        self.codificador.eje(ON.normalize_legal_text(texto))
        primero = self.consultar(texto, law="cnpp")[0]
        self.assertEqual((primero["match"], primero["semaforo"]), ("articulo_citado", "🟢"))

    def test_busqueda_por_tema_sin_rojo_por_similitud(self) -> None:
        texto = "plazo para la audiencia inicial"
        eje = self.codificador.eje(ON.normalize_legal_text(texto))
        self.coleccion.agregar("Texto sintético muy cercano al tema.",
                               {"source": CNPP, "article": "200", "page": "40", "chunk_index": "5"},
                               eje=eje, distancia=0.05)
        self.coleccion.agregar("Texto sintético lejano.",
                               {"source": CNPP, "article": "300", "page": "60", "chunk_index": "9"})
        resultados = self.consultar(texto, n=2)
        self.assertEqual([(r["match"], r["semaforo"]) for r in resultados],
                         [("semantico", "🟢"), ("semantico", "⚪")])
        # Sin artículo nombrado no se audita nada: solo la consulta semántica.
        self.assertEqual(self.codificador.llamadas, [ON.normalize_legal_text(texto)])

    def test_busqueda_por_tema_en_ley_no_vigente(self) -> None:
        texto = "plazo para la audiencia inicial"
        eje = self.codificador.eje(ON.normalize_legal_text(texto))
        self.coleccion.agregar("Texto sintético muy cercano al tema.",
                               {"source": CNPP, "article": "200", "page": "40", "chunk_index": "5"},
                               eje=eje, distancia=0.05)
        self.con_reporte(fila(CNPP, "DESACTUALIZADA", 1))
        (resultado,) = self.consultar(texto, n=1)
        self.assertEqual(resultado["semaforo"], "🟡")
        self.assertIn(MOTIVO_CNPP, resultado["detalle"])


if __name__ == "__main__":
    unittest.main()
