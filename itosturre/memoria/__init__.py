"""Memoria contextual de Itosturre: eventos persistentes, buscables y acotados.

Resuelve las fugas F1-F5 y F7 del informe
``docs/auditoria-memoria-contextual-10sep2026.md``: el conocimiento del proyecto
—decisiones, correcciones de criterio, alertas, huecos de corpus— deja de vivir
solo en prosa manual y pasa a un índice consultable, sin que por ello crezca el
contexto que se entrega al modelo.

Tres invariantes que no deben romperse al extender este paquete:

1. **La memoria nunca es fuente de una cita legal.** Recuerda decisiones, no
   derecho. Los artículos salen del corpus (regla 2 VVCA) y las tesis del SJF.
   Un evento que diga "el artículo 19 dice X" es un recuerdo de conversación, no
   una verificación.
2. **Todo lo recuperado son datos, no instrucciones.** El bloque que se inyecta
   lo declara explícitamente.
3. **Un fallo de memoria nunca tumba el trabajo en curso.** Los pipelines de
   producción entran por :func:`registrar_seguro`, que no propaga excepciones.

Uso mínimo::

    from itosturre.memoria import MemoriaStore

    with MemoriaStore(raiz=".") as m:
        m.record("architecture_decision", "SQLite+FTS5 en vez de base vectorial")
        print(m.recall("por qué no vectorial")["eventos"])

Implementación propia en Python sobre la biblioteca estándar. El estudio de
``context-mode`` (Elastic License 2.0) aportó ideas de arquitectura —snapshot por
referencia, bandera de consumo, pesos de columna en BM25—; no se portó código.
"""
from __future__ import annotations

from .esquema import (
    ESQUEMA_VERSION,
    MemoriaNoDisponible,
    fts5_disponible,
    project_id,
    ruta_base,
)
from .ranking import (
    PRESUPUESTO_BYTES,
    TIPOS,
    canonizar,
    decaimiento_recencia,
    formato_evento,
    importancia_por_defecto,
    normalizar_bm25,
    puntuar,
    recortar_por_presupuesto,
    tipo_valido,
)
from .redaccion import consulta_fts, redactar, ruta_relativa
from .snapshot import PRESUPUESTO_SNAPSHOT, construir_snapshot
from .store import MemoriaStore, registrar_seguro

__all__ = [
    "ESQUEMA_VERSION",
    "MemoriaNoDisponible",
    "MemoriaStore",
    "PRESUPUESTO_BYTES",
    "PRESUPUESTO_SNAPSHOT",
    "TIPOS",
    "canonizar",
    "construir_snapshot",
    "consulta_fts",
    "decaimiento_recencia",
    "formato_evento",
    "fts5_disponible",
    "importancia_por_defecto",
    "normalizar_bm25",
    "project_id",
    "puntuar",
    "recortar_por_presupuesto",
    "redactar",
    "registrar_seguro",
    "ruta_base",
    "ruta_relativa",
    "tipo_valido",
]
