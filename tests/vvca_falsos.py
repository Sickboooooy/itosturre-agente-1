"""Dobles de prueba del núcleo VVCA: colección y codificador falsos, sin dependencias.

``FakeCollection`` emula SOLO el subconjunto de ``chromadb.Collection`` que usan
``OpenNotebook.audit``, ``check_corpus_coverage`` y ``exact_article_chunks``:

- ``count()``;
- ``get(where=, limit=, include=)``: cobertura del corpus y recuperación por metadata
  ``source + article``;
- ``query(query_embeddings=[v], n_results=, where=, include=)``: distancia coseno
  (``hnsw:space = cosine``, es decir 1 − similitud), de menor a mayor.

Filtros ``where``: igualdad implícita ``{"campo": valor}``, ``$eq``, ``$in`` y ``$and``
(con al menos dos expresiones y una sola clave por nivel, como exige ChromaDB). Las
respuestas tienen la forma de ChromaDB: listas planas en ``get`` y listas por consulta en
``query``; lo no incluido vale ``None``.

Todo uso no emulado (otro método, operador, argumento o ``include``) lanza
``UsoNoEmulado``, que deriva de ``BaseException`` a propósito: ``audit()`` atrapa
``Exception`` en la recuperación por metadata y en la cobertura, y un uso no emulado
no debe convertirse en silencio en un camino de respaldo. Las entradas que ChromaDB
también rechaza (``$and`` con una sola expresión, ``n_results`` no positivo) lanzan
``ValueError``, como ChromaDB.

``ColeccionEscribible`` (re-ingesta por fuente, 4-oct-2026) añade ``add``, ``delete`` y ``get``
por ``ids`` con ``embeddings``, más estricta que ChromaDB (un ID existente en ``add`` falla) y
con un fallo de escritura inyectable; ``FakeCollection`` sigue sin emular escrituras.

``CodificadorFalso`` asigna a cada consulta registrada un eje propio; la colección coloca
cada fragmento a la distancia coseno que fija la prueba respecto de ese eje (y a 1.0 de
cualquier otro). Una consulta no registrada también lanza ``UsoNoEmulado``: la prueba
fija así el texto exacto de la consulta que construye ``audit()``.
"""
from __future__ import annotations

import copy
import logging
import math
import os
from typing import Any, Iterable
from unittest import mock

DIMENSION = 32
_EJE_RUIDO = DIMENSION - 1
_INCLUDE_GET = {"documents", "metadatas"}
_INCLUDE_QUERY = {"documents", "metadatas", "distances"}


class UsoNoEmulado(BaseException):
    """Uso de la API de ChromaDB (o consulta) que el doble de prueba no emula."""


def importar_opennotebook():
    """Importa ``OpenNotebook`` sin alterar el entorno ni el logging del proceso de pruebas.

    Al importarse, ``OpenNotebook`` carga ``.env`` (si python-dotenv está instalado) y
    configura el logger raíz. Se restauran ``os.environ`` y los manejadores del logger
    raíz para que ninguna otra prueba dependa del orden de importación.
    """
    raiz = logging.getLogger()
    manejadores, nivel = list(raiz.handlers), raiz.level
    try:
        with mock.patch.dict(os.environ):
            import OpenNotebook
    finally:
        raiz.handlers[:] = manejadores
        raiz.setLevel(nivel)
    return OpenNotebook


def vector_a_distancia(eje: int, distancia: float) -> list[float]:
    """Vector unitario a ``distancia`` coseno del eje ``eje`` y a 1.0 de cualquier otro."""
    if not 0 <= eje < _EJE_RUIDO:
        raise ValueError(f"eje fuera de rango: {eje}")
    if not 0.0 <= distancia <= 1.0:
        raise ValueError(f"distancia fuera de [0, 1]: {distancia}")
    coseno = 1.0 - distancia
    vector = [0.0] * DIMENSION
    vector[eje] = coseno
    vector[_EJE_RUIDO] = math.sqrt(max(0.0, 1.0 - coseno * coseno))
    return vector


def _vector_sin_afinidad() -> list[float]:
    vector = [0.0] * DIMENSION
    vector[_EJE_RUIDO] = 1.0
    return vector


