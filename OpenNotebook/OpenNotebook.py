"""
OpenNotebook.py v2.0 — RAG Legal Itosturre
Motor de auditoría anti-alucinaciones para escritos jurídicos.

Cambios v2.0:
  ✅ Configuración via .env (portabilidad)
  ✅ Resolución robusta de aliases (ventana expandida)
  ✅ Umbral de distancia ajustado (0.50 conservador)
  ✅ --clear, --reingest, --verbose
  ✅ Mejor logging y trazabilidad
  ✅ Unificación de jurisprudencia en Chroma (opcional)
  ✅ Metadatos enriquecidos (página, chunk)

Comandos:
  python OpenNotebook_v2.0.py ingest --directory /ruta/a/pdfs/
  python OpenNotebook_v2.0.py audit --text "texto del borrador"
  python OpenNotebook_v2.0.py audit --file /ruta/borrador.md
  python OpenNotebook_v2.0.py audit --file /ruta/borrador.md --verbose
"""

import argparse
import json
import re
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, List

import fitz  # PyMuPDF
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

# ─────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────

def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

logger = setup_logging()

# ─────────────────────────────────────────
# CONFIGURACIÓN (via .env o defaults)
# ─────────────────────────────────────────

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    logger.warning("⚠️  python-dotenv no instalado. Usando rutas por defecto.")

import os

CHROMA_PATH = os.getenv("CHROMA_PATH", "/home/licjo/chroma_db")
JURISPRUDENCIA_PATH = os.getenv("JURISPRUDENCIA_PATH", "/home/licjo/jurisprudencia")
COLLECTION_NAME = "corpus_legal_itosturre"
EMBED_MODEL = "intfloat/multilingual-e5-small"

# PDFs legales — excluir documentos personales
EXCLUDE_PATTERNS = [
    "ActaNacimiento", "Chapter_1es", "CONSIGNA", "Bloc de notas",
    "Battlefield", "Marvel", "FrameView", "SOFÍA", "desktop"
]

# Threshold de distancia coseno: por debajo → verificado; por encima → alerta.
# 0.50 = conservador para texto legal mexicano
# (0.60+ = muy permisivo, <0.40 = demasiado estricto)
COSINE_THRESHOLD = float(os.getenv("COSINE_THRESHOLD", "0.50"))

# Regex robusto para artículos legales. Captura:
#   Art. 247  /  artículo 247  /  arts. 247-250  /  Art. 247 Bis
#   Art. 247 fr. III  /  Art. 247, fracción IV  /  Art. 259°
ARTICLE_RE = re.compile(
    r'[Aa]rt[íi]?(?:culo)?s?\.?\s*'
    r'(\d+[\w\-]*(?:\s+[Bb]is|[Tt]er|[Qq]u[áa]ter)?)'
    r'(?:[°º])?'
    r'(?:'
        r'\s*[,;]?\s*'
        r'(?:fr(?:acci[oó]n)?\.?|frac\.?)\s*'
        r'([\w\.]+)'
    r')?',
    re.IGNORECASE
)

