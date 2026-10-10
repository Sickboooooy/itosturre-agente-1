"""Corte y etiqueta de la ingesta y re-ingesta por fuente (orden del responsable, 4-oct-2026).

Problema (diagnóstico del coordinador con el corpus real): el corte de "ley" exigía "rt" en
minúscula, así que "ARTICULO 496.-" o "ARTÍCULO 1o.-" no cortaban ni etiquetaban (CFPC, LFPC,
LFPCA y CDN quedaban con artículos del cuerpo dentro del fragmento de otro y sin etiqueta), y
cortaba en remisiones en minúscula al inicio de línea ("artículo 41."). Ahora el corte y la
etiqueta son funciones puras (``itosturre.audit.fragmentacion``) con la MISMA definición de
encabezado auténtico que la auditoría (``evidence._es_autentico``), más la designación sola al
final de su línea de los tratados. Además, ``ingest --fuente`` re-ingesta SOLO una fuente
(borra sus fragmentos, nunca la colección) con respaldo y restauración, y ``--simular``
informa sin escribir.

Todos los textos son SINTÉTICOS (relleno con la forma de los encabezados que trae el PDF);
única excepción: las primeras palabras de los arts. 26, 37 y 102 de la CPEUM y 185 de la LOPJF
tal como las guarda el corpus (las mismas de ``tests/test_vvca_verde_determinista.py``), para
fijar que el apartado que sigue al encabezado queda en el fragmento de su artículo. Corre sin
dependencias (Python 3.11 del CI): la re-ingesta usa ``ColeccionEscribible`` y costuras de
extracción, codificación y subdivisión.
"""
from __future__ import annotations

import contextlib
import io
import json
import logging
import re
import tempfile
import unittest
from array import array
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from itosturre.audit.evidence import (
    FORMA_CIERRE,
    FORMA_FIN_DE_LINEA,
    encabezado_autentico,
    encabezados_autenticos,
    has_suffixed_variant_heading,
    ocurrencias_encabezado,
)
from itosturre.audit.fragmentacion import (
    TIPO_CONTRATO,
    TIPO_LEY,
    TIPO_RESOLUCION,
    cortes,
    detectar_tipo,
    encabezados_de_ley,
    etiqueta_de_encabezado,
    etiqueta_ley,
    fragmentar,
    medir,
    paginas_incompletas,
    verificar_identidad,
)
from tests.vvca_falsos import ColeccionEscribible, importar_opennotebook, vector_a_distancia

ON = importar_opennotebook()

# Encabezado del 1o Bis con el sufijo en la línea siguiente (ver la prueba dedicada).
SUFIJO_PARTIDO = "Artículo 1o.\nBis.- Texto sintético."
# (línea sintética, designación, etiqueta, forma) — encabezados que CORTAN.
CORTAN = [
    ("ARTÍCULO 1o.- Texto sintético.", "1o", "1o", FORMA_CIERRE),
    ("ARTICULO 496.- Texto sintético.", "496", "496", FORMA_CIERRE),
    ("Artículo 1º\nTexto sintético.", "1º", "1º", FORMA_FIN_DE_LINEA),
    ("Artículo 1°\nTexto sintético.", "1°", "1", FORMA_FIN_DE_LINEA),
    ("Artículo 4o.-A.- Texto sintético.", "4o.-A", "4o", FORMA_CIERRE),
    ("Artículo 29-A. Texto sintético.", "29-A", "29-A", FORMA_CIERRE),
    ("Artículo 247 Bis.- Texto sintético.", "247 Bis", "247", FORMA_CIERRE),
    ("Artículo 2o. Bis.- Texto sintético.", "2o. Bis", "2o", FORMA_CIERRE),
    ("Artículo 32-B Quáter.- Texto sintético.", "32-B Quater", "32-B", FORMA_CIERRE),
    ("Art. 1004-A.- Texto sintético.", "1004-A", "1004-A", FORMA_CIERRE),
    ("Artículo 75.Texto sintético pegado al cierre.", "75", "75", FORMA_CIERRE),
    ("Artículo 12.- A falta de texto sintético.", "12", "12", FORMA_CIERRE),
    ("Artículo 10- Texto sintético.", "10", "10", FORMA_CIERRE),
    # Numeración con guion y número menor (LFPCA): designación "58-1" (ronda 2; la etiqueta
    # conserva la regla de siempre, '58-1').
    ("ARTÍCULO 58-1.- Texto sintético.", "58-1", "58-1", FORMA_CIERRE),
    # Número tras el sufijo latino y sufijos más allá de "decies" (ronda 2): etiqueta del
    # número base, como "247 Bis" → '247'.
    ("ARTÍCULO 65 Bis 1.- Texto sintético.", "65 Bis 1", "65", FORMA_CIERRE),
    ("Artículo 67. Terdecies.- Texto sintético.", "67. Terdecies", "67", FORMA_CIERRE),
    ("ARTICULO 63 QUINTUS.- Texto sintético.", "63 QUINTUS", "63", FORMA_CIERRE),
    # Encabezado partido entre líneas (ronda 2): "Artículo" solo y la designación con cierre.
    ("ARTICULO\n508.- Texto sintético.", "508", "508", FORMA_CIERRE),
    ("Artículo\n9. Texto sintético.", "9", "9", FORMA_CIERRE),
    ("Arti\u0301culo 115 bis. Texto sintético.", "115 bis", "115", FORMA_CIERRE),
    ("Artículo 64.-", "64", "64", FORMA_CIERRE),
    ("Artículo 9:  Texto sintético.", "9", "9", FORMA_CIERRE),
    (SUFIJO_PARTIDO, "1o", "1o", FORMA_CIERRE),
    # Tratados (PIDCP, CADH, CDN): la designación sola al final de su línea.
    ("Artículo 51\n1. Texto sintético.", "51", "51", FORMA_FIN_DE_LINEA),
    ("ARTÍCULO 1 \nTexto sintético.", "1", "1", FORMA_FIN_DE_LINEA),
    ("Artículo 5  \nTexto sintético.", "5", "5", FORMA_FIN_DE_LINEA),
]
# Líneas que NO cortan: remisión en minúscula, cita capitalizada con coma, mención sin cierre,
# sufijo seguido de coma, oración partida, encabezado en palabra.
NO_CORTAN = [
    "artículo 41. Texto sintético de una remisión al inicio de línea.",
    "Artículo 2o., fracción I, inciso H, texto sintético.",
    "Artículo 51 de esta Ley sintética se aplica.",
    "Artículo 4o.-A, fracción II, texto sintético.",
    "Artículo 5.-, fracción sintética.",
    "Artículo 247 Bis, segundo párrafo sintético.",
    "Texto sintético conforme al\nArtículo 51\nde esta Ley.",
    "Texto sintético conforme al\nArtículo 51\n, párrafo sintético.",
    "ARTÍCULO 7 texto sintético sin cierre.",
    "ARTÍCULO PRIMERO.- Texto sintético transitorio.",
    "Arts. 5.- Texto sintético.",
]
# Primeras palabras reales de CPEUM 26, 37, 102 y LOPJF 185 (ver el docstring).
APARTADOS = [
    ("Artículo 26.\nA. El Estado organizará un sistema", "26"),
    ("Artículo 37.\nA) Ningún mexicano por nacimiento", "37"),
    ("Artículo 102.\nA. El Ministerio Público de la Federación", "102"),
    ("Artículo 185.\nA efecto de preservar los principios", "185"),
]
# Regla de etiqueta anterior (main@59e8f19), para fijar la compatibilidad.
_ETIQUETA_ANTERIOR = re.compile(r'\s*[Aa]rt[íi]?(?:culo)?s?\.?\s+(\d+[\w\-]*)')


def _sin_division(texto: str) -> list[str]:
    return [texto]


