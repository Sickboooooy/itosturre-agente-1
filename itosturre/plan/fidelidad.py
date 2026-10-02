"""Cotejo de fidelidad determinista (C10, PR-4): ¿lo que AFIRMA el plan es lo que DICE la fuente?

La identidad (``identidad.py``, C9) ya garantiza **qué** documento, **qué** versión y
**qué** artículo respaldan una afirmación. Este módulo compara después el texto de la
afirmación con el texto oficial de ese artículo y emite **señales** deterministas por
categoría. **Nunca emite CONFORME ni valida**: el mejor resultado posible es
``SIN_SENALES_DETECTADAS``, que se rotula siempre como "sin señales detectadas por reglas
deterministas; revisión del abogado obligatoria" (``ETIQUETA_SIN_SENALES``). Tampoco
aprueba ni cambia estados del ledger (D3).

Alcance: afirmaciones ``texto_normativo``, ``inferencia`` y ``propuesta`` (las demás
quedan fuera de alcance; una ``INEXISTENTE`` es NO_COTEJABLE). Texto oficial:

1. el de sus pares **CONFORME** de ley en el cotejo de identidad (artículo ubicado, texto
   completo entre su encabezado y el siguiente, como ``tramo_articulo``), o
2. si no tiene ninguno, el de sus ``referencias`` resueltas contra el paquete con el
   mismo rigor que la identidad (piloto PEN-01: las propuestas e inferencias suelen no
   citar evidencia): mención "art. N SIGLA" con ley, una sola ley del paquete con ese
   ordenamiento (archivo **y** título del encabezado, ``ordenamiento_de``), pasos a–c de
   la identidad (integridad y relación original–texto) y artículo único en el cuerpo. Lo
   que no se resuelve no se supone: la afirmación queda ``NO_COTEJABLE`` con su motivo, o
   con fuentes parciales (nota visible).

**Política de precisión** (ronda 2, criterio por defecto fijado por el coordinador; el
responsable jurídico puede endurecerlo). Un motor sin análisis sintáctico tiene falsos
negativos y falsos positivos estructurales; por eso cada código tiene una precisión fija
(``CODIGOS``) y solo tres son de precisión ``alta`` (en una afirmación VERIFICADO bloquean,
PL-020):

- ``procedibilidad.modo_distinto``: el modo de la afirmación (querella, denuncia, de oficio,
  declaratoria, petición de parte) no está entre los que el artículo prevé explícitamente
  (artículo no truncado);
- ``plazos_cifras.distinto_misma_condicion``: un plazo (unidad de tiempo; número, unidad,
  calificador o rango) distinto del que la oración alineada fija para la **misma
  condición**: cada cifra se liga a su condición ("si se tratare de auto", "contra las
  resoluciones del Juez de control", "tratándose de…", "en los casos de…", un paréntesis
  tras la cifra) y se exige que compartan al menos ``MINIMO_CONDICION`` raíces;
- ``inicio_computo.distinto``: el inicio del cómputo difiere del de **todas** las oraciones
  candidatas que traen la misma cifra (o, sin cifra, de todas las candidatas).

Todo lo demás —modales, negación, cuantificadores, excepciones y condiciones, órgano,
cifras sin condición, montos (UMA, pesos, salario mínimo, días multa), cifra ausente y
todas las omisiones— es de precisión ``revisar``: ADVERTENCIA "señal a revisar" en
cualquier estado. Si la elección de la oración alineada cambia el resultado (rival con
puntaje cercano o con órgano distinto), el motor se abstiene y emite
``alineacion.ambigua`` (revisar); nunca una señal alta sale de una alineación ambigua.

Unidad de comparación: la afirmación se divide en cláusulas (``;`` y fin de oración) y el
artículo en oraciones (sin las notas de reforma de LeyesBiblio, ``reformas.extraer_notas``).
Cada cláusula se alinea con la oración del artículo que más raíces de contenido comparte
(cobertura: fracción de las raíces de la cláusula presentes en la oración, con el coseno
como desempate, ``PESO_COSENO``; mínimo dos raíces y ``UMBRAL_ALINEACION``); si la cláusula
nombra un órgano (juez, Ministerio Público…), solo compiten las oraciones compatibles. Las
palabras del inicio del cómputo no deciden la alineación; la cifra con su unidad sí cuenta
como una raíz, y una cifra que solo aparece en una oración la alinea por sí misma. Las
cláusulas de la afirmación que se alinean con la misma oración son hermanas: lo que dice
una no se señala como omitido en la otra.

Categorías (listas cerradas en este módulo; ampliarlas es decisión del responsable):

- **Procedibilidad** (por artículo): modo distinto (alta); modo negado que el artículo
  prevé; habla de persecución o procedencia sin el requisito que el artículo impone;
  requisito de la SHCP sin nombrarla.
- **Plazos y cifras**: número + unidad de tiempo (días, horas, meses, años, semanas) con
  calificador hábiles/naturales ("de calendario" = naturales), montos (UMA, pesos, "$",
  salario mínimo, días multa, días de salario), dígitos con separador de miles ("1,000")
  o palabras ("ciento ochenta"), rangos comparados como par ("de 3 a 9 años") y
  alternativas ("3 o 5 días").
- **Inicio del cómputo**: surta efectos la notificación, la notificación, de momento a
  momento, la publicación, la entrada en vigor (y el día siguiente), el conocimiento y
  "siguientes a / a partir de" + suceso.
- **Modales**: deber / facultad / prohibición ("no podrá", "no le está permitido", "le
  está prohibido", "ninguno … podrá") y el mandato implícito del futuro ("se interpondrá",
  "ordenará") frente a "podrá interponerse" / "podrá ordenar".
- **Negación**: la polaridad de cada predicado se lee en la cadena que lo precede
  (negadores, prohibitivos, clíticos, auxiliares; paridad: "no podrá no admitir" es
  afirmativo) y se compara con la ocurrencia del mismo verbo cuyo complemento más se
  parece (reordenar o separar cláusulas no cambia el emparejamiento).
- **Excepciones y condiciones**: presentes en la oración alineada y ausentes en la cláusula
  (omisión), o excepción con contenido distinto (las palabras tras "salvo/excepto" no se
  solapan).
- **Cuantificadores**: universal, negativo y exclusivo; añadido u omitido.
- **Sujeto**: familias de órgano disjuntas (jurisdiccional, Ministerio Público, defensor,
  policía).

Equivalencia lógica (piloto PEN-01, CPEUM 1o.): "no podrá … salvo/sino …" en un lado y
"solo/únicamente …" en el otro no generan señales de negación, cuantificador, excepción
ni modal entre esa cláusula y esa oración.

Fuente truncada (el artículo puede continuar en páginas no recibidas): es fuente
incompleta; no se emiten señales que dependan de una ausencia en ella (cifra ausente,
modo distinto, cifras o marcas que faltan en su última oración).

Cada señal trae una ``huella`` (código, fuente, artículo, documentos y tramos literales):
la decisión humana que la atiende la declara junto con el plan, la afirmación, su
``contenido_sha256`` y ``VERSION_MOTOR``; si cambia cualquiera, deja de valer.

Limitaciones conocidas (fijadas por prueba): no hay análisis sintáctico; la
procedibilidad se lee por artículo y no por delito; las enumeraciones incompletas y las
generalizaciones de contenido no se detectan; el órgano solo se compara entre familias
cerradas; el texto entre corchetes que la fuente declara inválido se coteja como texto.

Puro: sin red, reloj ni E/S propia. Lee el paquete solo a través de ``identidad``.
"""
from __future__ import annotations

import bisect
import math
import re
import unicodedata
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence

from ..evidencia.esquema import TIPO_LEY_LEYESBIBLIO, es_marcador_pendiente
from ..evidencia.huellas import json_canonico, sha256_texto
from ..evidencia.leyesbiblio import CoincidenciaArticulo, DocumentoLeyesBiblio, ubicar_articulo
from ..evidencia.reformas import extraer_notas
from .estados import (
    APROBADO,
    INEXISTENTE,
    VERIFICADO,
    contenido_sha256,
    normalizar_estado,
    problema_persona,
)
from .identidad import (
    CONFORME,
    CotejoLedger,
    Extractor,
    clave_articulo,
    consultar_articulo,
    cotejar_ledger,
    huella_ledger,
    ley_registrada,
    ordenamiento_de,
    tramo_articulo,
)
from .ledger import LedgerInvalido, validar_esquema
from .menciones import ARTICULO, RANGO, extraer_menciones

# Versión de las reglas: una decisión humana se liga a ella (si las reglas cambian, las
# señales pueden cambiar y la decisión deja de valer).
VERSION_MOTOR = "2.0"
ESQUEMA_FIDELIDAD = f"fidelidad-determinista/{VERSION_MOTOR}"

SENALES = "SENALES"
SIN_SENALES_DETECTADAS = "SIN_SENALES_DETECTADAS"
NO_COTEJABLE = "NO_COTEJABLE"
RESULTADOS = (SENALES, SIN_SENALES_DETECTADAS, NO_COTEJABLE)

CONTRADICCION = "contradiccion"
OMISION = "omision"
INDETERMINADA = "indeterminada"  # alineación ambigua: no se sabe qué oración parafrasea
SEVERIDADES = (CONTRADICCION, OMISION, INDETERMINADA)

ALTA = "alta"  # bloquea en VERIFICADO (PL-020)
REVISAR = "revisar"  # ADVERTENCIA "señal a revisar" en cualquier estado
PRECISIONES = (ALTA, REVISAR)

TIPOS_COTEJABLES = ("texto_normativo", "inferencia", "propuesta")

PROCEDIBILIDAD = "procedibilidad"
PLAZOS = "plazos_cifras"
INICIO_COMPUTO = "inicio_computo"
MODAL = "modal"
NEGACION = "negacion"
EXCEPCION_CONDICION = "excepcion_condicion"
CUANTIFICADOR = "cuantificador"
SUJETO = "sujeto"
ALINEACION = "alineacion"  # meta: no es una categoría de defecto
CATEGORIAS = (PROCEDIBILIDAD, PLAZOS, INICIO_COMPUTO, MODAL, NEGACION, EXCEPCION_CONDICION, CUANTIFICADOR, SUJETO)

# Código → (categoría, severidad, precisión, descripción). Lista cerrada.
CODIGOS = MappingProxyType({
    "procedibilidad.modo_distinto": (PROCEDIBILIDAD, CONTRADICCION, ALTA,
                                     "modo de procedibilidad que el artículo no prevé (prevé otro, explícito)"),
    "procedibilidad.modo_negado": (PROCEDIBILIDAD, CONTRADICCION, REVISAR,
                                   "niega un modo de procedibilidad que el artículo prevé"),
    "procedibilidad.requisito_omitido": (PROCEDIBILIDAD, OMISION, REVISAR,
                                         "habla de persecución o procedencia y omite el requisito que el artículo impone"),
    "procedibilidad.shcp_omitida": (PROCEDIBILIDAD, OMISION, REVISAR, "omite que el requisito corresponde a la SHCP"),
    "plazos_cifras.distinto_misma_condicion": (PLAZOS, CONTRADICCION, ALTA,
                                               "plazo distinto del que la fuente fija para la misma condición"),
    "plazos_cifras.numero_distinto": (PLAZOS, CONTRADICCION, REVISAR, "número distinto del de la oración alineada"),
    "plazos_cifras.unidad_distinta": (PLAZOS, CONTRADICCION, REVISAR, "unidad distinta de la de la oración alineada"),
    "plazos_cifras.calificador_distinto": (PLAZOS, CONTRADICCION, REVISAR, "hábiles frente a naturales"),
    "plazos_cifras.rango_distinto": (PLAZOS, CONTRADICCION, REVISAR, "rango distinto del de la oración alineada"),
    "plazos_cifras.cifra_ausente": (PLAZOS, CONTRADICCION, REVISAR, "cifra que no aparece en el texto oficial"),
    "inicio_computo.distinto": (INICIO_COMPUTO, CONTRADICCION, ALTA, "inicio del cómputo distinto del de la fuente"),
    "inicio_computo.omitido": (INICIO_COMPUTO, OMISION, REVISAR, "plazo sin el inicio del cómputo que la fuente fija"),
    "modal.atenuacion": (MODAL, CONTRADICCION, REVISAR, "deber o mandato de la fuente expresado como facultad"),
    "modal.refuerzo": (MODAL, CONTRADICCION, REVISAR, "facultad de la fuente expresada como deber o mandato"),
    "modal.cambio": (MODAL, CONTRADICCION, REVISAR, "prohibición frente a deber o facultad (polaridad invertida)"),
    "negacion.polaridad_distinta": (NEGACION, CONTRADICCION, REVISAR, "el mismo predicado con polaridad distinta"),
    "excepcion_condicion.excepcion_omitida": (EXCEPCION_CONDICION, OMISION, REVISAR, "excepción de la fuente omitida"),
    "excepcion_condicion.condicion_omitida": (EXCEPCION_CONDICION, OMISION, REVISAR, "condición de la fuente omitida"),
    "excepcion_condicion.excepcion_distinta": (EXCEPCION_CONDICION, CONTRADICCION, REVISAR,
                                               "excepción con contenido distinto del de la fuente"),
    "cuantificador.anadido": (CUANTIFICADOR, CONTRADICCION, REVISAR, "cuantificador que la oración fuente no tiene"),
    "cuantificador.omitido": (CUANTIFICADOR, OMISION, REVISAR, "cuantificador negativo o exclusivo omitido"),
    "sujeto.organo_distinto": (SUJETO, CONTRADICCION, REVISAR, "órgano o sujeto de otra familia que el de la fuente"),
    "alineacion.ambigua": (ALINEACION, INDETERMINADA, REVISAR,
                           "la oración que parafrasea la afirmación es ambigua y cambia el resultado: revisar"),
})
CODIGOS_ALTA = frozenset(codigo for codigo, datos in CODIGOS.items() if datos[2] == ALTA)

ETIQUETA_SIN_SENALES = "sin señales detectadas por reglas deterministas; revisión del abogado obligatoria"
AVISO = (
    f"SIN_SENALES_DETECTADAS = {ETIQUETA_SIN_SENALES}. Nunca es CONFORME ni una validación: las reglas "
    "deterministas (listas cerradas) no sustituyen la lectura del abogado."
)

