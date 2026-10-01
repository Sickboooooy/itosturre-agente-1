"""Registro de evidencia ``evidencia/1.0`` y su validación estructural.

Un documento solo es evidencia si trae procedencia verificable (D4): URL oficial,
fecha de consulta aportada por quien llama, huella del original y huella del derivado.
El índice RAG y el VVCA solo *localizan*; este registro es lo que se puede citar.

Forma del registro::

    {
      "esquema": "evidencia/1.0",
      "tipo": "tesis_sjf" | "ley_leyesbiblio",
      "fuente": {"url": <https oficial>, "fecha_consulta": <ISO>, "medio": <MEDIOS>},
      "original": {"sha256": <hex64>, "bytes": <entero > 0>, "media_type": "tipo/subtipo"},
      "derivado": {"sha256": <hex64>, "extractor": <texto>, "version_extractor": <texto>,
                   "transformacion": null | {"nombre": <texto>, "version": <texto>}},
      "metadatos": {...según el tipo...},
      "extracto": null | {"texto": <texto>, "ubicacion": <texto>, "sha256": <hex64>},
      "advertencias": [{"codigo": <texto>, "mensaje": <texto>, ...}]
    }

Decisiones:
  - El original nunca se sustituye por el derivado: se guardan ambas huellas.
  - ``validar_registro`` devuelve una lista de problemas (``[]`` si es válido); no lanza
    excepciones por datos mal formados.
  - ``validar_registro`` es **solo estructural** y **no habilita VERIFICADO**: un
    registro con huellas inventadas o metadatos alterados puede tener forma válida.
    Antes de usarlo como evidencia hace falta ``integridad.comprobar_integridad``, que
    recalcula huellas desde el original y el derivado y vuelve a leer la fuente.
  - Los marcadores de dato faltante (``[ASIGNAR]``, ``[VERIFICAR…]``…) nunca cuentan
    como valor, en ninguna parte del registro.
  - Los tipos son extensibles: ``validar_registro(..., tipos=...)`` acepta un catálogo
    propio sin mutar el global.
  - Las llaves desconocidas se ignoran (compatibilidad hacia adelante, igual que el
    ledger de planes).

Todas las funciones son puras: sin E/S, sin red y sin reloj (la fecha de consulta la
aporta quien llama).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .fuentes import (
    HOST_LEYESBIBLIO,
    HOST_SJF,
    RUTA_LEYESBIBLIO,
    RUTA_TESIS_SJF,
    host_de,
    motivo_url_no_oficial,
)
from .huellas import es_sha256, sha256_texto, sin_acentos

SCHEMA_VERSION = "evidencia/1.0"

TIPO_LEY_LEYESBIBLIO = "ley_leyesbiblio"
TIPO_TESIS_SJF = "tesis_sjf"

# Cómo se obtuvo el original. ``descarga_https``: bytes servidos por el host oficial;
# ``render_navegador``: texto visible de la página renderizada (innerText).
MEDIOS = ("descarga_https", "render_navegador")

# Marcadores que emiten las skills cuando falta un dato: nunca cuentan como valor.
# ``itosturre/plan/estados.py`` los reexporta (fuente única).
MARCADORES_PENDIENTES = ("[ASIGNAR", "[COMPLETAR", "[VERIFICAR", "[NO VERIFICADA")

# Épocas del Semanario Judicial con las que trabaja el parser del SJF.
EPOCAS = (
    "Quinta Época",
    "Sexta Época",
    "Séptima Época",
    "Octava Época",
    "Novena Época",
    "Décima Época",
    "Undécima Época",
    "Duodécima Época",
)

_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_FECHA_HORA_RE = re.compile(
    r"^(?P<fecha>\d{4}-\d{2}-\d{2})T(?P<h>\d{2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?"
    r"(?P<zona>Z|[+-]\d{2}:\d{2})$"
)
_MEDIA_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*(?:\s*;\s*\S+)*$", re.I)
_REGISTRO_RE = re.compile(r"^\d{1,8}$")


def es_marcador_pendiente(valor: Any) -> bool:
    """``True`` si el texto contiene un marcador de dato faltante (``[ASIGNAR]``…)."""
    if not isinstance(valor, str):
        return False
    normalizado = sin_acentos(valor).upper()
    return any(marcador in normalizado for marcador in MARCADORES_PENDIENTES)


def advertencia(codigo: str, mensaje: str, **datos: Any) -> dict:
    """Advertencia serializable ``{codigo, mensaje, ...datos}``.

    Los parsers emiten advertencias en lugar de callar: campo ausente, ambigüedad,
    discrepancia entre dos datos de la fuente… Nunca corrigen ni eligen.
    """
    return {"codigo": codigo, "mensaje": mensaje, **datos}


def fecha_iso(valor: Any) -> date | None:
    """La fecha si ``valor`` es exactamente ``AAAA-MM-DD`` válido; si no, ``None``."""
    if not isinstance(valor, str) or not _FECHA_RE.match(valor):
        return None
    try:
        return date.fromisoformat(valor)
    except ValueError:
        return None


def fecha_consulta_valida(valor: Any) -> bool:
    """``AAAA-MM-DD`` o ``AAAA-MM-DDTHH:MM[:SS]`` con zona explícita (``Z`` o ``±HH:MM``).

    Una hora sin zona se rechaza: no permite reconstruir el instante de la consulta.
    """
    if not isinstance(valor, str):
        return False
    if fecha_iso(valor) is not None:
        return True
    coincidencia = _FECHA_HORA_RE.match(valor)
    if not coincidencia or fecha_iso(coincidencia.group("fecha")) is None:
        return False
    zona = coincidencia.group("zona")
    normalizado = valor[:-1] + "+00:00" if zona == "Z" else valor
    try:
        datetime.fromisoformat(normalizado)
    except ValueError:
        return False
    return True


# ── Reglas por tipo ─────────────────────────────────────────────────────────


def _url_leyesbiblio(url: str, metadatos: Mapping[str, Any]) -> str | None:
    if host_de(url) != HOST_LEYESBIBLIO:
        return f"una ley de LeyesBiblio debe venir de {HOST_LEYESBIBLIO}"
    ruta = urlsplit(url.strip()).path
    if not ruta.startswith(RUTA_LEYESBIBLIO):
        return f"la ruta debe empezar por {RUTA_LEYESBIBLIO}"
    archivo = metadatos.get("archivo")
    if isinstance(archivo, str) and archivo and not ruta.endswith("/" + archivo):
        return f"la URL no corresponde al archivo declarado {archivo!r}"
    return None


def _url_tesis_sjf(url: str, metadatos: Mapping[str, Any]) -> str | None:
    if host_de(url) != HOST_SJF:
        return f"una tesis del SJF debe venir de {HOST_SJF}"
    ruta = urlsplit(url.strip()).path
    registro = metadatos.get("registro")
    if isinstance(registro, str) and ruta != f"{RUTA_TESIS_SJF}{registro}":
        return f"la URL no corresponde al registro digital {registro!r}"
    return None


def _texto_o_nulo(metadatos: Mapping[str, Any], campo: str, ruta: str, problemas: list[str]) -> None:
    if campo not in metadatos:
        problemas.append(f"{ruta}.{campo}: falta la llave (usar null si la fuente no lo dice)")
        return
    valor = metadatos[campo]
    if valor is not None and not (isinstance(valor, str) and valor.strip()):
        problemas.append(f"{ruta}.{campo}: debe ser texto no vacío o null")


def _fecha_o_nula(metadatos: Mapping[str, Any], campo: str, ruta: str, problemas: list[str]) -> None:
    if campo not in metadatos:
        problemas.append(f"{ruta}.{campo}: falta la llave (usar null si la fuente no lo dice)")
        return
    valor = metadatos[campo]
    if valor is not None and fecha_iso(valor) is None:
        problemas.append(f"{ruta}.{campo}: debe ser fecha AAAA-MM-DD o null")


def _metadatos_tesis_sjf(metadatos: Mapping[str, Any], ruta: str, problemas: list[str]) -> None:
    registro = metadatos.get("registro")
    if not (isinstance(registro, str) and _REGISTRO_RE.match(registro)):
        problemas.append(f"{ruta}.registro: debe ser el registro digital (solo dígitos)")
    for campo in ("instancia", "clave", "fuente", "tipo_tesis", "rubro"):
        _texto_o_nulo(metadatos, campo, ruta, problemas)
    for campo in ("epoca", "epoca_segun_clave"):
        _texto_o_nulo(metadatos, campo, ruta, problemas)
        valor = metadatos.get(campo)
        if isinstance(valor, str) and valor not in EPOCAS:
            problemas.append(f"{ruta}.{campo}: {valor!r} no pertenece al vocabulario de épocas")
    if "materias" not in metadatos:
        problemas.append(f"{ruta}.materias: falta la llave (lista, vacía si la fuente no lo dice)")
    else:
        materias = metadatos["materias"]
        if not isinstance(materias, list) or not all(
            isinstance(m, str) and m.strip() for m in materias
        ):
            problemas.append(f"{ruta}.materias: debe ser lista de textos no vacíos")
    for campo in ("fecha_publicacion", "fecha_obligatoriedad"):
        _fecha_o_nula(metadatos, campo, ruta, problemas)


def _metadatos_ley_leyesbiblio(metadatos: Mapping[str, Any], ruta: str, problemas: list[str]) -> None:
    archivo = metadatos.get("archivo")
    if not (isinstance(archivo, str) and archivo.strip() and "/" not in archivo):
        problemas.append(f"{ruta}.archivo: debe ser el nombre del PDF (sin rutas)")
    _texto_o_nulo(metadatos, "titulo", ruta, problemas)
    _fecha_o_nula(metadatos, "ultima_reforma_dof", ruta, problemas)
    if "total_paginas" not in metadatos:
        problemas.append(f"{ruta}.total_paginas: falta la llave (usar null si no es constante)")
    else:
        total = metadatos["total_paginas"]
        if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < 1):
            problemas.append(f"{ruta}.total_paginas: debe ser entero positivo o null")
    paginas = metadatos.get("paginas")
    if (
        not isinstance(paginas, list)
        or not paginas
        or not all(isinstance(p, int) and not isinstance(p, bool) and p >= 1 for p in paginas)
        or any(b <= a for a, b in zip(paginas, paginas[1:]))
    ):
        problemas.append(f"{ruta}.paginas: debe ser lista no vacía de enteros crecientes")
    if not es_sha256(metadatos.get("sha256_texto_extraido")):
        problemas.append(f"{ruta}.sha256_texto_extraido: debe ser SHA-256 hexadecimal en minúsculas")


@dataclass(frozen=True)
class TipoEvidencia:
    """Reglas de un tipo de evidencia: URL admisible y forma de sus metadatos."""

    nombre: str
    validar_url: Callable[[str, Mapping[str, Any]], str | None]
    validar_metadatos: Callable[[Mapping[str, Any], str, list[str]], None]


TIPOS = MappingProxyType(
    {
        TIPO_TESIS_SJF: TipoEvidencia(TIPO_TESIS_SJF, _url_tesis_sjf, _metadatos_tesis_sjf),
        TIPO_LEY_LEYESBIBLIO: TipoEvidencia(
            TIPO_LEY_LEYESBIBLIO, _url_leyesbiblio, _metadatos_ley_leyesbiblio
        ),
    }
)


# ── Validación ──────────────────────────────────────────────────────────────


def _marcadores(valor: Any, ruta: str, problemas: list[str]) -> None:
    """Recorre el registro completo y reporta cada marcador pendiente usado como valor."""
    if isinstance(valor, str):
        if es_marcador_pendiente(valor):
            problemas.append(f"{ruta}: marcador pendiente usado como valor ({valor!r})")
    elif isinstance(valor, Mapping):
        for llave, contenido in valor.items():
            _marcadores(contenido, f"{ruta}.{llave}", problemas)
    elif isinstance(valor, (list, tuple)):
        for indice, contenido in enumerate(valor):
            _marcadores(contenido, f"{ruta}[{indice}]", problemas)


def _objeto(registro: Mapping[str, Any], campo: str, problemas: list[str]) -> Mapping[str, Any]:
    valor = registro.get(campo)
    if not isinstance(valor, Mapping):
        problemas.append(f"{campo}: debe ser un objeto")
        return {}
    return valor


def _texto_requerido(obj: Mapping[str, Any], campo: str, ruta: str, problemas: list[str]) -> None:
    valor = obj.get(campo)
    if not (isinstance(valor, str) and valor.strip()):
        problemas.append(f"{ruta}.{campo}: debe ser texto no vacío")


def _hash_requerido(obj: Mapping[str, Any], campo: str, ruta: str, problemas: list[str]) -> None:
    if not es_sha256(obj.get(campo)):
        problemas.append(f"{ruta}.{campo}: debe ser SHA-256 hexadecimal de 64 caracteres en minúsculas")


def validar_registro(
    registro: Any, *, tipos: Mapping[str, TipoEvidencia] = TIPOS
) -> list[str]:
    """Problemas estructurales del registro ``evidencia/1.0`` (lista vacía si la forma es válida).

    No comprueba que las huellas correspondan a los artefactos: eso es
    ``integridad.comprobar_integridad``. Un ``[]`` aquí no basta para VERIFICADO.
    """
    if not isinstance(registro, Mapping):
        return ["raíz: debe ser un objeto"]
    problemas: list[str] = []
    if registro.get("esquema") != SCHEMA_VERSION:
        problemas.append(
            f"esquema: se esperaba {SCHEMA_VERSION!r}, se recibió {registro.get('esquema')!r}"
        )
    tipo = tipos.get(registro.get("tipo")) if isinstance(registro.get("tipo"), str) else None
    if tipo is None:
        problemas.append(f"tipo: {registro.get('tipo')!r} no es uno de {sorted(tipos)}")
    metadatos = _objeto(registro, "metadatos", problemas)

    fuente = _objeto(registro, "fuente", problemas)
    url = fuente.get("url")
    motivo = motivo_url_no_oficial(url)
    if motivo:
        problemas.append(f"fuente.url: {url!r} no es una URL oficial ({motivo})")
    elif tipo is not None:
        motivo_tipo = tipo.validar_url(url, metadatos)
        if motivo_tipo:
            problemas.append(f"fuente.url: {motivo_tipo}")
    if not fecha_consulta_valida(fuente.get("fecha_consulta")):
        problemas.append(
            f"fuente.fecha_consulta: {fuente.get('fecha_consulta')!r} no es AAAA-MM-DD ni "
            "fecha-hora ISO con zona explícita"
        )
    if fuente.get("medio") not in MEDIOS:
        problemas.append(f"fuente.medio: {fuente.get('medio')!r} no es uno de {list(MEDIOS)}")

    original = _objeto(registro, "original", problemas)
    _hash_requerido(original, "sha256", "original", problemas)
    tamano = original.get("bytes")
    if isinstance(tamano, bool) or not isinstance(tamano, int) or tamano < 1:
        problemas.append("original.bytes: debe ser entero positivo")
    media_type = original.get("media_type")
    if not (isinstance(media_type, str) and _MEDIA_TYPE_RE.match(media_type.strip())):
        problemas.append(f"original.media_type: {media_type!r} no es un tipo MIME válido")

    derivado = _objeto(registro, "derivado", problemas)
    _hash_requerido(derivado, "sha256", "derivado", problemas)
    _texto_requerido(derivado, "extractor", "derivado", problemas)
    _texto_requerido(derivado, "version_extractor", "derivado", problemas)
    transformacion = derivado.get("transformacion")
    if transformacion is not None:
        if not isinstance(transformacion, Mapping):
            problemas.append("derivado.transformacion: debe ser objeto o null")
        else:
            _texto_requerido(transformacion, "nombre", "derivado.transformacion", problemas)
            _texto_requerido(transformacion, "version", "derivado.transformacion", problemas)

    if tipo is not None and isinstance(registro.get("metadatos"), Mapping):
        tipo.validar_metadatos(metadatos, "metadatos", problemas)

    extracto = registro.get("extracto")
    if extracto is not None:
        if not isinstance(extracto, Mapping):
            problemas.append("extracto: debe ser objeto o null")
        else:
            _texto_requerido(extracto, "texto", "extracto", problemas)
            _texto_requerido(extracto, "ubicacion", "extracto", problemas)
            _hash_requerido(extracto, "sha256", "extracto", problemas)
            texto = extracto.get("texto")
            if (
                isinstance(texto, str)
                and es_sha256(extracto.get("sha256"))
                and extracto["sha256"] != sha256_texto(texto)
            ):
                problemas.append("extracto.sha256: no coincide con el texto del extracto")

    advertencias = registro.get("advertencias")
    if not isinstance(advertencias, list):
        problemas.append("advertencias: debe ser lista (vacía si no hay)")
    else:
        for indice, item in enumerate(advertencias):
            if not isinstance(item, Mapping):
                problemas.append(f"advertencias[{indice}]: debe ser objeto")
                continue
            _texto_requerido(item, "codigo", f"advertencias[{indice}]", problemas)
            _texto_requerido(item, "mensaje", f"advertencias[{indice}]", problemas)

    _marcadores(registro, "registro", problemas)
    return problemas


def construir_registro(
    *,
    tipo: str,
    url: str,
    fecha_consulta: str,
    medio: str,
    original_sha256: str,
    original_bytes: int,
    media_type: str,
    derivado_sha256: str,
    extractor: str,
    version_extractor: str,
    metadatos: Mapping[str, Any],
    transformacion: Mapping[str, str] | None = None,
    extracto: Mapping[str, str] | None = None,
    advertencias: list[dict] | None = None,
) -> dict:
    """Arma el registro ``evidencia/1.0`` sin validarlo (usar ``validar_registro``).

    Separar construir de validar permite que una prueba o un llamador inspeccione el
    registro completo junto con la lista de problemas, en lugar de perderlo en una
    excepción.
    """
    return {
        "esquema": SCHEMA_VERSION,
        "tipo": tipo,
        "fuente": {"url": url, "fecha_consulta": fecha_consulta, "medio": medio},
        "original": {
            "sha256": original_sha256,
            "bytes": original_bytes,
            "media_type": media_type,
        },
        "derivado": {
            "sha256": derivado_sha256,
            "extractor": extractor,
            "version_extractor": version_extractor,
            "transformacion": dict(transformacion) if transformacion is not None else None,
        },
        "metadatos": dict(metadatos),
        "extracto": dict(extracto) if extracto is not None else None,
        "advertencias": [dict(item) for item in (advertencias or [])],
    }


def crear_extracto(texto: str, ubicacion: str) -> dict:
    """Extracto literal con su huella (el texto se guarda tal cual, sin normalizar)."""
    return {"texto": texto, "ubicacion": ubicacion, "sha256": sha256_texto(texto)}
