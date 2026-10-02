"""
OpenNotebook.py v4.0 — RAG Legal Itosturre
Motor de auditoría anti-alucinaciones con semáforo VVCA.

Cambios R4b (extracción de referencias y resolución de ley; itosturre/audit/referencias.py):
  ✅ Designación con sufijo ("247 Ter", "4o.-A", "32-B Quáter") y una referencia por
     artículo en enumeraciones y rangos ("arts. 14, 16 y 19", "467 a 471").
  ✅ Ley solo por vínculo sintáctico (pegada a la derecha del precepto, pegada o posesiva a
     la izquierda; varias leyes solo con "respectivamente"; conflicto → no identificada),
     por palabra completa; "constitución" sola no es la CPEUM; claves estatales con entidad.
  ✅ Ley no identificada → 🟡 NO VERIFICABLE con motivo (sin buscar el número en todo el
     corpus); precepto con sufijo sin encabezado exacto → 🟡 NO VERIFICABLE; rango recortado
     o número no extraído con certeza → 🟡 COBERTURA INCOMPLETA; ley inferida de otro
     párrafo → 🟡 LEY POR CONFIRMAR.

Cambios v4.0:
  ✅ Embeddings: migración multilingual-e5-small (384d) → multilingual-e5-large (1024d)
     Encoding asimétrico e5 vía prefijos de texto: "passage: " al indexar (ingest),
     "query: " al buscar (encode_query / comando query). Requiere re-ingest completo
     del corpus tras actualizar el modelo.
  ✅ Chunking inteligente por tipo de documento:
     - Leyes/códigos: split en artículos (comportamiento anterior)
     - Contratos: split en cláusulas (CLÁUSULA PRIMERA, SEGUNDA...)
     - Resoluciones/sentencias: split en secciones (CONSIDERANDO, RESULTANDO...)
     Prefijo de contexto inyectado en sub-chunks para mantener referencia al artículo/cláusula.
     Max chunk size aumentado 1200 → 2000 chars. Metadata incluye doc_type.
  ✅ Scoring rediseñado (scoring_vvca.py) — dos scores independientes sin promediar:
     score_rag (artículos vs. corpus ChromaDB) y score_sjf (tesis CITADAS vs. corpus
     local de jurisprudencia; el scraper SJF en vivo es una herramienta estratégica aparte).
     Veredicto global binario con razón explícita (no es un número compuesto):
     cualquier tesis con rubro discrepante bloquea el veredicto (🔴), independiente del RAG.
  ✅ vvca_summary incluye score_rag, semaforo_rag, score_sjf, semaforo_sjf, veredicto,
     verdes/amarillos/rojos. (Ya no existen score_global/score_promedio/semaforo_global
     ni el score compuesto ponderado de versiones anteriores de este docstring.)

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
import importlib
import json
import re
import sys
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional, Tuple, Dict, List

from itosturre.audit.context import vvca_contextualizacion
from itosturre.audit.evidence import select_article_evidence
from itosturre.audit.referencias import (
    ARTICULO_RE,
    MOTIVO_CONFIRMAR,
    CatalogoLeyes,
    articulo_con_sufijo,
    construir_catalogo,
    designaciones_articulo,
    extraer_articulos,
    partes_articulo,
    patron_articulo,
    primera_mencion,
    sin_acentos,
    ultima_mencion,
)
from itosturre.audit.jurisprudence import (
    classify_fuerza_vinculante,
    rubro_keywords as _rubro_keywords,
)
from itosturre.audit.policy import disclaimer_graduado, vvca_score, vvca_semaforo
from itosturre.audit.traceability import build_trace_record, traceability_bundle
from scoring_vvca import veredicto_global

# ─────────────────────────────────────────
# DEPENDENCIAS PESADAS (carga perezosa)
# ─────────────────────────────────────────
# PyMuPDF, ChromaDB, LangChain y sentence-transformers se importaban al tope del módulo.
# Ahora se cargan juntas la primera vez que se USAN (modelo, colección, PDF), de modo que
# `import OpenNotebook` funciona sin paquetes: el CI (Python 3.11 sin dependencias) puede
# ejercer la extracción, la resolución de ley y el veredicto con una colección falsa.
# Se cargan las cuatro a la vez y en el orden del antiguo import (las bibliotecas nativas
# de torch/onnxruntime pueden ser sensibles al orden) y antes de cualquier efecto: si falta
# una, `ingest --clear` falla antes de borrar la colección, como fallaba antes al importar.
_DEPENDENCIAS_PESADAS = (
    # (módulo, paquete de pip)
    ("fitz", "PyMuPDF"),
    ("chromadb", "chromadb"),
    ("langchain_text_splitters", "langchain-text-splitters"),
    ("sentence_transformers", "sentence-transformers"),
)
_DEPENDENCIAS_CACHE: Optional[SimpleNamespace] = None


class DependenciaFaltante(ModuleNotFoundError):
    """Falta un paquete pesado del auditor. El mensaje dice cuál y cómo instalarlo."""


def _cargar_dependencias() -> SimpleNamespace:
    """Importa (una sola vez) las dependencias pesadas y las expone con sus nombres de
    siempre: ``fitz``, ``chromadb``, ``RecursiveCharacterTextSplitter`` y
    ``SentenceTransformer``. Un ImportError distinto de "módulo no encontrado" (DLL rota,
    versión incompatible) se propaga tal cual, igual que antes."""
    global _DEPENDENCIAS_CACHE
    if _DEPENDENCIAS_CACHE is None:
        modulos = {}
        for modulo, paquete in _DEPENDENCIAS_PESADAS:
            try:
                modulos[modulo] = importlib.import_module(modulo)
            except ModuleNotFoundError as exc:
                detalle = (
                    f" (falta el submódulo '{exc.name}')"
                    if exc.name and exc.name != modulo else ""
                )
                raise DependenciaFaltante(
                    f"OpenNotebook necesita el paquete '{paquete}' (módulo '{modulo}') "
                    f"para esta operación y no está instalado{detalle}. Instálalo con el "
                    f"intérprete del venv del proyecto: python -m pip install -r "
                    f"requirements.txt (o solo: python -m pip install {paquete}). "
                    f"Ver docs/ENTORNO.md.",
                    name=modulo,
                ) from exc
        _DEPENDENCIAS_CACHE = SimpleNamespace(
            fitz=modulos["fitz"],
            chromadb=modulos["chromadb"],
            RecursiveCharacterTextSplitter=(
                modulos["langchain_text_splitters"].RecursiveCharacterTextSplitter
            ),
            SentenceTransformer=modulos["sentence_transformers"].SentenceTransformer,
        )
    return _DEPENDENCIAS_CACHE

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
# e5-large trunca a 512 tokens de secuencia; 2000 chars ≈ 500 tokens — justo dentro del límite.
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
    "FOVISSSTE_Tesis",   # compilación de tesis — NO es ley; va por jurisprudencia, no corpus
    "_Tesis_Completas",  # cualquier compilación *_Tesis_Completas no es ordenamiento
    # Archivos no legales
    "Chapter_1es", "CONSIGNA", "Bloc de notas",
    "Battlefield", "Marvel", "FrameView", "SOFÍA", "desktop",
    # Typos y duplicados
    "EXTINSION",               # typo de filename — el correcto es "...EXTINCION..."; excluye copias mal nombradas
    "codigo_civil_de_jalisco_1",  # duplicado de Codigo-Civil-del-Estado-de-Jalisco_3
    # Fuera de jurisdicción (contaminaban casos de Jalisco por similitud de nº de artículo)
    "NUEVO LEON", "NUEVO LEÓN",
]

# Threshold de distancia coseno: por debajo → verificado; por encima → alerta.
# e5-large normalizado: distancia coseno = 1 − similitud. Pares legales relevantes
# quedan en similitud 0.75-0.90 → distancia 0.10-0.25. Usar 0.25 es el punto de
# corte calibrado; 0.50 era laxo (aceptaba similitud 0.50 = texto mediocre).
COSINE_THRESHOLD = float(os.getenv("COSINE_THRESHOLD", "0.25"))

# Regex de una referencia a artículo (cabeza + PRIMER artículo + fracción). Captura:
#   Art. 247  /  artículo 247  /  Art. 247 Bis  /  artículo 247 Ter  /  2o. Bis  /  4o.-A
#   29-A  /  32-B Quáter  /  Art. 247 fr. III  /  Art. 247, fracción IV  /  Art. 259°
# Grupo 1 = designación con sus sufijos (R4-D01: antes "247 Ter" → "247" y "4o.-A" → "4o");
# grupo 2 = fracción. Se conserva por compatibilidad: ``extract_references`` ya no la usa
# directamente, sino ``itosturre.audit.referencias.extraer_articulos``, que además lee las
# enumeraciones y los rangos completos ("arts. 14, 16 y 19", "467 a 471"; R4-D02).
ARTICLE_RE = ARTICULO_RE

# Abreviaciones → nombre normalizado del ordenamiento.
# Desde R4b, "Constitución" y "Constitucional" no se buscan como mención libre (R4-D04): la
# primera es genérica y la segunda solo cuenta junto al precepto ("artículo 16 constitucional").
# Se conservan aquí como datos del catálogo. Ver itosturre/audit/referencias.py.
LAW_ALIASES = {
    # Constitución
    "CPEUM": "Constitución Política de los Estados Unidos Mexicanos",
    "Constitución": "Constitución Política de los Estados Unidos Mexicanos",
    "Constitución Federal": "Constitución Política de los Estados Unidos Mexicanos",
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
    # Reforma judicial y carrera judicial 2024
    "LCJ": "Ley de Carrera Judicial",
    "Carrera Judicial": "Ley de Carrera Judicial",
    "Ley de Carrera Judicial": "Ley de Carrera Judicial",
    # Seguridad social / vivienda
    "ISSSTE": "Ley del ISSSTE",
    "Ley del ISSSTE": "Ley del ISSSTE",
    "FOVISSSTE": "Ley del ISSSTE",   # Fondo de vivienda del ISSSTE — art. 167-ss dentro de la Ley del ISSSTE
    "INFONAVIT": "Ley del INFONAVIT",
    "LINFONAVIT": "Ley del INFONAVIT",
    "Ley del INFONAVIT": "Ley del INFONAVIT",
    # Laboral burocrático
    "LFTSE": "Ley Federal de Trabajadores al Servicio del Estado",
    "Ley Federal de Trabajadores al Servicio del Estado": "Ley Federal de Trabajadores al Servicio del Estado",
    # Derechos de infancia
    "LGDNNA": "Ley General de Derechos de Niñas, Niños y Adolescentes",
    "Ley General de Derechos de Niñas": "Ley General de Derechos de Niñas, Niños y Adolescentes",
    "CDN": "Convención sobre los Derechos del Niño",
    "Convención sobre los Derechos del Niño": "Convención sobre los Derechos del Niño",
    "Derechos del Niño": "Convención sobre los Derechos del Niño",
    # Fiscal/contable (curso IA para contadores, 20-jul-2026)
    "RMF": "Resolución Miscelánea Fiscal",
    "Resolución Miscelánea Fiscal": "Resolución Miscelánea Fiscal",
    "Miscelánea Fiscal": "Resolución Miscelánea Fiscal",
    "PRODECON": "Ley Orgánica de la Procuraduría de la Defensa del Contribuyente",
    "Ley Orgánica de PRODECON": "Ley Orgánica de la Procuraduría de la Defensa del Contribuyente",
    "LOTFJA": "Ley Orgánica del Tribunal Federal de Justicia Administrativa",
    "Ley Orgánica del TFJA": "Ley Orgánica del Tribunal Federal de Justicia Administrativa",
    "LFDC": "Ley Federal de los Derechos del Contribuyente",
    "Ley Federal de los Derechos del Contribuyente": "Ley Federal de los Derechos del Contribuyente",
    "Derechos del Contribuyente": "Ley Federal de los Derechos del Contribuyente",
}

# Mapeo de palabras clave de ley (minúsculas) → nombre exacto del archivo en ChromaDB.
# Desde R4b cada clave se busca como palabra o abreviatura completa ("Olivares" ya no es
# "liva"; R4-D03), sin distinguir mayúsculas y admitiendo cualquier blanco entre palabras.
# "constitución" y "constitucional" son claves contextuales (ver LAW_ALIASES): sirven para
# --law y para el precepto "artículo N constitucional", nunca como mención libre.
LAW_SOURCE_MAP = {
    "código federal de procedimientos civiles": "Código Federal de Procedimientos Civiles 2026.pdf",
    "código nacional de procedimientos civiles": "Código Nacional de Procedimientos Civiles y Familiares 2026.pdf",
    "código nacional de procedimientos penales": "CodigoNacionalProcedPenales.pdf",
    "código civil federal": "CODIGO CIVIL FEDERAL 2026.pdf",
    "código civil del estado de jalisco": "Codigo-Civil-del-Estado-de-Jalisco_3.pdf",
    "código de procedimientos civiles del estado de jalisco": "CodigoProcedimientosCivilesEstadoJalisco.pdf",
    "código fiscal de la federación": "CODIGO FISCAL DE LA FEDERACION 2026.pdf",
    "código fiscal del estado de jalisco": "CODIGO FISCAL DEL ESTADO DE JALISCO 2026.pdf",
    # Ordenamientos estatales: la clave exige la entidad completa (R4b, ronda 2). Antes
    # "código penal para el estado" llevaba el Código Penal del Estado de México a Jalisco.
    "código penal para el estado libre y soberano de jalisco": "Código Penal para el Estado Libre y Soberano de Jalisco.pdf",
    "código penal para el estado de jalisco": "Código Penal para el Estado Libre y Soberano de Jalisco.pdf",
    "constitución política de los estados unidos": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    # Denominaciones de la CPEUM (R4b): "constitución" sola ya no la identifica.
    "constitución federal": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    "constitución general de la república": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
    "constitución política del estado de jalisco": "Constitución Politica del Estado de Jalisco 2026.pdf",
    "ley de amparo": "LEY DE AMPARO.pdf",
    "ley del seguro social": "LEY DEL SEGURO SOCIAL.pdf",
    "ley federal de protección a la propiedad intelectual": "LEY FEDERAL DE PROTECCION A LA PROPIEDAD INTELECTUAL LFPPI.pdf",
    "ley federal de protección al consumidor": "LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR LFPC.pdf",
    "ley federal de protección de datos personales": "LEY FEDERAL DE PROTECCIÓN DE DATOS PERSONALES EN POSESIÓN DE LOS PARTICULARES LFPDPPP.pdf",
    "ley federal de procedimiento administrativo": "Ley Federal de Procedimiento Administrativo 2026.pdf",
    "ley federal de procedimiento contencioso": "Ley Federal de Procedimiento Contencioso Administrativo 2026.pdf",
    "ley orgánica del poder judicial federal": "Ley Orgánica del Poder Judicial Federal 2026.pdf",
    # Denominación oficial (R4b): la clave anterior solo cubre "…Poder Judicial Federal"; sin
    # esta, "de la Ley Orgánica del Poder Judicial de la Federación" sería un ordenamiento no
    # reconocido (🟡 ley no identificada) ahora que la ley se resuelve por palabra completa.
    "ley orgánica del poder judicial de la federación": "Ley Orgánica del Poder Judicial Federal 2026.pdf",
    "ley de hacienda del estado de jalisco": "Ley de Hacienda del Estado de Jalisco -160424 2026.pdf",
    "ley de movilidad y transporte del estado de jalisco": "Ley de Movilidad y Transporte del Estado de Jalisco_2 2026.pdf",
    "ley del impuesto al valor agregado": "Ley del Impuesto al Valor Agregado 2026.pdf",
    "ley del impuesto sobre la renta": "Ley del Impuesto sobre la Renta 2026.pdf",
    "ley del notariado del estado de jalisco": "Ley del Notariado del Estado de Jalisco 2026.pdf",
    "ley del procedimiento administrativo del estado de jalisco": "Ley del Procedimiento Administrativo del Estado de Jalisco y sus Municipios_15_0 2026.pdf",
    "ley de justicia administrativa del estado de jalisco": "LeydeJusticiaAdministrativadelEstadodeJalisco 2026.pdf",
    "ley del registro civil del estado de jalisco": "ley_del_registro_civil_del_estado_de_jalisco 2026.pdf",
    "reglamento de la ley federal de protección al consumidor": "REGLAMENTO DE LA LEY FEDERAL DE PROTECCIÓN AL CONSUMIDOR Reg_LFPC_191219.pdf",
    # Título del PDF municipal: "Reglamento de Movilidad, Transporte y Seguridad Vial de
    # Guadalajara" (antes bastaba "reglamento de movilidad", de cualquier municipio).
    "reglamento de movilidad, transporte y seguridad vial de guadalajara": "RegMovilidadTransporteSeguridadVialGuadalajara 2026.pdf",
    # Ojo: el texto indexado de este PDF es la Ley Orgánica del Poder Judicial de la
    # Federación (verificado en el corpus el 1-oct-2026); la clave exige "de la federación".
    "reglamento orgánico del poder judicial de la federación": "Reglamento organico poder judicial de la federación 2026.pdf",
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
    # Reforma judicial 2024
    "ley de carrera judicial": "LEY DE CARRERA JUDICIAL 2024.pdf",
    "carrera judicial": "LEY DE CARRERA JUDICIAL 2024.pdf",
    "lcj": "LEY DE CARRERA JUDICIAL 2024.pdf",
    # Seguridad social / vivienda
    "ley del issste": "LEY DEL ISSSTE 2026.pdf",
    "issste": "LEY DEL ISSSTE 2026.pdf",
    "fovissste": "LEY DEL ISSSTE 2026.pdf",   # FOVISSSTE es el fondo de vivienda del ISSSTE (cap. VII)
    "ley del infonavit": "Ley del INFONAVIT 2026.pdf",
    "infonavit": "Ley del INFONAVIT 2026.pdf",
    "linfonavit": "Ley del INFONAVIT 2026.pdf",
    # Laboral burocrático
    "ley federal de trabajadores al servicio del estado": "Ley Federal de Trabajadores al Servicio del Estado 2026.pdf",
    "lftse": "Ley Federal de Trabajadores al Servicio del Estado 2026.pdf",
    # Derechos de infancia
    "ley general de derechos de niñas": "Ley General de Derechos de Niñas, Niños y Adolescentes 2026.pdf",
    "ley general de derechos de ninas": "Ley General de Derechos de Niñas, Niños y Adolescentes 2026.pdf",
    "lgdnna": "Ley General de Derechos de Niñas, Niños y Adolescentes 2026.pdf",
    "convención sobre los derechos del niño": "Convención sobre los Derechos del Niño.pdf",
    "convencion sobre los derechos del nino": "Convención sobre los Derechos del Niño.pdf",
    "cdn": "Convención sobre los Derechos del Niño.pdf",
    "derechos del niño": "Convención sobre los Derechos del Niño.pdf",
    "derechos del nino": "Convención sobre los Derechos del Niño.pdf",
    # Nuevas leyes indexadas mayo 2026
    "convención americana": "Convencion Americana sobre Derechos Humanos.pdf",
    "cadh": "Convencion Americana sobre Derechos Humanos.pdf",
    "pacto de san josé": "Convencion Americana sobre Derechos Humanos.pdf",
    "ley federal de delincuencia organizada": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA 2026.pdf",
    # Denominación oficial (título del PDF del corpus).
    "ley federal contra la delincuencia organizada": "LEY FEDERAL DE DELINCUENCIA ORGANIZADA 2026.pdf",
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
    # Fiscal/contable (curso IA para contadores, 20-jul-2026)
    "resolución miscelánea fiscal": "RESOLUCION MISCELANEA FISCAL 2026.pdf",
    "resolucion miscelanea fiscal": "RESOLUCION MISCELANEA FISCAL 2026.pdf",
    "rmf": "RESOLUCION MISCELANEA FISCAL 2026.pdf",
    "miscelánea fiscal": "RESOLUCION MISCELANEA FISCAL 2026.pdf",
    "miscelanea fiscal": "RESOLUCION MISCELANEA FISCAL 2026.pdf",
    "ley orgánica de la procuraduría de la defensa del contribuyente": "LEY ORGANICA DE LA PRODECON 2026.pdf",
    "ley organica de la procuraduria de la defensa del contribuyente": "LEY ORGANICA DE LA PRODECON 2026.pdf",
    "ley orgánica de prodecon": "LEY ORGANICA DE LA PRODECON 2026.pdf",
    "prodecon": "LEY ORGANICA DE LA PRODECON 2026.pdf",
    "ley orgánica del tribunal federal de justicia administrativa": "LEY ORGANICA DEL TFJA 2026.pdf",
    "ley organica del tribunal federal de justicia administrativa": "LEY ORGANICA DEL TFJA 2026.pdf",
    "lotfja": "LEY ORGANICA DEL TFJA 2026.pdf",
    "ley orgánica del tfja": "LEY ORGANICA DEL TFJA 2026.pdf",
    "ley federal de los derechos del contribuyente": "LEY FEDERAL DE DERECHOS DEL CONTRIBUYENTE 2026.pdf",
    "ley federal de derechos del contribuyente": "LEY FEDERAL DE DERECHOS DEL CONTRIBUYENTE 2026.pdf",
    "lfdc": "LEY FEDERAL DE DERECHOS DEL CONTRIBUYENTE 2026.pdf",
    "derechos del contribuyente": "LEY FEDERAL DE DERECHOS DEL CONTRIBUYENTE 2026.pdf",
}


# ─────────────────────────────────────────
# NORMALIZACIÓN DE TEXTO LEGAL
# ─────────────────────────────────────────

# Expansión de acrónimos antes del embed — mejora recall; e5-large es multilingüe pero
# genérico, así que la expansión ayuda sobre todo en consultas cortas o mal formateadas.
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
    (r'\bLCJ\b',      'Ley de Carrera Judicial'),
    (r'\bISSTE\b',    'Ley del ISSSTE'),
    (r'\bINFONAVIT\b','Ley del INFONAVIT'),
    (r'\bFOVISSSTE\b','Ley del ISSSTE'),
    (r'\bLFTSE\b',    'Ley Federal de Trabajadores al Servicio del Estado'),
    (r'\bLGDNNA\b',   'Ley General de Derechos de Niñas Niños y Adolescentes'),
    (r'\bCDN\b',      'Convención sobre los Derechos del Niño'),
    # Fiscal/contable (curso IA para contadores, 20-jul-2026)
    (r'\bRMF\b',      'Resolución Miscelánea Fiscal'),
    (r'\bLOTFJA\b',   'Ley Orgánica del Tribunal Federal de Justicia Administrativa'),
    (r'\bLFDC\b',     'Ley Federal de los Derechos del Contribuyente'),
    (r'\bPRODECON\b', 'Procuraduría de la Defensa del Contribuyente'),
    # TJAJ expande a nombre de la LEY, no del órgano, para que matchee LAW_SOURCE_MAP
    (r'\bTJAJ\b',     'Ley de Justicia Administrativa del Estado de Jalisco'),
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
        dependencias = _cargar_dependencias()
        logger.info(f"⏳ Cargando modelo de embeddings: {EMBED_MODEL}...")
        _EMBEDDER_CACHE = dependencias.SentenceTransformer(EMBED_MODEL)
    return _EMBEDDER_CACHE


def encode_query(text: str) -> List[float]:
    """Codifica una query con prefijo e5 'query: ' para búsqueda asimétrica."""
    embedder = get_embedder()
    vec = embedder.encode(["query: " + text], normalize_embeddings=True)
    return vec[0].tolist()


def get_collection(embedder):
    client = _cargar_dependencias().chromadb.PersistentClient(path=CHROMA_PATH)

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
    doc = _cargar_dependencias().fitz.open(str(pdf_path))
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

    # get_embedder() carga las cuatro dependencias pesadas antes de tocar la colección:
    # si falta alguna, la ingesta aborta aquí, nunca después de borrar con --clear.
    embedder = get_embedder()
    dependencias = _cargar_dependencias()
    client = dependencias.chromadb.PersistentClient(path=CHROMA_PATH)

    # clear y reingest borran la colección antes de ingestar
    # (antes: se borraba dos veces si se pasaban ambas flags)
    if clear or reingest:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("🗑️  Colección borrada para re-ingesta limpia.")
        except Exception as e:
            logger.warning(f"⚠️  No se pudo borrar colección: {e}")

    collection = get_collection(embedder)

    fallback_splitter = dependencias.RecursiveCharacterTextSplitter(
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

_CATALOGO_CACHE: Optional[Tuple[tuple, CatalogoLeyes]] = None


def _catalogo() -> CatalogoLeyes:
    """Catálogo de menciones de ley (patrones por palabra completa) de LAW_SOURCE_MAP y
    LAW_ALIASES. Se reconstruye si alguno de los dos diccionarios cambió."""
    global _CATALOGO_CACHE
    firma = (tuple(LAW_SOURCE_MAP.items()), tuple(LAW_ALIASES.items()))
    if _CATALOGO_CACHE is None or _CATALOGO_CACHE[0] != firma:
        _CATALOGO_CACHE = (firma, construir_catalogo(LAW_SOURCE_MAP, LAW_ALIASES))
    return _CATALOGO_CACHE[1]


def resolve_law_source(context: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca en el contexto la clave de ley (LAW_SOURCE_MAP) que aparece más pronto; a igual
    posición gana la más larga. Desde R4b la coincidencia es por palabra o abreviatura
    completa (R4-D03: "olivares" ya no contiene "liva") y "constitución"/"constitucional"
    sueltas no identifican la CPEUM (R4-D04). Devuelve (clave, archivo) o (None, None).
    """
    return primera_mencion(context or "", _catalogo())


