# ⚖️ Agente Itosturre — Auditoría Legal Anti-Alucinaciones

Herramienta para auditar demandas, escritos y conceptos de impugnación con IA bajo el
**Protocolo VVCA** (Verificación · Validación · Contextualización · Auditabilidad), sobre
un corpus legal mexicano indexado localmente.

✨ **Qué hace:**
- 🔍 Verifica cada cita de artículo contra el corpus oficial (RAG sobre ChromaDB)
- 📚 Verifica las tesis/jurisprudencia **citadas** en el documento contra el corpus de jurisprudencia (anti-alucinación)
- 🚦 Asigna un semáforo VVCA (🟢/🟡/🔴) por referencia, con razón explícita
- 🔭 Scraper SJF en vivo (aparte): consulta el SJF en tiempo real para **comparar y proponer** tesis que refuercen la estrategia
- 🧭 Conserva una traza estructurada por cita, incluidas las no verificables o refutadas
- 🧪 Ejecuta un Gold Set sintético como gate de regresión de las políticas VVCA
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
| Python | 3.10+ — **verificado en Python 3.14.2** (torch 2.12.1, chromadb 1.5.9, sentence-transformers 5.6.0 instalan sin problema) | https://www.python.org/downloads/ |
| Node.js | 18+ (solo para el scraper SJF) | https://nodejs.org/ |

Verifica lo que ya tienes:
```bash
python3 --version   # en macOS no existe el binario `python` a secas, usa python3
node --version
```

> ⚠️ **macOS (Homebrew):** solo existe `python3`, no `python`. Por eso **debes** trabajar
> dentro de un venv (Paso 2): una vez activado, `python` apunta al intérprete del venv y
> todos los comandos de abajo funcionan tal cual.

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
# con el venv ACTIVADO (source venv/bin/activate) — el script usa `python`:
bash scripts/bootstrap_corpus.sh

# o, sin activar el venv (macOS no tiene `python` global), apúntalo al venv:
PYTHON="$(pwd)/venv/bin/python" bash scripts/bootstrap_corpus.sh
```

> ⚠️ `bootstrap_corpus.sh` invoca `python` por defecto. En macOS ese binario no existe
> (solo `python3`), así que **o activas el venv primero** o pasas `PYTHON=...` como arriba.
> De lo contrario el ingest falla con "command not found" o usa un Python sin dependencias.

Esto deja el RAG funcionando. Carpeta del corpus en Drive — **pública en modo solo lectura**
("anyone with the link · Lector", verificado el 2026-06-19; antes estaba en *Editor*, se
corrigió para que nadie externo pueda alterar los PDFs):
<https://drive.google.com/drive/folders/1VS_LwlQXMCLfh5YA_nnxXzzQ_xuHkdtf> · 47 PDFs.

**Manual** (si prefieres): descarga los PDFs del Drive a `corpus/` y luego, con el venv activo:
```bash
python OpenNotebook.py ingest --directory corpus/   # = venv/bin/python si no lo activaste
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

## ✅ Setup verificado en este equipo (macOS · Python 3.14.2 · 2026-06-19)

Secuencia exacta que dejó el RAG funcional desde un clon limpio. Reprodúcela tal cual si
partes de cero (los comandos asumen que estás en la raíz del repo):

```bash
# 1) venv con python3 (en macOS NO existe `python` a secas)
python3 -m venv venv
./venv/bin/python -m pip install --upgrade pip

# 2) dependencias (requirements.txt + gdown para el bootstrap)
./venv/bin/python -m pip install -r requirements.txt gdown

# 3) corpus: descarga del Drive + ingest + verificación
PYTHON="$(pwd)/venv/bin/python" bash scripts/bootstrap_corpus.sh
```

**Dos dependencias faltaban en `requirements.txt`** y rompían el `ingest`; ya están
agregadas (si clonaste antes de este fix, reinstala con el comando del paso 2):

| Faltaba | Síntoma | Paquete |
|---|---|---|
| Extracción de texto de PDFs | `ModuleNotFoundError: No module named 'fitz'` | `PyMuPDF` |
| Chunking del corpus | `ModuleNotFoundError: No module named 'langchain_text_splitters'` | `langchain-text-splitters` |

> **Compatibilidad Python 3.14:** sin problemas — `torch 2.12.1`, `chromadb 1.5.9`,
> `sentence-transformers 5.6.0`, `PyMuPDF 1.27.2` traen wheels para cp314/arm64.

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

El scraper intenta `sjf2` y después `sjfsemanal`, y registra si cada fallo fue de red,
bloqueo, timeout, cambio de layout o ausencia confirmada. No consume endpoints internos no
documentados del microservicio de la SCJN.

### C) 🧩 Pipeline completo (recomendado)

`vvca_full.py` orquesta todo con rutas parametrizadas (sin editar scripts por caso):
```bash
python vvca_full.py --caso auditorias/2026-06-18-MI-CASO \
    --borrador mi_demanda.md \
    --contexto caso.json --registros 2024783 2003551
```
Hace: gate de cobertura → audit RAG → scraper SJF → capturas RAG → `vvca_full.json`
consolidado. (El `.docx` final sigue siendo un paso manual por caso.)