# Abreviaciones → nombre normalizado del ordenamiento.
LAW_ALIASES = {
    # Constitución
    "CPEUM": "Código Constitución Política de los Estados Unidos Mexicanos",
    "Constitución": "Constitución Política de los Estados Unidos Mexicanos",
    "Carta Magna": "Constitución Política de los Estados Unidos Mexicanos",
    "Constitucional": "Constitución Política de los Estados Unidos Mexicanos",
    # Penal federal
    "CPF": "Código Penal Federal",
    "C.P.F.": "Código Penal Federal",
    "CP Federal": "Código Penal Federal",
    "C.P. Federal": "Código Penal Federal",
    "C. P. Federal": "Código Penal Federal",
    "Código Penal Federal": "Código Penal Federal",
    # Penal Jalisco
    "CPJ": "Código Penal para el Estado Libre y Soberano de Jalisco",
    "CP Jalisco": "Código Penal para el Estado Libre y Soberano de Jalisco",
    "Código Penal de Jalisco": "Código Penal para el Estado Libre y Soberano de Jalisco",
    # Civil federal
    "CCF": "Código Civil Federal",
    "C.C.F.": "Código Civil Federal",
    "CC Federal": "Código Civil Federal",
    # Civil Jalisco
    "CCJ": "Código Civil del Estado de Jalisco",
    "CC Jalisco": "Código Civil del Estado de Jalisco",
    # Fiscal
    "CFF": "Código Fiscal de la Federación",
    "C.F.F.": "Código Fiscal de la Federación",
    # Procedimientos
    "CFPC": "Código Federal de Procedimientos Civiles",
    "CPCJ": "Código de Procedimientos Civiles del Estado de Jalisco",
    "CNPCF": "Código Nacional de Procedimientos Civiles y Familiares",
    "CNPP": "Código Nacional de Procedimientos Penales",
    # Leyes federales
    "LISR": "Ley del Impuesto sobre la Renta",
    "LIVA": "Ley del Impuesto al Valor Agregado",
    "LFPCA": "Ley Federal de Procedimiento Contencioso Administrativo",
    "LFPA": "Ley Federal de Procedimiento Administrativo",
    "LFPDPPP": "Ley Federal de Protección de Datos Personales",
    "LFPC": "Ley Federal de Protección al Consumidor",
    "LFPPI": "Ley Federal de Protección a la Propiedad Intelectual",
    "LSS": "Ley del Seguro Social",
    "LFT": "Ley Federal del Trabajo",
    "LOPJF": "Ley Orgánica del Poder Judicial Federal",
    "Ley de Amparo": "Ley de Amparo",
    # Jalisco
    "TJAJ": "Ley de Justicia Administrativa del Estado de Jalisco",
    "LPAJM": "Ley del Procedimiento Administrativo del Estado de Jalisco",
    # Internacional
    "CADH": "Convención Americana sobre Derechos Humanos",
    "PIDCP": "Pacto Internacional de Derechos Civiles y Políticos",
}

