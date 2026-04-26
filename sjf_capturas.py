"""
sjf_capturas.py — Captura de pantalla de tesis SJF para PDF de auditoría.

Uso standalone:
    source /home/licjo/venv/bin/activate
    python3 sjf_capturas.py 2030595 2030570 2027948

Uso como módulo:
    from sjf_capturas import capturar_tesis, agregar_capturas_al_pdf
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Optional

SJF_BASE = "https://sjf2.scjn.gob.mx/detalle/tesis/{registro}"
CAPTURAS_DIR = Path("/home/licjo/jurisprudencia/capturas")


async def _tomar_captura(registro: str, output_path: Path) -> bool:
    """Captura la página del SJF para un registro dado. Retorna True si exitosa."""
    from playwright.async_api import async_playwright

    url = SJF_BASE.format(registro=registro)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 900})
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(2500)  # Esperar que cargue el contenido dinámico

            # Intentar esperar que aparezca el rubro
            try:
                await page.wait_for_selector("h1, .tesis-rubro, .detalle-tesis", timeout=5000)
            except Exception:
                pass  # Continuar aunque no encuentre el selector

            await page.screenshot(path=str(output_path), full_page=False)
            await browser.close()
            return output_path.exists() and output_path.stat().st_size > 5000
    except Exception as e:
        print(f"  ⚠️ Error capturando {registro}: {e}")
        return False


def capturar_tesis(registros: list[str], directorio: Optional[Path] = None) -> dict[str, Path]:
    """
    Toma capturas de pantalla del SJF para cada registro.

    Args:
        registros: Lista de números de registro (ej. ["2030595", "2030570"])
        directorio: Carpeta de destino. Por defecto: /home/licjo/jurisprudencia/capturas/

    Returns:
        Dict {registro: ruta_imagen} — solo los exitosos.
    """
    out_dir = directorio or CAPTURAS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    resultados = {}
    for reg in registros:
        path = out_dir / f"sjf_{reg}.png"
        if path.exists() and path.stat().st_size > 5000:
            print(f"  📷 [{reg}] Captura existente → {path.name}")
            resultados[reg] = path
            continue

        print(f"  📷 [{reg}] Capturando sjf2.scjn.gob.mx...")
        ok = asyncio.run(_tomar_captura(reg, path))
        if ok:
            kb = path.stat().st_size // 1024
            print(f"  ✅ [{reg}] {kb} KB → {path.name}")
            resultados[reg] = path
        else:
            print(f"  ❌ [{reg}] Captura fallida")

    return resultados


def agregar_capturas_al_pdf(story: list, capturas: dict[str, Path],
                             tesis_meta: Optional[list[dict]] = None,
                             max_capturas: int = 5) -> list:
    """
    Agrega una sección 'ANEXO — Capturas SJF' al story de reportlab.

    Args:
        story:       Lista de flowables de reportlab (se modifica in-place).
        capturas:    Dict {registro: Path} devuelto por capturar_tesis().
        tesis_meta:  Lista de dicts con {registro, rubro, score} para etiquetas.
                     Si es None se usan solo los números de registro.
        max_capturas: Máximo de imágenes a incluir (default 5 — política Itosturre).

    Returns:
        El mismo story con los flowables de capturas añadidos.
    """
    from reportlab.platypus import (
        Paragraph, Spacer, Image as RLImage, PageBreak, HRFlowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch, cm
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    # Colores corporativos Itosturre
    AZUL_MEDIO = colors.HexColor("#1A3A6B")
    CYAN_NEON  = colors.HexColor("#06B6D4")
    AZUL_OSCURO= colors.HexColor("#0D1F3C")
    GRIS_TEXTO = colors.HexColor("#475569")
    BLANCO     = colors.white

    style_seccion = ParagraphStyle("seccion_capturas",
        fontSize=12, fontName="Helvetica-Bold",
        textColor=BLANCO, alignment=TA_LEFT,
        backColor=AZUL_MEDIO, borderPadding=(6, 8, 6, 8),
        spaceAfter=8, spaceBefore=14)

    style_label = ParagraphStyle("label_captura",
        fontSize=9, fontName="Helvetica-Bold",
        textColor=AZUL_OSCURO, spaceAfter=2, spaceBefore=6)

    style_url = ParagraphStyle("url_captura",
        fontSize=7.5, fontName="Helvetica-Oblique",
        textColor=GRIS_TEXTO, spaceAfter=8)

    style_nota = ParagraphStyle("nota_capturas",
        fontSize=8, fontName="Helvetica-Oblique",
        textColor=GRIS_TEXTO, alignment=TA_CENTER, spaceAfter=4)

    # Construir índice meta {registro: info}
    meta_index = {}
    if tesis_meta:
        for t in tesis_meta:
            reg = str(t.get("registro", ""))
            if reg:
                meta_index[reg] = t

    registros_a_incluir = list(capturas.keys())[:max_capturas]

    if not registros_a_incluir:
        return story

    story.append(PageBreak())
    story.append(Paragraph(
        f"  ANEXO — CAPTURAS SJF (top {len(registros_a_incluir)} por VVCA)",
        style_seccion
    ))
    story.append(Paragraph(
        f"Fuente: sjf2.scjn.gob.mx — capturas tomadas en fecha de auditoría. "
        f"Máximo {max_capturas} capturas por política Itosturre.",
        style_nota
    ))
    story.append(Spacer(1, 0.1 * inch))

    for i, reg in enumerate(registros_a_incluir, 1):
        img_path = capturas[reg]
        meta = meta_index.get(reg, {})

        rubro = meta.get("rubro", f"Tesis Registro {reg}")
        score = meta.get("score", "")
        score_str = f" — VVCA {score}" if score else ""

        story.append(Paragraph(
            f"{i}. Reg. {reg}{score_str} — {rubro[:90]}{'...' if len(rubro) > 90 else ''}",
            style_label
        ))
        story.append(Paragraph(
            f"sjf2.scjn.gob.mx/detalle/tesis/{reg}",
            style_url
        ))

        # Insertar imagen — ancho carta menos márgenes
        try:
            img = RLImage(str(img_path), width=6.5 * inch, height=4.5 * inch)
            story.append(img)
        except Exception as e:
            story.append(Paragraph(f"⚠️ Imagen no disponible: {e}", style_nota))

        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#CBD5E1")))
        story.append(Spacer(1, 0.1 * inch))

    return story


# ── CLI standalone ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    registros = sys.argv[1:] if len(sys.argv) > 1 else ["2030595"]
    print(f"📸 Capturando {len(registros)} tesis del SJF...")
    resultados = capturar_tesis(registros)
    print(f"\n✅ {len(resultados)}/{len(registros)} capturas exitosas")
    for reg, path in resultados.items():
        print(f"   {reg} → {path}")
