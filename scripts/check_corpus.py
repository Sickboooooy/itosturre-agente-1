#!/usr/bin/env python3
"""
check_corpus.py — Verificador de cobertura del corpus RAG Itosturre.

Compara las leyes que el resolutor dice conocer (LAW_SOURCE_MAP en OpenNotebook.py)
contra lo realmente indexado en ChromaDB, leyendo sqlite directo (no carga el modelo
e5). Sale con código != 0 si falta alguna fuente, para usarse como gate antes de
auditar o en CI.

Uso:
    python scripts/check_corpus.py
    python scripts/check_corpus.py --json
    python scripts/check_corpus.py --only "VICTIMAS,PIDCP,Pacto"   # subset por substring
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

# Permite correr desde la raíz del repo o desde scripts/
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from OpenNotebook import LAW_SOURCE_MAP, CHROMA_PATH  # noqa: E402


def sources_in_chroma(chroma_path: str) -> set[str]:
    db = Path(chroma_path) / "chroma.sqlite3"
    if not db.exists():
        return set()
    con = sqlite3.connect(str(db))
    try:
        rows = con.execute(
            "SELECT DISTINCT string_value FROM embedding_metadata WHERE key='source'"
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows if r[0]}


def main() -> int:
    # Consola Windows (cp1252) no codifica emojis — forzar UTF-8 como en OpenNotebook.py
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    as_json = "--json" in sys.argv
    only_terms: list[str] = []
    if "--only" in sys.argv:
        i = sys.argv.index("--only")
        if i + 1 < len(sys.argv):
            only_terms = [t.strip().lower() for t in sys.argv[i + 1].split(",") if t.strip()]

    expected = sorted(set(LAW_SOURCE_MAP.values()))
    if only_terms:
        expected = [s for s in expected if any(t in s.lower() for t in only_terms)]

    present = sources_in_chroma(CHROMA_PATH)
    ok = [s for s in expected if s in present]
    missing = [s for s in expected if s not in present]

    if as_json:
        print(json.dumps({
            "chroma_path": CHROMA_PATH,
            "expected": len(expected),
            "present": len(ok),
            "missing": missing,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"📚 Cobertura del corpus — {CHROMA_PATH}")
        print(f"   Fuentes mapeadas en LAW_SOURCE_MAP{' (subset)' if only_terms else ''}: {len(expected)}")
        print(f"   ✅ Indexadas: {len(ok)}")
        print(f"   ❌ Ausentes:  {len(missing)}")
        for s in missing:
            print(f"      • {s}")
        if missing:
            print("\n⚠️  Hay fuentes mapeadas sin indexar. Re-indexa antes de auditar con --force:")
            print('   python OpenNotebook.py ingest --directory "<carpeta_pdfs>"')
        else:
            print("\n🟢 Cobertura completa: 0 fuentes ausentes.")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
