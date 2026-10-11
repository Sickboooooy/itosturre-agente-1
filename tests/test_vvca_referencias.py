"""Unidades puras de ``itosturre.audit.referencias`` (R4b): designación de artículos,
enumeraciones, oraciones, catálogo de leyes y resolución del ordenamiento.

Sin dependencias ni corpus. Los textos mencionan leyes y artículos reales como TEXTO A
AUDITAR, no como citas que se afirmen. Las pruebas de los defectos R4-D01…D06 (y su
registro) están en ``tests/test_vvca_nucleo.py``.
"""
from __future__ import annotations

import unittest

from itosturre.audit import referencias as R

MAPA = {
    "cpeum": "CPEUM.pdf",
    "constitución política de los estados unidos": "CPEUM.pdf",
    "constitución": "CPEUM.pdf",
    "constitucional": "CPEUM.pdf",
    "constitución política del estado de jalisco": "CPEJ.pdf",
    "cff": "CODIGO FISCAL.pdf",
    "código fiscal de la federación": "CODIGO FISCAL.pdf",
    "liva": "Ley del IVA.pdf",
    "ley de amparo": "LEY DE AMPARO.pdf",
    "lfdo": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA.pdf",
    "ley federal de delincuencia organizada": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA.pdf",
    "delincuencia organizada": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA.pdf",
    "reglamento de la ley federal de protección al consumidor": "REGLAMENTO LFPC.pdf",
    "ley federal de protección al consumidor": "LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR.pdf",
}
ALIAS = {
    "CPEUM": "Constitución Política de los Estados Unidos Mexicanos",
    "Constitución": "Constitución Política de los Estados Unidos Mexicanos",
    "Ejecución Penal": "Ley Nacional de Ejecución Penal",
}
CATALOGO = R.construir_catalogo(MAPA, ALIAS)


def _leyes(texto: str) -> list[tuple]:
    return [
        (r["article"], r["law"], r["source_file"], r["law_method"], r["law_inferred"])
        for r in R.extraer_articulos(texto, CATALOGO)
    ]


class DesignacionTests(unittest.TestCase):
    def test_partes_articulo(self) -> None:
        casos = {
            "247 Ter": ("247", "", "", "ter"),
            "4o.-A": ("4", "o", "A", ""),
            "4o-a": ("4", "o", "A", ""),
            "2o. Bis": ("2", "o", "", "bis"),
            "32-B Quáter": ("32", "", "B", "quater"),
            "17-H Bis": ("17", "", "H", "bis"),
            "19º": ("19", "º", "", ""),
            "5A": ("5", "", "A", ""),
        }
        for articulo, esperado in casos.items():
            with self.subTest(articulo=articulo):
                partes = R.partes_articulo(articulo)
                # Ronda 2 de la re-ingesta: dos campos añadidos (subnúmero y número latino).
                self.assertEqual(tuple(partes)[:4], esperado)
                self.assertEqual((partes.subnumero, partes.numero_latino), ("", ""))
        # Ronda 2 (4-oct-2026): subnúmero pegado menor que el número, número tras el sufijo
        # latino y sufijos más allá de "decies" (forma canónica).
        for articulo, esperado in {
            "58-1": ("58", "", "", "", "1", ""),
            "142-0": ("142", "", "", "", "0", ""),
            "65 Bis 1": ("65", "", "", "bis", "", "1"),
            "76 BIS 1": ("76", "", "", "bis", "", "1"),
            "67 Terdecies": ("67", "", "", "terdecies", "", ""),
            "67. Quaterdecies": ("67", "", "", "quaterdecies", "", ""),
            "5 Sexies Decies": ("5", "", "", "sexiesdecies", "", ""),
            "63 QUINTUS": ("63", "", "", "quintus", "", ""),
        }.items():
            with self.subTest(articulo=articulo):
                self.assertEqual(tuple(R.partes_articulo(articulo)), esperado)
        self.assertIsNone(R.partes_articulo("14-16"))   # M ≥ N: rango, no designación
        self.assertIsNone(R.partes_articulo("247-250"))
        self.assertIsNone(R.partes_articulo("Único"))
        self.assertEqual(R.partes_articulo("4o.-A").base, "4o")
        self.assertTrue(R.articulo_con_sufijo("29-A"))
        self.assertFalse(R.articulo_con_sufijo("29"))

    def test_patron_tolerante_al_ordinal_pero_no_a_los_sufijos(self) -> None:
        import re

        def menciona(texto: str, articulo: str) -> bool:
            patron = R.patron_articulo(articulo, ordinal_estricto=False, espacio=r"\s")
            return bool(re.search(rf"articulo\s+{patron}", R.sin_acentos(texto), re.I))

        self.assertTrue(menciona("Artículo 1o. Todas las personas…", "1"))
        self.assertTrue(menciona("Artículo 4o.- Son créditos fiscales…", "4o"))
        self.assertFalse(menciona("Artículo 4o.-A.- Los impuestos…", "4o"))
        self.assertFalse(menciona("Artículo 4o.-A.- Los impuestos…", "4"))
        self.assertTrue(menciona("Artículo 4o.-A.- Los impuestos…", "4o.-A"))
        self.assertFalse(menciona("Artículo 247.- Se impondrán…", "247 Ter"))
        self.assertFalse(menciona("Artículo 2945.- …", "294"))


