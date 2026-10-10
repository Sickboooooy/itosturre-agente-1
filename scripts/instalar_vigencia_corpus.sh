#!/usr/bin/env bash
# instalar_vigencia_corpus.sh — agenda la verificación de vigencia del corpus RAG cada 2 meses (macOS).
#
# Instala un LaunchAgent que dispara scripts/vigencia_corpus.py a diario y al iniciar sesión;
# el script (--si-toca) solo verifica de verdad cuando pasaron ≥ 60 días desde la última
# verificación COMPLETA. Se hace así, y no con un calendario "día 1 de cada dos meses", porque
# launchd no recupera una cita perdida si la Mac estaba apagada: con el disparo diario el ciclo
# se cumple el primer día que la Mac esté encendida, y si la red o un portal oficial fallan,
# reintenta al día siguiente. Cada disparo que no toca termina en milisegundos y sin red.
#
# Uso:
#   bash scripts/instalar_vigencia_corpus.sh                # instala o actualiza la agenda
#   bash scripts/instalar_vigencia_corpus.sh --estado       # ¿cargada? último veredicto y log
#   bash scripts/instalar_vigencia_corpus.sh --ahora        # verifica ya, con la config instalada
#   bash scripts/instalar_vigencia_corpus.sh --desinstalar
#
# Variables opcionales al instalar:
#   CHROMA_PATH              índice a vigilar (default: <repo>/chroma_db)
#   ITOS_CORPUS_DIR          carpeta de PDFs (default: carpeta 'corpus' junto al índice)
#   ITOS_VIGENCIA_CADA_DIAS  periodo en días (default: 60)
#   ITOS_VIGENCIA_HORA       hora del disparo diario, 0-23 (default: 10)
#   ITOS_PYTHON              python3 ≥ 3.11 a usar; basta la librería estándar (default: python3 del PATH)
set -euo pipefail

LABEL="com.itosturre.vigencia-corpus"  # misma convención que com.itosturre.bridge / .ngrok
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO/scripts/vigencia_corpus.py"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/itosturre-vigencia-corpus.log"
DOMINIO="gui/$(id -u)"

xml() {  # escapa &, < y > para el plist
  printf '%s' "$1" | sed -e 's/&/\&amp;/g' -e 's/</\&lt;/g' -e 's/>/\&gt;/g'
}

del_plist() {  # del_plist <variable de EnvironmentVariables>
  /usr/bin/plutil -extract "EnvironmentVariables.$1" raw -o - "$PLIST" 2>/dev/null || true
}

case "${1:-}" in
  --desinstalar)
    launchctl bootout "$DOMINIO/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "✅ Agenda eliminada ($LABEL). Los reportes de reportes/vigencia_corpus/ se conservan."
    exit 0
    ;;
  --estado)
    if [ ! -f "$PLIST" ]; then
      echo "⚪ Agenda no instalada. Instálala con: bash scripts/instalar_vigencia_corpus.sh"
      exit 1
    fi
    echo "📅 Agenda: $PLIST"
    if launchctl print "$DOMINIO/$LABEL" >/dev/null 2>&1; then
      launchctl print "$DOMINIO/$LABEL" | grep -E '^[[:space:]]*(state|runs|last exit code) =' | sed -E 's/^[[:space:]]+/   /'
      echo "   (last exit code: 0 = nada desactualizado o no tocaba · 1 = hay leyes desactualizadas · 2 = no se pudo verificar todo)"
    else
      echo "   ⚠️  El plist existe pero launchd no lo tiene cargado: vuelve a instalar."
    fi
    echo "   Índice vigilado: $(del_plist CHROMA_PATH) · cada $(del_plist ITOS_VIGENCIA_CADA_DIAS) días"
    estado="$REPO/reportes/vigencia_corpus/estado.json"
    if [ -f "$estado" ]; then echo "── estado.json ──"; cat "$estado"; echo; fi
    if [ -f "$LOG" ]; then echo "── últimas líneas de $LOG ──"; tail -n 8 "$LOG"; fi
    exit 0
    ;;
  --ahora)
    [ -f "$PLIST" ] || { echo "❌ Agenda no instalada. Corre primero: bash scripts/instalar_vigencia_corpus.sh"; exit 1; }
    CHROMA_PATH="$(del_plist CHROMA_PATH)" ITOS_CORPUS_DIR="$(del_plist ITOS_CORPUS_DIR)" \
      "$(del_plist ITOS_PYTHON)" "$SCRIPT" --notificar
    exit $?
    ;;
  "") ;;
  *)
    echo "Uso: bash scripts/instalar_vigencia_corpus.sh [--estado|--ahora|--desinstalar]"
    exit 1
    ;;
