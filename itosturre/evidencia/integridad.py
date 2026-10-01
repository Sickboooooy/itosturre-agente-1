"""Comprobación de integridad de un registro ``evidencia/1.0`` contra sus artefactos.

``validar_registro`` (``esquema.py``) es **estructural**: confirma la forma del
registro, no que sus huellas y metadatos digan la verdad. Un registro con
``"0" * 64`` como huella, o con la época alterada, puede ser estructuralmente válido.
Por eso un registro **no habilita VERIFICADO** hasta pasar también
``comprobar_integridad``, que recalcula desde los artefactos:

  - la huella y el tamaño del original (los bytes capturados o descargados);
  - la huella del derivado (el texto que consumen las capas superiores);
  - para ``tesis_sjf``: vuelve a leer el original con el parser y exige que el
    derivado, los metadatos de identificación y las advertencias sean exactamente los
    de esa lectura (alterar o borrar una advertencia también se detecta);
  - para ``ley_leyesbiblio``: con el texto extraído (opcional, el PDF no se lee aquí),
    su huella, y que la limpieza repetida produzca el mismo derivado y los mismos
    metadatos;
  - que el extracto aparezca literal en la fuente.

Funciones puras: sin red, sin E/S y sin reloj.
"""
from __future__ import annotations

from typing import Any, Mapping

from .esquema import TIPO_LEY_LEYESBIBLIO, TIPO_TESIS_SJF, validar_registro
from .huellas import sha256_bytes, sha256_texto
from .leyesbiblio import SEPARADOR_PAGINAS, advertencias_registro, limpiar_documento
from .sjf import ErrorSJF, derivado_canonico, parsear_tesis


def _comparar(problemas: list[str], ruta: str, registrado: Any, recalculado: Any) -> None:
    if registrado != recalculado:
        problemas.append(
            f"{ruta}: el registro dice {registrado!r} y el artefacto da {recalculado!r}"
        )


def _tesis_sjf(registro: Mapping[str, Any], original: bytes, derivado: str, problemas: list[str]) -> None:
    try:
        texto = bytes(original).decode("utf-8")
    except UnicodeDecodeError:
        problemas.append("original: no es UTF-8; no se puede volver a leer la tesis")
        return
    metadatos = registro.get("metadatos") or {}
    try:
        tesis = parsear_tesis(texto, registro_esperado=metadatos.get("registro"))
    except ErrorSJF as error:
        problemas.append(f"original: la relectura falla ({error})")
        return
    if derivado != derivado_canonico(tesis):
        problemas.append("derivado: no es la lectura que el parser obtiene del original")
    for campo, valor in tesis.metadatos().items():
        _comparar(problemas, f"metadatos.{campo}", metadatos.get(campo), valor)
    _comparar(problemas, "advertencias", registro.get("advertencias"), [dict(a) for a in tesis.advertencias])
    extracto = registro.get("extracto")
    if isinstance(extracto, Mapping) and extracto.get("texto") not in texto:
        problemas.append("extracto.texto: no aparece literal en el original")


def _ley_leyesbiblio(
    registro: Mapping[str, Any], derivado: str, texto_extraido: str | None, problemas: list[str]
) -> None:
    metadatos = registro.get("metadatos") or {}
    extracto = registro.get("extracto")
    if isinstance(extracto, Mapping) and extracto.get("texto") not in derivado:
        problemas.append("extracto.texto: no aparece literal en el derivado")
    if texto_extraido is None:
        return
    _comparar(
        problemas,
        "metadatos.sha256_texto_extraido",
        metadatos.get("sha256_texto_extraido"),
        sha256_texto(texto_extraido),
    )
    paginas = texto_extraido.split(SEPARADOR_PAGINAS)
    numeros = metadatos.get("paginas")
    if not isinstance(numeros, list) or len(numeros) != len(paginas):
        problemas.append("metadatos.paginas: no corresponde al número de páginas del texto extraído")
        return
    total = metadatos.get("total_paginas")
    documento = limpiar_documento(
        paginas, numeros=numeros, total_paginas=total if isinstance(total, int) else None
    )
    if documento.texto != derivado:
        problemas.append("derivado: no es lo que produce la limpieza del texto extraído")
    _comparar(problemas, "advertencias", registro.get("advertencias"), advertencias_registro(documento))
    _comparar(problemas, "metadatos.titulo", metadatos.get("titulo"), documento.titulo)
    _comparar(
        problemas,
        "metadatos.ultima_reforma_dof",
        metadatos.get("ultima_reforma_dof"),
        documento.ultima_reforma_dof,
    )
    _comparar(problemas, "metadatos.total_paginas", total, documento.total_paginas)


def comprobar_integridad(
    registro: Any,
    *,
    original: bytes,
    derivado: str,
    texto_extraido: str | None = None,
) -> list[str]:
    """Problemas de integridad (``[]`` si las huellas y metadatos cuadran con los artefactos).

    Incluye primero los problemas estructurales de ``validar_registro``: la integridad
    presupone la forma. ``derivado`` es el texto del derivado (``sjf.derivado_canonico``
    para tesis; ``DocumentoLeyesBiblio.texto`` para leyes). ``texto_extraido`` solo
    aplica a ``ley_leyesbiblio`` y permite rehacer la limpieza.
    """
    problemas = [f"estructura: {p}" for p in validar_registro(registro)]
    if not isinstance(registro, Mapping):
        return problemas
    if not isinstance(original, (bytes, bytearray, memoryview)):
        raise TypeError("original debe ser bytes (lo capturado o descargado, sin convertir)")
    if not isinstance(derivado, str):
        raise TypeError("derivado debe ser texto")
    datos_original = registro.get("original") or {}
    _comparar(problemas, "original.sha256", datos_original.get("sha256"), sha256_bytes(original))
    _comparar(problemas, "original.bytes", datos_original.get("bytes"), len(original))
    datos_derivado = registro.get("derivado") or {}
    _comparar(problemas, "derivado.sha256", datos_derivado.get("sha256"), sha256_texto(derivado))
    tipo = registro.get("tipo")
    if tipo == TIPO_TESIS_SJF:
        _tesis_sjf(registro, original, derivado, problemas)
    elif tipo == TIPO_LEY_LEYESBIBLIO:
        _ley_leyesbiblio(registro, derivado, texto_extraido, problemas)
    else:
        problemas.append(f"tipo: {tipo!r} sin comprobación de integridad definida")
    return problemas