class EnumeracionTests(unittest.TestCase):
    def test_designaciones(self) -> None:
        self.assertEqual(
            R.designaciones_articulo("arts. 14, 16 y 19; artículo 247 Ter; art. 4o.-A; Art. 5 e 7"),
            ["14", "16", "19", "247 Ter", "4o.-A", "5", "7"],
        )
        self.assertEqual(R.designaciones_articulo("artículos 1o. y 2o."), ["1o", "2o"])
        self.assertEqual(R.designaciones_articulo("artículo 5, 3/2019"), ["5"])
        self.assertEqual(R.designaciones_articulo("artículo 5 a 10 días"), ["5"])
        self.assertEqual(R.designaciones_articulo("artículos 1910, 1915 y 1916"),
                         ["1910", "1915", "1916"])
        self.assertEqual(R.designaciones_articulo("Art. 247-250"), ["247", "248", "249", "250"])
        self.assertEqual(R.designaciones_articulo("Art. 29-A y 29-B"), ["29-A", "29-B"])

    def test_numeral_y_precepto_como_cabeza(self) -> None:
        # Ronda 3: "numeral"/"precepto" abren referencia; tras otro número o un apartado,
        # "numeral" califica al precepto y no abre otra.
        self.assertEqual(R.designaciones_articulo("el numeral 16 y los preceptos 14 y 17"),
                         ["16", "14", "17"])
        self.assertEqual(R.designaciones_articulo("artículo 9, numeral 2, del Reglamento"), ["9"])
        self.assertEqual(R.designaciones_articulo("artículo 16, apartado A, numeral 3"), ["16"])

    def test_punto_y_coma_con_ley_propia_sigue_la_enumeracion(self) -> None:
        self.assertEqual(
            _leyes("Los artículos 14 de la CPEUM; 42 del CFF."),
            [("14", "cpeum", "CPEUM.pdf", "adyacente_derecha", False),
             ("42", "cff", "CODIGO FISCAL.pdf", "adyacente_derecha", False)],
        )
        self.assertEqual([r[0] for r in _leyes("El artículo 14 de la CPEUM; el plazo es de 16 días.")],
                         ["14"])

    def test_raw_y_grupo(self) -> None:
        refs = R.extraer_articulos("Los artículos 14, fracción II, y 16 CPEUM.", CATALOGO)
        self.assertEqual(
            [(r["article"], r["fraction"], r["raw"], r["group_raw"]) for r in refs],
            [
                ("14", "II", "artículos 14, fracción II", "artículos 14, fracción II, y 16"),
                ("16", "", "artículos 14, fracción II, y 16", "artículos 14, fracción II, y 16"),
            ],
        )


