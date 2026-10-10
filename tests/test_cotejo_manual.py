"""Pruebas de ``scripts/cotejo_manual.py``: el texto del RAG frente al PDF oficial vigente.

Sin red ni PyMuPDF: el "PDF oficial" es el .txt por páginas que guarda ``preparar`` y el texto
indexado son chunks como los de la ingesta. Datos rotulados como sintéticos ("LEY SINTÉTICA DE
PRUEBA", artículos 9998-10000, fechas de 1800-1801): nunca un dato normativo inventado con
apariencia real.
"""
from __future__ import annotations

import unittest

from scripts import cotejo_manual as cm

ENCABEZADO = (
    "LEY SINTÉTICA DE PRUEBA\nCÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN\nSecretaría General\n"
    "Secretaría de Servicios Parlamentarios\nÚltima Reforma DOF {fecha}\n{n} de {total}\n"
)
PAGINAS_OFICIALES = [
    ENCABEZADO.format(fecha="15-03-1801", n=1, total=2)
    + "Artículo 9998.- Texto sintético anterior.\n"
    "Artículo reformado DOF 01-01-1800\n"
    "Artículo 9999.- Las personas sintéticas tendrán treinta días\n"
    "de prueba.\n"
    "Párrafo reformado DOF 15-03-1801\n"
    "CAPÍTULO II\n"
    "De las pruebas sintéticas\n"
    "Artículo 10000.- Texto sintético posterior.\n",
    ENCABEZADO.format(fecha="15-03-1801", n=2, total=2)
    + "TRANSITORIOS\n"
    "Artículo Primero.- El decreto sintético entrará en vigor al día siguiente.\n",
]
OFICIAL_TXT = "\n".join(f"[página {n}]\n{texto}" for n, texto in enumerate(PAGINAS_OFICIALES, 1))
CHUNKS_INDEXADOS = [
    ENCABEZADO.format(fecha="01-01-1801", n=1, total=2)
    + "Artículo 9998.- Texto sintético anterior.\nArtículo reformado DOF 01-01-1800",
    # Otro terminador del encabezado ("." en vez de ".-") y otra cifra: solo la cifra es diferencia.
    "Artículo 9999. Las personas sintéticas tendrán quince días",
    # Sub-chunk de la ingesta con el mobiliario de la página siguiente a media lectura.
    "[LEY 9999] CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN\nSecretaría General\n2 de 2\nde prueba.",
    "CAPÍTULO II\nDe las pruebas sintéticas\nArtículo 10000.- Texto sintético posterior.",
]
MANIFIESTO = {
    "etiqueta": "LSP", "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/LSP.pdf", "sha256": "0" * 64,
    "version_indexada": "Última Reforma DOF 01-01-1801", "version_oficial": "DOF 15/03/1801", "ruido": [],
}


def ficha(articulo: str) -> tuple[str, str]:
    indexado = cm.unir_chunks(CHUNKS_INDEXADOS)
    return cm.ficha("LEY SINTÉTICA DE PRUEBA.pdf", MANIFIESTO, articulo, indexado, OFICIAL_TXT)


class FichaTests(unittest.TestCase):
    def test_coincide(self) -> None:
        veredicto, texto = ficha("9998")
        self.assertTrue(veredicto.startswith("🟢 COINCIDE"))
        # La nota también la trae el RAG: no es novedad.
        self.assertNotIn("que el texto del RAG no trae", texto)
        self.assertIn("Notas de reforma en la fuente oficial: Artículo reformado DOF 01-01-1800", texto)

    def test_difiere_solo_por_el_texto(self) -> None:
        veredicto, texto = ficha("9999")
        self.assertTrue(veredicto.startswith("🔴 DIFIERE"))
        self.assertIn("(tachado = solo en el RAG; negritas = solo en el texto vigente; 1 tramos)", texto)
        self.assertIn("~~quince~~ → **treinta**", texto)
        self.assertIn("Notas de reforma que el texto del RAG no trae:** Párrafo reformado DOF 15-03-1801", texto)
        # El artículo termina en el rótulo del capítulo; la denominación no es parte de él.
        oficial = texto.split("**Texto oficial vigente:**", 1)[1]
        self.assertIn("> Artículo 9999.- Las personas sintéticas tendrán treinta días", oficial)
        self.assertNotIn("De las pruebas sintéticas", oficial)

    def test_no_localizado_informa_variantes_sin_elegir(self) -> None:
        veredicto, texto = ficha("9999-1")
        self.assertTrue(veredicto.startswith("🟡 NO LOCALIZADO en ninguno de los dos textos"))
        self.assertIn("variantes cercanas: 9999", veredicto)
        self.assertNotIn("**Texto oficial vigente:**", texto)

    def test_encabezado_solo_en_transitorios_no_se_coteja(self) -> None:
        veredicto, _ = ficha("Primero")
        self.assertIn("solo aparece como encabezado en transitorios", veredicto)

    def test_adicionado_despues_de_la_version_del_rag(self) -> None:
        indexado = cm.unir_chunks(CHUNKS_INDEXADOS[:2])  # el RAG no llega al artículo 10000
        veredicto, _ = cm.ficha("LEY SINTÉTICA DE PRUEBA.pdf", MANIFIESTO, "10000", indexado, OFICIAL_TXT)
        self.assertTrue(veredicto.startswith("🟡 NO LOCALIZADO en el texto indexado"))


class TextoIndexadoTests(unittest.TestCase):
    def test_unir_chunks_quita_prefijo_y_traslape(self) -> None:
        traslape = "texto común del traslape sintético"
        unido = cm.unir_chunks([f"Artículo 9999.- Inicio, {traslape}", f"[LEY 9999] {traslape} y final."])
        self.assertEqual(unido, f"Artículo 9999.- Inicio, {traslape} y final.")
        self.assertEqual(cm.unir_chunks(["uno", "dos"]), "uno\ndos")

    def test_ruido_repetido_y_notas(self) -> None:
        paginas = [f"PERIÓDICO OFICIAL SINTÉTICO\nI.\nPárrafo reformado DOF 01-01-1800\nTexto {n}" for n in range(4)]
        ruido = cm.ruido_repetido(paginas)
        self.assertIn(cm.vc.norm("PERIÓDICO OFICIAL SINTÉTICO"), ruido)
        self.assertNotIn(cm.vc.norm("I."), ruido)  # demasiado corta para ser mobiliario
        self.assertTrue(cm.es_ruido("PERIÓDICO OFICIAL SINTÉTICO", ruido))
        # Una nota de reforma nunca es mobiliario, aunque se repita en todas las páginas.
        self.assertFalse(cm.es_ruido("Párrafo reformado DOF 01-01-1800", ruido))
        self.assertTrue(cm.es_ruido("3 de 9", set()))

    def test_notas_de_jalisco(self) -> None:
        cuerpo, notas = cm.separar_notas(
            ["Artículo 9999.- Texto sintético. (REFORMADO, P.O. 1 DE ENERO DE 1800)", "Segundo párrafo."])
        self.assertEqual(notas, ["(REFORMADO, P.O. 1 DE ENERO DE 1800)"])
        self.assertNotIn("REFORMADO", " ".join(cuerpo))


if __name__ == "__main__":
    unittest.main()
