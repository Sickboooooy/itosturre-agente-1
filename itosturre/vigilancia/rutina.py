"""Contrato de CORRIDA de las rutinas de vigilancia (DOF/SAT, SJF y contenido).

`contrato.py` describe el estado de cada FUENTE; este módulo, el de cada
corrida: dónde se escriben las salidas, qué fecha es "hoy", qué código de
salida devuelve el script y qué queda escrito para quien orquesta (cron,
rutina programada, CI). Tres reglas que los tres agentes respetan por igual:

1. "No pude consultar la fuente" NO es "no hubo novedades". Si la fuente
   primaria no respondió, no se escribe brief: queda `<clave>.estado.json` con
   la causa y el script sale con EXIT_FUENTE_INACCESIBLE. Escribir el brief
   dejaría un "sin novedades" falso y, además, bloquearía el reintento (un
   brief existente hace que la siguiente corrida termine sin consultar).
2. La fecha operativa es la de la Ciudad de México, no la del servidor (los
   contenedores de las rutinas corren en UTC).
3. Las salidas nunca caen dentro del paquete `itosturre/`: en macOS y Windows
   (sistemas de archivos sin distinción de mayúsculas) `Itosturre/` ES
   `itosturre/`, y la regla de .gitignore que ocultaba esas salidas ocultaba
   también cualquier módulo nuevo del paquete.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_PAQUETE = REPO_ROOT / "itosturre"

# ── Salidas ───────────────────────────────────────────────────────────────────


def salida_dir() -> Path:
    """Raíz de salidas: $ITOSTURRE_SALIDA o, por omisión, `<repo>/salidas`.

    Una ruta relativa se resuelve desde la raíz del repo, no desde el
    directorio actual: un cron que arranca en otra carpeta escribe en el mismo
    lugar que una corrida manual.
    """
    valor = os.environ.get("ITOSTURRE_SALIDA", "").strip()
    if not valor:
        return REPO_ROOT / "salidas"
    ruta = Path(valor).expanduser()
    return ruta if ruta.is_absolute() else REPO_ROOT / ruta


SALIDA_DIR = salida_dir()


def validar_salida(ruta: Path) -> Path:
    """Devuelve la ruta resuelta; ValueError si cae dentro del paquete itosturre/.

    La comparación ignora mayúsculas a propósito: en macOS y Windows
    `<repo>/Itosturre/Vigilancia` es `<repo>/itosturre/Vigilancia`.
    """
    destino = Path(ruta).expanduser().resolve()
    paquete = [p.casefold() for p in _PAQUETE.resolve().parts]
    if [p.casefold() for p in destino.parts][: len(paquete)] == paquete:
        raise ValueError(
            f"La salida {destino} cae dentro del paquete de código {_PAQUETE} "
            "(sin distinguir mayúsculas son la misma carpeta). Usa $ITOSTURRE_SALIDA "
            "o la carpeta por omisión salidas/."
        )
    return destino


# ── Fecha operativa ───────────────────────────────────────────────────────────


def _zona_mx() -> tzinfo:
    """Zona de la Ciudad de México. Sin base IANA (Windows sin el paquete
    tzdata) se usa UTC-6 fijo: la Ciudad de México no tiene horario de verano
    desde octubre de 2022, así que la fecha resultante es la misma."""
    try:
        return ZoneInfo("America/Mexico_City")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=-6), "CST")


ZONA_MX = _zona_mx()


def hoy_mx(ahora: Optional[datetime] = None) -> date:
    """Fecha calendario en la Ciudad de México (de `ahora`, o del instante actual)."""
    return (ahora or datetime.now(timezone.utc)).astimezone(ZONA_MX).date()


# ── Insumos vigentes ──────────────────────────────────────────────────────────


def fecha_de_nombre(nombre: str) -> Optional[date]:
    """Fecha de un brief por su nombre: `YYYY-MM-DD.md` (vigilancia DOF/SAT) o
    `semana-YYYY-Www.md` (jurisprudencia: el domingo de esa semana ISO, último
    día que cubre el informe). None si el nombre no es de un brief."""
    base = nombre.rsplit(".", 1)[0]
    try:
        return date.fromisoformat(base)
    except ValueError:
        pass
    if base.startswith("semana-"):
        try:
            anio, semana = base[len("semana-"):].split("-W")
            return date.fromisocalendar(int(anio), int(semana), 7)
        except ValueError:
            return None
    return None


def briefs_vigentes(directorio: Path, hoy: date, dias: int = 7) -> list[Path]:
    """Briefs `.md` fechados en los últimos `dias`, el más reciente primero.

    Un brief viejo no es "lo de esta semana": el generador de contenido lo
    ignora en vez de reciclarlo. Se admite hasta el domingo de la semana en
    curso porque el informe semanal se fecha con ese domingo.
    """
    if not directorio.is_dir():
        return []
    desde, hasta = hoy - timedelta(days=dias), hoy + timedelta(days=6)
    vigentes = []
    for archivo in directorio.glob("*.md"):
        fecha = fecha_de_nombre(archivo.name)
        if fecha is not None and desde <= fecha <= hasta:
            vigentes.append((fecha, archivo))
    return [archivo for _, archivo in sorted(vigentes, reverse=True)]


# ── Estado de la corrida y códigos de salida ──────────────────────────────────

EXIT_OK = 0                  # brief/informe/borrador escrito (OK o PARCIAL)
EXIT_FUENTE_INACCESIBLE = 2  # la fuente primaria no respondió: NO hay brief
EXIT_SIN_INSUMOS = 3         # (contenido) ningún hallazgo verificado y vigente: NO hay borrador

OK = "OK"
PARCIAL = "PARCIAL"
FUENTE_INACCESIBLE = "FUENTE_INACCESIBLE"
SIN_INSUMOS = "SIN_INSUMOS"

_CODIGOS = {
    OK: EXIT_OK,
    PARCIAL: EXIT_OK,
    FUENTE_INACCESIBLE: EXIT_FUENTE_INACCESIBLE,
    SIN_INSUMOS: EXIT_SIN_INSUMOS,
}


def codigo_salida(estado: str) -> int:
    """Código de salida del script para un estado de corrida."""
    return _CODIGOS[estado]


def registrar_estado(directorio: Path, clave: str, estado: str, **detalle: Any) -> Path:
    """Escribe `<clave>.estado.json` con el resultado de la corrida.

    Solo lo escribe una corrida que consultó: la que termina porque el
    brief ya existía no lo toca, para no borrar lo que pasó en la corrida real.
    """
    if estado not in _CODIGOS:
        raise ValueError(f"estado de corrida inválido: {estado!r} (usar uno de {sorted(_CODIGOS)})")
    destino = validar_salida(directorio)
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / f"{clave}.estado.json"
    payload = {
        "clave": clave,
        "estado": estado,
        "codigo_salida": codigo_salida(estado),
        "registrado": datetime.now(ZONA_MX).isoformat(timespec="seconds"),
        **detalle,
    }
    ruta.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return ruta


# ── Redacción opcional con LLM ────────────────────────────────────────────────

# Una sola definición para los tres agentes. La rutina programada no necesita
# la API: sin ANTHROPIC_API_KEY los scripts entregan datos deterministas.
MODELO_POR_OMISION = "claude-opus-5-5"


def modelo() -> str:
    """Modelo para la redacción vía API: $ITOSTURRE_MODELO o el de por omisión."""
    return os.environ.get("ITOSTURRE_MODELO", "").strip() or MODELO_POR_OMISION
