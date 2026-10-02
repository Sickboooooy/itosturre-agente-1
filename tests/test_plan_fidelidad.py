"""Pruebas del cotejo de fidelidad determinista (C10, PR-4, ronda 2): motor puro, política de
precisión, pares adversariales, cotejo del ledger con paquete, PL-020 con decisiones humanas
ligadas a la huella de cada señal, reporte, CLI y Gold Set.

Los paquetes se arman en temporales con los fixtures oficiales de ``tests/fixtures/evidencia/``
(mismos constructores que ``test_plan_identidad``: PDF sintéticos rotulados y un extractor
sintético de prueba). Los textos de ley son literales de esos fixtures o de las fuentes del
Gold Set de fidelidad (las del paquete piloto se copiaron literalmente); los textos sintéticos
van rotulados ("LEY SINTÉTICA DE FIDELIDAD DE PRUEBA" y las fuentes ``sintetico_adversarial``
del Gold Set) y las afirmaciones son sintéticas o paráfrasis de prueba evidentes. Sin red ni
dependencias.
"""
from __future__ import annotations

import contextlib
import copy
import dataclasses
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import plan_audit
from itosturre.evidencia.fuentes import url_leyesbiblio
from itosturre.evidencia.huellas import sha256_bytes
from itosturre.evidencia.leyesbiblio import limpiar_documento
from itosturre.evidencia.leyesbiblio import registro_evidencia as registro_ley
from itosturre.evidencia.paquete import cargar_paquete, guardar_evidencia
from itosturre.plan import (
    REGLAS,
    REGLAS_COTEJO,
    Extractor,
    cotejar_fidelidad,
    cotejar_ledger,
    lint_ledger,
    reporte_markdown,
)
from itosturre.plan import fidelidad as F
from itosturre.plan.lint import ADVERTENCIA, ALTA, BLOQUEANTE
from scripts.evaluate_fidelidad_gold_set import (
    FidelidadGoldSetInvalido,
    evaluar_gold_set,
    validar_dataset,
)
from tests.test_plan_identidad import (
    CNPP_ART_2O,
    EXTRACTOR_PRUEBA,
    EXTRACTORES,
    FECHA_SINTETICA,
    FIXTURES,
    HUMANO,
    PDF_SINTETICO,
    VERSION_PRUEBA,
    agregar_ley,
    afirmacion,
    evidencia_ley,
    extraer_prueba,
    ledger,
    paginas_fixture,
)

REPO = Path(__file__).resolve().parent.parent
GOLD_SET = REPO / "tests" / "fixtures" / "fidelidad_gold_set_v1.json"
SHA_CNPP = sha256_bytes(PDF_SINTETICO["CNPP"])
SHA_CPF = sha256_bytes(PDF_SINTETICO["CPF"])
PLAN = "PLAN-C9"  # ID del plan de ``test_plan_identidad.ledger``

# Literales de los fixtures (una prueba comprueba que lo son).
CPF_429 = (
    "Los delitos previstos en este Título se perseguirán de oficio, excepto lo previsto en los \n"
    "artículos 424, fracción II, 424 Bis, fracción III y 427."
)
CPF_2O_I = "Por los delitos que se inicien, preparen o cometan en el extranjero"
CNPP_489_AUDIENCIA = "dentro de los cinco días siguientes al recibo de los registros y de las"

# Afirmaciones de prueba sobre el art. 2o. CNPP (fixture, p. 1): la de A1 suprime la negación.
TEXTO_INFIEL = "CNPP 2o: el Código tiene por objeto procurar que el culpable quede impune."
TEXTO_FIEL = "CNPP 2o: el Código tiene por objeto procurar que el culpable no quede impune y que se repare el daño."
TEXTO_OMISION = "CPF 2o: el Código se aplica por los delitos que se inicien, preparen o cometan en el extranjero."

# Ley sintética rotulada (no es ninguna ley real ni se cita): los artículos de los fixtures que
# la identidad ubica sin ambigüedad (página 1) no traen modos de procedibilidad ni plazos, y
# las señales de precisión alta necesitan uno. Mismo patrón que ``LEY_SINTETICA`` (C9, D1).
PDF_FIDELIDAD = b"%PDF sintetico de prueba (FIDELIDAD): no es un documento oficial\n"
SHA_FIDELIDAD = sha256_bytes(PDF_FIDELIDAD)
LEY_FIDELIDAD = "\n".join([
    "LEY SINTÉTICA DE FIDELIDAD DE PRUEBA",
    "CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN",
    "Secretaría General",
    "Secretaría de Servicios Parlamentarios",
    "Última Reforma DOF 01-01-1800",
    "1 de 1",
    "Artículo 1o.- Los delitos sintéticos de esta ley de prueba se perseguirán por querella de la persona ofendida.",
    "Artículo 2o.- El recurso sintético de prueba se interpondrá dentro de los tres días siguientes a aquel en que "
    "surta efectos la notificación.",
])
EXTRACTO_QUERELLA = "se perseguirán por querella de la persona ofendida"
EXTRACTO_RECURSO = "se interpondrá dentro de los tres días siguientes"
# Afirmaciones sintéticas sobre esa ley: modo distinto (art. 1o.), inicio del cómputo distinto
# y facultad en lugar de mandato (art. 2o.).
DE_OFICIO = "Los delitos sintéticos de esta ley de prueba se persiguen de oficio (afirmación sintética)."
INICIO_DISTINTO = ("El recurso sintético de prueba se interpone dentro de los tres días siguientes a la publicación "
                   "(afirmación sintética).")
FACULTAD = ("El recurso sintético de prueba podrá interponerse dentro de los tres días siguientes a aquel en que surta "
            "efectos la notificación (afirmación sintética).")


def extraer_fidelidad(original: bytes) -> list[str]:
    """Extractor sintético de prueba: la ley sintética de fidelidad, o las páginas del fixture."""
    if original == PDF_FIDELIDAD:
        return [LEY_FIDELIDAD]
    return extraer_prueba(original)


EXTRACTORES_FID = (Extractor(EXTRACTOR_PRUEBA, VERSION_PRUEBA, extraer_fidelidad),)


def agregar_ley_fidelidad(raiz: Path) -> dict:
    documento = limpiar_documento([LEY_FIDELIDAD], numeros=[1], total_paginas=1)
    evidencia = registro_ley(
        documento, archivo="FIDELIDAD.pdf", url=url_leyesbiblio("FIDELIDAD.pdf"), fecha_consulta=FECHA_SINTETICA,
        original_sha256=SHA_FIDELIDAD, original_bytes=len(PDF_FIDELIDAD), extractor=EXTRACTOR_PRUEBA,
        version_extractor=VERSION_PRUEBA,
    )
    guardar_evidencia(raiz, evidencia, original=PDF_FIDELIDAD, derivado=documento.texto,
                      texto_extraido=documento.texto_extraido)
    return evidencia


def evidencia_fidelidad(id_: str, ubicacion: str, extracto: str) -> dict:
    return evidencia_ley(id_, ubicacion, extracto, "SINTETICA", archivo="FIDELIDAD.pdf",
                         sha256_documento=SHA_FIDELIDAD)


def fuente(texto: str, descriptor: str = "art. de prueba", sha: str | None = "f" * 64, *,
           articulo: str | None = None, truncado: bool = False) -> F.FuenteTexto:
    return F.FuenteTexto(descriptor, texto, sha, articulo, truncado)


def pagina(ley: str, numero: int) -> str:
    """Texto literal de una página del fixture oficial (fuente de las pruebas del motor)."""
    return next(p["texto"] for p in paginas_fixture(ley)["paginas"] if p["numero"] == numero)


def codigos(senales) -> list[str]:
    return [s.codigo for s in senales]


def gold() -> dict:
    return json.loads(GOLD_SET.read_text(encoding="utf-8"))


def caso_gold(datos: dict, id_: str) -> tuple[str, list[F.FuenteTexto]]:
    """(afirmación, fuentes) de un caso del Gold Set de fidelidad, con su marca de truncado."""
    caso = next(c for c in datos["cases"] if c["id"] == id_)
    fuentes = [datos["fuentes"][clave] for clave in caso["fuentes"]]
    return caso["afirmacion"], [F.FuenteTexto(f["descriptor"], f["texto"], None, None, bool(f.get("truncado")))
                                for f in fuentes]


