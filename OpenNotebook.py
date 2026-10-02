"""
OpenNotebook.py v4.0 — RAG Legal Itosturre
Motor de auditoría anti-alucinaciones con semáforo VVCA.

Cambios R4d (jurisprudencia determinista; itosturre/audit/jurisprudence.py):
  ✅ Registros sin distinguir mayúsculas ("REGISTRO DIGITAL: …", "Registro Digital …",
     "registro IUS"; "Registro:", "Reg." o "IUS" solo con contexto de tesis) y sin números
     que no son registros ("2006224/2026", 8 dígitos): una tesis invocada ya no desaparece
     (R4-D07). Enumeraciones (",", "y", "o", "y/o", "/"): una tesis por número; un conector
     no reconocido deja 🟡 COBERTURA INCOMPLETA. El contexto no cruza el registro anterior.
  ✅ Cotejo del rubro: se extrae el rubro invocado (tras "rubro:"/"título y subtítulo:",
     entre comillas o en mayúsculas junto al registro) y se compara normalizado (NFKD sin
     acentos, casefold, sin puntuación no numérica; R4-D13). 🟢 solo con igualdad literal sin
     marca de supresión ni texto omitido tras el marcador; truncado → 🟡 RUBRO PARCIAL;
     polaridad invertida ("NO ES…", "IMPROCEDENTE"…) → 🔴 (R4-D14); otra diferencia → 🟡 o
     🔴 (< 40 %); sin rubro invocado o con asociación incierta → 🟡, solo acredita el registro.
  ✅ Vigencia nunca "vigente" sin fuente: ``no_consultada``/``no_reconocida`` como aviso
     informativo (``avisos``, fuera de ``alerts``) sin cambiar el semáforo; una pérdida
     registrada en cualquier campo prevalece; campos en conflicto → 🟡.
  ✅ La retención transitoria del 🟢 de "solo tesis" se mantiene (adjudicación del 2-oct-2026).

Cambios R4c (veredicto honesto):
  ✅ Precepto derogado ("Artículo 64.- (Se deroga).") → 🟡 PRECEPTO DEROGADO, nunca 🟢
     (criterio por defecto; el responsable puede endurecerlo).
  ✅ La fuente esperada nunca se borra: evidencia de otro ordenamiento → 🟡, nunca 🟢 con
     "Fuente correcta" (antes, si el filtro por fuente fallaba, source_match era True).
  ✅ El 🟢 enuncia solo lo verificado ("Normativa verificada; sin tesis citadas") y una
     dimensión sin citas no se califica como fallida (score None, semáforo neutro ⚪).
  ✅ Alcance explícito (``alcance_verificacion``): existencia y ubicación del precepto en el
     corpus local; 🟢 no significa que el precepto diga lo que el escrito afirma.
  ✅ Ronda 2: la unidad citada (fracción, inciso, párrafo…) se coteja en el texto; variantes
     inequívocas de la derogación y fórmula ambigua → 🟡; encabezado sin cuerpo → continuación
     del mismo precepto o 🟡 EVIDENCIA INCOMPLETA; tesis parciales cuentan en el veredicto;
     el 🟢 de "solo tesis" queda retenido (🟡) hasta R4d.

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
from itosturre.audit.evidence import (
    DEROGACION_AMBIGUA,
    DEROGADO,
    cotejar_precepto,
    describir_unidad,
    select_article_evidence,
)
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
    ESTADOS_VIGENCIA,
    RUBRO_BLOQUEANTE,
    RUBRO_COINCIDE,
    RUBRO_INVERTIDO,
    RUBRO_NO_ASOCIADO,
    RUBRO_NO_LITERAL,
    RUBRO_PARCIAL,
    RUBRO_SIN_COTEJO,
    RUBRO_SIN_FUENTE,
    RUBRO_SIN_INVOCADO,
    UMBRAL_TRASLAPE_RUBRO,
    VIGENCIA_EN_CONFLICTO,
    VIGENCIA_NO_CONSULTADA,
    VIGENCIA_PERDIDA,
    classify_fuerza_vinculante,
    cotejar_rubro,
    extraer_rubro_invocado,
    extraer_rubro_posterior,
    normalizar_vigencia,
)
from itosturre.audit.policy import (
    ALCANCE_JURISPRUDENCIA,
    ALCANCE_JURISPRUDENCIA_SIN_RUBRO,
    ALCANCE_NORMATIVA,
    alcance_jurisprudencia,
    disclaimer_graduado,
    semaforo_dimension,
    vvca_score,
    vvca_semaforo,
)
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


# R4d (R4-D07) — Registro de una tesis, en cualquier caja: "Registro digital: 2006224",
# "REGISTRO DIGITAL: 0000001", "Registro Digital 0000002", "Registro: 2019456", "registro IUS
# 2019456", "IUS: 2019456", "Reg. 2028965", "registro número 2006224". En plural o en
# enumeración ("registros digitales 2006224 y 2006225", "2006224 / 2032506", "2006224 y/o
# 2032506") cada número es una tesis. Antes solo "Registro"/"registro" (con "digital" en
# minúscula) y un número: el resto desaparecía de la auditoría.
# Ronda 2: el número es de 6 o 7 dígitos (los registros digitales del SJF); no lo es un número
# de 8 dígitos ("20261002", forma de fecha o folio) ni el de "N/AAAA" ("2006224/2026", un
# expediente). "registro digital" y "registro IUS" bastan; "Registro", "Reg." o "IUS" solos
# exigen contexto de tesis en el párrafo (``_CONTEXTO_TESIS_RE``).
_NUMERO_REGISTRO = r"\d{6,7}(?!\d|[/\-]\d{1,5}(?!\d))"
REGISTRO_TESIS_RE = re.compile(
    r"\b(?P<cabeza>registros?(?:\s+(?:digital(?:es)?|ius))?"
    r"|regs?\.(?:\s*(?:digital(?:es)?|ius))?|ius)"
    r"(?:\s*(?:n[úu]m(?:eros?|s?\.)|nos?\.|n\.?\s*[°º]s?\.?))?"
    r"\s*[:.]?\s*"
    rf"(?P<numeros>(?<![\d/]){_NUMERO_REGISTRO}"
    rf"(?:\s*(?:,|;|y/o|/|\b(?:y|e|o|u|ó)\b)\s*{_NUMERO_REGISTRO})*)",
    re.IGNORECASE,
)
_NUMERO_REGISTRO_RE = re.compile(r"\d{6,7}")
# Un número suelto de registro tras la enumeración, con un conector no reconocido ("2006224
# así como 2032506"): no se omite en silencio, queda como cobertura incompleta.
_NUMERO_SUELTO_RE = re.compile(rf"(?<![\d/]){_NUMERO_REGISTRO}")
# Contexto de tesis para las cabezas ambiguas ("Registro:", "Reg.", "IUS"): mención de tesis,
# jurisprudencia, rubro, título y subtítulo, Semanario, Gaceta, época o una clave ("P./J.",
# "J/7", "(10a.)").
_CONTEXTO_TESIS_RE = re.compile(
    r"\b(?:tesis|jurisprudencias?|rubros?|t[íi]tulo\s+y\s+subt[íi]tulo|semanario|gaceta"
    r"|sjf|[ée]poca|ejecutorias?|precedentes?)\b|\b(?:\d{1,2}a|P|PR|PC)\.\s*/\s*J\."
    r"|\bJ/\d|\(\d{1,2}a\.\)",
    re.IGNORECASE,
)
# Texto previo a cada registro donde se busca el rubro invocado (antes, 400 caracteres que
# podían incluir el rubro de la tesis anterior).
VENTANA_RUBRO = 1500


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

    Tesis (R4d, R4-D07): una referencia por cada registro, en cualquier caja
    (``REGISTRO_TESIS_RE``). ``ctx_invocado`` es el texto previo (a lo sumo
    ``VENTANA_RUBRO`` caracteres) donde ``build_vvca_tesis`` busca el rubro invocado; nunca
    cruza el registro anterior, para no atribuirle a una tesis el rubro de otra. Campos
    opcionales (solo cuando aplican): ``ctx_recortado=True`` si la ventana se recortó antes de
    llegar al inicio o al registro anterior; ``registro_en_enumeracion=True`` en "registros
    digitales 1 y 2" (``ctx_invocado`` vacío: el rubro de cada una no se asocia con certeza);
    ``ctx_posterior`` con el marcador y el rubro PEGADOS a la derecha del registro
    ("registro digital 164618, de rubro y texto: «…»"), que prevalece sobre el contexto previo.
    Lo consumido así ya no cuenta como contexto de la tesis siguiente. Ronda 2: un número de
    registro tras la enumeración con un conector no reconocido queda como referencia de
    cobertura incompleta (``coverage_gap``), y "Registro"/"Reg."/"IUS" sin contexto de tesis
    en el párrafo no son una tesis.
    """
    refs = extraer_articulos(text, _catalogo())

    coincidencias = [m for m in REGISTRO_TESIS_RE.finditer(text) if _es_registro_de_tesis(text, m)]
    fin_anterior = 0
    for indice, m in enumerate(coincidencias):
        numeros = list(_NUMERO_REGISTRO_RE.finditer(text, m.start("numeros"), m.end()))
        inicio_ventana = m.start() - VENTANA_RUBRO
        siguiente = (coincidencias[indice + 1].start() if indice + 1 < len(coincidencias)
                     else len(text))
        posterior = (extraer_rubro_posterior(text[m.end(): siguiente])
                     if len(numeros) == 1 else None)
        for numero in numeros:
            ref = {
                "type": "jurisprudencia",
                "registro": numero.group(),
                "raw": text[m.start(): numero.end()].strip(),
                "ctx_invocado": (
                    "" if len(numeros) > 1
                    else text[max(0, fin_anterior, inicio_ventana): m.start()].strip()
                ),
            }
            if len(numeros) > 1:
                ref["registro_en_enumeracion"] = True
            elif inicio_ventana > fin_anterior:
                ref["ctx_recortado"] = True
            if posterior:
                ref["ctx_posterior"] = text[m.end(): m.end() + posterior["fin"]]
            refs.append(ref)
        fin_anterior = m.end() + (posterior["fin"] if posterior else 0)
        # Ronda 2: nunca "solo el primero en silencio". Un número de registro pegado a la
        # enumeración con un conector no reconocido queda como cobertura incompleta.
        if not posterior:
            cola = re.split(r"\n|\.\s|[\"“«]", text[m.end(): min(m.end() + 40, siguiente)])[0]
            suelto = _NUMERO_SUELTO_RE.search(cola)
            if suelto:
                conector = " ".join(cola[:suelto.start()].split()) or "sin conector"
                refs.append({
                    "type": "jurisprudencia",
                    "registro": suelto.group(),
                    "raw": text[m.start(): m.end() + suelto.end()].strip(),
                    "ctx_invocado": "",
                    "coverage_gap": (
                        f"número junto al registro con un conector no reconocido («{conector}»): "
                        f"no se extrajo con certeza como registro de una tesis"
                    ),
                })

    return refs


