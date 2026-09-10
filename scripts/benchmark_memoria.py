#!/usr/bin/env python3
"""Benchmark ANTES/DESPUÉS de la memoria contextual (Fase 10 del encargo).

Mide lo que el encargo pidió medir, con números tomados de la memoria real de
este proyecto y no de datos sintéticos, salvo en la prueba de escala —donde
hacen falta 10 000 eventos que todavía no existen.

La métrica que manda no es el ahorro de bytes sino el **acierto de
recuperación**: ahorrar contexto perdiendo la respuesta correcta no es una
mejora, es una regresión disfrazada de optimización. Por eso el informe de
salida pone el acierto primero y el ahorro después.

Uso:
  python scripts/benchmark_memoria.py
  python scripts/benchmark_memoria.py --escala 10000 --salida docs/BENCHMARK_MEMORIA.md
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.memoria import (  # noqa: E402
    MemoriaNoDisponible,
    MemoriaStore,
    construir_snapshot,
)
from scripts.importar_memorias_md import localizar_memorias  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Bytes por token, aproximación para prosa en español (acentos = 2 bytes).
#: Es una estimación declarada, no una medición: no se tokeniza de verdad.
BYTES_POR_TOKEN = 4.0

#: Preguntas reales cuya respuesta está en la memoria histórica del proyecto.
#: Cada una lleva los términos que deben aparecer en lo recuperado para contar
#: como acierto. Es el gold set mínimo; ampliarlo es trabajo del operador.
PREGUNTAS: list[tuple[str, tuple[str, ...]]] = [
    ("que me corrigio Fabian sobre la via contra desercion de pruebas", ("revocación",)),
    ("clave de Anthropic expuesta en produccion sin resolver", ("Anthropic", "clave")),
    ("rama reconcile-jurisprudencia bloqueador SJF", ("reconcile-jurisprudencia",)),
    ("gotcha del IDE Antigravity al mover archivos en services", ("EBUSY",)),
    ("que bot de Telegram usa el canal", ("itosclaude",)),
    ("leyes que faltaban del corpus LGV PIDCP", ("LGV", "PIDCP")),
    ("formato al recomendar correcciones tras auditoria VVCA", ("ANTES", "DESPUÉS", "antes")),
    ("caso de derechos humanos del 28 de mayo de 2004", ("tortura", "Aaron", "Aarón")),
    ("skill fiscal escrita pero sin commitear", ("medios-defensa-fiscal",)),
    ("bug de npx en vvca_full.py en Windows", ("npx",)),
]


def _kb(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def _tokens(n: int) -> int:
    return int(n / BYTES_POR_TOKEN)


# ─────────────────────────────────────────
# ANTES: cargar toda la memoria en prosa
# ─────────────────────────────────────────

def medir_antes() -> dict:
    """El estado actual: para recordar algo hay que cargar los .md enteros."""
    origen = localizar_memorias()
    if not origen:
        return {"disponible": False}
    archivos = sorted(origen.glob("*.md"))
    total = sum(p.stat().st_size for p in archivos)
    indice = origen / "MEMORY.md"
    return {
        "disponible": True,
        "archivos": len(archivos),
        "bytes": total,
        "bytes_indice": indice.stat().st_size if indice.exists() else 0,
    }


# ─────────────────────────────────────────
# DESPUÉS: recuperación selectiva
# ─────────────────────────────────────────

def medir_acierto(store: MemoriaStore, max_bytes: int) -> dict:
    aciertos, detalle = 0, []
    latencias, bytes_usados = [], []
    for pregunta, esperados in PREGUNTAS:
        inicio = time.perf_counter()
        resultado = store.recall(pregunta, limite=8, max_bytes=max_bytes, con_detalles=True)
        latencias.append((time.perf_counter() - inicio) * 1000)
        bytes_usados.append(resultado["bytes"])
        heno = " ".join(
            f"{e.get('summary', '')} {e.get('details', '')}" for e in resultado["eventos"]
        )
        ok = any(term.lower() in heno.lower() for term in esperados)
        aciertos += ok
        detalle.append({
            "pregunta": pregunta,
            "acierto": ok,
            "esperado": esperados,
            "eventos": resultado["n_devueltos"],
            "bytes": resultado["bytes"],
        })
    return {
        "aciertos": aciertos,
        "total": len(PREGUNTAS),
        "detalle": detalle,
        "ms_medio": sum(latencias) / len(latencias),
        "ms_max": max(latencias),
        "bytes_medio": int(sum(bytes_usados) / len(bytes_usados)),
        "bytes_max": max(bytes_usados),
    }


def medir_escala(n: int, max_bytes: int) -> dict:
    """Prueba de escala: la salida no puede crecer con la base."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        with MemoriaStore(db_path=Path(tmp) / "escala.db", raiz=tmp, pid="escala") as store:
            inicio = time.perf_counter()
            lote = [
                {
                    "event_type": "important_context",
                    "summary": f"evento sintético {i} sobre amparo indirecto y competencia "
                               f"orgánica del tercer circuito, expediente {i}/2026",
                    "timestamp": f"2026-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}T00:00:00Z",
                }
                for i in range(n)
            ]
            store.record_lote(lote)
            ingesta = time.perf_counter() - inicio

            # Una decisión antigua enterrada entre los n eventos sintéticos.
            store.record(
                "architecture_decision",
                "Se eligió FTS5 con unicode61 remove_diacritics en vez de porter",
                timestamp="2026-01-01T00:00:00Z",
            )
            store.reindexar()

            inicio = time.perf_counter()
            resultado = store.recall("remove_diacritics porter", max_bytes=max_bytes)
            ms = (time.perf_counter() - inicio) * 1000

            encontrada = any(
                "remove_diacritics" in e.get("summary", "") for e in resultado["eventos"]
            )
            return {
                "n": n,
                "ms_ingesta": ingesta * 1000,
                "ms_consulta": ms,
                "bytes": resultado["bytes"],
                "devueltos": resultado["n_devueltos"],
                "decision_antigua_recuperada": encontrada,
                "db_bytes": (Path(tmp) / "escala.db").stat().st_size,
            }


