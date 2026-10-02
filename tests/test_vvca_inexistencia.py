"""R4-D10 — prueba positiva de inexistencia (criterio del responsable, 2-oct-2026: opción C).

Un artículo que no se localiza en una ley indexada solo es 🔴 con prueba positiva de que no
existe en el CUERPO de la ley (antes de la primera línea TRANSITORIOS):

1. vecinos en el MISMO fragmento, sin ninguna línea candidata a encabezado entre ellos;
2. número muy superior al último artículo de un cuerpo completo en el índice (``chunk_index``
   contiguos desde el 0 hasta la frontera, sin frontera dudosa, sin señal de páginas perdidas):
   N ≥ último + max(10, ⌈5 % del último⌉).

Ronda 2 (rechazo por falsos rojos): la prueba se ABSTIENE ante cualquier ambigüedad; además
exige identidad documental y una ley ligada por vínculo sintáctico explícito. Cada punto del
dictamen (P1–P9) tiene aquí su prueba de regresión.

Corre sin dependencias (Python 3.11 del CI). La "ley" de estas pruebas es SINTÉTICA: textos de
relleno con la forma de los fragmentos que guarda la ingesta. Su título es la denominación del
CFF solo para que la cita resuelva la ley y la identidad documental se compruebe; la fecha de
"Última Reforma DOF 01-01-2099" es ficticia a propósito y nada del contenido es texto legal.
"""
from __future__ import annotations

import unittest
from unittest import mock

from itosturre.audit import inexistencia as inx
from itosturre.audit.inexistencia import (
    CANDIDATA,
    PRUEBA_NUMERO_MAYOR,
    PRUEBA_VECINOS,
    SIN_FECHA,
    LeyPreparada,
    clave_orden,
    describir_posterior,
    describir_prueba,
    es_frontera_transitorios,
    evaluar_inexistencia,
    inexistencia_acreditada,
    margen_prueba_numero,
    preparar_ley,
)
from itosturre.evidencia.leyesbiblio import es_frontera_transitorios as frontera_evidencia
from tests.test_vvca_nucleo import AuditoriaBase
from tests.vvca_falsos import FakeCollection, importar_opennotebook

ON = importar_opennotebook()
CFF = ON.LAW_SOURCE_MAP["cff"]
DENOMINACIONES = ON._denominaciones(CFF)
VERSION = "Última Reforma DOF 01-01-2099"
CABECERA = (
    "CÓDIGO FISCAL DE LA FEDERACIÓN\nCÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN\n"
    "Secretaría General\nSecretaría de Servicios Parlamentarios\n"
    "Última Reforma DOF 01-01-2099\n\n1 de 9\n"
)

# Ley sintética: (texto, etiqueta del chunker, página). chunk_index = posición.
LEY = [
    (CABECERA + "DECRETO sintético de prueba.\n\nARTÍCULO ÚNICO.- Se expide la ley sintética.\n", "", "1"),
    ("Artículo 1o.- Texto sintético del primer artículo de la ley de prueba.", "1o", "1"),
    ("Artículo 2o.- Texto sintético del segundo artículo de la ley de prueba.", "2o", "2"),
    ("Artículo 3o.- Texto sintético del tercer artículo.\n\n"
     "Artículo 4o.- Texto sintético del cuarto artículo.", "3o", "2"),
    ("Artículo 5o.- (Se deroga).", "5o", "3"),
    ("Artículo 6o.- Texto sintético del sexto y último artículo.\n\nTRANSITORIOS\n\n"
     "PRIMERO.- El decreto sintético entra en vigor al día siguiente.", "6o", "3"),
]


def fragmentos(ley=LEY, *, fuente: str = CFF, indices=None) -> list[tuple[str, dict]]:
    indices = list(range(len(ley))) if indices is None else indices
    return [
        (texto, {"source": fuente, "article": etiqueta, "page": pagina,
                 "chunk_index": str(indice)})
        for (texto, etiqueta, pagina), indice in zip(ley, indices)
    ]


def evaluar(articulo: str, ley=LEY, **opciones) -> dict:
    return evaluar_inexistencia(fragmentos(ley, **opciones), articulo, DENOMINACIONES)


