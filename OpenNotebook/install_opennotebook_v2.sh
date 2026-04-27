#!/bin/bash
set -e

# OpenNotebook v2.0 — Script de instalación automática
# Uso: bash /home/licjo/install_opennotebook_v2.sh

echo "═══════════════════════════════════════════════════════════════════"
echo "  🚀 Instalador OpenNotebook v2.0"
echo "═══════════════════════════════════════════════════════════════════"
echo ""

# Paso 1: Verificar venv
echo "Step 1️⃣  Verificando venv..."
if [ ! -d "/home/licjo/venv" ]; then
    echo "❌ venv no encontrado en /home/licjo/venv"
    exit 1
fi
echo "✅ venv activo"
echo ""

# Paso 2: Activar venv
echo "Step 2️⃣  Activando venv..."
source /home/licjo/venv/bin/activate
echo "✅ venv activado"
echo ""

# Paso 3: Instalar dependencias nuevas
echo "Step 3️⃣  Instalando dependencias nuevas..."
pip install python-dotenv==1.0.1 -q
echo "✅ Dependencias instaladas"
echo ""

# Paso 4: Crear .env
echo "Step 4️⃣  Creando .env..."
if [ ! -f "/home/licjo/.env" ]; then
    cp /home/licjo/.env.example /home/licjo/.env
    echo "✅ .env creado (defaults)"
else
    echo "⚠️  .env ya existe (no sobrescrito)"
fi
echo ""

# Paso 5: Backup de v1.0
echo "Step 5️⃣  Backup de OpenNotebook.py..."
if [ -f "/home/licjo/OpenNotebook.py" ]; then
    cp /home/licjo/OpenNotebook.py /home/licjo/OpenNotebook_v1.0.backup
    echo "✅ Backup: /home/licjo/OpenNotebook_v1.0.backup"
else
    echo "⚠️  OpenNotebook.py no encontrado (primera instalación)"
fi
echo ""

# Paso 6: Validación rápida (auditoría de test)
echo "Step 6️⃣  Validación rápida..."
test_text="El artículo 247 del Código Penal Federal establece que..."
result=$(python /home/licjo/OpenNotebook_v2.0.py audit --text "$test_text" 2>&1)
if echo "$result" | grep -q '"status": "ok"'; then
    echo "✅ OpenNotebook_v2.0.py funcional"
else
    echo "❌ Error en validación"
    echo "$result"
    exit 1
fi
echo ""

# Paso 7: Preguntar si reemplazar v1.0
echo "Step 7️⃣  ¿Reemplazar OpenNotebook.py v1.0 con v2.0?"
echo ""
echo "Opciones:"
echo "  [1] Reemplazar ahora (producción)"
echo "  [2] Mantener ambas (safe)"
echo "  [0] Cancelar"
echo ""
read -p "Opción [0-2]: " choice

case $choice in
    1)
        echo "🔄 Reemplazando v1.0 con v2.0..."
        mv /home/licjo/OpenNotebook_v2.0.py /home/licjo/OpenNotebook.py
        echo "✅ OpenNotebook.py actualizado a v2.0"
        ;;
    2)
        echo "✅ Mantuviendo ambas versiones:"
        echo "   - v1.0: /home/licjo/OpenNotebook_v1.0.backup"
        echo "   - v2.0: /home/licjo/OpenNotebook_v2.0.py"
        ;;
    0)
        echo "❌ Instalación cancelada"
        exit 0
        ;;
    *)
        echo "❌ Opción inválida"
        exit 1
        ;;
esac
echo ""

# Paso 8: Re-ingestión (opcional)
echo "Step 8️⃣  ¿Re-ingestionar corpus completo?"
echo "     (Recalcula embeddings con metadatos de página)"
echo ""
read -p "¿Reingestionar? [s/N]: " reingest
if [ "$reingest" = "s" ] || [ "$reingest" = "S" ]; then
    echo "⏳ Re-ingestionando (~5-10 min)..."
    if [ -d "/home/licjo/corpus_legal" ]; then
        python /home/licjo/OpenNotebook.py ingest --directory /home/licjo/corpus_legal --reingest --verbose
        echo "✅ Re-ingestión completada"
    else
        echo "❌ No se encontró /home/licjo/corpus_legal"
        echo "   Saltando re-ingestión"
    fi
else
    echo "⏭️  Re-ingestión saltada"
fi
echo ""

# Resumen final
echo "═══════════════════════════════════════════════════════════════════"
echo "  ✅ INSTALACIÓN COMPLETADA"
echo "═══════════════════════════════════════════════════════════════════"
echo ""
echo "Próximos pasos:"
echo "  1. Leer: /home/licjo/CAMBIOS_v2.0.md"
echo "  2. Editar: /home/licjo/.env (si necesitas rutas diferentes)"
echo "  3. Probar: python OpenNotebook.py audit --file borrador.md --verbose"
echo ""
echo "Comandos disponibles:"
echo "  python OpenNotebook.py ingest --directory /pdfs/ --clear"
echo "  python OpenNotebook.py ingest --directory /pdfs/ --reingest"
echo "  python OpenNotebook.py audit --file borrador.md"
echo "  python OpenNotebook.py audit --file borrador.md --verbose"
echo ""
echo "Documentación:"
echo "  - CAMBIOS_v2.0.md (técnico, detallado)"
echo "  - RESUMEN_CAMBIOS_v2.0.txt (ejecutivo, rápido)"
echo ""
echo "═══════════════════════════════════════════════════════════════════"