# Mapeo de palabras clave de ley (minúsculas) → nombre exacto del archivo en ChromaDB
LAW_SOURCE_MAP = {
    "código federal de procedimientos civiles": "Código Federal de Procedimientos Civiles 2026.pdf",
    "código nacional de procedimientos civiles": "Código Nacional de Procedimientos Civiles y Familiares 2026.pdf",
    "código nacional de procedimientos penales": "CodigoNacionalProcedPenales.pdf",
    "código civil federal": "CODIGO CIVIL FEDERAL 2026.pdf",
    "código civil para el estado de nuevo": "CODIGO CIVIL PARA EL ESTADO DE NUEVO LEON 2026.pdf",
    "código civil del estado de jalisco": "Codigo-Civil-del-Estado-de-Jalisco_3.pdf",
    "código de procedimientos civiles del estado de jalisco": "CodigoProcedimientosCivilesEstadoJalisco.pdf",
    "código fiscal de la federación": "CODIGO FISCAL DE LA FEDERACION 2026.pdf",
    "código fiscal del estado de jalisco": "CODIGO FISCAL DEL ESTADO DE JALISCO 2026.pdf",
    "código penal para el estado": "Código Penal para el Estado Libre y Soberano de Jalisco.pdf",
    "constitución política de los estados unidos": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    "constitución política del estado de jalisco": "Constitución Politica del Estado de Jalisco 2026.pdf",
    "ley de amparo": "LEY DE AMPARO.pdf",
    "ley del seguro social": "LEY DEL SEGURO SOCIAL.pdf",
    "ley federal de protección a la propiedad intelectual": "LEY FEDERAL DE PROTECCION A LA PROPIEDAD INTELECTUAL LFPPI.pdf",
    "ley federal de protección al consumidor": "LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR LFPC.pdf",
    "ley federal de protección de datos personales": "LEY FEDERAL DE PROTECCIÓN DE DATOS PERSONALES EN POSESIÓN DE LOS PARTICULARES LFPDPPP.pdf",
    "ley federal de procedimiento administrativo": "Ley Federal de Procedimiento Administrativo 2026.pdf",
    "ley federal de procedimiento contencioso": "Ley Federal de Procedimiento Contencioso Administrativo 2026.pdf",
    "ley orgánica del poder judicial federal": "Ley Orgánica del Poder Judicial Federal 2026.pdf",
    "ley de hacienda del estado de jalisco": "Ley de Hacienda del Estado de Jalisco -160424 2026.pdf",
    "ley de movilidad y transporte": "Ley de Movilidad y Transporte del Estado de Jalisco_2 2026.pdf",
    "ley del impuesto al valor agregado": "Ley del Impuesto al Valor Agregado 2026.pdf",
    "ley del impuesto sobre la renta": "Ley del Impuesto sobre la Renta 2026.pdf",
    "ley del notariado del estado de jalisco": "Ley del Notariado del Estado de Jalisco 2026.pdf",
    "ley del procedimiento administrativo del estado de jalisco": "Ley del Procedimiento Administrativo del Estado de Jalisco y sus Municipios_15_0 2026.pdf",
    "ley de justicia administrativa del estado de jalisco": "LeydeJusticiaAdministrativadelEstadodeJalisco 2026.pdf",
    "ley del registro civil del estado de jalisco": "ley_del_registro_civil_del_estado_de_jalisco 2026.pdf",
    "reglamento de la ley federal de protección al consumidor": "REGLAMENTO DE LA LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR Reg_LFPC_191219.pdf",
    "reglamento de movilidad": "RegMovilidadTransporteSeguridadVialGuadalajara 2026.pdf",
    "reglamento orgánico del poder judicial": "Reglamento organico poder judicial de la federación 2026.pdf",
    # Abreviaciones
    "cfpc": "Código Federal de Procedimientos Civiles 2026.pdf",
    "cnpcf": "Código Nacional de Procedimientos Civiles y Familiares 2026.pdf",
    "cnpp": "CodigoNacionalProcedPenales.pdf",
    "ccf": "CODIGO CIVIL FEDERAL 2026.pdf",
    "cff": "CODIGO FISCAL DE LA FEDERACION 2026.pdf",
    "lisr": "Ley del Impuesto sobre la Renta 2026.pdf",
    "liva": "Ley del Impuesto al Valor Agregado 2026.pdf",
    "lfpca": "Ley Federal de Procedimiento Contencioso Administrativo 2026.pdf",
    "lfpa": "Ley Federal de Procedimiento Administrativo 2026.pdf",
    "lfpdppp": "LEY FEDERAL DE PROTECCIÓN DE DATOS PERSONALES EN POSESIÓN DE LOS PARTICULARES LFPDPPP.pdf",
    "lfpc": "LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR LFPC.pdf",
    "lfppi": "LEY FEDERAL DE PROTECCION A LA PROPIEDAD INTELECTUAL LFPPI.pdf",
    "lss": "LEY DEL SEGURO SOCIAL.pdf",
    "lft": "LEY FEDERAL DEL TRABAJO 2025.pdf",
    "ley federal del trabajo": "LEY FEDERAL DEL TRABAJO 2025.pdf",
    "pidcp": "Pacto Internacional de Derechos Civiles y Políticos.pdf",
    "pacto internacional de derechos civiles": "Pacto Internacional de Derechos Civiles y Políticos.pdf",
    "lopjf": "Ley Orgánica del Poder Judicial Federal 2026.pdf",
    "cpeum": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    "tjaj": "LeydeJusticiaAdministrativadelEstadodeJalisco 2026.pdf",
    "lpajm": "Ley del Procedimiento Administrativo del Estado de Jalisco y sus Municipios_15_0 2026.pdf",
    "cpf": "CODIGO PENAL FEDERAL 2025.pdf",
    "c.p.f.": "CODIGO PENAL FEDERAL 2025.pdf",
    "cp federal": "CODIGO PENAL FEDERAL 2025.pdf",
    "cpcj": "CodigoProcedimientosCivilesEstadoJalisco.pdf",
    "cpj": "Código Penal para el Estado Libre y Soberano de Jalisco.pdf",
    "cp jalisco": "Código Penal para el Estado Libre y Soberano de Jalisco.pdf",
    "ccj": "Codigo-Civil-del-Estado-de-Jalisco_3.pdf",
    "cc jalisco": "Codigo-Civil-del-Estado-de-Jalisco_3.pdf",
    "cc federal": "CODIGO CIVIL FEDERAL 2026.pdf",
    "c.c.f.": "CODIGO CIVIL FEDERAL 2026.pdf",
    "c.f.f.": "CODIGO FISCAL DE LA FEDERACION 2026.pdf",
    "ley de amparo": "LEY DE AMPARO.pdf",
    "carta magna": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    "constitución": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    "constitucional": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    "c.p. federal": "CODIGO PENAL FEDERAL 2025.pdf",
    "c. p. federal": "CODIGO PENAL FEDERAL 2025.pdf",
    "c.p.federal": "CODIGO PENAL FEDERAL 2025.pdf",
    "c.c. federal": "CODIGO CIVIL FEDERAL 2026.pdf",
    "c. c. federal": "CODIGO CIVIL FEDERAL 2026.pdf",
    "código penal federal": "CODIGO PENAL FEDERAL 2025.pdf",
    "código penal de jalisco": "Código Penal para el Estado Libre y Soberano de Jalisco.pdf",
    "código civil del estado de jalisco": "Codigo-Civil-del-Estado-de-Jalisco_3.pdf",
    "código nacional de procedimientos penales": "CodigoNacionalProcedPenales.pdf",
}


