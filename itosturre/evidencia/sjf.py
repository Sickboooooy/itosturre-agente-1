"""Parser del texto visible (innerText) del detalle de una tesis en el portal del SJF.

El render público ``https://sjf2.scjn.gob.mx/detalle/tesis/<registro>`` trae, antes de
la tesis, el banner del sitio, que menciona la época vigente del Semanario
(``Duodécima Época "De la Justicia Pluricultural…"``). Tomar "la primera línea que dice
época" atribuye esa época del banner a cualquier tesis (bug del scraper, registro
2006224: Décima Época leída como Duodécima). Por eso este parser se **ancla** en la
línea ``Registro digital:`` y solo lee la época en la región posterior al ancla y
anterior al rubro.

Reglas:
  - Sin ancla → ``ErrorSJF("sin_ancla")``. Dos o más anclas → ``ErrorSJF("ancla_ambigua")``:
    nunca se elige una.
  - Campos ausentes, duplicados, ambiguos o discrepantes producen **advertencias**; el
    parser nunca corrige un dato con otro (p. ej. la época del campo frente al sufijo
    ``(11a.)`` de la clave: se reportan ambos).
  - Las fechas de publicación y de obligatoriedad solo se leen si el texto las declara;
    se conserva la frase cruda. Nunca se infiere vigencia ni obligatoriedad.
  - El pie del sitio (desde ``UBICACIÓN``) queda fuera.
  - Lo que no se reconoce se conserva crudo y marcado (sección ``no_clasificada``).

Funciones puras: sin red, sin E/S y sin reloj.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .esquema import (
    EPOCAS,
    TIPO_TESIS_SJF,
    advertencia,
    construir_registro,
    crear_extracto,
)
from .huellas import json_canonico, normalizar_para_cotejo, sha256_bytes, sha256_texto

VERSION_PARSER = "1.0"
NOMBRE_PARSER = "itosturre.evidencia.sjf.parsear_tesis"

ANCLA = "Registro digital:"
PIE = "UBICACIÓN"

# Etiquetas conocidas del encabezado de la tesis → nombre del campo.
ETIQUETAS = {
    "instancia": "instancia",
    "materia(s)": "materias",
    "tesis": "clave",
    "fuente": "fuente",
    "tipo": "tipo",
}
TIPOS_TESIS = ("Jurisprudencia", "Aislada")
CAMPOS_OBLIGATORIOS = ("instancia", "epoca", "materias", "clave", "fuente", "tipo")
# Solo "Fuente" ocupa varias líneas ("Gaceta…" / "Libro 5, Abril de 2014…"). En los demás
# campos una línea pegada es ajena (p. ej. el texto de un botón "Copiar") y se excluye.
CAMPOS_MULTILINEA = frozenset({"fuente"})
# Clases de sección que nunca pueden ser el texto de la tesis.
_CLASES_NO_TEXTO = frozenset(
    {"publicacion", "nota", "encabezado_contendientes", "precedente", "organo_emisor"}
)

_EPOCA_POR_COTEJO = {normalizar_para_cotejo(epoca): epoca for epoca in EPOCAS}
# Sufijo de época en la clave: "(10a.)" → Décima… Solo 5a a 12a.
_EPOCA_POR_NUMERO = {numero: EPOCAS[numero - 5] for numero in range(5, 13)}
_SUFIJO_CLAVE = re.compile(r"\((\d{1,2})a\.\)\s*$")
_ETIQUETA_TITULO = re.compile(r"^([A-ZÁÉÍÓÚÑ][a-záéíóúñ()]+(?: [a-záéíóúñ()/]+){0,3}):(?:\s|$)")

_MESES = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
_DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_FECHA_LARGA = r"(?P<dia_semana>\w+) (?P<dia>\d{1,2}) de (?P<mes>\w+) de (?P<anio>\d{4})"
_PUBLICACION = re.compile(
    r"Esta tesis se public[óo] el " + _FECHA_LARGA + r"(?: a las (?P<hora>\d{1,2}:\d{2}) horas)?",
    re.IGNORECASE,
)
_OBLIGATORIEDAD = re.compile(
    r"aplicaci[óo]n obligatoria a partir del " + _FECHA_LARGA, re.IGNORECASE
)
# "Amparo directo 335/2022.", "Contradicción de tesis 293/2011.", "Queja 97/2026."
_PRECEDENTE = re.compile(r"^[A-ZÁÉÍÓÚÑ][^.\n]{0,150}?\b\d+/\d{4}\.")
_ESTRUCTURA_11A = ("hechos:", "criterio juridico:", "justificacion:")


class ErrorSJF(ValueError):
    """El texto no permite identificar sin ambigüedad la tesis (``codigo`` explica por qué)."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        self.codigo = codigo
        super().__init__(f"{codigo}: {mensaje}")


