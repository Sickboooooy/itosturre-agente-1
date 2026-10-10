#!/usr/bin/env python3
"""
vigencia_corpus.py — ¿Sigue vigente el corpus legal que alimenta a OpenNotebook.py?

Coteja la versión de cada ordenamiento INDEXADO en ChromaDB contra la versión que publica
hoy la fuente oficial y da un semáforo por fuente. No se promedia: basta una fuente
desactualizada para que el corpus no esté vigente.

  Federal → Cámara de Diputados (LeyesBiblio). Indexada = sello del encabezado del PDF
            ("Última Reforma DOF dd-mm-aaaa", "Nueva Ley DOF …"). Oficial = "Última reforma"
            del índice de leyes / reglamentos vigentes. Confianza alta.
  Jalisco → Congreso del Estado (Biblioteca Virtual). Indexada = fecha más reciente de la
            tabla de reformas al final del PDF ("Ene. 25 de 2020 sec. VI"). Oficial = fecha
            de última reforma del listado. Confianza media: la fecha indexada es inferida.
  Tratados y documentos sin fuente automatizable → ⚪ / 🟡 revisión manual.

También detecta fuentes del manifiesto sin indexar, fuentes indexadas sin manifiesto,
contenido duplicado entre fuentes, títulos que no corresponden a la ley esperada y PDFs en
disco más nuevos que su indexación (re-ingesta pendiente).

Solo usa la librería estándar y la capa de evidencia del repo (corre con cualquier
python3 ≥ 3.11, sin venv ni modelo e5) y lee chroma.sqlite3 en modo solo lectura, sin importar
OpenNotebook. NO descarga leyes ni re-indexa: la ingesta es una acción explícita del abogado
(CLAUDE.md). Solo hace GET públicos a URL https de hosts oficiales; no envía datos del corpus
ni de clientes (regla 9).

Uso:
    python3 scripts/vigencia_corpus.py                        # verifica + reporte
    python3 scripts/vigencia_corpus.py --json                 # resultado JSON en stdout
    python3 scripts/vigencia_corpus.py --si-toca --notificar  # modo agenda (launchd)
    CHROMA_PATH=/ruta/chroma_db python3 scripts/vigencia_corpus.py

Reporte: reportes/vigencia_corpus/vigencia_AAAA-MM-DD.{md,json} + estado.json del ciclo.
Agenda bimestral (macOS): bash scripts/instalar_vigencia_corpus.sh
Salida: 0 = todo cotejado y nada desactualizado · 1 = hay desactualizadas ·
        2 = no se pudo verificar (todo o en parte) y no se halló ninguna desactualizada.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from itosturre.evidencia.fuentes import HOSTS_OFICIALES, url_oficial  # noqa: E402  (stdlib puro)

COLLECTION_NAME = "corpus_legal_itosturre"  # la misma colección de OpenNotebook.py

# Fuentes oficiales. El entorno del proceso puede sobrescribirlas, pero solo se consulta una URL
# https cuyo host es oficial (`es_fuente_oficial`): cualquier otra deja la fila en 🟡 NO
# VERIFICABLE y nunca acredita vigencia. El .env no las sobrescribe: se carga después.
URL_LEYES_FED = os.getenv("ITOS_URL_LEYES_FED", "https://www.diputados.gob.mx/LeyesBiblio/index.htm")
URL_REGLAMENTOS_FED = os.getenv("ITOS_URL_REGLAMENTOS_FED", "https://www.diputados.gob.mx/LeyesBiblio/regla.htm")
URL_JALISCO = os.getenv(
    "ITOS_URL_JALISCO",
    "https://congresoweb.congresojal.gob.mx/BibliotecaVirtual/busquedasleyes/Listado%272.cfm",
)
USER_AGENT = "Mozilla/5.0 (Macintosh) Itosturre-vigencia-corpus/1.0"
# Los hosts oficiales de la capa de evidencia más el del Congreso de Jalisco, que publica el
# listado estatal y sus PDF.
HOSTS_VIGENCIA = HOSTS_OFICIALES | {"congresoweb.congresojal.gob.mx"}

# La tabla de reformas de los PDFs de Jalisco vive al final del documento. Buscar fechas en
# todo el texto arriesga tomar las de transitorios o artículos y fabricar un falso 🟢, que
# es peor que un falso 🔴: haría citar como vigente un texto viejo.
FRACCION_COLA = 0.25
# Una fecha de la tabla anterior a la Constitución vigente no es una reforma que cuente (cita
# histórica o error de OCR).
FECHA_MINIMA_TABLA = dt.date(1917, 1, 1)
DIAS_ENTRE_AVISOS_DE_FALLO = 7

VERDE, AMARILLO, ROJO, BLANCO = "🟢", "🟡", "🔴", "⚪"
SEMAFORO = {
    "VIGENTE": VERDE, "DESACTUALIZADA": ROJO, "ABROGADA": AMARILLO, "NO_VERIFICABLE": AMARILLO,
    "NO_INDEXADA": AMARILLO, "MANUAL": AMARILLO, "DESCARTADA": AMARILLO, "NO_APLICA": BLANCO,
}
PAGINAS = {
    "federal": ("Cámara de Diputados · leyes (LeyesBiblio)", URL_LEYES_FED),
    "federal_reglamento": ("Cámara de Diputados · reglamentos (LeyesBiblio)", URL_REGLAMENTOS_FED),
    "jalisco": ("Congreso del Estado de Jalisco · Biblioteca Virtual", URL_JALISCO),
}

# Sello del encabezado de los PDFs de la Cámara de Diputados (queda en el chunk 0).
SELLO_FED = re.compile(
    r"(?P<tipo>[UÚ]ltima\s+Reforma|Nuev[oa]\s+(?:Ley|C[oó]digo|Reglamento|Estatuto|Decreto)"
    r"|(?:C[oó]digo|Ley|Reglamento|Estatuto)\s+Abrogad[oa])\s+DOF\s+"
    r"(?P<d>\d{1,2})-(?P<m>\d{1,2})-(?P<y>\d{4})",
    re.IGNORECASE,
)
# Encabezado de algunos PDFs del Congreso de Jalisco.
SELLO_JAL = re.compile(
    r"[UÚ]LTIMA\s+REFORMA\s+PUBLICADA\s+EN\s+EL\s+PERI[OÓ]DICO\s+OFICIAL\s*:?\s*"
    r"(?P<d>\d{1,2})\s+DE\s+(?P<mes>[A-Za-zÁÉÍÓÚáéíóú]+)\s+DEL?\s+(?P<y>\d{4})",
    re.IGNORECASE,
)
# Fecha abreviada del Periódico Oficial en la tabla de reformas: "Ene. 25 de 2020 sec. VI".
FECHA_TABLA = re.compile(
    r"\b(?P<mes>Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sept?|Oct|Nov|Dic)\s*\.?\s*"
    r"(?P<d>\d{1,2})\s+de\s+(?P<y>\d{4})\b",
    re.IGNORECASE,
)
# Número de decreto del Congreso de Jalisco: "27392/LXII/19" (número/legislatura/año).
DECRETO_JAL = re.compile(r"\b(\d{4,5})/L[XVI]{1,6}/\d{2}\b")
# Resoluciones de la SCJN que modifican el texto sin ser reforma: "A.I. 48/2026",
# "Declaratoria General de Inconstitucionalidad 9/2022" (número/año).
RESOLUCION_SCJN = re.compile(r"(?:[Ii]nconstitucionalidad|\bA\.\s?I\.)\D{0,40}?\b(\d{1,4}/\d{4})\b")
# Una fuente se indexa en minutos (el corpus completo, en ~50): chunks de la misma fuente con
# más separación vienen de corridas distintas — p. ej. PDF reemplazado + `ingest` normal, que
# deja el articulado viejo y solo añade la cola nueva (con la tabla de reformas al día).
MAX_SPREAD_INDEXACION = dt.timedelta(hours=2)
FECHA_DMY = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8,
         "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12}


# ─────────────────────────────────────────
# Utilidades
# ─────────────────────────────────────────

def cargar_env(repo: Path) -> None:
    """Carga <repo>/.env sin pisar el entorno, como el load_dotenv() de OpenNotebook.py."""
    archivo = repo / ".env"
    if not archivo.exists():
        return
    for linea in archivo.read_text(encoding="utf-8", errors="replace").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        clave = clave.strip().removeprefix("export ").strip()
        os.environ.setdefault(clave, valor.strip().strip('"').strip("'"))


def nfc(texto: str) -> str:
    # macOS puede guardar nombres de archivo en NFD; el manifiesto está en NFC.
    return unicodedata.normalize("NFC", texto)


def norm(texto: str) -> str:
    """Para comparar nombres: sin acentos ni mayúsculas, espacios colapsados."""
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texto).strip().lower()


def fecha(y, m, d) -> Optional[dt.date]:
    try:
        return dt.date(int(y), int(m), int(d))
    except (TypeError, ValueError):
        return None


def mes_num(texto: str) -> Optional[int]:
    return MESES.get(norm(texto)[:3])


def fechas_dmy(texto: str) -> List[dt.date]:
    return [f for f in (fecha(y, m, d) for d, m, y in FECHA_DMY.findall(texto)) if f]


def dmy(f: Optional[dt.date], sep: str = "/") -> str:
    return f.strftime(f"%d{sep}%m{sep}%Y") if f else "—"


def limpiar(fragmento: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragmento))).strip()


def decodificar(datos: bytes) -> str:
    # Ambos portales sirven ISO-8859-1; si algún día pasan a UTF-8, se detecta solo.
    try:
        return datos.decode("utf-8")
    except UnicodeDecodeError:
        return datos.decode("cp1252", errors="replace")


def descargar(url: str) -> str:
    """GET con reintentos; si urllib falla (p. ej. certificados del Python de python.org), usa curl."""
    error: object = None
    for intento in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return decodificar(resp.read())
        except (urllib.error.URLError, OSError, ValueError) as e:
            error = e
            if intento == 0:
                time.sleep(5)
    if url.startswith("http") and shutil.which("curl"):
        try:
            p = subprocess.run(
                ["curl", "-sS", "-L", "--fail", "--proto", "=https", "--proto-redir", "=https",
                 "--max-time", "90", "-A", USER_AGENT, url],
                capture_output=True, check=True,
            )
            return decodificar(p.stdout)
        except subprocess.CalledProcessError as e:
            error = f"{error} · curl: {e.stderr.decode(errors='replace').strip()}"
    raise RuntimeError(f"{url}: {error}")


# ─────────────────────────────────────────
# Lo que dice el índice (ChromaDB)
# ─────────────────────────────────────────

def leer_indice(chroma_path: Path) -> Dict[str, dict]:
    """Por fuente: nº de chunks, fecha de indexación, texto del chunk 0 y fecha máxima de la
    tabla de reformas. Lee sqlite directo (como check_corpus.py), en solo lectura: no carga
    el modelo e5 ni estorba a una ingesta en curso."""
    db = chroma_path / "chroma.sqlite3"
    if not db.exists():
        raise FileNotFoundError(f"no existe {db} (¿CHROMA_PATH correcto? ¿corriste el bootstrap?)")
    con = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)  # as_uri: también C:\ en Windows
    base = """
        SELECT s.string_value, c.string_value, d.string_value, e.created_at
        FROM embeddings e
        JOIN embedding_metadata s ON s.id = e.id AND s.key = 'source'
        LEFT JOIN embedding_metadata c ON c.id = e.id AND c.key = 'chunk_index'
        LEFT JOIN embedding_metadata d ON d.id = e.id AND d.key = 'chroma:document'
    """
    try:
        try:
            filas = con.execute(
                base + """
                JOIN segments sg ON sg.id = e.segment_id
                JOIN collections col ON col.id = sg.collection
                WHERE col.name = ?""",
                (COLLECTION_NAME,),
            ).fetchall()
        except sqlite3.OperationalError as e:
            # Solo un esquema distinto de Chroma justifica leer sin filtro por colección (como
            # check_corpus.py); "database is locked" y similares son fallas reales.
            if "no such" not in str(e):
                raise
            filas = con.execute(base).fetchall()
    finally:
        con.close()

    fuentes: Dict[str, dict] = {}
    for source, idx, doc, creado in filas:
        if not source:
            continue
        f = fuentes.setdefault(nfc(source), {"chunks": 0, "indexado_utc": "", "indexado_min_utc": "",
                                             "chunk0": "", "tabla": [], "decretos": set(),
                                             "resoluciones": set()})
        f["chunks"] += 1
        if creado and str(creado) > f["indexado_utc"]:
            f["indexado_utc"] = str(creado)
        if creado and (not f["indexado_min_utc"] or str(creado) < f["indexado_min_utc"]):
            f["indexado_min_utc"] = str(creado)
        try:
            i = int(idx)
        except (TypeError, ValueError):
            continue
        doc = doc or ""
        if i == 0:
            f["chunk0"] = doc
        for m in FECHA_TABLA.finditer(doc):
            fe = fecha(m.group("y"), mes_num(m.group("mes")), m.group("d"))
            if fe:
                f["tabla"].append((i, fe))
        f["decretos"].update(DECRETO_JAL.findall(doc))
        f["resoluciones"].update(RESOLUCION_SCJN.findall(doc))

    hoy = dt.date.today()
    for f in fuentes.values():
        corte = int(f["chunks"] * (1 - FRACCION_COLA))
        validas = [fe for i, fe in f.pop("tabla") if i >= corte and FECHA_MINIMA_TABLA <= fe <= hoy]
        f["tabla_max"] = max(validas) if validas else None
        inicio, fin = utc(f["indexado_min_utc"]), utc(f["indexado_utc"])
        f["mixta"] = bool(inicio and fin and fin - inicio > MAX_SPREAD_INDEXACION)
    return fuentes


def utc(texto: str) -> Optional[dt.datetime]:
    """created_at de Chroma ("AAAA-MM-DD HH:MM:SS", UTC) → datetime con zona."""
    try:
        return dt.datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def version_indexada(info: dict, tipo: str) -> Tuple[Optional[dt.date], str, str, str]:
    """(fecha, texto, clase, confianza) de la versión indexada. clase: reforma|original|abrogado|tabla."""
    cabecera = info.get("chunk0", "")[:1500]
    if tipo.startswith("federal"):
        m = SELLO_FED.search(cabecera)
        if not m:
            return None, "", "", ""
        t = m.group("tipo").lower()
        clase = "abrogado" if "abrogad" in t else ("reforma" if "reforma" in t else "original")
        return (fecha(m.group("y"), m.group("m"), m.group("d")),
                re.sub(r"\s+", " ", m.group(0)), clase, "alta")
    # Jalisco: sello explícito del encabezado (alta) o tabla de reformas (media, inferida).
    candidatos = []
    m = SELLO_JAL.search(cabecera)
    if m and mes_num(m.group("mes")):
        fe = fecha(m.group("y"), mes_num(m.group("mes")), m.group("d"))
        if fe:
            candidatos.append((fe, f"Última reforma en el P.O. {dmy(fe, '-')}", "alta"))
    if info.get("tabla_max"):
        candidatos.append((info["tabla_max"], f"Tabla de reformas: {dmy(info['tabla_max'], '-')}", "media"))
    if not candidatos:
        return None, "", "", ""
    fe, texto, confianza = max(candidatos)
    return fe, texto, "tabla", confianza


def titulo_indexado(chunk0: str) -> str:
    """Título de un PDF de la Cámara de Diputados: lo que precede a 'CÁMARA DE DIPUTADOS'."""
    m = re.search(r"C[AÁ]MARA\s+DE\s+DIPUTADOS", chunk0, re.IGNORECASE)
    return re.sub(r"\s+", " ", chunk0[: m.start()]).strip() if m else ""


def mismo_ordenamiento(titulo: str, oficial: str) -> bool:
    a, b = norm(titulo), norm(oficial)
    return a == b or a.startswith(b) or b.startswith(a)


# ─────────────────────────────────────────
# Lo que dice la fuente oficial
# ─────────────────────────────────────────

def parse_leyesbiblio(texto: str, base: str, pagina: str) -> Dict[str, dict]:
    """Índice de LeyesBiblio → {clave del PDF: datos}. pagina: 'leyes' (index.htm) o 'reglamentos'."""
    filas: Dict[str, dict] = {}
    for tr in re.split(r"<tr[\s>]", texto, flags=re.IGNORECASE)[1:]:
        pdf = re.search(r'href="([^"]*?([^"/]+)\.pdf)"', tr, re.IGNORECASE)
        celdas = [limpiar(c) for c in re.findall(r"<td[^>]*>(.*?)(?=<td|</tr|$)", tr, re.I | re.S)]
        if not pdf or len(celdas) < 3:
            continue
        celda_nombre = celdas[1]
        nombre = re.split(r"\s+(?:DOF\s|\(\s*Antes|\(\s*Abrogad|Nueva reforma|Original\b)",
                          celda_nombre, maxsplit=1)[0].strip()
        if pagina == "leyes":
            publicacion = (fechas_dmy(celda_nombre) or [None])[0]
            ultima = (fechas_dmy(celdas[2]) or [None])[0]
            ultima_txt = celdas[2]
        else:  # reglamentos: "Original DOF dd/mm/aaaa" · "Reformas DOF a, b, …"
            original = re.search(r"Original\s*(?:DOF)?\s*(\d{1,2}/\d{1,2}/\d{4})", celda_nombre)
            publicacion = (fechas_dmy(original.group(1)) or [None])[0] if original else None
            reformas = fechas_dmy(celda_nombre.split("Reformas", 1)[1]) if "Reformas" in celda_nombre else []
            ultima = max(reformas) if reformas else None
            ultima_txt = f"DOF {dmy(ultima)}" if ultima else "Sin reforma"
        if not ultima and publicacion:
            ultima_txt = f"Sin reforma (publicación DOF {dmy(publicacion)})"
        abrogado = re.search(r"\(\s*Abrogad[^)]*\)?", celda_nombre, re.IGNORECASE)
        historial = re.search(r'href="(ref/[^"]+)"', tr, re.IGNORECASE)
        filas.setdefault(pdf.group(2), {
            "nombre": nombre,
            "ultima": ultima or publicacion,  # "Sin reforma" → cuenta la publicación original
            "ultima_txt": ultima_txt,
            "abrogado": abrogado.group(0).strip() if abrogado else "",
            "url_pdf": urllib.parse.urljoin(base, pdf.group(1)),
            "url_historial": urllib.parse.urljoin(base, historial.group(1)) if historial else "",
        })
    return filas


def parse_jalisco(texto: str, base: str) -> Dict[str, dict]:
    """Listado de la Biblioteca Virtual del Congreso de Jalisco → {nombre normalizado: datos}."""
    filas: Dict[str, dict] = {}
    for m in re.finditer(r'<td class="leyreg"[^>]*>(.*?)</td>(.*?)</tr>', texto, re.I | re.S):
        nombre = limpiar(m.group(1))
        celdas = [limpiar(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", m.group(2), re.I | re.S)]
        fechas = [f for c in celdas for f in fechas_dmy(c)]
        if not nombre or not fechas:
            continue
        instrumento = celdas[-1] if celdas and not fechas_dmy(celdas[-1]) else ""
        decreto = instrumento if instrumento.isdigit() else ""
        if decreto:
            instrumento = f"decreto {decreto}"
        resolucion = RESOLUCION_SCJN.search(instrumento)
        url = ""
        pdf = re.search(r'href="([^"]+\.pdf)"', m.group(2), re.IGNORECASE)
        if pdf:
            p = urllib.parse.urlsplit(urllib.parse.urljoin(base, html.unescape(pdf.group(1))))
            url = urllib.parse.urlunsplit((p.scheme, p.netloc, urllib.parse.quote(p.path, safe="/%"), p.query, ""))
        filas.setdefault(norm(nombre), {
            "nombre": nombre,
            "ultima": fechas[0],
            "ultima_txt": f"P.O. {dmy(fechas[0])}" + (f" · {instrumento}" if instrumento else ""),
            "decreto": decreto,  # número del decreto de la última reforma (si el listado lo da)
            "resolucion": resolucion.group(1) if resolucion else "",  # A.I. / declaratoria "N/AAAA"
            "url_pdf": url,
        })
    return filas


def es_fuente_oficial(url: str) -> bool:
    """https, sin credenciales ni puerto raro y host oficial exacto (`itosturre.evidencia.fuentes`)."""
    return url_oficial(url, hosts=HOSTS_VIGENCIA)


def consultar_oficiales(tipos: set) -> Tuple[Dict[str, dict], Dict[str, str]]:
    """Descarga solo las páginas que el manifiesto necesita. Devuelve (datos, errores) por tipo."""
    datos: Dict[str, dict] = {}
    errores: Dict[str, str] = {}
    for tipo in ("federal", "federal_reglamento", "jalisco"):
        if tipo not in tipos:
            continue
        url = PAGINAS[tipo][1]
        try:
            if not es_fuente_oficial(url):
                raise RuntimeError(f"{url} no es una URL https de un host oficial: no se consulta")
            texto = descargar(url)
            if tipo == "jalisco":
                datos[tipo] = parse_jalisco(texto, url)
            else:
                datos[tipo] = parse_leyesbiblio(texto, url, "leyes" if tipo == "federal" else "reglamentos")
            if not datos[tipo]:
                # Página caída o rediseñada: nunca disfrazar un resultado vacío de "sin hallazgos".
                raise RuntimeError(f"{url}: la página no trajo filas reconocibles (¿cambió el formato?)")
        except Exception as e:  # noqa: BLE001 — cualquier falla de red/parseo deja 🟡, no aborta
            datos.pop(tipo, None)
            errores[tipo] = str(e)
    return datos, errores


# ─────────────────────────────────────────
# Cotejo
# ─────────────────────────────────────────

def clasificar(fuente: str, info: Optional[dict], entrada: dict,
               oficiales: Dict[str, dict], errores: Dict[str, str]) -> dict:
    tipo = entrada.get("tipo", "sin_manifiesto")
    fila = {
        "fuente": fuente, "tipo": tipo,
        "etiqueta": entrada.get("clave") or entrada.get("nombre_oficial") or fuente,
        "nombre_oficial": entrada.get("nombre_oficial", ""),
        "estado": "", "detalle": "",
        "version_indexada": "", "fecha_indexada": None,
        "version_oficial": "", "fecha_oficial": None,
        "rezago_dias": None, "confianza": "",
        "indexado_el": info["indexado_utc"][:10] if info else None,
        "chunks": info["chunks"] if info else 0,
        "url_pdf": "", "url_historial": "",
        "identidad_confirmada": False,  # el título indexado coincide con el nombre oficial
        "notas": [entrada["nota"]] if entrada.get("nota") else [],
        "alertas": [],
    }

    def cerrar(estado: str, detalle: str = "") -> dict:
        fila["estado"], fila["detalle"] = estado, detalle
        return fila

    if tipo == "descartado":
        # Retirada del corpus: sus chunks siguen en el índice hasta que se reconstruya (la
        # re-ingesta por fuente reemplaza fragmentos; no borra una fuente).
        if info is None:
            return cerrar("NO_APLICA", "Descartada; ya no está en el índice.")
        return cerrar("DESCARTADA", "Retirada del corpus, pero sigue en el índice hasta que se "
                                    "reconstruya: no la cites.")
    if info is None:
        return cerrar("NO_INDEXADA", "Está en el manifiesto pero no tiene chunks en el índice.")
    if tipo == "tratado":
        return cerrar("NO_APLICA", "Tratado internacional: sin sello de última reforma que cotejar; su situación "
                                   "para México (reservas, declaraciones, denuncia) se revisa a mano.")
    if tipo == "manual":
        return cerrar("MANUAL", "Sin fuente oficial automatizable: revisión manual.")
    if tipo not in PAGINAS:
        return cerrar("NO_VERIFICABLE", "Sin entrada en scripts/fuentes_oficiales.json: agrégala para cotejarla.")
    if tipo in errores:
        return cerrar("NO_VERIFICABLE", f"No se pudo consultar {PAGINAS[tipo][0]}.")

    tabla = oficiales[tipo]
    if tipo == "jalisco" or tipo == "federal_reglamento":
        clave_busqueda = norm(entrada.get("nombre_oficial", ""))
        if tipo == "federal_reglamento":
            oficial = next((v for v in tabla.values() if norm(v["nombre"]) == clave_busqueda), None)
        else:
            oficial = tabla.get(clave_busqueda)
    else:
        oficial = tabla.get(entrada.get("clave", ""))
    if not oficial:
        return cerrar("NO_VERIFICABLE", "No aparece en la fuente oficial con esa clave o nombre "
                                        "(¿abrogada o renombrada? Revisa el manifiesto).")

    fila["nombre_oficial"] = oficial["nombre"]
    fila["version_oficial"] = oficial["ultima_txt"]
    fila["fecha_oficial"] = oficial["ultima"]
    fila["url_pdf"] = oficial.get("url_pdf", "")
    fila["url_historial"] = oficial.get("url_historial", "")

    fe_idx, txt_idx, clase, confianza = version_indexada(info, tipo)
    fila["version_indexada"], fila["fecha_indexada"], fila["confianza"] = txt_idx, fe_idx, confianza

    if tipo.startswith("federal"):
        titulo = titulo_indexado(info.get("chunk0", ""))
        if titulo and mismo_ordenamiento(titulo, oficial["nombre"]):
            fila["identidad_confirmada"] = True
        elif titulo:
            # Comparar fechas de dos ordenamientos distintos daría un 🔴/🟢 sin sentido.
            return cerrar("NO_VERIFICABLE", f"El texto indexado se titula «{titulo}», no «{oficial['nombre']}»: "
                                            "¿PDF equivocado o clave mal puesta en el manifiesto?")

    if oficial.get("abrogado") or clase == "abrogado":
        nota = oficial.get("abrogado") or txt_idx
        return cerrar("ABROGADA", f"Abrogada con vigencia transitoria según la fuente oficial: {nota}. "
                                  "Verifica el régimen transitorio y si el PDF incluye la última modificación.")
    if info.get("mixta"):
        fila["alertas"].append(
            f"Indexación mixta: los chunks de esta fuente vienen de corridas distintas "
            f"({info['indexado_min_utc'][:16]} → {info['indexado_utc'][:16]} UTC); el articulado puede ser de "
            "otra versión que su encabezado o su tabla de reformas. Re-ingesta esa fuente con "
            f"`OpenNotebook.py ingest --fuente \"{fuente}\"` (ver «Cómo actualizar»).")

    # Jalisco: segunda señal, independiente de la fecha inferida — ¿el texto indexado cita el
    # instrumento de la última modificación oficial (decreto, o A.I./declaratoria de la SCJN)?
    # Un PDF no puede citar un instrumento posterior a él. Si ambas señales coinciden la
    # confianza es alta; si se contradicen queda 🟡 en vez de arriesgar un 🔴 o un 🟢 falsos.
    if oficial.get("decreto"):
        instrumento = f"el decreto {oficial['decreto']}"
        incluye: Optional[bool] = oficial["decreto"] in info.get("decretos", set())
    elif oficial.get("resolucion"):
        instrumento = f"la resolución {oficial['resolucion']}"
        incluye = oficial["resolucion"] in info.get("resoluciones", set())
    else:
        instrumento, incluye = "", None
    if incluye is not None:
        fila["version_indexada"] = (f"{txt_idx} · " if txt_idx else "") + \
            ("cita " if incluye else "no cita ") + instrumento
        desfase = fe_idx is not None and oficial["ultima"] is not None and oficial["ultima"] > fe_idx
        fila["confianza"] = "alta" if incluye or desfase else "media"

    def vigente() -> dict:
        # Un índice mixto puede traer la tabla de reformas nueva con el articulado viejo.
        if info.get("mixta"):
            return cerrar("NO_VERIFICABLE", "La versión indexada parece al día, pero la indexación es mixta: "
                                            "no se puede afirmar que el articulado sea el vigente.")
        return cerrar("VIGENTE")

    if fe_idx is None:
        if incluye:
            return vigente()
        return cerrar("NO_VERIFICABLE", "El PDF indexado no trae sello ni tabla de reformas de donde leer su versión.")
    if oficial["ultima"] is None:
        return cerrar("NO_VERIFICABLE", "La fuente oficial no muestra fecha de última reforma.")
    if oficial["ultima"] > fe_idx:
        if incluye:
            return cerrar("NO_VERIFICABLE", f"Evidencia contradictoria: la tabla de reformas indexada llega a "
                                            f"{dmy(fe_idx)}, pero el texto sí cita {instrumento} de la última "
                                            "modificación oficial. Revísalo a mano.")
        fila["rezago_dias"] = (oficial["ultima"] - fe_idx).days
        return cerrar("DESACTUALIZADA", "La fuente oficial publicó una versión posterior a la indexada; "
                                        "verifica en los transitorios desde cuándo rige.")
    if oficial["ultima"] < fe_idx and not incluye:
        # La versión oficial no puede ser más vieja que nuestra copia: portal rediseñado (columna
        # equivocada) o desfase entre el listado y el PDF. Nunca dar 🟢 sobre esa base.
        return cerrar("NO_VERIFICABLE", f"La versión indexada ({dmy(fe_idx)}) aparenta ser posterior a la "
                                        f"oficial ({dmy(oficial['ultima'])}): ¿cambió el formato del portal?")
    return vigente()


def verificar(chroma: Path, corpus: Path, manifiesto: dict) -> dict:
    ahora = dt.datetime.now()
    resultado = {
        "fecha": ahora.date().isoformat(), "hora": ahora.strftime("%H:%M"),
        "chroma": str(chroma), "corpus": str(corpus),
        "estado_corrida": "fallida", "error": "", "fuentes_oficiales": {},
        # "No pude verificar" no es "está desactualizado" (CLAUDE.md, regla 7): 🟡, nunca 🔴.
        "filas": [], "veredicto": AMARILLO, "razon": "",
    }
    try:
        indice = leer_indice(chroma)
    except Exception as e:  # noqa: BLE001
        resultado["error"] = f"No se pudo leer el índice: {e}"
        resultado["razon"] = "NO SE PUDO VERIFICAR — " + resultado["error"]
        return resultado
    if not indice:
        resultado["error"] = f"El índice {chroma} está vacío (colección {COLLECTION_NAME})."
        resultado["razon"] = "NO SE PUDO VERIFICAR — " + resultado["error"]
        return resultado

    fuentes_manif = {nfc(k): v for k, v in manifiesto.get("fuentes", {}).items()}
    tipos = {fuentes_manif[f]["tipo"] for f in indice if f in fuentes_manif}
    oficiales, errores = consultar_oficiales(tipos)
    for tipo in sorted(tipos & set(PAGINAS)):
        nombre, url = PAGINAS[tipo]
        # La URL efectiva queda en el reporte: si alguien la redirige por entorno (.env), se ve.
        resultado["fuentes_oficiales"][nombre] = {
            "url": url, "estado": f"error: {errores[tipo]}" if tipo in errores else "ok"}

    filas = [clasificar(f, indice.get(f), fuentes_manif.get(f, {}), oficiales, errores)
             for f in sorted(set(indice) | set(fuentes_manif), key=lambda s: norm(s))]

    # Dos archivos con el mismo texto: el que no tiene identidad confirmada no contiene el
    # ordenamiento que dice su nombre (la alerta no recae sobre el gemelo genuino).
    grupos: Dict[str, List[dict]] = {}
    for f in filas:
        texto = norm(indice.get(f["fuente"], {}).get("chunk0", ""))[:2000]
        if texto:
            grupos.setdefault(hashlib.sha1(texto.encode()).hexdigest(), []).append(f)
    for grupo in (g for g in grupos.values() if len(g) > 1):
        genuino = next((g for g in grupo if g["identidad_confirmada"]), None)
        for f in grupo:
            if f is genuino:
                continue
            gemelo = genuino or next(g for g in grupo if g is not f)
            f["alertas"].append(
                f"Contenido idéntico a «{gemelo['fuente']}»: este archivo no contiene el ordenamiento que indica su nombre."
                if genuino else
                f"Contenido idéntico a «{gemelo['fuente']}»: uno de los dos no es el ordenamiento que indica su nombre.")

    # PDF reemplazado en disco pero no re-indexado: el texto viejo sigue vivo en el índice hasta
    # que esa fuente se re-ingeste (`ingest --fuente`). Se compara contra el
    # chunk MÁS VIEJO de la fuente: con el más nuevo, una ingesta normal posterior al reemplazo
    # (que solo añade la cola) escondería el problema. Copiar con Finder conserva el mtime, así
    # que esto es una pista, no un gate.
    if corpus.is_dir():
        for f in filas:
            pdf = corpus / f["fuente"]
            indexado = utc(indice.get(f["fuente"], {}).get("indexado_min_utc", ""))
            if not indexado or not pdf.exists():
                continue
            modificado = dt.datetime.fromtimestamp(pdf.stat().st_mtime, tz=dt.timezone.utc)
            if modificado > indexado + dt.timedelta(minutes=5):
                f["alertas"].append(
                    f"El PDF en disco ({modificado.astimezone():%Y-%m-%d %H:%M}) es posterior a parte de su "
                    f"indexación (desde {indexado.astimezone():%Y-%m-%d %H:%M}): re-ingesta esa fuente con "
                    f"`OpenNotebook.py ingest --fuente \"{f['fuente']}\"`.")

    for f in filas:
        f["semaforo"] = SEMAFORO[f["estado"]]
        if f["alertas"] and f["semaforo"] == VERDE:
            f["semaforo"] = AMARILLO
        for k in ("fecha_indexada", "fecha_oficial"):
            f[k] = f[k].isoformat() if f[k] else None

    resultado["filas"] = filas
    resultado["indice"] = {
        "fuentes": len(indice), "chunks": sum(v["chunks"] for v in indice.values()),
        "indexado_desde": min(v["indexado_utc"][:10] for v in indice.values()),
        "indexado_hasta": max(v["indexado_utc"][:10] for v in indice.values()),
    }
    resultado["conteo"] = {s: sum(1 for f in filas if f["semaforo"] == s) for s in (ROJO, AMARILLO, VERDE, BLANCO)}
    resultado["estado_corrida"] = "completa" if not errores else ("parcial" if oficiales else "fallida")

    rojas = [f for f in filas if f["estado"] == "DESACTUALIZADA"]
    amarillas = [f for f in filas if f["semaforo"] == AMARILLO]
    if rojas:
        resultado["veredicto"] = ROJO
        resultado["razon"] = f"CORPUS NO VIGENTE — {len(rojas)} fuente(s) desactualizada(s) frente a la fuente oficial"
    elif resultado["estado_corrida"] == "fallida":
        resultado["veredicto"] = AMARILLO
        resultado["razon"] = "NO SE PUDO VERIFICAR — no respondió ninguna fuente oficial"
    elif amarillas or errores:
        resultado["veredicto"] = AMARILLO
        resultado["razon"] = f"VIGENTE CON RESERVAS — {len(amarillas)} fuente(s) por revisar"
    else:
        resultado["veredicto"] = VERDE
        resultado["razon"] = "CORPUS VIGENTE — todas las fuentes verificables coinciden con la versión oficial"
    if errores:
        resultado["razon"] += " (fuente oficial no consultada: " + ", ".join(PAGINAS[t][0] for t in errores) + ")"
    return resultado


# ─────────────────────────────────────────
# Reporte
# ─────────────────────────────────────────

def desactualizadas(r: dict) -> List[dict]:
    """Federales primero (CPEUM y leyes de amparo/penal pesan más en el PJF), luego Jalisco;
    dentro de cada ámbito, mayor rezago primero."""
    rojas = [f for f in r["filas"] if f["estado"] == "DESACTUALIZADA"]
    return sorted(rojas, key=lambda f: (not f["tipo"].startswith("federal"), -(f["rezago_dias"] or 0)))


def _celda(texto: str) -> str:
    return (texto or "—").replace("|", "\\|").replace("\n", " ")


def _rel(ruta: Path) -> str:
    try:
        return str(ruta.relative_to(REPO))
    except ValueError:
        return str(ruta)


def rezago(dias: Optional[int]) -> str:
    if dias is None:
        return "—"
    return f"{dias:,} días" + (f" (≈ {round(dias / 365.25)} años)" if dias >= 730 else "")


def pasos_actualizacion(r: dict) -> Dict[str, str]:
    """Comandos de la re-ingesta POR FUENTE (`OpenNotebook.py ingest --fuente`, docs/ENTORNO.md)
    para las fuentes desactualizadas, con las rutas reales del índice auditado. Solo toca los
    fragmentos de esas fuentes, respalda lo que reemplaza y se restaura si algo falla. Nunca
    `--reingest` ni `--clear`: borran la colección entera."""
    chroma, corpus = Path(r["chroma"]), Path(r["corpus"])
    venv = next((p for p in (REPO / "venv/bin/python", chroma.parent / "venv/bin/python") if p.exists()), None)
    python = f'"{venv}"' if venv else "./venv/bin/python"
    entorno = f'cd "{REPO}" && CHROMA_PATH="{chroma}" INGEST_ALLOWED_BASE="{corpus.parent}"'
    fuentes = " ".join('--fuente "{}"'.format(f["fuente"]) for f in desactualizadas(r))
    ingesta = f'{entorno} \\\n  {python} OpenNotebook.py ingest --directory "{corpus}" {fuentes}'
    return {
        "respaldar": f'cp -a "{chroma}" "{chroma}.respaldo-$(date +%Y%m%d-%H%M)"',
        "simular": f"{ingesta} --simular",
        "reingestar": ingesta,
        "verificar": (f"{entorno} {python} scripts/check_corpus.py && \\\n"
                      f'  python3 scripts/vigencia_corpus.py --chroma "{chroma}" --corpus "{corpus}"'),
        "regresion": f'cd "{REPO}" && CHROMA_PATH="{chroma}" {python} scripts/run_regression.py',
        "restaurar": f'{entorno} \\\n  {python} OpenNotebook.py ingest --restaurar "<respaldo.json de esa fuente>"',
    }


def reporte_md(r: dict) -> str:
    out = [f"# Vigencia del corpus RAG · {r['fecha']}", ""]
    if r["estado_corrida"] == "fallida" and not r["filas"]:
        out += [f"**Veredicto: {r['veredicto']} {r['razon']}.**", "",
                "No hubo cotejo: esto no significa que el corpus esté desactualizado. Corrige la causa y "
                "vuelve a correr `python3 scripts/vigencia_corpus.py`.", "",
                "_Generado por `scripts/vigencia_corpus.py`._", ""]
        return "\n".join(out)
    out.append(f"**Veredicto: {r['veredicto']} {r['razon']}.** No es promedio: basta una fuente desactualizada.")
    out.append("")
    ind = r["indice"]
    periodo = ind["indexado_desde"] if ind["indexado_desde"] == ind["indexado_hasta"] else f"{ind['indexado_desde']} a {ind['indexado_hasta']}"
    out.append(f"- Índice auditado: `{r['chroma']}` · {ind['fuentes']} fuentes · {ind['chunks']:,} chunks · indexado el {periodo}")
    consultas = " · ".join(f"[{n}]({v['url']}) {'✅' if v['estado'] == 'ok' else '❌ ' + v['estado']}"
                           for n, v in r["fuentes_oficiales"].items())
    out.append(f"- Fuentes oficiales consultadas el {r['fecha']} {r['hora']}: {consultas or '—'}")
    c = r["conteo"]
    out.append(f"- Resumen: {ROJO} {c[ROJO]} desactualizadas · {AMARILLO} {c[AMARILLO]} por revisar · "
               f"{VERDE} {c[VERDE]} vigentes · {BLANCO} {c[BLANCO]} no aplica")
    out.append("")

    rojas = desactualizadas(r)
    if rojas:
        out += [f"## {ROJO} Desactualizadas — actualizar antes de auditar citas de estas leyes", "",
                "| Ordenamiento | Versión indexada | Versión oficial hoy | Rezago | Enlaces |",
                "|---|---|---|---|---|"]
        for f in rojas:
            enlaces = " · ".join(x for x in (f"[PDF oficial]({f['url_pdf']})" if f["url_pdf"] else "",
                                              f"[reformas]({f['url_historial']})" if f["url_historial"] else "") if x)
            out.append(f"| **{_celda(f['etiqueta'])}**<br>`{_celda(f['fuente'])}` | {_celda(f['version_indexada'])} | "
                       f"{_celda(f['version_oficial'])} | {rezago(f['rezago_dias'])} | {enlaces or '—'} |")
        con_notas = [f for f in rojas if f["notas"] or f["alertas"]]
        if con_notas:
            out += [""] + [f"- **{f['etiqueta']}**: {' '.join(f['alertas'] + f['notas'])}" for f in con_notas]
        if any(f["tipo"] == "jalisco" for f in rojas):
            out += ["", "_Jalisco: «Tabla de reformas» es la última entrada de la tabla de reformas del PDF "
                        "indexado (fecha inferida); «cita / no cita el decreto o la resolución N» dice si el texto "
                        "indexado menciona el instrumento de la última modificación oficial (decreto del Congreso, "
                        "o A.I./declaratoria de la SCJN). Cuando ambas señales coinciden la confianza es alta. "
                        "El sello «DOF» de los PDFs federales es explícito._"]
        out.append("")

    amarillas = [f for f in r["filas"] if f["semaforo"] == AMARILLO]
    if amarillas:
        out += [f"## {AMARILLO} Por revisar", "", "| Ordenamiento | Estado | Detalle |", "|---|---|---|"]
        for f in amarillas:
            detalle = " ".join([f["detalle"]] + f["alertas"] + f["notas"])
            if f["version_oficial"]:
                detalle += f" Indexada: {f['version_indexada'] or '—'} · oficial: {f['version_oficial']}."
            out.append(f"| **{_celda(f['etiqueta'])}**<br>`{_celda(f['fuente'])}` | {f['estado']} | {_celda(detalle.strip())} |")
        out.append("")

    verdes = [f for f in r["filas"] if f["semaforo"] == VERDE]
    if verdes:
        out += [f"## {VERDE} Vigentes", ""]
        out += [f"- **{f['etiqueta']}** — {f['version_indexada']} · oficial: {f['version_oficial']}" for f in verdes]
        out.append("")
    blancas = [f for f in r["filas"] if f["semaforo"] == BLANCO]
    if blancas:
        out += [f"## {BLANCO} No aplica", ""] + [f"- `{f['fuente']}` — {f['detalle']}" for f in blancas] + [""]

    if rojas:
        p = pasos_actualizacion(r)

        def bloque(cmd: str) -> List[str]:
            return ["", "   ```bash", "   " + cmd.replace("\n", "\n   "), "   ```", ""]

        out += ["## Cómo actualizar (manual, en tu Terminal: el agente no re-indexa solo)", "",
                f"Re-ingesta **por fuente** (`OpenNotebook.py ingest --fuente`, detalle en `docs/ENTORNO.md`): solo "
                f"reemplaza los fragmentos de cada fuente {ROJO}, guarda un respaldo durable de lo que sustituye y se "
                "restaura sola si algo falla. Nunca `--reingest` ni `--clear`: borran la colección entera.", "",
                f"1. En `{r['corpus']}`, reemplaza el PDF de cada fuente {ROJO} por el oficial (columna Enlaces) "
                "**con el mismo nombre de archivo** — es el `source` del índice y lo que resuelve `LAW_SOURCE_MAP` — "
                "y guarda el anterior fuera del repo.",
                "2. Respalda el índice completo, sin ningún proceso abierto sobre él:"] + bloque(p["respaldar"]) + [
                "3. Simula (no escribe): fragmentos, etiquetas, cobertura antes → después e identidad con lo "
                "indexado. Si una fuente sale ⛔, corrígela antes de seguir:"] + bloque(p["simular"]) + [
                "4. Re-ingesta (~0.45 s por fragmento en CPU) y anota la ruta del respaldo durable de cada fuente:"
                ] + bloque(p["reingestar"]) + [
                f"5. Verifica: 0 fuentes ausentes y las actualizadas en {VERDE}:"] + bloque(p["verificar"]) + [
                "   Regresión del motor (si un veredicto cambia, es hallazgo de Capa 2: no toques umbrales):"
                ] + bloque(p["regresion"]) + [
                "6. Para deshacer una fuente, repón su respaldo durable:"] + bloque(p["restaurar"]) + [
                "7. Sube a la carpeta de Drive del bootstrap **solo las leyes actualizadas** (nunca escritos de "
                "clientes), para que otro clon no baje la versión vieja.", ""]
    out += [
            "---",
            "⚠️ Capa 1 (automatizada): compara fechas de última reforma; no dice qué artículos cambiaron ni si la "
            "reforma afecta un asunto concreto. Eso es Capa 2 y lo decide el abogado (revisa el historial de "
            "reformas y los transitorios).",
            "",
            "_Generado por `scripts/vigencia_corpus.py`._", ""]
    return "\n".join(out)


def resumen_corto(r: dict) -> List[str]:
    return [f"{f['etiqueta']}: indexada {f['version_indexada']} → oficial {f['version_oficial']}"
            for f in desactualizadas(r)]


def cuerpo_aviso(r: dict, reporte: Path) -> str:
    """Texto breve para la notificación: siglas federales + conteo de Jalisco + ruta del reporte."""
    rojas = desactualizadas(r)
    federales = [f["etiqueta"] for f in rojas if f["tipo"].startswith("federal")]
    locales = len(rojas) - len(federales)
    partes = ([f"Federales: {', '.join(federales)}"] if federales else []) + \
             ([f"Jalisco: {locales}"] if locales else [])
    return " · ".join(partes + [f"ver {_rel(reporte)}"])


# ─────────────────────────────────────────
# Avisos y estado del ciclo
# ─────────────────────────────────────────

def notificar_macos(titulo: str, subtitulo: str, mensaje: str) -> None:
    if sys.platform != "darwin" or not shutil.which("osascript"):
        return

    def q(s: str) -> str:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'

    script = f"display notification {q(mensaje[:230])} with title {q(titulo)} subtitle {q(subtitulo[:120])} sound name \"Glass\""
    subprocess.run(["osascript", "-e", script], capture_output=True, check=False)


def notificar_telegram(texto: str) -> None:
    """Opcional: solo si TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID existen. Lleva nombres de leyes y fechas."""
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return
    datos = urllib.parse.urlencode({"chat_id": chat, "text": texto[:4000], "disable_web_page_preview": "true"}).encode()
    try:
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=datos, timeout=20).close()
    except Exception as e:  # noqa: BLE001 — un aviso fallido no invalida la verificación
        print(f"[vigencia] ⚠️  Telegram no se pudo enviar: {e}", file=sys.stderr)


def leer_estado(ruta: Path) -> dict:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def motivo_para_correr(estado: dict, hoy: dt.date, cada_dias: int, chroma: Path) -> str:
    """'' si no toca; si toca, el porqué (va al log de launchd)."""
    ultima = estado.get("ultima_completa")
    if not ultima:
        return "primera verificación"
    if estado.get("chroma") != str(chroma):
        return "cambió el índice vigilado"
    try:
        dias = (hoy - dt.date.fromisoformat(ultima)).days
    except ValueError:
        return "estado ilegible"
    return f"pasaron {dias} días" if dias >= cada_dias else ""


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    cargar_env(REPO)

    ap = argparse.ArgumentParser(description="Coteja la vigencia del corpus RAG contra las fuentes oficiales.")
    ap.add_argument("--chroma", default=os.getenv("CHROMA_PATH", str(REPO / "chroma_db")),
                    help="carpeta de ChromaDB (default: CHROMA_PATH o <repo>/chroma_db)")
    ap.add_argument("--corpus", default=os.getenv("ITOS_CORPUS_DIR"),
                    help="carpeta de PDFs para detectar re-ingestas pendientes (default: hermana 'corpus' del índice)")
    ap.add_argument("--manifiesto", default=str(REPO / "scripts" / "fuentes_oficiales.json"))
    ap.add_argument("--salida", default=os.getenv("ITOS_VIGENCIA_SALIDA", str(REPO / "reportes" / "vigencia_corpus")))
    ap.add_argument("--cada-dias", type=int, default=int(os.getenv("ITOS_VIGENCIA_CADA_DIAS", "60")))
    ap.add_argument("--si-toca", action="store_true",
                    help="solo verifica si pasaron --cada-dias desde la última verificación completa (modo launchd)")
    ap.add_argument("--notificar", action="store_true", help="aviso de macOS (+ Telegram si está configurado)")
    ap.add_argument("--json", action="store_true", help="imprime el resultado completo en JSON")
    args = ap.parse_args()

    chroma = Path(args.chroma).expanduser().resolve()
    corpus = Path(args.corpus).expanduser().resolve() if args.corpus else chroma.parent / "corpus"
    salida = Path(args.salida).expanduser().resolve()
    ruta_estado = salida / "estado.json"
    estado = leer_estado(ruta_estado)
    ahora = dt.datetime.now()

    if args.si_toca:
        motivo = motivo_para_correr(estado, ahora.date(), args.cada_dias, chroma)
        if not motivo:
            print(f"[vigencia] {ahora:%Y-%m-%d %H:%M} no toca: última verificación completa el "
                  f"{estado.get('ultima_completa')} (cada {args.cada_dias} días).", file=sys.stderr)
            return 0
        print(f"[vigencia] {ahora:%Y-%m-%d %H:%M} verificando ({motivo}).", file=sys.stderr)

    try:
        manifiesto = json.loads(Path(args.manifiesto).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"❌ No se pudo leer el manifiesto {args.manifiesto}: {e}", file=sys.stderr)
        return 2

    r = verificar(chroma, corpus, manifiesto)
    salida.mkdir(parents=True, exist_ok=True)
    base = salida / f"vigencia_{r['fecha']}"
    base.with_suffix(".md").write_text(reporte_md(r), encoding="utf-8")
    base.with_suffix(".json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    reporte = base.with_suffix(".md")

    if r["estado_corrida"] == "completa":
        estado.update({"ultima_completa": r["fecha"], "chroma": str(chroma), "ultimo_veredicto": r["veredicto"],
                       "ultima_razon": r["razon"], "ultimo_reporte": str(reporte)})
    else:
        estado["ultimo_intento_incompleto"] = f"{r['fecha']} {r['hora']}"
    avisar = args.notificar
    if avisar and r["estado_corrida"] != "completa":
        # Una corrida incompleta se reintenta a diario: avisa como mucho una vez por semana.
        previo = estado.get("ultimo_aviso_incompleto", "")
        try:
            avisar = not previo or (ahora.date() - dt.date.fromisoformat(previo)).days >= DIAS_ENTRE_AVISOS_DE_FALLO
        except ValueError:
            avisar = True
        if avisar:
            estado["ultimo_aviso_incompleto"] = r["fecha"]
    ruta_estado.write_text(json.dumps(estado, ensure_ascii=False, indent=2), encoding="utf-8")

    rojas = resumen_corto(r)
    if avisar:
        notificar_macos("Itosturre · Vigencia del corpus", f"{r['veredicto']} {r['razon'].split(' — ')[-1]}",
                        cuerpo_aviso(r, reporte))
        notificar_telegram("\n".join([f"🏛️ Itosturre · Vigencia del corpus ({r['fecha']})",
                                      f"{r['veredicto']} {r['razon']}"] + [f"• {x}" for x in rojas] +
                                     [f"Reporte: {_rel(reporte)}"]))

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print(f"{r['veredicto']} {r['razon']}")
        for linea in rojas:
            print(f"   {ROJO} {linea}")
        if r["filas"]:
            c = r["conteo"]
            print(f"   {ROJO} {c[ROJO]} · {AMARILLO} {c[AMARILLO]} · {VERDE} {c[VERDE]} · {BLANCO} {c[BLANCO]}")
        print(f"📄 Reporte: {_rel(reporte)}")

    if r["estado_corrida"] == "fallida":
        return 2
    if any(f["estado"] == "DESACTUALIZADA" for f in r["filas"]):
        return 1
    # Sin desactualizadas pero con una fuente oficial sin consultar: "no pude verificar todo"
    # no es "todo está bien" (regla 7), así que no sale 0.
    return 2 if r["estado_corrida"] != "completa" else 0


if __name__ == "__main__":
    raise SystemExit(main())
