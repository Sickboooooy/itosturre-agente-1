"""Pruebas del parser del SJF (``itosturre/evidencia/sjf.py``).

Fixtures reales: renders literales del portal público (``tests/fixtures/evidencia``).
Variantes sintéticas: textos armados aquí, rotulados y obviamente falsos (registro
0000001, clave SINT…, rubro "RUBRO SINTÉTICO DE PRUEBA"); no reproducen ninguna tesis.
Sin red y sin dependencias externas.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from itosturre.evidencia import validar_registro
from itosturre.evidencia.fuentes import url_tesis_sjf
from itosturre.evidencia.huellas import huella_registro, normalizar_para_cotejo, sha256_texto
from itosturre.evidencia.sjf import ErrorSJF, parsear_tesis, registro_evidencia

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "evidencia"


def _render(registro: str) -> bytes:
    return (FIXTURES / f"sjf_{registro}.txt").read_bytes()


def _tesis(registro: str):
    return parsear_tesis(_render(registro).decode("utf-8"), registro_esperado=registro)


def _codigos(tesis) -> list[str]:
    return [a["codigo"] for a in tesis.advertencias]


# ── Variante sintética base (rotulada; no corresponde a ninguna tesis real) ──────
SINTETICA = "\n".join(
    [
        "Portal sintético de prueba",
        "Duodécima Época",  # época del "banner" sintético: debe ignorarse
        "Registro digital: 0000001",
        "",
        "Instancia: Órgano Sintético de Prueba",
        "",
        "Undécima Época",
        "",
        "Materia(s): Materia Sintética",
        "",
        "Tesis: SINT.1o.X.1 X (11a.)",
        "",
        "Fuente: Fuente sintética de prueba.",
        "Línea sintética de ubicación",
        "",
        "Tipo: Aislada",
        "",
        "RUBRO SINTÉTICO DE PRUEBA. NO CORRESPONDE A NINGUNA TESIS REAL.",
        "",
        "",
        "",
        "",
        "Texto sintético de prueba sin valor jurídico.",
        "",
        "",
        "",
        "",
        "ÓRGANO SINTÉTICO DE PRUEBA.",
        "",
        "",
        "",
        "",
        "Asunto sintético 1/1800. Datos sintéticos de prueba.",
        "",
        "",
        "",
        "Esta tesis se publicó el viernes 7 de enero de 2000 a las 10:00 horas en el "
        "Semanario Judicial de la Federación.",
        "",
        "",
        "",
        "",
        "UBICACIÓN",
        "",
        "Pie sintético del sitio",
    ]
)


def _variante(reemplazos: dict[str, str] | None = None, quitar: tuple[str, ...] = ()) -> str:
    lineas = [linea for linea in SINTETICA.split("\n") if linea not in quitar]
    texto = "\n".join(lineas)
    for viejo, nuevo in (reemplazos or {}).items():
        assert viejo in texto, viejo
        texto = texto.replace(viejo, nuevo)
    return texto


class TesisRealesTests(unittest.TestCase):
    def test_2006224_regresion_epoca_del_banner(self) -> None:
        texto = _render("2006224").decode("utf-8")
        # El fixture reproduce la trampa: la primera línea que menciona "época" es la
        # del banner (Duodécima), anterior al ancla.
        primera = next(l for l in texto.splitlines() if "epoca" in normalizar_para_cotejo(l))
        self.assertIn("Duodécima", primera)
        self.assertLess(texto.index(primera), texto.index("Registro digital:"))

        tesis = _tesis("2006224")
        self.assertEqual(tesis.epoca, "Décima Época")
        self.assertEqual(tesis.epoca_segun_clave, "Décima Época")

    def test_2006224_campos(self) -> None:
        tesis = _tesis("2006224")
        self.assertEqual(tesis.registro, "2006224")
        self.assertEqual(tesis.instancia, "Pleno")
        self.assertEqual(tesis.materias, ("Constitucional",))
        self.assertEqual(tesis.clave, "P./J. 20/2014 (10a.)")
        self.assertEqual(tesis.tipo, "Jurisprudencia")
        self.assertEqual(
            tesis.fuente,
            "Gaceta del Semanario Judicial de la Federación.\nLibro 5, Abril de 2014, Tomo I, página 202",
        )
        self.assertTrue(
            tesis.rubro.startswith(
                "DERECHOS HUMANOS CONTENIDOS EN LA CONSTITUCIÓN Y EN LOS TRATADOS INTERNACIONALES."
            )
        )
        self.assertTrue(tesis.texto.startswith("El primer párrafo del artículo 1o. constitucional"))
        self.assertEqual(
            [s["clase"] for s in tesis.secciones],
            ["precedente", "encabezado_contendientes", "contendientes", "aprobacion", "nota", "publicacion"],
        )
        self.assertTrue(tesis.precedentes[0].startswith("Contradicción de tesis 293/2011."))
        self.assertTrue(tesis.notas[0].startswith("Nota: Esta tesis fue objeto de la denuncia"))
        self.assertEqual(tesis.advertencias, ())

    def test_2006224_publicacion_y_obligatoriedad_declaradas(self) -> None:
        tesis = _tesis("2006224")
        self.assertEqual(tesis.publicacion["fecha"], "2014-04-25")
        self.assertEqual(tesis.publicacion["dia_semana"], "viernes")
        self.assertEqual(tesis.publicacion["hora"], "09:32")
        self.assertEqual(tesis.obligatoriedad["fecha"], "2014-04-28")
        self.assertEqual(tesis.obligatoriedad["dia_semana"], "lunes")
        # Se conserva la frase cruda, no una paráfrasis.
        self.assertIn("se considera de aplicación obligatoria a partir del lunes", tesis.obligatoriedad["frase"])
        self.assertTrue(tesis.publicacion["frase"].startswith("Esta tesis se publicó el viernes 25 de abril"))

    def test_2031931_discrepancia_real_de_epoca_se_reporta_sin_corregir(self) -> None:
        tesis = _tesis("2031931")
        self.assertEqual(tesis.epoca, "Duodécima Época")
        self.assertEqual(tesis.clave, "I.24o.A.22 A (11a.)")
        self.assertEqual(tesis.epoca_segun_clave, "Undécima Época")
        self.assertEqual(_codigos(tesis), ["epoca_discrepante"])
        aviso = tesis.advertencias[0]
        self.assertEqual(aviso["epoca_campo"], "Duodécima Época")
        self.assertEqual(aviso["epoca_segun_clave"], "Undécima Época")
        self.assertEqual(tesis.metadatos()["epoca"], "Duodécima Época")
        self.assertEqual(tesis.metadatos()["epoca_segun_clave"], "Undécima Época")

    def test_2031931_estructura_undecima(self) -> None:
        tesis = _tesis("2031931")
        self.assertEqual(tesis.tipo, "Aislada")
        self.assertEqual(tesis.instancia, "Tribunales Colegiados de Circuito")
        for parte in ("Hechos:", "Criterio jurídico:", "Justificación:", "Por tanto, tratándose"):
            self.assertIn(parte, tesis.texto)
        self.assertEqual(
            [s["clase"] for s in tesis.secciones], ["organo_emisor", "precedente", "publicacion"]
        )
        self.assertTrue(tesis.precedentes[0].startswith("Amparo directo 335/2022."))
        self.assertEqual(tesis.fecha_publicacion, "2026-03-20")
        self.assertIsNone(tesis.obligatoriedad)

    def test_2032506_aislada_dos_materias_sin_obligatoriedad_inferida(self) -> None:
        tesis = _tesis("2032506")
        self.assertEqual(tesis.materias, ("Administrativa", "Común"))
        self.assertEqual(tesis.epoca, "Duodécima Época")
        self.assertEqual(tesis.epoca_segun_clave, "Duodécima Época")
        self.assertEqual(tesis.clave, "VI.3o.A.55 A (12a.)")
        self.assertEqual(tesis.fecha_publicacion, "2026-08-14")
        # Aislada: el texto no declara obligatoriedad y el parser no la calcula.
        self.assertIsNone(tesis.fecha_obligatoriedad)
        self.assertEqual(tesis.advertencias, ())

    def test_banner_y_pie_del_sitio_quedan_fuera(self) -> None:
        for registro in ("2006224", "2031931", "2032506"):
            with self.subTest(registro=registro):
                volcado = json.dumps(_tesis(registro).como_dict(), ensure_ascii=False)
                self.assertNotIn("Pluricultural", volcado)
                self.assertNotIn("Pino Suárez", volcado)
                self.assertNotIn("CONTÁCTANOS", volcado)

    def test_no_existe_campo_de_vigencia(self) -> None:
        metadatos = _tesis("2006224").metadatos()
        self.assertFalse({"vigencia", "vigente"} & set(metadatos))

    def test_fin_de_linea_no_altera_la_lectura(self) -> None:
        crlf = _render("2031931").decode("utf-8")
        self.assertIn("\r\n", crlf)
        lf = crlf.replace("\r\n", "\n")
        self.assertEqual(parsear_tesis(crlf).como_dict(), parsear_tesis(lf).como_dict())

    def test_registro_esperado_distinto_es_error(self) -> None:
        with self.assertRaises(ErrorSJF) as contexto:
            parsear_tesis(_render("2032506").decode("utf-8"), registro_esperado="2031931")
        self.assertEqual(contexto.exception.codigo, "registro_discrepante")

    def test_registro_de_evidencia_valido(self) -> None:
        original = _render("2031931")
        registro = registro_evidencia(
            original,
            url=url_tesis_sjf("2031931"),
            fecha_consulta="2026-10-01T19:57Z",
            registro_esperado="2031931",
        )
        self.assertEqual(validar_registro(registro), [])
        self.assertEqual(registro["original"]["bytes"], len(original))
        self.assertEqual(
            registro["original"]["sha256"],
            "3eca09954ce9e3710ee37ed6fd0f4087ae348239f5d5943b9793044569864b1e",
        )
        tesis = _tesis("2031931")
        self.assertEqual(registro["derivado"]["sha256"], huella_registro(tesis.como_dict()))
        self.assertNotEqual(registro["derivado"]["sha256"], registro["original"]["sha256"])
        self.assertEqual(registro["extracto"]["texto"], tesis.rubro)
        self.assertEqual(registro["extracto"]["sha256"], sha256_texto(tesis.rubro))
        self.assertEqual([a["codigo"] for a in registro["advertencias"]], ["epoca_discrepante"])


class VariantesSinteticasTests(unittest.TestCase):
    def test_base_sintetica_ignora_la_epoca_previa_al_ancla(self) -> None:
        tesis = parsear_tesis(SINTETICA)
        self.assertEqual(tesis.registro, "0000001")
        self.assertEqual(tesis.epoca, "Undécima Época")
        self.assertEqual(tesis.epoca_segun_clave, "Undécima Época")
        self.assertEqual(tesis.rubro, "RUBRO SINTÉTICO DE PRUEBA. NO CORRESPONDE A NINGUNA TESIS REAL.")
        self.assertEqual(tesis.fuente, "Fuente sintética de prueba.\nLínea sintética de ubicación")
        self.assertEqual(
            [s["clase"] for s in tesis.secciones], ["organo_emisor", "precedente", "publicacion"]
        )
        self.assertEqual(tesis.advertencias, ())

    def test_sin_ancla_es_error_explicito(self) -> None:
        with self.assertRaises(ErrorSJF) as contexto:
            parsear_tesis(_variante(quitar=("Registro digital: 0000001",)))
        self.assertEqual(contexto.exception.codigo, "sin_ancla")

    def test_ancla_doble_es_ambiguedad(self) -> None:
        texto = _variante({"Registro digital: 0000001": "Registro digital: 0000001\nRegistro digital: 0000002"})
        with self.assertRaises(ErrorSJF) as contexto:
            parsear_tesis(texto)
        self.assertEqual(contexto.exception.codigo, "ancla_ambigua")

    def test_registro_no_numerico(self) -> None:
        with self.assertRaises(ErrorSJF) as contexto:
            parsear_tesis(_variante({"Registro digital: 0000001": "Registro digital: SINT"}))
        self.assertEqual(contexto.exception.codigo, "registro_invalido")

    def test_epoca_doble_no_elige(self) -> None:
        tesis = parsear_tesis(_variante({"Undécima Época": "Undécima Época\n\nDécima Época"}))
        self.assertIsNone(tesis.epoca)
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "epoca_ambigua")
        self.assertEqual(aviso["valores"], ["Undécima Época", "Décima Época"])
        # La época de la clave se sigue reportando aparte, sin sustituir al campo.
        self.assertEqual(tesis.epoca_segun_clave, "Undécima Época")

    def test_campo_ausente_se_advierte(self) -> None:
        tesis = parsear_tesis(_variante(quitar=("Materia(s): Materia Sintética",)))
        self.assertEqual(tesis.materias, ())
        self.assertIn(
            {"codigo": "campo_ausente", "campo": "materias"},
            [{"codigo": a["codigo"], "campo": a.get("campo")} for a in tesis.advertencias],
        )

    def test_epoca_ausente_no_se_toma_de_la_clave(self) -> None:
        tesis = parsear_tesis(_variante(quitar=("Undécima Época",)))
        self.assertIsNone(tesis.epoca)
        self.assertEqual(tesis.epoca_segun_clave, "Undécima Época")
        self.assertIn("campo_ausente", _codigos(tesis))

    def test_campo_duplicado_no_elige(self) -> None:
        tesis = parsear_tesis(
            _variante({"Tesis: SINT.1o.X.1 X (11a.)": "Tesis: SINT.1o.X.1 X (11a.)\nTesis: SINT.2o.X.2 X (11a.)"})
        )
        self.assertIsNone(tesis.clave)
        self.assertIn("campo_duplicado", _codigos(tesis))

    def test_dia_de_la_semana_inconsistente_se_advierte_sin_corregir(self) -> None:
        tesis = parsear_tesis(_variante({"el viernes 7 de enero": "el lunes 7 de enero"}))
        self.assertEqual(tesis.fecha_publicacion, "2000-01-07")
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "dia_semana_inconsistente")
        self.assertEqual(aviso["dia_declarado"], "lunes")
        self.assertEqual(aviso["dia_calendario"], "viernes")

    def test_fecha_imposible_no_se_inventa(self) -> None:
        tesis = parsear_tesis(_variante({"viernes 7 de enero de 2000": "viernes 31 de febrero de 2000"}))
        self.assertIsNone(tesis.fecha_publicacion)
        self.assertIn("31 de febrero", tesis.publicacion["frase"])
        self.assertIn("fecha_invalida", _codigos(tesis))

    def test_jurisprudencia_sin_obligatoriedad_no_se_infiere(self) -> None:
        tesis = parsear_tesis(_variante({"Tipo: Aislada": "Tipo: Jurisprudencia"}))
        self.assertIsNone(tesis.fecha_obligatoriedad)
        self.assertIn("obligatoriedad_no_declarada", _codigos(tesis))

    def test_pie_ausente_se_advierte(self) -> None:
        tesis = parsear_tesis(_variante(quitar=("UBICACIÓN",)))
        self.assertIn("pie_no_encontrado", _codigos(tesis))

    def test_seccion_no_reconocida_se_conserva_cruda(self) -> None:
        tesis = parsear_tesis(
            _variante({"ÓRGANO SINTÉTICO DE PRUEBA.": "ÓRGANO SINTÉTICO DE PRUEBA.\n\n\n\nsección sintética sin forma reconocible"})
        )
        sueltas = [s for s in tesis.secciones if s["clase"] == "no_clasificada"]
        self.assertEqual([s["texto"] for s in sueltas], ["sección sintética sin forma reconocible"])
        self.assertIn("seccion_no_clasificada", _codigos(tesis))

    def test_etiqueta_desconocida_no_se_confunde_con_el_rubro(self) -> None:
        tesis = parsear_tesis(
            _variante({"Tipo: Aislada": "Tipo: Aislada\n\nLocalización: Dato sintético de prueba"})
        )
        self.assertEqual(tesis.rubro, "RUBRO SINTÉTICO DE PRUEBA. NO CORRESPONDE A NINGUNA TESIS REAL.")
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "campo_desconocido")
        self.assertEqual(aviso["linea"], "Localización: Dato sintético de prueba")

    def test_tipo_fuera_de_vocabulario_se_conserva(self) -> None:
        tesis = parsear_tesis(_variante({"Tipo: Aislada": "Tipo: Tipo Sintético"}))
        self.assertEqual(tesis.tipo, "Tipo Sintético")
        self.assertIn("tipo_no_reconocido", _codigos(tesis))


class EstructuraAdversarialTests(unittest.TestCase):
    """Defectos reproducidos por la revisión externa. Las alteraciones de fixtures
    reales se rotulan; las variantes sintéticas no reproducen tesis alguna."""

    def test_rubro_pegado_al_texto_no_absorbe_el_texto(self) -> None:
        rubro = "RUBRO SINTÉTICO DE PRUEBA. NO CORRESPONDE A NINGUNA TESIS REAL."
        texto = _variante({rubro + "\n\n\n\n\n": rubro + "\n"})
        self.assertIn(rubro + "\nTexto sintético de prueba", texto)
        tesis = parsear_tesis(texto)
        self.assertIsNone(tesis.rubro)
        self.assertIsNone(tesis.texto)
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "rubro_no_reconocible")
        self.assertEqual(aviso["crudo"], rubro + "\nTexto sintético de prueba sin valor jurídico.")
        # El crudo se conserva y lo demás se clasifica por contenido, no por posición.
        self.assertEqual(tesis.secciones[0], {"clase": "no_clasificada", "texto": aviso["crudo"]})
        self.assertEqual(
            [s["clase"] for s in tesis.secciones[1:]], ["organo_emisor", "precedente", "publicacion"]
        )
        self.assertNotIn("campo_ausente", _codigos(tesis))

    def test_sin_texto_el_organo_no_se_toma_como_texto(self) -> None:
        tesis = parsear_tesis(_variante(quitar=("Texto sintético de prueba sin valor jurídico.",)))
        self.assertEqual(tesis.rubro, "RUBRO SINTÉTICO DE PRUEBA. NO CORRESPONDE A NINGUNA TESIS REAL.")
        self.assertIsNone(tesis.texto)
        self.assertIn("texto_no_reconocible", _codigos(tesis))
        self.assertEqual(tesis.secciones[0]["clase"], "organo_emisor")

    def test_dos_frases_de_publicacion_en_el_mismo_bloque(self) -> None:
        # Alteración rotulada del fixture real 2032506: se agrega una segunda frase.
        original = _render("2032506").decode("utf-8")
        frase = "Esta tesis se publicó el viernes 14 de agosto de 2026 a las 10:22 horas"
        self.assertIn(frase, original)
        alterado = original.replace(
            frase,
            "Esta tesis se publicó el viernes 21 de agosto de 2026 a las 10:22 horas en el "
            "Semanario Judicial de la Federación. " + frase,
        )
        tesis = parsear_tesis(alterado)
        self.assertIsNone(tesis.publicacion)
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "publicacion_ambigua")
        self.assertEqual(
            [c["fecha_declarada"] for c in aviso["candidatos"]],
            ["viernes 21 de agosto de 2026", "viernes 14 de agosto de 2026"],
        )

    def test_frase_de_publicacion_repetida_identica_no_es_ambigua(self) -> None:
        frase = (
            "Esta tesis se publicó el viernes 7 de enero de 2000 a las 10:00 horas en el "
            "Semanario Judicial de la Federación."
        )
        tesis = parsear_tesis(_variante({frase: frase + "\n\n\n\n" + frase}))
        self.assertEqual(tesis.fecha_publicacion, "2000-01-07")
        self.assertNotIn("publicacion_ambigua", _codigos(tesis))

    def test_obligatoriedad_fuera_de_la_frase_de_publicacion(self) -> None:
        tesis = parsear_tesis(
            _variante(
                {
                    "Tipo: Aislada": "Tipo: Jurisprudencia",
                    "ÓRGANO SINTÉTICO DE PRUEBA.": "ÓRGANO SINTÉTICO DE PRUEBA.\n\n\n\nNota: Texto "
                    "sintético; se considera de aplicación obligatoria a partir del lunes 10 de "
                    "enero de 2000.",
                }
            )
        )
        self.assertIsNone(tesis.obligatoriedad)
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "obligatoriedad_fuera_de_publicacion")
        self.assertEqual(aviso["candidatos"][0]["fecha_declarada"], "lunes 10 de enero de 2000")
        self.assertIn("obligatoriedad_no_declarada", _codigos(tesis))

    def test_dos_obligatoriedades_en_la_frase_de_publicacion(self) -> None:
        tesis = parsear_tesis(
            _variante(
                {
                    "Tipo: Aislada": "Tipo: Jurisprudencia",
                    "en el Semanario Judicial de la Federación.\n": "en el Semanario Judicial de "
                    "la Federación y, por ende, se considera de aplicación obligatoria a partir del "
                    "lunes 10 de enero de 2000; se considera de aplicación obligatoria a partir del "
                    "lunes 17 de enero de 2000.\n",
                }
            )
        )
        self.assertEqual(tesis.fecha_publicacion, "2000-01-07")
        self.assertIsNone(tesis.obligatoriedad)
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "obligatoriedad_ambigua")
        self.assertEqual(len(aviso["candidatos"]), 2)
        self.assertNotIn("obligatoriedad_no_declarada", _codigos(tesis))

    def test_linea_ajena_pegada_a_la_clave(self) -> None:
        # Alteración rotulada del fixture real 2032506: texto de botón tras la clave.
        original = _render("2032506").decode("utf-8")
        alterado = original.replace("Tesis: VI.3o.A.55 A (12a.)", "Tesis: VI.3o.A.55 A (12a.)\nCopiar")
        self.assertNotEqual(original, alterado)
        tesis = parsear_tesis(alterado)
        self.assertEqual(tesis.clave, "VI.3o.A.55 A (12a.)")
        self.assertEqual(tesis.epoca_segun_clave, "Duodécima Época")
        aviso = next(a for a in tesis.advertencias if a["codigo"] == "continuacion_no_admitida")
        self.assertEqual((aviso["campo"], aviso["linea"]), ("clave", "Copiar"))
        # El resto de la lectura no se altera.
        self.assertEqual(tesis.rubro, _tesis("2032506").rubro)

    def test_fuente_si_admite_varias_lineas(self) -> None:
        self.assertEqual(
            _tesis("2006224").fuente,
            "Gaceta del Semanario Judicial de la Federación.\nLibro 5, Abril de 2014, Tomo I, página 202",
        )

    def test_clave_sin_sufijo_de_epoca_se_advierte(self) -> None:
        tesis = parsear_tesis(_variante({"SINT.1o.X.1 X (11a.)": "SINT.1o.X.1 X"}))
        self.assertEqual(tesis.clave, "SINT.1o.X.1 X")
        self.assertIsNone(tesis.epoca_segun_clave)
        self.assertIn("clave_sin_sufijo_epoca", _codigos(tesis))
        self.assertEqual(tesis.epoca, "Undécima Época")  # el campo no se toca


if __name__ == "__main__":
    unittest.main()