@dataclass(frozen=True)
class TesisSJF:
    """Campos leídos del render. ``None`` significa "la fuente no lo dice" o "ambiguo"."""

    registro: str
    instancia: str | None
    epoca: str | None
    epoca_segun_clave: str | None
    materias: tuple[str, ...]
    clave: str | None
    fuente: str | None
    tipo: str | None
    rubro: str | None
    texto: str | None
    secciones: tuple[dict, ...]
    publicacion: dict | None
    obligatoriedad: dict | None
    advertencias: tuple[dict, ...] = field(default_factory=tuple)

    @property
    def notas(self) -> tuple[str, ...]:
        return tuple(s["texto"] for s in self.secciones if s["clase"] == "nota")

    @property
    def precedentes(self) -> tuple[str, ...]:
        return tuple(s["texto"] for s in self.secciones if s["clase"] == "precedente")

    @property
    def fecha_publicacion(self) -> str | None:
        return self.publicacion.get("fecha") if self.publicacion else None

    @property
    def fecha_obligatoriedad(self) -> str | None:
        return self.obligatoriedad.get("fecha") if self.obligatoriedad else None

    def como_dict(self) -> dict:
        """Todo lo leído, serializable (base de la huella del derivado)."""
        return {
            "registro": self.registro,
            "instancia": self.instancia,
            "epoca": self.epoca,
            "epoca_segun_clave": self.epoca_segun_clave,
            "materias": list(self.materias),
            "clave": self.clave,
            "fuente": self.fuente,
            "tipo": self.tipo,
            "rubro": self.rubro,
            "texto": self.texto,
            "secciones": [dict(s) for s in self.secciones],
            "publicacion": dict(self.publicacion) if self.publicacion else None,
            "obligatoriedad": dict(self.obligatoriedad) if self.obligatoriedad else None,
            "advertencias": [dict(a) for a in self.advertencias],
        }

    def metadatos(self) -> dict:
        """Metadatos de identificación para el registro ``evidencia/1.0``."""
        return {
            "registro": self.registro,
            "instancia": self.instancia,
            "epoca": self.epoca,
            "epoca_segun_clave": self.epoca_segun_clave,
            "materias": list(self.materias),
            "clave": self.clave,
            "fuente": self.fuente,
            "tipo_tesis": self.tipo,
            "rubro": self.rubro,
            "fecha_publicacion": self.fecha_publicacion,
            "fecha_obligatoriedad": self.fecha_obligatoriedad,
        }


def _es_blanco(linea: str) -> bool:
    return not linea.strip()


def _epoca_de_linea(linea: str) -> str | None:
    """Época canónica si la línea es exactamente "<ordinal> Época"; si no, ``None``."""
    return _EPOCA_POR_COTEJO.get(normalizar_para_cotejo(linea))


def _etiqueta(linea: str) -> tuple[str | None, str | None, str]:
    """``(campo, etiqueta_cruda, valor)`` si la línea empieza con una etiqueta.

    ``campo`` es ``None`` para etiquetas con forma de título que no están en el
    vocabulario (se reportan como desconocidas, no se confunden con el rubro).
    """
    texto = linea.strip()
    for etiqueta, campo in ETIQUETAS.items():
        prefijo = etiqueta + ":"
        if normalizar_para_cotejo(texto[: len(prefijo)]) == prefijo:
            return campo, texto[: len(prefijo) - 1], texto[len(prefijo):].strip()
    coincidencia = _ETIQUETA_TITULO.match(texto)
    if coincidencia:
        return None, coincidencia.group(1), texto[coincidencia.end():].strip()
    return None, None, texto


