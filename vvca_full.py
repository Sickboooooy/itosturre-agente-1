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
      [--no-rag-capture] [--allow-partial-sjf]

Falla cerrado: si un paso esencial termina con error o produce una salida inválida,
persiste el diagnóstico, devuelve código 1 y no anuncia éxito. Solo ``--force``,
``--no-sjf``, ``--no-rag-capture`` y ``--allow-partial-sjf`` autorizan degradación u
omisión explícita.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent
SUMMARY_SCHEMA_VERSION = "2.0"


class PipelineStepError(RuntimeError):
    """Fallo de un subproceso esencial del pipeline."""

    def __init__(self, step: str, result: subprocess.CompletedProcess):
        self.step = step
        self.result = result
        super().__init__(
            f"{step} terminó con código {result.returncode}"
        )


def run(
    cmd: list,
    *,
    step: str | None = None,
    check: bool = False,
    **kw,
) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(str(c) for c in cmd)}")
    if kw.get("text") and "encoding" not in kw:
        kw["encoding"] = "utf-8"
    result = subprocess.run(cmd, **kw)
    if check and result.returncode != 0:
        raise PipelineStepError(step or str(cmd[0]), result)
    return result


def _compact_output(value: Any, limit: int = 2000) -> str:
    text = str(value or "").strip()
    return text[-limit:]


def _write_summary(caso: Path, summary: dict) -> Path:
    """Persiste el resumen de forma atómica para no dejar JSON truncado."""
    path = caso / "vvca_full.json"
    temp = caso / "vvca_full.json.tmp"
    temp.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temp.replace(path)
    return path


def _failure(
    caso: Path,
    summary: dict,
    *,
    step: str,
    message: str,
    result: subprocess.CompletedProcess | None = None,
) -> int:
    error = {"step": step, "message": message}
    if result is not None:
        error["returncode"] = result.returncode
        stderr = _compact_output(getattr(result, "stderr", ""))
        stdout = _compact_output(getattr(result, "stdout", ""))
        if stderr:
            error["stderr"] = stderr
        if stdout:
            error["stdout"] = stdout
    summary["status"] = "failed"
    summary.setdefault("errors", []).append(error)
    summary.setdefault("pasos", {}).setdefault(step, {})
    if isinstance(summary["pasos"][step], dict):
        summary["pasos"][step].update({"status": "failed", "error": message})
    path = _write_summary(caso, summary)
    print(f"\n❌ Pipeline VVCA fallido en {step}: {message}", file=sys.stderr)
    print(f"   Diagnóstico: {path}", file=sys.stderr)
    return 1


def _partial(
    summary: dict,
    *,
    step: str,
    message: str,
    result: subprocess.CompletedProcess | None = None,
) -> None:
    warning = {"step": step, "message": message}
    if result is not None:
        warning["returncode"] = result.returncode
        stderr = _compact_output(getattr(result, "stderr", ""))
        if stderr:
            warning["stderr"] = stderr
    summary["status"] = "partial"
    summary.setdefault("warnings", []).append(warning)
    summary.setdefault("pasos", {})[step] = {
        "status": "partial",
        "warning": message,
    }
    print(f"\n⚠️  Pipeline parcial en {step}: {message}", file=sys.stderr)


def _partial_or_failure(
    caso: Path,
    summary: dict,
    *,
    allowed: bool,
    step: str,
    message: str,
    result: subprocess.CompletedProcess | None = None,
) -> int | None:
    if allowed:
        _partial(summary, step=step, message=message, result=result)
        return None
    return _failure(
        caso,
        summary,
        step=step,
        message=message,
        result=result,
    )


def _read_json_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("la raíz JSON no es un objeto")
    return value


