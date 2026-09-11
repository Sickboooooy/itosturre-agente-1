# Auditoría de memoria y continuidad contextual · Itosturre-Agente vs. Context Mode

**Fecha:** 10-sep-2026 · **Estado:** informe previo a implementación — **sin cambios de código**
**Referencia externa:** `github.com/mksglu/context-mode` v1.0.169 (clonado a scratchpad, no al repo)

---

## 0. Dos correcciones de premisa antes de nada

### 0.1 Este repositorio no contiene un MCP

El encargo dice "mejorar la memoria de este MCP". No hay MCP que mejorar:

- No existe `.mcp.json` en el repo.
- No existe servidor MCP propio: cero imports de `mcp`, `fastmcp` o
  `@modelcontextprotocol/sdk` en código. Las ~40 coincidencias de "mcp" son
  **documentación** (`skills/itosturre/references/mcp-hardening.md`,
  `mcp-connector-catalog.md`) — material que *enseña* sobre MCP a despachos.
- La única mención funcional está en `deploy/telegram-ai-agent/README.md:13`,
  sobre una incompatibilidad de versión de un proyecto ajeno.

Lo que en la práctica hace de "agente con memoria" es otra cosa:

| Pieza | Qué es | Dónde |
|---|---|---|
| Prompt de sistema | 41.5 KB de política operativa | `CLAUDE.md` / `AGENTS.md` |
| Memoria persistente | 17 archivos `.md` escritos a mano | `~/.claude/projects/…/memory/` |
| Herramientas | CLIs de Python invocados por Bash | `OpenNotebook.py`, `vvca_full.py`, … |
| Skills | Submódulo | `services/itosturre-skills/` |
| Corpus | ChromaDB + e5-large (1024d) | `chroma_db/` |

Esto **no invalida el encargo** — el problema de memoria y continuidad es real y
está bien diagnosticado. Pero cambia dónde se interviene: no hay un servidor MCP
donde enchufar herramientas; hay CLIs de Python y un prompt. La propuesta se
adapta a eso (§3).

### 0.2 Context Mode es Elastic License 2.0 — no es open source permisivo

`LICENSE:1` — *Elastic License 2.0 (ELv2)*, Copyright 2026 Mert Koseoglu.
Limitación central:

> You may not provide the software to third parties as a hosted or managed
> service, where the service provides users with access to any substantial set
> of the features or functionality of the software.

Itosturre es un producto comercial con clientes B2B activos. **Copiar código de
Context Mode a este repo es un riesgo legal real**, no teórico: crearía una obra
derivada bajo ELv2 dentro de un producto que se ofrece a terceros.

La lectura correcta —y la que el encargo ya pedía— es **reutilización
conceptual**: las ideas de arquitectura no son objeto de derecho de autor; la
expresión concreta (el código) sí. Todo lo que sigue describe mecanismos a
**reimplementar desde cero en Python**, sin portar líneas. El clon vive en el
scratchpad de sesión y no se integra al repo.

---

## FASE 1 — Diagnóstico del sistema actual

### 1.1 Arquitectura

```
Entrada (escrito/caso)
      |
      v
vvca_full.py ──────────────────────────────┐
      |                                     |
      v                                     v
OpenNotebook.py (1808 líneas)      services/itosturre-scraper (submódulo)
  · extract_references()             · vvca_audit.ts / Playwright
  · ChromaDB + e5-large              · SJF en vivo
  · build_vvca / build_vvca_tesis
      |                                     |
      v                                     |
scoring_vvca.py ◄────────────────────────────┘
      |
      v
auditorias/<caso>/{vvca_full,audit_rag,vvca_traceability}.json + capturas
```

### 1.2 Inventario contra los 11 puntos solicitados

