"""Verde determinista (opción A del responsable, 3-oct-2026) y equivalencia ordinal.

Criterio del responsable jurídico (3-oct-2026, opción A): con EVIDENCIA COMPLETA una cita
normativa es 🟢 por regla determinista; la distancia coseno deja de decidir entre 🟢 y 🟡 en
esa ruta y queda como dato informativo. EVIDENCIA COMPLETA = todas a la vez: ``metadata_hit``
de ``audit`` (candidato por metadata source+article, encabezado exacto en el fragmento
seleccionado y fuente recuperada == esperada) · ley identificada y no por confirmar · sin
derogación del precepto ni de la unidad, sin derogación ambigua · sin unidad no cotejada ·
sin evidencia incompleta · distancia ≤ ``COSINE_THRESHOLD``. Con metadata y encabezado pero
distancia mayor que el umbral se conserva el comportamiento anterior (piso 70, 🟡 COTEJAR).
Fuera de esa ruta (búsqueda semántica sin metadata) la distancia decide como antes.

Ordinales (3-oct-2026): "1" ≡ "1o" ≡ "1º" ≡ "1°" al comparar designaciones (candidatos por
metadata, encabezado exacto, cuerpo del precepto, variantes con sufijo); nunca "10", "11" ni
"1o.-A", y los sufijos se siguen exigiendo exactos. D10: una cita sin ordinal ("CPEUM Art. 1.")
nunca es 🔴 por inexistencia "acreditada" al no hallar "Artículo 1." entre encabezados "1o.".

Corre sin dependencias (Python 3.11 del CI) con la colección y el codificador falsos de
``tests/vvca_falsos.py``. Todos los fragmentos son SINTÉTICOS (texto de relleno con la forma de
los fragmentos que guarda la ingesta); las leyes y artículos reales aparecen solo como TEXTO A
AUDITAR, no como citas que se afirmen. Única excepción (ronda 2, a petición del coordinador):
las primeras palabras de los arts. 26, 37 y 102 de la CPEUM y 185 de la LOPJF tal como las
guarda el corpus, para fijar que un apartado o inciso tras el encabezado no es un sufijo. La ley sintética de la prueba D10 es la de
``tests/test_vvca_inexistencia.py`` (fecha de reforma ficticia, 01-01-2099).
"""
from __future__ import annotations

import unittest
from unittest import mock

from itosturre.audit.evidence import (
    DEROGADO,
    cotejar_precepto,
    encabezado_autentico,
    has_exact_article_heading,
    has_suffixed_variant_heading,
    ocurrencias_encabezado,
    precepto_derogado,
    select_article_evidence,
)
from itosturre.audit.inexistencia import evaluar_inexistencia, frontera_creible, preparar_ley
from itosturre.audit.policy import vvca_score, vvca_semaforo
from itosturre.audit.referencias import ordinales_equivalentes, patron_articulo
from itosturre.audit.ubicacion import ubicar_en_cuerpo
from tests.test_vvca_inexistencia import DENOMINACIONES, LEY, fragmentos
from tests.test_vvca_nucleo import AuditoriaBase, _articulo
from tests.vvca_falsos import FakeCollection, importar_opennotebook

ON = importar_opennotebook()
CFF = ON.LAW_SOURCE_MAP["cff"]
CPEUM = ON.LAW_SOURCE_MAP["cpeum"]
CNPP = ON.LAW_SOURCE_MAP["cnpp"]
CCF = ON.LAW_SOURCE_MAP["ccf"]
LIVA = ON.LAW_SOURCE_MAP["liva"]

V_DETERMINISTA = "Verificación determinista: artículo localizado por metadata"


def consulta_de(texto: str) -> str:
    """La consulta que ``audit`` construye para la única referencia de ``texto`` (el
    codificador falso exige registrarla con su texto exacto)."""
    (ref,) = ON.extract_references(texto)
    consulta = f"Artículo {ref['article']}"
    if ref["fraction"]:
        consulta += f" fracción {ref['fraction']}"
    if ref["law"] and ref["law"] != "desconocido":
        consulta += f" {ref['law']}"
    return ON.normalize_legal_text(consulta)


# ─────────────────────────────────────────
# build_vvca (función pura)
# ─────────────────────────────────────────

