#!/usr/bin/env bash
# bootstrap_corpus.sh — deja el RAG legal funcionando en un comando para un clon nuevo.
#
# Descarga el corpus legal de la carpeta pública de Google Drive, lo coloca en corpus/,
# lo indexa en ChromaDB y verifica la cobertura. Pensado para cualquier IDE/agente que
# clone el repo (el corpus y chroma_db/ NO se versionan).
#
# Uso:   bash scripts/bootstrap_corpus.sh
# Requiere: python (con deps de requirements.txt). gdown se instala si falta.
set -euo pipefail

# Carpeta pública de Drive con los PDFs del corpus legal Itosturre.
DRIVE_URL="${ITOS_CORPUS_DRIVE_URL:-https://drive.google.com/drive/folders/1VS_LwlQXMCLfh5YA_nnxXzzQ_xuHkdtf}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CORPUS_DIR="$REPO/corpus"
PY="${PYTHON:-python}"

echo "📥 Descargando corpus legal desde Drive..."
"$PY" -c "import gdown" 2>/dev/null || "$PY" -m pip install -q gdown

mkdir -p "$CORPUS_DIR"
# gdown --folder soporta hasta 50 archivos por carpeta (el corpus son ~44).
if ! "$PY" -m gdown --folder "$DRIVE_URL" -O "$CORPUS_DIR"; then
  echo "⚠️  gdown no pudo bajar TODA la carpeta (límite de accesos de Drive es lo más común)."
  echo "   Reintenta en unos minutos, o descarga manualmente desde:"
  echo "   $DRIVE_URL"
fi

# gdown crea un subdirectorio con el nombre de la carpeta de Drive; aplanar a corpus/.
find "$CORPUS_DIR" -mindepth 2 -name "*.pdf" -exec mv -n {} "$CORPUS_DIR/" \; 2>/dev/null || true
find "$CORPUS_DIR" -mindepth 1 -type d -empty -delete 2>/dev/null || true

PDF_COUNT=$(find "$CORPUS_DIR" -maxdepth 1 -name "*.pdf" | wc -l | tr -d ' ')
echo "📚 PDFs en corpus/: $PDF_COUNT"
if [ "$PDF_COUNT" -eq 0 ]; then
  echo "❌ No se descargó ningún PDF. Revisa el enlace/permiso del Drive y reintenta."
  exit 1
fi

echo "🔧 Indexando en ChromaDB (puede tardar varios minutos la primera vez)..."
# Forzar INGEST_ALLOWED_BASE al repo para que corpus/ pase el guard aunque el .env
# local apunte a otra base. load_dotenv(override=False) respeta esta var del entorno.
# Código 3 = MIGRACIÓN PENDIENTE (4-oct-2026): fuentes ya indexadas con otra fragmentación que
# la ingesta omitió sin mezclar; el comando --fuente exacto quedó impreso arriba.
MIGRACION_PENDIENTE=0
set +e
INGEST_ALLOWED_BASE="$REPO" "$PY" "$REPO/OpenNotebook.py" ingest --directory "$CORPUS_DIR"
INGEST_RC=$?
set -e
if [ "$INGEST_RC" -eq 3 ]; then
  MIGRACION_PENDIENTE=1
elif [ "$INGEST_RC" -ne 0 ]; then
  echo "❌ La ingesta falló (código $INGEST_RC)."
  exit "$INGEST_RC"
fi

echo "✅ Verificando cobertura del corpus..."
if "$PY" "$REPO/scripts/check_corpus.py"; then
  if [ "$MIGRACION_PENDIENTE" -eq 1 ]; then
    echo "⚠️  Corpus indexado con MIGRACIÓN PENDIENTE: hay fuentes con la fragmentación anterior."
    echo "   Re-ingéstalas con el comando --fuente que imprimió la ingesta (arriba) antes de auditar."
    exit 3
  fi
  echo "🟢 Corpus listo. Ya puedes auditar: python OpenNotebook.py audit --file <archivo.md>"
else
  echo "⚠️  Cobertura incompleta — revisa los faltantes arriba (¿algún PDF no bajó del Drive?)."
  exit 1
fi
