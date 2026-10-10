"""Vigencia de la versión indexada de cada ley, según el reporte de ``scripts/vigencia_corpus.py``.

El 🟢 de una cita normativa acredita la existencia y la ubicación del precepto en la versión
indexada (``ALCANCE_NORMATIVA``), no su vigencia. Cuando el último reporte de vigencia, hecho
sobre ESTE índice, dice que la fuente oficial ya publicó una versión posterior a la indexada
(``DESACTUALIZADA``) o que el ordenamiento está abrogado (``ABROGADA``):

- la cita localizada no puede salir 🟢 (tope 84, traza ``partial``): el texto cotejado puede no
  ser el que rige;
- la prueba positiva de inexistencia (D10) deja de ser 🔴: acredita que el artículo no está en
  ESA versión, no que no exista en la vigente (una reforma posterior pudo adicionarlo, como el
  873-K de la LFT frente a un texto de 2015).

Nunca 🔴 por este motivo: un índice desactualizado no prueba que la cita sea falsa (criterio C
del responsable, Regla 7). Sin un reporte aplicable el semáforo no cambia, como la vigencia de
las tesis sin dato, y el resumen dice por qué no se aplicó.

Un reporte se aplica a una fuente solo si se hizo sobre el mismo índice (ruta de ChromaDB) y la
fuente conserva el número de fragmentos que el reporte registró: si se re-ingestó después, el
reporte ya no la describe.

Funciones puras: leer el archivo, resolver rutas y contar fragmentos lo hace quien llama.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

DESACTUALIZADA = "DESACTUALIZADA"
ABROGADA = "ABROGADA"
VIGENTE = "VIGENTE"
ESTADOS_NO_VIGENTES = frozenset({DESACTUALIZADA, ABROGADA})

# Estado del reporte en la auditoría (``vvca_summary["vigencia_corpus"]["estado"]``).
REPORTE_APLICADO = "aplicado"
REPORTE_AUSENTE = "sin_reporte"
REPORTE_OTRO_INDICE = "otro_indice"
REPORTE_ILEGIBLE = "ilegible"

# Estado de una fuente frente al reporte (``entry["vigencia_fuente"]["estado"]``).
FUENTE_NO_VIGENTE = "no_vigente"
FUENTE_VIGENTE = "vigente"
FUENTE_SIN_DATO = "sin_dato"
FUENTE_INDICE_CAMBIADO = "indice_cambiado"


def _nfc(texto: str) -> str:
    # macOS guarda nombres de archivo en NFD; el reporte y el índice pueden diferir.
    return unicodedata.normalize("NFC", texto)


@dataclass(frozen=True)
class ReporteVigencia:
    """Lo que la auditoría usa de un reporte: su fecha, el índice auditado y una fila por fuente."""

    ruta: str
    fecha: str
    chroma: str
    filas: dict = field(default_factory=dict)


def cargar_reporte(datos: Any, ruta: str) -> ReporteVigencia:
    """``ReporteVigencia`` de un reporte JSON ya leído; ``ValueError`` si no tiene su forma."""
    if not isinstance(datos, dict) or not isinstance(datos.get("filas"), list):
        raise ValueError("no es un reporte de vigencia: falta la lista 'filas'")
    if not datos.get("chroma") or not datos.get("fecha"):
        raise ValueError("reporte de vigencia sin 'chroma' o sin 'fecha'")
    filas = {
        _nfc(fila["fuente"]): fila
        for fila in datos["filas"]
        if isinstance(fila, dict) and isinstance(fila.get("fuente"), str)
    }
    return ReporteVigencia(ruta=ruta, fecha=str(datos["fecha"]), chroma=str(datos["chroma"]),
                           filas=filas)


def fila_de(reporte: Optional[ReporteVigencia], fuente: str) -> Optional[dict]:
    """La fila de ``fuente`` en el reporte (None si no la registra o no hay reporte)."""
    if reporte is None:
        return None
    return reporte.filas.get(_nfc(fuente))


def motivo_no_vigente(datos: dict) -> str:
    """Por qué el texto indexado de la fuente puede no ser el que rige."""
    if datos.get("estado_reporte") == ABROGADA:
        return (f"{datos['etiqueta']} está abrogada según la fuente oficial "
                f"({datos.get('version_oficial') or 'sin fecha'}; reporte de vigencia del "
                f"{datos['reporte']})")
    return (f"la versión indexada de {datos['etiqueta']} ({datos.get('version_indexada') or 'sin sello'}) "
            f"no es la vigente: la fuente oficial publicó {datos.get('version_oficial') or 'una posterior'} "
            f"(reporte de vigencia del {datos['reporte']})")


def vigencia_de_fuente(reporte: Optional[ReporteVigencia], fuente: str,
                       fragmentos: Optional[int]) -> dict:
    """Estado de ``fuente`` según el reporte; ``fragmentos`` son los que tiene hoy en el índice.

    ``estado`` es ``no_vigente`` solo si el reporte la da por DESACTUALIZADA o ABROGADA y la
    fuente conserva el número de fragmentos del reporte; entonces ``motivo`` dice por qué el
    texto cotejado puede no ser el vigente. ``indice_cambiado``: la fuente se re-ingestó (o no
    se pudo contar) después del reporte, que ya no la describe. Cualquier otro estado del
    reporte (manual, tratado, no verificable…) es ``sin_dato``: no cambia el semáforo."""
    if reporte is None:
        return {"estado": FUENTE_SIN_DATO}
    fila = fila_de(reporte, fuente)
    if not fila:
        return {"estado": FUENTE_SIN_DATO, "reporte": reporte.fecha}
    datos = {
        "estado_reporte": fila.get("estado", ""),
        "etiqueta": fila.get("etiqueta") or fuente,
        "version_indexada": fila.get("version_indexada") or "",
        "version_oficial": fila.get("version_oficial") or "",
        "url_pdf": fila.get("url_pdf") or "",
        "reporte": reporte.fecha,
    }
    if fragmentos is None or fila.get("chunks") != fragmentos:
        return {"estado": FUENTE_INDICE_CAMBIADO, **datos,
                "fragmentos_reporte": fila.get("chunks"), "fragmentos_indice": fragmentos}
    if datos["estado_reporte"] in ESTADOS_NO_VIGENTES:
        return {"estado": FUENTE_NO_VIGENTE, **datos, "motivo": motivo_no_vigente(datos)}
    if datos["estado_reporte"] == VIGENTE:
        return {"estado": FUENTE_VIGENTE, **datos}
    return {"estado": FUENTE_SIN_DATO, **datos}


def instruccion_cotejo(vigencia: dict, articulo: str) -> str:
    """Cómo cotejar el artículo contra el texto oficial (Regla 8 de CLAUDE.md)."""
    ley = vigencia.get("etiqueta") or "<ley>"
    if " " in ley:
        ley = f'"{ley}"'
    return (f"cotéjalo en el PDF oficial antes de citarlo: python scripts/cotejo_manual.py "
            f"articulo {ley} {articulo}")