def con_tercero(texto: str) -> list:
    """La ley sintética con el fragmento de los arts. 3o y 4o sustituido por ``texto``."""
    return LEY[:3] + [(texto, "3o", "2")] + LEY[4:]


class FuncionesAuxiliaresTests(unittest.TestCase):
    def test_clave_de_orden_con_sufijos(self) -> None:
        orden = ["19", "19 Bis", "19 Ter", "19 Quáter", "20"]
        self.assertEqual(sorted(orden, key=clave_orden), orden)
        orden = ["32-B", "32-B Bis", "32-B Ter", "32-C"]
        self.assertEqual(sorted(orden, key=clave_orden), orden)
        self.assertEqual(clave_orden("4o.-A"), clave_orden("4-A"))
        self.assertEqual(clave_orden("4o"), clave_orden("4"))
        self.assertIsNone(clave_orden("Primero"))

    def test_frontera_transitorios_igual_que_la_capa_de_evidencia(self) -> None:
        lineas = [
            "TRANSITORIOS", "TRANSITORIOS ", "Transitorios", "TRANSITORIO:", "ARTÍCULOS TRANSITORIOS",
            "Artículos Transitorios ", "ARTICULOS TRANSITORIOS DE DECRETOS DE REFORMA",
            "ARTÍCULOS TRANSITORIOS:", "Disposiciones transitorias", "Artículo transitorio primero",
            "TRANSITORIOS de la ley", "Artículo 1o.- Texto",
        ]
        for linea in lineas:
            with self.subTest(linea=linea):
                self.assertEqual(es_frontera_transitorios(linea), frontera_evidencia(linea))

    def test_margen_de_la_prueba_por_numero(self) -> None:
        # P6: max(10, ⌈5 % del último⌉).
        self.assertEqual(margen_prueba_numero(3), 10)
        self.assertEqual(margen_prueba_numero(136), 10)
        self.assertEqual(margen_prueba_numero(263), 14)
        self.assertEqual(margen_prueba_numero(3074), 154)

    def test_version_indexada(self) -> None:
        self.assertEqual(preparar_ley(fragmentos(), DENOMINACIONES).version, VERSION)
        nueva = [(LEY[0][0].replace("Última Reforma DOF 01-01-2099", "Nueva Ley DOF 01-01-2098"),
                  "", "1")] + LEY[1:]
        self.assertEqual(preparar_ley(fragmentos(nueva), DENOMINACIONES).version,
                         "Nueva Ley DOF 01-01-2098")
        sin = [("CÓDIGO FISCAL DE LA FEDERACIÓN\nTexto sintético.", "", "1")] + LEY[1:]
        self.assertEqual(preparar_ley(fragmentos(sin), DENOMINACIONES).version, SIN_FECHA)

    def test_designacion_ambigua_no_se_ordena(self) -> None:
        # "Artículo 20.- A. De los…": la "A" puede ser el apartado, no el sufijo "20-A".
        ley = preparar_ley(fragmentos(con_tercero(
            "Artículo 3o.- Texto.\nArtículo 20.- A. De los principios sintéticos.")), DENOMINACIONES)
        (veinte,) = [e for e in ley.encabezados if e.designacion.startswith("20")]
        self.assertEqual(veinte.tipo, CANDIDATA)


class IdentidadDocumentalTests(unittest.TestCase):
    """P5: sin identidad documental comprobada no hay prueba."""

    def test_titulo_del_encabezado_identifica(self) -> None:
        self.assertTrue(evaluar("9999")["acreditada"])

    def test_decreto_que_la_expide_identifica(self) -> None:
        ley = [("ALBERTO SINTÉTICO, gobernador. El Congreso decreta: Código Fiscal de la "
                "Federación, para quedar como sigue:\n", "", "1")] + LEY[1:]
        self.assertTrue(evaluar("9999", ley)["acreditada"])

    def test_documento_ajeno_no_prueba(self) -> None:
        # Otra ley indexada bajo el ``source`` del CFF: refutaría artículos reales del CFF.
        ajena = [(LEY[0][0].replace("CÓDIGO FISCAL DE LA FEDERACIÓN", "LEY SINTÉTICA AJENA"),
                  "", "1")] + LEY[1:]
        resultado = evaluar("9999", ajena)
        self.assertFalse(resultado["acreditada"])
        self.assertIn("no se identifica como 'codigo fiscal de la federacion'", resultado["motivo"])

    def test_denominacion_solo_mencionada_no_identifica(self) -> None:
        # El título de OTRA ley que menciona el CFF más adelante no lo identifica.
        ajena = [("LEY SINTÉTICA, reglamentaria del Código Fiscal de la Federación\n", "", "1")] + LEY[1:]
        self.assertFalse(evaluar("9999", ajena)["acreditada"])

    def test_sin_denominaciones_del_catalogo(self) -> None:
        resultado = evaluar_inexistencia(fragmentos(), "9999", ["cff", "c.f.f."])
        self.assertFalse(resultado["acreditada"])
        self.assertIn("no hay una denominación del catálogo", resultado["motivo"])