class EncabezadoAutenticoTests(unittest.TestCase):
    """Qué líneas son encabezado (corte) y con qué designación, etiqueta y forma."""

    def test_cortan(self) -> None:
        # Tratados (criterio del responsable, 4-oct-2026, opción A): la forma sin cierre solo
        # corta en un tratado registrado (``fin_de_linea=True``); en una ley nacional (por
        # omisión) el cierre es obligatorio.
        for linea, designacion, etiqueta, forma in CORTAN:
            with self.subTest(linea=linea):
                (encabezado,) = encabezados_de_ley(linea, fin_de_linea=True)
                self.assertEqual(encabezado["inicio"], 0)
                self.assertEqual(encabezado["designacion"], designacion)
                self.assertEqual(encabezado["etiqueta"], etiqueta)
                self.assertEqual(encabezado["forma"], forma)
                self.assertEqual(etiqueta_ley(linea, fin_de_linea=True), etiqueta)
                if forma == FORMA_FIN_DE_LINEA:
                    self.assertEqual(encabezados_de_ley(linea), [])
                    self.assertEqual(etiqueta_ley(linea), "")
                else:
                    self.assertEqual(encabezados_de_ley(linea), [encabezado])
                    self.assertEqual(etiqueta_ley(linea), etiqueta)

    def test_no_cortan(self) -> None:
        for linea in NO_CORTAN:
            for tratado in (False, True):
                with self.subTest(linea=linea, tratado=tratado):
                    self.assertEqual(encabezados_de_ley(linea, fin_de_linea=tratado), [])
                    self.assertEqual(etiqueta_ley(linea, fin_de_linea=tratado), "")

    def test_apartado_tras_el_encabezado_no_es_sufijo(self) -> None:
        for linea, etiqueta in APARTADOS:
            with self.subTest(linea=linea):
                (encabezado,) = encabezados_de_ley(linea)
                self.assertEqual(encabezado["etiqueta"], etiqueta)
                self.assertEqual(encabezado["designacion"], etiqueta)

    def test_fin_de_linea_solo_para_la_ingesta(self) -> None:
        # La auditoría no acepta "Artículo 51" sin cierre como encabezado exacto; la ingesta
        # sí corta ahí (tratados). Con cierre, ambas formas coinciden.
        texto = "Artículo 51\n1. Texto sintético.\nArtículo 52.- Texto sintético."
        self.assertEqual([h["designacion"] for h in encabezados_autenticos(texto)], ["52"])
        self.assertEqual(
            [(h["designacion"], h["forma"]) for h in encabezados_autenticos(texto, fin_de_linea=True)],
            [("51", FORMA_FIN_DE_LINEA), ("52", FORMA_CIERRE)],
        )

    def test_misma_definicion_que_la_auditoria(self) -> None:
        # Todo encabezado con cierre que corta la ingesta es, para la auditoría, el encabezado
        # AUTÉNTICO de su designación en esa línea; y ninguna línea que no corta lo es.
        for linea, designacion, _etiqueta, forma in CORTAN:
            if forma != FORMA_CIERRE or linea == SUFIJO_PARTIDO:
                continue
            with self.subTest(linea=linea):
                self.assertTrue(encabezado_autentico(linea, designacion))
        for linea, designacion in (
            ("artículo 41. Texto sintético de una remisión.", "41"),
            ("Artículo 2o., fracción I, texto sintético.", "2o"),
            ("Artículo 4o.-A, fracción II, texto sintético.", "4o"),
            ("Artículo 4o.-A, fracción II, texto sintético.", "4o.-A"),
            ("Artículo 247 Bis, párrafo sintético.", "247"),
        ):
            with self.subTest(linea=linea, designacion=designacion):
                self.assertFalse(encabezado_autentico(linea, designacion))
                self.assertEqual(encabezados_autenticos(linea), [])

    def test_sufijo_partido_corta_y_la_auditoria_lo_ve_como_variante(self) -> None:
        # "Artículo 1o.\nBis.-" es el encabezado del 1o Bis con el sufijo en la línea
        # siguiente: la ingesta corta ahí (como antes, etiqueta '1o', igual que "1o Bis") para
        # no pegar el 1o Bis al fragmento del 1o; la auditoría no lo acepta como encabezado del
        # 1o, sino como su variante con sufijo (``has_suffixed_variant_heading``).
        self.assertEqual(etiqueta_ley(SUFIJO_PARTIDO), "1o")
        self.assertFalse(encabezado_autentico(SUFIJO_PARTIDO, "1o"))
        self.assertTrue(has_suffixed_variant_heading(SUFIJO_PARTIDO, "1o"))

    def test_ocurrencias_conservan_su_comportamiento(self) -> None:
        # La autenticidad de ``ocurrencias_encabezado`` ahora la decide ``_es_autentico``; mismo
        # resultado que antes: remisión en minúscula y cita con coma no son auténticas.
        texto = ("Texto sintético.\nartículo 41. Remisión sintética.\n"
                 "Artículo 41, fracción I, sintética.\nArtículo 41. Texto sintético.")
        self.assertEqual(
            [o["autentico"] for o in ocurrencias_encabezado(texto, "41")], [False, True]
        )


class EtiquetaTests(unittest.TestCase):
    """Etiquetas compatibles con las anteriores y con ``_article_candidates``."""

    def test_linea_a_etiqueta(self) -> None:
        for linea, etiqueta in (
            ("ARTÍCULO 1o.- T", "1o"), ("ARTICULO 496.- T", "496"), ("Artículo 1º", "1º"),
            ("Artículo 1°", "1"), ("Artículo 4o.-A.- T", "4o"), ("Artículo 29-A. T", "29-A"),
            ("Artículo 247 Bis.- T", "247"), ("Artículo 20.- A. T", "20"),
            ("Artículo 10- T", "10"), ("ARTÍCULO 58-1.- T", "58-1"), ("  Art. 1004-A.- T", "1004-A"),
            # Acento descompuesto ("i" + U+0301), como lo trae algún PDF del corpus.
            ("Arti\u0301culo 115 bis. T", "115"),
            # Ronda 2: misma caja que los candidatos ("29-a" → "29-A"; el ordinal se conserva).
            ("Artículo 29-a.- T", "29-A"), ("Artículo 247bis.- T", "247BIS"),
            ("ARTICULO\n508.- T", "508"),
            ("Texto sin encabezado", ""), ("", ""),
        ):
            with self.subTest(linea=linea):
                self.assertEqual(etiqueta_de_encabezado(linea), etiqueta)

    def test_igual_que_la_regla_anterior_con_minuscula(self) -> None:
        # Donde el cortador anterior sí reconocía el encabezado ("Artículo", "Art."), la
        # etiqueta no cambia (salvo el guion de cierre, que ya no se pega: "10-" → "10").
        for pieza in (
            "Artículo 5.- Texto sintético.", "Artículo 1o.- Texto sintético.",
            "Artículo 4o.-A.- Texto sintético.", "Artículo 29-A. Texto sintético.",
            "Artículo 247 Bis.- Texto sintético.", "Art. 1004-A.- Texto sintético.",
            "Artículo 1º\nTexto sintético.", "Artículo 1°.- Texto sintético.",
            "Artículo 51\n1. Texto sintético.", "Artículo 58-1.- Texto sintético.",
        ):
            with self.subTest(pieza=pieza):
                # En un tratado (la forma sin cierre solo corta en los registrados).
                self.assertEqual(etiqueta_ley(pieza, fin_de_linea=True),
                                 _ETIQUETA_ANTERIOR.match(pieza).group(1))
        self.assertEqual(_ETIQUETA_ANTERIOR.match("Artículo 10- Texto.").group(1), "10-")
        self.assertEqual(etiqueta_ley("Artículo 10- Texto sintético."), "10")

    def test_compatibles_con_article_candidates(self) -> None:
        for cita, encabezado in (
            ("1", "ARTÍCULO 1o.- Texto sintético."), ("1o", "ARTÍCULO 1o.- Texto sintético."),
            ("1", "Artículo 1º\nTexto sintético."), ("1", "Artículo 1°\nTexto sintético."),
            ("496", "ARTICULO 496.- Texto sintético."), ("4o.-A", "Artículo 4o.-A.- Texto."),
            ("4-A", "Artículo 4o.-A.- Texto sintético."), ("29-A", "Artículo 29-A. Texto."),
            ("247 Bis", "Artículo 247 Bis.- Texto sintético."), ("51", "ARTÍCULO 51 \nTexto."),
        ):
            with self.subTest(cita=cita, encabezado=encabezado):
                self.assertIn(etiqueta_ley(encabezado, fin_de_linea=True),
                              ON._article_candidates(cita))