def _es_registro_de_tesis(text: str, m: "re.Match") -> bool:
    """¿La coincidencia de ``REGISTRO_TESIS_RE`` es el registro de una tesis? (ronda 2, D07).

    "registro digital" y "registro IUS" bastan. "Registro", "Reg." o "IUS" solos exigen
    contexto de tesis en el mismo párrafo (hasta 400 caracteres antes y 250 después): así
    "expediente Reg. 2006224/2026", "Registro 1234567 de la oficialía" o un inventario "IUS
    1234567" no se toman como tesis."""
    cabeza = re.sub(r"\s+", " ", m.group("cabeza").lower())
    if re.search(r"digital|ius", cabeza) and cabeza != "ius":
        return True
    inicio = max(0, m.start() - 400, text.rfind("\n\n", 0, m.start()) + 1)
    fin_parrafo = text.find("\n\n", m.end())
    fin = min(len(text), m.end() + 250, fin_parrafo if fin_parrafo >= 0 else len(text))
    entorno = text[inicio:m.start()] + " " + text[m.end():fin]
    return bool(_CONTEXTO_TESIS_RE.search(entorno))


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


def _unidades_de(ref: Dict) -> List[Dict]:
    """Unidad citada de una referencia (R4c, ronda 2): ``unidad_citada`` de la extracción o,
    en una referencia construida a mano, su ``fraction``. [] = el artículo completo."""
    if ref.get("unidad_citada") is not None:
        return [dict(u) for u in ref["unidad_citada"]]
    fraccion = (ref.get("fraction") or "").strip().rstrip(".,;")
    return [{"tipo": "fraccion", "valor": fraccion}] if fraccion else []


def _preferir_fuente(results: Optional[Dict], fuente: Optional[str]) -> Optional[Dict]:
    """R4c (R4-D09): resultados de una consulta SIN filtro reducidos a los de la fuente
    esperada, si alguno lo es; si ninguno, los resultados tal cual (la evidencia será de
    otro ordenamiento y ``audit`` la reporta así). Conserva la forma de ChromaDB."""
    if not results or not fuente:
        return results
    documentos = (results.get("documents") or [[]])[0] or []
    metadatas = (results.get("metadatas") or [[]])[0] or []
    distancias = (results.get("distances") or [[]])[0] or []
    indices = [
        i for i, meta in enumerate(metadatas)
        if i < len(documentos) and (meta or {}).get("source") == fuente
    ]
    if not indices:
        return results
    return {
        "documents": [[documentos[i] for i in indices]],
        "metadatas": [[metadatas[i] for i in indices]],
        "distances": [[distancias[i] for i in indices if i < len(distancias)]],
    }