class ConstruccionVerdeDeterministaTests(unittest.TestCase):
    def setUp(self) -> None:
        parche = mock.patch.object(ON, "COSINE_THRESHOLD", 0.25)
        parche.start()
        self.addCleanup(parche.stop)
        self.ref = _articulo("109", "cnpp", CNPP, "Art. 109", metodo="adyacente_izquierda")

    def construir(self, distancia: float, *, ref: dict | None = None, fuente: bool = True,
                  **opciones) -> dict:
        opciones.setdefault("metadata_verificado", True)
        opciones.setdefault("article_heading_verified", True)
        return ON.build_vvca(ref or self.ref, distancia, fuente, CNPP, "29", **opciones)

    def test_evidencia_completa_con_distancia_017_es_verde_determinista(self) -> None:
        vvca = self.construir(0.17)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (85, "🟢"))
        self.assertTrue(vvca["explicabilidad"]["verde_determinista"])
        # El puntaje por similitud se conserva como dato informativo.
        self.assertEqual(vvca["explicabilidad"]["score_similitud"], 83)
        self.assertEqual(vvca["explicabilidad"]["coseno"], 0.17)
        self.assertEqual(
            vvca["V_verificacion"],
            "Verificación determinista: artículo localizado por metadata (ley y artículo) con su "
            "encabezado exacto en la ley citada; existencia y ubicación en la versión indexada, "
            "no vigencia ni contenido. Distancia informativa: dist=0.170 (≤ umbral 0.25; "
            "puntaje por similitud 83)",
        )
        # La política pura no cambia (la usa scripts/evaluate_gold_set.py con v1 y v2).
        self.assertEqual(vvca_score(0.17, True, True), 83)
        self.assertEqual(vvca_semaforo(83), "🟡")

    def test_umbral_inclusivo_y_salvaguarda_de_anomalia(self) -> None:
        vvca = self.construir(0.25)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (85, "🟢"))
        self.assertEqual(vvca["explicabilidad"]["score_similitud"], 75)
        # Distancia > umbral con metadata y encabezado: comportamiento anterior (el puntaje por
        # similitud con piso 70).
        for distancia, esperado in ((0.2501, 75), (0.26, 74), (0.30, 70), (0.60, 70)):
            with self.subTest(distancia=distancia):
                vvca = self.construir(distancia)
                self.assertEqual((vvca["score"], vvca["semaforo"]), (esperado, "🟡"))
                self.assertNotIn("verde_determinista", vvca["explicabilidad"])
                self.assertNotIn("score_similitud", vvca["explicabilidad"])
                self.assertTrue(vvca["V_verificacion"].startswith(
                    "Artículo confirmado por metadata y encabezado exacto"))

    def test_cada_tope_deja_amarillo_con_evidencia_por_lo_demas_completa(self) -> None:
        por_confirmar = dict(self.ref, law_requires_confirmation=True)
        sin_ley = dict(self.ref, source_file=None)
        casos = {
            "ley por confirmar": dict(ref=por_confirmar),
            "evidencia de otra fuente": dict(fuente=False),
            "precepto derogado": dict(derogado=True),
            "unidad derogada": dict(unidad_derogada="fracción I"),
            "derogación ambigua": dict(derogacion_ambigua=True),
            "unidad no cotejada": dict(unidad_no_cotejada="motivo sintético"),
            "evidencia incompleta": dict(evidencia_incompleta=True),
            "sin ley identificada": dict(ref=sin_ley),
            "sin encabezado exacto": dict(article_heading_verified=False),
            "encabezado no evaluado": dict(article_heading_verified=None),
            "sin metadata": dict(metadata_verificado=False),
        }
        for nombre, opciones in casos.items():
            with self.subTest(tope=nombre):
                vvca = self.construir(0.17, **opciones)
                self.assertEqual(vvca["semaforo"], "🟡")
                self.assertLessEqual(vvca["score"], 84)
                self.assertNotIn("verde_determinista", vvca["explicabilidad"])
                self.assertNotIn("Verificación determinista", vvca["V_verificacion"])

    def test_ruta_semantica_sin_metadata_decide_la_distancia(self) -> None:
        # Como antes: sin metadata, con encabezado, 0.17 → 83 🟡 y 0.10 → 90 🟢.
        for distancia, esperado in ((0.17, (83, "🟡")), (0.10, (90, "🟢"))):
            with self.subTest(distancia=distancia):
                vvca = self.construir(distancia, metadata_verificado=False)
                self.assertEqual((vvca["score"], vvca["semaforo"]), esperado)
                self.assertNotIn("verde_determinista", vvca["explicabilidad"])
                self.assertEqual(vvca["V_verificacion"],
                                 f"Encontrado en corpus oficial (dist={distancia:.3f})")

    def test_ordinal_equivalente_sin_metadata_no_da_verde(self) -> None:
        # Ordinales: sin metadata, el encabezado que solo coincide por la equivalencia del
        # ordinal ubica el precepto pero no amplía el 🟢 de la ruta semántica.
        vvca = self.construir(0.10, metadata_verificado=False, ordinal_equivalente=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (84, "🟡"))
        self.assertTrue(vvca["explicabilidad"]["ordinal_equivalente"])
        self.assertTrue(vvca["V_verificacion"].endswith(
            "encabezado ubicado solo por equivalencia del ordinal, en un fragmento sin "
            "metadata del artículo: no acredita el precepto"))
        # Con metadata la etiqueta del índice identifica el artículo: el verde determinista
        # se conserva y la equivalencia queda como dato informativo.
        vvca = self.construir(0.17, ordinal_equivalente=True)
        self.assertEqual((vvca["score"], vvca["semaforo"]), (85, "🟢"))
        self.assertTrue(vvca["explicabilidad"]["ordinal_equivalente"])
        self.assertTrue(vvca["V_verificacion"].startswith(V_DETERMINISTA))


# ─────────────────────────────────────────
# audit() con la colección falsa
# ─────────────────────────────────────────

