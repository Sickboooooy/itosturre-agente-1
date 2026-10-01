"""Hosts oficiales y validación de URL de procedencia.

Fuente única de la lista de hosts oficiales: ``itosturre/plan/lint.py`` la importa de
aquí (D2: ``plan`` puede depender de ``evidencia``, nunca al revés). La validación es
estructural (esquema, host exacto, credenciales, puerto); no hace red.
"""
from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import quote, urlsplit

HOSTS_OFICIALES = frozenset(
    {
        "dof.gob.mx",
        "www.diputados.gob.mx",
        "sjf2.scjn.gob.mx",
        "sjfsemanal.scjn.gob.mx",
        "www.scjn.gob.mx",
        "www.corteidh.or.cr",
    }
)
# Variantes conocidas que NO se aceptan, con el host canónico que debe usarse.
# www.dof.gob.mx: su certificado TLS no cubre el subdominio www (D6).
HOSTS_CANONICOS = {"www.dof.gob.mx": "dof.gob.mx"}

HOST_LEYESBIBLIO = "www.diputados.gob.mx"
RUTA_LEYESBIBLIO = "/LeyesBiblio/pdf/"
HOST_SJF = "sjf2.scjn.gob.mx"
RUTA_TESIS_SJF = "/detalle/tesis/"


def host_de(url: Any) -> str:
    """Host en minúsculas y sin punto final; ``""`` si la URL no se puede analizar."""
    try:
        return (urlsplit(url.strip()).hostname or "").rstrip(".").lower()
    except (AttributeError, ValueError):
        return ""


def url_oficial(url: Any, hosts: Iterable[str] = HOSTS_OFICIALES) -> bool:
    """``True`` si la URL es https, sin credenciales ni puerto raro, y su host es exacto.

    Rechaza hosts parecidos (``dof.gob.mx.example.com``), ``http://`` y trucos de
    *userinfo* (``https://dof.gob.mx@otro.example``).
    """
    if not isinstance(url, str) or not url.strip():
        return False
    try:
        partes = urlsplit(url.strip())
        puerto = partes.port
    except ValueError:
        return False
    if partes.scheme.lower() != "https":
        return False
    if partes.username is not None or partes.password is not None:
        return False
    if puerto not in (None, 443):
        return False
    host = (partes.hostname or "").rstrip(".").lower()
    permitidos = {h.strip().rstrip(".").lower() for h in hosts}
    return bool(host) and host in permitidos


def motivo_url_no_oficial(url: Any, hosts: Iterable[str] = HOSTS_OFICIALES) -> str | None:
    """Motivo legible por el que ``url`` no es oficial (``None`` si lo es).

    Solo explica; la decisión la toma ``url_oficial``, de modo que ambos nunca
    discrepan.
    """
    if url_oficial(url, hosts):
        return None
    if not isinstance(url, str) or not url.strip():
        return "URL vacía o no es texto"
    canonico = HOSTS_CANONICOS.get(host_de(url))
    if canonico:
        return f"host no canónico; usar {canonico}"
    try:
        partes = urlsplit(url.strip())
        puerto = partes.port
    except ValueError:
        return "URL mal formada"
    if partes.scheme.lower() != "https":
        return f"esquema {partes.scheme or '(vacío)'!r}; se exige https"
    if partes.username is not None or partes.password is not None:
        return "la URL lleva credenciales (userinfo)"
    if puerto not in (None, 443):
        return f"puerto {puerto} no permitido"
    return f"host {host_de(url) or '(vacío)'!r} fuera de la lista de hosts oficiales"


def url_leyesbiblio(archivo: str) -> str:
    """URL oficial del PDF de LeyesBiblio (``CNPP.pdf`` → ``https://www.diputados…``)."""
    if not isinstance(archivo, str) or not archivo.strip() or "/" in archivo:
        raise ValueError(f"nombre de archivo de LeyesBiblio inválido: {archivo!r}")
    return f"https://{HOST_LEYESBIBLIO}{RUTA_LEYESBIBLIO}{quote(archivo.strip())}"


def url_tesis_sjf(registro: str) -> str:
    """URL pública del detalle de una tesis en el SJF (``/detalle/tesis/<registro>``)."""
    if not isinstance(registro, str) or not registro.isdigit():
        raise ValueError(f"registro digital inválido: {registro!r}")
    return f"https://{HOST_SJF}{RUTA_TESIS_SJF}{registro}"