class LiteralesTests(unittest.TestCase):
    def test_los_literales_vienen_de_los_fixtures(self) -> None:
        cpf = {p["numero"]: p["texto"] for p in paginas_fixture("CPF")["paginas"]}
        cnpp = {p["numero"]: p["texto"] for p in paginas_fixture("CNPP")["paginas"]}
        self.assertIn(CPF_429, cpf[147])
        self.assertIn(CPF_2O_I, cpf[1])
        self.assertIn(CNPP_489_AUDIENCIA, " ".join(cnpp[139].split()))
        self.assertIn(" ".join(CNPP_ART_2O.split()), " ".join(cnpp[1].split()))

    def test_la_ley_de_fidelidad_esta_rotulada_como_sintetica(self) -> None:
        self.assertTrue(LEY_FIDELIDAD.startswith("LEY SINTÉTICA DE FIDELIDAD DE PRUEBA"))
        self.assertIn(b"no es un documento oficial", PDF_FIDELIDAD)
        self.assertIn(EXTRACTO_QUERELLA, LEY_FIDELIDAD)
        self.assertIn(EXTRACTO_RECURSO, LEY_FIDELIDAD)
        for afirmacion_ in (DE_OFICIO, INICIO_DISTINTO, FACULTAD):
            self.assertIn("(afirmación sintética)", afirmacion_)


# ── Motor puro ───────────────────────────────────────────────────────────────