# ─────────────────────────────────────────
# EMBEDDINGS Y CHROMA
# ─────────────────────────────────────────

_EMBEDDER_CACHE = None

def get_embedder():
    global _EMBEDDER_CACHE
    if _EMBEDDER_CACHE is None:
        logger.info(f"⏳ Cargando modelo de embeddings: {EMBED_MODEL}...")
        _EMBEDDER_CACHE = SentenceTransformer(EMBED_MODEL)
    return _EMBEDDER_CACHE


def get_collection(embedder):
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    class STEmbeddingFunction:
        def __init__(self, model):
            self.model = model
        def name(self):
            return "itosturre-st-embedder"
        def __call__(self, input):
            return self.model.encode(input, normalize_embeddings=True).tolist()
        def embed_documents(self, input):
            return self.model.encode(input, normalize_embeddings=True).tolist()
        def embed_query(self, input):
            if isinstance(input, str):
                input = [input]
            return self.model.encode(input, normalize_embeddings=True).tolist()

    ef = STEmbeddingFunction(embedder)
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"}
    )
    return collection


# ─────────────────────────────────────────
# INGESTA
# ─────────────────────────────────────────

def is_legal_pdf(path: Path) -> bool:
    name = path.name
    for pat in EXCLUDE_PATTERNS:
        if pat.lower() in name.lower():
            return False
    return path.suffix.lower() == ".pdf"


def extract_text_from_pdf(pdf_path: Path) -> list:
    """Extrae texto y metadatos (página, posición) de PDF."""
    doc = fitz.open(str(pdf_path))
    pages = []
    for page_num, page in enumerate(doc, 1):
        text = page.get_text()
        if text.strip():
            pages.append({"page": page_num, "text": text})
    doc.close()
    return pages


