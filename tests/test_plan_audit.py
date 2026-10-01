"""Pruebas del auditor determinista de planes (``itosturre/plan`` y ``plan_audit.py``).

Todo es sintético: sin red, sin corpus, sin LLM y sin datos de clientes.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import subprocess
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

import plan_audit
from itosturre.plan import (
    APROBADO,
    LedgerInvalido,
    contenido_sha256,
    esta_bloqueado,
    estado_mostrado,
    extraer_menciones,
    lint_ledger,
    normalizar_estado,
    problema_persona,
    reporte_markdown,
    responsable_no_humano,
    url_oficial,
    validar_esquema,
)
from itosturre.plan.estados import ESTADO_INVALIDO
from itosturre.plan.lint import ALTA, BLOQUEANTE, MEDIA
from scripts.evaluate_plan_gold_set import (
    PlanGoldSetInvalido,
    evaluar_gold_set,
    validar_dataset,
)

REPO = Path(__file__).resolve().parent.parent
PLAN_AUDIT = REPO / "plan_audit.py"
GOLD_SET = REPO / "tests" / "fixtures" / "plan_gold_set_v1.json"
HUMANO = "Lic. Persona Ficticia"

DOCUMENTO = (
    "# Plan sintético\n"
    "1. Plazo del art. 471 CNPP.\n"
    "2. Criterio P./J. 20/2014 (10a.), registro digital: 2006224.\n"
    "3. No existe un art. 19 Ter en la CPEUM.\n"
)


def _evidencia(id_: str, **cambios: object) -> dict:
    evidencia = {
        "id": id_,
        "naturaleza": "compilado_oficial",
        "url": "https://www.diputados.gob.mx/LeyesBiblio/pdf/CNPP.pdf",
        "ubicacion": "Artículo 471",
        "extracto": "Extracto sintético de prueba con más de veinte caracteres.",
        "fecha_consulta": "2026-09-28",
        "sha256_documento": None,
        "consulta": None,
        "resultados": None,
    }
    evidencia.update(cambios)
    return evidencia


def _afirmacion(
    id_: str,
    texto: str,
    *,
    tipo: str = "texto_normativo",
    autor: str = "agente",
    estado: str = "VERIFICADO",
    evidencias: tuple[str, ...] = (),
    referencias: tuple[str, ...] = (),
    **extra: object,
) -> dict:
    afirmacion = {
        "id": id_,
        "texto": texto,
        "tipo": tipo,
        "autor": autor,
        "referencias": list(referencias),
        "verificacion": {"estado": estado, "evidencias": list(evidencias), "motivo": ""},
        "aprobacion": None,
    }
    afirmacion.update(extra)
    return afirmacion


def _aprobar(afirmacion: dict, por: str = HUMANO) -> dict:
    afirmacion["aprobacion"] = {
        "por": por,
        "en": "2026-09-30",
        "contenido_sha256": contenido_sha256(afirmacion),
    }
    return afirmacion


def ledger_limpio() -> dict:
    """Ledger sintético que no debe producir ningún hallazgo."""
    return {
        "schema_version": "plan-ledger/1.0",
        "plan": {"id": "PLAN-T", "titulo": "Plan de prueba", "fecha_documento": "2026-09-30"},
        "afirmaciones": [
            _afirmacion(
                "A1",
                "El art. 471 CNPP fija el plazo de apelación (afirmación sintética).",
                evidencias=("E1",),
                referencias=("art. 471 CNPP",),
            ),
            _afirmacion(
                "A2",
                "Jurisprudencia P./J. 20/2014 (10a.), registro digital 2006224 (sintético).",
                tipo="criterio_judicial",
                evidencias=("E2",),
                referencias=("registro 2006224",),
                identificacion_criterio={
                    "rubro": "RUBRO SINTÉTICO DE PRUEBA",
                    "clave": "P./J. 20/2014 (10a.)",
                    "organo": "Pleno de la SCJN",
                    "epoca": "Décima Época",
                    "registro": "2006224",
                    "integracion": "Contradicción de tesis 293/2011",
                    "publicacion": "Gaceta del SJF (dato de prueba)",
                    "obligatoriedad": "Dato de prueba",
                    "fuerza_vinculante": "[J] Obligatoria",
                    "alcance": "Nacional",
                },
            ),
            _aprobar(
                _afirmacion(
                    "A3",
                    "Proponer la apelación dentro de 3 días (propuesta sintética).",
                    tipo="propuesta",
                    estado="REQUIERE DECISIÓN HUMANA",
                )
            ),
            _afirmacion(
                "A4",
                "No existe un art. 19 Ter en la CPEUM (afirmación sintética).",
                estado="INEXISTENTE",
                evidencias=("E3",),
            ),
            _afirmacion("A5", "Notificado el día 25 (ficticio).", tipo="hecho_aportado",
                        autor="humano", estado="CONTRADICCIÓN"),
            _afirmacion("A6", "Notificado el día 26 (ficticio).", tipo="hecho_aportado",
                        autor="fuente", estado="CONTRADICCIÓN"),
        ],
        "evidencias": [
            _evidencia("E1"),
            _evidencia(
                "E2",
                naturaleza="portal_oficial",
                url="https://sjf2.scjn.gob.mx/detalle/tesis/2006224",
                ubicacion="Registro digital 2006224",
            ),
            _evidencia(
                "E3",
                url="https://www.diputados.gob.mx/LeyesBiblio/pdf/CPEUM.pdf",
                ubicacion="Artículos 19 y 20",
            ),
        ],
        "contradicciones": [
            {
                "id": "C1",
                "afirmaciones": ["A5", "A6"],
                "descripcion": "Fechas distintas (ficticias).",
                "estado": "CONTRADICCIÓN",
                "decision_id": "D2",
            }
        ],
        "decisiones": [
            {"id": "D1", "pregunta": "¿Apelar?", "responsable": HUMANO,
             "estado": "APROBADO", "bloquea": ["A3"]},
            {"id": "D2", "pregunta": "¿Qué fecha consta?", "responsable": HUMANO,
             "estado": "REQUIERE DECISIÓN HUMANA", "bloquea": ["C1"]},
        ],
    }


def _af(ledger: dict, id_: str) -> dict:
    return next(a for a in ledger["afirmaciones"] if a["id"] == id_)


def _ev(ledger: dict, id_: str) -> dict:
    return next(e for e in ledger["evidencias"] if e["id"] == id_)


def _reglas(ledger: dict, documento: str | None = None) -> set[str]:
    return {h["regla"] for h in lint_ledger(ledger, documento=documento)}


class EstadosTests(unittest.TestCase):
    def test_normaliza_mayusculas_acentos_y_espacios(self) -> None:
        self.assertEqual(normalizar_estado("verificado"), "VERIFICADO")
        self.assertEqual(normalizar_estado("  No   Verificado "), "NO VERIFICADO")
        self.assertEqual(normalizar_estado("CONTRADICCION"), "CONTRADICCIÓN")
        self.assertEqual(normalizar_estado("requiere decision humana"), "REQUIERE DECISIÓN HUMANA")

    def test_rechaza_sinonimos_y_simbolos(self) -> None:
        for sinonimo in ("CONFIRMADO", "OK", "PENDIENTE", "✅", "🟢", "", "NO_VERIFICADO", None, 3):
            with self.subTest(sinonimo=sinonimo):
                self.assertIsNone(normalizar_estado(sinonimo))

    def test_aprobado_es_otra_dimension(self) -> None:
        self.assertIsNone(normalizar_estado("APROBADO"))
        self.assertEqual(normalizar_estado("aprobado", admitir_aprobado=True), APROBADO)

    def test_estado_mostrado_aprobado_solo_con_aprobacion_valida(self) -> None:
        ledger = ledger_limpio()
        self.assertEqual(estado_mostrado(_af(ledger, "A3")), APROBADO)
        self.assertEqual(estado_mostrado(_af(ledger, "A1")), "VERIFICADO")
        _af(ledger, "A3")["aprobacion"]["por"] = "Claude"
        self.assertEqual(estado_mostrado(_af(ledger, "A3")), "REQUIERE DECISIÓN HUMANA")
        _af(ledger, "A1")["verificacion"]["estado"] = "OK"
        self.assertEqual(estado_mostrado(_af(ledger, "A1")), ESTADO_INVALIDO)

    def test_responsables_no_humanos(self) -> None:
        for nombre in (
            "Claude",
            "ChatGPT 4o",
            "gpt-4o",
            "gpt4o",
            "Claude Opus 5.5",
            "Codex CLI",
            "Anthropic Claude",
            "Claude (agente)",
            "itosclaude_bot",
            "Sistema VVCA",
            "IA",
        ):
            with self.subTest(nombre=nombre):
                self.assertTrue(responsable_no_humano(nombre))

    def test_personas_validas_no_se_rechazan(self) -> None:
        for nombre in (
            "Patricia García",
            "Lic. Persona Ficticia",
            "Mtra. Iára Díaz",
            "Claude Martínez",
            "Talbot",
            "Itosturre (responsable jurídico)",
            "JustIA (capa técnica)",
        ):
            with self.subTest(nombre=nombre):
                self.assertFalse(responsable_no_humano(nombre))
                self.assertIsNone(problema_persona(nombre))

    def test_problema_persona_marcadores_y_letras(self) -> None:
        casos = {
            "[ASIGNAR]": "marcador pendiente",
            "Lic. [COMPLETAR]": "marcador pendiente",
            "[Verificar en SJF]": "marcador pendiente",
            "J.": "menos de 3 letras",
            "AB 12": "menos de 3 letras",
            "": "vacío",
            None: "vacío",
            "Claude Opus": "agente o sistema",
        }
        for valor, esperado in casos.items():
            with self.subTest(valor=valor):
                self.assertIn(esperado, problema_persona(valor) or "")


class HashTests(unittest.TestCase):
    def test_hash_estable_ante_espacios_y_forma_unicode(self) -> None:
        base = {"tipo": "propuesta", "texto": "Apelación dentro de 3 días"}
        variante = {
            "tipo": " propuesta ",
            "texto": unicodedata.normalize("NFD", "  Apelación   dentro de\n3 días "),
        }
        self.assertEqual(contenido_sha256(base), contenido_sha256(variante))

    def test_hash_cambia_con_texto_o_tipo(self) -> None:
        base = {"tipo": "propuesta", "texto": "Apelación dentro de 3 días"}
        self.assertNotEqual(
            contenido_sha256(base), contenido_sha256({**base, "texto": "Apelación dentro de 5 días"})
        )
        self.assertNotEqual(contenido_sha256(base), contenido_sha256({**base, "tipo": "inferencia"}))

    def test_editar_invalida_la_aprobacion(self) -> None:
        ledger = ledger_limpio()
        _af(ledger, "A3")["texto"] = "Proponer la apelación dentro de 5 días (editada)."
        self.assertNotEqual(estado_mostrado(_af(ledger, "A3")), APROBADO)
        self.assertIn("PL-010", _reglas(ledger))


class LedgerSchemaTests(unittest.TestCase):
    def test_ledger_limpio_es_valido(self) -> None:
        self.assertEqual(validar_esquema(ledger_limpio()), [])

    def test_colecciones_opcionales(self) -> None:
        ledger = ledger_limpio()
        del ledger["contradicciones"]
        del ledger["decisiones"]
        for afirmacion in ledger["afirmaciones"]:
            if afirmacion["verificacion"]["estado"] == "CONTRADICCIÓN":
                afirmacion["verificacion"]["estado"] = "NO VERIFICADO"
        self.assertEqual(validar_esquema(ledger), [])

    def test_errores_estructurales(self) -> None:
        ledger = ledger_limpio()
        ledger["schema_version"] = "plan-ledger/0.9"
        ledger["plan"]["fecha_documento"] = "20260930"
        _af(ledger, "A1")["tipo"] = "opinion"
        _ev(ledger, "E1")["resultados"] = -1
        errores = validar_esquema(ledger)
        self.assertEqual(len(errores), 4, errores)
        with self.assertRaises(LedgerInvalido):
            lint_ledger(ledger)

    def test_raiz_no_objeto(self) -> None:
        self.assertEqual(validar_esquema([]), ["raíz: debe ser un objeto JSON"])


class ReglasTests(unittest.TestCase):
    def test_ledger_limpio_sin_hallazgos(self) -> None:
        self.assertEqual(lint_ledger(ledger_limpio(), documento=DOCUMENTO), [])

    def test_pl001_vocabulario(self) -> None:
        ledger = ledger_limpio()
        _af(ledger, "A1")["verificacion"]["estado"] = "  verificado "
        self.assertNotIn("PL-001", _reglas(ledger))
        _af(ledger, "A1")["verificacion"]["estado"] = "CONFIRMADO"
        ledger["decisiones"][1]["estado"] = "PENDIENTE"
        hallazgos = [h for h in lint_ledger(ledger) if h["regla"] == "PL-001"]
        self.assertEqual({h["objetivo"] for h in hallazgos}, {"A1", "D2"})
        self.assertTrue(all(h["severidad"] == BLOQUEANTE for h in hallazgos))

    def test_pl001_aprobado_como_verificacion(self) -> None:
        ledger = ledger_limpio()
        _af(ledger, "A1")["verificacion"]["estado"] = "APROBADO"
        mensajes = [h["mensaje"] for h in lint_ledger(ledger) if h["regla"] == "PL-001"]
        self.assertTrue(any("aprobacion" in m for m in mensajes))

    def test_pl002_verificado_sin_evidencias(self) -> None:
        ledger = ledger_limpio()
        self.assertNotIn("PL-002", _reglas(ledger))
        _af(ledger, "A1")["verificacion"]["evidencias"] = []
        self.assertIn("PL-002", _reglas(ledger))

    def test_pl003_evidencia_no_oficial(self) -> None:
        for cambio in (
            {"naturaleza": "secundaria"},
            {"naturaleza": "busqueda"},
            {"url": "http://www.diputados.gob.mx/LeyesBiblio/pdf/CNPP.pdf"},
            {"url": "https://dof.gob.mx.example.com/nota"},
            {"url": "https://www.diputados.gob.mx@evil.example/CNPP.pdf"},
            {"url": "https://www.diputados.gob.mx:8443/CNPP.pdf"},
            {"url": None},
        ):
            with self.subTest(cambio=cambio):
                ledger = ledger_limpio()
                _ev(ledger, "E1").update(cambio)
                self.assertIn("PL-003", _reglas(ledger))

    def test_pl003_url_marcador_y_host_www_dof(self) -> None:
        ledger = ledger_limpio()
        _ev(ledger, "E1")["url"] = "[ASIGNAR]"
        mensajes = [h["mensaje"] for h in lint_ledger(ledger) if h["regla"] == "PL-003"]
        self.assertTrue(any("marcador pendiente" in m for m in mensajes), mensajes)

        ledger = ledger_limpio()
        _ev(ledger, "E1")["url"] = "https://www.dof.gob.mx/nota_detalle.php?codigo=5746525"
        mensajes = [h["mensaje"] for h in lint_ledger(ledger) if h["regla"] == "PL-003"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("host canónico dof.gob.mx", mensajes[0])

    def test_pl003_hosts_oficiales_validos(self) -> None:
        for url in (
            "https://DOF.GOB.MX./nota_detalle.php?codigo=5746525",
            "https://dof.gob.mx:443/nota_detalle.php?codigo=5746525",
            "https://www.corteidh.or.cr/docs/casos/articulos/seriec_1_esp.pdf",
        ):
            with self.subTest(url=url):
                self.assertTrue(url_oficial(url))
        self.assertFalse(url_oficial("https://www.dof.gob.mx/nota_detalle.php?codigo=5746525"))
        self.assertTrue(url_oficial("https://intranet.example/x", hosts={"intranet.example"}))
        ledger = ledger_limpio()
        _af(ledger, "A1")["verificacion"]["estado"] = "NO VERIFICADO"
        _ev(ledger, "E1")["naturaleza"] = "secundaria"
        self.assertNotIn("PL-003", _reglas(ledger))

    def test_pl004_sin_ubicacion(self) -> None:
        ledger = ledger_limpio()
        self.assertNotIn("PL-004", _reglas(ledger))
        for ubicacion in ("  ", "[ASIGNAR]", "[COMPLETAR ubicación]", None):
            with self.subTest(ubicacion=ubicacion):
                _ev(ledger, "E1")["ubicacion"] = ubicacion
                self.assertIn("PL-004", _reglas(ledger))

    def test_pl005_extracto_minimo(self) -> None:
        ledger = ledger_limpio()
        _ev(ledger, "E1")["extracto"] = "x" * 20
        self.assertNotIn("PL-005", _reglas(ledger))
        _ev(ledger, "E1")["extracto"] = "  " + "x" * 19 + "   "
        self.assertIn("PL-005", _reglas(ledger))

    def test_pl005_extracto_marcador_aunque_sea_largo(self) -> None:
        ledger = ledger_limpio()
        _ev(ledger, "E1")["extracto"] = "[VERIFICAR EXTRACTO LITERAL]"
        mensajes = [h["mensaje"] for h in lint_ledger(ledger) if h["regla"] == "PL-005"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("marcador pendiente", mensajes[0])

    def test_pl006_fecha_consulta(self) -> None:
        ledger = ledger_limpio()
        _ev(ledger, "E1")["fecha_consulta"] = "2026-09-30"  # mismo día: válido
        self.assertNotIn("PL-006", _reglas(ledger))
        for fecha in ("2026-10-01", "20260928", "28/09/2026", None, "2026-02-30"):
            with self.subTest(fecha=fecha):
                _ev(ledger, "E1")["fecha_consulta"] = fecha
                self.assertIn("PL-006", _reglas(ledger))

    def test_pl007_identificacion_criterio(self) -> None:
        ledger = ledger_limpio()
        identificacion = _af(ledger, "A2")["identificacion_criterio"]
        identificacion["alcance"] = ""
        identificacion["publicacion"] = "[VERIFICAR EN SJF]"
        mensajes = [h["mensaje"] for h in lint_ledger(ledger) if h["regla"] == "PL-007"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("alcance", mensajes[0])
        self.assertIn("publicacion", mensajes[0])
        _af(ledger, "A2")["verificacion"]["estado"] = "CANDIDATO"
        self.assertNotIn("PL-007", _reglas(ledger))

    def test_pl007_valores_no_texto_cuentan_como_faltantes(self) -> None:
        for valor in (False, 0, True, 2006224, [], ["x"], {}):
            with self.subTest(valor=valor):
                ledger = ledger_limpio()
                identificacion = _af(ledger, "A2")["identificacion_criterio"]
                for campo in identificacion:
                    identificacion[campo] = valor
                mensajes = [h["mensaje"] for h in lint_ledger(ledger) if h["regla"] == "PL-007"]
                self.assertEqual(len(mensajes), 1)
                self.assertIn(f"no es texto ({type(valor).__name__})", mensajes[0])
                self.assertIn("fuerza_vinculante", mensajes[0])

    def test_pl008_inexistente(self) -> None:
        ledger = ledger_limpio()
        self.assertNotIn("PL-008", _reglas(ledger))
        _ev(ledger, "E3").update(naturaleza="busqueda", url=None, resultados=0)
        self.assertIn("PL-008", _reglas(ledger))
        ledger = ledger_limpio()
        _ev(ledger, "E3").update(naturaleza="portal_oficial",
                                  url="https://sjf2.scjn.gob.mx/busqueda", resultados=0)
        self.assertIn("PL-008", _reglas(ledger))
        ledger = ledger_limpio()
        _ev(ledger, "E3")["extracto"] = ""
        self.assertIn("PL-008", _reglas(ledger))

    def test_pl009_propuesta_o_inferencia_del_agente(self) -> None:
        ledger = ledger_limpio()
        _af(ledger, "A3")["verificacion"].update(estado="VERIFICADO", evidencias=["E1"])
        self.assertIn("PL-009", _reglas(ledger))
        _af(ledger, "A3")["autor"] = "humano"
        self.assertNotIn("PL-009", _reglas(ledger))

    def test_pl010_aprobacion_invalida(self) -> None:
        self.assertNotIn("PL-010", _reglas(ledger_limpio()))
        casos = {
            "por_agente": lambda l: _af(l, "A3")["aprobacion"].update(por="GPT"),
            "por_modelo": lambda l: _af(l, "A3")["aprobacion"].update(por="Claude Opus 5.5"),
            "por_marcador": lambda l: _af(l, "A3")["aprobacion"].update(por="[ASIGNAR]"),
            "por_sin_letras": lambda l: _af(l, "A3")["aprobacion"].update(por="AB"),
            "sin_hash": lambda l: _af(l, "A3")["aprobacion"].pop("contenido_sha256"),
            "fecha_invalida": lambda l: _af(l, "A3")["aprobacion"].update(en="ayer"),
            "copiada": lambda l: _af(l, "A1").update(
                aprobacion=copy.deepcopy(_af(l, "A3")["aprobacion"])
            ),
            "vacia": lambda l: _af(l, "A1").update(aprobacion={}),
        }
        for nombre, mutar in casos.items():
            with self.subTest(caso=nombre):
                ledger = ledger_limpio()
                mutar(ledger)
                self.assertIn("PL-010", _reglas(ledger))

    def test_pl011_contradicciones(self) -> None:
        ledger = ledger_limpio()
        ledger["contradicciones"][0]["estado"] = "APROBADO"  # con decision_id: válido
        self.assertNotIn("PL-011", _reglas(ledger))
        ledger["contradicciones"][0]["decision_id"] = None
        self.assertIn("PL-011", _reglas(ledger))

        ledger = ledger_limpio()
        ledger["contradicciones"][0]["afirmaciones"] = ["A5", "A5"]
        objetivos = {h["objetivo"] for h in lint_ledger(ledger) if h["regla"] == "PL-011"}
        self.assertEqual(objetivos, {"C1", "A6"})

        hallazgos = lint_ledger(ledger)
        self.assertTrue(all(h["severidad"] == ALTA for h in hallazgos if h["regla"] == "PL-011"))
        self.assertFalse(esta_bloqueado(hallazgos))

    def test_pl012_responsable_humano(self) -> None:
        self.assertNotIn("PL-012", _reglas(ledger_limpio()))
        for responsable in (
            None, "   ", "Codex", "agente itosturre", "[ASIGNAR]", "X", "Claude Opus"
        ):
            with self.subTest(responsable=responsable):
                ledger = ledger_limpio()
                ledger["decisiones"][1]["responsable"] = responsable
                self.assertIn("PL-012", _reglas(ledger))
        ledger = ledger_limpio()
        ledger["decisiones"][0]["responsable"] = "Itosturre (responsable jurídico)"
        ledger["decisiones"][1]["responsable"] = "JustIA (capa técnica)"
        self.assertNotIn("PL-012", _reglas(ledger))

    def test_pl013_severidad_segun_afecte_a_verificado(self) -> None:
        self.assertNotIn("PL-013", _reglas(ledger_limpio()))
        ledger = ledger_limpio()
        ledger["afirmaciones"].append(copy.deepcopy(_af(ledger, "A5")))
        hallazgos = [h for h in lint_ledger(ledger) if h["regla"] == "PL-013"]
        self.assertEqual([h["severidad"] for h in hallazgos], [MEDIA])

        ledger = ledger_limpio()
        _af(ledger, "A1")["verificacion"]["evidencias"] = ["E1", "E404"]
        ledger["decisiones"][0]["bloquea"] = ["A3", "X9"]
        severidades = {
            h["objetivo"]: h["severidad"] for h in lint_ledger(ledger) if h["regla"] == "PL-013"
        }
        self.assertEqual(severidades, {"A1": BLOQUEANTE, "D1": MEDIA})

    def test_pl013_evidencia_duplicada_de_verificado_bloquea(self) -> None:
        ledger = ledger_limpio()
        ledger["evidencias"].append(_evidencia("E1", naturaleza="secundaria"))
        hallazgos = lint_ledger(ledger)
        self.assertIn(("PL-013", BLOQUEANTE), {(h["regla"], h["severidad"]) for h in hallazgos})
        self.assertIn("PL-003", {h["regla"] for h in hallazgos})

    def test_pl014_cobertura(self) -> None:
        ledger = ledger_limpio()
        self.assertNotIn("PL-014", _reglas(ledger, documento=None))
        self.assertNotIn("PL-014", _reglas(ledger, documento=DOCUMENTO))
        documento = DOCUMENTO + "4. Ver registro 2012345 y P./J. 20/2014 (9a.).\n"
        hallazgos = [h for h in lint_ledger(ledger, documento=documento) if h["regla"] == "PL-014"]
        self.assertEqual(len(hallazgos), 2)
        self.assertTrue(all(h["objetivo"] == "documento:L5" for h in hallazgos))

    def test_pl014_sufijo_no_cubierto_por_numero_base(self) -> None:
        ledger = ledger_limpio()
        ledger["afirmaciones"] = [a for a in ledger["afirmaciones"] if a["id"] != "A4"]
        ledger["afirmaciones"].append(
            _afirmacion("A9", "El art. 19 CPEUM (sintética).", estado="CANDIDATO",
                        referencias=("art. 19 CPEUM",))
        )
        mensajes = [h["mensaje"] for h in lint_ledger(ledger, documento=DOCUMENTO)
                    if h["regla"] == "PL-014"]
        self.assertEqual(len(mensajes), 1)
        self.assertIn("art. 19 ter CPEUM", mensajes[0])
        self.assertIn("art. 19 Ter", mensajes[0])  # conserva el original

    def test_pl014_cobertura_sensible_al_ordenamiento(self) -> None:
        ledger = ledger_limpio()  # A1 cubre art. 471 CNPP
        casos = {
            "Plazo del art. 471 del Código Nacional de Procedimientos Penales.": False,
            "Plazo del artículo 471.": False,  # sin ley: basta el número
            "Plazo del art. 471 CPEUM.": True,  # misma cifra, otra ley
            "Ver el artículo 999.": True,  # sin ley y sin cobertura: ambigua
        }
        for documento, esperado in casos.items():
            with self.subTest(documento=documento):
                hallazgos = [
                    h for h in lint_ledger(ledger, documento=documento) if h["regla"] == "PL-014"
                ]
                self.assertEqual(bool(hallazgos), esperado)
        ambigua = lint_ledger(ledger, documento="Ver el artículo 999.")[0]["mensaje"]
        self.assertIn("ambigua", ambigua)
        con_ley = lint_ledger(ledger, documento="Plazo del art. 471 CPEUM.")[0]["mensaje"]
        self.assertNotIn("ambigua", con_ley)

    def test_pl014_afirmacion_sin_ley_no_cubre_mencion_con_ley(self) -> None:
        ledger = ledger_limpio()
        ledger["afirmaciones"].append(
            _afirmacion("A9", "El art. 20 regula la audiencia (sintética).", estado="CANDIDATO")
        )
        self.assertNotIn("PL-014", _reglas(ledger, documento="Ver art. 20."))
        self.assertIn("PL-014", _reglas(ledger, documento="Ver art. 20 CNPP."))

    def test_pl014_clave_con_materia_distinta(self) -> None:
        ledger = ledger_limpio()
        ledger["afirmaciones"].append(
            _afirmacion("A9", "Criterio PR.A.CS. J/1 A (11a.) (sintético).", estado="CANDIDATO")
        )
        self.assertNotIn("PL-014", _reglas(ledger, documento="Ver PR.A.CS. J/1 A (11a.)."))
        self.assertNotIn("PL-014", _reglas(ledger, documento="Ver PR.A.CS. J/1."))
        self.assertIn("PL-014", _reglas(ledger, documento="Ver PR.A.CS. J/1 P (11a.)."))


class MencionesTests(unittest.TestCase):
    def _claves(self, texto: str) -> list[str]:
        return [m.normalizada for m in extraer_menciones(texto)]

    def test_enumeraciones(self) -> None:
        self.assertEqual(
            self._claves("Los artículos 14, 16 y 17 CPEUM; arts. 1o. y 133."),
            ["art. 14 CPEUM", "art. 16 CPEUM", "art. 17 CPEUM", "art. 1", "art. 133"],
        )

    def test_ordenamiento_a_la_derecha(self) -> None:
        casos = {
            "art. 19 CNPP": "CNPP",
            "artículo 19 constitucional": "CPEUM",
            "ARTÍCULO 19 DE LA CONSTITUCIÓN POLÍTICA DE LOS ESTADOS UNIDOS MEXICANOS": "CPEUM",
            "art. 217 LA, fracción I": "LA",
            "artículo 217 de la Ley de Amparo": "LA",
            "artículo 471, fracción III, del Código Nacional de Procedimientos Penales": "CNPP",
            "art. 8 de la Convención Americana sobre Derechos Humanos": "CADH",
            "art. 2 LFCDO": "LFDO",
            "art. 19. El CNPP regula otra cosa": None,  # fin de oración
            "art. 5 de un ordenamiento cuyo nombre aparece lejos: CNPP": None,  # > 40
            "art. 3 de la ley local": None,
        }
        for texto, ley in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(extraer_menciones(texto)[0].ley, ley)

    def test_ordenamiento_no_se_roba_de_otro_articulo(self) -> None:
        menciones = extraer_menciones("art. 19 y art. 20 CNPP")
        self.assertEqual([(m.clave, m.ley) for m in menciones],
                         [("art. 19", None), ("art. 20", "CNPP")])
        self.assertTrue(menciones[0].ambigua)
        self.assertFalse(menciones[1].ambigua)

    def test_sufijos(self) -> None:
        self.assertEqual(
            self._claves("art. 19 Ter, Art. 19-Bis, artículo 21 Quáter, art. 5 quinquies"),
            ["art. 19 ter", "art. 19 bis", "art. 21 quater", "art. 5 quinquies"],
        )
        self.assertEqual(self._claves("el artículo 19 tercer párrafo"), ["art. 19"])

    def test_falsos_positivos(self) -> None:
        self.assertEqual(self._claves("Ver apart. 3 y Smart 5; artes 4; arte 9."), [])
        self.assertEqual(self._claves("El artículo 471, 3 días para autos."), ["art. 471"])

    def test_registros(self) -> None:
        self.assertEqual(
            self._claves("REGISTRO DIGITAL: 2006224 · reg. 168124 · IUS 2012345 · registro 123"),
            ["registro 2006224", "registro 168124", "registro 2012345"],
        )

    def test_claves_de_tesis(self) -> None:
        self.assertEqual(
            self._claves(
                "P./J. 20/2014 (10a.); 1a./J. 68/2022; 2a. CCLXX/2015 (10a.); "
                "PR.A.CS. J/1 A (11a.); PC.III.P. J/12 P (10a.); I.3o.C. J/12 (10a.)"
            ),
            [
                "p./j. 20/2014 (10a.)",
                "1a./j. 68/2022",
                "2a. cclxx/2015 (10a.)",
                "pr.a.cs. j/1 a (11a.)",
                "pc.iii.p. j/12 p (10a.)",
                "i.3o.c. j/12 (10a.)",
            ],
        )

    def test_materia_solo_si_la_sigue_epoca_o_puntuacion(self) -> None:
        self.assertEqual(extraer_menciones("PR.P.CN. J/1 P.")[0].materia, "P")
        self.assertIsNone(extraer_menciones("PR.P.CN. J/1 A la fecha")[0].materia)

    def test_original_conserva_acentos_y_linea(self) -> None:
        menciones = extraer_menciones("Primera línea\nVer artículos 14 y 16.")
        self.assertEqual(menciones[1].original, "artículos 14 y 16")
        self.assertEqual(menciones[1].linea, 2)


class ReporteTests(unittest.TestCase):
    def test_reporte_bloqueado_con_tabla_y_asignar(self) -> None:
        ledger = ledger_limpio()
        _af(ledger, "A1")["verificacion"]["evidencias"] = []
        ledger["decisiones"][1]["responsable"] = None
        ledger["decisiones"][1]["pregunta"] = "¿Fecha a | b?"
        hallazgos = lint_ledger(ledger)
        reporte = reporte_markdown(ledger, hallazgos)
        self.assertIn("**Resultado:** BLOQUEADO", reporte)
        self.assertIn(
            "| ID | Hallazgo / decisión | Evidencia | Estado | Responsable | Bloquea | "
            "Acción siguiente |",
            reporte,
        )
        self.assertIn("[ASIGNAR]", reporte)
        self.assertIn("a \\| b", reporte)
        self.assertIn("| APROBADO | 1 |", reporte)

    def test_reporte_limpio_no_promete_aprobacion_juridica(self) -> None:
        reporte = reporte_markdown(ledger_limpio(), [])
        self.assertIn("sin hallazgos bloqueantes", reporte)
        self.assertIn("decisión del abogado", reporte)


class CliTests(unittest.TestCase):
    def _ejecutar(self, *argumentos: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(PLAN_AUDIT), *argumentos],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def _escribir(self, carpeta: Path, nombre: str, contenido: str, *, bom: bool = False) -> Path:
        ruta = carpeta / nombre
        ruta.write_text(contenido, encoding="utf-8-sig" if bom else "utf-8")
        return ruta

    def test_codigos_de_salida(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            carpeta = Path(temp)
            limpio = self._escribir(carpeta, "limpio.json", json.dumps(ledger_limpio()), bom=True)
            documento = self._escribir(carpeta, "plan.md", DOCUMENTO)
            bloqueado_ledger = ledger_limpio()
            _ev(bloqueado_ledger, "E1")["url"] = "https://dof.gob.mx.example.com/x"
            bloqueado = self._escribir(carpeta, "bloqueado.json", json.dumps(bloqueado_ledger))
            roto = self._escribir(carpeta, "roto.json", "{ no es json")
            invalido = self._escribir(carpeta, "invalido.json", json.dumps({"schema_version": "x"}))

            resultado = self._ejecutar("lint", "--ledger", str(limpio), "--documento", str(documento))
            self.assertEqual(resultado.returncode, 0, resultado.stdout + resultado.stderr)
            self.assertEqual(self._ejecutar("lint", "--ledger", str(bloqueado)).returncode, 1)
            self.assertEqual(self._ejecutar("lint", "--ledger", str(roto)).returncode, 2)
            self.assertEqual(self._ejecutar("lint", "--ledger", str(invalido)).returncode, 2)
            self.assertEqual(
                self._ejecutar("lint", "--ledger", str(carpeta / "no-existe.json")).returncode, 2
            )

    def test_salidas_json_md_y_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            carpeta = Path(temp)
            ledger = ledger_limpio()
            ledger["decisiones"][1]["responsable"] = None  # ALTA: no bloquea
            entrada = self._escribir(carpeta, "ledger.json", json.dumps(ledger))
            salida_json = carpeta / "hallazgos.json"
            salida_md = carpeta / "reporte.md"
            resultado = self._ejecutar(
                "lint", "--ledger", str(entrada), "--json", str(salida_json), "--md", str(salida_md)
            )
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            datos = json.loads(salida_json.read_text(encoding="utf-8"))
            self.assertFalse(datos["bloqueado"])
            self.assertEqual(datos["resumen"]["ALTA"], 1)
            self.assertIn("[ASIGNAR]", salida_md.read_text(encoding="utf-8"))

            resultado = self._ejecutar("hash", "--ledger", str(entrada), "--afirmacion", "A3")
            self.assertEqual(resultado.returncode, 0, resultado.stderr)
            self.assertEqual(
                resultado.stdout.strip(), f"A3\t{contenido_sha256(_af(ledger, 'A3'))}"
            )

    def test_destinos_que_colisionan_o_no_son_escribibles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            carpeta = Path(temp)
            contenido_ledger = json.dumps(ledger_limpio())
            ledger = self._escribir(carpeta, "ledger.json", contenido_ledger)
            documento = self._escribir(carpeta, "plan.md", DOCUMENTO)
            salida = str(carpeta / "salida.json")
            casos = {
                "json_igual_md": ["--json", salida, "--md", salida],
                "json_igual_md_por_alias": [
                    "--json", salida, "--md", str(carpeta / "sub" / ".." / "salida.json")
                ],
                "json_igual_ledger": ["--json", str(ledger)],
                "md_igual_documento": ["--documento", str(documento), "--md", str(documento)],
                "destino_directorio": ["--md", str(carpeta)],
                "directorio_inexistente": [
                    "--json", salida, "--md", str(carpeta / "no-existe" / "r.md")
                ],
            }
            (carpeta / "sub").mkdir()
            for nombre, extra in casos.items():
                with self.subTest(caso=nombre):
                    resultado = self._ejecutar("lint", "--ledger", str(ledger), *extra)
                    self.assertEqual(resultado.returncode, 2, resultado.stdout + resultado.stderr)
                    self.assertNotIn("Traceback", resultado.stderr)
                    self.assertIn("Entrada inválida", resultado.stderr)
            # Nada se escribió y las entradas siguen intactas.
            self.assertFalse(Path(salida).exists())
            self.assertEqual(ledger.read_text(encoding="utf-8"), contenido_ledger)
            self.assertEqual(documento.read_text(encoding="utf-8"), DOCUMENTO)

    def test_error_de_escritura_devuelve_2_sin_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            carpeta = Path(temp)
            ledger = self._escribir(carpeta, "ledger.json", json.dumps(ledger_limpio()))
            errores = io.StringIO()
            with (
                patch("pathlib.Path.write_text", side_effect=PermissionError("denegado")),
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(errores),
            ):
                codigo = plan_audit.main(
                    ["lint", "--ledger", str(ledger), "--json", str(carpeta / "h.json")]
                )
            self.assertEqual(codigo, 2)
            self.assertIn("no se pudo escribir", errores.getvalue())


class GoldSetTests(unittest.TestCase):
    def test_gold_set_pasa_con_recall_completo(self) -> None:
        reporte = evaluar_gold_set(GOLD_SET)
        fallidos = [r for r in reporte["results"] if not r["passed"]]
        self.assertEqual(fallidos, [])
        self.assertTrue(reporte["gate_passed"])
        self.assertEqual(reporte["reglas_sin_caso"], [])
        self.assertGreaterEqual(reporte["casos_limpios"], 1)
        for regla, datos in reporte["recall_por_regla"].items():
            with self.subTest(regla=regla):
                self.assertEqual(datos["recall"], 1.0)

    def test_falso_negativo_hace_fallar_el_gate(self) -> None:
        data = json.loads(GOLD_SET.read_text(encoding="utf-8"))
        limpio = next(c for c in data["cases"] if c["id"] == "limpio_base")
        limpio["reglas_prohibidas"].remove("PL-002")
        limpio["reglas_esperadas"] = ["PL-002"]
        with tempfile.TemporaryDirectory() as temp:
            ruta = Path(temp) / "gold.json"
            ruta.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            reporte = evaluar_gold_set(ruta)
        self.assertFalse(reporte["gate_passed"])
        self.assertIn({"caso": "limpio_base", "reglas": ["PL-002"]}, reporte["falsos_negativos"])

    def test_dataset_invalido(self) -> None:
        with self.assertRaises(PlanGoldSetInvalido):
            validar_dataset({"schema_version": "plan-gold-set/1.0", "status": "seed_synthetic",
                             "cases": [{"id": "x", "descripcion": "d", "ledger": {},
                                        "documento": None, "reglas_esperadas": ["PL-999"],
                                        "reglas_prohibidas": [], "bloqueado_esperado": False}]})


if __name__ == "__main__":
    unittest.main()