class MotorTests(unittest.TestCase):
    def test_nunca_emite_conforme(self) -> None:
        self.assertNotIn("CONFORME", F.RESULTADOS)
        self.assertEqual(set(F.RESULTADOS), {"SENALES", "SIN_SENALES_DETECTADAS", "NO_COTEJABLE"})
        self.assertEqual(F.ETIQUETA_SIN_SENALES,
                         "sin señales detectadas por reglas deterministas; revisión del abogado obligatoria")
        self.assertIn(F.ETIQUETA_SIN_SENALES, F.AVISO)
        self.assertIn("no sustituyen la lectura del abogado", F.AVISO)

    def test_codigos_cerrados_con_categoria_severidad_y_precision(self) -> None:
        for codigo, (categoria, severidad, precision, descripcion) in F.CODIGOS.items():
            with self.subTest(codigo=codigo):
                self.assertTrue(codigo.startswith(categoria + "."))
                self.assertIn(categoria, (*F.CATEGORIAS, F.ALINEACION))
                self.assertIn(severidad, F.SEVERIDADES)
                self.assertIn(precision, F.PRECISIONES)
                self.assertTrue(descripcion)
        self.assertEqual({c[0] for c in F.CODIGOS.values()}, {*F.CATEGORIAS, F.ALINEACION})

    def test_politica_de_precision(self) -> None:
        """Solo tres códigos de alta precisión; todo lo demás es "señal a revisar"."""
        self.assertEqual(F.CODIGOS_ALTA, {
            "procedibilidad.modo_distinto",
            "plazos_cifras.distinto_misma_condicion",
            "inicio_computo.distinto",
        })
        for codigo in ("plazos_cifras.cifra_ausente", "inicio_computo.omitido", "procedibilidad.requisito_omitido",
                       "excepcion_condicion.excepcion_omitida", "cuantificador.omitido", "modal.atenuacion",
                       "negacion.polaridad_distinta", "sujeto.organo_distinto", "alineacion.ambigua"):
            with self.subTest(codigo=codigo):
                self.assertEqual(F.CODIGOS[codigo][2], F.REVISAR)

    def test_procedibilidad_contradiccion_y_omision(self) -> None:
        texto = pagina("CPF", 147)  # art. 429: "se perseguirán de oficio, excepto…"
        senales = F.comparar("Los delitos previstos en este Título se persiguen por querella.", [fuente(texto)])
        self.assertEqual(codigos(senales), ["procedibilidad.modo_distinto"])
        senal = senales[0]
        self.assertEqual((senal.categoria, senal.severidad, senal.precision),
                         ("procedibilidad", "contradiccion", F.ALTA))
        self.assertEqual(senal.marca_afirmacion, "querella")
        self.assertEqual(senal.marca_fuente, "de oficio")
        self.assertIn(senal.tramo_fuente, texto)
        self.assertEqual(F.comparar("Los delitos de este Título se persiguen de oficio, excepto los previstos en "
                                    "los artículos 424, fracción II, 424 Bis, fracción III y 427.", [fuente(texto)]), ())
        omision = F.comparar("Los delitos previstos en este Título se perseguirán de oficio.", [fuente(texto)])
        self.assertEqual([(s.codigo, s.precision) for s in omision],
                         [("excepcion_condicion.excepcion_omitida", F.REVISAR)])

    def test_oficiosamente_no_es_un_modo_de_procedibilidad(self) -> None:
        # Art. 167 CNPP (pp. 52 y 54): "ordenará la prisión preventiva oficiosamente" y, en la
        # misma fuente, "persecución penal" (art. 168): hay contexto, pero ningún modo.
        paginas = [fuente(pagina("CNPP", 52)), fuente(pagina("CNPP", 54))]
        self.assertFalse([m for f in paginas for o in F._preparar_fuente(f).oraciones for m in F._modos(o)])
        senales = F.comparar("La prisión preventiva oficiosa se persigue por denuncia.", paginas)
        self.assertFalse([s for s in senales if s.categoria == "procedibilidad"])

    def test_cifras_en_palabras_rangos_y_alternativas(self) -> None:
        texto = F._Texto("de dos a nueve años; 3 o 5 días; ciento ochenta días naturales; setenta y dos horas; "
                         "trescientos sesenta y cinco días; de quinientos a mil días multa; un año")
        cifras = [(c.valores, c.unidad, c.calificador, c.rango) for o in F._oraciones(texto) for c in F._cifras(o)]
        self.assertEqual(cifras, [
            ((2, 9), "anos", None, True), ((3,), "dias", None, False), ((5,), "dias", None, False),
            ((180,), "dias", "naturales", False), ((72,), "horas", None, False), ((365,), "dias", None, False),
            ((500, 1000), "dias multa", None, True), ((1,), "anos", None, False),
        ])
        # Fechas y artículos no son cifras con unidad.
        texto = F._Texto("DOF 07-11-2025; art. 113 Bis; fracción III")
        self.assertEqual([c for o in F._oraciones(texto) for c in F._cifras(o)], [])

    def test_separador_de_miles_calendario_y_montos(self) -> None:
        """Ronda 2: "1,000" es mil (no "1" y "000"), "de calendario" = naturales, y los montos
        (UMA, pesos, "$", salario mínimo) son unidades."""
        texto = F._Texto("1,000 días multa; diez días de calendario; 100 UMA; $2,531,920.00; dos salarios mínimos; "
                         "500 pesos; de 3 a 9 años")
        cifras = [(c.valores, c.unidad, c.calificador, c.rango) for o in F._oraciones(texto) for c in F._cifras(o)]
        self.assertEqual(cifras, [
            ((1000,), "dias multa", None, False), ((10,), "dias", "naturales", False), ((100,), "uma", None, False),
            ((2531920,), "pesos", None, False), ((2,), "salario_minimo", None, False), ((500,), "pesos", None, False),
            ((3, 9), "anos", None, True),
        ])

    def test_plazos_numero_unidad_calificador_y_cifra_ausente(self) -> None:
        texto = pagina("CNPP", 139)  # transitorio segundo: "deberán mediar sesenta días naturales"
        casos = {
            "Entre la Declaratoria y la entrada en vigor del Código deben mediar sesenta días hábiles.":
                "plazos_cifras.calificador_distinto",
            "Entre la Declaratoria y la entrada en vigor del Código deben mediar noventa días naturales.":
                "plazos_cifras.numero_distinto",
            "Entre la Declaratoria y la entrada en vigor del Código deben mediar sesenta meses.":
                "plazos_cifras.unidad_distinta",
        }
        for afirmacion_, codigo in casos.items():
            with self.subTest(codigo=codigo):
                senales = F.comparar(afirmacion_, [fuente(texto)])
                self.assertEqual(codigos(senales), [codigo])
                self.assertEqual(senales[0].precision, F.REVISAR)  # cifra sin condición: a revisar
        ausente = "El Código entra en vigor cuarenta y ocho horas después de la Declaratoria del Congreso."
        senales = F.comparar(ausente, [fuente(texto)])
        self.assertEqual([(s.codigo, s.precision) for s in senales], [("plazos_cifras.cifra_ausente", F.REVISAR)])
        # Con fuentes parciales o truncadas la cifra ausente no se atribuye.
        self.assertEqual(F.comparar(ausente, [fuente(texto)], fuentes_completas=False), ())
        self.assertEqual(F.comparar(ausente, [fuente(texto, truncado=True)]), ())
        fiel = "En todos los casos deben mediar 60 días naturales entre la Declaratoria y la entrada en vigor del Código."
        self.assertEqual(F.comparar(fiel, [fuente(texto)]), ())

    def test_inicio_del_computo(self) -> None:
        texto = pagina("CNPP", 139)  # art. 489
        distinto = "La audiencia se celebrará dentro de los cinco días siguientes a la notificación de la solicitud."
        omitido = "Recibidos los registros, el Tribunal de alzada citará a las partes a una audiencia dentro de cinco días."
        fiel = "La audiencia se celebrará dentro de los cinco días siguientes al recibo de los registros y de las pruebas."
        self.assertEqual([(s.codigo, s.precision) for s in F.comparar(distinto, [fuente(texto)])],
                         [("inicio_computo.distinto", F.ALTA)])
        self.assertEqual([(s.codigo, s.precision) for s in F.comparar(omitido, [fuente(texto)])],
                         [("inicio_computo.omitido", F.REVISAR)])
        self.assertEqual(F.comparar(fiel, [fuente(texto)]), ())

    def test_modales(self) -> None:
        texto = pagina("CNPP", 54)  # art. 167: "La solicitud deberá contar con la autorización…"
        self.assertEqual(codigos(F.comparar(
            "La solicitud podrá contar con la autorización del titular de la Fiscalía.", [fuente(texto)])),
            ["modal.atenuacion"])
        self.assertIn("modal.cambio", codigos(F.comparar(
            "La solicitud no podrá contar con la autorización del titular de la Fiscalía.", [fuente(texto)])))
        self.assertEqual(F.comparar("La solicitud debe contar con la autorización del titular de la Fiscalía.",
                                    [fuente(texto)]), ())
        # "no" que niega otra palabra no convierte el modal en prohibición (art. 3o. CFF, p. 2).
        self.assertEqual(F.comparar(
            "Los aprovechamientos por multas no fiscales podrán destinarse a cubrir los gastos de operación e "
            "inversión de las dependencias, cuando así lo establezcan las disposiciones jurídicas aplicables.",
            [fuente(pagina("CFF", 2))]), ())

    def test_negacion_y_equivalencia_logica(self) -> None:
        texto = pagina("CPEUM", 71)  # art. 73, VIII, 1o.: "Ningún empréstito podrá celebrarse sino para…"
        equivalente = ("Los empréstitos solo podrán celebrarse para la ejecución de obras que directamente produzcan "
                       "un incremento en los ingresos públicos.")
        self.assertEqual(F.comparar(equivalente, [fuente(texto)]), ())
        sin_restriccion = ("Los empréstitos podrán celebrarse para la ejecución de obras que directamente produzcan "
                           "un incremento en los ingresos públicos.")
        self.assertIn("cuantificador.omitido", codigos(F.comparar(sin_restriccion, [fuente(texto)])))
        cnpp = pagina("CNPP", 1)
        senales = F.comparar(TEXTO_INFIEL, [fuente(cnpp)])
        self.assertEqual([(s.codigo, s.precision) for s in senales], [("negacion.polaridad_distinta", F.REVISAR)])
        self.assertEqual(F.comparar(TEXTO_FIEL, [fuente(cnpp)]), ())

    def test_excepciones_y_cuantificadores(self) -> None:
        self.assertIn("excepcion_condicion.excepcion_omitida", codigos(F.comparar(
            "Los delitos previstos en este Título se perseguirán de oficio.", [fuente(pagina("CPF", 147))])))
        texto = pagina("CNPP", 52)  # art. 167: "El Ministerio Público sólo podrá solicitar…"
        self.assertIn("cuantificador.omitido", codigos(F.comparar(
            "El Ministerio Público podrá solicitar al Juez de control la prisión preventiva cuando otras medidas "
            "cautelares no sean suficientes.", [fuente(texto)])))
        self.assertIn("cuantificador.anadido", codigos(F.comparar(
            "El Ministerio Público siempre podrá solicitar al Juez de control la prisión preventiva cuando otras "
            "medidas cautelares no sean suficientes.", [fuente(texto)])))
        # "siempre que" es condición, no cuantificador (art. 20 CFF, p. 30).
        self.assertEqual(F.comparar(
            "Las personas físicas con ingresos inferiores al límite pueden pagar con cheques personales del mismo "
            "banco, siempre que se cumplan las condiciones que establezca el Reglamento.",
            [fuente(pagina("CFF", 30))]), ())

    def test_fuente_truncada_es_incompleta(self) -> None:
        """Ronda 2: el artículo puede continuar en páginas no recibidas; no se señalan
        ausencias en él (ni modo distinto ni cifra ausente)."""
        texto = pagina("CPF", 147)
        querella = "Los delitos previstos en este Título se persiguen por querella."
        self.assertEqual(codigos(F.comparar(querella, [fuente(texto)])), ["procedibilidad.modo_distinto"])
        self.assertEqual(F.comparar(querella, [fuente(texto, truncado=True)]), ())
        afirmacion_, fuentes = caso_gold(gold(), "ADV-TRUNC-01")
        self.assertTrue(all(f.truncado for f in fuentes))
        self.assertEqual(F.comparar(afirmacion_, fuentes), ())
        sin_truncar = [dataclasses.replace(f, truncado=False) for f in fuentes]
        self.assertEqual(codigos(F.comparar(afirmacion_, sin_truncar)), ["plazos_cifras.cifra_ausente"])

    def test_cada_oracion_de_los_fixtures_frente_a_su_pagina_no_da_senales(self) -> None:
        """Una afirmación que copia una oración del texto oficial no genera señales."""
        for ley in ("CFF", "CNPP", "CPEUM", "CPF", "LAmp"):
            for pagina_ in paginas_fixture(ley)["paginas"]:
                texto = F._Texto(pagina_["texto"])
                for oracion in F._oraciones(texto, F._notas_de_reforma(texto)):
                    frase = oracion.literal
                    if len(frase) < 25:
                        continue
                    with self.subTest(ley=ley, pagina=pagina_["numero"], frase=frase[:60]):
                        self.assertEqual(F.comparar(frase, [fuente(pagina_["texto"])]), ())

    def test_tramos_literales(self) -> None:
        cnpp = paginas_fixture("CNPP")["paginas"][0]["texto"]
        for senal in F.comparar(TEXTO_INFIEL, [fuente(cnpp)]):
            self.assertIn(senal.tramo_afirmacion, TEXTO_INFIEL)
            self.assertIn(senal.tramo_fuente, cnpp)
            self.assertIn(senal.marca_fuente, cnpp)
            self.assertIn(senal.marca_afirmacion, TEXTO_INFIEL)

    def test_notas_de_reforma_no_son_texto_normativo(self) -> None:
        texto = pagina("CNPP", 52)  # "Párrafo reformado DOF 19-02-2021, 28-11-2025" tras el párrafo tercero
        self.assertIn("Párrafo reformado DOF 19-02-2021, 28-11-2025", texto)
        preparada = F._preparar_fuente(fuente(texto))
        self.assertTrue(preparada.oraciones)
        self.assertTrue(all("19-02-2021" not in o.literal for o in preparada.oraciones))

    def test_huella_de_la_senal(self) -> None:
        """La huella identifica código, fuente, artículo, documentos y tramos: es estable al
        recalcular y cambia si cambia cualquiera de ellos."""
        texto = pagina("CPF", 147)
        querella = "Los delitos previstos en este Título se persiguen por querella."
        senal = F.comparar(querella, [fuente(texto, articulo="429")])[0]
        self.assertEqual(senal.huella, F.comparar(querella, [fuente(texto, articulo="429")])[0].huella)
        self.assertEqual(senal.articulo, "429")
        self.assertEqual(senal.como_dict()["huella"], senal.huella)
        for cambio in ({"articulo": "430"}, {"fuente": "art. 430 CPF"}, {"tramo_fuente": "otro tramo"},
                       {"tramo_afirmacion": "otra afirmación"}, {"sha256_documentos": ("e" * 64,)},
                       {"codigo": "procedibilidad.modo_negado"}):
            with self.subTest(cambio=cambio):
                self.assertNotEqual(dataclasses.replace(senal, **cambio).huella, senal.huella)


