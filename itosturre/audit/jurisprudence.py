"""Rubros, fuerza vinculante y vigencia de las tesis citadas (funciones puras, stdlib).

R4d — Cotejo determinista del rubro (falla cerrado)
  ``cotejar_rubro`` compara el rubro INVOCADO en el escrito (``extraer_rubro_invocado`` en el
  texto que precede al registro, o ``extraer_rubro_posterior`` con un marcador pegado a su
  derecha) con el rubro REAL de la fuente, ambos normalizados con ``normalizar_rubro`` (NFKD
  sin acentos, casefold, sin signos de puntuación ni comillas, espacios colapsados; Regla 1 de
  CLAUDE.md).
  La normalización solo sirve para COMPARAR: al abogado se le muestra siempre el rubro
  original, con sus acentos. Resultados (``RUBRO_*``), en este orden:

    rubro_no_asociado   hay un rubro en el párrafo, pero su vínculo con este
                        registro es incierto (otra mención de tesis entre
                        ambos, varios rubros)                              → 🟡, nunca 🟢 ni 🔴
    parcial             truncado de forma explícita ("…", "...", "[…]") y
                        sus tramos aparecen en orden en el real            → 🟡, nunca 🟢
    coincide            igualdad normalizada, sin marca de supresión ni
                        texto omitido tras el marcador                     → puede ser 🟢
    discrepante         traslape de palabras normalizado < 40 %            → 🔴 bloqueante
    invertido           misma tesis con la polaridad cambiada
                        (``diferencias_polaridad``)                         → 🔴 bloqueante
    no_literal          cualquier otra diferencia (también texto omitido
                        entre el marcador y el rubro)                      → 🟡, nunca 🟢
    sin_rubro_invocado  el escrito no transcribe un rubro identificable:
                        la tesis solo acredita la existencia del registro  → 🟡
    sin_rubro_fuente    la fuente local no registra el rubro               → 🟡

  Ningún traslape concede 🟢: solo la igualdad normalizada. ``rubro_keywords`` (palabras de 5+
  letras) queda solo por compatibilidad: ignoraba "NO", "NI" y "SIN" (R4-D14) y no normalizaba
  los acentos (R4-D13).

R4d — Vigencia
  ``normalizar_vigencia`` nunca devuelve "vigente" sin un valor registrado por el corpus o el
  scraper: sin valor → ``no_consultada``; valor desconocido → ``no_reconocida`` (ninguno de
  los dos cambia el semáforo: criterio por defecto). Lee TODOS los campos de vigencia: una
  pérdida registrada en cualquiera prevalece, y dos valores distintos con dato son un
  conflicto (``en_conflicto``, 🟡 mínimo). Ver docs/PROTOCOLO_VVCA.md §3 bis.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Optional


def rubro_keywords(text: str) -> set[str]:
    """Extrae palabras significativas de un rubro para comparar la cita con el corpus.

    Desde R4d el cotejo del rubro NO la usa (ver ``cotejar_rubro``): se conserva por
    compatibilidad con quien la importe."""
    stop = {
        "para", "como", "ante", "debe", "este", "esta", "dicho", "dicha",
        "donde", "cuando", "aunque", "entre", "sino", "cuyo", "cuya",
        "desde", "hasta", "sobre", "bajo", "cuales", "mismo", "misma",
    }
    return {
        word.lower()
        for word in re.findall(r"[A-Za-záéíóúÁÉÍÓÚüÜñÑ]{5,}", text)
        if word.lower() not in stop
    }


def _fuerza(
    sello: str,
    organo: str,
    obligatoria: bool,
    ambito: str,
    fundamento: str,
) -> dict:
    return {
        "sello": sello,
        "organo": organo,
        "obligatoria": obligatoria,
        "ambito": ambito,
        "fundamento": fundamento,
    }


_ROMANO = r"[IVXLCDM]+"


def classify_fuerza_vinculante(numero_tesis: str, tipo_tesis: str = "") -> dict:
    """Clasifica fuerza vinculante desde la clave, sin afirmar votaciones no verificadas."""
    up = (numero_tesis or "").strip().upper()
    es_jur = bool(re.search(r"/J\.|J/\d", up)) or bool(
        re.search(r"jurisprudencia", tipo_tesis or "", re.I)
    )

    if re.match(r"P\./J\.", up):
        return _fuerza(
            "[J-PLENO]", "Pleno de la SCJN", True, "nacional",
            "art. 217 LA — jurisprudencia obligatoria (Pleno de la SCJN)",
        )
    if re.match(r"[1-4]A\./J\.", up):
        return _fuerza(
            "[J-SALA]", "Sala de la SCJN", True, "nacional",
            "art. 217 LA — jurisprudencia obligatoria (Sala de la SCJN)",
        )
    if re.match(r"PR\.", up):
        return _fuerza(
            "[PR]", "Pleno Regional", True, "regional",
            "Acuerdo General 5/2021 — obligatoria en la región (Pleno Regional)",
        )
    if re.match(r"PC\.", up):
        return _fuerza(
            "[PC]", "Pleno de Circuito", True, "circuito",
            "art. 217 LA — obligatoria en el circuito (Pleno de Circuito)",
        )
    if es_jur:
        return _fuerza(
            "[J-TCC]", "Tribunal Colegiado de Circuito", True, "circuito",
            "art. 217 LA — jurisprudencia de TCC (obligatoria en su circuito)",
        )
    if re.match(r"(?:[1-4]A|P)\.\s*" + _ROMANO + r"\b", up):
        return _fuerza(
            "[SCJN-P]", "SCJN — tesis aislada / posible precedente", False, "orientadora",
            "Tesis aislada de la SCJN — orientadora; verificar si es precedente "
            "obligatorio por mayoría calificada (reforma art. 94 CPEUM 2021)",
        )
    return _fuerza(
        "[TA]", "Tesis aislada", False, "orientadora",
        "Tesis aislada — orientadora, no obligatoria (art. 217 LA a contrario)",
    )


# ─────────────────────────────────────────
# R4d — NORMALIZACIÓN DEL RUBRO (Regla 1 de CLAUDE.md)
# ─────────────────────────────────────────
# Umbral del 🔴 por traslape: el de siempre (R4d no cambia umbrales).
UMBRAL_TRASLAPE_RUBRO = 0.40

RUBRO_COINCIDE = "coincide"
RUBRO_PARCIAL = "parcial"
RUBRO_NO_LITERAL = "no_literal"
RUBRO_DISCREPANTE = "discrepante"
RUBRO_INVERTIDO = "invertido"
RUBRO_SIN_INVOCADO = "sin_rubro_invocado"
RUBRO_SIN_FUENTE = "sin_rubro_fuente"
RUBRO_NO_ASOCIADO = "rubro_no_asociado"
# Rubro discrepante: bloquea el documento (regla absoluta 2 de CLAUDE.md).
RUBRO_BLOQUEANTE = frozenset({RUBRO_DISCREPANTE, RUBRO_INVERTIDO})
# Sin cotejo del rubro: la tesis solo acredita la existencia del registro.
RUBRO_SIN_COTEJO = frozenset({RUBRO_SIN_INVOCADO, RUBRO_SIN_FUENTE, RUBRO_NO_ASOCIADO})

# Palabras vacías (artículos, contracciones, preposiciones, conjunciones y pronombres átonos):
# lista CERRADA que no cuenta en el traslape, para que dos rubros ajenos no se parezcan solo por
# "de", "la" o "en". Las palabras cortas con contenido ("ley", "pena", "acto") sí cuentan, y las
# negaciones ("no", "ni", "sin") nunca son vacías.
PALABRAS_VACIAS = frozenset({
    "el", "la", "los", "las", "lo", "un", "una", "unos", "unas", "al", "del",
    "a", "ante", "bajo", "con", "contra", "de", "desde", "durante", "en", "entre", "hacia",
    "hasta", "mediante", "para", "por", "segun", "sobre", "tras",
    "y", "e", "o", "u", "que", "como", "cuando", "si", "pero", "sino", "aunque",
    "se", "su", "sus", "le", "les",
})


# Palabra o identificador: letras y dígitos unidos por ".", ",", "/" o "-" ("1.4.14", "69-b",
# "1/4/14", "162"). El separador solo se conserva si lo toca un dígito.
_IDENTIFICADOR_RE = re.compile(r"[^\W_]+(?:[.,/-][^\W_]+)*")
_SEPARADOR_ENTRE_LETRAS_RE = re.compile(r"(?<=[^\d])[.,/-](?=[^\d])")


def normalizar_rubro(texto: str) -> str:
    """Forma de COMPARACIÓN de un rubro (Regla 1): NFKD sin marcas diacríticas, casefold, sin
    signos de puntuación ni comillas y con los espacios colapsados ("PETICIÓN." == "peticion").

    NFKD es la descomposición canónica (NFD) más la de compatibilidad: así "1º" y "1o"
    coinciden; el signo de grado ("1°") se lee como "o". Ronda 2: la estructura de números,
    rangos y designaciones normativas se conserva: el separador que toca un dígito no se borra
    ("REGLA 1.4.14." → "regla 1.4.14", distinta de "1/4/14"; "ARTÍCULO 69-B" → "articulo
    69-b", distinta de "69 B"); solo los acentos, las mayúsculas, los espacios y la puntuación
    no numérica se normalizan. Al abogado se le muestra siempre el rubro original, con acentos."""
    texto = (texto or "").replace("°", "o")
    descompuesto = unicodedata.normalize("NFKD", texto)
    sin_marcas = "".join(c for c in descompuesto if unicodedata.category(c) != "Mn").casefold()
    palabras: list[str] = []
    for token in _IDENTIFICADOR_RE.findall(sin_marcas):
        palabras.extend(_SEPARADOR_ENTRE_LETRAS_RE.sub(" ", token).split())
    return " ".join(palabras)


def palabras_rubro(texto: str) -> list[str]:
    """Palabras normalizadas del rubro, en orden (incluidas las cortas)."""
    return normalizar_rubro(texto).split()


def traslape_rubro(a: str, b: str) -> Optional[float]:
    """Proporción de palabras normalizadas en común, sobre el texto con menos palabras: la
    fórmula de siempre, ahora con NFKD y sin descartar las palabras de menos de 5 letras (solo
    las ``PALABRAS_VACIAS``). Es informativa y decide el 🔴 por debajo de 40 %; nunca concede
    🟢. None si alguno de los dos no tiene palabras."""
    pa = {p for p in palabras_rubro(a) if p not in PALABRAS_VACIAS}
    pb = {p for p in palabras_rubro(b) if p not in PALABRAS_VACIAS}
    if not pa or not pb:
        return None
    return len(pa & pb) / min(len(pa), len(pb))


# ─────────────────────────────────────────
# R4d — POLARIDAD DEL RUBRO (R4-D14). Lista CERRADA; ampliarla es decisión del responsable.
# ─────────────────────────────────────────
# Negaciones: cuentan en total ("NO … NI …" y "NO … NO …" tienen la misma polaridad).
NEGACIONES = frozenset({
    "no", "ni", "sin", "nunca", "jamas", "tampoco", "ningun", "ninguno", "ninguna", "nadie",
    "nada",
})

# Antónimos por prefijo negativo: la forma NEGATIVA cuenta como una marca de polaridad, por par
# ("ES IMPROCEDENTE" frente a "ES PROCEDENTE"). Clave: la forma positiva, solo para el mensaje.
ANTONIMOS_NEGATIVOS = {
    "procedente": ("improcedente", "improcedentes", "improcedencia"),
    "legal": ("ilegal", "ilegales", "ilegalidad"),
    "constitucional": ("inconstitucional", "inconstitucionales", "inconstitucionalidad"),
    "aplicable": ("inaplicable", "inaplicables", "inaplicabilidad"),
    "válido": ("invalido", "invalida", "invalidos", "invalidas", "invalidez"),
    "lícito": ("ilicito", "ilicita", "ilicitos", "ilicitas", "ilicitud"),
    "competente": ("incompetente", "incompetentes", "incompetencia"),
    "fundado": ("infundado", "infundada", "infundados", "infundadas"),
    "operante": ("inoperante", "inoperantes", "inoperancia"),
    "eficaz": ("ineficaz", "ineficaces", "ineficacia"),
    "existente": ("inexistente", "inexistentes", "inexistencia"),
    "prescriptible": ("imprescriptible", "imprescriptibles", "imprescriptibilidad"),
    "admisible": ("inadmisible", "inadmisibles", "inadmisibilidad"),
    "justificado": ("injustificado", "injustificada", "injustificados", "injustificadas"),
    "necesario": ("innecesario", "innecesaria", "innecesarios", "innecesarias"),
    "exigible": ("inexigible", "inexigibles", "inexigibilidad"),
    "suficiente": ("insuficiente", "insuficientes", "insuficiencia"),
    "imputable": ("inimputable", "inimputables", "inimputabilidad"),
}

# Pares simétricos (ninguna forma es un "no"): el sentido se invierte si los dos rubros
# mencionan el par y no con los mismos lados ("DEBE CONCEDERSE" frente a "DEBE NEGARSE").
PARES_SIMETRICOS = {
    ("conceder", "negar"): (
        ("concede", "conceden", "conceder", "concederse", "concedida", "concedido",
         "concedidas", "concedidos", "otorga", "otorgan", "otorgar", "otorgarse", "otorgada",
         "otorgado"),
        ("niega", "niegan", "negar", "negarse", "negada", "negado", "negadas", "negados",
         "deniega", "deniegan", "denegar", "denegarse", "denegada", "denegado"),
    ),
    ("oportuno", "extemporáneo"): (
        ("oportuno", "oportuna", "oportunos", "oportunas", "oportunamente"),
        ("extemporaneo", "extemporanea", "extemporaneos", "extemporaneas",
         "extemporaneamente"),
    ),
    ("permitir", "prohibir"): (
        ("permite", "permiten", "permitido", "permitida", "permitidos", "permitidas"),
        ("prohibe", "prohiben", "prohibido", "prohibida", "prohibidos", "prohibidas"),
    ),
    ("obligatorio", "optativo"): (
        ("obligatorio", "obligatoria", "obligatorios", "obligatorias"),
        ("optativo", "optativa", "optativos", "optativas", "potestativo", "potestativa",
         "potestativos", "potestativas"),
    ),
}


def _lados(con_a: int, con_b: int, nombres: tuple[str, str]) -> str:
    usados = [nombre for nombre, n in zip(nombres, (con_a, con_b)) if n]
    return " y ".join(f"«{nombre}»" for nombre in usados)


def diferencias_polaridad(invocado: str, real: str) -> list[str]:
    """Diferencias de polaridad entre el rubro invocado y el real (R4d, R4-D14).

    - Negaciones (``NEGACIONES``, en total) y formas negativas de ``ANTONIMOS_NEGATIVOS`` (por
      par): cuentan distinto en uno y otro rubro ("NO ES COMPUTABLE" frente a "ES
      COMPUTABLE"; "ES IMPROCEDENTE" frente a "ES PROCEDENTE").
    - ``PARES_SIMETRICOS``: ambos rubros mencionan el par y no con los mismos lados.
    Devuelve una descripción por diferencia; [] = misma polaridad."""
    pi = Counter(palabras_rubro(invocado))
    pr = Counter(palabras_rubro(real))
    diferencias = []

    def contar(conteo: Counter, formas) -> int:
        return sum(conteo[forma] for forma in formas)

    neg_i, neg_r = contar(pi, NEGACIONES), contar(pr, NEGACIONES)
    if neg_i != neg_r:
        diferencias.append(
            f"negaciones (no, ni, sin, nunca…): {neg_i} en el rubro invocado y {neg_r} en el real"
        )
    for positiva, negativas in ANTONIMOS_NEGATIVOS.items():
        ci, cr = contar(pi, negativas), contar(pr, negativas)
        if ci != cr:
            diferencias.append(
                f"«{negativas[0]}» (antónimo de «{positiva}»): {ci} en el rubro invocado y "
                f"{cr} en el real"
            )
    for nombres, (formas_a, formas_b) in PARES_SIMETRICOS.items():
        ia, ib = contar(pi, formas_a), contar(pi, formas_b)
        ra, rb = contar(pr, formas_a), contar(pr, formas_b)
        if (ia or ib) and (ra or rb) and (bool(ia), bool(ib)) != (bool(ra), bool(rb)):
            diferencias.append(
                f"{_lados(1, 1, nombres)}: el rubro invocado dice {_lados(ia, ib, nombres)} y "
                f"el real {_lados(ra, rb, nombres)}"
            )
    return diferencias


# ─────────────────────────────────────────
# R4d — RUBRO INVOCADO EN EL ESCRITO
# ─────────────────────────────────────────
# Marcador explícito del rubro: "de rubro:", "cuyo rubro es", "de título y subtítulo:", "lleva
# por título", "bajo el epígrafe", "intitulada". "título" solo cuenta en esas frases ("a título
# de ejemplo" no es un marcador).
_MARCADOR_RUBRO_RE = re.compile(
    r"\b(?:rubro|t[íi]tulo\s+y\s+subt[íi]tulo|ep[íi]grafe|(?:in)?titulad[oa]"
    r"|(?:lleva\s+por|con\s+el|bajo\s+el|cuyo)\s+t[íi]tulo)\b",
    re.IGNORECASE,
)
# Varios rubros en el párrafo ("de rubros «A» y «B»"): no se sabe cuál es el de cada registro.
_MARCADOR_PLURAL_RE = re.compile(r"\b(?:rubros|t[íi]tulos\s+y\s+subt[íi]tulos)\b",
                                 re.IGNORECASE)
# Fórmulas introductorias que pueden mediar entre el marcador y el rubro (lista CERRADA, en su
# forma normalizada): "de rubro y texto siguientes: «…»", "cuyo rubro es: …", "que a la letra
# dice". Cualquier otro texto omitido ("de rubro: no es cierto que …") impide "coincide".
FORMULAS_INTRODUCTORIAS = frozenset({
    "", "es", "son", "dice", "dicen", "reza", "siguiente", "siguientes", "literal",
    "literalmente", "es el siguiente", "son los siguientes", "que dice", "que dicen", "que reza",
    "que a la letra dice", "que a la letra dicen", "a la letra", "a la letra dice",
    "del tenor siguiente", "del tenor literal siguiente", "y texto", "y textos",
    "y texto siguiente", "y texto siguientes", "y textos siguientes", "y texto que dice",
    "y texto que dicen", "y texto que a la letra dicen", "y texto es", "y texto son",
    "y texto son los siguientes", "y texto del tenor siguiente",
})
# Texto entre comillas (rectas, curvas, angulares, simples) o en negritas de Markdown.
_SEGMENTO_RE = re.compile(
    r'"(?P<recta>[^"]+)"|“(?P<curva>[^”]+)”|«(?P<angular>[^»]+)»|‘(?P<simple>[^’]+)’'
    r"|'(?P<apostrofo>[^']+)'|\*\*(?P<negrita>.+?)\*\*|__(?P<subrayado>.+?)__",
    re.DOTALL,
)
# Supresión explícita: "[…]", "[...]", "(…)", "(...)", "…" o tres o más puntos.
_MARCA_TRUNCAMIENTO_RE = re.compile(
    r"\[\s*(?:…|\.{3,})\s*\]|\(\s*(?:…|\.{3,})\s*\)|…|\.{3,}"
)
# Salto de párrafo: una línea en blanco (también la de una cita en bloque de Markdown, "> ").
_SALTO_PARRAFO_RE = re.compile(r"\n[ \t>]*\n")
_TOKEN_RE = re.compile(r"\S+")
# Mención de una tesis entre el rubro y el registro (ronda 2, punto 4): corta el vínculo salvo
# que sea la etiqueta de la clave ("tesis 2a./J. 58/2010", "Tesis: P./J. 20/2014"), la del tipo
# ("Tipo: Jurisprudencia") o vaya seguida solo de calificativos ("jurisprudencia obligatoria").
_MENCION_TESIS_RE = re.compile(
    r"\b(?:tesis|jurisprudencias?|criterios?|precedentes?|ejecutorias?)\b", re.IGNORECASE
)
_ETIQUETA_TIPO_RE = re.compile(
    r"\btipo(?:\s+de\s+tesis)?\s*:\s*(?:jurisprudencia|aislada)\b", re.IGNORECASE
)
_CALIFICATIVOS_TESIS = frozenset({
    "obligatoria", "aislada", "jurisprudencial", "aplicable", "citada", "invocada", "referida",
    "mencionada", "transcrita",
})
# Órganos, publicaciones y encabezados (lista CERRADA, normalizada): un texto en mayúsculas
# hecho solo de estas palabras ("SUPREMA CORTE DE JUSTICIA DE LA NACIÓN", "PRIMER TRIBUNAL
# COLEGIADO EN MATERIA PENAL DEL TERCER CIRCUITO", "JURISPRUDENCIA APLICABLE AL CASO") no es un
# rubro (ronda 2, punto 6).
VOCABULARIO_ORGANOS_Y_ENCABEZADOS = frozenset({
    "suprema", "corte", "justicia", "nacion", "scjn", "sala", "salas", "pleno", "plenos",
    "regional", "regionales", "region", "circuito", "circuitos", "tribunal", "tribunales",
    "colegiado", "colegiados", "colegiada", "unitario", "juzgado", "juzgados", "distrito",
    "juez", "jueza", "magistrado", "magistrada", "materia", "materias", "penal", "civil",
    "administrativa", "administrativo", "trabajo", "laboral", "comun", "semanario", "judicial",
    "federacion", "gaceta", "epoca", "consejo", "judicatura", "federal", "poder", "residencia",
    "ciudad", "mexico", "jalisco", "guadalajara", "zapopan", "primera", "primer", "primero",
    "segunda", "segundo", "tercera", "tercer", "tercero", "cuarta", "cuarto", "quinta", "quinto",
    "sexta", "sexto", "septima", "septimo", "octava", "octavo", "novena", "noveno", "decima",
    "decimo", "undecima", "duodecima", "jurisprudencia", "jurisprudencias", "tesis", "aislada",
    "aisladas", "aplicable", "aplicables", "criterio", "criterios", "precedente", "precedentes",
    "agravio", "agravios", "unico", "concepto", "conceptos", "violacion", "considerando",
    "considerandos", "resultando", "resultandos", "antecedentes", "hechos", "derecho",
    "fundamentos", "puntos", "petitorios", "resolutivos", "capitulo", "seccion", "apartado",
    "caso", "concreto", "estudio", "fondo", "analisis", "marco", "juridico", "normativo",
    "cita", "citas", "sustento", "apoyo",
})
_ROMANO_NORMALIZADO_RE = re.compile(r"^[ivxlcdm]+$")


def _letras(token: str) -> int:
    return sum(1 for c in token if c.isalpha())


def _es_palabra(token: str) -> bool:
    """Palabra alfabética (2+ letras, sin dígitos)."""
    return _letras(token) >= 2 and not any(c.isdigit() for c in token)


def _califica(texto: str, minimo_palabras: int = 3, minimo_letras: int = 15) -> bool:
    """¿Tiene el tamaño mínimo de un rubro? (3+ palabras y 15+ letras; tras un marcador basta
    con 2 palabras y 8 letras)."""
    palabras = [t for t in texto.split() if _es_palabra(t)]
    return (len(palabras) >= minimo_palabras
            and sum(_letras(t) for t in palabras) >= minimo_letras)


def _predomina_mayuscula(texto: str) -> bool:
    """Al menos 80 % de las letras en mayúscula (sin contar los tokens con dígitos: "1o.")."""
    letras = [c for t in texto.split() if not any(d.isdigit() for d in t)
              for c in t if c.isalpha()]
    return bool(letras) and sum(1 for c in letras if c.isupper()) >= 0.8 * len(letras)


def _parece_organo_o_encabezado(texto: str) -> bool:
    """¿Todas sus palabras (salvo las vacías) son de órganos, publicaciones o encabezados, o
    números? ("SUPREMA CORTE DE JUSTICIA DE LA NACIÓN", "III. JURISPRUDENCIA APLICABLE")."""
    palabras = [p for p in palabras_rubro(texto) if p not in PALABRAS_VACIAS]
    return bool(palabras) and all(
        p in VOCABULARIO_ORGANOS_Y_ENCABEZADOS or _ROMANO_NORMALIZADO_RE.match(p) or p.isdigit()
        for p in palabras
    )


def _token_en_mayusculas(token: str) -> bool:
    """Token admisible en una corrida de mayúsculas: sin minúsculas, o con dígitos (ordinales
    "1o.", épocas "(10a.)", artículos "69-B")."""
    return any(c.isdigit() for c in token) or not any(c.islower() for c in token)


# Token de la clave o de los datos de publicación de una tesis, no del rubro: "P./J.", "J/7",
# "3/2019", "(10a.)", "I.5o.C.220", "XVII.2o.8", "PR.A.C.CN.".
_TOKEN_CLAVE_RE = re.compile(
    r"/|^\(\d{1,2}a\.\)[.,;:]*$|^\(?[IVXLCDM]+\.\d|^(?:[A-Z]{1,3}\.){2,}[,;:]?$"
)


def _token_fuera_del_rubro(token: str) -> bool:
    """Token que no puede abrir un rubro: de la clave, una numeración ("**1.**", "2.") o signos
    sueltos. Una marca de supresión ("…") sí puede abrirlo."""
    if _MARCA_TRUNCAMIENTO_RE.fullmatch(token.strip(".,;:")) or token.startswith("…"):
        return False
    return bool(_TOKEN_CLAVE_RE.search(token)) or not _es_palabra(token)


# Primer token de un encabezado ("##", "III.", "B)"). Una numeración arábiga ("1.", "2)") no:
# suele abrir un elemento de lista cuyo contenido puede ser el rubro; solo se recorta.
_ENCABEZADO_RE = re.compile(r"^(?:#+|\(?(?:[IVXLCDM]+|[A-Z])[.)])$")


def _inicio_de_linea(texto: str, posicion: int) -> bool:
    """¿Solo hay espacios (o la marca de cita "> ") entre el salto de línea previo y
    ``posicion``?"""
    return not texto[texto.rfind("\n", 0, posicion) + 1:posicion].strip(" \t>")


def _corridas_mayusculas(parrafo: str, enmascarado: str) -> list[tuple[int, int]]:
    """Corridas de tokens en mayúsculas fuera de comillas que tienen tamaño de rubro.

    La línea de un encabezado ("## III. JURISPRUDENCIA APLICABLE", "IV. AGRAVIOS DEL QUEJOSO")
    no es un rubro. Por la izquierda se recorta lo que no es palabra del rubro (la clave
    "P./J. 3/2019", una numeración "**1.**", signos sueltos); por la derecha, la corrida se
    corta en el primer token de una clave ("RUBRO. P./J. 1/2020 (10a.)" → "RUBRO.")."""
    grupos: list[list[re.Match]] = [[]]
    for token in _TOKEN_RE.finditer(enmascarado):
        if _token_en_mayusculas(token.group()):
            grupos[-1].append(token)
        elif grupos[-1]:
            grupos.append([])
    corridas = []
    for grupo in grupos:
        if (grupo and _ENCABEZADO_RE.match(grupo[0].group())
                and _inicio_de_linea(enmascarado, grupo[0].start())):
            # Se descarta la línea del encabezado; lo que sigue en otra línea aún puede serlo.
            fin_de_linea = enmascarado.find("\n", grupo[0].start())
            fin_de_linea = len(enmascarado) if fin_de_linea < 0 else fin_de_linea
            grupo = [token for token in grupo if token.start() > fin_de_linea]
        while grupo and _token_fuera_del_rubro(grupo[0].group()):
            grupo = grupo[1:]
        for i, token in enumerate(grupo[1:], start=1):
            if _TOKEN_CLAVE_RE.search(token.group()):
                grupo = grupo[:i]
                break
        if grupo:
            inicio, fin = grupo[0].start(), grupo[-1].end()
            if _califica(parrafo[inicio:fin]):
                corridas.append((inicio, fin))
    return corridas


def _candidatos(parrafo: str) -> tuple[list[dict], list[dict], list[int]]:
    """Segmentos entre comillas o negritas, corridas de mayúsculas y fin de cada marcador del
    rubro en ``parrafo`` (posiciones en el párrafo)."""
    segmentos = []
    enmascarado = list(parrafo)
    for m in _SEGMENTO_RE.finditer(parrafo):
        grupo = next(nombre for nombre in _SEGMENTO_RE.groupindex if m.group(nombre) is not None)
        segmentos.append({"inicio": m.start(), "fin": m.end(), "texto": m.group(grupo),
                          "metodo": "comillas"})
        enmascarado[m.start():m.end()] = " " * (m.end() - m.start())
    # Marcadores fuera de comillas. En mayúsculas solo cuentan seguidos de dos puntos ("RUBRO:
    # …"): "RUBRO" sin ellos puede ser una palabra del propio rubro. Se enmascaran para que la
    # corrida de mayúsculas que les sigue empiece después.
    marcadores = []
    for m in _MARCADOR_RUBRO_RE.finditer("".join(enmascarado)):
        dos_puntos = re.match(r"\s*:", "".join(enmascarado[m.end():]))
        if any(c.islower() for c in m.group()) or dos_puntos:
            fin = m.end() + (dos_puntos.end() if dos_puntos else 0)
            marcadores.append(fin)
            enmascarado[m.start():fin] = " " * (fin - m.start())
    corridas = [
        {"inicio": inicio, "fin": fin, "texto": parrafo[inicio:fin], "metodo": "mayusculas"}
        for inicio, fin in _corridas_mayusculas(parrafo, "".join(enmascarado))
    ]
    return segmentos, corridas, marcadores


def _primero_tras(segmentos: list[dict], corridas: list[dict], fin_marcador: int) -> Optional[dict]:
    """Primer texto entre comillas o negritas (cualquier caja) o corrida de mayúsculas que sigue
    al marcador. Lo que media entre ambos se revisa aparte (``_texto_omitido``)."""
    siguientes = sorted(
        [s for s in segmentos if s["inicio"] >= fin_marcador and _califica(s["texto"], 2, 8)]
        + [c for c in corridas if c["inicio"] >= fin_marcador],
        key=lambda c: c["inicio"],
    )
    return siguientes[0] if siguientes else None


def _texto_omitido(parrafo: str, marcadores: list[int], candidato: dict) -> Optional[str]:
    """Texto entre el último marcador anterior al rubro y el rubro que NO es una fórmula
    introductoria reconocida (ronda 2, punto 1): "de rubro: no es cierto que «…»" → "no es
    cierto que". None si no hay marcador previo o lo que media es una fórmula."""
    previos = [fin for fin in marcadores if fin <= candidato["inicio"]]
    if not previos:
        return None
    entre = parrafo[previos[-1]:candidato["inicio"]]
    if normalizar_rubro(entre) in FORMULAS_INTRODUCTORIAS:
        return None
    return " ".join(entre.split()).strip(" ,;:")


def _mencion_de_otra_tesis(entre: str) -> Optional[str]:
    """Mención de una tesis, jurisprudencia o criterio entre el rubro y el registro que no es la
    etiqueta de la clave o del tipo ni va seguida solo de calificativos (ronda 2, punto 4).
    Devuelve el fragmento para el motivo, o None."""
    limpio = _ETIQUETA_TIPO_RE.sub(" ", entre)
    for m in _MENCION_TESIS_RE.finditer(limpio):
        siguientes = limpio[m.end():].split()
        if any(_TOKEN_CLAVE_RE.search(token) for token in siguientes[:3]):
            continue
        resto = [p for p in palabras_rubro(" ".join(siguientes)) if p not in PALABRAS_VACIAS]
        if resto and all(p in _CALIFICATIVOS_TESIS for p in resto):
            continue
        return " ".join(limpio[max(0, m.start() - 25):m.end() + 25].split())
    return None


def _rubro(candidato: dict, metodo: str, parrafo: str) -> dict:
    texto = " ".join(candidato["texto"].split())
    return {"texto": texto, "metodo": metodo,
            "truncado": bool(_MARCA_TRUNCAMIENTO_RE.search(texto)),
            "parrafo": " ".join(parrafo.split())}


def extraer_rubro_invocado(contexto: str, *, recortado: bool = False) -> Optional[dict]:
    """Rubro que el escrito invoca para la tesis cuyo registro sigue a ``contexto`` (R4d).

    Solo se busca en el último párrafo de ``contexto`` (el del registro), en este orden:
      1. Tras el último marcador explícito ("rubro", "título y subtítulo", "epígrafe", "lleva
         por título", "intitulada"): el primer texto entre comillas o en negritas (en
         cualquier caja) o la primera corrida de mayúsculas que le sigue.
         ``metodo="marcador"``.
      2. Sin marcador: el texto entre comillas o negritas en mayúsculas, o la corrida de
         mayúsculas (3+ palabras, 15+ letras), más cercano al registro, que no sea solo un
         órgano, una publicación o un encabezado. ``metodo="comillas"`` o ``"mayusculas"``.
    Un texto entre comillas en minúsculas sin marcador NO se toma como rubro (suele citar el
    texto de la tesis o de una norma): la tesis queda sin rubro invocado.

    Devuelve ``{"texto", "metodo", "truncado", "parrafo"}`` con el texto original (acentos
    incluidos, espacios colapsados) o None, más, cuando aplican (ronda 2):
      - ``texto_omitido``: lo que media entre el marcador y el rubro si no es una fórmula
        introductoria (``FORMULAS_INTRODUCTORIAS``); impide "coincide";
      - ``asociacion_incierta``: motivo por el que el rubro puede no ser el de ESTE registro
        (otra mención de tesis entre ambos; varios rubros en el párrafo); la tesis queda 🟡.
    ``truncado``: marca explícita de supresión ("…", "...", "[…]"), o el rubro empieza en el
    borde de una ventana ``recortado``.
    """
    parrafos = _SALTO_PARRAFO_RE.split(contexto or "")
    parrafo = parrafos[-1]
    segmentos, corridas, marcadores = _candidatos(parrafo)

    candidato, metodo = None, None
    if marcadores:
        candidato = _primero_tras(segmentos, corridas, marcadores[-1])
        metodo = "marcador"
    if candidato is None:
        opciones = [
            s for s in segmentos if _califica(s["texto"]) and _predomina_mayuscula(s["texto"])
        ] + corridas
        opciones = [c for c in opciones if not _parece_organo_o_encabezado(c["texto"])]
        if opciones:
            candidato = max(opciones, key=lambda c: (c["fin"], c["metodo"] == "comillas"))
            metodo = candidato["metodo"]
    if candidato is None:
        return None

    rubro = _rubro(candidato, metodo, parrafo)
    omitido = _texto_omitido(parrafo, marcadores, candidato)
    if omitido:
        rubro["texto_omitido"] = omitido
    if _MARCADOR_PLURAL_RE.search(parrafo):
        rubro["asociacion_incierta"] = (
            "el párrafo invoca varios rubros: no se sabe cuál corresponde a este registro"
        )
    else:
        mencion = _mencion_de_otra_tesis(parrafo[candidato["fin"]:])
        if mencion:
            rubro["asociacion_incierta"] = (
                f"entre el rubro identificado y el registro hay otra mención de tesis "
                f"(«{mencion}»): el rubro puede ser de otra tesis"
            )
    # Ventana recortada: si el rubro empieza en su borde, pudo empezar antes (nunca 🟢 ni 🔴
    # por lo que no se vio: se trata como truncado al inicio).
    if (recortado and len(parrafos) == 1
            and not any(c.islower() for c in parrafo[:candidato["inicio"]])):
        rubro["truncado"] = True
        rubro["texto"] = "… " + rubro["texto"]
    return rubro


# Marcador pegado a la DERECHA del registro: "registro digital 164618, de rubro y texto: «…»";
# "Registro: 2006224, cuyo rubro es: …"; "…, de título y subtítulo: …"; "…, intitulada «…»".
_MARCADOR_POSTERIOR_RE = re.compile(
    r"\s*[,;]?\s*(?:(?:de|cuyo|con\s+el|bajo\s+el)\s+)?"
    r"(?:rubro|t[íi]tulo\s+y\s+subt[íi]tulo|ep[íi]grafe|(?:in)?titulad[oa])\b",
    re.IGNORECASE,
)


def extraer_rubro_posterior(texto: str) -> Optional[dict]:
    """Rubro que sigue al registro con un marcador PEGADO a él (R4d): "registro digital 164618,
    de rubro y texto: «…»". ``texto`` es lo que sigue al número del registro.

    Solo con el marcador al inicio de ``texto`` y en su primer párrafo; el rubro es el primer
    texto entre comillas o negritas o la primera corrida de mayúsculas tras el marcador, y lo
    que media debe ser una fórmula introductoria (si no, ``texto_omitido``).
    Devuelve el dict de ``extraer_rubro_invocado`` (``metodo="marcador_posterior"``) más
    ``fin``: la posición en ``texto`` donde termina el rubro (lo que sigue ya no es de esta
    tesis). None si no hay marcador pegado o rubro identificable."""
    parrafo = _SALTO_PARRAFO_RE.split(texto or "")[0]
    marcador = _MARCADOR_POSTERIOR_RE.match(parrafo)
    if not marcador:
        return None
    segmentos, corridas, marcadores = _candidatos(parrafo)
    fin_marcador = next((f for f in marcadores if f >= marcador.end()), None)
    if fin_marcador is None:
        return None
    candidato = _primero_tras(segmentos, corridas, fin_marcador)
    if candidato is None:
        return None
    rubro = _rubro(candidato, "marcador_posterior", parrafo)
    omitido = _texto_omitido(parrafo, [fin_marcador], candidato)
    if omitido:
        rubro["texto_omitido"] = omitido
    rubro["fin"] = candidato["fin"]
    return rubro


def _encaja_con_supresiones(texto: str, real_normalizado: str) -> bool:
    """¿Lo transcrito aparece en el real, en orden y SOLO con huecos donde el invocado marca la
    supresión? ("ES COMPUTABLE…" debe ser el INICIO del real; "… ES COMPUTABLE", su final)."""
    piezas = [normalizar_rubro(p) for p in _MARCA_TRUNCAMIENTO_RE.split(texto)]
    if not any(piezas):
        return False
    hueco = r"(?:\S+ )*"  # cero o más palabras suprimidas, completas
    patron = hueco.join(re.escape(p + " ") if p else "" for p in piezas)
    return re.fullmatch(patron, real_normalizado + " ") is not None


def _cotejo(resultado: str, motivo: str, traslape: Optional[float] = None,
            polaridad: Optional[list[str]] = None) -> dict:
    return {"resultado": resultado, "motivo": motivo, "traslape": traslape,
            "polaridad": list(polaridad or [])}


def _porcentaje(valor: Optional[float]) -> str:
    return "—" if valor is None else f"{round(valor * 100)} %"


def cotejar_rubro(invocado: Optional[dict], rubro_real: str) -> dict:
    """Cotejo determinista del rubro invocado contra el real (R4d; ver el docstring del módulo).

    ``invocado`` es el resultado de ``extraer_rubro_invocado`` (o None). Orden:
      1. Asociación incierta con el registro → ``rubro_no_asociado`` (🟡, nunca 🟢 ni 🔴).
      2. Marca de supresión (también la de una ventana recortada): nunca "coincide"; si lo
         transcrito encaja con el real → ``parcial``; si no, sigue en el paso 4.
      3. Igualdad normalizada → ``coincide``, salvo texto omitido entre el marcador y el rubro
         (→ ``no_literal``).
      4. Traslape < 40 % → ``discrepante`` (🔴). Si el rubro no vino tras un marcador, antes se
         mira el párrafo de la cita: si comparte 40 % o más de las palabras del real, el texto
         tomado como rubro pudo no serlo → ``no_literal`` (🟡).
      5. Polaridad distinta (``diferencias_polaridad``) → ``invertido`` (🔴).
      6. Cualquier otra diferencia → ``no_literal`` (🟡, nunca 🟢).
    Sin rubro invocado → ``sin_rubro_invocado``; sin rubro en la fuente → ``sin_rubro_fuente``.
    Devuelve ``{"resultado", "motivo", "traslape", "polaridad"}``.
    """
    real = " ".join((rubro_real or "").split())
    n_real = normalizar_rubro(real)
    if not n_real:
        return _cotejo(
            RUBRO_SIN_FUENTE,
            "la fuente local no registra el rubro de la tesis: no hubo cotejo del rubro",
        )
    texto = (invocado or {}).get("texto") or ""
    if not normalizar_rubro(texto):
        return _cotejo(
            RUBRO_SIN_INVOCADO,
            "el escrito no transcribe un rubro identificable para esta tesis (se reconoce tras "
            "«rubro» o «título y subtítulo», entre comillas en mayúsculas o en mayúsculas junto "
            "al registro): no hubo cotejo del rubro; la tesis solo acredita la existencia del "
            "registro",
        )
    traslape = traslape_rubro(texto, real)
    if invocado.get("asociacion_incierta"):
        return _cotejo(
            RUBRO_NO_ASOCIADO,
            f"{invocado['asociacion_incierta']}; no hubo cotejo del rubro y la tesis solo "
            f"acredita la existencia del registro",
            traslape,
        )
    omitido = invocado.get("texto_omitido")
    truncado = bool(invocado.get("truncado"))
    if truncado:
        if _encaja_con_supresiones(texto, n_real):
            return _cotejo(
                RUBRO_PARCIAL,
                "el rubro invocado está truncado de forma explícita y lo transcrito coincide "
                "con el real: no se cotejó el rubro completo",
                traslape,
            )
    elif normalizar_rubro(texto) == n_real:
        if not omitido:
            return _cotejo(
                RUBRO_COINCIDE,
                "el rubro invocado coincide literalmente con el real (comparación sin acentos, "
                "mayúsculas ni puntuación no numérica)",
                traslape,
            )
        return _cotejo(
            RUBRO_NO_LITERAL,
            f"el rubro coincide con el real, pero entre el marcador y el rubro hay texto que no "
            f"es una fórmula introductoria («{omitido}»): cotejar qué se afirma de la tesis",
            traslape,
        )
    if traslape is None or traslape < UMBRAL_TRASLAPE_RUBRO:
        if invocado.get("metodo") not in ("marcador", "marcador_posterior"):
            del_parrafo = traslape_rubro(invocado.get("parrafo") or "", real)
            if del_parrafo is not None and del_parrafo >= UMBRAL_TRASLAPE_RUBRO:
                return _cotejo(
                    RUBRO_NO_LITERAL,
                    f"el texto tomado como rubro no coincide con el real (traslape "
                    f"{_porcentaje(traslape)}), pero el párrafo de la cita comparte "
                    f"{_porcentaje(del_parrafo)} de sus palabras: cotejar qué rubro se invoca",
                    traslape,
                )
        return _cotejo(
            RUBRO_DISCREPANTE,
            f"el rubro invocado no coincide con el real (traslape {_porcentaje(traslape)}, "
            f"menor a {round(UMBRAL_TRASLAPE_RUBRO * 100)} %)",
            traslape,
        )
    polaridad = diferencias_polaridad(texto, real)
    if polaridad:
        return _cotejo(
            RUBRO_INVERTIDO,
            "sentido invertido: " + "; ".join(polaridad),
            traslape,
            polaridad,
        )
    detalle = (
        f"; además, entre el marcador y el rubro hay texto omitido («{omitido}»)" if omitido
        else ""
    )
    if truncado:
        motivo = (f"el rubro invocado está truncado y lo transcrito no encaja con el real "
                  f"(traslape {_porcentaje(traslape)}; sin inversión de sentido detectada)"
                  f"{detalle}: cotejar")
    else:
        motivo = (f"el rubro invocado no coincide literalmente con el real (traslape "
                  f"{_porcentaje(traslape)}; sin inversión de sentido detectada){detalle}: "
                  f"cotejar")
    return _cotejo(RUBRO_NO_LITERAL, motivo, traslape)


# ─────────────────────────────────────────
# R4d — VIGENCIA DEL CRITERIO
# ─────────────────────────────────────────
ESTADOS_VIGENCIA = ("vigente", "superada", "interrumpida", "sustituida")
# Criterio que ya no rige: bloquea el documento (falso verde; scoring_vvca regla 2).
VIGENCIA_PERDIDA = frozenset({"superada", "interrumpida", "sustituida"})
# Sin dato: ni el corpus ni el scraper registraron la vigencia. Nunca se asume "vigente".
VIGENCIA_NO_CONSULTADA = "no_consultada"
# La fuente registra un valor que no es un estado conocido (se conserva el original).
VIGENCIA_NO_RECONOCIDA = "no_reconocida"
# Dos campos con dato y valores distintos, sin pérdida registrada (ronda 2): 🟡 mínimo.
VIGENCIA_EN_CONFLICTO = "en_conflicto"
# Campos del corpus que pueden registrar la vigencia, en orden de lectura.
CAMPOS_VIGENCIA = ("estado_vigencia", "vigencia")


def _estado_de_valor(valor) -> Optional[str]:
    """Estado de UN valor registrado: None sin dato; un estado conocido; ``no_consultada`` si
    así se registró; una pérdida si su primera palabra lo es ("superada por contradicción" →
    superada); si no, ``no_reconocida``."""
    if valor is None or not str(valor).strip():
        return None
    texto = str(valor).strip().lower()
    if texto in ESTADOS_VIGENCIA or texto == VIGENCIA_NO_CONSULTADA:
        return texto
    primera = re.split(r"[\s,;:.()]+", texto)[0]
    for perdida in VIGENCIA_PERDIDA:
        if primera in (perdida, perdida[:-1] + "o"):
            return perdida
    return VIGENCIA_NO_RECONOCIDA


def normalizar_vigencia(item: dict) -> dict:
    """Estado de vigencia de una tesis del corpus local, leyendo TODOS sus campos (R4d).

    "vigente" solo si la fuente lo registra (p. ej. el scraper tras leer las notas del SJF).
    Ronda 2: una pérdida (superada/interrumpida/sustituida) registrada en CUALQUIER campo
    prevalece sobre "no consultada" o un valor desconocido; dos campos con dato y valores
    distintos son un conflicto (``conflicto=True``): si alguno es pérdida, bloquea esa pérdida;
    si no, el estado es ``en_conflicto`` (🟡 mínimo). Sin ningún dato → ``no_consultada``; un
    valor desconocido → ``no_reconocida`` (ninguno de los dos cambia el semáforo).

    Devuelve ``{"estado", "registrado", "conflicto", "valores"}``: ``registrado`` es el valor
    original que decidió el estado (None sin dato) y ``valores``, cada campo con dato."""
    valores = {
        campo: str(item.get(campo)) for campo in CAMPOS_VIGENCIA
        if item.get(campo) is not None and str(item.get(campo)).strip()
    }
    estados = {campo: _estado_de_valor(valor) for campo, valor in valores.items()}
    con_dato = {c: e for c, e in estados.items() if e and e != VIGENCIA_NO_CONSULTADA}
    conflicto = len(set(con_dato.values())) > 1
    perdidas = [c for c, e in con_dato.items() if e in VIGENCIA_PERDIDA]
    if perdidas:
        estado, registrado = con_dato[perdidas[0]], valores[perdidas[0]]
    elif conflicto:
        estado = VIGENCIA_EN_CONFLICTO
        registrado = "; ".join(f"{c}={valores[c]}" for c in con_dato)
    elif con_dato:
        campo = next(iter(con_dato))
        estado, registrado = con_dato[campo], valores[campo]
    else:
        estado = VIGENCIA_NO_CONSULTADA
        registrado = next(iter(valores.values()), None)
    return {"estado": estado, "registrado": registrado, "conflicto": conflicto,
            "valores": valores}