def _paginas(*textos: str) -> list[dict]:
    return [{"page": n, "text": t} for n, t in enumerate(textos, 1)]


class FragmentarTests(unittest.TestCase):
    """``fragmentar``: páginas → fragmentos con etiqueta y página (ley sintética)."""

    def _fragmentos(self, *textos: str, max_caracteres: int = 2000, subdividir=_sin_division,
                    fin_de_linea: bool = False):
        return fragmentar(_paginas(*textos), max_caracteres=max_caracteres, subdividir=subdividir,
                          fin_de_linea=fin_de_linea)

    def test_mayusculas_cortan_y_la_remision_no(self) -> None:
        resultado = self._fragmentos(
            "LEY SINTÉTICA\nTexto sintético del encabezado.\n"
            "ARTÍCULO 1o.- Texto sintético que remite al\n"
            "artículo 41. de otra ley sintética.\n"
            "ARTICULO 2.- Texto sintético.\n"
            "ARTÍCULO 3o.-A.- Texto sintético.\n"
        )
        self.assertEqual(resultado.tipo, TIPO_LEY)
        self.assertEqual([f.etiqueta for f in resultado.fragmentos], ["", "1o", "2", "3o"])
        self.assertIn("artículo 41. de otra ley", resultado.fragmentos[1].texto)
        self.assertTrue(resultado.fragmentos[2].texto.startswith("ARTICULO 2.-"))

    def test_apartados_siguen_en_su_fragmento(self) -> None:
        for linea, etiqueta in APARTADOS:
            with self.subTest(linea=linea):
                resultado = self._fragmentos(
                    f"LEY SINTÉTICA\n{linea} (continúa texto sintético).\n"
                    "Artículo 900.- Texto sintético.\n"
                )
                self.assertEqual([f.etiqueta for f in resultado.fragmentos], ["", etiqueta, "900"])
                self.assertIn(linea.split("\n")[1], resultado.fragmentos[1].texto)

    def test_tratado_con_encabezado_al_final_de_la_linea(self) -> None:
        texto = (
            "CONVENCIÓN SINTÉTICA\nPREÁMBULO\nTexto sintético.\n"
            "PARTE I\nARTÍCULO 1 \nPara los efectos sintéticos.\n"
            "ARTÍCULO 2 \n1. Texto sintético que cita el\nartículo 1\nde esta Convención.\n"
        )
        resultado = self._fragmentos(texto, fin_de_linea=True)
        self.assertEqual([f.etiqueta for f in resultado.fragmentos], ["", "1", "2"])
        self.assertIn("artículo 1\nde esta Convención", resultado.fragmentos[2].texto)
        # Ronda 2 (adjudicado): en una ley nacional (no registrada como tratado) la forma sin
        # cierre no corta (las líneas "Artículo N" de la Declaratoria del Código Civil de
        # Jalisco ya no cortan).
        self.assertEqual([f.etiqueta for f in self._fragmentos(texto).fragmentos], [""])
        ley = self._fragmentos(
            "CÓDIGO SINTÉTICO\nArtículo 1.- Texto sintético.\nTRANSITORIOS\nDECLARATORIA\n"
            "Artículo 1 \nLa familia sintética es la comunidad de prueba.\n"
            "Artículo 2 \nTexto sintético de la declaratoria.\n"
        )
        self.assertEqual([f.etiqueta for f in ley.fragmentos], ["", "1", ""])
        self.assertIn("Artículo 2 \nTexto sintético de la declaratoria", ley.fragmentos[2].texto)

    def test_pagina_del_encabezado_al_inicio_de_pagina(self) -> None:
        # Antes el corte caía en el salto de línea previo y el fragmento quedaba con la página
        # anterior; ahora es la página de la línea del encabezado.
        resultado = self._fragmentos(
            "LEY SINTÉTICA\nArtículo 1.- Texto sintético.", "Artículo 2.- Texto sintético."
        )
        self.assertEqual(
            [(f.etiqueta, f.pagina) for f in resultado.fragmentos], [("", 1), ("1", 1), ("2", 2)]
        )

    def test_subfragmentos_con_prefijo(self) -> None:
        largo = "Artículo 5.- " + "Texto sintético largo. " * 20
        resultado = self._fragmentos(
            "LEY SINTÉTICA\n" + largo + "\nArtículo 6.- Texto sintético.",
            max_caracteres=100,
            subdividir=lambda texto: [texto[i:i + 90] for i in range(0, len(texto), 90)],
        )
        quinto = [f for f in resultado.fragmentos if f.etiqueta == "5"]
        self.assertGreater(len(quinto), 1)
        self.assertTrue(all(f.texto.startswith("[LEY 5]\n") for f in quinto))
        self.assertTrue(quinto[0].texto.startswith("[LEY 5]\nArtículo 5.-"))

    def test_contrato_sin_cambios(self) -> None:
        resultado = self._fragmentos(
            "CONTRATO SINTÉTICO\nCláusula Primera. Texto sintético.\n"
            "Cláusula Segunda. Texto sintético.\nCláusula Tercera. Texto sintético.\n"
        )
        self.assertEqual(resultado.tipo, TIPO_CONTRATO)
        self.assertEqual(
            [f.etiqueta for f in resultado.fragmentos], ["", "Primera", "Segunda", "Tercera"]
        )

    def test_detectar_tipo_cuenta_los_encabezados_en_mayusculas(self) -> None:
        # Antes "ARTÍCULO N.-" no contaba y dos CONSIDERANDO bastaban para "resolucion".
        texto = (
            "\nCONSIDERANDO sintético.\nCONSIDERANDO sintético.\n"
            "ARTÍCULO 1.- Texto.\nARTÍCULO 2.- Texto.\nARTÍCULO 3.- Texto.\n"
        )
        self.assertEqual(detectar_tipo(texto), TIPO_LEY)
        self.assertEqual(detectar_tipo("\nCONSIDERANDO uno.\nCONSIDERANDO dos.\n"), TIPO_RESOLUCION)
        self.assertEqual(cortes("Texto.\nARTÍCULO 1.- Uno.\nartículo 2. Remisión.", TIPO_LEY), [7])


