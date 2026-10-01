"""Pruebas del parser de notas de reforma (``itosturre/evidencia/reformas.py``).

El invariante central se prueba sobre TODAS las notas de los fixtures reales: el
multiconjunto de fechas dd-mm-aaaa del crudo es exactamente el de las fechas
parseadas, y ninguna fecha de las páginas se pierde ni se cuenta dos veces. Las notas
sintéticas usan fechas de 1800 (anteriores a cualquier compilado vigente) y no se
atribuyen a ninguna ley. Sin red ni dependencias externas.
"""
from __future__ import annotations

import json
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path

from itosturre.evidencia.leyesbiblio import limpiar_documento
from itosturre.evidencia.reformas import (
    FECHA_DOF,
    EventoReforma,
    extraer_notas,
    fecha_dof_a_iso,
    invariante_fechas,
    iso_a_fecha_dof,
    parsear_nota,
    verificar_fechas,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "evidencia"
LEYES = ("CNPP", "CPF", "CPEUM", "CFF", "LAmp")


def notas_de(ley: str):
    """``(líneas (página, índice, texto), resultado)`` de la ley limpia."""
    datos = json.loads((FIXTURES / f"leyesbiblio_{ley}.json").read_text(encoding="utf-8"))
    doc = limpiar_documento(
        [p["texto"] for p in datos["paginas"]], numeros=[p["numero"] for p in datos["paginas"]]
    )
    lineas = doc.lineas()
    return lineas, extraer_notas([texto for _, _, texto in lineas])


def nota_en(ley: str, pagina: int, indice: int):
    """La nota que empieza en (página, índice) y sus líneas originales."""
    lineas, resultado = notas_de(ley)
    for nota in resultado.notas:
        primera = lineas[nota.lineas[0]]
        if (primera[0], primera[1]) == (pagina, indice):
            return nota, [lineas[k] for k in nota.lineas]
    raise AssertionError(f"no hay nota en {ley} p{pagina} l{indice}")


def eventos(nota) -> list[tuple]:
    return [(e.accion, list(e.fechas), e.elemento, e.detalle) for e in nota.eventos]


class InvarianteFechasTests(unittest.TestCase):
    def test_todas_las_notas_de_todos_los_fixtures(self) -> None:
        reconocidas = no_reconocidas = 0
        for ley in LEYES:
            lineas, resultado = notas_de(ley)
            textos = [texto for _, _, texto in lineas]
            with self.subTest(ley=ley):
                self.assertEqual(verificar_fechas(textos, resultado), [])
                for nota in resultado.notas:
                    self.assertTrue(invariante_fechas(nota), nota.crudo)
                    # El crudo son las líneas originales, intactas.
                    self.assertEqual(nota.crudo, "\n".join(textos[k] for k in nota.lineas))
                    if nota.reconocida:
                        reconocidas += 1
                        self.assertEqual(
                            Counter(FECHA_DOF.findall(nota.crudo)),
                            Counter(iso_a_fecha_dof(f) for f in nota.fechas_eventos),
                        )
                    else:
                        no_reconocidas += 1
                        self.assertEqual(nota.eventos, ())
                        self.assertTrue(nota.motivo)
        # Ambos caminos quedan ejercitados con datos reales.
        self.assertGreater(reconocidas, 40)
        self.assertGreaterEqual(no_reconocidas, 5)

    def test_ninguna_fecha_de_las_paginas_queda_sin_cubrir(self) -> None:
        for ley in LEYES:
            lineas, resultado = notas_de(ley)
            textos = [texto for _, _, texto in lineas]
            total = Counter(f for texto in textos for f in FECHA_DOF.findall(texto))
            cubiertas = Counter(f for nota in resultado.notas for f in nota.fechas_en_crudo)
            cubiertas.update(
                f for k in resultado.lineas_con_fecha_fuera_de_nota for f in FECHA_DOF.findall(textos[k])
            )
            with self.subTest(ley=ley):
                self.assertEqual(total, cubiertas)

    def test_el_verificador_detecta_fechas_perdidas_o_inventadas(self) -> None:
        nota, _ = nota_en("CPEUM", 75, 10)
        sin_una = replace(nota, eventos=nota.eventos[:-1])
        self.assertFalse(invariante_fechas(sin_una))
        inventada = replace(
            nota,
            eventos=nota.eventos + (EventoReforma("reformado", "Reformada", ("1800-01-01",)),),
        )
        self.assertFalse(invariante_fechas(inventada))
        no_reconocida_con_eventos = replace(nota, reconocida=False)
        self.assertFalse(invariante_fechas(no_reconocida_con_eventos))

        lineas, resultado = notas_de("CNPP")
        textos = [texto for _, _, texto in lineas]
        perdida = replace(resultado, lineas_con_fecha_fuera_de_nota=())
        self.assertTrue(verificar_fechas(textos, perdida))
        duplicada = replace(resultado, notas=resultado.notas + resultado.notas[:1])
        self.assertTrue(verificar_fechas(textos, duplicada))


class NotasRealesTests(unittest.TestCase):
    def test_nota_partida_en_coma_con_recorrida(self) -> None:
        nota, lineas = nota_en("CPEUM", 75, 10)
        self.assertEqual([(p, i) for p, i, _ in lineas], [(75, 10), (75, 11)])
        self.assertTrue(lineas[0][2].rstrip().endswith(","))
        self.assertTrue(nota.reconocida)
        self.assertEqual(nota.elemento, "Fracción")
        self.assertEqual(
            eventos(nota),
            [
                (
                    "recorrido",
                    ["1928-08-20"],
                    "Fracción",
                    "(antes fracción XXVIII) por derogación de fracciones XXV y XXVI",
                ),
                ("reformado", ["1933-04-29", "2012-08-09"], None, None),
            ],
        )

    def test_nota_partida_tras_la_accion(self) -> None:
        # "… Reformada" / "DOF 13-12-1934, …": la acción queda colgando al final de línea.
        nota, lineas = nota_en("CPEUM", 74, 65)
        self.assertEqual(len(lineas), 2)
        self.assertTrue(nota.reconocida)
        self.assertEqual([e.accion for e in nota.eventos], ["reformado", "recorrido", "reformado"])
        self.assertEqual(len(nota.eventos[-1].fechas), 7)

    def test_segundo_evento_con_su_propio_elemento(self) -> None:
        nota, _ = nota_en("CPEUM", 75, 58)
        self.assertEqual(
            [(e.accion, e.elemento) for e in nota.eventos],
            [("recorrido", "Fracción"), ("reformado", "Fracción")],
        )

    def test_fe_de_erratas_y_derogada(self) -> None:
        nota, _ = nota_en("CPEUM", 71, 18)
        self.assertEqual(
            eventos(nota),
            [("fe_de_erratas", ["1917-02-06"], "fracción", None), ("derogado", ["2005-12-08"], None, None)],
        )

    def test_reforma_con_detalle_tras_dos_puntos(self) -> None:
        nota, _ = nota_en("CPEUM", 43, 46)
        self.assertTrue(nota.reconocida)
        self.assertEqual(eventos(nota), [("reforma", ["1990-06-27"], None, None)])
        self.assertEqual(nota.cola, ": Derogó del artículo el entonces párrafo quinto")

    def test_reforma_con_fechas_dentro_del_detalle_no_se_reconoce(self) -> None:
        nota, lineas = nota_en("CPEUM", 43, 47)
        self.assertEqual(len(lineas), 2)  # paréntesis abierto: sigue en la línea siguiente
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.fechas_en_crudo, ("20-12-2024", "11-06-2013", "27-05-2015"))

    def test_anotacion_de_reformas_multiples_no_se_reconoce(self) -> None:
        nota, lineas = nota_en("CPEUM", 71, 25)
        self.assertIn("(2 reformas)", nota.crudo)
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.eventos, ())
        self.assertEqual(
            list(nota.fechas_en_crudo),
            [f for _, _, texto in lineas for f in FECHA_DOF.findall(texto)],
        )
        self.assertEqual(len(nota.fechas_en_crudo), 13)

    def test_publicado_sin_cambios(self) -> None:
        nota, _ = nota_en("CPEUM", 144, 40)
        self.assertTrue(nota.reconocida)
        self.assertEqual(eventos(nota)[-1], ("publicado", ["2025-04-01"], None, "sin cambios"))

    def test_accion_doble_real_no_se_reconoce(self) -> None:
        # "… Reformado y reubicado DOF 19-12-1978 …" admite dos lecturas (una acción con
        # detalle o dos acciones): se une la línea partida ("Publicado sin" / "cambios")
        # pero la nota no se reconoce y el crudo queda intacto.
        nota, lineas = nota_en("CPEUM", 144, 51)
        self.assertEqual(len(lineas), 2)
        self.assertTrue(lineas[0][2].rstrip().endswith("Publicado sin"))
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.eventos, ())
        self.assertIn("más de una acción", nota.motivo)
        self.assertEqual(len(nota.fechas_en_crudo), 5)

    def test_multas_del_cff_compiladas_por_miscelanea(self) -> None:
        nota, lineas = nota_en("CFF", 148, 25)
        self.assertEqual(len(lineas), 2)
        self.assertEqual(nota.elemento, "Multa de la fracción")
        self.assertEqual(
            eventos(nota),
            [
                ("compilado", ["2022-01-05"], "Multa de la fracción", "por resolución miscelánea fiscal"),
                ("actualizado", ["2022-12-27"], None, None),
                ("compilado", ["2023-12-29", "2024-12-30"], None, None),
                ("actualizado", ["2025-12-28"], None, None),
            ],
        )

    def test_cantidades_partidas_tras_punto(self) -> None:
        # La primera línea termina en punto y la siguiente empieza con "Actualizadas DOF".
        nota, lineas = nota_en("CFF", 30, 61)
        self.assertEqual(len(lineas), 2)
        self.assertEqual(
            [e.accion for e in nota.eventos], ["actualizado", "compilado", "actualizado", "compilado"]
        )

    def test_fecha_de_notificacion_dentro_de_la_nota_no_se_reconoce(self) -> None:
        # "…notificada para efectos legales 25-11-2022" / "y publicada DOF 20-08-2025"
        nota, lineas = nota_en("CNPP", 54, 28)
        self.assertEqual(len(lineas), 2)
        self.assertTrue(lineas[1][2].startswith("y publicada DOF"))
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.fechas_en_crudo, ("25-11-2022", "20-08-2025"))

    def test_denominacion_con_comillas_y_varios_dof_no_se_reconoce(self) -> None:
        nota, lineas = nota_en("CPF", 1, 37)
        self.assertEqual(len(lineas), 3)
        self.assertFalse(nota.reconocida)

    def test_lineas_con_fecha_que_no_son_notas(self) -> None:
        lineas, resultado = notas_de("CNPP")
        fuera = [lineas[k] for k in resultado.lineas_con_fecha_fuera_de_nota]
        self.assertEqual([(p, i) for p, i, _ in fuera], [(1, 14)])
        self.assertTrue(fuera[0][2].startswith("Última reforma publicada DOF 28-11-2025"))


