#!/usr/bin/env python3
"""
cotejo_manual.py — Cotejo de artículos contra el PDF oficial vigente (medida provisional).

Mientras una ley no esté 🟢 en el último reporte de vigencia, el texto que tiene el RAG puede no
ser el vigente: antes de citar un artículo suyo se coteja contra el PDF oficial. Es LECTURA de la
fuente oficial, no ingesta — no toca chroma_db/ ni corpus/.

  preparar  Baja los PDF oficiales de las fuentes no-verdes del último reporte a
            ~/itosturre-data/cotejo/<fecha del reporte>/, los valida (es PDF, sha256, texto
            extraíble, sello o decreto de la última reforma) y extrae su texto.
            Necesita PyMuPDF: córrelo con el Python del venv del proyecto.
  articulo  Ficha por artículo: lo que dice el RAG vs. el texto oficial vigente, diferencias
            palabra por palabra y notas de reforma de la propia fuente. Solo librería estándar.
  lista     Qué leyes están listas para cotejo.

La ubicación del artículo y las notas de reforma salen de la capa de evidencia
(`itosturre.evidencia.leyesbiblio.ubicar_articulo`, `itosturre.evidencia.reformas`): identificador
exacto ("1" y "1o" son distintos; las variantes cercanas se informan, nunca se eligen), zona
cuerpo/transitorios y ambigüedad sin elegir candidata.

Uso:
    "<venv>/bin/python" scripts/cotejo_manual.py preparar
    python3 scripts/cotejo_manual.py articulo LFT 47 48
    python3 scripts/cotejo_manual.py articulo "código penal para el estado" 142-A
    python3 scripts/cotejo_manual.py lista

La ficha es Capa 1 (¿el texto del RAG es el vigente?). Si la diferencia importa para el asunto es
Capa 2 y lo decide el abogado. Las fichas se guardan en <carpeta de cotejo>/fichas/.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import vigencia_corpus as vc  # noqa: E402  (mismos normalizadores, sellos y User-Agent)
from itosturre.evidencia import leyesbiblio as lb  # noqa: E402
from itosturre.evidencia import reformas as rf  # noqa: E402

REPO = vc.REPO
REPORTES = REPO / "reportes" / "vigencia_corpus"
COTEJO_BASE = Path(os.getenv("ITOS_COTEJO_DIR", str(Path.home() / "itosturre-data" / "cotejo")))

# Encabezado/pie de página de la Cámara de Diputados y prefijo de sub-chunk de la ingesta: dentro
# de los chunks indexados aparecen a media línea de texto, no al inicio de página, así que la
# limpieza por página de `leyesbiblio` no los alcanza.
RUIDO_PAGINA = re.compile(
    r"^\s*(?:C[AÁ]MARA DE DIPUTADOS DEL H\. CONGRESO DE LA UNI[OÓ]N|Secretar[ií]a General|"
    r"Secretar[ií]a de Servicios Parlamentarios|[UÚ]ltimas? Reformas? DOF\s+\d{2}-\d{2}-\d{4}|"
    r"\d+\s+de\s+\d+|\[(?:LEY|CONTRATO|RESOLUCION)[^\]]*\])\s*$",
    re.IGNORECASE,
)
# Notas del Periódico Oficial de Jalisco: "(REFORMADO, P.O. 14 DE AGOSTO DE 2003)".
NOTA_JAL = re.compile(r"\((?:REFORMAD|ADICIONAD|DEROGAD)[OA]S?\b[^)]{0,120}\)", re.IGNORECASE)
# Rótulo de división que cierra el artículo anterior: "CAPÍTULO II", "Título Primero", "Sección
# Única". Exige numeral u ordinal para no cortar en una línea que empieza con esa palabra.
DIVISION = re.compile(
    r"^\s*(?:CAP[ÍI]TULO|T[ÍI]TULO|SECCI[ÓO]N|LIBRO|Cap[íi]tulo|T[íi]tulo|Secci[óo]n|Libro)\s+"
    r"(?:[IVXLCDM]+\b|[ÚUúu]nic|Primer|Segund|Tercer|Cuart|Quint|Sext|S[ée]ptim|Octav|Noven|D[ée]cim"
    r"|PRIMER|SEGUND|TERCER|CUART|QUINT|SEXT|S[ÉE]PTIM|OCTAV|NOVEN|D[ÉE]CIM)")


# ─────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────

def ultimo_reporte(ruta: Optional[str]) -> Path:
    if ruta:
        return Path(ruta)
    reportes = sorted(REPORTES.glob("vigencia_*.json"))
    if not reportes:
        raise SystemExit("No hay reporte de vigencia: corre primero `python3 scripts/vigencia_corpus.py`.")
    return reportes[-1]


def slug(texto: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", vc.norm(texto)).strip("-")[:60] or "fuente"


def bajar_bytes(url: str) -> bytes:
    """GET binario; si urllib falla (certificados), usa curl solo por https."""
    error: object = None
    for intento in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": vc.USER_AGENT})
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except OSError as e:
            error = e
            if intento == 0:
                time.sleep(5)
    if url.startswith("https") and shutil.which("curl"):
        p = subprocess.run(["curl", "-sS", "-L", "--fail", "--proto", "=https", "--proto-redir", "=https",
                            "--max-time", "180", "-A", vc.USER_AGENT, url], capture_output=True)
        if p.returncode == 0:
            return p.stdout
        error = f"{error} · curl: {p.stderr.decode(errors='replace').strip()}"
    raise RuntimeError(f"{url}: {error}")


def ruido_repetido(paginas: List[str]) -> set:
    """Líneas presentes en ≥ 25 % de las páginas: encabezados propios de cada PDF. Las de menos
    de 15 caracteres se respetan: "I.", "II." o "Bis" se repiten sin ser encabezados."""
    total: Counter = Counter()
    for p in paginas:
        total.update({vc.norm(l) for l in p.splitlines() if 15 <= len(l.strip()) < 120})
    umbral = max(3, int(len(paginas) * 0.25))
    return {linea for linea, n in total.items() if n >= umbral}


def es_ruido(linea: str, ruido: set) -> bool:
    """Mobiliario de página que sobrevive a la limpieza de `leyesbiblio`: encabezados a media
    línea dentro de los chunks, encabezados de Jalisco o líneas repetidas en muchas páginas. Una
    nota de reforma nunca es mobiliario, aunque se repita."""
    s = linea.strip()
    if RUIDO_PAGINA.match(s):
        return True
    return vc.norm(s) in ruido and not (rf.es_inicio_nota(s) or rf.FECHA_DOF.search(s) or NOTA_JAL.search(s))


def paginas_de_txt(texto: str) -> List[str]:
    """Páginas del .txt que guarda `preparar` (marcadas con "[página N]")."""
    partes = re.split(r"^\[página \d+\]\n", texto, flags=re.MULTILINE)
    return partes[1:] if len(partes) > 1 else [texto]


def unir_chunks(chunks: List[str]) -> str:
    """Reconstruye el texto indexado: quita el prefijo "[LEY N]" de los sub-chunks y el traslape
    de ~200 caracteres que deja el splitter de respaldo de la ingesta."""
    out = ""
    for c in chunks:
        c = re.sub(r"^\[(?:LEY|CONTRATO|RESOLUCION)[^\]]*\]\s*", "", c)
        k = 0
        for n in range(min(len(out), len(c), 400), 20, -1):
            if out.endswith(c[:n]):
                k = n
                break
        out += ("\n" if out and not k else "") + c[k:]
    return out


def chunks_indexados(chroma: Path, fuente: str) -> List[str]:
    db = chroma / "chroma.sqlite3"
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)  # as_uri: también C:\ en Windows
    try:
        crudo = next((s for (s,) in con.execute(
            "SELECT DISTINCT string_value FROM embedding_metadata WHERE key='source'") if vc.nfc(s) == fuente), None)
        if crudo is None:
            return []
        filas = con.execute("""
            SELECT CAST(c.string_value AS INTEGER), d.string_value FROM embedding_metadata s
            JOIN embedding_metadata c ON c.id = s.id AND c.key = 'chunk_index'
            JOIN embedding_metadata d ON d.id = s.id AND d.key = 'chroma:document'
            WHERE s.key = 'source' AND s.string_value = ? ORDER BY 1""", (crudo,)).fetchall()
    finally:
        con.close()
    return [t or "" for _, t in filas]


# ─────────────────────────────────────────
# Ubicación y comparación (capa de evidencia)
# ─────────────────────────────────────────

def bloque_articulo(paginas: List[str], art: str, ruido: set) -> Tuple[List[str], str]:
    """(líneas del artículo, motivo si no se ubicó con certeza). Solo con una candidata única en
    el cuerpo de la ley; ambigüedad, solo-transitorios o variantes cercanas se informan sin elegir.
    El artículo termina en el siguiente encabezado de artículo, en TRANSITORIOS o en un rótulo de
    división."""
    documento = lb.limpiar_documento([p.replace("\xad", "") for p in paginas])
    try:
        ubicacion = lb.ubicar_articulo(documento, art)
    except ValueError:
        raise SystemExit(f"Número de artículo no reconocido: {art!r}")
    unica = ubicacion.unica
    if unica is None:
        if ubicacion.ambigua:
            return [], "varios encabezados candidatos en el cuerpo; no se elige ninguno"
        if ubicacion.transitorios:
            return [], "solo aparece como encabezado en transitorios"
        if ubicacion.variantes_cercanas:
            variantes = ", ".join(sorted({c.identificador for c in ubicacion.variantes_cercanas}))
            return [], f"sin encabezado exacto; variantes cercanas: {variantes}"
        return [], "sin encabezado exacto"
    lineas: List[str] = []
    anterior = ""
    for pagina, indice, linea in documento.lineas():
        previa, anterior = anterior, (linea if linea.strip() else anterior)
        if not lineas:
            if (pagina, indice) == (unica.pagina, unica.indice):
                lineas.append(linea.strip())
            continue
        if not linea.strip() or es_ruido(linea, ruido):
            continue
        # Una remisión partida ("…la parte final del" / "Artículo 1595.") no corta el artículo.
        if (lb.encabezado_en_contexto(linea, previa) or lb.es_frontera_transitorios(linea)
                or DIVISION.match(linea)):
            break
        lineas.append(linea.strip())
    return lineas, ""


def separar_notas(lineas: List[str]) -> Tuple[List[str], List[str]]:
    """(cuerpo sin notas, notas en crudo y sin repetir). Notas de la Cámara con el parser de
    `itosturre.evidencia.reformas`; las del P.O. de Jalisco, por su rótulo entre paréntesis."""
    resultado = rf.extraer_notas(lineas)
    usadas = {i for nota in resultado.notas for i in nota.lineas}
    notas = [re.sub(r"\s+", " ", nota.crudo) for nota in resultado.notas]
    cuerpo = []
    for i, linea in enumerate(lineas):
        if i in usadas:
            continue
        notas += NOTA_JAL.findall(linea)
        cuerpo.append(NOTA_JAL.sub(" ", linea))
    return cuerpo, list(dict.fromkeys(notas))


def sin_encabezado(linea: str) -> str:
    """La línea sin "Artículo N.-": el terminador ("." / ".-") cambia entre ediciones sin cambiar
    el artículo, y los dos bloques ya se ubicaron por el mismo identificador."""
    identificador = lb.encabezado_articulo(linea)
    if identificador is None:
        return linea
    return re.sub(r"^[\s.\-–—:]+", "", linea[linea.find(identificador) + len(identificador):])


def palabras(lineas: List[str]) -> List[str]:
    lineas = [sin_encabezado(lineas[0])] + lineas[1:] if lineas else []
    texto = " ".join(lineas).replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", texto).strip().split(" ") if texto.strip() else []


def ficha(fuente: str, m: dict, art: str, indexado_txt: str, oficial_txt: str) -> Tuple[str, str]:
    ruido = set(m.get("ruido", []))
    ofi_lineas, ofi_motivo = bloque_articulo(paginas_de_txt(oficial_txt), art, ruido)
    # El texto indexado entra como una sola página: los chunks ya perdieron la paginación.
    idx_lineas, idx_motivo = bloque_articulo([indexado_txt], art, ruido)
    ofi_cuerpo, ofi_notas = separar_notas(ofi_lineas)
    idx_cuerpo, idx_notas = separar_notas(idx_lineas)
    a, b = palabras(idx_cuerpo), palabras(ofi_cuerpo)
    if not b and not a:
        veredicto = f"🟡 NO LOCALIZADO en ninguno de los dos textos ({ofi_motivo})"
    elif not b:
        veredicto = f"🟡 NO LOCALIZADO en el texto oficial vigente ({ofi_motivo})"
    elif not a:
        veredicto = (f"🟡 NO LOCALIZADO en el texto indexado ({idx_motivo}): ¿adicionado después de "
                     "la versión del RAG?")
    elif a == b:
        veredicto = "🟢 COINCIDE: el texto del RAG es igual al oficial vigente"
    else:
        veredicto = "🔴 DIFIERE: el texto del RAG no es el vigente — cita el texto oficial de abajo"
    # Una nota que el texto del RAG ya trae no es novedad, aunque su fecha sea posterior al sello.
    ya_en_rag = {vc.norm(n) for n in idx_notas}
    nuevas = [n for n in ofi_notas if vc.norm(n) not in ya_en_rag]
    out = [f"## Cotejo · {m['etiqueta']} · artículo {art}", "",
           f"- **Resultado (Capa 1):** {veredicto}",
           f"- RAG: `{fuente}` · {m.get('version_indexada') or '—'}",
           f"- Oficial vigente: {m['url']} · {m.get('version_oficial') or '—'} · sha256 `{m['sha256'][:16]}…`"]
    if nuevas and a:
        out.append("- **Notas de reforma que el texto del RAG no trae:** " + "; ".join(nuevas))
    elif ofi_notas:
        out.append("- Notas de reforma en la fuente oficial: " + "; ".join(ofi_notas[:6]))
    if a and b and a != b:
        cambios = []
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
            if op != "equal":
                antes, despues = " ".join(a[i1:i2]), " ".join(b[j1:j2])
                cambios.append(f"  - {'~~' + antes + '~~' if antes else ''}{' → ' if antes and despues else ''}"
                               f"{'**' + despues + '**' if despues else ''}")
        out += ["", f"**Diferencias** (tachado = solo en el RAG; negritas = solo en el texto vigente; {len(cambios)} tramos):"]
        out += cambios[:25] + (["  - …"] if len(cambios) > 25 else [])
    if ofi_lineas:
        out += ["", "**Texto oficial vigente:**", ""] + ["> " + linea for linea in ofi_lineas]
    out += ["", "_Capa 1: dice si el texto del RAG es el vigente. Si la diferencia importa para el asunto "
                "lo decide el abogado (verifica también los transitorios)._"]
    return veredicto, "\n".join(out)


# ─────────────────────────────────────────
# preparar
# ─────────────────────────────────────────

def preparar(args) -> int:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        venv = REPO.parent / "itosturre-agente" / "venv" / "bin" / "python"
        print("❌ `preparar` necesita PyMuPDF. Córrelo con el Python del venv, p. ej.:\n"
              f'   "{venv}" scripts/cotejo_manual.py preparar', file=sys.stderr)
        return 2
    reporte = ultimo_reporte(args.reporte)
    r = json.loads(reporte.read_text(encoding="utf-8"))
    filas = [f for f in r["filas"] if f.get("url_pdf") and f["semaforo"] != vc.VERDE and f["estado"] != "NO_APLICA"]
    destino = COTEJO_BASE / r["fecha"]
    destino.mkdir(parents=True, exist_ok=True)
    previo = {}
    if (destino / "manifiesto.json").exists():
        previo = json.loads((destino / "manifiesto.json").read_text(encoding="utf-8")).get("fuentes", {})
    manifiesto: Dict[str, dict] = {}
    print(f"📥 {len(filas)} fuentes por cotejar (reporte {reporte.name}) → {destino}")
    for i, f in enumerate(filas):
        nombre = slug(f["etiqueta"])
        antes = previo.get(f["fuente"], {})
        reusar = (destino / f"{nombre}.pdf").exists() and antes.get("url") == f["url_pdf"] \
            and antes.get("descargado", "").startswith(time.strftime("%Y-%m-%d"))
        try:
            if not vc.es_fuente_oficial(f["url_pdf"]):
                raise RuntimeError(f"{f['url_pdf']} no es una URL https de un host oficial: no se descarga")
            # Mismo día y misma URL: se reutiliza lo ya bajado en vez de volver a pedirlo al portal.
            datos = (destino / f"{nombre}.pdf").read_bytes() if reusar else bajar_bytes(f["url_pdf"])
            if not datos.startswith(b"%PDF"):
                raise RuntimeError("la respuesta no es un PDF (¿portal caído o página de error?)")
            doc = fitz.open(stream=datos, filetype="pdf")
            paginas = [p.get_text() for p in doc]
            doc.close()
        except Exception as e:  # noqa: BLE001 — una fuente fallida no detiene a las demás
            manifiesto[f["fuente"]] = {"etiqueta": f["etiqueta"], "error": str(e)}
            print(f"   ❌ {f['etiqueta']}: {e}")
            continue
        (destino / f"{nombre}.pdf").write_bytes(datos)
        (destino / f"{nombre}.txt").write_text(
            "\n".join(f"[página {n}]\n{t}" for n, t in enumerate(paginas, 1)), encoding="utf-8")
        texto = "\n".join(paginas)
        # ¿El PDF descargado ya refleja la última modificación que anuncia el listado?
        sello = vc.SELLO_FED.search(paginas[0][:1500]) if paginas else None
        evidencia, confirma = "", None
        if sello:
            fe = vc.fecha(sello.group("y"), sello.group("m"), sello.group("d"))
            evidencia = re.sub(r"\s+", " ", sello.group(0))
            confirma = bool(fe and f.get("fecha_oficial") and fe.isoformat() >= f["fecha_oficial"])
        else:
            # Jalisco: el instrumento va después del "·" ("P.O. 18/06/2026 · decreto 30196"); la
            # fecha de antes no cuenta. Un PDF al día debe citar ese decreto o resolución.
            instrumento = f.get("version_oficial", "").split("·", 1)[-1]
            decreto = re.search(r"decreto (\d{4,5})", instrumento)
            resolucion = vc.RESOLUCION_SCJN.search(instrumento)
            if decreto:
                confirma = decreto.group(1) in vc.DECRETO_JAL.findall(texto)
                evidencia = f"{'cita' if confirma else 'no cita'} el decreto {decreto.group(1)}"
            elif resolucion:
                confirma = resolucion.group(1) in vc.RESOLUCION_SCJN.findall(texto)
                evidencia = f"{'cita' if confirma else 'no cita'} la resolución {resolucion.group(1)}"
        con_texto = sum(1 for t in paginas if t.strip())
        manifiesto[f["fuente"]] = {
            "etiqueta": f["etiqueta"], "nombre_oficial": f.get("nombre_oficial", ""), "tipo": f["tipo"],
            "pdf": f"{nombre}.pdf", "txt": f"{nombre}.txt", "url": f["url_pdf"],
            "sha256": hashlib.sha256(datos).hexdigest(), "bytes": len(datos),
            "paginas": len(paginas), "paginas_con_texto": con_texto,
            "version_indexada": f.get("version_indexada", ""), "fecha_indexada": f.get("fecha_indexada"),
            "version_oficial": f.get("version_oficial", ""), "evidencia_pdf": evidencia,
            "pdf_refleja_ultima_reforma": confirma, "ruido": sorted(ruido_repetido(paginas)),
            "descargado": time.strftime("%Y-%m-%d %H:%M"),
        }
        marca = "✅" if confirma else ("⚠️ " if confirma is False else "·")
        print(f"   {marca} {f['etiqueta'][:60]:60} {len(paginas):4} pág ({con_texto} con texto) · {evidencia}")
        if i < len(filas) - 1 and not reusar:
            time.sleep(1.5)  # no saturar los portales
    (destino / "manifiesto.json").write_text(json.dumps(
        {"reporte": str(reporte), "chroma": r["chroma"], "fuentes": manifiesto}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    dudosos = [m["etiqueta"] for m in manifiesto.values() if m.get("pdf_refleja_ultima_reforma") is False or "error" in m]
    print(f"📄 Manifiesto: {destino / 'manifiesto.json'}")
    if dudosos:
        print("⚠️  Revisa a mano (el PDF no confirma la última reforma del listado, o falló):", ", ".join(dudosos))
    return 1 if dudosos else 0


# ─────────────────────────────────────────
# articulo · lista
# ─────────────────────────────────────────

def ultimo_cotejo() -> Tuple[Path, dict]:
    carpetas = sorted(p for p in COTEJO_BASE.glob("*") if (p / "manifiesto.json").exists()) if COTEJO_BASE.exists() else []
    if not carpetas:
        raise SystemExit("No hay cotejo preparado: corre primero `cotejo_manual.py preparar` con el Python del venv.")
    return carpetas[-1], json.loads((carpetas[-1] / "manifiesto.json").read_text(encoding="utf-8"))


def buscar_ley(manifiesto: dict, consulta: str) -> Tuple[str, dict]:
    q = vc.norm(consulta)
    candidatos = [(fuente, m) for fuente, m in manifiesto["fuentes"].items() if "error" not in m and (
        vc.norm(m["etiqueta"]) == q or q in vc.norm(fuente) or q in vc.norm(m.get("nombre_oficial", "")))]
    exactos = [c for c in candidatos if vc.norm(c[1]["etiqueta"]) == q]
    elegidos = exactos or candidatos
    if len(elegidos) != 1:
        opciones = ", ".join(m["etiqueta"] for _, m in (elegidos or manifiesto["fuentes"].items()))
        raise SystemExit(f"«{consulta}» {'es ambiguo' if elegidos else 'no está en el cotejo'}. Opciones: {opciones}")
    return elegidos[0]


def articulo(args) -> int:
    destino, manifiesto = ultimo_cotejo()
    fuente, m = buscar_ley(manifiesto, args.ley)
    chroma = Path(args.chroma or os.getenv("CHROMA_PATH") or manifiesto["chroma"]).expanduser()
    indexado = unir_chunks(chunks_indexados(chroma, fuente))
    oficial = (destino / m["txt"]).read_text(encoding="utf-8")
    (destino / "fichas").mkdir(exist_ok=True)
    peor = 0
    for art in args.articulos:
        veredicto, texto = ficha(fuente, m, art, indexado, oficial)
        archivo = destino / "fichas" / f"{slug(m['etiqueta'])}_art{slug(art)}.md"
        archivo.write_text(texto + "\n", encoding="utf-8")
        print(texto, f"\n📄 {archivo}\n", sep="\n")
        peor = max(peor, 1 if veredicto.startswith("🔴") else (2 if veredicto.startswith("🟡") else 0))
    return peor


def lista(_args) -> int:
    destino, manifiesto = ultimo_cotejo()
    print(f"📚 Cotejo preparado en {destino}")
    for fuente, m in manifiesto["fuentes"].items():
        estado = "❌ " + m["error"] if "error" in m else (
            "✅ PDF confirma la última reforma" if m.get("pdf_refleja_ultima_reforma") else "⚠️  revisar PDF")
        print(f"   {m['etiqueta'][:60]:60} {estado}")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    vc.cargar_env(REPO)
    ap = argparse.ArgumentParser(description="Cotejo de artículos contra el PDF oficial vigente.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("preparar", help="baja y valida los PDF oficiales de las fuentes no-verdes")
    p.add_argument("--reporte", help="vigencia_*.json a usar (default: el más reciente)")
    p.set_defaults(fn=preparar)
    a = sub.add_parser("articulo", help="ficha: texto del RAG vs. texto oficial vigente")
    a.add_argument("ley", help="clave (LFT, CPEUM…) o parte del nombre de la ley")
    a.add_argument("articulos", nargs="+", help="identificadores exactos (47, 1o, 142-A, 123 Bis…)")
    a.add_argument("--chroma", help="índice a leer (default: CHROMA_PATH o el del reporte)")
    a.set_defaults(fn=articulo)
    sub.add_parser("lista", help="leyes listas para cotejo").set_defaults(fn=lista)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
