#!/usr/bin/env python3
"""
vvca_full.py — Pipeline VVCA unificado Itosturre.

Reemplaza los generar_word.py per-caso con OUT_DIR/JSON_SJF/DOCX_OUT hardcodeados:
todo se parametriza por --caso. Orquesta, en orden:

  1. check_corpus  — gate: aborta si faltan leyes referenciadas (salvo --force)
  2. RAG audit     — OpenNotebook.py audit sobre el borrador        -> audit_rag.json
  3. SJF tesis     — (opcional) node vvca_audit.ts sobre registros  -> auditoria_vvca.json + capturas
  4. RAG capture   — (opcional) capturar_rag.py                     -> rag_chunks.png
  5. resumen       — vvca_full.json consolidado

NO genera el .docx final (eso sigue siendo per-caso); deja el material listo para
el generador de Word. Honesto sobre su alcance: no inventa el entregable.

Uso:
  python vvca_full.py --caso auditorias/2026-06-18-AARON-GARCIA \
      --borrador casos_de_prueba/estrategia_aaron_garcia_28may2004.md \
      [--contexto caso.json] [--registros 2024783 2003551 ...] [--force] [--no-sjf]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, **kw)


def main() -> int:
    # Consola Windows (cp1252) no codifica emojis — forzar UTF-8 como en OpenNotebook.py
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description="Pipeline VVCA unificado Itosturre")
    ap.add_argument("--caso", required=True, help="Directorio del expediente (se crea si no existe)")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--borrador", help="Borrador .md/.txt a auditar")
    src.add_argument("--texto", help="Texto a auditar directamente (p. ej. respuesta de un LLM pegada)")
    ap.add_argument("--contexto", help="caso.json con el contexto para el scraper SJF")
    ap.add_argument("--registros", nargs="*", default=[], help="Registros SJF a verificar en vivo")
    ap.add_argument("--force", action="store_true", help="Auditar aunque el corpus esté incompleto")
    ap.add_argument("--no-sjf", action="store_true", help="Saltar la verificación SJF (scraper)")
    ap.add_argument("--python", default=sys.executable, help="Intérprete Python a usar")
    args = ap.parse_args()

    caso = Path(args.caso)
    caso.mkdir(parents=True, exist_ok=True)
    if args.texto:
        # Persistir el texto pegado como borrador (auditabilidad del input)
        borrador = caso / "borrador_input.md"
        borrador.write_text(args.texto, encoding="utf-8")
    else:
        borrador = Path(args.borrador)
        if not borrador.exists():
            print(f"❌ Borrador no encontrado: {borrador}", file=sys.stderr)
            return 2

    summary: dict = {"caso": str(caso), "borrador": str(borrador), "pasos": {}}

    # ── 1. Gate de cobertura del corpus ──────────────────────────────────────
    cc = run([args.python, str(REPO / "scripts" / "check_corpus.py"), "--json"],
             capture_output=True, text=True)
    try:
        cobertura = json.loads(cc.stdout or "{}")
    except json.JSONDecodeError:
        cobertura = {"missing": ["(salida no parseable)"]}
    summary["pasos"]["check_corpus"] = cobertura
    if cobertura.get("missing") and not args.force:
        print("⚠️  Corpus incompleto — faltan:", cobertura["missing"])
        print("   Re-indexa las leyes faltantes o usa --force para continuar con advertencia.")
        (caso / "vvca_full.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1

    # ── 2. RAG audit ─────────────────────────────────────────────────────────
    ra = run([args.python, str(REPO / "OpenNotebook.py"), "audit", "--file", str(borrador)]
             + (["--force"] if args.force else []),
             capture_output=True, text=True)
    (caso / "audit_rag.json").write_text(ra.stdout, encoding="utf-8")
    try:
        audit = json.loads(ra.stdout)
    except json.JSONDecodeError:
        audit = {"status": "parse_error", "stderr": ra.stderr[-2000:]}
    summary["pasos"]["rag_audit"] = audit.get("vvca_summary", audit.get("status"))

    # ── 3. SJF tesis (opcional) ──────────────────────────────────────────────
    if args.registros and not args.no_sjf:
        scraper = REPO / "services" / "itosturre-scraper" / "vvca_audit.ts"
        cmd = ["npx", "ts-node", "--esm", str(scraper), "--out", str(caso.resolve())]
        if args.contexto:
            cmd += ["--contexto", str(Path(args.contexto).resolve())]
        cmd += args.registros
        run(cmd, cwd=str(scraper.parent))
        sjf = caso / "auditoria_vvca.json"
        summary["pasos"]["sjf"] = {"json": str(sjf), "exists": sjf.exists()}

    # ── 4. RAG capture (opcional) — derivar chunks del audit ─────────────────
    chunks = []
    for s in (audit.get("retrieved_sources") or []):
        if s.get("ref_type") == "normativa":
            vvca = s.get("vvca", {}) or {}
            chunks.append({
                "precepto": s.get("reference", ""),
                "aplicacion": vvca.get("C_contextualizacion", ""),
                "score_rag": vvca.get("score", 0),
            })
    if chunks:
        chunks_file = caso / "chunks_rag.json"
        chunks_file.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        run([args.python, str(REPO / "capturar_rag.py"), "--chunks", str(chunks_file),
             "--out", str(caso), "--nombre", "rag_chunks"])
        summary["pasos"]["rag_capture"] = str(caso / "rag_chunks.png")

    (caso / "vvca_full.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Pipeline VVCA completo. Material en: {caso}")
    print(f"   Resumen: {caso / 'vvca_full.json'}")
    print("   Siguiente paso (manual por ahora): generar el .docx desde este material.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
