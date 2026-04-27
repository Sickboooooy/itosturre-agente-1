# OpenNotebook v2.0 — Quick Start (5 min)

## 🚀 Instalación express

### 1. Instalar dependencias (1 min)
```bash
source /home/licjo/venv/bin/activate
pip install python-dotenv==1.0.1
```

### 2. Crear .env (30 seg)
```bash
cp /home/licjo/.env.example /home/licjo/.env
```

### 3. Probar (2 min)
```bash
python /home/licjo/OpenNotebook_v2.0.py audit --text "El artículo 247 del CPF establece..."
```

✅ Si ves JSON con `"status": "ok"` → funciona.

---

## 📚 Uso básico

### Auditar un archivo
```bash
python /home/licjo/OpenNotebook.py audit --file borrador.md
```

### Ver output bonito
```bash
python /home/licjo/OpenNotebook.py audit --file borrador.md | python -m json.tool
```

### Debug mode (ver logs)
```bash
python /home/licjo/OpenNotebook.py audit --file borrador.md --verbose
```

### Re-ingestionar corpus
```bash
python /home/licjo/OpenNotebook.py ingest --directory /home/licjo/corpus_legal --reingest
```

---

## 🔑 Cambios visibles desde el usuario

### 1. Alertas más claras
**Antes (v1.0):**
```
ALERTA: 'Art. 247 CPF' — no se encontró coincidencia confiable 
en el corpus (distancia: 0.68). Verificar manualmente.
```

**Ahora (v2.0):**
```
🔴 ALERTA ALTA: 'Art. 247 CPF' — no se encontró coincidencia 
confiable en el corpus (distancia: 0.689, umbral: 0.5). 
Posible alucinación. Verificar en fuente oficial.
```

### 2. Página en resultado
Antes:
```json
{"reference": "Art. 247 CPF", "source_file": "...", "relevance_score": 0.52}
```

Ahora:
```json
{"reference": "Art. 247 CPF", "source_file": "...", "page": "123", "relevance_score": 0.521}
```

→ Puedes ir directo a la página 123 del PDF.

### 3. Score más preciso
Antes: 0.52  
Ahora: 0.521

→ Menos redondeado.

---

## ⚙️ Configuración

Edita `/home/licjo/.env` para cambiar:

```env
# Ruta a ChromaDB
CHROMA_PATH=/home/licjo/chroma_db

# Ruta a jurisprudencia
JURISPRUDENCIA_PATH=/home/licjo/jurisprudencia

# Umbral de distancia
COSINE_THRESHOLD=0.50   # 0.40=estricto, 0.50=recomendado, 0.60+=permisivo
```

**Después de editar .env:**
```bash
python /home/licjo/OpenNotebook.py audit --file borrador.md
# Automáticamente carga nuevos valores
```

---

## 🆚 Vs v1.0: ¿Qué cambió?

| Para el usuario | v1.0 | v2.0 |
|---|---|---|
| Auditoría funciona igual | ✅ | ✅ |
| Alertas más útiles | ⚠️ Genéricas | ✅ Con contexto |
| Sabe qué página | ❌ No | ✅ Sí |
| Logs útiles | ⚠️ Basic | ✅ Debug mode |
| Porátil a otra máquina | ❌ No | ✅ .env |
| Score preciso | ⚠️ 2 decimales | ✅ 3 decimales |

**Bottom line:** Mismo output, pero mejor información + más debuggable.

---

## 💡 Ejemplos reales

### Caso 1: Detectar alucinación

```bash
cat > test.md << 'EOF'
El Código de la Fantasía en su artículo 999 establece...
EOF

python OpenNotebook.py audit --file test.md
```

**Salida:**
```json
{
  "status": "ok",
  "total_references_found": 1,
  "verified": 0,
  "alerts_count": 1,
  "alerts": [
    "🔴 ALERTA CRÍTICA: 'artículo 999' — El borrador cita... 
     pero no se encontró en el corpus legal. Alucinación detectada 
     — verificar en fuente oficial ANTES de usar."
  ]
}
```

### Caso 2: Verificar cita válida