def _ancla(lineas: list[str]) -> int:
    indices = [i for i, linea in enumerate(lineas) if linea.strip().startswith(ANCLA)]
    if not indices:
        raise ErrorSJF("sin_ancla", f"no aparece la línea {ANCLA!r}; no se puede ubicar la tesis")
    if len(indices) > 1:
        raise ErrorSJF(
            "ancla_ambigua",
            f"{len(indices)} líneas {ANCLA!r} (líneas {[i + 1 for i in indices]}); no se elige ninguna",
        )
    return indices[0]


def _secciones(lineas: list[str]) -> list[str]:
    """Agrupa en secciones separadas por dos o más líneas en blanco.

    Dentro de una sección se conservan las líneas tal cual (incluidas las líneas en
    blanco simples entre párrafos), unidas por ``\\n``.
    """
    secciones: list[list[str]] = []
    actual: list[str] = []
    blancos = 0
    for linea in lineas:
        if _es_blanco(linea):
            blancos += 1
            continue
        if actual and blancos >= 2:
            secciones.append(actual)
            actual = []
        elif actual and blancos == 1:
            actual.append("")
        actual.append(linea.rstrip())
        blancos = 0
    if actual:
        secciones.append(actual)
    return ["\n".join(seccion) for seccion in secciones]


def _fecha_declarada(
    coincidencia: re.Match, frase: str, nombre: str, advertencias: list[dict]
) -> dict:
    """Fecha leída de la frase; valida calendario y día de la semana (sin corregir)."""
    dia_semana = coincidencia.group("dia_semana")
    resultado: dict[str, Any] = {
        "frase": frase,
        "fecha": None,
        "dia_semana": dia_semana,
    }
    mes = _MESES.get(normalizar_para_cotejo(coincidencia.group("mes")))
    try:
        if mes is None:
            raise ValueError("mes desconocido")
        fecha = date(int(coincidencia.group("anio")), mes, int(coincidencia.group("dia")))
    except ValueError:
        advertencias.append(
            advertencia(
                "fecha_invalida",
                f"La {nombre} declarada no es una fecha válida; se conserva la frase cruda.",
                campo=nombre,
                frase=frase,
            )
        )
        return resultado
    resultado["fecha"] = fecha.isoformat()
    calendario = _DIAS[fecha.weekday()]
    if normalizar_para_cotejo(dia_semana) != calendario:
        advertencias.append(
            advertencia(
                "dia_semana_inconsistente",
                f"La {nombre} dice {dia_semana!r}, pero el {fecha.isoformat()} fue "
                f"{calendario}; no se corrige ninguno de los dos datos.",
                campo=nombre,
                fecha=fecha.isoformat(),
                dia_declarado=dia_semana,
                dia_calendario=calendario,
            )
        )
    return resultado


def _en_mayusculas(linea: str) -> bool:
    """``True`` si la línea tiene letras y ninguna en minúscula (forma del rubro)."""
    letras = [c for c in linea if c.isalpha()]
    return bool(letras) and not any(c.islower() for c in letras)


def _candidatas(patron: re.Pattern, lineas: list[str]) -> list[tuple[int, str, re.Match]]:
    """``(índice de línea, línea cruda, coincidencia)`` de cada aparición del patrón."""
    encontradas = []
    for indice, linea in enumerate(lineas):
        colapsada = " ".join(linea.split())
        for coincidencia in patron.finditer(colapsada):
            encontradas.append((indice, linea.strip(), coincidencia))
    return encontradas