| Punto | Estado real | Evidencia |
|---|---|---|
| Herramientas | 6 CLIs Python + 1 CLI TS + 12 skills | `vvca_full.py`, `OpenNotebook.py`, … |
| Sistema de memoria | 17 `.md` manuales + `MEMORY.md` como índice | `~/.claude/projects/…/memory/` |
| Almacenamiento persistente | JSON por caso, sin índice | `auditorias/*/*.json` |
| Gestión de sesiones | **inexistente** | grep de `session/sesion/checkpoint` → 0 en código |
| Manejo de contexto | prompt fijo de 41.5 KB, cargado íntegro siempre | `CLAUDE.md` |
| Recuperación | semántica sobre **corpus jurídico**, no sobre memoria | `OpenNotebook.py:1594` |
| Hooks/eventos | **ninguno configurado** | `.claude/settings.local.json` = solo `permissions` |
| Compactación/resume | **ninguno** | no hay `PreCompact` ni `SessionStart` |
| Manejo de errores | try/except por paso, degradación honesta | `vvca_full.py:118-125` |
| Configuración | 7 variables en `.env`, sin secretos de LLM | `CHROMA_PATH`, `COSINE_THRESHOLD`, … |
| Aislamiento | `check_sensitive_paths.py` + `data-policy.json` | gate en CI |

### 1.3 Dónde se pierde contexto — ocho fugas concretas

**F1 · La memoria es manual y monótonamente creciente.**
Las 17 memorias se escriben a mano cuando el agente se acuerda. `MEMORY.md`
(4.2 KB) se carga **entero** en cada sesión. Ya es el antipatrón de la Fase 7 del
encargo: hoy son 17 punteros, en seis meses serán 50 y el índice pesará 12 KB
inyectados en todos los turnos. Nadie decide qué es relevante *para esta tarea*.

**F2 · No existe registro de eventos.**
Ninguna decisión, corrección, commit, prueba o error queda registrado
estructuradamente. Lo que no se convierta en prosa manual, se pierde.

**F3 · `traceability.py` ya fabrica eventos perfectos… y los tira.**
`build_trace_record()` (`itosturre/audit/traceability.py:36`) produce exactamente
el esquema que la Fase 4 del encargo pide: `trace_id` estable e independiente de
la fecha, `checked_at`, `status`, `score`, `semaforo`, `source`, `metadata`,
`evidence_sha256`. `vvca_full.py:110-119` lo escribe a
`auditorias/<caso>/vvca_traceability.json` — **y nadie lo vuelve a leer jamás**.
Hay 12 expedientes auditados en disco; cero consultables. *Esta es la fuga más
cara y la más barata de tapar: el productor de eventos ya existe.*

**F4 · Cero continuidad entre sesiones.**
No hay concepto de sesión en el código. Al compactar o cerrar, se pierde todo lo
que no esté en `CLAUDE.md` o `MEMORY.md`.

**F5 · Sin hooks.**
`.claude/settings.local.json` solo declara `permissions`. No hay `PreCompact`,
`SessionStart` ni `PostToolUse` — no hay ningún punto donde enganchar captura ni
restauración.

**F6 · El contexto base ya es enorme — y SQLite no lo arregla.**
`CLAUDE.md` son 41.5 KB ≈ **11-12k tokens en cada turno**, más `MEMORY.md`. Una
base de eventos no reduce ni un token de eso. **Es la mayor fuga de contexto del
sistema y ninguna de las 10 fases del encargo la toca** (§3.5).

**F7 · El conocimiento crítico está en prosa no consultable.**
`project_expediente_712_2023.md` registra: *"para deserción de pruebas la vía
correcta es REVOCACIÓN, no apelación (corrección de Fabián 09-jul)"*. Es una
corrección de criterio de un secretario del PJF con 25 años — el activo más
valioso del sistema. Hoy solo se recupera si alguien carga los 17 archivos y lee.
No hay forma de preguntar *"¿qué me has corregido sobre recursos en materia
civil?"*.

**F8 · Deriva de plataforma ya materializada.**
`CLAUDE.md` documenta macOS y ordena `./venv/bin/python`. El entorno real es
Windows 11 y el intérprete está en `./venv/Scripts/python.exe`. La instrucción
operativa más repetida del prompt está mal en este equipo. Es pérdida de contexto
en su forma más literal.

### 1.4 Lo único que ya funciona como memoria estructurada

`OpenNotebook.py:95` → `CORRECTIONS_FILE` = `jurisprudencia/vvca_corrections.json`,
alimentado por `OpenNotebook.py correct` y leído por `calibrate`. Es un event log
real de correcciones del usuario, con `ref`, `semaforo_correcto`,
`score_auditado`, `nota`, `timestamp`.

Sus límites marcan justo lo que falta: array JSON monolítico leído completo con
`json.loads()`, sin `session_id`, sin `project_id`, sin búsqueda, sin más uso que
mover un umbral. **Es el prototipo correcto a 1/20 de escala.**

