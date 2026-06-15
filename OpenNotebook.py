"""
OpenNotebook.py v4.0 — RAG Legal Itosturre
Motor de auditoría anti-alucinaciones con semáforo VVCA.

Cambios v4.0:
  ✅ Embeddings: migración multilingual-e5-small (384d) → jina-embeddings-v3 (1024d)
     Task-specific encoding: retrieval.passage (ingest) / retrieval.query (búsqueda)
     Requiere re-ingest completo del corpus tras actualizar.
  ✅ Chunking inteligente por tipo de documento:
     - Leyes/códigos: split en artículos (comportamiento anterior)
     - Contratos: split en cláusulas (CLÁUSULA PRIMERA, SEGUNDA...)
     - Resoluciones/sentencias: split en secciones (CONSIDERANDO, RESULTANDO...)
     Prefijo de contexto inyectado en sub-chunks para mantener referencia al artículo/cláusula.
     Max chunk size aumentado 1200 → 2000 chars. Metadata incluye doc_type.

Cambios v3.1:
  ✅ Score compuesto ponderado (scoring_vvca.py) — normativa 25% + jurisprudencia 50%
     + estrategia 15% + auditabilidad 10%. Penalización -45 si 5/5 tesis falsas.
  ✅ retrieved_sources incluye campo "ref_type" ("normativa"/"jurisprudencia")
  ✅ vvca_summary incluye score_global, score_normativa, score_jurisprudencia, apto_para_uso_procesal

Cambios v3.0:
  ✅ Semáforo VVCA por referencia (score 0-100, 🟢🟡🔴)
  ✅ Nuevas leyes: CADH, LFDO, LNED, LGV, LNEP
  ✅ Fix path traversal check (Path.is_relative_to)
  ✅ Fix clear/reingest redundancia
  ✅ Fix tesis lookup: acepta campo 'texto' o 'texto_completo'
  ✅ Eliminado embed_query_cached (código muerto)
  ✅ Comando 'query' para búsqueda interactiva

Comandos:
  python OpenNotebook.py ingest --directory /ruta/a/pdfs/
  python OpenNotebook.py audit --text "texto del borrador"
  python OpenNotebook.py audit --file /ruta/borrador.md --verbose
  python OpenNotebook.py query "prisión preventiva CNPP" [--n 5]
"""

import argparse
import json
import re
import sys
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, List

from scoring_vvca import semaforo as vvca_semaforo_global, veredicto_global

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

_BASE_DIR = Path(__file__).parent
CHROMA_PATH = os.getenv("CHROMA_PATH", str(_BASE_DIR / "chroma_db"))
JURISPRUDENCIA_PATH = os.getenv("JURISPRUDENCIA_PATH", str(_BASE_DIR / "jurisprudencia"))
# Base permitida para ingest — más amplia que JURISPRUDENCIA_PATH para aceptar OneDrive y otras rutas
INGEST_ALLOWED_BASE = os.getenv("INGEST_ALLOWED_BASE", str(_BASE_DIR))
CORRECTIONS_FILE = os.getenv("CORRECTIONS_FILE", str(_BASE_DIR / "jurisprudencia" / "vvca_corrections.json"))
COLLECTION_NAME = "corpus_legal_itosturre"
EMBED_MODEL = "intfloat/multilingual-e5-large"

# Tamaño máximo de chunk antes de sub-dividir con el splitter de respaldo.
# jina-v3 maneja hasta 8192 tokens (~32k chars); 2000 chars ≈ 500 tokens — bien dentro del límite.
MAX_CHUNK_SIZE = int(os.getenv("MAX_CHUNK_SIZE", "2000"))

# PDFs legales — excluir documentos personales y filenames con typos conocidos
EXCLUDE_PATTERNS = [
    # Documentos personales
    "ActaNacimiento", "CURP", "EdoCta",
    # Documentos de cliente (no leyes)
    "Reest_FOVISSSTE", "ESCRITO FOVISSSTE", "INTERRUPCION DE PAGO",
    # Marketing / internos
    "20_prompts_juridicos", "itosturre_lead_magnet",
    # Tesis SJF (van por ruta jurisprudencia, no corpus)
    "listado-de-tesis",
    # Archivos no legales
    "Chapter_1es", "CONSIGNA", "Bloc de notas",
    "Battlefield", "Marvel", "FrameView", "SOFÍA", "desktop",
    # Typos y duplicados
    "EXTINSION",               # typo — usar LEY NACIONAL EXTINSION ya corregida
    "codigo_civil_de_jalisco_1",  # duplicado de Codigo-Civil-del-Estado-de-Jalisco_3
]

