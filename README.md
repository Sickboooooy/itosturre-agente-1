# ⚖️ Agente Itosturre — Auditoría Legal Anti-Alucinaciones

Herramienta para auditar demandas, escritos y conceptos de impugnación con IA bajo el
**Protocolo VVCA** (Verificación · Validación · Contextualización · Auditabilidad), sobre
un corpus legal mexicano indexado localmente.

✨ **Qué hace:**
- 🔍 Verifica cada cita de artículo contra el corpus oficial (RAG sobre ChromaDB)
- 📚 Verifica las tesis/jurisprudencia **citadas** en el documento contra el corpus de jurisprudencia (anti-alucinación)
- 🚦 Asigna un semáforo VVCA (🟢/🟡/🔴) por referencia, con razón explícita
- 🔭 Scraper SJF en vivo (aparte): consulta el SJF en tiempo real para **comparar y proponer** tesis que refuercen la estrategia
- 🧾 Deja el material listo para un reporte (Word con capturas SJF + RAG)

Hecha por [**Itosturre LegalTech**](https://itosturre.com) para el curso
"IA Estratégica para Abogados" (junio 2026).

> ⚠️ **El Protocolo Anti-Alucinación es innegociable.** La herramienta nunca inventa
> número de tesis, registro SJF, época o localización. Si una cita no se puede verificar,
> lo dice — no la maquilla. La validación final corresponde a un abogado humano.

---

## 📋 Requisitos

| | Versión | Descarga |
|---|---|---|
| Python | 3.10+ (este equipo usa el global 3.14, sin venv) | https://www.python.org/downloads/ |
| Node.js | 18+ (solo para el scraper SJF) | https://nodejs.org/ |

Verifica lo que ya tienes:
```bash
python --version
node --version
```

---

## 🚀 Paso 1 — Clonar el repositorio

```bash
git clone https://github.com/Sickboooooy/itosturre-agente.git
cd itosturre-agente
```

## 📦 Paso 2 — Entorno Python

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

**Mac/Linux:**
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

> El modelo de embeddings `intfloat/multilingual-e5-large` (~2 GB) se descarga solo la
> primera vez que corres un `ingest` o un `audit`.

## 📥 Paso 3 — Corpus legal (un solo comando)

El corpus (PDFs de leyes y códigos) y la base vectorial `chroma_db/` **no viajan en el
repo** por tamaño. El script de bootstrap los baja del Drive compartido, los indexa y
verifica la cobertura:

```bash
bash scripts/bootstrap_corpus.sh
```

Esto deja el RAG funcionando. Carpeta del corpus (públicas, "anyone with the link"):
<https://drive.google.com/drive/folders/1VS_LwlQXMCLfh5YA_nnxXzzQ_xuHkdtf>

**Manual** (si prefieres): descarga los PDFs del Drive a `corpus/` y luego:
```bash
python OpenNotebook.py ingest --directory corpus/
python scripts/check_corpus.py
```
La verificación debe terminar en `🟢 Cobertura completa: 0 fuentes ausentes`. Si lista
faltantes, indéxalas antes de auditar — auditar sin el corpus completo degrada la verificación.

## ✅ Paso 4 — Scraper SJF (submódulo, opcional)

El scraper SJF vive en su propio repo como **submódulo** (`services/itosturre-scraper`). Si
clonaste sin `--recursive`, inicialízalo primero:

```bash
git submodule update --init --recursive
cd services/itosturre-scraper && npm install && npx playwright install chromium && cd ../..
```

> Tip: clona el repo con `git clone --recursive ...` para traer el submódulo de una vez.

---

## 💼 Cómo usar la herramienta

### A) 🔍 Auditar un escrito

```bash
python OpenNotebook.py audit --file mi_demanda.md
# salida lista para Telegram:
python OpenNotebook.py audit --file mi_demanda.md --format telegram
```

Lee el JSON: cada referencia trae su `vvca` con **score 0–100** y semáforo:

| Semáforo | Score | Acción |
|---|---|---|
| 🟢 | ≥85 | Citar con seguridad |
| 🟡 | 60–84 | Citar con reserva — verificar |
| 🔴 | <60 | No citar — investigar |

El campo `vvca_summary.veredicto` da una **decisión binaria con razón**: una tesis con
rubro discrepante bloquea el veredicto (🔴) por sí sola, sin importar el RAG. Si el corpus
no contiene una ley citada, el sistema lo marca **🟡 NO VERIFICABLE** (no la tacha de
alucinación) y te pide indexarla o verificar en fuente oficial.

> Si auditas con `--force` y el corpus está incompleto, el resultado incluye
> `corpus_warning` con las leyes no verificadas.

### B) 📚 Buscar / verificar jurisprudencia en el SJF

```bash
cd services/itosturre-scraper
npx ts-node --esm vvca_audit.ts --out <dir_expediente> --contexto caso.json 2024783 2003551
```
Con `--contexto caso.json` evalúa la relevancia de cada tesis al caso, descarta las
inaplicables y busca alternativas de oficio. Resultado en `<dir_expediente>/auditoria_vvca.json`
+ capturas `sjf_<registro>.png`.

### C) 🧩 Pipeline completo (recomendado)

`vvca_full.py` orquesta todo con rutas parametrizadas (sin editar scripts por caso):
```bash
python vvca_full.py --caso auditorias/2026-06-18-MI-CASO \
    --borrador mi_demanda.md \
    --contexto caso.json --registros 2024783 2003551
```
Hace: gate de cobertura → audit RAG → scraper SJF → capturas RAG → `vvca_full.json`
consolidado. (El `.docx` final sigue siendo un paso manual por caso.)

---

## 🧠 Búsqueda semántica directa

```bash
python OpenNotebook.py query "prisión preventiva oficiosa CNPP" --n 5
```

---

## ⚠️ Si algo falla

| Síntoma | Solución |
|---|---|
| "Base vectorial no encontrada" | Corre primero `python OpenNotebook.py ingest --directory corpus/` |
| "corpus_incomplete" | Indexa las leyes que liste, o añade `--force` para auditar con advertencia |
| Emojis rotos / `charmap codec` | La consola fuerza UTF-8 sola; si persiste, usa Windows Terminal |
| Error de Playwright/Chromium | `cd services/itosturre-scraper && npx playwright install chromium` |
| `check_corpus.py` lista faltantes | Re-indexa esas leyes desde su PDF oficial |

---

## 📂 Estructura real

```
itosturre-agente/
├── OpenNotebook.py            # Motor RAG + auditoría VVCA (CLI: ingest/audit/query/correct/calibrate)
├── scoring_vvca.py            # Veredicto binario VVCA (dos scores independientes)
├── vvca_full.py              # Pipeline unificado parametrizado
├── capturar_rag.py           # Screenshots de chunks RAG para el reporte
├── scripts/
│   ├── bootstrap_corpus.sh   # Descarga el corpus del Drive + ingest + verifica (onboarding)
│   ├── check_corpus.py       # Verificador de cobertura del corpus
│   ├── run_regression.py     # Suite de regresión VVCA (gate pre-merge)
│   └── git_strategy.sh       # Disciplina de ramas (0=rama 1=commit 2=push 3=merge)
├── services/itosturre-scraper/  # Scraper SJF en vivo — búsqueda estratégica (TS/Playwright)
├── chroma_db/                # Base vectorial (generada por ingest — no se versiona)
└── docs/PROTOCOLO_VVCA.md    # Especificación del scoring y los guards
```

---

## ⚖️ Aviso Legal

Herramienta de **apoyo** a la verificación. **Tú** eres responsable de los escritos que
presentes. Verifica toda cita en fuentes oficiales antes de uso procesal:
sjf2.scjn.gob.mx · dof.gob.mx · cjf.gob.mx.

**Licencia:** uso educativo, no comercial.

---

## 👥 Equipo

🏛️ **Lic. Jorge Fabián Martínez Sánchez** — Director Legal & IA · 25 años en el Poder Judicial Federal
💻 **Ing. Aldo Guillermo Madrigal** — CTO & Lead Developer

**Itosturre LegalTech © 2026.** Hecho con ⚖️ y ❤️.
