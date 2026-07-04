# Revisión técnica — uso del corpus legal y del scraper SJF

> **Revisión de solo lectura (4-jul-2026), sin cambios de código.** Handoff para continuar
> con sesiones Opus/Sonnet. Autor de la revisión: Claude (Fable 5), con conocimiento directo
> del código construido en las sesiones de jun-jul 2026. Evidencia: exploración con agentes
> (mapas file:line), corridas reales del pipeline y hallazgos empíricos del workflow fiscal.

---

## Estado de implementación (4-jul-2026 · sesión Opus)

Ejecutadas las mejoras de mayor valor/menor riesgo. Regresión verde tras cada una (caso_001 apto).

| # | Mejora | Estado | Commit | Nota |
|---|--------|--------|--------|------|
| 1 | Cerrar checkpoint fiscal (skill medios-defensa-fiscal) | ✅ HECHO | skills `@a27e407` · padre `@01e32d4` | Gate VVCA 91/91 verificadas, veredicto apto |
| 2 | **P0 · Retrieval por metadata (source+article)** | ✅ HECHO | padre `@e531987` | Bug real corregido: 'art. 121 CFF' devolvía art. 116. Piso `metadata_verificado`. 58/91 citas fiscales ahora deterministas. +2 invariantes |
| 5b | **P1 · Ventana de frescura de vigencia** (caché) | ✅ HECHO | scraper `@5f8935f` · padre `@121a9fe` | `[VIGENCIA?]` si 'vigente' viene de caché > 7d; recomienda `--no-cache` para uso procesal final |
| 3 | P0 · Re-chunking por fracción (re-ingesta) | ⏸️ DIFERIDO | — | Cambia 25k chunks del índice, exige los PDFs y arriesga la regresión. El filtro P0 ya captura la mayoría del valor sobre los labels existentes (99% poblados). El re-chunking EXTIENDE el boost a leyes con label pobre (ej. LFPCA: solo 7 labels) y habilita el semáforo por fracción. Hacer con re-ingesta controlada + comparar regresión antes/después |
| 4 | P1 · Fallback JSON del SJF + mergear vigilancia | ⏸️ DIFERIDO | — | Requiere la rama `reconcile-jurisprudencia` (@21afe60, NO borrar) que ya resolvió el POST /tesis; merge de 10 commits divergidos + validación en vivo. Desfragiliza el parseo por innerText |
| 6 | P2 · Scoring literal de citas (difflib/rapidfuzz) | ⏸️ DIFERIDO | — | Alto valor anti-alucinación PERO alto riesgo de FALSO POSITIVO (citas legales legítimamente parciales). En un núcleo que "nunca debe tachar de falsa una cita válida", exige calibración cuidadosa + corpus de prueba. Diseño seguro propuesto: solo disparar sobre texto ENTRECOMILLADO (el autor afirma verbatim) comparado contra el chunk del artículo ya recuperado por metadata; difflib es stdlib. Merece su propio pase |
| 6b | P2 · Metadato temporal por chunk (fecha reforma DOF) | ⏸️ DIFERIDO | — | Necesita re-ingesta (como #3). Prerrequisito del diff DOF de la vigilancia |
| — | Unificar taxonomía de fuerza (Python 95/72 vs TS 92/72/60) | ⏸️ DIFERIDO | — | Consistencia de reporte; bajo valor, no urgente |
| 7 | Golden set (~30 citas + ~30 plazos) + doc real | ⛔ BLOQUEADO | — | Requiere a Fabián (verdad de terreno) |

**Regla seguida:** todo cambio aditivo, `run_regression.py` verde antes de merge; padre por `feat/*`
(REGLA #4); submódulo scraper y repo de skills con su disciplina propia; nunca arrastrar el
cambio ajeno de `itosturre-validator/SKILL.md`.

---

## Veredicto general

La arquitectura es **sana y correcta en su decisión más importante**: separar
**verificación de citas** (corpus local ChromaDB + `jurisprudencia/*.json` → alimenta el
veredicto VVCA) de **búsqueda estratégica** (scraper SJF en vivo → propone, no veredicta).
Esa separación —documentada en el docstring de `scoring_vvca.py`— es lo que hace honesto al
sistema: el veredicto nunca depende de una fuente viva que puede fallar a media auditoría.

Las incorporaciones recientes (fuerza vinculante, vigencia/falso-verde, explicabilidad,
disclaimer graduado, caché del scraper, router de competencia) cierran los riesgos más
graves del roadmap. Lo que queda no son agujeros de diseño sino **tres cuellos de precisión
y dos de integración**, priorizados abajo. Ninguno exige rediseño; todos son incrementales.

---

## 1. Corpus / RAG (`OpenNotebook.py`)

### Lo que está bien (no tocar)
- **Embeddings** `intfloat/multilingual-e5-large` con prefijos `query:`/`passage:` correctos
  (`encode_query`, `get_collection`) — uso canónico del modelo.
- **Normalización de acrónimos solo en la query** (`normalize_legal_text`), nunca en el
  corpus indexado — decisión correcta: el índice conserva el texto oficial.
- **Sticky-law resolver** (`resolve_law_source_backward`, ventana 600 chars) + `LAW_ALIASES`
  (90+) + `LAW_SOURCE_MAP` (44 fuentes) — resuelve el problema real de "art. 16" ambiguo.
- **Anti-falso-🟢 estructural**: cap a 84 sin ley identificada; −15 por fuente distinta;
  tesis no encontrada = 🟡 NO VERIFICABLE (no 🔴); un rubro discrepante bloquea sin promediar.
- **Cobertura verificable**: `check_corpus.py` 44/44; `run_regression.py` con 25+ invariantes
  como gate pre-merge — pocos proyectos legales tienen esto.

### Cuellos de precisión (prioridad para Opus/Sonnet)

**P0 — Recuperación por similitud pura donde debería haber filtro por metadata.**
Hoy `audit()` verifica un artículo lanzando UNA query semántica y confiando en que el chunk
correcto quede arriba. El chunker ya guarda metadata (`source`, `article`, `page`), pero la
consulta **no filtra por ella** (`collection.query` sin `where` por artículo). Evidencia
empírica de esta sesión: el workflow fiscal tuvo que anotar "re-verificar con consulta
dirigida: el chunk del plazo no siempre es recuperado" para el art. 13 LFPCA — el precepto
ESTÁ indexado pero la similitud no siempre lo trae. **Recomendación:** verificación en dos
pasos: (1) `where={"source": ley, "article": N}` para match exacto de metadata; (2) similitud
solo como fallback/desempate. Es la mejora de mayor precisión al menor costo: convierte la
verificación de artículos de probabilística a determinista cuando la metadata existe.

**P0 — Chunking corta preceptos largos en la parte relevante.**
`MAX_CHUNK_SIZE=2000` chars parte artículos largos. Evidencia empírica real: la
investigación fiscal encontró chunks truncados justo en la parte operativa de los arts. 117,
127 y 144 CFF (la skill lo marca honestamente como "[VERIFICAR EN DOF] — chunk truncado",
pero eso degrada 🟢 alcanzables a 🟡). **Recomendación:** re-chunking por unidad normativa
(artículo íntegro; si excede, partir por fracción/inciso extendiendo `_SPLIT_PATTERNS` /
`extract_section_label` y guardando `fraction` en metadata). Esto además habilita el quick
win #7 del roadmap (semáforo a nivel fracción — hoy un 🟢 de artículo puede ocultar una
fracción equivocada, p. ej. causales del art. 61 LA).

**P1 — Sin verificación literal del texto citado.** El coseno da 🟢 a paráfrasis que
tergiversan ("72 h" vs "96 h", "podrá" vs "deberá"). El quick win #6 del roadmap (fuzzy-match
del entrecomillado con `rapidfuzz` contra el chunk) sigue pendiente y es barato.

