import sys
import json
from playwright.sync_api import sync_playwright

def fetch(registro: str) -> dict:
    url = f"https://sjf2.scjn.gob.mx/detalle/tesis/{registro}"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 1400})
        page.goto(url, timeout=30000)
        page.wait_for_timeout(3000)
        try:
            page.wait_for_selector("h1, .tesis-rubro, .detalle-tesis", timeout=8000)
        except Exception:
            pass
        body_text = page.inner_text("body")
        browser.close()
        return {"registro": registro, "url": url, "body_text": body_text}

if __name__ == "__main__":
    reg = sys.argv[1]
    data = fetch(reg)
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"tesis_{reg}_raw.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"OK -> {out_path} ({len(data['body_text'])} chars)")
