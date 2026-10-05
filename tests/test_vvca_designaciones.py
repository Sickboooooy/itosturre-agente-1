"""Gramática única de designaciones y encabezados (ronda 2 de la re-ingesta, 4-oct-2026).

Correcciones del coordinador y de la revisión externa, todas con la MISMA gramática para la
extracción de citas, el encabezado exacto de la auditoría, las variantes con sufijo, la prueba
de inexistencia (D10) y el cortador de la ingesta:

1. "N-M" pegado con M < N es UNA designación ("58-1" de la LFPCA); con M ≥ N sigue siendo un
   rango ("14-16" → 14, 15, 16). El sufijo latino seguido de número es una designación
   completa ("65 Bis 1", "76 BIS 1"). Sufijos latinos más allá de "decies" ("67 Terdecies",
   "Sexies Decies") y la grafía "quintus". Falla cerrada: si el texto continúa la designación
   extraída sin capturarla entera ("65 Bis 123", "247 Bis Ter"), la cita nunca es 🟢 (🟡
   COBERTURA INCOMPLETA con la razón).
2. Encabezado partido entre líneas ("ARTICULO\\n508.-"): cuenta para la ingesta y la auditoría
   solo con "Artículo" solo al final de su línea y la designación con su cierre al inicio de la
   siguiente.
3. El cuerpo del último artículo se detiene en la línea TRANSITORIOS.

Todos los textos son SINTÉTICOS; las leyes reales aparecen solo como TEXTO A AUDITAR (para que
la cita resuelva su ordenamiento), nunca como contenido que se afirme. Corre sin dependencias.
"""
from __future__ import annotations

import unittest

from itosturre.audit.evidence import (
    cotejar_precepto,
    encabezado_autentico,
    encabezados_autenticos,
    has_exact_article_heading,
    has_suffixed_variant_heading,
    reconstruir_cuerpo,
)
from itosturre.audit.fragmentacion import encabezados_de_ley, fragmentar
from itosturre.audit.inexistencia import clave_orden, evaluar_inexistencia
from itosturre.audit.referencias import canon_caja, canon_latino, rango_latino
from tests.test_vvca_inexistencia import DENOMINACIONES, LEY, fragmentos
from tests.test_vvca_nucleo import AuditoriaBase
from tests.test_vvca_verde_determinista import consulta_de
from tests.vvca_falsos import importar_opennotebook

ON = importar_opennotebook()
LFPCA = ON.LAW_SOURCE_MAP["lfpca"]
LFPC = ON.LAW_SOURCE_MAP["lfpc"]
CFPC = ON.LAW_SOURCE_MAP["cfpc"]


def _articulos(texto: str) -> list[tuple[str, bool]]:
    """(designación, cobertura incompleta) de cada referencia a artículo de ``texto``."""
    return [(r["article"], bool(r.get("coverage_gap")))
            for r in ON.extract_references(texto) if r["type"] == "article"]


