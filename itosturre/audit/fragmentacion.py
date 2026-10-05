"""Corte y etiqueta de los fragmentos que guarda la ingesta (re-ingesta por fuente, 4-oct-2026).

Funciones puras (solo biblioteca estándar): reciben el texto de las páginas de un PDF y
devuelven los fragmentos con su etiqueta y su página. No usan PyMuPDF, ChromaDB, LangChain ni
el modelo, de modo que el CI (Python 3.11 sin paquetes) las ejerce; ``OpenNotebook.ingest`` les
inyecta el divisor de respaldo (``RecursiveCharacterTextSplitter.split_text``).

Problema que corrige (diagnóstico del coordinador con el corpus real, 4-oct-2026). El corte de
"ley" era ``(?=\\n[Aa]rt[íi]?(?:culo)?s?\\.?\\s+\\d+)`` y la etiqueta
``[Aa]rt[íi]?(?:culo)?s?\\.?\\s+(\\d+[\\w\\-]*)``: exigían "rt" en minúscula, así que los
encabezados en MAYÚSCULAS ("ARTICULO 496.-", "ARTÍCULO 1o.-") no cortaban ni etiquetaban. En el
Código Federal de Procedimientos Civiles, la LFPC, la LFPCA y la Convención sobre los Derechos
del Niño los artículos del cuerpo quedaban dentro del fragmento de otro artículo y sin etiqueta,
y nunca alcanzaban el verde determinista. El mismo patrón cortaba en remisiones en minúscula al
inicio de línea ("artículo 41." del Código Civil Federal) y etiquetaba el fragmento con un
número que no era su encabezado.

Leyes ("ley"): se corta al inicio de la línea de cada ENCABEZADO AUTÉNTICO
(``itosturre.audit.evidence.encabezados_autenticos``), la misma definición con que la auditoría
acepta un encabezado (``_es_autentico``): prefijo con "A" mayúscula ("Artículo", "ARTÍCULO",
"ARTICULO", "Art."), designación (número, ordinal o º ª °, sufijos -A, Bis, Ter…) y cierre
".-", ".", "-" o ":" no seguido de "," ni ";"; o bien, para los tratados, la designación sola al
final de su línea ("Artículo 51", "ARTÍCULO 1") si la línea siguiente no continúa una oración.
No cortan "artículo 41." (minúscula), "Artículo 2o., fracción I" (cita) ni "Artículo 51 de esta
Ley…" (sin cierre a media línea). "Artículo 26.\\nA. El Estado…" o "Artículo 185.\\nA efecto
de…" siguen en un solo fragmento: solo corta una línea que empieza con el prefijo.

Etiqueta (metadato ``article``), compatible con la anterior y con
``OpenNotebook._article_candidates``: la misma regla ``\\d+[\\w\\-]*`` tras el prefijo, ahora
solo en la línea de un encabezado auténtico: "ARTÍCULO 1o.-" → '1o', "ARTICULO 496.-" → '496',
"Artículo 1º" → '1º', "Artículo 1°" → '1', "Artículo 4o.-A.-" → '4o' (como antes),
"Artículo 29-A." → '29-A', "ARTÍCULO 58-1.-" → '58-1', "Artículo 247 Bis.-" → '247'.
Diferencia deliberada: un cierre "-" ya no se pega a la etiqueta ("Artículo 10- Texto" → '10',
antes '10-').

Página: la de la línea del encabezado (antes, la del salto de línea anterior: un encabezado en
la primera línea de una página quedaba con la página previa).

Contratos y resoluciones: sin cambios (mismos patrones de corte y etiqueta que antes).

Ronda 2 (4-oct-2026): la gramática única de ``referencias`` ("58-1", "65 Bis 1", latinos más
allá de "decies"); el encabezado partido entre líneas ("ARTICULO\n508.-") corta y se etiqueta
con su número; también se corta en la línea TRANSITORIOS; las etiquetas van en la caja de
``canon_caja`` ("29-a" → "29-A"). ``paginas_incompletas`` y ``verificar_identidad`` son las
comprobaciones (puras) que la re-ingesta por fuente exige antes de borrar nada.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from .evidence import (
    FORMA_FIN_DE_LINEA,
    _without_accents,
    encabezados_autenticos,
    es_frontera_transitorios,
)
from .referencias import canon_caja

TIPO_LEY = "ley"
TIPO_CONTRATO = "contrato"
TIPO_RESOLUCION = "resolucion"

MUESTRA_TIPO = 3000          # caracteres con que se decide el tipo de documento (como antes)
SEPARADOR_PAGINAS = "\n\n"   # las páginas se concatenan antes de cortar (artículos que cruzan
                             # un salto de página quedan enteros)

# Contratos y resoluciones: los patrones de siempre (sin cambios).
_CORTE_CONTRATO = re.compile(
    r'(?=\n[Cc]l[áa]usula\s+(?:[A-ZÁÉÍÓÚa-záéíóú]+|\d+))', re.MULTILINE
)
_CORTE_RESOLUCION = re.compile(
    r'(?=\n(?:CONSIDERANDO|RESULTANDO|VISTOS|[A-ZÁÉÍÓÚ]{4,}[:\s]|'
    r'[Pp]rimero[:\s]|[Ss]egundo[:\s]|[Tt]ercero[:\s]|[Cc]uarto[:\s]))',
    re.MULTILINE,
)
_CLAUSULA = re.compile(r'\n[Cc]l[áa]usula\s+\w+')
_SECCION = re.compile(r'\n(?:CONSIDERANDO|RESULTANDO|VISTOS)\b')
_ETIQUETA_CONTRATO = re.compile(r'\s*[Cc]l[áa]usula\s+(\w+)')
_ETIQUETA_RESOLUCION = re.compile(r'\s*([A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚa-záéíóú\s]{2,30})[:\s]')

# Etiqueta de un artículo: la regla de siempre (``\d+[\w\-]*`` tras el prefijo) aplicada a la
# línea del encabezado auténtico: número, ordinal y lo que siga pegado con guion.
# Ronda 2: el blanco tras el prefijo puede ser un salto de línea (encabezado partido,
# "ARTICULO\n508.-"); la regla se aplica al texto del encabezado reconocido.
_ETIQUETA_LEY = re.compile(r"[ \t]*[^\W\d_]+\.?\s+(\d+[\w\-]*)")
# Prefijo que se inyecta en los subfragmentos de un texto largo ("[LEY 42]\n").
_PREFIJO_SUBFRAGMENTO = re.compile(r"\A\[(?:LEY|CONTRATO|RESOLUCION)(?: [^\]\n]*)?\]\n")


def etiqueta_de_encabezado(linea: str) -> str:
    """Etiqueta ``article`` de la línea de un encabezado: "ARTÍCULO 1o.-" → '1o',
    "Artículo 4o.-A.-" → '4o', "Artículo 29-A." → '29-A', "ARTÍCULO 58-1.-" → '58-1',
    "Artículo 247 Bis.-" → '247', "Artículo 1°" → '1'. Es la regla anterior; solo se quita
    un guion final de cierre ("Artículo 10- Texto" → '10', antes '10-'). Se aplica al texto sin
    acentos, como el reconocimiento del encabezado: un PDF puede traer el acento descompuesto
    ("i" + tilde combinante) y el prefijo no se reconocería."""
    m = _ETIQUETA_LEY.match(_without_accents(linea or ""))
    # Ronda 2: misma caja que los candidatos (``canon_caja``: "29-a" → "29-A"; el ordinal
    # "1o" se conserva).
    return canon_caja(m.group(1).rstrip("-")) if m else ""


def _inicios_de_linea(texto: str) -> list[int]:
    inicios = [0]
    posicion = texto.find("\n")
    while posicion >= 0:
        inicios.append(posicion + 1)
        posicion = texto.find("\n", posicion + 1)
    return inicios


def encabezados_de_ley(texto: str) -> list[dict[str, Any]]:
    """Encabezados auténticos de ``texto`` (con la forma "fin de línea" de los tratados), con
    posiciones del TEXTO ORIGINAL: ``inicio`` (inicio de su línea), ``primer_caracter`` (primer
    carácter no blanco), ``designacion``, ``etiqueta`` y ``forma``.

    ``encabezados_autenticos`` trabaja sobre el texto sin acentos; quitar acentos no quita
    saltos de línea, así que cada encabezado (que empieza al inicio de una línea) se ubica en
    el original por su número de línea."""
    normalizado = _without_accents(texto)
    hallados = encabezados_autenticos(texto, fin_de_linea=True)
    if not hallados:
        return []
    lineas_norm = _inicios_de_linea(normalizado)
    lineas_orig = _inicios_de_linea(texto)
    salida = []
    for h in hallados:
        numero = bisect.bisect_right(lineas_norm, h["inicio"]) - 1
        inicio = lineas_orig[numero]
        fin_linea = texto.find("\n", inicio)
        linea = texto[inicio:fin_linea if fin_linea >= 0 else len(texto)]
        salida.append({
            "inicio": inicio,
            "primer_caracter": inicio + len(linea) - len(linea.lstrip()),
            "designacion": h["designacion"],
            # Ronda 2: el texto del encabezado reconocido (también partido entre líneas).
            "etiqueta": etiqueta_de_encabezado(normalizado[h["inicio"]:h["fin"]]),
            "forma": h["forma"],
        })
    return salida


def etiqueta_ley(pieza: str) -> str:
    """Etiqueta de un fragmento de ley: la del encabezado auténtico con que EMPIEZA (tras los
    blancos iniciales); "" si no empieza con uno (preámbulo, decreto, remisión)."""
    for encabezado in encabezados_de_ley(pieza):
        if not pieza[:encabezado["inicio"]].strip():
            return encabezado["etiqueta"]
        break
    return ""


def detectar_tipo(texto: str) -> str:
    """"contrato", "resolucion" o "ley" según los primeros ``MUESTRA_TIPO`` caracteres.

    Igual que antes, salvo cómo se cuentan los artículos: ahora son los encabezados auténticos
    (también en MAYÚSCULAS y los de los tratados al final de su línea); antes, cualquier línea
    "Artículo/artículo N" (con las remisiones en minúscula y sin los "ARTÍCULO N")."""
    muestra = texto[:MUESTRA_TIPO]
    articulos = len(encabezados_autenticos(muestra, fin_de_linea=True))
    clausulas = len(_CLAUSULA.findall(muestra))
    secciones = len(_SECCION.findall(muestra))
    if clausulas >= 2 and clausulas >= articulos:
        return TIPO_CONTRATO
    if secciones >= 2 and secciones >= articulos:
        return TIPO_RESOLUCION
    return TIPO_LEY


def cortes(texto: str, tipo: str) -> list[int]:
    """Posiciones donde empieza un fragmento según el tipo (sin el 0 inicial)."""
    if tipo == TIPO_CONTRATO:
        return [m.start() for m in _CORTE_CONTRATO.finditer(texto)]
    if tipo == TIPO_RESOLUCION:
        return [m.start() for m in _CORTE_RESOLUCION.finditer(texto)]
    # Ronda 2 de la re-ingesta (4-oct-2026): también se corta en la línea TRANSITORIOS, para
    # que los transitorios (y sus fracciones) no queden en el fragmento del último artículo.
    limites = {e["inicio"] for e in encabezados_de_ley(texto)} | set(_lineas_frontera(texto))
    return sorted(posicion for posicion in limites if posicion > 0)


def _lineas_frontera(texto: str) -> list[int]:
    """Inicio de cada línea TRANSITORIOS de ``texto``."""
    posiciones, posicion = [], 0
    for linea in texto.split("\n"):
        if es_frontera_transitorios(linea):
            posiciones.append(posicion)
        posicion += len(linea) + 1
    return posiciones


def etiqueta(pieza: str, tipo: str) -> str:
    """Encabezado de sección del fragmento (artículo, cláusula o sección)."""
    if tipo == TIPO_LEY:
        return etiqueta_ley(pieza)
    if tipo == TIPO_CONTRATO:
        m = _ETIQUETA_CONTRATO.match(pieza)
        return m.group(1) if m else ""
    if tipo == TIPO_RESOLUCION:
        m = _ETIQUETA_RESOLUCION.match(pieza)
        return m.group(1).strip() if m else ""
    return ""


@dataclass(frozen=True)
class Fragmento:
    texto: str
    etiqueta: str
    pagina: int


@dataclass(frozen=True)
class Fragmentacion:
    tipo: str
    texto: str                                  # páginas concatenadas (SEPARADOR_PAGINAS)
    fragmentos: tuple[Fragmento, ...] = field(default_factory=tuple)


def unir_paginas(paginas: Sequence[Mapping[str, Any]]) -> tuple[str, list[tuple[int, int]]]:
    """Texto completo y (desplazamiento, página) de cada página, como la ingesta de siempre."""
    desplazamientos: list[tuple[int, int]] = []
    posicion = 0
    partes: list[str] = []
    for pagina in paginas:
        desplazamientos.append((posicion, int(pagina["page"])))
        partes.append(pagina["text"])
        posicion += len(pagina["text"]) + len(SEPARADOR_PAGINAS)
    return SEPARADOR_PAGINAS.join(partes), desplazamientos


def _pagina_de(desplazamientos: list[tuple[int, int]], posicion: int) -> int:
    pagina = desplazamientos[0][1] if desplazamientos else 1
    for desplazamiento, numero in desplazamientos:
        if posicion >= desplazamiento:
            pagina = numero
        else:
            break
    return pagina


def fragmentar(
    paginas: Sequence[Mapping[str, Any]],
    *,
    max_caracteres: int,
    subdividir: Callable[[str], Iterable[str]],
) -> Fragmentacion:
    """Fragmentos de un documento a partir de sus páginas (``{"page", "text"}``, en orden).

    Corta según el tipo (``detectar_tipo``; si un contrato o una resolución no da al menos dos
    cortes, se intenta como ley), etiqueta cada pieza y subdivide con ``subdividir`` las que
    pasan de ``max_caracteres``, con el prefijo "[LEY N]\\n" en cada subfragmento (como antes).
    """
    texto, desplazamientos = unir_paginas(paginas)
    if not texto:
        return Fragmentacion(tipo=TIPO_LEY, texto=texto)
    tipo = detectar_tipo(texto)
    limites = cortes(texto, tipo)
    if len(limites) < 2 and tipo != TIPO_LEY:
        como_ley = cortes(texto, TIPO_LEY)
        if len(como_ley) >= 2:
            tipo, limites = TIPO_LEY, como_ley
    if not limites or limites[0] > 0:
        limites = [0] + limites
    limites.append(len(texto))

    fragmentos: list[Fragmento] = []
    for inicio, fin in zip(limites, limites[1:]):
        pieza = texto[inicio:fin].strip()
        if not pieza:
            continue
        pagina = _pagina_de(desplazamientos, inicio)
        rotulo = etiqueta(pieza, tipo)
        if len(pieza) <= max_caracteres:
            fragmentos.append(Fragmento(pieza, rotulo, pagina))
            continue
        prefijo = f"[{tipo.upper()} {rotulo}]\n" if rotulo else ""
        for sub in subdividir(pieza):
            fragmentos.append(Fragmento(prefijo + sub.strip(), rotulo, pagina))
    return Fragmentacion(tipo=tipo, texto=texto, fragmentos=tuple(fragmentos))


# ─────────────────────────────────────────
# MEDICIÓN (--simular): fragmentos, etiquetas y cobertura de los encabezados
# ─────────────────────────────────────────

def _frontera(texto: str) -> Optional[int]:
    """Posición de la primera línea TRANSITORIOS (criterio de ``inexistencia``), o None."""
    posicion = 0
    for linea in texto.split("\n"):
        if es_frontera_transitorios(linea):
            return posicion
        posicion += len(linea) + 1
    return None


def medir(texto: str, fragmentos: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """Métricas de una fragmentación de ``texto`` (páginas unidas como en la ingesta).

    ``fragmentos``: (texto, etiqueta) en orden de ``chunk_index`` — los indexados (antes) o
    los de ``fragmentar`` (después). Cada fragmento se ubica en ``texto`` (sin el prefijo de
    subfragmento) buscando su inicio a partir del anterior.

    - ``encabezados`` / ``encabezados_cuerpo``: encabezados auténticos del documento y del
      cuerpo (antes de la primera línea TRANSITORIOS; todo el texto si no la hay);
    - ``cubiertos_cuerpo`` y ``cobertura``: encabezados del cuerpo con los que EMPIEZA un
      fragmento que lleva su etiqueta, y su porcentaje (``cubiertos_documento`` y
      ``cobertura_documento``: lo mismo en todo el documento; sirve cuando un índice inicial
      trae la línea TRANSITORIOS y el "cuerpo" queda vacío);
    - ``etiquetados``, ``propios`` (empiezan con el encabezado auténtico de su etiqueta),
      ``continuaciones`` (los demás subfragmentos de un texto largo, con prefijo "[LEY N]"),
      ``etiqueta_sin_encabezado`` (etiqueta sin encabezado auténtico al inicio: remisiones
      tomadas por encabezado) y ``no_ubicados`` (el texto del fragmento no está en el PDF).
    """
    encabezados = encabezados_de_ley(texto)
    frontera = _frontera(texto)
    cuerpo = [e for e in encabezados if frontera is None or e["inicio"] < frontera]
    por_posicion = {e["primer_caracter"]: e for e in encabezados}

    inicios: list[Optional[int]] = []
    desde = 0
    for documento, _rotulo in fragmentos:
        contenido = _PREFIJO_SUBFRAGMENTO.sub("", documento or "", count=1).strip()
        sonda = contenido[:200]
        posicion = texto.find(sonda, desde) if sonda else -1
        if posicion < 0:
            inicios.append(None)
            continue
        inicios.append(posicion)
        desde = posicion + 1

    cubiertos: set[int] = set()
    etiquetados = propios = continuaciones = sin_encabezado = no_ubicados = 0
    for (documento, rotulo), posicion in zip(fragmentos, inicios):
        rotulo = str(rotulo or "")
        if rotulo:
            etiquetados += 1
        if posicion is None:
            no_ubicados += 1
            continue
        encabezado = por_posicion.get(posicion)
        if encabezado is not None and rotulo and encabezado["etiqueta"] == rotulo:
            propios += 1
            cubiertos.add(posicion)
        elif rotulo and _PREFIJO_SUBFRAGMENTO.match(documento or ""):
            continuaciones += 1
        elif rotulo:
            sin_encabezado += 1
    cubiertos_cuerpo = sum(1 for e in cuerpo if e["primer_caracter"] in cubiertos)
    cubiertos_documento = sum(1 for e in encabezados if e["primer_caracter"] in cubiertos)
    return {
        "fragmentos": len(fragmentos),
        "etiquetados": etiquetados,
        "sin_etiqueta": len(fragmentos) - etiquetados,
        "propios": propios,
        "continuaciones": continuaciones,
        "etiqueta_sin_encabezado": sin_encabezado,
        "no_ubicados": no_ubicados,
        "encabezados": len(encabezados),
        "encabezados_fin_de_linea": sum(1 for e in encabezados if e["forma"] == FORMA_FIN_DE_LINEA),
        "encabezados_cuerpo": len(cuerpo),
        "cubiertos_cuerpo": cubiertos_cuerpo,
        "cobertura": round(100.0 * cubiertos_cuerpo / len(cuerpo), 1) if cuerpo else None,
        "cubiertos_documento": cubiertos_documento,
        "cobertura_documento": (
            round(100.0 * cubiertos_documento / len(encabezados), 1) if encabezados else None
        ),
        "frontera_transitorios": frontera is not None,
    }


# ─────────────────────────────────────────
# SEGURIDAD DE LA RE-INGESTA POR FUENTE (ronda 2, adjudicado el 4-oct-2026)
# ─────────────────────────────────────────
# Antes de borrar los fragmentos de una fuente, ``OpenNotebook.reingestar_fuentes`` exige que
# la extracción nueva esté completa y sea del MISMO documento que lo indexado (sin depender
# del catálogo). Funciones puras: reciben textos y páginas.

MIN_CARACTERES_PAGINA = 200     # una página del cuerpo con menos texto delata escaneo o pérdida
UMBRAL_IDENTIDAD = 0.90         # designaciones (o fragmentos) indexados que deben reaparecer
MIN_DESIGNACIONES_IDENTIDAD = 10


def paginas_incompletas(paginas: Sequence[Mapping[str, Any]]) -> list[str]:
    """Problemas de extracción ANTES de la frontera TRANSITORIOS ([] si no hay): páginas sin
    texto (la extracción las omite: huecos de numeración) o con menos de
    ``MIN_CARACTERES_PAGINA`` caracteres. Sin línea TRANSITORIOS se revisan todas salvo la
    última. Las páginas posteriores a la frontera no se revisan (anexos, notas de reforma)."""
    if not paginas:
        return ["el PDF no dio texto"]
    numeros = [int(p["page"]) for p in paginas]
    frontera = next(
        (int(p["page"]) for p in paginas
         if any(es_frontera_transitorios(linea) for linea in p["text"].split("\n"))),
        None,
    )
    limite = frontera if frontera is not None else max(numeros)
    problemas = []
    faltantes = sorted(set(range(1, limite)) - set(numeros))
    if faltantes:
        problemas.append(
            f"páginas sin texto extraíble antes de "
            f"{'la frontera TRANSITORIOS' if frontera is not None else 'la última'}: "
            f"{', '.join(map(str, faltantes[:20]))}"
        )
    cortas = [
        f"{p['page']} ({len(p['text'].strip())} caracteres)" for p in paginas
        if int(p["page"]) < limite and len(p["text"].strip()) < MIN_CARACTERES_PAGINA
    ]
    if cortas:
        problemas.append(
            f"páginas con menos de {MIN_CARACTERES_PAGINA} caracteres antes de "
            f"{'la frontera TRANSITORIOS' if frontera is not None else 'la última'}: "
            f"{', '.join(cortas[:20])}"
        )
    return problemas


def _titulo(texto: str) -> str:
    """Primera línea con contenido, sin acentos, en minúsculas y solo letras y dígitos."""
    for linea in (texto or "").split("\n"):
        plano = re.sub(r"[^0-9a-z]+", " ", _without_accents(linea).casefold()).strip()
        if plano:
            return plano
    return ""


def _claves_designacion(texto: str) -> set[str]:
    """Designaciones de los encabezados auténticos de ``texto``, comparables entre sí."""
    return {
        canon_caja(re.sub(r"[\s.]+", "", e["designacion"])) for e in encabezados_de_ley(texto)
    }


def _sin_blancos(texto: str) -> str:
    return " ".join((texto or "").split())


def verificar_identidad(indexados: Sequence[str], texto_nuevo: str) -> dict[str, Any]:
    """¿El PDF nuevo es el MISMO documento que la fuente indexada? ``indexados``: textos de los
    fragmentos indexados de esa fuente en orden de ``chunk_index``; ``texto_nuevo``: páginas
    unidas del PDF. No depende del catálogo ni del cortador:

    - el título (primera línea con contenido) del fragmento 0 y del PDF coinciden;
    - al menos ``UMBRAL_IDENTIDAD`` de las designaciones de los encabezados auténticos que
      aparecen en el texto indexado reaparecen en el PDF (con al menos
      ``MIN_DESIGNACIONES_IDENTIDAD``; si hay menos, la misma proporción de fragmentos
      indexados cuyo texto, sin el prefijo de subfragmento y con los blancos colapsados,
      aparece en el PDF).

    Devuelve ``coincide``, ``motivo`` ("" si coincide), ``criterio``, ``solapamiento`` y los
    títulos. Sin fragmentos indexados no hay nada que comparar: coincide (fuente nueva)."""
    if not indexados:
        return {"coincide": True, "motivo": "", "criterio": "fuente_nueva", "solapamiento": None,
                "titulo_indexado": "", "titulo_nuevo": _titulo(texto_nuevo)}
    limpios = [_PREFIJO_SUBFRAGMENTO.sub("", t or "", count=1) for t in indexados]
    salida: dict[str, Any] = {
        "titulo_indexado": _titulo(limpios[0]), "titulo_nuevo": _titulo(texto_nuevo),
    }
    if salida["titulo_indexado"] != salida["titulo_nuevo"]:
        return {**salida, "coincide": False, "criterio": "titulo", "solapamiento": None,
                "motivo": (
                    f"el título de la primera página no coincide con el indexado "
                    f"('{salida['titulo_nuevo'][:80]}' frente a "
                    f"'{salida['titulo_indexado'][:80]}')"
                )}
    previas = _claves_designacion("\n\n".join(limpios))
    if len(previas) >= MIN_DESIGNACIONES_IDENTIDAD:
        comunes = len(previas & _claves_designacion(texto_nuevo))
        solapamiento = comunes / len(previas)
        criterio = "designaciones"
        detalle = f"{comunes} de {len(previas)} designaciones de artículo indexadas"
    else:
        plano = _sin_blancos(texto_nuevo)
        hallados = sum(1 for t in limpios if _sin_blancos(t)[:200] in plano)
        solapamiento = hallados / len(limpios)
        criterio = "texto"
        detalle = f"{hallados} de {len(limpios)} fragmentos indexados"
    coincide = solapamiento >= UMBRAL_IDENTIDAD
    return {**salida, "coincide": coincide, "criterio": criterio,
            "solapamiento": round(solapamiento, 4),
            "motivo": "" if coincide else (
                f"solo {detalle} reaparecen en el PDF ({solapamiento:.0%} < "
                f"{UMBRAL_IDENTIDAD:.0%}): no se acredita que sea el mismo documento"
            )}