def _clave_fecha(coincidencia: re.Match) -> tuple:
    """Identidad de una fecha declarada (dos frases iguales no son ambigüedad)."""
    grupos = coincidencia.groupdict()
    return (
        normalizar_para_cotejo(grupos["dia_semana"]),
        int(grupos["dia"]),
        normalizar_para_cotejo(grupos["mes"]),
        grupos["anio"],
        grupos.get("hora"),
    )


def _candidato(frase: str, coincidencia: re.Match) -> dict:
    grupos = coincidencia.groupdict()
    return {
        "fecha_declarada": f"{grupos['dia_semana']} {grupos['dia']} de {grupos['mes']} de {grupos['anio']}",
        "frase": frase,
    }


def _clasificar(secciones: list[str]) -> list[dict]:
    """Clase de cada sección posterior al texto de la tesis (vocabulario cerrado)."""
    clasificadas: list[dict] = []
    siguiente_es_contendiente = False
    for seccion in secciones:
        primera = seccion.split("\n", 1)[0].strip()
        cotejo = normalizar_para_cotejo(seccion)
        if siguiente_es_contendiente:
            clase = "contendientes"
            siguiente_es_contendiente = False
        elif cotejo.startswith("esta tesis se publico"):
            clase = "publicacion"
        elif cotejo.startswith(("nota:", "notas:")):
            clase = "nota"
        elif cotejo == "tesis y/o criterios contendientes:":
            clase = "encabezado_contendientes"
            siguiente_es_contendiente = True
        elif _PRECEDENTE.match(primera):
            clase = "precedente"
        elif "\n" not in seccion and primera.endswith(".") and primera == primera.upper() and any(
            c.isalpha() for c in primera
        ):
            clase = "organo_emisor"
        elif " aprobo" in f" {cotejo}" and "tesis" in cotejo:
            clase = "aprobacion"
        else:
            clase = "no_clasificada"
        clasificadas.append({"clase": clase, "texto": seccion})
    return clasificadas


