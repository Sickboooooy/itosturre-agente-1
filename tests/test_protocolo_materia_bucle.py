"""Bucle determinista de los protocolos de materia (scripts/protocolo_materia.py): offline.

El auditor del corpus se sustituye por uno falso; el reporte de vigencia, la ficha procesal y
las capturas del SJF son ficticios. Todo se escribe en carpetas temporales fuera del repo.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from itosturre.protocolos import contrato as c

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("protocolo_materia", REPO / "scripts" / "protocolo_materia.py")
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

S = c.SECCIONES
FICHA = {"laboral": {
    "codigo": "Ley Ficticia de Procedimiento Uniforme de Prueba",
    "etapas": "etapa ficticia de conciliación; etapa ficticia de juicio; etapa ficticia de ejecución",
    "principios": "principio ficticio uno, principio ficticio dos y principio ficticio tres",
    "estandar": "la parte actora debe acreditar los hechos ficticios de su pretensión",
}}
VIGENCIA = {"filas": [
    {"fuente": "LEY FICTICIA DE PRUEBA.pdf", "etiqueta": "LFP", "nombre_oficial": "Ley Ficticia de Prueba",
     "semaforo": "🟢", "estado": "VIGENTE", "version_indexada": "Última Reforma DOF 01-01-2026"},
    {"fuente": "CODIGO FICTICIO.pdf", "etiqueta": "CF", "nombre_oficial": "Código Ficticio",
     "semaforo": "🔴", "estado": "NO_VIGENTE", "version_indexada": "Última Reforma DOF 01-01-2020"},
    {"fuente": "Codigo Ficticio del Estado de Jalisco.pdf", "etiqueta": "Código Ficticio de Jalisco",
     "nombre_oficial": "Código Ficticio de Jalisco", "semaforo": "🟢", "estado": "VIGENTE",
     "version_indexada": "Tabla de reformas: 01-01-2026"},
]}


class AuditorFalso:
    """Reprueba los fixtures como el auditor real (o no, para probar un gate roto) y deja pasar
    lo demás, salvo las alertas fijas que se le indiquen."""

    def __init__(self, reprueba: bool = True, alertas: tuple = ()):
        self.reprueba = reprueba
        self.alertas = list(alertas)

    def __call__(self, texto: str) -> dict:
        alerts = list(self.alertas)
        if self.reprueba and "artículo 9999" in texto:
            alerts.append("🔴 ARTÍCULO INEXISTENTE ACREDITADO: 'artículo 9999' — el cuerpo termina en el 300")
        if self.reprueba and "artículo 19 de la" in texto:
            alerts.append("🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'artículo 19' — ordenamiento fuera del "
                          "catálogo: 'Ley Ficticia Ajena' (no es una ley del corpus).")
        return {"status": "ok", "alerts": alerts, "avisos": [],
                "vvca_summary": {"articulos_ok": 1, "articulos_total": 1 + len(alerts),
                                 "normativa_refutada": 0, "normativa_no_verificable": 0}}


AMBIGUA = ("🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: 'artículos 12' (artículo 12) — vínculos en conflicto: "
           "a la izquierda 'norma general' y a la derecha 'ley ficticia de prueba'.")
FUERA_DEL_CORPUS = ("🟡 NO VERIFICABLE: Registro digital 2000001 no encontrado en el corpus de jurisprudencia "
                    "local (no confirmado como falso).")


def borrador(**cambios) -> dict:
    p = {"clave": "laboral_materia", "version": "v1", "nombre": "Protocolo ficticio de prueba",
         "materia": "laboral", "palabras": ["despido ficticio", "patron ficticio"],
         "datosIndispensables": ["Dato ficticio de prueba."], "objecionesTipicas": ["Objeción ficticia de prueba."],
         "instrucciones": [S[0] + " Rige el artículo 1 de la Ley Ficticia de Prueba."]
                          + [s + " Texto ficticio de prueba." for s in S[1:]]}
    p.update(cambios)
    return p


class Base(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        self.fichas = self.base / "fichas_simulador.json"
        self.fichas.write_text(json.dumps(FICHA, ensure_ascii=False), encoding="utf-8")
        self.vigencia = self.base / "vigencia_2026-01-01.json"
        self.vigencia.write_text(json.dumps(VIGENCIA, ensure_ascii=False), encoding="utf-8")

    def preparar(self, leyes=("Ley Ficticia de Prueba",), auditor=None, con_rag=True, ley_principal="de la Ley Ficticia de Prueba"):
        return pm.preparar("laboral", self.base, leyes=list(leyes), ley_principal=ley_principal,
                           fichas=self.fichas, plantilla=self.base / "plantilla.docx", con_rag=con_rag,
                           auditor=auditor or AuditorFalso(), reporte_vigencia=self.vigencia)

    def carpeta(self) -> "pm.Carpeta":
        return pm.Carpeta(self.base / "laboral_materia")


class TestPreparar(Base):
    def test_crea_la_carpeta_y_la_precondicion_pasa(self):
        codigo, estado = self.preparar()
        self.assertEqual(codigo, 0, estado["precondicion"]["problemas"])
        ruta = self.base / "laboral_materia"
        for sub in ("investigacion", "evidencia_sjf", "fixtures", "prompts"):
            self.assertTrue((ruta / sub).is_dir())
        self.assertEqual(self.carpeta().config["clave"], "laboral_materia")
        self.assertEqual(estado["etapa"], "investigación (A1, A2)")
        self.assertTrue(all(r["ok"] for r in estado["precondicion"]["fixtures"].values()))
        self.assertEqual([x["condicion"] for x in estado["precondicion"]["corpus"]], ["OK"])

    def test_ley_roja_o_fuera_del_indice_bloquea(self):
        codigo, estado = self.preparar(leyes=("Código Ficticio", "Ley que no existe"))
        self.assertEqual(codigo, 1)
        problemas = " ".join(estado["precondicion"]["problemas"])
        self.assertIn("Código Ficticio", problemas)
        self.assertIn("NO_INDEXADA", problemas)

    def test_una_ley_local_bloquea_por_el_enfoque_nacional(self):
        codigo, estado = self.preparar(leyes=("Ley Ficticia de Prueba", "Código Ficticio de Jalisco"))
        self.assertEqual(codigo, 1)
        self.assertIn("LEY_LOCAL", " ".join(estado["precondicion"]["problemas"]))

    def test_el_gate_de_enfoque_nacional_reprueba_su_fixture(self):
        _, estado = self.preparar()
        self.assertTrue(estado["precondicion"]["fixtures"]["rojo_entidad"]["ok"])

    def test_un_gate_que_no_reprueba_detiene_la_precondicion(self):
        codigo, estado = self.preparar(auditor=AuditorFalso(reprueba=False))
        self.assertEqual(codigo, 1)
        self.assertIs(estado["precondicion"]["fixtures"]["rojo_inexistente"]["ok"], False)
        self.assertEqual(estado["etapa"], "precondición no cumplida")

    def test_sin_rag_los_fixtures_de_g3_quedan_sin_correr(self):
        _, estado = self.preparar(con_rag=False)
        fixtures = estado["precondicion"]["fixtures"]
        self.assertIsNone(fixtures["rojo_inexistente"]["ok"])
        self.assertTrue(fixtures["rojo_rol"]["ok"])

    def test_sin_ley_principal_no_se_prepara(self):
        with self.assertRaises(SystemExit):
            self.preparar(ley_principal=None)

    def test_las_salidas_no_pueden_vivir_en_el_repo(self):
        with self.assertRaises(SystemExit):
            pm.base_de(pm.REPO / "protocolos_de_prueba")


class TestPrompts(Base):
    def setUp(self):
        super().setUp()
        self.preparar()
        config = self.carpeta().config
        config.update({"temas_a1": {"I": "jerarquía ficticia", "V": "plazos ficticios"},
                       "temas_a2": ["tema ficticio de jurisprudencia"]})
        pm.escribir_json(self.base / "laboral_materia" / "config.json", config)

    def test_a1_y_a2_quedan_sin_marcas_pendientes(self):
        rutas = pm.prompts(self.carpeta(), ["a1", "a2"])
        self.assertEqual([r.name for r in rutas], ["a1.md", "a2.md"])
        for ruta in rutas:
            texto = ruta.read_text(encoding="utf-8")
            self.assertNotIn("{{", texto)
            self.assertIn(str(self.base / "laboral_materia"), texto)
        a1 = rutas[0].read_text(encoding="utf-8")
        self.assertIn("«Ley Ficticia de Prueba»", a1)
        self.assertIn("etapa ficticia de conciliación", a1)   # la ficha va como "qué NO buscar"
        self.assertIn("Última Reforma DOF 01-01-2026", a1)     # versión indexada, del reporte

    def test_a5_exige_un_protocolo_escrito(self):
        with self.assertRaises(SystemExit):
            pm.prompts(self.carpeta(), ["a5"])
        pm.escribir(self.carpeta(), borrador())
        texto = pm.prompts(self.carpeta(), ["a5"])[0].read_text(encoding="utf-8")
        self.assertIn("laboral_materia.json", texto)

    def test_temas_vacios_se_rechazan(self):
        config = self.carpeta().config
        config["temas_a1"] = {}
        pm.escribir_json(self.base / "laboral_materia" / "config.json", config)
        with self.assertRaises(SystemExit):
            pm.prompts(self.carpeta(), ["a1"])

    def test_tolera_el_estado_de_una_corrida_anterior_al_script(self):
        estado = self.carpeta().estado()
        estado["precondicion"]["corpus"] = {"Ley Ficticia de Prueba": "🟢 (DOF 01-01-2026)"}
        pm.escribir_json(self.base / "laboral_materia" / "estado.json", estado)
        self.assertNotIn("Versiones indexadas", pm.prompts(self.carpeta(), ["a1"])[0].read_text(encoding="utf-8"))

    def test_la_descripcion_del_destino_viene_de_fuera_del_repo(self):
        (self.base / "destino.json").write_text(json.dumps({"descripcion": "un destino ficticio de prueba"}),
                                                encoding="utf-8")
        texto = pm.prompts(self.carpeta(), ["a1"])[0].read_text(encoding="utf-8")
        self.assertIn("un destino ficticio de prueba", texto)


class TestEscribirYGates(Base):
    def setUp(self):
        super().setUp()
        self.preparar()

    def test_escribir_rechaza_lo_que_no_pasa_g1(self):
        largo = borrador()
        largo["instrucciones"][4] += " palabra" * 300
        codigo, mensajes = pm.escribir(self.carpeta(), largo)
        self.assertEqual(codigo, 1)
        self.assertTrue(any("SECCION_LARGA" in m for m in mensajes))
        self.assertFalse(self.carpeta().protocolo.exists())

    def test_escribir_respalda_la_version_anterior(self):
        pm.escribir(self.carpeta(), borrador())
        pm.escribir(self.carpeta(), borrador(version="v1.1"))
        respaldo = json.loads((self.base / "laboral_materia" / "laboral_materia.iter0.json").read_text(encoding="utf-8"))
        self.assertEqual(respaldo["version"], "v1")

    def test_gates_en_verde_es_exito_y_queda_anotado(self):
        pm.escribir(self.carpeta(), borrador())
        datos, veredicto = pm.iteracion(self.carpeta(), auditor=AuditorFalso(), cambio="primer borrador")
        self.assertEqual(veredicto["estado"], pm.EXITO, datos["hallazgos"])
        self.assertTrue((self.base / "laboral_materia" / "gates_iter1.json").exists())
        historial = self.carpeta().historial()
        self.assertEqual(len(historial), 1)
        self.assertEqual(historial[0]["cambio"], "primer borrador")
        self.assertEqual(self.carpeta().estado()["iteracion"], 1)

    def test_el_mismo_fallo_dos_vueltas_seguidas_es_estancado(self):
        pm.escribir(self.carpeta(), borrador())
        auditor = AuditorFalso(alertas=(AMBIGUA,))
        _, primero = pm.iteracion(self.carpeta(), auditor=auditor)
        self.assertEqual(primero["estado"], pm.SEGUIR)
        self.assertEqual(primero["fallo"]["codigo"], "LEY_AMBIGUA")
        _, segundo = pm.iteracion(self.carpeta(), auditor=auditor)
        self.assertEqual((segundo["estado"], segundo["paro"]), (pm.PARO, "ESTANCADO"))

    def test_solo_tesis_fuera_del_corpus_es_hueco_de_corpus(self):
        p = borrador()
        p["instrucciones"][1] += " Lo sostiene la P./J. 1/2020 (10a.), registro digital 2000001."
        pm.escribir(self.carpeta(), p)
        pm.escribir_json(self.carpeta().evidencia, {"tesis": [{
            "registro": "2000001", "rubro": "RUBRO FICTICIO.", "estado_consulta": "VERIFICADO",
            "estado_vigencia": "vigente"}]})
        datos, veredicto = pm.iteracion(self.carpeta(), auditor=AuditorFalso(alertas=(FUERA_DEL_CORPUS,)))
        self.assertEqual(datos["gates"]["G4"], "OK")
        self.assertEqual((veredicto["estado"], veredicto["paro"]), (pm.PARO, "HUECO_DE_CORPUS"))


class TestDecidir(unittest.TestCase):
    @staticmethod
    def datos(*errores, gates=None) -> dict:
        return {"gates": gates or {g: "OK" for g in pm.GATES},
                "hallazgos": [{"gate": g, "severidad": c.ERROR, "codigo": k, "ruta": "", "mensaje": k} for g, k in errores]}

    def test_prioridad_g1_g2_g3_g4(self):
        veredicto = pm.decidir(self.datos(("G3", "REFUTADA"), ("G2", "R1_ROL")), 1)
        self.assertEqual(veredicto["fallo"]["gate"], "G2")

    def test_una_cita_ambigua_no_es_hueco_de_corpus(self):
        veredicto = pm.decidir(self.datos(("G3", "LEY_AMBIGUA"), ("G3", "TESIS_FUERA_DEL_CORPUS")), 1)
        self.assertEqual((veredicto["estado"], veredicto["fallo"]["codigo"]), (pm.SEGUIR, "LEY_AMBIGUA"))

    def test_tope_de_iteraciones(self):
        veredicto = pm.decidir(self.datos(("G3", "REFUTADA")), pm.MAX_ITERACIONES)
        self.assertEqual((veredicto["estado"], veredicto["paro"]), (pm.PARO, "TOPE"))

    def test_sin_errores_pero_sin_g3_no_es_exito(self):
        gates = {"G1": "OK", "G2": "OK", "G3": "NO_CORRIDO", "G4": "OK"}
        self.assertEqual(pm.decidir(self.datos(gates=gates), 1)["estado"], pm.SEGUIR)


class TestEvidenciaYCierre(Base):
    def setUp(self):
        super().setUp()
        self.preparar()
        verif = self.base / "laboral_materia" / "investigacion" / "a2" / "verif_1"
        verif.mkdir(parents=True)
        tesis = [{"registro": r, "rubro": f"RUBRO FICTICIO {r}.", "numero_tesis": f"P./J. {i}/2020 (10a.)",
                  "tipo_tesis": "Jurisprudencia", "sala": "Pleno", "epoca": "Décima Época", "fuente": "Ficticia",
                  "estado_consulta": estado, "estado_vigencia": "vigente"}
                 for i, (r, estado) in enumerate((("2000001", "VERIFICADO"), ("2000002", "VERIFICADO"),
                                                  ("2000003", "NO_VERIFICABLE")), start=1)]
        (verif / "auditoria_vvca.json").write_text(json.dumps(
            {"schema_version": "2.0", "politica_fuentes": {"api_interna": "NO_CONSUMIDA"}, "verificados": tesis,
             "propuestas": []}, ensure_ascii=False), encoding="utf-8")
        for t in tesis:
            (verif / f"sjf_{t['registro']}.png").write_bytes(b"png ficticio")

    def test_evidencia_solo_lleva_las_citadas_y_deja_candidatas(self):
        codigo, _ = pm.evidencia(self.carpeta(), ["2000001"])
        self.assertEqual(codigo, 0)
        ruta = self.base / "laboral_materia"
        auditoria = json.loads((ruta / "evidencia_sjf" / "auditoria_vvca.json").read_text(encoding="utf-8"))
        self.assertEqual([t["registro"] for t in auditoria["verificados"]], ["2000001"])
        self.assertEqual(auditoria["politica_fuentes"]["api_interna"], "NO_CONSUMIDA")
        self.assertTrue((ruta / "evidencia_sjf" / "sjf_2000001.png").exists())
        evidencia = json.loads(self.carpeta().evidencia.read_text(encoding="utf-8"))
        self.assertEqual([t["registro"] for t in evidencia["tesis"]], ["2000001"])
        self.assertEqual([t["registro"] for t in evidencia["tesis_candidatas_capa2"]], ["2000002"])
        self.assertEqual(evidencia["aprobacion"]["estado"], "PENDIENTE")

    def test_lo_que_a2_descarto_no_vuelve_como_candidata(self):
        a2 = self.base / "laboral_materia" / "investigacion" / "a2" / "a2_jurisprudencia.json"
        a2.write_text(json.dumps({"verificadas": [{"registro": "2000001", "tema": "tema ficticio"}],
                                  "descartadas": [{"registro": "2000002", "motivo": "aislada"}]}), encoding="utf-8")
        pm.evidencia(self.carpeta(), ["2000001"])
        evidencia = json.loads(self.carpeta().evidencia.read_text(encoding="utf-8"))
        self.assertEqual(evidencia["tesis_candidatas_capa2"], [])
        self.assertEqual(evidencia["tesis"][0]["tema"], "tema ficticio")

    def test_sin_captura_verificada_no_hay_cita(self):
        codigo, mensajes = pm.evidencia(self.carpeta(), ["2000003"])
        self.assertEqual(codigo, 1)
        self.assertIn("2000003", mensajes[0])

    def test_cerrar_exige_el_reporte_del_protocolo_actual_y_nunca_firma(self):
        pm.escribir(self.carpeta(), borrador())
        pm.iteracion(self.carpeta(), auditor=AuditorFalso())
        pm.escribir(self.carpeta(), borrador(nombre="Protocolo ficticio cambiado"))
        self.assertEqual(pm.cerrar(self.carpeta())[0], 1)
        pm.iteracion(self.carpeta(), auditor=AuditorFalso())
        self.assertEqual(pm.cerrar(self.carpeta())[0], 0)
        evidencia = json.loads(self.carpeta().evidencia.read_text(encoding="utf-8"))
        self.assertEqual(evidencia["gates"]["sha256_protocolo"],
                         json.loads((self.base / "laboral_materia" / "gates.json").read_text(encoding="utf-8"))["sha256"])
        self.assertEqual(evidencia["aprobacion"]["estado"], "PENDIENTE")
        self.assertIn("minutos_totales", self.carpeta().estado())

    def test_revisar_coteja_a1_contra_la_salida_cruda_y_a2_contra_la_captura(self):
        investigacion = self.base / "laboral_materia" / "investigacion"
        (investigacion / "a1_raw").mkdir(parents=True)
        (investigacion / "a1_raw" / "q01.json").write_text(
            json.dumps({"texto": "Artículo 1. Texto ficticio\nde la ley de prueba."}), encoding="utf-8")
        pm.escribir_json(investigacion / "a1_mapa_normativo.json", {"items": [
            {"articulo": "1", "extracto": "Texto ficticio de la ley de prueba."},     # literal (salto de línea)
            {"articulo": "2", "extracto": "Texto parafraseado que no está en el corpus."},
        ], "huecos": [], "consultas_realizadas": 1})
        pm.escribir_json(investigacion / "a2" / "a2_jurisprudencia.json", {"terminos": ["uno"], "verificadas": [
            {"registro": "2000001", "numero_tesis": "P./J. 1/2020 (10a.)", "rubro": "RUBRO FICTICIO 2000001.",
             "epoca": "Décima Época", "fuente": "Ficticia", "instancia": "Pleno", "tipo": "Jurisprudencia"},
            {"registro": "2000002", "numero_tesis": "P./J. 2/2020 (10a.)", "rubro": "RUBRO CAMBIADO POR EL AGENTE.",
             "epoca": "Décima Época", "fuente": "Ficticia", "instancia": "Pleno", "tipo": "Jurisprudencia"},
            {"registro": "2000003", "numero_tesis": "P./J. 3/2020 (10a.)"},
        ]})
        informe = pm.revisar(self.carpeta())
        self.assertEqual((informe["a1"]["items"], informe["a1"]["literales"]), (2, 1))
        self.assertEqual(informe["a1"]["no_literales"][0]["articulo"], "2")
        self.assertEqual([(d["registro"], d["campo"]) for d in informe["a2"]["diferencias"]], [("2000002", "rubro")])
        self.assertEqual(informe["a2"]["sin_captura_verificada"], ["2000003"])

    def test_medir_suma_los_tokens_de_los_agentes(self):
        pm.medir(self.carpeta(), "A1", 100, 2.0)
        estado = pm.medir(self.carpeta(), "A2", 50, 1.5)
        self.assertEqual(estado["medicion"]["tokens_subagentes"], 150)


class TestCli(Base):
    def _correr(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(REPO / "scripts" / "protocolo_materia.py"), *args],
                              capture_output=True, text=True, cwd=REPO, check=False)

    def test_carpeta_inexistente_sale_con_2(self):
        self.assertEqual(self._correr("gates", str(self.base / "no_existe")).returncode, 2)

    def test_gates_sin_rag_no_es_exito_y_sale_con_1(self):
        self.preparar()
        pm.escribir(self.carpeta(), borrador())
        resultado = self._correr("gates", str(self.base / "laboral_materia"), "--sin-rag", "--cambio", "prueba")
        self.assertEqual(resultado.returncode, 1, resultado.stdout + resultado.stderr)
        self.assertIn("SEGUIR", resultado.stdout)
        self.assertTrue((self.base / "laboral_materia" / "gates_iter1.json").exists())


if __name__ == "__main__":
    unittest.main()
