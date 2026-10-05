"""Prueba positiva de inexistencia de un artículo en una ley indexada (R4-D10).

Criterio del responsable jurídico (2-oct-2026, opción C): un artículo citado que NO se
localiza en una ley que SÍ está indexada solo es 🔴 con **prueba positiva de inexistencia**;
en cualquier otro caso es 🟡. "No lo encontré" no es "no existe": el hueco puede ser del
índice (fragmentación, extracción del PDF), no de la ley. Principio rector (ronda 2): ante
CUALQUIER ambigüedad la prueba se abstiene; es preferible perder un 🔴 que emitir uno falso.

Función pura (solo biblioteca estándar): recibe los fragmentos indexados de la ley citada
(texto y metadatos ``source``, ``chunk_index`` y ``page``, como los guarda la ingesta), las
denominaciones con que el catálogo nombra esa ley y la designación citada con su sufijo
("19 Ter", "4o.-A", "247 Bis"). No lee el corpus. ``preparar_ley`` hace una vez por ley el
trabajo que no depende del artículo (orden, normalización, cuerpo, encabezados, identidad,
versión, densidad) para reutilizarlo en cada referencia.

Solo hay dos pruebas válidas, ambas sobre el CUERPO de la ley (lo anterior a la primera
línea "TRANSITORIOS"):

1. **Vecinos en el mismo fragmento.** El encabezado del artículo inmediatamente anterior
   según el orden de numeración (N < N Bis < N Ter…; N < N-A < N-B…) y el del siguiente que
   existe aparecen seguidos DENTRO DE UN MISMO FRAGMENTO, cada uno una sola vez en el cuerpo,
   sin ninguna línea candidata entre ellos (otro encabezado, un ordinal en palabra, un número
   al inicio de línea con o sin "Artículo": "3 Bis.-", "3o.-", "Art 3 Bis", "artículo 3…",
   también partido con guion: "ARTÍ-\\nCULO 3 BIS.-"). La continuidad entre fragmentos ya no
   cuenta: un texto repetido (una nota o una cabecera idéntica) no prueba que dos fragmentos
   sean la misma aparición, y la ingesta corta en cada artículo sin solapar. Si el número
   citado tiene variantes con letra y latinas ("70-A" y "70 Bis"), no hay prueba.
2. **Número muy superior al último artículo.** El cuerpo está completo en el índice
   (``chunk_index`` contiguos desde el 0 hasta el fragmento de la frontera), su último
   encabezado numerado es el de mayor número, ninguna línea candidata del cuerpo ni ningún
   encabezado o línea "Artículo N" posterior a la frontera tiene un número mayor (frontera
   dudosa), la densidad de páginas no delata texto perdido, y el número citado alcanza el
   margen: N ≥ último + max(10, ⌈5 % del último⌉). Entre el último + 1 y ese margen no hay
   prueba: el artículo puede haberlo adicionado una reforma posterior a la versión indexada
   (``posterior_al_ultimo`` en el resultado).

Salvaguardas comunes (si alguna falla no hay prueba y la cita queda 🟡):

- fragmentos de una sola fuente, con ``chunk_index`` entero y sin repetir;
- **identidad documental**: el fragmento 0 empieza con una denominación del catálogo para esa
  ley (título del encabezado) o el decreto que la expide la nombra ("decreta: Código…", "se
  expide la Ley…"); si no se comprueba, no hay prueba (una ley indexada bajo el ``source`` de
  otra refutaría artículos reales);
- la frontera TRANSITORIOS se observa (sin ella no se delimita el cuerpo);
- el encabezado del artículo citado no aparece en ninguna parte de la fuente, con ningún
  ordinal ("4" frente a "4o."): un encabezado "N.- (Se deroga)" acredita EXISTENCIA;
- el texto de la fuente (cuerpo y transitorios) no menciona el artículo citado: tras
  "artículo(s)/art(s)." —también en una enumeración o un rango ("arts. 136, 137 y 138",
  "467 a 471")— ni, si lleva sufijo, como "N Bis" suelto.

Riesgo residual (documentado en ``docs/PROTOCOLO_VVCA.md``): la metadata solo guarda la
página de inicio de cada fragmento; el control de densidad reduce, no elimina, el riesgo de
páginas perdidas por la extracción del PDF.

Tratados internacionales (criterio del responsable, 4-oct-2026, opción A): con
``preparar_ley(..., fin_de_linea=True)`` (fuente registrada como tratado en el catálogo) el
encabezado sin cierre ("Artículo 51" solo en su línea) es un encabezado numerado del cuerpo y
acredita existencia. Los tratados del corpus no tienen línea TRANSITORIOS: la prueba se abstiene
("sin línea TRANSITORIOS") y un artículo inexistente de un tratado queda 🟡, nunca 🔴.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Union

from .evidence import (
    _ENCABEZADO_SIGUIENTE,
    _FRONTERA_RE,  # noqa: F401 — reexportado (antes vivía aquí)
    _PREFIJO_SUBFRAGMENTO,
    FORMA_FIN_DE_LINEA,
    _indice,
    _without_accents,
    encabezados_autenticos,
    es_frontera_transitorios,
)
from .referencias import (
    CLAVES_CONTEXTUALES,
    partes_articulo,
    patron_articulo,
    patron_latinos,
    rango_latino,
)

PRUEBA_VECINOS = "vecinos_en_el_mismo_fragmento"
PRUEBA_NUMERO_MAYOR = "numero_muy_superior_al_ultimo"

# Margen de la prueba 2: un artículo adicionado por una reforma posterior a la versión
# indexada (o unas páginas finales perdidas) no debe dar un 🔴. Solo acredita N ≥ último +
# max(MARGEN_MINIMO, ⌈MARGEN_PROPORCIONAL × último⌉).
MARGEN_MINIMO = 10
MARGEN_PROPORCIONAL = 0.05
# Control de densidad: un tramo de fragmentos que empiezan en la misma página no puede
# abarcar, hasta el siguiente, más de 1 + caracteres / CARACTERES_POR_PAGINA páginas.
CARACTERES_POR_PAGINA = 800
# Solapamiento máximo de la ingesta entre subfragmentos de un mismo texto (se descuenta de la
# longitud del tramo para no inflarla).
SOLAPAMIENTO_INGESTA = 200
SIN_FECHA = "versión indexada sin fecha"

# Frontera del cuerpo: la línea "TRANSITORIOS" / "ARTÍCULOS TRANSITORIOS". Desde la ronda 2
# de la re-ingesta (4-oct-2026) ``_FRONTERA_RE`` y ``es_frontera_transitorios`` viven en
# ``evidence`` (el cuerpo del precepto se detiene en ella) y se reexportan aquí.

# Palabra partida con guion al final de la línea ("ARTÍ-\nCULO"): se une antes de buscar.
_GUION_DE_LINEA = re.compile(r"(?<=[^\W\d_])-[ \t]*\n[ \t]*(?=[^\W\d_])")

# Encabezado con ordinal en palabra ("Artículo Primero.-", "ARTÍCULO ÚNICO.-"): los del
# decreto que expide la ley o los que siguen a su último artículo. No se ordenan, pero
# cuentan como encabezado: entre dos vecinos no puede haber ninguno.
_ENCABEZADO_EN_PALABRA = re.compile(
    r"^[ \t]*(?-i:A)rt(?:iculo)?\.?[ \t]+(?:unico|primero|segundo|tercero|cuarto|quinto"
    r"|sexto|septimo|octavo|noveno|decimo)(?![^\W\d_])",
    re.IGNORECASE | re.MULTILINE,
)

# Ronda 2 de la re-ingesta: la misma alternativa de sufijos latinos que la extracción.
_LATINOS_ALT = patron_latinos(r"[^\S\n]")[3:-1]
_SEP = r"[^\S\n]*\.?[^\S\n]*-?[^\S\n]*"
# Línea CANDIDATA a encabezado que el lector exacto no interpreta: "Artículo"/"ARTÍCULO"/
# "Art." (mayúscula inicial) seguido de un número, aunque falte el cierre ("Artículo
# 75.Quedan…", "ARTICULO 225 …", "Art 3 Bis"); o un número al inicio de la línea con un
# sufijo latino ("3 Bis Texto…") o con su cierre seguido de texto en la misma línea ("3
# Bis.- Texto", "3o.- Texto", "1. Los…"). Un número con cierre al final de la línea ("…
# de\n2016.") o entre paréntesis ("de 1982)") es el final de una fecha, no un encabezado.
_LINEA_CANDIDATA = re.compile(
    r"^[^\S\n]*(?:"
    r"(?-i:A)rt(?:iculos?|s)?\.?[^\S\n]*(?P<prefijada>\d+)"
    r"|(?P<numerica>\d+)(?:[oaºª°](?![^\W\d_]))?"
    rf"(?:{_SEP}(?:{_LATINOS_ALT})(?![^\W\d_])"
    rf"|(?:{_SEP}[A-Za-z](?![^\W\d_]))?(?:{_SEP}(?:{_LATINOS_ALT})(?![^\W\d_]))?"
    r"[^\S\n]*(?:\.-|\.|-|:)(?=[^\S\n]*[^\s.\-:]))"
    r")",
    re.IGNORECASE | re.MULTILINE,
)
# Entre dos vecinos (prueba 1) la exigencia es máxima: ninguna línea que empiece con
# "artículo"/"art." y un número, en cualquier caja ("artículo 42 de esta Ley…"), ni con un
# número ("3o.-\nTexto", "1."): no se distinguen de un encabezado deformado.
_LINEA_ART_CUALQUIERA = re.compile(
    r"^[^\S\n]*(?:art(?:iculos?|s)?\.?[^\S\n]*)?\d", re.IGNORECASE | re.MULTILINE
)
# "artículo(s)" / "art(s)." y la enumeración que sigue: números, sufijos, conectores y rangos
# ("arts. 14, 16 y 19", "467 a 471", "32-B Bis y 32-C").
_CABEZA_MENCION = re.compile(r"(?<![^\W\d_])art(?:iculos?|s)?\.?", re.IGNORECASE)
_TOKEN_ENUMERACION = re.compile(
    r"\s*(?:(?P<num>\d+)(?:[oaºª°](?![^\W\d_]))?"
    r"|(?P<rango>(?:a|al)(?=\s+\d)|[-–](?=\s*\d))"
    rf"|(?P<suf>{_LATINOS_ALT}|[a-z])(?![^\W\d_])"
    r"|(?:y|e|o|u)(?![^\W\d_])|[-–,.;°º])",
    re.IGNORECASE,
)
# Versión indexada según el encabezado de la fuente (texto normalizado, en minúsculas).
_VERSIONES = (
    (re.compile(r"(codigo|ley|reglamento) (abrogad[oa]) dof (\d{2}-\d{2}-\d{4})"), "{0} {1} DOF {2}"),
    (re.compile(r"ultimas? reformas? (?:publicadas? )?dof (\d{2}-\d{2}-\d{4})"), "Última Reforma DOF {0}"),
    (re.compile(r"(nueva ley|nuevo codigo|nuevo reglamento) dof (\d{2}-\d{2}-\d{4})"), "{0} DOF {1}"),
    (re.compile(r"ultima reforma publicada en el periodico oficial:? (\d{1,2} de [a-z]+ de \d{4})"),
     "Última reforma P.O. {0}"),
)
_NOMBRES_VERSION = {
    "codigo": "Código", "ley": "Ley", "reglamento": "Reglamento", "nueva ley": "Nueva Ley",
    "nuevo codigo": "Nuevo Código", "nuevo reglamento": "Nuevo Reglamento",
}

# Tipos de encabezado observados en el cuerpo.
NUMERADO = "numerado"        # encabezado exacto con designación ordenable ("Artículo 19 Bis.-")
EN_PALABRA = "en_palabra"    # ordinal en palabra ("ARTÍCULO ÚNICO.-")
CANDIDATA = "candidata"      # línea con forma de encabezado que no se interpreta

# Familias de sufijo de un mismo número: sin sufijo ("19"), solo latino ("19 Bis") o con
# letra ("19-A", "19-A Bis"). El orden entre "N Bis" y "N-A" no es uniforme entre leyes
# (el CFF pone el 70-A antes del 70 Bis): si conviven, no se razona por posición. Ronda 2 de la
# re-ingesta (4-oct-2026): el subnúmero ("58-1") es una familia más.
_SIN_SUFIJO, _LATINO, _LETRA, _SUBNUMERO = 0, 1, 2, 3


def clave_orden(articulo: str) -> Optional[tuple[int, int, int, int, int]]:
    """Clave del orden de numeración: (número, letra, latino, subnúmero, número latino).
    "19" < "19 Bis" < "19 Ter"; "32-B" < "32-B Bis" < "32-C"; ronda 2: "58" < "58-1" < "58-2" y
    "65 Bis" < "65 Bis 1" < "65 Ter"; "quintus" ocupa el lugar de "quinquies". El ordinal ("4o")
    no cuenta. None si no se descompone."""
    partes = partes_articulo(articulo)
    if partes is None:
        return None
    letra = ord(partes.letra) - ord("A") + 1 if partes.letra else 0
    return (
        int(partes.numero), letra, rango_latino(partes.latino),
        int(partes.subnumero or 0), int(partes.numero_latino or 0),
    )


def margen_prueba_numero(ultimo: int) -> int:
    """Diferencia mínima con el último artículo para acreditar por número (P6)."""
    return max(MARGEN_MINIMO, math.ceil(MARGEN_PROPORCIONAL * ultimo))


def _familia(clave: tuple[int, ...]) -> int:
    if clave[1]:
        return _LETRA
    if clave[3]:
        return _SUBNUMERO
    return _LATINO if clave[2] else _SIN_SUFIJO


def _normalizar(texto: str) -> str:
    return " ".join(_without_accents(texto or "").casefold().split())


@dataclass(frozen=True)
class _Fragmento:
    chunk_index: int
    pagina: str
    texto: str                 # sin acentos, sin prefijo "[LEY N]" y con los guiones de
                               # final de línea unidos
    subfragmento: bool         # traía el prefijo de subfragmento de la ingesta


@dataclass(frozen=True)
class _Encabezado:
    fragmento: int             # posición del fragmento en el orden de ``chunk_index``
    inicio: int                # desplazamiento en el texto del fragmento
    fin: int
    tipo: str                  # NUMERADO, EN_PALABRA o CANDIDATA
    designacion: str
    clave: Optional[tuple[int, int, int]] = None   # solo NUMERADO
    numero: Optional[int] = None                    # NUMERADO y CANDIDATA


@dataclass(frozen=True)
class LeyPreparada:
    """Lo que la prueba necesita de una ley y no depende del artículo citado."""

    fuente: str
    motivo: str                               # "" si la estructura es utilizable
    fragmentos: tuple[_Fragmento, ...] = ()
    frontera: Optional[tuple[int, int]] = None
    cuerpo: tuple[str, ...] = ()
    encabezados: tuple[_Encabezado, ...] = ()
    posteriores: tuple[str, ...] = ()         # texto tras la frontera
    identidad: str = ""                       # "" si se comprobó; si no, el motivo
    version: str = SIN_FECHA
    densidad: str = ""                        # "" si no delata pérdida; si no, el motivo
    # Tratados (4-oct-2026, campo añadido): la fuente es un tratado internacional registrado
    # en el catálogo; sus encabezados sin cierre cuentan ("Artículo 51" solo en su línea).
    fin_de_linea: bool = False


def _sin_prueba(motivo: str, **extra: Any) -> dict[str, Any]:
    return {"acreditada": False, "prueba": None, "motivo": motivo, **extra}


def _ordenar(
    fragmentos: Iterable[tuple[str, Mapping[str, Any] | None]],
) -> tuple[Optional[list[_Fragmento]], str, str]:
    """Fragmentos en el orden de ``chunk_index`` (o None y el motivo) y su fuente."""
    filas: list[tuple[int, str, Mapping[str, Any]]] = []
    fuentes = set()
    for documento, metadata in fragmentos:
        metadata = metadata or {}
        indice = _indice(metadata)
        if indice is None or not isinstance(documento, str):
            return None, "fragmento sin chunk_index entero o sin texto", ""
        filas.append((indice, documento, metadata))
        fuentes.add(metadata.get("source"))
    if not filas:
        return None, "la ley no tiene fragmentos indexados", ""
    if len(fuentes) != 1 or not next(iter(fuentes)):
        return None, "los fragmentos no son de una sola fuente identificada", ""
    filas.sort(key=lambda fila: fila[0])
    if len({fila[0] for fila in filas}) != len(filas):
        return None, "chunk_index repetido en la fuente", ""
    ordenados = []
    for indice, documento, metadata in filas:
        texto = _without_accents(documento)
        sin_prefijo = _PREFIJO_SUBFRAGMENTO.sub("", texto, count=1)
        ordenados.append(_Fragmento(
            chunk_index=indice,
            pagina=str(metadata.get("page", "?")),
            texto=_GUION_DE_LINEA.sub("", sin_prefijo),
            subfragmento=sin_prefijo != texto,
        ))
    return ordenados, "", str(next(iter(fuentes)))


def _frontera(fragmentos: list[_Fragmento]) -> Optional[tuple[int, int]]:
    """(fragmento, desplazamiento) de la primera línea TRANSITORIOS, o None."""
    for posicion, fragmento in enumerate(fragmentos):
        desplazamiento = 0
        for linea in fragmento.texto.split("\n"):
            if es_frontera_transitorios(linea):
                return posicion, desplazamiento
            desplazamiento += len(linea) + 1
    return None


def _encabezados_de(texto: str, posicion: int, fin_de_linea: bool = False) -> list[_Encabezado]:
    """Encabezados de un texto en su orden: el exacto (``evidence``) con su designación, el
    de ordinal en palabra y cualquier otra línea candidata. En un tratado (``fin_de_linea``,
    4-oct-2026) también el auténtico sin cierre ("Artículo 51" solo en su línea), con la
    definición única de ``evidence.encabezados_autenticos``."""
    hallados: dict[int, _Encabezado] = {}
    numerados = [
        (m.start(), m.end(), m.group("designacion")) for m in _ENCABEZADO_SIGUIENTE.finditer(texto)
    ]
    if fin_de_linea:
        numerados += [
            (h["inicio"], h["fin"], h["designacion"])
            for h in encabezados_autenticos(texto, fin_de_linea=True)
            if h["forma"] == FORMA_FIN_DE_LINEA
        ]
    for inicio, fin, designacion in numerados:
        designacion = " ".join(designacion.split())
        # "Artículo 20.- A. De los…" (apartado tras el cierre) se lee como el sufijo "20-A":
        # una letra suelta separada por un espacio es ambigua, no se ordena.
        clave = None if re.search(r"\s[A-Za-z]$", designacion) else clave_orden(designacion)
        hallados[inicio] = _Encabezado(
            posicion, inicio, fin, NUMERADO if clave else CANDIDATA, designacion, clave,
            int(re.match(r"\d+", designacion).group(0)),
        )
    for m in _ENCABEZADO_EN_PALABRA.finditer(texto):
        hallados.setdefault(m.start(), _Encabezado(
            posicion, m.start(), m.end(), EN_PALABRA, " ".join(m.group(0).split())))
    for m in _LINEA_CANDIDATA.finditer(texto):
        numero = m.group("prefijada") or m.group("numerica")
        hallados.setdefault(m.start(), _Encabezado(
            posicion, m.start(), m.end(), CANDIDATA, " ".join(m.group(0).split()),
            numero=int(numero)))
    return [hallados[inicio] for inicio in sorted(hallados)]


def _con_forma_de_articulo(encabezado: _Encabezado) -> bool:
    """Encabezado exacto, línea "Artículo N…" o "N Bis…" con número. Tras la frontera no
    cuenta un número suelto con punto ("2014.", "1."): ahí abundan años y listas."""
    if encabezado.tipo == NUMERADO:
        return True
    if encabezado.tipo != CANDIDATA:
        return False
    return not encabezado.designacion[:1].isdigit() or bool(re.search(
        rf"(?<![^\W\d_])(?:{_LATINOS_ALT})(?![^\W\d_])", encabezado.designacion, re.IGNORECASE
    ))


def _identidad(fragmentos: list[_Fragmento], denominaciones: Iterable[str]) -> str:
    """"" si el documento indexado es la ley que el catálogo dice (P5); si no, el motivo.

    Se aceptan dos señales: el fragmento 0 EMPIEZA con una denominación del catálogo (título
    del encabezado, como en los compilados de la Cámara de Diputados) o el decreto que la
    expide la nombra en los dos primeros fragmentos ("decreta: Código…", "se expide la
    Ley…", "se aprueba la Ley…"). Las abreviaturas y las claves genéricas ("constitución",
    "carta magna") no identifican un documento."""
    nombres = sorted({
        _normalizar(d) for d in denominaciones
        if d and len(d.strip()) >= 12 and " " in d.strip() and "." not in d
        and d.strip().lower() not in CLAVES_CONTEXTUALES
    }, key=len, reverse=True)
    if not nombres:
        return "no hay una denominación del catálogo con que comprobar la identidad del documento"
    if not fragmentos or fragmentos[0].chunk_index != 0:
        return "falta el primer fragmento: no se comprueba la identidad del documento"
    inicio = re.sub(r"^\d+\s+", "", _normalizar(fragmentos[0].texto))
    if any(inicio.startswith(nombre) for nombre in nombres):
        return ""
    texto = _normalizar(" ".join(f.texto for f in fragmentos[:2]))
    for nombre in nombres:
        if re.search(
            rf"(?:decreta|se expide|se aprueba)\s*[:.\-]*\s*(?:el |la |los |las )?{re.escape(nombre)}",
            texto,
        ):
            return ""
    return (
        f"el documento indexado no se identifica como '{nombres[0]}' (ni el título del "
        f"encabezado ni el decreto que lo expide lo nombran)"
    )


def _version(fragmentos: list[_Fragmento]) -> str:
    """Versión indexada según el encabezado del primer fragmento (P6)."""
    if not fragmentos:
        return SIN_FECHA
    texto = _normalizar(fragmentos[0].texto)[:2000]
    for patron, formato in _VERSIONES:
        m = patron.search(texto)
        if m:
            grupos = [_NOMBRES_VERSION.get(g, g) for g in m.groups()]
            return formato.format(*grupos)
    return SIN_FECHA


def _pagina_entera(pagina: str) -> Optional[int]:
    try:
        return int(pagina)
    except (TypeError, ValueError):
        return None


def _densidad(fragmentos: list[_Fragmento], frontera: tuple[int, int]) -> str:
    """"" si ningún tramo del cuerpo abarca más páginas de las que su texto puede llenar (P7).

    La metadata guarda solo la página de INICIO de cada fragmento (los subfragmentos de un
    texto largo repiten la de su inicio), así que se agrupan los fragmentos consecutivos con
    la misma página: el tramo abarca hasta la página del fragmento siguiente y no puede pasar
    de 1 + caracteres / CARACTERES_POR_PAGINA. Si pasa, pudo perderse texto (una página sin
    texto extraíble no deja hueco de ``chunk_index``)."""
    i, ultimo = 0, frontera[0]
    while i <= ultimo:
        pagina = _pagina_entera(fragmentos[i].pagina)
        if pagina is None:
            return f"página no numérica en el fragmento {fragmentos[i].chunk_index}"
        j, longitud = i, 0
        while j < len(fragmentos) and fragmentos[j].pagina == fragmentos[i].pagina:
            longitud += len(fragmentos[j].texto)
            if j > i and fragmentos[j].subfragmento:
                longitud -= SOLAPAMIENTO_INGESTA
            j += 1
        if j >= len(fragmentos):
            return ""
        siguiente = _pagina_entera(fragmentos[j].pagina)
        if siguiente is None or siguiente < pagina:
            return (
                f"páginas fuera de orden entre los fragmentos {fragmentos[j - 1].chunk_index} y "
                f"{fragmentos[j].chunk_index}"
            )
        if siguiente - pagina > 1 + max(longitud, 0) / CARACTERES_POR_PAGINA:
            return (
                f"posible texto perdido: los fragmentos {fragmentos[i].chunk_index}–"
                f"{fragmentos[j - 1].chunk_index} empiezan en la pág. {pagina} y el siguiente en "
                f"la {siguiente}, con solo {max(longitud, 0)} caracteres"
            )
        i = j
    return ""


def preparar_ley(
    fragmentos: Iterable[tuple[str, Mapping[str, Any] | None]],
    denominaciones: Iterable[str] = (),
    *,
    fin_de_linea: bool = False,
) -> LeyPreparada:
    """Estructura de la ley reutilizable entre referencias (P9). ``fin_de_linea`` (4-oct-2026):
    la fuente es un tratado internacional registrado en el catálogo; sus encabezados sin
    cierre cuentan como encabezados numerados del cuerpo y como prueba de existencia."""
    ordenados, motivo, fuente = _ordenar(fragmentos)
    if ordenados is None:
        return LeyPreparada(fuente=fuente, motivo=motivo, fin_de_linea=fin_de_linea)
    frontera = _frontera(ordenados)
    identidad = _identidad(ordenados, denominaciones)
    version = _version(ordenados)
    if frontera is None:
        return LeyPreparada(
            fuente=fuente, motivo="", fragmentos=tuple(ordenados), identidad=identidad,
            version=version, fin_de_linea=fin_de_linea,
        )
    ultimo, corte = frontera
    cuerpo = [
        f.texto if posicion < ultimo else f.texto[:corte]
        for posicion, f in enumerate(ordenados[: ultimo + 1])
    ]
    encabezados = [
        e for posicion, texto in enumerate(cuerpo)
        for e in _encabezados_de(texto, posicion, fin_de_linea)
    ]
    posteriores = [ordenados[ultimo].texto[corte:]] + [f.texto for f in ordenados[ultimo + 1:]]
    return LeyPreparada(
        fuente=fuente, motivo="", fragmentos=tuple(ordenados), frontera=frontera,
        cuerpo=tuple(cuerpo), encabezados=tuple(encabezados), posteriores=tuple(posteriores),
        identidad=identidad, version=version, densidad=_densidad(ordenados, frontera),
        fin_de_linea=fin_de_linea,
    )


def secuencia_de_encabezados(ley: LeyPreparada) -> list[tuple[int, tuple[int, ...]]]:
    """Tratados (ronda 2, 4-oct-2026): ``(chunk_index, clave)`` de cada encabezado NUMERADO de
    TODA la fuente (sin frontera, como en un tratado), en el orden del documento, con la
    definición de ``_encabezados_de`` (en un tratado, también los auténticos sin cierre). Un
    encabezado repetido en fragmentos consecutivos (solapamiento) cuenta una vez."""
    secuencia: list[tuple[int, tuple[int, ...]]] = []
    for posicion, fragmento in enumerate(ley.fragmentos):
        for encabezado in _encabezados_de(fragmento.texto, posicion, ley.fin_de_linea):
            if encabezado.tipo != NUMERADO:
                continue
            if secuencia and secuencia[-1][1] == encabezado.clave and (
                fragmento.chunk_index - secuencia[-1][0] <= 1
            ):
                continue
            secuencia.append((fragmento.chunk_index, encabezado.clave))
    return secuencia


def _motivo_frontera_no_creible(ley: LeyPreparada) -> str:
    """"" si la frontera TRANSITORIOS de ``ley`` (ya observada, con encabezados numerados en el
    cuerpo) delimita el cuerpo con credibilidad; si no, el motivo. Son los controles de la
    prueba 2 (P6/P7): el último encabezado del cuerpo es el de mayor número, ninguna línea
    candidata del cuerpo ni ninguna línea con forma de artículo tras la frontera tiene un
    número mayor (frontera dudosa), el cuerpo está completo desde el ``chunk_index`` 0 y la
    densidad de páginas no delata texto perdido."""
    encabezados = list(ley.encabezados)
    numerados = [e for e in encabezados if e.tipo == NUMERADO]
    mayor = max(e.clave[0] for e in numerados)
    ultimo = numerados[-1]
    if ultimo.clave[0] != mayor:
        return (
            f"el último encabezado del cuerpo ({' '.join(ultimo.designacion.split())}) no es el "
            f"de mayor número ({mayor})"
        )
    candidatas = [e for e in encabezados if e.tipo == CANDIDATA and e.numero > mayor]
    if candidatas:
        return (
            f"una línea candidata a encabezado tiene un número mayor que el último "
            f"artículo ({candidatas[0].designacion}): no se acredita dónde termina el cuerpo"
        )
    for texto in ley.posteriores:
        for e in _encabezados_de(texto, -1, ley.fin_de_linea):
            if _con_forma_de_articulo(e) and e.numero > mayor:
                return (
                    f"tras la frontera TRANSITORIOS hay una línea con forma de artículo y "
                    f"número mayor ({e.designacion}): frontera dudosa"
                )
    indices = [f.chunk_index for f in ley.fragmentos[: ley.frontera[0] + 1]]
    if indices[0] != 0:
        return f"el cuerpo no empieza en el chunk_index 0 ({indices[0]})"
    if indices != list(range(len(indices))):
        hueco = next(b for a, b in zip(indices, indices[1:]) if b != a + 1)
        return f"cuerpo incompleto: hueco de chunk_index antes del {hueco}"
    return ley.densidad


def frontera_creible(ley: Optional[LeyPreparada]) -> dict[str, Any]:
    """¿La primera línea TRANSITORIOS de la ley delimita su cuerpo con credibilidad?

    Verde determinista, ronda 2 (pertenencia al cuerpo): la frontera cruda no basta (en un
    reglamento aparece en el índice del fragmento 3; en el CFPC un artículo auténtico del
    cuerpo queda tras ella). Se exigen la estructura utilizable de la ley y los mismos
    controles de credibilidad que la prueba 2 (``_motivo_frontera_no_creible``). Devuelve
    ``creible``, ``motivo`` ("" si es creíble) y ``chunk_index`` del fragmento de la frontera.
    """
    def no(motivo: str) -> dict[str, Any]:
        return {"creible": False, "motivo": motivo, "chunk_index": None}

    if ley is None:
        return no("no se pudieron leer los fragmentos de la ley indexada")
    if ley.motivo:
        return no(ley.motivo)
    if ley.frontera is None:
        return no("sin línea TRANSITORIOS: no se delimita el cuerpo de la ley")
    if not any(e.tipo == NUMERADO for e in ley.encabezados):
        return no("el cuerpo no tiene encabezados de artículo numerados")
    motivo = _motivo_frontera_no_creible(ley)
    if motivo:
        return no(motivo)
    return {
        "creible": True,
        "motivo": "",
        "chunk_index": ley.fragmentos[ley.frontera[0]].chunk_index,
    }


def _menciona(texto: str, tolerante: re.Pattern, base: int, con_sufijo: bool) -> bool:
    """¿El texto menciona el artículo citado (``tolerante``: su designación con cualquier
    ordinal y espacio)? Tras "artículo(s)"/"art(s)." en una enumeración o un rango que lo
    comprenda, o —si lleva sufijo— "N Bis" suelto."""
    if con_sufijo and tolerante.search(texto):
        return True
    for cabeza in _CABEZA_MENCION.finditer(texto):
        posicion, numeros, rango = cabeza.end(), [], False
        while True:
            token = _TOKEN_ENUMERACION.match(texto, posicion)
            if not token or token.end() == posicion:
                break
            if token.group("num"):
                numero = int(token.group("num"))
                if rango and numeros and numeros[-1] <= base <= numero:
                    return True
                numeros.append(numero)
                rango = False
            elif token.group("rango"):
                rango = bool(numeros)
            elif token.group("suf"):
                rango = False
            posicion = token.end()
            if posicion - cabeza.end() > 300:
                break
        if numeros and tolerante.search(texto, cabeza.end(), posicion):
            return True
    return False


def evaluar_inexistencia(
    ley: Union[LeyPreparada, Iterable[tuple[str, Mapping[str, Any] | None]]],
    articulo: str,
    denominaciones: Iterable[str] = (),
) -> dict[str, Any]:
    """Busca una prueba positiva de que ``articulo`` no existe en el cuerpo de la ley.

    ``ley``: la ``LeyPreparada`` o los pares (texto, metadatos) de TODOS los fragmentos de
    la ley citada (entonces ``denominaciones`` son las del catálogo para comprobar la
    identidad). Devuelve ``{"acreditada", "prueba", "motivo"}``; con un número entre el último
    + 1 y el margen, además ``posterior_al_ultimo`` (sin prueba)."""
    if not isinstance(ley, LeyPreparada):
        ley = preparar_ley(ley, denominaciones)
    citada = clave_orden(articulo)
    patron_tolerante = patron_articulo(articulo, ordinal_estricto=False)
    if citada is None or patron_tolerante is None:
        return _sin_prueba(f"la designación '{articulo}' no se puede descomponer")
    if ley.motivo:
        return _sin_prueba(ley.motivo)
    if ley.identidad:
        return _sin_prueba(ley.identidad)
    if ley.frontera is None:
        return _sin_prueba("sin línea TRANSITORIOS: no se delimita el cuerpo de la ley")

    # Existencia: el encabezado citado (cualquier ordinal; también "(Se deroga)") en cualquier
    # parte de la fuente, o una mención del artículo en cualquier parte de su texto.
    # Ronda 2 de la re-ingesta: también partido entre líneas ("ARTICULO\n508.-").
    # Tratados (4-oct-2026): en un tratado registrado también sin cierre, solo al final de su
    # línea ("Artículo 51", en cualquier caja: ante la duda, la prueba se abstiene).
    cierre = r"[^\S\n]*(?:\.\-|[.\-:])"
    if ley.fin_de_linea:
        cierre = rf"(?:{cierre}|[^\S\n]*$)"
    encabezado_citado = re.compile(
        rf"^[^\S\n]*art(?:iculo)?\.?(?:[^\S\n]+|[^\S\n]*\n[^\S\n]*){patron_tolerante}{cierre}",
        re.IGNORECASE | re.MULTILINE,
    )
    if any(encabezado_citado.search(f.texto) for f in ley.fragmentos):
        return _sin_prueba(f"el encabezado del artículo {articulo} aparece en la fuente")
    con_sufijo = bool(citada[1] or citada[2] or citada[3])
    tolerante = re.compile(
        patron_articulo(articulo, ordinal_estricto=False, espacio=r"\s"), re.IGNORECASE
    )
    if any(_menciona(f.texto, tolerante, citada[0], con_sufijo) for f in ley.fragmentos):
        return _sin_prueba(f"el texto de la ley menciona el artículo {articulo}")

    encabezados = list(ley.encabezados)
    numerados = [e for e in encabezados if e.tipo == NUMERADO]
    if not numerados:
        return _sin_prueba("el cuerpo no tiene encabezados de artículo numerados")
    if any(e.clave == citada for e in numerados):
        return _sin_prueba(f"el artículo {articulo} tiene encabezado en el cuerpo")
    ordenados = ley.fragmentos

    def describir(encabezado: _Encabezado) -> dict[str, Any]:
        fragmento = ordenados[encabezado.fragmento]
        return {
            "articulo": " ".join(encabezado.designacion.split()),
            "pagina": fragmento.pagina,
            "chunk_index": fragmento.chunk_index,
        }

    # ── Prueba 2: número muy superior al último artículo del cuerpo completo ────────────
    mayor = max(e.clave[0] for e in numerados)
    if citada[0] > mayor:
        ultimo = numerados[-1]
        # Controles de credibilidad de la frontera (factorizados en la ronda 2 del verde
        # determinista para reutilizarlos en ``frontera_creible``; mismos motivos y orden).
        motivo = _motivo_frontera_no_creible(ley)
        if motivo:
            return _sin_prueba(motivo)
        indices = [f.chunk_index for f in ordenados[: ley.frontera[0] + 1]]
        margen = margen_prueba_numero(mayor)
        if citada[0] < mayor + margen:
            return _sin_prueba(
                f"el artículo {articulo} es posterior al último artículo de la versión indexada "
                f"({describir(ultimo)['articulo']}) pero no lo supera por el margen "
                f"({margen}): una reforma posterior pudo adicionarlo",
                posterior_al_ultimo={
                    "articulo": articulo,
                    "fuente": ley.fuente,
                    "ultimo": describir(ultimo),
                    "margen": margen,
                    "version": ley.version,
                },
            )
        frontera_fragmento = ordenados[ley.frontera[0]]
        return {
            "acreditada": True,
            "motivo": "",
            "prueba": {
                "tipo": PRUEBA_NUMERO_MAYOR,
                "articulo": articulo,
                "fuente": ley.fuente,
                "version": ley.version,
                "ultimo": describir(ultimo),
                "margen": margen,
                "frontera_transitorios": {
                    "pagina": frontera_fragmento.pagina,
                    "chunk_index": frontera_fragmento.chunk_index,
                },
                "fragmentos": [indices[0], indices[-1]],
                "paginas": [ordenados[ultimo.fragmento].pagina],
            },
        }

    # ── Prueba 1: vecinos en el mismo fragmento ─────────────────────────────────────────
    familia = _familia(citada)
    if familia != _SIN_SUFIJO and {
        _familia(e.clave) for e in numerados
        if e.clave[0] == citada[0] and _familia(e.clave) != _SIN_SUFIJO
    } - {familia}:
        return _sin_prueba(
            f"el número {citada[0]} tiene sufijos de letra y latinos: su orden no es uniforme"
        )
    anteriores = [e for e in numerados if e.clave < citada]
    siguientes = [e for e in numerados if e.clave > citada]
    if not anteriores or not siguientes:
        return _sin_prueba(
            f"el artículo {articulo} sigue al último encabezado del cuerpo sin un número "
            f"mayor, o precede al primero: no hay dos vecinos"
        )
    anterior = max(anteriores, key=lambda e: e.clave)
    siguiente = min(siguientes, key=lambda e: e.clave)
    for vecino in (anterior, siguiente):
        if sum(1 for e in numerados if e.clave == vecino.clave) != 1:
            return _sin_prueba(
                f"el encabezado del art. {describir(vecino)['articulo']} se repite en el cuerpo"
            )
    if anterior.fragmento != siguiente.fragmento:
        return _sin_prueba(
            f"los arts. {describir(anterior)['articulo']} y {describir(siguiente)['articulo']} "
            f"están en fragmentos distintos: la continuidad entre fragmentos no se acredita"
        )
    posicion_anterior = encabezados.index(anterior)
    if posicion_anterior + 1 >= len(encabezados) or encabezados[posicion_anterior + 1] != siguiente:
        return _sin_prueba(
            f"los arts. {describir(anterior)['articulo']} y {describir(siguiente)['articulo']} "
            f"no aparecen seguidos (otra línea candidata a encabezado entre ellos o fuera de orden)"
        )
    intervalo = ley.cuerpo[anterior.fragmento][anterior.fin:siguiente.inicio]
    if _LINEA_CANDIDATA.search(intervalo) or _LINEA_ART_CUALQUIERA.search(intervalo):
        return _sin_prueba(
            f"entre los arts. {describir(anterior)['articulo']} y "
            f"{describir(siguiente)['articulo']} hay una línea candidata a encabezado"
        )
    fragmento = ordenados[anterior.fragmento]
    return {
        "acreditada": True,
        "motivo": "",
        "prueba": {
            "tipo": PRUEBA_VECINOS,
            "articulo": articulo,
            "fuente": ley.fuente,
            "version": ley.version,
            "anterior": describir(anterior),
            "siguiente": describir(siguiente),
            "fragmentos": [fragmento.chunk_index],
            "paginas": [fragmento.pagina],
        },
    }


def inexistencia_acreditada(
    ley: Union[LeyPreparada, Iterable[tuple[str, Mapping[str, Any] | None]]],
    articulo: str,
    denominaciones: Iterable[str] = (),
) -> Optional[dict[str, Any]]:
    """La prueba positiva de inexistencia del artículo en el cuerpo de la ley, o None."""
    return evaluar_inexistencia(ley, articulo, denominaciones)["prueba"]


def _version_texto(version: str) -> str:
    return SIN_FECHA if version == SIN_FECHA else f"versión indexada: {version}"


def describir_prueba(prueba: Mapping[str, Any], ley: str) -> str:
    """La prueba en una frase para el abogado: qué se observó, en qué versión y dónde."""
    citado = prueba["articulo"]
    version = _version_texto(prueba.get("version", SIN_FECHA))
    pagina = f"pág. {prueba['paginas'][0]}"
    if prueba["tipo"] == PRUEBA_VECINOS:
        return (
            f"en el cuerpo de {ley} ({version}) el art. {prueba['anterior']['articulo']} pasa "
            f"al art. {prueba['siguiente']['articulo']} sin el {citado} ({pagina})"
        )
    return (
        f"el cuerpo de {ley} ({version}) termina en el art. {prueba['ultimo']['articulo']} "
        f"({pagina}); se cita el {citado}"
    )


def describir_posterior(posterior: Mapping[str, Any], ley: str) -> str:
    """El artículo citado sigue al último de la versión indexada sin superar el margen."""
    version = posterior.get("version", SIN_FECHA)
    detalle = f"; {version}" if version != SIN_FECHA else f"; {SIN_FECHA}"
    return (
        f"el art. {posterior['articulo']} es posterior al último artículo de la VERSIÓN "
        f"INDEXADA de {ley} (art. {posterior['ultimo']['articulo']}, pág. "
        f"{posterior['ultimo']['pagina']}{detalle}): verificar si una reforma lo adicionó"
    )