class AuditoriaVerdeDeterministaTests(AuditoriaBase):
    def indexar(self, texto_cita: str, documento: str, metadata: dict, distancia: float,
                *, coleccion: FakeCollection | None = None) -> None:
        (coleccion or self.coleccion).agregar(
            documento, metadata, eje=self.codificador.eje(consulta_de(texto_cita)),
            distancia=distancia,
        )

    def unica(self, resultado: dict) -> tuple[dict, dict]:
        (fuente,) = resultado["retrieved_sources"]
        (traza,) = resultado["traceability"]["records"]
        return fuente, traza

    def test_verde_determinista_de_punta_a_punta(self) -> None:
        texto = "CNPP Art. 109."
        self.indexar(texto, "Artículo 109. Texto sintético de prueba del artículo.",
                     {"source": CNPP, "article": "109", "page": "29", "chunk_index": "120"},
                     0.17)
        resultado = self.auditar(texto)
        fuente, traza = self.unica(resultado)
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (85, "🟢"))
        self.assertEqual(fuente["relevance_score"], 0.83)
        explicabilidad = fuente["vvca"]["explicabilidad"]
        self.assertTrue(explicabilidad["verde_determinista"])
        self.assertEqual(explicabilidad["score_similitud"], 83)
        self.assertNotIn("ordinal_equivalente", explicabilidad)
        self.assertTrue(fuente["vvca"]["V_verificacion"].startswith(V_DETERMINISTA))
        # trace_status "verified" se deriva como antes: metadata_hit y score ≥ 85.
        self.assertEqual((traza["verification"]["status"], traza["retrieval"]["method"]),
                         ("verified", "corpus_metadata"))
        self.assertEqual(resultado["alerts"], [])
        veredicto = resultado["vvca_summary"]["veredicto"]
        self.assertEqual((veredicto["semaforo"], veredicto["apto"]), ("🟢", True))

    def test_distancia_mayor_al_umbral_con_metadata_conserva_cotejar(self) -> None:
        texto = "CNPP Art. 109."
        self.indexar(texto, "Artículo 109. Texto sintético de prueba del artículo.",
                     {"source": CNPP, "article": "109", "page": "29", "chunk_index": "120"},
                     0.30)
        resultado = self.auditar(texto)
        fuente, traza = self.unica(resultado)
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (70, "🟡"))
        self.assertEqual(traza["verification"]["status"], "partial")
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith("🟡 COTEJAR: 'Art. 109' — artículo confirmado por "
                                          "metadata"))

    def test_topes_con_evidencia_completa_y_distancia_017_siguen_amarillos(self) -> None:
        casos = (
            ("ley por confirmar",
             "El Código Fiscal de la Federación regula las facultades.\n\n"
             "En el caso, el artículo 42 autoriza la revisión.",
             "Artículo 42.- Texto sintético de las facultades de comprobación.",
             {"source": CFF, "article": "42", "page": "91", "chunk_index": "200"},
             "🟡 LEY POR CONFIRMAR"),
            ("precepto derogado", "El artículo 64 del CFF se invoca.",
             "Artículo 64.- (Se deroga).",
             {"source": CFF, "article": "64", "page": "127", "chunk_index": "300"},
             "🟡 PRECEPTO DEROGADO"),
            ("fracción derogada",
             "El artículo 31, fracción I, del Código Civil Federal se invoca.",
             "Artículo 31.- Texto sintético del domicilio:\nI.\n(Se deroga).\n"
             "II. Texto sintético de la segunda fracción.",
             {"source": CCF, "article": "31", "page": "5", "chunk_index": "30"},
             "🟡 PRECEPTO DEROGADO"),
            ("unidad no cotejada", "El artículo 1o., párrafo tercero, de la CPEUM se invoca.",
             "Artículo 1o. Texto sintético del primer artículo de la prueba.",
             {"source": CPEUM, "article": "1o", "page": "1", "chunk_index": "1"},
             "🟡 UNIDAD CITADA NO COTEJADA"),
            ("evidencia incompleta", "El artículo 70 del CFF se invoca.",
             "Texto sintético.\nArtículo 70.- Las",
             {"source": CFF, "article": "70", "page": "140", "chunk_index": "310"},
             "🟡 EVIDENCIA INCOMPLETA"),
        )
        for nombre, texto, documento, metadata, alerta in casos:
            with self.subTest(tope=nombre):
                self.coleccion = FakeCollection()
                self.indexar(texto, documento, metadata, 0.17)
                resultado = self.auditar(texto)
                fuente, traza = self.unica(resultado)
                self.assertEqual(fuente["vvca"]["semaforo"], "🟡")
                self.assertTrue(fuente["vvca"]["explicabilidad"]["match_metadata"])
                self.assertNotIn("verde_determinista", fuente["vvca"]["explicabilidad"])
                self.assertEqual(traza["verification"]["status"], "partial")
                self.assertTrue(any(a.startswith(alerta) for a in resultado["alerts"]),
                                resultado["alerts"])
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    def test_evidencia_de_otra_fuente_con_017_sigue_amarilla(self) -> None:
        coleccion = FakeCollection(fallar_consultas_filtradas=True)
        texto = "El artículo 16 de la Constitución Política de los Estados Unidos Mexicanos."
        coleccion.agregar("Artículo 16. Texto sintético de la Constitución.",
                          {"source": CPEUM, "article": "16", "page": "19"})
        self.indexar(texto, "Artículo 16.- Texto sintético de otro ordenamiento.",
                     {"source": CFF, "article": "16", "page": "7"}, 0.17, coleccion=coleccion)
        for pagina in ("8", "9"):
            self.indexar(texto, "Texto sintético de otro ordenamiento.",
                         {"source": LIVA, "article": "3", "page": pagina}, 0.20,
                         coleccion=coleccion)
        resultado = self.auditar(texto, coleccion=coleccion)
        fuente, traza = self.unica(resultado)
        self.assertEqual((fuente["source_file"], fuente["vvca"]["semaforo"]), (CFF, "🟡"))
        self.assertNotIn("verde_determinista", fuente["vvca"]["explicabilidad"])
        self.assertEqual(traza["verification"]["status"], "not_verifiable")

    def test_ruta_semantica_sin_metadata_con_017_decide_la_distancia(self) -> None:
        # Fragmento sin etiqueta de artículo (como los de una ley con "ARTÍCULO" en
        # mayúsculas que el chunker no etiqueta): no hay candidatos por metadata.
        for distancia, esperado, estado in ((0.17, (83, "🟡"), "partial"),
                                            (0.10, (90, "🟢"), "verified")):
            with self.subTest(distancia=distancia):
                self.setUp()
                texto = "CNPP Art. 109."
                self.indexar(texto, "ARTÍCULO 109.- Texto sintético sin etiqueta del chunker.",
                             {"source": CNPP, "article": "", "page": "29", "chunk_index": "9"},
                             distancia)
                resultado = self.auditar(texto)
                fuente, traza = self.unica(resultado)
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                                 esperado)
                self.assertFalse(fuente["vvca"]["explicabilidad"]["match_metadata"])
                self.assertNotIn("verde_determinista", fuente["vvca"]["explicabilidad"])
                self.assertEqual(
                    (traza["verification"]["status"], traza["retrieval"]["method"]),
                    (estado, "corpus_semantic"),
                )

    def test_ruta_semantica_con_ordinal_equivalente_no_amplia_el_verde(self) -> None:
        # Ordinales: "artículo 2" frente a "ARTÍCULO 2o.-" en un fragmento sin etiqueta. La
        # grafía citada literal ("2o.") conserva el 🟢 que ya tenía por distancia.
        documento = ("Texto sintético previo del fragmento.\nARTÍCULO 2o.- Texto sintético "
                     "del segundo artículo de la prueba.")
        metadata = {"source": CNPP, "article": "", "page": "1", "chunk_index": "3"}
        for texto, esperado, alerta in (
            ("El artículo 2 del CNPP se invoca.", (84, "🟡"), "🟡 COTEJAR (score 84)"),
            ("El artículo 2o. del CNPP se invoca.", (90, "🟢"), None),
        ):
            with self.subTest(texto=texto):
                self.setUp()
                self.indexar(texto, documento, metadata, 0.10)
                resultado = self.auditar(texto)
                fuente, traza = self.unica(resultado)
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                                 esperado)
                self.assertTrue(fuente["vvca"]["explicabilidad"]["encabezado_articulo"])
                self.assertEqual(traza["retrieval"]["method"], "corpus_semantic")
                if alerta:
                    (unica,) = resultado["alerts"]
                    self.assertTrue(unica.startswith(alerta), unica)
                    self.assertIn("con otra grafía del ordinal", unica)
                    self.assertTrue(fuente["vvca"]["explicabilidad"]["ordinal_equivalente"])
                else:
                    self.assertEqual(resultado["alerts"], [])