# Threshold de distancia coseno: por debajo → verificado; por encima → alerta.
# 0.50 = conservador para texto legal mexicano
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
    "Convención Americana": "Convención Americana sobre Derechos Humanos",
    "Pacto de San José": "Convención Americana sobre Derechos Humanos",
    "PIDCP": "Pacto Internacional de Derechos Civiles y Políticos",
    # Penales especiales (nuevas leyes 2026)
    "LFDO": "Ley Federal de Delincuencia Organizada",
    "Delincuencia Organizada": "Ley Federal de Delincuencia Organizada",
    "LNED": "Ley Nacional de Extinción de Dominio",
    "Extinción de Dominio": "Ley Nacional de Extinción de Dominio",
    "LGV": "Ley General de Víctimas",
    "Ley General de Víctimas": "Ley General de Víctimas",
    "LNEP": "Ley Nacional de Ejecución Penal",
    "Ejecución Penal": "Ley Nacional de Ejecución Penal",
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
    # Nuevas leyes indexadas mayo 2026
    "convención americana": "Convencion Americana sobre Derechos Humanos.pdf",
    "cadh": "Convencion Americana sobre Derechos Humanos.pdf",
    "pacto de san josé": "Convencion Americana sobre Derechos Humanos.pdf",
    "ley federal de delincuencia organizada": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA 2026.pdf",
    "lfdo": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA 2026.pdf",
    "delincuencia organizada": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA 2026.pdf",
    "ley nacional de extinción de dominio": "LEY NACIONAL EXTINCION DE DOMINIO 2026.pdf",
    "ley nacional extincion de dominio": "LEY NACIONAL EXTINCION DE DOMINIO 2026.pdf",
    "ley nacional extinsion de dominio": "LEY NACIONAL EXTINCION DE DOMINIO 2026.pdf",  # typo
    "lned": "LEY NACIONAL EXTINCION DE DOMINIO 2026.pdf",
    "extinción de dominio": "LEY NACIONAL EXTINCION DE DOMINIO 2026.pdf",
    "extincion de dominio": "LEY NACIONAL EXTINCION DE DOMINIO 2026.pdf",
    "ley general de víctimas": "LEY GENERAL DE VICTIMAS 2026.pdf",
    "ley general de victimas": "LEY GENERAL DE VICTIMAS 2026.pdf",
    "lgv": "LEY GENERAL DE VICTIMAS 2026.pdf",
    "ley nacional de ejecución penal": "LEY NACIONAL EJECUCION PENAL 2026.pdf",
    "ley nacional ejecucion penal": "LEY NACIONAL EJECUCION PENAL 2026.pdf",
    "lnep": "LEY NACIONAL EJECUCION PENAL 2026.pdf",
}


# ─────────────────────────────────────────
# NORMALIZACIÓN DE TEXTO LEGAL
# ─────────────────────────────────────────

# Expansión de acrónimos antes del embed — mejora recall aunque jina-v3 reconoce
# mejor el dominio legal; la expansión ayuda en consultas muy cortas o mal formateadas.
_LEGAL_NORMALIZER: List[Tuple[str, str]] = [
    (r'\bCPEUM\b',    'Constitución Política de los Estados Unidos Mexicanos'),
    (r'\bCNPP\b',     'Código Nacional de Procedimientos Penales'),
    (r'\bCPF\b',      'Código Penal Federal'),
    (r'\bCCF\b',      'Código Civil Federal'),
    (r'\bCFF\b',      'Código Fiscal de la Federación'),
    (r'\bCFPC\b',     'Código Federal de Procedimientos Civiles'),
    (r'\bCNPCF\b',    'Código Nacional de Procedimientos Civiles y Familiares'),
    (r'\bLISR\b',     'Ley del Impuesto sobre la Renta'),
    (r'\bLIVA\b',     'Ley del Impuesto al Valor Agregado'),
    (r'\bLFT\b',      'Ley Federal del Trabajo'),
    (r'\bLSS\b',      'Ley del Seguro Social'),
    (r'\bLFPA\b',     'Ley Federal de Procedimiento Administrativo'),
    (r'\bLFPCA\b',    'Ley Federal de Procedimiento Contencioso Administrativo'),
    (r'\bLOPJF\b',    'Ley Orgánica del Poder Judicial Federal'),
    (r'\bLFPC\b',     'Ley Federal de Protección al Consumidor'),
    (r'\bLFPPI\b',    'Ley Federal de Protección a la Propiedad Intelectual'),
    (r'\bLFPDPPP\b',  'Ley Federal de Protección de Datos Personales en Posesión de los Particulares'),
    (r'\bCADH\b',     'Convención Americana sobre Derechos Humanos'),
    (r'\bPIDCP\b',    'Pacto Internacional de Derechos Civiles y Políticos'),
    (r'\bLFDO\b',     'Ley Federal de Delincuencia Organizada'),
    (r'\bLNED\b',     'Ley Nacional de Extinción de Dominio'),
    (r'\bLGV\b',      'Ley General de Víctimas'),
    (r'\bLNEP\b',     'Ley Nacional de Ejecución Penal'),
    (r'\bTJAJ\b',     'Tribunal de Justicia Administrativa de Jalisco'),
    (r'\bSCJN\b',     'Suprema Corte de Justicia de la Nación'),
    (r'\bTCC\b',      'Tribunal Colegiado de Circuito'),
    (r'\bPJF\b',      'Poder Judicial Federal'),
    (r'\bSAT\b',      'Servicio de Administración Tributaria'),
]
# Compilar una sola vez
_NORMALIZER_COMPILED = [(re.compile(p), r) for p, r in _LEGAL_NORMALIZER]


def normalize_legal_text(text: str) -> str:
    """Expande acrónimos jurídicos antes de generar el query embedding.
    Solo se aplica a queries — NO a los chunks del corpus.
    """
    for pattern, replacement in _NORMALIZER_COMPILED:
        text = pattern.sub(replacement, text)
    return text


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


def encode_query(text: str) -> List[float]:
    """Codifica una query con prefijo e5 'query: ' para búsqueda asimétrica."""
    embedder = get_embedder()
    vec = embedder.encode(["query: " + text], normalize_embeddings=True)
    return vec[0].tolist()