---

## FASE 2 — Informe comparativo

### 2.0 Cómo funciona Context Mode de verdad (tres correcciones al brief)

El encargo asume cosas sobre Context Mode que el código no confirma. Verificado
contra la fuente:

**(a) Context Mode NO usa FTS5/BM25 sobre eventos.** Son **dos bases separadas**:

| Base | Contenido | Recuperación |
|---|---|---|
| `SessionDB` | `session_events`, `session_meta`, `session_resume`, `tool_calls` | **`LIKE '%…%'` + `ORDER BY id ASC`** (`src/session/db.ts:1086-1093`) |
| `ContentStore` | `chunks` (docs indexados) | **FTS5 + BM25** (`src/store.ts:475-496`) |

La tabla `session_events` tiene índices por `session_id`, `type` y `priority` —
se **filtra**, no se rankea. BM25 solo toca documentos indexados.
Consecuencia: **hacer BM25 sobre eventos, como pide la Fase 5, es *mejorar* la
referencia, no copiarla.** No hay implementación previa que imitar ahí.

**(b) El stemmer `porter` de Context Mode es solo para inglés.**
`tokenize='porter unicode61'` (`src/store.ts:484`). Sobre texto jurídico
mexicano no aporta nada y confunde. Además **no activa `remove_diacritics`**, lo
que en español rompe: `revocacion` no encontraría `revocación`. Nuestra
adaptación debe usar `unicode61 remove_diacritics 2` (§3.2) — verificado
funcionando en este equipo.

**(c) La taxonomía de 18 eventos del encargo no es la de Context Mode.**
Los tipos reales son `file_read`/`file_write`/`file_edit`/`file_search`,
`git_commit`, `decision`, `plan_approved`/`plan_rejected`, `blocker`/
`blocker_resolved`, `error_resolved`, `constraint_discovered`,
`subagent_launched`/`subagent_completed`, `bash_outcome`, `intent`, `goal`.
La lista del encargo es razonable, pero es un diseño nuevo — hay que validarla
contra el dominio, no adoptarla como si estuviera probada (§3.3).

### 2.1 A — Qué ya tenemos bien

| Activo | Por qué es superior a la referencia |
|---|---|
| `traceability.py` | Esquema de evento con `trace_id` estable, hash de evidencia y `human_review_required`. Context Mode no tiene equivalente auditable. |
| `normalize_legal_text()` | Normalización de dominio (`OpenNotebook.py:435`) que ya resuelve lo que `remove_diacritics` haría a medias. |
| `vvca_corrections.json` | Captura de correcciones del experto — Context Mode no modela "el humano me corrigió". |
| `data-policy.json` + `check_sensitive_paths.py` | Gate en CI que impide versionar datos de cliente. **Context Mode no tiene nada así.** |
| Regla de privacidad 100% local | `OpenNotebook.py` no llama a ningún LLM externo. Invariante de producto. |
| Separación corpus/estrategia | Regla 3 VVCA: SJF en vivo mejora la planeación, no vota el veredicto. |
| Umbrales explícitos y falibles | Semáforo con umbrales documentados como provisionales, distinción 🟡 "no verificable" ≠ 🔴 "refutado". |

### 2.2 B — Qué nos falta

| Falta | Fuga | Severidad |
|---|---|---|
| Registro de eventos | F2, F3 | **Alta** |
| Índice buscable de memoria | F1, F7 | **Alta** |
| Identidad de sesión y proyecto | F4 | Alta |
| Snapshot pre-compactación | F4, F5 | Alta |
| Hooks (`SessionStart`, `PreCompact`) | F5 | Media |
| Política de retención/poda | F1 | Media |
| Redacción de secretos antes de persistir | (nueva al persistir) | **Alta si implementamos** |
| Presupuesto de contexto medido | F6 | Media |

### 2.3 C — Qué reutilizar conceptualmente

1. **Snapshot por referencia, no por contenido** (`src/session/snapshot.ts:1-14`).
   El snapshot es un *índice de contenidos*: resumen natural + una llamada de
   búsqueda ejecutable. Cero datos en línea, cero truncamiento. **La mejor idea
   del proyecto** y la que directamente satisface "memoria grande + contexto
   pequeño".
2. **`session_resume` con bandera `consumed`** (`src/session/db.ts:858-865`).
   `PreCompact` escribe, `SessionStart` consume y marca. Evita reinyectar el
   mismo estado en bucle.