def resolve_law_alias(law: str) -> str:
    """Resuelve el valor de --law (alias legible o nombre exacto del PDF) al
    nombre de archivo indexado en metadata['source']. Antes, el filtro --law
    exigía el nombre exacto del PDF (p. ej. 'CodigoProcedimientosCivilesEstadoJalisco.pdf')
    y un alias del LAW_SOURCE_MAP como 'código de procedimientos civiles del estado
    de jalisco' no producía resultados (0 chunks) en vez de un error explícito.
    """
    if not law:
        return law
    key = law.strip().lower()
    if key in LAW_SOURCE_MAP:
        return LAW_SOURCE_MAP[key]
    if law in LAW_SOURCE_MAP.values():
        return law  # ya es el nombre de archivo exacto
    _, resolved = resolve_law_source(key)
    return resolved or law


def extract_article_numbers(text: str) -> List[str]:
    """Extrae las designaciones de artículo mencionadas explícitamente en `text`, sin
    repetir: 'artículo 294', 'art. 294', 'arts. 14, 16 y 19' (cada uno; R4-D02) y con su
    sufijo ('artículo 247 Ter' → '247 Ter'; R4-D01)."""
    return designaciones_articulo(text, _catalogo())


def exact_article_chunks(collection, source: str, article_num: str) -> List[Dict]:
    """Escaneo literal (no semántico) de los chunks de `source` que contienen el
    encabezado exacto 'Artículo {n}.'. Complementa la búsqueda semántica: un
    artículo corto o temáticamente atípico dentro de su capítulo puede empatar en
    score con vecinos y quedar fuera del top-N sin que exista ningún hueco de
    indexación (caso real: art. 294 CPCJ, auditoría VVCA 07-jul-2026 — el chunk
    existía en el corpus pero no rankeó dentro de n=4 resultados semánticos).

    Desde R4b la designación se compara completa: '4o' no coincide con 'Artículo 4o.-A.'
    ni '247' con 'Artículo 247 Bis.', y '247 Ter' exige el sufijo.
    """
    res = collection.get(where={"source": source}, include=["documents", "metadatas"])
    designacion = patron_articulo(article_num, espacio=r"\s") or re.escape(
        sin_acentos(article_num)
    )
    pattern = re.compile(rf"articulo\s+{designacion}\s*\.", re.IGNORECASE)
    hits = []
    for doc, meta in zip(res.get("documents") or [], res.get("metadatas") or []):
        if pattern.search(sin_acentos(doc)):
            hits.append({"source": meta.get("source", "?"), "page": meta.get("page", "?"), "snippet": doc.strip()})
    return hits


