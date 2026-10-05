"""Tratados internacionales y párrafos numerados (criterio del responsable, 4-oct-2026, opción A).

Criterio del responsable jurídico (4-oct-2026, opción A): el encabezado "Artículo N" SOLO en su
línea, sin punto ni guion, cuenta como encabezado auténtico ÚNICAMENTE en los TRATADOS
INTERNACIONALES registrados en el catálogo (``OpenNotebook.TRATADOS_INTERNACIONALES``), nunca
por el nombre del archivo; las leyes nacionales siguen exigiendo el cierre. Es la misma
definición de ``itosturre.audit.evidence`` (``_fin_de_linea_autentico``, la forma
``FORMA_FIN_DE_LINEA`` que ya cortaba la ingesta), activada con ``fin_de_linea=True`` según la
fuente esperada en la selección de evidencia, la ubicación en el cuerpo, el cuerpo del
precepto, el cotejo de la unidad y la existencia de D10.

Párrafos numerados: "artículo 8.1", "artículo 8, numeral 1", "artículo 8, párrafo 1" ("8.1 y
8.2", "párrafos 1 y 2") son el artículo 8 con la unidad "párrafo numerado 1". Falla cerrada:
"N.M" nunca se reduce en silencio a "N"; el cotejo solo da la unidad por ubicada si encuentra
la línea "1." (y la numeración 1, 2, 3… del cuerpo es la de sus párrafos).

Corre sin dependencias (Python 3.11 del CI) con la colección y el codificador falsos de
``tests/vvca_falsos.py``. Todos los fragmentos son SINTÉTICOS (texto de relleno con la FORMA de
los fragmentos indexados de la CADH, la CDN y el PIDCP: encabezado sin cierre, línea de título,
párrafos "1.", subfragmentos con el prefijo "[LEY N]"); los tratados aparecen solo como TEXTO A
AUDITAR y como nombre de la fuente, nunca con su contenido.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from itosturre.audit.evidence import (
    FORMA_CIERRE,
    FORMA_FIN_DE_LINEA,
    cotejar_precepto,
    cotejar_unidad,
    encabezado_autentico,
    encabezados_autenticos,
    has_exact_article_heading,
    has_suffixed_variant_heading,
    ocurrencias_encabezado,
    reconstruir_cuerpo,
    select_article_evidence,
)
from itosturre.audit.inexistencia import (
    CANDIDATA,
    NUMERADO,
    evaluar_inexistencia,
    frontera_creible,
    preparar_ley,
)
from itosturre.audit.referencias import tipo_fuente
from itosturre.audit.ubicacion import AMBIGUO, FUERA_DE_SECUENCIA, UNICO, ubicar_en_cuerpo
from tests.test_vvca_nucleo import AuditoriaBase
from tests.test_vvca_verde_determinista import consulta_de
from tests.vvca_falsos import FakeCollection, importar_opennotebook

ON = importar_opennotebook()
CADH = ON.LAW_SOURCE_MAP["cadh"]
CDN = ON.LAW_SOURCE_MAP["cdn"]
PIDCP = ON.LAW_SOURCE_MAP["pidcp"]
CCJ = ON.LAW_SOURCE_MAP["ccj"]
CFF = ON.LAW_SOURCE_MAP["cff"]

V_DETERMINISTA = "Verificación determinista: artículo localizado por metadata"

# ── Fragmentos SINTÉTICOS con la forma de los tratados indexados ──────────────────────────
# CADH: "Artículo 8º" + línea de título + párrafos numerados con incisos.
CADH_8 = (
    "Artículo 8º \nGarantías Sintéticas de Prueba  \n \n"
    "1. Texto sintético del primer párrafo numerado de la prueba.  \n \n"
    "2. Texto sintético del segundo párrafo numerado, con incisos:  \n \n"
    "a) primer inciso sintético de la prueba;  \n \n"
    "h) último inciso sintético de la prueba.  \n \n"
    "3. Texto sintético del tercer párrafo numerado de la prueba."
)
CADH_9 = "Artículo 9º \nPrincipio Sintético  \n \nTexto sintético sin párrafos numerados."
# CDN: "ARTÍCULO N" en mayúsculas, sin título.
CDN_7 = (
    "ARTÍCULO 7 \n1. Texto sintético del primer párrafo de la prueba. \n"
    "2. Texto sintético del segundo párrafo de la prueba."
)
# PIDCP: "Artículo N" sin º.
PIDCP_14 = (
    "[LEY 14]\nArtículo 14  \n1. Texto sintético del primer párrafo de la prueba.  \n"
    "2. Texto sintético del segundo párrafo de la prueba.  \n"
    "3. Texto sintético del tercer párrafo, con incisos:  \n"
    "a) inciso sintético de la prueba;"
)


class RegistroDeTratadosTests(unittest.TestCase):
    def test_cada_tratado_registrado_esta_en_el_catalogo(self) -> None:
        self.assertIsInstance(ON.TRATADOS_INTERNACIONALES, frozenset)
        self.assertEqual(
            ON.TRATADOS_INTERNACIONALES,
            {
                "Convencion Americana sobre Derechos Humanos.pdf",
                "Convención sobre los Derechos del Niño.pdf",
                "Pacto Internacional de Derechos Civiles y Políticos.pdf",
            },
        )
        fuentes = set(ON.LAW_SOURCE_MAP.values())
        for fuente in ON.TRATADOS_INTERNACIONALES:
            with self.subTest(fuente=fuente):
                self.assertIn(fuente, fuentes)
                self.assertTrue(ON.es_tratado_internacional(fuente))
        self.assertEqual({CADH, CDN, PIDCP}, ON.TRATADOS_INTERNACIONALES)

    def test_solo_el_catalogo_decide_no_el_nombre_del_archivo(self) -> None:
        # Un PDF con nombre de tratado que el catálogo no registra se audita como ley, aunque la
        # heurística de nombres (``tipo_fuente``, para los genéricos) lo llame "tratado".
        for fuente in ("Convención Sintética de Prueba.pdf", "PACTO SINTETICO.pdf",
                       "TRATADO SINTETICO.pdf"):
            with self.subTest(fuente=fuente):
                self.assertEqual(tipo_fuente(fuente), "tratado")
                self.assertFalse(ON.es_tratado_internacional(fuente))
        for fuente in (CCJ, CFF, None, ""):
            with self.subTest(fuente=fuente):
                self.assertFalse(ON.es_tratado_internacional(fuente))

    def test_la_ingesta_usa_el_mismo_registro(self) -> None:
        # Ronda 2 (adjudicado): el cortador de la ingesta recibe el registro; "Artículo N" sin
        # cierre solo corta en un tratado registrado, y en una ley nacional no.
        paginas = [{"page": 1, "text": (
            "TEXTO SINTÉTICO DE PRUEBA\nPreámbulo sintético.\nARTÍCULO 1 \n"
            "Texto sintético del primero.\nARTÍCULO 2 \nTexto sintético del segundo."
        )}]
        for fuente, etiquetas in ((CDN, ["", "1", "2"]), (CCJ, [""])):
            with self.subTest(fuente=fuente):
                fragmentacion = ON.fragmentos_de_pdf(
                    Path(fuente), extraer=lambda _ruta: paginas, subdividir=lambda t: [t]
                )
                self.assertEqual([f.etiqueta for f in fragmentacion.fragmentos], etiquetas)


class EncabezadoDeTratadoTests(unittest.TestCase):
    def test_sin_cierre_solo_cuenta_en_un_tratado(self) -> None:
        for texto, articulo in (
            (CADH_8, "8"), (CADH_8, "8o"), (CADH_8, "8º"),
            (CDN_7, "7"), (PIDCP_14, "14"),
            ("ARTICULO 51\n1. Texto sintético.", "51"),
            ("Art. 3 \nTexto sintético.", "3"),
        ):
            with self.subTest(texto=texto[:30], articulo=articulo):
                # Por omisión (leyes nacionales) se exige el cierre: nada cambia.
                self.assertFalse(has_exact_article_heading(texto, articulo))
                self.assertFalse(encabezado_autentico(texto, articulo))
                # En un tratado registrado, el encabezado sin cierre es auténtico.
                self.assertTrue(has_exact_article_heading(texto, articulo, fin_de_linea=True))
                self.assertTrue(encabezado_autentico(texto, articulo, fin_de_linea=True))
                (ocurrencia,) = ocurrencias_encabezado(texto, articulo, fin_de_linea=True)
                self.assertEqual((ocurrencia["forma"], ocurrencia["autentico"]),
                                 (FORMA_FIN_DE_LINEA, True))

    def test_la_salvaguarda_es_la_de_la_ingesta(self) -> None:
        for texto, articulo, motivo in (
            ("Conforme al\nArtículo 51\nde esta Convención sintética.", "51", "continúa en minúscula"),
            ("Artículo 51\n, texto sintético.", "51", "continúa con coma"),
            ("Artículo 51\n; texto sintético.", "51", "continúa con punto y coma"),
            ("artículo 51\nTexto sintético.", "51", "minúscula"),
            ("Artículo\n51\n1. Texto sintético.", "51", "partido sin cierre"),
            ("Artículo 1\nBis.- Texto sintético.", "1", "sufijo en la línea siguiente"),
            ("Artículo 1 de la Convención sintética.", "1", "texto en su línea"),
            ("Artículo 10º \nTítulo Sintético", "1", "otro número"),
            ("Artículo 1º \nTítulo Sintético", "10", "otro número"),
            ("Artículo 8-A \nTítulo Sintético", "8", "sufijo"),
        ):
            with self.subTest(motivo=motivo, texto=texto):
                self.assertFalse(has_exact_article_heading(texto, articulo, fin_de_linea=True))
                self.assertFalse(encabezado_autentico(texto, articulo, fin_de_linea=True))

    def test_misma_definicion_que_encabezados_autenticos(self) -> None:
        # Las ocurrencias auténticas sin cierre de cada artículo son exactamente los
        # encabezados ``FORMA_FIN_DE_LINEA`` de la definición única (la de la ingesta).
        texto = "\n".join([
            "Preámbulo sintético.",
            "Artículo 1º ", "Título Sintético", "1. Texto sintético.",
            "ARTÍCULO 2 ", "Texto sintético del segundo.",
            "conforme al", "Artículo 3", "de la Convención sintética.",
            "artículo 4", "Texto sintético.",
            "Artículo 5.- Texto sintético con cierre.",
            "Artículo 6 ", "Texto sintético del sexto.",
        ])
        genericos = {
            h["designacion"]: h["forma"] for h in encabezados_autenticos(texto, fin_de_linea=True)
        }
        self.assertEqual(genericos, {"1º": FORMA_FIN_DE_LINEA, "2": FORMA_FIN_DE_LINEA,
                                     "5": FORMA_CIERRE, "6": FORMA_FIN_DE_LINEA})
        for articulo in ("1", "2", "3", "4", "5", "6"):
            with self.subTest(articulo=articulo):
                autenticas = [o["forma"] for o in ocurrencias_encabezado(
                    texto, articulo, fin_de_linea=True) if o["autentico"]]
                esperado = [genericos[d] for d in genericos if d.rstrip("º") == articulo]
                self.assertEqual(autenticas, esperado)

    def test_la_remision_con_cierre_sigue_sin_ser_autentica(self) -> None:
        # Un tratado no relaja la forma con cierre: "artículo 48." en minúscula al inicio de
        # línea (la PDF de un tratado la deja así) sigue siendo una remisión.
        texto = "artículo 48.  \n2. Texto sintético de otro artículo."
        (ocurrencia,) = ocurrencias_encabezado(texto, "48", fin_de_linea=True)
        self.assertEqual((ocurrencia["forma"], ocurrencia["autentico"]), (FORMA_CIERRE, False))
        self.assertFalse(encabezado_autentico(texto, "48", fin_de_linea=True))

    def test_variante_con_sufijo_y_seleccion(self) -> None:
        self.assertFalse(has_suffixed_variant_heading(CADH_8, "8", fin_de_linea=True))
        resultados = {
            "documents": [["artículo 8.  \nTexto sintético de una remisión.", CADH_8]],
            "metadatas": [[{"source": CADH, "article": "8", "page": "19", "chunk_index": "54"},
                           {"source": CADH, "article": "8º", "page": "4", "chunk_index": "8"}]],
            "distances": [[0.10, 0.16]],
        }
        elegido = select_article_evidence(resultados, "8", fin_de_linea=True)
        self.assertEqual((elegido["rank"], elegido["heading_authentic"],
                          elegido["heading_fin_de_linea"], elegido["heading_literal"]),
                         (2, True, True, False))
        # Por omisión, como antes: solo la remisión con cierre tiene forma de encabezado.
        elegido = select_article_evidence(resultados, "8")
        self.assertEqual((elegido["rank"], elegido["heading_authentic"],
                          elegido["heading_fin_de_linea"]), (1, False, False))


class CuerpoDeTratadoTests(unittest.TestCase):
    def test_el_cuerpo_empieza_tras_el_titulo_y_acaba_en_el_siguiente_encabezado(self) -> None:
        documento = CADH_8 + "\n\n" + CADH_9
        cuerpo = reconstruir_cuerpo(documento, None, "8", fin_de_linea=True)
        self.assertTrue(cuerpo["cerrado"])
        self.assertTrue(cuerpo["cuerpo"].lstrip().startswith("1. Texto sintetico del primer"))
        self.assertNotIn("Garantias Sinteticas", cuerpo["cuerpo"])
        self.assertNotIn("Principio Sintetico", cuerpo["cuerpo"])
        self.assertTrue(cuerpo["cuerpo"].rstrip().endswith("tercer parrafo numerado de la prueba."))
        # Sin título (CDN, PIDCP), el cuerpo empieza en la línea siguiente.
        cuerpo = reconstruir_cuerpo(CDN_7, None, "7", fin_de_linea=True)
        self.assertTrue(cuerpo["cuerpo"].lstrip().startswith("1. Texto sintetico"))
        # Por omisión no hay encabezado (las leyes exigen el cierre).
        self.assertIsNone(reconstruir_cuerpo(documento, None, "8"))

    def test_una_primera_linea_de_texto_no_es_titulo(self) -> None:
        for documento, inicio in (
            ("Artículo 34º\nLa Comisión sintética se compondrá de siete miembros.", "La Comision"),
            ("Artículo 3 \nToda persona sintética tiene derecho.", "Toda persona"),
            ("Artículo 5 \n(Se deroga)", "(Se deroga)"),
            ("Artículo 5 \nDerogado", "Derogado"),
            ("Artículo 6 \n1. Texto sintético.", "1. Texto"),
        ):
            with self.subTest(documento=documento):
                cuerpo = reconstruir_cuerpo(documento, None, documento.split()[1].rstrip("º"),
                                            fin_de_linea=True)
                self.assertTrue(cuerpo["cuerpo"].lstrip().startswith(inicio), cuerpo)

    def test_el_cuerpo_se_detiene_en_cualquier_candidato(self) -> None:
        # Ronda 2 (Codex P1, defensivo): en un tratado el cuerpo se detiene ante cualquier
        # línea candidata, aunque no se autentique (partido "Artículo⏎9", o con texto en su
        # línea); una remisión en minúscula al inicio de línea no corta.
        for siguiente in ("Artículo\n9\nTexto sintético del noveno.",
                          "Artículo 9 de la Convención sintética.",
                          "ARTICULO 9.- Texto sintético."):
            with self.subTest(siguiente=siguiente):
                documento = ("Artículo 8º \n1. Texto sintético del primer párrafo.\n"
                             + siguiente + "\n2. Texto sintético que no es del artículo 8.")
                cuerpo = reconstruir_cuerpo(documento, None, "8", fin_de_linea=True)
                self.assertTrue(cuerpo["cerrado"])
                self.assertNotIn("2. Texto sintetico", cuerpo["cuerpo"])
        documento = ("Artículo 8º \n1. Texto sintético que remite al\nartículo 48.\n"
                     "2. Texto sintético del segundo párrafo.")
        cuerpo = reconstruir_cuerpo(documento, None, "8", fin_de_linea=True)
        self.assertIn("2. Texto sintetico del segundo", cuerpo["cuerpo"])

    def test_un_titulo_solo_nunca_completa_la_evidencia(self) -> None:
        # Ronda 2 (adjudicado): separación conservadora del título, también con línea en
        # blanco y aunque la heurística ``_es_titulo`` no lo reconozca.
        for documento in (
            "Artículo 1º\n\nObligación Sintética de Respetar los Derechos",
            "Artículo 1º \nObligación sintética de respetar los derechos",
            "Artículo 1º \n\n\nTítulo Sintético",
        ):
            with self.subTest(documento=documento):
                self.assertFalse(cotejar_precepto(documento, None, "1", fin_de_linea=True)["completo"])
        for documento in (
            "Artículo 1º\n\nTítulo Sintético\n\nToda persona sintética tiene derecho.",
            "Artículo 3 \nLa Comisión sintética se compondrá de siete\nmiembros sintéticos.",
            "Artículo 7 \nNadie será sometido a pruebas sintéticas.",
        ):
            with self.subTest(documento=documento):
                articulo = documento.split()[1].rstrip("º")
                self.assertTrue(cotejar_precepto(documento, None, articulo,
                                                 fin_de_linea=True)["completo"])

    def test_encabezado_con_titulo_y_sin_texto_no_es_cuerpo_suficiente(self) -> None:
        documento = "Texto sintético previo.\nArtículo 8º \nGarantías Sintéticas de Prueba"
        cotejo = cotejar_precepto(documento, None, "8", fin_de_linea=True)
        self.assertFalse(cotejo["completo"])
        # Con la continuación del MISMO precepto (misma fuente, etiqueta y chunk consecutivo).
        meta = {"source": CADH, "article": "8º", "page": "4", "chunk_index": "8"}
        continuacion = ("[LEY 8º]\n1. Texto sintético del primer párrafo.\n"
                        "2. Texto sintético del segundo párrafo.\nArtículo 9º \nOtro Título")
        cotejo = cotejar_precepto(
            documento, meta, "8", [{"tipo": "parrafo_numerado", "valor": "2"}],
            [(documento, meta), (continuacion, dict(meta, chunk_index="9"))],
            fin_de_linea=True,
        )
        self.assertEqual((cotejo["completo"], cotejo["cerrado"], cotejo["continuaciones"]),
                         (True, True, 1))
        self.assertEqual(cotejo["unidad"]["estado"], "cotejada")


class ParrafoNumeradoTests(unittest.TestCase):
    def cotejar(self, cuerpo: str, *valores: str, inciso: str | None = None) -> dict:
        unidades = [{"tipo": "parrafo_numerado", "valor": v} for v in valores]
        if inciso:
            unidades.append({"tipo": "inciso", "valor": inciso})
        return cotejar_unidad(cuerpo, unidades, parrafos_numerados=True)

    def test_en_una_ley_nacional_el_parrafo_numerado_no_se_coteja(self) -> None:
        # Ronda 2 (adjudicado): en una ley, "párrafo 1" suele ser el primer párrafo por
        # posición; el cotejo positivo del párrafo numerado solo en tratados registrados,
        # también en las llamadas que no lo activan (por omisión).
        cuerpo = "\n1. Texto sintético uno.\n2. Texto sintético dos."
        for resultado in (
            cotejar_unidad(cuerpo, [{"tipo": "parrafo_numerado", "valor": "1"}]),
            cotejar_precepto("Artículo 20-Ter.- Texto sintético:" + cuerpo, None, "20-Ter",
                             [{"tipo": "parrafo_numerado", "valor": "1"}])["unidad"],
        ):
            with self.subTest(resultado=resultado):
                self.assertEqual(resultado["estado"], "no_cotejada")
                self.assertIn("solo se coteja en los tratados internacionales registrados",
                              resultado["motivo"])

    def test_se_ubica_la_linea_del_parrafo(self) -> None:
        cuerpo = reconstruir_cuerpo(CADH_8, None, "8", fin_de_linea=True)["cuerpo"]
        for valores in (("1",), ("2",), ("3",), ("1", "2")):
            with self.subTest(valores=valores):
                resultado = self.cotejar(cuerpo, *valores)
                self.assertEqual(resultado["estado"], "cotejada", resultado)
        self.assertEqual(self.cotejar(cuerpo, "2", inciso="h")["estado"], "cotejada")
        self.assertEqual(self.cotejar(cuerpo, "1")["descripcion"], "párrafo numerado 1")

    def test_parrafo_inexistente_o_sin_numeracion_no_se_coteja(self) -> None:
        cuerpo = reconstruir_cuerpo(CADH_8, None, "8", fin_de_linea=True)["cuerpo"]
        for valores, inciso, fragmento in (
            (("9",), None, "el párrafo 9 no se ubica"),
            (("3",), "h", "el inciso h) no se ubica"),
        ):
            with self.subTest(valores=valores, inciso=inciso):
                resultado = self.cotejar(cuerpo, *valores, inciso=inciso)
                self.assertEqual(resultado["estado"], "no_cotejada")
                self.assertIn(fragmento, resultado["motivo"])
        sin_parrafos = reconstruir_cuerpo(CADH_9, None, "9", fin_de_linea=True)["cuerpo"]
        resultado = self.cotejar(sin_parrafos, "1")
        self.assertEqual(resultado["estado"], "no_cotejada")
        self.assertIn("no tiene párrafos numerados", resultado["motivo"])

    def test_la_numeracion_debe_ser_la_de_los_parrafos(self) -> None:
        for cuerpo, motivo in (
            # Falta un número (la marca "3 " sin punto): el 3 no se ubica; el 2 sí.
            ("\n1. Texto sintético uno.\n2. Texto sintético dos.\n3 Texto sintético tres.",
             None),
            # Repetida, salto, o lista dentro de una fracción: nada se ubica.
            ("\n1. Texto sintético.\n2. Texto sintético.\n2. Otro texto sintético.", "secuencia"),
            ("\n1. Texto sintético.\n3. Texto sintético.", "secuencia"),
            ("\nI. Fracción sintética:\n1. Texto sintético.\n2. Texto sintético.", "fracciones"),
            ("\na) Inciso sintético:\n1. Texto sintético.\n2. Texto sintético.", "fracciones"),
        ):
            with self.subTest(cuerpo=cuerpo):
                resultado = self.cotejar(cuerpo, "2")
                if motivo is None:
                    self.assertEqual(resultado["estado"], "cotejada")
                    self.assertEqual(self.cotejar(cuerpo, "3")["estado"], "no_cotejada")
                else:
                    self.assertEqual(resultado["estado"], "no_cotejada")
                    self.assertIn(motivo, resultado["motivo"])

    def test_marcas_que_no_son_parrafos(self) -> None:
        # "1.e." (remisión a un inciso), "1.1", "2016." y "1 de junio" no son marcas.
        cuerpo = ("\n1. Texto sintético del párrafo uno, conforme al inciso\n"
                  "1.e. del artículo sintético.\n1.1 Texto sintético.\n2016.\n1 de junio sintético.\n"
                  "2. Texto sintético del párrafo dos.")
        self.assertEqual(self.cotejar(cuerpo, "1")["estado"], "cotejada")
        self.assertEqual(self.cotejar(cuerpo, "2")["estado"], "cotejada")

    def test_solo_el_solapamiento_comprobado_cuenta_una_vez(self) -> None:
        # Ronda 2 (Codex P1): la línea repetida por el solapamiento de la ingesta (la
        # continuación CONSECUTIVA empieza repitiendo el final del fragmento anterior) se
        # descuenta al reunir el cuerpo; una repetición en otro lugar sigue siendo repetición.
        meta = {"source": CADH, "article": "8º", "page": "4", "chunk_index": "8"}
        primero = ("Artículo 8º \nTítulo Sintético\n1. Texto sintético uno.\n"
                   "2. Texto sintético dos.\n3. Texto sintético tres.\n"
                   "4. Texto sintético del cuarto párrafo que el solapamiento repite")
        segundo = ("[LEY 8º]\n3. Texto sintético tres.\n"
                   "4. Texto sintético del cuarto párrafo que el solapamiento repite \n"
                   "y sigue el texto sintético del cuarto párrafo.\n5. Texto sintético cinco.")
        candidatos = [(primero, meta), (segundo, dict(meta, chunk_index="9"))]
        for valor in ("3", "4", "5"):
            with self.subTest(valor=valor):
                cotejo = cotejar_precepto(primero, meta, "8",
                                          [{"tipo": "parrafo_numerado", "valor": valor}],
                                          candidatos, fin_de_linea=True)
                self.assertEqual(cotejo["unidad"]["estado"], "cotejada", cotejo)
        # Sin el modo tratado el solapamiento no se descuenta (las leyes no cambian).
        cuerpo = reconstruir_cuerpo(primero.replace("Artículo 8º ", "Artículo 8.- "), meta, "8",
                                    [(c.replace("Artículo 8º ", "Artículo 8.- "), m)
                                     for c, m in candidatos])["cuerpo"]
        self.assertEqual(cuerpo.count("3. Texto sintetico tres."), 2)
        # La misma línea repetida dentro de un fragmento no es solapamiento: no se ubica.
        repetida = ("\n1. Texto sintético uno.\n2. Texto sintético dos.\n"
                    "2. Texto sintético dos.\n3. Texto sintético tres.")
        self.assertEqual(self.cotejar(repetida, "1")["estado"], "no_cotejada")

    def test_el_parrafo_debe_estar_antes_de_las_notas(self) -> None:
        cuerpo = ("\n1. Texto sintético uno.\n2. Texto sintético dos.\nNotas explicativas\n"
                  "3. Texto sintético de una nota.")
        self.assertEqual(self.cotejar(cuerpo, "2")["estado"], "cotejada")
        resultado = self.cotejar(cuerpo, "3")
        self.assertEqual(resultado["estado"], "no_cotejada")
        self.assertIn("el párrafo 3 no se ubica", resultado["motivo"])
        self.assertEqual(self.cotejar("\nNota: texto sintético.\n1. Texto sintético.", "1")["estado"],
                         "no_cotejada")

    def test_fraccion_y_parrafo_a_la_vez_no_se_cotejan(self) -> None:
        resultado = cotejar_unidad("\n1. Texto sintético.\nI. Fracción sintética.",
                                   [{"tipo": "fraccion", "valor": "I"},
                                    {"tipo": "parrafo_numerado", "valor": "1"}])
        self.assertEqual(resultado["estado"], "no_cotejada")


class UbicacionEnElTratadoTests(unittest.TestCase):
    def test_sin_frontera_un_encabezado_se_admite_y_dos_son_ambiguos(self) -> None:
        frontera = frontera_creible(preparar_ley(
            [(CADH_8, {"source": CADH, "article": "8º", "page": "4", "chunk_index": "0"})],
            fin_de_linea=True,
        ))
        self.assertFalse(frontera["creible"])
        meta = {"source": CADH, "article": "8º", "page": "4", "chunk_index": "8"}

        def ley(*filas):
            return preparar_ley([(texto, dict(meta, chunk_index=str(indice)))
                                 for indice, texto in filas], fin_de_linea=True)

        siete = "Artículo 7º \nTítulo Sintético\n\nTexto sintético del séptimo."
        nueve = CADH_9
        en_orden = ley((7, siete), (8, CADH_8), (9, nueve))
        unico = ubicar_en_cuerpo([CADH_8], [meta], "8", CADH, frontera, fin_de_linea=True,
                                 ley=en_orden)
        self.assertEqual((unico["estado"], unico["indice"]), (UNICO, 0))
        otro = "Artículo 8º \nTítulo Sintético Distinto\n\n1. Otro texto sintético de prueba."
        doble = ubicar_en_cuerpo([CADH_8, otro], [meta, dict(meta, chunk_index="80", page="30")],
                                 "8", CADH, frontera, fin_de_linea=True, ley=en_orden)
        self.assertEqual(doble["estado"], AMBIGUO)
        # Ronda 2 (Codex P1, defensivo): el único encabezado debe encajar en la secuencia de
        # la fuente (N−1 antes y N+1 después); si no, o sin la ley, no se acredita.
        for nombre, preparada in (
            ("fuera de orden", ley((7, nueve), (8, CADH_8), (9, siete))),
            ("sin la ley", None),
        ):
            with self.subTest(nombre=nombre):
                fuera = ubicar_en_cuerpo([CADH_8], [meta], "8", CADH, frontera,
                                         fin_de_linea=True, ley=preparada)
                self.assertEqual(fuera["estado"], FUERA_DE_SECUENCIA)
                self.assertIn("secuencia", fuera["motivo"])
        # Por omisión no hay encabezado auténtico (las leyes exigen el cierre).
        self.assertEqual(ubicar_en_cuerpo([CADH_8], [meta], "8", CADH, frontera)["estado"],
                         "sin_encabezado_autentico")


class InexistenciaEnTratadosTests(unittest.TestCase):
    TRATADO = [
        ("Convención Americana sintética de prueba\nPreámbulo sintético.", "", "1"),
        ("Artículo 1º \nTítulo Sintético\n\nTexto sintético del primero.\n\n"
         "Artículo 3º \nTítulo Sintético\n\nTexto sintético del tercero.", "1º", "1"),
        ("Artículo 5º \nTítulo Sintético\n\nTexto sintético del quinto.", "5º", "2"),
    ]

    def fragmentos(self, filas=None, fuente=CADH):
        return [(texto, {"source": fuente, "article": etiqueta, "page": pagina,
                         "chunk_index": str(indice)})
                for indice, (texto, etiqueta, pagina) in enumerate(filas or self.TRATADO)]

    def test_sin_frontera_transitorios_se_abstiene(self) -> None:
        for articulo in ("2", "4", "6", "90", "500"):
            with self.subTest(articulo=articulo):
                evaluacion = evaluar_inexistencia(
                    preparar_ley(self.fragmentos(), ON._denominaciones(CADH), fin_de_linea=True),
                    articulo,
                )
                self.assertFalse(evaluacion["acreditada"])
                self.assertIn("TRANSITORIOS", evaluacion["motivo"])

    def test_encabezados_numerados_y_existencia_con_la_definicion_de_tratado(self) -> None:
        # Con una frontera (hipotética en un tratado), los encabezados sin cierre son
        # numerados solo en modo tratado, y su existencia impide la prueba.
        filas = self.TRATADO + [("TRANSITORIOS\nTexto sintético.", "", "3")]
        denominaciones = ON._denominaciones(CADH)
        preparada = preparar_ley(self.fragmentos(filas), denominaciones, fin_de_linea=True)
        self.assertEqual(preparada.identidad, "")
        self.assertEqual([e.tipo for e in preparada.encabezados], [NUMERADO] * 3)
        como_ley = preparar_ley(self.fragmentos(filas), denominaciones)
        self.assertEqual([e.tipo for e in como_ley.encabezados], [CANDIDATA] * 3)
        evaluacion = evaluar_inexistencia(preparada, "5")
        self.assertFalse(evaluacion["acreditada"])
        self.assertIn("el encabezado del artículo 5 aparece en la fuente", evaluacion["motivo"])


class ExtraccionDeParrafosTests(unittest.TestCase):
    def refs(self, texto: str) -> list[tuple]:
        return [(r["article"], r["law"], r["unidad_citada"], r["coverage_gap"])
                for r in ON.extract_references(texto)]

    def test_parrafo_numerado_nunca_se_reduce_al_articulo(self) -> None:
        p = lambda *v: [{"tipo": "parrafo_numerado", "valor": x} for x in v]   # noqa: E731
        casos = {
            "artículo 8.1 de la Convención Americana sobre Derechos Humanos":
                [("8", "convención americana", p("1"), None)],
            "artículo 8, numeral 1, de la CADH": [("8", "cadh", p("1"), None)],
            "artículo 8, párrafo 1, de la CADH": [("8", "cadh", p("1"), None)],
            "artículo 14.3 del PIDCP": [("14", "pidcp", p("3"), None)],
            "artículo 3.1 de la Convención sobre los Derechos del Niño":
                [("3", "convención sobre los derechos del niño", p("1"), None)],
            "artículo 8º.1 de la CADH": [("8º", "cadh", p("1"), None)],
            "artículo 8.1 y 8.2 de la CADH": [("8", "cadh", p("1"), None),
                                              ("8", "cadh", p("2"), None)],
            "artículo 8, párrafos 1 y 2, de la CADH": [("8", "cadh", p("1", "2"), None)],
            "artículo 8, numerales 1, 2 y 3, de la CADH": [("8", "cadh", p("1", "2", "3"), None)],
            "los párrafos 1 y 2 del artículo 8 de la CADH": [("8", "cadh", p("1", "2"), None)],
            "artículo 8.2, inciso h), de la CADH":
                [("8", "cadh", p("2") + [{"tipo": "inciso", "valor": "h"}], None)],
            "artículos 8.1 y 25 de la Convención Americana":
                [("8", "convención americana", p("1"), None),
                 ("25", "convención americana", [], None)],
            "artículos 8 y 25 de la Convención Americana":
                [("8", "convención americana", [], None),
                 ("25", "convención americana", [], None)],
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(self.refs(texto), esperado)

    def test_lo_que_no_se_extrae_completo_es_cobertura_incompleta(self) -> None:
        for texto, fragmento in (
            ("artículo 8. 1 de la CADH", "'8. 1'"),
            ("artículo 8.1.2 de la CADH", "'8.1.2'"),
            ("artículo 8.100 de la CADH", "'8.100'"),
        ):
            with self.subTest(texto=texto):
                ((articulo, _ley, _unidad, cobertura),) = self.refs(texto)
                self.assertEqual(articulo, "8")
                self.assertIn(f"la designación continúa en el texto ({fragmento})", cobertura)
        # Un rango de párrafos y "párrafo 1, y 25": el 25 o el 8.3 no desaparecen.
        refs = self.refs("artículo 8.1 a 8.3 de la CADH")
        self.assertEqual(refs[0][2], [{"tipo": "parrafo_numerado", "valor": "1"}])
        self.assertIn("8.3 de la CADH", refs[1][3])
        refs = self.refs("artículo 8, párrafo 1, y 25 de la CADH")
        self.assertEqual([r[0] for r in refs], ["8", "25"])
        self.assertIn("posible artículo 25", refs[1][3])

    def test_lo_demas_no_cambia(self) -> None:
        casos = {
            "El artículo 8. La CADH dispone.": [("8", "desconocido", [], None)],
            "CPEUM Art. 1.": [("1", "cpeum", [], None)],
            "El artículo 19 párrafo 2° de la CPEUM.":
                [("19", "cpeum", [{"tipo": "parrafo", "valor": "2°"}], None)],
            "El artículo 16, párrafo segundo, de la CPEUM.":
                [("16", "cpeum", [{"tipo": "parrafo", "valor": "segundo"}], None)],
            "El artículo 16. 2o. párrafo de la CPEUM.":
                [("16", "cpeum", [{"tipo": "parrafo", "valor": "2o."}], None)],
            "artículos 1o. y 2o. de la CPEUM": [("1o", "cpeum", [], None),
                                                 ("2o", "cpeum", [], None)],
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(self.refs(texto), esperado)

    def test_listas_de_unidades_se_extraen_completas(self) -> None:
        # Ronda 2 (Codex P1, reproducido): antes solo se tomaba la primera unidad de la lista.
        p = lambda v: {"tipo": "parrafo_numerado", "valor": v}      # noqa: E731
        inc = lambda v: {"tipo": "inciso", "valor": v}             # noqa: E731
        fr = lambda v: {"tipo": "fraccion", "valor": v}            # noqa: E731
        casos = {
            "artículo 8.2, incisos c), d) y f), de la Convención Americana sobre Derechos "
            "Humanos": [p("2"), inc("c"), inc("d"), inc("f")],
            "artículo 8.2, incisos a) y z), de la CADH": [p("2"), inc("a"), inc("z")],
            "artículo 8, incisos a, b y c, de la CADH": [inc("a"), inc("b"), inc("c")],
            "artículo 107, fracción III, incisos a) y b), de la Ley de Amparo":
                [fr("III"), inc("a"), inc("b")],
            "artículo 42, fracciones I, II y IV, del CFF": [fr("I"), fr("II"), fr("IV")],
            "artículo 42, fracción I y II, del CFF": [fr("I"), fr("II")],
            "los incisos a) y b) de la fracción III del artículo 107 de la Ley de Amparo":
                [inc("a"), inc("b"), fr("III")],
            "artículo 16, apartados A y B, de la CPEUM":
                [{"tipo": "apartado", "valor": "A"}, {"tipo": "apartado", "valor": "B"}],
            "artículo 16, párrafos primero y segundo, de la CPEUM":
                [{"tipo": "parrafo", "valor": "primero"}, {"tipo": "parrafo", "valor": "segundo"}],
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                ((_articulo, _ley, unidad, cobertura),) = self.refs(texto)
                self.assertEqual(unidad, esperado)
                self.assertIsNone(cobertura)

    def test_unidad_que_no_se_extrae_completa_es_cobertura_incompleta(self) -> None:
        # Falla cerrada: lo que queda entre las unidades leídas y la ley ligada y parece una
        # unidad nunca se descarta en silencio.
        for texto in ("artículo 16, apartado A y B, de la CPEUM",
                      "artículo 8, inciso a) y z, de la CADH"):
            with self.subTest(texto=texto):
                ((_articulo, _ley, _unidad, cobertura),) = self.refs(texto)
                self.assertIn("la unidad citada continúa en el texto", cobertura)
        # "párrafos 1 y 2°" (número y ordinal mezclados): el 2° no se pierde (sin vínculo con
        # la ley, queda como posible artículo con cobertura incompleta).
        refs = self.refs("artículo 19, párrafos 1 y 2°, de la CPEUM")
        self.assertTrue(any(r[3] for r in refs))

    def test_numeral_con_ordinal_ya_no_se_pierde(self) -> None:
        # Antes "numeral 1o." no era unidad y la cita se auditaba como la fracción VIII sola.
        ((articulo, _ley, unidad, _cobertura),) = self.refs(
            "artículo 35, fracción VIII, numeral 1o., de la CPEUM")
        self.assertEqual(unidad, [{"tipo": "fraccion", "valor": "VIII"},
                                  {"tipo": "otra", "valor": "numeral 1o."}])


class AuditoriaDeTratadosTests(AuditoriaBase):
    def indexar(self, texto_cita: str, documento: str, metadata: dict, distancia: float) -> None:
        self.coleccion.agregar(documento, metadata,
                               eje=self.codificador.eje(consulta_de(texto_cita)),
                               distancia=distancia)

    def indexar_cadh(self, texto: str, distancia: float = 0.17) -> None:
        self.coleccion.agregar("Convención Americana sintética\nPreámbulo sintético.",
                               {"source": CADH, "article": "", "page": "1", "chunk_index": "0"})
        self.indexar(texto, CADH_8, {"source": CADH, "article": "8º", "page": "4",
                                     "chunk_index": "8"}, distancia)
        self.coleccion.agregar(CADH_9, {"source": CADH, "article": "9º", "page": "5",
                                        "chunk_index": "9"})

    def unica(self, resultado: dict) -> tuple[dict, dict]:
        (fuente,) = resultado["retrieved_sources"]
        (traza,) = resultado["traceability"]["records"]
        return fuente, traza

    def test_articulo_de_tratado_es_verde_determinista(self) -> None:
        texto = "artículo 8 de la Convención Americana sobre Derechos Humanos"
        self.indexar_cadh(texto)
        resultado = self.auditar(texto)
        fuente, traza = self.unica(resultado)
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (85, "🟢"))
        explicabilidad = fuente["vvca"]["explicabilidad"]
        self.assertTrue(explicabilidad["verde_determinista"])
        self.assertTrue(explicabilidad["encabezado_fin_de_linea"])
        self.assertEqual(explicabilidad["ubicacion"]["estado"], UNICO)
        self.assertTrue(fuente["vvca"]["V_verificacion"].startswith(V_DETERMINISTA))
        self.assertTrue(fuente["retrieved_text_full"].startswith("Artículo 8º"))
        self.assertEqual(traza["verification"]["status"], "verified")
        self.assertEqual(resultado["alerts"], [])

    def test_sin_registro_el_mismo_texto_se_audita_como_ley(self) -> None:
        # Fuera del registro (p. ej. un PDF de tratado no registrado): se exige el cierre.
        texto = "artículo 8 de la Convención Americana sobre Derechos Humanos"
        self.indexar_cadh(texto)
        with mock.patch.object(ON, "TRATADOS_INTERNACIONALES", frozenset()):
            resultado = self.auditar(texto)
        fuente, _traza = self.unica(resultado)
        self.assertEqual(fuente["vvca"]["semaforo"], "🟡")
        self.assertFalse(fuente["vvca"]["explicabilidad"]["encabezado_articulo"])
        self.assertNotIn("encabezado_fin_de_linea", fuente["vvca"]["explicabilidad"])

    def test_parrafo_numerado_ubicado_y_no_ubicado(self) -> None:
        for texto, esperado, cotejada in (
            ("artículo 8.1 de la CADH", (85, "🟢"), True),
            ("artículo 8, numeral 3, de la CADH", (85, "🟢"), True),
            ("artículo 8.2, inciso h), de la CADH", (85, "🟢"), True),
            # Ronda 2: TODAS las unidades de la lista deben cotejarse.
            ("artículo 8.2, incisos a) y h), de la CADH", (85, "🟢"), True),
            ("artículo 8.2, incisos a) y z), de la CADH", (83, "🟡"), False),
            # Sin la línea "9.": tope 84, sin piso (el puntaje por similitud a 0.17 es 83).
            ("artículo 8.9 de la CADH", (83, "🟡"), False),
        ):
            with self.subTest(texto=texto):
                self.coleccion = FakeCollection()
                self.indexar_cadh(texto)
                resultado = self.auditar(texto)
                fuente, _traza = self.unica(resultado)
                self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), esperado)
                self.assertEqual(fuente["unidad_cotejada"], cotejada)
                if not cotejada:
                    (alerta,) = resultado["alerts"]
                    self.assertTrue(alerta.startswith("🟡 UNIDAD CITADA NO COTEJADA (score 83)"))
                    self.assertNotIn("verde_determinista", fuente["vvca"]["explicabilidad"])
                    self.assertTrue("el párrafo 9 no se ubica" in alerta
                                    or "el inciso z) no se ubica" in alerta, alerta)

    def test_parrafo_1_en_una_ley_nacional_queda_amarillo(self) -> None:
        # Ronda 2 (corpus real: "artículo 20-Ter, párrafo 1, del CFF" salía 🟢 casando la línea
        # "1." de una lista): en una ley, el párrafo numerado no se coteja.
        texto = "artículo 20-Ter, párrafo 1, del CFF"
        self.indexar(texto, "Artículo 20-Ter.- Texto sintético de prueba:\n"
                     "1. Texto sintético del primer elemento.\n2. Texto sintético del segundo.",
                     {"source": CFF, "article": "20-Ter", "page": "40", "chunk_index": "113"},
                     0.17)
        resultado = self.auditar(texto)
        fuente, _traza = self.unica(resultado)
        self.assertEqual(fuente["vvca"]["semaforo"], "🟡")
        self.assertFalse(fuente["unidad_cotejada"])
        self.assertIn("solo se coteja en los tratados internacionales registrados",
                      fuente["unidad_no_cotejada"])

    def test_parrafo_con_espacio_es_cobertura_incompleta(self) -> None:
        texto = "artículo 8. 1 de la CADH"
        self.coleccion.agregar(CADH_8, {"source": CADH, "article": "8º", "page": "4",
                                        "chunk_index": "8"})
        resultado = self.auditar(texto)
        self.assertEqual(resultado["retrieved_sources"], [])
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith("🟡 COBERTURA INCOMPLETA: 'artículo 8'"))

    def test_ruta_semantica_sin_metadata_no_da_verde(self) -> None:
        # El fragmento no lleva la etiqueta del artículo: la evidencia es semántica (con el
        # encabezado "Artículo 14" sin ordinal, para no mezclar la equivalencia ordinal).
        texto = "artículo 14 del Pacto Internacional de Derechos Civiles y Políticos"
        self.indexar(texto, PIDCP_14, {"source": PIDCP, "article": "", "page": "5",
                                       "chunk_index": "14"}, 0.10)
        resultado = self.auditar(texto)
        fuente, _traza = self.unica(resultado)
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (84, "🟡"))
        self.assertTrue(fuente["vvca"]["explicabilidad"]["encabezado_fin_de_linea"])
        (alerta,) = resultado["alerts"]
        self.assertTrue(alerta.startswith("🟡 COTEJAR (score 84)"))
        self.assertIn("encabezado sin cierre", alerta)

    def test_articulo_inexistente_de_un_tratado_nunca_es_rojo(self) -> None:
        texto = "artículo 90 de la Convención Americana sobre Derechos Humanos"
        self.coleccion.agregar("Convención Americana sintética\nPreámbulo sintético.",
                               {"source": CADH, "article": "", "page": "1", "chunk_index": "0"})
        self.indexar(texto, CADH_8, {"source": CADH, "article": "8º", "page": "4",
                                     "chunk_index": "1"}, 0.40)
        resultado = self.auditar(texto)
        self.assertEqual(resultado["vvca_summary"]["rojos"], 0)
        self.assertFalse([a for a in resultado["alerts"] if a.startswith("🔴")])
        fuente, traza = self.unica(resultado)
        self.assertEqual(fuente["vvca"]["semaforo"], "🟡")
        self.assertIn("TRANSITORIOS", fuente["vvca"]["explicabilidad"]["inexistencia_no_acreditada"])

    def test_ley_nacional_con_encabezado_sin_cierre_no_cambia(self) -> None:
        # El Código Civil de Jalisco tiene líneas "Artículo N" sin cierre (no es tratado): no
        # son encabezados; la cita queda como antes (sin encabezado exacto, 🟡).
        texto = "artículo 1 del Código Civil del Estado de Jalisco"
        self.indexar(texto, "Artículo 1 \nTexto sintético que no es un encabezado de la ley.",
                     {"source": CCJ, "article": "1", "page": "9", "chunk_index": "40"}, 0.17)
        resultado = self.auditar(texto)
        fuente, _traza = self.unica(resultado)
        self.assertEqual(fuente["vvca"]["semaforo"], "🟡")
        self.assertFalse(fuente["vvca"]["explicabilidad"]["encabezado_articulo"])


if __name__ == "__main__":
    unittest.main()
