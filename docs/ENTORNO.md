# Entorno de ejecución

**Estado:** vigente desde 10-sep-2026
**Alcance:** intérprete, dependencias y bootstrap del corpus.
**Por qué existe:** este detalle vivía en `CLAUDE.md` y se pagaba en tokens en cada
turno para describir una plataforma que no era la de esta máquina.

---

## Intérprete por plataforma

| Plataforma | Comando canónico |
|---|---|
| **Windows** (equipo actual) | `./venv/Scripts/python.exe` |
| macOS / Linux | `./venv/bin/python` |

El layout del venv difiere entre plataformas: `Scripts/` en Windows, `bin/` en
POSIX. `./venv/bin/python` **no existe en Windows**.

`source venv/bin/activate` (o `venv\Scripts\activate`) **no persiste** entre
llamadas de shell del IDE: cada invocación arranca limpia. Por eso los comandos
se escriben con la ruta completa al intérprete en lugar de activar el entorno.

### Estado verificado en el equipo actual (10-sep-2026)

Comprobado ejecutando, no supuesto:

- Windows 11 · Python **3.14.0** · SQLite **3.50.4**.
- `python` global (`C:\Python314\python.exe`) **existe y tiene todas las
  dependencias** (`chromadb`, `sentence_transformers`, `fitz`,
  `langchain_text_splitters`).
- `python3` **no existe**: el alias de Microsoft Store lo intercepta y sugiere
  instalar desde la tienda.
- El venv del proyecto tiene el mismo juego de dependencias.

> Nota histórica: `CLAUDE.md` describía este equipo como macOS, afirmaba que solo
> existía `python3` y ordenaba `./venv/bin/python`. Las tres cosas eran falsas
> aquí. Se corrigen en este documento.

**Aun así, prefiere el venv sobre el `python` global.** Que hoy funcione es una
coincidencia de esta máquina: el venv es el que está fijado a `requirements.txt`
y el único que se puede reproducir en un clon limpio.

---

## Setup desde clon limpio

```bash
# Windows
python -m venv venv
./venv/Scripts/python.exe -m pip install -r requirements.txt gdown
PYTHON="$(pwd)/venv/Scripts/python.exe" bash scripts/bootstrap_corpus.sh

# macOS / Linux
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt gdown
PYTHON="$(pwd)/venv/bin/python" bash scripts/bootstrap_corpus.sh
```

`requirements.txt` incluye **PyMuPDF** y **langchain-text-splitters**: eran
imports de `OpenNotebook.py` que faltaban y abortaban el `ingest`. Si un comando
falla con `ModuleNotFoundError`, reinstala los requirements en el venv.

---

## Corpus

Los PDFs vienen de una carpeta pública de Drive en **solo lectura**. El RAG queda
indexado en `chroma_db/` tras el bootstrap.

```bash
./venv/Scripts/python.exe scripts/check_corpus.py          # cobertura legible
./venv/Scripts/python.exe scripts/check_corpus.py --json   # para el pipeline
```

**Estado a 10-sep-2026: 48 de 48 ordenamientos presentes.** (`CLAUDE.md` decía 47;
la cifra se movió con la indexación fiscal de julio y el texto no se actualizó.)

Un hueco de corpus **no invalida el argumento que cita la ley ausente** — es una
limitación del índice. Ver Regla 7 del protocolo anti-alucinación en `CLAUDE.md`.

---

## Memoria contextual

Base fuera del repositorio, en `~/.itosturre/memoria/<project_id>.db`.
Variables de entorno y detalle en [`MEMORIA.md`](MEMORIA.md).

---

## Verificación antes de mergear

```bash
./venv/Scripts/python.exe -m unittest discover -s tests -p "test_*.py"
./venv/Scripts/python.exe scripts/check_agent_surfaces.py
./venv/Scripts/python.exe scripts/check_sensitive_paths.py
./venv/Scripts/python.exe scripts/evaluate_gold_set.py
./venv/Scripts/python.exe scripts/run_regression.py    # requiere corpus local
```

`run_regression.py` no corre en CI compartido porque necesita el corpus y el
modelo de embeddings: **un CI verde no sustituye ese gate local.** Contratos
completos en [`ARQUITECTURA.md`](ARQUITECTURA.md).