class OracionTests(unittest.TestCase):
    def test_abreviaturas_no_cortan_la_oracion(self) -> None:
        texto = "Art. 107 Fr. V CPEUM"
        self.assertEqual(_leyes(texto), [("107", "cpeum", "CPEUM.pdf", "adyacente_derecha", False)])
        self.assertEqual(
            _leyes("El artículo 1o. Constitucional se invoca."),
            [("1o", "constitucional", "CPEUM.pdf", "adyacente_derecha", False)],
        )

    def test_fin_de_oracion_corta_la_ventana(self) -> None:
        self.assertEqual(
            _leyes("Se invoca el artículo 42. El CFF regula otra cosa."),
            [("42", "desconocido", None, None, False)],
        )

    def test_lista_y_tabla_cortan_la_ventana(self) -> None:
        self.assertEqual(
            _leyes("- Art. 5 regla general\n- La LIVA se cita aparte"),
            [("5", "desconocido", None, None, False)],
        )
        self.assertEqual(
            _leyes("| Art. 5 | regla | CFF |"),
            [("5", "desconocido", None, None, False)],
        )

    def test_salto_de_linea_simple_no_corta_la_denominacion(self) -> None:
        self.assertEqual(
            _leyes("el artículo 19 de la Constitución Política de los Estados\nUnidos Mexicanos"),
            [("19", "constitución política de los estados unidos", "CPEUM.pdf",
              "adyacente_derecha", False)],
        )


class CatalogoTests(unittest.TestCase):
    def test_palabra_completa_y_mayusculas(self) -> None:
        self.assertEqual(R.primera_mencion("perito Olivares", CATALOGO), (None, None))
        self.assertEqual(R.primera_mencion("la liva", CATALOGO), ("liva", "Ley del IVA.pdf"))
        # Las claves contextuales nunca se buscan como mención libre.
        self.assertEqual(R.primera_mencion("la constitución", CATALOGO), (None, None))
        self.assertEqual(R.primera_mencion("orden constitucional", CATALOGO), (None, None))

    def test_alias_respeta_mayusculas_y_conserva_su_fuente(self) -> None:
        menciones = R.menciones_explicitas("ejecución penal y Ejecución Penal", CATALOGO)
        self.assertEqual([(m.clave, m.fuente, m.alias) for m in menciones],
                         [("Ley Nacional de Ejecución Penal", None, True)])

    def test_menciones_contenidas_se_descartan(self) -> None:
        menciones = R.menciones_explicitas(
            "el Reglamento de la Ley Federal de Protección al Consumidor y la Ley Federal de "
            "Delincuencia Organizada", CATALOGO,
        )
        self.assertEqual([m.clave for m in menciones], [
            "reglamento de la ley federal de protección al consumidor",
            "ley federal de delincuencia organizada",
        ])

    def test_tipo_fuente(self) -> None:
        casos = {
            "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf": "constitucion",
            "Constitución Politica del Estado de Jalisco 2026.pdf": "constitucion",
            "CodigoNacionalProcedPenales.pdf": "codigo",
            "LeydeJusticiaAdministrativadelEstadodeJalisco 2026.pdf": "ley",
            "ley_del_registro_civil_del_estado_de_jalisco 2026.pdf": "ley",
            "REGLAMENTO DE LA LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR.pdf": "reglamento",
            "RegMovilidadTransporteSeguridadVialGuadalajara 2026.pdf": "reglamento",
            "Convencion Americana sobre Derechos Humanos.pdf": "tratado",
            "Pacto Internacional de Derechos Civiles y Políticos.pdf": "tratado",
            "RESOLUCION MISCELANEA FISCAL 2026.pdf": "otro",
            None: "otro",
        }
        for nombre, esperado in casos.items():
            with self.subTest(nombre=nombre):
                self.assertEqual(R.tipo_fuente(nombre), esperado)