# ─────────────────────────────────────────
# Ordinales: equivalencia N ↔ No / Nº / N°
# ─────────────────────────────────────────

class OrdinalesTests(unittest.TestCase):
    def test_ordinales_equivalentes(self) -> None:
        for ordinal in ("", "o", "º", "°"):
            with self.subTest(ordinal=ordinal):
                self.assertEqual(ordinales_equivalentes(ordinal), ("", "o", "º", "°"))
        for ordinal in ("a", "ª"):
            with self.subTest(ordinal=ordinal):
                self.assertEqual(ordinales_equivalentes(ordinal), ("a", "ª"))

    def test_encabezado_equivalente_en_ambos_sentidos(self) -> None:
        for texto, articulo in (
            ("Artículo 1o. Texto sintético.", "1"),
            ("Artículo 1º.- Texto sintético.", "1"),
            ("Artículo 1°.- Texto sintético.", "1"),
            ("Artículo 1.- Texto sintético.", "1o"),
            ("Artículo 1. Texto sintético.", "1º"),
            ("Artículo 1o.- Texto sintético.", "1°"),
            ("ARTÍCULO 2o.- Texto sintético.", "2"),
            ("Artículo 9o.- Texto sintético.", "9"),
            ("Artículo 10. Texto sintético.", "10"),
            # Con el mismo sufijo, el ordinal también es equivalente.
            ("Artículo 4-A.- Texto sintético.", "4o.-A"),
            ("Artículo 4o.-A.- Texto sintético.", "4-A"),
            ("Artículo 2o. Bis.- Texto sintético.", "2 Bis"),
            ("Artículo 1ª.- Texto sintético.", "1a"),
        ):
            with self.subTest(texto=texto, articulo=articulo):
                self.assertTrue(has_exact_article_heading(texto, articulo))

    def test_casos_prohibidos(self) -> None:
        for texto, articulo in (
            # Nunca otro número.
            ("Artículo 10.- Texto sintético.", "1"),
            ("Artículo 11.- Texto sintético.", "1"),
            ("Artículo 100.- Texto sintético.", "1o"),
            ("Artículo 1o.- Texto sintético.", "10"),
            ("Artículo 21.- Texto sintético.", "1"),
            # Ni un sufijo no pedido, ni la falta del sufijo pedido.
            ("Artículo 1o.-A.- Texto sintético.", "1"),
            ("Artículo 1o.-A.- Texto sintético.", "1o"),
            ("Artículo 4o.-A.- Texto sintético.", "4"),
            ("Artículo 4.- Texto sintético.", "4o.-A"),
            ("Artículo 4o.- Texto sintético.", "4o.-A"),
            ("Artículo 1o. Bis.- Texto sintético.", "1"),
            ("Artículo 1 Bis.- Texto sintético.", "1o"),
            ("Artículo 1o.- Texto sintético.", "1 Bis"),
            ("Artículo 29-B.- Texto sintético.", "29"),
            ("Artículo 29.- Texto sintético.", "29-A"),
            ("Artículo 247 Bis.- Texto sintético.", "247 Ter"),
            # El femenino no equivale al masculino ni a la falta de ordinal.
            ("Artículo 1a.- Texto sintético.", "1"),
            ("Artículo 1o.- Texto sintético.", "1a"),
            # Una remisión sigue sin ser encabezado.
            ("conforme al artículo 1o., fracción II", "1"),
        ):
            with self.subTest(texto=texto, articulo=articulo):
                self.assertFalse(has_exact_article_heading(texto, articulo))

    def test_comparacion_literal_conserva_la_anterior(self) -> None:
        for texto, articulo, esperado in (
            ("Artículo 1o. Texto.", "1", False),
            ("Artículo 1o. Texto.", "1o", True),
            ("Artículo 1. Texto.", "1o", False),
        ):
            with self.subTest(texto=texto, articulo=articulo):
                self.assertEqual(
                    has_exact_article_heading(texto, articulo, ordinal_literal=True), esperado
                )
        # Ronda 2 (Codex e): ``patron_articulo`` conserva por defecto la comparación literal;
        # la equivalencia se activa explícitamente.
        import re
        literal = re.compile(rf"articulo\s+{patron_articulo('1')}\s*\.", re.I)
        equivalente = re.compile(
            rf"articulo\s+{patron_articulo('1', ordinal_equivalente=True)}\s*\.", re.I
        )
        self.assertIsNone(literal.search("Articulo 1o. Texto."))
        self.assertIsNotNone(equivalente.search("Articulo 1o. Texto."))
        self.assertIsNotNone(literal.search("Articulo 1. Texto."))

    def test_variantes_con_sufijo_y_cuerpo_por_equivalencia(self) -> None:
        self.assertTrue(has_suffixed_variant_heading("Artículo 4o.-A.- Texto sintético.", "4"))
        self.assertTrue(has_suffixed_variant_heading("Artículo 1-A.- Texto sintético.", "1o"))
        self.assertFalse(has_suffixed_variant_heading("Artículo 4o.- Texto sintético.", "4"))
        self.assertTrue(precepto_derogado("Artículo 5o.- (Se deroga).", "5"))
        self.assertFalse(precepto_derogado("Artículo 5o.-A.- (Se deroga).\nArtículo 5o.- Texto "
                                           "sintético vigente del artículo.", "5"))
        cotejo = cotejar_precepto(
            "Artículo 1o. Texto sintético suficiente para cotejar el precepto citado.\n"
            "Artículo 2o. Otro texto sintético.", None, "1",
        )
        self.assertEqual((cotejo["derogacion"], cotejo["completo"], cotejo["cerrado"]),
                         (None, True, True))

    def test_candidatos_por_metadata_con_ordinal_equivalente(self) -> None:
        self.assertEqual(ON._article_candidates("1"), ["1", "1o", "1º"])
        self.assertEqual(ON._article_candidates("1o"), ["1", "1o", "1º"])
        self.assertEqual(ON._article_candidates("9"), ["9", "9o", "9º"])
        self.assertNotIn("10", ON._article_candidates("1"))
        self.assertNotIn("1", ON._article_candidates("10"))

    def test_seleccion_prefiere_la_primera_aparicion_de_la_misma_fuente(self) -> None:
        # Cuerpo (chunk 1) y decreto de reforma (chunk 3188) con el mismo encabezado por
        # equivalencia; el decreto está más cerca de la consulta.
        resultados = {
            "documents": [["Artículo 1.- Se reforma el texto sintético del decreto.",
                           "Artículo 1o.- Texto sintético del cuerpo de la ley."]],
            "metadatas": [[{"source": CCF, "article": "1", "page": "335", "chunk_index": "3188"},
                           {"source": CCF, "article": "1o", "page": "1", "chunk_index": "1"}]],
            "distances": [[0.10, 0.16]],
        }
        elegido = select_article_evidence(resultados, "1")
        self.assertEqual((elegido["metadata"]["page"], elegido["rank"]), ("1", 2))
        self.assertTrue(elegido["heading_verified"])
        self.assertFalse(elegido["heading_literal"])
        self.assertTrue(select_article_evidence(resultados, "1o")["heading_literal"])
        # Sin chunk_index entero, o con fuentes distintas, decide el ranking como antes.
        for cambio in ({"chunk_index": None}, {"source": CPEUM}):
            with self.subTest(cambio=cambio):
                otros = {
                    "documents": resultados["documents"],
                    "metadatas": [[dict(resultados["metadatas"][0][0], **cambio),
                                   resultados["metadatas"][0][1]]],
                    "distances": resultados["distances"],
                }
                self.assertEqual(select_article_evidence(otros, "1")["rank"], 1)