class MedirTests(unittest.TestCase):
    """``medir``: cobertura de los encabezados y etiquetas de remisión."""

    TEXTO = (
        "LEY SINTÉTICA\nARTÍCULO 1o.- Texto sintético que remite al\n"
        "artículo 41. de otra ley sintética.\nARTICULO 2.- Texto sintético.\n"
        "TRANSITORIOS\nARTÍCULO 1o.- Texto sintético transitorio."
    )

    def test_cortador_anterior_frente_al_actual(self) -> None:
        corte = self.TEXTO.index("\nartículo 41.")
        anterior = [(self.TEXTO[:corte].strip(), ""), (self.TEXTO[corte:].strip(), "41")]
        antes = medir(self.TEXTO, anterior)
        self.assertEqual(
            (antes["encabezados"], antes["encabezados_cuerpo"], antes["cubiertos_cuerpo"],
             antes["cobertura"], antes["etiqueta_sin_encabezado"]),
            (3, 2, 0, 0.0, 1),
        )
        actual = fragmentar(
            _paginas(self.TEXTO), max_caracteres=2000, subdividir=_sin_division
        ).fragmentos
        despues = medir(self.TEXTO, [(f.texto, f.etiqueta) for f in actual])
        self.assertEqual(
            (despues["cubiertos_cuerpo"], despues["cobertura"], despues["cobertura_documento"],
             despues["etiqueta_sin_encabezado"], despues["no_ubicados"]),
            (2, 100.0, 100.0, 0, 0),
        )

    def test_fragmento_que_no_esta_en_el_pdf(self) -> None:
        self.assertEqual(medir(self.TEXTO, [("Otro texto sintético.", "")])["no_ubicados"], 1)


# ── Re-ingesta por fuente ───────────────────────────────────────────────────────────────

LEY_A = "LEY A.pdf"
LEY_B = "LEY B.pdf"
_RELLENO = "Texto sintético de relleno para que la página tenga cuerpo suficiente. " * 3
PAGINAS = {
    LEY_A: _paginas(
        "LEY SINTÉTICA A\nTexto sintético del encabezado.\n" + _RELLENO + "\n"
        "ARTÍCULO 1o.- Texto sintético que remite al\nartículo 41. de otra ley sintética.\n",
        "ARTICULO 2.- Texto sintético.\nARTÍCULO 3o.-A.- Texto sintético.\n"
        "TRANSITORIOS\nARTÍCULO PRIMERO.- Texto sintético transitorio.",
    ),
    LEY_B: _paginas("LEY SINTÉTICA B\nArtículo 1.- Texto sintético.\nArtículo 2.- Texto."),
}
VECTOR_VIEJO = vector_a_distancia(0, 0.3)
VECTOR_NUEVO = vector_a_distancia(1, 0.1)
# Fragmentos nuevos de LEY A: preámbulo, 1o, 2, 3o y, desde la ronda 2, la línea TRANSITORIOS.
NUEVOS_A = [("", "1", "0"), ("1o", "1", "1"), ("2", "2", "2"), ("3o", "2", "3"), ("", "2", "4")]


def _meta(fuente: str, articulo: str, pagina: str, indice: int) -> dict:
    return {"source": fuente, "law": Path(fuente).stem, "article": articulo, "page": pagina,
            "chunk_index": str(indice), "doc_type": "ley"}


def _texto(fuente: str) -> str:
    return "\n\n".join(p["text"] for p in PAGINAS[fuente])


def _float32(vector) -> list:
    return list(array("f", map(float, vector)))


class ReingestaBase(unittest.TestCase):
    def setUp(self) -> None:
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.carpeta = Path(temporal.name) / "pdfs"
        self.carpeta.mkdir()
        self.respaldos = Path(temporal.name) / "respaldos"
        for nombre in (LEY_A, LEY_B, "ActaNacimiento sintética.pdf", "notas.txt"):
            (self.carpeta / nombre).write_bytes(b"")
        for nombre, valor in (("INGEST_ALLOWED_BASE", str(self.carpeta)),
                              ("CHROMA_PATH", str(Path(temporal.name) / "chroma"))):
            parche = mock.patch.object(ON, nombre, valor)
            parche.start()
            self.addCleanup(parche.stop)
        self.coleccion = self._coleccion()
        self.original = self.coleccion.filas()
        self.codificados: list[list[str]] = []
        self.extraer = lambda ruta: PAGINAS[ruta.name]

    def _coleccion(self, **kwargs) -> ColeccionEscribible:
        coleccion = ColeccionEscribible(**kwargs)
        # Índice "anterior" de LEY A: el corte viejo (sin las MAYÚSCULAS, con la remisión).
        texto = _texto(LEY_A)
        corte = texto.index("\nartículo 41.")
        for indice, (documento, articulo) in enumerate(
            [(texto[:corte].strip(), ""), (texto[corte:].strip(), "41")]
        ):
            coleccion.agregar_fila(f"LEY A_chunk_{indice}", documento,
                                   _meta(LEY_A, articulo, "1", indice), VECTOR_VIEJO)
        for indice, (documento, articulo) in enumerate(
            [("LEY SINTÉTICA B", ""), ("Artículo 1.- Texto sintético.", "1"),
             ("Artículo 2.- Texto.", "2")]
        ):
            coleccion.agregar_fila(f"LEY B_chunk_{indice}", documento,
                                   _meta(LEY_B, articulo, "1", indice), VECTOR_VIEJO)
        return coleccion

    def codificar(self, textos: list[str]) -> list[list[float]]:
        self.codificados.append(list(textos))
        return [VECTOR_NUEVO for _ in textos]

    def reingestar(self, fuentes, **kwargs):
        opciones = {
            "collection": self.coleccion, "codificar": self.codificar,
            "extraer": lambda ruta: self.extraer(ruta), "subdividir": _sin_division,
            "respaldos_dir": str(self.respaldos),
        }
        opciones.update(kwargs)
        return ON.reingestar_fuentes(str(self.carpeta), fuentes, **opciones)

    def escrituras(self) -> list[str]:
        return [nombre for nombre, _ in self.coleccion.llamadas if nombre in ("add", "delete")]

    def filas_de(self, fuente: str) -> list:
        return [f for f in self.coleccion.filas() if f[2]["source"] == fuente]