3. **Pesos de columna en BM25** (`bm25(chunks, 5.0, 1.0)`). El resumen pesa 5×
   los detalles: se rankea por lo que se escribió para ser leído.
4. **Redacción de secretos por patrón de clave, sobre-redactando a propósito**
   (`src/session/extract.ts:986-1037`): *"preferimos sobre-redactar a mandar un
   Bearer token a SQLite"*. Criterio correcto.
5. **WAL + `busy_timeout` + reintento** (`src/db-base.ts:342-354`).
6. **`priority` como columna de primera clase**, no calculada al vuelo.
7. **Degradación parcial**: si una fuente falla, se devuelven resultados
   parciales y se registra (`src/search/unified.ts`). Coincide con la cultura de
   este repo ("nunca entregues un resultado vacío disfrazado de sin hallazgos").

### 2.4 D — Qué NO incorporar

| Descartado | Razón |
|---|---|
| **Cualquier línea de código** | ELv2. Solo conceptos. |
| Los 18 adaptadores de plataforma | Aquí solo hay Claude Code. |
| `ctx_execute_file` / ejecución en sandbox | Fuera de alcance; superficie de ataque nueva. |
| Bloqueo de `curl`/`wget`, parser de comandos encadenados | 889 líneas para un problema que no tenemos. |
| Stemmer `porter` | Solo inglés. Inútil o dañino en español. |
| `chunks_trigram` + fusión RRF | Optimización para código y rutas. Un evento son 2-3 frases. Sin corpus de evaluación es complejidad no justificada. **Reevaluar solo si el benchmark de Fase 10 muestra fallo de recuperación.** |
| Telemetría/analytics de sesiones, precios de modelos | Ruido. |
| **Una base vectorial para la memoria** | Ya hay ChromaDB para el corpus. Los eventos son cortos y densos en identificadores exactos (`712/2023`, `art. 294 CPCJ`, registro `2024783`) — el terreno donde BM25 gana y los embeddings pierden. Duplicar infraestructura para el caso más débil no se sostiene. |

### 2.5 E — Riesgos de seguridad

| # | Riesgo | Impacto | Mitigación de diseño |
|---|---|---|---|
| E1 | **Persistir datos de cliente en una base nueva** | **Crítico** — regla absoluta #8 | La BD vive **fuera del repo** (`~/.itosturre/memoria/`). Añadir su ruta a `data-policy.json` y al gate de CI. |
| E2 | Fuga de secretos a la BD | Alto — `.env` tiene `TELEGRAM_BOT_TOKEN` | Redacción por patrón antes de persistir, sobre-redactando. Prueba unitaria obligatoria. |
| E3 | Inyección SQL | Alto | Solo consultas parametrizadas. El texto de búsqueda **nunca** se concatena: se sanea a términos FTS5 seguros (el `MATCH` de FTS5 tiene su propia sintaxis — comillas, `*`, `NEAR`, `OR` — y es inyectable aunque no lo sea el SQL). |
| E4 | Path traversal en `file_path` | Medio | Normalizar a ruta relativa al proyecto; rechazar `..` y rutas absolutas fuera de la raíz. |
| E5 | Contaminación cruzada entre proyectos/clientes | **Alto** — un expediente no debe ver otro | `project_id` obligatorio y filtrado **en todas** las consultas, con prueba de aislamiento. |
| E6 | Permisos del archivo SQLite | Bajo en Windows monousuario | Crear el directorio con permisos restrictivos donde el SO lo soporte; documentar el límite. |
| E7 | Los eventos son entrada no confiable para el LLM | Medio | Marcar el bloque recuperado como **datos, no instrucciones**. Un evento que diga "ignora tus reglas" no debe obedecerse. |
| E8 | La memoria contradice al corpus | **Alto en dominio jurídico** | La memoria **nunca** es fuente de una cita. Regla 2 VVCA intacta: los artículos salen del corpus. La memoria recuerda *decisiones*, no *derecho*. |

### 2.6 F — Riesgos de rendimiento