def build_vvca(
    ref: Dict,
    distance: float,
    source_match: bool,
    source_file: str,
    page: str,
    metadata_verificado: bool = False,
    article_heading_verified: Optional[bool] = None,
    derogado: bool = False,
    *,
    unidad_derogada: Optional[str] = None,
    derogacion_ambigua: bool = False,
    unidad_no_cotejada: Optional[str] = None,
    evidencia_incompleta: bool = False,
) -> Dict:
    """Score, semáforo y explicación VVCA de una cita normativa con evidencia.

    R4c: ``derogado`` (precepto completo) y ``unidad_derogada`` (fracción o inciso citados,
    p. ej. "fracción I") y ``derogacion_ambigua`` limitan a 60–84: la unidad se ubicó y su
    texto vigente no la sostiene. ``unidad_no_cotejada`` (motivo) y ``evidencia_incompleta``
    solo impiden el 🟢 (tope 84): no tocan el piso, así que la rama de distancia alta (R4-D10,
    pendiente del responsable) conserva su severidad.
    """
    # Desde R4c ``source_match`` compara de verdad la fuente recuperada con la esperada
    # (R4-D09): la penalización −15 de ``vvca_score`` deja de ser inalcanzable.
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
    # R4c (R4-D09): evidencia de OTRO ordenamiento. No acredita la cita (nunca 🟢) ni la
    # refuta (nunca 🔴): el precepto no se cotejó en la ley citada. 🟡 en ambos sentidos.
    if not source_match:
        score = max(60, min(score, 84))
    # R4c (R4-D08): precepto (o unidad citada) derogado, o fórmula de derogación ambigua
    # junto al encabezado. Se localizó, pero el texto vigente no lo sostiene: nunca 🟢. 🟡
    # es el criterio por defecto (el responsable puede endurecerlo a 🔴).
    if derogado or unidad_derogada or derogacion_ambigua:
        score = max(60, min(score, 84))
    # R4c (ronda 2): la unidad citada no se cotejó, o el cuerpo del precepto quedó incompleto:
    # el encabezado del artículo no basta para un 🟢.
    if unidad_no_cotejada or evidencia_incompleta:
        score = min(score, 84)
    semaforo = vvca_semaforo(score)
    law = ref.get("law", "desconocido")
    art = ref.get("article", "?")
    frac = ref.get("fraction", "")
    art_label = f"Art. {art}" + (f" fr. {frac}" if frac else "")

    if not source_match:
        v_verificacion = (
            f"Evidencia de otro ordenamiento: no acredita la cita en la ley citada "
            f"(dist={distance:.3f})"
        )
    elif derogado:
        v_verificacion = (
            f"Precepto derogado: tras el encabezado exacto, el texto vigente del corpus solo "
            f"indica que se deroga (dist={distance:.3f})"
        )
    elif unidad_derogada:
        v_verificacion = (
            f"Unidad citada derogada ({unidad_derogada}): el texto vigente del corpus solo "
            f"indica que se deroga; el resto del artículo no se declara derogado "
            f"(dist={distance:.3f})"
        )
    elif derogacion_ambigua:
        v_verificacion = (
            f"Fórmula de derogación ambigua junto al encabezado: verificar qué parte está "
            f"derogada (dist={distance:.3f})"
        )
    elif evidencia_incompleta:
        v_verificacion = (
            f"Evidencia incompleta: el fragmento trae el encabezado exacto, pero no cuerpo "
            f"suficiente para cotejar el precepto (dist={distance:.3f})"
        )
    elif metadata_verificado:
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
    if unidad_no_cotejada:
        v_verificacion = f"{v_verificacion}; unidad citada no cotejada: {unidad_no_cotejada}"
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
    if derogado:
        explicabilidad["precepto_derogado"] = True
    if unidad_derogada:
        explicabilidad["unidad_derogada"] = unidad_derogada
    if derogacion_ambigua:
        explicabilidad["derogacion_ambigua"] = True
    if unidad_no_cotejada:
        explicabilidad["unidad_no_cotejada"] = unidad_no_cotejada
    if evidencia_incompleta:
        explicabilidad["evidencia_incompleta"] = True
    return {
        "score": score,
        "semaforo": semaforo,
        "V_verificacion": v_verificacion,
        "V_validacion": v_validacion,
        "C_contextualizacion": c_contextualizacion,
        "A_auditabilidad": a_auditabilidad,
        "explicabilidad": explicabilidad,
    }


MOTIVO_ENUMERACION = (
    "registro citado en una enumeración (\"registros digitales … y …\"): el rubro de cada "
    "tesis no se asocia con certeza; no hubo cotejo del rubro y la tesis solo acredita la "
    "existencia del registro"
)