class GramaticaEstrictaTests(unittest.TestCase):
    """Defectos reproducidos por la revisión externa: la acción se tomaba en cualquier
    posición. Notas sintéticas (fechas de 1800, sin atribución a ley alguna)."""

    def test_palabra_sobrante_con_segunda_accion(self) -> None:
        nota = parsear_nota("Párrafo original reformado DOF 01-01-1800")
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.eventos, ())
        self.assertIsNone(nota.elemento)
        self.assertIn("más de una acción", nota.motivo)
        self.assertEqual(nota.fechas_en_crudo, ("01-01-1800",))

    def test_negacion(self) -> None:
        nota = parsear_nota("Párrafo no reformado DOF 01-01-1800")
        self.assertFalse(nota.reconocida)
        self.assertIsNone(nota.elemento)
        self.assertIn("negación", nota.motivo)
        self.assertFalse(parsear_nota("Párrafo reformado (no vigente) DOF 01-01-1800").reconocida)

    def test_accion_no_inmediata_tras_el_elemento(self) -> None:
        for crudo in (
            "Párrafo parcialmente reformado DOF 01-01-1800",
            "Párrafo sintético reformado DOF 01-01-1800",
            "Reformado el párrafo DOF 01-01-1800",
        ):
            with self.subTest(crudo=crudo):
                nota = parsear_nota(crudo)
                self.assertFalse(nota.reconocida)
                self.assertEqual(nota.eventos, ())

    def test_accion_doble_en_evento_posterior(self) -> None:
        nota = parsear_nota("Párrafo reformado DOF 01-01-1800. Reformado y reubicado DOF 02-01-1800")
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.fechas_en_crudo, ("01-01-1800", "02-01-1800"))

    def test_elementos_compuestos_y_designados(self) -> None:
        casos = {
            "Multa de la fracción compilada DOF 01-01-1800": "Multa de la fracción",
            "Párrafo y epígrafe del artículo reformados DOF 01-01-1800": "Párrafo y epígrafe del artículo",
            "Fracción con incisos adicionada DOF 01-01-1800": "Fracción con incisos",
            "Apartado B adicionado DOF 01-01-1800": "Apartado B",
        }
        for crudo, elemento in casos.items():
            with self.subTest(crudo=crudo):
                nota = parsear_nota(crudo)
                self.assertTrue(nota.reconocida, nota.motivo)
                self.assertEqual(nota.elemento, elemento)
                self.assertEqual(nota.eventos[0].detalle, None)