class ReingestaPorFuenteTests(ReingestaBase):

    def test_se_niega_sin_fuente(self) -> None:
        for fuentes in ([], ()):
            with self.subTest(fuentes=fuentes), self.assertRaisesRegex(ValueError, "al menos una"):
                self.reingestar(fuentes)
        self.assertEqual(self.escrituras(), [])
        self.assertEqual(self.coleccion.filas(), self.original)

    def test_valida_cada_fuente_antes_de_tocar_nada(self) -> None:
        for fuentes, motivo in (
            ([LEY_A, "NO EXISTE.pdf"], "No existe"),
            (["ley a.pdf"], "nombre exacto"),            # otra caja: no es el 'source'
            ([f"sub/{LEY_A}"], "solo el nombre"),
            (["..", LEY_A], "solo el nombre"),
            (["ActaNacimiento sintética.pdf"], "no es un PDF legal"),
            (["notas.txt"], "no es un PDF legal"),
            ([LEY_A, LEY_A], "repetida"),
        ):
            with self.subTest(fuentes=fuentes), self.assertRaisesRegex(ValueError, motivo):
                self.reingestar(fuentes)
        self.assertEqual(self.escrituras(), [])
        self.assertEqual(self.coleccion.filas(), self.original)

    def test_carpeta_fuera_de_la_base_permitida(self) -> None:
        with mock.patch.object(ON, "INGEST_ALLOWED_BASE", str(self.carpeta / "otra")), \
                self.assertRaisesRegex(ValueError, "Path traversal"):
            self.reingestar([LEY_A])
        self.assertEqual(self.escrituras(), [])

    def test_borra_solo_la_fuente_pedida(self) -> None:
        (informe,) = self.reingestar([LEY_A])
        self.assertEqual(self.filas_de(LEY_B), [f for f in self.original if f[2]["source"] == LEY_B])
        nuevos = self.filas_de(LEY_A)
        self.assertEqual([f[3] for f in nuevos], [VECTOR_NUEVO] * len(nuevos))
        self.assertNotIn("41", [f[2]["article"] for f in nuevos])
        # Borrado por fuente, nunca de la colección ni por otros filtros.
        borrados = [datos for nombre, datos in self.coleccion.llamadas if nombre == "delete"]
        self.assertEqual(borrados, [{"ids": None, "where": {"source": LEY_A}}])
        self.assertEqual(informe["antes"]["fragmentos"], 2)
        self.assertEqual(informe["despues"]["fragmentos"], len(NUEVOS_A))
        self.assertEqual((informe["antes"]["cobertura"], informe["despues"]["cobertura"]), (0.0, 100.0))
        self.assertEqual(informe["etiquetas_perdidas"], 1)        # la remisión "41"
        self.assertFalse(informe["simulacion"])
        self.assertTrue(informe["identidad"]["coincide"])
        self.assertEqual((informe["extraccion_incompleta"], informe["rechazo"]), ([], []))

    def test_ids_y_metadatos_coherentes(self) -> None:
        self.reingestar([LEY_A])
        nuevos = self.filas_de(LEY_A)
        self.assertEqual([f[0] for f in nuevos], [f"LEY A_chunk_{i}" for i in range(len(NUEVOS_A))])
        self.assertEqual(
            [(f[2]["article"], f[2]["page"], f[2]["chunk_index"]) for f in nuevos], NUEVOS_A
        )
        for _, documento, metadata, _ in nuevos:
            self.assertEqual(set(metadata), {"source", "law", "article", "page", "chunk_index",
                                             "doc_type"})
            self.assertEqual((metadata["source"], metadata["law"], metadata["doc_type"]),
                             (LEY_A, "LEY A", "ley"))
        self.assertTrue(nuevos[2][1].startswith("ARTICULO 2.-"))
        # Ronda 2: la línea TRANSITORIOS abre su propio fragmento.
        self.assertTrue(nuevos[4][1].startswith("TRANSITORIOS"))
        self.assertNotIn("TRANSITORIOS", nuevos[3][1])
        # Los vectores se calcularon antes de cualquier escritura, sobre los mismos textos.
        self.assertEqual(sum(self.codificados, []), [f[1] for f in nuevos])

    def test_nunca_mezcla_viejos_y_nuevos(self) -> None:
        # El índice tenía MÁS fragmentos de la misma fuente (otro corte del mismo texto) que
        # los nuevos: no queda ninguno viejo.
        coleccion = ColeccionEscribible()
        lineas = [l for l in _texto(LEY_A).split("\n") if l.strip()]
        for indice, linea in enumerate(lineas):
            coleccion.agregar_fila(f"LEY A_chunk_{indice}", linea,
                                   _meta(LEY_A, "", "1", indice), VECTOR_VIEJO)
        self.assertGreater(len(lineas), len(NUEVOS_A))
        self.coleccion = coleccion
        self.reingestar([LEY_A])
        filas = self.coleccion.filas()
        self.assertEqual([f[0] for f in filas], [f"LEY A_chunk_{i}" for i in range(len(NUEVOS_A))])
        self.assertEqual([f[3] for f in filas], [VECTOR_NUEVO] * len(NUEVOS_A))

    def test_simular_no_escribe(self) -> None:
        (informe,) = self.reingestar([LEY_A], simular=True, codificar=None)
        self.assertEqual(self.escrituras(), [])
        self.assertEqual(self.codificados, [])
        self.assertEqual(self.coleccion.filas(), self.original)
        self.assertFalse(self.respaldos.exists())          # tampoco escribe respaldos
        self.assertTrue(informe["simulacion"])
        self.assertEqual(
            (informe["antes"]["fragmentos"], informe["despues"]["fragmentos"],
             informe["antes"]["etiquetados"], informe["despues"]["etiquetados"],
             informe["antes"]["etiqueta_sin_encabezado"]),
            (2, len(NUEVOS_A), 1, 3, 1),
        )
        self.assertIn("simulación: el índice no se modificó", ON.formato_informe_reingesta([informe]))

    def test_restaura_si_falla_la_escritura(self) -> None:
        for lote, falla in ((50, 1), (1, 3)):   # primer lote, o a mitad de varios lotes
            with self.subTest(lote=lote, falla=falla):
                self.coleccion = self._coleccion(fallar_add_en=falla)
                original = self.coleccion.filas()
                with mock.patch.object(ON, "LOTE_REINGESTA", lote), \
                        self.assertRaisesRegex(ON.ReingestaFallida, "se restauraron los 2"):
                    self.reingestar([LEY_A])
                self.assertEqual(sorted(self.coleccion.filas()), sorted(original))

    def test_falla_al_codificar_sin_tocar_el_indice(self) -> None:
        def codificar(_textos):
            raise RuntimeError("modelo no disponible (simulación)")
        with self.assertRaisesRegex(RuntimeError, "modelo no disponible"):
            self.reingestar([LEY_A], codificar=codificar)
        self.assertEqual(self.escrituras(), [])
        self.assertEqual(self.coleccion.filas(), self.original)

    def test_pdf_sin_texto(self) -> None:
        with self.assertRaisesRegex(ON.ReingestaRechazada, "no dio texto"):
            self.reingestar([LEY_A], extraer=lambda _ruta: [])
        self.assertEqual(self.escrituras(), [])

    def test_varias_fuentes_en_orden(self) -> None:
        informes = self.reingestar([LEY_B, LEY_A])
        self.assertEqual([i["fuente"] for i in informes], [LEY_B, LEY_A])
        self.assertEqual(
            [datos["where"] for nombre, datos in self.coleccion.llamadas if nombre == "delete"],
            [{"source": LEY_B}, {"source": LEY_A}],
        )


