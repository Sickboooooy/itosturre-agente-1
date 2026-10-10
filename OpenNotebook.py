"""
OpenNotebook.py v4.0 — RAG Legal Itosturre
Motor de auditoría anti-alucinaciones con semáforo VVCA.

Cambios vigencia del corpus y ruta query (rama fix/vvca-query-vigencia, 9-oct-2026;
itosturre/audit/vigencia.py):
  ✅ ``audit`` lee el último reporte de scripts/vigencia_corpus.py hecho sobre este índice. Si
     da por no vigente la versión indexada de la ley (DESACTUALIZADA o ABROGADA): la cita no
     sale 🟢 ("🟡 VERSIÓN INDEXADA NO VIGENTE", tope 84) y la inexistencia probada solo en esa
     versión no sale 🔴 ("🟡 INEXISTENTE EN UNA VERSIÓN NO VIGENTE"). Nunca 🔴 por vigencia;
     sin reporte aplicable nada cambia (``vigencia_corpus`` del resumen dice por qué).
  ✅ ``query`` (``consultar_corpus``): un artículo nombrado recibe el veredicto de ``audit``;
     los pasajes cercanos son contexto (⚪), nunca 🟢 por parecido ni 🔴 por poco parecido
     (antes: "art. 750 LA" 🟢 87 con el art. 5o; un derogado 🟢 100 «literal»).

Cambios Movilidad y retiro de fuentes (orden del responsable, 10-oct-2026):
  ✅ La «Ley de Movilidad, Seguridad Vial y Transporte del Estado de Jalisco» es fuente propia;
     la que abrogó («Ley de Movilidad y Transporte…», decreto 24451/LX/13) ya no se resuelve.
  ✅ ``ingest --retirar ARCHIVO.pdf``: saca del índice una fuente que el catálogo ya no
     resuelve, con respaldo durable, verificación y restauración ante fallo (``--restaurar``).

Cambios identidad confirmada (orden del responsable, 10-oct-2026):
  ✅ ``ingest --fuente X.pdf --identidad-confirmada X.pdf``: el operador confirma que X es el
     mismo ordenamiento aunque el título de su primera página difiera del indexado (los PDF
     oficiales del Congreso de Jalisco anteponen el preámbulo del decreto). Solo se omite la
     comparación del título; el contenido decide con el mismo umbral (90 % de designaciones) y
     el informe registra ambos títulos. Sin su --fuente, la opción se rechaza.

Cambios re-ingesta por fuente (orden del responsable jurídico, 4-oct-2026):
  ✅ Corte y etiqueta de "ley" como funciones puras (itosturre/audit/fragmentacion.py) con la
     misma definición de encabezado AUTÉNTICO que la auditoría (evidence._es_autentico): cortan
     "ARTÍCULO 1o.-"/"ARTICULO 496.-" (antes no: exigían "rt" en minúscula) y la designación
     sola al final de su línea de los tratados; ya no cortan remisiones en minúscula al inicio
     de línea ("artículo 41.") ni citas ("Artículo 2o., fracción I"). Etiquetas compatibles.
  ✅ ``ingest --fuente ARCHIVO.pdf [--fuente …] [--simular]``: borra SOLO los fragmentos de esa
     fuente (nunca la colección), con vectores calculados antes, respaldo y restauración ante
     fallo; ``--simular`` informa fragmentos, etiquetas y cobertura antes/después sin escribir.
  ✅ La ingesta sin flags ya no mezcla fragmentos viejos y nuevos de una fuente indexada con
     otra fragmentación: la omite, pide ``--fuente`` y sale con código 3 (MIGRACIÓN
     PENDIENTE). ``--reingest``/``--clear`` no cambian (borran la colección ENTERA).
  ✅ Ronda 2: gramática única ("58-1", "65 Bis 1", latinos extendidos, falla cerrada),
     encabezado partido entre líneas, cuerpo hasta TRANSITORIOS; ``--fuente`` con fase 1 sin
     escrituras (identidad, extracción completa, colisiones), respaldo DURABLE por fuente e
     ``ingest --restaurar``.

Cambios D10 (artículo no localizado; itosturre/audit/inexistencia.py):
  ✅ Criterio del responsable jurídico (2-oct-2026, opción C): un artículo que no se localiza
     en una ley indexada solo es 🔴 con prueba positiva de inexistencia sobre el cuerpo de la
     ley (vecinos en el mismo fragmento o número muy superior al último artículo del cuerpo
     completo de la versión indexada): "🔴 ARTÍCULO INEXISTENTE ACREDITADO" con la prueba, la
     página y la versión. Sin prueba, "🟡 NO LOCALIZADO" (antes "🔴 ALERTA ALTA … Posible
     alucinación" y "🔴 ALERTA CRÍTICA … Alucinación detectada") o "🟡 POSTERIOR AL ÚLTIMO
     ARTÍCULO"; las demás rutas de "no localizado" conservan su 🟡.
  ✅ Ronda 2: la prueba se abstiene ante cualquier ambigüedad (líneas candidatas, menciones,
     frontera dudosa, densidad, identidad documental, ley no ligada explícitamente).
  ✅ La distancia alta sin metadata limita el puntaje a 60–84 (nunca 🔴 sin prueba).

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
  python OpenNotebook.py ingest --directory /ruta/a/pdfs/ --fuente "ARCHIVO.pdf" [--simular]
  python OpenNotebook.py audit --text "texto del borrador"
  python OpenNotebook.py audit --file /ruta/borrador.md --verbose
  python OpenNotebook.py query "prisión preventiva CNPP" [--n 5]
"""

import argparse
import base64
import datetime
import hashlib
import importlib
import json
import re
import sys
import logging
import time
from array import array
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Optional, Sequence, Tuple, Dict, List

from itosturre.audit.context import vvca_contextualizacion
from itosturre.audit.fragmentacion import (
    Fragmentacion,
    fragmentar,
    medir,
    paginas_incompletas,
    verificar_identidad,
)
from itosturre.audit.evidence import (
    DEROGACION_AMBIGUA,
    DEROGADO,
    cotejar_precepto,
    describir_unidad,
    encabezado_autentico,
    select_article_evidence,
)
from itosturre.audit.referencias import (
    ARTICULO_RE,
    MOTIVO_CONFIRMAR,
    CatalogoLeyes,
    articulo_con_sufijo,
    canon_caja,
    construir_catalogo,
    designaciones_articulo,
    extraer_articulos,
    ordinales_equivalentes,
    partes_articulo,
    patron_articulo,
    primera_mencion,
    sin_acentos,
    ultima_mencion,
)
from itosturre.audit.inexistencia import (
    PRUEBA_VECINOS,
    describir_posterior,
    describir_prueba,
    evaluar_inexistencia,
    frontera_creible,
    preparar_ley,
)
from itosturre.audit.ubicacion import NO_ACREDITADA as UBICACION_NO_ACREDITADA
from itosturre.audit.ubicacion import ubicar_en_cuerpo
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
from itosturre.audit.vigencia import (
    FUENTE_NO_VIGENTE,
    REPORTE_APLICADO,
    REPORTE_AUSENTE,
    REPORTE_ILEGIBLE,
    REPORTE_OTRO_INDICE,
    ReporteVigencia,
    cargar_reporte,
    fila_de,
    instruccion_cotejo,
    vigencia_de_fuente,
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
# Vigencia del corpus (rama fix/vvca-query-vigencia): reporte de scripts/vigencia_corpus.py. Por
# omisión, el más reciente de su carpeta de salida; solo se aplica el hecho sobre este índice
# (``itosturre.audit.vigencia``).
VIGENCIA_REPORTE = os.getenv("ITOS_VIGENCIA_REPORTE", "")
VIGENCIA_REPORTES_DIR = os.getenv("ITOS_VIGENCIA_SALIDA", str(_BASE_DIR / "reportes" / "vigencia_corpus"))
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
    # Movilidad (orden del responsable, 10-oct-2026): la «Ley de Movilidad, Seguridad Vial y
    # Transporte del Estado de Jalisco» es ley nueva, con fuente propia; sus transitorios abrogan
    # la «Ley de Movilidad y Transporte del Estado de Jalisco» (decreto 24451/LX/13), que salió del
    # catálogo y del índice: citarla queda 🟡 (ley no identificada), nunca contra la nueva.
    "ley de movilidad, seguridad vial y transporte del estado de jalisco": "Ley de Movilidad Seguridad Vial y Transporte del Estado de Jalisco 2026.pdf",
    "ley de movilidad seguridad vial y transporte del estado de jalisco": "Ley de Movilidad Seguridad Vial y Transporte del Estado de Jalisco 2026.pdf",
    # Su reglamento (orden del responsable, 10-oct-2026): fuente propia. El «Reglamento General de
    # la Ley de Movilidad y Transporte», que reglamentaba la ley abrogada, salió del índice.
    "reglamento de la ley de movilidad, seguridad vial y transporte del estado de jalisco": "Reglamento de la Ley de Movilidad Seguridad Vial y Transporte del Estado de Jalisco 2026.pdf",
    "reglamento de la ley de movilidad seguridad vial y transporte del estado de jalisco": "Reglamento de la Ley de Movilidad Seguridad Vial y Transporte del Estado de Jalisco 2026.pdf",
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
    # Sin clave para el "Reglamento Orgánico del Poder Judicial de la Federación": su PDF era una
    # copia de la LOPJF (mismo sha256, verificado el 1-oct-2026) y el responsable lo descartó el
    # 9-oct-2026 (scripts/fuentes_oficiales.json). Mapearlo cotejaba esa cita contra la LOPJF;
    # sin clave queda 🟡 NO VERIFICABLE.
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

# Tratados internacionales del corpus (criterio del responsable jurídico, 4-oct-2026, opción A).
# ÚNICA fuente de verdad de la regla: el encabezado "Artículo N" / "ARTÍCULO N" / "Artículo Nº"
# SOLO al final de su línea, sin punto ni guion, es un encabezado auténtico únicamente en estas
# fuentes (sus PDF no cierran los encabezados); las leyes nacionales siguen exigiendo el cierre.
# Se identifican por el catálogo, nunca por el nombre del archivo (no se usa
# ``itosturre.audit.referencias.tipo_fuente``). Cada valor es el ``source`` exacto con que está
# indexado, el mismo de ``LAW_SOURCE_MAP`` (una prueba lo exige).
#
# Para añadir un tratado: (1) indexar su PDF; (2) añadir a ``LAW_SOURCE_MAP`` sus denominaciones
# y abreviaturas con el nombre exacto del archivo; (3) añadir aquí ese nombre; (4) medir en el
# índice que sus encabezados sin cierre van seguidos de una línea que no continúa la oración y
# auditar antes→después todos sus artículos (tabla de docs/PROTOCOLO_VVCA.md §4, "Tratados
# internacionales"). Un PDF de tratado que no esté aquí se audita como ley (exige el cierre).
TRATADOS_INTERNACIONALES = frozenset({
    "Convencion Americana sobre Derechos Humanos.pdf",
    "Convención sobre los Derechos del Niño.pdf",
    "Pacto Internacional de Derechos Civiles y Políticos.pdf",
})


def es_tratado_internacional(fuente: Optional[str]) -> bool:
    """¿``fuente`` (el ``source`` indexado) está registrada como tratado internacional?"""
    return fuente in TRATADOS_INTERNACIONALES


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


def encode_passages(model, textos: List[str]) -> List[List[float]]:
    """Codifica fragmentos con prefijo e5 'passage: ' (el mismo cálculo que hace ChromaDB al
    indexar con la función de la colección). La re-ingesta por fuente lo usa para calcular
    los vectores ANTES de tocar el índice."""
    return model.encode(["passage: " + t for t in textos], normalize_embeddings=True).tolist()


def get_collection(embedder, *, crear: bool = True):
    """Colección del corpus. ``crear=False`` (re-ingesta ``--simular``): solo la abre y falla
    si no existe, en vez de crearla."""
    client = _cargar_dependencias().chromadb.PersistentClient(path=CHROMA_PATH)

    class STEmbeddingFunction:
        def __init__(self, model):
            self.model = model
        def name(self):
            return "itosturre-st-embedder"
        def __call__(self, input):
            # Usado por ChromaDB al indexar documentos — prefijo e5 'passage: '
            return encode_passages(self.model, input)
        def embed_documents(self, input):
            return encode_passages(self.model, input)
        def embed_query(self, input):
            if isinstance(input, str):
                input = [input]
            return self.model.encode(["query: " + t for t in input], normalize_embeddings=True).tolist()

    ef = STEmbeddingFunction(embedder)
    if not crear:
        return client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
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


def _directorio_de_ingesta(directory: str) -> Path:
    """Carpeta de PDFs resuelta, solo si está bajo ``INGEST_ALLOWED_BASE`` (path traversal).
    ValueError si no lo está."""
    pdf_dir = Path(directory).resolve()
    allowed_base = Path(INGEST_ALLOWED_BASE).resolve()
    try:
        pdf_dir.relative_to(allowed_base)
    except ValueError:
        raise ValueError(
            f"Path traversal bloqueado: '{pdf_dir}' no está bajo '{allowed_base}'. Ajusta "
            f"INGEST_ALLOWED_BASE en .env si necesitas ingestar desde otra ruta."
        ) from None
    return pdf_dir


def _divisor_respaldo():
    """Divisor de respaldo de los textos que pasan de ``MAX_CHUNK_SIZE`` (el de siempre)."""
    return _cargar_dependencias().RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=200,
        separators=["\n\n", "\n", " "]
    )


def fragmentos_de_pdf(
    pdf_path: Path,
    *,
    extraer: Optional[Callable[[Path], list]] = None,
    subdividir: Optional[Callable[[str], List[str]]] = None,
) -> Fragmentacion:
    """Fragmentos de un PDF con el corte y la etiqueta de ``itosturre.audit.fragmentacion``
    (re-ingesta por fuente, 4-oct-2026: encabezados auténticos, también en MAYÚSCULAS; sin
    cortes en remisiones). ``extraer`` (páginas) y ``subdividir`` son costuras para pruebas.
    Tratados (4-oct-2026, opción A): solo un PDF registrado en ``TRATADOS_INTERNACIONALES``
    corta en "Artículo N" sin cierre; en las leyes nacionales el cierre es obligatorio."""
    paginas = (extraer or extract_text_from_pdf)(pdf_path)
    if subdividir is None:
        subdividir = _divisor_respaldo().split_text
    return fragmentar(paginas, max_caracteres=MAX_CHUNK_SIZE, subdividir=subdividir,
                      fin_de_linea=es_tratado_internacional(pdf_path.name))


