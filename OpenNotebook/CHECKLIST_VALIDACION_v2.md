# OpenNotebook v2.0 — Checklist de Validación

**Antes de reemplazar v1.0 con v2.0, ejecuta este checklist.**

---

## 📋 Pre-requisitos

- [ ] Python 3.9+ (`python --version`)
- [ ] venv activo: `source /home/licjo/venv/bin/activate`
- [ ] ChromaDB populado (38 PDFs)
- [ ] Acceso a `/home/licjo/chroma_db` 
- [ ] Acceso a `/home/licjo/jurisprudencia`

---

## 🔧 Instalación

### 1. Dependencias
```bash
source /home/licjo/venv/bin/activate
pip install python-dotenv==1.0.1
```
- [ ] Sin errores de instalación
- [ ] `pip list | grep python-dotenv`

### 2. Archivo .env
```bash
cp /home/licjo/.env.example /home/licjo/.env
cat /home/licjo/.env
```
- [ ] .env existe en `/home/licjo/.env`
- [ ] Contiene 3 variables: CHROMA_PATH, JURISPRUDENCIA_PATH, COSINE_THRESHOLD
- [ ] Rutas correctas

### 3. Permisos de script
```bash
chmod +x /home/licjo/install_opennotebook_v2.sh
ls -lh /home/licjo/install_opennotebook_v2.sh
```
- [ ] Script ejecutable (rwxr-xr-x)

---

## ✅ Validación funcional

### Test 1: Auditoría simple
```bash
python /home/licjo/OpenNotebook_v2.0.py audit --text "El artículo 247 del CPF establece que..."
```
**Esperado:**
```json
{
  "status": "ok",
  "total_references_found": 1,
  "verified": 1,
  "alerts_count": 0,
  "cosine_threshold": 0.5,
  ...
}
```

- [ ] Status = "ok"
- [ ] JSON válido (sin errores de parsing)
- [ ] `total_references_found` > 0
- [ ] `cosine_threshold` = 0.5 (o tu valor en .env)

### Test 2: Auditoría con archivo
Crea un archivo de test:
```bash
cat > /tmp/test_borrador.md << 'EOF'
# Borrador test

De conformidad con los artículos 247 del Código Penal Federal y 50 del Código Civil Federal, se establece que...

Asimismo, el Código Fiscal de la Federación en su artículo 1 dispone...
EOF
```

Ejecuta:
```bash
python /home/licjo/OpenNotebook_v2.0.py audit --file /tmp/test_borrador.md
```

**Esperado:**
- [ ] 2-3 referencias detectadas (`total_references_found`)
- [ ] Mínimo 1 verificada (`verified` > 0)
- [ ] JSON estructurado con `alerts` y `retrieved_sources`

### Test 3: Auditoría con --verbose
```bash
python /home/licjo/OpenNotebook_v2.0.py audit --file /tmp/test_borrador.md --verbose
```

**Esperado:**
- [ ] Logs con timestamps: `2026-04-26 20:15:30 [DEBUG] ...`
- [ ] Salida más detallada que sin --verbose
- [ ] Sin errores en logs

### Test 4: Ingestión --clear (PELIGRO: borra colección)

**⚠️ ADVERTENCIA:** Este test borra la colección. Solo con 1-2 PDFs de test.

Crea carpeta de test:
```bash
mkdir -p /tmp/pdfs_test
# Copiar 1 PDF pequeño de test
cp /home/licjo/corpus_legal/CONSTITUCION*.pdf /tmp/pdfs_test/
```

Ejecuta:
```bash
python /home/licjo/OpenNotebook_v2.0.py ingest --directory /tmp/pdfs_test --clear --verbose
```

**Esperado:**
- [ ] Logs muestran "🗑️  Colección borrada."
- [ ] Luego "Indexado correctamente"
- [ ] Colección recreada vacía → llenada con nuevo PDF

### Test 5: Metadatos con página
```bash
python /home/licjo/OpenNotebook_v2.0.py audit --file /tmp/test_borrador.md
```

En la salida JSON, verifica `retrieved_sources`:
```json
{
  "retrieved_sources": [
    {
      "reference": "Art. 247 CPF",
      "law": "Código Penal Federal",
      "article": "247",
      "source_file": "CODIGO PENAL FEDERAL 2025.pdf",
      "page": "123",         ← ¡NUEVO EN v2.0!
      "relevance_score": 0.521,
      ...
    }
  ]
}
```

- [ ] Campo `page` presente en `retrieved_sources`
- [ ] Valor razonable (entre 1 y total de páginas del PDF)

---

## 🔍 Validación de calidad

### Test 6: Alucinación detectada
Crea un borrador con cita **falsa**:
```bash
cat > /tmp/fake.md << 'EOF'
El artículo 9999 del Código Imaginario establece que...
EOF
```

```bash
python /home/licjo/OpenNotebook_v2.0.py audit --file /tmp/fake.md
```

**Esperado:**
- [ ] `alerts_count` > 0
- [ ] Alert contiene "ALERTA CRÍTICA" o "ALERTA ALTA"
- [ ] Menciona "alucinación"

### Test 7: Comparar scores entre v1.0 y v2.0

Mismo borrador en ambas versiones:
```bash
python /home/licjo/OpenNotebook.py audit --file /tmp/test_borrador.md > /tmp/v1_output.json
python /home/licjo/OpenNotebook_v2.0.py audit --file /tmp/test_borrador.md > /tmp/v2_output.json

diff -u /tmp/v1_output.json /tmp/v2_output.json
```

