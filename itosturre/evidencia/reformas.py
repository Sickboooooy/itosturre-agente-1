"""Notas de reforma de LeyesBiblio ("Párrafo reformado DOF 04-12-2006, 10-06-2011").

Cada nota es una secuencia de eventos ``<elemento> <acción> [detalle] DOF <fechas>``
separados por punto::

    Fracción adicionada DOF 08-12-2005. Derogada DOF 15-10-2012. Adicionada DOF 10-02-2014.
    Fe de erratas al artículo DOF 14-03-1951. Reformado DOF 25-10-1967, 31-12-1994
    Fracción recorrida (antes fracción XXVIII) por derogación de fracciones XXV y XXVI DOF 20-08-1928. Reformada DOF 29-04-1933,
    09-08-2012
    Reforma DOF 20-12-2024: Derogó del artículo el entonces párrafo segundo

Invariante obligatorio: en una nota ``reconocida`` el multiconjunto de fechas
``dd-mm-aaaa`` del texto crudo es exactamente el de las fechas de sus eventos. Si no
cuadra —una fecha dentro del detalle, una anotación "(2 reformas)", una fecha partida,
una forma no prevista— la nota queda ``reconocida=False``, sin eventos y con el crudo
intacto. Nunca se inventa ni se pierde una fecha.

``extraer_notas`` localiza las notas en una secuencia de líneas y une las que la fuente
parte en dos líneas (terminan en coma, en palabra colgante o con paréntesis abierto, o
la siguiente empieza por fecha, por "DOF" o por una acción como "Compilada DOF").
Las líneas con fecha que no forman parte de una nota (p. ej. "(sic DOF 05-02-1917)"
dentro del texto) se devuelven aparte, sin interpretar.

Funciones puras: sin red, sin E/S y sin reloj.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Sequence

from .esquema import advertencia
from .huellas import sin_acentos

FECHA_DOF = re.compile(r"\d{2}-\d{2}-\d{4}")
# Cualquier forma de fecha, completa o partida ("28-12-", "4-12-2006", "04/12/2006").
# Se busca en textos que no deben contener fechas (elemento, detalle, texto final): si
# aparece, la nota no se reconoce.
_FRAGMENTO_FECHA = re.compile(r"\d{1,2}\s*-\s*\d{1,2}\s*-|\d{1,2}/\d{1,2}/\d{2,4}|\d+-\d+-\d+")
_GRUPO_DOF = re.compile(r"\bDOF\s+(\d{2}-\d{2}-\d{4}(?:\s*,\s*\d{2}-\d{2}-\d{4})*)")

# Primera palabra del elemento (sin acentos, minúsculas).
ELEMENTOS = frozenset(
    {
        "articulo",
        "articulos",
        "parrafo",
        "parrafos",
        "fraccion",
        "fracciones",
        "inciso",
        "incisos",
        "subinciso",
        "subincisos",
        "apartado",
        "apartados",
        "base",
        "bases",
        "numeral",
        "numerales",
        "epigrafe",
        "encabezado",
        "denominacion",
        "capitulo",
        "capitulos",
        "titulo",
        "titulos",
        "seccion",
        "secciones",
        "libro",
        "libros",
        "multa",
        "multas",
        "cantidad",
        "cantidades",
        "tabla",
        "tablas",
        "anexo",
        "apendice",
        "epigrafes",
        "codigo",
        "ley",
        "decreto",
        "reglamento",
    }
)
# Palabras que unen sustantivos del elemento ("Multa de la fracción", "Párrafo y
# epígrafe del artículo", "Fracción con incisos").
_CONECTORES_ELEMENTO = frozenset({"de", "del", "la", "las", "los", "el", "con", "y", "e", "a", "al"})
# Negaciones: nunca forman parte de una nota reconocible ("Párrafo no reformado").
_NEGACIONES = frozenset({"no", "ni", "nunca", "jamas"})
# Designación de un elemento: "Apartado B", "Fracción XXIX", "Apéndice 1".
_DESIGNACION = re.compile(r"^(?:[A-Z]|[IVXLC]+|\d+)$")
# Raíz del participio (o adjetivo) → acción canónica.
ACCIONES = {
    "reformad": "reformado",
    "adicionad": "adicionado",
    "derogad": "derogado",
    "recorrid": "recorrido",
    "reubicad": "reubicado",
    "compilad": "compilado",
    "actualizad": "actualizado",
    "suprimid": "suprimido",
    "abrogad": "abrogado",
    "restablecid": "restablecido",
    "reenumerad": "reenumerado",
    "renumerad": "renumerado",
    "reestructurad": "reestructurado",
    "trasladad": "trasladado",
    "declarad": "declarado",
    "publicad": "publicado",
    "terminad": "terminado",
    "modificad": "modificado",
}
FE_DE_ERRATAS = "fe_de_erratas"
REFORMA = "reforma"
ACLARACION = "aclaracion"
ORIGINAL = "original"

_PALABRA_ACCION = re.compile(
    r"\b(?P<palabra>(?:" + "|".join(ACCIONES) + r")(?:o|a|os|as)|original)\b",
    re.IGNORECASE,
)
_FE_DE_ERRATAS = re.compile(
    r"^Fe de erratas(?:\s+(?:al|a la|a los|a las)\s+(?P<elemento>.+))?$", re.IGNORECASE
)
_ACLARACION = re.compile(r"^Aclaraci[óo]n(?:\s+(?P<detalle>.+))?$", re.IGNORECASE)
_CONECTORES = frozenset({"y", "e", "o", "sin", "con", "de", "del", "la", "el", "las", "los", "por", "a", "al", "en"})
# Inicio de nota: palabra de elemento seguida (sin cifras ni puntuación fuerte) de una
# acción, o los encabezados especiales.
_INICIO_ELEMENTO = re.compile(
    r"^(?P<primera>[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\b[^\d.;:]{0,80}?\b(?:"
    + "|".join(ACCIONES)
    + r")(?:o|a|os|as)\b|^(?P<primera_original>[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+) original\b"
)
# "y publicada DOF 20-08-2025": la línea anterior terminó en fecha, pero la nota sigue.
_CONECTOR_ACCION = re.compile(
    r"^(?:y|e)\s+(?:" + "|".join(ACCIONES) + r")(?:o|a|os|as)\b"
)
_INICIO_ESPECIAL = re.compile(r"^(?:Fe de erratas\b|Reforma DOF\b|Aclaraci[óo]n\b.*\bDOF\b)")
_INICIO_EDITORIAL = re.compile(r"^Notas?:")
MAX_LINEAS_NOTA = 6
MAX_LINEAS_EDITORIAL = 10


@dataclass(frozen=True)
class EventoReforma:
    """Un evento de la historia del elemento: acción, fechas DOF (ISO) y detalle crudo."""

    accion: str
    accion_texto: str
    fechas: tuple[str, ...]
    elemento: str | None = None
    detalle: str | None = None

    def como_dict(self) -> dict:
        return {
            "accion": self.accion,
            "accion_texto": self.accion_texto,
            "fechas": list(self.fechas),
            "elemento": self.elemento,
            "detalle": self.detalle,
        }


@dataclass(frozen=True)
class NotaReforma:
    """Nota cruda y, si se reconoció, su elemento y eventos."""

    crudo: str
    reconocida: bool
    tipo: str = "nota_reforma"
    elemento: str | None = None
    eventos: tuple[EventoReforma, ...] = ()
    cola: str | None = None
    motivo: str | None = None
    lineas: tuple[int, ...] = ()

    @property
    def fechas_en_crudo(self) -> tuple[str, ...]:
        """Fechas ``dd-mm-aaaa`` del texto crudo, en orden (siempre disponibles)."""
        return tuple(FECHA_DOF.findall(self.crudo))

    @property
    def fechas_eventos(self) -> tuple[str, ...]:
        return tuple(fecha for evento in self.eventos for fecha in evento.fechas)

    def como_dict(self) -> dict:
        return {
            "crudo": self.crudo,
            "reconocida": self.reconocida,
            "tipo": self.tipo,
            "elemento": self.elemento,
            "eventos": [evento.como_dict() for evento in self.eventos],
            "cola": self.cola,
            "motivo": self.motivo,
            "lineas": list(self.lineas),
        }


@dataclass(frozen=True)
class ResultadoNotas:
    """Notas encontradas y líneas con fecha que no pertenecen a ninguna nota."""

    notas: tuple[NotaReforma, ...]
    lineas_con_fecha_fuera_de_nota: tuple[int, ...]
    advertencias: tuple[dict, ...] = field(default_factory=tuple)


def fecha_dof_a_iso(fecha: str) -> str | None:
    """``"04-12-2006"`` → ``"2006-12-04"``; ``None`` si no es una fecha de calendario."""
    if not FECHA_DOF.fullmatch(fecha):
        return None
    dia, mes, anio = fecha.split("-")
    try:
        return date(int(anio), int(mes), int(dia)).isoformat()
    except ValueError:
        return None


def iso_a_fecha_dof(fecha: str) -> str:
    """``"2006-12-04"`` → ``"04-12-2006"`` (inversa de ``fecha_dof_a_iso``)."""
    anio, mes, dia = fecha.split("-")
    return f"{dia}-{mes}-{anio}"


def invariante_fechas(nota: NotaReforma) -> bool:
    """El multiconjunto de fechas del crudo es el de los eventos (si está reconocida).

    Una nota no reconocida no tiene eventos: sus fechas viven solo en el crudo.
    """
    if not nota.reconocida:
        return not nota.eventos
    parseadas = Counter(iso_a_fecha_dof(fecha) for fecha in nota.fechas_eventos)
    return Counter(nota.fechas_en_crudo) == parseadas


def _no_reconocida(crudo: str, motivo: str, tipo: str = "nota_reforma") -> NotaReforma:
    return NotaReforma(crudo=crudo, reconocida=False, tipo=tipo, motivo=motivo)


def _clave(palabra: str) -> str:
    return sin_acentos(palabra).casefold()


def accion_de_palabra(palabra: str) -> str | None:
    """Acción canónica si la palabra **completa** es una acción ("Reformada" → "reformado")."""
    clave = _clave(palabra)
    if clave == ORIGINAL:
        return ORIGINAL
    coincidencia = re.fullmatch(r"(" + "|".join(ACCIONES) + r")(?:o|a|os|as)", clave)
    return ACCIONES[coincidencia.group(1)] if coincidencia else None


def _longitud_elemento(palabras: list[str]) -> int:
    """Cuántas palabras forman el elemento: ``SUSTANTIVO [DESIGNACIÓN] (CONECTOR+ SUSTANTIVO [DESIGNACIÓN])*``.

    Los sustantivos son del vocabulario ``ELEMENTOS``; la designación es una letra
    mayúscula, un romano o un número ("Apartado B", "Apéndice 1"). ``0`` si la primera
    palabra no es un elemento.
    """

    def con_designacion(i: int) -> int:
        return i + 1 if i < len(palabras) and _DESIGNACION.match(palabras[i]) else i

    if not palabras or _clave(palabras[0]) not in ELEMENTOS:
        return 0
    i = con_designacion(1)
    while i < len(palabras):
        j = i
        while j < len(palabras) and _clave(palabras[j]) in _CONECTORES_ELEMENTO:
            j += 1
        if j == i or j >= len(palabras) or _clave(palabras[j]) not in ELEMENTOS:
            break
        i = con_designacion(j + 1)
    return i


def _segmento(texto: str, primero: bool) -> tuple[str | None, str, str, str | None] | str:
    """``(elemento, accion, accion_texto, detalle)`` del texto previo a "DOF"; o el motivo del fallo.

    Gramática completa: ``[ELEMENTO] ACCIÓN [DETALLE]``, con la acción inmediatamente
    después del elemento. El detalle no puede contener otra acción (dos lecturas
    posibles: "Reformado y reubicado") ni una negación ("no", "ni").
    """
    texto = texto.strip()
    if not texto:
        return "evento sin acción antes de DOF"
    if FECHA_DOF.search(texto) or _FRAGMENTO_FECHA.search(texto):
        return f"fecha fuera de la lista DOF ({texto!r})"
    if "DOF" in texto.split():
        return f"'DOF' sin fecha ({texto!r})"
    palabras = texto.split()
    negacion = [p for p in palabras if _clave(p.strip("(),.;:")) in _NEGACIONES]
    if negacion:
        return f"negación en la nota ({texto!r})"
    fe = _FE_DE_ERRATAS.match(texto)
    if fe:
        elemento = fe.group("elemento")
        if elemento is not None and _longitud_elemento(elemento.split()) != len(elemento.split()):
            return f"elemento de la fe de erratas no reconocible ({elemento!r})"
        return elemento, FE_DE_ERRATAS, texto, None
    if primero and texto == "Reforma":
        return None, REFORMA, texto, None
    aclaracion = _ACLARACION.match(texto)
    if aclaracion:
        return None, ACLARACION, texto, aclaracion.group("detalle")
    largo = _longitud_elemento(palabras)
    if primero and largo == 0:
        return f"la nota no empieza por un elemento del vocabulario ({texto!r})"
    if largo >= len(palabras):
        return f"elemento sin acción ({texto!r})"
    accion = accion_de_palabra(palabras[largo])
    if accion is None:
        return f"palabra inesperada tras el elemento: {palabras[largo]!r} ({texto!r})"
    resto = palabras[largo + 1 :]
    otras = [p for p in resto if accion_de_palabra(p.strip("(),.;:"))]
    if otras:
        return f"más de una acción en el evento ({texto!r})"
    elemento = " ".join(palabras[:largo]) or None
    detalle = " ".join(resto) or None
    return elemento, accion, palabras[largo], detalle


def parsear_nota(crudo: str) -> NotaReforma:
    """Interpreta una nota completa (ya unida si venía partida en varias líneas)."""
    if not isinstance(crudo, str):
        raise TypeError(f"se esperaba texto, se recibió {type(crudo).__name__}")
    texto = " ".join(crudo.split())
    if _INICIO_EDITORIAL.match(texto):
        return _no_reconocida(crudo, "nota editorial: se conserva sin interpretar", "nota_editorial")
    grupos = list(_GRUPO_DOF.finditer(texto))
    if not grupos:
        return _no_reconocida(crudo, "sin 'DOF dd-mm-aaaa'")

    eventos: list[EventoReforma] = []
    inicio = 0
    for numero, grupo in enumerate(grupos):
        previo = texto[inicio : grupo.start()]
        if numero > 0:
            # Entre dos grupos DOF solo cabe ". <Acción> [detalle]".
            if not previo.lstrip().startswith("."):
                return _no_reconocida(crudo, f"separador inesperado entre eventos ({previo!r})")
            previo = previo.lstrip()[1:]
        segmento = _segmento(previo, primero=numero == 0)
        if isinstance(segmento, str):
            return _no_reconocida(crudo, segmento)
        elemento, accion, accion_texto, detalle = segmento
        fechas = []
        for fecha in FECHA_DOF.findall(grupo.group(1)):
            iso = fecha_dof_a_iso(fecha)
            if iso is None:
                return _no_reconocida(crudo, f"fecha inexistente en el calendario ({fecha})")
            fechas.append(iso)
        eventos.append(
            EventoReforma(
                accion=accion,
                accion_texto=accion_texto,
                fechas=tuple(fechas),
                elemento=elemento,
                detalle=detalle,
            )
        )
        inicio = grupo.end()

    cola = texto[inicio:].strip()
    if cola in ("", "."):
        cola_final = None
    elif cola.startswith(":") and eventos[-1].accion == REFORMA:
        cola_final = cola
    elif cola.startswith("(") and cola.rstrip(".").endswith(")"):
        cola_final = cola
    else:
        return _no_reconocida(crudo, f"texto final no reconocido ({cola!r})")
    if cola_final and (FECHA_DOF.search(cola_final) or _FRAGMENTO_FECHA.search(cola_final)):
        return _no_reconocida(crudo, "fecha en el texto final de la nota")

    nota = NotaReforma(
        crudo=crudo,
        reconocida=True,
        elemento=eventos[0].elemento,
        eventos=tuple(eventos),
        cola=cola_final,
    )
    # Red de seguridad: el invariante decide, no la gramática.
    if not invariante_fechas(nota):
        return _no_reconocida(crudo, "las fechas parseadas no cuadran con las del texto")
    return nota


def es_inicio_nota(linea: str) -> bool:
    """``True`` si la línea abre una nota de reforma o una nota editorial ("Nota: …")."""
    texto = linea.strip()
    if _INICIO_ESPECIAL.match(texto) or _INICIO_EDITORIAL.match(texto):
        return True
    coincidencia = _INICIO_ELEMENTO.match(texto)
    if not coincidencia:
        return False
    primera = coincidencia.group("primera") or coincidencia.group("primera_original")
    return sin_acentos(primera).casefold() in ELEMENTOS


def _continua(acumulado: str, siguiente: str) -> bool:
    """¿La línea ``siguiente`` continúa la nota ``acumulado``? (reglas observadas en la fuente)."""
    if not siguiente:
        return False
    # Fecha, "DOF …" o paréntesis ("(antes adicionados DOF …)") al inicio: la nota sigue.
    if FECHA_DOF.match(siguiente) or siguiente.startswith(("DOF ", "(")):
        return True
    if acumulado.endswith(",") or acumulado.count("(") > acumulado.count(")"):
        return True
    if es_inicio_nota(siguiente):
        return False
    accion = _PALABRA_ACCION.match(siguiente)
    if accion and siguiente[:1].isupper() and "DOF" in siguiente:
        return True
    if _CONECTOR_ACCION.match(siguiente):
        return True
    ultima = sin_acentos(acumulado.split()[-1]).casefold() if acumulado.split() else ""
    return bool(_PALABRA_ACCION.fullmatch(ultima)) or ultima in _CONECTORES


def extraer_notas(lineas: Sequence[str]) -> ResultadoNotas:
    """Localiza las notas en ``lineas`` (índices relativos a esa secuencia).

    Cada nota guarda en ``crudo`` sus líneas originales unidas por ``\\n``. Las líneas
    con fecha ``dd-mm-aaaa`` que no forman parte de una nota se listan aparte.
    """
    if isinstance(lineas, str):
        raise TypeError("se esperaba una secuencia de líneas, no un texto")
    notas: list[NotaReforma] = []
    fuera: list[int] = []
    advertencias: list[dict] = []
    i = 0
    while i < len(lineas):
        texto = lineas[i].strip()
        if not es_inicio_nota(texto):
            if FECHA_DOF.search(lineas[i]):
                fuera.append(i)
            if re.search(r"\d{1,2}-\d{1,2}-\s*$", lineas[i]):
                advertencias.append(
                    advertencia(
                        "fecha_partida",
                        "Una fecha parece continuar en la línea siguiente; no se cuenta como fecha.",
                        linea=i,
                    )
                )
            i += 1
            continue
        editorial = bool(_INICIO_EDITORIAL.match(texto))
        maximo = MAX_LINEAS_EDITORIAL if editorial else MAX_LINEAS_NOTA
        indices = [i]
        acumulado = texto
        while len(indices) < maximo and indices[-1] + 1 < len(lineas):
            siguiente = lineas[indices[-1] + 1].strip()
            if editorial:
                # La nota editorial es un párrafo: termina en la línea en blanco o donde
                # empieza una nota de reforma.
                if not siguiente or es_inicio_nota(siguiente):
                    break
            elif not _continua(acumulado, siguiente):
                break
            indices.append(indices[-1] + 1)
            acumulado = f"{acumulado} {siguiente}"
        crudo = "\n".join(lineas[k] for k in indices)
        if "DOF" not in acumulado and not FECHA_DOF.search(acumulado):
            # Tiene forma de nota pero no cita el DOF (p. ej. "Fracción derogada."):
            # no es nota de reforma y no tiene fechas que perder.
            i += 1
            continue
        notas.append(replace(parsear_nota(crudo), lineas=tuple(indices)))
        i = indices[-1] + 1
    return ResultadoNotas(
        notas=tuple(notas),
        lineas_con_fecha_fuera_de_nota=tuple(fuera),
        advertencias=tuple(advertencias),
    )


def verificar_fechas(lineas: Sequence[str], resultado: ResultadoNotas) -> list[str]:
    """Problemas de conservación de fechas (``[]`` si no se perdió ni inventó ninguna).

    1. Cada nota cumple ``invariante_fechas``.
    2. Las fechas de todas las líneas son exactamente las de las notas más las de las
       líneas fuera de nota (ninguna línea se cuenta dos veces ni se omite).
    """
    problemas: list[str] = []
    for nota in resultado.notas:
        if not invariante_fechas(nota):
            problemas.append(f"nota en líneas {list(nota.lineas)}: fechas no cuadran")
    usadas = [k for nota in resultado.notas for k in nota.lineas]
    if len(usadas) != len(set(usadas)):
        problemas.append("una línea pertenece a más de una nota")
    if set(usadas) & set(resultado.lineas_con_fecha_fuera_de_nota):
        problemas.append("una línea figura como nota y como fuera de nota")
    total = Counter(f for linea in lineas for f in FECHA_DOF.findall(linea))
    cubiertas: Counter = Counter()
    for nota in resultado.notas:
        cubiertas.update(nota.fechas_en_crudo)
    for indice in resultado.lineas_con_fecha_fuera_de_nota:
        cubiertas.update(FECHA_DOF.findall(lineas[indice]))
    if total != cubiertas:
        faltan = total - cubiertas
        sobran = cubiertas - total
        problemas.append(f"fechas no conservadas: faltan {dict(faltan)}, sobran {dict(sobran)}")
    return problemas