def parsear_tesis(texto: str, *, registro_esperado: str | None = None) -> TesisSJF:
    """Lee el innerText del detalle de una tesis del SJF.

    Lanza ``ErrorSJF`` si no hay ancla, si hay más de una, si el registro no es
    numérico o si no coincide con ``registro_esperado``. Todo lo demás se reporta en
    ``advertencias``.
    """
    if not isinstance(texto, str):
        raise TypeError(f"se esperaba texto, se recibió {type(texto).__name__}")
    lineas = texto.splitlines()
    ancla = _ancla(lineas)
    registro = lineas[ancla].strip()[len(ANCLA):].strip()
    if not registro.isdigit():
        raise ErrorSJF("registro_invalido", f"el registro digital {registro!r} no es numérico")
    if registro_esperado is not None and registro != registro_esperado:
        raise ErrorSJF(
            "registro_discrepante",
            f"se pidió el registro {registro_esperado!r} y el texto corresponde a {registro!r}",
        )
    advertencias: list[dict] = []

    fin = next(
        (i for i in range(ancla + 1, len(lineas)) if normalizar_para_cotejo(lineas[i]) == "ubicacion"),
        None,
    )
    if fin is None:
        fin = len(lineas)
        advertencias.append(
            advertencia(
                "pie_no_encontrado",
                f"No aparece el pie del sitio ({PIE!r}); el cuerpo podría incluir texto ajeno a la tesis.",
            )
        )
    region = lineas[ancla + 1 : fin]

    # ── Encabezado: etiquetas y época entre el ancla y el rubro ────────────────
    valores: dict[str, list[str]] = {}
    epocas: list[str] = []
    campo_actual: str | None = None
    hubo_blanco = True
    inicio_rubro: int | None = None
    for indice, linea in enumerate(region):
        if _es_blanco(linea):
            hubo_blanco = True
            continue
        campo, etiqueta_cruda, valor = _etiqueta(linea)
        epoca = _epoca_de_linea(linea)
        if campo is not None:
            valores.setdefault(campo, []).append(valor)
            campo_actual = campo
        elif etiqueta_cruda is not None:
            advertencias.append(
                advertencia(
                    "campo_desconocido",
                    f"Etiqueta {etiqueta_cruda!r} fuera del vocabulario; la línea se conserva "
                    "cruda en esta advertencia.",
                    linea=linea.strip(),
                )
            )
            campo_actual = None
        elif epoca is not None:
            epocas.append(linea.strip())
            campo_actual = None
        elif campo_actual is not None and not hubo_blanco:
            if campo_actual in CAMPOS_MULTILINEA:
                # Continuación admitida (la segunda línea de "Fuente:").
                valores[campo_actual][-1] += "\n" + linea.strip()
            else:
                advertencias.append(
                    advertencia(
                        "continuacion_no_admitida",
                        f"Línea pegada al campo {campo_actual!r}, que no admite continuación; "
                        "se excluye del campo y se conserva en esta advertencia.",
                        campo=campo_actual,
                        linea=linea.strip(),
                    )
                )
        else:
            inicio_rubro = indice
            break
        hubo_blanco = False

    def unico(campo: str) -> str | None:
        lista = valores.get(campo) or []
        if len(lista) > 1:
            advertencias.append(
                advertencia(
                    "campo_duplicado",
                    f"El campo {campo!r} aparece {len(lista)} veces; no se elige ninguno.",
                    campo=campo,
                    valores=lista,
                )
            )
            return None
        return lista[0] if lista and lista[0] else None

    instancia = unico("instancia")
    clave = unico("clave")
    fuente = unico("fuente")
    tipo = unico("tipo")
    materias_crudo = unico("materias")
    materias = tuple(
        m.strip() for m in (materias_crudo or "").split(",") if m.strip()
    )

    epoca: str | None = None
    if len(epocas) == 1:
        epoca = _epoca_de_linea(epocas[0])
    elif len(epocas) > 1:
        advertencias.append(
            advertencia(
                "epoca_ambigua",
                f"{len(epocas)} líneas de época entre el ancla y el rubro; no se elige ninguna.",
                valores=epocas,
            )
        )

    epoca_segun_clave: str | None = None
    if clave:
        sufijo = _SUFIJO_CLAVE.search(clave)
        if sufijo:
            epoca_segun_clave = _EPOCA_POR_NUMERO.get(int(sufijo.group(1)))
            if epoca_segun_clave is None:
                advertencias.append(
                    advertencia(
                        "sufijo_epoca_desconocido",
                        f"El sufijo {sufijo.group(0)!r} de la clave no corresponde a una época conocida.",
                        clave=clave,
                    )
                )
        else:
            # Normal en épocas anteriores a la Décima; en las recientes delata una clave
            # mal leída. En ambos casos no se infiere la época.
            advertencias.append(
                advertencia(
                    "clave_sin_sufijo_epoca",
                    f"La clave {clave!r} no termina en un sufijo de época como '(11a.)'; "
                    "no se infiere la época desde la clave.",
                    clave=clave,
                )
            )
    if epoca and epoca_segun_clave and epoca != epoca_segun_clave:
        advertencias.append(
            advertencia(
                "epoca_discrepante",
                f"La fuente dice {epoca!r} en el campo de época y la clave {clave!r} indica "
                f"{epoca_segun_clave!r}; se reportan ambos, no se corrige ninguno.",
                epoca_campo=epoca,
                epoca_segun_clave=epoca_segun_clave,
                clave=clave,
            )
        )
    if tipo and normalizar_para_cotejo(tipo) not in {normalizar_para_cotejo(t) for t in TIPOS_TESIS}:
        advertencias.append(
            advertencia(
                "tipo_no_reconocido",
                f"Tipo de tesis {tipo!r} fuera de {list(TIPOS_TESIS)}; se conserva tal cual.",
                tipo=tipo,
            )
        )

    # ── Rubro, texto y secciones posteriores ───────────────────────────────────
    rubro: str | None = None
    texto_tesis: str | None = None
    secciones: list[dict] = []
    if inicio_rubro is not None:
        cuerpo = region[inicio_rubro:]
        fin_rubro = next((i for i, linea in enumerate(cuerpo) if _es_blanco(linea)), len(cuerpo))
        bloque_rubro = [linea.strip() for linea in cuerpo[:fin_rubro]]
        bloques = _secciones(cuerpo[fin_rubro:])
        cuenta_texto = 0
        if all(_en_mayusculas(linea) for linea in bloque_rubro):
            rubro = "\n".join(bloque_rubro)
        else:
            # El rubro del SJF va en mayúsculas. Un bloque que mezcla (p. ej. rubro y
            # texto sin línea en blanco) no se asigna por posición: rubro y texto
            # quedan en None y el bloque se conserva crudo.
            advertencias.append(
                advertencia(
                    "rubro_no_reconocible",
                    "El bloque que sigue al encabezado no tiene forma de rubro (mezcla "
                    "mayúsculas y minúsculas); rubro y texto no se asignan por posición.",
                    campos=["rubro", "texto"],
                    crudo="\n".join(bloque_rubro),
                )
            )
            secciones.append({"clase": "no_clasificada", "texto": "\n".join(bloque_rubro)})
            cuenta_texto = -1  # sin texto: todo lo que sigue se clasifica por contenido
        if bloques and cuenta_texto == 0:
            if normalizar_para_cotejo(bloques[0]).startswith(_ESTRUCTURA_11A[0]):
                while cuenta_texto < len(bloques) and normalizar_para_cotejo(
                    bloques[cuenta_texto]
                ).startswith(_ESTRUCTURA_11A):
                    cuenta_texto += 1
            elif _clasificar(bloques[:1])[0]["clase"] in _CLASES_NO_TEXTO or not any(
                c.islower() for c in bloques[0]
            ):
                advertencias.append(
                    advertencia(
                        "texto_no_reconocible",
                        "El bloque que sigue al rubro no tiene forma de texto de tesis; no se "
                        "asigna por posición.",
                        campo="texto",
                        inicio=bloques[0][:80],
                    )
                )
            else:
                cuenta_texto = 1
            texto_tesis = "\n\n".join(bloques[:cuenta_texto]) or None
        cuenta_texto = max(cuenta_texto, 0)
        secciones.extend(_clasificar(bloques[cuenta_texto:]))
        for seccion in secciones:
            if seccion["clase"] == "no_clasificada":
                advertencias.append(
                    advertencia(
                        "seccion_no_clasificada",
                        "Sección posterior al texto sin clase reconocida; se conserva cruda.",
                        inicio=seccion["texto"][:80],
                    )
                )
        # Etiquetas del encabezado después del rubro: la estructura no es la esperada.
        for linea in cuerpo:
            campo, _, _ = _etiqueta(linea)
            if campo is not None or _epoca_de_linea(linea) is not None:
                advertencias.append(
                    advertencia(
                        "campo_fuera_de_encabezado",
                        "Una etiqueta o época del encabezado aparece después del rubro; "
                        "revisar la estructura del render.",
                        linea=linea.strip(),
                    )
                )

    # ── Publicación y obligatoriedad (solo si el texto las declara) ───────────
    # Se cuentan TODAS las frases en el texto posterior al ancla, línea por línea (cada
    # párrafo del render es una línea), no solo la sección de publicación.
    posteriores = lineas[ancla + 1 :]
    publicaciones = _candidatas(_PUBLICACION, posteriores)
    obligatoriedades = _candidatas(_OBLIGATORIEDAD, posteriores)
    lineas_publicacion = {indice for indice, _, _ in publicaciones}
    publicacion: dict | None = None
    obligatoriedad: dict | None = None
    distintas = {_clave_fecha(coincidencia) for _, _, coincidencia in publicaciones}
    if len(distintas) > 1:
        advertencias.append(
            advertencia(
                "publicacion_ambigua",
                f"{len(distintas)} fechas de publicación distintas declaradas; no se elige ninguna.",
                candidatos=[_candidato(frase, c) for _, frase, c in publicaciones],
            )
        )
    elif publicaciones:
        _, frase, coincidencia = publicaciones[0]
        publicacion = _fecha_declarada(coincidencia, frase, "fecha_publicacion", advertencias)
        publicacion["hora"] = coincidencia.group("hora")
    elif any(s["clase"] == "publicacion" for s in secciones):
        frase = next(s["texto"] for s in secciones if s["clase"] == "publicacion")
        advertencias.append(
            advertencia(
                "publicacion_no_reconocida",
                "Frase de publicación con forma no reconocida; se conserva cruda.",
                frase=frase,
            )
        )

    # La obligatoriedad solo vale dentro de la frase de publicación ("…y, por ende, se
    # considera de aplicación obligatoria a partir del…"). Fuera de ella (p. ej. en una
    # nota que habla de otra tesis) se advierte y no se usa.
    dentro = [o for o in obligatoriedades if o[0] in lineas_publicacion]
    fuera = [o for o in obligatoriedades if o[0] not in lineas_publicacion]
    if fuera:
        advertencias.append(
            advertencia(
                "obligatoriedad_fuera_de_publicacion",
                "Declaración de obligatoriedad fuera de la frase de publicación; no se usa.",
                candidatos=[_candidato(frase, c) for _, frase, c in fuera],
            )
        )
    distintas_obl = {_clave_fecha(coincidencia) for _, _, coincidencia in dentro}
    if dentro and (len(distintas_obl) > 1 or len(distintas) > 1):
        advertencias.append(
            advertencia(
                "obligatoriedad_ambigua",
                "Fecha de obligatoriedad ambigua (varias declaradas o publicación ambigua); "
                "no se elige ninguna.",
                candidatos=[_candidato(frase, c) for _, frase, c in dentro],
            )
        )
    elif dentro:
        _, frase, coincidencia = dentro[0]
        obligatoriedad = _fecha_declarada(coincidencia, frase, "fecha_obligatoriedad", advertencias)

    presentes = {
        "instancia": instancia,
        "epoca": epoca,
        "materias": materias,
        "clave": clave,
        "fuente": fuente,
        "tipo": tipo,
        "rubro": rubro,
        "texto": texto_tesis,
        "fecha_publicacion": publicacion and publicacion.get("fecha"),
    }
    ya_reportados = (
        {a.get("campo") for a in advertencias}
        | {campo for a in advertencias for campo in a.get("campos", [])}
        | {"epoca" for a in advertencias if a["codigo"] == "epoca_ambigua"}
        | {"fecha_publicacion" for a in advertencias if a["codigo"].startswith("publicacion_")}
    )
    for campo, valor in presentes.items():
        if not valor and campo not in ya_reportados:
            advertencias.append(
                advertencia(
                    "campo_ausente",
                    f"La fuente no muestra {campo!r} (o no se pudo leer sin ambigüedad).",
                    campo=campo,
                )
            )
    obligatoriedad_ambigua = any(a["codigo"] == "obligatoriedad_ambigua" for a in advertencias)
    if (
        tipo
        and normalizar_para_cotejo(tipo) == "jurisprudencia"
        and obligatoriedad is None
        and not obligatoriedad_ambigua
    ):
        advertencias.append(
            advertencia(
                "obligatoriedad_no_declarada",
                "Jurisprudencia sin fecha de obligatoriedad en el texto; no se infiere.",
            )
        )
    if tipo and normalizar_para_cotejo(tipo) == "aislada" and obligatoriedad is not None:
        advertencias.append(
            advertencia(
                "obligatoriedad_en_aislada",
                "El texto declara obligatoriedad para una tesis aislada; revisar la fuente.",
            )
        )

    return TesisSJF(
        registro=registro,
        instancia=instancia,
        epoca=epoca,
        epoca_segun_clave=epoca_segun_clave,
        materias=materias,
        clave=clave,
        fuente=fuente,
        tipo=tipo,
        rubro=rubro,
        texto=texto_tesis,
        secciones=tuple(secciones),
        publicacion=publicacion,
        obligatoriedad=obligatoriedad,
        advertencias=tuple(advertencias),
    )