**P1 — Sin conciencia temporal.** La única señal de vigencia de una ley es el "2026" del
nombre del PDF. Falta `fecha_ultima_reforma_dof`/`fecha_corte_corpus` por chunk (prerrequisito
del diff DOF; la vigilancia ya existe en la rama `reconcile-jurisprudencia`, sin mergear).

**P2 — Costo de arranque por invocación.** Cada CLI recarga e5-large en CPU. Para skills que
verifican 10+ artículos conviene un modo batch (varias queries por proceso — el workflow
fiscal ya lo hizo a mano) o un proceso residente. No urgente, sí molesto.

**P2 — Gaps de corpus conocidos:** LFDC y RISAT (los marca la skill fiscal), LNEDo
(extinción de dominio), y el corpus sin respaldar en Drive.

---

## 2. Scraper SJF (`services/itosturre-scraper/`)

### Lo que está bien (no tocar)
- **Caché por registro** (`.sjf_cache/`, TTL 30 días, `--no-cache`) + 2 reintentos con
  backoff + detección `[LAYOUT?]` que evita envenenar la caché — probado con red bloqueada:
  la auditoría se completa offline. El single point of failure quedó mitigado.
- **Parser de vigencia** (sección NOTAS, patrones afirmativos + guardia de negación,
  "precisión > cobertura"): 9/9 en test offline y 0 falsos positivos en 7 tesis reales en
  vivo. Es el diferenciador anti-falso-verde y está bien acotado.
- **Capa 2 (`scorePorContexto`/`calcularRelevancia`) etiquetada como estratégica** y separada
  del veredicto de citas — coherente con la filosofía.
- **Screenshots como evidencia** — pieza clave de la demo comercial.

### Cuellos (prioridad para Opus/Sonnet)

**P1 — Parseo por `innerText` línea a línea = fragilidad estructural.** `[LAYOUT?]` avisa,
pero no hay plan B. La rama `reconcile-jurisprudencia` (@21afe60, NO borrar) ya resolvió el
contrato real del **POST /tesis del microservicio del SJF** para la vigilancia. 
**Recomendación:** unificar — usar ese endpoint JSON como fuente primaria del detalle de
tesis (campos estables) y dejar Playwright solo para screenshot/fallback. Desfragiliza el
foso entero de un golpe y probablemente acelere 10×.