class CodificadorFalso:
    """Codificador de consultas: un eje ortogonal por consulta registrada."""

    def __init__(self) -> None:
        self._ejes: dict[str, int] = {}
        self.llamadas: list[str] = []

    def eje(self, consulta: str) -> int:
        """Registra ``consulta`` (texto exacto) y devuelve su eje."""
        if consulta not in self._ejes:
            if len(self._ejes) >= _EJE_RUIDO:
                raise ValueError("demasiadas consultas para la dimensión del doble")
            self._ejes[consulta] = len(self._ejes)
        return self._ejes[consulta]

    def __call__(self, consulta: str) -> list[float]:
        self.llamadas.append(consulta)
        if consulta not in self._ejes:
            raise UsoNoEmulado(
                f"Consulta no registrada en CodificadorFalso: {consulta!r}. "
                f"Registradas: {sorted(self._ejes)}"
            )
        vector = [0.0] * DIMENSION
        vector[self._ejes[consulta]] = 1.0
        return vector


def _coseno(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        raise UsoNoEmulado(f"dimensiones distintas: {len(a)} y {len(b)}")
    producto = sum(x * y for x, y in zip(a, b))
    norma = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    if norma == 0:
        raise UsoNoEmulado("vector nulo")
    return producto / norma


def _validar_where(where: dict | None) -> None:
    """Valida el filtro completo (sin cortocircuito) aunque la colección esté vacía."""
    if where is None:
        return
    if not isinstance(where, dict) or len(where) != 1:
        # ChromaDB exige exactamente un operador o campo por nivel.
        raise ValueError(f"where debe tener exactamente una clave: {where!r}")
    (clave, valor), = where.items()
    if clave == "$and":
        if not isinstance(valor, list) or len(valor) < 2:
            raise ValueError("$and exige una lista con al menos dos expresiones")
        for expresion in valor:
            _validar_where(expresion)
        return
    if clave.startswith("$"):
        raise UsoNoEmulado(f"operador lógico no emulado en where: {clave}")
    if isinstance(valor, dict):
        if len(valor) != 1:
            raise ValueError(f"condición con más de un operador: {valor!r}")
        (operador, esperado), = valor.items()
        if operador == "$in":
            if not isinstance(esperado, list):
                raise ValueError("$in exige una lista")
        elif operador != "$eq":
            raise UsoNoEmulado(f"operador de metadata no emulado en where: {operador}")
        return
    if not isinstance(valor, (str, int, float, bool)):
        raise UsoNoEmulado(f"valor de where no emulado: {valor!r}")


def _cumple(metadata: dict, where: dict | None) -> bool:
    """Evalúa un filtro ya validado por ``_validar_where``."""
    if where is None:
        return True
    (clave, valor), = where.items()
    if clave == "$and":
        return all(_cumple(metadata, expresion) for expresion in valor)
    if clave not in metadata:
        return False
    actual = metadata[clave]
    if isinstance(valor, dict):
        (operador, esperado), = valor.items()
        return actual in esperado if operador == "$in" else actual == esperado
    return actual == valor


def _validar_include(include: Iterable[str] | None, permitidos: set[str], defecto: set[str]) -> set[str]:
    if include is None:
        return set(defecto)
    pedidos = set(include)
    extra = pedidos - permitidos
    if extra:
        raise UsoNoEmulado(f"include no emulado: {sorted(extra)}")
    return pedidos


class FakeCollection:
    """Colección en memoria con el subconjunto de la API de ChromaDB descrito arriba.

    ``fallar_consultas_filtradas`` hace que ``query`` con ``where`` lance ``ValueError``
    (como ChromaDB ante un filtro que no admite), para ejercer el respaldo sin filtro de
    ``audit()``. ``vaciar_consultas`` hace que ``query`` devuelva listas vacías: simula
    un índice que no devuelve vecinos, el único modo de alcanzar la rama "no encontrado"
    de ``audit()``; un ChromaDB sano siempre devuelve vecinos de una fuente indexada.
    """

    def __init__(
        self,
        *,
        fallar_consultas_filtradas: bool = False,
        vaciar_consultas: bool = False,
    ) -> None:
        self._filas: list[dict[str, Any]] = []
        self.fallar_consultas_filtradas = fallar_consultas_filtradas
        self.vaciar_consultas = vaciar_consultas
        self.llamadas: list[tuple[str, dict[str, Any]]] = []

    # ── Preparación (no forma parte de la API de ChromaDB) ──────────────────────────
    def agregar(
        self,
        documento: str,
        metadata: dict[str, Any],
        *,
        eje: int | None = None,
        distancia: float | None = None,
    ) -> str:
        """Agrega un fragmento; con ``eje`` y ``distancia`` lo ubica respecto de esa consulta."""
        if (eje is None) != (distancia is None):
            raise ValueError("eje y distancia van juntos")
        vector = (
            _vector_sin_afinidad() if eje is None else vector_a_distancia(eje, distancia)
        )
        identificador = f"falso_{len(self._filas)}"
        self._filas.append({
            "id": identificador,
            "document": documento,
            "metadata": dict(metadata),
            "embedding": vector,
        })
        return identificador

    # ── API emulada ──────────────────────────────────────────────────────────────────
    def count(self) -> int:
        self.llamadas.append(("count", {}))
        return len(self._filas)

    def get(
        self,
        *,
        where: dict | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.llamadas.append(("get", {"where": where, "limit": limit, "include": include}))
        incluidos = _validar_include(include, _INCLUDE_GET, _INCLUDE_GET)
        _validar_where(where)
        filas = [fila for fila in self._filas if _cumple(fila["metadata"], where)]
        if limit is not None:
            filas = filas[:limit]
        return {
            "ids": [fila["id"] for fila in filas],
            "embeddings": None,
            "documents": [fila["document"] for fila in filas] if "documents" in incluidos else None,
            "metadatas": (
                [copy.deepcopy(fila["metadata"]) for fila in filas]
                if "metadatas" in incluidos else None
            ),
            "include": sorted(incluidos),
        }

    def query(
        self,
        *,
        query_embeddings: list[list[float]],
        n_results: int = 10,
        where: dict | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.llamadas.append(
            ("query", {"n_results": n_results, "where": where, "include": include})
        )
        if not isinstance(query_embeddings, list) or len(query_embeddings) != 1:
            raise UsoNoEmulado("query con más de un vector de consulta")
        if not isinstance(n_results, int) or n_results < 1:
            raise ValueError(f"n_results debe ser un entero positivo: {n_results!r}")
        incluidos = _validar_include(include, _INCLUDE_QUERY, _INCLUDE_QUERY)
        _validar_where(where)
        if where is not None and self.fallar_consultas_filtradas:
            raise ValueError("filtro where rechazado (simulación de la prueba)")
        filas = [fila for fila in self._filas if _cumple(fila["metadata"], where)]
        consulta = query_embeddings[0]
        # ChromaDB devuelve float32; se redondea a 6 decimales para que la distancia que
        # fija la prueba no arrastre artefactos de punto flotante (0.15 → 0.15000000000000002).
        puntuadas = [
            (round(1.0 - _coseno(consulta, fila["embedding"]), 6), orden, fila)
            for orden, fila in enumerate(filas)
        ]
        puntuadas.sort(key=lambda par: (par[0], par[1]))
        elegidas = [] if self.vaciar_consultas else puntuadas[:n_results]
        return {
            "ids": [[fila["id"] for _, _, fila in elegidas]],
            "embeddings": None,
            "documents": (
                [[fila["document"] for _, _, fila in elegidas]]
                if "documents" in incluidos else None
            ),
            "metadatas": (
                [[copy.deepcopy(fila["metadata"]) for _, _, fila in elegidas]]
                if "metadatas" in incluidos else None
            ),
            "distances": (
                [[distancia for distancia, _, _ in elegidas]]
                if "distances" in incluidos else None
            ),
            "include": sorted(incluidos),
        }

    def __getattr__(self, nombre: str) -> Any:
        if nombre.startswith("__"):
            raise AttributeError(nombre)
        raise UsoNoEmulado(f"FakeCollection no emula '{nombre}'")


class ColeccionEscribible(FakeCollection):
    """``FakeCollection`` con la escritura que usa la re-ingesta por fuente (4-oct-2026):
    ``add(ids=, documents=, metadatas=, embeddings=)``, ``delete(where=)`` / ``delete(ids=)`` y
    ``get`` también por ``ids`` y con ``include=["embeddings"]``.

    Más estricta que ChromaDB a propósito: ``add`` con un ID que ya existe (o repetido en el
    lote) lanza ``ValueError`` —ChromaDB lo omite con un aviso, que es justo como la ingesta de
    antes mezclaba fragmentos viejos y nuevos—, y ``add`` sin ``embeddings`` es un uso no
    emulado (la re-ingesta los calcula antes de tocar el índice). ``fallar_add_en=n`` hace
    fallar la n-ésima llamada a ``add`` (1 = la primera) para ejercer la restauración; las
    filas de ese lote no se agregan.
    """

    def __init__(self, *, fallar_add_en: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.fallar_add_en = fallar_add_en
        self._adds = 0

    def agregar_fila(self, identificador: str, documento: str, metadata: dict[str, Any],
                     embedding: list[float] | None = None) -> None:
        """Preparación: fila con ID propio (la forma que guarda la ingesta)."""
        if any(fila["id"] == identificador for fila in self._filas):
            raise ValueError(f"ID repetido en la preparación: {identificador}")
        self._filas.append({
            "id": identificador, "document": documento, "metadata": dict(metadata),
            "embedding": list(embedding) if embedding is not None else _vector_sin_afinidad(),
        })

    def filas(self) -> list[tuple[str, str, dict[str, Any], list[float]]]:
        """Estado completo (para comparar antes/después en las pruebas)."""
        return [
            (f["id"], f["document"], copy.deepcopy(f["metadata"]), list(f["embedding"]))
            for f in self._filas
        ]

    def get(
        self,
        *,
        ids: list[str] | None = None,
        where: dict | None = None,
        limit: int | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        self.llamadas.append(
            ("get", {"ids": ids, "where": where, "limit": limit, "include": include})
        )
        incluidos = _validar_include(include, _INCLUDE_GET | {"embeddings"}, _INCLUDE_GET)
        _validar_where(where)
        filas = [fila for fila in self._filas if _cumple(fila["metadata"], where)]
        if ids is not None:
            pedidos = set(ids)
            filas = [fila for fila in filas if fila["id"] in pedidos]
        if limit is not None:
            filas = filas[:limit]
        return {
            "ids": [fila["id"] for fila in filas],
            "embeddings": (
                [list(fila["embedding"]) for fila in filas] if "embeddings" in incluidos else None
            ),
            "documents": [fila["document"] for fila in filas] if "documents" in incluidos else None,
            "metadatas": (
                [copy.deepcopy(fila["metadata"]) for fila in filas]
                if "metadatas" in incluidos else None
            ),
            "include": sorted(incluidos),
        }

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, Any]],
        embeddings: list[list[float]] | None = None,
    ) -> None:
        self.llamadas.append(("add", {"ids": list(ids)}))
        self._adds += 1
        if self.fallar_add_en is not None and self._adds == self.fallar_add_en:
            raise RuntimeError("fallo de escritura (simulación de la prueba)")
        if embeddings is None:
            raise UsoNoEmulado("add sin embeddings")
        if not (len(ids) == len(documents) == len(metadatas) == len(embeddings)):
            raise ValueError("add con listas de longitudes distintas")
        existentes = {fila["id"] for fila in self._filas}
        if len(set(ids)) != len(ids) or existentes & set(ids):
            raise ValueError(f"add con IDs existentes o repetidos: {sorted(existentes & set(ids))}")
        for identificador, documento, metadata, vector in zip(ids, documents, metadatas, embeddings):
            self._filas.append({
                "id": identificador, "document": documento, "metadata": dict(metadata),
                "embedding": [float(x) for x in vector],
            })

    def delete(self, *, ids: list[str] | None = None, where: dict | None = None) -> None:
        self.llamadas.append(("delete", {"ids": ids, "where": where}))
        if ids is None and where is None:
            raise ValueError("delete exige ids o where")
        _validar_where(where)
        pedidos = set(ids) if ids is not None else None
        self._filas = [
            fila for fila in self._filas
            if not (_cumple(fila["metadata"], where) and (pedidos is None or fila["id"] in pedidos))
        ]