class PruebaNumeroMayorTests(unittest.TestCase):
    def test_numero_muy_superior_al_ultimo(self) -> None:
        resultado = evaluar("9999")
        self.assertTrue(resultado["acreditada"])
        self.assertEqual(resultado["prueba"], {
            "tipo": PRUEBA_NUMERO_MAYOR,
            "articulo": "9999",
            "fuente": CFF,
            "version": VERSION,
            "ultimo": {"articulo": "6o", "pagina": "3", "chunk_index": 5},
            "margen": 10,
            "frontera_transitorios": {"pagina": "3", "chunk_index": 5},
            "fragmentos": [0, 5],
            "paginas": ["3"],
        })
        self.assertEqual(
            describir_prueba(resultado["prueba"], "'ley sintética'"),
            f"el cuerpo de 'ley sintética' (versión indexada: {VERSION}) termina en el art. 6o "
            f"(pág. 3); se cita el 9999",
        )
        # Con LeyPreparada (P9) el resultado es el mismo.
        ley = preparar_ley(fragmentos(), DENOMINACIONES)
        self.assertIsInstance(ley, LeyPreparada)
        self.assertEqual(evaluar_inexistencia(ley, "9999"), resultado)

    def test_P6_ultimo_mas_uno_no_prueba_y_lo_dice(self) -> None:
        # Un artículo adicionado por una reforma posterior a la versión indexada: 🟡.
        for citado in ("7", "15"):
            with self.subTest(citado=citado):
                resultado = evaluar(citado)
                self.assertFalse(resultado["acreditada"])
                posterior = resultado["posterior_al_ultimo"]
                self.assertEqual((posterior["ultimo"]["articulo"], posterior["margen"],
                                  posterior["version"]), ("6o", 10, VERSION))
        self.assertEqual(
            describir_posterior(evaluar("7")["posterior_al_ultimo"], "'ley sintética'"),
            f"el art. 7 es posterior al último artículo de la VERSIÓN INDEXADA de 'ley sintética' "
            f"(art. 6o, pág. 3; {VERSION}): verificar si una reforma lo adicionó",
        )
        self.assertTrue(evaluar("16")["acreditada"])   # 6 + 10

    def test_hueco_de_chunk_index(self) -> None:
        resultado = evaluar("9999", LEY[:4] + LEY[5:], indices=[0, 1, 2, 3, 5])
        self.assertFalse(resultado["acreditada"])
        self.assertEqual(resultado["motivo"], "cuerpo incompleto: hueco de chunk_index antes del 5")

    def test_sin_frontera_transitorios(self) -> None:
        ley = LEY[:5] + [("Artículo 6o.- Texto sintético del sexto artículo.", "6o", "3")]
        self.assertEqual(evaluar("9999", ley)["motivo"],
                         "sin línea TRANSITORIOS: no se delimita el cuerpo de la ley")

    def test_P2_frontera_dudosa_con_linea_sin_cierre(self) -> None:
        ley = LEY + [("ARTÍCULO 7 texto sintético sin cierre tras la frontera.", "", "4")]
        resultado = evaluar("9999", ley)
        self.assertFalse(resultado["acreditada"])
        self.assertIn("frontera dudosa", resultado["motivo"])

    def test_P2_mencion_del_citado_tras_la_frontera(self) -> None:
        ley = LEY + [("SEGUNDO.- Se reforma el artículo 9999 sintético.", "", "4")]
        resultado = evaluar("9999", ley)
        self.assertFalse(resultado["acreditada"])
        self.assertEqual(resultado["motivo"], "el texto de la ley menciona el artículo 9999")

    def test_P1_linea_candidata_con_numero_mayor_en_el_cuerpo(self) -> None:
        for linea in ("ARTICULO 225 sin cierre", "Art 30 Bis texto", "40 Bis.- Texto", "50.- Texto"):
            with self.subTest(linea=linea):
                resultado = evaluar("9999", con_tercero(
                    "Artículo 3o.- Texto.\n" + linea + "\nArtículo 4o.- Texto."))
                self.assertFalse(resultado["acreditada"])
                self.assertIn("línea candidata", resultado["motivo"])

    def test_fecha_al_final_de_la_linea_no_es_candidata(self) -> None:
        ley = con_tercero("Artículo 3o.- Publicado el 1 de enero de\n2016.\n\nArtículo 4o.- Texto.")
        self.assertTrue(evaluar("9999", ley)["acreditada"])

    def test_mencion_en_enumeracion_o_rango(self) -> None:
        for texto in ("Véanse los artículos 2o., 13 y 20.", "Los artículos 10 a 20 sintéticos."):
            with self.subTest(texto=texto):
                ley = LEY[:1] + [("Artículo 1o.- " + texto, "1o", "1")] + LEY[2:]
                self.assertEqual(evaluar("15" if " a " in texto else "13", ley)["motivo"],
                                 "el texto de la ley menciona el artículo "
                                 + ("15" if " a " in texto else "13"))

    def test_P7_densidad_delata_paginas_perdidas(self) -> None:
        # El fragmento del art. 2o empieza en la pág. 2 y el siguiente en la 9, con unas
        # decenas de caracteres: no pudo llenar siete páginas.
        ley = LEY[:3] + [(LEY[3][0], "3o", "9"), (LEY[4][0], "5o", "9"), (LEY[5][0], "6o", "9")]
        resultado = evaluar("9999", ley)
        self.assertFalse(resultado["acreditada"])
        self.assertIn("posible texto perdido", resultado["motivo"])

    def test_cuerpo_que_no_empieza_en_cero(self) -> None:
        resultado = evaluar("9999", LEY[1:], indices=[1, 2, 3, 4, 5])
        self.assertFalse(resultado["acreditada"])