**Esperado:**
- [ ] `verified` puede ser diferente (umbral más estricto en v2.0)
- [ ] `alerts_count` posiblemente mayor en v2.0 (más conservador)
- [ ] Ambas JSON válidas
- [ ] Mismas referencias detectadas (`total_references_found` igual)

---

## 🚀 Instalación automática (opcional)

Alterna: ejecutar script automático
```bash
bash /home/licjo/install_opennotebook_v2.sh
```

Checklist del script:
- [ ] Detecta venv
- [ ] Instala dependencias
- [ ] Crea .env
- [ ] Hace backup de v1.0
- [ ] Validación rápida pasa
- [ ] Pregunta si reemplazar
- [ ] Pregunta si re-ingestionar

---

## 📊 Validación de datos (ChromaDB)

### Test 8: Colección después de re-ingesta

Después de un `--reingest` pequeño:
```bash
python << 'EOF'
import chromadb
client = chromadb.PersistentClient(path="/home/licjo/chroma_db")
collection = client.get_collection("corpus_legal_itosturre")
print(f"Total chunks: {collection.count()}")

# Ver un documento aleatorio
results = collection.get(limit=1)
print(f"Metadatos: {results['metadatas'][0]}")
EOF
```

**Esperado:**
- [ ] `Total chunks` > 0
- [ ] Metadatos incluyen: `source`, `law`, `article`, `page`, `chunk_index`
- [ ] Campo `page` es string (ej: "123")

### Test 9: Búsqueda por fuente

```bash
python << 'EOF'
import chromadb
client = chromadb.PersistentClient(path="/home/licjo/chroma_db")
collection = client.get_collection("corpus_legal_itosturre")

# Búsqueda con filtro
results = collection.query(
    query_texts=["Artículo 1 Constitución"],
    n_results=1,
    where={"source": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf"}
)
print(f"Resultados: {len(results['documents'][0])}")
print(f"Distancia: {results['distances'][0][0]:.3f}")
EOF
```

- [ ] Búsqueda retorna resultados (len > 0)
- [ ] Distancia es float entre 0.0 y 1.0
- [ ] Sin errores de filtro

---

## 🛡️ Validación de seguridad

### Test 10: Inyección en búsqueda
```bash
python /home/licjo/OpenNotebook_v2.0.py audit --text 'Art. 1; DROP TABLE --' 
```

**Esperado:**
- [ ] Sin errores de SQL/base datos
- [ ] Trata como texto normal
- [ ] No ejecuta comandos

### Test 11: Archivos grandes
```bash
# Crear un borrador grande (~1 MB)
python << 'EOF'
with open("/tmp/large.md", "w") as f:
    for i in range(1000):
        f.write(f"El artículo {i} del CPF establece... " * 100 + "\n")
EOF

python /home/licjo/OpenNotebook_v2.0.py audit --file /tmp/large.md --verbose
```

**Esperado:**
- [ ] Sin timeout
- [ ] Memoria < 2GB
- [ ] JSON válido en salida

---

## 📈 Resumen de validación

**Después de completar todo, marca el estado general:**

| Test | Status | Nota |
|------|--------|------|
| 1. Auditoría simple | ⬜ | |
| 2. Auditoría con archivo | ⬜ | |
| 3. --verbose | ⬜ | |
| 4. --clear | ⬜ | |
| 5. Metadatos página | ⬜ | |
| 6. Alucinación detectada | ⬜ | |
| 7. v1.0 vs v2.0 | ⬜ | |
| 8. ChromaDB metadatos | ⬜ | |
| 9. Búsqueda filtrada | ⬜ | |
| 10. Seguridad inyección | ⬜ | |
| 11. Archivos grandes | ⬜ | |

---

## ✅ Decisión final

Si todos los tests pasan:

### Opción A: Reemplazar v1.0 (PRODUCCIÓN)
```bash
# Backup seguro
cp /home/licjo/OpenNotebook.py /home/licjo/OpenNotebook_v1.0.backup
cp /home/licjo/OpenNotebook_v1.0.backup /media/backup/OpenNotebook_2026-04-26.py  # Backup externo

# Reemplazar
mv /home/licjo/OpenNotebook_v2.0.py /home/licjo/OpenNotebook.py

# Verificación final
python /home/licjo/OpenNotebook.py audit --text "Test final"
```

### Opción B: Mantener ambas (SEGURO)
```bash
# Dejar:
# - /home/licjo/OpenNotebook.py (v1.0)
# - /home/licjo/OpenNotebook_v2.0.py (v2.0)

# Usar alias para v2.0
echo "alias opennotebook-v2='python /home/licjo/OpenNotebook_v2.0.py'" >> ~/.bashrc
source ~/.bashrc
```

---

## 🔙 Rollback (por si acaso)

Si algo sale mal post-migración:
```bash
# Restaurar v1.0
cp /home/licjo/OpenNotebook_v1.0.backup /home/licjo/OpenNotebook.py

# Verificar
python /home/licjo/OpenNotebook.py audit --text "Test"
```

---

## 📞 Soporte

Si algún test falla:
1. Leer error completo + logs
2. Consultar `CAMBIOS_v2.0.md` (documentación técnica)
3. Revisar `.env` (rutas correctas)
4. Verificar ChromaDB status

---

**Checklist completado:** [ ] SÍ, todo OK, proceder con migración  
**Fecha validación:** ________  
**Notas:** _________________________________________________________________