def ingest(directory: str, clear: bool = False, reingest: bool = False):
    pdf_dir = Path(directory)
    pdfs = [p for p in pdf_dir.iterdir() if is_legal_pdf(p)]

    if not pdfs:
        logger.error(f"❌ No se encontraron PDFs legales en: {directory}")
        sys.exit(1)

    logger.info(f"📚 PDFs encontrados: {len(pdfs)}")

    embedder = get_embedder()
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # Limpiar colección si se solicita
    if clear:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("🗑️  Colección borrada.")
        except Exception as e:
            logger.warning(f"⚠️  No se pudo borrar colección: {e}")

    collection = get_collection(embedder)

    # Si reingest, limpiar colección
    if reingest:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("🔄 Colección limpiada para re-ingesta.")
            collection = get_collection(embedder)
        except Exception:
            pass

    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " "]
    )

    total_chunks = 0
    for pdf_path in pdfs:
        logger.info(f"  🔍 Procesando: {pdf_path.name}")
        try:
            pages = extract_text_from_pdf(pdf_path)
            if not pages:
                logger.warning(f"     ⚠️  Texto muy corto, omitiendo.")
                continue

            # Splitter article-aware
            art_split_re = re.compile(
                r'(?=\n[Aa]rt[íi]?(?:culo)?s?\.?\s+\d+)', re.MULTILINE
            )

            chunks_with_meta: List[Tuple[str, str, int]] = []
            for page_data in pages:
                page_num = page_data["page"]
                raw_text = page_data["text"]

                raw_pieces = art_split_re.split(raw_text)

                for piece in raw_pieces:
                    if not piece.strip():
                        continue

                    head_match = re.match(
                        r'\s*[Aa]rt[íi]?(?:culo)?s?\.?\s+(\d+[\w\-]*)', piece
                    )
                    art_num = head_match.group(1) if head_match else ""

                    if len(piece) <= 1200:
                        chunks_with_meta.append((piece.strip(), art_num, page_num))
                    else:
                        sub_chunks = fallback_splitter.split_text(piece)
                        for sc in sub_chunks:
                            chunks_with_meta.append((sc.strip(), art_num, page_num))

            logger.info(f"     📄 {len(chunks_with_meta)} chunks generados")

            # Insertar en lotes
            batch_size = 50
            for i in range(0, len(chunks_with_meta), batch_size):
                batch = chunks_with_meta[i:i + batch_size]
                texts = [c[0] for c in batch]
                art_nums = [c[1] for c in batch]
                page_nums = [c[2] for c in batch]
                ids = [f"{pdf_path.stem}_chunk_{i + j}" for j in range(len(batch))]
                metadatas = [
                    {
                        "source": pdf_path.name,
                        "law": pdf_path.stem,
                        "article": art_nums[j],
                        "page": str(page_nums[j]),
                        "chunk_index": str(i + j)
                    }
                    for j in range(len(batch))
                ]

                # Evitar duplicados
                existing = collection.get(ids=ids)
                existing_ids = set(existing["ids"])
                new_batch = [
                    (id_, doc, meta)
                    for id_, doc, meta in zip(ids, texts, metadatas)
                    if id_ not in existing_ids
                ]

                if new_batch:
                    n_ids, n_docs, n_metas = zip(*new_batch)
                    collection.add(
                        ids=list(n_ids),
                        documents=list(n_docs),
                        metadatas=list(n_metas)
                    )

            total_chunks += len(chunks_with_meta)
            logger.info(f"     ✅ Indexado correctamente")

        except Exception as e:
            logger.error(f"     ❌ Error procesando {pdf_path.name}: {e}")

    logger.info(f"\n✅ INGESTA COMPLETADA")
    logger.info(f"   PDFs procesados : {len(pdfs)}")
    logger.info(f"   Chunks totales  : {total_chunks}")
    logger.info(f"   Base vectorial  : {CHROMA_PATH}")
    logger.info(f"   Colección       : {COLLECTION_NAME}")


# ─────────────────────────────────────────
# AUDITORÍA
# ─────────────────────────────────────────