# ── Pares adversariales (ronda 2) ────────────────────────────────────────────

# Caso del Gold Set → códigos esperados con el motor 2.0. Con el motor 1.0 los FN daban
# "sin señales" y los FP una contradicción que bloqueaba (``docs/ROADMAP_AUDITORIA_PLANES.md``).
PARES_ADVERSARIALES = {
    "ADV-FN-01": ["plazos_cifras.calificador_distinto"],  # "de calendario" = naturales
    "ADV-FN-02": ["plazos_cifras.rango_distinto"],  # rango comparado como par
    "ADV-FN-03": ["plazos_cifras.numero_distinto"],  # UMA es unidad
    "ADV-FN-04": ["sujeto.organo_distinto"],  # fiscal frente a juez
    "ADV-FN-05": ["negacion.polaridad_distinta"],  # doble negación por paridad
    "ADV-FN-06": ["excepcion_condicion.excepcion_distinta"],  # contenido de la excepción
    "ADV-FN-07": ["modal.refuerzo"],  # "podrá ordenar" → "ordenará"
    "ADV-FN-08": ["modal.atenuacion"],  # se alinea con la oración del mismo órgano
    "ADV-FP-01": [],  # "no le está permitido" = "no podrá"
    "ADV-FP-02": [],  # "le está prohibido" = "no podrá"
    "ADV-FP-03": [],  # reordenar y separar cláusulas
    "ADV-FP-04": [],  # "1,000" = "mil"
    "ADV-FP-05": [],  # artículo con varias oraciones
    "ADV-COORD-01": ["plazos_cifras.distinto_misma_condicion"],  # cinco días para autos (son tres)
    "ADV-COORD-02": ["modal.atenuacion"],  # "podrá interponerse" frente a "se interpondrá"
    "ADV-COORD-03": ["plazos_cifras.distinto_misma_condicion"],  # tres días para sentencia (son cinco)
    "ADV-COORD-C1": [],
    "ADV-COORD-C2": [],
    "ADV-TRUNC-01": [],  # fuente truncada: sin cifra ausente
    "ALIN-01": ["alineacion.ambigua"],  # rivales cercanos con resultados distintos: se abstiene
}


class AdversarialesTests(unittest.TestCase):
    def test_pares_adversariales(self) -> None:
        datos = gold()
        for id_, esperado in PARES_ADVERSARIALES.items():
            with self.subTest(caso=id_):
                afirmacion_, fuentes = caso_gold(datos, id_)
                senales = F.comparar(afirmacion_, fuentes)
                self.assertEqual(codigos(senales), esperado)
                # Ningún par fiel ni ningún FN corregido de baja precisión bloquea.
                for senal in senales:
                    self.assertEqual(senal.precision == F.ALTA, senal.codigo in F.CODIGOS_ALTA)

    def test_los_pares_estan_en_el_gold_set_con_su_expectativa(self) -> None:
        casos = {c["id"]: c for c in gold()["cases"]}
        for id_, esperado in PARES_ADVERSARIALES.items():
            with self.subTest(caso=id_):
                self.assertIn(id_, casos)
                self.assertEqual(len(casos[id_]["esperado"]), len(esperado))

    def test_condicion_ligada_a_cada_cifra(self) -> None:
        """Art. 471 CNPP (paquete piloto): tres días si es auto y cinco si es sentencia
        definitiva; cada cifra de la afirmación se compara con la de su misma condición."""
        datos = gold()
        for id_ in ("ADV-COORD-01", "ADV-COORD-03"):
            with self.subTest(caso=id_):
                afirmacion_, fuentes = caso_gold(datos, id_)
                senal = F.comparar(afirmacion_, fuentes)[0]
                self.assertEqual(senal.precision, F.ALTA)
                self.assertIn("para la misma condición", senal.detalle)
                self.assertIn(senal.tramo_fuente, fuentes[0].texto)

    def test_alineacion_ambigua_se_abstiene_y_nunca_es_alta(self) -> None:
        afirmacion_, fuentes = caso_gold(gold(), "ALIN-01")
        senales = F.comparar(afirmacion_, fuentes)
        self.assertEqual([(s.codigo, s.severidad, s.precision) for s in senales],
                         [("alineacion.ambigua", F.INDETERMINADA, F.REVISAR)])
        self.assertIn("revisar a mano", senales[0].detalle)


# ── Cotejo del ledger con paquete ────────────────────────────────────────────


class _ConPaquete(unittest.TestCase):
    def setUp(self) -> None:
        temporal = tempfile.TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        self.base = Path(temporal.name)
        self.raiz = self.base / "paquete"
        agregar_ley(self.raiz, "CNPP")
        agregar_ley(self.raiz, "CPF")

    def paquete(self):
        return cargar_paquete(self.raiz)

    def libro(self, decisiones: list[dict] | None = None) -> dict:
        return ledger(
            [
                afirmacion("A1", ["E1"], texto=TEXTO_INFIEL),
                afirmacion("A2", [], tipo="propuesta", estado="CANDIDATO",
                           texto="Propuesta de prueba: el objeto del Código es procurar que el culpable quede impune.",
                           referencias=["art. 2o. CNPP"]),
                afirmacion("A3", ["E1"], texto=TEXTO_FIEL),
                afirmacion("A4", [], tipo="inferencia", estado="CANDIDATO", texto="Inferencia sintética de prueba.",
                           referencias=["art. 999 CNPP", "art. 1 LNEP", "art. 2"]),
                afirmacion("A5", ["E2"], texto=TEXTO_OMISION),
                afirmacion("A6", [], tipo="hecho_aportado", estado="CANDIDATO", texto="Hecho sintético de prueba."),
                afirmacion("A7", ["E1"], estado="INEXISTENTE", texto=TEXTO_INFIEL),
            ],
            [
                evidencia_ley("E1", "Artículo 2o.", CNPP_ART_2O, "CNPP"),
                evidencia_ley("E2", "Artículo 2o.", CPF_2O_I, "CPF"),
            ],
            decisiones,
        )

    def libro_alta(self, decisiones: list[dict] | None = None) -> dict:
        """Ledger sobre la ley sintética rotulada: señales de precisión alta y una a revisar."""
        agregar_ley_fidelidad(self.raiz)
        return ledger(
            [
                afirmacion("B1", ["F1"], texto=DE_OFICIO),
                afirmacion("B2", ["F1"], estado="CANDIDATO", texto=DE_OFICIO),
                afirmacion("B3", ["F2"], texto=INICIO_DISTINTO),
                afirmacion("B4", ["F2"], texto=FACULTAD),
            ],
            [
                evidencia_fidelidad("F1", "Artículo 1o.", EXTRACTO_QUERELLA),
                evidencia_fidelidad("F2", "Artículo 2o.", EXTRACTO_RECURSO),
            ],
            decisiones,
        )

    def fidelidad(self, libro: dict):
        return cotejar_fidelidad(libro, self.paquete(), extractores=EXTRACTORES_FID)

    def resultado(self, libro: dict, id_: str) -> F.ResultadoFidelidad:
        return next(r for r in self.fidelidad(libro).afirmaciones if r.afirmacion == id_)

    def lint(self, libro: dict) -> dict[str, list[tuple[str, str]]]:
        resultado: dict[str, list[tuple[str, str]]] = {}
        for hallazgo in lint_ledger(libro, paquete=self.paquete(), extractores=EXTRACTORES_FID):
            if hallazgo["regla"] == "PL-020":
                resultado.setdefault(hallazgo["objetivo"], []).append((hallazgo["severidad"], hallazgo["mensaje"]))
        return resultado