def region_tesis(texto: str) -> str:
    """Texto de la tesis tal como lo muestra el render: desde la línea ``Registro digital:``
    hasta antes del pie del sitio (``UBICACIÓN``), con todos sus campos (instancia, época,
    materias, clave, fuente, tipo, rubro, texto, precedentes, notas y publicación).

    Excluye el banner y el menú del portal (antes del ancla) y el pie. Las líneas se unen
    con ``\\n`` (un render guardado con CRLF da el mismo resultado). Lanza ``ErrorSJF``
    como ``parsear_tesis`` si no hay un ancla única.
    """
    if not isinstance(texto, str):
        raise TypeError(f"se esperaba texto, se recibió {type(texto).__name__}")
    lineas = texto.splitlines()
    ancla = _ancla(lineas)
    fin = next(
        (i for i in range(ancla + 1, len(lineas)) if normalizar_para_cotejo(lineas[i]) == "ubicacion"),
        len(lineas),
    )
    return "\n".join(lineas[ancla:fin])


# Secciones posteriores al texto que pertenecen al criterio de la propia tesis. Las demás
# (precedentes, contendientes, notas, aprobación, no clasificadas) pueden traer rubros o
# datos de otras tesis: no acreditan el criterio propio.
SECCIONES_DEL_CRITERIO = frozenset({"publicacion"})