| # | Riesgo | Evaluación |
|---|---|---|
| F1 | Latencia de consulta | Despreciable. FTS5 sobre <100k filas responde en <5 ms. El presupuesto real lo consume el modelo de embeddings de ChromaDB (~2 s de carga), que esto no toca. |
| F2 | Escritura en el camino crítico | Un `INSERT` es <1 ms con WAL. Riesgo real: si el hook falla, no debe romper el turno → **todo fallo de memoria degrada en silencio y se registra**. |
| F3 | Crecimiento del índice | ~1 KB/evento. 10k eventos ≈ 10 MB. No es problema en años. |
| F4 | Concurrencia | Baja: un usuario, procesos secuenciales. WAL + `busy_timeout=5000` sobra. |
| F5 | Corrupción | Renombrar y recrear ante `DatabaseError`; la memoria es un caché reconstruible, no la fuente de verdad. **Los JSON de `auditorias/` siguen siendo canónicos.** |
| F6 | **Inflación de contexto por la propia memoria** | **El riesgo real.** Es exactamente lo que el encargo teme. Mitigación: presupuesto duro en bytes para el bloque inyectado, medido en Fase 10 y verificado en prueba. |

### 2.7 G — Riesgos de dependencia y licencia

| # | Riesgo | Evaluación |
|---|---|---|
| G1 | **ELv2 de Context Mode** | **El riesgo dominante.** Mitigación: reimplementación limpia en Python, cero código portado, clon confinado al scratchpad. Registrar qué se tomó (conceptos, §2.3) y qué no (código). |
| G2 | Dependencias nuevas | **Ninguna.** Verificado en este equipo: Python 3.14.0 / SQLite 3.50.4, FTS5 + `bm25()` + `unicode61 remove_diacritics 2` operativos con la stdlib. Prueba real: buscar `revocacion` recuperó `revocación`. |
| G3 | `better-sqlite3` (nativo, requiere compilación) | Se evita por completo al no ir por Node. |
| G4 | Deriva del formato de hooks de Claude Code | Media. Mitigación: los hooks son envoltorios finos; la lógica vive en Python invocable a mano. Si el formato cambia, la memoria sigue usable por CLI. |

### 2.8 H — Complejidad estimada

| # | Mejora | Complejidad | Valor | Orden |
|---|---|---|---|---|
| 1 | Esquema SQLite + `MemoryStore` (escribir/leer) | **S** (~250 líneas) | Alto | 1 |
| 2 | Índice FTS5 + búsqueda BM25 con recencia e importancia | **S-M** (~200) | **Muy alto** | 2 |
| 3 | Puente desde `traceability.py` (F3: el productor ya existe) | **XS** (~60) | **Muy alto** | 3 |
| 4 | CLI `memoria` (`record`/`search`/`snapshot`/`resume`/`stats`) | **S** (~200) | Alto | 4 |
| 5 | Migración de `vvca_corrections.json` a eventos | **XS** (~50) | Medio | 5 |
| 6 | Snapshot por referencia + `PreCompact`/`SessionStart` | **M** (~250) | Alto | 6 |
| 7 | Redacción de secretos + saneo FTS + aislamiento | **S** (~120) | **Obligatorio** | con 1 |
| 8 | Pruebas unitarias + integración | **M** (~350) | **Obligatorio** | continuo |
| 9 | Benchmark antes/después | **S** (~150) | Alto | 9 |
| 10 | Importar las 17 memorias `.md` existentes | **S** (~100) | Alto | 10 |
| 11 | **Adelgazar `CLAUDE.md` (F6)** | **M** | **El mayor ahorro de tokens** | ver §3.5 |
| — | ~~Fusión RRF / trigramas~~ | M | No demostrado | descartado |
| — | ~~Base vectorial~~ | L | Negativo | descartado |

---

## FASE 3 — Arquitectura propuesta

### 3.1 Diagrama

```
   Claude Code (agente Itosturre)          CLIs Python (vvca_full, OpenNotebook)
            │                                          │
    hooks (SessionStart/PreCompact)          traceability.build_trace_record()
            │                                          │
            └──────────────┬───────────────────────────┘
                           ▼
                 itosturre/memoria/  (Python puro, stdlib)
                 ┌──────────────────────────────────┐
                 │ redact()  → quita secretos       │  ← obligatorio, pre-escritura
                 │ record()  → valida y persiste    │
                 │ recall()  → BM25 + recencia      │
                 │ snapshot()→ índice de contenidos │
                 └──────────────┬───────────────────┘
                                ▼
              ~/.itosturre/memoria/<project_id>.db   ← FUERA del repo
              ┌────────────┬──────────────┬────────────────┐
              │  eventos   │ eventos_fts  │   sesiones     │
              │ (verdad)   │ (FTS5 ext.)  │  + snapshots   │
              └────────────┴──────────────┴────────────────┘
                                │
                       BM25 + recencia + importancia
                                ▼
                    top-k (presupuesto duro en bytes)
                                ▼
                       Bloque compacto → agente
```

