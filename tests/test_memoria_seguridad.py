"""Pruebas de las defensas de la memoria contextual (riesgos E2-E5 del informe).

Estas pruebas no comprueban comodidad, comprueban contención. Cada una
corresponde a un riesgo concreto de ``docs/auditoria-memoria-contextual-10sep2026.md``:
que un token acabe en SQLite, que una consulta rompa el ``MATCH``, que una ruta
se escape del proyecto o que un expediente vea el de otro cliente.
"""
from __future__ import annotations

import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from itosturre.memoria import (
    MemoriaStore,
    consulta_fts,
    fts5_disponible,
    project_id,
    redactar,
    ruta_relativa,
)

_SIN_FTS5 = not fts5_disponible(sqlite3.connect(":memory:"))


class RedaccionDeSecretos(unittest.TestCase):
    """E2 — ningún secreto debe llegar a persistirse.

    Los valores de prueba conservan la FORMA de una credencial (para que el
    detector tenga algo que detectar) pero son inconfundiblemente falsos: un
    fixture con aspecto de token real dispara los escáneres de secretos del
    alojamiento y bloquea el push.
    """

    def test_token_de_telegram_en_texto_libre(self) -> None:
        texto = "Se fijó TELEGRAM_BOT_TOKEN=000000000:FALSO-FIXTURE-DE-PRUEBA-NO-ES-REAL-000"
        salida, tocado = redactar(texto)
        self.assertTrue(tocado)
        self.assertNotIn("FALSO-FIXTURE", salida)
        self.assertIn("[REDACTADO]", salida)

    def test_clave_de_proveedor_de_modelo(self) -> None:
        salida, tocado = redactar("la clave es sk-FALSO-FIXTURE-DE-PRUEBA-NO-ES-REAL")
        self.assertTrue(tocado)
        self.assertNotIn("FALSO-FIXTURE", salida)

    def test_valor_por_nombre_de_clave(self) -> None:
        salida, tocado = redactar({"api_key": "loquesea", "nota": "texto inocuo"})
        self.assertTrue(tocado)
        self.assertEqual(salida["api_key"], "[REDACTADO]")
        self.assertEqual(salida["nota"], "texto inocuo")

    def test_estructura_anidada(self) -> None:
        salida, tocado = redactar({"cfg": [{"password": "hunter2"}, {"ok": 1}]})
        self.assertTrue(tocado)
        self.assertEqual(salida["cfg"][0]["password"], "[REDACTADO]")
        self.assertEqual(salida["cfg"][1]["ok"], 1)

    def test_cabecera_authorization(self) -> None:
        salida, _ = redactar("curl -H 'Authorization: Bearer abcdefghijklmnopqrs'")
        self.assertNotIn("abcdefghijklmnopqrs", salida)

    def test_estructura_ciclica_no_cuelga(self) -> None:
        ciclo: dict = {"a": 1}
        ciclo["yo"] = ciclo
        salida, _ = redactar(ciclo)
        self.assertEqual(salida["a"], 1)

    def test_texto_juridico_no_se_toca(self) -> None:
        """Sobre-redactar es aceptable; mutilar un escrito legal, no."""
        texto = ("El artículo 294 del CPCJ y la tesis 2024783 obligan a la revocación "
                 "contra el auto de 30-jun-2026 en el expediente 712/2023.")
        salida, tocado = redactar(texto)
        self.assertFalse(tocado)
        self.assertEqual(salida, texto)


