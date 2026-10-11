"""Gates de los protocolos de materia (itosturre/protocolos): offline, sin corpus ni red.

El auditor del corpus se sustituye por uno falso: aquí se prueba qué hace cada gate con
lo que el auditor reporta, no el auditor (que tiene su propia suite). Los textos y la
ficha procesal son ficticios: no son citas para usar ni copian el sistema de destino.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from itosturre.protocolos import contrato as c
from itosturre.protocolos import citas, lint as l
from itosturre.protocolos.gates import correr_gates, huella

REPO = Path(__file__).resolve().parent.parent
S = c.SECCIONES

BASE = {
    "clave": "penal_materia",
    "version": "v1",
    "nombre": "Protocolo de materia: Penal (ficticio de prueba)",
    "materia": "penal",
    "palabras": ["delito", "denuncia penal", "carpeta de investigacion"],
    "datosIndispensables": ["Fecha de los hechos, porque de ella depende la prescripción."],
    "objecionesTipicas": ["Que la conducta descrita no encuadre exactamente en el tipo."],
    "instrucciones": [
        S[0] + " Tu análisis respeta esta cadena: la norma constitucional ficticia → la ley ficticia.",
        S[1] + " Señala cuándo un argumento pasa por alto la exacta aplicación de la ley.",
        S[2] + " Prioriza la subsunción estricta del tipo.",
        S[3] + " Además del Semanario, prefiere la fuente ficticia oficial; si no puedes verificar, "
               "márcalo [VERIFICAR EN: fuente ficticia].",
        S[4] + " Antes de avanzar, verifica que no haya prescrito la acción.",
    ],
    "_notaVersion": "ficticio de prueba",
}

FICHA = {
    "codigo": "Código Ficticio de Procedimientos de Prueba Uniforme",
    "etapas": "etapa inicial ficticia de investigación; etapa intermedia ficticia; etapa ficticia de juicio oral",
    "principios": "contradicción ficticia, inmediación ficticia, continuidad ficticia y oralidad ficticia",
    "estandar": "la parte acusadora debe aportar datos ficticios suficientes que establezcan el hecho atribuido",
}


def protocolo(**cambios) -> dict:
    p = copy.deepcopy(BASE)
    p.update(cambios)
    return p


def con_instruccion(i: int, extra: str) -> dict:
    p = protocolo()
    p["instrucciones"][i] = p["instrucciones"][i] + " " + extra
    return p


def codigos(hallazgos, severidad=c.ERROR) -> list[str]:
    return [h.codigo for h in hallazgos if h.severidad == severidad]


class AuditorFalso:
    """Devuelve lo que se le indica y guarda el texto que recibió."""

    def __init__(self, alerts=(), avisos=(), status="ok", ok=3, total=3, refutada=0, no_verificable=0):
        self.textos: list[str] = []
        self.informe = {
            "status": status, "alerts": list(alerts), "avisos": list(avisos),
            "vvca_summary": {"articulos_ok": ok, "articulos_total": total,
                             "normativa_refutada": refutada, "normativa_no_verificable": no_verificable},
        }

    def __call__(self, texto: str) -> dict:
        self.textos.append(texto)
        return self.informe


# ── G1: contrato ───────────────────────────────────────────────────────────────


class TestG1Contrato(unittest.TestCase):
    def test_protocolo_valido_no_tiene_errores(self):
        self.assertEqual(codigos(c.validar_esquema(protocolo())), [])

    def test_no_objeto(self):
        self.assertEqual(codigos(c.validar_esquema(["no"])), ["NO_ES_OBJETO"])

    def test_campo_obligatorio_vacio(self):
        self.assertIn("CAMPO_VACIO", codigos(c.validar_esquema(protocolo(version=" "))))
        self.assertIn("LISTA_VACIA", codigos(c.validar_esquema(protocolo(objecionesTipicas=[]))))

    def test_campo_con_error_de_dedo_se_rechaza(self):
        p = protocolo()
        p["datosIndispensable"] = p.pop("datosIndispensables")
        self.assertIn("CAMPO_DESCONOCIDO", codigos(c.validar_esquema(p)))

    def test_mayusculas_solo_avisan_porque_el_cargador_no_las_distingue(self):
        p = protocolo()
        p["Palabras"] = p.pop("palabras")
        hallazgos = c.validar_esquema(p)
        self.assertEqual(codigos(hallazgos), [])
        self.assertIn("MAYUSCULAS", codigos(hallazgos, c.AVISO))

    def test_materia_del_catalogo_y_clave_derivada(self):
        self.assertIn("MATERIA_FUERA_DE_CATALOGO", codigos(c.validar_esquema(protocolo(materia="agrario"))))
        self.assertIn("CLAVE", codigos(c.validar_esquema(protocolo(clave="penal_general"))))
        self.assertEqual(c.clave_esperada("seguridad_social"), "seguridad_social_materia")

    def test_version(self):
        self.assertIn("VERSION", codigos(c.validar_esquema(protocolo(version="1.0"))))
        self.assertEqual(codigos(c.validar_esquema(protocolo(version="v1.1"))), [])

    def test_palabras_de_activacion(self):
        self.assertIn("ACTIVACION", codigos(c.validar_esquema(protocolo(palabras=["Delito", "delito"]))))
        self.assertIn("PALABRA_CORTA", codigos(c.validar_esquema(protocolo(palabras=["delito", "mp"]))))

    def test_cinco_secciones_en_orden_con_rotulo(self):
        p = protocolo()
        p["instrucciones"] = p["instrucciones"][:4]
        self.assertIn("SECCIONES", codigos(c.validar_esquema(p)))
        p = protocolo()
        p["instrucciones"][1], p["instrucciones"][2] = p["instrucciones"][2], p["instrucciones"][1]
        self.assertEqual(codigos(c.validar_esquema(p)).count("ROTULO"), 2)

    def test_seccion_larga_se_rechaza(self):
        p = con_instruccion(0, "palabra " * (c.MAX_PALABRAS_SECCION + 1))
        self.assertIn("SECCION_LARGA", codigos(c.validar_esquema(p)))


# ── G2: complemento, no sustituto ──────────────────────────────────────────────


class TestG2Lint(unittest.TestCase):
    def test_protocolo_valido_pasa_con_ficha(self):
        self.assertEqual(codigos(l.lint(protocolo(), FICHA)), [])

    def test_r1_rol(self):
        for texto in ("Eres el Juez que conduce la audiencia.", "Actúa como fiscal experto.",
                      "Tu rol es asesorar al imputado."):
            with self.subTest(texto=texto):
                self.assertIn("R1_ROL", codigos(l.lint(con_instruccion(1, texto), FICHA)))

    def test_r1_no_marca_eres_a_media_oracion(self):
        p = con_instruccion(1, "Distingue lo que la persona dice que eres de lo que acredita.")
        self.assertNotIn("R1_ROL", codigos(l.lint(p, FICHA)))

    def test_r2_formato_de_salida(self):
        for texto in ("Llena siempre faseActual.", 'Devuelve {"mensaje": "..."}.',
                      "Responde en JSON con tu evaluación."):
            with self.subTest(texto=texto):
                self.assertIn("R2_FORMATO_SALIDA", codigos(l.lint(con_instruccion(2, texto), FICHA)))

    def test_r2_no_marca_la_palabra_mensaje_en_prosa(self):
        p = con_instruccion(2, "Si el mensaje del usuario omite la fecha, pídela.")
        self.assertNotIn("R2_FORMATO_SALIDA", codigos(l.lint(p, FICHA)))

    def test_r3_antialucinacion_generica(self):
        for texto in ("No inventes artículos.", "Nunca inventar registros.", "Jamás alucines datos."):
            with self.subTest(texto=texto):
                self.assertIn("R3_ANTIALUCINACION_GENERICA", codigos(l.lint(con_instruccion(3, texto), FICHA)))

    def test_r3_admite_donde_verificar(self):
        self.assertEqual(codigos(l.lint(protocolo(), FICHA)), [])  # trae [VERIFICAR EN: …]

    def test_r4_repetir_la_ficha_reprueba(self):
        p = con_instruccion(4, "Recuerda que la parte acusadora debe aportar datos ficticios suficientes "
                               "que establezcan el hecho atribuido.")
        self.assertIn("R4_FICHA_ESTANDAR", codigos(l.lint(p, FICHA)))
        p = con_instruccion(0, "Etapa inicial ficticia de investigación, etapa intermedia ficticia y "
                               "etapa ficticia de juicio oral.")
        self.assertIn("R4_FICHA_ETAPAS", codigos(l.lint(p, FICHA)))

    def test_r4_nombrar_el_codigo_solo_avisa(self):
        p = con_instruccion(0, "En la cadena va el Código Ficticio de Procedimientos de Prueba Uniforme.")
        hallazgos = l.lint(p, FICHA)
        self.assertNotIn("R4_FICHA_CODIGO", codigos(hallazgos))
        self.assertIn("R4_FICHA_CODIGO", codigos(hallazgos, c.AVISO))

    def test_r4_rozar_los_principios_solo_avisa(self):
        p = con_instruccion(1, "Rigen la contradicción ficticia, la inmediación ficticia, la continuidad "
                               "ficticia y la oralidad ficticia.")
        hallazgos = l.lint(p, FICHA)
        self.assertNotIn("R4_FICHA_PRINCIPIOS", codigos(hallazgos))
        self.assertIn("R4_FICHA_PRINCIPIOS", codigos(hallazgos, c.AVISO))

    def test_sin_ficha_avisa_que_r4_no_se_evaluo(self):
        self.assertIn("R4_SIN_FICHA", codigos(l.lint(protocolo()), c.AVISO))


# ── G3: normas contra el corpus ────────────────────────────────────────────────


class TestEnfoqueNacional(unittest.TestCase):
    """Criterio del operador (11-oct-2026): los protocolos son NACIONALES. No distinguen por el
    código de una entidad (habría que hacer uno por cada entidad): lo local se remite a «la
    entidad del asunto» con [VERIFICAR EN]."""

    def test_r5_nombrar_una_entidad_reprueba(self):
        for texto in ("Rige el Código Civil del Estado de Jalisco.",
                      "En el Estado de México el plazo es otro.",
                      "Si el asunto es de Nuevo León, revisa su código.",
                      "Consulta el Periódico Oficial «El Estado de Jalisco»."):
            with self.subTest(texto=texto):
                self.assertIn("R5_ENTIDAD_FEDERATIVA", codigos(l.lint(con_instruccion(1, texto), FICHA)))

    def test_r5_la_remision_generica_y_el_pais_no_reprueban(self):
        for texto in ("Aplica el código civil de la entidad del asunto [VERIFICAR EN: periódico oficial de la entidad].",
                      "Rige en todo México.", "La Constitución Política de los Estados Unidos Mexicanos."):
            with self.subTest(texto=texto):
                self.assertNotIn("R5_ENTIDAD_FEDERATIVA", codigos(l.lint(con_instruccion(1, texto), FICHA)))

    def test_r5_tambien_en_palabras_y_objeciones(self):
        p = protocolo(palabras=["codigo civil de jalisco", "otra palabra"])
        self.assertIn("R5_ENTIDAD_FEDERATIVA", codigos(l.lint(p, FICHA)))

    def test_fuentes_locales(self):
        locales = ("Codigo-Civil-del-Estado-de-Jalisco_3.pdf", "CodigoProcedimientosCivilesEstadoJalisco.pdf",
                   "LeydeJusticiaAdministrativadelEstadodeJalisco 2026.pdf",
                   "Código Penal para el Estado Libre y Soberano de Jalisco.pdf",
                   "RegMovilidadTransporteSeguridadVialGuadalajara 2026.pdf",
                   "CODIGO CIVIL PARA EL DISTRITO FEDERAL.pdf")
        nacionales = ("CODIGO CIVIL FEDERAL 2026.pdf", "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
                      "Código Nacional de Procedimientos Civiles y Familiares 2026.pdf", "LEY DEL SEGURO SOCIAL.pdf",
                      "Convención sobre los Derechos del Niño.pdf")
        for fuente in locales:
            with self.subTest(fuente=fuente):
                self.assertTrue(c.es_fuente_local(fuente))
        for fuente in nacionales:
            with self.subTest(fuente=fuente):
                self.assertFalse(c.es_fuente_local(fuente))

    def test_g3_cita_de_una_ley_local_reprueba(self):
        a = AuditorFalso()
        a.informe["retrieved_sources"] = [
            {"ref_type": "normativa", "source_file": "Codigo-Civil-del-Estado-de-Jalisco_3.pdf", "article": "1266"},
            {"ref_type": "normativa", "source_file": "CODIGO CIVIL FEDERAL 2026.pdf", "article": "1796"},
        ]
        h, _ = citas.auditar_normas(protocolo(), a, no_verdes={})
        self.assertEqual(codigos(h), ["LEY_LOCAL"])
        self.assertIn("1266", h[0].mensaje)
        self.assertIn("entidad del asunto", h[0].mensaje)


class TestG3Normas(unittest.TestCase):
    def test_todo_verificado_pasa_y_el_auditor_recibe_todos_los_textos(self):
        auditor = AuditorFalso()
        hallazgos, informe = citas.auditar_normas(protocolo(), auditor)
        self.assertEqual(codigos(hallazgos), [])
        self.assertIn("Fecha de los hechos", auditor.textos[0])
        self.assertIn("encuadre exactamente", auditor.textos[0])
        self.assertIs(informe, auditor.informe)

    def test_notacion_no_auditable(self):
        p = con_instruccion(0, "Conforme al artículo 31-IV de la Constitución.")
        self.assertIn("NOTACION_NO_AUDITABLE", codigos(citas.auditar_normas(p, AuditorFalso())[0]))

    def test_articulos_con_letra_no_son_fracciones(self):
        p = con_instruccion(0, "Artículos 17-H, 17-I y 69-B del código fiscal ficticio.")
        self.assertNotIn("NOTACION_NO_AUDITABLE", codigos(citas.auditar_normas(p, AuditorFalso())[0]))

    def test_cada_alerta_reprueba_con_su_camino(self):
        casos = {
            "🔴 ARTÍCULO INEXISTENTE ACREDITADO: 'artículo 999' — el cuerpo del corpus termina en el 429": "REFUTADA",
            "🟡 VERSIÓN INDEXADA NO VIGENTE según el reporte de vigencia": "VIGENCIA",
            "🟡 COBERTURA INCOMPLETA: 'art. 31' — la unidad citada continúa": "COBERTURA_INCOMPLETA",
            "🟡 NO VERIFICABLE: ley no indexada en el corpus": "NO_VERIFICABLE",
        }
        for alerta, esperado in casos.items():
            with self.subTest(esperado=esperado):
                hallazgos, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[alerta], ok=2))
                self.assertIn(esperado, codigos(hallazgos))

    def test_ley_ambigua_por_redaccion_no_es_hueco_de_corpus(self):
        """Una cita que el extractor liga a dos leyes se arregla reescribiéndola; una ley fuera
        del corpus sí es la Regla 7. Las dos alertas empiezan igual ("LEY NO IDENTIFICADA")."""
        ambiguas = (
            "🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'artículos 128' (artículo 128) — vínculos en "
            "conflicto: a la izquierda 'ordenamiento fuera del catálogo: 'norma general'' y a la derecha "
            "'ley ficticia'.",
            "🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'artículos 19' (artículo 19) — el contexto previo "
            "es ambiguo: la oración anterior nombra varios ordenamientos.",
        )
        for alerta in ambiguas:
            with self.subTest(alerta=alerta[:60]):
                h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[alerta], ok=2))
                self.assertEqual(codigos(h), ["LEY_AMBIGUA"])
                self.assertNotIn("Regla 7", h[0].mensaje)
        sin_ley = ("🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'artículo 123' (artículo 123) — el texto no liga el "
                   "artículo a un ordenamiento (ni a su derecha ni a su izquierda) ni lo nombra en las oraciones previas.")
        h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[sin_ley], ok=2))
        self.assertEqual(codigos(h), ["CITA_SIN_LEY"])
        self.assertNotIn("Regla 7", h[0].mensaje)
        fuera = ("🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'artículo 19' (artículo 19) — ordenamiento "
                 "fuera del catálogo: 'Ley Ficticia de Prueba' (no es una ley del corpus).")
        h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[fuera], ok=2))
        self.assertEqual(codigos(h), ["NO_VERIFICABLE"])
        self.assertIn("Regla 7", h[0].mensaje)

    def test_sigla_fuera_del_catalogo_es_redaccion_no_hueco_de_corpus(self):
        """Texto literal del auditor (fix/auditor-sigla-desconocida, 5e5fe41). Menciona «ley no
        indexada» y «corpus», pero se arregla escribiendo la denominación de la ley: si fuera
        NO_VERIFICABLE, el bucle pararía en un falso hueco de corpus."""
        sigla = ("🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'artículo 248' (artículo 248) — sigla fuera del "
                 "catálogo: 'LISSSTE' (no es una abreviatura reconocida ni se define en el texto: puede ser "
                 "una ley no indexada o la sigla de una ley del corpus; escriba su denominación). NO es "
                 "alucinación: sin el ordenamiento no se puede cotejar el precepto. Precisar la ley junto al "
                 "artículo o verificar en fuente oficial antes de citar.")
        h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[sigla], ok=2))
        self.assertEqual(codigos(h), ["SIGLA_DESCONOCIDA"])
        self.assertIn("denominación", h[0].mensaje)
        self.assertNotIn("Regla 7", h[0].mensaje)

    def test_tesis_del_corpus_sin_rubro_transcrito_es_aviso(self):
        """Promovida la tesis, el auditor la halla en el corpus local pero no coteja el rubro: el
        protocolo la cita por clave y registro, como pide la plantilla. Es aviso, no error, porque
        G4 coteja la clave contra la captura del SJF y la fidelidad la revisan A3 y A5. Los demás
        problemas de rubro siguen siendo error."""
        sin_rubro = ("🟡 SIN RUBRO INVOCADO: Registro digital 2099001 — El escrito no transcribe un rubro "
                     "identificable para esta tesis: no hubo cotejo del rubro; la tesis solo acredita la "
                     "existencia del registro. Rubro real: «RUBRO FICTICIO.». Cotejar que el criterio "
                     "respalde lo afirmado antes de citar.")
        h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[sin_rubro]))
        self.assertEqual(codigos(h), [])
        self.assertEqual(codigos(h, c.AVISO), ["TESIS_SIN_RUBRO_TRANSCRITO"])
        for alerta in ("🟡 RUBRO PARCIAL: Registro digital 2099001 — truncado. Rubro invocado: «RUBRO». "
                       "Rubro real: «RUBRO FICTICIO.».",
                       "🔴 RUBRO DISCREPANTE: Registro digital 2099001 existe en el corpus local, pero su "
                       "rubro no coincide."):
            with self.subTest(alerta=alerta[:30]):
                h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[alerta]))
                self.assertTrue(codigos(h))

    def test_regla_7_y_8_indican_el_camino(self):
        h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=["🟡 ley no indexada"], ok=2))
        self.assertTrue(any("Regla 7" in x.mensaje for x in h))
        h, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=["🟡 versión no vigente"], ok=2))
        self.assertTrue(any("cotejo_manual" in x.mensaje for x in h))

    def test_tesis_fuera_del_corpus_local_indica_promoverla_no_el_dof(self):
        """Regla 3: la cita de una tesis se verifica contra el corpus local; la captura del SJF
        solo es el insumo para promoverla (scripts/promover_tesis.py), y eso lo decide el abogado."""
        alerta = ("🟡 NO VERIFICABLE: Registro digital 2099001 no encontrado en el corpus de jurisprudencia "
                  "local (no confirmado como falso). Verificar en sjf2.scjn.gob.mx antes de citar.")
        hallazgos, _ = citas.auditar_normas(protocolo(), AuditorFalso(alerts=[alerta]))
        self.assertIn("TESIS_FUERA_DEL_CORPUS", codigos(hallazgos))
        mensaje = next(h.mensaje for h in hallazgos if h.codigo == "TESIS_FUERA_DEL_CORPUS")
        self.assertIn("promover_tesis.py", mensaje)
        self.assertIn("[VERIFICAR EN SJF]", mensaje)
        self.assertNotIn("DOF", mensaje)

    def test_aviso_de_corpus_parcial_tambien_reprueba(self):
        auditor = AuditorFalso(avisos=["auditoría ejecutada con corpus parcial: falta una ley"])
        hallazgos, _ = citas.auditar_normas(protocolo(), auditor)
        self.assertIn("NO_VERIFICABLE", codigos(hallazgos))

    def test_auditoria_no_utilizable(self):
        hallazgos, _ = citas.auditar_normas(protocolo(), AuditorFalso(status="corpus_incomplete"))
        self.assertIn("AUDITORIA_NO_UTILIZABLE", codigos(hallazgos))

    def test_verificados_incompletos_sin_alerta_reprueban(self):
        hallazgos, _ = citas.auditar_normas(protocolo(), AuditorFalso(ok=2, total=3))
        self.assertIn("CITAS_SIN_VERIFICAR", codigos(hallazgos))

    def test_refutada_en_el_resumen_reprueba_aunque_no_haya_alerta(self):
        hallazgos, _ = citas.auditar_normas(protocolo(), AuditorFalso(refutada=1))
        self.assertIn("NORMATIVA_REFUTADA", codigos(hallazgos))

    def test_sin_citas_solo_avisa(self):
        hallazgos, _ = citas.auditar_normas(protocolo(), AuditorFalso(ok=0, total=0))
        self.assertEqual(codigos(hallazgos), [])
        self.assertIn("SIN_CITAS_NORMATIVAS", codigos(hallazgos, c.AVISO))


# ── G4: jurisprudencia con evidencia ───────────────────────────────────────────

class TestG3Regla8(unittest.TestCase):
    """Regla 8: el auditor da 🟢 a un artículo que existe en la versión indexada aunque la ley esté
    en 🟡 en el reporte de vigencia. G3 exige entonces el cotejo de cada artículo contra el PDF
    oficial (civil, 11-oct-2026: el CPCJ se cotejó a mano porque el gate no lo pedía)."""

    FUENTES = [
        {"ref_type": "normativa", "source_file": "LEY AMARILLA.pdf", "article": "4"},
        {"ref_type": "normativa", "source_file": "LEY AMARILLA.pdf", "article": "9"},
        {"ref_type": "normativa", "source_file": "LEY VERDE.pdf", "article": "1"},
    ]
    NO_VERDES = {"LEY AMARILLA.pdf": "Ley Amarilla"}

    def auditor(self):
        a = AuditorFalso()
        a.informe["retrieved_sources"] = self.FUENTES
        return a

    def test_ley_en_amarillo_exige_cotejo_de_cada_articulo(self):
        pedidos = []

        def cotejador(ley, articulos):
            pedidos.append((ley, sorted(articulos)))
            return {"4": "🟢 COINCIDE: el texto del RAG es igual al oficial vigente",
                    "9": "🔴 DIFIERE: el texto del RAG no es el oficial vigente"}

        h, _ = citas.auditar_normas(protocolo(), self.auditor(), no_verdes=self.NO_VERDES,
                                    cotejador=cotejador)
        self.assertEqual(pedidos, [("Ley Amarilla", ["4", "9"])])
        self.assertEqual(codigos(h), ["COTEJO_DIFIERE"])

    def test_cotejo_sin_resultado_verde_queda_pendiente(self):
        def cotejador(ley, articulos):
            return {"4": "🟡 NO LOCALIZADO en ninguno de los dos textos"}

        h, _ = citas.auditar_normas(protocolo(), self.auditor(), no_verdes=self.NO_VERDES,
                                    cotejador=cotejador)
        self.assertEqual(codigos(h), ["COTEJO_PENDIENTE", "COTEJO_PENDIENTE"])
        self.assertIn("Regla 8", h[0].mensaje)

    def test_sin_leyes_en_amarillo_no_se_coteja(self):
        def cotejador(ley, articulos):
            raise AssertionError("no debía cotejar")

        h, _ = citas.auditar_normas(protocolo(), self.auditor(), no_verdes={}, cotejador=cotejador)
        self.assertEqual(codigos(h), [])

    def test_lee_la_salida_de_cotejo_manual(self):
        salida = ("## Cotejo · Ley Amarilla · artículo 4\n\n"
                  "- **Resultado (Capa 1):** 🟢 COINCIDE: el texto del RAG es igual al oficial vigente\n"
                  "- RAG: `LEY AMARILLA.pdf`\n\n"
                  "## Cotejo · Ley Amarilla · artículo 29 bis\n\n"
                  "- **Resultado (Capa 1):** 🟡 NO LOCALIZADO en ninguno de los dos textos\n")
        self.assertEqual(citas.resultados_cotejo(salida), {
            "4": "🟢 COINCIDE: el texto del RAG es igual al oficial vigente",
            "29 bis": "🟡 NO LOCALIZADO en ninguno de los dos textos",
        })


TESIS_OK = {"registro": "2099001", "rubro": "RUBRO FICTICIO.", "tipo": "Jurisprudencia",
            "estado_consulta": "VERIFICADO", "estado_vigencia": "vigente"}


class TestG4Jurisprudencia(unittest.TestCase):
    def test_sin_tesis_citadas_no_hay_nada_que_verificar(self):
        self.assertEqual(citas.verificar_jurisprudencia(protocolo(), None), [])

    def test_tesis_sin_evidencia_reprueba(self):
        p = con_instruccion(0, "Véase la jurisprudencia con registro digital 2099001.")
        self.assertIn("TESIS_SIN_EVIDENCIA", codigos(citas.verificar_jurisprudencia(p, None)))

    def test_tesis_con_evidencia_verificada_pasa(self):
        p = con_instruccion(0, "Véase la jurisprudencia con registro digital: 2099001.")
        self.assertEqual(codigos(citas.verificar_jurisprudencia(p, {"tesis": [TESIS_OK]})), [])

    def test_evidencia_no_verificada_o_no_vigente_reprueba(self):
        p = con_instruccion(0, "Registro 2099001.")
        for cambio, esperado in (({"estado_consulta": "NO_VERIFICABLE"}, "TESIS_NO_VERIFICADA"),
                                 ({"estado_vigencia": "superada"}, "TESIS_NO_VIGENTE"),
                                 ({"rubro": ""}, "TESIS_SIN_RUBRO")):
            with self.subTest(esperado=esperado):
                tesis = {**TESIS_OK, **cambio}
                self.assertIn(esperado, codigos(citas.verificar_jurisprudencia(p, {"tesis": [tesis]})))

    def test_clave_citada_debe_coincidir_con_la_captura(self):
        """Sin cotejo de rubro, lo que ata la cita a la tesis es la pareja clave–registro: la clave
        citada junto al registro debe ser la que trae la captura del SJF para ese registro."""
        tesis = {**TESIS_OK, "numero_tesis": "1a./J. 12/2099 (11a.)"}
        ok = con_instruccion(0, "Conforme a la 1a./J. 12/2099 (11a.), registro digital 2099001.")
        self.assertEqual(codigos(citas.verificar_jurisprudencia(ok, {"tesis": [tesis]})), [])
        mal = con_instruccion(0, "Conforme a la 1a./J. 13/2099 (11a.), registro digital 2099001.")
        self.assertIn("TESIS_CLAVE_DISCREPANTE", codigos(citas.verificar_jurisprudencia(mal, {"tesis": [tesis]})))

    def test_clave_de_tesis_sin_registro_reprueba(self):
        p = con_instruccion(0, "Conforme a la tesis 1a./J. 12/2099 (ficticia).")
        self.assertIn("TESIS_SIN_REGISTRO", codigos(citas.verificar_jurisprudencia(p, None)))


# ── Reporte y CLI ──────────────────────────────────────────────────────────────


class TestReporte(unittest.TestCase):
    def test_g1_reprobado_no_corre_los_demas_ni_llama_al_auditor(self):
        auditor = AuditorFalso()
        reporte = correr_gates(protocolo(materia="agrario"), ficha=FICHA, auditor=auditor)
        self.assertFalse(reporte.ok)
        self.assertEqual(reporte.to_dict()["gates"], {"G1": "ERROR", "G2": "NO_CORRIDO",
                                                      "G3": "NO_CORRIDO", "G4": "NO_CORRIDO"})
        self.assertEqual(auditor.textos, [])

    def test_protocolo_valido_pasa_los_cuatro_gates(self):
        reporte = correr_gates(protocolo(), ficha=FICHA, auditor=AuditorFalso())
        self.assertTrue(reporte.ok)
        self.assertEqual(set(reporte.to_dict()["gates"].values()), {"OK"})

    def test_sin_rag_g3_queda_sin_correr(self):
        reporte = correr_gates(protocolo(), ficha=FICHA, con_rag=False)
        self.assertEqual(reporte.estado_gate("G3"), "NO_CORRIDO")

    def test_huella_canonica_estable(self):
        p = protocolo()
        invertido = dict(reversed(list(p.items())))
        self.assertEqual(huella(p), huella(invertido))
        self.assertNotEqual(huella(p), huella(protocolo(version="v2")))


class TestCli(unittest.TestCase):
    def _correr(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(REPO / "scripts" / "protocolo_gates.py"), *args],
                              capture_output=True, text=True, cwd=REPO)

    def test_sin_rag_queda_incompleto_con_salida_3_y_reporte(self):
        with TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "penal_materia.json"
            ruta.write_text(json.dumps(protocolo(), ensure_ascii=False), encoding="utf-8")
            fichas = Path(tmp) / "fichas.json"
            fichas.write_text(json.dumps({"penal": FICHA}, ensure_ascii=False), encoding="utf-8")
            salida = Path(tmp) / "gates.json"
            res = self._correr(str(ruta), "--ficha", str(fichas), "--sin-rag", "--salida", str(salida))
            self.assertEqual(res.returncode, 3, res.stderr)
            reporte = json.loads(salida.read_text(encoding="utf-8"))
            self.assertEqual(reporte["gates"]["G3"], "NO_CORRIDO")
            self.assertEqual(reporte["sha256"], huella(protocolo()))

    def test_error_sale_con_1_y_toma_la_evidencia_hermana(self):
        with TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "penal_materia.json"
            ruta.write_text(json.dumps(con_instruccion(0, "Registro digital 2099001."), ensure_ascii=False),
                            encoding="utf-8")
            res = self._correr(str(ruta), "--sin-rag")
            self.assertEqual(res.returncode, 1)
            self.assertIn("TESIS_SIN_EVIDENCIA", res.stdout)
            (Path(tmp) / "penal_materia.evidencia.json").write_text(
                json.dumps({"tesis": [TESIS_OK]}), encoding="utf-8")
            self.assertEqual(self._correr(str(ruta), "--sin-rag").returncode, 3)

    def test_archivo_ilegible_sale_con_2(self):
        self.assertEqual(self._correr("/no/existe/nunca.json", "--sin-rag").returncode, 2)


if __name__ == "__main__":
    unittest.main()