def main(argv: list[str] | None = None) -> int:
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
    ap.add_argument(
        "--allow-partial-sjf",
        action="store_true",
        help=(
            "Continuar de forma explícita con status=partial si falla el SJF solicitado; "
            "sin este flag el pipeline falla cerrado"
        ),
    )
    ap.add_argument(
        "--no-rag-capture",
        action="store_true",
        help="Omitir explícitamente la captura PNG de chunks RAG",
    )
    ap.add_argument("--no-popup-articulos", action="store_true",
                     help="Saltar la generación de pop-ups por artículo 🟡/🔴 (snippet + página del PDF)")
    ap.add_argument("--no-telegram", action="store_true",
                     help="Generar los pop-ups de artículo pero no enviarlos a Telegram")
    ap.add_argument("--python", default=sys.executable, help="Intérprete Python a usar")
    args = ap.parse_args(argv)

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

    summary: dict = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "running",
        "caso": str(caso),
        "borrador": str(borrador),
        "pasos": {},
        "warnings": [],
        "errors": [],
    }

    # ── 1. Gate de cobertura del corpus ──────────────────────────────────────
    try:
        cc = run(
            [args.python, str(REPO / "scripts" / "check_corpus.py"), "--json"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return _failure(
            caso,
            summary,
            step="check_corpus",
            message=f"no se pudo iniciar el verificador de cobertura: {exc}",
        )
    try:
        cobertura = json.loads(cc.stdout or "")
        if not isinstance(cobertura, dict) or not isinstance(cobertura.get("missing"), list):
            raise ValueError("salida sin lista 'missing'")
    except (json.JSONDecodeError, ValueError) as exc:
        return _failure(
            caso,
            summary,
            step="check_corpus",
            message=f"salida de cobertura inválida: {exc}",
            result=cc,
        )

    missing = cobertura["missing"]
    cobertura["returncode"] = cc.returncode
    cobertura["status"] = "partial" if missing and args.force else "ok"
    summary["pasos"]["check_corpus"] = cobertura
    if cc.returncode not in (0, 1):
        return _failure(
            caso,
            summary,
            step="check_corpus",
            message="el verificador de cobertura no pudo ejecutarse",
            result=cc,
        )
    if missing and cc.returncode == 0:
        return _failure(
            caso,
            summary,
            step="check_corpus",
            message="resultado inconsistente: reportó faltantes con código de éxito",
            result=cc,
        )
    if not missing and cc.returncode != 0:
        return _failure(
            caso,
            summary,
            step="check_corpus",
            message="resultado inconsistente: no reportó faltantes pero devolvió error",
            result=cc,
        )
    if missing and not args.force:
        return _failure(
            caso,
            summary,
            step="check_corpus",
            message=(
                "corpus incompleto; re-indexa las fuentes faltantes o usa --force "
                "para continuar de forma explícita"
            ),
            result=cc,
        )
    if missing:
        _partial(
            summary,
            step="check_corpus",
            message=f"auditoría autorizada con corpus parcial: {missing}",
            result=cc,
        )
        summary["pasos"]["check_corpus"].update(cobertura)

    # ── 2. RAG audit ─────────────────────────────────────────────────────────
    try:
        ra = run(
            [args.python, str(REPO / "OpenNotebook.py"), "audit", "--file", str(borrador)]
            + (["--force"] if args.force else []),
            step="rag_audit",
            check=True,
            capture_output=True,
            text=True,
        )
    except PipelineStepError as exc:
        return _failure(
            caso,
            summary,
            step="rag_audit",
            message="OpenNotebook terminó con error",
            result=exc.result,
        )
    except OSError as exc:
        return _failure(
            caso,
            summary,
            step="rag_audit",
            message=f"no se pudo iniciar OpenNotebook: {exc}",
        )

    rag_stdout = ra.stdout or ""
    try:
        audit = json.loads(rag_stdout)
        if not isinstance(audit, dict):
            raise ValueError("la raíz JSON no es un objeto")
    except (json.JSONDecodeError, ValueError) as exc:
        return _failure(
            caso,
            summary,
            step="rag_audit",
            message=f"OpenNotebook no produjo JSON válido: {exc}",
            result=ra,
        )
    if audit.get("status") != "ok":
        return _failure(
            caso,
            summary,
            step="rag_audit",
            message=f"auditoría RAG no utilizable: status={audit.get('status')!r}",
            result=ra,
        )

    (caso / "audit_rag.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary["pasos"]["rag_audit"] = {
        "status": "ok",
        "vvca_summary": audit.get("vvca_summary", {}),
    }
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
        summary["pasos"]["memoria"] = {"status": "ok", "eventos": n_eventos}
        if n_eventos:
            print(f"🧠 {n_eventos} evento(s) registrados en la memoria contextual.")
    except Exception as e:  # noqa: BLE001 — la memoria nunca tumba el pipeline
        message = f"memoria contextual no disponible: {e}"
        summary["pasos"]["memoria"] = {"status": "warning", "error": str(e)}
        summary["warnings"].append({"step": "memoria", "message": message})

    # ── 3. SJF tesis (opcional) ──────────────────────────────────────────────
    if args.registros and args.no_sjf:
        summary["pasos"]["sjf"] = {
            "status": "skipped",
            "reason": "omitido explícitamente con --no-sjf",
            "registros": args.registros,
        }
    elif args.registros:
        scraper = REPO / "services" / "itosturre-scraper" / "vvca_audit.ts"
        sjf = caso / "auditoria_vvca.json"
        previous_mtime = sjf.stat().st_mtime_ns if sjf.exists() else None
        # En Windows, subprocess sin shell=True busca "npx.exe" (WinError 2): npx es
        # en realidad npx.CMD. shutil.which() resuelve la extensión real vía PATHEXT.
        npx = shutil.which("npx")
        if not npx:
            outcome = _partial_or_failure(
                caso,
                summary,
                allowed=args.allow_partial_sjf,
                step="sjf",
                message="npx no encontrado en PATH; no se verificó el SJF solicitado",
            )
            if outcome is not None:
                return outcome
        else:
            cmd = [npx, "ts-node", "--esm", str(scraper), "--out", str(caso.resolve())]
            if args.contexto:
                cmd += ["--contexto", str(Path(args.contexto).resolve())]
            cmd += args.registros
            try:
                sjf_result = run(
                    cmd,
                    step="sjf",
                    check=True,
                    cwd=str(scraper.parent),
                )
            except PipelineStepError as exc:
                outcome = _partial_or_failure(
                    caso,
                    summary,
                    allowed=args.allow_partial_sjf,
                    step="sjf",
                    message="el scraper SJF terminó con error",
                    result=exc.result,
                )
                if outcome is not None:
                    return outcome
            except OSError as exc:
                outcome = _partial_or_failure(
                    caso,
                    summary,
                    allowed=args.allow_partial_sjf,
                    step="sjf",
                    message=f"no se pudo iniciar el scraper SJF: {exc}",
                )
                if outcome is not None:
                    return outcome
            else:
                current_mtime = sjf.stat().st_mtime_ns if sjf.exists() else None
                if current_mtime is None or current_mtime == previous_mtime:
                    outcome = _partial_or_failure(
                        caso,
                        summary,
                        allowed=args.allow_partial_sjf,
                        step="sjf",
                        message="el scraper no produjo un auditoria_vvca.json nuevo",
                        result=sjf_result,
                    )
                    if outcome is not None:
                        return outcome
                else:
                    try:
                        sjf_payload = _read_json_object(sjf)
                        if sjf_payload.get("schema_version") != "2.0":
                            raise ValueError("schema_version SJF distinto de 2.0")
                        if not isinstance(sjf_payload.get("verificados"), list):
                            raise ValueError("falta la lista 'verificados'")
                        if not isinstance(sjf_payload.get("propuestas"), list):
                            raise ValueError("falta la lista 'propuestas'")
                    except (OSError, json.JSONDecodeError, ValueError) as exc:
                        outcome = _partial_or_failure(
                            caso,
                            summary,
                            allowed=args.allow_partial_sjf,
                            step="sjf",
                            message=f"salida SJF inválida: {exc}",
                            result=sjf_result,
                        )
                        if outcome is not None:
                            return outcome
                    else:
                        summary["pasos"]["sjf"] = {
                            "status": "ok",
                            "json": str(sjf),
                            "schema_version": sjf_payload["schema_version"],
                            "verificados": len(sjf_payload["verificados"]),
                            "propuestas": len(sjf_payload["propuestas"]),
                        }
    else:
        summary["pasos"]["sjf"] = {
            "status": "not_requested",
            "reason": "no se proporcionaron registros",
        }

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
    if args.no_rag_capture:
        summary["pasos"]["rag_capture"] = {
            "status": "skipped",
            "reason": "omitido explícitamente con --no-rag-capture",
            "chunks": len(chunks),
        }
    elif chunks:
        chunks_file = caso / "chunks_rag.json"
        chunks_file.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")
        capture_path = caso / "rag_chunks.png"
        previous_mtime = capture_path.stat().st_mtime_ns if capture_path.exists() else None
        try:
            run(
                [args.python, str(REPO / "capturar_rag.py"), "--chunks", str(chunks_file),
                 "--out", str(caso), "--nombre", "rag_chunks"],
                step="rag_capture",
                check=True,
            )
        except PipelineStepError as exc:
            return _failure(
                caso,
                summary,
                step="rag_capture",
                message="falló la captura de evidencia RAG",
                result=exc.result,
            )
        except OSError as exc:
            return _failure(
                caso,
                summary,
                step="rag_capture",
                message=f"no se pudo iniciar capturar_rag.py: {exc}",
            )
        current_mtime = capture_path.stat().st_mtime_ns if capture_path.exists() else None
        if current_mtime is None or current_mtime == previous_mtime:
            return _failure(
                caso,
                summary,
                step="rag_capture",
                message="capturar_rag.py terminó sin producir un rag_chunks.png nuevo",
            )
        summary["pasos"]["rag_capture"] = {
            "status": "ok",
            "png": str(capture_path),
        }
    else:
        summary["pasos"]["rag_capture"] = {
            "status": "not_required",
            "reason": "la auditoría no devolvió chunks normativos",
        }

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
            summary["pasos"]["rag_popup_articulos"] = {
                "status": "not_required",
                "items": 0,
            }
        else:
            popup_file = caso / "articulos_popup.json"
            popup_file.write_text(json.dumps(popup_items, ensure_ascii=False, indent=2), encoding="utf-8")
            cmd = [args.python, str(REPO / "capturar_rag.py"), "--modo", "popup",
                   "--items", str(popup_file), "--out", str(caso)]
            if args.no_telegram:
                cmd.append("--no-telegram")
            try:
                run(cmd, step="rag_popup_articulos", check=True)
            except PipelineStepError as exc:
                return _failure(
                    caso,
                    summary,
                    step="rag_popup_articulos",
                    message="falló la generación de pop-ups por artículo",
                    result=exc.result,
                )
            except OSError as exc:
                return _failure(
                    caso,
                    summary,
                    step="rag_popup_articulos",
                    message=f"no se pudo iniciar capturar_rag.py: {exc}",
                )
            summary["pasos"]["rag_popup_articulos"] = {
                "status": "ok",
                "items": len(popup_items),
            }
    else:
        summary["pasos"]["rag_popup_articulos"] = {
            "status": "skipped",
            "reason": "omitido explícitamente con --no-popup-articulos",
        }

    if summary["status"] == "running":
        summary["status"] = "ok"
    path = _write_summary(caso, summary)
    if summary["status"] == "partial":
        print(f"\n⚠️  Pipeline VVCA parcial (continuación autorizada). Material en: {caso}")
    else:
        print(f"\n✅ Pipeline VVCA completo. Material en: {caso}")
    print(f"   Resumen: {path}")
    print("   Siguiente paso (manual por ahora): generar el .docx desde este material.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
