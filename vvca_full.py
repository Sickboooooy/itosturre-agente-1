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
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    if kw.get("text") and "encoding" not in kw:
        kw["encoding"] = "utf-8"
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
    ap.add_argument("--no-popup-articulos", action="store_true",
                     help="Saltar la generación de pop-ups por artículo 🟡/🔴 (snippet + página del PDF)")
    ap.add_argument("--no-telegram", action="store_true",
                     help="Generar los pop-ups de artículo pero no enviarlos a Telegram")
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
    rag_stdout = ra.stdout or ""
    (caso / "audit_rag.json").write_text(rag_stdout, encoding="utf-8")
    try:
        audit = json.loads(rag_stdout)
    except json.JSONDecodeError:
        audit = {"status": "parse_error", "stderr": (ra.stderr or "")[-2000:]}
    summary["pasos"]["rag_audit"] = audit.get("vvca_summary", audit.get("status"))
    traceability = audit.get("traceability")
    if traceability:
        trace_path = caso / "vvca_traceability.json"
        trace_path.write_text(
            json.dumps(traceability, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary["pasos"]["rag_traceability"] = {
            "json": str(trace_path),
            "summary": traceability.get("summary", {}),
        }

    # ── 2b. Memoria contextual ───────────────────────────────────────────────
    # Hasta ahora el veredicto y las citas bloqueadas morían en el JSON del caso:
    # ningún expediente auditado era consultable después. Se registran como
    # eventos para que la próxima sesión pueda recuperarlos sin releer la carpeta.
    # Accesorio por definición — si la memoria falla, la auditoría continúa.
    try:
        from itosturre.memoria.puente import registrar_auditoria

        n_eventos = registrar_auditoria(
            audit,
            raiz=str(REPO),
            caso=caso.name,
            borrador=str(borrador),
            faltantes=cobertura.get("missing") or [],
        )
        summary["pasos"]["memoria"] = {"eventos": n_eventos}
        if n_eventos:
            print(f"🧠 {n_eventos} evento(s) registrados en la memoria contextual.")
    except Exception as e:  # noqa: BLE001 — la memoria nunca tumba el pipeline
        summary["pasos"]["memoria"] = {"error": str(e)}

    # ── 3. SJF tesis (opcional) ──────────────────────────────────────────────
    if args.registros and not args.no_sjf:
        scraper = REPO / "services" / "itosturre-scraper" / "vvca_audit.ts"
        # En Windows, subprocess sin shell=True busca "npx.exe" (WinError 2): npx es
        # en realidad npx.CMD. shutil.which() resuelve la extensión real vía PATHEXT.
        npx = shutil.which("npx")
        if not npx:
            print("⚠️  'npx' no está en el PATH — se omite la verificación SJF en vivo.", file=sys.stderr)
            summary["pasos"]["sjf"] = {"error": "npx no encontrado en PATH"}
        else:
            cmd = [npx, "ts-node", "--esm", str(scraper), "--out", str(caso.resolve())]
            if args.contexto:
                cmd += ["--contexto", str(Path(args.contexto).resolve())]
            cmd += args.registros
            try:
                run(cmd, cwd=str(scraper.parent))
                sjf = caso / "auditoria_vvca.json"
                summary["pasos"]["sjf"] = {"json": str(sjf), "exists": sjf.exists()}
            except (OSError, subprocess.SubprocessError) as e:
                print(f"⚠️  Falló la verificación SJF en vivo: {e}", file=sys.stderr)
                summary["pasos"]["sjf"] = {"error": str(e)}

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

    # ── 5. Pop-ups por artículo 🟡/🔴 (opcional) — snippet literal + página del
    #      PDF como prueba de ubicación, uno por artículo, deduplicado ─────────
    if not args.no_popup_articulos:
        vistos = {}
        for s in (audit.get("retrieved_sources") or []):
            if s.get("ref_type") != "normativa":
                continue
            vvca = s.get("vvca", {}) or {}
            sem = vvca.get("semaforo")
            if sem not in ("🟡", "🔴"):
                continue
            key = (s.get("expected_source") or s.get("source_file"), s.get("article"))
            if key in vistos:
                vistos[key]["veces_citado"] += 1
                continue
            explicabilidad = vvca.get("explicabilidad", {}) or {}
            vistos[key] = {
                "reference": s.get("reference", ""),
                "law": s.get("law", ""),
                "article": s.get("article", ""),
                "source_file": s.get("source_file"),
                "expected_source": s.get("expected_source"),
                "page": s.get("page"),
                "semaforo": sem,
                # coincide_fuente es *vacíamente* True cuando expected_source es None
                # (ninguna ley fue identificada cerca de la cita) — eso NO es lo mismo
                # que "se confirmó que la ley es la correcta". Se distingue con
                # ley_identificada para no mostrar como probada una página que en
                # realidad viene de un match semántico sin ley de referencia.
                "coincide_fuente": explicabilidad.get("coincide_fuente", True),
                "ley_identificada": bool(s.get("expected_source")),
                "retrieved_text_full": s.get("retrieved_text_full") or s.get("retrieved_text"),
                "veces_citado": 1,
            }
        popup_items = list(vistos.values())
        if not popup_items:
            print("\n[INFO] 0 artículos 🟡/🔴 — nada que capturar en pop-ups.")
            summary["pasos"]["rag_popup_articulos"] = {"items": 0}
        else:
            popup_file = caso / "articulos_popup.json"
            popup_file.write_text(json.dumps(popup_items, ensure_ascii=False, indent=2), encoding="utf-8")
            cmd = [args.python, str(REPO / "capturar_rag.py"), "--modo", "popup",
                   "--items", str(popup_file), "--out", str(caso)]
            if args.no_telegram:
                cmd.append("--no-telegram")
            try:
                run(cmd)
                summary["pasos"]["rag_popup_articulos"] = {"items": len(popup_items)}
            except (OSError, subprocess.SubprocessError) as e:
                print(f"⚠️  Falló la generación de pop-ups por artículo: {e}", file=sys.stderr)
                summary["pasos"]["rag_popup_articulos"] = {"error": str(e)}

    (caso / "vvca_full.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ Pipeline VVCA completo. Material en: {caso}")
    print(f"   Resumen: {caso / 'vvca_full.json'}")
    print("   Siguiente paso (manual por ahora): generar el .docx desde este material.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