class CotejoLedgerTests(_ConPaquete):
    def test_resultados_por_afirmacion(self) -> None:
        fidelidad = self.fidelidad(self.libro())
        por_id = {r.afirmacion: r for r in fidelidad.afirmaciones}
        self.assertEqual(fidelidad.fuera_de_alcance, ("A6",))
        self.assertEqual(por_id["A1"].resultado, F.SENALES)
        self.assertEqual(codigos(por_id["A1"].senales), ["negacion.polaridad_distinta"])
        self.assertEqual([(f.descriptor, f.origen, f.evidencias) for f in por_id["A1"].fuentes],
                         [("art. 2o CNPP", "par_conforme", ("E1",))])
        self.assertEqual(por_id["A1"].fuentes[0].sha256_documento, SHA_CNPP)
        senal = por_id["A1"].senales[0]
        self.assertEqual((senal.sha256_documentos, senal.articulo, senal.fuente), ((SHA_CNPP,), "2o", "art. 2o CNPP"))
        # Sin evidencia: la referencia "art. 2o. CNPP" se resuelve contra el paquete.
        self.assertEqual(por_id["A2"].resultado, F.SENALES)
        self.assertEqual([(f.descriptor, f.origen, f.referencia) for f in por_id["A2"].fuentes],
                         [("art. 2o CNPP", "referencia", "art. 2o. CNPP")])
        self.assertEqual(por_id["A3"].resultado, F.SIN_SENALES_DETECTADAS)
        self.assertEqual(por_id["A3"].etiqueta, f"SIN_SENALES_DETECTADAS ({F.ETIQUETA_SIN_SENALES})")
        self.assertEqual(por_id["A5"].resultado, F.SENALES)
        self.assertEqual(codigos(por_id["A5"].senales), ["excepcion_condicion.condicion_omitida"])
        self.assertEqual(por_id["A7"].resultado, F.NO_COTEJABLE)
        self.assertFalse(fidelidad.nada_cotejable)
        datos = fidelidad.como_dict()
        self.assertEqual((datos["esquema"], datos["version_motor"]), (F.ESQUEMA_FIDELIDAD, F.VERSION_MOTOR))
        self.assertEqual(datos["resumen"]["alta"], 0)
        self.assertEqual(datos["resumen"]["revisar"], 3)

    def test_no_cotejable_dice_por_que(self) -> None:
        resultado = next(r for r in self.fidelidad(self.libro()).afirmaciones if r.afirmacion == "A4")
        self.assertEqual(resultado.resultado, F.NO_COTEJABLE)
        motivos = " | ".join(resultado.motivos)
        self.assertIn("art. 999 CNPP no se ubica sin ambigüedad", motivos)
        self.assertIn("no acredita que no exista", motivos)
        self.assertIn("no tiene registrada la ley LNEP", motivos)
        self.assertIn("art. 2 sin ordenamiento identificable", motivos)

    def test_nada_cotejable(self) -> None:
        libro = ledger([afirmacion("A4", [], tipo="inferencia", estado="CANDIDATO", texto="Inferencia sintética.",
                                   referencias=["art. 999 CNPP"])], [])
        fidelidad = self.fidelidad(libro)
        self.assertTrue(fidelidad.nada_cotejable)
        self.assertTrue(fidelidad.como_dict()["nada_cotejable"])

    def test_ley_ambigua_en_el_paquete_no_se_elige(self) -> None:
        agregar_ley(self.raiz, "CNPP", archivo="CNPP.pdf", pdf=PDF_SINTETICO["OTRA"])  # otro registro del CNPP
        libro = ledger([afirmacion("A2", [], tipo="propuesta", estado="CANDIDATO", texto=TEXTO_INFIEL,
                                   referencias=["art. 2o. CNPP"])], [])
        resultado = self.fidelidad(libro).afirmaciones[0]
        self.assertEqual(resultado.resultado, F.NO_COTEJABLE)
        self.assertIn("ambiguo, no se elige", " ".join(resultado.motivos))

    def test_relacion_original_texto_no_comprobable_no_se_coteja(self) -> None:
        libro = ledger([afirmacion("A2", [], tipo="propuesta", estado="CANDIDATO", texto=TEXTO_INFIEL,
                                   referencias=["art. 2o. CNPP"])], [])
        resultado = cotejar_fidelidad(libro, self.paquete(), extractores=()).afirmaciones[0]
        self.assertEqual(resultado.resultado, F.NO_COTEJABLE)
        self.assertIn("no se acredita en el paquete", " ".join(resultado.motivos))

    def test_cotejo_de_otro_ledger_se_rechaza(self) -> None:
        libro = self.libro()
        otro = copy.deepcopy(libro)
        otro["afirmaciones"][0]["texto"] = TEXTO_FIEL
        cotejo = cotejar_ledger(otro, self.paquete(), extractores=EXTRACTORES_FID)
        with self.assertRaises(ValueError):
            cotejar_fidelidad(libro, self.paquete(), cotejo=cotejo, extractores=EXTRACTORES_FID)
        fidelidad = self.fidelidad(otro)
        with self.assertRaisesRegex(ValueError, "otro contenido"):
            lint_ledger(libro, fidelidad=fidelidad)
        with self.assertRaises(ValueError):
            lint_ledger(libro, paquete=self.paquete(), fidelidad=fidelidad)

    def test_cache_compartido_re_extrae_una_vez_por_documento(self) -> None:
        llamadas: list[bytes] = []

        def contar(original: bytes):
            llamadas.append(original)
            return EXTRACTORES[0].extraer(original)

        extractores = (Extractor(EXTRACTORES[0].nombre, EXTRACTORES[0].version, contar),)
        libro = self.libro()
        cache: dict = {}
        cotejo = cotejar_ledger(libro, self.paquete(), extractores=extractores, cache=cache)
        cotejar_fidelidad(libro, self.paquete(), cotejo=cotejo, extractores=extractores, cache=cache)
        self.assertEqual(sorted(llamadas), sorted([PDF_SINTETICO["CNPP"], PDF_SINTETICO["CPF"]]))

    def test_no_cambia_estados_ni_el_ledger(self) -> None:
        for libro in (self.libro(), self.libro_alta()):
            antes = copy.deepcopy(libro)
            self.fidelidad(libro)
            lint_ledger(libro, paquete=self.paquete(), extractores=EXTRACTORES_FID)
            self.assertEqual(libro, antes)

    def test_senales_de_precision_alta_con_la_ley_sintetica(self) -> None:
        por_id = {r.afirmacion: r for r in self.fidelidad(self.libro_alta()).afirmaciones}
        self.assertEqual({k: [(s.codigo, s.precision) for s in r.senales] for k, r in por_id.items()}, {
            "B1": [("procedibilidad.modo_distinto", F.ALTA)],
            "B2": [("procedibilidad.modo_distinto", F.ALTA)],
            "B3": [("inicio_computo.distinto", F.ALTA)],
            "B4": [("modal.atenuacion", F.REVISAR)],
        })
        self.assertEqual(por_id["B1"].fuentes[0].sha256_documento, SHA_FIDELIDAD)


# ── PL-020 y decisiones humanas ──────────────────────────────────────────────


def decision_fidelidad(resultado: F.ResultadoFidelidad, *, plan: str = PLAN, estado: str = "APROBADO",
                       responsable: str = HUMANO, resolucion: str | None = "Se corrige la afirmación en la versión 2.",
                       id_: str = "D1", cambios: dict | None = None) -> dict:
    """El bloque que imprime ``plan_audit.py fidelidad`` (``plantilla_decision``), llenado por
    una persona ficticia; ``cambios`` altera el campo ``fidelidad`` para las pruebas negativas."""
    decision = F.plantilla_decision(plan, resultado)
    decision.update(id=id_, responsable=responsable, estado=estado)
    if resolucion is None:
        del decision["fidelidad"]["resolucion"]
    else:
        decision["fidelidad"]["resolucion"] = resolucion
    decision["fidelidad"].update(cambios or {})
    return decision