```bash
cat > test.md << 'EOF'
De conformidad con la Constitución Política de los Estados Unidos 
Mexicanos, artículo 1, se establece que todos somos iguales.
EOF

python OpenNotebook.py audit --file test.md
```

**Salida:**
```json
{
  "status": "ok",
  "total_references_found": 1,
  "verified": 1,
  "alerts_count": 0,
  "retrieved_sources": [
    {
      "reference": "artículo 1",
      "law": "Constitución Política de los Estados Unidos Mexicanos",
      "article": "1",
      "source_file": "CONSTITUCION POLITICA DE LOS ESTADOS UNIDOS MEXICANOS CPEUM.pdf",
      "page": "1",
      "relevance_score": 0.945,
      "retrieved_text": "Artículo 1. En los Estados Unidos Mexicanos todas las personas..."
    }
  ],
  "summary": "Auditoría RAG completada: 1 fuentes verificadas, 0 alertas."
}
```

### Caso 3: Re-ingestionar después de agregar PDFs

```bash
# Agregas nuevos PDFs a corpus_legal/
cp ~/Downloads/*.pdf /home/licjo/corpus_legal/

# Re-ingestionar (recalcula embeddings)
python OpenNotebook.py ingest --directory /home/licjo/corpus_legal --reingest --verbose
```

**Logs:**
```
2026-04-26 20:15:32 [INFO] 🗑️  Colección borrada.
2026-04-26 20:15:33 [INFO] 🔄 Colección limpiada para re-ingesta.
2026-04-26 20:15:33 [INFO] 📚 PDFs encontrados: 42
2026-04-26 20:15:34 [INFO]   🔍 Procesando: CODIGO_PENAL_FEDERAL_2025.pdf
2026-04-26 20:15:35 [INFO]     📄 234 chunks generados
2026-04-26 20:15:36 [INFO]     ✅ Indexado correctamente
... (más PDFs)
2026-04-26 20:16:45 [INFO] ✅ INGESTA COMPLETADA
2026-04-26 20:16:45 [INFO]    PDFs procesados : 42
2026-04-26 20:16:45 [INFO]    Chunks totales  : 30953
2026-04-26 20:16:45 [INFO]    Base vectorial  : /home/licjo/chroma_db
```

---

## 🐛 Si algo no funciona

### Error: `No such file or directory: '.env'`
```bash
cp /home/licjo/.env.example /home/licjo/.env
```

### Error: `chromadb not found` o `sentence-transformers not found`
```bash
pip install chromadb langchain-text-splitters sentence-transformers PyMuPDF
```

### Error: `"status": "error", "message": "La colección está vacía"`
ChromaDB está vacío. Re-ingestiona:
```bash
python OpenNotebook.py ingest --directory /home/licjo/corpus_legal --reingest
```

### Output JSON roto
Usa `| python -m json.tool` para debuggear:
```bash
python OpenNotebook.py audit --file test.md 2>&1 | python -m json.tool
```

---

## 📖 Siguiente: Documentación

Para entender internals:
- **CAMBIOS_v2.0.md** — Qué cambió y por qué (técnico)
- **COMPARATIVO_v1_vs_v2.md** — Lado-a-lado de código
- **CHECKLIST_VALIDACION_v2.md** — Tests antes de producción

---

## ✅ Checklist post-instalación

- [ ] pip install python-dotenv OK
- [ ] .env creado en /home/licjo/
- [ ] Primer audit test pasa
- [ ] JSON output válido
- [ ] --verbose muestra logs
- [ ] Listo para producción

---

**¿Listo?** Reemplaza v1.0:
```bash
mv /home/licjo/OpenNotebook.py /home/licjo/OpenNotebook_v1.0.backup
mv /home/licjo/OpenNotebook_v2.0.py /home/licjo/OpenNotebook.py
```

**¿Preocupado?** Mantén ambas:
```bash
# v1.0: /home/licjo/OpenNotebook_v1.0.backup
# v2.0: /home/licjo/OpenNotebook_v2.0.py
# Usa v2.0 cuando quieras, v1.0 si hay problema
```

---

Ahora sí, **OpenNotebook v2.0 está listo para rodar.** 🚀