class AuditoriaOrdinalesTests(AuditoriaBase):
    def indexar(self, texto_cita: str, documento: str, metadata: dict, distancia: float) -> None:
        self.coleccion.agregar(documento, metadata,
                               eje=self.codificador.eje(consulta_de(texto_cita)),
                               distancia=distancia)

    def test_cita_sin_ordinal_se_localiza_por_metadata_y_es_verde_determinista(self) -> None:
        for texto, documento, etiqueta, fuente in (
            ("CPEUM Art. 1.", "Artículo 1o. Texto sintético del primer artículo.", "1o", CPEUM),
            ("CPEUM Art. 1º.", "Artículo 1o. Texto sintético del primer artículo.", "1o", CPEUM),
            ("CFF Art. 9.", "Artículo 9o.- Texto sintético del noveno artículo.", "9o", CFF),
            ("CNPP Art. 1o.", "Artículo 1. Texto sintético del primer artículo.", "1", CNPP),
        ):
            with self.subTest(texto=texto):
                self.setUp()
                self.indexar(texto, documento,
                             {"source": fuente, "article": etiqueta, "page": "1",
                              "chunk_index": "1"}, 0.17)
                resultado = self.auditar(texto)
                (fuente_hallada,) = resultado["retrieved_sources"]
                vvca = fuente_hallada["vvca"]
                self.assertEqual((vvca["score"], vvca["semaforo"]), (85, "🟢"))
                self.assertTrue(vvca["explicabilidad"]["verde_determinista"])
                self.assertTrue(vvca["explicabilidad"]["ordinal_equivalente"])
                self.assertEqual(self.estados(resultado)[0][1:], ("verified", "corpus_metadata"))
                self.assertEqual(resultado["alerts"], [])

    def test_dos_encabezados_sin_frontera_es_ubicacion_ambigua(self) -> None:
        # Ronda 2 (regla i): cuerpo (chunk 1) y decreto (chunk 3188) con el mismo encabezado
        # por equivalencia y sin frontera TRANSITORIOS creíble: la primera aparición ya no
        # basta (ronda 1 daba 🟢 con el chunk 1). Se muestra la primera aparición, con 🟡.
        texto = "Código Civil Federal Art. 1."
        self.indexar(texto, "Artículo 1o.- Texto sintético del cuerpo del código.",
                     {"source": CCF, "article": "1o", "page": "1", "chunk_index": "1"}, 0.20)
        self.indexar(texto, "Artículo 1.- Se reforma el texto sintético de un decreto.",
                     {"source": CCF, "article": "1", "page": "335", "chunk_index": "3188"},
                     0.10)
        resultado = self.auditar(texto)
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["page"], fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                         ("1", 80, "🟡"))
        self.assertIn("cuerpo del código", fuente["retrieved_text_full"])
        ubicacion = fuente["vvca"]["explicabilidad"]["ubicacion"]
        self.assertEqual((ubicacion["estado"], ubicacion["encabezados_autenticos"],
                          ubicacion["frontera_creible"]), ("ambiguo", 2, False))
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith("🟡 UBICACIÓN NO ACREDITADA (score 80): 'Art. 1' — "
                                          f"en '{CCF}': ubicación ambigua: el encabezado del "
                                          "artículo 1 aparece 2 veces en el PDF (págs. 1, 335)"),
                        alerta)

    def test_numero_distinto_nunca_se_confunde(self) -> None:
        # "CPEUM Art. 10." con solo el "Artículo 1o." indexado: ni metadata ni encabezado.
        texto = "CPEUM Art. 10."
        self.indexar(texto, "Artículo 1o. Texto sintético del primer artículo.",
                     {"source": CPEUM, "article": "1o", "page": "1", "chunk_index": "1"}, 0.10)
        resultado = self.auditar(texto)
        (fuente,) = resultado["retrieved_sources"]
        self.assertFalse(fuente["vvca"]["explicabilidad"]["encabezado_articulo"])
        self.assertFalse(fuente["vvca"]["explicabilidad"]["match_metadata"])
        self.assertEqual(fuente["vvca"]["semaforo"], "🟡")

    def test_D10_sin_ordinal_nunca_es_rojo_por_inexistencia(self) -> None:
        # CRÍTICO (D10): en la ley sintética (encabezados "1o."…"6o.", identidad comprobada,
        # cuerpo completo y TRANSITORIOS) las citas sin ordinal NO acreditan inexistencia.
        for articulo in ("1", "2", "3", "4", "5", "6", "1º", "1°", "4o"):
            with self.subTest(articulo=articulo):
                evaluacion = evaluar_inexistencia(fragmentos(), articulo, DENOMINACIONES)
                self.assertFalse(evaluacion["acreditada"])
                self.assertIsNone(evaluacion["prueba"])
        # Control: la prueba positiva sigue funcionando para un número inexistente.
        self.assertTrue(evaluar_inexistencia(fragmentos(), "9999", DENOMINACIONES)["acreditada"])

        # De punta a punta, por las rutas sin metadata: el "4o." comparte fragmento con el
        # "3o." (etiqueta "3o"), así que "4" no tiene candidatos por metadata.
        texto = "El artículo 4 del Código Fiscal de la Federación se invoca."
        consulta = consulta_de(texto)
        for cercano, distancia in ((3, 0.10), (1, 0.10), (3, 0.40), (1, 0.40)):
            with self.subTest(cercano=cercano, distancia=distancia):
                self.setUp()
                eje = self.codificador.eje(consulta)
                for posicion, (documento, metadata) in enumerate(fragmentos()):
                    if posicion == cercano:
                        self.coleccion.agregar(documento, metadata, eje=eje, distancia=distancia)
                    else:
                        self.coleccion.agregar(documento, metadata)
                resultado = self.auditar(texto)
                self.assertNotIn("refuted", [estado for _, estado, _ in self.estados(resultado)])
                self.assertFalse([a for a in resultado["alerts"] if a.startswith("🔴")])
                self.assertEqual(resultado["vvca_summary"]["rojos"], 0)
                self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")