def filas_de_fragmentos(
    pdf_path: Path, fragmentacion: Fragmentacion
) -> Tuple[List[str], List[str], List[Dict]]:
    """IDs, textos y metadatos de los fragmentos de un PDF, con el esquema de siempre: ID
    ``{stem}_chunk_{i}`` y metadatos ``source``, ``law``, ``article``, ``page``,
    ``chunk_index`` y ``doc_type`` (todos texto), con ``chunk_index`` contiguo desde 0."""
    ids, textos, metadatas = [], [], []
    for indice, fragmento in enumerate(fragmentacion.fragmentos):
        ids.append(f"{pdf_path.stem}_chunk_{indice}")
        textos.append(fragmento.texto)
        metadatas.append({
            "source": pdf_path.name,
            "law": pdf_path.stem,
            "article": fragmento.etiqueta,
            "page": str(fragmento.pagina),
            "chunk_index": str(indice),
            "doc_type": fragmentacion.tipo,
        })
    return ids, textos, metadatas


_CAMPOS_FRAGMENTO = ("source", "law", "article", "page", "chunk_index", "doc_type")


def _filas_comparables(ids, textos, metadatas) -> Dict[str, Tuple[str, Dict]]:
    return {
        id_: (texto, {k: (meta or {}).get(k) for k in _CAMPOS_FRAGMENTO})
        for id_, texto, meta in zip(ids, textos, metadatas)
    }


def pendientes_sin_mezcla(collection, fuente: str, ids, textos, metadatas) -> Optional[List[int]]:
    """Posiciones de los fragmentos nuevos que faltan en el índice, o None si la fuente ya está
    indexada con OTRA fragmentación.

    Re-ingesta por fuente (4-oct-2026) — Nunca mezclar fragmentos viejos y nuevos. Antes la
    ingesta sin flags omitía por ID los fragmentos ya existentes: si la fragmentación había
    cambiado (otro cortador, otro PDF), el índice quedaba con el texto viejo en los IDs
    existentes y el nuevo en los demás. Ahora una fuente ya indexada solo se completa si todo
    lo existente coincide con lo nuevo (texto y metadatos: una ingesta interrumpida); si
    difiere en algo, None (la ingesta la omite y pide --fuente)."""
    existentes = collection.get(where={"source": fuente}, include=["documents", "metadatas"])
    previos = _filas_comparables(
        existentes.get("ids") or [],
        existentes.get("documents") or [],
        existentes.get("metadatas") or [],
    )
    nuevos = _filas_comparables(ids, textos, metadatas)
    if any(nuevos.get(id_) != fila for id_, fila in previos.items()):
        return None
    return [k for k, id_ in enumerate(ids) if id_ not in previos]


def ingest(directory: str, clear: bool = False, reingest: bool = False):
    try:
        pdf_dir = _directorio_de_ingesta(directory)
    except ValueError as exc:
        logger.error(f"❌ {exc}")
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

    # clear y reingest borran la colección ENTERA antes de ingestar (todas las fuentes).
    # Para re-ingestar una sola fuente: ``ingest --fuente`` (reingestar_fuentes).
    if clear or reingest:
        try:
            client.delete_collection(COLLECTION_NAME)
            logger.info("🗑️  Colección borrada para re-ingesta limpia.")
        except Exception as e:
            logger.warning(f"⚠️  No se pudo borrar colección: {e}")

    collection = get_collection(embedder)
    subdividir = _divisor_respaldo().split_text

    total_chunks = 0
    con_otra_fragmentacion: List[str] = []
    for pdf_path in pdfs:
        logger.info(f"  🔍 Procesando: {pdf_path.name}")
        try:
            pages = extract_text_from_pdf(pdf_path)
            if not pages:
                logger.warning(f"     ⚠️  Texto muy corto, omitiendo.")
                continue

            fragmentacion = fragmentos_de_pdf(
                pdf_path, extraer=lambda _ruta: pages, subdividir=subdividir
            )
            ids, texts, metadatas = filas_de_fragmentos(pdf_path, fragmentacion)
            logger.info(f"     📄 {len(ids)} chunks generados")

            pendientes = pendientes_sin_mezcla(collection, pdf_path.name, ids, texts, metadatas)
            if pendientes is None:
                logger.warning(
                    f"     ⚠️  {pdf_path.name} ya está indexada con otra fragmentación: no se "
                    f"mezcla. Re-ingesta esa fuente con --fuente \"{pdf_path.name}\"."
                )
                con_otra_fragmentacion.append(pdf_path.name)
                continue

            # Insertar en lotes
            batch_size = 50
            for i in range(0, len(pendientes), batch_size):
                lote = pendientes[i:i + batch_size]
                collection.add(
                    ids=[ids[k] for k in lote],
                    documents=[texts[k] for k in lote],
                    metadatas=[metadatas[k] for k in lote],
                )

            total_chunks += len(ids)
            logger.info(f"     ✅ Indexado correctamente")

        except Exception as e:
            logger.error(f"     ❌ Error procesando {pdf_path.name}: {e}")

    logger.info(f"\n✅ INGESTA COMPLETADA")
    logger.info(f"   PDFs procesados : {len(pdfs)}")
    logger.info(f"   Chunks totales  : {total_chunks}")
    logger.info(f"   Base vectorial  : {CHROMA_PATH}")
    logger.info(f"   Colección       : {COLLECTION_NAME}")
    if con_otra_fragmentacion:
        # Ronda 2 (adjudicado): MIGRACIÓN PENDIENTE — la ingesta no terminó su trabajo; sale
        # con código distinto de 0 y dice exactamente cómo completarla.
        fuentes = " ".join(f'--fuente "{nombre}"' for nombre in con_otra_fragmentacion)
        logger.warning(
            f"\n⚠️  MIGRACIÓN PENDIENTE: {len(con_otra_fragmentacion)} fuente(s) ya indexadas con "
            f"otra fragmentación se omitieron (no se mezclan fragmentos viejos y nuevos): "
            f"{', '.join(con_otra_fragmentacion)}\n"
            f"   Simula y luego re-ingesta solo esas fuentes:\n"
            f"   python OpenNotebook.py ingest --directory \"{directory}\" {fuentes} --simular\n"
            f"   python OpenNotebook.py ingest --directory \"{directory}\" {fuentes}"
        )
        sys.exit(SALIDA_MIGRACION_PENDIENTE)


# ─────────────────────────────────────────
# RE-INGESTA POR FUENTE (4-oct-2026)
# ─────────────────────────────────────────
# Orden expresa del responsable jurídico (4-oct-2026). ``--reingest``/``--clear`` borran la
# colección ENTERA (49 leyes, ~28 000 fragmentos) y re-ingestar un PDF sin borrar antes sus
# fragmentos mezclaba viejos y nuevos. ``reingestar_fuentes`` sustituye SOLO los fragmentos de
# las fuentes nombradas, en dos fases:
#   Fase 1, sin escribir nada, para TODAS las fuentes: nombre exacto de un PDF de la carpeta,
#     no excluido; extracción completa antes de la frontera TRANSITORIOS
#     (``paginas_incompletas``); identidad con lo indexado de esa fuente
#     (``verificar_identidad``: título y designaciones, sin depender del catálogo); ningún ID
#     nuevo ocupado por otra fuente. Si alguna falla, se niega sin tocar el índice.
#   Fase 2, por fuente: vectores calculados ANTES de tocar el índice; respaldo DURABLE en disco
#     (fuera del repositorio y del índice: ids, documentos, metadatos y vectores, con su huella)
#     y en memoria; borrado SOLO de ``source == fuente``; alta y verificación; ante cualquier
#     fallo, restauración. ``restaurar_respaldo`` (``ingest --restaurar``) repone un respaldo.
# Con ``simular=True`` no escribe: informa fragmentos, etiquetas y cobertura antes (índice) y
# después (cortador actual), y lo que la fase 1 rechazaría.

LOTE_REINGESTA = 50
MAX_ETIQUETAS_INFORME = 40
FORMATO_RESPALDO = "itosturre-respaldo-fuente/1"
# Carpeta de los respaldos durables: ``--respaldos``, la variable de entorno o, por omisión,
# ~/.itosturre/respaldos_reingesta (fuera del repositorio).
VARIABLE_RESPALDOS = "ITOSTURRE_RESPALDOS_REINGESTA"
# Ingesta sin flags que omitió fuentes con otra fragmentación (migración pendiente).
SALIDA_MIGRACION_PENDIENTE = 3
# Al restaurar, ChromaDB (espacio coseno) vuelve a normalizar cada vector: medido en el corpus,
# difiere del respaldo en a lo sumo 1.5e-8 por componente (coseno 1.0). Más que esto es otro
# vector.
TOLERANCIA_VECTOR = 1e-6


class ReingestaFallida(RuntimeError):
    """La re-ingesta de una fuente falló; el mensaje dice si se restauró el respaldo."""


class ReingestaRechazada(ValueError):
    """La fase 1 (sin escribir) rechazó la re-ingesta: el índice no se tocó."""


def _validar_fuentes(pdf_dir: Path, fuentes: Sequence[str]) -> List[Path]:
    """Rutas de las fuentes pedidas. Cada una es el nombre EXACTO (también en mayúsculas y
    acentos: es el ``source`` del índice) de un PDF de ``pdf_dir`` no excluido por
    ``EXCLUDE_PATTERNS``. ValueError si no hay ninguna, se repite o no cumple."""
    if not fuentes:
        raise ValueError(
            "La re-ingesta por fuente exige al menos una --fuente (nombre exacto del PDF). "
            "Para re-ingestar todo el corpus está --reingest, que borra la colección entera."
        )
    repetidas = sorted(f for f, n in Counter(fuentes).items() if n > 1)
    if repetidas:
        raise ValueError(f"Fuente repetida: {', '.join(repetidas)}")
    en_carpeta = {p.name: p for p in pdf_dir.iterdir() if p.is_file()}
    rutas = []
    for fuente in fuentes:
        if not fuente or Path(fuente).name != fuente or fuente in (".", ".."):
            raise ValueError(f"--fuente debe ser solo el nombre del archivo: {fuente!r}")
        ruta = en_carpeta.get(fuente)
        if ruta is None:
            raise ValueError(
                f"No existe '{fuente}' en la carpeta indicada (se exige el nombre exacto, "
                f"con mayúsculas y acentos, porque es el 'source' del índice)."
            )
        if not is_legal_pdf(ruta):
            raise ValueError(f"'{fuente}' no es un PDF legal (extensión o EXCLUDE_PATTERNS).")
        rutas.append(ruta)
    return rutas


def _en_orden(respuesta: Dict) -> List[Tuple[str, str, Dict]]:
    """(id, texto, metadatos) de un ``collection.get`` en orden de ``chunk_index``."""
    filas = list(zip(
        respuesta.get("ids") or [],
        respuesta.get("documents") or [],
        respuesta.get("metadatas") or [],
    ))

    def clave(fila):
        try:
            return (0, int(str((fila[2] or {}).get("chunk_index"))))
        except (TypeError, ValueError):
            return (1, 0)

    return sorted(filas, key=clave)


def _diferencia_etiquetas(antes: Counter, despues: Counter) -> Dict:
    ganadas, perdidas = despues - antes, antes - despues
    return {
        "etiquetas_ganadas": sum(ganadas.values()),
        "etiquetas_perdidas": sum(perdidas.values()),
        "muestra_ganadas": sorted(ganadas.elements())[:MAX_ETIQUETAS_INFORME],
        "muestra_perdidas": sorted(perdidas.elements())[:MAX_ETIQUETAS_INFORME],
    }


def _agregar_por_lotes(collection, ids, textos, metadatas, vectores) -> None:
    for i in range(0, len(ids), LOTE_REINGESTA):
        collection.add(
            ids=list(ids[i:i + LOTE_REINGESTA]),
            documents=list(textos[i:i + LOTE_REINGESTA]),
            metadatas=list(metadatas[i:i + LOTE_REINGESTA]),
            embeddings=[list(map(float, v)) for v in vectores[i:i + LOTE_REINGESTA]],
        )


# ── Respaldo durable de una fuente ───────────────────────────────────────────────────────

def _directorio_respaldos(respaldos_dir: Optional[str] = None) -> Path:
    """Carpeta de respaldos: ``respaldos_dir``, ``$ITOSTURRE_RESPALDOS_REINGESTA`` o
    ~/.itosturre/respaldos_reingesta. ValueError si queda dentro del repositorio o del índice
    (un respaldo ahí se borraría o versionaría con ellos)."""
    elegido = respaldos_dir or os.getenv(VARIABLE_RESPALDOS) or str(
        Path.home() / ".itosturre" / "respaldos_reingesta"
    )
    destino = Path(elegido).expanduser().resolve()
    for prohibida, nombre in ((_BASE_DIR.resolve(), "el repositorio"),
                              (Path(CHROMA_PATH).resolve(), "el índice (CHROMA_PATH)")):
        if destino == prohibida or prohibida in destino.parents:
            raise ValueError(f"Los respaldos no pueden quedar dentro de {nombre}: {destino}")
    return destino


def _vectores_a_texto(vectores, dimension: int) -> str:
    """Vectores → float32 little-endian en base64 (sin pérdida: ChromaDB guarda float32)."""
    datos = array("f")
    for vector in vectores:
        if len(vector) != dimension:
            raise ReingestaFallida("vectores de dimensión distinta en el respaldo")
        datos.extend(float(x) for x in vector)
    if sys.byteorder != "little":
        datos.byteswap()
    return base64.b64encode(datos.tobytes()).decode("ascii")


def _texto_a_vectores(texto: str, dimension: int, cantidad: int) -> List[List[float]]:
    datos = array("f")
    datos.frombytes(base64.b64decode(texto.encode("ascii")))
    if sys.byteorder != "little":
        datos.byteswap()
    if len(datos) != dimension * cantidad:
        raise ValueError("el respaldo no tiene tantos valores como vectores × dimensión")
    return [list(datos[i * dimension:(i + 1) * dimension]) for i in range(cantidad)]


