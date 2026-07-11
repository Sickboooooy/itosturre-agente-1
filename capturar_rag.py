"""
capturar_rag.py — genera screenshot de chunk cards del corpus OpenNotebook RAG
Uso (modo tabla, default): python capturar_rag.py --chunks chunks_rag.json --out auditorias/2026-06-14-FOVISSSTE
Uso (modo popup, un PNG por artículo 🟡/🔴): python capturar_rag.py --modo popup --items articulos_popup.json --out <caso>
"""
import json
import argparse
import datetime
import os
import re
import sys
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright
import fitz  # PyMuPDF — ya es dependencia dura del proyecto (ver requirements.txt)
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

_BASE_DIR = Path(__file__).parent
INGEST_ALLOWED_BASE = os.getenv("INGEST_ALLOWED_BASE", str(_BASE_DIR))

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #111827;
    padding: 28px;
    width: 960px;
  }}
  .header {{
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1.5px solid #C9A84C;
    border-radius: 10px 10px 0 0;
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .header-title {{
    color: #C9A84C;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 1.2px;
    text-transform: uppercase;
  }}
  .header-badge {{
    background: #C9A84C;
    color: #1A1A2E;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #F9FAFB;
    border: 1.5px solid #C9A84C;
    border-top: none;
    border-radius: 0 0 10px 10px;
    overflow: hidden;
  }}
  thead tr th {{
    background: #1A1A2E;
    color: #C9A84C;
    padding: 10px 16px;
    font-size: 10.5px;
    text-align: left;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    border-bottom: 2px solid #C9A84C;
  }}
  th.col-score {{ text-align: center; width: 90px; }}
  th.col-semaforo {{ text-align: center; width: 60px; }}
  td {{
    padding: 11px 16px;
    font-size: 12px;
    border-bottom: 1px solid #E5E7EB;
    vertical-align: top;
    color: #1F2937;
    line-height: 1.5;
  }}
  td.precepto {{
    font-weight: 700;
    color: #1A1A2E;
    width: 220px;
    border-right: 2px solid #C9A84C;
    white-space: pre-line;
  }}
  td.score {{
    text-align: center;
    font-weight: 700;
    font-size: 13px;
    width: 90px;
    border-right: 1px solid #E5E7EB;
  }}
  td.semaforo {{
    text-align: center;
    font-size: 18px;
    width: 60px;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tr:nth-child(even) td {{ background: #F3F4F6; }}
  .score-green {{ color: #16A34A; }}
  .score-yellow {{ color: #D97706; }}
  .score-red {{ color: #DC2626; }}
  .footer {{
    color: #6B7280;
    font-size: 10px;
    text-align: right;
    margin-top: 8px;
    padding: 0 2px;
  }}
</style>
</head>
<body>
  <div class="header">
    <span class="header-title">📚 OpenNotebook RAG &mdash; Corpus Legal Verificado</span>
    <span class="header-badge">{total} preceptos · {leyes} leyes federales</span>
  </div>
  <table>
    <thead>
      <tr>
        <th>PRECEPTO</th>
        <th>APLICACIÓN AL CASO</th>
        <th class="col-score">SCORE RAG</th>
        <th class="col-semaforo">VVCA</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  <div class="footer">
    Fuente: ChromaDB · Corpus OpenNotebook v4.0 · {leyes} leyes federales MX &nbsp;·&nbsp; {date}
  </div>
</body>
</html>
"""

def semaforo(score: int) -> tuple[str, str]:
    if score >= 85: return "🟢", "score-green"
    if score >= 60: return "🟡", "score-yellow"
    return "🔴", "score-red"

def build_html(chunks: list[dict], leyes: int = 42) -> str:
    rows = []
    for c in chunks:
        score = c.get("score_rag", 0)
        sem, css = semaforo(score)
        rows.append(f"""
      <tr>
        <td class="precepto">{c['precepto']}</td>
        <td>{c['aplicacion']}</td>
        <td class="score {css}">{score}/100</td>
        <td class="semaforo">{sem}</td>
      </tr>""")
    return HTML_TEMPLATE.format(
        total=len(chunks),
        leyes=leyes,
        rows="\n".join(rows),
        date=datetime.date.today().strftime("%d/%b/%Y"),
    )

def capturar(chunks: list[dict], out_dir: Path, nombre: str = "rag_chunks", leyes: int = 42) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"{nombre}.html"
    png_path  = out_dir / f"{nombre}.png"

    html_path.write_text(build_html(chunks, leyes), encoding="utf-8")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
        )
        page = browser.new_page(viewport={"width": 1020, "height": 800})
        page.goto(f"file:///{html_path.as_posix()}")
        page.wait_for_load_state("networkidle")
        page.locator("body").screenshot(path=str(png_path))
        browser.close()

    html_path.unlink()  # limpiar HTML temporal
    print(f"[OK] Screenshot RAG guardado: {png_path}")
    return png_path


# ─────────────────────────────────────────────────────────────────────────
# MODO POPUP — un PNG por artículo con hallazgo (🟡/🔴): texto literal +
# página del PDF como prueba de ubicación (o tarjeta de no-coincidencia).
# ─────────────────────────────────────────────────────────────────────────

POPUP_MATCH_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #111827; padding: 28px; width: 820px; }}
  .header {{
    background: linear-gradient(135deg, #1A1A2E 0%, #16213E 100%);
    border: 1.5px solid #C9A84C;
    border-radius: 10px 10px 0 0;
    padding: 14px 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .header-title {{ color: #C9A84C; font-weight: 700; font-size: 13px; letter-spacing: 1px; }}
  .header-badge {{ padding: 4px 12px; border-radius: 20px; font-size: 11px; font-weight: 700; }}
  .badge-yellow {{ background: #D97706; color: #1A1A2E; }}
  .badge-red {{ background: #DC2626; color: #F9FAFB; }}
  .body {{
    background: #F9FAFB;
    border: 1.5px solid #C9A84C;
    border-top: none;
    border-radius: 0 0 10px 10px;
    padding: 20px;
  }}
  .label {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.8px; color: #6B7280; font-weight: 700; margin-bottom: 6px; }}
  .snippet {{
    background: #FFFFFF;
    border-left: 4px solid #C9A84C;
    padding: 14px 16px;
    font-size: 13.5px;
    line-height: 1.6;
    color: #1F2937;
    white-space: pre-line;
    margin-bottom: 18px;
  }}
  .page-img {{ width: 100%; border: 1px solid #E5E7EB; border-radius: 4px; }}
  .missing-pdf {{
    background: #FEF3C7;
    border: 1px solid #D97706;
    border-radius: 4px;
    padding: 12px 16px;
    font-size: 12.5px;
    color: #92400E;
  }}
  .footer {{ color: #6B7280; font-size: 10px; text-align: right; margin-top: 8px; padding: 0 2px; }}
</style>
</head>
<body>
  <div class="header">
    <span class="header-title">📖 {reference}</span>
    <span class="header-badge {badge_class}">{semaforo} {ley}</span>
  </div>
  <div class="body">
    <div class="label">TEXTO LITERAL DEL CORPUS</div>
    <div class="snippet">{snippet}</div>
    <div class="label">UBICACIÓN — {source_file}, pág. {page}</div>
    {page_block}
  </div>
  <div class="footer">
    Fuente: ChromaDB · Corpus OpenNotebook v4.0 · {date}
  </div>
</body>
</html>
"""

POPUP_MISMATCH_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #111827; padding: 28px; width: 820px; }}
  .header {{
    background: linear-gradient(135deg, #450A0A 0%, #7F1D1D 100%);
    border: 1.5px solid #DC2626;
    border-radius: 10px 10px 0 0;
    padding: 14px 20px;
  }}
  .header-title {{ color: #FCA5A5; font-weight: 700; font-size: 13px; letter-spacing: 1px; }}
  .body {{
    background: #F9FAFB;
    border: 1.5px solid #DC2626;
    border-top: none;
    border-radius: 0 0 10px 10px;
    padding: 20px;
  }}
  .alert {{
    background: #FEF2F2;
    border-left: 4px solid #DC2626;
    padding: 12px 16px;
    font-size: 13px;
    color: #7F1D1D;
    font-weight: 600;
    margin-bottom: 16px;
  }}
  .compare {{ display: flex; gap: 16px; margin-bottom: 16px; }}
  .compare-col {{ flex: 1; }}
  .compare-label {{ font-size: 10px; text-transform: uppercase; color: #6B7280; font-weight: 700; margin-bottom: 4px; }}
  .compare-value {{ background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 4px; padding: 10px 12px; font-size: 12.5px; color: #1F2937; }}
  .label {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.8px; color: #6B7280; font-weight: 700; margin-bottom: 6px; }}
  .snippet {{ background: #FFFFFF; border-left: 4px solid #6B7280; padding: 14px 16px; font-size: 13px; line-height: 1.6; color: #1F2937; white-space: pre-line; }}
  .footer {{ color: #6B7280; font-size: 10px; text-align: right; margin-top: 8px; padding: 0 2px; }}
</style>
</head>
<body>
  <div class="header">
    <span class="header-title">🔴 {reference} — FUENTE NO COINCIDE</span>
  </div>
  <div class="body">
    <div class="alert">La ley citada y la ley donde realmente se encontró el texto NO coinciden. No se muestra ubicación en PDF — verificar manualmente antes de citar.</div>
    <div class="compare">
      <div class="compare-col">
        <div class="compare-label">LEY CITADA</div>
        <div class="compare-value">{expected_source}</div>
      </div>
      <div class="compare-col">
        <div class="compare-label">TEXTO ENCONTRADO EN</div>
        <div class="compare-value">{source_file}</div>
      </div>
    </div>
    <div class="label">TEXTO ENCONTRADO (contexto, no prueba de la cita)</div>
    <div class="snippet">{snippet}</div>
  </div>
  <div class="footer">
    Fuente: ChromaDB · Corpus OpenNotebook v4.0 · {date}
  </div>
</body>
</html>
"""

POPUP_UNVERIFIED_TEMPLATE = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', Arial, sans-serif; background: #111827; padding: 28px; width: 820px; }}
  .header {{
    background: linear-gradient(135deg, #451A03 0%, #78350F 100%);
    border: 1.5px solid #D97706;
    border-radius: 10px 10px 0 0;
    padding: 14px 20px;
  }}
  .header-title {{ color: #FCD34D; font-weight: 700; font-size: 13px; letter-spacing: 1px; }}
  .body {{
    background: #F9FAFB;
    border: 1.5px solid #D97706;
    border-top: none;
    border-radius: 0 0 10px 10px;
    padding: 20px;
  }}
  .alert {{
    background: #FFFBEB;
    border-left: 4px solid #D97706;
    padding: 12px 16px;
    font-size: 13px;
    color: #78350F;
    font-weight: 600;
    margin-bottom: 16px;
  }}
  .label {{ font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.8px; color: #6B7280; font-weight: 700; margin-bottom: 6px; }}
  .value {{ background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 4px; padding: 10px 12px; font-size: 12.5px; color: #1F2937; margin-bottom: 16px; }}
  .snippet {{ background: #FFFFFF; border-left: 4px solid #6B7280; padding: 14px 16px; font-size: 13px; line-height: 1.6; color: #1F2937; white-space: pre-line; }}
  .footer {{ color: #6B7280; font-size: 10px; text-align: right; margin-top: 8px; padding: 0 2px; }}
</style>
</head>
<body>
  <div class="header">
    <span class="header-title">⚠️ {reference} — {titulo}</span>
  </div>
  <div class="body">
    <div class="alert">{alerta}</div>
    <div class="label">MEJOR CANDIDATO ENCONTRADO EN</div>
    <div class="value">{source_file}</div>
    <div class="label">TEXTO ENCONTRADO (candidato, no confirmado)</div>
    <div class="snippet">{snippet}</div>
  </div>
  <div class="footer">
    Fuente: ChromaDB · Corpus OpenNotebook v4.0 · {date}
  </div>
</body>
</html>
"""

def locate_pdf(filename: str) -> Path | None:
    """Busca el PDF original en corpus/ (repo) y luego en INGEST_ALLOWED_BASE
    (búsqueda plana, igual que hace OpenNotebook.ingest())."""
    if not filename:
        return None
    for base in (_BASE_DIR / "corpus", Path(INGEST_ALLOWED_BASE)):
        candidate = base / filename
        if candidate.exists():
            return candidate
    return None

def render_pdf_page_b64(pdf_path: Path, page: str, zoom: float = 2.0) -> str | None:
    """Renderiza una página del PDF (1-indexada) a PNG en base64. Nunca truena:
    devuelve None ante cualquier fallo (archivo corrupto, página fuera de rango, etc.)."""
    try:
        page_num = int(page)
    except (TypeError, ValueError):
        print(f"[WARN] Número de página inválido: {page!r}", file=sys.stderr)
        return None
    try:
        doc = fitz.open(str(pdf_path))
        try:
            if page_num < 1 or page_num > doc.page_count:
                print(f"[WARN] Página {page_num} fuera de rango en {pdf_path.name} ({doc.page_count} páginas)", file=sys.stderr)
                return None
            pix = doc[page_num - 1].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            return base64.b64encode(pix.tobytes("png")).decode("ascii")
        finally:
            doc.close()
    except Exception as e:
        print(f"[WARN] No se pudo renderizar {pdf_path} pág. {page}: {e}", file=sys.stderr)
        return None

def _slug(text: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^\w]+", "_", (text or "").strip().lower()).strip("_")
    return s[:maxlen] or "item"

def _escape(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _display_law(item: dict) -> str:
    """'desconocido' es un placeholder interno de extract_references(), no un dato
    útil para mostrar — preferir la ley resuelta (expected_source/source_file)."""
    law = item.get("law") or ""
    if law and law != "desconocido":
        return law
    return item.get("expected_source") or item.get("source_file") or ""

_ARTICULO_HEADER_RE_CACHE: dict = {}

def _contains_article_header(text: str, article) -> bool:
    """¿El texto recuperado realmente trae un encabezado 'Artículo {N}' para el
    número citado? Evita mostrar como 'prueba' un chunk que coincide en ley y
    rankeó bien, pero corresponde a OTRO número de artículo (vecino semántico)."""
    if not article or not text:
        return True  # sin dato para comparar — no bloqueamos por esto
    m = re.match(r"\d+", str(article))
    if not m:
        return True  # formato no numérico (transitorios, etc.) — no verificable así
    num = m.group(0)
    pattern = _ARTICULO_HEADER_RE_CACHE.get(num)
    if pattern is None:
        pattern = re.compile(rf"art[íi]culos?\.?\s+{re.escape(num)}(?!\d)", re.IGNORECASE)
        _ARTICULO_HEADER_RE_CACHE[num] = pattern
    return bool(pattern.search(text))

def build_popup_html(item: dict) -> str:
    snippet_raw = item.get("retrieved_text_full") or item.get("retrieved_text") or ""
    snippet = _escape(snippet_raw or "(sin texto)")
    reference = _escape(item.get("reference", ""))
    sem = item.get("semaforo", "🟡")
    date = datetime.date.today().strftime("%d/%b/%Y")

    # Caso 1: ninguna ley fue identificada cerca de la cita — el "coincide_fuente"
    # es vacíamente True aquí (no hay con qué comparar), así que NO se debe mostrar
    # como si estuviera probado. Se muestra el candidato con advertencia explícita,
    # sin página de PDF (evita fabricar una prueba de ubicación no confirmada).
    if not item.get("ley_identificada", True):
        return POPUP_UNVERIFIED_TEMPLATE.format(
            reference=reference,
            titulo="LEY NO IDENTIFICADA EN EL TEXTO",
            alerta="El escrito no nombra explícitamente la ley cerca de esta cita. "
                   "El texto de abajo es el mejor candidato por similitud semántica, "
                   "pero NO está confirmado que sea la ley correcta — no se muestra "
                   "página de PDF como prueba de ubicación.",
            source_file=_escape(item.get("source_file") or "?"),
            snippet=snippet,
            date=date,
        )

    # Caso 2: ley identificada, pero el chunk recuperado vino de OTRA ley — la
    # bandera roja del P0 de integridad del corpus haciéndose visible.
    if not item.get("coincide_fuente", True):
        return POPUP_MISMATCH_TEMPLATE.format(
            reference=reference,
            expected_source=_escape(item.get("expected_source") or "(no identificada)"),
            source_file=_escape(item.get("source_file") or "?"),
            snippet=snippet,
            date=date,
        )

    # Caso 3: misma ley, pero el chunk corresponde a OTRO número de artículo (p. ej.
    # se citó "artículo 8" y el chunk recuperado es en realidad "Artículo 68"). No
    # es un error de ley — es un error de número — pero igual invalida la "prueba".
    if not _contains_article_header(snippet_raw, item.get("article")):
        return POPUP_UNVERIFIED_TEMPLATE.format(
            reference=reference,
            titulo="NÚMERO DE ARTÍCULO NO CONFIRMADO",
            alerta=f"Se citó el artículo {_escape(str(item.get('article') or '?'))}, pero el "
                   "texto recuperado del corpus no trae ese encabezado — podría corresponder "
                   "a otro artículo de la misma ley (vecino semántico). No se muestra página "
                   "de PDF como prueba hasta verificar manualmente el número exacto.",
            source_file=_escape(item.get("source_file") or "?"),
            snippet=snippet,
            date=date,
        )

    # Caso 4: ley identificada, coincide, y el número de artículo se confirma en el
    # propio texto — snippet + página del PDF como prueba.
    badge_class = "badge-red" if sem == "🔴" else "badge-yellow"
    ley = _escape(_display_law(item))
    source_file = item.get("source_file") or ""
    page = item.get("page") or "?"
    pdf_path = locate_pdf(source_file) if source_file else None
    b64 = render_pdf_page_b64(pdf_path, page) if pdf_path else None
    if b64:
        page_block = f'<img class="page-img" src="data:image/png;base64,{b64}" alt="pág. {_escape(str(page))}">'
    else:
        page_block = '<div class="missing-pdf">⚠️ PDF no disponible localmente — no se pudo renderizar la página para verificación visual.</div>'

    return POPUP_MATCH_TEMPLATE.format(
        reference=reference,
        semaforo=sem,
        badge_class=badge_class,
        ley=ley,
        snippet=snippet,
        source_file=_escape(source_file or "?"),
        page=_escape(str(page)),
        page_block=page_block,
        date=date,
    )

def capturar_articulos(items: list[dict], out_dir: Path, prefix: str = "art") -> list[dict]:
    """Genera un PNG por artículo (snippet literal + página del PDF, o tarjeta de
    no-coincidencia). Reutiliza un solo browser Playwright para todo el lote.
    Devuelve [{"path", "caption"}] listo para enviar por Telegram."""
    out_dir.mkdir(parents=True, exist_ok=True)
    resultados = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
        )
        page_ctx = browser.new_page(viewport={"width": 880, "height": 900})
        for i, item in enumerate(items, 1):
            slug = _slug(f"{_display_law(item)}_{item.get('article','')}")
            html = build_popup_html(item)
            html_path = out_dir / f"{prefix}_{i:02d}_{slug}.html"
            png_path  = out_dir / f"{prefix}_{i:02d}_{slug}.png"
            html_path.write_text(html, encoding="utf-8")
            page_ctx.goto(f"file:///{html_path.as_posix()}")
            page_ctx.wait_for_load_state("networkidle")
            page_ctx.locator("body").screenshot(path=str(png_path))
            html_path.unlink()

            sem = item.get("semaforo", "🟡")
            veces = item.get("veces_citado", 1)
            extra = f" (citado {veces}x)" if veces and veces > 1 else ""
            caption = f"{sem} {item.get('reference','')}{extra}"
            resultados.append({"path": str(png_path), "caption": caption})
            print(f"[OK] Popup artículo guardado: {png_path}")
        browser.close()
    return resultados


# ─────────────────────────────────────────────────────────────────────────
# Envío a Telegram (Python puro, mismo patrón que services/itosturre-wa/telegram_listener.py)
# ─────────────────────────────────────────────────────────────────────────

def _load_telegram_env() -> tuple:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if token and chat_id:
        return token, chat_id
    fallback = Path.home() / ".claude" / "channels" / "telegram" / ".env"
    if fallback.exists():
        for line in fallback.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                chat_id = line.split("=", 1)[1].strip()
    return (token, chat_id) if token and chat_id else (None, None)

def enviar_texto(token: str, chat_id: str, text: str) -> bool:
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=30,
        )
        return r.ok
    except Exception as e:
        print(f"[WARN] Falló envío de texto a Telegram: {e}", file=sys.stderr)
        return False

def enviar_foto(token: str, chat_id: str, path: str, caption: str = "") -> bool:
    try:
        with open(path, "rb") as f:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": caption},
                files={"photo": f},
                timeout=60,
            )
        return r.ok
    except Exception as e:
        print(f"[WARN] Falló envío de foto a Telegram ({path}): {e}", file=sys.stderr)
        return False

def enviar_lote_telegram(resultados: list[dict], resumen: str) -> dict:
    token, chat_id = _load_telegram_env()
    if not token or not chat_id:
        print("[WARN] TELEGRAM_BOT_TOKEN/CHAT_ID no configurados — se omite el envío.", file=sys.stderr)
        return {"enviado": False, "razon": "credenciales no configuradas"}
    enviar_texto(token, chat_id, resumen)
    enviados = sum(1 for r in resultados if enviar_foto(token, chat_id, r["path"], r["caption"]))
    return {"enviado": True, "fotos_enviadas": enviados, "total": len(resultados)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", help="JSON con lista de chunks RAG (modo tabla)")
    parser.add_argument("--items",  help="JSON con lista de artículos enriquecidos (modo popup)")
    parser.add_argument("--out",    required=True, help="Directorio de salida")
    parser.add_argument("--nombre", default="rag_chunks")
    parser.add_argument("--leyes",  type=int, default=42)
    parser.add_argument("--modo",   choices=["tabla", "popup"], default="tabla")
    parser.add_argument("--no-telegram", action="store_true", help="Solo generar PNGs, no enviar a Telegram")
    args = parser.parse_args()

    if args.modo == "tabla":
        if not args.chunks:
            parser.error("--chunks es requerido en modo tabla")
        chunks = json.loads(Path(args.chunks).read_text(encoding="utf-8"))
        capturar(chunks, Path(args.out), args.nombre, args.leyes)
        return

    if not args.items:
        parser.error("--items es requerido en modo popup")
    items = json.loads(Path(args.items).read_text(encoding="utf-8"))
    if not items:
        print("[INFO] 0 artículos 🟡/🔴 — nada que capturar.")
        return

    resultados = capturar_articulos(items, Path(args.out))
    if not args.no_telegram:
        resumen = f"📖 {len(resultados)} artículo(s) con hallazgo (🟡/🔴) — evidencia adjunta"
        envio = enviar_lote_telegram(resultados, resumen)
        print(f"[OK] Telegram: {envio}")

if __name__ == "__main__":
    main()