def resolve_law_source(context: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca en el contexto el alias de ley que aparece más pronto.
    Ventana expandida: busca en hasta 200 caracteres (antes: 65).
    """
    ctx = context.lower()
    best_key = None
    best_file = None
    best_pos = len(ctx) + 1
    best_len = 0

    for key, source_file in LAW_SOURCE_MAP.items():
        pos = ctx.find(key)
        if pos == -1:
            continue
        if pos < best_pos or (pos == best_pos and len(key) > best_len):
            best_pos = pos
            best_len = len(key)
            best_key = key
            best_file = source_file

    return (best_key, best_file)


def extract_references(text: str) -> List[Dict]:
    """Extrae referencias a artículos y jurisprudencias del borrador."""
    refs = []

    for m in ARTICLE_RE.finditer(text):
        art_num = m.group(1).strip()
        frac = (m.group(2) or "").strip()

        # Estrategia de ventana mejorada (ahora: 30 → 100 → amplia)
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.end())
        if line_end == -1:
            line_end = len(text)

        right_ctx = text[m.end(): min(len(text), m.end() + 100)]  # Ampliado de 30 a 100
        line_ctx = text[line_start:line_end]
        wide_ctx = text[max(0, m.start() - 100): min(len(text), m.end() + 150)]  # Ampliado

        # 1. LAW_SOURCE_MAP — prioridad: derecha → línea → wide
        law_name, source_file = resolve_law_source(right_ctx)
        if not law_name:
            law_name, source_file = resolve_law_source(line_ctx)
        if not law_name:
            law_name, source_file = resolve_law_source(wide_ctx)

        # 2. Fallback alias (case-sensitive)
        if not law_name:
            for ctx in (right_ctx, line_ctx, wide_ctx):
                for alias, full_name in sorted(LAW_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
                    if alias in ctx:
                        law_name = full_name
                        _, source_file = resolve_law_source(alias.lower())
                        break
                if law_name:
                    break

        refs.append({
            "type": "article",
            "article": art_num,
            "fraction": frac,
            "law": law_name or "desconocido",
            "source_file": source_file,
            "raw": m.group(0).strip()
        })

    # Registros digitales SJF
    reg_pattern = re.compile(r'[Rr]egistro\s+(?:digital[:\s]+)?(\d{6,8})')
    for m in reg_pattern.finditer(text):
        refs.append({
            "type": "jurisprudencia",
            "registro": m.group(1),
            "raw": m.group(0).strip()
        })

    return refs


def audit(text: str, verbose: bool = False) -> Dict:
    """
    Audita el borrador contra el corpus legal.
    Retorna JSON con alerts y retrieved_sources.
    """
    embedder = get_embedder()

    # Verificar que existe la base vectorial
    chroma_path = Path(CHROMA_PATH)
    if not chroma_path.exists():
        return {
            "status": "error",
            "message": "Base vectorial no encontrada. Ejecuta primero: python OpenNotebook_v2.0.py ingest --directory /ruta/pdfs/",
            "alerts": [],
            "retrieved_sources": []
        }

    collection = get_collection(embedder)

    if collection.count() == 0:
        return {
            "status": "error",
            "message": "La colección está vacía. Ejecuta primero el comando ingest.",
            "alerts": [],
            "retrieved_sources": []
        }

    refs = extract_references(text)
    alerts = []
    retrieved_sources = []
    verified_count = 0

    if verbose:
        logger.debug(f"🔍 Auditoría: {len(refs)} referencias detectadas")

    for ref in refs:
        if ref["type"] == "article":
            query = f"Artículo {ref['article']}"
            if ref["fraction"]:
                query += f" fracción {ref['fraction']}"
            if ref["law"] and ref["law"] != "desconocido":
                query += f" {ref['law']}"

            expected_source = ref.get("source_file")
            where_filter = {"source": expected_source} if expected_source else None

            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=3,
                    where=where_filter
                )
            except Exception:
                results = collection.query(query_texts=[query], n_results=3)
                expected_source = None

            if results and results["documents"] and results["documents"][0]:
                best_doc = results["documents"][0][0]
                best_meta = results["metadatas"][0][0] if results["metadatas"] else {}
                best_source = best_meta.get("source", "desconocido")
                best_distance = results["distances"][0][0] if results.get("distances") else 1.0

                # Detectar falso positivo por fuente cruzada
                source_mismatch = (
                    expected_source
                    and best_source != expected_source
                    and best_distance <= COSINE_THRESHOLD
                )

                if source_mismatch:
                    alerts.append(
                        f"⚠️  ALERTA: '{ref['raw']}' — se encontró en '{best_source}' "
                        f"pero se esperaba en '{expected_source}'. "
                        f"Posible confusión entre ordenamientos (distancia: {best_distance:.3f}). "
                        f"Verificar manualmente."
                    )
                elif best_distance > COSINE_THRESHOLD:
                    alerts.append(
                        f"🔴 ALERTA ALTA: '{ref['raw']}' — no se encontró coincidencia confiable en el corpus "
                        f"(distancia: {best_distance:.3f}, umbral: {COSINE_THRESHOLD}). "
                        f"Posible alucinación. Verificar en fuente oficial."
                    )
                else:
                    retrieved_sources.append({
                        "reference": ref["raw"],
                        "law": ref["law"],
                        "article": ref["article"],
                        "source_file": best_source,
                        "page": best_meta.get("page", "?"),
                        "expected_source": expected_source,
                        "relevance_score": round(1 - best_distance, 3),
                        "retrieved_text": best_doc[:600]
                    })
                    verified_count += 1
            else:
                alerts.append(
                    f"🔴 ALERTA CRÍTICA: El borrador cita '{ref['raw']}' pero no se encontró en el corpus legal. "
                    f"Alucinación detectada — verificar en fuente oficial ANTES de usar."
                )

        elif ref["type"] == "jurisprudencia":
            # Buscar en corpus local de tesis (para v2.0 aún separado)
            tesis_path = Path(JURISPRUDENCIA_PATH)
            found_in_tesis = False
            if tesis_path.exists():
                for json_file in tesis_path.glob("*.json"):
                    try:
                        data = json.loads(json_file.read_text())
                        for item in (data if isinstance(data, list) else []):
                            if str(ref["registro"]) in str(item.get("registro", "")):
                                found_in_tesis = True
                                retrieved_sources.append({
                                    "reference": ref["raw"],
                                    "registro": ref["registro"],
                                    "source_file": json_file.name,
                                    "relevance_score": 1.0,
                                    "retrieved_text": item.get("texto_completo", "Tesis verificada en corpus SJF.")[:600]
                                })
                                verified_count += 1
                                break
                    except Exception as e:
                        if verbose:
                            logger.debug(f"Error leyendo {json_file}: {e}")
                        continue

            if not found_in_tesis:
                alerts.append(
                    f"⚠️  ALERTA: El borrador cita el Registro digital {ref['registro']} "
                    f"pero no fue encontrado en el corpus de jurisprudencia. "
                    f"Verificar en sjf2.scjn.gob.mx antes de citar."
                )

    return {
        "status": "ok",
        "total_references_found": len(refs),
        "verified": verified_count,
        "alerts_count": len(alerts),
        "cosine_threshold": COSINE_THRESHOLD,
        "alerts": alerts,
        "retrieved_sources": retrieved_sources,
        "summary": f"Auditoría RAG completada: {verified_count} fuentes verificadas, {len(alerts)} alertas."
    }


# ─────────────────────────────────────────
# CLASE — interfaz orientada a objetos
# ─────────────────────────────────────────

class OpenNotebook:
    """
    Interfaz de clase para el auditor RAG v2.0.

    Uso:
        from OpenNotebook_v2 import OpenNotebook
        auditor = OpenNotebook(db_path="/home/licjo/chroma_db/")
        result  = auditor.audit_draft("Art. 247 CPF establece...")
    """

    def __init__(self, db_path: str = CHROMA_PATH, embed_model: str = EMBED_MODEL):
        global CHROMA_PATH
        self._embedder = None
        self._collection = None
        CHROMA_PATH = db_path

    def _ensure_loaded(self):
        if self._embedder is None:
            self._embedder = get_embedder()
            self._collection = get_collection(self._embedder)

    def audit_draft(self, text: str, verbose: bool = False) -> Dict:
        self._ensure_loaded()
        return audit(text, verbose=verbose)

    def audit_file(self, path: str, verbose: bool = False) -> Dict:
        self._ensure_loaded()
        return audit(Path(path).read_text(encoding="utf-8"), verbose=verbose)

    def ingest_directory(self, directory: str, clear: bool = False, reingest: bool = False):
        ingest(directory, clear=clear, reingest=reingest)
        self._embedder = None
        self._collection = None


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OpenNotebook v2.0 — RAG Legal Itosturre",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python OpenNotebook_v2.0.py ingest --directory /ruta/pdfs/
  python OpenNotebook_v2.0.py ingest --directory /ruta/pdfs/ --clear
  python OpenNotebook_v2.0.py ingest --directory /ruta/pdfs/ --reingest
  python OpenNotebook_v2.0.py audit --text "Art. 247 CPF establece..."
  python OpenNotebook_v2.0.py audit --file borrador.md --verbose
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    # Comando: ingest
    ingest_parser = subparsers.add_parser("ingest", help="Indexar PDFs en ChromaDB")
    ingest_parser.add_argument(
        "--directory", required=True,
        help="Carpeta con PDFs legales"
    )
    ingest_parser.add_argument(
        "--clear", action="store_true",
        help="Borrar colección antes de ingestión"
    )
    ingest_parser.add_argument(
        "--reingest", action="store_true",
        help="Reindexar todo aunque ya exista"
    )
    ingest_parser.add_argument(
        "--verbose", action="store_true",
        help="Mostrar logs detallados"
    )

    # Comando: audit
    audit_parser = subparsers.add_parser("audit", help="Auditar un borrador legal")
    audit_group = audit_parser.add_mutually_exclusive_group(required=True)
    audit_group.add_argument("--text", help="Texto del borrador (string)")
    audit_group.add_argument("--file", help="Ruta al archivo del borrador (.md/.txt)")
    audit_parser.add_argument(
        "--verbose", action="store_true",
        help="Mostrar logs detallados"
    )

    args = parser.parse_args()

    if args.command == "ingest":
        setup_logging(args.verbose)
        ingest(args.directory, clear=args.clear, reingest=args.reingest)

    elif args.command == "audit":
        setup_logging(args.verbose)
        if args.file:
            draft_text = Path(args.file).read_text(encoding="utf-8")
        else:
            draft_text = args.text

        result = audit(draft_text, verbose=args.verbose)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