class ResolucionTests(unittest.TestCase):
    def test_genericos_adyacentes(self) -> None:
        self.assertEqual(
            _leyes("La Ley de Amparo rige. El artículo 5 de la citada ley dispone."),
            [("5", "ley de amparo", "LEY DE AMPARO.pdf", "antecedente", True)],
        )
        self.assertEqual(
            _leyes("La Ley de Amparo rige. El artículo 5 de la ley de la materia dispone."),
            [("5", "ley de amparo", "LEY DE AMPARO.pdf", "antecedente", True)],
        )
        self.assertEqual(
            _leyes("La Ley de Amparo rige. Dicha ley, en su artículo 5, dispone."),
            [("5", "ley de amparo", "LEY DE AMPARO.pdf", "antecedente", True)],
        )
        # "ordenamiento" acepta cualquier tipo, pero exige uno solo.
        self.assertEqual(
            _leyes("El CFF rige. El artículo 5 del ordenamiento citado dispone."),
            [("5", "cff", "CODIGO FISCAL.pdf", "antecedente", True)],
        )
        # Un genérico que no es adyacente al artículo no es remisión.
        self.assertEqual(
            _leyes("La Ley de Amparo rige.\n\nEl artículo 5 regula la ley aplicable."),
            [("5", "ley de amparo", "LEY DE AMPARO.pdf", "contexto_previo_otro_parrafo", True)],
        )

    def test_genericos_con_modificador_son_ordenamientos_concretos(self) -> None:
        for texto, nombre in (
            ("La Ley de Amparo rige. El artículo 5 de la ley fiscal dispone.", "'ley fiscal'"),
            ("La Ley de Amparo rige. El artículo 5 del Código de Comercio dispone.",
             "'Código de Comercio'"),
            ("La Ley de Amparo rige. El artículo 5 de la ley del estado dispone.",
             "'ley del estado'"),
        ):
            with self.subTest(texto=texto):
                (ref,) = R.extraer_articulos(texto, CATALOGO)
                self.assertIsNone(ref["source_file"])
                self.assertIn(nombre, ref["law_unidentified_reason"])

    def test_cadena_de_articulos_comparte_la_ley(self) -> None:
        for texto in (
            "El artículo 14 y el artículo 16 de la CPEUM se invocan.",
            "El artículo 14, en relación con el artículo 16, ambos de la CPEUM.",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(
                    [(a, fuente, metodo) for a, _, fuente, metodo, _ in _leyes(texto)],
                    [("14", "CPEUM.pdf", "adyacente_derecha"),
                     ("16", "CPEUM.pdf", "adyacente_derecha")],
                )
        # Sin "ambos", "así como" no comparte la ley (ronda 2: solo coordinación pura).
        self.assertEqual(
            _leyes("El artículo 14, así como el artículo 16 de la CPEUM, se invocan.")[0],
            ("14", "desconocido", None, None, False),
        )
        # Otra palabra entre ambos rompe la cadena: el 14 no toma la ley del 16.
        self.assertEqual(
            _leyes("El artículo 14 regula la audiencia y el artículo 16 de la CPEUM la legalidad.")[0],
            ("14", "desconocido", None, None, False),
        )

    def test_encabezado_inequivoco(self) -> None:
        def encabezado(texto: str) -> bool:
            (mencion,) = [m for m in R.menciones_explicitas(texto, CATALOGO) if not m.alias][:1]
            return R._es_encabezado(texto, mencion)

        self.assertTrue(encabezado("## Constitución Política de los Estados Unidos Mexicanos"))
        self.assertTrue(encabezado("**CÓDIGO FISCAL DE LA FEDERACIÓN**"))
        self.assertTrue(encabezado("II. Ley de Amparo (LA)"))
        self.assertFalse(encabezado("### A. Orden constitucional mexicano (CPEUM)"))
        self.assertFalse(encabezado("La Ley de Amparo regula el juicio."))

    def test_entidad_ajena_y_ordinal_adjetivo(self) -> None:
        mapa_jalisco = dict(MAPA, **{"ley de carrera judicial": "LEY DE CARRERA JUDICIAL.pdf"})
        catalogo = R.construir_catalogo(mapa_jalisco, ALIAS)
        (ref,) = R.extraer_articulos(
            "El artículo 5 de la Ley de Carrera Judicial del Estado de Jalisco.", catalogo)
        self.assertIsNone(ref["source_file"])
        self.assertIn("fuera del catálogo", ref["law_unidentified_reason"])
        (ref,) = R.extraer_articulos(
            "El artículo 5 de la Ley de Carrera Judicial del Poder Judicial de la Federación.",
            catalogo)
        self.assertEqual(ref["source_file"], "LEY DE CARRERA JUDICIAL.pdf")
        # "2o. párrafo" y "10 de junio" no son artículos de una continuación.
        self.assertEqual(
            [a for a, *_ in _leyes("El artículo 19 de la CPEUM, 2o. párrafo, se invoca.")],
            ["19"])
        self.assertEqual(
            [a for a, *_ in _leyes("El artículo 1o. de la CPEUM, 10 de junio de 2011, rige.")],
            ["1o"])

    def test_sticky_no_va_hacia_adelante(self) -> None:
        self.assertEqual(
            _leyes("Art. 5 establece la regla general.\n\nEl CFF se aplica."),
            [("5", "desconocido", None, None, False)],
        )

    def test_constitucional_solo_junto_al_precepto(self) -> None:
        self.assertEqual(
            _leyes("El artículo 16, párrafo primero, constitucional exige fundamentación."),
            [("16", "constitucional", "CPEUM.pdf", "adyacente_derecha", False)],
        )
        self.assertEqual(
            _leyes("El artículo 5 regula el control constitucional."),
            [("5", "desconocido", None, None, False)],
        )

    def test_sigla_fuera_del_catalogo_no_toma_la_ley_anterior(self) -> None:
        # Falso verde (11-oct-2026, protocolo de seguridad social): "de la LISSSTE" no es una
        # sigla del catálogo y el artículo tomaba, por contexto previo, la ley nombrada antes.
        for texto, articulos in (
            ("Rige el artículo 5 del CFF. El artículo 248 de la LISSSTE dispone.", ["248"]),
            ("Rige el artículo 5 del CFF. El artículo 248, fracción II, de la LISSSTE dispone.",
             ["248"]),
            ("Rige el artículo 5 del CFF. El artículo 248 LISSSTE dispone.", ["248"]),
            ("Rige el artículo 5 del CFF. Los artículos 248 y 249 de la LISSSTE disponen.",
             ["248", "249"]),
            ("Rige el artículo 5 del CFF. La LISSSTE, en su artículo 248, dispone.", ["248"]),
        ):
            with self.subTest(texto=texto):
                refs = R.extraer_articulos(texto, CATALOGO)[1:]
                self.assertEqual([r["article"] for r in refs], articulos)
                for ref in refs:
                    self.assertIsNone(ref["source_file"])
                    self.assertIn("'LISSSTE'", ref["law_unidentified_reason"])
                    self.assertIn("fuera del catálogo", ref["law_unidentified_reason"])

    def test_sigla_definida_en_el_texto_identifica_su_ley(self) -> None:
        for texto in (
            "La Ley de Amparo (LAMP) rige. El artículo 5 de la LAMP dispone.",
            "La Ley de Amparo (en adelante, LAMP) rige. El artículo 5 de la LAMP dispone.",
            "La Ley de Amparo (en lo sucesivo «LAMP») rige.\n\nEl artículo 5 de la LAMP dispone.",
        ):
            with self.subTest(texto=texto):
                self.assertEqual(
                    _leyes(texto),
                    [("5", "ley de amparo", "LEY DE AMPARO.pdf", "adyacente_derecha", False)],
                )
        # Definida después de la cita no cuenta: la sigla todavía no tiene significado.
        (ref,) = R.extraer_articulos(
            "Rige el CFF. El artículo 5 de la LAMP dispone. La Ley de Amparo (LAMP) rige.",
            CATALOGO)
        self.assertIsNone(ref["source_file"])

    def test_mayusculas_que_no_son_sigla_de_ley(self) -> None:
        # Sin vínculo con el artículo, una sigla (de una autoridad, por ejemplo) no estorba.
        self.assertEqual(
            _leyes("El CFF rige al SAT. Su artículo 42 dispone."),
            [("42", "cff", "CODIGO FISCAL.pdf", "contexto_previo", True)],
        )
        self.assertEqual(
            _leyes("El IMSS, en el artículo 42 del CFF, dispone."),
            [("42", "cff", "CODIGO FISCAL.pdf", "adyacente_derecha", False)],
        )
        # Numerales romanos, y un texto todo en mayúsculas (como un rubro), quedan como antes.
        self.assertEqual(
            _leyes("Rige el artículo 5 del CFF. El artículo 107, fracción XXIX, dispone.")[1],
            ("107", "cff", "CODIGO FISCAL.pdf", "contexto_previo", True),
        )
        self.assertEqual(
            _leyes("EL CFF RIGE. EL ARTÍCULO 42 DISPONE."),
            [("42", "cff", "CODIGO FISCAL.pdf", "contexto_previo", True)],
        )


if __name__ == "__main__":
    unittest.main()