El pipeline **falla cerrado**: si OpenNotebook termina con error, devuelve JSON inválido, el
scraper solicitado falla o no produce un `auditoria_vvca.json` esquema 2.0 nuevo, guarda el
diagnóstico con `status: "failed"` y sale con código 1. No imprime un mensaje de éxito.
Solo continúa degradado por una decisión explícita del operador:

- `--force`: permite corpus incompleto y produce `status: "partial"`;
- `--no-sjf`: omite conscientemente el SJF aunque se hayan proporcionado registros;
- `--no-rag-capture`: omite conscientemente la captura PNG de los chunks recuperados;
- `--allow-partial-sjf`: permite continuar con `status: "partial"` si falla el SJF solicitado.

La memoria contextual es accesoria: su fallo queda como advertencia, pero no invalida una
auditoría RAG/SJF correcta.

---

## 🧠 Búsqueda semántica directa

```bash
python OpenNotebook.py query "prisión preventiva oficiosa CNPP" --n 5
```

```python
from OpenNotebook import OpenNotebook_query
results = OpenNotebook_query("prisión preventiva oficiosa CNPP", n=5, json=True)
print(results)
```
---

## ⚠️ Si algo falla

| Síntoma | Solución |
|---|---|
| `ModuleNotFoundError: No module named 'fitz'` | Falta PyMuPDF: `pip install PyMuPDF` (ya está en requirements.txt; reinstala con `pip install -r requirements.txt`) |
| `ModuleNotFoundError: No module named 'langchain_text_splitters'` | `pip install langchain-text-splitters` (ya está en requirements.txt) |
| `python: command not found` (macOS) | No existe `python` global, solo `python3`. Activa el venv (`source venv/bin/activate`) o usa `venv/bin/python` / `PYTHON=venv/bin/python` con el bootstrap |
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
├── router_competencia.py     # Competencia orgánica determinista
├── agentes/                  # Vigilancia y automatizaciones auxiliares
├── itosturre/audit/          # Políticas VVCA puras extraídas del monolito
├── config/data-policy.json   # Reglas ejecutables de confidencialidad
├── tests/                    # Pruebas unitarias offline
├── scripts/
│   ├── bootstrap_corpus.sh   # Descarga el corpus del Drive + ingest + verifica (onboarding)
│   ├── check_corpus.py       # Verificador de cobertura del corpus
│   ├── run_regression.py     # Suite de regresión VVCA (gate pre-merge)
│   ├── check_agent_surfaces.py # Evita divergencia CLAUDE/AGENTS y skills
│   ├── check_sensitive_paths.py # Evita versionar datos y artefactos locales
│   └── git_strategy.sh       # Disciplina de ramas (0=rama 1=commit 2=push 3=merge)
├── services/itosturre-scraper/  # Scraper SJF en vivo — búsqueda estratégica (TS/Playwright)
├── services/itosturre-skills/   # Skills jurídicas distribuibles (submódulo)
├── corpus/ y jurisprudencia/    # Fuentes locales; no se versionan
├── chroma_db/                # Base vectorial (generada por ingest — no se versiona)
├── auditorias/               # Producto confidencial por caso; no se versiona
└── docs/
    ├── ARQUITECTURA.md       # Mapa, límites y fuentes canónicas
    └── PROTOCOLO_VVCA.md     # Especificación del scoring y los guards
```

El repositorio padre es Python. Las dependencias Node pertenecen exclusivamente al
submódulo `services/itosturre-scraper`; por eso no hay `package.json` en la raíz.

### Pruebas

```bash
# Gate completo local (requiere corpus + ChromaDB)
python scripts/run_regression.py

# Consistencia de instrucciones Claude/Codex
python scripts/check_agent_surfaces.py

# Política de rutas sensibles y fixtures
python scripts/check_sensitive_paths.py

# Políticas VVCA puras
python -m unittest discover -s tests -p "test_*.py"

# Gold Set sintético de políticas VVCA
python scripts/evaluate_gold_set.py

# Parser de vigencia + resiliencia del scraper (offline)
python scripts/test_scraper_offline.py
```

La arquitectura completa y la política de datos están en
[`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

El diseño de fallback, Gold Set y trazabilidad está en
[`docs/CONFIABILIDAD_VVCA.md`](docs/CONFIABILIDAD_VVCA.md).

La política de confidencialidad está en [`docs/POLITICA_DATOS.md`](docs/POLITICA_DATOS.md).
La preparación local de prospectos B2B está documentada en
[`docs/PROSPECCION_RESPONSABLE.md`](docs/PROSPECCION_RESPONSABLE.md). Este módulo normaliza,
deduplica y aplica exclusiones; no recolecta datos ni envía comunicaciones.
Los consumidores de `fetch_tesis_detalle.py` deben seguir la
[`guía de migración`](docs/MIGRACION_FETCH_TESIS.md).

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

*En memoria de Alejandro “Itosturre” (QEPD), cuyo nombre y recuerdo inspiran este proyecto.*

**Itosturre LegalTech © 2026.** Hecho con ⚖️ y ❤️.