class ConsultaFTS(unittest.TestCase):
    """E3 — el texto del usuario nunca puede llegar como sintaxis a MATCH."""

    #: La forma inerte: solo literales entrecomillados unidos por OR. Un término
    #: como "near" dentro de comillas es una palabra a buscar, no el operador
    #: NEAR — las comillas son precisamente lo que lo desactiva.
    FORMA_SEGURA = re.compile(r'^"[^"]*"(?: OR "[^"]*")*$')

    def test_toda_consulta_produce_forma_inerte(self) -> None:
        venenos = [
            '"', 'a" OR "b', "NEAR(a b)", "art*", "-negado", 'x" AND y:"',
            "'; DROP TABLE eventos; --", "^inicio", "col:valor", "a AND b NOT c",
            "revocación (deserción)", "***", "{}[]()",
        ]
        for veneno in venenos:
            with self.subTest(veneno=veneno):
                expresion = consulta_fts(veneno)
                if expresion:
                    self.assertRegex(expresion, self.FORMA_SEGURA)

    def test_ningun_caracter_de_sintaxis_sobrevive_como_operador(self) -> None:
        """Los metacaracteres se descartan al tokenizar, no se escapan."""
        for simbolo in ("*", "-", "^", ":", "(", ")", "{", "}", "[", "]"):
            with self.subTest(simbolo=simbolo):
                self.assertNotIn(simbolo, consulta_fts(f"art{simbolo}294"))

    def test_acentos_se_conservan_para_el_tokenizador(self) -> None:
        self.assertIn("revocación", consulta_fts("revocación"))

    def test_palabras_vacias_fuera(self) -> None:
        expresion = consulta_fts("de la que el")
        self.assertEqual(expresion, "")

    def test_numeros_cortos_sobreviven(self) -> None:
        """En derecho "art. 5" importa; una letra suelta no."""
        self.assertIn("5", consulta_fts("artículo 5"))

    @unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
    def test_veneno_no_rompe_una_consulta_real(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p") as store:
                store.record("important_context", "amparo indirecto contra el auto")
                for veneno in ('" OR "', "NEAR(a b)", "'; DROP TABLE eventos; --", "*"):
                    with self.subTest(veneno=veneno):
                        store.recall(veneno)  # no debe lanzar
                self.assertEqual(store._total(), 1)


class RutasAncladas(unittest.TestCase):
    """E4 — ninguna ruta puede apuntar fuera del proyecto."""

    def test_ascenso_rechazado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(ruta_relativa("../../etc/passwd", tmp))

    def test_absoluta_ajena_rechazada(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fuera = str(Path(tempfile.gettempdir()) / "otro_sitio" / "x.txt")
            self.assertIsNone(ruta_relativa(fuera, Path(tmp) / "sub"))

    def test_relativa_valida_se_normaliza(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ruta_relativa("sub/../OpenNotebook.py", tmp), "OpenNotebook.py")

    @unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
    def test_evento_con_ruta_venenosa_se_guarda_sin_ruta(self) -> None:
        """Perder el campo es preferible a guardar un puntero fuera del proyecto."""
        with tempfile.TemporaryDirectory() as tmp:
            with MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p") as store:
                fila = store.record("file_modified", "algo", file_path="../../secreto")
                self.assertIsNone(fila["file_path"])


@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class AislamientoEntreProyectos(unittest.TestCase):
    """E5 — un expediente no puede ver el de otro cliente."""

    def test_recall_no_cruza_proyectos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "compartida.db"
            with MemoriaStore(db_path=base, raiz=tmp, pid="despacho-a") as a:
                a.record("important_context", "expediente 712/2023 de Fabián")
            with MemoriaStore(db_path=base, raiz=tmp, pid="despacho-b") as b:
                b.record("important_context", "expediente 999/2026 de otro cliente")
                resultado = b.recall("expediente")
                resúmenes = " ".join(e["summary"] for e in resultado["eventos"])
                self.assertIn("999/2026", resúmenes)
                self.assertNotIn("712/2023", resúmenes)
                self.assertEqual(b._total(), 1)

    def test_estadisticas_no_cruzan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "compartida.db"
            with MemoriaStore(db_path=base, raiz=tmp, pid="a") as a:
                a.record("important_context", "uno")
                a.record("important_context", "dos")
            with MemoriaStore(db_path=base, raiz=tmp, pid="b") as b:
                self.assertEqual(b.estadisticas()["total"], 0)

    def test_borrar_por_origen_no_cruza(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "compartida.db"
            with MemoriaStore(db_path=base, raiz=tmp, pid="a") as a:
                a.record("important_context", "de a", metadata={"origen": "memoria_md"})
            with MemoriaStore(db_path=base, raiz=tmp, pid="b") as b:
                b.record("important_context", "de b", metadata={"origen": "memoria_md"})
                self.assertEqual(b.borrar_por_origen("memoria_md"), 1)
            with MemoriaStore(db_path=base, raiz=tmp, pid="a") as a:
                self.assertEqual(a._total(), 1)

    def test_project_id_distingue_clones(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            uno = Path(tmp) / "clon1" / "repo"
            dos = Path(tmp) / "clon2" / "repo"
            uno.mkdir(parents=True)
            dos.mkdir(parents=True)
            self.assertNotEqual(project_id(uno), project_id(dos))
            self.assertEqual(project_id(uno), project_id(uno))


@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class EscrituraSaneada(unittest.TestCase):
    """El saneamiento no es opcional desde fuera: pasa siempre por record()."""

    def test_secreto_no_llega_a_la_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p") as store:
                store.record(
                    "configuration_changed",
                    "token TELEGRAM_BOT_TOKEN=000000000:FALSO-FIXTURE-DE-PRUEBA-NO-ES-REAL-111",
                    details={"secret": "no-debe-persistir"},
                )
                crudo = "".join(
                    str(v) for fila in store.con.execute("SELECT * FROM eventos")
                    for v in tuple(fila)
                )
                self.assertNotIn("FALSO-FIXTURE", crudo)
                self.assertNotIn("no-debe-persistir", crudo)
                self.assertEqual(
                    store.con.execute("SELECT redacted FROM eventos").fetchone()[0], 1
                )


if __name__ == "__main__":
    unittest.main()