class Pl020Tests(_ConPaquete):
    def test_severidades_por_precision(self) -> None:
        """Política de la ronda 2: alta → BLOQUEANTE en VERIFICADO y ALTA en otro estado;
        revisar → ADVERTENCIA "señal a revisar" en cualquier estado."""
        hallazgos = self.lint(self.libro())
        self.assertEqual([s for s, _ in hallazgos["A1"]], [ADVERTENCIA])  # negación en VERIFICADO
        self.assertEqual([s for s, _ in hallazgos["A2"]], [ADVERTENCIA])  # negación en CANDIDATO
        self.assertEqual([s for s, _ in hallazgos["A5"]], [ADVERTENCIA])  # omisión en VERIFICADO
        self.assertNotIn("A3", hallazgos)
        self.assertNotIn("A4", hallazgos)
        mensaje = hallazgos["A1"][0][1]
        self.assertIn("señal(es) a revisar", mensaje)
        self.assertIn("negacion.polaridad_distinta", mensaje)
        self.assertIn("no quede", mensaje)
        self.assertIn("no sustituyen la lectura del abogado", mensaje)
        hallazgos = self.lint(self.libro_alta())
        self.assertEqual([s for s, _ in hallazgos["B1"]], [BLOQUEANTE])
        self.assertEqual([s for s, _ in hallazgos["B2"]], [ALTA])
        self.assertEqual([s for s, _ in hallazgos["B3"]], [BLOQUEANTE])
        self.assertEqual([s for s, _ in hallazgos["B4"]], [ADVERTENCIA])
        self.assertIn("señal(es) de alta precisión", hallazgos["B1"][0][1])
        self.assertIn("procedibilidad.modo_distinto", hallazgos["B1"][0][1])

    def test_registro(self) -> None:
        self.assertIn("PL-020", REGLAS_COTEJO)
        self.assertNotIn("PL-020", REGLAS)

    def test_sin_paquete_el_lint_no_cambia(self) -> None:
        libro = self.libro()
        self.assertEqual(lint_ledger(libro), lint_ledger(libro, paquete=None, cotejo=None, fidelidad=None))
        self.assertNotIn("PL-020", {h["regla"] for h in lint_ledger(libro)})

    def test_decision_aprobada_ligada_atiende(self) -> None:
        libro = self.libro_alta()
        b1 = self.resultado(libro, "B1")
        libro["decisiones"] = [decision_fidelidad(b1)]
        self.assertNotIn("B1", self.lint(libro))
        # sha256_documento también como texto; una advertencia se atiende igual.
        decision = decision_fidelidad(b1)
        decision["fidelidad"]["senales"][0]["sha256_documento"] = SHA_FIDELIDAD
        libro["decisiones"] = [decision, decision_fidelidad(self.resultado(libro, "B4"), id_="D2")]
        hallazgos = self.lint(libro)
        self.assertNotIn("B1", hallazgos)
        self.assertNotIn("B4", hallazgos)

    def test_plantilla_sin_llenar_no_atiende(self) -> None:
        libro = self.libro_alta()
        b1 = self.resultado(libro, "B1")
        plantilla = F.plantilla_decision(PLAN, b1)
        self.assertEqual(plantilla["fidelidad"]["version_motor"], F.VERSION_MOTOR)
        self.assertEqual(plantilla["fidelidad"]["senales"][0]["huella"], b1.senales[0].huella)
        problemas = " | ".join(F.problemas_decision_fidelidad(
            plantilla, libro["afirmaciones"][0], b1.senales[0], verificada=True, plan=PLAN))
        self.assertIn("responsable no válido", problemas)
        self.assertIn("resolución vacía o pendiente", problemas)
        self.assertIn("no está APROBADA", problemas)

    def test_decision_que_no_atiende(self) -> None:
        libro = self.libro_alta()
        b1, b3 = self.resultado(libro, "B1"), self.resultado(libro, "B3")
        entrada = F.plantilla_decision(PLAN, b1)["fidelidad"]["senales"][0]
        casos = {
            "no_aprobada": (dict(estado="REQUIERE DECISIÓN HUMANA"), "no está APROBADA"),
            "otro_plan": (dict(cambios={"plan": "PLAN-OTRO"}), "declara el plan 'PLAN-OTRO'"),
            "otra_afirmacion": (dict(cambios={"afirmacion": "B2"}), "declara la afirmación 'B2'"),
            "contenido_viejo": (dict(cambios={"contenido_sha256": "0" * 64}), "contenido_sha256 no es el vigente"),
            "motor_viejo": (dict(cambios={"version_motor": "1.0"}), "version_motor '1.0'"),
            "huella_ajena": (dict(cambios={"senales": F.plantilla_decision(PLAN, b3)["fidelidad"]["senales"]}),
                             "no declara la huella vigente"),
            "otro_codigo": (dict(cambios={"senales": [{**entrada, "codigo": "procedibilidad.modo_negado"}]}),
                            "declara el código"),
            "otro_articulo": (dict(cambios={"senales": [{**entrada, "articulo": "2o"}]}),
                              "fuente y el artículo vigentes"),
            "otro_documento": (dict(cambios={"senales": [{**entrada, "sha256_documento": [SHA_CNPP]}]}),
                               "sha256_documento vigente"),
            "sin_resolucion": (dict(resolucion=None), "resolución vacía"),
            "agente": (dict(responsable="Claude"), "responsable no válido"),
        }
        for nombre, (argumentos, motivo) in casos.items():
            with self.subTest(caso=nombre):
                decision = decision_fidelidad(b1, **argumentos)
                problemas = " | ".join(F.problemas_decision_fidelidad(
                    decision, libro["afirmaciones"][0], b1.senales[0], verificada=True, plan=PLAN))
                self.assertIn(motivo, problemas)
                libro["decisiones"] = [decision]
                self.assertEqual([s for s, _ in self.lint(libro)["B1"]], [BLOQUEANTE])

    def test_una_decision_vieja_no_atiende_una_senal_nueva(self) -> None:
        """Revisión externa (ronda 2): la misma afirmación y el mismo código con otro artículo
        u otros tramos (p. ej. la evidencia pasa a otro artículo del mismo PDF) es otra señal."""
        libro = self.libro_alta()
        b1 = self.resultado(libro, "B1")
        decision = decision_fidelidad(b1)
        senal = b1.senales[0]
        afirmacion_ = libro["afirmaciones"][0]
        self.assertEqual(F.problemas_decision_fidelidad(decision, afirmacion_, senal, verificada=True, plan=PLAN), [])
        for cambio in ({"articulo": "2o"}, {"tramo_fuente": EXTRACTO_RECURSO}, {"fuente": "art. 2o (FIDELIDAD.pdf)"}):
            with self.subTest(cambio=cambio):
                nueva = dataclasses.replace(senal, **cambio)
                problemas = F.problemas_decision_fidelidad(decision, afirmacion_, nueva, verificada=True, plan=PLAN)
                self.assertTrue(any("huella vigente" in p for p in problemas), problemas)

    def test_editar_la_afirmacion_invalida_la_decision(self) -> None:
        libro = self.libro_alta()
        libro["decisiones"] = [decision_fidelidad(self.resultado(libro, "B1"))]
        libro["afirmaciones"][0]["texto"] = DE_OFICIO.replace("sintética)", "sintética, versión 2)")  # sigue la señal
        hallazgos = self.lint(libro)
        self.assertEqual([s for s, _ in hallazgos["B1"]], [BLOQUEANTE])
        self.assertIn("contenido_sha256 no es el vigente", hallazgos["B1"][0][1])

    def test_estado_no_verificado_basta_decision_registrada(self) -> None:
        libro = self.libro_alta()
        libro["decisiones"] = [decision_fidelidad(self.resultado(libro, "B2"), estado="REQUIERE DECISIÓN HUMANA",
                                                  resolucion=None)]
        self.assertNotIn("B2", self.lint(libro))


# ── Reporte y CLI ────────────────────────────────────────────────────────────