class ExtraccionTests(unittest.TestCase):
    def test_subnumero_frente_a_rango(self) -> None:
        self.assertEqual(_articulos("LFPCA Art. 58-1."), [("58-1", False)])
        self.assertEqual(_articulos("El artículo 58-1 de la LFPCA se invoca."), [("58-1", False)])
        self.assertEqual(_articulos("Los artículos 14-16 de la CPEUM se invocan."),
                         [("14", False), ("15", False), ("16", False)])
        self.assertEqual(_articulos("Los artículos 467-471 del CPF se invocan."),
                         [(str(n), False) for n in range(467, 472)])

    def test_sufijo_latino_con_numero(self) -> None:
        self.assertEqual(
            _articulos("El artículo 65 Bis 1 de la Ley Federal de Protección al Consumidor."),
            [("65 Bis 1", False)],
        )
        self.assertEqual(_articulos("El artículo 76 BIS 1 de la LFPC."), [("76 BIS 1", False)])
        self.assertEqual(_articulos("El artículo 211 bis 7 del CPF."), [("211 bis 7", False)])

    def test_latinos_mas_alla_de_decies(self) -> None:
        for texto, esperado in (
            ("El artículo 67 Terdecies del CFF.", "67 Terdecies"),
            ("El artículo 67. Quaterdecies del CFF.", "67. Quaterdecies"),
            ("El artículo 5 Sexies Decies del CFF.", "5 Sexies Decies"),
            ("El artículo 63 Quintus de la LFPC.", "63 Quintus"),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(_articulos(texto), [(esperado, False)])
        self.assertEqual(canon_latino("Sexies Decies"), "sexiesdecies")
        self.assertEqual(canon_latino("Quáter"), "quater")
        self.assertEqual(canon_latino("Quintus"), "quintus")
        self.assertEqual(rango_latino("quintus"), rango_latino("quinquies"))

    def test_falla_cerrada_si_la_designacion_sigue(self) -> None:
        for texto, articulo in (
            ("El artículo 65 Bis 123 de la LFPC.", "65 Bis"),
            ("El artículo 5 bis 10 días del CFF.", "5 bis"),
            ("El artículo 247 Bis Ter del CPF.", "247 Bis"),
            ("El artículo 247 Undevicies del CPF.", "247"),
            ("El artículo 65 Bis 1-3 de la LFPC.", "65 Bis 1"),
        ):
            with self.subTest(texto=texto):
                (ref,) = [r for r in ON.extract_references(texto) if r["type"] == "article"]
                self.assertEqual(ref["article"], articulo)
                self.assertIn("la designación continúa en el texto", ref["coverage_gap"])

    def test_sin_cambios_en_lo_de_siempre(self) -> None:
        for texto, esperado in (
            ("El artículo 4o.-A del CFF.", [("4o.-A", False)]),
            ("Los artículos 1o. y 2o. de la CPEUM.", [("1o", False), ("2o", False)]),
            ("El artículo 22 bis del CFF se aplica.", [("22 bis", False)]),
            ("El artículo 5 de la CPEUM dispone.", [("5", False)]),
        ):
            with self.subTest(texto=texto):
                self.assertEqual(_articulos(texto), esperado)


class EncabezadoTests(unittest.TestCase):
    def test_subnumero_y_numero_latino_exactos(self) -> None:
        self.assertTrue(has_exact_article_heading("ARTÍCULO 58-1.- Texto.", "58-1"))
        self.assertFalse(has_exact_article_heading("ARTÍCULO 58-1.- Texto.", "58"))
        self.assertTrue(has_suffixed_variant_heading("ARTÍCULO 58-1.- Texto.", "58"))
        self.assertTrue(has_exact_article_heading("ARTICULO 65 Bis 1. Texto.", "65 Bis 1"))
        self.assertFalse(has_exact_article_heading("ARTICULO 65 Bis 1. Texto.", "65 Bis"))
        self.assertFalse(has_exact_article_heading("ARTICULO 65 Bis 10. Texto.", "65 Bis 1"))
        self.assertTrue(has_suffixed_variant_heading("ARTICULO 65 Bis 1. Texto.", "65 Bis"))
        self.assertTrue(has_exact_article_heading("ARTICULO 65 Bis.- Texto.", "65 Bis"))
        # "65 Bis" con una fracción "1." en la línea siguiente sigue siendo el 65 Bis.
        self.assertTrue(has_exact_article_heading("ARTICULO 65 Bis.\n1. Texto.", "65 Bis"))
        self.assertTrue(has_exact_article_heading("Artículo 67. Terdecies.- Texto.", "67 Terdecies"))
        self.assertFalse(has_exact_article_heading("Artículo 67. Terdecies.- Texto.", "67 Ter"))
        self.assertTrue(has_exact_article_heading("Artículo 5 Sexies Decies.- T.", "5 Sexdecies"))

    def test_encabezado_partido_entre_lineas(self) -> None:
        for texto, articulo in (("ARTICULO\n508.- Texto sintético.", "508"),
                                ("Artículo\n9. Texto sintético.", "9")):
            with self.subTest(texto=texto):
                self.assertTrue(encabezado_autentico(texto, articulo))
                (h,) = encabezados_autenticos(texto)
                self.assertEqual((h["inicio"], h["designacion"]), (0, articulo))
        # Remisión en minúscula, sin cierre o con texto tras "Artículo": no cuentan.
        self.assertFalse(encabezado_autentico("artículo\n41. Texto sintético.", "41"))
        self.assertEqual(encabezados_autenticos("Artículo\n51\n1. Texto.", fin_de_linea=True), [])
        self.assertEqual(encabezados_autenticos("El Artículo\n51.- Texto."), [])
        # La ingesta corta en la línea de "Artículo" y etiqueta con el número.
        resultado = fragmentar(
            [{"page": 1, "text": "LEY SINTÉTICA\nArtículo 507.- Texto sintético.\nARTICULO\n"
                                 "508.- Texto sintético del siguiente."}],
            max_caracteres=2000, subdividir=lambda t: [t],
        )
        self.assertEqual([f.etiqueta for f in resultado.fragmentos], ["", "507", "508"])
        self.assertTrue(resultado.fragmentos[2].texto.startswith("ARTICULO\n508.-"))
        self.assertEqual(encabezados_de_ley("ARTICULO\n508.- T")[0]["etiqueta"], "508")

    def test_cuerpo_se_detiene_en_transitorios(self) -> None:
        texto = ("Artículo 10.- Texto sintético del último artículo.\n"
                 "TRANSITORIOS\nARTÍCULO PRIMERO.-\nI. Fracción sintética del transitorio.")
        cuerpo = reconstruir_cuerpo(texto, None, "10")
        self.assertTrue(cuerpo["cerrado"])
        self.assertNotIn("TRANSITORIOS", cuerpo["cuerpo"])
        cotejo = cotejar_precepto(texto, None, "10", [{"tipo": "fraccion", "valor": "I"}])
        self.assertEqual(cotejo["unidad"]["estado"], "no_cotejada")
        # La ingesta corta también en la línea TRANSITORIOS.
        resultado = fragmentar([{"page": 1, "text": "LEY\n" + texto}], max_caracteres=2000,
                               subdividir=lambda t: [t])
        self.assertTrue(resultado.fragmentos[-1].texto.startswith("TRANSITORIOS"))
        self.assertNotIn("TRANSITORIOS", resultado.fragmentos[-2].texto)

    def test_caja_canonica(self) -> None:
        self.assertEqual([canon_caja(x) for x in ("29-a", "247bis", "1o", "4o-A", "1004oA", "1º")],
                         ["29-A", "247BIS", "1o", "4o-A", "1004oA", "1º"])


class InexistenciaTests(unittest.TestCase):
    """D10 con la gramática nueva: orden de numeración y existencia del encabezado partido."""

    def test_orden_de_numeracion(self) -> None:
        orden = ["58", "58-1", "58-2", "58-30", "59"]
        self.assertEqual(sorted(orden, key=clave_orden), orden)
        orden = ["65", "65 Bis", "65 Bis 1", "65 Bis 7", "65 Ter", "65 Ter 1", "66"]
        self.assertEqual(sorted(orden, key=clave_orden), orden)
        self.assertEqual(clave_orden("63 Quintus")[2], clave_orden("63 Quinquies")[2])
        self.assertLess(clave_orden("67 Decies"), clave_orden("67 Undecies"))
        self.assertLess(clave_orden("67 Duodecies"), clave_orden("67 Terdecies"))

    def test_encabezado_partido_acredita_existencia(self) -> None:
        ley = list(LEY)
        texto, etiqueta, pagina = ley[3]
        ley[3] = (texto.replace("Artículo 4o.-", "ARTICULO\n3o Bis.- Texto sintético.\n\n"
                                "Artículo 4o.-"), etiqueta, pagina)
        resultado = evaluar_inexistencia(fragmentos(ley), "3o Bis", DENOMINACIONES)
        self.assertFalse(resultado["acreditada"])
        self.assertIn("aparece en la fuente", resultado["motivo"])
        # Sin él, el 3o Bis sigue acreditándose inexistente (vecinos en el mismo fragmento).
        self.assertTrue(evaluar_inexistencia(fragmentos(LEY), "3o Bis", DENOMINACIONES)["acreditada"])


class AuditoriaRondaDosTests(AuditoriaBase):
    """De punta a punta con la colección falsa: casos del coordinador."""

    def indexar(self, texto_cita: str, documento: str, metadata: dict, distancia: float) -> None:
        self.coleccion.agregar(documento, metadata,
                               eje=self.codificador.eje(consulta_de(texto_cita)),
                               distancia=distancia)

    def fuentes(self, resultado: dict) -> list[dict]:
        return [s for s in resultado["retrieved_sources"] if s.get("ref_type") == "normativa"]

    def test_58_1_es_una_sola_referencia_cotejada_contra_su_encabezado(self) -> None:
        texto = "LFPCA Art. 58-1."
        self.indexar(texto, "ARTÍCULO 58.- Texto sintético del cincuenta y ocho.",
                     {"source": LFPCA, "article": "58", "page": "30", "chunk_index": "100"}, 0.12)
        self.indexar(texto, "ARTÍCULO 58-1.- Texto sintético del cincuenta y ocho guion uno.",
                     {"source": LFPCA, "article": "58-1", "page": "31", "chunk_index": "101"},
                     0.16)
        (fuente,) = self.fuentes(self.auditar(texto))
        self.assertEqual(fuente["article"], "58-1")
        self.assertEqual(fuente["vvca"]["semaforo"], "🟢")
        self.assertTrue(fuente["retrieved_text"].startswith("ARTÍCULO 58-1.-"))

    def test_65_bis_1_solo_verde_con_su_encabezado(self) -> None:
        texto = "El artículo 65 Bis 1 de la Ley Federal de Protección al Consumidor se invoca."
        self.indexar(texto, "ARTICULO 65 Bis.- Texto sintético del sesenta y cinco bis.",
                     {"source": LFPC, "article": "65", "page": "30", "chunk_index": "100"}, 0.12)
        resultado = self.auditar(texto)
        # Solo la variante "65 Bis": nunca 🟢 contra ella (🟡 NO VERIFICABLE por sufijo).
        self.assertFalse(any(s["vvca"]["semaforo"] == "🟢" for s in self.fuentes(resultado)))
        self.assertTrue(any("65 Bis 1" in a and a.startswith("🟡") for a in resultado["alerts"]))
        self.indexar(texto, "ARTICULO 65 Bis 1. Texto sintético del sesenta y cinco bis uno.",
                     {"source": LFPC, "article": "65", "page": "30", "chunk_index": "101"}, 0.16)
        (fuente,) = self.fuentes(self.auditar(texto))
        self.assertEqual(fuente["vvca"]["semaforo"], "🟢")
        self.assertTrue(fuente["retrieved_text"].startswith("ARTICULO 65 Bis 1."))

    def test_encabezado_partido_508(self) -> None:
        texto = "El artículo 508 del Código Federal de Procedimientos Civiles se invoca."
        self.indexar(texto, "ARTICULO\n508.- Texto sintético del quinientos ocho.",
                     {"source": CFPC, "article": "508", "page": "73", "chunk_index": "300"}, 0.15)
        (fuente,) = self.fuentes(self.auditar(texto))
        self.assertEqual((fuente["vvca"]["semaforo"], fuente["page"]), ("🟢", "73"))

    def test_designacion_incompleta_nunca_verde(self) -> None:
        self.coleccion.agregar("ARTICULO 65 Bis.- Texto sintético.",
                               {"source": LFPC, "article": "65", "page": "30", "chunk_index": "1"})
        resultado = self.auditar("El artículo 65 Bis 123 de la LFPC se invoca.")
        self.assertEqual(self.fuentes(resultado), [])
        self.assertTrue(any("COBERTURA INCOMPLETA" in a and "continúa en el texto" in a
                            for a in resultado["alerts"]))


if __name__ == "__main__":
    unittest.main()