class NotasSinteticasTests(unittest.TestCase):
    def test_fechas_repetidas_se_conservan_como_multiconjunto(self) -> None:
        nota = parsear_nota("Párrafo reformado DOF 01-01-1800, 01-01-1800")
        self.assertTrue(nota.reconocida)
        self.assertEqual(nota.fechas_eventos, ("1800-01-01", "1800-01-01"))

    def test_fecha_imposible_no_se_reconoce(self) -> None:
        nota = parsear_nota("Párrafo reformado DOF 31-02-1800")
        self.assertFalse(nota.reconocida)
        self.assertIn("calendario", nota.motivo)
        self.assertEqual(nota.fechas_en_crudo, ("31-02-1800",))

    def test_fecha_partida_no_se_inventa(self) -> None:
        nota = parsear_nota("Párrafo reformado DOF 01-01-1800, 02-01-\n1800")
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.eventos, ())

    def test_formato_de_fecha_no_estandar_no_se_reconoce(self) -> None:
        for crudo in ("Párrafo reformado DOF 1-01-1800", "Párrafo reformado DOF 01/01/1800"):
            with self.subTest(crudo=crudo):
                self.assertFalse(parsear_nota(crudo).reconocida)

    def test_texto_final_inesperado_no_se_reconoce(self) -> None:
        nota = parsear_nota("Párrafo reformado DOF 01-01-1800. Reformado")
        self.assertFalse(nota.reconocida)
        self.assertIn("texto final", nota.motivo)

    def test_elemento_fuera_de_vocabulario(self) -> None:
        nota = parsear_nota("Renglón sintético reformado DOF 01-01-1800")
        self.assertFalse(nota.reconocida)

    def test_nota_editorial_se_conserva_sin_interpretar(self) -> None:
        resultado = extraer_notas(
            ["Nota: Texto editorial sintético DOF 01-01-1800 de prueba,", "que sigue en otra línea.", ""]
        )
        self.assertEqual(len(resultado.notas), 1)
        nota = resultado.notas[0]
        self.assertEqual(nota.tipo, "nota_editorial")
        self.assertFalse(nota.reconocida)
        self.assertEqual(nota.lineas, (0, 1))
        self.assertEqual(nota.fechas_en_crudo, ("01-01-1800",))

    def test_nota_editorial_no_absorbe_la_nota_siguiente(self) -> None:
        resultado = extraer_notas(
            ["Nota: Texto editorial sintético DOF 01-01-1800.", "Párrafo reformado DOF 02-01-1800", ""]
        )
        self.assertEqual([(n.tipo, n.lineas) for n in resultado.notas], [("nota_editorial", (0,)), ("nota_reforma", (1,))])
        self.assertTrue(resultado.notas[1].reconocida)

    def test_forma_de_nota_sin_dof_no_es_nota(self) -> None:
        resultado = extraer_notas(["Fracción derogada.", ""])
        self.assertEqual(resultado.notas, ())
        self.assertEqual(resultado.lineas_con_fecha_fuera_de_nota, ())

    def test_fecha_partida_en_texto_ordinario_se_advierte(self) -> None:
        resultado = extraer_notas(["Texto sintético (sic DOF 01-01-", "1800) que continúa.", ""])
        self.assertEqual(resultado.notas, ())
        self.assertEqual([a["codigo"] for a in resultado.advertencias], ["fecha_partida"])

    def test_conversion_de_fechas(self) -> None:
        self.assertEqual(fecha_dof_a_iso("04-12-1800"), "1800-12-04")
        self.assertIsNone(fecha_dof_a_iso("31-02-1800"))
        self.assertIsNone(fecha_dof_a_iso("4-12-1800"))
        self.assertEqual(iso_a_fecha_dof("1800-12-04"), "04-12-1800")


if __name__ == "__main__":
    unittest.main()