def region_criterio(texto: str) -> str:
    """Lo que identifica y enuncia la propia tesis en el render: los campos de su ficha (del
    ancla "Registro digital:" al rubro: instancia, época, materias, clave, fuente, tipo), el
    rubro, el texto y la frase de publicación.

    Excluye el banner y el pie del portal y las secciones de precedentes, contendientes,
    notas, aprobación y no clasificadas. Sin rubro reconocible no se puede delimitar la
    ficha: solo quedan el texto y la publicación (falla cerrado). Lanza ``ErrorSJF`` como
    ``parsear_tesis``.
    """
    tesis = parsear_tesis(texto)
    region = region_tesis(texto)
    partes: list[str] = []
    if tesis.rubro:
        corte = region.find(tesis.rubro.split("\n", 1)[0])
        if corte >= 0:
            partes.append(region[:corte])
        partes.append(tesis.rubro)
    if tesis.texto:
        partes.append(tesis.texto)
    partes += [s["texto"] for s in tesis.secciones if s["clase"] in SECCIONES_DEL_CRITERIO]
    return "\n".join(parte for parte in partes if parte)


def derivado_canonico(tesis: TesisSJF) -> str:
    """El derivado de una tesis: JSON canónico de toda la lectura (su huella va al registro)."""
    return json_canonico(tesis.como_dict())