def resolve_law_source_backward(context_before: str) -> Tuple[Optional[str], Optional[str]]:
    """Busca el alias de ley MÁS CERCANO al final del texto (el más próximo antes del
    artículo). Maneja el patrón legal de agrupar artículos bajo un encabezado de ley:

        ### A. Orden constitucional mexicano (CPEUM)
        - Art. 16 — ...
        - Art. 19 — ...

    donde la ley vive en el encabezado, fuera de la ventana local del artículo.
    A igualdad de posición gana el alias más largo (más específico). Desde R4b la
    coincidencia es por palabra completa y una clave contenida en otra mayor ("delincuencia
    organizada" dentro de "Ley Federal de Delincuencia Organizada") no cuenta aparte.
    """
    return ultima_mencion(context_before or "", _catalogo())


def extract_references(text: str) -> List[Dict]:
    """Extrae referencias a artículos y jurisprudencias del borrador.

    Artículos (R4b, ``itosturre.audit.referencias``): una referencia por artículo, también
    en enumeraciones, rangos y segmentos con leyes intercaladas ("arts. 14, 16 y 19",
    "467 a 471", "14 de la CPEUM y 42 del CFF"), con su sufijo ("247 Ter", "4o.-A"). La ley
    solo se asocia por vínculo sintáctico (pegada a la derecha del precepto, pegada o
    posesiva a la izquierda) y, como último recurso, por el contexto previo de oraciones
    anteriores (``law_inferred=True``; desde otro párrafo sin encabezado inequívoco,
    ``law_requires_confirmation=True``). Si no se identifica de forma inequívoca:
    ``law="desconocido"``, ``source_file=None`` y el motivo en ``law_unidentified_reason``
    (``audit`` la reporta 🟡 NO VERIFICABLE, nunca 🔴). Lo que no se extrae con certeza
    queda como referencia de cobertura incompleta (``coverage_gap``). Campos añadidos:
    ``law_method``, ``law_unidentified_reason``, ``group_raw``,
    ``law_requires_confirmation`` y ``coverage_gap``.
    """
    refs = extraer_articulos(text, _catalogo())

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