class SeguridadReingestaTests(ReingestaBase):
    """Ronda 2 (adjudicado): identidad, extracción completa, colisiones antes de borrar y
    respaldo durable con ``--restaurar``."""

    # ── (a) identidad ───────────────────────────────────────────────────────────────────
    def test_otro_documento_se_rechaza_sin_tocar_nada(self) -> None:
        otra = _paginas("OTRA LEY SINTÉTICA\n" + _RELLENO + "\nArtículo 1.- Texto sintético.")
        with self.assertRaisesRegex(ON.ReingestaRechazada, "otro documento: el título"):
            self.reingestar([LEY_A], extraer=lambda _ruta: otra)
        self.assertEqual(self.escrituras(), [])
        self.assertEqual(self.coleccion.filas(), self.original)
        self.assertFalse(self.respaldos.exists())
        # Con --simular el rechazo se informa sin lanzar.
        (informe,) = self.reingestar([LEY_A], extraer=lambda _ruta: otra, simular=True)
        self.assertTrue(informe["rechazo"])
        self.assertIn("⛔ otro documento", ON.formato_informe_reingesta([informe]))

    def test_identidad_por_designaciones(self) -> None:
        cuerpo = "LEY SINTÉTICA C\n" + "".join(f"Artículo {n}.- Texto sintético.\n" for n in range(1, 21))
        mismo = verificar_identidad([cuerpo], cuerpo + "TRANSITORIOS\n")
        self.assertEqual((mismo["coincide"], mismo["criterio"], mismo["solapamiento"]),
                         (True, "designaciones", 1.0))
        corto = "LEY SINTÉTICA C\n" + "".join(f"Artículo {n}.- Texto.\n" for n in range(1, 16))
        distinto = verificar_identidad([cuerpo], corto)
        self.assertEqual((distinto["coincide"], distinto["solapamiento"]), (False, 0.75))
        self.assertIn("15 de 20 designaciones", distinto["motivo"])
        # Sin fragmentos indexados: fuente nueva.
        self.assertEqual(verificar_identidad([], cuerpo)["criterio"], "fuente_nueva")
        # Pocas designaciones: decide el texto de los fragmentos indexados.
        self.assertEqual(verificar_identidad(["LEY X\nUno.", "Dos."], "LEY X\nUno.\nDos.")["criterio"],
                         "texto")

    def test_titulo_confirmado_solo_omite_el_titulo(self) -> None:
        # Identidad confirmada por el operador (10-oct-2026): el PDF oficial antepone el
        # preámbulo del decreto y la primera línea ya no es el título; decide el contenido.
        cuerpo = "LEY SINTÉTICA C\n" + "".join(f"Artículo {n}.- Texto sintético.\n" for n in range(1, 21))
        preambulo = "Al margen un sello sintético del decreto.\n" + cuerpo
        self.assertEqual(verificar_identidad([cuerpo], preambulo)["criterio"], "titulo")
        confirmada = verificar_identidad([cuerpo], preambulo, titulo_confirmado=True)
        self.assertEqual(
            (confirmada["coincide"], confirmada["criterio"], confirmada["solapamiento"],
             confirmada["titulo_confirmado"]),
            (True, "designaciones", 1.0, True))
        self.assertEqual((confirmada["titulo_indexado"], confirmada["titulo_nuevo"]),
                         ("ley sintetica c", "al margen un sello sintetico del decreto"))
        # El umbral no se relaja: 15 de 20 designaciones no bastan aunque haya confirmación.
        corto = "Al margen un sello sintético.\n" + "".join(
            f"Artículo {n}.- Texto.\n" for n in range(1, 16))
        distinto = verificar_identidad([cuerpo], corto, titulo_confirmado=True)
        self.assertEqual((distinto["coincide"], distinto["solapamiento"]), (False, 0.75))
        self.assertIn("15 de 20 designaciones", distinto["motivo"])
        # Con el mismo título la confirmación no se usa ni se registra.
        mismo = verificar_identidad([cuerpo], cuerpo, titulo_confirmado=True)
        self.assertTrue(mismo["coincide"])
        self.assertNotIn("titulo_confirmado", mismo)

    def test_identidad_confirmada_por_fuente(self) -> None:
        con_preambulo = [
            {"page": 1, "text": "Al margen un sello sintético del decreto.\n"
                                + PAGINAS[LEY_A][0]["text"]},
        ] + PAGINAS[LEY_A][1:]
        with self.assertRaisesRegex(ON.ReingestaRechazada, "otro documento: el título"):
            self.reingestar([LEY_A], extraer=lambda _ruta: con_preambulo)
        self.assertEqual(self.escrituras(), [])
        # La confirmación tiene que nombrar una de las fuentes a re-ingestar.
        with self.assertRaisesRegex(ValueError, "sin su --fuente"):
            self.reingestar([LEY_A], extraer=lambda _ruta: con_preambulo,
                            identidad_confirmada=[LEY_B])
        # Contenido incompleto: se rechaza aunque el operador confirme la identidad.
        with self.assertRaisesRegex(ON.ReingestaRechazada, "otro documento: solo"):
            self.reingestar([LEY_A], extraer=lambda _ruta: con_preambulo[:1],
                            identidad_confirmada=[LEY_A])
        self.assertEqual(self.escrituras(), [])
        (informe,) = self.reingestar([LEY_A], extraer=lambda _ruta: con_preambulo,
                                     identidad_confirmada=[LEY_A])
        identidad = informe["identidad"]
        self.assertEqual(
            (identidad["coincide"], identidad["criterio"], identidad["solapamiento"],
             identidad["titulo_confirmado"]),
            (True, "texto", 1.0, True))
        self.assertEqual(informe["rechazo"], [])
        self.assertTrue(self.escrituras())
        texto = ON.formato_informe_reingesta([informe])
        self.assertIn("título confirmado por el operador: 'al margen un sello sintetico del "
                      "decreto' frente a 'ley sintetica a'", texto)

    # ── (b) extracción completa ─────────────────────────────────────────────────────────
    def test_extraccion_incompleta_antes_de_la_frontera(self) -> None:
        completa = PAGINAS[LEY_A]
        self.assertEqual(paginas_incompletas(completa), [])
        corta = [completa[0], {"page": 2, "text": "Página casi vacía."},
                 {"page": 3, "text": completa[1]["text"]}]
        self.assertIn("2 (18 caracteres)", paginas_incompletas(corta)[0])
        hueco = [completa[0], {"page": 3, "text": completa[1]["text"]}]
        self.assertIn("sin texto extraíble antes de la frontera TRANSITORIOS: 2",
                      paginas_incompletas(hueco)[0])
        # Tras la frontera no se revisa (anexos); sin frontera se revisan todas menos la última.
        self.assertEqual(paginas_incompletas(completa + [{"page": 3, "text": "Nota."}]), [])
        self.assertEqual(paginas_incompletas([{"page": 1, "text": _RELLENO},
                                              {"page": 2, "text": "Firma."}]), [])
        with self.assertRaisesRegex(ON.ReingestaRechazada, "extracción incompleta"):
            self.reingestar([LEY_A], extraer=lambda _ruta: corta)
        self.assertEqual(self.escrituras(), [])

    # ── (c) colisiones antes de borrar y respaldo durable ───────────────────────────────
    def test_id_ocupado_por_otra_fuente_antes_de_borrar(self) -> None:
        coleccion = ColeccionEscribible()
        coleccion.agregar_fila("LEY A_chunk_0", "Fragmento sintético de otra fuente.",
                               _meta("otra.pdf", "", "1", 0), VECTOR_VIEJO)
        self.coleccion = coleccion
        original = coleccion.filas()
        with self.assertRaisesRegex(ON.ReingestaRechazada, "ocupados por otra fuente"):
            self.reingestar([LEY_A])
        self.assertEqual(self.escrituras(), [])
        self.assertEqual(self.coleccion.filas(), original)

    def test_respaldo_durable_y_restaurar(self) -> None:
        (informe,) = self.reingestar([LEY_A])
        ruta = Path(informe["respaldo"])
        self.assertEqual(ruta.parent, self.respaldos.resolve())
        respaldo = ON.leer_respaldo(ruta)
        previos = [f for f in self.original if f[2]["source"] == LEY_A]
        self.assertEqual((respaldo["fuente"], respaldo["fragmentos"]), (LEY_A, len(previos)))
        self.assertEqual(respaldo["ids"], [f[0] for f in previos])
        self.assertEqual(respaldo["documents"], [f[1] for f in previos])
        self.assertEqual(respaldo["metadatas"], [f[2] for f in previos])
        self.assertEqual(respaldo["vectores"], [_float32(f[3]) for f in previos])
        # --restaurar repone la fuente tal como estaba (vectores en float32) y respalda antes
        # el estado que sustituye.
        resultado = ON.restaurar_respaldo(str(ruta), collection=self.coleccion,
                                          respaldos_dir=str(self.respaldos))
        self.assertEqual(resultado["fragmentos"], len(previos))
        self.assertTrue(Path(resultado["respaldo_previo"]).is_file())
        repuestos = self.filas_de(LEY_A)
        self.assertEqual([f[:3] for f in repuestos], [f[:3] for f in previos])
        self.assertEqual([_float32(f[3]) for f in repuestos], [_float32(f[3]) for f in previos])
        self.assertEqual(self.filas_de(LEY_B), [f for f in self.original if f[2]["source"] == LEY_B])

    def test_respaldo_alterado_se_rechaza(self) -> None:
        (informe,) = self.reingestar([LEY_A])
        ruta = Path(informe["respaldo"])
        cuerpo = json.loads(ruta.read_text(encoding="utf-8"))
        cuerpo["documents"][0] = "Texto alterado."
        ruta.write_text(json.dumps(cuerpo, ensure_ascii=False), encoding="utf-8")
        antes = self.coleccion.filas()
        with self.assertRaisesRegex(ValueError, "huella no coincide"):
            ON.restaurar_respaldo(str(ruta), collection=self.coleccion,
                                  respaldos_dir=str(self.respaldos))
        self.assertEqual(self.coleccion.filas(), antes)

    def test_respaldos_fuera_del_repositorio_y_del_indice(self) -> None:
        for dentro in (ON._BASE_DIR / "respaldos", Path(ON.CHROMA_PATH) / "respaldos"):
            with self.subTest(dentro=dentro), self.assertRaisesRegex(ValueError, "no pueden quedar"):
                self.reingestar([LEY_A], respaldos_dir=str(dentro))
        self.assertEqual(self.escrituras(), [])
        with mock.patch.dict("os.environ", {ON.VARIABLE_RESPALDOS: str(self.respaldos)}):
            self.assertEqual(ON._directorio_respaldos(), self.respaldos.resolve())