def build_vvca_tesis(ref: Dict, item: Dict, source_file: str) -> Dict:
    """Semáforo de una tesis localizada en el corpus local (R4d: cotejo determinista del rubro).

    El puntaje base es el de siempre: 95 jurisprudencia, 72 aislada. El rubro invocado se
    extrae de ``ctx_invocado`` (``extraer_rubro_invocado``) y se coteja con el real
    (``cotejar_rubro``):
      - coincide (igualdad literal normalizada) → puntaje base (🟢 si es jurisprudencia);
      - discrepante o con el sentido invertido → 0 (🔴 bloqueante: un registro real con rubro
        falso es más peligroso que uno inexistente);
      - parcial, no literal, sin rubro invocado o sin rubro en la fuente → a lo sumo 84 (🟡,
        traza ``partial``): ningún heurístico de traslape concede 🟢.
    La vigencia nunca se asume: sin dato es ``no_consultada`` (``normalizar_vigencia``) y no
    cambia el puntaje; superada/interrumpida/sustituida bloquean en el veredicto, como antes.
    """
    tipo    = item.get("tipo_tesis", "") or ""
    sala    = item.get("sala", "")
    epoca   = item.get("epoca", "")
    materia = item.get("materia", "")
    numero  = item.get("numero_tesis", "")
    registro = ref.get("registro", "?")
    # Rubro original (con acentos) para mostrarlo; la comparación lo normaliza.
    rubro_real = " ".join(str(item.get("rubro") or "").split())

    # Rubro invocado: nunca el de otra tesis (en una enumeración no se asocia ninguno). El
    # marcador pegado a la derecha del registro ("…, de rubro: «…»") prevalece.
    if ref.get("registro_en_enumeracion"):
        invocado = None
    elif ref.get("ctx_posterior"):
        invocado = extraer_rubro_posterior(ref["ctx_posterior"])
    else:
        invocado = extraer_rubro_invocado(
            ref.get("ctx_invocado") or "", recortado=bool(ref.get("ctx_recortado"))
        )
    cotejo = cotejar_rubro(invocado, rubro_real)
    resultado = cotejo["resultado"]
    motivo = cotejo["motivo"]
    if resultado == RUBRO_SIN_INVOCADO and ref.get("registro_en_enumeracion"):
        motivo = MOTIVO_ENUMERACION
    rubro_invocado = invocado["texto"] if invocado else ""
    overlap = cotejo["traslape"]

    es_jurisprudencia = bool(re.search(r"jurisprudencia", tipo, re.I))
    base = 95 if es_jurisprudencia else 72
    rubro_mismatch = resultado in RUBRO_BLOQUEANTE
    if rubro_mismatch:
        score = 0  # Registro real con rubro falso es más peligroso que uno inexistente
        verificacion = (
            f"⚠️ DISCREPANCIA: Reg. {registro} existe en corpus pero su rubro real "
            f"NO coincide con lo invocado en el documento ({motivo}). "
            f"Rubro invocado: '{rubro_invocado}'. Rubro real: '{rubro_real}'."
        )
    else:
        # Solo la igualdad literal conserva el puntaje base: lo demás queda en 🟡 (≤ 84).
        score = base if resultado == RUBRO_COINCIDE else min(base, 84)
        verificacion = f"Registro {registro} encontrado en corpus SJF local; {motivo}"

    # Estado de vigencia (R4d): solo el que registró el corpus o el scraper, leyendo todos los
    # campos. Sin dato → "no_consultada" (antes se asumía "vigente"); un valor desconocido →
    # "no_reconocida". Una pérdida registrada en cualquier campo prevalece y bloquea en el
    # veredicto (falso verde), como antes; campos en conflicto sin pérdida → 🟡 (ronda 2).
    vigencia = normalizar_vigencia(item)
    estado_vigencia = vigencia["estado"]
    if estado_vigencia == VIGENCIA_EN_CONFLICTO and not rubro_mismatch:
        score = min(score, 84)
        verificacion += (
            f"; vigencia en conflicto entre los campos de la fuente ({vigencia['registrado']})"
        )

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

    return {
        "score": score,
        "semaforo": semaforo,
        "rubro_mismatch": rubro_mismatch,
        # R4d (campo añadido): resultado del cotejo del rubro (``RUBRO_*``).
        "cotejo_rubro": resultado,
        "fuerza_vinculante": fuerza,
        "estado_vigencia": estado_vigencia,
        "V_verificacion": verificacion,
        "V_validacion": tipo_label,
        "C_contextualizacion": contexto,
        "A_auditabilidad": f"{numero} · Reg. {registro} · {sala} · {source_file}",
        # Traza reproducible por cita (explicabilidad). R4d: rubros completos y originales
        # (antes, 160 caracteres; el "invocado" era el contexto previo, no el rubro).
        "explicabilidad": {
            "registro": registro,
            "overlap_rubro": round(overlap, 3) if overlap is not None else None,
            "umbral_mismatch": UMBRAL_TRASLAPE_RUBRO,
            "rubro_real": rubro_real,
            "rubro_invocado": rubro_invocado,
            "estado_vigencia": estado_vigencia,
            "fuente": source_file,
            # R4d (campos añadidos).
            "cotejo_rubro": resultado,
            "motivo_cotejo": motivo,
            "rubro_invocado_metodo": invocado["metodo"] if invocado else None,
            "rubro_truncado": bool(invocado and invocado["truncado"]),
            "polaridad": cotejo["polaridad"],
            "vigencia_registrada": vigencia["registrado"],
            # Ronda 2: campos de vigencia con dato y si discrepan.
            "vigencia_campos": vigencia["valores"],
            "vigencia_en_conflicto": vigencia["conflicto"],
            "texto_omitido": (invocado or {}).get("texto_omitido"),
            "asociacion_incierta": (invocado or {}).get("asociacion_incierta"),
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


def _puntaje(score: Optional[float]) -> str:
    """Subpuntaje para mostrar: "—" cuando la dimensión no tiene evidencia evaluable."""
    return "—" if score is None else f"{score}"


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _resumen_rag(score: Optional[float], semaforo: str, total: int,
                 no_verificables: int, refutadas: int) -> str:
    """Parte normativa del ``summary`` (R4c, R4-D12): "sin citas" si no hay artículos; si
    los hay, el subpuntaje va acompañado de cuántas citas quedaron sin verificar o
    refutadas, para que un 🟢 del promedio nunca las oculte."""
    if total == 0:
        return "RAG sin citas"
    detalle = [f"{total} arts"]
    if no_verificables:
        detalle.append(_plural(no_verificables, "no verificable", "no verificables"))
    if refutadas:
        detalle.append(_plural(refutadas, "refutada", "refutadas"))
    return f"RAG {_puntaje(score)} {semaforo} ({'; '.join(detalle)})"


def _resumen_sjf(score: Optional[float], semaforo: str, total: int, ok: int,
                 discrepantes: int, no_encontradas: int, parciales: int = 0) -> str:
    """Parte de jurisprudencia del ``summary`` (R4c, R4-D12): "sin citas" si no se invocó
    ninguna tesis (antes "SJF 0.0 🔴 (0/0 tesis ok)"). "ok" cuenta solo las verificadas
    (ronda 2); las parciales se dicen aparte."""
    if total == 0:
        return "SJF sin citas"
    return (
        f"SJF {_puntaje(score)} {semaforo} ({ok}/{total} tesis ok)"
        + (f" — {discrepantes} rubro discrepante" if discrepantes else "")
        + (f", {no_encontradas} no encontradas" if no_encontradas else "")
        + (f", {_plural(parciales, 'parcial', 'parciales')}" if parciales else "")
    )


def _oracion(texto: str) -> str:
    """Primera letra en mayúscula (para encadenar el motivo del cotejo en una alerta)."""
    return texto[:1].upper() + texto[1:] if texto else texto


def _alerta_rubro(registro: str, vvca: Dict) -> Optional[str]:
    """Alerta del cotejo del rubro de una tesis localizada (R4d), con los rubros ORIGINALES
    (acentos incluidos; Regla 1). Sin alerta cuando el rubro coincide literalmente."""
    cotejo = vvca.get("cotejo_rubro")
    explicabilidad = vvca.get("explicabilidad") or {}
    real = explicabilidad.get("rubro_real") or ""
    invocado = explicabilidad.get("rubro_invocado") or ""
    motivo = _oracion(explicabilidad.get("motivo_cotejo") or "")
    if cotejo == RUBRO_INVERTIDO:
        polaridad = "; ".join(explicabilidad.get("polaridad") or [])
        return (
            f"🔴 RUBRO DISCREPANTE — SENTIDO INVERTIDO: Registro digital {registro}. "
            f"Diferencia de polaridad: {polaridad}. Rubro invocado: «{invocado}». Rubro real: "
            f"«{real}». USO PROCESAL PROHIBIDO: corregir o sustituir la cita."
        )
    if cotejo in RUBRO_BLOQUEANTE:
        return (
            f"🔴 RUBRO DISCREPANTE: Registro digital {registro} existe en el corpus local, "
            f"pero {explicabilidad.get('motivo_cotejo') or 'su rubro no coincide'}. "
            f"Rubro invocado: «{invocado}». Rubro real: «{real}». USO PROCESAL PROHIBIDO: "
            f"sustituir la cita."
        )
    if cotejo == RUBRO_PARCIAL:
        return (
            f"🟡 RUBRO PARCIAL: Registro digital {registro} — {motivo}. Rubro invocado: "
            f"«{invocado}». Rubro real: «{real}». Cotejar el rubro completo en "
            f"sjf2.scjn.gob.mx antes de citar."
        )
    if cotejo == RUBRO_NO_LITERAL:
        return (
            f"🟡 RUBRO NO COINCIDE LITERALMENTE: Registro digital {registro} — {motivo}. "
            f"Rubro invocado: «{invocado}». Rubro real: «{real}». Cotejar en "
            f"sjf2.scjn.gob.mx antes de citar."
        )
    if cotejo == RUBRO_SIN_INVOCADO:
        return (
            f"🟡 SIN RUBRO INVOCADO: Registro digital {registro} — {motivo}. Rubro real: "
            f"«{real}». Cotejar que el criterio respalde lo afirmado antes de citar."
        )
    if cotejo == RUBRO_SIN_FUENTE:
        return (
            f"🟡 RUBRO NO DISPONIBLE: Registro digital {registro} — {motivo}. Verificar el "
            f"rubro en sjf2.scjn.gob.mx antes de citar."
        )
    if cotejo == RUBRO_NO_ASOCIADO:
        return (
            f"🟡 RUBRO NO ASOCIADO CON CERTEZA: Registro digital {registro} — {motivo}. Texto "
            f"tomado como rubro: «{invocado}». Rubro real: «{real}». Precisar qué tesis se "
            f"invoca antes de citar."
        )
    return None


def _alerta_vigencia(registro: str, vvca: Dict) -> Optional[str]:
    """Alerta (no aviso) de vigencia en conflicto entre los campos de la fuente (ronda 2): sí
    cambia el semáforo (🟡 mínimo). Una pérdida registrada ya bloquea en el veredicto."""
    if vvca.get("estado_vigencia") != VIGENCIA_EN_CONFLICTO or vvca.get("rubro_mismatch"):
        return None
    registrada = (vvca.get("explicabilidad") or {}).get("vigencia_registrada")
    return (
        f"🟡 VIGENCIA EN CONFLICTO: Registro digital {registro} — la fuente registra valores "
        f"distintos («{registrada}»). Verificar la vigencia en sjf2.scjn.gob.mx antes de citar."
    )


def _aviso_vigencia(registro: str, vvca: Dict) -> Optional[str]:
    """Aviso informativo (ℹ️) de una tesis localizada cuya vigencia nadie registró (R4d).

    Criterio por defecto: no cambia el semáforo. Sin aviso si la fuente registra un estado
    conocido (vigente, o perdido, que ya bloquea en el veredicto) o si la cita ya está
    bloqueada por su rubro (hay que sustituirla de todos modos)."""
    estado = vvca.get("estado_vigencia")
    if (estado in ESTADOS_VIGENCIA or estado == VIGENCIA_EN_CONFLICTO
            or vvca.get("rubro_mismatch")):
        return None
    if estado == VIGENCIA_NO_CONSULTADA:
        return (
            f"ℹ️ VIGENCIA NO CONSULTADA: Registro digital {registro} — ni el corpus local ni el "
            f"scraper registran la vigencia del criterio; no se asume vigente. No cambia el "
            f"semáforo: verificar en sjf2.scjn.gob.mx (notas y ejecutorias) que no esté "
            f"superado, interrumpido o sustituido."
        )
    registrada = (vvca.get("explicabilidad") or {}).get("vigencia_registrada")
    return (
        f"ℹ️ VIGENCIA NO RECONOCIDA: Registro digital {registro} — la fuente registra "
        f"«{registrada}», que no es un estado reconocido ({', '.join(ESTADOS_VIGENCIA)}). No "
        f"cambia el semáforo: verificar la vigencia en sjf2.scjn.gob.mx."
    )


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
    # R4d: avisos informativos de vigencia (ℹ️). Ronda 2: van en ``avisos`` (con
    # ``avisos_count``), no en ``alerts``: ``alerts_count`` conserva su significado anterior.
    avisos_vigencia: List[str] = []
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

            filtro_fuente_fallido = False
            if results is None:
                try:
                    # Encoding asimétrico (retrieval.query); filtro por fuente si se conoce.
                    results = collection.query(
                        query_embeddings=[codificar(query)],
                        n_results=3,
                        where=where_filter,
                    )
                except Exception:
                    # where_filter puede fallar (ChromaDB rechaza el filtro): consulta sin
                    # filtro. R4c (R4-D09): la fuente esperada YA NO se borra (antes
                    # ``expected_source = None`` hacía source_match True por construcción y la
                    # evidencia de otro ordenamiento salía 🟢 "Fuente correcta"). Se prefiere
                    # la evidencia de la ley citada y, si no la hay, se reporta como de otro
                    # ordenamiento.
                    results = _preferir_fuente(
                        collection.query(
                            query_embeddings=[codificar(query)],
                            n_results=3,
                        ),
                        expected_source,
                    )
                    filtro_fuente_fallido = True

            selected = select_article_evidence(results, ref["article"])
            if selected:
                best_doc = selected["document"]
                best_meta = selected["metadata"]
                best_source = best_meta.get("source", "desconocido")
                best_distance = selected["distance"]
                article_heading_verified = selected["heading_verified"]
                # R4c (R4-D09): comparación real con la fuente esperada (desde R4b siempre
                # existe aquí: una cita sin ley identificada no llega a la consulta).
                source_match = best_source == expected_source
                # La metadata solo corrobora si la evidencia es de la ley citada.
                metadata_hit = metadata_candidate_found and article_heading_verified and source_match

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

                # R4c — Cotejo del precepto ubicado (encabezado exacto en la ley citada): su
                # cuerpo hasta el encabezado de otro artículo, reunido con la continuación del
                # MISMO precepto (misma fuente y etiqueta, fragmentos consecutivos) cuando el
                # fragmento termina antes; la derogación (D08) solo de lo que sigue a SU
                # encabezado, y la unidad citada (fracción, inciso…) en ese cuerpo. Nunca se
                # examina el texto de otro artículo ni el de otro ordenamiento.
                unidades = _unidades_de(ref)
                cotejo = None
                if source_match and article_heading_verified:
                    candidatos = [
                        (doc, meta) for doc, meta in zip(
                            (results.get("documents") or [[]])[0] or [],
                            (results.get("metadatas") or [[]])[0] or [],
                        )
                        if (meta or {}).get("source") == best_source
                    ]
                    cotejo = cotejar_precepto(best_doc, best_meta, ref["article"], unidades,
                                              candidatos)
                derogado = bool(cotejo and cotejo["derogacion"] == DEROGADO)
                derogacion_ambigua = bool(cotejo and cotejo["derogacion"] == DEROGACION_AMBIGUA)
                evidencia_incompleta = bool(cotejo and not cotejo["completo"])
                unidad = (cotejo or {}).get("unidad")
                unidad_derogada = None
                unidad_no_cotejada = None
                if unidad and unidad["estado"] == "derogada":
                    unidad_derogada = ", ".join(unidad["derogadas"])
                elif unidad and unidad["estado"] == "ambigua":
                    derogacion_ambigua = True
                elif unidad and unidad["estado"] == "no_cotejada":
                    unidad_no_cotejada = unidad["motivo"] + (
                        " (evidencia incompleta)" if evidencia_incompleta else ""
                    )
                elif unidades and source_match and not article_heading_verified:
                    unidad_no_cotejada = "sin el encabezado exacto del artículo no se coteja la unidad"

                vvca = build_vvca(
                    ref=ref,
                    distance=best_distance,
                    source_match=source_match,
                    source_file=best_source,
                    page=best_meta.get("page", "?"),
                    metadata_verificado=metadata_hit,
                    article_heading_verified=article_heading_verified,
                    derogado=derogado,
                    unidad_derogada=unidad_derogada,
                    derogacion_ambigua=derogacion_ambigua,
                    unidad_no_cotejada=unidad_no_cotejada,
                    evidencia_incompleta=evidencia_incompleta,
                )
                if filtro_fuente_fallido:
                    vvca["explicabilidad"]["filtro_fuente_fallido"] = True
                if cotejo and cotejo["continuaciones"]:
                    vvca["explicabilidad"]["fragmentos_continuacion"] = cotejo["continuaciones"]

                entry = {
                    "reference": ref["raw"],
                    "law": ref["law"],
                    "article": ref["article"],
                    "ref_type": "normativa",
                    "source_file": best_source,
                    "page": best_meta.get("page", "?"),
                    "expected_source": expected_source,
                    "law_inferred": ref.get("law_inferred", False),
                    # R4b (campos añadidos): cómo se resolvió la ley de la cita y si es una
                    # ley inferida de otro párrafo que el abogado debe confirmar.
                    "law_method": ref.get("law_method"),
                    "law_requires_confirmation": bool(ref.get("law_requires_confirmation")),
                    "relevance_score": round(1 - best_distance, 3),
                    "retrieved_text": best_doc[:600],
                    "retrieved_text_full": best_doc,
                    "vvca": vvca,
                    # R4c (campos añadidos): precepto derogado y alcance de la verificación.
                    "precepto_derogado": derogado,
                    "alcance_verificacion": ALCANCE_NORMATIVA,
                    # R4c, ronda 2 (campos añadidos): unidad citada y su cotejo; derogación
                    # ambigua; evidencia sin cuerpo suficiente.
                    "unidad_citada": unidades,
                    "unidad_cotejada": (
                        None if not unidades
                        else bool(unidad and unidad["estado"] == "cotejada")
                    ),
                    "unidad_derogada": unidad_derogada,
                    "unidad_no_cotejada": unidad_no_cotejada,
                    "derogacion_ambigua": derogacion_ambigua,
                    "evidencia_incompleta": evidencia_incompleta,
                }

                if not source_match:
                    # R4c (R4-D09): la evidencia es de otro ordenamiento: no acredita ni
                    # refuta la cita (antes, inalcanzable, se marcaba refutada).
                    trace_status = "not_verifiable"
                elif derogado or unidad_derogada or derogacion_ambigua:
                    # R4c (R4-D08): localizado, pero sin norma vigente (o con una fórmula de
                    # derogación ambigua): nunca verificado.
                    trace_status = "partial"
                elif metadata_hit:
                    trace_status = "verified" if vvca["score"] >= 85 else "partial"
                elif best_distance > COSINE_THRESHOLD:
                    trace_status = "refuted"
                else:
                    trace_status = "verified" if vvca["score"] >= 85 else "partial"
                por_confirmar = bool(ref.get("law_requires_confirmation"))
                if por_confirmar and trace_status != "not_verifiable":
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

                if not source_match:
                    # R4c (R4-D09): antes inalcanzable ("Posible confusión entre
                    # ordenamientos"). Una sola alerta, con la fuente esperada y la hallada.
                    causa = " (el filtro por fuente falló)" if filtro_fuente_fallido else ""
                    alerts.append(
                        f"🟡 EVIDENCIA DE OTRO ORDENAMIENTO (score {vvca['score']}): "
                        f"'{ref['raw']}' — el fragmento recuperado es de '{best_source}', no "
                        f"de '{expected_source}'{causa}. No acredita ni refuta la cita: "
                        f"cotejar el precepto en la ley citada."
                    )
                    if por_confirmar:
                        alerts.append(
                            f"🟡 LEY POR CONFIRMAR: '{ref['raw']}' — {MOTIVO_CONFIRMAR}. "
                            f"Precisar la ley junto al artículo antes de citar."
                        )
                elif por_confirmar or derogado or unidad_derogada or derogacion_ambigua:
                    if por_confirmar:
                        alerts.append(
                            f"🟡 LEY POR CONFIRMAR (score {vvca['score']}): '{ref['raw']}' — "
                            f"{MOTIVO_CONFIRMAR} (se cotejó contra '{best_source}'). "
                            f"{vvca['V_verificacion']}. Precisar la ley junto al artículo "
                            f"antes de citar."
                        )
                    pagina = best_meta.get("page", "?")
                    if derogado:
                        # R4c (R4-D08): criterio por defecto 🟡 (el responsable puede
                        # endurecerlo). Sustituye a COTEJAR / ALERTA ALTA: el precepto sí se
                        # ubicó y su texto vigente es solo la fórmula de derogación.
                        alerts.append(
                            f"🟡 PRECEPTO DEROGADO (score {vvca['score']}): '{ref['raw']}' — "
                            f"en '{best_source}' (pág. {pagina}) el "
                            f"artículo {ref['article']} dice que se deroga: el texto vigente no "
                            f"contiene norma. Verificar si el escrito cita una versión anterior "
                            f"del precepto o un régimen transitorio aplicable antes de citar."
                        )
                    elif unidad_derogada:
                        # R4c (ronda 2): la unidad citada está derogada; el resto del artículo
                        # no se declara derogado.
                        alerts.append(
                            f"🟡 PRECEPTO DEROGADO (score {vvca['score']}): '{ref['raw']}' — "
                            f"en '{best_source}' (pág. {pagina}) la {unidad_derogada} del "
                            f"artículo {ref['article']} dice que se deroga (el resto del artículo "
                            f"no se declara derogado): el texto vigente de la unidad citada no "
                            f"contiene norma. Verificar si el escrito cita una versión anterior "
                            f"o un régimen transitorio aplicable antes de citar."
                        )
                    elif derogacion_ambigua:
                        alerts.append(
                            f"🟡 POSIBLE DEROGACIÓN (score {vvca['score']}): '{ref['raw']}' — "
                            f"en '{best_source}' (pág. {pagina}) junto al encabezado del "
                            f"artículo {ref['article']} hay una fórmula de derogación que no es "
                            f"inequívoca. Verificar qué parte del precepto está vigente antes de "
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
                # (Guard P0 "LEY NO IDENTIFICADA — coincidencia por número": desde R4b una
                # cita sin ley identificada no llega aquí y desde R4c la fuente esperada no se
                # borra; la rama quedó inalcanzable y se retiró.)

                # R4c (ronda 2): avisos que se suman a los anteriores (no los sustituyen).
                if source_match and evidencia_incompleta and not derogado:
                    alerts.append(
                        f"🟡 EVIDENCIA INCOMPLETA (score {vvca['score']}): '{ref['raw']}' — el "
                        f"fragmento de '{best_source}' trae el encabezado del artículo "
                        f"{ref['article']} pero no cuerpo suficiente, y su continuación no se "
                        f"localizó entre los fragmentos del mismo precepto. Cotejar el precepto "
                        f"en la fuente oficial antes de citar."
                    )
                if source_match and unidad_no_cotejada and article_heading_verified:
                    alerts.append(
                        f"🟡 UNIDAD CITADA NO COTEJADA (score {vvca['score']}): '{ref['raw']}' "
                        f"— se ubicó el artículo {ref['article']} en '{best_source}', pero "
                        f"{unidad_no_cotejada}: el semáforo no cubre la "
                        f"{describir_unidad(unidades[0]) if len(unidades) == 1 else 'unidad citada'}. "
                        f"Cotejarla en la fuente oficial antes de citar."
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
            # R4d (ronda 2): número de registro no extraído con certeza (conector no
            # reconocido): cobertura incompleta, como en los artículos (R4b). No se busca.
            if ref.get("coverage_gap"):
                alerts.append(
                    f"🟡 COBERTURA INCOMPLETA: '{ref['raw']}' — {ref['coverage_gap']}. "
                    f"Auditar el registro {ref['registro']} por separado o verificarlo en "
                    f"sjf2.scjn.gob.mx antes de citar."
                )
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="jurisprudencia",
                    status="not_verifiable",
                    method="cobertura_extraccion",
                    reason=f"Cobertura incompleta: {ref['coverage_gap']}",
                    semaforo="🟡",
                    locator=f"Registro digital {ref['registro']}",
                    metadata={"cobertura_incompleta": True},
                ))
                continue
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
                                # R4d: alerta del cotejo del rubro (con los rubros originales)
                                # y aviso informativo de vigencia no consultada.
                                alerta_rubro = _alerta_rubro(ref["registro"], vvca)
                                alerta_vigencia = _alerta_vigencia(ref["registro"], vvca)
                                aviso_vigencia = _aviso_vigencia(ref["registro"], vvca)
                                # R4d: todo se registra junto y solo entonces cuenta como
                                # localizada. Antes ``found_in_tesis`` se marcaba primero y un
                                # error al construir el semáforo hacía desaparecer la tesis sin
                                # traza; ahora queda 🟡 NO VERIFICABLE.
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
                                    # R4c: qué acredita (y qué no) el semáforo de la tesis.
                                    # R4d: sin cotejo del rubro, solo el registro.
                                    "alcance_verificacion": (
                                        ALCANCE_JURISPRUDENCIA_SIN_RUBRO
                                        if vvca.get("cotejo_rubro") in RUBRO_SIN_COTEJO
                                        else ALCANCE_JURISPRUDENCIA
                                    ),
                                })
                                if alerta_rubro:
                                    alerts.append(alerta_rubro)
                                if alerta_vigencia:
                                    alerts.append(alerta_vigencia)
                                if aviso_vigencia:
                                    avisos_vigencia.append(aviso_vigencia)
                                found_in_tesis = True
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
    # R4c (R4-D12): sin evidencia evaluable el puntaje es None, no 0.0: "sin citas" o "sin
    # verificar" no es lo mismo que una cita con 0 puntos (antes salía "RAG 0.0 🔴").
    art_scores = [
        s["vvca"]["score"] for s in retrieved_sources
        if "vvca" in s and s.get("ref_type") == "normativa"
    ]
    score_rag = round(sum(art_scores) / len(art_scores), 1) if art_scores else None

    # ── Score SJF (tesis) — validación dinámica
    jur_scores = [
        s["vvca"]["score"] for s in retrieved_sources
        if "vvca" in s and s.get("ref_type") == "jurisprudencia"
    ]
    score_sjf = round(sum(jur_scores) / len(jur_scores), 1) if jur_scores else None

    # Conteo de tesis problemáticas (mismatch de rubro o no encontradas)
    tesis_total_invocadas = sum(1 for r in refs if r.get("type") == "jurisprudencia")
    tesis_no_encontradas  = tesis_total_invocadas - len(jur_scores)
    tesis_mismatch        = sum(
        1 for s in retrieved_sources
        if s.get("ref_type") == "jurisprudencia" and s.get("vvca", {}).get("rubro_mismatch")
    )
    tesis_rojas = tesis_no_encontradas + tesis_mismatch
    # R4c (ronda 2): las trazas de tesis cuentan en el veredicto como las normativas. Una
    # tesis localizada con puntaje < 85 (p. ej. aislada, 72) queda ``partial``: antes contaba
    # como "ok" y un escrito con solo esa tesis salía 🟢. ``tesis_ok`` = solo verificadas.
    trazas_jurisprudencia = [
        t for t in verification_traces
        if t.get("claim", {}).get("type") == "jurisprudencia"
    ]
    tesis_ok = sum(
        1 for t in trazas_jurisprudencia
        if t.get("verification", {}).get("status") == "verified"
    )
    tesis_parciales = sum(
        1 for t in trazas_jurisprudencia
        if t.get("verification", {}).get("status") == "partial"
    )

    # Tesis con criterio superado/interrumpido/sustituido (falso verde). Por defecto 0:
    # el corpus solo marca vigencia si el scraper la capturó (sección NOTAS del SJF).
    tesis_superadas = sum(
        1 for s in retrieved_sources
        if s.get("ref_type") == "jurisprudencia"
        and s.get("vvca", {}).get("estado_vigencia") in VIGENCIA_PERDIDA
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

    # R4d: conteo de tesis localizadas por resultado del cotejo del rubro y por estado de
    # vigencia (``no_consultada`` = nadie la registró; nunca se asume "vigente").
    tesis_por_cotejo_rubro: Dict[str, int] = {}
    tesis_por_vigencia: Dict[str, int] = {}
    for s in retrieved_sources:
        if s.get("ref_type") == "jurisprudencia":
            vvca_tesis = s.get("vvca", {})
            cotejo = vvca_tesis.get("cotejo_rubro")
            if cotejo:
                tesis_por_cotejo_rubro[cotejo] = tesis_por_cotejo_rubro.get(cotejo, 0) + 1
            estado = vvca_tesis.get("estado_vigencia")
            if estado:
                tesis_por_vigencia[estado] = tesis_por_vigencia.get(estado, 0) + 1
    tesis_sin_cotejo_rubro = sum(tesis_por_cotejo_rubro.get(c, 0) for c in RUBRO_SIN_COTEJO)

    # ── Veredicto binario — las tesis rojas son bloqueantes por sí solas
    # R4c: con ``articulos_total`` el veredicto distingue "sin artículos" de "artículos con
    # verificación insuficiente" (R4-D12) y la razón del 🟢 enuncia solo lo verificado (D11).
    articulos_total = len(trazas_normativas)
    veredicto = veredicto_global(
        score_rag, score_sjf, tesis_mismatch, tesis_no_encontradas,
        tesis_total_invocadas, tesis_superadas,
        normativa_refutada, normativa_no_verificable,
        articulos_total=articulos_total,
        tesis_parciales=tesis_parciales,
    )
    # Semáforo por dimensión (R4-D12): neutro sin citas; sin puntaje, 🟡 (o 🔴 si hay
    # refutadas); con puntaje, el del promedio de siempre.
    semaforo_rag = semaforo_dimension(score_rag, articulos_total, normativa_refutada)
    semaforo_sjf = semaforo_dimension(score_sjf, tesis_total_invocadas, tesis_mismatch)

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
        # R4d (ronda 2, campos añadidos): avisos informativos (ℹ️ vigencia no consultada o no
        # reconocida). No cambian el semáforo y no cuentan en ``alerts_count``.
        "avisos": avisos_vigencia,
        "avisos_count": len(avisos_vigencia),
        "cosine_threshold": COSINE_THRESHOLD,
        "vvca_summary": {
            "score_rag":           score_rag,
            "semaforo_rag":        semaforo_rag,
            "articulos_ok":        sum(
                1 for t in trazas_normativas
                if t.get("verification", {}).get("status") == "verified"
            ),
            "articulos_total":     articulos_total,
            "normativa_refutada":  normativa_refutada,
            "normativa_no_verificable": normativa_no_verificable,
            "score_sjf":           score_sjf,
            "semaforo_sjf":        semaforo_sjf,
            "tesis_total":         tesis_total_invocadas,
            # R4c (ronda 2): solo las verificadas (antes contaba las parciales).
            "tesis_ok":            tesis_ok,
            "tesis_parciales":     tesis_parciales,
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
            # R4c (campos añadidos): dimensiones sin citas (R4-D12) y alcance de la
            # verificación: un 🟢 acredita existencia y ubicación en el corpus local, no que
            # lo citado diga lo que el escrito afirma.
            "rag_sin_citas": articulos_total == 0,
            "sjf_sin_citas": tesis_total_invocadas == 0,
            "alcance_verificacion": ALCANCE_NORMATIVA,
            # R4d: si alguna tesis localizada quedó sin cotejo del rubro, lo dice.
            "alcance_verificacion_tesis": alcance_jurisprudencia(tesis_sin_cotejo_rubro),
            # R4d (campos añadidos): tesis localizadas por cotejo del rubro y por vigencia.
            "tesis_por_cotejo_rubro": tesis_por_cotejo_rubro,
            "tesis_por_vigencia": tesis_por_vigencia,
        },
        "alerts": alerts,
        "retrieved_sources": retrieved_sources,
        "traceability": traceability_bundle(verification_traces),
        "summary": (
            _resumen_rag(score_rag, semaforo_rag, articulos_total,
                         normativa_no_verificable, normativa_refutada)
            + " · "
            + _resumen_sjf(score_sjf, semaforo_sjf, tesis_total_invocadas, tesis_ok,
                           tesis_mismatch, tesis_no_encontradas, tesis_parciales)
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


# Telegram admite 4 096 caracteres por mensaje; se deja margen.
LIMITE_TELEGRAM = 3800


def _avisos_telegram(avisos: List[str]) -> List[str]:
    """Avisos informativos (ℹ️) agrupados por tipo, con TODOS sus registros (R4d, ronda 2)."""
    grupos: Dict[str, List[str]] = {}
    for aviso in avisos:
        etiqueta = aviso.split(":", 1)[0]
        registro = re.search(r"Registro digital (\d+)", aviso)
        grupos.setdefault(etiqueta, []).append(registro.group(1) if registro else "?")
    return [
        f"{etiqueta} (no cambia el semáforo; verificar en sjf2.scjn.gob.mx): Reg. "
        f"{', '.join(registros)}"
        for etiqueta, registros in grupos.items()
    ]


def formato_telegram(result: Dict) -> str:
    """Bloque de texto de ``audit --format telegram`` (función aparte para probarla).

    R4d (ronda 2): las alertas van completas (con los rubros), todas las que quepan en
    ``LIMITE_TELEGRAM``; si no caben, "… y N alerta(s) más" remite al JSON (``alerts``). Los
    avisos informativos (``avisos``) se cuentan aparte y se agrupan por tipo con todos sus
    registros. Antes: tres alertas recortadas a 120 caracteres, avisos incluidos."""
    vs = result["vvca_summary"]
    # R4c (R4-D12): una dimensión sin citas se muestra como tal, no como "0.0 🔴".
    rag = ("sin citas" if vs.get("rag_sin_citas")
           else f"{_puntaje(vs['score_rag'])} {vs['semaforo_rag']}")
    sjf = ("sin citas" if vs.get("sjf_sin_citas")
           else f"{_puntaje(vs['score_sjf'])} {vs['semaforo_sjf']}")
    avisos = result.get("avisos") or []
    encabezado = (
        f"📋 <b>Auditoría VVCA</b> · {result['total_references_found']} refs · "
        f"{result['alerts_count']} alertas"
        + (f" · {len(avisos)} avisos" if avisos else "")
    )
    lines = [
        encabezado,
        f"RAG: {rag} · SJF: {sjf}"
        f"  🟢{vs['verdes']} 🟡{vs['amarillos']} 🔴{vs['rojos']}"
        f"  · Veredicto: {vs['veredicto']['semaforo']} {vs['veredicto']['razon']}",
        "",
    ]
    if vs["veredicto"]["semaforo"] == "🟢":
        # R4c: alcance del 🟢 (no significa que lo citado diga lo que se afirma) de cada
        # dimensión con citas (ronda 2: el de las tesis cuando las hay; ambos si hay ambos).
        alcances = []
        if not vs.get("rag_sin_citas"):
            alcances.append(f"Alcance (normas): {vs['alcance_verificacion']}")
        if not vs.get("sjf_sin_citas"):
            alcances.append(f"Alcance (tesis): {vs['alcance_verificacion_tesis']}")
        lines[2:2] = alcances
    for s in result["retrieved_sources"]:
        v = s.get("vvca", {})
        sem = v.get("semaforo", "⬜")
        score = v.get("score", "?")
        ref = s.get("reference", "?")[:40]
        ctx = v.get("C_contextualizacion", "")[:50]
        lines.append(f"{sem} <b>{score}</b> · {ref} · {ctx}")
    cola = []
    if avisos:
        cola += [""] + _avisos_telegram(avisos)
    if result.get("corpus_warning"):
        cola += ["", f"⚠️ {result['corpus_warning']}"]
    cola += ["", "🔗 Fuentes: sjf2.scjn.gob.mx · dof.gob.mx · cjf.gob.mx"]
    alertas = result["alerts"]
    if alertas:
        lines.append("")
        # Espacio ya usado (cabecera, fuentes, avisos, pie) más el aviso de truncado.
        usado = len("\n".join(lines + cola)) + 160
        for indice, alerta in enumerate(alertas):
            linea = f"⚠️ {alerta}"
            if usado + len(linea) + 1 > LIMITE_TELEGRAM:
                lines.append(
                    f"… y {len(alertas) - indice} alerta(s) más: el texto completo, con los "
                    f"rubros, está en el JSON de la auditoría (\"alerts\")."
                )
                break
            lines.append(linea)
            usado += len(linea) + 1
    return "\n".join(lines + cola)


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
            print(formato_telegram(result))
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
