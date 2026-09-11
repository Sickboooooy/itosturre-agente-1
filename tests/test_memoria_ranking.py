"""Pruebas del ranking y del presupuesto de contexto (funciones puras).

Lo que se protege aquí es la promesa central del encargo: **el contexto que se
entrega al modelo no crece con la base**. Si esta suite pasa, diez mil eventos
en disco siguen cabiendo en cuatro kilobytes.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from itosturre.memoria import ranking


class Taxonomia(unittest.TestCase):
    def test_alias_se_canonizan(self) -> None:
        self.assertEqual(ranking.canonizar("file_created"), "file_modified")
        self.assertEqual(ranking.canonizar("file_deleted"), "file_modified")
        self.assertEqual(ranking.canonizar("FILE_WRITE"), "file_modified")

    def test_tipo_desconocido_se_conserva_sin_bono(self) -> None:
        self.assertFalse(ranking.tipo_valido("invento_raro"))
        self.assertEqual(ranking.bono_tipo("invento_raro"), 0.0)
        self.assertEqual(ranking.canonizar("invento_raro"), "invento_raro")

    def test_prioridad_del_criterio_juridico(self) -> None:
        """El orden de bonos debe reflejar la Fase 5 del encargo."""
        self.assertGreater(
            ranking.bono_tipo("correccion_criterio_pjf"),
            ranking.bono_tipo("architecture_decision"),
        )
        self.assertGreater(
            ranking.bono_tipo("architecture_decision"), ranking.bono_tipo("task_started")
        )
        self.assertGreater(ranking.bono_tipo("task_started"), ranking.bono_tipo("git_commit"))
        self.assertGreater(ranking.bono_tipo("alerta_procesal"), ranking.bono_tipo("file_modified"))

    def test_importancia_por_defecto_del_dominio(self) -> None:
        self.assertEqual(ranking.importancia_por_defecto("alerta_procesal"), 1)
        self.assertEqual(ranking.importancia_por_defecto("cita_bloqueada"), 1)
        self.assertEqual(ranking.importancia_por_defecto("git_branch"), 3)


class Recencia(unittest.TestCase):
    def setUp(self) -> None:
        self.ahora = datetime(2026, 9, 10, tzinfo=timezone.utc)

    def test_evento_de_hoy_no_decae(self) -> None:
        self.assertAlmostEqual(
            ranking.decaimiento_recencia(self.ahora.isoformat(), self.ahora), 1.0, places=3
        )

    def test_semivida_a_treinta_dias(self) -> None:
        hace30 = (self.ahora - timedelta(days=30)).isoformat()
        self.assertAlmostEqual(ranking.decaimiento_recencia(hace30, self.ahora), 0.5, places=2)

    def test_suelo_protege_el_criterio_antiguo(self) -> None:
        """Una corrección del PJF de hace años sigue siendo derecho vigente."""
        hace5anos = (self.ahora - timedelta(days=1825)).isoformat()
        self.assertEqual(
            ranking.decaimiento_recencia(hace5anos, self.ahora), ranking.SUELO_RECENCIA
        )

    def test_fecha_corrupta_devuelve_suelo_y_no_revienta(self) -> None:
        self.assertEqual(ranking.decaimiento_recencia("no-es-fecha"), ranking.SUELO_RECENCIA)
        self.assertEqual(ranking.decaimiento_recencia(None), ranking.SUELO_RECENCIA)

    def test_acepta_formato_de_sqlite(self) -> None:
        """datetime('now') de SQLite no lleva T ni Z."""
        self.assertGreater(ranking.decaimiento_recencia("2026-09-09 12:00:00", self.ahora), 0.9)


class NormalizacionBM25(unittest.TestCase):
    def test_mas_negativo_puntua_mas_alto(self) -> None:
        norm = ranking.normalizar_bm25([-10.0, -5.0, -1.0])
        self.assertEqual(norm[0], 1.0)
        self.assertGreater(norm[0], norm[1])
        self.assertGreater(norm[1], norm[2])

    def test_rango_acotado(self) -> None:
        for valor in ranking.normalizar_bm25([-8.0, -4.0, 0.0, 2.0]):
            self.assertGreaterEqual(valor, 0.0)
            self.assertLessEqual(valor, 1.0)

    def test_conjunto_vacio(self) -> None:
        self.assertEqual(ranking.normalizar_bm25([]), [])

    def test_todo_cero_no_divide_por_cero(self) -> None:
        self.assertEqual(ranking.normalizar_bm25([0.0, 0.0]), [1.0, 1.0])


class Presupuesto(unittest.TestCase):
    @staticmethod
    def _eventos(n: int, largo: int = 80) -> list[dict]:
        return [
            {
                "timestamp": "2026-09-10T00:00:00Z",
                "event_type": "important_context",
                "summary": f"evento {i} " + ("x" * largo),
                "file_path": None,
            }
            for i in range(n)
        ]

    def test_diez_mil_eventos_caben_en_el_presupuesto(self) -> None:
        """La promesa del encargo, comprobada: la salida no crece con la base."""
        elegidos, usados = ranking.recortar_por_presupuesto(self._eventos(10_000), 4096)
        self.assertLessEqual(usados, 4096)
        self.assertLess(len(elegidos), 10_000)
        self.assertGreater(len(elegidos), 0)

    def test_presupuesto_diminuto_no_desborda(self) -> None:
        elegidos, usados = ranking.recortar_por_presupuesto(self._eventos(50), 10)
        self.assertLessEqual(usados, 10)
        self.assertEqual(elegidos, [])

    def test_corta_en_el_primero_que_no_cabe(self) -> None:
        """No se salta al siguiente más pequeño: el orden es por relevancia."""
        eventos = [
            {"timestamp": "2026-09-10", "event_type": "t", "summary": "L" * 300},
            {"timestamp": "2026-09-10", "event_type": "t", "summary": "corto"},
        ]
        elegidos, _ = ranking.recortar_por_presupuesto(eventos, 100)
        self.assertEqual(elegidos, [])

    def test_medicion_en_bytes_no_en_caracteres(self) -> None:
        """Los acentos ocupan dos bytes en UTF-8; el techo es de bytes."""
        eventos = [{"timestamp": "2026-09-10", "event_type": "t", "summary": "á" * 200}]
        _, usados = ranking.recortar_por_presupuesto(eventos, 10_000)
        self.assertGreater(usados, 200)


class Puntuacion(unittest.TestCase):
    def test_los_cuatro_factores_intervienen(self) -> None:
        ahora = datetime(2026, 9, 10, tzinfo=timezone.utc)
        base = dict(bm25_norm=0.5, importance=3, timestamp=ahora.isoformat(), ahora=ahora)
        self.assertGreater(
            ranking.puntuar(event_type="alerta_procesal", **base),
            ranking.puntuar(event_type="git_commit", **base),
        )
        self.assertGreater(
            ranking.puntuar(event_type="git_commit", **{**base, "importance": 1}),
            ranking.puntuar(event_type="git_commit", **{**base, "importance": 4}),
        )
        self.assertGreater(
            ranking.puntuar(event_type="git_commit", **{**base, "bm25_norm": 1.0}),
            ranking.puntuar(event_type="git_commit", **base),
        )

    def test_formato_omite_detalles_por_defecto(self) -> None:
        evento = {
            "timestamp": "2026-09-10T12:00:00Z",
            "event_type": "vvca_veredicto",
            "summary": "VVCA 🔴 caso X",
            "details": "un detalle larguísimo que no debe aparecer",
            "file_path": "borrador.md",
        }
        linea = ranking.formato_evento(evento)
        self.assertIn("2026-09-10", linea)
        self.assertIn("borrador.md", linea)
        self.assertNotIn("larguísimo", linea)
        self.assertIn("larguísimo", ranking.formato_evento(evento, con_detalles=True))


if __name__ == "__main__":
    unittest.main()