**P1 — TTL de caché vs vigencia.** Los datos de una tesis publicada no cambian… excepto su
vigencia (puede ser superada en cualquier momento). Con TTL 30 días, una auditoría servida
de caché puede dar 🟢 a una tesis superada ayer. **Recomendación:** para auditorías de uso
procesal final, forzar `--no-cache` (o TTL corto solo para el campo vigencia); documentarlo
en el protocolo VVCA.

**P2 — Taxonomías paralelas sin unificar.** Python clasifica fuerza vinculante con
`classify_fuerza_vinculante` ([J-PLENO]/[J-SALA]/[PR]/[PC]/[J-TCC]/[SCJN-P]/[TA], scores
95/72) y el TS tiene su propio `scorePorTipo` (92/72/60/40, sin [PR]/[PC]). Dos verdades
sobre lo mismo confunden reportes. **Recomendación:** una sola fuente (portar el clasificador
al output del scraper o reclasificar en Python al promover).

**P2 — Screenshot `fullPage: false`** puede dejar fuera la sección NOTAS — justo la evidencia
de una vigencia perdida. Para tesis con `estado_vigencia != vigente`, capturar también NOTAS.

**P2 — `fetch_tesis_detalle.py` (raíz)** duplica scraping en Python sin parseo estructurado.
Candidato a deprecar cuando exista el fallback JSON.

---

## 3. Integración corpus ↔ scraper (lo sistémico)

- **El puente es manual.** `scripts/promover_tesis.py` (upsert seguro, probado end-to-end)
  existe, pero nadie lo llama automáticamente: el `estado_vigencia` capturado por el scraper
  solo llega al veredicto si alguien corre la promoción. **Recomendación:** invocarlo como
  paso final opcional de `vvca_full.py` (flag `--promover`), y añadir la **re-auditoría
  longitudinal** del roadmap (revalidar citas de escritos ya presentados cuando cambie la
  vigencia de una tesis promovida).
- **El corpus local de jurisprudencia envejece en silencio.** `jurisprudencia/*.json` no
  tiene fecha de verificación por tesis. Añadir `verificado_el` al promover costaría poco y
  habilita alertas de frescura.

---

## 4. Estado pendiente (checkpoint del 1-jul, aún vigente)

Trabajo **escrito en disco, sin commitear** (verificado hoy):
1. `services/itosturre-skills/skills/medios-defensa-fiscal/SKILL.md` (27 KB, 82 artículos
   verificados contra corpus) + `README.md` del repo de skills.
2. `CLAUDE.md` del padre con el MENÚ 15 integrado.
3. Pasos restantes (en `project_fase2_readiness.md` → CHECKPOINT): gate VVCA sobre la skill,
   `install.sh`, `run_regression.py`, commits (skills → su main; padre → `feat/*` → merge).
4. Ojo: `skills/itosturre-validator/SKILL.md` tiene un cambio **ajeno** en el repo de skills
   — no arrastrarlo en el commit de la skill fiscal.

---

## 5. Orden de ataque sugerido (para la siguiente sesión Opus/Sonnet)

| # | Tarea | Tipo | Por qué primero |
|---|-------|------|-----------------|
| 1 | Cerrar el checkpoint fiscal (gate VVCA + install + regresión + commits) | housekeeping | Trabajo terminado que no está protegido en git |
| 2 | Retrieval con filtro por metadata (`where` article/law) + fallback semántico | precisión P0 | Convierte la verificación de artículos en determinista; evidencia empírica de misses |
| 3 | Re-chunking por unidad normativa + metadata `fraction` (re-ingesta) | precisión P0 | Elimina los "chunk truncado" y habilita semáforo por fracción |
| 4 | Fallback JSON del SJF (aprovechar el POST /tesis de la rama `reconcile-jurisprudencia`) + mergear vigilancia | resiliencia P1 | Desfragiliza el scraper y desbloquea la vigilancia DOF/SJF ya escrita |
| 5 | Política de caché vs vigencia (`--no-cache` en auditoría final) + unificar taxonomía de fuerza | corrección P1 | Coherencia del veredicto |
| 6 | Scoring literal (rapidfuzz) + metadato temporal por chunk | precisión P2 | Quick wins ya especificados en el roadmap |
| 7 | Golden set (~30 citas + ~30 plazos, con Fabián) + validación con escrito real | datos | Sigue siendo el prerrequisito para vender garantías |

**Regla de oro para quien continúe:** todo cambio al núcleo debe ser aditivo y pasar
`python scripts/run_regression.py` (caso_001 apto, sin 🔴) antes de merge; en el padre,
nunca commitear directo a main (`feat/*` → merge, REGLA #4); el repo de skills y el
submódulo del scraper tienen su propia disciplina (main directo).

---

*Documentos hermanos: `docs/brainstorm-mejoras-itosturre.md` (roadmap 90 días) ·
`docs/PROTOCOLO_VVCA.md` · memoria del proyecto (`project_fase2_readiness.md` → CHECKPOINT).*