class ReporteTests(_ConPaquete):
    def test_seccion_de_fidelidad_con_tramos_lado_a_lado(self) -> None:
        libro = self.libro()
        paquete = self.paquete()
        cache: dict = {}
        cotejo = cotejar_ledger(libro, paquete, extractores=EXTRACTORES_FID, cache=cache)
        fidelidad = cotejar_fidelidad(libro, paquete, cotejo=cotejo, extractores=EXTRACTORES_FID, cache=cache)
        hallazgos = lint_ledger(libro, cotejo=cotejo, fidelidad=fidelidad)
        reporte = reporte_markdown(libro, hallazgos, cotejo, fidelidad)
        seccion = reporte.split("## Cotejo de fidelidad")[1].split("## Hallazgos")[0]
        self.assertIn("| La afirmación dice | El texto oficial dice |", seccion)
        self.assertIn("| Precisión |", seccion)
        self.assertIn(TEXTO_INFIEL, seccion)
        self.assertIn("procurar que el culpable no quede impune", seccion)
        self.assertIn("sin decisión que la atienda", seccion)
        self.assertIn("NO_COTEJABLE", seccion)
        self.assertIn("nunca emite CONFORME", seccion)
        self.assertIn(f"SIN_SENALES_DETECTADAS ({F.ETIQUETA_SIN_SENALES})", seccion)
        self.assertIn("| Señales de precisión alta / a revisar | 0 / 3 |", seccion)
        self.assertNotIn("| CONFORME |", seccion)
        self.assertNotIn("Nada fue cotejable", seccion)
        libro["decisiones"] = [decision_fidelidad(fidelidad.afirmaciones[0])]
        cotejo = cotejar_ledger(libro, paquete, extractores=EXTRACTORES_FID, cache=cache)
        fidelidad = cotejar_fidelidad(libro, paquete, cotejo=cotejo, extractores=EXTRACTORES_FID, cache=cache)
        reporte = reporte_markdown(libro, lint_ledger(libro, cotejo=cotejo, fidelidad=fidelidad), cotejo, fidelidad)
        self.assertIn("atendida por D1", reporte)
        self.assertIn(f"Atiende señales de fidelidad de A1 (negacion.polaridad_distinta; motor {F.VERSION_MOTOR}",
                      reporte)
        self.assertNotIn("## Cotejo de fidelidad", reporte_markdown(libro, hallazgos))

    def test_nada_cotejable_se_dice(self) -> None:
        libro = ledger([afirmacion("A4", [], tipo="inferencia", estado="CANDIDATO", texto="Inferencia sintética.",
                                   referencias=["art. 999 CNPP"])], [])
        fidelidad = self.fidelidad(libro)
        reporte = reporte_markdown(libro, lint_ledger(libro, fidelidad=fidelidad), None, fidelidad)
        self.assertIn("**Nada fue cotejable:**", reporte)


class CliFidelidadTests(_ConPaquete):
    def _en_proceso(self, *argumentos: str) -> tuple[int, str, str]:
        salida, errores = io.StringIO(), io.StringIO()
        with patch.object(plan_audit, "_extractores_disponibles", lambda: list(EXTRACTORES_FID)), \
                contextlib.redirect_stdout(salida), contextlib.redirect_stderr(errores):
            codigo = plan_audit.main(list(argumentos))
        return codigo, salida.getvalue(), errores.getvalue()

    def _ledger(self, libro: dict) -> Path:
        ruta = self.base / "ledger.json"
        ruta.write_text(json.dumps(libro, ensure_ascii=False), encoding="utf-8")
        return ruta

    def test_fidelidad_en_texto_y_json(self) -> None:
        ruta = self._ledger(self.libro())
        codigo, salida, _ = self._en_proceso("fidelidad", "--ledger", str(ruta), "--paquete", str(self.raiz))
        self.assertEqual(codigo, 1)
        self.assertIn(f"motor {F.VERSION_MOTOR}", salida)
        self.assertIn("[SENALES] A1 (texto_normativo · VERIFICADO)", salida)
        self.assertIn("[señal a revisar · contradiccion] negacion.polaridad_distinta", salida)
        self.assertIn(f"afirmación: «{TEXTO_INFIEL}»", salida)
        self.assertIn("fuente (art. 2o CNPP · sha256", salida)
        self.assertIn("huella de la señal: ", salida)
        self.assertIn("bloque de decisión para decisiones[]", salida)
        self.assertIn('"version_motor": "2.0"', salida)
        self.assertIn(f"[SIN_SENALES_DETECTADAS ({F.ETIQUETA_SIN_SENALES})] A3", salida)
        self.assertIn("[NO_COTEJABLE] A4", salida)
        self.assertIn("Fuera de alcance (criterio judicial, hecho aportado): A6", salida)
        self.assertIn("Resultado: con señales", salida)
        codigo, salida, _ = self._en_proceso("fidelidad", "--ledger", str(ruta), "--paquete", str(self.raiz), "--json")
        self.assertEqual(codigo, 1)
        datos = json.loads(salida)
        self.assertEqual(datos["esquema"], F.ESQUEMA_FIDELIDAD)
        self.assertEqual(datos["version_motor"], F.VERSION_MOTOR)
        self.assertEqual(datos["resumen"]["SENALES"], 3)
        self.assertNotIn("CONFORME", {r["resultado"] for r in datos["afirmaciones"]})
        senal = datos["afirmaciones"][0]["senales"][0]
        self.assertEqual(senal["tramo_afirmacion"], TEXTO_INFIEL)
        self.assertEqual(senal["precision"], F.REVISAR)
        self.assertEqual(len(senal["huella"]), 64)
        a3 = next(r for r in datos["afirmaciones"] if r["afirmacion"] == "A3")
        self.assertEqual(a3["etiqueta"], f"SIN_SENALES_DETECTADAS ({F.ETIQUETA_SIN_SENALES})")

    def test_sin_senales_nada_cotejable_y_entrada_invalida(self) -> None:
        libro = ledger([afirmacion("A3", ["E1"], texto=TEXTO_FIEL)],
                       [evidencia_ley("E1", "Artículo 2o.", CNPP_ART_2O, "CNPP")])
        ruta = self._ledger(libro)
        codigo, salida, _ = self._en_proceso("fidelidad", "--ledger", str(ruta), "--paquete", str(self.raiz))
        self.assertEqual(codigo, 0)
        self.assertIn(f"Resultado: {F.ETIQUETA_SIN_SENALES} (no equivale a conformidad ni a validación)", salida)
        # Nada cotejable no es "sin señales": sale ≠ 0 (revisión externa, ronda 2).
        ruta = self._ledger(ledger([afirmacion("A4", [], tipo="inferencia", estado="CANDIDATO",
                                               texto="Inferencia sintética.", referencias=["art. 999 CNPP"])], []))
        codigo, salida, _ = self._en_proceso("fidelidad", "--ledger", str(ruta), "--paquete", str(self.raiz))
        self.assertEqual(codigo, 1)
        self.assertIn("Resultado: nada fue cotejable", salida)
        codigo, salida, _ = self._en_proceso("fidelidad", "--ledger", str(ruta), "--paquete", str(self.raiz), "--json")
        self.assertEqual(codigo, 1)
        self.assertTrue(json.loads(salida)["nada_cotejable"])
        codigo, _, errores = self._en_proceso("fidelidad", "--ledger", str(ruta), "--paquete",
                                              str(self.base / "no-existe"))
        self.assertEqual(codigo, 2)
        self.assertIn("paquete de evidencia", errores)

    def test_lint_con_paquete_agrega_pl020_y_la_seccion(self) -> None:
        ruta = self._ledger(self.libro_alta())
        md, js = self.base / "reporte.md", self.base / "hallazgos.json"
        codigo, salida, _ = self._en_proceso("lint", "--ledger", str(ruta), "--paquete", str(self.raiz),
                                             "--md", str(md), "--json", str(js))
        self.assertEqual(codigo, 1)
        self.assertIn("[BLOQUEANTE] PL-020 B1", salida)
        self.assertIn("[ADVERTENCIA] PL-020 B4", salida)
        self.assertIn("Cotejo de fidelidad:", salida)
        self.assertIn("## Cotejo de fidelidad", md.read_text(encoding="utf-8"))
        datos = json.loads(js.read_text(encoding="utf-8"))
        self.assertEqual(datos["fidelidad"]["esquema"], F.ESQUEMA_FIDELIDAD)
        self.assertIn("PL-020", {h["regla"] for h in datos["hallazgos"]})

    def test_ayuda_documenta_el_protocolo(self) -> None:
        for texto in ("Protocolo de uso de la fidelidad", "Nunca emite CONFORME", "version_motor", "huella",
                      F.ETIQUETA_SIN_SENALES.split(";")[0], "nada fue cotejable"):
            with self.subTest(texto=texto):
                self.assertIn(texto, " ".join(plan_audit.__doc__.split()))