# Llave opcional de una decisión del ledger (el esquema 1.0 la ignora) con la que una
# persona atiende las señales de fidelidad de una afirmación (PL-020).
CAMPO_DECISION_FIDELIDAD = "fidelidad"

UMBRAL_ALINEACION = 0.25  # cobertura mínima: fracción de raíces de la cláusula en la oración
PESO_COSENO = 0.1  # desempate por coseno
MINIMO_RAICES_COMUNES = 2  # cifras e inicio del cómputo
MINIMO_RAICES_SECUNDARIAS = 3  # modal, negación, excepciones, cuantificadores, sujeto
FRACCION_CANDIDATAS = 0.75
FRACCION_RIVAL = 0.9  # rival con puntaje cercano: si cambia el resultado, alineación ambigua
MINIMO_CONDICION = 2  # raíces comunes para ligar una cifra a la misma condición
# Palabras tras la cifra en las que puede empezar su condición posterior ("tres días contados
# a partir de aquel en el que surta efectos la notificación si se tratare de auto"), siempre
# antes de la cifra siguiente.
VENTANA_CONDICION_POSTERIOR = 16
VENTANA_CONTENIDO = 6
MAXIMO_TRAMO = 360


# ── Listas cerradas de términos (normalizados: minúsculas, sin acentos) ─────────
# Ampliarlas es decisión del responsable jurídico; cada cambio debe entrar con su caso
# en el Gold Set de fidelidad.

QUERELLA = "querella"
DENUNCIA = "denuncia"
DE_OFICIO = "de_oficio"
DECLARATORIA = "declaratoria"
PETICION_DE_PARTE = "peticion_de_parte"
MODOS_PROCEDIBILIDAD = MappingProxyType({
    QUERELLA: ("querella", "querellas"),
    DENUNCIA: ("denuncia", "denuncias"),
    DE_OFICIO: ("de oficio",),
    DECLARATORIA: ("declaratoria", "declaratorias", "declare que el fisco"),
    PETICION_DE_PARTE: ("a peticion de parte", "a instancia de parte"),
})
MODOS_REQUISITO = frozenset({QUERELLA, DECLARATORIA, PETICION_DE_PARTE})
# Contexto de persecución o procedencia. "oficiosamente" (prisión preventiva oficiosa) NO
# es un modo de procedibilidad.
PREFIJOS_CONTEXTO = ("persegu", "persig", "persecuci", "procedibilidad")
FRASES_CONTEXTO = (
    "proceder penalmente", "procedera penalmente", "procedencia por", "procedencia penal",
    "accion penal", "se procede por", "se procedera por",
)
FRASES_SHCP = ("secretaria de hacienda y credito publico", "shcp", "hacienda")

UNIDADES_TIEMPO = MappingProxyType({
    "dia": "dias", "dias": "dias", "hora": "horas", "horas": "horas", "mes": "meses",
    "meses": "meses", "ano": "anos", "anos": "anos", "semana": "semanas", "semanas": "semanas",
})
TEMPORALES = frozenset({"dias", "horas", "meses", "anos", "semanas"})
CALIFICADORES = MappingProxyType({"habil": "habiles", "habiles": "habiles", "natural": "naturales",
                                  "naturales": "naturales"})
