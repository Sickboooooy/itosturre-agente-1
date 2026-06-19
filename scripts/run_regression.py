#!/usr/bin/env python3
"""
run_regression.py — Suite de regresión VVCA (gate pre-merge).

Reemplaza al inexistente `OpenNotebook.py --test-suite`. Corre el auditor sobre
casos_de_prueba/ y verifica los invariantes anti-alucinación que el P0 debía garantizar.
Sale != 0 si alguno falla — úsalo como gate antes de `git_strategy.sh 3` (merge).

Invariantes:
  1. Cobertura del corpus completa (0 fuentes mapeadas ausentes).
  2. caso_001_prision_preventiva: status ok, veredicto apto, sin alertas 🔴.
  3. Ningún caso lanza excepción al auditar.
  4. Sin alertas "LEY NO IDENTIFICADA" residuales (sticky-law resuelve
     constitucionales/tratados agrupados bajo encabezado de ley).

Uso: python scripts/run_regression.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import OpenNotebook as ON  # noqa: E402

fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    mark = "✅" if cond else "❌"
    suffix = f" — {detail}" if detail else ""
    print(f"  {mark} {name}{suffix}")
    if not cond:
        fails.append(name)


def corpus_sources() -> set[str]:
    db = Path(ON.CHROMA_PATH) / "chroma.sqlite3"
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT DISTINCT string_value FROM embedding_metadata WHERE key='source'"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows if r[0]}


def main() -> int:
    print("── Regresión VVCA ──")

    # 1. Cobertura del corpus
    present = corpus_sources()
    missing = sorted({s for s in ON.LAW_SOURCE_MAP.values() if s not in present})
    check("Cobertura del corpus (0 ausentes)", not missing,
          f"faltan: {missing}" if missing else "")

    # 2-4. Auditar cada caso de prueba
    casos = sorted((REPO / "casos_de_prueba").glob("*.md"))
    if not casos:
        check("Hay casos de prueba", False, "casos_de_prueba/*.md vacío")
        return _final()

    for caso in casos:
        try:
            res = ON.audit(caso.read_text(encoding="utf-8"), allow_incomplete_corpus=True)
        except Exception as e:  # invariante 3
            check(f"{caso.name}: audita sin excepción", False, repr(e))
            continue
        check(f"{caso.name}: status ok", res.get("status") == "ok")

        alerts = res.get("alerts", [])
        leyni = [a for a in alerts if "LEY NO IDENTIFICADA" in a]
        rojas = [a for a in alerts if a.strip().startswith("🔴")]
        # invariante 4 — informativo por caso
        check(f"{caso.name}: sin 'LEY NO IDENTIFICADA' residual", not leyni,
              f"{len(leyni)} sin resolver")

        # invariante 2 — específico del caso oficial de prisión preventiva
        if "prision_preventiva" in caso.name:
            vered = res.get("vvca_summary", {}).get("veredicto", {})
            check("caso_001: veredicto apto", vered.get("apto") is True,
                  vered.get("razon", ""))
            check("caso_001: sin alertas 🔴", not rojas, f"{len(rojas)} rojas")

    return _final()


def _final() -> int:
    print()
    if fails:
        print(f"❌ REGRESIÓN FALLÓ — {len(fails)} invariante(s): {', '.join(fails)}")
        print("   NO mergear hasta resolver.")
        return 1
    print("🟢 REGRESIÓN OK — todos los invariantes pasan. Apto para merge (sujeto a Drive OK).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
