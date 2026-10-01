"""Huellas (SHA-256), normalización para cotejo y JSON canónico.

Tres herramientas con propósitos que no deben mezclarse:

* ``sha256_bytes`` / ``sha256_texto``: identidad exacta. El texto se codifica en UTF-8
  tal cual llega, **sin normalizar** (ni Unicode ni espacios): dos textos que se ven
  iguales pero difieren en un byte tienen huellas distintas, y eso es lo correcto.
* ``normalizar_para_cotejo``: **solo para comparar**. Quita acentos, colapsa espacios
  y aplica ``casefold``. Su resultado nunca se almacena como evidencia ni se muestra al
  abogado: lo que se guarda y se cita es siempre el texto original.
* ``json_canonico`` / ``huella_registro``: serialización determinista de un registro
  para que su huella no dependa del orden de las llaves.

Todas las funciones son puras: sin E/S, sin red y sin reloj.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any, Mapping

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(datos: bytes) -> str:
    """SHA-256 hexadecimal (minúsculas) de una secuencia de bytes."""
    if not isinstance(datos, (bytes, bytearray, memoryview)):
        raise TypeError(f"se esperaban bytes, se recibió {type(datos).__name__}")
    return hashlib.sha256(bytes(datos)).hexdigest()


def sha256_texto(texto: str) -> str:
    """SHA-256 del texto codificado en UTF-8, sin normalización alguna."""
    if not isinstance(texto, str):
        raise TypeError(f"se esperaba texto, se recibió {type(texto).__name__}")
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def es_sha256(valor: Any) -> bool:
    """``True`` si ``valor`` es una huella SHA-256 en hexadecimal de 64 minúsculas."""
    return isinstance(valor, str) and bool(_HEX64.match(valor))


def sin_acentos(texto: str) -> str:
    """Quita las marcas diacríticas (descomposición NFD sin categoría ``Mn``).

    Para cotejo únicamente: "Época" → "Epoca", "ñ" → "n".
    """
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def normalizar_para_cotejo(texto: str) -> str:
    """Forma de comparación: sin acentos, espacios colapsados y ``casefold``.

    SOLO PARA COMPARAR. Nunca almacenar ni mostrar este valor: la evidencia conserva
    el texto original con sus acentos, mayúsculas y espacios.
    """
    if not isinstance(texto, str):
        raise TypeError(f"se esperaba texto, se recibió {type(texto).__name__}")
    return " ".join(sin_acentos(texto).casefold().split())


def _validar_json_canonico(valor: Any, ruta: str) -> None:
    """Rechaza tipos sin forma canónica única (flotantes, bytes, objetos)."""
    if valor is None or isinstance(valor, (bool, int, str)):
        return
    if isinstance(valor, float):
        # La representación textual de un flotante no es canónica entre
        # implementaciones; los registros de evidencia no los necesitan.
        raise ValueError(f"{ruta}: los flotantes no tienen forma canónica")
    if isinstance(valor, Mapping):
        for llave, contenido in valor.items():
            if not isinstance(llave, str):
                raise ValueError(f"{ruta}: llave no textual {llave!r}")
            _validar_json_canonico(contenido, f"{ruta}.{llave}")
        return
    if isinstance(valor, (list, tuple)):
        for indice, contenido in enumerate(valor):
            _validar_json_canonico(contenido, f"{ruta}[{indice}]")
        return
    raise ValueError(f"{ruta}: tipo {type(valor).__name__} no serializable de forma canónica")


def json_canonico(registro: Any) -> str:
    """JSON determinista: llaves ordenadas, sin espacios, UTF-8 literal.

    Solo admite ``dict`` (llaves texto), listas/tuplas, texto, enteros, booleanos y
    ``null``; cualquier otro tipo lanza ``ValueError`` en lugar de serializarse de
    forma ambigua.
    """
    _validar_json_canonico(registro, "raíz")
    return json.dumps(
        registro,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def huella_registro(registro: Mapping[str, Any]) -> str:
    """SHA-256 del JSON canónico del registro (independiente del orden de las llaves)."""
    return sha256_texto(json_canonico(registro))
