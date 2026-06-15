"""
capturar_rag.py — genera screenshot de chunk cards del corpus OpenNotebook RAG
Uso: python capturar_rag.py --chunks chunks_rag.json --out auditorias/2026-06-14-FOVISSSTE
"""
import json
import argparse
import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", required=True, help="JSON con lista de chunks RAG")
    parser.add_argument("--out",    required=True, help="Directorio de salida")
    parser.add_argument("--nombre", default="rag_chunks")
    parser.add_argument("--leyes",  type=int, default=42)
    args = parser.parse_args()

    chunks = json.loads(Path(args.chunks).read_text(encoding="utf-8"))
    capturar(chunks, Path(args.out), args.nombre, args.leyes)

if __name__ == "__main__":
    main()
