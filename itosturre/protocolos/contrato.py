"""Gate G1 — contrato de un protocolo de materia.

Un protocolo de materia es conocimiento de fondo que se inyecta a agentes que ya tienen
su rol, sus reglas y su formato de salida: lo complementa, no lo sustituye. Su forma es
la del JSON que ya consume el sistema de destino:

    clave, version, nombre, materia, palabras, datosIndispensables,
    objecionesTipicas, instrucciones   (+ claves "_…" informativas, que se ignoran)

`instrucciones` lleva exactamente las cinco secciones de la plantilla, en su orden y con
su rótulo. Este módulo es determinista: no consulta fuentes ni modelos. Un JSON que no
cumple se rechaza aquí, porque el cargador de destino ignora en silencio un protocolo
mal formado y nadie se enteraría.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

# Catálogo de materias del simulador de destino (claves tal cual, p. ej. "seguridad_social").
MATERIAS = (
    "civil", "penal", "laboral", "mercantil", "familiar",
    "administrativo", "constitucional", "consumidor", "seguridad_social",
)

SECCIONES = (
    "I. JERARQUÍA NORMATIVA PROPIA DE ESTA MATERIA.",
    "II. PRINCIPIOS RECTORES PROPIOS DE ESTA MATERIA.",
    "III. MÉTODOS DE ARGUMENTACIÓN QUE MÁS PESAN EN ESTA MATERIA.",
    "IV. FUENTES DE VERIFICACIÓN PROPIAS DE ESTA MATERIA.",
    "V. ADVERTENCIAS PARTICULARES DE ESTA MATERIA.",
)

CAMPOS = (
    "clave", "version", "nombre", "materia",
    "palabras", "datosIndispensables", "objecionesTipicas", "instrucciones",
)
LISTAS = ("palabras", "datosIndispensables", "objecionesTipicas", "instrucciones")

# "Un bloque independiente y corto, no un documento de treinta páginas" (plantilla).
MAX_PALABRAS_SECCION = 260
MIN_PALABRAS_ACTIVACION = 2  # el selector exige al menos dos coincidencias

_CLAVE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_VERSION_RE = re.compile(r"^v\d+(\.\d+)*$")

ERROR = "ERROR"
AVISO = "AVISO"


@dataclass(frozen=True)
class Hallazgo:
    """Un resultado de un gate: ERROR reprueba; AVISO va al abogado sin reprobar."""

    gate: str
    severidad: str
    codigo: str
    mensaje: str
    ruta: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def norm(texto: str) -> str:
    """Minúsculas y sin diacríticos: la misma normalización que usa el selector de destino
    para comparar palabras de activación con el mensaje del usuario."""
    base = unicodedata.normalize("NFD", (texto or "").lower())
    return unicodedata.normalize("NFC", "".join(c for c in base if unicodedata.category(c) != "Mn"))


# ── Enfoque nacional (criterio del operador, 11-oct-2026) ────────────────────────────────────
# Los protocolos de materia son NACIONALES: no distinguen por el código de una entidad (habría
# que hacer uno por cada entidad del país). Lo local se remite a «la entidad del asunto» con
# [VERIFICAR EN: …]. «México» solo es el país y no cuenta; «Estado de México» sí.
ENTIDADES = (
    "aguascalientes", "baja california sur", "baja california", "campeche", "chiapas", "chihuahua",
    "ciudad de mexico", "coahuila", "colima", "durango", "estado de mexico", "guanajuato",
    "guerrero", "hidalgo", "jalisco", "michoacan", "morelos", "nayarit", "nuevo leon", "oaxaca",
    "puebla", "queretaro", "quintana roo", "san luis potosi", "sinaloa", "sonora", "tabasco",
    "tamaulipas", "tlaxcala", "veracruz", "yucatan", "zacatecas", "distrito federal",
)
_ENTIDAD_RE = re.compile(r"(?<![a-z])(" + "|".join(re.escape(e) for e in ENTIDADES) + r")(?![a-z])")
# Normas municipales del corpus (reglamentos de un ayuntamiento): también son locales.
_MARCAS_MUNICIPALES = ("municipio", "municipal", "ayuntamiento", "guadalajara")


def entidades_mencionadas(texto: str) -> list[str]:
    """Entidades federativas nombradas en el texto (normalizado), sin repetir."""
    return sorted({m.group(1) for m in _ENTIDAD_RE.finditer(norm(texto))})


def es_fuente_local(fuente: str) -> bool:
    """¿El archivo indexado es una ley o un reglamento de una entidad o de un municipio? Mira
    el nombre sin espacios ni signos, porque varios PDF lo traen pegado
    ("…EstadodeJalisco", "RegMovilidad…Guadalajara")."""
    plano = re.sub(r"[^a-z]", "", norm(fuente))
    return (any(e.replace(" ", "") in plano for e in ENTIDADES)
            or any(m in plano for m in _MARCAS_MUNICIPALES))


def clave_esperada(materia: str) -> str:
    return f"{materia}_materia"


def _error(codigo: str, mensaje: str, ruta: str = "") -> Hallazgo:
    return Hallazgo("G1", ERROR, codigo, mensaje, ruta)


def _aviso(codigo: str, mensaje: str, ruta: str = "") -> Hallazgo:
    return Hallazgo("G1", AVISO, codigo, mensaje, ruta)


_CANONICAS = {c.lower(): c for c in CAMPOS}


def canonizar(protocolo: dict) -> dict:
    """Mismas claves con la grafía canónica: el cargador de destino no distingue mayúsculas
    ("Palabras" carga igual que "palabras"), así que aquí tampoco se pierde el valor."""
    return {_CANONICAS.get(k.lower(), k) if isinstance(k, str) else k: v for k, v in protocolo.items()}


def validar_esquema(protocolo: Any) -> list[Hallazgo]:
    """Hallazgos de G1. Lista vacía = el protocolo cumple el contrato."""
    if not isinstance(protocolo, dict):
        return [_error("NO_ES_OBJETO", "el protocolo debe ser un objeto JSON")]
    hallazgos: list[Hallazgo] = []

    for clave in protocolo:
        if clave.startswith("_") or clave in CAMPOS:
            continue
        if clave.lower() in _CANONICAS:
            hallazgos.append(_aviso(
                "MAYUSCULAS", f"'{clave}' debería escribirse '{_CANONICAS[clave.lower()]}'", clave))
        else:
            hallazgos.append(_error(
                "CAMPO_DESCONOCIDO",
                f"'{clave}' no es un campo del protocolo: el cargador lo ignoraría sin avisar "
                "(¿error de dedo?). Las notas informativas van en claves que empiezan con '_'",
                clave))
    protocolo = canonizar(protocolo)

    for campo in ("clave", "version", "nombre", "materia"):
        valor = protocolo.get(campo)
        if not isinstance(valor, str) or not valor.strip():
            hallazgos.append(_error("CAMPO_VACIO", f"'{campo}' es obligatorio y no puede ir vacío", campo))
    for campo in LISTAS:
        valor = protocolo.get(campo)
        if not isinstance(valor, list) or not valor:
            hallazgos.append(_error("LISTA_VACIA", f"'{campo}' debe ser una lista no vacía", campo))
        elif not all(isinstance(x, str) and x.strip() for x in valor):
            hallazgos.append(_error("ELEMENTO_INVALIDO", f"'{campo}' solo admite textos no vacíos", campo))
    if any(h.severidad == ERROR for h in hallazgos):
        return hallazgos

    materia = protocolo["materia"]
    if materia not in MATERIAS:
        hallazgos.append(_error(
            "MATERIA_FUERA_DE_CATALOGO",
            f"materia '{materia}' no está en el catálogo del simulador: {', '.join(MATERIAS)}", "materia"))
    elif protocolo["clave"] != clave_esperada(materia):
        hallazgos.append(_error(
            "CLAVE", f"la clave debe ser '{clave_esperada(materia)}' (no chocar con los protocolos de asunto)",
            "clave"))
    if not _CLAVE_RE.match(protocolo["clave"]):
        hallazgos.append(_error("CLAVE", "la clave solo admite minúsculas, dígitos y '_'", "clave"))
    if not _VERSION_RE.match(protocolo["version"]):
        hallazgos.append(_error("VERSION", "la versión debe tener la forma v1, v1.1, …", "version"))

    normalizadas = [norm(p).strip() for p in protocolo["palabras"]]
    if len(set(normalizadas)) < MIN_PALABRAS_ACTIVACION:
        hallazgos.append(_error(
            "ACTIVACION", f"hacen falta al menos {MIN_PALABRAS_ACTIVACION} palabras de activación distintas",
            "palabras"))
    duplicadas = sorted({p for p in normalizadas if normalizadas.count(p) > 1})
    if duplicadas:
        hallazgos.append(_aviso("PALABRA_DUPLICADA", f"palabras repetidas: {', '.join(duplicadas)}", "palabras"))
    cortas = [p for p in normalizadas if len(p) < 3]
    if cortas:
        hallazgos.append(_error(
            "PALABRA_CORTA", f"palabras demasiado cortas para activar con seguridad: {cortas}", "palabras"))

    instrucciones = protocolo["instrucciones"]
    if len(instrucciones) != len(SECCIONES):
        hallazgos.append(_error(
            "SECCIONES", f"'instrucciones' debe tener exactamente {len(SECCIONES)} secciones (I–V); tiene "
            f"{len(instrucciones)}", "instrucciones"))
    for i, (texto, rotulo) in enumerate(zip(instrucciones, SECCIONES)):
        if not texto.startswith(rotulo):
            hallazgos.append(_error(
                "ROTULO", f"la sección {i + 1} debe empezar con «{rotulo}»", f"instrucciones[{i}]"))
        palabras = len(texto.split())
        if palabras > MAX_PALABRAS_SECCION:
            hallazgos.append(_error(
                "SECCION_LARGA",
                f"la sección {i + 1} tiene {palabras} palabras (tope {MAX_PALABRAS_SECCION}): el protocolo "
                "de materia es un bloque corto que complementa, no un tratado", f"instrucciones[{i}]"))
    return hallazgos


def textos(protocolo: dict) -> list[tuple[str, str]]:
    """(ruta, texto) de todos los textos del protocolo, en orden estable."""
    protocolo = canonizar(protocolo)
    salida: list[tuple[str, str]] = []
    if isinstance(protocolo.get("nombre"), str):
        salida.append(("nombre", protocolo["nombre"]))
    for campo in LISTAS:
        for i, valor in enumerate(protocolo.get(campo) or []):
            if isinstance(valor, str):
                salida.append((f"{campo}[{i}]", valor))
    return salida