# ── Gold Set de fidelidad ────────────────────────────────────────────────────


class GoldSetFidelidadTests(unittest.TestCase):
    def _evaluar(self, datos: dict) -> dict:
        ruta = Path(tempfile.mkdtemp()) / "gold.json"
        self.addCleanup(lambda: ruta.unlink(missing_ok=True))
        ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return evaluar_gold_set(ruta)

    def test_la_puerta_sintetica_pasa(self) -> None:
        reporte = evaluar_gold_set(GOLD_SET)
        self.assertTrue(reporte["gate_passed"], [r for r in reporte["results"] if not r["passed"]])
        self.assertEqual(reporte["version_motor"], F.VERSION_MOTOR)
        for categoria, datos in reporte["recall_por_categoria"].items():
            with self.subTest(categoria=categoria):
                self.assertGreater(datos["casos"], 0)
                self.assertEqual(datos["recall"], 1.0)
        self.assertEqual(set(reporte["recall_precision_alta"]), set(F.CODIGOS_ALTA))
        for codigo, datos in reporte["recall_precision_alta"].items():
            with self.subTest(codigo=codigo):
                self.assertEqual(datos["recall"], 1.0)
        self.assertEqual(reporte["categorias_sin_caso"], [])
        self.assertEqual(reporte["codigos_alta_sin_caso"], [])
        self.assertEqual(reporte["bloqueantes_no_esperados"], [])
        self.assertGreater(reporte["controles"], 0)
        self.assertEqual(reporte["controles_con_senales"], [])
        self.assertEqual(reporte["literalidad"]["problemas"], [])

    def test_limites_documentados_no_son_puerta(self) -> None:
        reporte = evaluar_gold_set(GOLD_SET)
        self.assertEqual({l["id"] for l in reporte["limites_documentados"]}, {"LIM-01", "LIM-02", "LIM-03"})
        datos = gold()
        caso = next(c for c in datos["cases"] if c["id"] == "LIM-01")
        caso["limite_documentado"] = False  # convertido en puerta, el falso negativo la rompe
        self.assertFalse(self._evaluar(datos)["gate_passed"])

    def test_candidatos_del_piloto_son_pendientes_y_no_son_puerta(self) -> None:
        candidatos = gold()["candidatos_piloto"]["candidatos"]
        self.assertEqual(len(candidatos), 22)
        self.assertEqual({c["review_status"] for c in candidatos}, {"pendiente_responsable"})
        reporte = evaluar_gold_set(GOLD_SET)
        metricas = reporte["candidatos_pendientes"]["metricas"]
        self.assertEqual(metricas["total"], 22)
        self.assertEqual((metricas["falsos_positivos"], metricas["falsos_positivos_alta"]), (0, 0))
        self.assertEqual(reporte["candidatos_aprobados"]["metricas"]["total"], 0)

    def test_tramos_de_las_senales_son_literales(self) -> None:
        datos = gold()
        for caso in datos["cases"]:
            afirmacion_, fuentes = caso_gold(datos, caso["id"])
            for senal in F.comparar(afirmacion_, fuentes):
                with self.subTest(caso=caso["id"], codigo=senal.codigo):
                    self.assertIn(senal.tramo_afirmacion, afirmacion_)
                    if senal.tramo_fuente:
                        self.assertTrue(any(senal.tramo_fuente in f.texto for f in fuentes))

    def test_texto_editado_control_con_senales_o_alta_inesperada_falla(self) -> None:
        datos = gold()
        editado = copy.deepcopy(datos)
        clave = next(k for k, v in editado["fuentes"].items() if v["origen"] == "fixture")
        editado["fuentes"][clave]["texto"] += " (editado)"
        reporte = self._evaluar(editado)
        self.assertFalse(reporte["gate_passed"])
        self.assertTrue(any(clave in p for p in reporte["literalidad"]["problemas"]))
        roto = copy.deepcopy(datos)
        control = next(c for c in roto["cases"] if c["categoria"] == "control_fiel")
        defecto = next(c for c in roto["cases"] if c["categoria"] == "negacion")
        control["afirmacion"], control["fuentes"] = defecto["afirmacion"], defecto["fuentes"]
        self.assertFalse(self._evaluar(roto)["gate_passed"])
        # Un caso que espera "revisar" y recibe una señal alta rompe la puerta (falso bloqueante).
        alta = copy.deepcopy(datos)
        origen = next(c for c in alta["cases"] if c["id"] == "ADV-COORD-01")
        destino = next(c for c in alta["cases"] if c["id"] == "ADV-COORD-02")
        destino["afirmacion"] = origen["afirmacion"]
        reporte = self._evaluar(alta)
        self.assertFalse(reporte["gate_passed"])
        self.assertTrue(reporte["bloqueantes_no_esperados"])

    def test_candidato_aprobado_entra_en_la_puerta_con_la_verdad_del_responsable(self) -> None:
        datos = gold()
        reporte = evaluar_gold_set(GOLD_SET)
        no_detectado = next(r["id"] for r in reporte["candidatos_pendientes"]["resultados"]
                            if r["propuesta_operador"] == "cambia" and not r["senales"])
        candidato = next(c for c in datos["candidatos_piloto"]["candidatos"] if c["id"] == no_detectado)
        propuesta = candidato["propuesta_operador"]
        candidato["review_status"] = "aprobado_responsable"
        candidato["verdad_responsable"] = "cambia"  # no se detecta: la puerta debe fallar
        reporte = self._evaluar(datos)
        self.assertFalse(reporte["gate_passed"])
        self.assertEqual(reporte["candidatos_aprobados"]["fallan"], [no_detectado])
        self.assertEqual(candidato["propuesta_operador"], propuesta)  # nunca se reescribe

    def test_dataset_invalido(self) -> None:
        datos = gold()
        alta = next(i for i, c in enumerate(datos["cases"])
                    if any(e.get("precision") == "alta" for e in c["esperado"]))
        sintetica = next(k for k, v in datos["fuentes"].items() if v["origen"] == "sintetico_adversarial")
        for cambio in (
            lambda d: d.update(schema_version="otra"),
            lambda d: d["cases"][0].update(review_status="operator_curated"),
            lambda d: d["cases"][0].update(fuentes=["NO-EXISTE"]),
            lambda d: d["cases"][0].update(esperado=[]),
            lambda d: d["cases"][alta]["esperado"][0].pop("codigo"),
            lambda d: d["cases"][alta]["esperado"][0].update(precision="media"),
            lambda d: d["fuentes"][sintetica].update(rotulo="texto de prueba"),
            lambda d: d["candidatos_piloto"]["candidatos"][0].update(review_status="aprobado_responsable"),
        ):
            copia = copy.deepcopy(datos)
            cambio(copia)
            with self.assertRaises(FidelidadGoldSetInvalido):
                validar_dataset(copia)

    def test_fuentes_de_fixture_son_subcadena_exacta(self) -> None:
        for clave, fuente_ in gold()["fuentes"].items():
            if fuente_["origen"] != "fixture":
                continue
            with self.subTest(fuente=clave):
                paginas = json.loads((REPO / fuente_["archivo"]).read_text(encoding="utf-8"))["paginas"]
                pagina_ = next(p["texto"] for p in paginas if p["numero"] == fuente_["pagina"])
                self.assertIn(fuente_["texto"], pagina_)
        self.assertTrue((FIXTURES / "manifiesto.json").is_file())


if __name__ == "__main__":
    unittest.main()