class PruebaVecinosTests(unittest.TestCase):
    def test_vecinos_en_el_mismo_fragmento(self) -> None:
        for citado in ("3 Bis", "3 Ter", "3-A", "3o. Bis"):
            with self.subTest(citado=citado):
                prueba = inexistencia_acreditada(fragmentos(), citado, DENOMINACIONES)
                self.assertEqual(prueba["tipo"], PRUEBA_VECINOS)
                self.assertEqual(prueba["anterior"], {"articulo": "3o", "pagina": "2", "chunk_index": 3})
                self.assertEqual(prueba["siguiente"], {"articulo": "4o", "pagina": "2", "chunk_index": 3})
                self.assertEqual((prueba["fragmentos"], prueba["paginas"]), ([3], ["2"]))
        self.assertEqual(
            describir_prueba(inexistencia_acreditada(fragmentos(), "3 Bis", DENOMINACIONES),
                             "'ley sintética'"),
            f"en el cuerpo de 'ley sintética' (versión indexada: {VERSION}) el art. 3o pasa al "
            f"art. 4o sin el 3 Bis (pág. 2)",
        )

    def test_P3_fragmentos_distintos_no_prueban_aunque_solapen(self) -> None:
        relleno = "texto sintético de relleno que se repite al final y al inicio de dos fragmentos"
        ley = [
            LEY[0], LEY[1],
            ("Artículo 2o.- Texto sintético del segundo artículo.\n" + relleno, "2o", "2"),
            ("[LEY 2o]\n" + relleno + "\n\nArtículo 3o.- Texto sintético del tercero.", "2o", "2"),
            LEY[5],
        ]
        resultado = evaluar("2 Bis", ley)
        self.assertFalse(resultado["acreditada"])
        self.assertIn("están en fragmentos distintos", resultado["motivo"])

    def test_P1_linea_candidata_entre_los_vecinos(self) -> None:
        casos = {
            "3 Bis.- Texto del artículo adicionado.": "menciona",
            "3o.- Texto.": "no aparecen seguidos",
            "ARTÍ-\nCULO 3 BIS.- Texto.": "encabezado del artículo 3 Bis aparece",
            "Art 3 Bis Texto.": "menciona",
            "artículo 42 de esta ley sintética.": "línea candidata",
            "3o.-\nTexto.": "línea candidata",
            "1. Primera regla sintética.": "no aparecen seguidos",
        }
        for linea, motivo in casos.items():
            with self.subTest(linea=linea):
                resultado = evaluar("3 Bis", con_tercero(
                    "Artículo 3o.- Texto.\n" + linea + "\nArtículo 4o.- Texto."))
                self.assertFalse(resultado["acreditada"])
                self.assertIn(motivo, resultado["motivo"])

    def test_P1_mencion_del_citado_con_sufijo_en_el_cuerpo(self) -> None:
        ley = LEY[:1] + [("Artículo 1o.- Conforme a los artículos 2o. y 3 Bis sintéticos.", "1o", "1")] + LEY[2:]
        self.assertEqual(evaluar("3 Bis", ley)["motivo"], "el texto de la ley menciona el artículo 3 Bis")

    def test_derogado_acredita_existencia(self) -> None:
        self.assertEqual(evaluar("5")["motivo"], "el encabezado del artículo 5 aparece en la fuente")

    def test_otro_ordinal_acredita_existencia(self) -> None:
        self.assertFalse(evaluar("4")["acreditada"])

    def test_ordinal_en_palabra_entre_los_vecinos(self) -> None:
        ley = con_tercero("Artículo 3o.- Texto.\nARTÍCULO SEGUNDO.- Decreto sintético.\n\n"
                          "Artículo 4o.- Texto.")
        self.assertFalse(evaluar("3 Bis", ley)["acreditada"])

    def test_sufijos_de_letra_y_latinos_del_mismo_numero(self) -> None:
        ley = con_tercero("Artículo 3o.- Texto.\n\nArtículo 3o.-A.- Texto.\n\n"
                          "Artículo 3o Bis.- Texto.\n\nArtículo 4o.- Texto.")
        self.assertIn("sufijos de letra y latinos", evaluar("3 Ter", ley)["motivo"])

    def test_vecino_repetido(self) -> None:
        ley = LEY[:2] + [("Artículo 3o.- Texto sintético repetido.", "3o", "2")] + LEY[3:]
        self.assertIn("se repite en el cuerpo", evaluar("3 Bis", ley)["motivo"])

    def test_entradas_invalidas(self) -> None:
        sin_indice = [(texto, {"source": CFF}) for texto, _, _ in LEY]
        self.assertIn("chunk_index", evaluar_inexistencia(sin_indice, "9999", DENOMINACIONES)["motivo"])
        mezcla = fragmentos() + [("Artículo 1.- Otro.", {"source": "otra.pdf", "chunk_index": "9"})]
        self.assertIn("una sola fuente", evaluar_inexistencia(mezcla, "9999", DENOMINACIONES)["motivo"])
        repetido = fragmentos() + [("Artículo 7.- Otro.", {"source": CFF, "chunk_index": "1"})]
        self.assertIn("repetido", evaluar_inexistencia(repetido, "9999", DENOMINACIONES)["motivo"])
        self.assertIn("no se puede descomponer", evaluar("Único")["motivo"])
        self.assertIn("no tiene fragmentos", evaluar_inexistencia([], "9999", DENOMINACIONES)["motivo"])