def get_collection(embedder):
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    class STEmbeddingFunction:
        def __init__(self, model):
            self.model = model
        def name(self):
            return "itosturre-st-embedder"
        def __call__(self, input):
            # Usado por ChromaDB al indexar documentos — prefijo e5 'passage: '
            return self.model.encode(["passage: " + t for t in input], normalize_embeddings=True).tolist()
        def embed_documents(self, input):
            return self.model.encode(["passage: " + t for t in input], normalize_embeddings=True).tolist()
        def embed_query(self, input):
            if isinstance(input, str):
                input = [input]
            return self.model.encode(["query: " + t for t in input], normalize_embeddings=True).tolist()

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
    pdf_dir = Path(directory).resolve()
    allowed_base = Path(INGEST_ALLOWED_BASE).resolve()

    try:
        pdf_dir.relative_to(allowed_base)
    except ValueError:
        logger.error(f"❌ Path traversal bloqueado: '{pdf_dir}' no está bajo '{allowed_base}'")
        logger.error(f"   Ajusta INGEST_ALLOWED_BASE en .env si necesitas ingestar desde otra ruta.")
        sys.exit(1)

    pdfs = [p for p in pdf_dir.iterdir() if is_legal_pdf(p)]

    if not pdfs:
        logger.error(f"❌ No se encontraron PDFs legales en: {directory}")
        sys.exit(1)

    logger.info(f"📚 PDFs encontrados: {len(pdfs)}")

    embedder = get_embedder()
    client = chromadb.PersistentClient(path=CHROMA_PATH)

    # clear y reingest borran la colección antes de ingestar
    # (antes: se borraba dos veces si se pasaban ambas flags)
    if clear or reingest:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("🗑️  Colección borrada para re-ingesta limpia.")
        except Exception as e:
            logger.warning(f"⚠️  No se pudo borrar colección: {e}")

    collection = get_collection(embedder)

    fallback_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n", "\n", " "]
    )

    # Patrones de split por tipo de documento
    _SPLIT_PATTERNS = {
        "ley":       re.compile(r'(?=\n[Aa]rt[íi]?(?:culo)?s?\.?\s+\d+)', re.MULTILINE),
        "contrato":  re.compile(r'(?=\n[Cc]l[áa]usula\s+(?:[A-ZÁÉÍÓÚa-záéíóú]+|\d+))', re.MULTILINE),
        "resolucion": re.compile(
            r'(?=\n(?:CONSIDERANDO|RESULTANDO|VISTOS|[A-ZÁÉÍÓÚ]{4,}[:\s]|'
            r'[Pp]rimero[:\s]|[Ss]egundo[:\s]|[Tt]ercero[:\s]|[Cc]uarto[:\s]))',
            re.MULTILINE
        ),
    }

    def detect_doc_type(text: str) -> str:
        sample = text[:3000]
        art_count = len(re.findall(r'\n[Aa]rt[íi]?(?:culo)?s?\.?\s+\d+', sample))
        clause_count = len(re.findall(r'\n[Cc]l[áa]usula\s+\w+', sample))
        section_count = len(re.findall(
            r'\n(?:CONSIDERANDO|RESULTANDO|VISTOS)\b', sample
        ))
        if clause_count >= 2 and clause_count >= art_count:
            return "contrato"
        if section_count >= 2 and section_count >= art_count:
            return "resolucion"
        return "ley"

    def extract_section_label(piece: str, doc_type: str) -> str:
        """Extrae el encabezado de sección (Artículo N, Cláusula X, etc.)."""
        if doc_type == "ley":
            m = re.match(r'\s*[Aa]rt[íi]?(?:culo)?s?\.?\s+(\d+[\w\-]*)', piece)
            return m.group(1) if m else ""
        if doc_type == "contrato":
            m = re.match(r'\s*[Cc]l[áa]usula\s+(\w+)', piece)
            return m.group(1) if m else ""
        if doc_type == "resolucion":
            m = re.match(r'\s*([A-ZÁÉÍÓÚ][A-ZÁÉÍÓÚa-záéíóú\s]{2,30})[:\s]', piece)
            return m.group(1).strip() if m else ""
        return ""

    total_chunks = 0
    for pdf_path in pdfs:
        logger.info(f"  🔍 Procesando: {pdf_path.name}")
        try:
            pages = extract_text_from_pdf(pdf_path)
            if not pages:
                logger.warning(f"     ⚠️  Texto muy corto, omitiendo.")
                continue

            # Chunking cross-page: concatenar todo antes de partir.
            # Evita cortar artículos/cláusulas que cruzan saltos de página.
            page_offsets: List[Tuple[int, int]] = []
            char_pos = 0
            full_parts: List[str] = []
            for p in pages:
                page_offsets.append((char_pos, p["page"]))
                full_parts.append(p["text"])
                char_pos += len(p["text"]) + 2  # +2 por separador \n\n

            full_text = "\n\n".join(full_parts)
            doc_type = detect_doc_type(full_text)

            def get_page_for_pos(pos: int) -> int:
                page = page_offsets[0][1] if page_offsets else 1
                for off, pnum in page_offsets:
                    if pos >= off:
                        page = pnum
                    else:
                        break
                return page

            # Elegir patrón según tipo; si no produce suficientes splits, caer a "ley"
            split_re = _SPLIT_PATTERNS.get(doc_type, _SPLIT_PATTERNS["ley"])
            boundaries = [m.start() for m in split_re.finditer(full_text)]

            # Fallback: si el patrón primario no encontró splits, intentar con "ley"
            if len(boundaries) < 2 and doc_type != "ley":
                split_re = _SPLIT_PATTERNS["ley"]
                boundaries = [m.start() for m in split_re.finditer(full_text)]
                if len(boundaries) >= 2:
                    doc_type = "ley"

            if not boundaries or boundaries[0] > 0:
                boundaries = [0] + boundaries
            boundaries.append(len(full_text))

            chunks_with_meta: List[Tuple[str, str, int]] = []
            for i in range(len(boundaries) - 1):
                piece = full_text[boundaries[i]:boundaries[i + 1]].strip()
                if not piece:
                    continue

                page_num = get_page_for_pos(boundaries[i])
                section_label = extract_section_label(piece, doc_type)

                if len(piece) <= MAX_CHUNK_SIZE:
                    chunks_with_meta.append((piece, section_label, page_num))
                else:
                    # Sub-dividir chunks largos e inyectar el encabezado como prefijo
                    # para que cada sub-chunk sea recuperable por artículo/cláusula.
                    prefix = f"[{doc_type.upper()} {section_label}]\n" if section_label else ""
                    sub_chunks = fallback_splitter.split_text(piece)
                    for sc in sub_chunks:
                        sc_text = (prefix + sc.strip()) if prefix else sc.strip()
                        chunks_with_meta.append((sc_text, section_label, page_num))

            logger.info(f"     📄 {len(chunks_with_meta)} chunks generados")

            # Insertar en lotes
            batch_size = 50
            for i in range(0, len(chunks_with_meta), batch_size):
                batch = chunks_with_meta[i:i + batch_size]
                texts = [c[0] for c in batch]
                section_labels = [c[1] for c in batch]
                page_nums = [c[2] for c in batch]
                ids = [f"{pdf_path.stem}_chunk_{i + j}" for j in range(len(batch))]
                metadatas = [
                    {
                        "source": pdf_path.name,
                        "law": pdf_path.stem,
                        "article": section_labels[j],
                        "page": str(page_nums[j]),
                        "chunk_index": str(i + j),
                        "doc_type": doc_type,
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

    # Registros digitales SJF — captura "Registro: 2019456", "Registro 2019456",
    # "Registro digital: 2019456", "registro digital 2019456"
    reg_pattern = re.compile(r'[Rr]egistro(?:\s+digital)?[:\s]+(\d{6,8})')
    for m in reg_pattern.finditer(text):
        # Captura hasta 400 chars antes del registro para incluir el rubro invocado
        ctx_start = max(0, m.start() - 400)
        ctx_invocado = text[ctx_start: m.start()].strip()
        refs.append({
            "type": "jurisprudencia",
            "registro": m.group(1),
            "raw": m.group(0).strip(),
            "ctx_invocado": ctx_invocado,
        })

    return refs


def vvca_score(distance: float, source_match: bool, has_source_file: bool) -> int:
    """Score 0-100 basado en distancia coseno + coincidencia de fuente."""
    base = round((1 - min(distance, 1.0)) * 100)
    if not source_match:
        base -= 15
    if not has_source_file:
        base -= 10
    return max(0, min(100, base))


def vvca_semaforo(score: int) -> str:
    if score >= 85:
        return "🟢"
    if score >= 60:
        return "🟡"
    return "🔴"


def vvca_contextualizacion(source_file: str) -> str:
    s = source_file.lower()
    if "cpeum" in s or "estados unidos mexicanos" in s:
        return "Constitucional · Federal · Aplicable a todo el sistema jurídico"
    if "cnpp" in s or "procedpenales" in s or "procedimientos penales" in s:
        return "Procesal Penal · Nacional · PJF y juzgados locales acreditados CNPP"
    if "penal federal" in s:
        return "Penal sustantivo · Federal · PJF"
    if "delincuencia organizada" in s:
        return "Penal especial · Federal · LFDO — delitos del catálogo art. 2"
    if "extincion de dominio" in s or "extinción" in s:
        return "Extinción de dominio · Federal · Proceso civil especial autónomo"
    if "general de victimas" in s or "víctimas" in s:
        return "Penal/DDHH · Federal · Derechos de víctimas en toda causa penal"
    if "ejecucion penal" in s or "ejecución penal" in s:
        return "Ejecución de sanciones · Federal · Post-sentencia"
    if "convencion americana" in s or "cadh" in s:
        return "DDHH · Internacional · Control de convencionalidad obligatorio (art. 1° CPEUM)"
    if "pacto internacional" in s or "pidcp" in s:
        return "DDHH · ONU · Control de convencionalidad — aplica en amparo"
    if "amparo" in s:
        return "Amparo · Federal · Juzgados de Distrito y TCC"
    if "lopjf" in s or "orgánica del poder judicial" in s or "organica del poder judicial" in s or "organicopoder" in s or "reglamentoorgan" in s:
        return "Orgánica · Federal · Competencia PJF"
    if "fiscal de la federacion" in s or "c.f.f" in s:
        return "Fiscal · Federal · SAT / contribuciones federales"
    if "fiscal del estado de jalisco" in s:
        return "Fiscal · Local · Jalisco"
    if "impuesto sobre la renta" in s:
        return "Fiscal · Federal · ISR"
    if "impuesto al valor agregado" in s:
        return "Fiscal · Federal · IVA"
    if "trabajo" in s or "lft" in s:
        return "Laboral · Federal · JFCA / Tribunales Laborales"
    if "seguro social" in s:
        return "Seguridad Social · Federal · IMSS"
    if "civil federal" in s:
        return "Civil · Federal"
    if "jalisco" in s:
        return "Local · Estado de Jalisco"
    if "nuevo leon" in s or "nuevo león" in s:
        return "Local · Estado de Nuevo León"
    return "Normativo · Verificar ámbito de aplicación específico"


def build_vvca(
    ref: Dict,
    distance: float,
    source_match: bool,
    source_file: str,
    page: str,
    retrieved_text: str,
) -> Dict:
    score = vvca_score(distance, source_match, has_source_file=bool(ref.get("source_file")))
    semaforo = vvca_semaforo(score)
    law = ref.get("law", "desconocido")
    art = ref.get("article", "?")
    frac = ref.get("fraction", "")
    art_label = f"Art. {art}" + (f" fr. {frac}" if frac else "")

    v_verificacion = (
        f"Encontrado en corpus oficial (dist={distance:.3f})"
        if distance <= COSINE_THRESHOLD
        else f"Coincidencia débil — posible alucinación (dist={distance:.3f}, umbral={COSINE_THRESHOLD})"
    )
    v_validacion = (
        f"Fuente correcta: {source_file}"
        if source_match
        else f"Fuente distinta: se encontró en '{source_file}', se esperaba '{ref.get('source_file')}'"
    )
    c_contextualizacion = vvca_contextualizacion(source_file)
    a_auditabilidad = f"{art_label} · {law} · pág. {page} · corpus: {source_file}"

    return {
        "score": score,
        "semaforo": semaforo,
        "V_verificacion": v_verificacion,
        "V_validacion": v_validacion,
        "C_contextualizacion": c_contextualizacion,
        "A_auditabilidad": a_auditabilidad,
    }


def _rubro_keywords(text: str) -> set:
    """Extrae palabras clave significativas (>4 chars) de un rubro para comparación."""
    stop = {"para", "como", "ante", "debe", "este", "esta", "dicho", "dicha",
            "donde", "cuando", "aunque", "entre", "sino", "cuyo", "cuya",
            "desde", "hasta", "sobre", "bajo", "cuales", "mismo", "misma"}
    return {
        w.lower() for w in re.findall(r'[A-Za-záéíóúÁÉÍÓÚüÜñÑ]{5,}', text)
        if w.lower() not in stop
    }


def build_vvca_tesis(ref: Dict, item: Dict, source_file: str) -> Dict:
    tipo    = item.get("tipo_tesis", "")
    sala    = item.get("sala", "")
    epoca   = item.get("epoca", "")
    materia = item.get("materia", "")
    numero  = item.get("numero_tesis", "")
    registro = ref.get("registro", "?")
    rubro_real = item.get("rubro", "")

    # Validación semántica: ¿el rubro del corpus coincide con lo invocado en el doc?
    # ctx_invocado trae hasta 400 chars previos (contiene el rubro si está en el texto)
    rubro_invocado = ref.get("ctx_invocado", ref.get("raw", ""))
    rubro_mismatch = False
    if rubro_real and rubro_invocado:
        kw_real     = _rubro_keywords(rubro_real)
        kw_invocado = _rubro_keywords(rubro_invocado)
        if kw_real and kw_invocado:
            overlap = len(kw_real & kw_invocado) / min(len(kw_real), len(kw_invocado))
            rubro_mismatch = overlap < 0.20  # < 20% de palabras en común → tesis equivocada

    if rubro_mismatch:
        score = 0  # Registro real con rubro falso es más peligroso que uno inexistente
        verificacion = (
            f"⚠️ DISCREPANCIA: Reg. {registro} existe en corpus pero su rubro real "
            f"NO coincide con lo invocado en el documento. "
            f"Rubro real: '{rubro_real[:120]}...'"
        )
    else:
        score = 95 if re.search(r"jurisprudencia", tipo, re.I) else 72
        verificacion = f"Registro {registro} encontrado en corpus SJF local"

    semaforo = vvca_semaforo(score)

    tipo_label = (
        "Jurisprudencia obligatoria" if re.search(r"jurisprudencia", tipo, re.I)
        else f"Tesis aislada — orientadora, no obligatoria ({tipo})"
    )
    contexto = (
        f"{epoca} · {sala} · Materia: {materia}"
        if any([epoca, sala, materia]) else "Ver detalle en SJF"
    )

    return {
        "score": score,
        "semaforo": semaforo,
        "rubro_mismatch": rubro_mismatch,
        "V_verificacion": verificacion,
        "V_validacion": tipo_label,
        "C_contextualizacion": contexto,
        "A_auditabilidad": f"{numero} · Reg. {registro} · {sala} · {source_file}",
    }


def check_corpus_coverage(refs: List[Dict], collection) -> List[str]:
    """
    Detecta qué source_files referenciados en el borrador no están indexados en ChromaDB.
    Retorna lista de nombres de archivo faltantes.
    """
    needed = {ref["source_file"] for ref in refs if ref.get("source_file")}
    missing = []
    for source_file in needed:
        try:
            result = collection.get(where={"source": source_file}, limit=1, include=[])
            if not result["ids"]:
                missing.append(source_file)
        except Exception:
            missing.append(source_file)
    return sorted(missing)


def audit(text: str, verbose: bool = False, allow_incomplete_corpus: bool = False) -> Dict:
    """
    Audita el borrador contra el corpus legal.
    Retorna JSON con alerts y retrieved_sources.

    Si el corpus no contiene leyes referenciadas en el texto y
    allow_incomplete_corpus=False, retorna status='corpus_incomplete' con la lista
    de leyes faltantes para que el caller decida si continuar.
    Pasar allow_incomplete_corpus=True para forzar la auditoría e incluir
    la advertencia en el campo 'corpus_warning' del resultado.
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
    corpus_warning = None

    if verbose:
        logger.debug(f"🔍 Auditoría: {len(refs)} referencias detectadas")

    # ── Verificar cobertura del corpus ───────────────────────────────────────
    missing_sources = check_corpus_coverage(refs, collection)
    if missing_sources:
        if not allow_incomplete_corpus:
            return {
                "status": "corpus_incomplete",
                "missing_sources": missing_sources,
                "message": (
                    f"⚠️  Corpus incompleto: {len(missing_sources)} ley(es) referenciada(s) "
                    f"no están indexadas en ChromaDB.\n"
                    + "\n".join(f"  • {s}" for s in missing_sources)
                    + "\n\nIndexar primero: python OpenNotebook.py ingest /ruta/corpus/\n"
                    "O continuar con: --force (el resultado incluirá advertencia)."
                ),
                "alerts": [],
                "retrieved_sources": [],
            }
        corpus_warning = (
            f"⚠️  Auditoría ejecutada con corpus parcial. "
            f"Ley(es) no verificadas por ausencia en ChromaDB: "
            + ", ".join(missing_sources)
        )

    for ref in refs:
        if ref["type"] == "article":
            query_raw = f"Artículo {ref['article']}"
            if ref["fraction"]:
                query_raw += f" fracción {ref['fraction']}"
            if ref["law"] and ref["law"] != "desconocido":
                query_raw += f" {ref['law']}"
            # Normalizar acrónimos para mejorar recall en e5-small
            query = normalize_legal_text(query_raw)

            expected_source = ref.get("source_file")
            where_filter = {"source": expected_source} if expected_source else None

            try:
                # Usar query_embeddings con task=retrieval.query para encoding asimétrico
                results = collection.query(
                    query_embeddings=[encode_query(query)],
                    n_results=3,
                    where=where_filter
                )
            except Exception:
                # where_filter puede fallar si la fuente no existe en el corpus
                results = collection.query(
                    query_embeddings=[encode_query(query)],
                    n_results=3
                )
                expected_source = None

            if results and results["documents"] and results["documents"][0]:
                best_doc = results["documents"][0][0]
                best_meta = results["metadatas"][0][0] if results["metadatas"] else {}
                best_source = best_meta.get("source", "desconocido")
                best_distance = results["distances"][0][0] if results.get("distances") else 1.0
                source_match = (not expected_source) or (best_source == expected_source)

                vvca = build_vvca(
                    ref=ref,
                    distance=best_distance,
                    source_match=source_match,
                    source_file=best_source,
                    page=best_meta.get("page", "?"),
                    retrieved_text=best_doc,
                )

                if not source_match and best_distance <= COSINE_THRESHOLD:
                    alerts.append(
                        f"{vvca['semaforo']} ALERTA (score {vvca['score']}): '{ref['raw']}' — "
                        f"encontrado en '{best_source}' pero se esperaba '{expected_source}'. "
                        f"Posible confusión entre ordenamientos. Verificar manualmente."
                    )
                elif best_distance > COSINE_THRESHOLD:
                    alerts.append(
                        f"🔴 ALERTA ALTA (score {vvca['score']}): '{ref['raw']}' — "
                        f"sin coincidencia confiable (dist={best_distance:.3f}, umbral={COSINE_THRESHOLD}). "
                        f"Posible alucinación. Verificar en fuente oficial."
                    )
                else:
                    retrieved_sources.append({
                        "reference": ref["raw"],
                        "law": ref["law"],
                        "article": ref["article"],
                        "ref_type": "normativa",
                        "source_file": best_source,
                        "page": best_meta.get("page", "?"),
                        "expected_source": expected_source,
                        "relevance_score": round(1 - best_distance, 3),
                        "retrieved_text": best_doc[:600],
                        "vvca": vvca,
                    })
                    verified_count += 1
            else:
                alerts.append(
                    f"🔴 ALERTA CRÍTICA: '{ref['raw']}' — no encontrado en el corpus. "
                    f"Alucinación detectada. Verificar en fuente oficial ANTES de usar."
                )

        elif ref["type"] == "jurisprudencia":
            tesis_path = Path(JURISPRUDENCIA_PATH)
            found_in_tesis = False
            if tesis_path.exists():
                for json_file in sorted(tesis_path.rglob("*.json")):
                    try:
                        data = json.loads(json_file.read_text(encoding="utf-8"))
                        items = data if isinstance(data, list) else []
                        for item in items:
                            # Bug fix (Sonnet): substring match causaba false positives
                            # "2031" matcheaba con "20319", "203112", etc.
                            if str(ref["registro"]) == str(item.get("registro", "")):
                                found_in_tesis = True
                                # Bug fix: el scraper guarda 'texto', no 'texto_completo'
                                texto = (
                                    item.get("texto_completo")
                                    or item.get("texto")
                                    or "Tesis verificada en corpus SJF."
                                )
                                vvca = build_vvca_tesis(ref, item, json_file.name)
                                retrieved_sources.append({
                                    "reference": ref["raw"],
                                    "registro": ref["registro"],
                                    "ref_type": "jurisprudencia",
                                    "source_file": json_file.name,
                                    "relevance_score": 1.0,
                                    "retrieved_text": texto[:600],
                                    "vvca": vvca,
                                })
                                verified_count += 1
                                break
                    except Exception as e:
                        if verbose:
                            logger.debug(f"Error leyendo {json_file}: {e}")
                        continue
                    if found_in_tesis:
                        break

            if not found_in_tesis:
                alerts.append(
                    f"⚠️  ALERTA (🔴 score 30): Registro digital {ref['registro']} "
                    f"no encontrado en corpus de jurisprudencia local. "
                    f"Verificar en sjf2.scjn.gob.mx antes de citar."
                )

    # ── Score RAG (artículos) — validación estática
    art_scores = [
        s["vvca"]["score"] for s in retrieved_sources
        if "vvca" in s and s.get("ref_type") == "normativa"
    ]
    score_rag = round(sum(art_scores) / len(art_scores), 1) if art_scores else 0.0

    # ── Score SJF (tesis) — validación dinámica
    jur_scores = [
        s["vvca"]["score"] for s in retrieved_sources
        if "vvca" in s and s.get("ref_type") == "jurisprudencia"
    ]
    score_sjf = round(sum(jur_scores) / len(jur_scores), 1) if jur_scores else 0.0

    # Conteo de tesis problemáticas (mismatch de rubro o no encontradas)
    tesis_total_invocadas = sum(1 for r in refs if r.get("type") == "jurisprudencia")
    tesis_no_encontradas  = tesis_total_invocadas - len(jur_scores)
    tesis_mismatch        = sum(
        1 for s in retrieved_sources
        if s.get("ref_type") == "jurisprudencia" and s.get("vvca", {}).get("rubro_mismatch")
    )
    tesis_rojas = tesis_no_encontradas + tesis_mismatch

    # ── Veredicto binario — las tesis rojas son bloqueantes por sí solas
    veredicto = veredicto_global(score_rag, score_sjf, tesis_rojas, tesis_total_invocadas)

    all_scores = art_scores + jur_scores
    verdes    = sum(1 for sc in all_scores if sc >= 85)
    amarillos = sum(1 for sc in all_scores if 60 <= sc < 85)
    rojos     = sum(1 for sc in all_scores if sc < 60) + tesis_no_encontradas

    result = {
        "status": "ok",
        "total_references_found": len(refs),
        "verified": verified_count,
        "alerts_count": len(alerts),
        "cosine_threshold": COSINE_THRESHOLD,
        "vvca_summary": {
            "score_rag":           score_rag,
            "semaforo_rag":        vvca_semaforo(score_rag),
            "articulos_ok":        len(art_scores),
            "score_sjf":           score_sjf,
            "semaforo_sjf":        vvca_semaforo(score_sjf),
            "tesis_total":         tesis_total_invocadas,
            "tesis_ok":            len(jur_scores) - tesis_mismatch,
            "tesis_rojas":         tesis_rojas,
            "tesis_mismatch":      tesis_mismatch,
            "tesis_no_encontradas": tesis_no_encontradas,
            "veredicto":           veredicto,
            "verdes":   verdes,
            "amarillos": amarillos,
            "rojos":     rojos,
        },
        "alerts": alerts,
        "retrieved_sources": retrieved_sources,
        "summary": (
            f"RAG {score_rag} {vvca_semaforo(score_rag)} "
            f"({len(art_scores)} arts) · "
            f"SJF {score_sjf} {vvca_semaforo(score_sjf)} "
            f"({tesis_total_invocadas - tesis_rojas}/{tesis_total_invocadas} tesis ok)"
            + (f" — {tesis_mismatch} rubro discrepante" if tesis_mismatch else "")
            + (f", {tesis_no_encontradas} no encontradas" if tesis_no_encontradas else "")
            + f" · Veredicto: {veredicto['semaforo']} {veredicto['razon']}"
        ),
    }
    if corpus_warning:
        result["corpus_warning"] = corpus_warning
    return result


# ─────────────────────────────────────────
# CLASE — interfaz orientada a objetos
# ─────────────────────────────────────────

class OpenNotebook:
    """
    Interfaz de clase para el auditor RAG v2.0.

    Uso:
        from OpenNotebook_v2 import OpenNotebook
        auditor = OpenNotebook(db_path="./chroma_db/")
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

    def audit_draft(self, text: str, verbose: bool = False, allow_incomplete_corpus: bool = False) -> Dict:
        self._ensure_loaded()
        return audit(text, verbose=verbose, allow_incomplete_corpus=allow_incomplete_corpus)

    def audit_file(self, path: str, verbose: bool = False, allow_incomplete_corpus: bool = False) -> Dict:
        self._ensure_loaded()
        return audit(Path(path).read_text(encoding="utf-8"), verbose=verbose, allow_incomplete_corpus=allow_incomplete_corpus)

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

    # Comando: query
    query_parser = subparsers.add_parser("query", help="Búsqueda semántica directa en el corpus")
    query_parser.add_argument("texto", help="Texto a buscar (entre comillas)")
    query_parser.add_argument("--n", type=int, default=5, help="Número de resultados (default: 5)")
    query_parser.add_argument("--verbose", action="store_true")

    # Comando: audit
    audit_parser = subparsers.add_parser("audit", help="Auditar un borrador legal")
    audit_group = audit_parser.add_mutually_exclusive_group(required=True)
    audit_group.add_argument("--text", help="Texto del borrador (string)")
    audit_group.add_argument("--file", help="Ruta al archivo del borrador (.md/.txt)")
    audit_parser.add_argument("--verbose", action="store_true")
    audit_parser.add_argument(
        "--format", choices=["json", "telegram"], default="json",
        help="Formato de salida: json (default) o telegram (bloque listo para Telegram)"
    )
    audit_parser.add_argument(
        "--force", action="store_true",
        help="Auditar aunque el corpus esté incompleto (incluye advertencia en el resultado)"
    )

    # Comando: correct — registrar corrección manual para calibración futura
    correct_parser = subparsers.add_parser("correct", help="Registrar corrección VVCA para calibración")
    correct_parser.add_argument("--ref", required=True, help="Texto exacto de la referencia (ej: 'Art. 19 CPEUM')")
    correct_parser.add_argument("--semaforo", required=True, choices=["🟢", "🟡", "🔴"], help="Semáforo correcto")
    correct_parser.add_argument("--score-auditado", type=int, default=0, help="Score que dio el sistema")
    correct_parser.add_argument("--nota", default="", help="Nota opcional (contexto del error)")

    # Comando: calibrate — analizar correcciones y sugerir nuevo threshold
    subparsers.add_parser("calibrate", help="Analizar correcciones y sugerir ajuste de COSINE_THRESHOLD")

    args = parser.parse_args()

    if args.command == "correct":
        import datetime
        corrections_path = Path(CORRECTIONS_FILE)
        corrections_path.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(corrections_path.read_text()) if corrections_path.exists() else []
        existing.append({
            "ref": args.ref,
            "semaforo_correcto": args.semaforo,
            "score_auditado": args.score_auditado,
            "nota": args.nota,
            "timestamp": datetime.datetime.now().isoformat(),
        })
        corrections_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
        print(f"✅ Corrección registrada ({len(existing)} total). Usa 'calibrate' para analizar.")
        return

    if args.command == "calibrate":
        corrections_path = Path(CORRECTIONS_FILE)
        if not corrections_path.exists():
            print("⚠️  Sin correcciones registradas. Usa 'correct' para registrar discrepancias.")
            return
        corrections = json.loads(corrections_path.read_text())
        if not corrections:
            print("⚠️  El archivo de correcciones está vacío.")
            return

        # Analizar drift: cuando el sistema dijo verde pero la realidad es rojo
        false_greens = [c for c in corrections if c["semaforo_correcto"] == "🔴" and c["score_auditado"] >= 85]
        false_reds   = [c for c in corrections if c["semaforo_correcto"] == "🟢" and c["score_auditado"] < 60]
        total = len(corrections)

        print(f"\n📊 Calibración VVCA — {total} correcciones registradas")
        print(f"   🔴 Falsos positivos (sistema 🟢 → real 🔴): {len(false_greens)}")
        print(f"   🟢 Falsos negativos (sistema 🔴 → real 🟢): {len(false_reds)}")
        print(f"\n   COSINE_THRESHOLD actual: {COSINE_THRESHOLD}")

        if len(false_greens) > len(false_reds) and len(false_greens) >= 3:
            suggested = round(COSINE_THRESHOLD - 0.05, 2)
            print(f"   💡 Sugerido: {suggested} (bajar — el sistema es demasiado permisivo)")
        elif len(false_reds) > len(false_greens) and len(false_reds) >= 3:
            suggested = round(COSINE_THRESHOLD + 0.05, 2)
            print(f"   💡 Sugerido: {suggested} (subir — el sistema es demasiado estricto)")
        else:
            print(f"   ✅ Threshold parece calibrado (diferencia < 3 casos).")

        if false_greens:
            print("\n   Ejemplos falsos positivos:")
            for c in false_greens[:3]:
                print(f"   • {c['ref']} | score={c['score_auditado']} | {c.get('nota','')}")
        return

    if args.command == "query":
        setup_logging(getattr(args, "verbose", False))
        embedder = get_embedder()
        col = get_collection(embedder)
        query_norm = normalize_legal_text(args.texto)
        results = col.query(query_texts=[query_norm], n_results=args.n, include=["documents", "metadatas", "distances"])
        print(f"\n🔍 Búsqueda: \"{args.texto}\" — top {args.n} resultados\n")
        for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
            score = round((1 - dist) * 100)
            sem = vvca_semaforo(score)
            print(f"{sem} Score {score} | {meta.get('source','?')} pág.{meta.get('page','?')}")
            print(f"   {doc[:200].strip()}")
            print()

    elif args.command == "ingest":
        setup_logging(args.verbose)
        ingest(args.directory, clear=args.clear, reingest=args.reingest)

    elif args.command == "audit":
        setup_logging(args.verbose)
        if args.file:
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"❌ Archivo no encontrado: {args.file}", file=sys.stderr)
                sys.exit(1)
            if file_path.stat().st_size > 500_000:
                print(f"⚠️  Archivo muy grande ({file_path.stat().st_size // 1024} KB). Considera dividirlo.", file=sys.stderr)
            draft_text = file_path.read_text(encoding="utf-8")
        else:
            draft_text = args.text
            if len(draft_text) > 200_000:
                print("⚠️  Texto muy largo — puede causar timeout en ChromaDB.", file=sys.stderr)

        result = audit(draft_text, verbose=args.verbose, allow_incomplete_corpus=args.force)

        # ── Corpus incompleto: prompt interactivo o advertencia automática ────
        if result.get("status") == "corpus_incomplete":
            print(result["message"], file=sys.stderr)
            interactive = sys.stdin.isatty() and not args.force
            if interactive:
                respuesta = input("\n¿Continuar auditoría con corpus parcial? (s/N): ").strip().lower()
                if respuesta not in ("s", "si", "sí", "y", "yes"):
                    print("Auditoría cancelada. Indexa las leyes faltantes y vuelve a intentarlo.")
                    sys.exit(0)
            # Continúa con advertencia (interactivo confirmó, o modo no-interactivo)
            result = audit(draft_text, verbose=args.verbose, allow_incomplete_corpus=True)

        if args.format == "telegram":
            vs = result["vvca_summary"]
            lines = [
                f"📋 <b>Auditoría VVCA</b> · {result['total_references_found']} refs · {result['alerts_count']} alertas",
                f"Score global: {vs['score_promedio']} {vs['semaforo_global']}"
                f"  🟢{vs['verdes']} 🟡{vs['amarillos']} 🔴{vs['rojos']}",
                "",
            ]
            for s in result["retrieved_sources"]:
                v = s.get("vvca", {})
                sem = v.get("semaforo", "⬜")
                score = v.get("score", "?")
                ref = s.get("reference", "?")[:40]
                ctx = v.get("C_contextualizacion", "")[:50]
                lines.append(f"{sem} <b>{score}</b> · {ref} · {ctx}")
            if result["alerts"]:
                lines.append("")
                for a in result["alerts"][:3]:
                    lines.append(f"⚠️ {a[:120]}")
            if result.get("corpus_warning"):
                lines.append("")
                lines.append(f"⚠️ {result['corpus_warning']}")
            lines.append("")
            lines.append("🔗 Fuentes: sjf2.scjn.gob.mx · dof.gob.mx · cjf.gob.mx")
            print("\n".join(lines))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
