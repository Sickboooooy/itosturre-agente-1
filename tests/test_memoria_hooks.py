"""Pruebas de los hooks de captura y restauración (etapa 7I).

Los trece escenarios que pide el plan, más los invariantes que sostienen el
diseño: que el ruido no entre, que un fallo no detenga al agente y que lo que
sale hacia el modelo esté acotado por más que crezca la base.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from itosturre.memoria import MemoriaStore, construir_snapshot, fts5_disponible
from itosturre.memoria.hooks import (
    clasificar,
    clasificar_bash,
    clasificar_prompt,
    procesar,
    registrar_diagnostico,
    ruta_log,
)

_SIN_FTS5 = not fts5_disponible(sqlite3.connect(":memory:"))


@contextlib.contextmanager
def entorno(**variables: str | None):
    """Fija variables de entorno y las restaura pase lo que pase."""
    previos = {k: os.environ.get(k) for k in variables}
    try:
        for clave, valor in variables.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor
        yield
    finally:
        for clave, valor in previos.items():
            if valor is None:
                os.environ.pop(clave, None)
            else:
                os.environ[clave] = valor


def _tool(nombre: str, entrada: dict, respuesta=None, sesion="s1") -> dict:
    payload = {"session_id": sesion, "tool_name": nombre, "tool_input": entrada}
    if respuesta is not None:
        payload["tool_response"] = respuesta
    return payload


# ── 1. Captura correcta ──────────────────────────────────────────────────────

class CapturaCorrecta(unittest.TestCase):
    def test_edicion_de_archivo(self) -> None:
        p = clasificar(_tool("Edit", {"file_path": "vvca_full.py"}), "PostToolUse")
        self.assertEqual(p["event_type"], "file_modified")
        self.assertIn("vvca_full.py", p["summary"])

    def test_archivo_de_configuracion_sube_de_categoria(self) -> None:
        p = clasificar(_tool("Write", {"file_path": ".gitignore"}), "PostToolUse")
        self.assertEqual(p["event_type"], "configuration_changed")

    def test_commit_conserva_el_asunto_no_el_cuerpo(self) -> None:
        p = clasificar_bash('git commit -m "refactor: memoria contextual"', "")
        self.assertEqual(p["event_type"], "git_commit")
        self.assertIn("refactor: memoria contextual", p["summary"])

    def test_rama_de_trabajo(self) -> None:
        p = clasificar_bash("git checkout -b feat/hooks", "")
        self.assertEqual(p["event_type"], "git_branch")
        self.assertIn("feat/hooks", p["summary"])

    def test_dependencias(self) -> None:
        self.assertEqual(
            clasificar_bash("pip install requests", "")["event_type"], "dependency_changed"
        )

    def test_prueba_en_rojo(self) -> None:
        p = clasificar_bash("python -m unittest discover", "FAILED (failures=2)")
        self.assertEqual(p["event_type"], "test_failed")

    def test_prompt_con_correccion(self) -> None:
        p = clasificar_prompt("No, en realidad hay que usar revocación aquí.")
        self.assertEqual(p["event_type"], "user_correction")
        self.assertEqual(p["importance"], 1)

    def test_criterio_juridico_sin_acentos(self) -> None:
        """Se escribe "via" tanto como "vía"; exigir la tilde perdería la mitad."""
        for texto in ("la via correcta es revocacion", "la vía correcta es revocación"):
            with self.subTest(texto=texto):
                self.assertEqual(
                    clasificar_prompt(texto)["event_type"], "correccion_criterio_pjf"
                )

    def test_comando_compuesto_no_se_pierde(self) -> None:
        """Regresión de la primera prueba de humo real.

        El agente casi nunca ejecuta un comando suelto: ejecuta
        ``cd /repo && git commit -m …``. Clasificar por el primer token hacía que
        todo comando compuesto se descartara por empezar con `cd`, y con él se
        perdían commits, pruebas e instalaciones. La prueba sintética no lo vio
        porque pasaba comandos sueltos.
        """
        casos = [
            ('cd "/repo" && git commit -m "refactor: algo"', "git_commit"),
            ("cd /repo && git checkout -b feat/x", "git_branch"),
            ("cd /repo && pip install requests", "dependency_changed"),
            ('cd /repo && echo "hola" && git commit -m "x"', "git_commit"),
            ("ls -la; git commit -m 'y'", "git_commit"),
        ]
        for comando, esperado in casos:
            with self.subTest(comando=comando):
                resultado = clasificar_bash(comando, "OK")
                self.assertIsNotNone(resultado, "el comando compuesto se descartó")
                self.assertEqual(resultado["event_type"], esperado)

    def test_heredoc_no_se_clasifica_linea_a_linea(self) -> None:
        """Regresión observada en vivo: el cuerpo de un heredoc no es un comando.

        Una línea de código Python que mencionaba `unittest` dentro de un
        heredoc acabó registrada como "Pruebas en rojo". El salto de línea casi
        siempre delimita datos, no comandos encadenados.
        """
        comando = "\n".join([
            "cat >> tests/x.py <<'FIN'",
            "class Algo(unittest.TestCase):",
            "    def test_x(self): pass",
            "FIN",
        ])
        self.assertIsNone(clasificar_bash(comando, "FAILED"))

    def test_compuesto_solo_de_triviales_sigue_descartandose(self) -> None:
        for comando in ("cd /repo && ls -la", "cd /repo && git status && pwd",
                        "cd /x && cat a.md | grep foo"):
            with self.subTest(comando=comando):
                self.assertIsNone(clasificar_bash(comando, ""))

    def test_fallo_de_herramienta_se_marca_como_error(self) -> None:
        p = clasificar(
            _tool("Bash", {"command": "pip install cosa-inexistente"}), "PostToolUseFailure"
        )
        self.assertEqual(p["event_type"], "error_detected")


# ── 2. Evento irrelevante descartado ─────────────────────────────────────────

class RuidoDescartado(unittest.TestCase):
    def test_lecturas_y_busquedas(self) -> None:
        for herramienta, entrada in (
            ("Read", {"file_path": "x.py"}),
            ("Grep", {"pattern": "foo"}),
            ("Glob", {"pattern": "**/*.py"}),
        ):
            with self.subTest(herramienta=herramienta):
                self.assertIsNone(clasificar(_tool(herramienta, entrada), "PostToolUse"))

    def test_comandos_triviales(self) -> None:
        for comando in ("ls -la", "cd /tmp", "pwd", "cat README.md", "git status",
                        "git diff", "git log --oneline", "echo hola", "which python"):
            with self.subTest(comando=comando):
                self.assertIsNone(clasificar_bash(comando, ""))

    def test_prueba_en_verde_sin_senal_no_se_registra(self) -> None:
        self.assertIsNone(clasificar_bash("python -m unittest discover", ""))

    def test_artefactos_y_caches(self) -> None:
        for ruta in ("itosturre/__pycache__/x.pyc", "node_modules/lib/a.js",
                     "chroma_db/data.bin", "temp/borrador.md", "salida.log"):
            with self.subTest(ruta=ruta):
                self.assertIsNone(clasificar(_tool("Edit", {"file_path": ruta}), "PostToolUse"))

    def test_prompt_ordinario(self) -> None:
        for texto in ("gracias, continúa", "¿puedes revisar esto?", "ok"):
            with self.subTest(texto=texto):
                self.assertIsNone(clasificar_prompt(texto))

    def test_no_se_guarda_la_salida_completa(self) -> None:
        """El invariante del módulo: se guarda el hecho, no el output."""
        salida = "x" * 50_000
        p = clasificar_bash("python -m unittest discover", f"FAILED (failures=1)\n{salida}")
        serializado = json.dumps(p, ensure_ascii=False)
        self.assertLess(len(serializado), 600)
        self.assertNotIn("x" * 500, serializado)


# ── 3, 4, 11. Snapshot, restauración y ciclo de compactación ─────────────────

@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class SnapshotYRestauracion(unittest.TestCase):
    def _store(self, tmp: str, sesion="s1") -> MemoriaStore:
        return MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p", session_id=sesion)

    def test_snapshot_cubre_las_secciones_del_plan(self) -> None:
        eventos = [
            {"event_type": "alerta_procesal", "summary": "plazo de amparo vence el viernes",
             "timestamp": "2026-09-10T00:00:00Z"},
            {"event_type": "task_started", "summary": "implementar hooks",
             "timestamp": "2026-09-10T00:00:00Z"},
            {"event_type": "task_completed", "summary": "escribir el store",
             "timestamp": "2026-09-09T00:00:00Z"},
            {"event_type": "architecture_decision", "summary": "SQLite sobre base vectorial",
             "timestamp": "2026-09-08T00:00:00Z"},
            {"event_type": "file_modified", "summary": "Modificó store.py",
             "file_path": "itosturre/memoria/store.py", "timestamp": "2026-09-10T00:00:00Z"},
            {"event_type": "test_failed", "summary": "Pruebas en rojo: unittest",
             "timestamp": "2026-09-10T00:00:00Z"},
        ]
        texto = construir_snapshot(eventos, project_id="p", total_en_memoria=6)
        for esperado in ("Alertas procesales", "Tareas abiertas", "Tareas completadas",
                         "Decisiones", "Archivos tocados", "Pruebas",
                         "Siguiente acción sugerida"):
            with self.subTest(seccion=esperado):
                self.assertIn(esperado, texto)

    def test_siguiente_accion_respeta_la_precedencia(self) -> None:
        """Lo que puede costar una instancia va antes que lo que cuesta una tarde."""
        base = {"timestamp": "2026-09-10T00:00:00Z"}
        alerta = {"event_type": "alerta_procesal", "summary": "plazo vence", **base}
        error = {"event_type": "error_detected", "summary": "algo falló", **base}
        tarea = {"event_type": "task_started", "summary": "tarea en curso", **base}
        self.assertIn("alerta procesal",
                      construir_snapshot([alerta, error, tarea], project_id="p"))
        self.assertIn("error abierto", construir_snapshot([error, tarea], project_id="p"))
        self.assertIn("tarea en curso", construir_snapshot([tarea], project_id="p"))
        self.assertIn("nada pendiente", construir_snapshot([], project_id="p"))

    def test_ciclo_compactacion_reanudacion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self._store(tmp) as store:
                store.record("task_started", "migrar CLAUDE.md")
                eventos = store.recall("", limite=50, max_bytes=10 ** 7)["eventos"]
                texto = construir_snapshot(eventos, project_id=store.project_id)
                store.guardar_snapshot(texto)          # PreCompact
            # Sesión nueva tras la compactación
            with self._store(tmp, sesion="s2") as store:
                recuperado = store.consumir_snapshot()  # SessionStart
                self.assertIsNotNone(recuperado)
                self.assertIn("migrar CLAUDE.md", recuperado)
                self.assertIsNone(store.consumir_snapshot())  # no se reinyecta

    def test_restauracion_acotada_en_bytes(self) -> None:
        muchos = [
            {"event_type": "alerta_procesal", "summary": f"alerta número {i} con relleno",
             "timestamp": "2026-09-10T00:00:00Z"}
            for i in range(3000)
        ]
        texto = construir_snapshot(muchos, project_id="p", total_en_memoria=3000,
                                   max_bytes=2048)
        self.assertLessEqual(len(texto.encode("utf-8")), 2048)


# ── 5. Deduplicación ─────────────────────────────────────────────────────────

@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class Deduplicacion(unittest.TestCase):
    def test_mismo_hecho_repetido_no_duplica(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p",
                              session_id="s1") as store:
                for _ in range(20):
                    store.record("file_modified", "Modificó store.py",
                                 file_path="itosturre/memoria/store.py",
                                 dedupe_key="file:itosturre/memoria/store.py")
                self.assertEqual(store._total(), 1)
                fila = store.con.execute("SELECT metadata FROM eventos").fetchone()
                self.assertIn("\"veces\":20", fila["metadata"].replace(" ", ""))

    def test_la_fecha_se_refresca_a_la_ultima_vez(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p",
                              session_id="s1") as store:
                store.record("file_modified", "Modificó a.py", dedupe_key="file:a.py",
                             timestamp="2026-01-01T00:00:00Z")
                store.record("file_modified", "Modificó a.py", dedupe_key="file:a.py",
                             timestamp="2026-09-10T00:00:00Z")
                fila = store.con.execute("SELECT timestamp FROM eventos").fetchone()
                self.assertTrue(fila["timestamp"].startswith("2026-09-10"))

    def test_sesiones_distintas_son_hechos_distintos(self) -> None:
        """Trabajar hoy en un archivo no es el mismo hecho que haberlo hecho ayer."""
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "m.db"
            for sesion in ("s1", "s2"):
                with MemoriaStore(db_path=base, raiz=tmp, pid="p", session_id=sesion) as s:
                    s.record("file_modified", "Modificó a.py", dedupe_key="file:a.py")
            with MemoriaStore(db_path=base, raiz=tmp, pid="p") as s:
                self.assertEqual(s._total(), 2)

    def test_procesar_dos_veces_el_mismo_evento(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with entorno(ITOSTURRE_MEMORIA_DB=str(Path(tmp) / "m.db"),
                         ITOSTURRE_MEMORIA_LOG=str(Path(tmp) / "h.log")):
                payload = _tool("Edit", {"file_path": "a.py"})
                for _ in range(3):
                    self.assertEqual(procesar(payload, "PostToolUse", raiz=tmp)["accion"],
                                     "almacenado")
                with MemoriaStore(raiz=tmp) as store:
                    self.assertEqual(store._total(), 1)


# ── 6, 7. Aislamiento ────────────────────────────────────────────────────────

@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class Aislamiento(unittest.TestCase):
    def test_entre_proyectos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "compartida.db"
            with MemoriaStore(db_path=base, raiz=tmp, pid="despacho-a") as a:
                a.record("important_context", "expediente 712/2023")
            with MemoriaStore(db_path=base, raiz=tmp, pid="despacho-b") as b:
                b.record("important_context", "expediente 999/2026")
                self.assertEqual(b._total(), 1)
                eventos = b.recall("expediente", limite=10)["eventos"]
                self.assertNotIn("712/2023", " ".join(e["summary"] for e in eventos))

    def test_snapshot_no_cruza_proyectos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "compartida.db"
            with MemoriaStore(db_path=base, raiz=tmp, pid="a", session_id="s") as a:
                a.guardar_snapshot("<estado de A/>")
            with MemoriaStore(db_path=base, raiz=tmp, pid="b", session_id="s") as b:
                self.assertIsNone(b.consumir_snapshot())
                self.assertIsNone(b.ultimo_snapshot())

    def test_entre_sesiones_del_mismo_proyecto(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "m.db"
            with MemoriaStore(db_path=base, raiz=tmp, pid="p", session_id="s1") as s1:
                s1.guardar_snapshot("<estado s1/>")
            with MemoriaStore(db_path=base, raiz=tmp, pid="p", session_id="s2") as s2:
                s2.record("task_started", "trabajo de s2")
                filas = s2.con.execute(
                    "SELECT session_id FROM eventos WHERE summary LIKE '%s2%'"
                ).fetchall()
                self.assertEqual([f["session_id"] for f in filas], ["s2"])


# ── 8, 9. Fallos ─────────────────────────────────────────────────────────────

class FallaSegura(unittest.TestCase):
    """El agente debe poder seguir trabajando pase lo que pase (etapa 7G)."""

    def test_sqlite_inaccesible_no_lanza(self) -> None:
        # Un archivo donde debería haber un directorio: la base no puede abrirse.
        imposible = os.path.join(os.path.abspath(__file__), "sub", "m.db")
        with entorno(ITOSTURRE_MEMORIA_DB=imposible, ITOSTURRE_MEMORIA_LOG=None):
            diag = procesar(_tool("Edit", {"file_path": "a.py"}), "PostToolUse", raiz=".")
        self.assertEqual(diag["accion"], "error")
        self.assertIn("error", diag)
        self.assertIn("ms", diag)

    def test_payload_malformado_no_lanza(self) -> None:
        for basura in ({}, {"tool_name": "Edit"}, {"tool_name": "Edit", "tool_input": "no dict"},
                       {"tool_name": None}, {"prompt": None}):
            with self.subTest(basura=basura):
                self.assertIsNone(clasificar(basura, "PostToolUse"))

    def test_evento_desconocido_se_ignora(self) -> None:
        self.assertIsNone(clasificar(_tool("Edit", {"file_path": "a.py"}), "EventoInventado"))

    def test_interruptor_general_apaga_la_captura(self) -> None:
        with entorno(ITOSTURRE_MEMORIA_HOOKS="off"):
            diag = procesar(_tool("Edit", {"file_path": "a.py"}), "PostToolUse", raiz=".")
        self.assertEqual(diag["accion"], "descartado")
        self.assertIn("desactivados", diag["motivo"])

    def test_los_prompts_se_pueden_desactivar_por_separado(self) -> None:
        with entorno(ITOSTURRE_MEMORIA_PROMPTS="off"):
            self.assertIsNone(clasificar_prompt("No, en realidad usa revocación."))

    def test_la_bitacora_nunca_lanza(self) -> None:
        with entorno(ITOSTURRE_MEMORIA_LOG=os.path.join(os.path.abspath(__file__), "x.log")):
            registrar_diagnostico({"evento": "X", "accion": "prueba"})  # no debe lanzar


# ── 10. Secretos ─────────────────────────────────────────────────────────────

class SinSecretos(unittest.TestCase):
    def test_comando_con_token_se_redacta_al_persistir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with entorno(ITOSTURRE_MEMORIA_DB=str(Path(tmp) / "m.db"),
                         ITOSTURRE_MEMORIA_LOG=str(Path(tmp) / "h.log")):
                payload = _tool("Bash", {
                    "command": "git commit -m 'usa TELEGRAM_BOT_TOKEN="
                               "000000000:FALSO-FIXTURE-DE-PRUEBA-NO-ES-REAL-000'",
                })
                diag = procesar(payload, "PostToolUse", raiz=tmp)
                self.assertEqual(diag["accion"], "almacenado")
                self.assertTrue(diag["redactado"])
                with MemoriaStore(raiz=tmp) as store:
                    crudo = "".join(
                        str(v) for fila in store.con.execute("SELECT * FROM eventos")
                        for v in tuple(fila)
                    )
                self.assertNotIn("FALSO-FIXTURE", crudo)

    def test_la_bitacora_tambien_se_redacta(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            destino = Path(tmp) / "h.log"
            with entorno(ITOSTURRE_MEMORIA_LOG=str(destino)):
                registrar_diagnostico({
                    "evento": "X", "api_key": "no-debe-aparecer",
                    "detalle": "sk-FALSO-FIXTURE-DE-PRUEBA-NO-ES-REAL",
                })
            contenido = destino.read_text(encoding="utf-8")
            self.assertNotIn("no-debe-aparecer", contenido)
            self.assertNotIn("FALSO-FIXTURE", contenido)
            self.assertIn("[REDACTADO]", contenido)

    def test_ruta_de_bitacora_fuera_del_repositorio(self) -> None:
        with entorno(ITOSTURRE_MEMORIA_LOG=None):
            repo = Path(__file__).resolve().parent.parent
            self.assertFalse(str(ruta_log()).startswith(str(repo)))


# ── 12, 13. Memoria vacía y memoria enorme ───────────────────────────────────

@unittest.skipIf(_SIN_FTS5, "SQLite sin FTS5")
class VolumenExtremo(unittest.TestCase):
    def test_memoria_vacia(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p") as store:
                self.assertEqual(store._total(), 0)
                self.assertIsNone(store.consumir_snapshot())
                self.assertEqual(store.recall("lo que sea")["n_devueltos"], 0)
            self.assertIn("Sin eventos previos", construir_snapshot([], project_id="p"))

    def test_diez_mil_eventos_no_desbordan_el_contexto(self) -> None:
        """La promesa del sistema, comprobada con los hooks encima."""
        with tempfile.TemporaryDirectory() as tmp:
            with MemoriaStore(db_path=Path(tmp) / "m.db", raiz=tmp, pid="p",
                              session_id="s") as store:
                store.record_lote([
                    {"event_type": "file_modified",
                     "summary": f"Modificó archivo_{i}.py del expediente {i}",
                     "file_path": f"src/archivo_{i}.py",
                     "timestamp": f"2026-0{(i % 9) + 1}-{(i % 28) + 1:02d}T00:00:00Z"}
                    for i in range(10_000)
                ])
                self.assertEqual(store._total(), 10_000)

                resultado = store.recall("expediente 4242", limite=20, max_bytes=4096)
                self.assertLessEqual(resultado["bytes"], 4096)

                eventos = store.recall("", limite=80, max_bytes=10 ** 7)["eventos"]
                texto = construir_snapshot(eventos, project_id="p",
                                           total_en_memoria=10_000, max_bytes=2048)
                self.assertLessEqual(len(texto.encode("utf-8")), 2048)


if __name__ == "__main__":
    unittest.main()


class CodificacionDelPayload(unittest.TestCase):
    """Regresión de la primera prueba de humo real (fallo 2).

    En Windows `sys.stdin.encoding` es cp1252 y el payload del hook llega en
    UTF-8: leerlo como texto convertía "todavía" en "todavÃ­a" y la corrupción
    se persistía. El hook lee el búfer binario y decodifica a mano.
    """

    def test_el_hook_lee_utf8_sea_cual_sea_la_consola(self) -> None:
        import subprocess

        repo = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as tmp:
            # La variable se fija en ESTE proceso para que el hijo la herede y
            # para que la verificación abra la misma base temporal. Fijarla solo
            # en el hijo dejaba al verificador leyendo la memoria real.
            with entorno(ITOSTURRE_MEMORIA_DB=str(Path(tmp) / "m.db"),
                         ITOSTURRE_MEMORIA_LOG=str(Path(tmp) / "h.log")):
                payload = json.dumps(
                    {"session_id": "utf8", "prompt":
                     "No, en realidad la vía correcta es revocación — ñandú, acentuación."},
                    ensure_ascii=False,
                ).encode("utf-8")
                subprocess.run(
                    [sys.executable, str(repo / "scripts" / "memoria_hook.py"),
                     "UserPromptSubmit"],
                    input=payload, env=dict(os.environ), capture_output=True, timeout=60,
                )
                # El hook corre con `raiz=REPO`, así que su project_id es el del
                # repositorio: verificar con otra raíz daría cero filas por
                # aislamiento, no por fallo del hook.
                with MemoriaStore(raiz=repo) as store:
                    filas = store.con.execute("SELECT summary FROM eventos").fetchall()
            self.assertEqual(len(filas), 1, "el hook no registró el evento")
            resumen = filas[0]["summary"]
            for esperado in ("vía", "revocación", "ñandú", "acentuación"):
                with self.subTest(palabra=esperado):
                    self.assertIn(esperado, resumen)
            self.assertNotIn("Ã", resumen)