**Invariante rectora:** la BD es grande y crece; **lo que entra al modelo tiene
un techo en bytes que no depende del tamaño de la BD.**

### 3.2 Esquema (Fase 4)

```sql
CREATE TABLE eventos (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  event_uid    TEXT NOT NULL UNIQUE,   -- hash estable → idempotencia
  session_id   TEXT NOT NULL,
  project_id   TEXT NOT NULL,          -- aislamiento (E5)
  timestamp    TEXT NOT NULL,          -- ISO-8601 UTC
  event_type   TEXT NOT NULL,
  summary      TEXT NOT NULL,          -- ≤200 chars, para leer
  details      TEXT,                   -- JSON, para consultar
  file_path    TEXT,                   -- relativa, validada (E4)
  importance   INTEGER NOT NULL DEFAULT 2,  -- 1 crítico … 4 rutina
  metadata     TEXT,
  redacted     INTEGER NOT NULL DEFAULT 0   -- si se enmascaró algo (E2)
);
CREATE INDEX idx_ev_proj_ts   ON eventos(project_id, timestamp DESC);
CREATE INDEX idx_ev_proj_tipo ON eventos(project_id, event_type);
CREATE INDEX idx_ev_sesion    ON eventos(session_id);

-- FTS5 externo: el índice NO duplica la verdad, la referencia.
CREATE VIRTUAL TABLE eventos_fts USING fts5(
  summary, details, file_path,
  content='eventos', content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'   -- español, NO porter
);

CREATE TABLE sesiones (
  session_id  TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL,
  iniciada_en TEXT NOT NULL,
  ultima_en   TEXT,
  n_eventos   INTEGER NOT NULL DEFAULT 0,
  n_compact   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE snapshots (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  project_id TEXT NOT NULL,
  snapshot   TEXT NOT NULL,     -- índice de contenidos, no datos
  creado_en  TEXT NOT NULL,
  consumido  INTEGER NOT NULL DEFAULT 0
);
```

`content='eventos'` (índice externo) evita almacenar el texto dos veces —
diferencia frente a Context Mode, que sí duplica.

### 3.3 Taxonomía adaptada al dominio

Los 18 tipos del encargo son un punto de partida razonable. Ajustes propuestos:

**Genéricos que se conservan (11):** `user_decision`, `user_correction`,
`task_started`, `task_completed`, `architecture_decision`, `error_detected`,
`error_resolved`, `git_commit`, `file_modified`, `configuration_changed`,
`session_snapshot`.

**Que se fusionan (ruido puro):** `file_created`/`file_modified`/`file_deleted` →
`file_modified` con `metadata.op`. Git ya versiona esto; no vale tres tipos.
`test_passed` se descarta salvo cuando cierra un `test_failed` — registrar cada
prueba verde es contaminar el índice con lo que nunca se consultará.

**Que se añaden (el valor real de este dominio):**