def registro_evidencia(
    original: bytes,
    *,
    url: str,
    fecha_consulta: str,
    medio: str = "render_navegador",
    registro_esperado: str | None = None,
) -> dict:
    """Registro ``evidencia/1.0`` de una tesis a partir de los bytes del innerText.

    Se reciben **bytes** para que la huella del original sea la de lo capturado, sin
    conversiones de fin de línea. El derivado es ``derivado_canonico`` (la lectura
    completa) y el extracto, el rubro literal. No valida: usar ``validar_registro`` y
    ``comprobar_integridad`` sobre el resultado.
    """
    texto = bytes(original).decode("utf-8")
    tesis = parsear_tesis(texto, registro_esperado=registro_esperado)
    return construir_registro(
        tipo=TIPO_TESIS_SJF,
        url=url,
        fecha_consulta=fecha_consulta,
        medio=medio,
        original_sha256=sha256_bytes(original),
        original_bytes=len(original),
        media_type="text/plain; charset=utf-8",
        derivado_sha256=sha256_texto(derivado_canonico(tesis)),
        extractor=NOMBRE_PARSER,
        version_extractor=VERSION_PARSER,
        metadatos=tesis.metadatos(),
        extracto=crear_extracto(tesis.rubro, "rubro") if tesis.rubro else None,
        advertencias=list(tesis.advertencias),
    )

