"""Pruebas de integración del almacén, el puente VVCA y el snapshot.

Cubren el recorrido completo: registrar → indexar → recuperar acotado →
condensar en snapshot → reanudar. Y la garantía de que un fallo de memoria nunca
tumba una auditoría en curso.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from itosturre.memoria import MemoriaStore, construir_snapshot, fts5_disponible
from itosturre.memoria.puente import eventos_desde_auditoria

_SIN_FTS5 = not fts5_disponible(sqlite3.connect(":memory:"))


def _store(tmp: str) -> MemoriaStore:
    return MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="prueba", session_id="s1")


@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class EscrituraYRecuperacion(unittest.TestCase):
    def test_ciclo_basico(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record("architecture_decision", "SQLite con FTS5 en vez de base vectorial")
            resultado = store.recall("vectorial")
            self.assertEqual(resultado["n_devueltos"], 1)
            self.assertEqual(resultado["modo"], "bm25")

    def test_busqueda_insensible_a_acentos(self) -> None:
        """El motivo por el que no se usa el tokenizador `porter` de la referencia."""
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record("correccion_criterio_pjf",
                         "La vía correcta contra la deserción es REVOCACIÓN, no apelación")
            for consulta in ("revocacion", "REVOCACIÓN", "desercion", "vía"):
                with self.subTest(consulta=consulta):
                    self.assertEqual(store.recall(consulta)["n_devueltos"], 1)

    def test_idempotencia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            marca = "2026-09-10T00:00:00Z"
            store.record("git_commit", "mismo hecho", timestamp=marca)
            store.record("git_commit", "mismo hecho", timestamp=marca)
            self.assertEqual(store._total(), 1)

    def test_resumen_vacio_se_rechaza(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            with self.assertRaises(ValueError):
                store.record("git_commit", "   ")

    def test_importancia_se_acota(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            self.assertEqual(store.record("git_commit", "a", importance=99)["importance"], 4)
            self.assertEqual(store.record("git_commit", "b", importance=-5)["importance"], 1)

    def test_sin_consulta_cae_a_reciente(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record("important_context", "algo")
            resultado = store.recall("")
            self.assertEqual(resultado["modo"], "reciente")
            self.assertEqual(resultado["n_devueltos"], 1)

    def test_consulta_solo_de_palabras_vacias_cae_a_reciente(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record("important_context", "algo")
            self.assertEqual(store.recall("de la que el")["modo"], "reciente")

    def test_filtro_por_tipo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record("alerta_procesal", "plazo de amparo vence el viernes")
            store.record("git_commit", "plazo en el mensaje del commit")
            resultado = store.recall("plazo", tipos=["alerta_procesal"])
            self.assertEqual(resultado["n_devueltos"], 1)
            self.assertEqual(resultado["eventos"][0]["event_type"], "alerta_procesal")

    def test_presupuesto_se_respeta_con_muchos_eventos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record_lote([
                {"event_type": "important_context",
                 "summary": f"amparo indirecto expediente {i} con texto de relleno suficiente",
                 "timestamp": f"2026-09-{(i % 28) + 1:02d}T00:00:00Z"}
                for i in range(500)
            ])
            resultado = store.recall("amparo", limite=100, max_bytes=1024)
            self.assertLessEqual(resultado["bytes"], 1024)
            self.assertEqual(store._total(), 500)

    def test_lote_es_atomico(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            with self.assertRaises(ValueError):
                store.record_lote([
                    {"event_type": "git_commit", "summary": "válido"},
                    {"event_type": "git_commit", "summary": ""},  # revienta
                ])
            self.assertEqual(store._total(), 0)

    def test_reindexar_recupera_el_indice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record("important_context", "contenido indexable")
            store.con.execute("INSERT INTO eventos_fts(eventos_fts) VALUES ('delete-all')")
            self.assertEqual(store.recall("indexable")["n_devueltos"], 0)
            store.reindexar()
            self.assertEqual(store.recall("indexable")["n_devueltos"], 1)


@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class Continuidad(unittest.TestCase):
    def test_snapshot_se_consume_una_sola_vez(self) -> None:
        """La bandera evita reinyectar el mismo estado en cada arranque."""
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.guardar_snapshot("<estado/>")
            self.assertEqual(store.consumir_snapshot(), "<estado/>")
            self.assertIsNone(store.consumir_snapshot())
            self.assertEqual(store.ultimo_snapshot(), "<estado/>")

    def test_snapshot_no_crece_con_la_base(self) -> None:
        """La propiedad que hace útil el snapshot por referencia."""
        pocos = [
            {"event_type": "alerta_procesal", "summary": f"alerta {i}",
             "timestamp": "2026-09-10T00:00:00Z", "file_path": None}
            for i in range(5)
        ]
        muchos = [
            {"event_type": "alerta_procesal", "summary": f"alerta {i}",
             "timestamp": "2026-09-10T00:00:00Z", "file_path": None}
            for i in range(5000)
        ]
        chico = construir_snapshot(pocos, project_id="p", total_en_memoria=5)
        grande = construir_snapshot(muchos, project_id="p", total_en_memoria=5000)
        self.assertLessEqual(len(grande.encode("utf-8")), 2048)
        self.assertLess(len(grande.encode("utf-8")), len(chico.encode("utf-8")) * 2)

    def test_snapshot_marca_su_contenido_como_datos(self) -> None:
        """E7: un evento no puede convertirse en instrucción para el modelo."""
        texto = construir_snapshot([], project_id="p")
        self.assertIn("no instrucciones", texto)
        self.assertIn("NUNCA es fuente de una cita legal", texto)

    def test_snapshot_prioriza_lo_que_condiciona_el_trabajo(self) -> None:
        eventos = [
            {"event_type": "git_commit", "summary": "un commit cualquiera",
             "timestamp": "2026-09-10T00:00:00Z", "file_path": "a.py"},
            {"event_type": "alerta_procesal", "summary": "plazo de amparo vence el viernes",
             "timestamp": "2026-09-10T00:00:00Z", "file_path": None},
        ]
        texto = construir_snapshot(eventos, project_id="p")
        self.assertLess(texto.index("Alertas procesales"), texto.index("Archivos tocados"))

    def test_tareas_abiertas_excluyen_las_cerradas(self) -> None:
        eventos = [
            {"event_type": "task_started", "summary": "tarea uno",
             "timestamp": "2026-09-01T00:00:00Z"},
            {"event_type": "task_completed", "summary": "tarea uno",
             "timestamp": "2026-09-02T00:00:00Z"},
            {"event_type": "task_started", "summary": "tarea dos",
             "timestamp": "2026-09-03T00:00:00Z"},
        ]
        texto = construir_snapshot(eventos, project_id="p")
        self.assertIn("tarea dos", texto)
        self.assertIn("Tareas abiertas (1)", texto)

    def test_sin_eventos_lo_dice(self) -> None:
        self.assertIn("Sin eventos previos", construir_snapshot([], project_id="p"))


class PuenteVVCA(unittest.TestCase):
    """Etapa 3: la traza de auditoría deja de morir en el JSON del caso."""

    AUDITORIA = {
        "vvca_summary": {
            "score_rag": 82, "score_sjf": 0, "articulos_ok": 5, "tesis_total": 2,
            "tesis_mismatch": 1, "tesis_no_encontradas": 0, "tesis_superadas": 0,
            "veredicto": {
                "apto": False, "semaforo": "🔴",
                "razon": "1/2 tesis con rubro discrepante — USO PROCESAL PROHIBIDO",
                "accion": "Sustituir tesis antes de cualquier uso procesal",
            },
        },
        "retrieved_sources": [
            {"ref_type": "jurisprudencia", "reference": "Reg. 2024783",
             "vvca": {"rubro_mismatch": True, "estado_vigencia": "vigente",
                      "fuerza_vinculante": "[J-SALA]",
                      "explicabilidad": {"registro": "2024783", "overlap_rubro": 0.12,
                                         "rubro_real": "RUBRO REAL", "rubro_invocado": "OTRO"}}},
            {"ref_type": "jurisprudencia", "reference": "Reg. 2003551",
             "vvca": {"rubro_mismatch": False, "estado_vigencia": "vigente",
                      "explicabilidad": {"registro": "2003551"}}},
            {"ref_type": "normativa", "reference": "art. 16 CPEUM", "vvca": {"semaforo": "🟢"}},
        ],
    }

    def test_veredicto_rojo_genera_alerta(self) -> None:
        eventos = eventos_desde_auditoria(self.AUDITORIA, caso="712-2023", borrador="b.md")
        tipos = [e["event_type"] for e in eventos]
        self.assertIn("vvca_veredicto", tipos)
        self.assertIn("alerta_procesal", tipos)

    def test_solo_se_bloquea_la_tesis_discrepante(self) -> None:
        eventos = eventos_desde_auditoria(self.AUDITORIA, caso="712-2023")
        bloqueadas = [e for e in eventos if e["event_type"] == "cita_bloqueada"]
        self.assertEqual(len(bloqueadas), 1)
        self.assertIn("2024783", bloqueadas[0]["summary"])

    def test_criterio_superado_tambien_bloquea(self) -> None:
        """El 'falso verde': registro y rubro reales, criterio ya no vigente."""
        auditoria = {
            "vvca_summary": {},
            "retrieved_sources": [
                {"ref_type": "jurisprudencia", "reference": "Reg. 111",
                 "vvca": {"rubro_mismatch": False, "estado_vigencia": "superada",
                          "explicabilidad": {"registro": "111"}}},
            ],
        }
        eventos = eventos_desde_auditoria(auditoria)
        self.assertEqual(len(eventos), 1)
        self.assertIn("superada", eventos[0]["summary"])

    def test_vigencia_sin_dato_o_en_conflicto_no_es_bloqueo(self) -> None:
        """R4d: "no_consultada", "no_reconocida" y "en_conflicto" no son vigencia perdida.

        Antes el puente bloqueaba todo lo que no fuera "vigente": una tesis 🟢 sin dato de
        vigencia habría quedado en la memoria como cita bloqueada."""
        for estado in ("no_consultada", "no_reconocida", "en_conflicto"):
            with self.subTest(estado=estado):
                auditoria = {
                    "vvca_summary": {},
                    "retrieved_sources": [
                        {"ref_type": "jurisprudencia", "reference": "Reg. 111",
                         "vvca": {"rubro_mismatch": False, "estado_vigencia": estado,
                                  "explicabilidad": {"registro": "111"}}},
                    ],
                }
                self.assertEqual(eventos_desde_auditoria(auditoria), [])

    def test_toda_vigencia_perdida_bloquea(self) -> None:
        for estado in ("superada", "interrumpida", "sustituida"):
            with self.subTest(estado=estado):
                auditoria = {
                    "vvca_summary": {},
                    "retrieved_sources": [
                        {"ref_type": "jurisprudencia", "reference": "Reg. 111",
                         "vvca": {"rubro_mismatch": False, "estado_vigencia": estado,
                                  "explicabilidad": {"registro": "111"}}},
                    ],
                }
                (evento,) = eventos_desde_auditoria(auditoria)
                self.assertEqual(evento["event_type"], "cita_bloqueada")
                self.assertIn(f"criterio {estado}", evento["summary"])

    def test_rubro_con_sentido_invertido_se_registra_con_su_motivo(self) -> None:
        """R4d: el cotejo distingue el sentido invertido y el puente lo conserva."""
        auditoria = {
            "vvca_summary": {},
            "retrieved_sources": [
                {"ref_type": "jurisprudencia", "reference": "Reg. 111",
                 "vvca": {"rubro_mismatch": True, "cotejo_rubro": "invertido",
                          "estado_vigencia": "no_consultada",
                          "explicabilidad": {
                              "registro": "111", "rubro_real": "EL PLAZO ES COMPUTABLE",
                              "rubro_invocado": "EL PLAZO NO ES COMPUTABLE",
                              "motivo_cotejo": "sentido invertido: negaciones",
                              "polaridad": ["negaciones: 1 en el invocado y 0 en el real"]}}},
            ],
        }
        (evento,) = eventos_desde_auditoria(auditoria)
        self.assertEqual(evento["event_type"], "cita_bloqueada")
        self.assertIn("rubro discrepante (sentido invertido)", evento["summary"])
        self.assertEqual(evento["details"]["cotejo_rubro"], "invertido")
        self.assertEqual(evento["details"]["polaridad"],
                         ["negaciones: 1 en el invocado y 0 en el real"])

    def test_hueco_de_corpus_no_es_bloqueo(self) -> None:
        """Regla 7 VVCA: falta de índice no es defecto del argumento."""
        eventos = eventos_desde_auditoria(
            {"vvca_summary": {}}, faltantes=["Ley General de Víctimas"]
        )
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0]["event_type"], "corpus_gap")
        self.assertEqual(eventos[0]["importance"], 3)

    def test_estructura_inesperada_no_revienta(self) -> None:
        for basura in ({}, {"vvca_summary": None}, {"retrieved_sources": ["no es dict"]}):
            with self.subTest(basura=basura):
                self.assertIsInstance(eventos_desde_auditoria(basura), list)

    @unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
    def test_los_eventos_del_puente_son_recuperables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _store(tmp) as store:
            store.record_lote(eventos_desde_auditoria(self.AUDITORIA, caso="712-2023"))
            self.assertGreaterEqual(store.recall("rubro discrepante")["n_devueltos"], 1)
            self.assertGreaterEqual(store.recall("2024783")["n_devueltos"], 1)


class Degradacion(unittest.TestCase):
    """Un fallo de memoria nunca puede tumbar el trabajo del abogado."""

    def test_registrar_seguro_no_propaga(self) -> None:
        from itosturre.memoria import registrar_seguro
        import os

        previo = os.environ.get("ITOSTURRE_MEMORIA_DB")
        # Ruta imposible: un archivo donde debería haber un directorio.
        os.environ["ITOSTURRE_MEMORIA_DB"] = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "test_memoria_store.py", "x.db"
        )
        try:
            self.assertFalse(registrar_seguro("git_commit", "no debería lograrlo"))
        finally:
            if previo is None:
                os.environ.pop("ITOSTURRE_MEMORIA_DB", None)
            else:
                os.environ["ITOSTURRE_MEMORIA_DB"] = previo

    def test_registrar_auditoria_devuelve_cero_ante_fallo(self) -> None:
        from itosturre.memoria.puente import registrar_auditoria
        self.assertEqual(registrar_auditoria({}, raiz="/ruta/que/no/existe/jamas"), 0)


if __name__ == "__main__":
    unittest.main()
