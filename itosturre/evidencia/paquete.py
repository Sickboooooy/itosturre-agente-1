"""Paquete de evidencia: almacén direccionado por contenido de registros ``evidencia/1.0``.

Es el **único** módulo de ``itosturre/evidencia`` con E/S de archivos (lectura y
escritura). Sigue sin red y sin reloj: la fecha de consulta la aporta quien llama.

Estructura en disco::

    <paquete>/
      registros/<huella_registro>.json   JSON canónico del registro (json_canonico)
      objetos/<sha256>                   bytes exactos: original, derivado (UTF-8) y,
                                         para leyes, texto extraído (UTF-8)

Todo se nombra por su SHA-256, de modo que el nombre ES la huella del contenido:

  - ``registros/<h>.json`` contiene exactamente ``json_canonico(registro)``, cuya huella
    (``huella_registro``) es ``h``; al cargar se recalcula y un archivo editado a mano
    queda marcado como alterado (no se descarta: el cotejo lo reporta).
  - ``objetos/<h>`` contiene los bytes cuya huella es ``h``; ``Paquete.objeto`` la
    recalcula en cada lectura y lanza ``ObjetoCorrupto`` si no coincide.

Publicación: se escribe un temporal en la misma carpeta y se **enlaza** (enlace duro)
con el nombre definitivo, que falla si el destino ya existe; donde no hay enlaces
duros, se crea con ``O_CREAT | O_EXCL``. Nunca hay "comprobar y luego reemplazar": un
archivo existente nunca se sobrescribe; si su contenido no es el de su nombre, se lanza
``ObjetoCorrupto``.

Enlaces: la raíz, ``registros/``, ``objetos/`` y cada archivo que se lee o se publica
no pueden ser enlaces simbólicos ni puntos de reanálisis de Windows (junctions); y la
ruta real de cada uno debe quedar dentro de la ruta real de la raíz. Se comprueba en
cada operación, no solo al cargar.

``guardar_evidencia`` solo acepta un registro que pasa ``comprobar_integridad`` con los
artefactos que se guardan junto a él, y rechaza un segundo registro distinto para el
mismo documento (misma huella del original y misma URL): el cotejo de identidad no elige
entre registros, así que ese paquete quedaría ambiguo.

Los paquetes de un asunto viven fuera de git (D7): ``auditorias/<asunto>/plan/…`` o
fuera del repositorio.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .esquema import TIPO_LEY_LEYESBIBLIO, validar_registro
from .huellas import es_sha256, huella_registro, json_canonico, sha256_bytes
from .integridad import comprobar_integridad

DIR_REGISTROS = "registros"
DIR_OBJETOS = "objetos"
_NOMBRE_REGISTRO = re.compile(r"^([0-9a-f]{64})\.json$")
_PREFIJO_TEMPORAL = ".tmp-"


class ErrorPaquete(ValueError):
    """El paquete no existe, no tiene la estructura esperada o una operación no procede."""


class ObjetoCorrupto(ErrorPaquete):
    """Un archivo del paquete no tiene la huella que declara su nombre (o es un enlace)."""


class RegistroRechazado(ErrorPaquete):
    """El registro no se guarda: forma inválida, sin integridad o ambiguo en el paquete."""

    def __init__(self, mensaje: str, problemas: list[str] | None = None) -> None:
        self.problemas = list(problemas or [])
        detalle = "; ".join(self.problemas[:5])
        super().__init__(f"{mensaje}: {detalle}" if detalle else mensaje)


@dataclass(frozen=True)
class RegistroEnPaquete:
    """Un archivo de ``registros/`` tal como está en disco.

    ``huella`` es la del nombre del archivo; ``registro`` el JSON leído (``None`` si es
    ilegible); ``problema`` explica por qué no es íntegro (``None`` si lo es).
    """

    huella: str
    registro: Any
    problema: str | None = None

    @property
    def integro(self) -> bool:
        return self.problema is None


# ── Enlaces y contención ─────────────────────────────────────────────────────


def es_enlace(ruta: str | Path) -> bool:
    """``True`` si ``ruta`` es un enlace simbólico o un punto de reanálisis (junction).

    En Python 3.11 no existe ``os.path.isjunction``: en Windows se mira el atributo
    ``FILE_ATTRIBUTE_REPARSE_POINT`` de ``os.lstat``. Una ruta inexistente no es enlace.
    """
    try:
        info = os.lstat(ruta)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    atributos = getattr(info, "st_file_attributes", 0)
    return bool(atributos & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _real(ruta: str | Path) -> str:
    return os.path.normcase(os.path.realpath(ruta))


def _dentro(ruta: str | Path, raiz_real: str) -> bool:
    real = _real(ruta)
    return real == raiz_real or real.startswith(raiz_real.rstrip(os.sep) + os.sep)


def _comprobar_ruta(ruta: Path, raiz_real: str, error: type[ErrorPaquete] = ErrorPaquete) -> None:
    """Rechaza enlaces y rutas cuya ruta real sale de la raíz del paquete."""
    if es_enlace(ruta):
        raise error(f"{ruta}: es un enlace simbólico o punto de reanálisis; no se sigue")
    if not _dentro(ruta, raiz_real):
        raise error(f"{ruta}: su ruta real queda fuera del paquete")


def _raiz_segura(raiz: str | Path) -> tuple[Path, str]:
    raiz = Path(raiz)
    if es_enlace(raiz):
        raise ErrorPaquete(f"{raiz}: la raíz del paquete es un enlace o punto de reanálisis")
    return raiz, _real(raiz)


def _carpeta_segura(raiz: Path, raiz_real: str, nombre: str) -> Path:
    carpeta = raiz / nombre
    _comprobar_ruta(carpeta, raiz_real)
    return carpeta


# ── Escritura ────────────────────────────────────────────────────────────────


def _verificar_existente(destino: Path, esperado: str) -> None:
    if es_enlace(destino):
        raise ObjetoCorrupto(f"{destino} ya existe y es un enlace; no se sigue ni se sobrescribe")
    actual = sha256_bytes(destino.read_bytes())
    if actual != esperado:
        raise ObjetoCorrupto(f"{destino} ya existe con otro contenido (huella {actual}); no se sobrescribe")


def _crear_exclusivo(destino: Path, datos: bytes) -> bool:
    """Crea ``destino`` con ``O_CREAT | O_EXCL``; ``False`` si ya existía."""
    banderas = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(destino, banderas, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "wb") as archivo:
        archivo.write(datos)
        archivo.flush()
        os.fsync(archivo.fileno())
    return True


def _publicar(destino: Path, datos: bytes, raiz_real: str) -> None:
    """Publica ``datos`` en ``destino`` sin sobrescribir nunca (ver el docstring del módulo).

    El nombre de ``destino`` es la huella SHA-256 de ``datos`` (más ``.json`` para los
    registros). Si ya existe con esa huella no se toca; si existe con otra, o es un
    enlace, se lanza ``ObjetoCorrupto``.
    """
    esperado = sha256_bytes(datos)
    _comprobar_ruta(destino.parent, raiz_real)
    if os.path.lexists(destino):
        _comprobar_ruta(destino, raiz_real, ObjetoCorrupto)
    descriptor, temporal = tempfile.mkstemp(prefix=_PREFIJO_TEMPORAL, dir=str(destino.parent))
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(datos)
            archivo.flush()
            os.fsync(archivo.fileno())
        try:
            os.link(temporal, destino)  # atómico y falla si el destino existe
            creado = True
        except FileExistsError:
            creado = False
        except OSError:
            # Sistema de archivos sin enlaces duros: creación exclusiva directa.
            creado = _crear_exclusivo(destino, datos)
        if not creado:
            _verificar_existente(destino, esperado)
    finally:
        if os.path.lexists(temporal):
            os.unlink(temporal)


def crear_paquete(raiz: str | Path) -> Path:
    """Crea (si faltan) ``raiz``, ``registros/`` y ``objetos/``; devuelve la ruta.

    Rechaza que cualquiera de ellos sea un enlace o un punto de reanálisis.
    """
    raiz, _ = _raiz_segura(raiz)
    if raiz.exists() and not raiz.is_dir():
        raise ErrorPaquete(f"{raiz} existe y no es un directorio")
    raiz.mkdir(parents=True, exist_ok=True)
    raiz, raiz_real = _raiz_segura(raiz)
    for nombre in (DIR_REGISTROS, DIR_OBJETOS):
        carpeta = raiz / nombre
        if os.path.lexists(carpeta):
            _comprobar_ruta(carpeta, raiz_real)
        carpeta.mkdir(exist_ok=True)
        _comprobar_ruta(carpeta, raiz_real)
    return raiz


def guardar_objeto(raiz: str | Path, datos: bytes) -> str:
    """Guarda bytes en ``objetos/<sha256>`` y devuelve la huella."""
    if not isinstance(datos, (bytes, bytearray, memoryview)):
        raise TypeError(f"se esperaban bytes, se recibió {type(datos).__name__}")
    datos = bytes(datos)
    huella = sha256_bytes(datos)
    raiz = crear_paquete(raiz)
    raiz_real = _real(raiz)
    _publicar(_carpeta_segura(raiz, raiz_real, DIR_OBJETOS) / huella, datos, raiz_real)
    return huella


def guardar_texto(raiz: str | Path, texto: str) -> str:
    """Guarda un texto como objeto UTF-8 (su huella es ``sha256_texto(texto)``)."""
    if not isinstance(texto, str):
        raise TypeError(f"se esperaba texto, se recibió {type(texto).__name__}")
    return guardar_objeto(raiz, texto.encode("utf-8"))


def guardar_registro(raiz: str | Path, registro: Mapping[str, Any]) -> str:
    """Guarda el registro como ``registros/<huella_registro>.json`` (JSON canónico).

    Solo comprueba la forma (``validar_registro``); para exigir integridad con los
    artefactos usar ``guardar_evidencia``.
    """
    problemas = validar_registro(registro)
    if problemas:
        raise RegistroRechazado("el registro no tiene forma válida", problemas)
    huella = huella_registro(registro)
    datos = json_canonico(registro).encode("utf-8")
    raiz = crear_paquete(raiz)
    raiz_real = _real(raiz)
    _publicar(_carpeta_segura(raiz, raiz_real, DIR_REGISTROS) / f"{huella}.json", datos, raiz_real)
    return huella


def guardar_evidencia(
    raiz: str | Path,
    registro: Mapping[str, Any],
    *,
    original: bytes,
    derivado: str,
    texto_extraido: str | None = None,
) -> str:
    """Guarda los artefactos y el registro, solo si el registro es íntegro con ellos.

    Exige ``comprobar_integridad == []`` (para ``ley_leyesbiblio`` también el texto
    extraído, que el cotejo necesita para ubicar artículos). Rechaza un registro distinto
    para el mismo documento y URL que ya esté en el paquete (sería ambiguo). Volver a
    guardar el mismo registro es inofensivo. Devuelve la huella del registro.
    """
    if registro.get("tipo") == TIPO_LEY_LEYESBIBLIO and texto_extraido is None:
        raise RegistroRechazado("una ley necesita el texto extraído para cotejarse")
    problemas = comprobar_integridad(
        registro, original=original, derivado=derivado, texto_extraido=texto_extraido
    )
    if problemas:
        raise RegistroRechazado("el registro no es íntegro con los artefactos", problemas)
    huella = huella_registro(registro)
    raiz = crear_paquete(raiz)
    for existente in cargar_paquete(raiz).buscar(_sha_del_original(registro), _url_de_fuente(registro)):
        if existente.huella != huella:
            raise RegistroRechazado(
                "ya hay otro registro para el mismo documento y la misma URL "
                f"(registros/{existente.huella}.json); el cotejo lo trataría como ambiguo. "
                "Usar otro paquete o retirar el registro anterior"
            )
    guardar_objeto(raiz, original)
    guardar_texto(raiz, derivado)
    if texto_extraido is not None:
        guardar_texto(raiz, texto_extraido)
    return guardar_registro(raiz, registro)


# ── Lectura ──────────────────────────────────────────────────────────────────


def _sha_del_original(registro: Any) -> str | None:
    if not isinstance(registro, Mapping) or not isinstance(registro.get("original"), Mapping):
        return None
    return registro["original"].get("sha256")


def _url_de_fuente(registro: Any) -> str | None:
    if not isinstance(registro, Mapping) or not isinstance(registro.get("fuente"), Mapping):
        return None
    return registro["fuente"].get("url")


class Paquete:
    """Paquete cargado: registros leídos de disco y acceso verificado a los objetos."""

    def __init__(
        self, raiz: Path, registros: tuple[RegistroEnPaquete, ...], problemas: tuple[str, ...]
    ) -> None:
        self.raiz = raiz
        self.raiz_real = _real(raiz)
        self.registros = registros
        self.problemas = problemas

    def buscar(self, sha256_documento: Any, url: Any) -> list[RegistroEnPaquete]:
        """Registros cuyo ``original.sha256`` y ``fuente.url`` son exactamente esos."""
        if not isinstance(sha256_documento, str) or not isinstance(url, str):
            return []
        return [
            item
            for item in self.registros
            if _sha_del_original(item.registro) == sha256_documento
            and _url_de_fuente(item.registro) == url
        ]

    def objeto(self, huella: str) -> bytes | None:
        """Bytes de ``objetos/<huella>``; ``None`` si no existe.

        Recalcula la huella al leer y rechaza enlaces o rutas fuera del paquete: en esos
        casos lanza ``ObjetoCorrupto``.
        """
        if not es_sha256(huella):
            raise ValueError(f"huella inválida: {huella!r}")
        if es_enlace(self.raiz) or _real(self.raiz) != self.raiz_real:
            raise ObjetoCorrupto(f"{self.raiz}: la raíz del paquete cambió o es un enlace desde que se cargó")
        carpeta = self.raiz / DIR_OBJETOS
        _comprobar_ruta(carpeta, self.raiz_real, ObjetoCorrupto)
        ruta = carpeta / huella
        if not os.path.lexists(ruta):
            return None
        _comprobar_ruta(ruta, self.raiz_real, ObjetoCorrupto)
        if not ruta.is_file():
            return None
        datos = ruta.read_bytes()
        if sha256_bytes(datos) != huella:
            raise ObjetoCorrupto(f"objetos/{huella}: el contenido no tiene la huella de su nombre")
        return datos

    def huella(self) -> str:
        """Huella del estado del paquete: nombres de registros y de objetos presentes.

        Como todo se nombra por su contenido, dos paquetes con los mismos nombres tienen
        el mismo contenido (salvo archivos alterados, que el cotejo detecta al leer).
        """
        partes = []
        for nombre in (DIR_REGISTROS, DIR_OBJETOS):
            carpeta = self.raiz / nombre
            nombres = sorted(os.listdir(carpeta)) if carpeta.is_dir() and not es_enlace(carpeta) else []
            partes.append(nombre + ":" + ",".join(n for n in nombres if not n.startswith(_PREFIJO_TEMPORAL)))
        return hashlib.sha256("\n".join(partes).encode("utf-8")).hexdigest()


def _leer_registro(ruta: Path, huella: str) -> RegistroEnPaquete:
    datos = ruta.read_bytes()
    problema = None
    if sha256_bytes(datos) != huella:
        problema = "la huella del archivo no coincide con su nombre (registro alterado)"
    try:
        registro = json.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return RegistroEnPaquete(huella, None, f"JSON ilegible: {error}")
    if problema is None:
        try:
            if huella_registro(registro) != huella:
                problema = "la huella del registro no coincide con su nombre"
        except ValueError as error:
            problema = f"el registro no tiene forma canónica: {error}"
    return RegistroEnPaquete(huella, registro, problema)


def cargar_paquete(raiz: str | Path) -> Paquete:
    """Lee ``registros/``. Lanza ``ErrorPaquete`` si ``raiz`` no es un paquete o si la
    raíz, ``registros/`` u ``objetos/`` son enlaces o puntos de reanálisis.

    Los archivos ajenos, los temporales huérfanos, los enlaces dentro de ``registros/``
    y los registros ilegibles o alterados no detienen la carga: se informan en
    ``Paquete.problemas`` o en el ``problema`` de cada registro (los enlaces no se leen).
    """
    raiz, raiz_real = _raiz_segura(raiz)
    if not raiz.is_dir():
        raise ErrorPaquete(f"{raiz} no existe o no es un directorio")
    carpeta = raiz / DIR_REGISTROS
    if not os.path.lexists(carpeta):
        raise ErrorPaquete(f"{raiz} no es un paquete de evidencia: falta {DIR_REGISTROS}/")
    _comprobar_ruta(carpeta, raiz_real)
    if not carpeta.is_dir():
        raise ErrorPaquete(f"{raiz} no es un paquete de evidencia: {DIR_REGISTROS} no es un directorio")
    objetos = raiz / DIR_OBJETOS
    if os.path.lexists(objetos):
        _comprobar_ruta(objetos, raiz_real)
    registros: list[RegistroEnPaquete] = []
    problemas: list[str] = []
    for ruta in sorted(carpeta.iterdir(), key=lambda r: r.name):
        nombre = f"{DIR_REGISTROS}/{ruta.name}"
        if es_enlace(ruta) or not _dentro(ruta, raiz_real):
            problemas.append(f"{nombre}: enlace o ruta fuera del paquete; no se lee")
            continue
        coincidencia = _NOMBRE_REGISTRO.match(ruta.name)
        if ruta.name.startswith(_PREFIJO_TEMPORAL):
            problemas.append(f"{nombre}: temporal huérfano de una escritura interrumpida")
            continue
        if not coincidencia or not ruta.is_file():
            problemas.append(f"{nombre}: archivo ajeno al paquete")
            continue
        registro = _leer_registro(ruta, coincidencia.group(1))
        if registro.problema:
            problemas.append(f"{nombre}: {registro.problema}")
        registros.append(registro)
    if not objetos.is_dir():
        problemas.append(f"falta {DIR_OBJETOS}/: ningún artefacto se puede comprobar")
    return Paquete(raiz, tuple(registros), tuple(problemas))