# ─────────────────────────────────────────
# Ronda 2 (adjudicada por el coordinador, 3-oct-2026)
# ─────────────────────────────────────────
# 1) remisión en minúscula como encabezado · 2) pertenencia al cuerpo · 3) sufijo partido
# entre líneas · 4) "°" con sufijo en la extracción · 5) la metadata no sobrevive al respaldo
# semántico · 6) la equivalencia ordinal no es el comportamiento por defecto.

TRANSITORIO = ("Artículo 1o.- Texto sintético de un transitorio de un decreto de reforma.",
               "1o", "4")


class EncabezadoAutenticoTests(unittest.TestCase):
    def test_remision_en_minuscula_o_seguida_de_coma_no_es_autentica(self) -> None:
        for texto, articulo, esperado in (
            ("artículo 41.    Texto sintético que continúa el artículo anterior.", "41", False),
            ("Artículo 2o., fracción I, inciso H.  Texto sintético.", "2", False),
            ("Artículo 41.; texto sintético", "41", False),
            ("art. 41.- texto sintético", "41", False),
            ("Artículo 41. Texto sintético del artículo.", "41", True),
            ("ARTÍCULO 41.- Texto sintético.", "41", True),
            ("Art. 41.- Texto sintético.", "41", True),
        ):
            with self.subTest(texto=texto):
                # El encabezado exacto (caja indistinta) no cambia: D10 no se altera.
                self.assertTrue(has_exact_article_heading(texto, articulo))
                self.assertEqual(encabezado_autentico(texto, articulo), esperado)

    def test_seleccion_prefiere_el_autentico_y_lo_informa(self) -> None:
        resultados = {
            "documents": [["artículo 41.    Texto sintético del artículo anterior.",
                           "Artículo 41. Texto sintético del artículo cuarenta y uno."]],
            "metadatas": [[{"source": CCF, "article": "41", "page": "6", "chunk_index": "41"},
                           {"source": CCF, "article": "41", "page": "7", "chunk_index": "44"}]],
            "distances": [[0.10, 0.16]],
        }
        elegido = select_article_evidence(resultados, "41")
        self.assertEqual((elegido["metadata"]["page"], elegido["heading_authentic"]), ("7", True))
        self.assertEqual(elegido["autenticos"], [1])
        solo = {clave: [valor[0][:1]] for clave, valor in resultados.items()}
        elegido = select_article_evidence(solo, "41")
        self.assertEqual((elegido["heading_verified"], elegido["heading_authentic"]), (True, False))

    def test_el_cuerpo_se_reconstruye_desde_la_misma_ocurrencia(self) -> None:
        documento = "artículo 5.\nTexto sintético previo.\nArtículo 5.- (Se deroga)."
        self.assertEqual([o["autentico"] for o in ocurrencias_encabezado(documento, "5")],
                         [False, True])
        self.assertIsNone(cotejar_precepto(documento, None, "5")["derogacion"])
        self.assertEqual(cotejar_precepto(documento, None, "5", solo_autentico=True)["derogacion"],
                         DEROGADO)

    def test_sufijo_partido_entre_lineas_impide_el_numero_base(self) -> None:
        for texto in ("Artículo 1o.\nBis.- Texto sintético.", "Artículo 1o.\n-A.- Texto sintético.",
                      "Artículo 1o.\nTer. Texto sintético."):
            with self.subTest(texto=texto):
                self.assertFalse(has_exact_article_heading(texto, "1"))
                self.assertFalse(has_exact_article_heading(texto, "1o"))
                self.assertTrue(has_suffixed_variant_heading(texto, "1"))
        # Una letra suelta NO es sufijo: apartados, incisos o el inicio del texto (líneas de
        # apertura de la CPEUM y de la LOPJF tal como las guarda el corpus).
        for texto, articulo in (
            ("Artículo 26.\nA. El Estado organizará un sistema", "26"),
            ("Artículo 37.\nA) Ningún mexicano por nacimiento", "37"),
            ("Artículo 102.\nA. El Ministerio Público de la Federación", "102"),
            ("Artículo 185.\nA efecto de preservar los principios", "185"),
        ):
            with self.subTest(texto=texto):
                self.assertTrue(has_exact_article_heading(texto, articulo))
                self.assertTrue(encabezado_autentico(texto, articulo))
                self.assertFalse(has_suffixed_variant_heading(texto, articulo))

    def test_equivalencia_ordinal_solo_explicita(self) -> None:
        # Codex (e): ``patron_articulo`` y ``patron_variante_con_sufijo`` conservan por defecto
        # la comparación literal del ordinal.
        import re
        from itosturre.audit.referencias import patron_variante_con_sufijo
        variante = re.compile(rf"articulo\s+{patron_variante_con_sufijo('4')}", re.I)
        self.assertIsNone(variante.search("Articulo 4o.-A.- Texto."))
        variante = re.compile(
            rf"articulo\s+{patron_variante_con_sufijo('4', ordinal_equivalente=True)}", re.I
        )
        self.assertIsNotNone(variante.search("Articulo 4o.-A.- Texto."))