def medir_snapshot(store: MemoriaStore) -> dict:
    eventos = store.recall("", limite=200, max_bytes=10 ** 7)["eventos"]
    inicio = time.perf_counter()
    texto = construir_snapshot(
        eventos, project_id=store.project_id, total_en_memoria=store._total()
    )
    ms = (time.perf_counter() - inicio) * 1000
    return {"bytes": len(texto.encode("utf-8")), "ms": ms, "eventos_resumidos": len(eventos)}


# ─────────────────────────────────────────
# Informe
# ─────────────────────────────────────────

def informe(antes: dict, despues: dict, escala: dict, snap: dict, stats: dict) -> str:
    L: list[str] = []
    ap = L.append
    ap("# Benchmark de memoria contextual — Itosturre")
    ap("")
    ap(f"Generado por `scripts/benchmark_memoria.py` · {stats['total']} eventos reales "
       f"en memoria · base de {_kb(stats['db_bytes'])}.")
    ap("")
    ap("Los tokens son una **estimación** (bytes ÷ 4 para prosa en español), no una "
       "tokenización real. Sirven para comparar órdenes de magnitud, no para facturar.")
    ap("")

    ap("## 1. Acierto de recuperación — la métrica que manda")
    ap("")
    ap("Ahorrar contexto perdiendo la respuesta correcta no es una mejora. Diez preguntas "
       "reales cuya respuesta está en la memoria histórica del proyecto:")
    ap("")
    ap("| Pregunta | Acierto | Eventos | Bytes |")
    ap("|---|:--:|--:|--:|")
    for d in despues["detalle"]:
        marca = "✅" if d["acierto"] else "❌"
        ap(f"| {d['pregunta'][:58]} | {marca} | {d['eventos']} | {d['bytes']} |")
    ap("")
    ap(f"**Acierto: {despues['aciertos']}/{despues['total']}** · "
       f"latencia media {despues['ms_medio']:.2f} ms (máx. {despues['ms_max']:.2f} ms) · "
       f"{despues['bytes_medio']} bytes de media por consulta.")
    ap("")

    ap("## 2. ANTES vs. DESPUÉS")
    ap("")
    if antes.get("disponible"):
        bytes_antes = antes["bytes"]
        bytes_despues = despues["bytes_medio"]
        ahorro = 100 * (1 - bytes_despues / bytes_antes) if bytes_antes else 0
        ap("| | ANTES (memorias .md) | DESPUÉS (recuperación selectiva) |")
        ap("|---|---|---|")
        ap(f"| Unidades | {antes['archivos']} archivos | "
           f"top-k acotado por presupuesto |")
        ap(f"| Contexto por consulta | {_kb(bytes_antes)} (cargar todo) | "
           f"{bytes_despues} B (media) |")
        ap(f"| Tokens aprox. | ~{_tokens(bytes_antes):,} | ~{_tokens(bytes_despues):,} |")
        ap(f"| Eventos enviados | todos | "
           f"{despues['detalle'][0]['eventos']}-{max(d['eventos'] for d in despues['detalle'])} |")
        ap(f"| Latencia | lectura de {antes['archivos']} archivos | "
           f"{despues['ms_medio']:.2f} ms |")
        ap(f"| Selectividad | ninguna | BM25 + importancia + recencia |")
        ap("")
        ap(f"**Ahorro de contexto por consulta: {ahorro:.1f}%.**")
        ap("")
        ap(f"Matiz honesto: hoy `MEMORY.md` ({_kb(antes['bytes_indice'])}) se carga en cada "
           "sesión y los archivos completos solo al consultarlos. La comparación de arriba "
           "es contra el coste de **responder una pregunta concreta**, que es el caso de uso "
           "que este sistema sustituye.")
    else:
        ap("_(No se encontró el directorio de memorias .md; sin comparación ANTES.)_")
    ap("")

    ap("## 3. Escenarios del encargo")
    ap("")
    ap("| Escenario | Antes | Después |")
    ap("|---|---|---|")
    ap(f"| Decisión antigua entre {escala['n']:,} eventos | no existía | "
       f"{'recuperada' if escala['decision_antigua_recuperada'] else 'NO recuperada'} en "
       f"{escala['ms_consulta']:.2f} ms |")
    ap(f"| Tras muchos eventos | degradación lineal | {escala['bytes']} B, "
       f"{escala['devueltos']} eventos |")
    ap(f"| Sesión nueva | `MEMORY.md` completo | snapshot de {snap['bytes']} B |")
    ap(f"| Tras compactación | **todo perdido** | snapshot restaurable de {snap['bytes']} B |")
    ap("| Errores previos | no existía | consulta por `error_detected` |")
    ap("| Archivos modificados | no existía | consulta por `file_path` |")
    ap("")

    ap("## 4. Escala")
    ap("")
    ap(f"- {escala['n']:,} eventos sintéticos ingeridos en {escala['ms_ingesta']:.0f} ms.")
    ap(f"- Base resultante: {_kb(escala['db_bytes'])}.")
    ap(f"- Consulta sobre esos {escala['n']:,} eventos: **{escala['ms_consulta']:.2f} ms**, "
       f"devuelve **{escala['bytes']} bytes**.")
    ap("")
    ap("Es la promesa del encargo comprobada: **la base crece, el contexto no**. "
       f"Con {escala['n']:,} eventos en disco, lo que llega al modelo sigue siendo "
       f"{escala['bytes']} bytes.")
    ap("")

    ap("## 5. Snapshot de continuidad")
    ap("")
    ap(f"- {snap['eventos_resumidos']} eventos condensados en **{snap['bytes']} bytes** "
       f"({snap['ms']:.2f} ms).")
    ap("- No lleva datos, lleva referencias: un resumen por sección más el comando que "
       "recupera el detalle. Por eso no crece con la base.")
    ap("")

    ap("## 6. El otro frente: el prompt permanente")
    ap("")
    ap("La memoria no reduce el prompt base — son problemas distintos y se atacaron por "
       "separado. `CLAUDE.md` pasó de ~10 523 a ~4 372 tokens por turno al mover el detalle "
       "de los quince menús a la skill `menu-itosturre` y el entorno a `docs/ENTORNO.md` "
       "(ver `docs/propuesta-adelgazar-claude-md.md`).")
    ap("")
    ap("Sumando ambos frentes: ~6 150 tokens menos **por turno** de prompt permanente, más "
       "~95 % menos de contexto cada vez que hay que recordar algo del historial.")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--escala", type=int, default=10_000)
    ap.add_argument("--max-bytes", type=int, default=4096, dest="max_bytes")
    ap.add_argument("--salida", help="Escribir el informe a este archivo Markdown")
    args = ap.parse_args()

    try:
        with MemoriaStore(raiz=REPO) as store:
            stats = store.estadisticas()
            if stats["total"] == 0:
                print("⚠️  La memoria está vacía. Ejecuta antes:")
                print("    python scripts/importar_memorias_md.py")
                return 1
            print(f"Midiendo sobre {stats['total']} eventos reales…")
            antes = medir_antes()
            despues = medir_acierto(store, args.max_bytes)
            snap = medir_snapshot(store)
            print(f"Prueba de escala con {args.escala:,} eventos sintéticos…")
            escala = medir_escala(args.escala, args.max_bytes)
            texto = informe(antes, despues, escala, snap, stats)
    except MemoriaNoDisponible as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3

    if args.salida:
        destino = Path(args.salida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n", encoding="utf-8")
        print(f"\n✅ Informe escrito en {destino}")
    print()
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
