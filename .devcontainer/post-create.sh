#!/usr/bin/env bash
# post-create.sh — se ejecuta UNA VEZ al crear el contenedor.
# Instala browsers de Playwright y dependencias del scraper.
set -euo pipefail

echo ""
echo "══════════════════════════════════════════════════"
echo "  🏛️  Itosturre Legal Agent — Setup Dev Container"
echo "══════════════════════════════════════════════════"
echo ""

# ── 1. Playwright: instalar Chromium + sus dependencias de sistema ─────────────
echo "▶ Instalando Playwright Chromium..."
python -m playwright install chromium
python -m playwright install-deps chromium
echo "  ✅ Playwright Chromium listo"
echo ""

# ── 2. Node packages del scraper SJF ─────────────────────────────────────────
echo "▶ Instalando dependencias Node.js del scraper..."
cd /workspaces/itosturre-agente/services/itosturre-scraper
npm install --prefer-offline 2>/dev/null || npm install
cd /workspaces/itosturre-agente
echo "  ✅ Scraper SJF listo (Playwright TS + ts-node)"
echo ""

# ── 3. Credenciales Telegram ──────────────────────────────────────────────────
# El archivo .env con TELEGRAM_BOT_TOKEN vive en ~/.claude/channels/telegram/.env
# en el host Windows. En el contenedor NO existe ese path.
# Opciones:
#   A) Copiar manualmente: cp /mnt/c/Users/licjo/.claude/channels/telegram/.env ~/.claude/channels/telegram/.env
#   B) Añadir las vars al .env del proyecto (ignorado por git)
echo "▶ Verificando credenciales Telegram..."
TELE_ENV="$HOME/.claude/channels/telegram/.env"
if [ -f "$TELE_ENV" ]; then
    echo "  ✅ Credenciales Telegram encontradas en $TELE_ENV"
else
    mkdir -p "$HOME/.claude/channels/telegram"
    cat > "$TELE_ENV" << 'ENVTEMPLATE'
# Copia tus valores reales aquí o ejecuta:
#   cp /mnt/c/Users/licjo/.claude/channels/telegram/.env ~/.claude/channels/telegram/.env
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
GROQ_API_KEY=
ENVTEMPLATE
    echo "  ⚠️  Plantilla Telegram creada en $TELE_ENV"
    echo "     → Copia tus credenciales: cp /mnt/c/Users/licjo/.claude/channels/telegram/.env ~/.claude/channels/telegram/.env"
fi
echo ""

# ── 4. Verificar corpus ChromaDB ─────────────────────────────────────────────
echo "▶ Verificando corpus ChromaDB..."
if [ -f "/workspaces/itosturre-agente/chroma_db/chroma.sqlite3" ]; then
    SIZE=$(du -sh /workspaces/itosturre-agente/chroma_db/chroma.sqlite3 | cut -f1)
    echo "  ✅ corpus OK — chroma.sqlite3 ($SIZE)"
else
    echo "  ⚠️  chroma_db no encontrado."
    echo "     → Ejecuta: python OpenNotebook.py ingest --directory <ruta_pdfs>"
fi
echo ""

# ── 5. Health check rápido ───────────────────────────────────────────────────
echo "▶ Health check del stack..."
python -c "
import chromadb, sentence_transformers, playwright, docx
print('  ✅ chromadb', chromadb.__version__)
print('  ✅ sentence-transformers', sentence_transformers.__version__)
print('  ✅ playwright', playwright.__version__)
print('  ✅ python-docx OK')
"
echo ""

echo "══════════════════════════════════════════════════"
echo "  ✅ Dev Container listo. Happy coding, Fabián."
echo ""
echo "  Comandos principales:"
echo "    python OpenNotebook.py query \"tu consulta\" --n 5"
echo "    python vvca_full.py --caso auditorias/<slug> --borrador <archivo.md>"
echo "    python scripts/check_corpus.py"
echo "══════════════════════════════════════════════════"
echo ""