class GradoConSufijoTests(unittest.TestCase):
    def test_el_grado_antes_de_un_sufijo_es_ordinal_y_conserva_la_ley(self) -> None:
        for texto, articulo, ley, metodo in (
            ("CFF Art. 4°-A.", "4°-A", "cff", "adyacente_izquierda"),
            ("artículo 4°-A del Código Fiscal de la Federación", "4°-A",
             "código fiscal de la federación", "adyacente_derecha"),
            ("artículo 1°. Bis del CFF", "1°. Bis", "cff", "adyacente_derecha"),
            ("artículo 1º. Bis del CFF", "1º. Bis", "cff", "adyacente_derecha"),
            ("artículo 2° Bis del CFF", "2° Bis", "cff", "adyacente_derecha"),
            # El grado final se sigue descartando.
            ("Art. 259° del Código Penal Federal", "259", "código penal federal",
             "adyacente_derecha"),
        ):
            with self.subTest(texto=texto):
                (ref,) = ON.extract_references(texto)
                self.assertEqual((ref["article"], ref["law"], ref["law_method"]),
                                 (articulo, ley, metodo))
        # Sin sufijo, el punto tras el grado sigue cerrando la oración.
        (ref,) = ON.extract_references("El artículo 19°. La CPEUM dispone otra cosa.")
        self.assertEqual((ref["article"], ref["law"]), ("19", "desconocido"))