def _article_candidates(article: str) -> List[str]:
    """Formas del número de artículo para el match EXACTO contra la metadata del corpus.

    El chunker guarda el número base ('Art. 247 Bis' → '247' porque el label corta en el
    espacio); la referencia puede traer el sufijo. Se generan ambas formas (y la variante sin
    espacios internos) para no perder el match por espaciado — p. ej. '247 Bis' → ['247 Bis',
    '247', '247Bis'], '1004-A' → ['1004-A'], '19' → ['19'].
    """
    a = (article or "").strip()
    if not a:
        return []
    cands = {a}
    m = re.match(r"\d+[\w\-]*", a)  # número base, sin ' Bis'/' Ter'
    if m:
        cands.add(m.group(0))
    if " " in a:
        cands.add(a.replace(" ", ""))
    return list(cands)


def build_vvca(
    ref: Dict,
    distance: float,
    source_match: bool,
    source_file: str,
    page: str,
    metadata_verificado: bool = False,
    article_heading_verified: Optional[bool] = None,
) -> Dict:
    score = vvca_score(distance, source_match, has_source_file=bool(ref.get("source_file")))
    # Anti-falso-🟢: sin ley identificada en el contexto el match es solo por número de
    # artículo; no dar verde aunque la distancia sea baja — capar a 🟡 (84).
    if not ref.get("source_file"):
        score = min(score, 84)
    # Anti-falso-🟢: source+article en metadata no basta. El fragmento debe mostrar el
    # encabezado exacto; una remisión interna al precepto sólo permite 🟡.
    if article_heading_verified is False:
        score = min(score, 84)
    # La metadata corroborada por encabezado confirma la existencia del artículo, pero una
    # distancia alta conserva el piso 🟡: la pertinencia del texto aún requiere cotejo.
    if metadata_verificado:
        score = max(score, 70)
    # R4b: ley inferida de otro párrafo (no de un encabezado inequívoco). El cotejo se hizo
    # contra una ley que el abogado debe confirmar: el semáforo se limita a 🟡 en ambos
    # sentidos (ni 🟢 ni 🔴 por una ley supuesta). Mínimo necesario; el resto es R4c.
    por_confirmar = bool(ref.get("law_requires_confirmation"))
    if por_confirmar:
        score = max(60, min(score, 84))
    semaforo = vvca_semaforo(score)
    law = ref.get("law", "desconocido")
    art = ref.get("article", "?")
    frac = ref.get("fraction", "")
    art_label = f"Art. {art}" + (f" fr. {frac}" if frac else "")

    if metadata_verificado:
        v_verificacion = (
            f"Artículo confirmado por metadata y encabezado exacto en corpus oficial "
            f"(dist={distance:.3f})"
        )
    elif article_heading_verified is False:
        v_verificacion = (
            f"Evidencia insuficiente: el fragmento no contiene el encabezado exacto "
            f"del artículo (dist={distance:.3f})"
        )
    elif distance <= COSINE_THRESHOLD:
        v_verificacion = f"Encontrado en corpus oficial (dist={distance:.3f})"
    else:
        v_verificacion = (
            f"Coincidencia débil — posible alucinación (dist={distance:.3f}, "
            f"umbral={COSINE_THRESHOLD})"
        )
    v_validacion = (
        f"Fuente correcta: {source_file}"
        if source_match
        else f"Fuente distinta: se encontró en '{source_file}', se esperaba '{ref.get('source_file')}'"
    )
    if por_confirmar:
        v_verificacion = f"Ley inferida de otro párrafo (confirmar el ordenamiento); {v_verificacion}"
    c_contextualizacion = vvca_contextualizacion(source_file)
    a_auditabilidad = f"{art_label} · {law} · pág. {page} · corpus: {source_file}"

    # Traza reproducible del veredicto por cita (explicabilidad — no caja negra).
    explicabilidad = {
        "coseno": round(distance, 4),
        "umbral": COSINE_THRESHOLD,
        "aprobado_umbral": distance <= COSINE_THRESHOLD,
        "match_metadata": metadata_verificado,
        "encabezado_articulo": article_heading_verified,
        "coincide_fuente": source_match,
        "fuente_encontrada": source_file,
        "fuente_esperada": ref.get("source_file"),
        "ley_inferida": bool(ref.get("law_inferred")),
    }
    if por_confirmar:
        explicabilidad["ley_por_confirmar"] = True
    return {
        "score": score,
        "semaforo": semaforo,
        "V_verificacion": v_verificacion,
        "V_validacion": v_validacion,
        "C_contextualizacion": c_contextualizacion,
        "A_auditabilidad": a_auditabilidad,
        "explicabilidad": explicabilidad,
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
    overlap = None
    if rubro_real and rubro_invocado:
        kw_real     = _rubro_keywords(rubro_real)
        kw_invocado = _rubro_keywords(rubro_invocado)
        if kw_real and kw_invocado:
            overlap = len(kw_real & kw_invocado) / min(len(kw_real), len(kw_invocado))
            rubro_mismatch = overlap < 0.40  # < 40% de palabras en común → tesis equivocada

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

    # Fuerza vinculante ([J]/[PR]/[PC]/[TCC]/[SCJN-P]/[TA]) desde la clave.
    fuerza = classify_fuerza_vinculante(numero, tipo)

    # Estado de vigencia: por defecto "vigente". Solo si el corpus/scraper marcó el
    # criterio como superado/interrumpido/sustituido dispara el bloqueo (falso verde).
    _estado_raw = item.get("estado_vigencia") or item.get("vigencia") or "vigente"
    estado_vigencia = str(_estado_raw).strip().lower()
    if estado_vigencia not in ("vigente", "superada", "interrumpida", "sustituida"):
        estado_vigencia = "vigente"

    return {
        "score": score,
        "semaforo": semaforo,
        "rubro_mismatch": rubro_mismatch,
        "fuerza_vinculante": fuerza,
        "estado_vigencia": estado_vigencia,
        "V_verificacion": verificacion,
        "V_validacion": tipo_label,
        "C_contextualizacion": contexto,
        "A_auditabilidad": f"{numero} · Reg. {registro} · {sala} · {source_file}",
        # Traza reproducible por cita (explicabilidad).
        "explicabilidad": {
            "registro": registro,
            "overlap_rubro": round(overlap, 3) if overlap is not None else None,
            "umbral_mismatch": 0.40,
            "rubro_real": rubro_real[:160],
            "rubro_invocado": (rubro_invocado or "")[:160],
            "estado_vigencia": estado_vigencia,
            "fuente": source_file,
        },
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


def _motivo_ley_no_identificada(ref: Dict) -> str:
    """Motivo, para el abogado, de que una referencia no tenga ley verificable."""
    if ref.get("law_unidentified_reason"):
        return ref["law_unidentified_reason"]
    law = ref.get("law") or "desconocido"
    if law != "desconocido":
        # Alias reconocido sin archivo asociado en LAW_SOURCE_MAP (p. ej. "Ejecución Penal").
        return f"el ordenamiento '{law}' no tiene fuente asociada en el corpus (LAW_SOURCE_MAP)"
    return "el texto no nombra el ordenamiento del artículo"


def _registrar_sin_encabezado_exacto(
    ref: Dict,
    selected: Dict,
    best_source: str,
    expected_source: Optional[str],
    sufijo_pedido: bool,
    metadata_candidate_found: bool,
    alerts: List[str],
    verification_traces: List[Dict],
) -> None:
    """🟡 NO VERIFICABLE para un precepto que el índice no localiza con su encabezado exacto
    porque agrupa las variantes con letra o sufijo bajo el número base (R4b)."""
    partes = partes_articulo(ref["article"])
    base = partes.base if partes else ref["article"]
    page = selected["metadata"].get("page", "?")
    if sufijo_pedido:
        detalle = (
            f"el artículo {ref['article']} no aparece con su encabezado exacto en la evidencia "
            f"recuperada de '{best_source}' (el índice agrupa los preceptos con letra o sufijo "
            f"bajo el número base '{base}')"
        )
    else:
        detalle = (
            f"en '{best_source}' solo se localizaron variantes con letra o sufijo del artículo "
            f"{ref['article']} (p. ej. '{base}-A' o '{base} Bis'), no su encabezado exacto"
        )
    alerts.append(
        f"🟡 NO VERIFICABLE: '{ref['raw']}' — {detalle}. NO es alucinación: el corpus no "
        f"permite localizar el precepto. Cotejarlo en la fuente oficial antes de citar."
    )
    verification_traces.append(build_trace_record(
        reference=ref["raw"],
        ref_type="normativa",
        status="not_verifiable",
        method="corpus_metadata" if metadata_candidate_found else "corpus_semantic",
        reason=f"Precepto no localizado con su encabezado exacto: {detalle}",
        semaforo="🟡",
        source_file=best_source,
        locator=f"página {page} · artículo {ref['article']}",
        evidence_text=selected["document"],
        metadata={
            "encabezado_articulo": False,
            "sufijo_solicitado": sufijo_pedido,
            "variante_con_sufijo": bool(selected.get("variant_heading")),
            "candidatos_metadata": metadata_candidate_found,
            "coseno": round(selected["distance"], 4),
            "umbral": COSINE_THRESHOLD,
            "fuente_encontrada": best_source,
            "fuente_esperada": expected_source,
            "ley_inferida": bool(ref.get("law_inferred")),
        },
    ))


def audit(
    text: str,
    verbose: bool = False,
    allow_incomplete_corpus: bool = False,
    *,
    collection=None,
    encode: Optional[Callable[[str], List[float]]] = None,
) -> Dict:
    """
    Audita el borrador contra el corpus legal.
    Retorna JSON con alerts y retrieved_sources.

    Si el corpus no contiene leyes referenciadas en el texto y
    allow_incomplete_corpus=False, retorna status='corpus_incomplete' con la lista
    de leyes faltantes para que el caller decida si continuar.
    Pasar allow_incomplete_corpus=True para forzar la auditoría e incluir
    la advertencia en el campo 'corpus_warning' del resultado.

    Costuras de prueba (R4a; solo por nombre, nunca las usa la CLI):
      - ``collection``: objeto con la API de ``chromadb.Collection`` que usa esta
        función (``count``, ``get``, ``query``). Si se inyecta, no se carga el modelo ni
        se abre ChromaDB y se omite la comprobación de CHROMA_PATH: esa ruta solo sirve
        para abrir la colección persistente (y evitar que ChromaDB cree una vacía en una
        ruta equivocada), y una colección inyectada no la usa. ``count() == 0`` se
        comprueba igual en ambos caminos.
      - ``encode``: codificador de consultas (texto → vector); por defecto
        ``encode_query`` (modelo e5 con prefijo "query: ").
    Con ambos en None el camino es el de siempre: modelo → CHROMA_PATH → colección.
    """
    if collection is None:
        embedder = get_embedder()

        # Verificar que existe la base vectorial
        chroma_path = Path(CHROMA_PATH)
        if not chroma_path.exists():
            return {
                "status": "error",
                "message": "Base vectorial no encontrada. Ejecuta primero: python OpenNotebook.py ingest --directory /ruta/pdfs/",
                "alerts": [],
                "retrieved_sources": []
            }

        collection = get_collection(embedder)

    codificar = encode if encode is not None else encode_query

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
    verification_traces = []
    verified_count = 0
    corpus_warning = None

    if verbose:
        logger.debug(f"🔍 Auditoría: {len(refs)} referencias detectadas")

    # ── Verificar cobertura del corpus ───────────────────────────────────────
    missing_sources = check_corpus_coverage(refs, collection)
    if missing_sources:
        if not allow_incomplete_corpus:
            for ref in refs:
                expected_source = ref.get("source_file")
                if expected_source in missing_sources:
                    verification_traces.append(build_trace_record(
                        reference=ref["raw"],
                        ref_type=ref["type"],
                        status="not_verifiable",
                        method="corpus_coverage_gate",
                        reason=f"Fuente no indexada en el corpus local: {expected_source}",
                        semaforo="🟡",
                        source_file=expected_source,
                        metadata={"corpus_partial": True},
                    ))
            return {
                "status": "corpus_incomplete",
                "missing_sources": missing_sources,
                "message": (
                    f"⚠️  Corpus incompleto: {len(missing_sources)} ley(es) referenciada(s) "
                    f"no están indexadas en ChromaDB.\n"
                    + "\n".join(f"  • {s}" for s in missing_sources)
                    + "\n\nIndexar primero: python OpenNotebook.py ingest --directory /ruta/corpus/\n"
                    "O continuar con: --force (el resultado incluirá advertencia)."
                ),
                "alerts": [],
                "retrieved_sources": [],
                "traceability": traceability_bundle(verification_traces),
            }
        corpus_warning = (
            f"⚠️  Auditoría ejecutada con corpus parcial. "
            f"Ley(es) no verificadas por ausencia en ChromaDB: "
            + ", ".join(missing_sources)
        )

    for ref in refs:
        if ref["type"] == "article":
            # R4b — Cobertura incompleta de la extracción: un rango de más de MAX_RANGO
            # artículos (solo se auditaron sus extremos) o un número ligado a una ley que no
            # se extrajo con certeza de la enumeración. Nada desaparece en silencio: cuenta
            # como no verificable, así que el veredicto global no puede ser 🟢.
            if ref.get("coverage_gap"):
                alerts.append(
                    f"🟡 COBERTURA INCOMPLETA: '{ref['raw']}' — {ref['coverage_gap']}. "
                    f"Auditar esos artículos por separado o verificarlos en fuente oficial "
                    f"antes de citar."
                )
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="normativa",
                    status="not_verifiable",
                    method="cobertura_extraccion",
                    reason=f"Cobertura incompleta: {ref['coverage_gap']}",
                    semaforo="🟡",
                    source_file=ref.get("source_file"),
                    locator=f"artículos {ref['article']}",
                    metadata={
                        "cobertura_incompleta": True,
                        "law": ref.get("law", "desconocido"),
                        "law_method": ref.get("law_method"),
                    },
                ))
                continue

            # R4b — Ley no identificada (o sin fuente en el corpus): 🟡 NO VERIFICABLE con su
            # motivo, por el mismo camino que la "ley no indexada" (Guard P0): sin un
            # ordenamiento identificado no hay contra qué cotejar el precepto, y buscarlo por
            # número en todo el corpus sería adivinar la ley. Nunca 🔴 ni 🟢 (Regla 4 de
            # CLAUDE.md; "🟡 NO VERIFICABLE no es 🔴").
            if not ref.get("source_file"):
                motivo = _motivo_ley_no_identificada(ref)
                alerts.append(
                    f"🟡 NO VERIFICABLE — LEY NO IDENTIFICADA: '{ref['raw']}' (artículo "
                    f"{ref['article']}) — {motivo}. NO es alucinación: sin el ordenamiento no "
                    f"se puede cotejar el precepto. Precisar la ley junto al artículo o "
                    f"verificar en fuente oficial antes de citar."
                )
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="normativa",
                    status="not_verifiable",
                    method="resolucion_ley",
                    reason=f"Ley no identificada: {motivo}",
                    semaforo="🟡",
                    locator=f"artículo {ref['article']}",
                    metadata={
                        "ley_no_identificada": True,
                        "motivo": motivo,
                        "law": ref.get("law", "desconocido"),
                        "law_method": ref.get("law_method"),
                    },
                ))
                continue

            query_raw = f"Artículo {ref['article']}"
            if ref["fraction"]:
                query_raw += f" fracción {ref['fraction']}"
            if ref["law"] and ref["law"] != "desconocido":
                query_raw += f" {ref['law']}"
            # Normalizar acrónimos para mejorar recall en e5-large
            query = normalize_legal_text(query_raw)

            expected_source = ref.get("source_file")
            where_filter = {"source": expected_source} if expected_source else None

            # Guard P0 (anti-falso-🔴): si la ley fue identificada pero su PDF NO está
            # indexado en el corpus, esto NO es una alucinación — el corpus simplemente no
            # la contiene. Marcar 🟡 NO VERIFICABLE en vez de dejar que caiga al else de
            # "no encontrado / alucinación detectada", que tacharía de falsa una cita válida
            # (p. ej. LGV/PIDCP en el caso Aaron García).
            if expected_source and expected_source in missing_sources:
                alerts.append(
                    f"🟡 NO VERIFICABLE: '{ref['raw']}' — la ley '{expected_source}' no está "
                    f"indexada en el corpus. NO es alucinación: el corpus no la contiene. "
                    f"Indexar la ley o verificar en fuente oficial antes de citar."
                )
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="normativa",
                    status="not_verifiable",
                    method="corpus_local",
                    reason=f"Ley no indexada en el corpus local: {expected_source}",
                    semaforo="🟡",
                    source_file=expected_source,
                    locator=f"artículo {ref['article']}",
                    metadata={
                        "corpus_partial": True,
                        "law_inferred": ref.get("law_inferred", False),
                    },
                ))
                continue

            # P0 — Recuperación por metadata primero: si la ley está identificada, traer el
            # chunk del ARTÍCULO EXACTO (match source+article), determinista; solo caer a
            # similitud pura si no hay match de metadata. Evita recuperar un artículo distinto
            # que resulte semánticamente parecido (el problema real de la búsqueda por coseno).
            metadata_hit = False
            metadata_candidate_found = False
            results = None
            if expected_source:
                cands = _article_candidates(ref["article"])
                if cands:
                    try:
                        exact_where = {
                            "$and": [
                                {"source": expected_source},
                                {"article": {"$in": cands}},
                            ]
                        }
                        exact_candidates = collection.get(
                            where=exact_where,
                            include=["documents"],
                        )
                        candidate_count = len(exact_candidates.get("documents") or [])
                        metadata_candidate_found = candidate_count > 0
                        if not metadata_candidate_found:
                            raise LookupError("sin candidatos exactos de metadata")
                        results = collection.query(
                            query_embeddings=[codificar(query)],
                            n_results=max(3, candidate_count),
                            where=exact_where,
                        )
                        if not (results and results["documents"] and results["documents"][0]):
                            results = None
                    except Exception:
                        results = None  # sintaxis where no soportada → fallback semántico

            if results is None:
                try:
                    # Encoding asimétrico (retrieval.query); filtro por fuente si se conoce.
                    results = collection.query(
                        query_embeddings=[codificar(query)],
                        n_results=3,
                        where=where_filter,
                    )
                except Exception:
                    # where_filter puede fallar si la fuente no existe en el corpus
                    results = collection.query(
                        query_embeddings=[codificar(query)],
                        n_results=3,
                    )
                    expected_source = None

            selected = select_article_evidence(results, ref["article"])
            if selected:
                best_doc = selected["document"]
                best_meta = selected["metadata"]
                best_source = best_meta.get("source", "desconocido")
                best_distance = selected["distance"]
                article_heading_verified = selected["heading_verified"]
                metadata_hit = metadata_candidate_found and article_heading_verified
                source_match = (not expected_source) or (best_source == expected_source)

                # R4b — El chunker etiqueta "4o.-A", "247 Bis" o "29-A Bis" con el número
                # base, así que la búsqueda por metadata devuelve el artículo base y sus
                # variantes. Si el precepto pedido trae sufijo, o el índice solo ofreció
                # variantes con sufijo del número pedido, y ningún fragmento muestra el
                # encabezado exacto, el corpus no permite localizarlo: 🟡 NO VERIFICABLE.
                # Nunca 🟢 contra el artículo base (R4-D01/D06) ni 🔴: no se acreditó que
                # el precepto no exista. (Una re-ingesta con etiqueta completa lo evitaría.)
                sufijo_pedido = articulo_con_sufijo(ref["article"])
                if not article_heading_verified and (sufijo_pedido or selected["variant_heading"]):
                    _registrar_sin_encabezado_exacto(
                        ref, selected, best_source, expected_source, sufijo_pedido,
                        metadata_candidate_found, alerts, verification_traces,
                    )
                    continue

                vvca = build_vvca(
                    ref=ref,
                    distance=best_distance,
                    source_match=source_match,
                    source_file=best_source,
                    page=best_meta.get("page", "?"),
                    metadata_verificado=metadata_hit,
                    article_heading_verified=article_heading_verified,
                )

                entry = {
                    "reference": ref["raw"],
                    "law": ref["law"],
                    "article": ref["article"],
                    "ref_type": "normativa",
                    "source_file": best_source,
                    "page": best_meta.get("page", "?"),
                    "expected_source": expected_source,
                    "law_inferred": ref.get("law_inferred", False),
                    # R4b (campo añadido): cómo se resolvió la ley de la cita.
                    "law_method": ref.get("law_method"),
                    "relevance_score": round(1 - best_distance, 3),
                    "retrieved_text": best_doc[:600],
                    "retrieved_text_full": best_doc,
                    "vvca": vvca,
                }

                if not source_match:
                    trace_status = "refuted"
                elif metadata_hit:
                    trace_status = "verified" if vvca["score"] >= 85 else "partial"
                elif best_distance > COSINE_THRESHOLD:
                    trace_status = "refuted"
                else:
                    trace_status = "verified" if vvca["score"] >= 85 else "partial"
                por_confirmar = bool(ref.get("law_requires_confirmation"))
                if por_confirmar:
                    # Ley inferida de otro párrafo: nunca verificada ni refutada (🟡).
                    trace_status = "partial"
                trace = build_trace_record(
                    reference=ref["raw"],
                    ref_type="normativa",
                    status=trace_status,
                    method="corpus_metadata" if metadata_hit else "corpus_semantic",
                    reason=f"{vvca['V_verificacion']}; {vvca['V_validacion']}",
                    score=vvca["score"],
                    semaforo=vvca["semaforo"],
                    source_file=best_source,
                    locator=f"página {best_meta.get('page', '?')} · artículo {ref['article']}",
                    evidence_text=best_doc,
                    metadata=vvca.get("explicabilidad", {}),
                )
                verification_traces.append(trace)
                entry["trace_id"] = trace["trace_id"]

                # Conservar también la evidencia parcial o refutada. Excluirla de
                # ``retrieved_sources`` ocultaba el fragmento que originó la alerta y,
                # además, permitía que el promedio global ignorara la peor cita.
                retrieved_sources.append(entry)
                if trace_status == "verified":
                    verified_count += 1

                if por_confirmar:
                    alerts.append(
                        f"🟡 LEY POR CONFIRMAR (score {vvca['score']}): '{ref['raw']}' — "
                        f"{MOTIVO_CONFIRMAR} (se cotejó contra '{best_source}'). "
                        f"{vvca['V_verificacion']}. Precisar la ley junto al artículo antes de "
                        f"citar."
                    )
                elif metadata_hit:
                    # Artículo confirmado por metadata (ley+artículo exactos) → verificado.
                    # Distancia alta ya NO es "alucinación": es texto de otra porción del
                    # artículo (largo/troceado). Se avisa para cotejar, no se tacha de falso.
                    if best_distance > COSINE_THRESHOLD:
                        alerts.append(
                            f"🟡 COTEJAR: '{ref['raw']}' — artículo confirmado por metadata en "
                            f"'{best_source}', pero el texto recuperado coincide poco "
                            f"(dist={best_distance:.3f}): puede ser otra porción del artículo. "
                            f"Cotejar el texto citado contra el precepto."
                        )
                elif not source_match and best_distance <= COSINE_THRESHOLD:
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
                elif article_heading_verified is False:
                    alerts.append(
                        f"🟡 EVIDENCIA INSUFICIENTE (score {vvca['score']}): "
                        f"'{ref['raw']}' — el fragmento recuperado en '{best_source}' "
                        f"no contiene el encabezado exacto del artículo {ref['article']}. "
                        f"Puede ser una remisión interna; cotejar el precepto auténtico."
                    )
                else:
                    # Guard P0 (anti-falso-🟢): si el contexto no nombró la ley, el match
                    # es solo por número de artículo y pudo caer en otro ordenamiento.
                    # No bloquear, pero advertir explícitamente — no dar 🟢 ciego.
                    if not expected_source:
                        alerts.append(
                            f"🟡 LEY NO IDENTIFICADA: '{ref['raw']}' — coincidencia por número "
                            f"de artículo contra '{best_source}'. El contexto no nombró el "
                            f"ordenamiento; verificar que sea la ley correcta antes de citar."
                        )
            elif ref.get("law_requires_confirmation"):
                # Ley inferida de otro párrafo: no localizar el precepto en una ley supuesta
                # no acredita nada (🟡, nunca 🔴).
                alerts.append(
                    f"🟡 LEY POR CONFIRMAR: '{ref['raw']}' — {MOTIVO_CONFIRMAR}; el corpus no "
                    f"devolvió evidencia en '{expected_source}'. Precisar la ley junto al "
                    f"artículo antes de citar."
                )
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="normativa",
                    status="not_verifiable",
                    method="corpus_local",
                    reason=f"{MOTIVO_CONFIRMAR}; sin evidencia en la ley inferida",
                    semaforo="🟡",
                    source_file=expected_source,
                    locator=f"artículo {ref['article']}",
                    metadata={"ley_por_confirmar": True},
                ))
            else:
                alerts.append(
                    f"🔴 ALERTA CRÍTICA: '{ref['raw']}' — no encontrado en el corpus. "
                    f"Alucinación detectada. Verificar en fuente oficial ANTES de usar."
                )
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="normativa",
                    status="refuted",
                    method="corpus_local",
                    reason="No se encontró coincidencia en una fuente que sí está indexada",
                    score=0,
                    semaforo="🔴",
                    source_file=expected_source,
                    locator=f"artículo {ref['article']}",
                ))

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
                                trace = build_trace_record(
                                    reference=ref["raw"],
                                    ref_type="jurisprudencia",
                                    status="refuted" if vvca.get("rubro_mismatch") else (
                                        "verified" if vvca.get("score", 0) >= 85 else "partial"
                                    ),
                                    method="corpus_jurisprudencia",
                                    reason=vvca["V_verificacion"],
                                    score=vvca["score"],
                                    semaforo=vvca["semaforo"],
                                    source_file=json_file.name,
                                    locator=f"Registro digital {ref['registro']}",
                                    evidence_text=texto,
                                    metadata=vvca.get("explicabilidad", {}),
                                )
                                verification_traces.append(trace)
                                retrieved_sources.append({
                                    "reference": ref["raw"],
                                    "registro": ref["registro"],
                                    "ref_type": "jurisprudencia",
                                    "source_file": json_file.name,
                                    "relevance_score": 1.0,
                                    "retrieved_text": texto[:600],
                                    "vvca": vvca,
                                    "trace_id": trace["trace_id"],
                                })
                                if trace["verification"]["status"] == "verified":
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
                    f"🟡 NO VERIFICABLE: Registro digital {ref['registro']} "
                    f"no encontrado en el corpus de jurisprudencia local (no confirmado como falso). "
                    f"Verificar en sjf2.scjn.gob.mx antes de citar."
                )
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="jurisprudencia",
                    status="not_verifiable",
                    method="corpus_jurisprudencia",
                    reason="Registro ausente del corpus local; no se confirma como falso",
                    semaforo="🟡",
                    locator=f"Registro digital {ref['registro']}",
                    metadata={"corpus_partial": True},
                ))

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

    # Tesis con criterio superado/interrumpido/sustituido (falso verde). Por defecto 0:
    # el corpus solo marca vigencia si el scraper la capturó (sección NOTAS del SJF).
    tesis_superadas = sum(
        1 for s in retrieved_sources
        if s.get("ref_type") == "jurisprudencia"
        and s.get("vvca", {}).get("estado_vigencia") in ("superada", "interrumpida", "sustituida")
    )

    # El veredicto global respeta la peor traza normativa. El score promedio se
    # conserva como métrica descriptiva, pero nunca puede diluir una cita refutada
    # ni convertir evidencia parcial en un documento apto.
    trazas_normativas = [
        t for t in verification_traces
        if t.get("claim", {}).get("type") == "normativa"
    ]
    normativa_refutada = sum(
        1 for t in trazas_normativas
        if t.get("verification", {}).get("status") == "refuted"
    )
    normativa_no_verificable = sum(
        1 for t in trazas_normativas
        if t.get("verification", {}).get("status") in ("partial", "not_verifiable")
    )

    # Conteo por fuerza vinculante ([J-PLENO]/[J-SALA]/[PR]/[PC]/[J-TCC]/[SCJN-P]/[TA])
    tesis_por_fuerza: Dict[str, int] = {}
    for s in retrieved_sources:
        if s.get("ref_type") == "jurisprudencia":
            sello = s.get("vvca", {}).get("fuerza_vinculante", {}).get("sello")
            if sello:
                tesis_por_fuerza[sello] = tesis_por_fuerza.get(sello, 0) + 1

    # ── Veredicto binario — las tesis rojas son bloqueantes por sí solas
    veredicto = veredicto_global(
        score_rag, score_sjf, tesis_mismatch, tesis_no_encontradas,
        tesis_total_invocadas, tesis_superadas,
        normativa_refutada, normativa_no_verificable,
    )

    # Conteo por estado de verificación, no por el promedio ni sólo por las citas
    # recuperadas. Así cada referencia procesada aparece exactamente en un bucket.
    verdes = sum(
        1 for t in verification_traces
        if t.get("verification", {}).get("status") == "verified"
    )
    amarillos = sum(
        1 for t in verification_traces
        if t.get("verification", {}).get("status") in ("partial", "not_verifiable")
    )
    rojos = sum(
        1 for t in verification_traces
        if t.get("verification", {}).get("status") == "refuted"
    )

    result = {
        "status": "ok",
        "total_references_found": len(refs),
        "verified": verified_count,
        "alerts_count": len(alerts),
        "cosine_threshold": COSINE_THRESHOLD,
        "vvca_summary": {
            "score_rag":           score_rag,
            "semaforo_rag":        vvca_semaforo(score_rag),
            "articulos_ok":        sum(
                1 for t in trazas_normativas
                if t.get("verification", {}).get("status") == "verified"
            ),
            "articulos_total":     len(trazas_normativas),
            "normativa_refutada":  normativa_refutada,
            "normativa_no_verificable": normativa_no_verificable,
            "score_sjf":           score_sjf,
            "semaforo_sjf":        vvca_semaforo(score_sjf),
            "tesis_total":         tesis_total_invocadas,
            "tesis_ok":            len(jur_scores) - tesis_mismatch,
            "tesis_rojas":         tesis_rojas,
            "tesis_mismatch":      tesis_mismatch,
            "tesis_no_encontradas": tesis_no_encontradas,
            "tesis_superadas":     tesis_superadas,
            "tesis_por_fuerza":    tesis_por_fuerza,
            "veredicto":           veredicto,
            "disclaimer":          disclaimer_graduado(veredicto),
            "verdes":   verdes,
            "amarillos": amarillos,
            "rojos":     rojos,
        },
        "alerts": alerts,
        "retrieved_sources": retrieved_sources,
        "traceability": traceability_bundle(verification_traces),
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
    Interfaz de clase para el auditor RAG v4.0.

    Uso:
        from OpenNotebook import OpenNotebook
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

    def query(self, text: str, n: int = 5, law: Optional[str] = None, json_output: bool = False, verbose: bool = False) -> List[Dict]:
        """Perform a semantic search over the corpus.

        Returns a list of result dictionaries. If json_output is True, prints JSON.
        """
        self._ensure_loaded()
        embedder = get_embedder()
        col = get_collection(embedder)
        query_norm = normalize_legal_text(text)
        resolved_law = resolve_law_alias(law) if law else None
        where_filter = {"source": resolved_law} if resolved_law else None
        results = col.query(
            query_embeddings=[encode_query(query_norm)],
            n_results=n,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        result_list = []
        for doc, meta, dist in zip(results["documents"][0], results["metadatas"][0], results["distances"][0]):
            score = round((1 - dist) * 100)
            sem = vvca_semaforo(score)
            source = meta.get('source', '?')
            page = meta.get('page', '?')
            result_list.append({
                "score": score,
                "semaforo": sem,
                "source": source,
                "page": page,
                "snippet": doc.strip()
            })
        # Fallback literal: si el texto nombra un artículo explícito, garantizar su
        # chunk exacto aunque no haya rankeado en el top-N semántico (ver docstring
        # de exact_article_chunks).
        if resolved_law:
            for art_num in extract_article_numbers(text):
                already = any(f"artículo {art_num}." in r["snippet"].lower() for r in result_list)
                if already:
                    continue
                for hit in exact_article_chunks(col, resolved_law, art_num):
                    result_list.insert(0, {
                        "score": 100,
                        "semaforo": vvca_semaforo(100),
                        "source": hit["source"],
                        "page": hit["page"],
                        "snippet": hit["snippet"],
                        "match": "literal",
                    })
        if json_output:
            print(json.dumps(result_list, ensure_ascii=False, indent=2))
        return result_list


# ─────────────────────────────────────────
# CLI
# ─────────────────────────────────────────

def OpenNotebook_query(text: str, n: int = 5, law: Optional[str] = None, json_output: bool = False, verbose: bool = False) -> List[Dict]:
    """Convenience wrapper: crea instancia de OpenNotebook y ejecuta query semántico."""
    notebook = OpenNotebook()
    return notebook.query(text, n=n, law=law, json_output=json_output, verbose=verbose)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="OpenNotebook v4.0 — RAG Legal Itosturre",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python OpenNotebook.py ingest --directory /ruta/pdfs/
  python OpenNotebook.py ingest --directory /ruta/pdfs/ --clear
  python OpenNotebook.py ingest --directory /ruta/pdfs/ --reingest
  python OpenNotebook.py audit --text "Art. 247 CPF establece..."
  python OpenNotebook.py audit --file borrador.md --verbose
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
    query_parser.add_argument("--law", help="Filtrar por ley: acepta un alias del LAW_SOURCE_MAP (p. ej. 'cpeum', 'código civil de jalisco') o el nombre exacto del PDF indexado")
    query_parser.add_argument("--json", action="store_true", help="Emitir resultados también en formato JSON")

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

        # Además del archivo de calibración (que solo mueve un umbral), la
        # corrección se guarda como evento buscable: el criterio de un operador
        # con años de foro es el activo que hoy se pierde entre sesiones.
        # vvca_corrections.json queda intacto — 'calibrate' sigue leyéndolo igual.
        try:
            from itosturre.memoria import registrar_seguro

            registrar_seguro(
                "correccion_criterio_pjf",
                f"{args.ref}: el semáforo correcto es {args.semaforo} "
                f"(el sistema auditó {args.score_auditado})",
                details={"nota": args.nota, "referencia": args.ref,
                         "semaforo_correcto": args.semaforo,
                         "score_auditado": args.score_auditado},
                raiz=str(_BASE_DIR),
                importance=1,
            )
        except Exception:  # noqa: BLE001 — la memoria nunca bloquea la calibración
            pass
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
        # Delega en OpenNotebook.query() en vez de reimplementar la búsqueda: evita
        # duplicar el filtro --law y el fallback literal por artículo (antes vivían
        # por separado aquí y en el método de clase, y solo uno de los dos se corregía).
        notebook = OpenNotebook()
        result_list = notebook.query(args.texto, n=args.n, law=getattr(args, "law", None))
        print(f"\n🔍 Búsqueda: \"{args.texto}\" — top {len(result_list)} resultados")
        for r in result_list:
            etiqueta = " [coincidencia literal]" if r.get("match") == "literal" else ""
            print(f"{r['semaforo']} Score {r['score']} | {r['source']} pág.{r['page']}{etiqueta}")
            print(f"   {r['snippet'][:200]}")
            print()
        # Output JSON if requested
        if getattr(args, "json", False):
            print(json.dumps(result_list, ensure_ascii=False, indent=2))

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
                f"RAG: {vs['score_rag']} {vs['semaforo_rag']} · SJF: {vs['score_sjf']} {vs['semaforo_sjf']}"
                f"  🟢{vs['verdes']} 🟡{vs['amarillos']} 🔴{vs['rojos']}"
                f"  · Veredicto: {vs['veredicto']['semaforo']} {vs['veredicto']['razon']}",
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
    try:
        main()
    except DependenciaFaltante as exc:
        # Mismo código de salida (1) que el ImportError que antes abortaba al importar,
        # con un mensaje que dice qué paquete falta y cómo instalarlo.
        print(f"❌ {exc}", file=sys.stderr)
        sys.exit(1)