CONECTORES_RANGO = frozenset({"a", "al", "hasta"})
CONECTORES_ALTERNATIVA = frozenset({"o", "u", "y", "e"})
_UNIDADES_NUM = {"cero": 0, "un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4,
                 "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9}
_ESPECIALES_NUM = {"diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
                   "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19, "veinte": 20,
                   "veintiun": 21, "veintiuno": 21, "veintiuna": 21, "veintidos": 22, "veintitres": 23,
                   "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26, "veintisiete": 27,
                   "veintiocho": 28, "veintinueve": 29}
_DECENAS_NUM = {"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70,
                "ochenta": 80, "noventa": 90}
_CENTENAS_NUM = {"cien": 100, "ciento": 100, "doscientos": 200, "doscientas": 200, "trescientos": 300,
                 "trescientas": 300, "cuatrocientos": 400, "cuatrocientas": 400, "quinientos": 500,
                 "quinientas": 500, "seiscientos": 600, "seiscientas": 600, "setecientos": 700,
                 "setecientas": 700, "ochocientos": 800, "ochocientas": 800, "novecientos": 900,
                 "novecientas": 900}

# Condición a la que se liga una cifra: marcadores previos (valen para las cifras que
# siguen) y posteriores (la cifra inmediatamente anterior); también un paréntesis tras ella.
MARCADORES_CONDICION_PREVIA = (
    "contra", "en contra de", "tratandose de", "en los casos de", "en el caso de", "en caso de",
    "si se tratare de", "si se trata de", "cuando se trate de",
)
MARCADORES_CONDICION_POSTERIOR = (
    "si se tratare de", "si se trata de", "tratandose de", "cuando se trate de", "en el caso de",
    "en los casos de",
)

SURTE_EFECTOS = "surte_efectos_notificacion"
NOTIFICACION = "notificacion"
MOMENTO_A_MOMENTO = "momento_a_momento"
PUBLICACION = "publicacion"
ENTRADA_EN_VIGOR = "entrada_en_vigor"
DIA_SIGUIENTE_VIGOR = "dia_siguiente_entrada_en_vigor"
CONOCIMIENTO = "conocimiento"
ANCLAS = MappingProxyType({
    SURTE_EFECTOS: (
        "surta efectos la notificacion", "surte efectos la notificacion", "surtan efectos la notificacion",
        "surten efectos la notificacion", "surta sus efectos la notificacion", "surte sus efectos la notificacion",
        "surta efectos su notificacion", "surte efectos su notificacion",
    ),
    NOTIFICACION: (
        "siguientes a la notificacion", "siguiente a la notificacion", "siguientes a su notificacion",
        "siguiente a su notificacion", "a partir de la notificacion", "a partir de su notificacion",
        "desde la notificacion", "desde su notificacion", "desde que se notifique", "desde que se le notifique",
        "a partir de que se notifique", "a partir de que se le notifique",
    ),
    MOMENTO_A_MOMENTO: ("de momento a momento",),
    PUBLICACION: (
        "siguiente al de su publicacion", "siguiente al de la publicacion", "siguiente de su publicacion",
        "a partir de su publicacion", "a partir de la publicacion", "desde su publicacion",
        "siguientes a su publicacion", "siguientes a la publicacion",
    ),
    DIA_SIGUIENTE_VIGOR: (
        "dia siguiente de la entrada en vigor", "dia siguiente a la entrada en vigor",
        "dia siguiente al de la entrada en vigor",
    ),
    ENTRADA_EN_VIGOR: (
        "a partir de la entrada en vigor", "desde la entrada en vigor", "siguiente de la entrada en vigor",
        "siguiente a la entrada en vigor", "siguientes a la entrada en vigor",
    ),
    CONOCIMIENTO: (
        "a partir de que tenga conocimiento", "desde que tenga conocimiento", "a partir de que se tenga conocimiento",
        "desde que se tuvo conocimiento", "a partir del conocimiento", "desde el conocimiento",
    ),
})
# Ancla genérica: "siguientes a(l)", "a partir de(l)", "contados desde" + suceso.
_ARRANQUES_ANCLA = (("siguientes", "a"), ("siguientes", "al"), ("siguiente", "a"), ("siguiente", "al"),
                    ("a", "partir", "de"), ("a", "partir", "del"), ("contados", "desde"), ("contado", "desde"))
_DETERMINANTES = frozenset({"el", "la", "los", "las", "su", "sus", "que", "de", "del"})

DEBER = "deber"
FACULTAD = "facultad"
PROHIBICION = "prohibicion"
MODALES = MappingProxyType({
    DEBER: (
        "debera", "deberan", "debe", "deben", "esta obligado", "esta obligada", "estan obligados",
        "estan obligadas", "estara obligado", "estaran obligados", "queda obligado", "quedan obligados",
        "tendra que", "tendran que", "tiene que", "tienen que", "tiene la obligacion", "tienen la obligacion",
        "es obligatorio", "es obligatoria", "sera obligatorio", "sera obligatoria", "son obligatorios",
        "son obligatorias", "seran obligatorios", "seran obligatorias", "obliga", "obligan",
    ),
    FACULTAD: (
        "podra", "podran", "puede", "pueden", "es potestativo", "es potestativa", "esta facultado",
        "esta facultada", "estan facultados", "esta permitido", "esta permitida", "estan permitidos",
        "estan permitidas", "es permitido",
    ),
    PROHIBICION: (
        "se prohibe", "se prohiben", "queda prohibido", "queda prohibida", "quedan prohibidos",
        "quedan prohibidas", "esta prohibido", "esta prohibida", "estan prohibidos", "estan prohibidas",
        "quedando prohibido", "quedando prohibida", "prohibido", "prohibida",
    ),
})
NEGADORES = frozenset({"no", "ni", "nunca", "jamas", "tampoco"})
_NO_NEGACION = (("no", "obstante"), ("no", "solo"), ("no", "solamente"), ("ni", "siquiera"))
_CLITICOS = frozenset({"se", "le", "les", "lo", "me", "nos", "te"})
_AUXILIARES = frozenset({
    "podra", "podran", "puede", "pueden", "podria", "podrian", "debera", "deberan", "debe", "deben",
    "deberia", "sera", "seran", "es", "son", "ha", "han", "habra", "habran", "hubiere", "hubieren",
    "haya", "hayan", "ser", "estar", "esta", "estan", "estara", "estaran", "fue", "fueron", "sea", "sean",
    "queda", "quedan", "quedando",
})
# Participios de permiso u obligación que forman perífrasis ("no le está permitido admitir").
_PERMISIVOS = frozenset({
    "permitido", "permitida", "permitidos", "permitidas", "autorizado", "autorizada", "autorizados",
    "autorizadas", "facultado", "facultada", "facultados", "facultadas", "obligado", "obligada",
    "obligados", "obligadas",
})
# Prohibitivos: invierten la polaridad del predicado que sigue ("le está prohibido admitir").
_PROHIBITIVOS = frozenset({"prohibido", "prohibida", "prohibidos", "prohibidas", "prohibe", "prohiben"})
_CADENA = _CLITICOS | _AUXILIARES | _PERMISIVOS | _PROHIBITIVOS
# Terminaciones verbales. Sin "-o" ni "-s": "cómputo", "días" o "restricciones" no cuentan.
_TERMINACIONES_VERBALES = (
    "arse", "erse", "irse", "aran", "eran", "iran", "aria", "eria", "iria", "ando", "iendo",
    "ado", "ada", "ido", "ida", "ara", "era", "ira", "an", "en", "ar", "er", "ir", "a", "e",
)
_TERMINACIONES_INFINITIVO = ("arse", "erse", "irse", "ar", "er", "ir")
# Futuro de indicativo como mandato implícito ("se interpondrá", "ordenará").
_TERMINACIONES_FUTURO = ("aran", "eran", "iran", "dran", "ara", "era", "ira", "dra")
_NO_FUTUROS = frozenset({
    "podra", "podran", "debera", "deberan", "sera", "seran", "habra", "habran", "tendra", "tendran",
    "estara", "estaran", "hara", "haran", "primera", "manera", "carrera", "cualquiera", "frontera", "tercera",
    "postrera", "madera", "esfera", "bandera", "mientras",
})

EXCEPCION = "excepcion"
CONDICION = "condicion"
MARCAS = MappingProxyType({
    EXCEPCION: ("salvo", "excepto", "con excepcion de", "a excepcion de", "con la salvedad", "exceptuando",
                "fuera de los casos", "a menos que", "sino"),
    CONDICION: ("siempre que", "siempre y cuando", "cuando", "en caso de que", "en el caso de que",
                "a condicion de que", "con tal de que"),
})

UNIVERSAL = "universal"
NEGATIVO = "negativo"
EXCLUSIVO = "exclusivo"
CUANTIFICADORES = MappingProxyType({
    UNIVERSAL: ("todo", "toda", "todos", "todas", "siempre", "en todos los casos"),
    NEGATIVO: ("ningun", "ninguna", "ninguno", "nadie", "nunca", "jamas", "en ningun caso"),
    EXCLUSIVO: ("solo", "solamente", "unicamente", "exclusivamente"),
})
_NO_CUANTIFICADOR_DESPUES = {"siempre": ("que", "y"), "todo": ("caso",)}
_NO_CUANTIFICADOR_ANTES = {"todo": ("sobre", "con", "del"), "solo": ("este", "ese", "aquel", "un", "el", "su", "si")}

# Familias de órgano o sujeto que nunca son sinónimos entre sí. "fiscal" solo cuenta como
# Ministerio Público tras un determinante ("el fiscal"): "crédito fiscal" o "autoridad
# fiscal" no lo son.
ORGANOS = MappingProxyType({
    "jurisdiccional": ("juez", "jueza", "jueces", "juezas", "juzgador", "juzgadora", "persona juzgadora",
                       "tribunal", "tribunales", "organo jurisdiccional", "autoridad judicial", "magistrado",
                       "magistrada", "magistrados", "magistradas"),
    "ministerio_publico": ("ministerio publico", "fiscal", "fiscales", "fiscalia", "mp"),
    "defensor": ("defensor", "defensora", "defensores", "defensoras", "defensoria"),
    "policia": ("policia", "policias"),
})
_DETERMINANTES_ORGANO = frozenset({"el", "la", "los", "las", "al", "del", "un", "una"})

# Siglas que se expanden para comparar contenidos (excepciones y condiciones).
EXPANSIONES = MappingProxyType({
    "scjn": "suprema corte justicia nacion",
    "shcp": "secretaria hacienda credito publico",
    "mp": "ministerio publico",
    "ppo": "prision preventiva oficiosa",
    "sat": "servicio administracion tributaria",
})

_STOPWORDS = frozenset("""
el la los las lo un una unos unas al del de a ante bajo con contra desde durante en entre hacia hasta
mediante para por segun sin sobre tras y e o u ni que se su sus le les me nos te mi tu este esta estos
estas ese esa esos esas aquel aquella aquellos aquellas dicho dicha dichos dichas mismo misma mismos mismas
cual cuales cuyo cuya cuyos cuyas quien quienes donde como cuando cuanto muy mas menos tambien asi ya aun
es son sera seran ser sea sean fue fueron ha han haya hayan hubiere hubieren habra habran estar esta estan
estara estaran otro otra otros otras cada no si sino pero porque pues art arts articulo articulos parr
parrafo parrafos fraccion fracciones fr inciso incisos presente caso casos demas respectivo respectiva
respectivos respectivas termino terminos dispuesto conformidad lugar forma manera materia codigo ley leyes
cpeum cnpp cpf cff lamp lnep lnmascmp lfdo lfcdo lgs cadh dof tal tales dentro aquello ello ellos ellas
podra podran puede pueden debera deberan debe deben solo solamente unicamente exclusivamente siempre
nunca jamas salvo excepto todo toda todos todas ningun ninguna ninguno previsto prevista previstos previstas
""".split())
_CONJUNCIONES = frozenset({"y", "e", "o", "u", "ni", "pero", "sino", "que"})


# ── Texto normalizado con correspondencia al original ──────────────────────────


@dataclass(frozen=True)
class _Token:
    palabra: str
    ini: int  # posiciones en el texto normalizado
    fin: int


# Cifras con separador de miles y decimales ("1,000", "$2,531,920.00") son un solo token.
_TOKEN_RE = re.compile(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![a-z0-9])|\d+\.\d+(?![a-z0-9])|[a-z0-9]+")


class _Texto:
    """Texto original y su forma normalizada (minúsculas, sin acentos), carácter a carácter.

    ``literal(ini, fin)`` devuelve la subcadena **original** que corresponde a un tramo
    del texto normalizado: los tramos que se muestran nunca se reescriben.
    """

    def __init__(self, original: str) -> None:
        self.original = original
        caracteres: list[str] = []
        mapa: list[int] = []
        for indice, caracter in enumerate(original):
            if caracter in "º°":
                caracter = "o"
            for parte in unicodedata.normalize("NFD", caracter):
                if unicodedata.category(parte) == "Mn":
                    continue
                for minuscula in parte.lower():
                    caracteres.append(minuscula)
                    mapa.append(indice)
        self.norm = "".join(caracteres)
        self.mapa = mapa
        # Inversa: posición del original → primera posición normalizada que le corresponde
        # (o la del siguiente carácter, si este no produjo ninguna: una marca diacrítica suelta).
        inversa = [len(self.norm)] * (len(original) + 1)
        con_posicion = [False] * (len(original) + 1)
        for posicion in range(len(mapa) - 1, -1, -1):
            inversa[mapa[posicion]] = posicion
            con_posicion[mapa[posicion]] = True
        for indice in range(len(original) - 1, -1, -1):
            if not con_posicion[indice]:
                inversa[indice] = inversa[indice + 1]
        self.inversa = inversa
        self.tokens = [_Token(m.group().replace(",", ""), m.start(), m.end()) for m in _TOKEN_RE.finditer(self.norm)]
        self._inicios = [t.ini for t in self.tokens]

    def literal(self, ini: int, fin: int) -> str:
        if ini >= fin or ini >= len(self.mapa):
            return ""
        return self.original[self.mapa[ini]: self.mapa[min(fin, len(self.mapa)) - 1] + 1]


def _raiz(palabra: str) -> str:
    """Raíz burda para alinear (no es lematización): sin "-s" ni vocal final, seis letras."""
    if len(palabra) > 3 and palabra.endswith("s"):
        palabra = palabra[:-1]
    if len(palabra) > 4 and palabra[-1] in "aeiou":
        palabra = palabra[:-1]
    return palabra[:6]


def _es_verbal(palabra: str) -> bool:
    return len(palabra) >= 4 and palabra.endswith(_TERMINACIONES_VERBALES)


def _es_cifra(palabra: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", palabra))


def _valor(palabra: str) -> int | Decimal:
    try:
        valor = Decimal(palabra).normalize()
    except InvalidOperation:  # pragma: no cover - el token ya es una cifra
        return 0
    return int(valor) if valor == valor.to_integral_value() else valor


# ── Segmentación ─────────────────────────────────────────────────────────────

_ABREVIATURAS = frozenset({
    "art", "arts", "fr", "frs", "frac", "fracc", "parr", "num", "no", "inc", "lic", "dr", "dra", "ing",
    "pag", "p", "pp", "cfr", "etc", "sr", "sra", "c", "cc", "ss", "vs", "ver", "tit", "cap", "secc",
})
_ROMANO = re.compile(r"^[ivxlc]+$")


@dataclass
class _Oracion:
    """Oración de la fuente o cláusula de la afirmación (tramo del texto normalizado)."""

    texto: _Texto
    ini: int
    fin: int
    t0: int  # tokens [t0, t1)
    t1: int
    orden: int
    incompleta: bool = False  # última oración de una fuente truncada
    _cache: dict = field(default_factory=dict, repr=False)

    @property
    def palabras(self) -> list[str]:
        return [t.palabra for t in self.texto.tokens[self.t0:self.t1]]

    @property
    def literal(self) -> str:
        return self.texto.literal(self.ini, self.fin).strip()

    def literal_tokens(self, a: int, b: int) -> str:
        """Subcadena original de los tokens [a, b) (índices relativos a la oración)."""
        tokens = self.texto.tokens[self.t0:self.t1]
        if not tokens or a >= b:
            return ""
        return self.texto.literal(tokens[a].ini, tokens[min(b, len(tokens)) - 1].fin)

    def entre(self, i: int, j: int) -> str:
        """Texto normalizado entre el token ``i`` y el ``j`` (relativos), sin incluirlos."""
        tokens = self.texto.tokens
        return self.texto.norm[tokens[self.t0 + i].fin:tokens[self.t0 + j].ini]

    def calcular(self, nombre: str, funcion):
        if nombre not in self._cache:
            self._cache[nombre] = funcion(self)
        return self._cache[nombre]


def _cortes(texto: _Texto, ini: int, fin: int) -> list[int]:
    """Posiciones normalizadas donde termina una oración dentro de [ini, fin)."""
    cortes = []
    for coincidencia in re.finditer(r"[.;](?=\s|$)", texto.norm[ini:fin]):
        posicion = ini + coincidencia.end()
        if coincidencia.group() == ".":
            previa = re.search(r"([a-z0-9]+)\.$", texto.norm[max(ini, posicion - 20):posicion])
            palabra = previa.group(1) if previa else ""
            if (palabra in _ABREVIATURAS or _ROMANO.match(palabra) or len(palabra) == 1
                    or re.fullmatch(r"\d+[a-z]?", palabra)):
                continue
            siguiente = re.search(r"\S", texto.norm[posicion:fin])
            if siguiente is not None:
                original = texto.original[texto.mapa[posicion + siguiente.start()]]
                if not (original.isupper() or original in "\"“«[(¿¡"):
                    continue
        cortes.append(posicion)
    return cortes


def _oraciones(texto: _Texto, excluidos: Sequence[tuple[int, int]] = ()) -> list[_Oracion]:
    """Oraciones (o cláusulas) del texto, sin los tramos excluidos (notas de reforma)."""
    bloques: list[tuple[int, int]] = []
    inicio = 0
    for a, b in sorted(excluidos):
        if a > inicio:
            bloques.append((inicio, a))
        inicio = max(inicio, b)
    if inicio < len(texto.norm):
        bloques.append((inicio, len(texto.norm)))
    oraciones: list[_Oracion] = []
    for a, b in bloques:
        limites = [a, *_cortes(texto, a, b), b]
        for ini, fin in zip(limites, limites[1:]):
            t0 = bisect.bisect_left(texto._inicios, ini)
            t1 = t0
            while t1 < len(texto.tokens) and texto.tokens[t1].fin <= fin:
                t1 += 1
            if t1 == t0:
                continue
            oraciones.append(_Oracion(texto, texto.tokens[t0].ini, fin, t0, t1, len(oraciones)))
    return oraciones


def _notas_de_reforma(texto: _Texto) -> list[tuple[int, int]]:
    """Tramos normalizados de las notas de reforma de LeyesBiblio ("Párrafo reformado DOF …")."""
    lineas = texto.original.split("\n")
    desplazamientos = []
    posicion = 0
    for linea in lineas:
        desplazamientos.append(posicion)
        posicion += len(linea) + 1
    excluidos = []
    for nota in extraer_notas(lineas).notas:
        primera, ultima = nota.lineas[0], nota.lineas[-1]
        a = desplazamientos[primera]
        b = desplazamientos[ultima] + len(lineas[ultima])
        excluidos.append((texto.inversa[a], texto.inversa[b]))
    return excluidos


# ── Marcas en una oración ────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Marca:
    clase: str
    a: int  # tokens relativos a la oración [a, b)
    b: int
    negada: bool = False


def _frases(palabras: list[str], frases: Iterable[str]) -> list[tuple[str, int, int]]:
    """Apariciones de frases (palabras separadas por espacio) sin solaparse, la más larga primero."""
    candidatas = []
    for frase in frases:
        partes = frase.split()
        n = len(partes)
        for i in range(len(palabras) - n + 1):
            if palabras[i:i + n] == partes:
                candidatas.append((frase, i, i + n))
    # La más larga primero; entre iguales, la de más a la izquierda (orden estable).
    candidatas.sort(key=lambda c: (c[1], -(c[2] - c[1])))
    elegidas: list[tuple[str, int, int]] = []
    ocupado: set[int] = set()
    for frase, a, b in sorted(candidatas, key=lambda c: -(c[2] - c[1])):
        if ocupado.isdisjoint(range(a, b)):
            elegidas.append((frase, a, b))
            ocupado.update(range(a, b))
    return sorted(elegidas, key=lambda c: c[1])


def _clasificadas(palabras: list[str], tabla: Mapping[str, Sequence[str]]) -> list[_Marca]:
    frases = {frase: clase for clase, lista in tabla.items() for frase in lista}
    return [_Marca(frases[frase], a, b) for frase, a, b in _frases(palabras, frases)]


def _negaciones(palabras: list[str]) -> list[tuple[int, int]]:
    """Negadores [a, b): "no", "ni", "nunca", "jamás", "tampoco", "en ningún caso"."""
    marcas = []
    for i, palabra in enumerate(palabras):
        siguiente = palabras[i + 1] if i + 1 < len(palabras) else ""
        if palabra in NEGADORES and (palabra, siguiente) not in _NO_NEGACION:
            marcas.append((i, i + 1))
        elif palabra == "ningun" and i > 0 and palabras[i - 1] == "en" and siguiente == "caso":
            marcas.append((i - 1, i + 2))
    return marcas


def _negado(posicion: int, negaciones: list[tuple[int, int]], ventana: int = 3) -> bool:
    """La posición sigue a una negación a menos de ``ventana`` palabras ("no se formulará querella")."""
    return any(b <= posicion and posicion - b < ventana for _, b in negaciones)


def _modos(o: _Oracion) -> list[_Marca]:
    palabras = o.palabras
    negaciones = _negaciones(palabras)
    marcas = []
    for marca in _clasificadas(palabras, MODOS_PROCEDIBILIDAD):
        negada = _negado(marca.a, negaciones) or (marca.a > 0 and palabras[marca.a - 1] == "sin")
        marcas.append(_Marca(marca.clase, marca.a, marca.b, negada))
    return marcas


def _contexto(o: _Oracion) -> list[tuple[int, int]]:
    palabras = o.palabras
    tramos = [(i, i + 1) for i, p in enumerate(palabras) if p.startswith(PREFIJOS_CONTEXTO)]
    tramos += [(a, b) for _, a, b in _frases(palabras, FRASES_CONTEXTO)]
    return sorted(tramos)


def _shcp(o: _Oracion) -> bool:
    return bool(_frases(o.palabras, FRASES_SHCP))


def _contenido(o: _Oracion, desde: int, *, hasta: int | None = None, maximo: int = VENTANA_CONTENIDO,
               cortes: str = ",;:()", conjunciones: bool = False, cifras: bool = False) -> frozenset[str]:
    """Raíces de contenido desde el token ``desde`` hasta una puntuación de ``cortes``,
    ``hasta`` o ``maximo`` raíces; con ``conjunciones`` también se corta en "y", "o",
    "que"…; las siglas de ``EXPANSIONES`` se expanden; ``cifras`` incluye las cifras."""
    palabras = o.palabras
    limite = len(palabras) if hasta is None else min(hasta, len(palabras))
    raices: list[str] = []
    j = desde
    while j < limite and len(raices) < maximo:
        if j > desde and cortes and any(c in o.entre(j - 1, j) for c in cortes):
            break
        palabra = palabras[j]
        if conjunciones and palabra in _CONJUNCIONES:
            break
        for parte in EXPANSIONES.get(palabra, palabra).split():
            if _es_cifra(parte):
                if cifras:
                    raices.append(parte)
            elif len(parte) > 2 and parte not in _STOPWORDS and _numero([parte], 0) is None:
                raices.append(_raiz(parte))
        j += 1
    return frozenset(raices)


def _numero(palabras: list[str], i: int) -> tuple[int | Decimal, int] | None:
    """(valor, fin) del número que empieza en ``i`` (cifras, con separador de miles o
    decimales, o palabras hasta 999 999)."""
    if i >= len(palabras):
        return None
    if _es_cifra(palabras[i]):
        return _valor(palabras[i]), i + 1

    def menor_de_mil(j: int) -> tuple[int, int] | None:
        valor, inicio = 0, j
        if j < len(palabras) and palabras[j] in _CENTENAS_NUM:
            valor += _CENTENAS_NUM[palabras[j]]
            j += 1
        if j < len(palabras) and palabras[j] in _DECENAS_NUM:
            valor += _DECENAS_NUM[palabras[j]]
            j += 1
            if j + 1 < len(palabras) and palabras[j] == "y" and palabras[j + 1] in _UNIDADES_NUM:
                valor += _UNIDADES_NUM[palabras[j + 1]]
                j += 2
        elif j < len(palabras) and palabras[j] in _ESPECIALES_NUM:
            valor += _ESPECIALES_NUM[palabras[j]]
            j += 1
        elif j < len(palabras) and palabras[j] in _UNIDADES_NUM:
            valor += _UNIDADES_NUM[palabras[j]]
            j += 1
        return (valor, j) if j > inicio else None

    primero = menor_de_mil(i)
    j = primero[1] if primero else i
    if j < len(palabras) and palabras[j] == "mil":
        valor = (primero[0] if primero else 1) * 1000
        resto = menor_de_mil(j + 1)
        return (valor + resto[0], resto[1]) if resto else (valor, j + 1)
    return primero


@dataclass(frozen=True)
class _Cifra:
    valores: tuple  # (v,) o, si es rango, (desde, hasta)
    unidad: str
    calificador: str | None
    a: int  # tokens del primer número de su cadena a la unidad/calificador
    b: int
    rango: bool = False

    @property
    def temporal(self) -> bool:
        return self.unidad in TEMPORALES


def _contiene(palabras: list[str], frase: Sequence[str]) -> bool:
    n = len(frase)
    return any(palabras[i:i + n] == list(frase) for i in range(len(palabras) - n + 1))


def _unidad(o: _Oracion, inicio: int, fin: int) -> tuple[str, int, str | None] | None:
    """(unidad, fin, calificador) de la cifra que ocupa [inicio, fin), o ``None``."""
    palabras = o.palabras
    palabra = palabras[fin] if fin < len(palabras) else ""
    if palabra in UNIDADES_TIEMPO:
        unidad, j = UNIDADES_TIEMPO[palabra], fin + 1
        if unidad == "dias" and palabras[j:j + 1] == ["multa"]:
            return "dias multa", j + 1, None
        if unidad == "dias" and palabras[j:j + 2] == ["de", "salario"]:
            j += 2
            if palabras[j:j + 1] == ["minimo"]:
                j += 1
            return "dias de salario", j, None
        calificador = None
        if j < len(palabras) and palabras[j] in CALIFICADORES:
            calificador, j = CALIFICADORES[palabras[j]], j + 1
        elif palabras[j:j + 2] == ["de", "calendario"]:
            calificador, j = "naturales", j + 2
        return unidad, j, calificador
    if palabra in ("uma", "umas"):
        return "uma", fin + 1, None
    if palabra == "pesos":
        return "pesos", fin + 1, None
    if palabras[fin:fin + 2] in (["salario", "minimo"], ["salarios", "minimos"]):
        return "salario_minimo", fin + 2, None
    if palabra == "veces":
        ventana = palabras[fin + 1:fin + 9]
        if "uma" in ventana or "umas" in ventana or _contiene(ventana, ("unidad", "de", "medida")):
            return "uma", fin + 1, None
        if _contiene(ventana, ("salario", "minimo")) or _contiene(ventana, ("salarios", "minimos")):
            return "salario_minimo", fin + 1, None
        return None
    previo = o.texto.norm[:o.texto.tokens[o.t0 + inicio].ini].rstrip()
    if previo.endswith("$"):
        return "pesos", fin, None
    return None


def _cifras(o: _Oracion) -> list[_Cifra]:
    """Cifras con unidad: plazos y montos, con rangos ("de 2 a 9 años", "entre 3 y 5 días") y
    alternativas ("3 o 5 días")."""
    palabras = o.palabras
    numeros: dict[int, tuple[Any, int]] = {}  # fin → (valor, inicio)
    lista: list[tuple[Any, int, int]] = []
    i = 0
    while i < len(palabras):
        leido = _numero(palabras, i)
        if leido is None:
            i += 1
            continue
        numeros[leido[1]] = (leido[0], i)
        lista.append((leido[0], i, leido[1]))
        i = leido[1]
    usados: set[int] = set()
    cifras: list[_Cifra] = []
    for valor, inicio, fin in reversed(lista):
        if inicio in usados:
            continue
        unidad = _unidad(o, inicio, fin)
        if unidad is None:
            continue
        nombre, fin_unidad, calificador = unidad
        cadena = [(valor, inicio)]
        conectores: list[str] = []
        actual = inicio
        while actual >= 2 and palabras[actual - 1] in CONECTORES_RANGO | CONECTORES_ALTERNATIVA \
                and actual - 1 in numeros:
            previo, desde = numeros[actual - 1]
            propia = _unidad(o, desde, actual - 1)
            if propia is not None and propia[0] != nombre:
                break  # "seis meses a seis años": cada cifra tiene su unidad
            conectores.append(palabras[actual - 1])
            cadena.append((previo, desde))
            actual = desde
        usados.update(desde for _, desde in cadena)
        primero = cadena[-1][1]
        es_rango = len(cadena) == 2 and (
            conectores[0] in CONECTORES_RANGO
            or (conectores[0] == "y" and primero > 0 and palabras[primero - 1] == "entre")
        )
        if es_rango:
            cifras.append(_Cifra((cadena[1][0], cadena[0][0]), nombre, calificador, primero, fin_unidad, True))
        else:
            cifras.extend(_Cifra((v,), nombre, calificador, primero, fin_unidad) for v, _ in cadena)
    return sorted(cifras, key=lambda c: (c.a, str(c.valores)))


def _parentesis_tras(o: _Oracion, b: int) -> int | None:
    """Fin (token) del paréntesis que abre justo tras el token ``b - 1``, o ``None``."""
    tokens = o.texto.tokens
    if b <= 0 or b >= o.t1 - o.t0:
        return None
    if not re.match(r"\s*\(", o.entre(b - 1, b)):
        return None
    cierre = o.texto.norm.find(")", tokens[o.t0 + b - 1].fin)
    if cierre < 0:
        return None
    j = b
    while j < o.t1 - o.t0 and tokens[o.t0 + j].fin <= cierre:
        j += 1
    return j


def _condiciones(o: _Oracion) -> list[frozenset[str]]:
    """Condición (raíces) a la que se liga cada cifra de ``_cifras`` (mismo orden): las
    condiciones previas que no se ligaron a otra cifra y la posterior inmediata."""
    cifras = _rasgo(o, "cifras")
    palabras = o.palabras
    inicios = sorted({c.a for c in cifras})

    def contenido(b: int) -> frozenset[str]:
        siguiente = min([s for s in inicios if s >= b], default=len(palabras))
        return _contenido(o, b, hasta=siguiente)

    previas = _frases(palabras, MARCADORES_CONDICION_PREVIA)
    posteriores_marcas = _frases(palabras, MARCADORES_CONDICION_POSTERIOR)
    posteriores: dict[int, frozenset[str]] = {}
    usadas: set[int] = set()
    for k, cifra in enumerate(cifras):
        siguiente = min([x.a for x in cifras if x.a >= cifra.b], default=len(palabras))
        cierre = _parentesis_tras(o, cifra.b)
        if cierre is not None:
            posteriores[k] = _contenido(o, cifra.b, hasta=cierre, cortes=",;:")
            continue
        for _, a, b in posteriores_marcas:
            if cifra.b <= a < min(siguiente, cifra.b + VENTANA_CONDICION_POSTERIOR):
                posteriores[k] = contenido(b)
                usadas.add(a)
                break
    resultado = []
    for k, cifra in enumerate(cifras):
        partes = [contenido(b) for _, a, b in previas if b <= cifra.a and a not in usadas]
        resultado.append(frozenset().union(*partes, posteriores.get(k, frozenset())))
    return resultado


def _anclas(o: _Oracion) -> list[_Marca]:
    palabras = o.palabras
    especificas = _clasificadas(palabras, ANCLAS)
    ocupado = {i for m in especificas for i in range(m.a, m.b)}
    marcas = list(especificas)
    for i in range(len(palabras)):
        for arranque in _ARRANQUES_ANCLA:
            n = len(arranque)
            if tuple(palabras[i:i + n]) != arranque or i in ocupado:
                continue
            j = i + n
            while j < len(palabras) and palabras[j] in _DETERMINANTES:
                j += 1
            if (j < len(palabras) and palabras[j] not in _STOPWORDS and palabras[j] not in UNIDADES_TIEMPO
                    and not _es_cifra(palabras[j]) and len(palabras[j]) > 3
                    and ocupado.isdisjoint(range(i, j + 1))):
                marcas.append(_Marca("suceso:" + _raiz(palabras[j]), i, j + 1))
                ocupado.update(range(i, j + 1))
    return sorted(marcas, key=lambda m: m.a)


def _modales(o: _Oracion) -> list[_Marca]:
    """Modales con su clase; un deber o una facultad negados ("no podrá", "no le está
    permitido", "ninguno … podrá") son prohibición. La negación debe preceder al modal sin
    más que clíticos en medio: en "multas no fiscales podrán" el "no" niega "fiscales"."""
    palabras = o.palabras
    negaciones = _negaciones(palabras)
    negativos = [m.a for m in _clasificadas(palabras, {NEGATIVO: CUANTIFICADORES[NEGATIVO]})]
    marcas = []
    for marca in _clasificadas(palabras, MODALES):
        clase = marca.clase
        inmediata = any(b <= marca.a and all(p in _CLITICOS for p in palabras[b:marca.a]) for _, b in negaciones)
        negada = inmediata or any(n < marca.a for n in negativos)
        if negada and clase in (DEBER, FACULTAD):
            clase = PROHIBICION
        marcas.append(_Marca(clase, marca.a, marca.b, negada))
    return marcas


def _marcas_excepcion(o: _Oracion) -> list[_Marca]:
    palabras = o.palabras
    negaciones = _negaciones(palabras)
    negativos = [m.a for m in _clasificadas(palabras, {NEGATIVO: CUANTIFICADORES[NEGATIVO]})]
    marcas = []
    for marca in _clasificadas(palabras, MARCAS):
        previa = palabras[marca.a - 1] if marca.a > 0 else ""
        siguiente = palabras[marca.b] if marca.b < len(palabras) else ""
        frase = " ".join(palabras[marca.a:marca.b])
        if frase == "salvo" and previa == "a":
            continue  # "a salvo"
        if frase == "cuando" and (previa in ("aun", "de") or siguiente == "menos"):
            continue  # "aun cuando" (concesiva), "cuando menos", "de cuando en cuando"
        if frase == "sino" and not (any(b <= marca.a for _, b in negaciones) or any(n < marca.a for n in negativos)):
            continue  # "sino" solo es excepción tras una negación
        marcas.append(marca)
    return marcas


def _cuantificadores(o: _Oracion) -> list[_Marca]:
    palabras = o.palabras
    marcas = []
    for marca in _clasificadas(palabras, CUANTIFICADORES):
        frase = " ".join(palabras[marca.a:marca.b])
        previa = palabras[marca.a - 1] if marca.a > 0 else ""
        siguiente = palabras[marca.b] if marca.b < len(palabras) else ""
        clave = "todo" if frase in ("todo", "toda") else frase
        if siguiente in _NO_CUANTIFICADOR_DESPUES.get(clave, ()):
            continue
        if previa in _NO_CUANTIFICADOR_ANTES.get(clave, ()):
            continue
        marcas.append(marca)
    return marcas


@dataclass(frozen=True)
class _Predicado:
    raiz: str
    posicion: int
    inicio_cadena: int  # primer token de su cadena (negadores, auxiliares, clíticos…)
    negado: bool
    complemento: frozenset[str]


def _predicados(o: _Oracion) -> list[_Predicado]:
    """Predicados (palabras verbales) con su polaridad y su complemento.

    La polaridad se lee en la cadena que precede al verbo (negadores, prohibitivos,
    clíticos, auxiliares y participios de permiso) sin cruzar puntuación; cuenta la
    paridad: "no podrá admitir" es negativo, "no podrá no admitir" afirmativo, "le está
    prohibido admitir" negativo. El complemento son las raíces que siguen hasta una
    puntuación o una conjunción: empareja "aceptar la prueba documental" con su par y no
    con "no deberá aceptar la prueba ilícita"."""
    palabras = o.palabras
    finales = {b - 1: a for a, b in _rasgo(o, "negaciones")}
    resultado = []
    for i, palabra in enumerate(palabras):
        if not _es_verbal(palabra) or palabra in _CADENA or palabra in _STOPWORDS or palabra in NEGADORES:
            continue
        cuenta, j, inicio = 0, i - 1, i
        while j >= 0 and not any(c in o.entre(j, j + 1) for c in ",;:."):
            if j in finales:
                cuenta += 1
                inicio = finales[j]
                j = finales[j] - 1
                continue
            if palabras[j] in _PROHIBITIVOS:
                cuenta += 1
            elif palabras[j] not in _CADENA:
                break
            inicio = j
            j -= 1
        complemento = _contenido(o, i + 1, maximo=5, cortes=",;:.", conjunciones=True)
        resultado.append(_Predicado(_raiz(palabra), i, inicio, cuenta % 2 == 1, complemento))
    return resultado


def _facultades_con_infinitivo(o: _Oracion) -> list[tuple[str, int, int]]:
    """(raíz del infinitivo, inicio, fin) de cada facultad no negada seguida de infinitivo
    ("podrá interponerse", "podrá ordenar")."""
    palabras = o.palabras
    resultado = []
    for marca in _rasgo(o, "modales"):
        if marca.clase != FACULTAD:
            continue
        j = marca.b
        while j < len(palabras) and palabras[j] in _CLITICOS:
            j += 1
        if j < len(palabras) and palabras[j].endswith(_TERMINACIONES_INFINITIVO) and len(palabras[j]) >= 4:
            resultado.append((_raiz(palabras[j]), marca.a, j + 1))
    return resultado


def _futuros(o: _Oracion) -> dict[str, tuple[int, int]]:
    """Raíz → (inicio, fin) de cada futuro de indicativo no negado ni modalizado
    ("se interpondrá", "ordenará"): un mandato implícito."""
    palabras = o.palabras
    negados = {p.posicion for p in _rasgo(o, "predicados") if p.negado}
    resultado: dict[str, tuple[int, int]] = {}
    for i, palabra in enumerate(palabras):
        if (len(palabra) < 6 or palabra in _NO_FUTUROS or palabra in _CADENA
                or not palabra.endswith(_TERMINACIONES_FUTURO) or i in negados):
            continue
        inicio = i - 1 if i > 0 and palabras[i - 1] in _CLITICOS else i
        resultado.setdefault(_raiz(palabra), (inicio, i + 1))
    return resultado


def _organos(o: _Oracion) -> frozenset[str]:
    palabras = o.palabras
    familias = set()
    for familia, frases in ORGANOS.items():
        for frase, a, _ in _frases(palabras, frases):
            if frase in ("fiscal", "fiscales") and (a == 0 or palabras[a - 1] not in _DETERMINANTES_ORGANO):
                continue
            familias.add(familia)
    return frozenset(familias)


def _raices(o: _Oracion) -> frozenset[str]:
    """Raíces de contenido para alinear. Se excluyen las palabras de lo que se compara
    (cifras e inicio del cómputo, además de modales, negaciones y cuantificadores en
    ``_STOPWORDS``): "contados a partir de que surta efectos la notificación" no debe
    decidir con qué oración se alinea una cláusula cuyo inicio del cómputo se coteja."""
    excluidas = {i for m in _rasgo(o, "anclas") for i in range(m.a, m.b)}
    excluidas |= {i for c in _rasgo(o, "cifras") for i in range(c.a, c.b)}
    raices = {
        _raiz(p) for i, p in enumerate(o.palabras)
        if i not in excluidas and len(p) > 2 and p not in _STOPWORDS and not _es_cifra(p)
        and _numero([p], 0) is None
    }
    # Una cifra idéntica (valores y unidad) sí alinea: distingue la fr. II ("de dos años a
    # cinco años") de la fr. I ("de tres meses a dos años") del mismo artículo.
    raices |= {"#" + "-".join(str(v) for v in c.valores) + ":" + c.unidad for c in _rasgo(o, "cifras")}
    return frozenset(raices)


_RASGOS = {
    "modos": _modos, "contexto": _contexto, "shcp": _shcp, "cifras": _cifras, "condiciones": _condiciones,
    "anclas": _anclas, "modales": _modales, "marcas": _marcas_excepcion, "cuantificadores": _cuantificadores,
    "predicados": _predicados, "raices": _raices, "negaciones": lambda x: _negaciones(x.palabras),
    "facultades": _facultades_con_infinitivo, "futuros": _futuros, "organos": _organos,
}


def _rasgo(o: _Oracion, nombre: str):
    return o.calcular(nombre, _RASGOS[nombre])


# ── Señales ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FuenteTexto:
    """Texto oficial de un artículo para el motor puro (``comparar``)."""

    descriptor: str  # "art. 113 Bis CFF"
    texto: str
    sha256_documento: str | None = None
    articulo: str | None = None  # "113 Bis"
    truncado: bool = False  # el artículo puede continuar en páginas no recibidas


@dataclass(frozen=True)
class Senal:
    """Una diferencia determinista entre la afirmación y el texto oficial."""

    codigo: str
    detalle: str
    tramo_afirmacion: str  # subcadena literal de la afirmación
    tramo_fuente: str  # subcadena literal del artículo ("" si la cifra no aparece)
    fuente: str  # descriptor del artículo, o varios separados por " · "
    marca_afirmacion: str | None = None
    marca_fuente: str | None = None
    sha256_documentos: tuple[str, ...] = ()
    articulo: str = ""  # identificador del artículo, o varios separados por " · "

    @property
    def categoria(self) -> str:
        return CODIGOS[self.codigo][0]

    @property
    def severidad(self) -> str:
        return CODIGOS[self.codigo][1]

    @property
    def precision(self) -> str:
        return CODIGOS[self.codigo][2]

    @property
    def huella(self) -> str:
        """SHA-256 de lo que identifica la señal: código, fuente, artículo, documentos y
        tramos literales. Una decisión humana atiende esta huella, no la familia de señal."""
        return sha256_texto(json_canonico({
            "codigo": self.codigo,
            "fuente": self.fuente,
            "articulo": self.articulo,
            "sha256_documentos": list(self.sha256_documentos),
            "tramo_afirmacion": self.tramo_afirmacion,
            "tramo_fuente": self.tramo_fuente,
        }))

    def como_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "categoria": self.categoria,
            "severidad": self.severidad,
            "precision": self.precision,
            "huella": self.huella,
            "detalle": self.detalle,
            "tramo_afirmacion": self.tramo_afirmacion,
            "tramo_fuente": self.tramo_fuente,
            "fuente": self.fuente,
            "articulo": self.articulo,
            "marca_afirmacion": self.marca_afirmacion,
            "marca_fuente": self.marca_fuente,
            "sha256_documentos": list(self.sha256_documentos),
        }


def _ventana(oracion: _Oracion, a: int | None = None, b: int | None = None) -> str:
    """Tramo literal de la oración; si es largo, una ventana literal alrededor de [a, b)
    (o del inicio de la oración, sin marca)."""
    completo = oracion.literal
    if len(completo) <= MAXIMO_TRAMO:
        return completo
    if a is None:
        a, b = 0, 1
    return _recorte(oracion, a, b if b is not None else a + 1)


def _recorte(oracion: _Oracion, a: int, b: int) -> str:
    tokens = oracion.texto.tokens[oracion.t0:oracion.t1]
    centro_ini = tokens[max(0, min(a, len(tokens) - 1))].ini
    centro_fin = tokens[max(0, min(b, len(tokens)) - 1)].fin
    margen = max(0, (MAXIMO_TRAMO - (centro_fin - centro_ini)) // 2)
    ini = max(oracion.ini, centro_ini - margen)
    fin = min(oracion.fin, centro_fin + margen)
    # Ajustar a límites de palabra para no cortar una palabra.
    while ini > oracion.ini and oracion.texto.norm[ini - 1].isalnum():
        ini -= 1
    while fin < oracion.fin and fin < len(oracion.texto.norm) and oracion.texto.norm[fin].isalnum():
        fin += 1
    return oracion.texto.literal(ini, fin).strip()


@dataclass
class _Fuente:
    descriptor: str
    sha256: str | None
    articulo: str
    truncado: bool
    oraciones: list[_Oracion]


def _preparar_fuente(fuente: FuenteTexto) -> _Fuente:
    texto = _Texto(fuente.texto)
    oraciones = _oraciones(texto, _notas_de_reforma(texto))
    if fuente.truncado and oraciones:
        oraciones[-1].incompleta = True
    return _Fuente(fuente.descriptor, fuente.sha256_documento, fuente.articulo or "", fuente.truncado, oraciones)


def _senal(codigo: str, detalle: str, clausula: _Oracion, fuentes: Sequence[_Fuente], tramo_fuente: str,
           marca_afirmacion: str | None = None, marca_fuente: str | None = None) -> Senal:
    return Senal(
        codigo, detalle, clausula.literal, tramo_fuente,
        " · ".join(f.descriptor for f in fuentes),
        marca_afirmacion, marca_fuente,
        tuple(sorted({f.sha256 for f in fuentes if f.sha256})),
        " · ".join(f.articulo for f in fuentes if f.articulo),
    )


Candidata = tuple  # (puntaje, raíces comunes, oración, fuente)


def _alinear(clausula: _Oracion, fuentes: Sequence[_Fuente]) -> list[Candidata]:
    """Oraciones candidatas para la cláusula, de mejor a peor: (puntaje, raíces comunes,
    oración, fuente). Si la cláusula nombra un órgano, solo compiten las oraciones
    compatibles (sin órgano o con alguno en común), si las hay."""
    propias = _rasgo(clausula, "raices")
    if len(propias) < MINIMO_RAICES_COMUNES:
        return []
    puntuadas = []
    for fuente in fuentes:
        for oracion in fuente.oraciones:
            ajenas = _rasgo(oracion, "raices")
            comunes = len(propias & ajenas)
            if comunes < MINIMO_RAICES_COMUNES:
                continue
            # Cobertura de la cláusula (qué parte de lo que dice está en la oración) y, para
            # desempatar, el coseno: el coseno solo favorecía oraciones cortas aunque no
            # contuvieran lo que la cláusula parafrasea (revisión externa, ronda 2).
            cobertura = comunes / len(propias)
            if cobertura < UMBRAL_ALINEACION:
                continue
            puntaje = cobertura + PESO_COSENO * comunes / math.sqrt(len(propias) * len(ajenas))
            puntuadas.append((puntaje, comunes, oracion, fuente))
    organos = _rasgo(clausula, "organos")
    if organos:
        compatibles = [x for x in puntuadas if not _rasgo(x[2], "organos") or _rasgo(x[2], "organos") & organos]
        puntuadas = compatibles or puntuadas
    if not puntuadas:
        return []
    puntuadas.sort(key=lambda x: (-x[0], -x[1], fuentes.index(x[3]), x[2].orden))
    mejor = puntuadas[0][0]
    return [x for x in puntuadas if x[0] >= FRACCION_CANDIDATAS * mejor]


def _negacion_con_excepcion(o: _Oracion) -> bool:
    """"no … salvo/sino/excepto …": una negación (o "ningún") seguida de una excepción."""
    negaciones = [a for a, _ in _rasgo(o, "negaciones")]
    negaciones += [m.a for m in _rasgo(o, "cuantificadores") if m.clase == NEGATIVO]
    excepciones = [m.a for m in _rasgo(o, "marcas") if m.clase == EXCEPCION]
    return any(n < e for n in negaciones for e in excepciones)


def _exclusiva(o: _Oracion) -> bool:
    return any(m.clase == EXCLUSIVO for m in _rasgo(o, "cuantificadores"))


def _equivalentes(clausula: _Oracion, oracion: _Oracion) -> bool:
    """Equivalencia lógica "no podrá … salvo …" ↔ "solo …" (en cualquier sentido)."""
    return ((_negacion_con_excepcion(oracion) and _exclusiva(clausula) and not _negacion_con_excepcion(clausula))
            or (_negacion_con_excepcion(clausula) and _exclusiva(oracion) and not _negacion_con_excepcion(oracion)))


def _tiene_negacion(o: _Oracion) -> bool:
    return bool(_rasgo(o, "negaciones")) or any(m.clase == NEGATIVO for m in _rasgo(o, "cuantificadores"))


class _Acumulador:
    def __init__(self) -> None:
        self.senales: list[Senal] = []
        self._vistas: set[tuple] = set()

    def agregar(self, senal: Senal) -> None:
        clave = (senal.codigo, senal.tramo_afirmacion, senal.tramo_fuente, senal.fuente, senal.marca_afirmacion)
        if clave not in self._vistas:
            self._vistas.add(clave)
            self.senales.append(senal)


# ── Reglas ───────────────────────────────────────────────────────────────────


def _procedibilidad(clausulas: list[_Oracion], fuentes: list[_Fuente], salida: _Acumulador) -> None:
    activa = any(_rasgo(c, "contexto") or any(m.clase == QUERELLA for m in _rasgo(c, "modos")) for c in clausulas)
    if not activa:
        return
    positivos = [(c, m) for c in clausulas for m in _rasgo(c, "modos") if not m.negada]
    negados = [(c, m) for c in clausulas for m in _rasgo(c, "modos") if m.negada]
    con_contexto = [c for c in clausulas if _rasgo(c, "contexto")]
    for fuente in fuentes:
        if not any(_rasgo(o, "contexto") or any(m.clase == QUERELLA for m in _rasgo(o, "modos"))
                   for o in fuente.oraciones):
            continue
        modos = [(o, m) for o in fuente.oraciones for m in _rasgo(o, "modos") if not m.negada]
        clases = {m.clase for _, m in modos}
        requisitos = [(o, m) for o, m in modos if m.clase in MODOS_REQUISITO]
        # Modo distinto: depende de que el artículo NO prevea el modo de la afirmación; con
        # una fuente truncada esa ausencia no se acredita.
        if positivos and clases and not ({m.clase for _, m in positivos} & clases) and not fuente.truncado:
            clausula, marca = positivos[0]
            oracion, ajena = (requisitos or modos)[0]
            salida.agregar(_senal(
                "procedibilidad.modo_distinto",
                f"la afirmación dice «{clausula.literal_tokens(marca.a, marca.b)}» y {fuente.descriptor} "
                f"prevé «{oracion.literal_tokens(ajena.a, ajena.b)}»",
                clausula, [fuente], _ventana(oracion, ajena.a, ajena.b),
                clausula.literal_tokens(marca.a, marca.b), oracion.literal_tokens(ajena.a, ajena.b)))
        for clausula, marca in negados:
            coincidentes = [(o, m) for o, m in modos if m.clase == marca.clase]
            if coincidentes:
                oracion, ajena = coincidentes[0]
                salida.agregar(_senal(
                    "procedibilidad.modo_negado",
                    f"la afirmación niega «{clausula.literal_tokens(marca.a, marca.b)}» y {fuente.descriptor} lo prevé",
                    clausula, [fuente], _ventana(oracion, ajena.a, ajena.b),
                    clausula.literal_tokens(marca.a, marca.b), oracion.literal_tokens(ajena.a, ajena.b)))
        if not positivos and not negados and requisitos and con_contexto:
            clausula = con_contexto[0]
            a, b = _rasgo(clausula, "contexto")[0]
            oracion, ajena = requisitos[0]
            salida.agregar(_senal(
                "procedibilidad.requisito_omitido",
                f"la afirmación habla de «{clausula.literal_tokens(a, b)}» sin el requisito que {fuente.descriptor} "
                f"impone («{oracion.literal_tokens(ajena.a, ajena.b)}»)",
                clausula, [fuente], _ventana(oracion, ajena.a, ajena.b),
                clausula.literal_tokens(a, b), oracion.literal_tokens(ajena.a, ajena.b)))
        if positivos and not any(_rasgo(c, "shcp") for c in clausulas):
            propios = {m.clase for _, m in positivos}
            for oracion, ajena in requisitos:
                if ajena.clase in propios and _rasgo(oracion, "shcp"):
                    clausula, marca = next((c, m) for c, m in positivos if m.clase == ajena.clase)
                    salida.agregar(_senal(
                        "procedibilidad.shcp_omitida",
                        f"{fuente.descriptor} impone la {ajena.clase.replace('_', ' ')} a la Secretaría de Hacienda "
                        "y Crédito Público y la afirmación no la nombra",
                        clausula, [fuente], _ventana(oracion, ajena.a, ajena.b),
                        clausula.literal_tokens(marca.a, marca.b), oracion.literal_tokens(ajena.a, ajena.b)))
                    break


def _misma_cifra(propia: _Cifra, ajena: _Cifra) -> bool:
    if propia.unidad != ajena.unidad:
        return False
    if propia.valores == ajena.valores:
        return True
    # "hasta 9 años" frente a "de dos a nueve años": un extremo del rango.
    return not propia.rango and ajena.rango and propia.valores[0] in ajena.valores


def _calificador_compatible(propia: _Cifra, ajena: _Cifra) -> bool:
    return not (propia.calificador and ajena.calificador and propia.calificador != ajena.calificador)


def _describir_cifra(oracion: _Oracion, cifra: _Cifra) -> str:
    return oracion.literal_tokens(cifra.a, cifra.b)


def _cifras_e_inicio(clausula: _Oracion, candidatas: list[Candidata], fuentes: list[_Fuente], completas: bool,
                     salida: _Acumulador) -> None:
    """Cifras de la cláusula frente a las oraciones candidatas (ver el docstring del módulo)."""
    anclas_propias = _rasgo(clausula, "anclas")
    clases_propias = {m.clase for m in anclas_propias}
    oraciones = [(o, f) for _, _, o, f in candidatas]
    incompleta = any(o.incompleta for o, _ in oraciones)
    cifras = _rasgo(clausula, "cifras")
    condiciones = _rasgo(clausula, "condiciones")
    omisiones_inicio: list[tuple] = []

    def inicio(cifra: _Cifra, iguales: list[tuple]) -> None:
        """Inicio del cómputo frente a TODAS las oraciones que traen la misma cifra."""
        anclas = [{m.clase for m in _rasgo(o, "anclas")} for o, _, _ in iguales]
        if not all(anclas):
            return
        o, f, x = iguales[0]
        ancla = _rasgo(o, "anclas")[0]
        if clases_propias:
            if all(not (a & clases_propias) for a in anclas) and not any(o2.incompleta for o2, _, _ in iguales):
                propia = anclas_propias[0]
                salida.agregar(_senal(
                    "inicio_computo.distinto",
                    f"la afirmación cuenta «{_describir_cifra(clausula, cifra)}» "
                    f"«{clausula.literal_tokens(propia.a, propia.b)}» y {f.descriptor} "
                    f"«{o.literal_tokens(ancla.a, ancla.b)}»",
                    clausula, [f], _ventana(o, ancla.a, ancla.b),
                    clausula.literal_tokens(propia.a, propia.b), o.literal_tokens(ancla.a, ancla.b)))
        else:
            omisiones_inicio.append((cifra, o, f, ancla))

    for k, cifra in enumerate(cifras):
        marca = _describir_cifra(clausula, cifra)
        condicion = condiciones[k]
        # 1. Misma condición: la cifra se compara con la que la fuente liga a esa condición.
        if cifra.temporal and len(condicion) >= MINIMO_CONDICION:
            pool = []
            for o, f in oraciones:
                propias_condiciones = _rasgo(o, "condiciones")
                for j, x in enumerate(_rasgo(o, "cifras")):
                    if x.temporal and propias_condiciones[j]:
                        pool.append((len(condicion & propias_condiciones[j]), o, f, x))
            mejor = max((p[0] for p in pool), default=0)
            if mejor >= MINIMO_CONDICION:
                mejores = [p for p in pool if p[0] == mejor]
                iguales = [(o, f, x) for _, o, f, x in mejores if _misma_cifra(cifra, x)]
                if iguales:
                    compatibles = [t for t in iguales if _calificador_compatible(cifra, t[2])]
                    if compatibles:
                        inicio(cifra, compatibles)
                        continue
                    o, f, x = iguales[0]
                    if not o.incompleta:
                        salida.agregar(_senal(
                            "plazos_cifras.distinto_misma_condicion",
                            f"para la misma condición la afirmación dice «{marca}» y {f.descriptor} "
                            f"«{_describir_cifra(o, x)}» (calificador)",
                            clausula, [f], _ventana(o, x.a, x.b), marca, _describir_cifra(o, x)))
                    continue
                if not any(o.incompleta for _, o, _, _ in mejores):
                    _, o, f, x = mejores[0]
                    salida.agregar(_senal(
                        "plazos_cifras.distinto_misma_condicion",
                        f"para la misma condición la afirmación dice «{marca}» y {f.descriptor} "
                        f"«{_describir_cifra(o, x)}»",
                        clausula, [f], _ventana(o, x.a, x.b), marca, _describir_cifra(o, x)))
                    continue
        # 2. La misma cifra en las candidatas (o en una sola oración de las fuentes).
        iguales = [(o, f, x) for o, f in oraciones for x in _rasgo(o, "cifras") if _misma_cifra(cifra, x)]
        if not iguales:
            en_fuentes = [(o, f, x) for f in fuentes for o in f.oraciones for x in _rasgo(o, "cifras")
                          if _misma_cifra(cifra, x)]
            if en_fuentes:
                if len({id(o) for o, _, _ in en_fuentes}) != 1:
                    continue  # en varias oraciones no alineadas: no se atribuye
                # "180 días para armonizar" ↔ "en un plazo de ciento ochenta días, contado…"
                iguales = en_fuentes
        if iguales:
            compatibles = [t for t in iguales if _calificador_compatible(cifra, t[2])]
            if not compatibles:
                o, f, x = iguales[0]
                salida.agregar(_senal(
                    "plazos_cifras.calificador_distinto",
                    f"la afirmación dice «{marca}» y {f.descriptor} «{_describir_cifra(o, x)}»",
                    clausula, [f], _ventana(o, x.a, x.b), marca, _describir_cifra(o, x)))
                continue
            inicio(cifra, compatibles)
            continue
        if incompleta:
            continue  # la oración alineada puede continuar en páginas no recibidas
        # 3. Rango, número o unidad distintos en las candidatas; si no, cifra ausente.
        if cifra.rango:
            rangos = [(o, f, x) for o, f in oraciones for x in _rasgo(o, "cifras")
                      if x.rango and x.unidad == cifra.unidad]
            if rangos:
                o, f, x = rangos[0]
                salida.agregar(_senal(
                    "plazos_cifras.rango_distinto",
                    f"la afirmación dice «{marca}» y la oración alineada de {f.descriptor} «{_describir_cifra(o, x)}»",
                    clausula, [f], _ventana(o, x.a, x.b), marca, _describir_cifra(o, x)))
                continue
        misma_unidad = [(o, f, x) for o, f in oraciones for x in _rasgo(o, "cifras") if x.unidad == cifra.unidad]
        mismo_numero = [(o, f, x) for o, f in oraciones for x in _rasgo(o, "cifras")
                        if set(x.valores) & set(cifra.valores)]
        if misma_unidad or mismo_numero:
            codigo = "plazos_cifras.numero_distinto" if misma_unidad else "plazos_cifras.unidad_distinta"
            o, f, x = (misma_unidad or mismo_numero)[0]
            salida.agregar(_senal(
                codigo,
                f"la afirmación dice «{marca}» y la oración alineada de {f.descriptor} «{_describir_cifra(o, x)}»",
                clausula, [f], _ventana(o, x.a, x.b), marca, _describir_cifra(o, x)))
            continue
        if not completas:
            continue
        oracion = candidatas[0][2] if candidatas else None
        descriptores = " · ".join(f.descriptor for f in fuentes)
        salida.agregar(_senal(
            "plazos_cifras.cifra_ausente", f"la cifra «{marca}» no aparece en el texto oficial de {descriptores}",
            clausula, fuentes, _ventana(oracion) if oracion else "", marca))
    for cifra, o, f, ancla in omisiones_inicio[:1]:
        salida.agregar(_senal(
            "inicio_computo.omitido",
            f"«{_describir_cifra(clausula, cifra)}» sin el inicio del cómputo que fija {f.descriptor} "
            f"(«{o.literal_tokens(ancla.a, ancla.b)}»)",
            clausula, [f], _ventana(o, ancla.a, ancla.b),
            _describir_cifra(clausula, cifra), o.literal_tokens(ancla.a, ancla.b)))
    # Inicio del cómputo sin cifra: distinto de TODAS las candidatas.
    if anclas_propias and not cifras and oraciones and not incompleta:
        anclas = [{m.clase for m in _rasgo(o, "anclas")} for o, _ in oraciones]
        if all(anclas) and all(not (a & clases_propias) for a in anclas):
            o, f = oraciones[0]
            propia, ancla = anclas_propias[0], _rasgo(o, "anclas")[0]
            salida.agregar(_senal(
                "inicio_computo.distinto",
                f"la afirmación dice «{clausula.literal_tokens(propia.a, propia.b)}» y {f.descriptor} "
                f"«{o.literal_tokens(ancla.a, ancla.b)}»",
                clausula, [f], _ventana(o, ancla.a, ancla.b),
                clausula.literal_tokens(propia.a, propia.b), o.literal_tokens(ancla.a, ancla.b)))


def _modal(clausula: _Oracion, oracion: _Oracion, fuente: _Fuente, equivalentes: bool) -> list[Senal]:
    if equivalentes:
        return []
    propias = _rasgo(clausula, "modales")
    ajenas = _rasgo(oracion, "modales")
    clases_propias = {m.clase for m in propias}
    clases_ajenas = {m.clase for m in ajenas}
    if clases_propias and clases_ajenas and not (clases_propias & clases_ajenas):
        if PROHIBICION in clases_propias | clases_ajenas:
            codigo = "modal.cambio"  # prohibición frente a deber o facultad: polaridad invertida
        elif clases_ajenas == {DEBER} and clases_propias == {FACULTAD}:
            codigo = "modal.atenuacion"
        else:
            codigo = "modal.refuerzo"
        propia, ajena = propias[0], ajenas[0]
        return [_senal(
            codigo,
            f"la afirmación dice «{clausula.literal_tokens(propia.a, propia.b)}» ({propia.clase}) y "
            f"{fuente.descriptor} «{oracion.literal_tokens(ajena.a, ajena.b)}» ({ajena.clase})",
            clausula, [fuente], _ventana(oracion, ajena.a, ajena.b),
            clausula.literal_tokens(propia.a, propia.b), oracion.literal_tokens(ajena.a, ajena.b))]
    # Mandato implícito: "se interpondrá" (fuente) ↔ "podrá interponerse" (afirmación) y al revés.
    for origen, destino, codigo in ((clausula, oracion, "modal.atenuacion"), (oracion, clausula, "modal.refuerzo")):
        futuros = _rasgo(destino, "futuros")
        for raiz, a, b in _rasgo(origen, "facultades"):
            if raiz not in futuros:
                continue
            fa, fb = futuros[raiz]
            facultad = origen.literal_tokens(a, b)
            mandato = destino.literal_tokens(fa, fb)
            if origen is clausula:
                detalle = f"{fuente.descriptor} manda «{mandato}» y la afirmación dice «{facultad}» (facultad)"
                return [_senal(codigo, detalle, clausula, [fuente], _ventana(oracion, fa, fb), facultad, mandato)]
            detalle = f"{fuente.descriptor} dice «{facultad}» (facultad) y la afirmación manda «{mandato}»"
            return [_senal(codigo, detalle, clausula, [fuente], _ventana(oracion, a, b), mandato, facultad)]
    return []


def _polaridad(clausula: _Oracion, oracion: _Oracion, fuente: _Fuente) -> list[Senal]:
    ajenos = _rasgo(oracion, "predicados")
    for propio in _rasgo(clausula, "predicados"):
        otros = [q for q in ajenos if q.raiz == propio.raiz]
        if not otros:
            continue
        mejor = max(len(propio.complemento & q.complemento) for q in otros)
        elegidos = [q for q in otros if len(propio.complemento & q.complemento) == mejor]
        if len({q.negado for q in elegidos}) != 1:
            continue  # ocurrencias con polaridad distinta e igual parecido: ambiguo, no se elige
        ajeno = elegidos[0]
        if ajeno.negado == propio.negado:
            continue
        marca_propia = clausula.literal_tokens(propio.inicio_cadena, propio.posicion + 1)
        marca_ajena = oracion.literal_tokens(ajeno.inicio_cadena, ajeno.posicion + 1)
        polaridad = "negativa" if ajeno.negado else "afirmativa"
        return [_senal(
            "negacion.polaridad_distinta",
            f"{fuente.descriptor} dice «{marca_ajena}» (polaridad {polaridad}) y la afirmación «{marca_propia}»",
            clausula, [fuente], _ventana(oracion, ajeno.inicio_cadena, ajeno.posicion + 1),
            marca_propia, marca_ajena)]
    return []


def _excepciones(clausula: _Oracion, oracion: _Oracion, fuente: _Fuente, equivalentes: bool,
                 hermanas: Sequence[_Oracion] = ()) -> list[Senal]:
    """Excepciones y condiciones. ``hermanas``: otras cláusulas de la afirmación alineadas con
    la misma oración (una afirmación que separa la oración en dos cláusulas conserva la
    excepción aunque esté en la otra)."""
    propias = _rasgo(clausula, "marcas")
    clases_propias = {m.clase for m in propias} | {m.clase for h in hermanas for m in _rasgo(h, "marcas")}
    senales: list[Senal] = []
    vistas: set[str] = set()
    for marca in _rasgo(oracion, "marcas"):
        if marca.clase in vistas:
            continue
        texto_marca = oracion.literal_tokens(marca.a, marca.b)
        if marca.clase not in clases_propias:
            if marca.clase == EXCEPCION and equivalentes:
                continue
            vistas.add(marca.clase)
            codigo = ("excepcion_condicion.excepcion_omitida" if marca.clase == EXCEPCION
                      else "excepcion_condicion.condicion_omitida")
            senales.append(_senal(
                codigo,
                f"la oración de {fuente.descriptor} que parafrasea la afirmación trae «{texto_marca}» y la afirmación "
                f"no recoge ninguna {'excepción' if marca.clase == EXCEPCION else 'condición'}",
                clausula, [fuente], _ventana(oracion, marca.a, min(marca.b + 6, oracion.t1 - oracion.t0)),
                None, texto_marca))
            continue
        if marca.clase != EXCEPCION:
            continue
        # Contenido de la excepción: lo que sigue a "salvo/excepto" debe solaparse.
        ajeno = _contenido(oracion, marca.b, maximo=8, cortes=";:.", cifras=True)
        contenidos = [(m, _contenido(clausula, m.b, maximo=8, cortes=";:.", cifras=True))
                      for m in propias if m.clase == EXCEPCION]
        if ajeno and contenidos and all(c and not (c & ajeno) for _, c in contenidos):
            vistas.add(marca.clase)
            propia = contenidos[0][0]
            senales.append(_senal(
                "excepcion_condicion.excepcion_distinta",
                f"la excepción de la afirmación («{clausula.literal_tokens(propia.a, propia.b + 4)}») no comparte "
                f"contenido con la de {fuente.descriptor} («{oracion.literal_tokens(marca.a, marca.b + 4)}»)",
                clausula, [fuente], _ventana(oracion, marca.a, min(marca.b + 6, oracion.t1 - oracion.t0)),
                clausula.literal_tokens(propia.a, propia.b + 4), oracion.literal_tokens(marca.a, marca.b + 4)))
    return senales


def _cuantificador(clausula: _Oracion, oracion: _Oracion, fuente: _Fuente, equivalentes: bool,
                   hermanas: Sequence[_Oracion] = ()) -> list[Senal]:
    propias = _rasgo(clausula, "cuantificadores")
    ajenas = _rasgo(oracion, "cuantificadores")
    clases_propias = {m.clase for m in propias}
    clases_hermanas = {m.clase for h in hermanas for m in _rasgo(h, "cuantificadores")}
    clases_ajenas = {m.clase for m in ajenas}
    senales: list[Senal] = []
    for marca in propias:
        if marca.clase in clases_ajenas:
            continue
        if marca.clase == EXCLUSIVO and equivalentes:
            continue
        if marca.clase == NEGATIVO and _tiene_negacion(oracion):
            continue
        texto_marca = clausula.literal_tokens(marca.a, marca.b)
        senales.append(_senal(
            "cuantificador.anadido",
            f"la afirmación dice «{texto_marca}» ({marca.clase}) y la oración de {fuente.descriptor} que parafrasea "
            "no trae ese cuantificador",
            clausula, [fuente], _ventana(oracion), texto_marca))
        clases_ajenas.add(marca.clase)
    for marca in ajenas:
        if marca.clase not in (NEGATIVO, EXCLUSIVO) or marca.clase in clases_propias | clases_hermanas:
            continue
        if equivalentes:
            continue  # "ningún … sino" / "no … salvo" ↔ "solo": la restricción se conserva
        if marca.clase == NEGATIVO and (_tiene_negacion(clausula) or any(_tiene_negacion(h) for h in hermanas)):
            continue
        texto_marca = oracion.literal_tokens(marca.a, marca.b)
        senales.append(_senal(
            "cuantificador.omitido", f"{fuente.descriptor} dice «{texto_marca}» ({marca.clase}) y la afirmación lo omite",
            clausula, [fuente], _ventana(oracion, marca.a, marca.b), None, texto_marca))
        clases_propias.add(marca.clase)
    return senales


def _sujeto(clausula: _Oracion, oracion: _Oracion, fuente: _Fuente) -> list[Senal]:
    propias, ajenas = _rasgo(clausula, "organos"), _rasgo(oracion, "organos")
    if not (propias and ajenas) or propias & ajenas:
        return []
    return [_senal(
        "sujeto.organo_distinto",
        f"la afirmación nombra {', '.join(sorted(propias))} y la oración de {fuente.descriptor} que parafrasea, "
        f"{', '.join(sorted(ajenas))}",
        clausula, [fuente], _ventana(oracion))]


def _secundarias(clausula: _Oracion, oracion: _Oracion, fuente: _Fuente,
                 hermanas: Sequence[_Oracion] = ()) -> list[Senal]:
    equivalentes = _equivalentes(clausula, oracion)
    senales = _modal(clausula, oracion, fuente, equivalentes)
    if not equivalentes:
        senales += _polaridad(clausula, oracion, fuente)
    senales += _excepciones(clausula, oracion, fuente, equivalentes, hermanas)
    senales += _cuantificador(clausula, oracion, fuente, equivalentes, hermanas)
    senales += _sujeto(clausula, oracion, fuente)
    return senales


def _organos_distintos(a: _Oracion, b: _Oracion) -> bool:
    primeros, segundos = _rasgo(a, "organos"), _rasgo(b, "organos")
    return bool(primeros and segundos) and not (primeros & segundos)


def comparar(
    afirmacion: str, fuentes: Sequence[FuenteTexto], *, fuentes_completas: bool = True
) -> tuple[Senal, ...]:
    """Señales deterministas entre el texto de una afirmación y los textos oficiales.

    Función pura (sin paquete): la usan el cotejo del ledger y el Gold Set de fidelidad.
    ``fuentes_completas=False`` (la afirmación también descansa en evidencia que no se
    pudo cotejar) o una fuente ``truncado`` suprimen las señales que dependen de una
    ausencia en la fuente (cifra ausente).
    """
    if not isinstance(afirmacion, str) or not afirmacion.strip() or not fuentes:
        return ()
    texto = _Texto(afirmacion)
    clausulas = _oraciones(texto)
    preparadas = [_preparar_fuente(f) for f in fuentes if isinstance(f.texto, str) and f.texto.strip()]
    completas = fuentes_completas and not any(f.truncado for f in preparadas)
    salida = _Acumulador()
    _procedibilidad(clausulas, preparadas, salida)
    alineadas = [(clausula, _alinear(clausula, preparadas)) for clausula in clausulas]
    # Cláusulas hermanas: las que se alinean con la misma oración (una afirmación que separa
    # una oración en dos cláusulas no "omite" lo que dice en la otra).
    por_oracion: dict[int, list[_Oracion]] = {}
    for clausula, candidatas in alineadas:
        if candidatas:
            por_oracion.setdefault(id(candidatas[0][2]), []).append(clausula)
    for clausula, candidatas in alineadas:
        _cifras_e_inicio(clausula, candidatas, preparadas, completas, salida)
        # Modal, negación, excepciones, cuantificadores y sujeto: frente a la mejor oración,
        # si comparte al menos ``MINIMO_RAICES_SECUNDARIAS`` raíces y no está incompleta.
        if not candidatas or candidatas[0][1] < MINIMO_RAICES_SECUNDARIAS or candidatas[0][2].incompleta:
            continue
        puntaje, _, oracion, fuente = candidatas[0]
        hermanas = [c for c in por_oracion.get(id(oracion), []) if c is not clausula]
        propias = _secundarias(clausula, oracion, fuente, hermanas)
        # Alineación ambigua: un rival cercano (o con otro órgano) que cambia el resultado.
        rivales = [c for c in candidatas[1:]
                   if c[1] >= MINIMO_RAICES_SECUNDARIAS and not c[2].incompleta
                   and (c[0] >= FRACCION_RIVAL * puntaje or _organos_distintos(c[2], oracion))]
        codigos_propios = {s.codigo for s in propias}
        rival = next((c for c in rivales
                      if {s.codigo for s in _secundarias(
                          clausula, c[2], c[3], [h for h in por_oracion.get(id(c[2]), []) if h is not clausula])}
                      != codigos_propios), None)
        if rival is not None:
            donde = (f"de {fuente.descriptor}" if rival[3] is fuente
                     else f"(de {fuente.descriptor} y de {rival[3].descriptor})")
            salida.agregar(_senal(
                "alineacion.ambigua",
                f"la cláusula se alinea casi igual con dos oraciones {donde} que dan resultados distintos: el motor "
                "se abstiene; revisar a mano",
                clausula, [fuente] if rival[3] is fuente else [fuente, rival[3]], _ventana(oracion),
                None, _ventana(rival[2])))
            continue
        for senal in propias:
            salida.agregar(senal)
    return tuple(salida.senales)


# ── Cotejo del ledger ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FuenteFidelidad:
    """Artículo oficial contra el que se cotejó una afirmación."""

    descriptor: str
    ordenamiento: str | None
    articulo: str
    sha256_documento: str
    url: str
    ultima_reforma_dof: str | None
    origen: str  # "par_conforme" | "referencia"
    evidencias: tuple[str, ...] = ()
    referencia: str | None = None
    texto: str = ""
    truncado: bool = False

    def como_dict(self, *, con_texto: bool = False) -> dict:
        datos = {
            "descriptor": self.descriptor,
            "ordenamiento": self.ordenamiento,
            "articulo": self.articulo,
            "sha256_documento": self.sha256_documento,
            "url": self.url,
            "ultima_reforma_dof": self.ultima_reforma_dof,
            "origen": self.origen,
            "evidencias": list(self.evidencias),
            "referencia": self.referencia,
            "truncado": self.truncado,
        }
        if con_texto:
            datos["texto"] = self.texto
        return datos


@dataclass(frozen=True)
class ResultadoFidelidad:
    """Resultado de una afirmación: nunca CONFORME."""

    afirmacion: str
    indice: int  # posición en ``ledger.afirmaciones``
    tipo: str
    estado_declarado: str | None
    contenido_sha256: str
    resultado: str
    senales: tuple[Senal, ...] = ()
    fuentes: tuple[FuenteFidelidad, ...] = ()
    motivos: tuple[str, ...] = ()  # por qué NO_COTEJABLE
    notas: tuple[str, ...] = ()  # fuentes parciales, referencias no resueltas…

    @property
    def etiqueta(self) -> str:
        """Rótulo para mostrar: SIN_SENALES_DETECTADAS nunca se lee como validación."""
        if self.resultado == SIN_SENALES_DETECTADAS:
            return f"{SIN_SENALES_DETECTADAS} ({ETIQUETA_SIN_SENALES})"
        return self.resultado

    def como_dict(self) -> dict:
        return {
            "afirmacion": self.afirmacion,
            "tipo": self.tipo,
            "estado_declarado": self.estado_declarado,
            "contenido_sha256": self.contenido_sha256,
            "resultado": self.resultado,
            "etiqueta": self.etiqueta,
            "senales": [s.como_dict() for s in self.senales],
            "fuentes": [f.como_dict() for f in self.fuentes],
            "motivos": list(self.motivos),
            "notas": list(self.notas),
        }


@dataclass(frozen=True)
class FidelidadLedger:
    """Cotejo de fidelidad de todo el ledger (afirmaciones en alcance, en orden del ledger)."""

    afirmaciones: tuple[ResultadoFidelidad, ...]
    fuera_de_alcance: tuple[str, ...] = ()
    huella_ledger: str | None = None
    huella_paquete: str | None = None
    plan: str | None = None

    def resumen(self) -> dict[str, int]:
        conteo = {resultado: 0 for resultado in RESULTADOS}
        for resultado in self.afirmaciones:
            conteo[resultado.resultado] += 1
        senales = [s for r in self.afirmaciones for s in r.senales]
        conteo["senales"] = len(senales)
        conteo["alta"] = sum(s.precision == ALTA for s in senales)
        conteo["revisar"] = sum(s.precision == REVISAR for s in senales)
        conteo["contradicciones"] = sum(s.severidad == CONTRADICCION for s in senales)
        conteo["omisiones"] = sum(s.severidad == OMISION for s in senales)
        conteo["fuera_de_alcance"] = len(self.fuera_de_alcance)
        return conteo

    @property
    def nada_cotejable(self) -> bool:
        """Ninguna afirmación tuvo texto oficial que cotejar (o no hubo ninguna en alcance)."""
        return all(r.resultado == NO_COTEJABLE for r in self.afirmaciones)

    def problemas_correspondencia(self, ledger: Mapping[str, Any]) -> list[str]:
        if self.huella_ledger != huella_ledger(ledger):
            return ["el cotejo de fidelidad se calculó sobre otro contenido del ledger: volver a cotejar"]
        return []

    def como_dict(self) -> dict:
        return {
            "esquema": ESQUEMA_FIDELIDAD,
            "version_motor": VERSION_MOTOR,
            "huella_ledger": self.huella_ledger,
            "huella_paquete": self.huella_paquete,
            "aviso": AVISO,
            "resumen": self.resumen(),
            "nada_cotejable": self.nada_cotejable,
            "fuera_de_alcance": list(self.fuera_de_alcance),
            "afirmaciones": [r.como_dict() for r in self.afirmaciones],
        }


def _leyes_por_ordenamiento(paquete: Any) -> dict[str, list[tuple[str, str]]]:
    """Sigla → [(sha256 del original, URL)] de las leyes del paquete con ordenamiento fijado
    por archivo **y** título del encabezado (``ordenamiento_de``)."""
    leyes: dict[str, list[tuple[str, str]]] = {}
    for item in getattr(paquete, "registros", ()):
        registro = item.registro
        if not isinstance(registro, Mapping) or registro.get("tipo") != TIPO_LEY_LEYESBIBLIO:
            continue
        metadatos = registro.get("metadatos") or {}
        sigla, _ = ordenamiento_de(metadatos.get("archivo"), metadatos.get("titulo"))
        sha = (registro.get("original") or {}).get("sha256")
        url = (registro.get("fuente") or {}).get("url")
        if sigla and isinstance(sha, str) and isinstance(url, str):
            par = (sha, url)
            if par not in leyes.setdefault(sigla, []):
                leyes[sigla].append(par)
    return leyes


def _ubicar_mencion(documento: DocumentoLeyesBiblio, clave: str) -> tuple[CoincidenciaArticulo | None, str]:
    """Artículo único en el cuerpo para la clave de ``menciones`` ("art. 113 bis", "art. 1").

    Como en la identidad, el ordinal no distingue ("art. 1" es el "1o."): si no hay
    encabezado exacto, se acepta la única variante del cuerpo con la misma clave
    (``clave_articulo``). Nunca se elige entre varias.
    """
    identificador = clave.split(" ", 1)[1] if " " in clave else clave
    ubicado = ubicar_articulo(documento, identificador)
    if ubicado.unica is not None:
        return ubicado.unica, ""
    if not ubicado.coincidencias:
        variantes = {c.identificador for c in ubicado.variantes_cercanas if clave_articulo(c.identificador) == clave}
        if len(variantes) == 1:
            ubicado = ubicar_articulo(documento, variantes.pop())
            if ubicado.unica is not None:
                return ubicado.unica, ""
    codigos = [a.get("codigo") for a in ubicado.advertencias if a.get("codigo") != "sin_frontera_transitorios"]
    return None, ", ".join(c for c in codigos if c) or "sin ubicación única"


def _fuentes_de(
    afirmacion: Mapping[str, Any],
    agregado: Any,
    evidencias: Mapping[str, list[Mapping[str, Any]]],
    paquete: Any,
    leyes: Mapping[str, list[tuple[str, str]]],
    extractores: Sequence[Extractor],
    cache: dict,
) -> tuple[list[FuenteFidelidad], list[str], list[str], bool]:
    """(fuentes, motivos, notas, completas) de una afirmación."""
    fuentes: list[FuenteFidelidad] = []
    motivos: list[str] = []
    notas: list[str] = []
    completas = True
    conformes = [p for p in agregado.pares
                 if p.resultado == CONFORME and p.tipo_fuente == TIPO_LEY_LEYESBIBLIO and p.articulo_fuente
                 and not p.encabezado]
    otros = [p for p in agregado.pares if p not in conformes]
    if conformes:
        vistos: dict[tuple[str, str], int] = {}
        for par in conformes:
            candidatas = evidencias.get(par.evidencia) or []
            url = candidatas[0].get("url") if len(candidatas) == 1 else None
            clave = (par.sha256_documento or "", par.articulo_fuente)
            if clave in vistos:
                fuente = fuentes[vistos[clave]]
                fuentes[vistos[clave]] = replace(fuente, evidencias=fuente.evidencias + (par.evidencia,))
                continue
            try:
                consulta = consultar_articulo(paquete, articulo=par.articulo_fuente, sha256=par.sha256_documento,
                                              url=url, extractores=extractores, cache=cache)
            except ValueError as error:
                notas.append(f"{par.evidencia}: el artículo del par CONFORME no se pudo releer ({error})")
                completas = False
                continue
            if consulta.tramo is None:
                notas.append(f"{par.evidencia}: el artículo del par CONFORME no se pudo releer")
                completas = False
                continue
            sigla = consulta.ordenamiento
            vistos[clave] = len(fuentes)
            fuentes.append(FuenteFidelidad(
                f"art. {consulta.articulo} {sigla}" if sigla else f"art. {consulta.articulo} ({consulta.archivo})",
                sigla, consulta.articulo, consulta.sha256_documento, consulta.url, consulta.ultima_reforma_dof,
                "par_conforme", (par.evidencia,), None, consulta.tramo.texto, consulta.tramo.truncado))
        for par in otros:
            completas = False
            notas.append(f"{par.evidencia} ({par.resultado}"
                         + (", cabecera del compilado" if par.encabezado else "")
                         + "): no aporta texto de artículo; lo que solo ella sostiene no se coteja")
        return fuentes, motivos, notas, completas

    if agregado.pares:
        completas = False
        notas.append("ninguna evidencia citada es un artículo de ley CONFORME en la identidad ("
                     + ", ".join(f"{p.evidencia}: {p.resultado}" for p in agregado.pares)
                     + "); se resuelven sus referencias")
    for referencia in afirmacion.get("referencias") or []:
        if not isinstance(referencia, str):
            continue
        for mencion in extraer_menciones(referencia):
            if mencion.tipo == RANGO:
                completas = False
                notas.append(f"referencia «{referencia}»: rango largo sin resolver ({mencion.normalizada})")
                continue
            if mencion.tipo != ARTICULO:
                continue
            nombre = mencion.normalizada
            if mencion.ley is None:
                completas = False
                motivos.append(f"referencia «{referencia}»: {nombre} sin ordenamiento identificable")
                continue
            candidatas = leyes.get(mencion.ley, [])
            if len(candidatas) != 1:
                completas = False
                motivos.append(
                    f"referencia «{referencia}»: el paquete no tiene registrada la ley {mencion.ley}" if not candidatas
                    else f"referencia «{referencia}»: {len(candidatas)} registros de {mencion.ley} en el paquete "
                    "(ambiguo, no se elige)")
                continue
            sha, url = candidatas[0]
            ley = ley_registrada(paquete, sha256=sha, url=url, extractores=extractores, cache=cache)
            if ley.motivos or ley.documento is None:
                completas = False
                motivos.append(f"referencia «{referencia}»: la ley {mencion.ley} no se acredita en el paquete ("
                               + "; ".join(m.resumen() for m in ley.motivos[:2]) + ")")
                continue
            coincidencia, problema = _ubicar_mencion(ley.documento, mencion.clave)
            if coincidencia is None:
                completas = False
                motivos.append(f"referencia «{referencia}»: {nombre} no se ubica sin ambigüedad en el cuerpo "
                               f"({problema}); esto no acredita que no exista")
                continue
            tramo = tramo_articulo(ley.documento, coincidencia)
            identificador = coincidencia.identificador.rstrip(".").strip()
            if any(f.sha256_documento == sha and f.articulo == identificador for f in fuentes):
                continue
            fuentes.append(FuenteFidelidad(
                f"art. {identificador} {mencion.ley}", mencion.ley, identificador, sha, url, ley.ultima_reforma_dof,
                "referencia", (), referencia, tramo.texto, tramo.truncado))
    if not fuentes and not motivos:
        if not (afirmacion.get("referencias") or []) and not agregado.pares:
            motivos.append("la afirmación no cita evidencias ni referencias")
        else:
            motivos.append("sin fuente cotejable: ninguna evidencia citada es un artículo de ley CONFORME en la "
                           "identidad y las referencias no nombran un artículo con su ley («art. N SIGLA»)")
    return fuentes, motivos, notas, completas


def _huella_de_paquete(paquete: Any) -> str | None:
    huella = getattr(paquete, "huella", None)
    return huella() if callable(huella) else None


def cotejar_fidelidad(
    ledger: Mapping[str, Any],
    paquete: Any,
    *,
    cotejo: CotejoLedger | None = None,
    extractores: Sequence[Extractor] = (),
    cache: dict | None = None,
) -> FidelidadLedger:
    """Coteja la fidelidad de cada afirmación ``texto_normativo``, ``inferencia`` o
    ``propuesta`` contra el texto oficial de su artículo (ver el docstring del módulo).

    ``cotejo`` es el cotejo de identidad del mismo ledger (si falta, se calcula con el
    mismo ``cache``); uno de otro contenido lanza ``ValueError``. Lanza ``LedgerInvalido``
    si el ledger no cumple ``plan-ledger/1.0``. Nunca aprueba ni cambia estados.
    """
    errores = validar_esquema(ledger)
    if errores:
        raise LedgerInvalido(errores)
    cache = {} if cache is None else cache
    extractores = tuple(extractores)
    if cotejo is None:
        cotejo = cotejar_ledger(ledger, paquete, extractores=extractores, cache=cache)
    problemas = cotejo.problemas_correspondencia(ledger)
    afirmaciones = ledger.get("afirmaciones") or []
    if problemas or [a.afirmacion for a in cotejo.afirmaciones] != [str(a["id"]) for a in afirmaciones]:
        raise ValueError("el cotejo de identidad no corresponde a este ledger: "
                         + ("; ".join(problemas) or "afirmaciones distintas"))
    evidencias: dict[str, list[Mapping[str, Any]]] = {}
    for evidencia in ledger.get("evidencias") or []:
        evidencias.setdefault(evidencia["id"], []).append(evidencia)
    leyes = _leyes_por_ordenamiento(paquete)
    resultados: list[ResultadoFidelidad] = []
    fuera: list[str] = []
    for indice, (afirmacion, agregado) in enumerate(zip(afirmaciones, cotejo.afirmaciones)):
        tipo = afirmacion["tipo"]
        if tipo not in TIPOS_COTEJABLES:
            fuera.append(str(afirmacion["id"]))
            continue
        estado = normalizar_estado(afirmacion["verificacion"].get("estado"))
        base = dict(afirmacion=str(afirmacion["id"]), indice=indice, tipo=tipo, estado_declarado=estado,
                    contenido_sha256=contenido_sha256(afirmacion))
        if estado == INEXISTENTE:
            resultados.append(ResultadoFidelidad(**base, resultado=NO_COTEJABLE, motivos=(
                "INEXISTENTE: la inexistencia exige prueba positiva; no hay texto que cotejar",)))
            continue
        fuentes, motivos, notas, completas = _fuentes_de(
            afirmacion, agregado, evidencias, paquete, leyes, extractores, cache)
        if not fuentes:
            resultados.append(ResultadoFidelidad(**base, resultado=NO_COTEJABLE, motivos=tuple(motivos),
                                                 notas=tuple(notas)))
            continue
        if motivos:
            notas = [*notas, *(f"fuente parcial: {m}" for m in motivos)]
        if any(f.truncado for f in fuentes):
            notas.append("fuente truncada: el artículo puede continuar en páginas no incluidas en el registro; no "
                         "se emiten señales que dependan de una ausencia en ella")
        if not completas:
            notas.append("fuentes parciales: las cifras que no aparecen en el texto cotejado no se señalan")
        senales = comparar(
            afirmacion["texto"],
            [FuenteTexto(f.descriptor, f.texto, f.sha256_documento, f.articulo, f.truncado) for f in fuentes],
            fuentes_completas=completas,
        )
        resultados.append(ResultadoFidelidad(
            **base, resultado=SENALES if senales else SIN_SENALES_DETECTADAS, senales=senales,
            fuentes=tuple(fuentes), notas=tuple(notas)))
    plan = ledger.get("plan") if isinstance(ledger.get("plan"), Mapping) else {}
    return FidelidadLedger(tuple(resultados), tuple(fuera), huella_ledger(ledger), _huella_de_paquete(paquete),
                           plan.get("id"))


# ── Decisiones humanas sobre señales de fidelidad (PL-020) ───────────────────


def _texto_utilizable(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip()) and not es_marcador_pendiente(valor)


def _documentos_declarados(valor: Any) -> set[str]:
    if isinstance(valor, str):
        valor = [valor]
    if not isinstance(valor, list):
        return set()
    return {v.strip().lower() for v in valor if isinstance(v, str) and v.strip()}


def problemas_decision_fidelidad(
    decision: Mapping[str, Any], afirmacion: Mapping[str, Any], senal: Senal, *, verificada: bool, plan: Any
) -> list[str]:
    """Por qué ``decision`` no atiende ``senal`` de ``afirmacion`` (``[]`` si la atiende).

    La decisión debe traer ``fidelidad`` con: ``plan`` (el ID del plan del ledger),
    ``afirmacion`` (su ID), ``contenido_sha256`` **vigente** de la afirmación,
    ``version_motor`` (``VERSION_MOTOR``) y, en ``senales``, una entrada por señal atendida
    con su ``huella`` vigente, ``codigo``, ``fuente`` (descriptor), ``articulo`` y
    ``sha256_documento`` (texto o lista); y un responsable humano. Para una afirmación
    VERIFICADO, además una ``resolucion`` no vacía y la decisión APROBADA (como PL-017).
    Si cambia el plan, el texto o tipo de la afirmación, la fuente, el artículo, los tramos
    de la señal o las reglas, deja de valer: una decisión vieja o ajena no atiende una
    señal nueva.
    """
    problemas = []
    motivo = problema_persona(decision.get("responsable"))
    if motivo:
        problemas.append(f"responsable no válido ({motivo})")
    datos = decision.get(CAMPO_DECISION_FIDELIDAD)
    if not isinstance(datos, Mapping):
        return problemas + [f"no declara {CAMPO_DECISION_FIDELIDAD} (plan, afirmación, contenido_sha256, "
                            "version_motor, señales con huella y resolución)"]
    if datos.get("plan") != plan:
        problemas.append(f"declara el plan {datos.get('plan')!r}, no {plan!r}")
    if datos.get("afirmacion") != afirmacion.get("id"):
        problemas.append(f"declara la afirmación {datos.get('afirmacion')!r}, no {afirmacion.get('id')}")
    sha = datos.get("contenido_sha256")
    if not (isinstance(sha, str) and sha.strip().lower() == contenido_sha256(afirmacion)):
        problemas.append("contenido_sha256 no es el vigente de la afirmación (falta o se editó el texto)")
    if datos.get("version_motor") != VERSION_MOTOR:
        problemas.append(f"version_motor {datos.get('version_motor')!r}: la vigente es {VERSION_MOTOR!r} "
                         "(las reglas cambiaron)")
    entradas = datos.get("senales")
    entrada = next((e for e in entradas if isinstance(e, Mapping) and e.get("huella") == senal.huella), None) \
        if isinstance(entradas, list) else None
    if entrada is None:
        problemas.append(f"no declara la huella vigente de la señal {senal.codigo} (señal nueva o cambiada)")
    else:
        if entrada.get("codigo") != senal.codigo:
            problemas.append(f"la entrada de la huella declara el código {entrada.get('codigo')!r}")
        if entrada.get("fuente") != senal.fuente or entrada.get("articulo") != senal.articulo:
            problemas.append("la entrada no declara la fuente y el artículo vigentes de la señal")
        if not senal.sha256_documentos or set(senal.sha256_documentos) - _documentos_declarados(
                entrada.get("sha256_documento")):
            problemas.append("no declara el sha256_documento vigente de la fuente (falta o la fuente cambió)")
    if verificada:
        if not _texto_utilizable(datos.get("resolucion")):
            problemas.append("resolución vacía o pendiente")
        if normalizar_estado(decision.get("estado"), admitir_aprobado=True) != APROBADO:
            problemas.append("no está APROBADA")
    return problemas


def decisiones_que_atienden(
    decisiones: Iterable[Mapping[str, Any]], afirmacion: Mapping[str, Any], senal: Senal, *, verificada: bool,
    plan: Any
) -> list[str]:
    """IDs de las decisiones que atienden la señal."""
    return [str(d.get("id")) for d in decisiones
            if not problemas_decision_fidelidad(d, afirmacion, senal, verificada=verificada, plan=plan)]


def senales_pendientes(
    resultado: ResultadoFidelidad, afirmacion: Mapping[str, Any], decisiones: Iterable[Mapping[str, Any]],
    *, verificada: bool, plan: Any
) -> list[Senal]:
    """Señales que ninguna decisión humana atiende."""
    decisiones = list(decisiones)
    return [s for s in resultado.senales
            if not decisiones_que_atienden(decisiones, afirmacion, s, verificada=verificada, plan=plan)]


def plantilla_decision(plan: Any, resultado: ResultadoFidelidad) -> dict:
    """Bloque de decisión listo para pegar en ``decisiones[]`` (los campos [ASIGNAR] son del
    responsable): liga el plan, la afirmación, su contenido, la versión del motor y la
    huella de cada señal."""
    return {
        "id": "[ASIGNAR]",
        "pregunta": f"¿Cómo se atienden las señales de fidelidad de {resultado.afirmacion}?",
        "responsable": "[ASIGNAR]",
        "estado": "[ASIGNAR]",
        "bloquea": [],
        CAMPO_DECISION_FIDELIDAD: {
            "plan": plan,
            "afirmacion": resultado.afirmacion,
            "contenido_sha256": resultado.contenido_sha256,
            "version_motor": VERSION_MOTOR,
            "senales": [
                {"huella": s.huella, "codigo": s.codigo, "fuente": s.fuente, "articulo": s.articulo,
                 "sha256_documento": list(s.sha256_documentos)}
                for s in resultado.senales
            ],
            "resolucion": "[ASIGNAR]",
        },
    }


def es_verificada(afirmacion: Mapping[str, Any]) -> bool:
    verificacion = afirmacion.get("verificacion")
    return isinstance(verificacion, Mapping) and normalizar_estado(verificacion.get("estado")) == VERIFICADO
