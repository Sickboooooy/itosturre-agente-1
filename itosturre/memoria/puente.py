"""Puente entre la auditoría VVCA y la memoria contextual.

Cierra la fuga F3 del informe: ``itosturre/audit/traceability.py`` ya construía
registros con identificador estable, hash de evidencia y estado de verificación,
y ``vvca_full.py`` los escribía a ``auditorias/<caso>/vvca_traceability.json``
donde nadie volvía a leerlos. Doce expedientes auditados en disco, cero
consultables.

Este módulo traduce el resultado de una auditoría a eventos de memoria. No
inventa nada: toma lo que el auditor ya decidió. En particular **no vuelve a
juzgar** una cita — si el veredicto dijo 🔴 por rubro discrepante, aquí se
registra como bloqueada; si dijo 🟡 por corpus incompleto, se registra como hueco
de corpus, que es cosa distinta (regla 7 VVCA).

Funciones puras salvo :func:`registrar_auditoria`, que escribe y nunca falla
hacia fuera.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from .store import MemoriaStore


def eventos_desde_auditoria(
    audit: Mapping[str, Any],
    *,
    caso: str | None = None,
    borrador: str | None = None,
    faltantes: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Convierte el resultado de ``OpenNotebook.audit`` en eventos de memoria.

    Devuelve una lista lista para :meth:`MemoriaStore.record_lote`. Nunca lanza:
    ante una estructura inesperada devuelve menos eventos, no una excepción — un
    cambio de forma en el auditor no debe romper una auditoría en curso.
    """
    eventos: list[dict[str, Any]] = []
    resumen = dict(audit.get("vvca_summary") or {})
    veredicto = dict(resumen.get("veredicto") or {})
    etiqueta = caso or "(sin caso)"

    # ── 1. El veredicto de la auditoría ──────────────────────────────────
    if veredicto:
        semaforo = veredicto.get("semaforo", "?")
        eventos.append({
            "event_type": "vvca_veredicto",
            "summary": f"VVCA {semaforo} · {etiqueta}: {veredicto.get('razon', 'sin razón')}",
            "details": {
                "apto": veredicto.get("apto"),
                "accion": veredicto.get("accion"),
                "score_rag": resumen.get("score_rag"),
                "score_sjf": resumen.get("score_sjf"),
                "articulos_ok": resumen.get("articulos_ok"),
                "tesis_total": resumen.get("tesis_total"),
                "tesis_mismatch": resumen.get("tesis_mismatch"),
                "tesis_no_encontradas": resumen.get("tesis_no_encontradas"),
                "tesis_superadas": resumen.get("tesis_superadas"),
            },
            "file_path": borrador,
            # Un documento no apto pesa más al recuperar que uno limpio: es el que
            # todavía exige trabajo.
            "importance": 1 if veredicto.get("apto") is False else 3,
            "metadata": {"caso": caso},
        })

        # Un 🔴 es bloqueante por regla absoluta #2; merece además alerta procesal.
        if veredicto.get("semaforo") == "🔴":
            eventos.append({
                "event_type": "alerta_procesal",
                "summary": f"Documento BLOQUEADO por VVCA en {etiqueta}: "
                           f"{veredicto.get('razon', '')}",
                "details": {"accion": veredicto.get("accion")},
                "file_path": borrador,
                "importance": 1,
                "metadata": {"caso": caso},
            })

    # ── 2. Citas bloqueadas, una por tesis ───────────────────────────────
    for fuente in audit.get("retrieved_sources") or []:
        if not isinstance(fuente, Mapping):
            continue
        if fuente.get("ref_type") != "jurisprudencia":
            continue
        vvca = dict(fuente.get("vvca") or {})
        mismatch = bool(vvca.get("rubro_mismatch"))
        superada = str(vvca.get("estado_vigencia", "vigente")).lower() != "vigente"
        if not (mismatch or superada):
            continue
        explicabilidad = dict(vvca.get("explicabilidad") or {})
        registro = explicabilidad.get("registro") or fuente.get("reference") or "?"
        motivo = "rubro discrepante" if mismatch else f"criterio {vvca.get('estado_vigencia')}"
        eventos.append({
            "event_type": "cita_bloqueada",
            "summary": f"Tesis Reg. {registro} bloqueada por {motivo} en {etiqueta}",
            "details": {
                "referencia": fuente.get("reference"),
                "rubro_real": explicabilidad.get("rubro_real"),
                "rubro_invocado": explicabilidad.get("rubro_invocado"),
                "overlap_rubro": explicabilidad.get("overlap_rubro"),
                "estado_vigencia": vvca.get("estado_vigencia"),
                "fuerza_vinculante": vvca.get("fuerza_vinculante"),
            },
            "file_path": borrador,
            "importance": 1,
            "metadata": {"caso": caso, "registro": registro},
        })

    # ── 3. Huecos de corpus (regla 7: no es defecto del criterio) ────────
    for ley in faltantes or []:
        eventos.append({
            "event_type": "corpus_gap",
            "summary": f"Ordenamiento citado y ausente del índice: {ley}",
            "details": {
                "remedio": "Re-indexar la ley (OpenNotebook.py ingest) — "
                           "un hueco de corpus NO baja el score del argumento (regla 7 VVCA)",
                "caso": caso,
            },
            "importance": 3,
            "metadata": {"caso": caso, "ley": ley},
        })

    return eventos


def registrar_auditoria(
    audit: Mapping[str, Any],
    *,
    raiz: str | None = None,
    caso: str | None = None,
    borrador: str | None = None,
    faltantes: Sequence[str] | None = None,
) -> int:
    """Persiste los eventos de una auditoría. Devuelve cuántos se registraron.

    Tolerante a fallos por diseño: devuelve 0 ante cualquier problema en lugar de
    propagar. La memoria es accesoria; la auditoría del abogado no lo es y no
    puede caerse porque el disco esté lleno o SQLite venga sin FTS5.
    """
    try:
        eventos = eventos_desde_auditoria(
            audit, caso=caso, borrador=borrador, faltantes=faltantes
        )
        if not eventos:
            return 0
        with MemoriaStore(raiz=raiz) as store:
            store.record_lote(eventos)
        return len(eventos)
    except Exception:  # noqa: BLE001 — frontera deliberada, ver docstring
        return 0
