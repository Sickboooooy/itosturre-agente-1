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
falla con `ModuleNotFoundError` (en `OpenNotebook.py`: "❌ OpenNotebook necesita el
paquete …", código de salida 1), reinstala los requirements en el venv.

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

### Re-ingestar una sola fuente (desde el 4-oct-2026)

> ⚠️ **`--reingest` y `--clear` borran la colección ENTERA** (las 49 leyes, ~28 000
> fragmentos) y re-ingestan todo lo que haya en la carpeta. No sirven para corregir una ley.
> Tampoco basta volver a correr `ingest` sin flags: una fuente ya indexada con otra
> fragmentación se **omite** (antes se mezclaban fragmentos viejos y nuevos por ID) y la
> ingesta termina con **código 3 (MIGRACIÓN PENDIENTE)**, la lista de fuentes omitidas y el
> comando `--fuente` exacto; `scripts/bootstrap_corpus.sh` no anuncia "Corpus listo" en ese
> caso (sale también con 3).

Para sustituir solo los fragmentos de una ley (p. ej., tras un cambio del cortador o un PDF
nuevo con el mismo nombre), con el nombre **exacto** del PDF (mayúsculas y acentos: es el
`source` del índice) dentro de la carpeta de ingesta (`INGEST_ALLOWED_BASE`):

```bash
# 1. Simular (no escribe): fragmentos, etiquetas y cobertura antes (índice) → después,
#    identidad con lo indexado y lo que se rechazaría (⛔)
./venv/Scripts/python.exe OpenNotebook.py ingest --directory "<carpeta_pdfs>" \
    --fuente "LEY DE AMPARO.pdf" --simular            # --json para el informe en JSON

# 2. Respaldar el índice completo (sin ningún proceso abierto sobre él)
cp -a chroma_db "chroma_db.respaldo-$(date +%Y%m%d-%H%M)"

# 3. Re-ingestar (repetible: --fuente "A.pdf" --fuente "B.pdf"); imprime la ruta del
#    respaldo durable de cada fuente
./venv/Scripts/python.exe OpenNotebook.py ingest --directory "<carpeta_pdfs>" \
    --fuente "LEY DE AMPARO.pdf" [--respaldos "<carpeta fuera del repo>"]

# 4. Verificar
./venv/Scripts/python.exe scripts/check_corpus.py
./venv/Scripts/python.exe scripts/run_regression.py

# Deshacer una fuente: reponer su respaldo durable (valida la huella, respalda el estado
# actual y verifica textos, metadatos y vectores)
./venv/Scripts/python.exe OpenNotebook.py ingest --restaurar "<respaldo.json>"
```

Qué hace la re-ingesta por fuente (`reingestar_fuentes` en `OpenNotebook.py`), en dos fases:

1. **Sin escribir nada, para todas las fuentes pedidas** (si una falla, se niega con código 2
   y el índice no se toca): al menos una fuente, nombre exacto, PDF no excluido, sin repetir;
   **extracción completa** (ninguna página antes de la línea TRANSITORIOS sin texto o con menos
   de 200 caracteres: delata escaneo o pérdida; sin TRANSITORIOS se revisan todas menos la
   última); **identidad** con lo indexado de esa misma fuente, sin depender del catálogo
   (mismo título en la primera página y ≥ 90 % de las designaciones de artículo indexadas
   presentes en el PDF; con menos de 10, ≥ 90 % de los fragmentos indexados presentes en su
   texto); ningún ID nuevo ocupado por **otra** fuente. Si el título difiere solo por el
   formato del PDF (los oficiales del Congreso de Jalisco anteponen el preámbulo del decreto) y
   el operador confirma que es el mismo ordenamiento, `--identidad-confirmada "<pdf>"` (junto a
   su `--fuente`) omite solo la comparación del título: decide el contenido, con el mismo
   umbral, y el informe registra los dos títulos (desde el 10-oct-2026).
2. **Por fuente:** calcula los vectores antes de escribir; escribe un **respaldo durable** de
   los fragmentos actuales (ids, documentos, metadatos y vectores float32, con su huella
   SHA-256) en `--respaldos`, `$ITOSTURRE_RESPALDOS_REINGESTA` o
   `~/.itosturre/respaldos_reingesta` (nunca dentro del repositorio ni del índice) y lo relee;
   borra **solo** `source == <archivo.pdf>`; agrega los nuevos con los metadatos de siempre
   (`source`, `law`, `article`, `page`, `chunk_index`, `doc_type`; IDs `{stem}_chunk_{i}`
   contiguos desde 0) y verifica. Si algo falla, restaura los fragmentos previos y sale con
   código 1 (el mensaje da el respaldo durable).

Para **sacar del índice** una fuente que el catálogo ya no resuelve (p. ej. una ley abrogada cuya
sucesora se indexó como fuente propia; primero se quita de `LAW_SOURCE_MAP` y el manifiesto la
marca `descartado`): `OpenNotebook.py ingest --retirar "<pdf>"` (repetible, sin `--directory`).
Valida todas antes de escribir, respalda cada una de forma durable, borra solo esa fuente,
verifica y, si algo falla, restaura; se repone con `ingest --restaurar` (desde el 10-oct-2026).

Tiempo de referencia en este equipo (CPU, e5-large): ~0.45 s por fragmento (CFPC, 726
fragmentos: 331 s). `--restaurar` no recalcula vectores (segundos). Nunca dos procesos sobre
el mismo `chroma_db`.

### Vigencia del corpus (desde el 9-oct-2026)

Estar indexada no es estar vigente. `scripts/vigencia_corpus.py` coteja la versión de cada
fuente del índice (sello "Última Reforma DOF" de LeyesBiblio, o el "Acuerdo DOF" posterior de
actualización de montos que el PDF anota bajo ese sello, como en la LFPC; en Jalisco, la tabla
de reformas y el decreto citado) contra el listado oficial de hoy y da un semáforo por fuente, sin
promediar. Es solo lectura: no descarga leyes ni re-indexa, y solo consulta URL https de hosts
oficiales. La fuente oficial de cada PDF vive en `scripts/fuentes_oficiales.json`.

```bash
python scripts/vigencia_corpus.py               # reporte en reportes/vigencia_corpus/ (no se versiona)
bash scripts/instalar_vigencia_corpus.sh        # agenda bimestral, solo macOS (launchd): --estado · --ahora · --desinstalar
```

Mientras una ley no esté 🟢, sus artículos se cotejan contra el PDF oficial antes de citarlos
(Regla 8 de `CLAUDE.md`). Las descargas y las fichas quedan fuera del repo, en
`~/itosturre-data/cotejo/<fecha>/`:

```bash
./venv/Scripts/python.exe scripts/cotejo_manual.py preparar    # baja y valida los PDF oficiales (PyMuPDF)
python scripts/cotejo_manual.py articulo LFT 47 48             # ficha por artículo (solo librería estándar)
```

Para actualizar una ley 🔴, el reporte trae los comandos de la re-ingesta por fuente de arriba,
con las rutas del índice auditado.


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