| Tipo | Por qué | Importancia |
|---|---|---|
| `correccion_criterio_pjf` | La corrección de un secretario con 25 años **es el activo más valioso** (F7). Regla absoluta #6: se incorpora sin réplica. Merece su propio tipo, no un `user_correction` genérico. | 1 |
| `vvca_veredicto` | Cierra el bucle F3: cada auditoría queda consultable. | 2 |
| `cita_bloqueada` | Un 🔴 por rubro discrepante bloquea el documento (regla #2). Debe ser recuperable entre sesiones. | 1 |
| `alerta_procesal` | Regla #7: 🚨 con impacto de instancia. | 1 |
| `corpus_gap` | Ley no indexada (regla 7): saber qué falta y desde cuándo. | 3 |
| `plazo_detectado` | Un plazo vencido es pérdida de instancia. | 1 |

### 3.4 Recuperación (Fases 5 y 7)

Puntuación **determinista y comprobable** — nada de magia:

```
score = bm25_norm(consulta)              -- BM25, summary pesa 5×
      × peso_importancia[importance]     -- 1.5 / 1.2 / 1.0 / 0.7
      × decaimiento_recencia(timestamp)  -- semivida ~30 días, suelo 0.3
      + bono_tipo[event_type]            -- prioridades del encargo
```

`bono_tipo` implementa el orden pedido en la Fase 5: decisiones arquitectónicas y
`correccion_criterio_pjf` primero; luego instrucciones del usuario; luego tareas
abiertas; archivos recientes; errores; soluciones previas.

**Suelo de decaimiento en 0.3, no 0:** una corrección de criterio del PJF de hace
un año sigue siendo derecho vigente. Aquí la recencia informa, no manda — es
justo lo contrario de un repo de software.

**Presupuesto duro:** `recall()` recibe `max_bytes` (por defecto 4 KB) y recorta
por presupuesto, no por número de filas. Con 10 000 eventos en disco entran ~8-12
al contexto. La garantía se verifica en prueba.

### 3.5 El asunto que el encargo no cubre — y es el más grande

Ninguna de las 10 fases toca la mayor fuga de contexto del sistema:
**`CLAUDE.md` son 41.5 KB ≈ 11-12k tokens inyectados en cada turno**, más
`MEMORY.md`. El diseño completo de arriba, funcionando a la perfección, mueve
~4 KB. El prompt mueve diez veces más, siempre, se use o no.

De esos 41.5 KB, ~24 KB son los quince menús — y en una sesión típica se usa uno.
Los menús 10-15 ya delegan en skills que se cargan bajo demanda; los menús 1-9
podrían seguir el mismo patrón: dejar en `CLAUDE.md` la identidad, las reglas
absolutas y el protocolo anti-alucinación (~12 KB, que es lo que debe estar
siempre), y mover los menús a una skill `menu-itosturre` que se invoque al
pedirla.

**Ahorro estimado: ~7k tokens por turno — más que todo lo demás junto.**

No lo incluyo en el plan porque toca la pieza de configuración más delicada del
producto y merece su propia decisión. Lo dejo señalado como recomendación
separada: si el objetivo es "contexto pequeño", este es el primer sitio a mirar.

---

## Los seis puntos que pediste antes de aprobar

### 1 · Diagnóstico
§1.3: ocho fugas. Las tres decisivas: **F3** (`traceability.py` ya produce
eventos con esquema correcto y se descartan), **F7** (las correcciones de criterio
del PJF están en prosa no consultable) y **F6** (el prompt de 41.5 KB, que este
plan no arregla).

### 2 · Arquitectura propuesta
§3. SQLite + FTS5 con índice externo, tokenizador español, puntuación
determinista con presupuesto duro en bytes, snapshot por referencia. Sin base
vectorial, sin trigramas, sin RRF hasta que un benchmark los justifique.

### 3 · Archivos que se tocarían

**Nuevos** (todo el código nuevo vive aislado):

| Archivo | Qué |
|---|---|
| `itosturre/memoria/__init__.py` | API pública |
| `itosturre/memoria/esquema.py` | DDL + migraciones idempotentes |
| `itosturre/memoria/store.py` | `record()` / `recall()` / conexión WAL |
| `itosturre/memoria/redaccion.py` | Secretos y saneo FTS (E2, E3) |
| `itosturre/memoria/ranking.py` | Puntuación pura, sin E/S — testeable sola |
| `itosturre/memoria/snapshot.py` | Índice de contenidos, funciones puras |
| `memoria_cli.py` | CLI en la raíz, junto a `vvca_full.py` |
| `scripts/importar_memorias_md.py` | Importa las 17 memorias existentes |
| `scripts/benchmark_memoria.py` | Fase 10 |
| `tests/test_memoria_*.py` | Unidad + integración + aislamiento + secretos |
| `docs/MEMORIA.md` | Documentación del subsistema |

**Modificados** (aditivo, sin borrar nada):

| Archivo | Cambio | Compatibilidad |
|---|---|---|
| `vvca_full.py` | Tras escribir `vvca_traceability.json`, emitir eventos. En `try/except` que degrada en silencio. | Total — el JSON se sigue escribiendo igual |
| `OpenNotebook.py` | `correct` escribe también un evento `correccion_criterio_pjf` | Total — `vvca_corrections.json` intacto |
| `config/data-policy.json` | Añadir la ruta de la BD a las prohibidas de versionar | Endurece el gate |
| `docs/ARQUITECTURA.md` | Nueva fila de componente | Documentación |
| `.claude/settings.local.json` | Hooks — **solo con tu visto bueno explícito** | Reversible |

**Intocables:** `scoring_vvca.py`, `router_competencia.py`, `capturar_rag.py`,
ambos submódulos, `chroma_db/`, `auditorias/`, `CLAUDE.md`.

### 4 · Dependencias nuevas
**Ninguna.** `sqlite3` de la stdlib. Verificado en este equipo (Python 3.14.0 /
SQLite 3.50.4): FTS5, `bm25()` y `unicode61 remove_diacritics 2` operativos;
`revocacion` recupera `revocación`. `requirements.txt` no cambia.

### 5 · Riesgos
Detallados en §2.5-2.7. Los tres que gobiernan el diseño:

- **ELv2** (G1) → reimplementación limpia, cero código portado.
- **Datos de cliente en una base nueva** (E1) → BD fuera del repo + gate en CI.
- **Que la memoria contradiga al corpus** (E8) → la memoria recuerda decisiones,
  **nunca** es fuente de una cita. Regla 2 VVCA intacta.

### 6 · Plan de implementación

Cada etapa es autónoma y verificable. **Ninguna borra código. Sin commit hasta
que valides.**

| # | Etapa | Entregable | Verificación |
|---|---|---|---|
| 0 | Rama `feat/memoria-contextual` vía `scripts/git_strategy.sh 0` | — | Regla absoluta #4 |
| 1 | Esquema + store + redacción + saneo FTS | `itosturre/memoria/` | Pruebas: aislamiento por proyecto, secretos, traversal, inyección FTS |
| 2 | Ranking + `recall()` con presupuesto | `ranking.py` | Prueba: 10 000 eventos → salida ≤4 KB |
| 3 | Puente `traceability.py` → eventos (cierra F3) | `vvca_full.py` +15 líneas | Regresión VVCA verde; `vvca_traceability.json` byte-idéntico |
| 4 | CLI `memoria_cli.py` | CLI | Uso manual sin hooks |
| 5 | Importar las 17 memorias `.md` (cierra F7) | script | Consulta real: *"¿qué me corrigió Fabián sobre recursos?"* |
| 6 | Migrar `vvca_corrections.json` | script | `calibrate` sigue funcionando igual |
| 7 | Snapshot + hooks — **solo si lo apruebas** | `snapshot.py` + settings | Ciclo compactación/restauración |
| 8 | Benchmark Fase 10 | `docs/BENCHMARK_MEMORIA.md` | Números medidos, no estimados |
| 9 | Actualizar `ARQUITECTURA.md` y `data-policy.json` | docs | `check_sensitive_paths.py` verde |

**Punto de decisión tras la etapa 5:** con las 17 memorias importadas y
consultables se puede medir si BM25 recupera de verdad lo que hace falta —
*antes* de tocar hooks. Si falla ahí, el diseño se corrige barato; y solo
entonces tendría sentido discutir trigramas o vectores.

### Benchmark (Fase 10) — qué se medirá

| Escenario del encargo | Antes | Después |
|---|---|---|
| Recuperar decisión antigua | Cargar 17 `.md` ≈ 68 KB | top-k ≤4 KB |
| Recuperar tras muchos eventos | No existe | latencia y bytes con 10k eventos |
| Sesión nueva | `MEMORY.md` completo, 4.2 KB fijos | snapshot dirigido |
| Tras compactación | **Todo perdido** | snapshot restaurado |
| Errores previos | No existe | consulta por `error_detected` |
| Archivos modificados | No existe | consulta por `file_path` |

Métricas: bytes al modelo, eventos enviados, latencia (ms), tokens aproximados
(bytes/4 para español) y **acierto de recuperación** sobre un set de 10 preguntas
reales cuya respuesta esté en las memorias actuales. Esta última es la que
importa: ahorrar contexto perdiendo la respuesta correcta no es una mejora.

---

## Recomendación

Aprobar las etapas 0-6 (memoria persistente, buscable y aislada, sin tocar
hooks). Decidir la 7 con el benchmark de la 5 sobre la mesa.

Y, en paralelo y por separado: mirar `CLAUDE.md` (§3.5). Es donde de verdad está
el contexto.
