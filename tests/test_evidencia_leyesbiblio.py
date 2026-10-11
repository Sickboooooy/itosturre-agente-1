"""Pruebas de la limpieza de LeyesBiblio y de la ubicación de artículos.

Fixtures reales: texto de páginas concretas de los PDF oficiales
(``tests/fixtures/evidencia/leyesbiblio_*.json``, procedencia en ``manifiesto.json``).
Variantes: páginas sintéticas rotuladas ("LEY SINTÉTICA DE PRUEBA", artículos 9999 y
fechas de 1800) o alteraciones explícitas de una página real (quitar una línea); nunca
un dato normativo inventado con apariencia real. Sin red ni dependencias externas.
"""
from __future__ import annotations

import json
import unittest
from dataclasses import replace
from pathlib import Path

from itosturre.evidencia import validar_registro
from itosturre.evidencia.fuentes import url_leyesbiblio
from itosturre.evidencia.huellas import sha256_texto
from itosturre.evidencia.leyesbiblio import (
    CLASES_MOBILIARIO,
    LineaQuitada,
    encabezado_articulo,
    es_frontera_transitorios,
    es_subsecuencia,
    identificador_canonico,
    limpiar_documento,
    limpiar_pagina,
    registro_evidencia,
    ubicar_articulo,
    verificar_documento,
    verificar_pagina,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "evidencia"
LEYES = ("CNPP", "CPF", "CPEUM", "CFF", "LAmp")
ESPERADO = {
    # ley: (título del encabezado, Última Reforma DOF, páginas del PDF)
    "CNPP": ("CÓDIGO NACIONAL DE PROCEDIMIENTOS PENALES", "2025-11-28", 168),
    "CPF": ("CÓDIGO PENAL FEDERAL", "2026-03-13", 353),
    "CPEUM": ("CONSTITUCIÓN POLÍTICA DE LOS ESTADOS UNIDOS MEXICANOS", "2026-06-02", 414),
    "CFF": ("CÓDIGO FISCAL DE LA FEDERACIÓN", "2026-04-09", 377),
    "LAmp": (
        "LEY DE AMPARO, REGLAMENTARIA DE LOS ARTÍCULOS 103 Y 107 DE LA CONSTITUCIÓN "
        "POLÍTICA DE LOS ESTADOS UNIDOS MEXICANOS",
        "2025-10-16",
        119,
    ),
}


def cargar(ley: str) -> dict:
    return json.loads((FIXTURES / f"leyesbiblio_{ley}.json").read_text(encoding="utf-8"))


def documento(ley: str, paginas: tuple[int, ...] | None = None):
    datos = cargar(ley)
    seleccion = [p for p in datos["paginas"] if paginas is None or p["numero"] in paginas]
    return limpiar_documento(
        [p["texto"] for p in seleccion],
        numeros=[p["numero"] for p in seleccion],
        total_paginas=datos["total_paginas_pdf"],
    )


def pagina_sintetica(numero: int, total: int, reforma: str, *, titulo: str = "LEY SINTÉTICA DE PRUEBA") -> str:
    """Página con el mobiliario de LeyesBiblio y cuerpo sintético (no es norma alguna)."""
    return "\n".join(
        [
            " ",
            f"{titulo} ",
            " ",
            "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN ",
            "Secretaría General ",
            "Secretaría de Servicios Parlamentarios ",
            f"Última Reforma DOF {reforma} ",
            " ",
            " ",
            f"{numero} de {total} ",
            "Texto sintético de prueba sin valor normativo. ",
            "",
        ]
    )


class LimpiezaFixturesTests(unittest.TestCase):
    def test_invariantes_en_todas_las_paginas(self) -> None:
        for ley in LEYES:
            doc = documento(ley)
            with self.subTest(ley=ley):
                self.assertEqual(verificar_documento(doc), [])
                for pagina in doc.paginas:
                    self.assertTrue(pagina.encabezado_reconocido)
                    # Ninguna línea alterada: el limpio es subsecuencia del original y
                    # conservadas + quitadas cubren exactamente la página.
                    self.assertTrue(es_subsecuencia(pagina.lineas_limpias, pagina.lineas))
                    self.assertEqual(
                        sorted(list(pagina.conservadas) + [q.indice for q in pagina.quitadas]),
                        list(range(len(pagina.lineas))),
                    )
                    self.assertEqual(pagina.original, "\n".join(pagina.lineas))
                    for quitada in pagina.quitadas:
                        self.assertIn(quitada.clase, CLASES_MOBILIARIO)
                        self.assertEqual(pagina.lineas[quitada.indice], quitada.texto)

    def test_datos_comunes_del_encabezado(self) -> None:
        for ley, (titulo, reforma, total) in ESPERADO.items():
            doc = documento(ley)
            with self.subTest(ley=ley):
                self.assertEqual(doc.titulo, titulo)
                self.assertEqual(doc.ultima_reforma_dof, reforma)
                self.assertEqual(doc.total_paginas, total)
                self.assertEqual(doc.advertencias, ())
                for pagina in doc.paginas:
                    self.assertEqual(pagina.paginacion, (pagina.numero, total))

    def test_clases_del_mobiliario_quitado(self) -> None:
        pagina = documento("CNPP").paginas[0]
        self.assertEqual(
            [q.clase for q in pagina.quitadas],
            [
                "blanco_encabezado",
                "titulo",
                "blanco_encabezado",
                "camara",
                "secretaria_general",
                "secretaria_servicios_parlamentarios",
                "ultima_reforma",
                "blanco_encabezado",
                "blanco_encabezado",
                "paginacion",
            ],
        )
        # LAmp: el título del encabezado ocupa dos líneas.
        lamp = documento("LAmp").paginas[0]
        self.assertEqual([q.clase for q in lamp.quitadas].count("titulo"), 2)

    def test_primera_pagina_conserva_el_cuerpo(self) -> None:
        pagina = documento("CNPP").paginas[0]
        limpias = [linea.strip() for linea in pagina.lineas_limpias]
        # El título vuelve a aparecer en el cuerpo de la primera página: se conserva.
        self.assertEqual(limpias[0], "CÓDIGO NACIONAL DE PROCEDIMIENTOS PENALES")
        self.assertIn("Última reforma publicada DOF 28-11-2025", limpias)
        self.assertNotIn("Secretaría General", limpias)
        self.assertNotIn("1 de 168", limpias)

    def test_texto_extraido_y_limpio_se_conservan_ambos(self) -> None:
        doc = documento("CPF")
        self.assertEqual(doc.texto_extraido, "\f".join(cargar("CPF")["paginas"][i]["texto"] for i in range(3)))
        self.assertNotEqual(sha256_texto(doc.texto_extraido), sha256_texto(doc.texto))

        def lineas(texto: str) -> list[str]:
            return [linea for pagina in texto.split("\f") for linea in pagina.split("\n")]

        self.assertTrue(es_subsecuencia(lineas(doc.texto), lineas(doc.texto_extraido)))
        self.assertLess(len(lineas(doc.texto)), len(lineas(doc.texto_extraido)))


class LimpiezaVariantesTests(unittest.TestCase):
    def test_encabezado_incompleto_se_conserva_integro(self) -> None:
        # Alteración explícita de una página real: se quita la línea "Secretaría General".
        original = cargar("CNPP")["paginas"][1]["texto"]
        alterada = original.replace("Secretaría General \n", "", 1)
        self.assertNotEqual(original, alterada)
        pagina = limpiar_pagina(alterada, 52)
        self.assertFalse(pagina.encabezado_reconocido)
        self.assertEqual(pagina.quitadas, ())
        self.assertEqual(pagina.texto, alterada)
        self.assertEqual(verificar_pagina(pagina), [])
        doc = limpiar_documento([alterada], numeros=[52])
        self.assertEqual(doc.advertencias[0]["codigo"], "encabezado_no_reconocido")
        self.assertIsNone(doc.titulo)

    def test_ultima_reforma_contradictoria_no_elige(self) -> None:
        doc = limpiar_documento(
            [pagina_sintetica(1, 2, "01-01-1800"), pagina_sintetica(2, 2, "02-01-1800")]
        )
        self.assertIsNone(doc.ultima_reforma_dof)
        aviso = next(a for a in doc.advertencias if a["codigo"] == "contradiccion_ultima_reforma")
        self.assertEqual(aviso["valores"], {"01-01-1800": [1], "02-01-1800": [2]})

    def test_ultima_reforma_constante(self) -> None:
        doc = limpiar_documento([pagina_sintetica(1, 2, "01-01-1800"), pagina_sintetica(2, 2, "01-01-1800")])
        self.assertEqual(doc.ultima_reforma_dof, "1800-01-01")
        self.assertEqual(doc.advertencias, ())

    def test_paginacion_que_no_coincide_con_la_pagina(self) -> None:
        doc = limpiar_documento([pagina_sintetica(5, 9, "01-01-1800")], numeros=[2])
        self.assertEqual(doc.advertencias[0]["codigo"], "paginacion_inconsistente")

    def test_total_de_paginas_no_constante(self) -> None:
        doc = limpiar_documento([pagina_sintetica(1, 9, "01-01-1800"), pagina_sintetica(2, 8, "01-01-1800")])
        self.assertIsNone(doc.total_paginas)
        self.assertIn("total_paginas_inconsistente", [a["codigo"] for a in doc.advertencias])

    def test_total_distinto_del_pdf(self) -> None:
        doc = limpiar_documento([pagina_sintetica(1, 9, "01-01-1800")], total_paginas=10)
        self.assertIsNone(doc.total_paginas)
        self.assertIn("total_paginas_inconsistente", [a["codigo"] for a in doc.advertencias])

    def test_titulo_que_cambia_entre_paginas_sin_mayoria_no_limpia_ninguna(self) -> None:
        paginas = [
            pagina_sintetica(1, 2, "01-01-1800"),
            pagina_sintetica(2, 2, "01-01-1800", titulo="OTRA LEY SINTÉTICA DE PRUEBA"),
        ]
        doc = limpiar_documento(paginas)
        self.assertIsNone(doc.titulo)
        aviso = next(a for a in doc.advertencias if a["codigo"] == "titulo_inconsistente")
        self.assertEqual(aviso["paginas_sin_limpiar"], [1, 2])
        for pagina, texto in zip(doc.paginas, paginas):
            self.assertEqual(pagina.quitadas, ())
            self.assertEqual(pagina.texto, texto)

    def test_titulo_minoritario_se_conserva_integro(self) -> None:
        paginas = [
            pagina_sintetica(1, 3, "01-01-1800"),
            pagina_sintetica(2, 3, "01-01-1800"),
            pagina_sintetica(3, 3, "01-01-1800", titulo="OTRA LEY SINTÉTICA DE PRUEBA"),
        ]
        doc = limpiar_documento(paginas)
        self.assertEqual(doc.titulo, "LEY SINTÉTICA DE PRUEBA")
        self.assertTrue(doc.paginas[0].quitadas and doc.paginas[1].quitadas)
        self.assertEqual(doc.paginas[2].quitadas, ())
        self.assertEqual(doc.paginas[2].texto, paginas[2])
        self.assertIn("mayoría", doc.paginas[2].motivo)
        aviso = next(a for a in doc.advertencias if a["codigo"] == "titulo_inconsistente")
        self.assertEqual(aviso["paginas_sin_limpiar"], [3])
        self.assertEqual(verificar_documento(doc), [])

    def test_titulo_esperado_por_quien_llama(self) -> None:
        datos = cargar("CNPP")
        textos = [p["texto"] for p in datos["paginas"]]
        numeros = [p["numero"] for p in datos["paginas"]]
        bien = limpiar_documento(textos, numeros=numeros, titulo="Código Nacional de Procedimientos Penales")
        self.assertTrue(all(p.encabezado_reconocido for p in bien.paginas))
        mal = limpiar_documento(textos, numeros=numeros, titulo="LEY SINTÉTICA DE PRUEBA")
        self.assertTrue(all(p.quitadas == () for p in mal.paginas))
        self.assertIsNone(mal.titulo)
        self.assertIn("titulo_inconsistente", [a["codigo"] for a in mal.advertencias])

    def test_contenido_normativo_no_sale_como_titulo(self) -> None:
        # Defecto reproducido por la revisión externa: un artículo pegado sobre el
        # encabezado se quitaba como "titulo" sin advertencia. Variantes sintéticas.
        for primera in (
            "Artículo 9999. Queda prohibido algo sintético.",
            "ARTÍCULO 9999. QUEDA PROHIBIDO ALGO SINTÉTICO.",
            "CAPÍTULO SINTÉTICO",
        ):
            with self.subTest(primera=primera):
                texto = "\n".join(
                    [
                        primera,
                        "LEY SINTÉTICA",
                        "",
                        "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN",
                        "Secretaría General",
                        "Secretaría de Servicios Parlamentarios",
                        "Última Reforma DOF 01-01-1800",
                        "",
                        "1 de 1",
                        "Texto.",
                    ]
                )
                doc = limpiar_documento([texto])
                pagina = doc.paginas[0]
                self.assertFalse(pagina.encabezado_reconocido)
                self.assertEqual(pagina.quitadas, ())
                self.assertEqual(pagina.texto, texto)
                self.assertIn("título no plausible", pagina.motivo)
                aviso = next(a for a in doc.advertencias if a["codigo"] == "encabezado_no_reconocido")
                self.assertIn("título no plausible", aviso["motivos"]["1"])
                self.assertEqual(verificar_documento(doc), [])

    def test_el_verificador_rechaza_texto_normativo_quitado_como_titulo(self) -> None:
        pagina = documento("CNPP").paginas[0]
        # Mutación: la línea del encabezado de artículo 1o. (cuerpo) marcada como título.
        indice = next(i for i in pagina.conservadas if pagina.lineas[i].startswith("Artículo 1o."))
        mutada = replace(
            pagina,
            quitadas=pagina.quitadas + (LineaQuitada(indice, pagina.lineas[indice], "titulo"),),
            conservadas=tuple(i for i in pagina.conservadas if i != indice),
        )
        self.assertTrue(any("no es plausible" in p for p in verificar_pagina(mutada)))

    def test_numeros_de_pagina_invalidos(self) -> None:
        paginas = [pagina_sintetica(1, 2, "01-01-1800"), pagina_sintetica(2, 2, "01-01-1800")]
        with self.assertRaises(ValueError):
            limpiar_documento(paginas, numeros=[2, 1])
        with self.assertRaises(ValueError):
            limpiar_documento(paginas, numeros=[1])

    def test_el_verificador_detecta_limpiezas_indebidas(self) -> None:
        # Pruebas de mutación: el verificador debe rechazar limpiezas que la función
        # nunca produce (quitar una línea del cuerpo, clasificar mal, alterar el texto).
        pagina = documento("CNPP").paginas[0]
        cuerpo = pagina.conservadas[5]
        fuera_de_bloque = replace(
            pagina,
            conservadas=tuple(i for i in pagina.conservadas if i != cuerpo),
            quitadas=pagina.quitadas + (LineaQuitada(cuerpo, pagina.lineas[cuerpo], "titulo"),),
        )
        self.assertTrue(any("posterior al cuerpo" in p for p in verificar_pagina(fuera_de_bloque)))
        mal_clasificada = replace(
            pagina,
            quitadas=(LineaQuitada(3, pagina.lineas[3], "paginacion"),) + pagina.quitadas[1:],
            conservadas=pagina.conservadas + (0,),
        )
        problemas = verificar_pagina(mal_clasificada)
        self.assertTrue(any("no es 'N de M'" in p for p in problemas))
        self.assertTrue(any("orden estricto" in p for p in problemas))
        alterada = replace(pagina, quitadas=(LineaQuitada(0, "otra cosa", "blanco_encabezado"),) + pagina.quitadas[1:])
        self.assertTrue(any("no es la original" in p for p in verificar_pagina(alterada)))


class UbicacionArticulosTests(unittest.TestCase):
    def test_fecha_ultima_reforma_de_la_linea_del_encabezado(self) -> None:
        # Piloto PEN-01 (D3): el cotejo del encabezado lee la fecha de la línea literal.
        from itosturre.evidencia.leyesbiblio import fecha_ultima_reforma

        self.assertEqual(fecha_ultima_reforma("Última Reforma DOF 28-11-2025 "), "2025-11-28")
        self.assertEqual(fecha_ultima_reforma("Últimas Reformas DOF 02-06-2026"), "2026-06-02")
        self.assertEqual(documento("CNPP").ultima_reforma_dof, fecha_ultima_reforma("Última Reforma DOF 28-11-2025"))
        for linea in ("Última Reforma DOF 31-02-1800", "Reforma DOF 28-11-2025", "CÓDIGO NACIONAL", None):
            with self.subTest(linea=linea):
                self.assertIsNone(fecha_ultima_reforma(linea))

    def test_cnpp_articulo_167_en_pagina_no_contigua_es_indeterminado(self) -> None:
        # El fixture trae las páginas 1, 52, 54, 139 y 155: entre la 1 y la 52 faltan
        # páginas, así que no se acredita que la 52 esté antes de la frontera real.
        ubicacion = ubicar_articulo(documento("CNPP"), "167")
        self.assertEqual(len(ubicacion.coincidencias), 1)  # la remisión de la p. 155 no cuenta
        coincidencia = ubicacion.coincidencias[0]
        self.assertEqual((coincidencia.pagina, coincidencia.indice, coincidencia.zona), (52, 17, "indeterminada"))
        self.assertTrue(coincidencia.linea.startswith("Artículo 167. Causas de procedencia"))
        self.assertIsNone(ubicacion.unica)
        self.assertFalse(ubicacion.ambigua)
        self.assertEqual([a["codigo"] for a in ubicacion.advertencias], ["zona_indeterminada"])
        self.assertEqual(ubicacion.frontera_transitorios, (139, 36))

    def test_pagina_de_decreto_suelta_no_acredita_cuerpo(self) -> None:
        # Defecto reproducido: CNPP p. 155 sola daba como "única en el cuerpo" el
        # "Artículo Primero.-" de un decreto de reforma. Página real del fixture.
        ubicacion = ubicar_articulo(documento("CNPP", paginas=(155,)), "Primero")
        self.assertEqual(
            [(c.pagina, c.indice, c.zona) for c in ubicacion.coincidencias], [(155, 21, "indeterminada")]
        )
        self.assertTrue(ubicacion.coincidencias[0].linea.startswith("Artículo Primero.- Se reforman el artículo 167"))
        self.assertIsNone(ubicacion.unica)
        self.assertEqual(ubicacion.cuerpo, ())
        # La línea "Transitorios" de ese decreto (l. 29) va después de la coincidencia.
        self.assertEqual(ubicacion.frontera_transitorios, (155, 29))
        self.assertEqual([a["codigo"] for a in ubicacion.advertencias], ["zona_indeterminada"])

    def test_sin_coincidencia_exacta_advierte_variantes_sin_elegir(self) -> None:
        ubicacion = ubicar_articulo(documento("CNPP"), "1")
        self.assertEqual(ubicacion.coincidencias, ())
        self.assertIsNone(ubicacion.unica)
        self.assertEqual(
            [(c.pagina, c.indice, c.identificador) for c in ubicacion.variantes_cercanas], [(1, 44, "1o")]
        )
        codigos = [a["codigo"] for a in ubicacion.advertencias]
        self.assertIn("sin_coincidencia", codigos)
        self.assertIn("variantes_cercanas", codigos)
        aviso = next(a for a in ubicacion.advertencias if a["codigo"] == "sin_coincidencia")
        self.assertIn("no acredita que el artículo no exista", aviso["mensaje"])

        cuarto = ubicar_articulo(documento("CFF"), "4")
        self.assertEqual([c.identificador for c in cuarto.variantes_cercanas], ["4o", "4o.-A"])

        nada = ubicar_articulo(documento("CNPP"), "9999")
        self.assertEqual(nada.variantes_cercanas, ())
        self.assertIn("sin_coincidencia", [a["codigo"] for a in nada.advertencias])

    def test_cnpp_1o_unico_y_1_no_equivale(self) -> None:
        doc = documento("CNPP")
        ubicacion = ubicar_articulo(doc, "1o")
        self.assertEqual((ubicacion.unica.pagina, ubicacion.unica.indice), (1, 44))
        self.assertEqual(ubicar_articulo(doc, "Artículo 1o.").unica, ubicacion.unica)
        self.assertEqual(ubicar_articulo(doc, "1").coincidencias, ())

    def test_cnpp_primero_solo_en_transitorios(self) -> None:
        ubicacion = ubicar_articulo(documento("CNPP"), "Primero")
        self.assertEqual(ubicacion.cuerpo, ())
        self.assertIsNone(ubicacion.unica)
        self.assertEqual(
            [(c.pagina, c.indice) for c in ubicacion.transitorios], [(139, 38), (155, 21)]
        )
        self.assertEqual([a["codigo"] for a in ubicacion.advertencias], ["solo_en_transitorios"])

    def test_cpf_1o_cuerpo_y_decreto_de_reforma(self) -> None:
        ubicacion = ubicar_articulo(documento("CPF"), "1o")
        self.assertEqual((ubicacion.unica.pagina, ubicacion.unica.indice), (1, 44))
        self.assertEqual([(c.pagina, c.indice) for c in ubicacion.transitorios], [(151, 14)])
        self.assertEqual(ubicacion.transitorios[0].identificador, "1°")
        self.assertEqual(ubicacion.frontera_transitorios, (147, 38))
        self.assertEqual(ubicacion.advertencias, ())

    def test_cpf_sin_la_frontera_el_encabezado_es_ambiguo(self) -> None:
        # Sin la página 147 (TRANSITORIOS), el decreto de la p. 151 podría ser cuerpo.
        ubicacion = ubicar_articulo(documento("CPF", paginas=(1, 151)), "1o")
        self.assertTrue(ubicacion.ambigua)
        self.assertIsNone(ubicacion.unica)
        self.assertEqual([(c.pagina, c.indice) for c in ubicacion.cuerpo], [(1, 44)])
        self.assertEqual([(c.pagina, c.indice) for c in ubicacion.indeterminadas], [(151, 14)])
        self.assertEqual(
            [a["codigo"] for a in ubicacion.advertencias],
            ["sin_frontera_transitorios", "zona_indeterminada", "articulo_ambiguo"],
        )

    def test_cff_4o_y_4o_a_no_se_confunden(self) -> None:
        doc = documento("CFF")  # páginas 2, 30 y 148: nada se acredita como cuerpo
        cuarto = ubicar_articulo(doc, "4o")
        self.assertEqual([(c.pagina, c.indice) for c in cuarto.coincidencias], [(2, 47)])
        for forma in ("4o-A", "4o.-A", "4o A"):
            with self.subTest(forma=forma):
                cuarto_a = ubicar_articulo(doc, forma)
                self.assertEqual([(c.pagina, c.indice) for c in cuarto_a.coincidencias], [(2, 61)])
                self.assertEqual(cuarto_a.coincidencias[0].identificador, "4o.-A")
                self.assertEqual(cuarto_a.coincidencias[0].zona, "indeterminada")
                self.assertIsNone(cuarto_a.unica)

    def test_encabezados_sinteticos(self) -> None:
        casos = {
            "Artículo 9999. Encabezado sintético": "9999",
            "Artículo 9999.- Encabezado sintético": "9999",
            "ARTÍCULO 9999 Bis.- Encabezado sintético": "9999 Bis",
            "Artículo 9999-B. Encabezado sintético": "9999-B",
            "Art. 9999-A.- Encabezado sintético": "9999-A",
            "ART. 9999.- Encabezado sintético": "9999",
            "Artículo Décimo Primero.- Encabezado sintético": "Décimo Primero",
            # No son encabezados: remisión partida en minúscula, remisión sin terminador.
            "artículo 9999. Remisión sintética": None,
            "Artículo 9999 de la Ley Sintética": None,
            "Artículo reformado DOF 01-01-1800": None,
        }
        for linea, esperado in casos.items():
            with self.subTest(linea=linea):
                self.assertEqual(encabezado_articulo(linea), esperado)

    def test_sufijo_latino_en_minuscula(self) -> None:
        # CPC de Jalisco (11-oct-2026): "Artículo 29 bis.-" no se reconocía como encabezado y el
        # cotejo del artículo daba NO LOCALIZADO aunque estaba en ambos textos.
        self.assertEqual(encabezado_articulo("Artículo 9999 bis.- Encabezado sintético"), "9999 bis")
        self.assertEqual(encabezado_articulo("Artículo 9999 ter. Encabezado sintético"), "9999 ter")
        self.assertIsNone(encabezado_articulo("Artículo 9999 bis de la Ley Sintética"))
        doc = limpiar_documento(
            ["Artículo 9999.- Texto sintético.\nArtículo 9999 bis.- Texto sintético.\nTRANSITORIOS\n"]
        )
        self.assertEqual(ubicar_articulo(doc, "9999 Bis").unica.indice, 1)

    def test_remision_partida_al_inicio_de_linea_no_es_encabezado(self) -> None:
        # Código Civil de Jalisco (11-oct-2026): "…se observará lo dispuesto en la parte final del /
        # Artículo 1595." duplicaba el encabezado del 1595 y su ubicación quedaba ambigua.
        doc = limpiar_documento(
            [
                "Artículo 9998.- Si la obligación sintética no tuviere plazo, se estará a la parte final del\n"
                "Artículo 9999.\n"
                "El que contraviene una obligación sintética pagará daños.\n"
                "Artículo 9999.- Texto sintético del artículo verdadero.\n"
                "TRANSITORIOS\n"
            ]
        )
        ubicacion = ubicar_articulo(doc, "9999")
        self.assertIsNotNone(ubicacion.unica)
        self.assertEqual(ubicacion.unica.indice, 3)

    def test_encabezados_con_subnumero(self) -> None:
        # Subnúmero pegado con guion, como "ARTÍCULO 58-1.-" de la LFPCA: misma regla que
        # ``itosturre.audit.referencias`` (designación si M < N; con M ≥ N es un rango).
        casos = {
            "ARTÍCULO 9999-1.- Encabezado sintético": "9999-1",
            "Artículo 9999-12. Encabezado sintético": "9999-12",
            "ARTÍCULO 9999-2 Bis.- Encabezado sintético": "9999-2 Bis",
            "Artículo 14-16. Rango sintético": None,
        }
        for linea, esperado in casos.items():
            with self.subTest(linea=linea):
                self.assertEqual(encabezado_articulo(linea), esperado)

    def test_subnumero_no_se_confunde_con_otro_articulo(self) -> None:
        doc = limpiar_documento(
            [
                "ARTÍCULO 9998.- Texto sintético.\n"
                "ARTÍCULO 9998-1.- Texto sintético.\n"
                "ARTÍCULO 9998-2.- Texto sintético.\n"
                "ARTÍCULO 99982.- Texto sintético.\n"
                "TRANSITORIOS\n"
            ]
        )
        for buscado, indice in (("9998", 0), ("9998-1", 1), ("9998-2", 2), ("9998 - 2", 2), ("99982", 3)):
            with self.subTest(buscado=buscado):
                ubicacion = ubicar_articulo(doc, buscado)
                self.assertIsNotNone(ubicacion.unica)
                self.assertEqual(ubicacion.unica.indice, indice)
        sin_exacto = ubicar_articulo(doc, "9998-3")
        self.assertIsNone(sin_exacto.unica)
        self.assertEqual(
            sorted(c.identificador for c in sin_exacto.variantes_cercanas), ["9998", "9998-1", "9998-2"]
        )

    def test_identificador_canonico(self) -> None:
        self.assertEqual(identificador_canonico("4o.-A"), identificador_canonico("4o-A"))
        self.assertEqual(identificador_canonico("1°"), "1o")
        self.assertEqual(identificador_canonico("Décimo Primero"), identificador_canonico("DECIMOPRIMERO"))
        self.assertNotEqual(identificador_canonico("1"), identificador_canonico("1o"))
        self.assertNotEqual(identificador_canonico("58-2"), identificador_canonico("582"))
        self.assertEqual(identificador_canonico("58-2"), identificador_canonico("58 - 2"))
        with self.assertRaises(ValueError):
            ubicar_articulo(documento("LAmp"), "  ")

    def test_frontera_de_transitorios(self) -> None:
        self.assertTrue(es_frontera_transitorios("ARTICULOS TRANSITORIOS: "))
        self.assertTrue(es_frontera_transitorios("TRANSITORIOS "))
        self.assertTrue(es_frontera_transitorios("ARTÍCULOS TRANSITORIOS DE DECRETOS DE REFORMA"))
        self.assertFalse(es_frontera_transitorios("ARTICULO TRANSITORIO.- Texto sintético de prueba"))


class RegistroLeyTests(unittest.TestCase):
    def test_registro_de_evidencia_de_ley(self) -> None:
        manifiesto = json.loads((FIXTURES / "manifiesto.json").read_text(encoding="utf-8"))
        entrada = next(f for f in manifiesto["fixtures"] if f["archivo"] == "leyesbiblio_CNPP.json")
        doc = documento("CNPP")
        registro = registro_evidencia(
            doc,
            archivo="CNPP.pdf",
            url=url_leyesbiblio("CNPP.pdf"),
            # Fecha sintética: la de la descarga real no se registró (ver manifiesto).
            fecha_consulta="1800-01-01",
            original_sha256=entrada["original"]["sha256"],
            original_bytes=entrada["original"]["bytes"],
            extractor=entrada["extractor"],
            version_extractor=entrada["version_extractor"],
        )
        self.assertEqual(validar_registro(registro), [])
        metadatos = registro["metadatos"]
        self.assertEqual(metadatos["paginas"], [1, 52, 54, 139, 155])
        self.assertEqual(metadatos["ultima_reforma_dof"], "2025-11-28")
        self.assertEqual(metadatos["total_paginas"], 168)
        # Se guardan las tres huellas: PDF, texto extraído y texto limpio.
        self.assertEqual(metadatos["sha256_texto_extraido"], sha256_texto(doc.texto_extraido))
        self.assertEqual(registro["derivado"]["sha256"], sha256_texto(doc.texto))
        self.assertEqual(registro["original"]["sha256"], entrada["original"]["sha256"])
        self.assertEqual(len({metadatos["sha256_texto_extraido"], registro["derivado"]["sha256"], registro["original"]["sha256"]}), 3)
        self.assertEqual(registro["advertencias"], [])


if __name__ == "__main__":
    unittest.main()