esac

[ "$(uname -s)" = "Darwin" ] || { echo "❌ La agenda usa launchd (macOS). En Linux usa cron: 0 10 * * * python3 $SCRIPT --si-toca"; exit 1; }
[ -f "$SCRIPT" ] || { echo "❌ No existe $SCRIPT"; exit 1; }

PY="${ITOS_PYTHON:-$(command -v python3 || true)}"
if [ -z "$PY" ] || ! "$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
  echo "❌ Necesito python3 ≥ 3.11, la versión de la CI (define ITOS_PYTHON=/ruta/a/python3)."
  exit 1
fi
CHROMA="${CHROMA_PATH:-$REPO/chroma_db}"
[ -d "$CHROMA" ] && CHROMA="$(cd "$CHROMA" && pwd)"
CORPUS="${ITOS_CORPUS_DIR:-$(dirname "$CHROMA")/corpus}"
CADA="${ITOS_VIGENCIA_CADA_DIAS:-60}"
HORA="${ITOS_VIGENCIA_HORA:-10}"
if [ ! -f "$CHROMA/chroma.sqlite3" ]; then
  echo "⚠️  No hay índice en $CHROMA (falta chroma.sqlite3). La agenda se instala, pero cada"
  echo "   corrida dirá 🟡 NO SE PUDO VERIFICAR hasta que exista. Para vigilar otro índice:"
  echo "   CHROMA_PATH=/ruta/al/chroma_db bash scripts/instalar_vigencia_corpus.sh"
fi

# Si el script desaparece (p. ej. cambiaste a una rama sin fusionar), el aviso llega igual.
# $0 = ruta del script (último argumento del plist); $ITOS_PYTHON viene de EnvironmentVariables.
CMD='if [ -f "$0" ]; then exec "$ITOS_PYTHON" "$0" --si-toca --notificar; fi
echo "[vigencia] $(date "+%F %T") no existe $0: ¿cambiaste a una rama sin fusionar?"
osascript -e "display notification \"No encuentro scripts/vigencia_corpus.py: ¿cambiaste a una rama sin fusionar?\" with title \"Itosturre · Vigencia del corpus\""
exit 2'

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>-c</string>
    <string>$(xml "$CMD")</string>
    <string>$(xml "$SCRIPT")</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ITOS_PYTHON</key>
    <string>$(xml "$PY")</string>
    <key>CHROMA_PATH</key>
    <string>$(xml "$CHROMA")</string>
    <key>ITOS_CORPUS_DIR</key>
    <string>$(xml "$CORPUS")</string>
    <key>ITOS_VIGENCIA_CADA_DIAS</key>
    <string>$CADA</string>
    <key>PATH</key>
    <string>/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin</string>
  </dict>
  <key>WorkingDirectory</key>
  <string>$(xml "$REPO")</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$HORA</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>RunAtLoad</key>
  <true/>
  <key>ProcessType</key>
  <string>Background</string>
  <key>StandardOutPath</key>
  <string>$(xml "$LOG")</string>
  <key>StandardErrorPath</key>
  <string>$(xml "$LOG")</string>
</dict>
</plist>
EOF
/usr/bin/plutil -lint "$PLIST" >/dev/null

launchctl bootout "$DOMINIO/$LABEL" 2>/dev/null || true
launchctl bootstrap "$DOMINIO" "$PLIST"
launchctl enable "$DOMINIO/$LABEL" 2>/dev/null || true

echo "✅ Agenda instalada: $LABEL"
echo "   Revisa a diario a las $HORA:00 (y al iniciar sesión); verifica de verdad cada $CADA días."
echo "   Índice : $CHROMA"
echo "   Corpus : $CORPUS"
echo "   Python : $PY"
echo "   Reporte: $REPO/reportes/vigencia_corpus/  ·  Log: $LOG"
echo "   Estado: bash scripts/instalar_vigencia_corpus.sh --estado"
echo "   Si macOS avisa «Elemento de inicio añadido», es esta agenda (Ajustes › General › Ítems de inicio)."