def _huella_respaldo(cuerpo: Dict) -> str:
    sin_huella = {k: v for k, v in cuerpo.items() if k != "sha256"}
    canonico = json.dumps(sin_huella, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _escribir_respaldo(destino_dir: Path, fuente: str, respaldo: Dict) -> Path:
    """Escribe el respaldo de ``fuente`` (lo que devolvió ``collection.get`` con documentos,
    metadatos y vectores), lo relee y comprueba su huella. Devuelve la ruta."""
    ids = list(respaldo.get("ids") or [])
    vectores = respaldo.get("embeddings")
    vectores = [] if vectores is None else list(vectores)
    dimension = len(vectores[0]) if ids else 0
    cuerpo = {
        "formato": FORMATO_RESPALDO,
        "fuente": fuente,
        "coleccion": COLLECTION_NAME,
        "creado": datetime.datetime.now().isoformat(timespec="seconds"),
        "fragmentos": len(ids),
        "dimension": dimension,
        "ids": ids,
        "documents": list(respaldo.get("documents") or []),
        "metadatas": [dict(m or {}) for m in (respaldo.get("metadatas") or [])],
        "vectores_f32le_b64": _vectores_a_texto(vectores, dimension) if ids else "",
    }
    if not (len(cuerpo["documents"]) == len(cuerpo["metadatas"]) == len(vectores) == len(ids)):
        raise ReingestaFallida("respaldo incompleto: ids, documentos, metadatos o vectores")
    cuerpo["sha256"] = _huella_respaldo(cuerpo)
    destino_dir.mkdir(parents=True, exist_ok=True)
    marca = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = re.sub(r"[^\w.\- ]+", "_", Path(fuente).stem)
    ruta = destino_dir / f"{base}__{marca}.json"
    contador = 1
    while ruta.exists():
        contador += 1
        ruta = destino_dir / f"{base}__{marca}-{contador}.json"
    temporal = ruta.with_suffix(".json.tmp")
    temporal.write_text(json.dumps(cuerpo, ensure_ascii=False), encoding="utf-8")
    os.replace(temporal, ruta)
    leido = leer_respaldo(ruta)   # relectura: la huella y las cantidades cuadran
    if leido["fragmentos"] != len(ids):
        raise ReingestaFallida(f"el respaldo escrito en {ruta} no se relee completo")
    return ruta


def leer_respaldo(ruta) -> Dict:
    """Lee y valida un respaldo de fuente (formato, huella, cantidades). ValueError si no."""
    cuerpo = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if cuerpo.get("formato") != FORMATO_RESPALDO:
        raise ValueError(f"{ruta}: no es un respaldo de fuente ({cuerpo.get('formato')!r})")
    if cuerpo.get("sha256") != _huella_respaldo(cuerpo):
        raise ValueError(f"{ruta}: la huella no coincide (respaldo alterado o incompleto)")
    n = cuerpo["fragmentos"]
    if not (len(cuerpo["ids"]) == len(cuerpo["documents"]) == len(cuerpo["metadatas"]) == n):
        raise ValueError(f"{ruta}: cantidades inconsistentes")
    if any((m or {}).get("source") != cuerpo["fuente"] for m in cuerpo["metadatas"]):
        raise ValueError(f"{ruta}: hay fragmentos de otra fuente")
    cuerpo["vectores"] = (
        _texto_a_vectores(cuerpo["vectores_f32le_b64"], cuerpo["dimension"], n) if n else []
    )
    return cuerpo


def _ids_ajenos(collection, fuente: str, ids) -> List[str]:
    """IDs de ``ids`` que el índice ya tiene con OTRA fuente (colisión)."""
    if not ids:
        return []
    existentes = collection.get(ids=list(ids), include=["metadatas"])
    return [
        id_ for id_, meta in zip(existentes.get("ids") or [], existentes.get("metadatas") or [])
        if (meta or {}).get("source") != fuente
    ]


def _restaurar(collection, fuente: str, respaldo: Dict) -> int:
    """Deja la fuente como estaba: borra lo escrito y vuelve a agregar el respaldo."""
    collection.delete(where={"source": fuente})
    ids = list(respaldo.get("ids") or [])
    if ids:
        _agregar_por_lotes(
            collection, ids, list(respaldo["documents"]), list(respaldo["metadatas"]),
            respaldo["embeddings"],
        )
    return len(ids)


def _sustituir_fuente(
    collection, fuente: str, ids, textos, metadatas, vectores, *, respaldos: Path
) -> Path:
    """Fase 2 de una fuente: comprueba colisiones de IDs ANTES de borrar, escribe el respaldo
    durable (y lo conserva en memoria), borra SOLO la fuente, agrega y verifica; ante cualquier
    fallo restaura el respaldo y lanza ReingestaFallida. Devuelve la ruta del respaldo."""
    ajenos = _ids_ajenos(collection, fuente, ids)
    if ajenos:
        raise ReingestaRechazada(
            f"{fuente}: {len(ajenos)} IDs nuevos ya existen en el índice con otra fuente "
            f"(p. ej. {ajenos[0]}); no se tocó el índice."
        )
    respaldo = collection.get(
        where={"source": fuente}, include=["documents", "metadatas", "embeddings"]
    )
    ruta_respaldo = _escribir_respaldo(respaldos, fuente, respaldo)
    logger.info(f"     💾 Respaldo de la fuente: {ruta_respaldo}")
    try:
        collection.delete(where={"source": fuente})
        if collection.get(where={"source": fuente}, include=[]).get("ids"):
            raise ReingestaFallida("quedaron fragmentos de la fuente tras el borrado")
        ocupados = collection.get(ids=list(ids), include=["metadatas"]).get("ids") or []
        if ocupados:
            raise ReingestaFallida(
                f"{len(ocupados)} IDs nuevos ya existen en el índice con otra fuente "
                f"(p. ej. {ocupados[0]})"
            )
        _agregar_por_lotes(collection, ids, textos, metadatas, vectores)
        escritos = collection.get(where={"source": fuente}, include=["documents", "metadatas"])
        if _filas_comparables(
            escritos.get("ids") or [], escritos.get("documents") or [],
            escritos.get("metadatas") or [],
        ) != _filas_comparables(ids, textos, metadatas):
            raise ReingestaFallida(
                f"verificación fallida: el índice tiene {len(escritos.get('ids') or [])} "
                f"fragmentos de la fuente y se esperaban {len(ids)} idénticos a los generados"
            )
    except BaseException as exc:
        try:
            restaurados = _restaurar(collection, fuente, respaldo)
        except Exception as error_restauracion:
            raise ReingestaFallida(
                f"{fuente}: la re-ingesta falló ({exc}) y la RESTAURACIÓN en memoria también "
                f"({error_restauracion}). Repón la fuente con: python OpenNotebook.py ingest "
                f"--restaurar \"{ruta_respaldo}\""
            ) from exc
        if not isinstance(exc, Exception):
            raise  # interrupción (Ctrl+C) u otra BaseException: ya restaurado, se propaga
        if isinstance(exc, ReingestaFallida):
            mensaje = str(exc)
        else:
            mensaje = f"{type(exc).__name__}: {exc}"
        raise ReingestaFallida(
            f"{fuente}: la re-ingesta falló ({mensaje}); se restauraron los {restaurados} "
            f"fragmentos previos (respaldo durable: {ruta_respaldo})."
        ) from exc
    return ruta_respaldo


def reingestar_fuentes(
    directory: str,
    fuentes: Sequence[str],
    *,
    simular: bool = False,
    collection=None,
    codificar: Optional[Callable[[List[str]], List[List[float]]]] = None,
    extraer: Optional[Callable[[Path], list]] = None,
    subdividir: Optional[Callable[[str], List[str]]] = None,
    respaldos_dir: Optional[str] = None,
    identidad_confirmada: Sequence[str] = (),
) -> List[Dict]:
    """Re-ingesta (o, con ``simular``, simulación) de las ``fuentes`` nombradas de
    ``directory``: borra SOLO sus fragmentos y los sustituye por los del cortador actual, con
    los mismos metadatos. Devuelve un informe por fuente (fragmentos, etiquetas y cobertura
    antes/después, identidad, extracción, respaldo y segundos).

    ValueError si las fuentes no son válidas; ``ReingestaRechazada`` (subclase de ValueError)
    si la fase 1 rechaza alguna (extracción incompleta, otro documento, IDs ajenos): en ambos
    casos nada se toca. ``ReingestaFallida`` si una sustitución falla (esa fuente queda
    restaurada y las siguientes no se procesan). Con ``simular`` los rechazos se informan
    (``rechazo``) sin lanzar.

    Costuras (para pruebas sin dependencias): ``collection`` (``get``, ``delete``, ``add``),
    ``codificar`` (textos → vectores "passage: "), ``extraer`` (ruta → páginas),
    ``subdividir`` (divisor de respaldo) y ``respaldos_dir``.

    ``identidad_confirmada`` (``--identidad-confirmada``; orden del responsable, 10-oct-2026):
    fuentes, entre las nombradas, cuyo título de primera página el operador confirma aunque
    difiera del indexado. La identidad de esas fuentes la decide solo el contenido, con el
    mismo umbral (``verificar_identidad(titulo_confirmado=True)``); el informe lo registra."""
    pdf_dir = _directorio_de_ingesta(directory)
    rutas = _validar_fuentes(pdf_dir, fuentes)
    sobrantes = sorted(set(identidad_confirmada) - set(fuentes))
    if sobrantes:
        raise ValueError(f"--identidad-confirmada sin su --fuente: {', '.join(sobrantes)}")
    confirmadas = set(identidad_confirmada)
    respaldos = None if simular else _directorio_respaldos(respaldos_dir)

    if collection is None:
        if simular:
            if not (Path(CHROMA_PATH) / "chroma.sqlite3").exists():
                raise ValueError(f"No hay índice en CHROMA_PATH ({CHROMA_PATH}): nada que simular.")
            _cargar_dependencias()
            collection = get_collection(None, crear=False)
        else:
            embedder = get_embedder()
            collection = get_collection(embedder)
            if codificar is None:
                codificar = lambda textos: encode_passages(embedder, textos)  # noqa: E731
    if codificar is None and not simular:
        codificar = lambda textos: encode_passages(get_embedder(), textos)  # noqa: E731
    if subdividir is None:
        subdividir = _divisor_respaldo().split_text

    # ── Fase 1: nada se escribe ───────────────────────────────────────────────────────
    preparadas = []
    for ruta in rutas:
        inicio = time.perf_counter()
        paginas = (extraer or extract_text_from_pdf)(ruta)
        # Tratados (4-oct-2026, opción A): "Artículo N" sin cierre solo corta en un tratado
        # registrado en el catálogo; en las leyes nacionales el cierre es obligatorio.
        tratado = es_tratado_internacional(ruta.name)
        fragmentacion = fragmentar(paginas, max_caracteres=MAX_CHUNK_SIZE, subdividir=subdividir,
                                   fin_de_linea=tratado)
        ids, textos, metadatas = filas_de_fragmentos(ruta, fragmentacion)
        previos = _en_orden(collection.get(
            where={"source": ruta.name}, include=["documents", "metadatas"]
        ))
        identidad = verificar_identidad([doc for _, doc, _ in previos], fragmentacion.texto,
                                        fin_de_linea=tratado,
                                        titulo_confirmado=ruta.name in confirmadas)
        extraccion = paginas_incompletas(paginas)
        ajenos = _ids_ajenos(collection, ruta.name, ids)
        rechazo = []
        if not ids:
            rechazo.append("el PDF no dio texto")
        if extraccion:
            rechazo.append("extracción incompleta: " + "; ".join(extraccion))
        if not identidad["coincide"]:
            rechazo.append("otro documento: " + identidad["motivo"])
        if ajenos:
            rechazo.append(f"{len(ajenos)} IDs nuevos ocupados por otra fuente (p. ej. {ajenos[0]})")
        informe = {
            "fuente": ruta.name,
            "tipo": fragmentacion.tipo,
            "simulacion": simular,
            "antes": medir(
                fragmentacion.texto, [(doc, (meta or {}).get("article", "")) for _, doc, meta in previos],
                fin_de_linea=tratado,
            ),
            "despues": medir(
                fragmentacion.texto, [(f.texto, f.etiqueta) for f in fragmentacion.fragmentos],
                fin_de_linea=tratado,
            ),
            **_diferencia_etiquetas(
                Counter((meta or {}).get("article", "") for _, _, meta in previos
                        if (meta or {}).get("article")),
                Counter(f.etiqueta for f in fragmentacion.fragmentos if f.etiqueta),
            ),
            "identidad": identidad,
            "extraccion_incompleta": extraccion,
            "rechazo": rechazo,
        }
        # Segundos de la fase 1 de ESTA fuente (la fase 2 suma los suyos).
        preparadas.append((ruta, ids, textos, metadatas, previos, informe,
                           time.perf_counter() - inicio))
    rechazadas = [(p[0].name, p[5]["rechazo"]) for p in preparadas if p[5]["rechazo"]]
    if rechazadas and not simular:
        raise ReingestaRechazada(
            "Re-ingesta rechazada; el índice no se tocó. "
            + " | ".join(f"{fuente}: {'; '.join(motivos)}" for fuente, motivos in rechazadas)
        )

    # ── Fase 2: por fuente ────────────────────────────────────────────────────────────
    informes: List[Dict] = []
    for ruta, ids, textos, metadatas, previos, informe, fase1 in preparadas:
        inicio = time.perf_counter() - fase1
        logger.info(f"  🔍 {'Simulado' if simular else 'Re-ingestando'}: {ruta.name}")
        if not simular:
            vectores: List[List[float]] = []
            for i in range(0, len(textos), LOTE_REINGESTA):
                vectores.extend(codificar(textos[i:i + LOTE_REINGESTA]))
            if len(vectores) != len(ids):
                raise ReingestaFallida(
                    f"{ruta.name}: se codificaron {len(vectores)} de {len(ids)} fragmentos; "
                    f"no se tocó el índice."
                )
            informe["respaldo"] = str(_sustituir_fuente(
                collection, ruta.name, ids, textos, metadatas, vectores, respaldos=respaldos
            ))
            logger.info(
                f"     ✅ {len(previos)} fragmentos sustituidos por {len(ids)} "
                f"({time.perf_counter() - inicio:.1f} s)"
            )
        informe["segundos"] = round(time.perf_counter() - inicio, 2)
        informes.append(informe)
    return informes


def restaurar_respaldo(
    archivo: str, *, collection=None, respaldos_dir: Optional[str] = None
) -> Dict:
    """Repone en el índice la fuente de un respaldo durable (``ingest --restaurar``): valida
    el respaldo (formato, huella, cantidades), respalda a su vez el estado actual de la fuente,
    la sustituye por la del respaldo y verifica ids, textos, metadatos y vectores (float32).
    ``ReingestaFallida`` si la verificación falla (con restauración del estado previo)."""
    cuerpo = leer_respaldo(archivo)
    fuente = cuerpo["fuente"]
    respaldos = _directorio_respaldos(respaldos_dir)
    if collection is None:
        _cargar_dependencias()
        collection = get_collection(None)   # los vectores vienen del respaldo
    previo = _sustituir_fuente(
        collection, fuente, cuerpo["ids"], cuerpo["documents"], cuerpo["metadatas"],
        cuerpo["vectores"], respaldos=respaldos,
    )
    if cuerpo["fragmentos"]:
        escritos = collection.get(where={"source": fuente}, include=["embeddings"])
        por_id = dict(zip(escritos.get("ids") or [], escritos.get("embeddings")
                          if escritos.get("embeddings") is not None else []))
        for id_, vector in zip(cuerpo["ids"], cuerpo["vectores"]):
            guardado = array("f", map(float, por_id.get(id_, [])))
            if len(guardado) != len(vector) or any(
                abs(a - b) > TOLERANCIA_VECTOR for a, b in zip(guardado, vector)
            ):
                raise ReingestaFallida(
                    f"{fuente}: el vector de {id_} no coincide con el respaldo tras restaurar; "
                    f"el estado anterior quedó en {previo}"
                )
    logger.info(f"     ✅ {fuente}: {cuerpo['fragmentos']} fragmentos restaurados desde {archivo}")
    return {"fuente": fuente, "fragmentos": cuerpo["fragmentos"], "respaldo_previo": str(previo)}


def retirar_fuentes(
    fuentes: Sequence[str], *, collection=None, respaldos_dir: Optional[str] = None
) -> List[Dict]:
    """Saca del índice TODOS los fragmentos de cada fuente (``ingest --retirar``; orden del
    responsable, 10-oct-2026): p. ej. una ley abrogada cuya sucesora ya se indexó como fuente
    propia. Antes de escribir valida todas: nombre exacto sin ruta, sin repetir, con fragmentos
    en el índice y fuera de ``LAW_SOURCE_MAP`` (lo que el catálogo aún resuelve no se retira:
    la cita quedaría sin fuente). Luego, por fuente: respaldo durable, borrado y verificación;
    ante un fallo restaura el respaldo y lanza ``ReingestaFallida``. Se repone con
    ``ingest --restaurar <respaldo>``."""
    if not fuentes:
        raise ValueError("--retirar exige al menos una fuente (nombre exacto del PDF)")
    repetidas = sorted(f for f, n in Counter(fuentes).items() if n > 1)
    if repetidas:
        raise ValueError(f"Fuente repetida: {', '.join(repetidas)}")
    for fuente in fuentes:
        if not fuente or Path(fuente).name != fuente or fuente in (".", ".."):
            raise ValueError(f"--retirar debe ser solo el nombre del archivo: {fuente!r}")
    catalogadas = set(LAW_SOURCE_MAP.values())
    en_catalogo = sorted(f for f in fuentes if f in catalogadas)
    if en_catalogo:
        raise ValueError(
            f"{', '.join(en_catalogo)} sigue en LAW_SOURCE_MAP: retírala del catálogo antes de "
            f"sacarla del índice"
        )
    if collection is None:
        _cargar_dependencias()
        collection = get_collection(None)   # solo se borra: no hace falta el modelo
    sin_fragmentos = sorted(
        f for f in fuentes if not collection.get(where={"source": f}, include=[]).get("ids")
    )
    if sin_fragmentos:
        raise ValueError(f"{', '.join(sin_fragmentos)} no tiene fragmentos en el índice")
    respaldos = _directorio_respaldos(respaldos_dir)

    informes: List[Dict] = []
    for fuente in fuentes:
        respaldo = collection.get(
            where={"source": fuente}, include=["documents", "metadatas", "embeddings"]
        )
        ruta_respaldo = _escribir_respaldo(respaldos, fuente, respaldo)
        logger.info(f"     💾 Respaldo de la fuente: {ruta_respaldo}")
        try:
            collection.delete(where={"source": fuente})
            if collection.get(where={"source": fuente}, include=[]).get("ids"):
                raise ReingestaFallida("quedaron fragmentos de la fuente tras el borrado")
        except BaseException as exc:
            try:
                restaurados = _restaurar(collection, fuente, respaldo)
            except Exception as error_restauracion:
                raise ReingestaFallida(
                    f"{fuente}: el retiro falló ({exc}) y la RESTAURACIÓN en memoria también "
                    f"({error_restauracion}). Repón la fuente con: python OpenNotebook.py ingest "
                    f"--restaurar \"{ruta_respaldo}\""
                ) from exc
            if not isinstance(exc, Exception):
                raise  # interrupción (Ctrl+C): ya restaurado, se propaga
            raise ReingestaFallida(
                f"{fuente}: el retiro falló ({exc}); se restauraron los {restaurados} "
                f"fragmentos (respaldo durable: {ruta_respaldo})."
            ) from exc
        fragmentos = len(respaldo.get("ids") or [])
        logger.info(f"     ✅ {fuente}: {fragmentos} fragmentos retirados del índice")
        informes.append({"fuente": fuente, "fragmentos": fragmentos, "respaldo": str(ruta_respaldo)})
    return informes


def formato_informe_reingesta(informes: List[Dict]) -> str:
    """Informe legible de ``reingestar_fuentes`` (consola)."""
    lineas = []
    for inf in informes:
        a, d = inf["antes"], inf["despues"]

        def cob(m, clave):
            return "—" if m[clave] is None else f"{m[clave]:.1f} %"

        identidad = inf.get("identidad") or {}
        lineas += [
            f"📄 {inf['fuente']} (tipo {inf['tipo']}; {inf['segundos']} s)",
            f"   fragmentos       : {a['fragmentos']} → {d['fragmentos']}",
            f"   etiquetados      : {a['etiquetados']} → {d['etiquetados']}"
            f"  (sin etiqueta: {a['sin_etiqueta']} → {d['sin_etiqueta']})",
            f"   encabezados      : {d['encabezados']} auténticos ({d['encabezados_cuerpo']} en el "
            f"cuerpo; {d['encabezados_fin_de_linea']} al final de su línea)",
            f"   con su fragmento : cuerpo {a['cubiertos_cuerpo']} → {d['cubiertos_cuerpo']} "
            f"(cobertura {cob(a, 'cobertura')} → {cob(d, 'cobertura')}); documento "
            f"{cob(a, 'cobertura_documento')} → {cob(d, 'cobertura_documento')}",
            f"   etiqueta sin encabezado al inicio (remisiones): "
            f"{a['etiqueta_sin_encabezado']} → {d['etiqueta_sin_encabezado']}",
            f"   etiquetas ganadas: {inf['etiquetas_ganadas']}"
            + (f" ({', '.join(inf['muestra_ganadas'][:20])}…)" if inf["muestra_ganadas"] else ""),
            f"   etiquetas perdidas: {inf['etiquetas_perdidas']}"
            + (f" ({', '.join(inf['muestra_perdidas'][:20])}…)" if inf["muestra_perdidas"] else ""),
            f"   identidad        : {'✅' if identidad.get('coincide') else '❌'} "
            f"({identidad.get('criterio')}; solapamiento {identidad.get('solapamiento')}"
            + (f"; título confirmado por el operador: '{identidad.get('titulo_nuevo', '')[:80]}' "
               f"frente a '{identidad.get('titulo_indexado', '')[:80]}'"
               if identidad.get("titulo_confirmado") else "")
            + ")",
        ]
        if a["no_ubicados"]:
            lineas.append(
                f"   ⚠️  {a['no_ubicados']} fragmentos del índice no se ubican en el texto del "
                f"PDF (el PDF o su extracción cambió desde la ingesta)"
            )
        for motivo in inf.get("rechazo") or []:
            lineas.append(f"   ⛔ {motivo}")
        if inf.get("respaldo"):
            lineas.append(f"   💾 respaldo: {inf['respaldo']}")
        lineas.append(
            "   (simulación: el índice no se modificó)" if inf["simulacion"]
            else "   ✅ fuente re-ingestada (solo sus fragmentos)"
        )
    return "\n".join(lineas)


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
    ni '247' con 'Artículo 247 Bis.', y '247 Ter' exige el sufijo. Ordinales (3-oct-2026): el
    ordinal se compara por equivalencia ('1' coincide con 'Artículo 1o.').
    """
    res = collection.get(where={"source": source}, include=["documents", "metadatas"])
    designacion = patron_articulo(
        article_num, ordinal_equivalente=True, espacio=r"\s"
    ) or re.escape(
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
    '247', '247Bis'].

    Ordinales (3-oct-2026): el chunker etiqueta "Artículo 1o." como '1o', "Artículo 1º"
    como '1º' y "Artículo 1." o "Artículo 1°" como '1'; el escrito puede citar cualquiera de
    esas grafías. Se añaden las etiquetas del mismo número con cada indicador ordinal
    equivalente ('1' → ['1', '1o', '1º']; '1o' → los mismos), con su letra si la trae
    ('4o.-A' → también '4-A', '4o-A'…). Solo amplía los candidatos: el encabezado exacto (que
    sigue exigiendo el número completo y el sufijo pedido) decide cuál acredita el precepto.
    Antes 'CPEUM Art. 1.' no tenía candidatos por metadata y caía a la búsqueda semántica, que
    mostraba la evidencia de otro artículo. Lista ordenada (determinista).
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
    partes = partes_articulo(a)
    if partes is not None:
        for ordinal in ordinales_equivalentes(partes.ordinal):
            if ordinal == "°":
                continue  # no es carácter de palabra: la etiqueta de "Artículo 1°" es '1'
            base = partes.numero + ordinal
            cands.add(base)
            if partes.letra:
                cands.update({f"{base}-{partes.letra}", f"{base}{partes.letra}"})
        if partes.subnumero:
            # Ronda 2 de la re-ingesta: "58-1" → etiqueta '58-1' (la del encabezado "58-1.-").
            cands.add(f"{partes.numero}-{partes.subnumero}")
    # Ronda 2 (4-oct-2026): la ingesta guarda las etiquetas con ``canon_caja`` ("29-a" →
    # "29-A", "247bis" → "247BIS"); el índice anterior, tal como venían. Se buscan ambas (solo
    # para candidatos con forma de etiqueta: sin blancos ni puntos).
    cands.update({canon_caja(c) for c in cands if re.fullmatch(r"\d+[\w\-]*", c)})
    return sorted(cands)


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


# Verde determinista (criterio del responsable, 3-oct-2026: opción A) — Puntaje mínimo de
# una cita normativa con evidencia completa: el umbral del 🟢 de ``vvca_semaforo`` (85).
VERDE_DETERMINISTA = 85


def _evidencia_completa(
    ref: Dict,
    distance: float,
    source_match: bool,
    metadata_verificado: bool,
    article_heading_verified: Optional[bool],
    derogado: bool,
    unidad_derogada: Optional[str],
    derogacion_ambigua: bool,
    unidad_no_cotejada: Optional[str],
    evidencia_incompleta: bool,
    encabezado_autentico: bool = True,
    ubicacion_no_acreditada: Optional[str] = None,
) -> bool:
    """¿La cita normativa tiene EVIDENCIA COMPLETA para el 🟢 determinista? Todas a la vez:

    - ``metadata_verificado`` (``metadata_hit`` de ``audit``: candidato por metadata
      source+article, encabezado exacto en el fragmento seleccionado, fuente recuperada ==
      esperada y, desde la ronda 2, etiqueta del fragmento elegido entre los candidatos), con
      el encabezado exacto y la coincidencia de fuente también aquí;
    - ronda 2: encabezado AUTÉNTICO ("A" mayúscula y cierre no seguido de "," ni ";"), no una
      remisión al inicio de línea, y ubicación en el cuerpo acreditada
      (``itosturre.audit.ubicacion``: sin ambigüedad ni encabezado tras la frontera);
    - ley identificada (``source_file``) y no por confirmar (``law_requires_confirmation``);
    - precepto no derogado, sin unidad derogada ni derogación ambigua;
    - sin unidad citada no cotejada ni evidencia incompleta;
    - distancia ≤ ``COSINE_THRESHOLD``. Salvaguarda de anomalía (decisión del coordinador):
      con metadata y encabezado pero distancia mayor que el umbral se conserva el
      comportamiento anterior (piso 70, 🟡 COTEJAR). En el corpus real esas distancias van
      de 0.116 a 0.193.
    """
    return bool(
        metadata_verificado
        and article_heading_verified is True
        and source_match
        and ref.get("source_file")
        and not ref.get("law_requires_confirmation")
        and not derogado
        and not unidad_derogada
        and not derogacion_ambigua
        and not unidad_no_cotejada
        and not evidencia_incompleta
        and encabezado_autentico
        and not ubicacion_no_acreditada
        and distance <= COSINE_THRESHOLD
    )


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
    no_localizado: bool = False,
    ordinal_equivalente: bool = False,
    encabezado_autentico: bool = True,
    ubicacion_no_acreditada: Optional[str] = None,
    encabezado_fin_de_linea: bool = False,
    version_no_vigente: Optional[str] = None,
) -> Dict:
    """Score, semáforo y explicación VVCA de una cita normativa con evidencia.

    R4c: ``derogado`` (precepto completo) y ``unidad_derogada`` (fracción o inciso citados,
    p. ej. "fracción I") y ``derogacion_ambigua`` limitan a 60–84: la unidad se ubicó y su
    texto vigente no la sostiene. ``unidad_no_cotejada`` (motivo) y ``evidencia_incompleta``
    solo impiden el 🟢 (tope 84).

    R4-D10 (criterio del responsable, 2-oct-2026: opción C): una cita normativa con evidencia
    nunca es 🔴 aquí. El 🔴 exige prueba positiva de inexistencia, que ``audit`` resuelve
    aparte (``itosturre.audit.inexistencia``); la distancia alta sin metadata limita el
    puntaje a 60–84. ``no_localizado``: el fragmento no trae el encabezado exacto, la
    distancia supera el umbral y no hubo prueba (antes "Posible alucinación").

    Verde determinista (criterio del responsable, 3-oct-2026: opción A): con EVIDENCIA
    COMPLETA (``_evidencia_completa``) la cita es 🟢 por regla determinista (puntaje mínimo
    85): la distancia coseno de una consulta corta ("Artículo 109 cnpp") al fragmento con el
    encabezado exacto no mide la existencia del precepto. El puntaje por similitud queda como
    dato informativo (``explicabilidad["score_similitud"]``). El 🟢 de una norma acredita
    existencia y ubicación en la versión indexada (``ALCANCE_NORMATIVA``), no vigencia ni
    contenido. Fuera de esa ruta (sin metadata) la distancia decide como antes.

    Ordinales (3-oct-2026): ``ordinal_equivalente`` indica que el encabezado solo coincide por
    la equivalencia del ordinal ("2" frente a "ARTÍCULO 2o.-"). Con metadata no cambia nada
    (la etiqueta del índice ya identifica el artículo); sin metadata limita a 84: la
    equivalencia ubica el precepto, pero el 🟢 de la ruta semántica no se amplía a otras
    grafías del ordinal.

    Ronda 2: ``encabezado_autentico`` False (la línea es una remisión: "artículo 41." en
    minúscula o "Artículo 2o., fracción I") y ``ubicacion_no_acreditada`` (motivo: encabezado
    repetido que la frontera TRANSITORIOS no desambigua, o el único tras ella) impiden el 🟢
    en cualquier ruta (tope 84).

    Tratados (criterio del responsable, 4-oct-2026, opción A): ``encabezado_fin_de_linea``
    indica que el encabezado elegido es el de un tratado internacional registrado, sin cierre
    ("Artículo 8º" solo en su línea). Con metadata no cambia nada (dato informativo,
    ``explicabilidad["encabezado_fin_de_linea"]``); sin metadata limita a 84, como la
    equivalencia ordinal: el 🟢 de la ruta semántica no se amplía a esa forma.

    Vigencia del corpus (rama fix/vvca-query-vigencia): ``version_no_vigente`` (motivo) dice que
    el reporte de vigencia, hecho sobre este índice, da por no vigente la versión indexada de la
    ley (``itosturre.audit.vigencia``). Limita a 84 en cualquier ruta: el precepto existe en esa
    versión (el verde determinista queda como dato), pero el texto cotejado puede no ser el que
    rige. Nunca baja de 🟡 por este motivo.
    """
    # Desde R4c ``source_match`` compara de verdad la fuente recuperada con la esperada
    # (R4-D09): la penalización −15 de ``vvca_score`` deja de ser inalcanzable.
    score = vvca_score(distance, source_match, has_source_file=bool(ref.get("source_file")))
    score_similitud = score
    por_confirmar = bool(ref.get("law_requires_confirmation"))
    verde_determinista = _evidencia_completa(
        ref, distance, source_match, metadata_verificado, article_heading_verified, derogado,
        unidad_derogada, derogacion_ambigua, unidad_no_cotejada, evidencia_incompleta,
        encabezado_autentico, ubicacion_no_acreditada,
    )
    # Verde determinista: metadata source+article, encabezado exacto en el fragmento
    # seleccionado, fuente recuperada == esperada, ley identificada y no por confirmar, sin
    # derogación ni unidad sin cotejar ni evidencia incompleta, y distancia ≤ umbral. Los
    # topes de abajo siguen aplicándose después (con evidencia completa ninguno se activa).
    if verde_determinista:
        score = max(score, VERDE_DETERMINISTA)
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
    # R4-D10 (opción C): la distancia alta sin metadata no acredita ni refuta: 🟡 (60–84).
    # Antes, con distancia > 0.40, el puntaje caía bajo 60 (🔴) sin prueba de inexistencia.
    if distance > COSINE_THRESHOLD and not metadata_verificado:
        score = max(60, min(score, 84))
    # Ordinales (3-oct-2026): en la ruta semántica (sin metadata) un encabezado que solo
    # coincide por la equivalencia del ordinal ubica el precepto, pero no da 🟢.
    ordinal_sin_metadata = ordinal_equivalente and not metadata_verificado
    if ordinal_sin_metadata:
        score = min(score, 84)
    # Tratados (4-oct-2026): igual con el encabezado sin cierre de un tratado sin metadata.
    fin_de_linea_sin_metadata = encabezado_fin_de_linea and not metadata_verificado
    if fin_de_linea_sin_metadata:
        score = min(score, 84)
    # Ronda 2: solo una remisión al inicio de línea ("artículo 41.", "Artículo 2o., fracción
    # I") o una ubicación no acreditada en el cuerpo (encabezado repetido sin frontera que lo
    # desambigüe, o el único tras la frontera TRANSITORIOS): nunca 🟢, en ninguna ruta.
    solo_remision = bool(article_heading_verified) and not encabezado_autentico
    if solo_remision or ubicacion_no_acreditada:
        score = min(score, 84)
    # Vigencia del corpus: la versión indexada ya no es la vigente según el reporte: nunca 🟢.
    if version_no_vigente:
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
    elif solo_remision:
        # Ronda 2: la línea con forma de encabezado es una remisión, no el encabezado.
        v_verificacion = (
            f"Solo remisión: el fragmento trae el artículo citado al inicio de una línea en "
            f"minúscula o seguido de coma (remisión o cita), no su encabezado; no acredita el "
            f"precepto (dist={distance:.3f})"
        )
    elif ubicacion_no_acreditada:
        v_verificacion = (
            f"Ubicación no acreditada: {ubicacion_no_acreditada} (dist={distance:.3f})"
        )
    elif verde_determinista:
        # Verde determinista: la verificación es determinista; la distancia se muestra
        # como dato informativo, no como fundamento del 🟢.
        v_verificacion = (
            f"Verificación determinista: artículo localizado por metadata (ley y artículo) con "
            f"su encabezado exacto en la ley citada; existencia y ubicación en la versión "
            f"indexada, no vigencia ni contenido. Distancia informativa: dist={distance:.3f} "
            f"(≤ umbral {COSINE_THRESHOLD}; puntaje por similitud {score_similitud})"
        )
    elif metadata_verificado:
        v_verificacion = (
            f"Artículo confirmado por metadata y encabezado exacto en corpus oficial "
            f"(dist={distance:.3f})"
        )
    elif no_localizado:
        v_verificacion = (
            f"No localizado: el fragmento no contiene el encabezado exacto del artículo y no "
            f"se acredita su inexistencia (dist={distance:.3f}, umbral={COSINE_THRESHOLD})"
        )
    elif article_heading_verified is False:
        v_verificacion = (
            f"Evidencia insuficiente: el fragmento no contiene el encabezado exacto "
            f"del artículo (dist={distance:.3f})"
        )
    elif distance <= COSINE_THRESHOLD:
        v_verificacion = f"Encontrado en corpus oficial (dist={distance:.3f})"
    else:
        # R4-D10: antes "Coincidencia débil — posible alucinación".
        v_verificacion = (
            f"Coincidencia débil: el texto recuperado coincide poco con la cita "
            f"(dist={distance:.3f}, umbral={COSINE_THRESHOLD})"
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
    if ordinal_sin_metadata:
        v_verificacion = (
            f"{v_verificacion}; encabezado ubicado solo por equivalencia del ordinal, en un "
            f"fragmento sin metadata del artículo: no acredita el precepto"
        )
    if fin_de_linea_sin_metadata:
        v_verificacion = (
            f"{v_verificacion}; encabezado de tratado sin cierre en un fragmento sin metadata "
            f"del artículo: no acredita el precepto"
        )
    if version_no_vigente:
        v_verificacion = f"{v_verificacion}; {version_no_vigente}"
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
    if no_localizado:
        explicabilidad["no_localizado"] = True
    if ordinal_equivalente:
        # Ordinales (3-oct-2026, campo añadido): el encabezado coincide con otra grafía del
        # ordinal ("Artículo 1o." para el "1"); informativo con metadata, tope sin ella.
        explicabilidad["ordinal_equivalente"] = True
    if encabezado_fin_de_linea:
        # Tratados (4-oct-2026, campo añadido): el encabezado elegido es el de un tratado
        # registrado, sin cierre; informativo con metadata, tope sin ella.
        explicabilidad["encabezado_fin_de_linea"] = True
    if solo_remision:
        # Ronda 2 (campo añadido): el "encabezado" es una remisión al inicio de línea.
        explicabilidad["encabezado_autentico"] = False
    if ubicacion_no_acreditada:
        explicabilidad["ubicacion_no_acreditada"] = ubicacion_no_acreditada
    if version_no_vigente:
        # Vigencia del corpus (campo añadido): por qué el 🟢 no se concede.
        explicabilidad["version_no_vigente"] = version_no_vigente
    if verde_determinista:
        # Verde determinista (campos añadidos): la regla que dio el 🟢 y el puntaje por
        # similitud (informativo) que habría dado la distancia sola.
        explicabilidad["verde_determinista"] = True
        explicabilidad["score_similitud"] = score_similitud
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
                 discrepantes: int, no_encontradas: int, parciales: int = 0,
                 vigencia_perdida: int = 0) -> str:
    """Parte de jurisprudencia del ``summary`` (R4c, R4-D12): "sin citas" si no se invocó
    ninguna tesis (antes "SJF 0.0 🔴 (0/0 tesis ok)"). "ok" cuenta solo las verificadas
    (ronda 2); las parciales se dicen aparte. V1 (piloto PEN-01): las rojas reales (rubro
    discrepante, vigencia perdida) van primero; las no encontradas se dicen 🟡 (no
    verificables, no confirmadas como falsas)."""
    if total == 0:
        return "SJF sin citas"
    return (
        f"SJF {_puntaje(score)} {semaforo} ({ok}/{total} tesis ok)"
        + (f" — {discrepantes} rubro discrepante" if discrepantes else "")
        + (f", {vigencia_perdida} con vigencia perdida" if vigencia_perdida else "")
        + (f", {no_encontradas} no encontradas (🟡 no verificables)" if no_encontradas else "")
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
    posterior: Optional[Dict] = None,
) -> None:
    """🟡 NO VERIFICABLE para un precepto que el índice no localiza con su encabezado exacto
    porque agrupa las variantes con letra o sufijo bajo el número base (R4b). D10: si el
    artículo sigue al último de la versión indexada sin superar el margen (``posterior``),
    la alerta lo dice ("🟡 POSTERIOR AL ÚLTIMO ARTÍCULO")."""
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
        _alerta_posterior(ref, posterior) if posterior else
        f"🟡 NO VERIFICABLE: '{ref['raw']}' — {detalle}. NO es alucinación: el corpus no "
        f"permite localizar el precepto. Cotejarlo en la fuente oficial antes de citar."
    )
    metadata = {
        "encabezado_articulo": False,
        "sufijo_solicitado": sufijo_pedido,
        "variante_con_sufijo": bool(selected.get("variant_heading")),
        "candidatos_metadata": metadata_candidate_found,
        "coseno": round(selected["distance"], 4),
        "umbral": COSINE_THRESHOLD,
        "fuente_encontrada": best_source,
        "fuente_esperada": expected_source,
        "ley_inferida": bool(ref.get("law_inferred")),
    }
    if posterior:
        metadata["posterior_al_ultimo"] = posterior
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
        metadata=metadata,
    ))


# ─────────────────────────────────────────
# R4-D10 — ARTÍCULO NO LOCALIZADO EN UNA LEY INDEXADA
# ─────────────────────────────────────────
# Criterio del responsable jurídico (2-oct-2026, opción C): un artículo citado que no se
# localiza en una ley que SÍ está indexada solo es 🔴 con prueba positiva de inexistencia
# (``itosturre.audit.inexistencia``: vecinos en el mismo fragmento o número muy superior al
# último artículo del cuerpo completo de la versión indexada). En cualquier otro caso es 🟡:
# "no localizado" no es "no existe" (puede ser un hueco del índice). Antes: "🔴 ALERTA ALTA
# … Posible alucinación" y "🔴 ALERTA CRÍTICA … Alucinación detectada". Ronda 2: la prueba
# se abstiene ante cualquier ambigüedad (preferimos perder un 🔴 que emitir uno falso).

# Solo una ley ligada al artículo por vínculo sintáctico explícito puede sostener la prueba:
# a la derecha o a la izquierda pegada, o por posesivo (la coordinación hereda ese método).
# Con la ley del contexto previo, de un antecedente o de un encabezado, inferida o por
# confirmar, un 🔴 dependería de haber adivinado bien el ordenamiento.
METODOS_LEY_EXPLICITA = frozenset({"adyacente_derecha", "adyacente_izquierda", "posesivo"})


def _denominaciones(fuente: str) -> List[str]:
    """Denominaciones del catálogo para una fuente (comprobación de identidad, P5)."""
    return [clave for clave, archivo in LAW_SOURCE_MAP.items() if archivo == fuente]


def _evaluar_inexistencia(ref: Dict, collection, leyes: Dict) -> Dict:
    """Prueba positiva de inexistencia del artículo en el cuerpo de su ley (o el motivo por
    el que no la hay). Cada ley se lee (por metadata ``source``) y se prepara una sola vez
    por auditoría; si la lectura falla no hay prueba."""
    metodo = ref.get("law_method")
    if (metodo not in METODOS_LEY_EXPLICITA or ref.get("law_inferred")
            or ref.get("law_requires_confirmation")):
        return {
            "acreditada": False,
            "prueba": None,
            "motivo": (
                f"la ley no se ligó al artículo por vínculo sintáctico explícito (método "
                f"'{metodo}'): no se puede acreditar la inexistencia"
            ),
        }
    preparada = _ley_preparada(ref.get("source_file"), collection, leyes)
    if preparada is None:
        return {
            "acreditada": False,
            "prueba": None,
            "motivo": "no se pudieron leer los fragmentos de la ley indexada",
        }
    return evaluar_inexistencia(preparada[0], ref["article"])


def _ley_preparada(
    fuente: Optional[str], collection, leyes: Dict
) -> Optional[Tuple[object, Dict[int, str]]]:
    """La ley ``fuente`` leída (por metadata ``source``) y preparada (``preparar_ley``) una sola
    vez por auditoría, con sus textos originales por ``chunk_index``; None si la lectura
    falla. La comparten la prueba de inexistencia (D10) y la frontera del cuerpo del verde
    determinista (ronda 2)."""
    if fuente not in leyes:
        try:
            res = collection.get(where={"source": fuente}, include=["documents", "metadatas"])
            pares = list(zip(res.get("documents") or [], res.get("metadatas") or []))
        except Exception:
            pares = []
        originales: Dict[int, str] = {}
        for documento, metadata in pares:
            try:
                originales[int(str((metadata or {}).get("chunk_index")))] = documento
            except (TypeError, ValueError):
                continue
        # Tratados (4-oct-2026): en un tratado registrado los encabezados sin cierre cuentan.
        leyes[fuente] = (
            (preparar_ley(pares, _denominaciones(fuente),
                          fin_de_linea=es_tratado_internacional(fuente)), originales)
            if pares else None
        )
    return leyes[fuente]


def _alerta_posterior(ref: Dict, posterior: Dict, score: Optional[int] = None) -> str:
    """🟡 el artículo sigue al último de la versión indexada sin superar el margen (P6)."""
    puntaje = f" (score {score})" if score is not None else ""
    ley = f"'{posterior['fuente']}'"
    return (
        f"🟡 POSTERIOR AL ÚLTIMO ARTÍCULO{puntaje}: '{ref['raw']}' — "
        f"{describir_posterior(posterior, ley)}."
    )


def _alerta_no_localizado(ref: Dict, fuente: str, score: Optional[int] = None) -> str:
    """🟡 NO LOCALIZADO: el corpus no localizó el precepto, sin prueba de que no exista."""
    puntaje = f" (score {score})" if score is not None else ""
    return (
        f"🟡 NO LOCALIZADO{puntaje}: '{ref['raw']}' — no se encontró el art. {ref['article']} "
        f"en la ley indexada '{fuente}'; no se acredita que no exista (puede ser un hueco del "
        f"índice): cotejar en la fuente oficial."
    )


def _evidencia_de_la_prueba(prueba: Dict, originales: Dict[int, str]) -> Tuple[str, str]:
    """Texto original de los fragmentos que sustentan la prueba (para la traza y el pop-up)
    y la página que se informa: el fragmento de los vecinos (prueba 1) o el del último
    artículo y el de la frontera TRANSITORIOS (prueba 2)."""
    if prueba["tipo"] == PRUEBA_VECINOS:
        return originales.get(prueba["fragmentos"][0], ""), prueba["anterior"]["pagina"]
    indices = [prueba["ultimo"]["chunk_index"]]
    if prueba["frontera_transitorios"]["chunk_index"] != indices[0]:
        indices.append(prueba["frontera_transitorios"]["chunk_index"])
    texto = "\n[…]\n".join(originales.get(i, "") for i in indices)
    return texto, prueba["ultimo"]["pagina"]


def _registrar_inexistencia(
    ref: Dict,
    prueba: Dict,
    originales: Dict[int, str],
    selected: Optional[Dict],
    alerts: List[str],
    verification_traces: List[Dict],
    retrieved_sources: List[Dict],
    vigencia: Optional[Dict] = None,
) -> None:
    """🔴 ARTÍCULO INEXISTENTE ACREDITADO (traza ``refuted``, puntaje 0). Bloquea el
    documento como toda cita normativa refutada. La evidencia es la de la prueba (los
    encabezados vecinos o el final del cuerpo), no el fragmento semántico más cercano.

    Vigencia del corpus: si el reporte de vigencia (``vigencia``) da por no vigente la versión
    indexada, la prueba solo acredita que el artículo no está en ESA versión: 🟡 INEXISTENTE EN
    UNA VERSIÓN NO VIGENTE (traza ``not_verifiable``, puntaje 60). Una reforma posterior pudo
    adicionarlo; nunca 🔴 sin prueba sobre la ley vigente (criterio C)."""
    fuente = ref["source_file"]
    descripcion = describir_prueba(prueba, f"'{fuente}'")
    evidencia, pagina = _evidencia_de_la_prueba(prueba, originales)
    no_vigente = bool(vigencia and vigencia.get("estado") == FUENTE_NO_VIGENTE)
    art = ref.get("article", "?")
    if no_vigente:
        alerts.append(
            f"🟡 INEXISTENTE EN UNA VERSIÓN NO VIGENTE (score 60): '{ref['raw']}' — "
            f"{descripcion}; pero {vigencia['motivo']}: no acredita que el artículo no exista en "
            f"la ley vigente; {instruccion_cotejo(vigencia, art)}"
        )
    else:
        alerts.append(
            f"🔴 ARTÍCULO INEXISTENTE ACREDITADO: '{ref['raw']}' — {descripcion}. Corregir o "
            f"sustituir la cita antes de cualquier uso procesal; si el escrito invoca una reforma "
            f"posterior a esa versión, cotejarla en la fuente oficial."
        )
    frac = ref.get("fraction", "")
    art_label = f"Art. {art}" + (f" fr. {frac}" if frac else "")
    explicabilidad = {
        ("inexistencia_version_indexada" if no_vigente else "inexistencia_acreditada"): prueba,
        "coseno": round(selected["distance"], 4) if selected else None,
        "umbral": COSINE_THRESHOLD,
        "encabezado_articulo": False,
        "coincide_fuente": True,
        "fuente_encontrada": fuente,
        "fuente_esperada": fuente,
        "ley_inferida": bool(ref.get("law_inferred")),
    }
    if no_vigente:
        explicabilidad["version_no_vigente"] = vigencia["motivo"]
    puntaje, semaforo = (60, "🟡") if no_vigente else (0, "🔴")
    vvca = {
        "score": puntaje,
        "semaforo": semaforo,
        "V_verificacion": (
            f"Inexistente en la versión indexada, que no es la vigente: {descripcion}; "
            f"{vigencia['motivo']}" if no_vigente
            else f"Artículo inexistente acreditado: {descripcion}"
        ),
        "V_validacion": f"Fuente correcta: {fuente}",
        "C_contextualizacion": vvca_contextualizacion(fuente),
        "A_auditabilidad": f"{art_label} · {ref.get('law', 'desconocido')} · pág. {pagina} · corpus: {fuente}",
        "explicabilidad": explicabilidad,
    }
    trace = build_trace_record(
        reference=ref["raw"],
        ref_type="normativa",
        status="not_verifiable" if no_vigente else "refuted",
        method="corpus_estructura",
        reason=vvca["V_verificacion"],
        score=puntaje,
        semaforo=semaforo,
        source_file=fuente,
        locator=f"página {pagina} · artículo {art}",
        evidence_text=evidencia,
        metadata=explicabilidad,
    )
    verification_traces.append(trace)
    unidades = _unidades_de(ref)
    entrada = {
        "reference": ref["raw"],
        "law": ref["law"],
        "article": art,
        "ref_type": "normativa",
        "source_file": fuente,
        "page": pagina,
        "expected_source": fuente,
        "law_inferred": ref.get("law_inferred", False),
        "law_method": ref.get("law_method"),
        "law_requires_confirmation": False,
        "relevance_score": round(1 - selected["distance"], 3) if selected else None,
        "retrieved_text": evidencia[:600],
        "retrieved_text_full": evidencia,
        "vvca": vvca,
        "precepto_derogado": False,
        "alcance_verificacion": ALCANCE_NORMATIVA,
        "unidad_citada": unidades,
        "unidad_cotejada": None if not unidades else False,
        "unidad_derogada": None,
        "unidad_no_cotejada": None,
        "derogacion_ambigua": False,
        "evidencia_incompleta": False,
        # R4-D10 (campo añadido): la prueba positiva de inexistencia.
        "inexistencia_acreditada": prueba,
        "trace_id": trace["trace_id"],
    }
    if vigencia is not None:
        # Vigencia del corpus (campos añadidos): estado de la ley según el reporte; con versión
        # no vigente la prueba solo vale para la versión indexada.
        entrada["vigencia_fuente"] = vigencia
        if no_vigente:
            entrada["inexistencia_version_indexada"] = entrada.pop("inexistencia_acreditada")
    retrieved_sources.append(entrada)


# ─────────────────────────────────────────
# VIGENCIA DEL CORPUS (rama fix/vvca-query-vigencia)
# ─────────────────────────────────────────

def _ultimo_reporte_vigencia(carpeta: Path) -> Optional[Path]:
    """El reporte ``vigencia_AAAA-MM-DD.json`` más reciente de ``carpeta`` (o None)."""
    try:
        reportes = sorted(carpeta.glob("vigencia_*.json"))
    except OSError:
        return None
    return reportes[-1] if reportes else None


def _reporte_vigencia() -> Tuple[Optional[ReporteVigencia], Dict]:
    """El reporte de vigencia aplicable a ESTE índice y lo que de él va al resumen.

    Solo se aplica el reporte hecho sobre ``CHROMA_PATH``: el de otro índice (otra copia, otro
    equipo) no describe estas versiones. Sin reporte, ilegible o de otro índice, el semáforo no
    cambia y el resumen dice por qué."""
    ruta = (Path(VIGENCIA_REPORTE).expanduser() if VIGENCIA_REPORTE
            else _ultimo_reporte_vigencia(Path(VIGENCIA_REPORTES_DIR).expanduser()))
    if ruta is None or not ruta.is_file():
        return None, {"estado": REPORTE_AUSENTE, "reporte": None, "ruta": None}
    try:
        reporte = cargar_reporte(json.loads(ruta.read_text(encoding="utf-8")), str(ruta))
    except (OSError, ValueError) as exc:
        logger.warning(f"⚠️  Reporte de vigencia ilegible ({ruta}): {exc}")
        return None, {"estado": REPORTE_ILEGIBLE, "reporte": None, "ruta": str(ruta)}
    if Path(reporte.chroma).expanduser().resolve() != Path(CHROMA_PATH).expanduser().resolve():
        return None, {"estado": REPORTE_OTRO_INDICE, "reporte": reporte.fecha, "ruta": str(ruta)}
    return reporte, {"estado": REPORTE_APLICADO, "reporte": reporte.fecha, "ruta": str(ruta)}


def _fragmentos_de(fuente: str, collection, cache: Dict) -> Optional[int]:
    """Fragmentos que ``fuente`` tiene hoy en el índice (None si no se pudieron contar)."""
    if fuente not in cache:
        try:
            cache[fuente] = len(
                collection.get(where={"source": fuente}, include=[]).get("ids") or []
            )
        except Exception:
            cache[fuente] = None
    return cache[fuente]


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
    # R4-D10: cada ley citada (por ``source``), leída y preparada una sola vez por auditoría
    # —``(LeyPreparada, textos originales por chunk_index)``— y solo si algún artículo suyo
    # no se localiza.
    leyes_preparadas: Dict[str, Optional[Tuple[object, Dict[int, str]]]] = {}
    # Vigencia del corpus (rama fix/vvca-query-vigencia): el reporte aplicable a este índice,
    # leído una sola vez; los fragmentos de una fuente se cuentan solo si el reporte la registra.
    reporte_vigencia, resumen_vigencia = _reporte_vigencia()
    fragmentos_por_fuente: Dict[str, Optional[int]] = {}

    def vigencia_de(fuente: str) -> Optional[Dict]:
        if reporte_vigencia is None:
            return None
        fragmentos = (_fragmentos_de(fuente, collection, fragmentos_por_fuente)
                      if fila_de(reporte_vigencia, fuente) else None)
        return vigencia_de_fuente(reporte_vigencia, fuente, fragmentos)

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
            # "no encontrado" (entonces "alucinación detectada"; desde D10, 🟡 NO LOCALIZADO
            # salvo prueba de inexistencia), que tacharía de falsa una cita válida (p. ej.
            # LGV/PIDCP en el caso Aaron García).
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
            cands: List[str] = []
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
            # Ronda 2 (Codex P1): si la consulta exacta se abandona (falla o vuelve vacía), la
            # evidencia sale de la búsqueda semántica y no hereda la bandera de metadata (antes
            # un fragmento del respaldo con otra etiqueta obtenía ``metadata_hit``).
            if results is None:
                metadata_candidate_found = False

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

            # Tratados (criterio del responsable, 4-oct-2026, opción A): si la ley citada es un
            # tratado internacional registrado en el catálogo, su encabezado "Artículo N" sin
            # cierre (solo al final de su línea) es auténtico en la selección de evidencia, la
            # ubicación, el cuerpo y el cotejo de la unidad, y la existencia de D10.
            tratado = es_tratado_internacional(expected_source)
            selected = select_article_evidence(results, ref["article"], fin_de_linea=tratado)
            ubicacion = None
            if selected:
                # Ronda 2 (pertenencia al cuerpo): con metadata y encabezado auténtico, la
                # ubicación se acredita con la frontera TRANSITORIOS creíble de la ley citada
                # (``itosturre.audit.ubicacion``); si lo decide otro resultado, se elige ese.
                if (
                    metadata_candidate_found
                    and selected["heading_authentic"]
                    and (selected["metadata"] or {}).get("source") == expected_source
                ):
                    preparada = _ley_preparada(expected_source, collection, leyes_preparadas)
                    ubicacion = ubicar_en_cuerpo(
                        (results.get("documents") or [[]])[0] or [],
                        (results.get("metadatas") or [[]])[0] or [],
                        ref["article"],
                        expected_source,
                        frontera_creible(preparada[0] if preparada else None),
                        fin_de_linea=tratado,
                        # Tratados (ronda 2): la secuencia de encabezados de la fuente.
                        ley=preparada[0] if preparada else None,
                    )
                    otro = ubicacion["indice"]
                    if otro is not None and otro != selected["rank"] - 1:
                        selected = select_article_evidence(
                            results, ref["article"], preferido=ubicacion["indice"],
                            fin_de_linea=tratado,
                        )
                best_doc = selected["document"]
                best_meta = selected["metadata"]
                best_source = best_meta.get("source", "desconocido")
                best_distance = selected["distance"]
                article_heading_verified = selected["heading_verified"]
                # Ronda 2: el encabezado elegido es auténtico (no una remisión al inicio de línea).
                encabezado_autentico = bool(selected["heading_authentic"])
                # Ordinales (3-oct-2026): el encabezado elegido solo coincide por la equivalencia
                # del ordinal ("2" frente a "ARTÍCULO 2o.-"), no con la grafía citada.
                ordinal_equivalente = bool(
                    article_heading_verified and not selected.get("heading_literal", True)
                )
                # Tratados (4-oct-2026): el encabezado elegido no lleva cierre ("Artículo 8º"
                # solo en su línea); sin metadata no da 🟢 (como la equivalencia ordinal).
                encabezado_fin_de_linea = bool(selected.get("heading_fin_de_linea"))
                # R4c (R4-D09): comparación real con la fuente esperada (desde R4b siempre
                # existe aquí: una cita sin ley identificada no llega a la consulta).
                source_match = best_source == expected_source
                # La metadata solo corrobora si la evidencia es de la ley citada. Ronda 2
                # (Codex P1): y si la etiqueta del fragmento ELEGIDO está entre los candidatos.
                metadata_hit = (
                    metadata_candidate_found and article_heading_verified and source_match
                    and str(best_meta.get("article", "")) in cands
                )
                ubicacion_no_acreditada = (
                    ubicacion["motivo"]
                    if metadata_hit and ubicacion and ubicacion["estado"] in UBICACION_NO_ACREDITADA
                    else None
                )
                por_confirmar = bool(ref.get("law_requires_confirmation"))

                # R4-D10 (criterio del responsable, 2-oct-2026: opción C) — El precepto no se
                # localizó: la evidencia de la ley citada (indexada) no trae su encabezado
                # exacto. Solo es 🔴 con prueba positiva de inexistencia sobre el cuerpo de la
                # ley (vecinos en el mismo fragmento o número muy superior al último artículo
                # del cuerpo completo) y con la ley ligada por vínculo sintáctico explícito;
                # sin ella cada ruta conserva su 🟡 (o "POSTERIOR AL ÚLTIMO ARTÍCULO" si el
                # número sigue al último sin superar el margen). Con la ley por confirmar o con
                # evidencia de otro ordenamiento no se busca la prueba.
                evaluacion = None
                posterior = None
                if not article_heading_verified and source_match and not por_confirmar:
                    evaluacion = _evaluar_inexistencia(ref, collection, leyes_preparadas)
                    if evaluacion["acreditada"]:
                        _registrar_inexistencia(
                            ref, evaluacion["prueba"], leyes_preparadas[expected_source][1],
                            selected, alerts, verification_traces, retrieved_sources,
                            vigencia_de(expected_source),
                        )
                        continue
                    posterior = evaluacion.get("posterior_al_ultimo")

                # R4b — El chunker etiqueta "4o.-A", "247 Bis" o "29-A Bis" con el número
                # base, así que la búsqueda por metadata devuelve el artículo base y sus
                # variantes. Si el precepto pedido trae sufijo, o el índice solo ofreció
                # variantes con sufijo del número pedido, y ningún fragmento muestra el
                # encabezado exacto, el corpus no permite localizarlo: 🟡 NO VERIFICABLE.
                # Nunca 🟢 contra el artículo base (R4-D01/D06) ni 🔴 sin la prueba positiva
                # de inexistencia de arriba (R4-D10). (Una re-ingesta con etiqueta completa
                # lo evitaría.)
                sufijo_pedido = articulo_con_sufijo(ref["article"])
                if not article_heading_verified and (sufijo_pedido or selected["variant_heading"]):
                    _registrar_sin_encabezado_exacto(
                        ref, selected, best_source, expected_source, sufijo_pedido,
                        metadata_candidate_found, alerts, verification_traces, posterior,
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
                    # Ronda 2: el cuerpo se reconstruye desde la MISMA ocurrencia elegida (el
                    # encabezado auténtico, no una remisión anterior del fragmento).
                    cotejo = cotejar_precepto(best_doc, best_meta, ref["article"], unidades,
                                              candidatos, solo_autentico=encabezado_autentico,
                                              fin_de_linea=tratado)
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

                # Vigencia del corpus: estado de la ley de la evidencia (solo si es la citada).
                vigencia = vigencia_de(best_source) if source_match else None
                version_no_vigente = (
                    vigencia["motivo"]
                    if vigencia and vigencia["estado"] == FUENTE_NO_VIGENTE else None
                )
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
                    # R4-D10: sin encabezado exacto, con distancia alta y sin prueba positiva
                    # de inexistencia (antes "ALERTA ALTA … Posible alucinación").
                    no_localizado=(
                        evaluacion is not None and best_distance > COSINE_THRESHOLD
                    ),
                    ordinal_equivalente=ordinal_equivalente,
                    encabezado_autentico=encabezado_autentico or not article_heading_verified,
                    ubicacion_no_acreditada=ubicacion_no_acreditada,
                    encabezado_fin_de_linea=encabezado_fin_de_linea,
                    version_no_vigente=version_no_vigente,
                )
                if ubicacion and metadata_hit:
                    # Ronda 2 (campo añadido): cómo se acreditó (o no) la pertenencia al cuerpo.
                    vvca["explicabilidad"]["ubicacion"] = {
                        "estado": ubicacion["estado"],
                        "encabezados_autenticos": ubicacion["encabezados"],
                        "paginas": ubicacion["paginas"],
                        "frontera_creible": ubicacion["frontera_creible"],
                        "motivo_frontera": ubicacion["motivo_frontera"],
                    }
                if evaluacion is not None and best_distance > COSINE_THRESHOLD:
                    vvca["explicabilidad"]["inexistencia_no_acreditada"] = evaluacion["motivo"]
                if posterior:
                    vvca["explicabilidad"]["posterior_al_ultimo"] = posterior
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
                if vigencia is not None:
                    # Vigencia del corpus (campo añadido): estado de la ley según el reporte.
                    entry["vigencia_fuente"] = vigencia

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
                    # R4-D10 (opción C): la distancia alta sin metadata ya no refuta. Sin
                    # encabezado exacto (y sin la prueba positiva de inexistencia, que se
                    # resolvió arriba) el precepto queda no localizado: no verificable. Con el
                    # encabezado, o con la ley por confirmar, parcial (como antes de pasar por
                    # el "refuted" que la ley por confirmar ya rebajaba).
                    trace_status = "not_verifiable" if evaluacion is not None else "partial"
                else:
                    trace_status = "verified" if vvca["score"] >= 85 else "partial"
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
                elif article_heading_verified and not encabezado_autentico:
                    # Ronda 2: la línea con forma de encabezado es una remisión ("artículo 41."
                    # al inicio de línea, en minúscula) o una cita ("Artículo 2o., fracción I").
                    alerts.append(
                        f"🟡 COTEJAR (score {vvca['score']}): '{ref['raw']}' — en "
                        f"'{best_source}' (pág. {best_meta.get('page', '?')}) solo se ubicó una "
                        f"remisión al artículo {ref['article']} al inicio de una línea, no su "
                        f"encabezado: no acredita el precepto. Cotejarlo en la fuente oficial "
                        f"antes de citar."
                    )
                elif ubicacion_no_acreditada:
                    # Ronda 2 (pertenencia al cuerpo): encabezado repetido sin frontera que lo
                    # desambigüe, o el único tras la frontera TRANSITORIOS.
                    alerts.append(
                        f"🟡 UBICACIÓN NO ACREDITADA (score {vvca['score']}): '{ref['raw']}' — "
                        f"en '{best_source}': {ubicacion_no_acreditada}. Cotejar el precepto en "
                        f"la fuente oficial antes de citar."
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
                    # R4-D10 (opción C): antes "🔴 ALERTA ALTA … Posible alucinación". Sin
                    # prueba positiva de inexistencia la distancia alta es 🟡: no localizado
                    # (sin encabezado exacto) o ubicado con texto que coincide poco.
                    if article_heading_verified:
                        alerts.append(
                            f"🟡 COTEJAR (score {vvca['score']}): '{ref['raw']}' — se ubicó el "
                            f"encabezado del artículo {ref['article']} en '{best_source}', pero "
                            f"el texto recuperado coincide poco (dist={best_distance:.3f}, "
                            f"umbral={COSINE_THRESHOLD}). Cotejar el texto citado contra el "
                            f"precepto."
                        )
                    elif posterior:
                        alerts.append(_alerta_posterior(ref, posterior, vvca["score"]))
                    else:
                        alerts.append(_alerta_no_localizado(ref, best_source, vvca["score"]))
                elif ordinal_equivalente:
                    # Ordinales (3-oct-2026): ruta semántica (sin metadata del artículo) con el
                    # encabezado ubicado solo por la equivalencia del ordinal: 🟡 (tope 84), como
                    # quedaba esa grafía antes de la equivalencia; el 🟢 de la ruta semántica no
                    # se amplía.
                    alerts.append(
                        f"🟡 COTEJAR (score {vvca['score']}): '{ref['raw']}' — se ubicó en "
                        f"'{best_source}' el encabezado del artículo {ref['article']} con otra "
                        f"grafía del ordinal, en un fragmento sin metadata de ese artículo: la "
                        f"equivalencia lo ubica pero no lo acredita. Cotejar el precepto antes "
                        f"de citar."
                    )
                elif encabezado_fin_de_linea:
                    # Tratados (4-oct-2026): ruta semántica (sin metadata del artículo) con el
                    # encabezado sin cierre de un tratado: 🟡 (tope 84), como la equivalencia
                    # ordinal; el 🟢 de la ruta semántica no se amplía.
                    alerts.append(
                        f"🟡 COTEJAR (score {vvca['score']}): '{ref['raw']}' — se ubicó en "
                        f"'{best_source}' el encabezado sin cierre del artículo {ref['article']} "
                        f"(tratado internacional), en un fragmento sin metadata de ese artículo: "
                        f"lo ubica pero no lo acredita. Cotejar el precepto antes de citar."
                    )
                elif article_heading_verified is False and posterior:
                    # D10 (ronda 2): el número sigue al último artículo de la versión indexada
                    # sin superar el margen: una reforma posterior pudo adicionarlo (🟡).
                    alerts.append(_alerta_posterior(ref, posterior, vvca["score"]))
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
                if version_no_vigente:
                    # Vigencia del corpus: aviso que se suma a los anteriores.
                    alerts.append(
                        f"🟡 VERSIÓN INDEXADA NO VIGENTE (score {vvca['score']}): '{ref['raw']}' "
                        f"— {version_no_vigente}; {instruccion_cotejo(vigencia, ref['article'])}"
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
                # R4-D10 (opción C): la consulta no devolvió evidencia en una ley indexada.
                # Antes "🔴 ALERTA CRÍTICA … Alucinación detectada". Solo es 🔴 con prueba
                # positiva de inexistencia sobre el cuerpo de la ley; si no, 🟡 NO LOCALIZADO.
                evaluacion = _evaluar_inexistencia(ref, collection, leyes_preparadas)
                if evaluacion["acreditada"]:
                    _registrar_inexistencia(
                        ref, evaluacion["prueba"], leyes_preparadas[expected_source][1],
                        None, alerts, verification_traces, retrieved_sources,
                        vigencia_de(expected_source),
                    )
                    continue
                posterior = evaluacion.get("posterior_al_ultimo")
                alerts.append(
                    _alerta_posterior(ref, posterior) if posterior
                    else _alerta_no_localizado(ref, expected_source)
                )
                metadata_no_localizado = {
                    "no_localizado": True,
                    "inexistencia_no_acreditada": evaluacion["motivo"],
                }
                if posterior:
                    metadata_no_localizado["posterior_al_ultimo"] = posterior
                verification_traces.append(build_trace_record(
                    reference=ref["raw"],
                    ref_type="normativa",
                    status="not_verifiable",
                    method="corpus_local",
                    reason=(
                        "Artículo no localizado en una fuente que sí está indexada; no se "
                        f"acredita su inexistencia: {evaluacion['motivo']}"
                    ),
                    semaforo="🟡",
                    source_file=expected_source,
                    locator=f"artículo {ref['article']}",
                    metadata=metadata_no_localizado,
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

    # Conteo de tesis problemáticas: rubro discrepante o invertido (🔴), no encontradas (🟡)
    tesis_total_invocadas = sum(1 for r in refs if r.get("type") == "jurisprudencia")
    tesis_no_encontradas  = tesis_total_invocadas - len(jur_scores)
    tesis_mismatch        = sum(
        1 for s in retrieved_sources
        if s.get("ref_type") == "jurisprudencia" and s.get("vvca", {}).get("rubro_mismatch")
    )
    # V1 (piloto PEN-01): solo rojas reales —rubro discrepante o invertido, o vigencia
    # perdida—, cada tesis una vez. Antes sumaba las no encontradas, que son 🟡 NO
    # VERIFICABLE ("🟡 no es 🔴"): un escrito 🟡 con rojos 0 reportaba tesis_rojas > 0.
    # Solo informa: el veredicto se calcula con los conteos de siempre y no cambia.
    tesis_rojas = sum(
        1 for s in retrieved_sources
        if s.get("ref_type") == "jurisprudencia" and (
            s.get("vvca", {}).get("rubro_mismatch")
            or s.get("vvca", {}).get("estado_vigencia") in VIGENCIA_PERDIDA
        )
    )
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
    # Vigencia del corpus: citas que no son verdes (o rojas) porque la versión indexada de su ley
    # ya no es la vigente según el reporte.
    normativa_no_vigente = sum(
        1 for s in retrieved_sources
        if s.get("ref_type") == "normativa"
        and s.get("vvca", {}).get("explicabilidad", {}).get("version_no_vigente")
    )
    veredicto = veredicto_global(
        score_rag, score_sjf, tesis_mismatch, tesis_no_encontradas,
        tesis_total_invocadas, tesis_superadas,
        normativa_refutada, normativa_no_verificable,
        articulos_total=articulos_total,
        tesis_parciales=tesis_parciales,
        normativa_no_vigente=normativa_no_vigente,
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
            # Vigencia del corpus (campo añadido): si se aplicó un reporte de vigencia a este
            # índice y cuántas citas normativas toca.
            "vigencia_corpus": {**resumen_vigencia,
                                "normativa_version_no_vigente": normativa_no_vigente},
        },
        "alerts": alerts,
        "retrieved_sources": retrieved_sources,
        "traceability": traceability_bundle(verification_traces),
        "summary": (
            _resumen_rag(score_rag, semaforo_rag, articulos_total,
                         normativa_no_verificable, normativa_refutada)
            + " · "
            + _resumen_sjf(score_sjf, semaforo_sjf, tesis_total_invocadas, tesis_ok,
                           tesis_mismatch, tesis_no_encontradas, tesis_parciales,
                           tesis_superadas)
            + f" · Veredicto: {veredicto['semaforo']} {veredicto['razon']}"
        ),
    }
    if corpus_warning:
        result["corpus_warning"] = corpus_warning
    return result


# ─────────────────────────────────────────
# CONSULTA (ruta ``query``) — rama fix/vvca-query-vigencia
# ─────────────────────────────────────────

# ⚪ en una consulta: pasaje de contexto o poco parecido; no es un veredicto (ni 🟢 ni 🔴).
SEMAFORO_CONTEXTO = "⚪"


def _texto_de_cita(texto: str, law: Optional[str], ley_resuelta: Optional[str]) -> str:
    """El texto que se audita por los artículos nombrados en una consulta: el mismo o, si no
    nombra ley y se pidió ``--law``, con esa ley al lado ("Art. 109" + "cnpp")."""
    if not ley_resuelta or not law:
        return texto
    if any(ref.get("source_file") for ref in extract_references(texto)):
        return texto
    return f"{texto.rstrip().rstrip('.')} {law.strip()}"


def _encabezados_literales(collection, fuente: str, articulos: List[str],
                           citados: List[Dict]) -> List[Dict]:
    """Respaldo de la consulta (caso art. 294 CPCJ, 07-jul-2026): el encabezado AUTÉNTICO de un
    artículo nombrado que ``audit`` no ubicó ni acreditó inexistente, hallado por escaneo
    literal de la ley. 🟡: falta la verificación completa (derogación, ubicación, vigencia)."""
    hallados: List[Dict] = []
    for articulo in articulos:
        resuelto = any(
            c["source"] == fuente and c.get("articulo") == articulo and (
                c["semaforo"] == "🔴"
                or c.get("vvca", {}).get("explicabilidad", {}).get("encabezado_articulo")
            )
            for c in citados
        )
        if resuelto:
            continue
        for hit in exact_article_chunks(collection, fuente, articulo):
            if encabezado_autentico(hit["snippet"], articulo):
                hallados.append({
                    "score": None,
                    "semaforo": "🟡",
                    "source": hit["source"],
                    "page": hit["page"],
                    "snippet": hit["snippet"],
                    "match": "literal",
                    "articulo": articulo,
                    "detalle": (
                        "encabezado auténtico del artículo hallado por escaneo literal del "
                        "índice; la auditoría no lo ubicó: cotéjalo (derogación, vigencia) antes "
                        "de citarlo"
                    ),
                })
    return hallados


def consultar_corpus(texto: str, n: int = 5, law: Optional[str] = None, *, collection,
                     encode: Callable[[str], List[float]]) -> List[Dict]:
    """Búsqueda en el corpus sin 🟢 por similitud (rama fix/vvca-query-vigencia).

    Antes cada pasaje llevaba el semáforo de su PARECIDO con la consulta y el respaldo literal
    daba 🟢 100 a cualquier encabezado hallado: "artículo 750 de la Ley de Amparo" (inexistente)
    salía 🟢 87 con el «Artículo 5o», un artículo derogado 🟢 100 y una ley desactualizada 🟢.

    - ``articulo_citado``: cada artículo nombrado recibe el veredicto de ``audit`` (misma cita,
      mismo semáforo y su explicación en ``detalle``).
    - ``contexto``: con artículos nombrados, los pasajes semánticos van con ⚪: se parecen a la
      consulta, no son el artículo citado (el pasaje que ``audit`` ya mostró no se repite).
    - ``semantico``: sin artículo nombrado, el semáforo mide el parecido (🟢 ≥ 85), nunca 🔴
      (poco parecido no refuta nada: ⚪), y el pasaje de una ley cuya versión indexada no es la
      vigente no sale 🟢.
    - ``literal``: ver ``_encabezados_literales``.

    Costuras de prueba como las de ``audit``: ``collection`` y ``encode`` inyectados.
    """
    ley_resuelta = resolve_law_alias(law) if law else None
    resultados = collection.query(
        query_embeddings=[encode(normalize_legal_text(texto))],
        n_results=n,
        where={"source": ley_resuelta} if ley_resuelta else None,
        include=["documents", "metadatas", "distances"],
    )
    reporte, _ = _reporte_vigencia()
    fragmentos_por_fuente: Dict[str, Optional[int]] = {}

    def vigencia_de(fuente: str) -> Optional[Dict]:
        if reporte is None or not fila_de(reporte, fuente):
            return None
        return vigencia_de_fuente(
            reporte, fuente, _fragmentos_de(fuente, collection, fragmentos_por_fuente)
        )

    articulos = extract_article_numbers(texto)
    citados: List[Dict] = []
    if articulos:
        auditoria = audit(_texto_de_cita(texto, law, ley_resuelta), allow_incomplete_corpus=True,
                          collection=collection, encode=encode)
        for fuente_auditada in auditoria.get("retrieved_sources", []):
            if fuente_auditada.get("ref_type") != "normativa":
                continue
            vvca = fuente_auditada.get("vvca", {})
            citados.append({
                "score": vvca.get("score"),
                "semaforo": vvca.get("semaforo"),
                "source": fuente_auditada.get("source_file"),
                "page": fuente_auditada.get("page"),
                "snippet": (fuente_auditada.get("retrieved_text_full") or "").strip(),
                "match": "articulo_citado",
                "referencia": fuente_auditada.get("reference"),
                "articulo": fuente_auditada.get("article"),
                "detalle": vvca.get("V_verificacion", ""),
                "vvca": vvca,
            })
        if ley_resuelta:
            citados += _encabezados_literales(collection, ley_resuelta, articulos, citados)

    vistos = {c["snippet"] for c in citados}
    pasajes: List[Dict] = []
    for documento, metadata, distancia in zip(
        (resultados.get("documents") or [[]])[0] or [],
        (resultados.get("metadatas") or [[]])[0] or [],
        (resultados.get("distances") or [[]])[0] or [],
    ):
        snippet = (documento or "").strip()
        if snippet in vistos:
            continue
        metadata = metadata or {}
        fuente = metadata.get("source", "?")
        score = round((1 - distancia) * 100)
        if articulos:
            semaforo, match = SEMAFORO_CONTEXTO, "contexto"
            detalle = "pasaje parecido a la consulta; no es el artículo citado"
        else:
            semaforo, match = vvca_semaforo(score), "semantico"
            detalle = f"parecido con la consulta: {score} (no es un veredicto)"
            if semaforo == "🔴":
                semaforo = SEMAFORO_CONTEXTO
            vigencia = vigencia_de(fuente)
            if vigencia and vigencia["estado"] == FUENTE_NO_VIGENTE:
                semaforo = "🟡" if semaforo == "🟢" else semaforo
                detalle = f"{detalle}; {vigencia['motivo']}"
        pasajes.append({
            "score": score,
            "semaforo": semaforo,
            "source": fuente,
            "page": metadata.get("page", "?"),
            "snippet": snippet,
            "match": match,
            "detalle": detalle,
        })
    return citados + pasajes


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
        """Búsqueda en el corpus (``consultar_corpus``): un artículo nombrado recibe el veredicto
        de ``audit``; los demás pasajes son contexto, no veredictos.

        Returns a list of result dictionaries. If json_output is True, prints JSON.
        """
        self._ensure_loaded()
        result_list = consultar_corpus(text, n=n, law=law, collection=self._collection,
                                       encode=encode_query)
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
  python OpenNotebook.py ingest --directory /ruta/pdfs/ --clear      (borra TODA la colección)
  python OpenNotebook.py ingest --directory /ruta/pdfs/ --reingest   (borra TODA la colección)
  python OpenNotebook.py ingest --directory /ruta/pdfs/ --fuente "LEY DE AMPARO.pdf" --simular
  python OpenNotebook.py ingest --directory /ruta/pdfs/ --fuente "LEY DE AMPARO.pdf"
  python OpenNotebook.py audit --text "Art. 247 CPF establece..."
  python OpenNotebook.py audit --file borrador.md --verbose
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    # Comando: ingest
    ingest_parser = subparsers.add_parser("ingest", help="Indexar PDFs en ChromaDB")
    ingest_parser.add_argument(
        "--directory",
        help="Carpeta con PDFs legales (obligatoria salvo con --restaurar)"
    )
    ingest_parser.add_argument(
        "--clear", action="store_true",
        help="Borrar la colección ENTERA (todas las fuentes) antes de ingestar"
    )
    ingest_parser.add_argument(
        "--reingest", action="store_true",
        help="Reindexar todo: borra la colección ENTERA (todas las fuentes) antes de ingestar"
    )
    ingest_parser.add_argument(
        "--fuente", action="append", metavar="ARCHIVO.pdf",
        help="Re-ingestar SOLO esta fuente: nombre exacto del PDF en --directory (repetible). "
             "Borra solo sus fragmentos (source == ARCHIVO.pdf), nunca la colección"
    )
    ingest_parser.add_argument(
        "--simular", action="store_true",
        help="Con --fuente: informa fragmentos, etiquetas y cobertura antes/después sin escribir"
    )
    ingest_parser.add_argument(
        "--json", action="store_true",
        help="Con --fuente: emitir también el informe en JSON"
    )
    ingest_parser.add_argument(
        "--identidad-confirmada", action="append", metavar="ARCHIVO.pdf",
        help="Con --fuente ARCHIVO.pdf: el operador confirma que es el mismo ordenamiento aunque "
             "el título de la primera página difiera del indexado (p. ej. el PDF oficial antepone "
             "el preámbulo del decreto); la identidad la decide solo el contenido, con el mismo "
             "umbral (repetible)"
    )
    ingest_parser.add_argument(
        "--respaldos", metavar="CARPETA",
        help="Con --fuente/--restaurar: carpeta de los respaldos durables de cada fuente (fuera "
             "del repositorio y del índice; por omisión $ITOSTURRE_RESPALDOS_REINGESTA o "
             "~/.itosturre/respaldos_reingesta)"
    )
    ingest_parser.add_argument(
        "--retirar", action="append", metavar="ARCHIVO.pdf",
        help="Sacar del índice TODOS los fragmentos de esta fuente (repetible), con respaldo "
             "durable (se repone con --restaurar). Solo fuentes que LAW_SOURCE_MAP ya no "
             "resuelve, p. ej. una ley abrogada; no exige --directory"
    )
    ingest_parser.add_argument(
        "--restaurar", metavar="RESPALDO.json",
        help="Reponer en el índice la fuente de un respaldo durable (lo valida, respalda el "
             "estado actual de la fuente y verifica textos, metadatos y vectores)"
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
        print(f"\n🔍 Búsqueda: \"{args.texto}\" — {len(result_list)} resultados")
        etiquetas = {
            "articulo_citado": " [artículo citado · veredicto VVCA]",
            "literal": " [encabezado por escaneo literal · sin verificación completa]",
            "contexto": " [contexto · no es el artículo citado]",
        }
        for r in result_list:
            puntaje = f"Score {r['score']} | " if r.get("score") is not None else ""
            print(f"{r['semaforo']} {puntaje}{r['source']} pág.{r['page']}"
                  f"{etiquetas.get(r.get('match'), '')}")
            if r.get("match") in ("articulo_citado", "literal") or (
                    r.get("match") == "semantico" and "; " in r.get("detalle", "")):
                print(f"   ↳ {r['detalle']}")
            print(f"   {r['snippet'][:200]}")
            print()
        print("Semáforo: 🟢🟡🔴 = veredicto VVCA del artículo citado (o parecido con la consulta en "
              "una búsqueda por tema) · ⚪ = contexto, no es un veredicto")
        # Output JSON if requested
        if getattr(args, "json", False):
            print(json.dumps(result_list, ensure_ascii=False, indent=2))

    elif args.command == "ingest":
        setup_logging(args.verbose)
        if not args.restaurar and not args.retirar and not args.directory:
            parser.error("ingest exige --directory (salvo con --restaurar o --retirar)")
        if args.retirar:
            # Retiro de fuentes (10-oct-2026): operación propia, nunca junto con otras.
            if (args.fuente or args.simular or args.json or args.clear or args.reingest
                    or args.restaurar or args.identidad_confirmada):
                parser.error("--retirar no se combina con --fuente, --simular, --json, "
                             "--restaurar, --clear, --reingest ni --identidad-confirmada")
            try:
                informes = retirar_fuentes(args.retirar, respaldos_dir=args.respaldos)
            except ValueError as exc:
                print(f"❌ {exc}", file=sys.stderr)
                sys.exit(2)
            except ReingestaFallida as exc:
                print(f"❌ {exc}", file=sys.stderr)
                sys.exit(1)
            for informe in informes:
                print(f"✅ {informe['fuente']}: {informe['fragmentos']} fragmentos retirados del "
                      f"índice; respaldo durable: {informe['respaldo']} (se repone con "
                      f"--restaurar)")
        elif args.restaurar:
            if (args.fuente or args.simular or args.clear or args.reingest
                    or args.identidad_confirmada):
                parser.error("--restaurar no se combina con --fuente, --simular, --clear, "
                             "--reingest ni --identidad-confirmada")
            try:
                resultado = restaurar_respaldo(args.restaurar, respaldos_dir=args.respaldos)
            except ValueError as exc:
                print(f"❌ {exc}", file=sys.stderr)
                sys.exit(2)
            except ReingestaFallida as exc:
                print(f"❌ {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"✅ {resultado['fuente']}: {resultado['fragmentos']} fragmentos restaurados; "
                  f"estado anterior respaldado en {resultado['respaldo_previo']}")
        elif args.fuente or args.simular or args.json or args.identidad_confirmada:
            # Re-ingesta por fuente (4-oct-2026): nunca junto con los borrados de la colección.
            # --identidad-confirmada sin --fuente no puede caer en la ingesta de siempre.
            if args.clear or args.reingest:
                parser.error(
                    "--fuente/--simular no se combinan con --clear ni --reingest "
                    "(estos borran la colección entera)"
                )
            if not args.fuente:
                parser.error(
                    "--simular, --json e --identidad-confirmada exigen al menos una --fuente "
                    "(nombre exacto del PDF)"
                )
            opciones = {"identidad_confirmada": args.identidad_confirmada} \
                if args.identidad_confirmada else {}
            try:
                informes = reingestar_fuentes(args.directory, args.fuente, simular=args.simular,
                                              respaldos_dir=args.respaldos, **opciones)
            except ValueError as exc:
                print(f"❌ {exc}", file=sys.stderr)
                sys.exit(2)
            except ReingestaFallida as exc:
                print(f"❌ {exc}", file=sys.stderr)
                sys.exit(1)
            print(formato_informe_reingesta(informes))
            if args.json:
                print(json.dumps(informes, ensure_ascii=False, indent=2))
        else:
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
