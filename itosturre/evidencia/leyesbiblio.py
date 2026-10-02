"""Limpieza del texto por página de los PDF de LeyesBiblio (Cámara de Diputados).

Cada página del compilado oficial abre con el mismo mobiliario::

    <título de la ley, una o más líneas>
    CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN
    Secretaría General
    Secretaría de Servicios Parlamentarios
    Última Reforma DOF dd-mm-aaaa        (o "Últimas Reformas DOF …")
    N de M

con líneas en blanco intercaladas. La limpieza quita **solo** ese bloque cuando se
reconoce completo; si algo no encaja, la página se conserva íntegra y se agrega una
advertencia. Nunca se altera una línea: el texto limpio es una subsecuencia ordenada
del original, cada línea quitada queda clasificada y ``verificar_pagina`` comprueba
esas invariantes. La limpieza nunca sustituye al original: ``PaginaLimpia`` guarda
todas las líneas originales.

El contenido normativo nunca sale como mobiliario: una línea solo cuenta como título
del encabezado si es plausible (todas sus letras en mayúscula; no es encabezado de
artículo ni de división), y en un documento el título debe coincidir con el de la
mayoría estricta de las páginas (o con el ``titulo`` que indique quien llama). Una
página que no cumple se conserva íntegra y se advierte.

Comprobaciones de documento (advertencias, nunca elección): el título y la fecha de
"Última Reforma DOF" del encabezado son los mismos en todas las páginas; la
paginación "N de M" coincide con el número de página declarado y M es constante.

``ubicar_articulo`` devuelve **todas** las líneas con encabezado exacto del artículo,
separando cuerpo, transitorios e indeterminadas (los decretos de reforma del final
repiten "Artículo Primero.-", "ARTICULO 1o.-"…). Una línea solo se acredita como
cuerpo si las páginas recibidas cubren sin huecos desde la página 1 hasta la suya; con
páginas sueltas la zona es indeterminada. Más de una candidata posible en el cuerpo es
ambigüedad: no se elige. Sin coincidencia exacta se advierte (no acredita
inexistencia) y se listan las variantes cercanas sin elegirlas.

Convención de huellas: el texto de un documento es la unión de sus páginas con salto
de página (``\\f``); ``texto_extraido`` usa las páginas originales y ``texto`` las
limpias.

Funciones puras: sin red, sin E/S y sin reloj.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

from .esquema import TIPO_LEY_LEYESBIBLIO, advertencia, construir_registro, fecha_iso
from .huellas import normalizar_para_cotejo, sha256_texto, sin_acentos

VERSION_LIMPIEZA = "1.0"
NOMBRE_LIMPIEZA = "itosturre.evidencia.leyesbiblio.limpiar_documento"
SEPARADOR_PAGINAS = "\f"

BLANCO = "blanco_encabezado"
TITULO = "titulo"
CAMARA = "camara"
SECRETARIA_GENERAL = "secretaria_general"
SECRETARIA_SERVICIOS = "secretaria_servicios_parlamentarios"
ULTIMA_REFORMA = "ultima_reforma"
PAGINACION = "paginacion"
CLASES_MOBILIARIO = (
    BLANCO,
    TITULO,
    CAMARA,
    SECRETARIA_GENERAL,
    SECRETARIA_SERVICIOS,
    ULTIMA_REFORMA,
    PAGINACION,
)

_FIJAS = (
    (CAMARA, normalizar_para_cotejo("CÁMARA DE DIPUTADOS DEL H. CONGRESO DE LA UNIÓN")),
    (SECRETARIA_GENERAL, normalizar_para_cotejo("Secretaría General")),
    (SECRETARIA_SERVICIOS, normalizar_para_cotejo("Secretaría de Servicios Parlamentarios")),
)
_ULTIMA_REFORMA_RE = re.compile(r"^ultimas? reformas? dof (\d{2})-(\d{2})-(\d{4})$")
_PAGINACION_RE = re.compile(r"^\s*(\d+) de (\d+)\s*$")
# Límite del bloque de encabezado: más allá, la página no tiene encabezado reconocible.
_MAX_LINEAS_ENCABEZADO = 20
_MAX_LINEAS_TITULO = 4

# Divisiones del texto normativo que nunca son título del encabezado.
_DIVISION_RE = re.compile(r"^(?:libro|titulo|capitulo|seccion)\b")

ZONA_CUERPO = "cuerpo"
ZONA_TRANSITORIOS = "transitorios"
ZONA_INDETERMINADA = "indeterminada"
_FRONTERA_RE = re.compile(r"^(?:articulos? )?transitorios?(?: de decretos de reforma)?$")

_ORDINAL = (
    r"(?:unico"
    r"|(?:(?:decimo|vigesimo|trigesimo|cuadragesimo|quincuagesimo|sexagesimo"
    r"|septuagesimo|octogesimo|nonagesimo)\s*)?"
    r"(?:primero|segundo|tercero|cuarto|quinto|sexto|septimo|octavo|noveno)"
    r"|decimo|undecimo|duodecimo|vigesimo|trigesimo|cuadragesimo|quincuagesimo"
    r"|sexagesimo|septuagesimo|octogesimo|nonagesimo|centesimo)"
)
_LATINES = r"(?:Bis|BIS|Ter|TER|Quater|QUATER|Quintus|QUINTUS|Quinquies|QUINQUIES|Sexies|SEXIES|Septies|SEPTIES|Octies|OCTIES|Nonies|NONIES|Decies|DECIES)"
# Encabezado de artículo sobre el texto sin acentos. "Artículo" con mayúscula inicial
# (una remisión partida en la línea, "artículo 167. …", no cuenta) y un terminador
# (". ", ".-", "-", ":") tras el identificador: "Artículo 73 de la Constitución" no es
# encabezado.
_ENCABEZADO_RE = re.compile(
    r"^\s*(?:Articulo|ARTICULO|Art\.|ART\.)\s+"
    r"(?P<id>\d+\s*[oOº°]?"
    r"(?:\s*(?:\.\s*)?-\s*[A-Z]\b|\s+" + _LATINES + r"(?:\s+\d+)?|-" + _LATINES + r")*"
    r"|(?i:" + _ORDINAL + r"))"
    r"\s*(?:\.\s*-|\.|-|:)(?=\s|$)"
)
_PREFIJO_ARTICULO = re.compile(r"^\s*(?:art[ií]culo|art\.)\s+", re.IGNORECASE)


@dataclass(frozen=True)
class LineaQuitada:
    """Línea de mobiliario retirada de una página, con su clase."""

    indice: int
    texto: str
    clase: str


@dataclass(frozen=True)
class PaginaLimpia:
    """Página original (todas sus líneas) y la selección de las conservadas."""

    numero: int
    lineas: tuple[str, ...]
    conservadas: tuple[int, ...]
    quitadas: tuple[LineaQuitada, ...]
    encabezado_reconocido: bool
    titulo: str | None = None
    ultima_reforma: str | None = None
    paginacion: tuple[int, int] | None = None
    motivo: str | None = None  # por qué no se reconoció (o se revirtió) el encabezado

    @property
    def original(self) -> str:
        return "\n".join(self.lineas)

    @property
    def lineas_limpias(self) -> tuple[str, ...]:
        return tuple(self.lineas[i] for i in self.conservadas)

    @property
    def texto(self) -> str:
        return "\n".join(self.lineas_limpias)


@dataclass(frozen=True)
class DocumentoLeyesBiblio:
    """Páginas limpias y datos del encabezado comunes a todas (o ``None`` si discrepan)."""

    paginas: tuple[PaginaLimpia, ...]
    titulo: str | None
    ultima_reforma_dof: str | None
    total_paginas: int | None
    advertencias: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def numeros(self) -> tuple[int, ...]:
        return tuple(p.numero for p in self.paginas)

    @property
    def texto_extraido(self) -> str:
        return SEPARADOR_PAGINAS.join(p.original for p in self.paginas)

    @property
    def texto(self) -> str:
        return SEPARADOR_PAGINAS.join(p.texto for p in self.paginas)

    def lineas(self) -> tuple[tuple[int, int, str], ...]:
        """Líneas conservadas como ``(página, índice original, texto)``, en orden."""
        return tuple(
            (pagina.numero, indice, pagina.lineas[indice])
            for pagina in self.paginas
            for indice in pagina.conservadas
        )


def _clase_fija(linea: str) -> str | None:
    cotejo = normalizar_para_cotejo(linea)
    for clase, esperado in _FIJAS:
        if cotejo == esperado:
            return clase
    return None


def _sin_encabezado(numero: int, lineas: tuple[str, ...], motivo: str) -> PaginaLimpia:
    return PaginaLimpia(
        numero=numero,
        lineas=lineas,
        conservadas=tuple(range(len(lineas))),
        quitadas=(),
        encabezado_reconocido=False,
        motivo=motivo,
    )


def motivo_titulo_no_plausible(linea: str) -> str | None:
    """Por qué ``linea`` no puede ser título del encabezado (``None`` si puede).

    El título de LeyesBiblio va en mayúsculas. Se rechaza cualquier línea con letras
    minúsculas, un encabezado de artículo ("ARTÍCULO 5o.- …") o de división (LIBRO,
    TÍTULO, CAPÍTULO, SECCIÓN, TRANSITORIOS): eso es texto normativo.
    """
    texto = linea.strip()
    letras = [c for c in texto if c.isalpha()]
    if not letras:
        return "línea sin letras"
    if any(c.islower() for c in letras):
        return "tiene minúsculas (el título del encabezado va en mayúsculas)"
    if encabezado_articulo(texto) is not None:
        return "es encabezado de artículo"
    if es_frontera_transitorios(texto) or _DIVISION_RE.match(normalizar_para_cotejo(texto)):
        return "es encabezado de división del texto normativo"
    return None


def limpiar_pagina(texto: str, numero: int) -> PaginaLimpia:
    """Quita el bloque de encabezado si se reconoce completo; si no, conserva todo.

    El bloque reconocido es: blancos, título (1 a 4 líneas plausibles), blancos, las
    tres líneas fijas en orden, "Última(s) Reforma(s) DOF dd-mm-aaaa", blancos y
    "N de M". Si algo falla, ``motivo`` dice qué.
    """
    if not isinstance(texto, str):
        raise TypeError(f"se esperaba texto, se recibió {type(texto).__name__}")
    lineas = tuple(texto.split("\n"))
    limite = min(len(lineas), _MAX_LINEAS_ENCABEZADO)
    clases: list[str] = []
    i = 0

    def blancos() -> None:
        nonlocal i
        while i < limite and not lineas[i].strip():
            clases.append(BLANCO)
            i += 1

    blancos()
    titulo: list[str] = []
    while i < limite and lineas[i].strip() and _clase_fija(lineas[i]) is None:
        titulo.append(lineas[i].strip())
        clases.append(TITULO)
        i += 1
    if not titulo:
        return _sin_encabezado(numero, lineas, "no hay título antes de las líneas fijas")
    if len(titulo) > _MAX_LINEAS_TITULO:
        return _sin_encabezado(numero, lineas, f"más de {_MAX_LINEAS_TITULO} líneas antes de las líneas fijas")
    for linea in titulo:
        motivo = motivo_titulo_no_plausible(linea)
        if motivo:
            return _sin_encabezado(numero, lineas, f"título no plausible ({linea!r}: {motivo})")
    blancos()
    for clase, _ in _FIJAS:
        if i >= limite or _clase_fija(lineas[i]) != clase:
            return _sin_encabezado(numero, lineas, f"falta la línea fija {clase!r}")
        clases.append(clase)
        i += 1
    reforma = _ULTIMA_REFORMA_RE.match(normalizar_para_cotejo(lineas[i])) if i < limite else None
    if reforma is None:
        return _sin_encabezado(numero, lineas, "falta 'Última Reforma DOF dd-mm-aaaa'")
    clases.append(ULTIMA_REFORMA)
    i += 1
    blancos()
    paginacion = _PAGINACION_RE.match(lineas[i]) if i < limite else None
    if paginacion is None:
        return _sin_encabezado(numero, lineas, "falta la paginación 'N de M'")
    clases.append(PAGINACION)
    i += 1
    return PaginaLimpia(
        numero=numero,
        lineas=lineas,
        conservadas=tuple(range(i, len(lineas))),
        quitadas=tuple(
            LineaQuitada(indice, lineas[indice], clase) for indice, clase in enumerate(clases)
        ),
        encabezado_reconocido=True,
        titulo=" ".join(titulo),
        ultima_reforma="-".join(reforma.groups()),
        paginacion=(int(paginacion.group(1)), int(paginacion.group(2))),
    )


def fecha_ultima_reforma(linea: str) -> str | None:
    """``AAAA-MM-DD`` si la línea es exactamente "Última(s) Reforma(s) DOF dd-mm-aaaa"
    (comparación sin acentos ni mayúsculas); ``None`` si no lo es o la fecha es imposible."""
    if not isinstance(linea, str):
        return None
    coincidencia = _ULTIMA_REFORMA_RE.match(normalizar_para_cotejo(linea))
    if coincidencia is None:
        return None
    dia, mes, anio = coincidencia.groups()
    fecha = fecha_iso(f"{anio}-{mes}-{dia}")
    return fecha.isoformat() if fecha else None


def es_subsecuencia(corta: Sequence[str], larga: Sequence[str]) -> bool:
    """``True`` si ``corta`` aparece en ``larga`` en el mismo orden (con huecos)."""
    iterador = iter(larga)
    return all(any(elemento == candidato for candidato in iterador) for elemento in corta)


def verificar_pagina(pagina: PaginaLimpia) -> list[str]:
    """Problemas de invariantes de la limpieza (``[]`` si se cumplen todas).

    1. Conservadas y quitadas particionan los índices de la página, sin repetir.
    2. Cada línea quitada es idéntica a la original en su índice y tiene una clase
       del vocabulario que la describe de verdad (p. ej. un ``blanco_encabezado`` solo
       contiene espacios; una ``paginacion`` tiene la forma "N de M"; un ``titulo`` es
       plausible: nunca texto normativo).
    3. Solo se quita el bloque superior: toda línea quitada precede a toda conservada.
    4. El texto limpio es subsecuencia ordenada del original, sin líneas alteradas.
    """
    problemas: list[str] = []
    n = len(pagina.lineas)
    indices_quitados = [q.indice for q in pagina.quitadas]
    todos = list(pagina.conservadas) + indices_quitados
    if sorted(todos) != list(range(n)):
        problemas.append(f"p{pagina.numero}: conservadas y quitadas no particionan las {n} líneas")
    if list(pagina.conservadas) != sorted(set(pagina.conservadas)):
        problemas.append(f"p{pagina.numero}: las líneas conservadas no están en orden estricto")
    for quitada in pagina.quitadas:
        if not 0 <= quitada.indice < n or pagina.lineas[quitada.indice] != quitada.texto:
            problemas.append(f"p{pagina.numero}: la línea quitada {quitada.indice} no es la original")
            continue
        if quitada.clase not in CLASES_MOBILIARIO:
            problemas.append(f"p{pagina.numero}: clase desconocida {quitada.clase!r}")
        elif quitada.clase == BLANCO and quitada.texto.strip():
            problemas.append(f"p{pagina.numero}: línea {quitada.indice} no es blanca")
        elif quitada.clase == TITULO and motivo_titulo_no_plausible(quitada.texto):
            problemas.append(
                f"p{pagina.numero}: línea {quitada.indice} quitada como título no es plausible "
                f"({motivo_titulo_no_plausible(quitada.texto)})"
            )
        elif quitada.clase in (CAMARA, SECRETARIA_GENERAL, SECRETARIA_SERVICIOS) and (
            _clase_fija(quitada.texto) != quitada.clase
        ):
            problemas.append(f"p{pagina.numero}: línea {quitada.indice} no es {quitada.clase}")
        elif quitada.clase == ULTIMA_REFORMA and not _ULTIMA_REFORMA_RE.match(
            normalizar_para_cotejo(quitada.texto)
        ):
            problemas.append(f"p{pagina.numero}: línea {quitada.indice} no es 'Última Reforma DOF'")
        elif quitada.clase == PAGINACION and not _PAGINACION_RE.match(quitada.texto):
            problemas.append(f"p{pagina.numero}: línea {quitada.indice} no es 'N de M'")
    if indices_quitados and pagina.conservadas and max(indices_quitados) > min(pagina.conservadas):
        problemas.append(f"p{pagina.numero}: se quitó una línea posterior al cuerpo de la página")
    if not es_subsecuencia(pagina.lineas_limpias, pagina.lineas):
        problemas.append(f"p{pagina.numero}: el texto limpio no es subsecuencia del original")
    return problemas


def limpiar_documento(
    paginas: Sequence[str],
    *,
    numeros: Sequence[int] | None = None,
    total_paginas: int | None = None,
    titulo: str | None = None,
) -> DocumentoLeyesBiblio:
    """Limpia cada página y contrasta el encabezado entre páginas.

    ``numeros`` son los números de página (base 1) de cada texto en el PDF original;
    por omisión, ``1..len(paginas)``. Deben ser crecientes. ``total_paginas`` (el
    número de páginas del PDF, si quien llama lo conoce) se contrasta con la M de
    "N de M". ``titulo`` (opcional) es el título esperado del encabezado; si no se
    da, se exige el de la mayoría estricta de las páginas reconocidas. Una página cuyo
    título no coincide se conserva íntegra (sin limpiar) y se advierte.
    """
    if isinstance(paginas, str):
        raise TypeError("se esperaba una secuencia de páginas, no un texto")
    numeros = list(numeros) if numeros is not None else list(range(1, len(paginas) + 1))
    if len(numeros) != len(paginas):
        raise ValueError("numeros y paginas deben tener la misma longitud")
    if any(n < 1 for n in numeros) or any(b <= a for a, b in zip(numeros, numeros[1:])):
        raise ValueError(f"los números de página deben ser positivos y crecientes: {numeros}")

    limpias = [limpiar_pagina(texto, numero) for texto, numero in zip(paginas, numeros)]
    advertencias: list[dict] = []
    reconocidas = [p for p in limpias if p.encabezado_reconocido]
    no_reconocidas = [p for p in limpias if not p.encabezado_reconocido]
    if no_reconocidas:
        advertencias.append(
            advertencia(
                "encabezado_no_reconocido",
                "Páginas sin encabezado reconocible: se conservan íntegras.",
                paginas=[p.numero for p in no_reconocidas],
                motivos={str(p.numero): p.motivo for p in no_reconocidas},
            )
        )

    # Título: el indicado por quien llama o el de la mayoría estricta. Las páginas que
    # no coinciden se revierten a su forma íntegra (nada sale como mobiliario).
    conteo = Counter(normalizar_para_cotejo(p.titulo) for p in reconocidas)
    if titulo is not None:
        esperado: str | None = normalizar_para_cotejo(titulo)
    else:
        esperado = next((t for t, n in conteo.items() if 2 * n > len(reconocidas)), None)
    discrepantes = [p for p in reconocidas if normalizar_para_cotejo(p.titulo) != esperado]
    if discrepantes:
        valores: dict[str, list[int]] = {}
        for pagina in reconocidas:
            valores.setdefault(pagina.titulo, []).append(pagina.numero)
        advertencias.append(
            advertencia(
                "titulo_inconsistente",
                "El título del encabezado no coincide entre páginas (o con el esperado); "
                "las páginas discrepantes se conservan íntegras, sin limpiar.",
                valores=valores,
                esperado=titulo,
                paginas_sin_limpiar=[p.numero for p in discrepantes],
            )
        )
        motivo = (
            "título distinto del esperado"
            if titulo is not None
            else "título distinto del de la mayoría de las páginas (o sin mayoría)"
        )
        revertidas = {p.numero for p in discrepantes}
        limpias = [
            _sin_encabezado(p.numero, p.lineas, motivo) if p.numero in revertidas else p
            for p in limpias
        ]
    limpias = tuple(limpias)
    titulo_documento = next(
        (p.titulo for p in limpias if p.encabezado_reconocido), None
    )

    def comun(nombre: str, valores: dict[Any, list[int]], codigo: str) -> Any:
        if len(valores) == 1:
            return next(iter(valores))
        if len(valores) > 1:
            advertencias.append(
                advertencia(
                    codigo,
                    f"El {nombre} del encabezado difiere entre páginas; no se elige ninguno.",
                    valores={str(valor): paginas_ for valor, paginas_ in valores.items()},
                )
            )
        return None

    # Fecha de reforma y paginación: se contrastan en todas las páginas cuyo encabezado
    # se reconoció, incluidas las revertidas por título, para no ocultar contradicciones.
    reformas: dict[str, list[int]] = {}
    totales: dict[int, list[int]] = {}
    for pagina in reconocidas:
        reformas.setdefault(pagina.ultima_reforma, []).append(pagina.numero)
        totales.setdefault(pagina.paginacion[1], []).append(pagina.numero)
        if pagina.paginacion[0] != pagina.numero:
            advertencias.append(
                advertencia(
                    "paginacion_inconsistente",
                    f"La página declarada {pagina.numero} dice "
                    f"'{pagina.paginacion[0]} de {pagina.paginacion[1]}'.",
                    pagina=pagina.numero,
                    paginacion=list(pagina.paginacion),
                )
            )

    reforma = comun("dato de 'Última Reforma DOF'", reformas, "contradiccion_ultima_reforma")
    ultima_reforma_dof = None
    if reforma is not None:
        dia, mes, anio = reforma.split("-")
        fecha = fecha_iso(f"{anio}-{mes}-{dia}")
        if fecha is None:
            advertencias.append(
                advertencia(
                    "fecha_invalida",
                    f"'Última Reforma DOF {reforma}' no es una fecha válida.",
                    valor=reforma,
                )
            )
        else:
            ultima_reforma_dof = fecha.isoformat()
    total = comun("total de páginas (M de 'N de M')", totales, "total_paginas_inconsistente")
    if total is not None and total_paginas is not None and total != total_paginas:
        advertencias.append(
            advertencia(
                "total_paginas_inconsistente",
                f"El encabezado dice {total} páginas y el PDF tiene {total_paginas}.",
                encabezado=total,
                pdf=total_paginas,
            )
        )
        total = None
    return DocumentoLeyesBiblio(
        paginas=limpias,
        titulo=titulo_documento,
        ultima_reforma_dof=ultima_reforma_dof,
        total_paginas=total,
        advertencias=tuple(advertencias),
    )


def verificar_documento(documento: DocumentoLeyesBiblio) -> list[str]:
    """Problemas de invariantes de todas las páginas del documento."""
    return [problema for pagina in documento.paginas for problema in verificar_pagina(pagina)]


# ── Ubicación de artículos ──────────────────────────────────────────────────


def identificador_canonico(articulo: str) -> str:
    """Forma de comparación de un identificador de artículo.

    Sin acentos, ``casefold``, sin espacios, puntos ni guiones, y "º"/"°" como "o":
    ``"4o.-A"`` y ``"4o-A"`` → ``"4oa"``; ``"Décimo Primero"`` → ``"decimoprimero"``.
    "1" y "1o" siguen siendo distintos: la comparación es exacta salvo separadores.
    """
    texto = _PREFIJO_ARTICULO.sub("", articulo)
    texto = sin_acentos(texto).replace("º", "o").replace("°", "o").casefold()
    return re.sub(r"[\s.\-]", "", texto)


def encabezado_articulo(linea: str) -> str | None:
    """Identificador tal como aparece si la línea es encabezado de artículo; si no, ``None``.

    El patrón se aplica sobre la línea sin acentos; el identificador se recorta de la
    línea original (en NFC), de modo que "Único" se devuelve con su acento.
    """
    original = unicodedata.normalize("NFC", linea)
    cotejo = sin_acentos(original)
    coincidencia = _ENCABEZADO_RE.match(cotejo)
    if not coincidencia:
        return None
    if len(cotejo) != len(original):
        # Caracteres que no se alinean 1:1 (raro en texto NFC): se devuelve la forma
        # sin acentos antes que un recorte desplazado.
        return coincidencia.group("id").strip()
    return original[coincidencia.start("id") : coincidencia.end("id")].strip()


def es_frontera_transitorios(linea: str) -> bool:
    """``True`` si la línea es el título "TRANSITORIOS" / "ARTÍCULOS TRANSITORIOS" (con o sin ":")."""
    return bool(_FRONTERA_RE.match(normalizar_para_cotejo(linea).rstrip(":. ")))


@dataclass(frozen=True)
class CoincidenciaArticulo:
    """Línea con encabezado exacto del artículo buscado."""

    pagina: int
    indice: int
    linea: str
    identificador: str
    zona: str


@dataclass(frozen=True)
class UbicacionArticulo:
    """Todas las candidatas; ``unica`` solo existe si hay exactamente una en el cuerpo
    y ninguna en zona indeterminada."""

    articulo: str
    coincidencias: tuple[CoincidenciaArticulo, ...]
    frontera_transitorios: tuple[int, int] | None
    advertencias: tuple[dict, ...] = field(default_factory=tuple)
    # Encabezados con el mismo número base pero otro identificador ("1" frente a "1o",
    # "4o" frente a "4o.-A"). Se informan cuando no hay coincidencia exacta; nunca se eligen.
    variantes_cercanas: tuple[CoincidenciaArticulo, ...] = ()

    @property
    def cuerpo(self) -> tuple[CoincidenciaArticulo, ...]:
        return tuple(c for c in self.coincidencias if c.zona == ZONA_CUERPO)

    @property
    def transitorios(self) -> tuple[CoincidenciaArticulo, ...]:
        return tuple(c for c in self.coincidencias if c.zona == ZONA_TRANSITORIOS)

    @property
    def indeterminadas(self) -> tuple[CoincidenciaArticulo, ...]:
        return tuple(c for c in self.coincidencias if c.zona == ZONA_INDETERMINADA)

    @property
    def ambigua(self) -> bool:
        """Más de una candidata que podría estar en el cuerpo."""
        return len(self.cuerpo) + len(self.indeterminadas) > 1

    @property
    def unica(self) -> CoincidenciaArticulo | None:
        if len(self.cuerpo) == 1 and not self.indeterminadas:
            return self.cuerpo[0]
        return None


def _base_articulo(canonico: str) -> str:
    """Número base del identificador canónico ("4oa" → "4", "19bis" → "19")."""
    numero = re.match(r"\d+", canonico)
    return numero.group(0) if numero else canonico


def _prefijo_contiguo(numeros: Sequence[int]) -> int:
    """Mayor k tal que las páginas 1..k están todas presentes (0 si falta la 1)."""
    presentes = set(numeros)
    k = 0
    while k + 1 in presentes:
        k += 1
    return k


def ubicar_articulo(documento: DocumentoLeyesBiblio, articulo: str) -> UbicacionArticulo:
    """Todas las líneas cuyo encabezado es exactamente el artículo pedido.

    Zonas, en el orden de las páginas recibidas:
      - ``transitorios``: después de la primera línea "TRANSITORIOS" vista (la
        frontera real está en ella o antes, así que esto es cierto aunque falten
        páginas);
      - ``cuerpo``: antes de esa línea, y solo si las páginas recibidas cubren sin
        huecos desde la 1 hasta la de la coincidencia;
      - ``indeterminada``: antes de la frontera, con páginas faltantes: no se sabe si
        hubo una frontera en las páginas que no se recibieron.

    Una remisión ("artículo 167 del presente Código") nunca cuenta. Sin coincidencia
    exacta se advierte ``sin_coincidencia`` (no acredita inexistencia) y, si existen,
    ``variantes_cercanas``.
    """
    buscado = identificador_canonico(articulo)
    if not buscado:
        raise ValueError(f"identificador de artículo vacío: {articulo!r}")
    contiguo_hasta = _prefijo_contiguo(documento.numeros)
    coincidencias: list[CoincidenciaArticulo] = []
    cercanas: list[CoincidenciaArticulo] = []
    frontera: tuple[int, int] | None = None
    for pagina, indice, linea in documento.lineas():
        if frontera is None and es_frontera_transitorios(linea):
            frontera = (pagina, indice)
            continue
        identificador = encabezado_articulo(linea)
        if identificador is None:
            continue
        if frontera is not None:
            zona = ZONA_TRANSITORIOS
        elif pagina <= contiguo_hasta:
            zona = ZONA_CUERPO
        else:
            zona = ZONA_INDETERMINADA
        coincidencia = CoincidenciaArticulo(pagina, indice, linea, identificador, zona)
        canonico = identificador_canonico(identificador)
        if canonico == buscado:
            coincidencias.append(coincidencia)
        elif _base_articulo(canonico) == _base_articulo(buscado):
            cercanas.append(coincidencia)

    def ubicaciones(lista: list[CoincidenciaArticulo]) -> list[list]:
        return [[c.pagina, c.indice, c.identificador, c.zona] for c in lista]

    advertencias: list[dict] = []
    if frontera is None:
        advertencias.append(
            advertencia(
                "sin_frontera_transitorios",
                "No aparece la línea TRANSITORIOS en las páginas recibidas: el cuerpo solo "
                "se acredita en páginas contiguas desde la 1.",
            )
        )
    cuerpo = [c for c in coincidencias if c.zona == ZONA_CUERPO]
    indeterminadas = [c for c in coincidencias if c.zona == ZONA_INDETERMINADA]
    if indeterminadas:
        advertencias.append(
            advertencia(
                "zona_indeterminada",
                "Coincidencias en páginas no contiguas desde la 1: no se sabe si están en "
                "el cuerpo o en transitorios; no se acredita ninguna.",
                ubicaciones=ubicaciones(indeterminadas),
            )
        )
    if len(cuerpo) + len(indeterminadas) > 1:
        advertencias.append(
            advertencia(
                "articulo_ambiguo",
                f"{len(cuerpo) + len(indeterminadas)} encabezados del artículo {articulo!r} "
                "que podrían estar en el cuerpo; no se elige ninguno.",
                ubicaciones=ubicaciones(cuerpo + indeterminadas),
            )
        )
    if coincidencias and not cuerpo and not indeterminadas:
        advertencias.append(
            advertencia(
                "solo_en_transitorios",
                f"El artículo {articulo!r} solo aparece como encabezado en transitorios.",
                ubicaciones=ubicaciones(coincidencias),
            )
        )
    if not coincidencias:
        advertencias.append(
            advertencia(
                "sin_coincidencia",
                f"No hay encabezado exacto del artículo {articulo!r} en las páginas "
                "recibidas; esto no acredita que el artículo no exista.",
            )
        )
        if cercanas:
            advertencias.append(
                advertencia(
                    "variantes_cercanas",
                    "Hay encabezados con el mismo número base y otro identificador "
                    "(ordinal, Bis, letra); se informan sin elegir ninguno.",
                    ubicaciones=ubicaciones(cercanas),
                )
            )
    return UbicacionArticulo(
        articulo=articulo,
        coincidencias=tuple(coincidencias),
        frontera_transitorios=frontera,
        advertencias=tuple(advertencias),
        variantes_cercanas=tuple(cercanas) if not coincidencias else (),
    )


def registro_evidencia(
    documento: DocumentoLeyesBiblio,
    *,
    archivo: str,
    url: str,
    fecha_consulta: str,
    original_sha256: str,
    original_bytes: int,
    extractor: str,
    version_extractor: str,
    medio: str = "descarga_https",
    extracto: dict | None = None,
) -> dict:
    """Registro ``evidencia/1.0`` de páginas de una ley de LeyesBiblio.

    El original es el PDF (su huella y tamaño los declara quien lo descargó); el
    derivado es el texto limpio de las páginas incluidas, y la huella del texto
    extraído antes de limpiar se conserva en ``metadatos.sha256_texto_extraido``. No
    valida: usar ``validar_registro`` y ``comprobar_integridad`` sobre el resultado.
    """
    return construir_registro(
        tipo=TIPO_LEY_LEYESBIBLIO,
        url=url,
        fecha_consulta=fecha_consulta,
        medio=medio,
        original_sha256=original_sha256,
        original_bytes=original_bytes,
        media_type="application/pdf",
        derivado_sha256=sha256_texto(documento.texto),
        extractor=extractor,
        version_extractor=version_extractor,
        transformacion={"nombre": NOMBRE_LIMPIEZA, "version": VERSION_LIMPIEZA},
        metadatos={
            "archivo": archivo,
            "titulo": documento.titulo,
            "ultima_reforma_dof": documento.ultima_reforma_dof,
            "total_paginas": documento.total_paginas,
            "paginas": list(documento.numeros),
            "sha256_texto_extraido": sha256_texto(documento.texto_extraido),
        },
        extracto=extracto,
        advertencias=advertencias_registro(documento),
    )


def advertencias_registro(documento: DocumentoLeyesBiblio) -> list[dict]:
    """Advertencias que lleva el registro: las del documento más cualquier invariante rota."""
    advertencias = [dict(a) for a in documento.advertencias]
    advertencias.extend(
        advertencia("invariante_incumplida", problema) for problema in verificar_documento(documento)
    )
    return advertencias