class AuditoriaRondaDosTests(AuditoriaBase):
    TEXTO_1O = "El artículo 1o. del Código Fiscal de la Federación se invoca."

    def indexar(self, texto_cita: str, documento: str, metadata: dict, distancia: float,
                *, coleccion: FakeCollection | None = None) -> None:
        (coleccion or self.coleccion).agregar(
            documento, metadata, eje=self.codificador.eje(consulta_de(texto_cita)),
            distancia=distancia,
        )

    def cargar_ley(self, ley, cercanos: dict[int, float], texto: str) -> None:
        """Indexa la ley sintética; los fragmentos de ``cercanos`` quedan a esa distancia."""
        eje = self.codificador.eje(consulta_de(texto))
        for posicion, (documento, metadata) in enumerate(fragmentos(ley)):
            if posicion in cercanos:
                self.coleccion.agregar(documento, metadata, eje=eje, distancia=cercanos[posicion])
            else:
                self.coleccion.agregar(documento, metadata)

    def unica(self, resultado: dict) -> dict:
        (fuente,) = resultado["retrieved_sources"]
        return fuente

    # ── 1) Remisión en minúscula ────────────────────────────────────────────────────────
    def test_remision_no_gana_al_encabezado_autentico(self) -> None:
        texto = "El artículo 41 del Código Civil Federal se invoca."
        self.indexar(texto, "artículo 41.    Texto sintético que continúa el artículo anterior.",
                     {"source": CCF, "article": "41", "page": "6", "chunk_index": "41"}, 0.13)
        self.indexar(texto, "Artículo 41. Texto sintético del artículo cuarenta y uno.",
                     {"source": CCF, "article": "41", "page": "7", "chunk_index": "44"}, 0.17)
        fuente = self.unica(self.auditar(texto))
        self.assertEqual((fuente["page"], fuente["vvca"]["semaforo"]), ("7", "🟢"))
        self.assertTrue(fuente["vvca"]["explicabilidad"]["verde_determinista"])

    def test_solo_remision_es_amarilla_con_razon_honesta(self) -> None:
        for texto, documento in (
            ("El artículo 1 de la Ley Federal de Protección al Consumidor se invoca.",
             "artículo 1o., la fracción IX bis sintética al artículo 24 y otro texto."),
            ("El artículo 2 del Código Fiscal de la Federación se invoca.",
             "Artículo 2o., fracción I, inciso H.  Texto sintético de una cita."),
        ):
            with self.subTest(texto=texto):
                self.setUp()
                (ref,) = ON.extract_references(texto)
                etiqueta = "1o" if "Consumidor" in texto else "2o"
                self.indexar(texto, documento, {"source": ref["source_file"], "article": etiqueta,
                                                "page": "64", "chunk_index": "186"}, 0.12)
                resultado = self.auditar(texto)
                fuente = self.unica(resultado)
                vvca = fuente["vvca"]
                self.assertEqual((vvca["score"], vvca["semaforo"]), (84, "🟡"))
                self.assertFalse(vvca["explicabilidad"]["encabezado_autentico"])
                self.assertNotIn("verde_determinista", vvca["explicabilidad"])
                self.assertTrue(vvca["V_verificacion"].startswith("Solo remisión"))
                (alerta,) = resultado["alerts"]
                self.assertIn("solo se ubicó una remisión", alerta)
                self.assertEqual(self.estados(resultado)[0][1], "partial")

    # ── 2) Pertenencia al cuerpo ────────────────────────────────────────────────────────
    def test_frontera_creible_elige_el_encabezado_del_cuerpo(self) -> None:
        # Regla (i): cuerpo (chunk 1) y transitorio tras la frontera (chunk 6, más cercano).
        ley = LEY + [TRANSITORIO]
        self.assertTrue(frontera_creible(preparar_ley(fragmentos(ley), DENOMINACIONES))["creible"])
        self.cargar_ley(ley, {1: 0.17, 6: 0.10}, self.TEXTO_1O)
        fuente = self.unica(self.auditar(self.TEXTO_1O))
        self.assertEqual((fuente["page"], fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                         ("1", 85, "🟢"))
        self.assertEqual(fuente["vvca"]["explicabilidad"]["ubicacion"]["estado"],
                         "unico_antes_de_la_frontera")

    def test_dos_encabezados_antes_de_la_frontera_son_ambiguos(self) -> None:
        ley = LEY[:2] + [("Artículo 1o.- Otro texto sintético con el mismo encabezado.", "1o",
                          "1")] + LEY[2:]
        self.cargar_ley(ley, {1: 0.17, 2: 0.18}, self.TEXTO_1O)
        resultado = self.auditar(self.TEXTO_1O)
        fuente = self.unica(resultado)
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (83, "🟡"))
        self.assertIn("ubicación ambigua",
                      fuente["vvca"]["explicabilidad"]["ubicacion_no_acreditada"])
        self.assertTrue(resultado["alerts"][0].startswith("🟡 UBICACIÓN NO ACREDITADA"))

    def test_mismo_pasaje_repetido_cuenta_una_vez(self) -> None:
        ley = LEY[:2] + [("[LEY 1o]\nArtículo 1o.- Texto sintético del primer artículo de la ley "
                          "de prueba. Continúa el subfragmento.", "1o", "1")] + LEY[2:]
        self.cargar_ley(ley, {1: 0.17, 2: 0.18}, self.TEXTO_1O)
        fuente = self.unica(self.auditar(self.TEXTO_1O))
        self.assertEqual((fuente["page"], fuente["vvca"]["semaforo"]), ("1", "🟢"))

    def test_unico_encabezado_tras_la_frontera_es_transitorio(self) -> None:
        # Regla (ii): el cuerpo usa "ARTÍCULO" (el chunker no lo etiqueta) y solo el
        # transitorio "Artículo 1o.-" queda como candidato por metadata.
        ley = [(LEY[0][0], "", "1"),
               ("ARTÍCULO 1o.- Texto sintético del primer artículo de la ley de prueba.", "", "1")]
        ley += LEY[2:] + [TRANSITORIO]
        self.cargar_ley(ley, {6: 0.10}, self.TEXTO_1O)
        resultado = self.auditar(self.TEXTO_1O)
        fuente = self.unica(resultado)
        self.assertEqual((fuente["page"], fuente["vvca"]["score"], fuente["vvca"]["semaforo"]),
                         ("4", 84, "🟡"))
        self.assertEqual(fuente["vvca"]["explicabilidad"]["ubicacion"]["estado"],
                         "tras_la_frontera")
        self.assertIn("transitorio o de un decreto", resultado["alerts"][0])

    def test_ubicar_en_cuerpo_sin_frontera_admite_el_unico(self) -> None:
        # Regla (iii) (función pura).
        documentos = ["Artículo 9.- Texto sintético."]
        metadatas = [{"source": CFF, "article": "9", "page": "5", "chunk_index": "17"}]
        no_creible = {"creible": False, "motivo": "sin línea TRANSITORIOS", "chunk_index": None}
        ubicacion = ubicar_en_cuerpo(documentos, metadatas, "9", CFF, no_creible)
        self.assertEqual((ubicacion["estado"], ubicacion["indice"]), ("unico", 0))

    # ── 4) "°" con sufijo ──────────────────────────────────────────────────────────────
    def test_grado_con_sufijo_nunca_acredita_el_articulo_base(self) -> None:
        texto = "CFF Art. 4°-A."
        self.indexar(texto, "Artículo 4o.- Texto sintético del artículo cuarto.",
                     {"source": CFF, "article": "4o", "page": "2", "chunk_index": "6"}, 0.10)
        self.indexar(texto, "Artículo 4o.-A.- Texto sintético del artículo cuarto A.",
                     {"source": CFF, "article": "4o", "page": "3", "chunk_index": "7"}, 0.17)
        fuente = self.unica(self.auditar(texto))
        self.assertEqual((fuente["page"], fuente["vvca"]["semaforo"]), ("3", "🟢"))
        self.assertIn("cuarto A", fuente["retrieved_text_full"])
        # Sin el 4o.-A indexado, nunca 🟢 con el art. 4o.
        self.setUp()
        self.indexar(texto, "Artículo 4o.- Texto sintético del artículo cuarto.",
                     {"source": CFF, "article": "4o", "page": "2", "chunk_index": "6"}, 0.10)
        resultado = self.auditar(texto)
        self.assertNotIn("🟢", [f["vvca"]["semaforo"] for f in resultado["retrieved_sources"]])
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🟡")

    # ── 5) La metadata no sobrevive al respaldo semántico ──────────────────────────────
    def test_respaldo_semantico_no_hereda_la_metadata(self) -> None:
        # Hay candidato por metadata (etiqueta "16"), pero la consulta exacta falla y el
        # respaldo elige otro fragmento (etiqueta "15") que también trae "Artículo 16.".
        coleccion = FakeCollection(fallar_consultas_filtradas=True)
        texto = "El artículo 16 de la Constitución Política de los Estados Unidos Mexicanos."
        coleccion.agregar("Artículo 16. Texto sintético del candidato lejano.",
                          {"source": CPEUM, "article": "16", "page": "19", "chunk_index": "40"})
        self.indexar(texto, "Artículo 15.- Texto sintético.\nArtículo 16. Texto sintético.",
                     {"source": CPEUM, "article": "15", "page": "18", "chunk_index": "39"},
                     0.17, coleccion=coleccion)
        for pagina in ("8", "9"):
            self.indexar(texto, "Texto sintético de otro ordenamiento.",
                         {"source": LIVA, "article": "3", "page": pagina}, 0.20,
                         coleccion=coleccion)
        resultado = self.auditar(texto, coleccion=coleccion)
        fuente = self.unica(resultado)
        self.assertEqual(fuente["page"], "18")
        self.assertFalse(fuente["vvca"]["explicabilidad"]["match_metadata"])
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (83, "🟡"))
        self.assertEqual(self.estados(resultado)[0][2], "corpus_semantic")


if __name__ == "__main__":
    unittest.main()