class IngestaSinMezclaTests(ReingestaBase):
    """La ingesta sin flags no completa por ID una fuente indexada con otra fragmentación."""

    def test_pendientes_sin_mezcla(self) -> None:
        ids = ["LEY B_chunk_0", "LEY B_chunk_1", "LEY B_chunk_2", "LEY B_chunk_3"]
        textos = ["LEY SINTÉTICA B", "Artículo 1.- Texto sintético.", "Artículo 2.- Texto.",
                  "Artículo 3.- Texto sintético nuevo."]
        metas = [_meta(LEY_B, a, "1", i) for i, a in enumerate(["", "1", "2", "3"])]
        # Lo indexado coincide con lo nuevo (ingesta interrumpida): solo falta el último.
        self.assertEqual(ON.pendientes_sin_mezcla(self.coleccion, LEY_B, ids, textos, metas), [3])
        # Otro texto o otra etiqueta en un ID existente: no se mezcla.
        otro = list(textos)
        otro[1] = "ARTÍCULO 1.- Otro texto sintético."
        self.assertIsNone(ON.pendientes_sin_mezcla(self.coleccion, LEY_B, ids, otro, metas))
        otra_meta = [dict(m) for m in metas]
        otra_meta[2]["article"] = "2-A"
        self.assertIsNone(ON.pendientes_sin_mezcla(self.coleccion, LEY_B, ids, textos, otra_meta))
        # Menos fragmentos nuevos que indexados: tampoco.
        self.assertIsNone(ON.pendientes_sin_mezcla(self.coleccion, LEY_B, ids[:2], textos[:2], metas[:2]))
        # Fuente no indexada: todos.
        self.assertEqual(
            ON.pendientes_sin_mezcla(self.coleccion, "NUEVA.pdf", ids, textos, metas), [0, 1, 2, 3]
        )

    def test_migracion_pendiente_sale_con_codigo_3_y_el_comando_exacto(self) -> None:
        # Ronda 2 (adjudicado): LEY A está indexada con el corte anterior; la ingesta sin flags
        # la omite, lo resume con el comando --fuente exacto y sale con código 3.
        (self.carpeta / LEY_B).unlink()
        dependencias = SimpleNamespace(
            chromadb=SimpleNamespace(PersistentClient=lambda path: SimpleNamespace()),
        )
        registro = io.StringIO()
        manejador = logging.StreamHandler(registro)
        ON.logger.addHandler(manejador)
        self.addCleanup(ON.logger.removeHandler, manejador)
        with mock.patch.object(ON, "get_embedder", return_value=object()), \
                mock.patch.object(ON, "_cargar_dependencias", return_value=dependencias), \
                mock.patch.object(ON, "get_collection", return_value=self.coleccion), \
                mock.patch.object(ON, "extract_text_from_pdf", side_effect=self.extraer), \
                mock.patch.object(ON, "_divisor_respaldo",
                                  return_value=SimpleNamespace(split_text=_sin_division)), \
                self.assertRaises(SystemExit) as salida:
            ON.ingest(str(self.carpeta))
        self.assertEqual(salida.exception.code, ON.SALIDA_MIGRACION_PENDIENTE)
        self.assertEqual(self.escrituras(), [])
        texto = registro.getvalue()
        self.assertIn("MIGRACIÓN PENDIENTE", texto)
        self.assertIn(f'--fuente "{LEY_A}" --simular', texto)

    def test_bootstrap_no_anuncia_corpus_listo_con_migracion_pendiente(self) -> None:
        guion = (Path(__file__).resolve().parent.parent / "scripts" / "bootstrap_corpus.sh"
                 ).read_text(encoding="utf-8")
        self.assertIn('if [ "$INGEST_RC" -eq 3 ]; then', guion)
        listo = guion.index("Corpus listo")
        self.assertLess(guion.index('if [ "$MIGRACION_PENDIENTE" -eq 1 ]; then'), listo)


class RetiroTests(ReingestaBase):
    """``ingest --retirar`` (orden del responsable, 10-oct-2026): saca del índice una fuente que el
    catálogo ya no resuelve (p. ej. una ley abrogada que se indexó como fuente nueva), con
    respaldo durable y reposición por ``--restaurar``."""

    def retirar(self, fuentes, **kwargs):
        opciones = {"collection": self.coleccion, "respaldos_dir": str(self.respaldos)}
        opciones.update(kwargs)
        return ON.retirar_fuentes(fuentes, **opciones)

    def test_retira_solo_esa_fuente_y_se_puede_reponer(self) -> None:
        previos = self.filas_de(LEY_B)
        (informe,) = self.retirar([LEY_B])
        self.assertEqual((informe["fuente"], informe["fragmentos"]), (LEY_B, 3))
        self.assertEqual(self.filas_de(LEY_B), [])
        self.assertEqual(self.filas_de(LEY_A), [f for f in self.original if f[2]["source"] == LEY_A])
        self.assertTrue(Path(informe["respaldo"]).is_file())
        ON.restaurar_respaldo(informe["respaldo"], collection=self.coleccion,
                              respaldos_dir=str(self.respaldos))
        repuestos = self.filas_de(LEY_B)
        self.assertEqual([f[:3] for f in repuestos], [f[:3] for f in previos])
        self.assertEqual([_float32(f[3]) for f in repuestos], [_float32(f[3]) for f in previos])

    def test_nada_se_toca_si_alguna_no_se_puede_retirar(self) -> None:
        for fuentes, mensaje in (([], "al menos una"), ([LEY_B, LEY_B], "repetida"),
                                 (["no_indexada.pdf"], "no tiene fragmentos"),
                                 (["../LEY B.pdf"], "solo el nombre")):
            with self.subTest(fuentes=fuentes), self.assertRaisesRegex(ValueError, mensaje):
                self.retirar(fuentes)
        # Lo que el catálogo aún resuelve no se saca del índice (se quedaría sin fuente).
        with mock.patch.dict(ON.LAW_SOURCE_MAP, {"ley sintética b": LEY_B}), \
                self.assertRaisesRegex(ValueError, "sigue en LAW_SOURCE_MAP"):
            self.retirar([LEY_A, LEY_B])
        self.assertEqual(self.escrituras(), [])
        self.assertEqual(self.coleccion.filas(), self.original)
        self.assertFalse(self.respaldos.exists())

    def test_fallo_al_borrar_restaura(self) -> None:
        borrar = self.coleccion.delete
        llamadas: list[dict] = []

        def delete(**kwargs):
            llamadas.append(kwargs)
            if len(llamadas) == 1:
                raise RuntimeError("fallo sintético de escritura")
            return borrar(**kwargs)

        with mock.patch.object(self.coleccion, "delete", side_effect=delete), \
                self.assertRaisesRegex(ON.ReingestaFallida, "se restauraron los 3 fragmentos"):
            self.retirar([LEY_B])
        self.assertEqual([f[:3] for f in self.filas_de(LEY_B)],
                         [f[:3] for f in self.original if f[2]["source"] == LEY_B])