class AuditoriaInexistenciaTests(AuditoriaBase):
    """``audit`` con la ley sintética en la colección falsa."""

    CONSULTA_9999 = "Artículo 9999 código fiscal de la federación"
    TEXTO_9999 = "El artículo 9999 del Código Fiscal de la Federación se invoca."

    def cargar(self, ley=LEY, *, coleccion: FakeCollection | None = None, consulta=None,
               cercano: int = 1, distancia: float = 0.10, indices=None) -> FakeCollection:
        """Indexa la ley; el fragmento ``cercano`` queda a ``distancia`` de ``consulta``."""
        coleccion = coleccion or self.coleccion
        eje = self.codificador.eje(consulta) if consulta else None
        for posicion, (texto, metadata) in enumerate(fragmentos(ley, indices=indices)):
            if eje is not None and posicion == cercano:
                coleccion.agregar(texto, metadata, eje=eje, distancia=distancia)
            else:
                coleccion.agregar(texto, metadata)
        return coleccion

    def alerta_roja_9999(self) -> str:
        return (
            f"🔴 ARTÍCULO INEXISTENTE ACREDITADO: 'artículo 9999' — el cuerpo de '{CFF}' "
            f"(versión indexada: {VERSION}) termina en el art. 6o (pág. 3); se cita el 9999. "
            f"Corregir o sustituir la cita antes de cualquier uso procesal; si el escrito invoca "
            f"una reforma posterior a esa versión, cotejarla en la fuente oficial."
        )

    def test_R4_D10_numero_muy_superior_por_evidencia_insuficiente_es_rojo(self) -> None:
        # La ruta real de "art. 9999 CFF" en el corpus: el vecino semántico no trae el
        # encabezado (antes 🟡 EVIDENCIA INSUFICIENTE 84).
        self.cargar(consulta=self.CONSULTA_9999, distancia=0.10)
        resultado = self.auditar(self.TEXTO_9999)
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "refuted", "corpus_estructura")])
        self.assertEqual(resultado["alerts"], [self.alerta_roja_9999()])
        (fuente,) = resultado["retrieved_sources"]
        self.assertEqual((fuente["vvca"]["score"], fuente["vvca"]["semaforo"]), (0, "🔴"))
        self.assertEqual(fuente["inexistencia_acreditada"]["tipo"], PRUEBA_NUMERO_MAYOR)
        self.assertEqual(fuente["page"], "3")
        # La evidencia es la de la prueba (texto original): el último artículo y la frontera.
        self.assertIn("Artículo 6o.-", fuente["retrieved_text_full"])
        self.assertIn("TRANSITORIOS", fuente["retrieved_text_full"])
        resumen = resultado["vvca_summary"]
        self.assertEqual((resumen["verdes"], resumen["amarillos"], resumen["rojos"]), (0, 0, 1))
        self.assertEqual(resumen["veredicto"]["semaforo"], "🔴")

    def test_R4_D10_numero_muy_superior_con_distancia_alta_es_rojo(self) -> None:
        self.cargar(consulta=self.CONSULTA_9999, distancia=0.40)
        resultado = self.auditar(self.TEXTO_9999)
        self.assertEqual(resultado["alerts"], [self.alerta_roja_9999()])

    def test_R4_D10_vecinos_por_la_ruta_de_sufijo_es_rojo(self) -> None:
        consulta = "Artículo 3 Bis código fiscal de la federación"
        self.cargar(consulta=consulta, cercano=3, distancia=0.10)
        resultado = self.auditar("El artículo 3 Bis del Código Fiscal de la Federación se invoca.")
        self.assertEqual(self.estados(resultado),
                         [("artículo 3 Bis", "refuted", "corpus_estructura")])
        self.assertEqual(resultado["alerts"], [
            f"🔴 ARTÍCULO INEXISTENTE ACREDITADO: 'artículo 3 Bis' — en el cuerpo de '{CFF}' "
            f"(versión indexada: {VERSION}) el art. 3o pasa al art. 4o sin el 3 Bis (pág. 2). "
            f"Corregir o sustituir la cita antes de cualquier uso procesal; si el escrito invoca "
            f"una reforma posterior a esa versión, cotejarla en la fuente oficial."
        ])

    def test_R4_D10_sin_vecinos_con_prueba_es_rojo(self) -> None:
        coleccion = self.cargar(coleccion=FakeCollection(vaciar_consultas=True),
                                consulta=self.CONSULTA_9999)
        resultado = self.auditar(self.TEXTO_9999, coleccion=coleccion)
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "refuted", "corpus_estructura")])
        (fuente,) = resultado["retrieved_sources"]
        self.assertIsNone(fuente["relevance_score"])

    def test_R4_D10_P6_ultimo_mas_uno_es_posterior_en_cada_ruta(self) -> None:
        aviso = (f"el art. 7 es posterior al último artículo de la VERSIÓN INDEXADA de '{CFF}' "
                 f"(art. 6o, pág. 3; {VERSION}): verificar si una reforma lo adicionó.")
        consulta = "Artículo 7 código fiscal de la federación"
        casos = (
            (0.10, "partial", f"🟡 POSTERIOR AL ÚLTIMO ARTÍCULO (score 84): 'artículo 7' — {aviso}"),
            (0.40, "not_verifiable", f"🟡 POSTERIOR AL ÚLTIMO ARTÍCULO (score 60): 'artículo 7' — {aviso}"),
        )
        for distancia, estado, alerta in casos:
            with self.subTest(distancia=distancia):
                self.setUp()
                self.cargar(consulta=consulta, distancia=distancia)
                resultado = self.auditar("El artículo 7 del Código Fiscal de la Federación se invoca.")
                self.assertEqual(self.estados(resultado), [("artículo 7", estado, "corpus_semantic")])
                self.assertEqual(resultado["alerts"], [alerta])
                self.assertEqual(resultado["vvca_summary"]["rojos"], 0)
        self.setUp()
        coleccion = self.cargar(coleccion=FakeCollection(vaciar_consultas=True), consulta=consulta)
        resultado = self.auditar("El artículo 7 del Código Fiscal de la Federación se invoca.",
                                 coleccion=coleccion)
        self.assertEqual(resultado["alerts"],
                         [f"🟡 POSTERIOR AL ÚLTIMO ARTÍCULO: 'artículo 7' — {aviso}"])
        (traza,) = resultado["traceability"]["records"]
        self.assertEqual(traza["metadata"]["posterior_al_ultimo"]["ultimo"]["articulo"], "6o")

    def test_R4_D10_hueco_de_chunk_index_queda_no_localizado(self) -> None:
        self.cargar(LEY[:4] + LEY[5:], consulta=self.CONSULTA_9999, distancia=0.40,
                    indices=[0, 1, 2, 3, 5])
        resultado = self.auditar(self.TEXTO_9999)
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "not_verifiable", "corpus_semantic")])
        self.assertTrue(resultado["alerts"][0].startswith("🟡 NO LOCALIZADO (score 60)"))

    def test_R4_D10_P4a_ley_del_contexto_previo_no_sostiene_la_prueba(self) -> None:
        # "El CFF regula la materia. El artículo 9999…": ley del contexto previo (inferida),
        # no ligada por vínculo sintáctico explícito: nunca 🔴, ruta de siempre.
        self.cargar(consulta="Artículo 9999 cff", distancia=0.10)
        resultado = self.auditar("El CFF regula la materia. El artículo 9999 dispone las facultades.")
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "partial", "corpus_semantic")])
        self.assertTrue(resultado["alerts"][0].startswith("🟡 EVIDENCIA INSUFICIENTE"))
        self.assertEqual(resultado["vvca_summary"]["rojos"], 0)

    def test_R4_D10_P4b_contexto_previo_con_dos_leyes_es_ambiguo(self) -> None:
        texto = ("La Ley de Amparo regula la jurisprudencia y la CPEUM fija sus bases. "
                 "El artículo 217 determina su obligatoriedad.")
        (ref,) = ON.extract_references(texto)
        self.assertIsNone(ref["source_file"])
        self.assertIn("contexto previo es ambiguo", ref["law_unidentified_reason"])
        self.cargar()
        resultado = self.auditar(texto)
        self.assertTrue(resultado["alerts"][0].startswith("🟡 NO VERIFICABLE — LEY NO IDENTIFICADA"))
        self.assertEqual(resultado["vvca_summary"]["rojos"], 0)

    def test_R4_D10_P5_documento_ajeno_no_prueba(self) -> None:
        ajena = [(LEY[0][0].replace("CÓDIGO FISCAL DE LA FEDERACIÓN", "LEY SINTÉTICA AJENA"),
                  "", "1")] + LEY[1:]
        self.cargar(ajena, consulta=self.CONSULTA_9999, distancia=0.40)
        resultado = self.auditar(self.TEXTO_9999)
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "not_verifiable", "corpus_semantic")])
        (fuente,) = resultado["retrieved_sources"]
        self.assertIn("no se identifica", fuente["vvca"]["explicabilidad"]["inexistencia_no_acreditada"])

    def test_R4_D10_derogado_no_localizado_no_es_rojo(self) -> None:
        ley = LEY[:4] + [("Artículo 5o.- (Se deroga).", "4o", "3")] + LEY[5:]
        self.cargar(ley, consulta="Artículo 5 código fiscal de la federación", distancia=0.10)
        resultado = self.auditar("El artículo 5 del Código Fiscal de la Federación se invoca.")
        self.assertEqual(self.estados(resultado), [("artículo 5", "partial", "corpus_semantic")])
        self.assertTrue(resultado["alerts"][0].startswith("🟡 EVIDENCIA INSUFICIENTE"))

    def test_R4_D10_ley_por_confirmar_no_busca_prueba(self) -> None:
        texto = "El CFF regula la materia.\n\nEl artículo 9999 dispone las facultades."
        self.cargar(consulta="Artículo 9999 cff", distancia=0.40)
        resultado = self.auditar(texto)
        self.assertEqual(self.estados(resultado),
                         [("artículo 9999", "partial", "corpus_semantic")])
        self.assertTrue(resultado["alerts"][0].startswith("🟡 LEY POR CONFIRMAR"))

    def test_R4_D10_encabezado_ubicado_con_distancia_alta_es_cotejar(self) -> None:
        # Encabezado exacto sin candidatos de metadata (etiqueta distinta) y distancia alta:
        # antes "🔴 ALERTA ALTA … Posible alucinación"; el precepto sí se ubicó.
        self.cargar(consulta="Artículo 4o código fiscal de la federación", cercano=3,
                    distancia=0.40)
        resultado = self.auditar("El artículo 4o. del Código Fiscal de la Federación se invoca.")
        self.assertEqual(self.estados(resultado), [("artículo 4o", "partial", "corpus_semantic")])
        self.assertEqual(resultado["alerts"], [
            f"🟡 COTEJAR (score 60): 'artículo 4o' — se ubicó el encabezado del artículo 4o en "
            f"'{CFF}', pero el texto recuperado coincide poco (dist=0.400, umbral=0.25). "
            f"Cotejar el texto citado contra el precepto."
        ])

    def test_R4_D10_P9_la_ley_se_prepara_una_vez(self) -> None:
        self.cargar(consulta="Artículo 1o código fiscal de la federación", cercano=1, distancia=0.05)
        self.codificador.eje(self.CONSULTA_9999)
        self.codificador.eje("Artículo 8888 código fiscal de la federación")
        with mock.patch.object(ON, "preparar_ley", wraps=ON.preparar_ley) as preparar:
            resultado = self.auditar(
                "El artículo 1o. del Código Fiscal de la Federación, el artículo 9999 del Código "
                "Fiscal de la Federación y el artículo 8888 del Código Fiscal de la Federación."
            )
        self.assertEqual([estado for _, estado, _ in self.estados(resultado)],
                         ["verified", "refuted", "refuted"])
        self.assertEqual(preparar.call_count, 1)
        lecturas = [
            llamada for llamada in self.coleccion.llamadas
            if llamada[0] == "get" and llamada[1]["where"] == {"source": CFF}
            and llamada[1]["include"] == ["documents", "metadatas"]
        ]
        self.assertEqual(len(lecturas), 1)
        self.assertEqual(resultado["vvca_summary"]["veredicto"]["semaforo"], "🔴")


class ModuloTests(unittest.TestCase):
    def test_exportado_en_el_paquete(self) -> None:
        from itosturre import audit
        self.assertIs(audit.evaluar_inexistencia, evaluar_inexistencia)
        self.assertIs(audit.inexistencia_acreditada, inexistencia_acreditada)
        self.assertIs(audit.describir_prueba, describir_prueba)
        self.assertIs(audit.preparar_ley, preparar_ley)
        self.assertEqual((inx.MARGEN_MINIMO, inx.CARACTERES_POR_PAGINA), (10, 800))


if __name__ == "__main__":
    unittest.main()