class CliTests(ReingestaBase):
    """``ingest --fuente/--simular/--restaurar``: validación de flags y despacho."""

    def test_retirar(self) -> None:
        informe = {"fuente": LEY_B, "fragmentos": 3, "respaldo": "r.json"}
        with mock.patch.object(ON, "retirar_fuentes", return_value=[informe]) as retirar, \
                mock.patch.object(ON, "reingestar_fuentes") as reingestar, \
                mock.patch.object(ON, "ingest") as ingestar:
            codigo, salida, _ = self._main("--retirar", LEY_B, directorio=False)
        self.assertEqual(codigo, 0)
        retirar.assert_called_once_with([LEY_B], respaldos_dir=None)
        reingestar.assert_not_called()
        ingestar.assert_not_called()
        self.assertIn(f"{LEY_B}: 3 fragmentos retirados del índice", salida)
        for argumentos in (("--retirar", LEY_B, "--fuente", LEY_A),
                           ("--retirar", LEY_B, "--simular"),
                           ("--retirar", LEY_B, "--restaurar", "r.json"),
                           ("--retirar", LEY_B, "--reingest")):
            with self.subTest(argumentos=argumentos), \
                    mock.patch.object(ON, "retirar_fuentes") as retirar, \
                    mock.patch.object(ON, "reingestar_fuentes") as reingestar, \
                    mock.patch.object(ON, "restaurar_respaldo") as restaurar, \
                    mock.patch.object(ON, "ingest") as ingestar:
                codigo, _, _ = self._main(*argumentos, directorio=False)
                self.assertEqual(codigo, 2)
                for llamado in (retirar, reingestar, restaurar, ingestar):
                    llamado.assert_not_called()
        for error, esperado in ((ValueError("no tiene fragmentos"), 2),
                                (ON.ReingestaFallida("restaurado"), 1)):
            with self.subTest(error=error), \
                    mock.patch.object(ON, "retirar_fuentes", side_effect=error):
                codigo, _, errores = self._main("--retirar", LEY_B, directorio=False)
                self.assertEqual(codigo, esperado)
                self.assertIn(str(error), errores)

    def _main(self, *argumentos: str, directorio: bool = True):
        salida, errores = io.StringIO(), io.StringIO()
        base = ["OpenNotebook.py", "ingest"] + (["--directory", str(self.carpeta)] if directorio else [])
        with mock.patch("sys.argv", base + list(argumentos)), \
                mock.patch.object(ON, "setup_logging"), \
                contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
            try:
                ON.main()
                codigo = 0
            except SystemExit as salida_sistema:
                codigo = salida_sistema.code
        return codigo, salida.getvalue(), errores.getvalue()

    def test_simular_exige_fuente(self) -> None:
        with mock.patch.object(ON, "reingestar_fuentes") as reingestar, \
                mock.patch.object(ON, "ingest") as ingestar:
            codigo, _, errores = self._main("--simular")
        self.assertEqual(codigo, 2)
        self.assertIn("exigen al menos una --fuente", errores)
        reingestar.assert_not_called()
        ingestar.assert_not_called()

    def test_fuente_no_se_combina_con_borrar_la_coleccion(self) -> None:
        for flag in ("--reingest", "--clear"):
            with self.subTest(flag=flag), \
                    mock.patch.object(ON, "reingestar_fuentes") as reingestar, \
                    mock.patch.object(ON, "ingest") as ingestar:
                codigo, _, errores = self._main("--fuente", LEY_A, flag)
                self.assertEqual(codigo, 2)
                self.assertIn("colección entera", errores)
                reingestar.assert_not_called()
                ingestar.assert_not_called()

    def test_despacha_a_la_reingesta_por_fuente(self) -> None:
        informe = {"fuente": LEY_A}
        with mock.patch.object(ON, "reingestar_fuentes", return_value=[informe]) as reingestar, \
                mock.patch.object(ON, "formato_informe_reingesta", return_value="INFORME"), \
                mock.patch.object(ON, "ingest") as ingestar:
            codigo, salida, _ = self._main("--fuente", LEY_A, "--fuente", LEY_B, "--simular",
                                           "--json", "--respaldos", str(self.respaldos))
        self.assertEqual(codigo, 0)
        reingestar.assert_called_once_with(str(self.carpeta), [LEY_A, LEY_B], simular=True,
                                           respaldos_dir=str(self.respaldos))
        ingestar.assert_not_called()
        self.assertIn("INFORME", salida)
        self.assertEqual(json.loads(salida[salida.index("["):]), [informe])

    def test_identidad_confirmada_va_con_su_fuente(self) -> None:
        with mock.patch.object(ON, "reingestar_fuentes", return_value=[{"fuente": LEY_A}]) as reingestar, \
                mock.patch.object(ON, "formato_informe_reingesta", return_value="INFORME"), \
                mock.patch.object(ON, "ingest") as ingestar:
            codigo, _, _ = self._main("--fuente", LEY_A, "--identidad-confirmada", LEY_A)
        self.assertEqual(codigo, 0)
        reingestar.assert_called_once_with(str(self.carpeta), [LEY_A], simular=False,
                                           respaldos_dir=None, identidad_confirmada=[LEY_A])
        ingestar.assert_not_called()
        # Sin --fuente (o con --restaurar) nunca cae en la ingesta de siempre ni restaura.
        for argumentos, directorio in ((("--identidad-confirmada", LEY_A), True),
                                       (("--restaurar", "r.json", "--identidad-confirmada", LEY_A),
                                        False)):
            with self.subTest(argumentos=argumentos), \
                    mock.patch.object(ON, "reingestar_fuentes") as reingestar, \
                    mock.patch.object(ON, "restaurar_respaldo") as restaurar, \
                    mock.patch.object(ON, "ingest") as ingestar:
                codigo, _, errores = self._main(*argumentos, directorio=directorio)
                self.assertEqual(codigo, 2)
                reingestar.assert_not_called()
                restaurar.assert_not_called()
                ingestar.assert_not_called()

    def test_errores_de_validacion_y_de_reingesta(self) -> None:
        for error, codigo_esperado in ((ValueError("fuente inválida"), 2),
                                       (ON.ReingestaRechazada("rechazada"), 2),
                                       (ON.ReingestaFallida("restaurado"), 1)):
            with self.subTest(error=error), \
                    mock.patch.object(ON, "reingestar_fuentes", side_effect=error):
                codigo, _, errores = self._main("--fuente", LEY_A)
                self.assertEqual(codigo, codigo_esperado)
                self.assertIn(str(error), errores)

    def test_restaurar(self) -> None:
        with mock.patch.object(ON, "restaurar_respaldo", return_value={
                "fuente": LEY_A, "fragmentos": 2, "respaldo_previo": "previo.json"}) as restaurar, \
                mock.patch.object(ON, "reingestar_fuentes") as reingestar:
            codigo, salida, _ = self._main("--restaurar", "r.json", directorio=False)
        self.assertEqual(codigo, 0)
        restaurar.assert_called_once_with("r.json", respaldos_dir=None)
        reingestar.assert_not_called()
        self.assertIn("2 fragmentos restaurados", salida)
        codigo, _, errores = self._main("--restaurar", "r.json", "--fuente", LEY_A)
        self.assertEqual(codigo, 2)
        codigo, _, errores = self._main(directorio=False)
        self.assertEqual(codigo, 2)
        self.assertIn("exige --directory", errores)

    def test_sin_flags_nuevos_la_ingesta_de_siempre(self) -> None:
        with mock.patch.object(ON, "reingestar_fuentes") as reingestar, \
                mock.patch.object(ON, "ingest") as ingestar:
            codigo, _, _ = self._main("--reingest")
        self.assertEqual(codigo, 0)
        ingestar.assert_called_once_with(str(self.carpeta), clear=False, reingest=True)
        reingestar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
