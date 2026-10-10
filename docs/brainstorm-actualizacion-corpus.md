# 🧠 Brainstorm — Planificación de la actualización del corpus RAG

> Generado el 2026-10-09 con un brainstorm multi-agente: 5 lentes en paralelo (arquitectura del
> índice · jurídico/temporalidad · operación · gates y loop · red team), una crítica de completitud
> y la síntesis. Cada hecho sobre el código o el índice se verificó contra la fuente (sqlite en solo
> lectura, archivo:línea, API de Drive); lo no verificado va marcado [NO VERIFICADO]. Documento de
> trabajo para el Lic. Jorge Fabián Martínez Sánchez. La IA valida, el abogado decide.

## 0. Contraste con `main` (ea478dc, 9-oct-2026) — leer primero

Este brainstorm se hizo sobre un checkout ~70 commits atrás de `main`. Contra `main`:

**Ya resuelto en `main`** (no se porta nada de la rama vieja sobre esto):

- Veredicto sin promedio: los 🔴 por artículo mandan sobre el score (§1, segunda viñeta).
- Inexistencia con el **criterio C** del responsable (2-oct-2026): un artículo no localizado en una
  ley indexada solo es 🔴 con prueba positiva de inexistencia; si no, 🟡.
- Artículos derogados → 🟡; re-ingesta **por fuente** (`ingest --fuente … --simular`, respaldo
  durable, `--restaurar`; `docs/ENTORNO.md`). Eso reemplaza el azul/verde de §1, cuarta viñeta, y
  §4: ya no hace falta reconstruir todo en staging para actualizar una ley.
- Capa de evidencia (`itosturre/evidencia/`): limpieza de LeyesBiblio, ubicación exacta de
  artículos por zona, notas de reforma, hosts oficiales.

**Medido con el motor de `main` sobre una copia de la gen-0** (casos ficticios): `audit` da 750 LA
🔴 (inexistencia acreditada), 9999 CCF 🔴, 57 CPF 🟡 (derogado), pero **15 LFT 🟢 85** aunque la LFT
indexada es de 2015, y la ruta `query` da 57 CPF 🟢 100 «literal», 750 LA 🟢 87 (apunta al
«Artículo 5o») y 15 LFT 🟢 100. Faltan dos cosas en el motor: **la ruta `query`** y **que el
veredicto conozca la vigencia**. Van en una rama de motor aparte, respetando el criterio C.

**Lo que trae `feat/vigencia-corpus-v2`** (datos y herramientas, sin tocar el veredicto):
`vigencia_corpus.py` + agenda bimestral + `cotejo_manual.py` sobre la capa de evidencia
(Regla 8 de `CLAUDE.md`); el lector de encabezados de `evidencia` ahora reconoce el subnúmero
"58-1" (antes "58-2" ubicaba el artículo 582); la vigencia solo consulta URL oficiales; el
manifiesto cubre las 47 fuentes de `LAW_SOURCE_MAP` (con LFDC, LOPDC, LOTFJA y la RMF) y una
prueba lo exige; se retiró de `LAW_SOURCE_MAP` el duplicado de la LOPJF.

## 1. Resumen ejecutivo

- **La causa raíz es la procedencia, no la velocidad de las reformas.** De las 16 fuentes en 🔴,
  **11 ya estaban desactualizadas el día que se indexaron** (19-jun-2026). Los PDF vinieron del Drive
  sin fecha ni hash, y el nombre engaña: "LEY FEDERAL DEL TRABAJO 2025.pdf" trae sello DOF 12-06-2015.
  Cada actualización debe bajar el PDF del **portal oficial** y registrar su sha256 y su sello. El Drive
  deja de ser fuente de leyes.
- **El veredicto VVCA no ve los artículos, y eso hay que arreglarlo antes que nada.** `score_rag` es
  un **promedio**. `veredicto_global` solo baja a 🟡 si ese promedio cae bajo 70, y los 🔴 por artículo
  van solo a `alerts`: puede salir «🔴 posible alucinación» junto a «🟢 apto». Por eso la vigencia y
  los artículos derogados deben entrar como **reglas de precedencia**, no como tope de score. Hasta
  entonces, regla operativa: **toda cita de una ley 🔴 se coteja a mano contra el PDF oficial** del
  reporte.
- **Actualizar el corpus no es un loop.** Reprueba el test de aptitud: no es semanal, la ingesta la
  autoriza el abogado y decidir qué versión rige es Capa 2. Lo que corresponde es un **runbook** con
  una lista de gates, y la skill solo después de 3 corridas limpias. Lo único agendado es la
  *detección*, que conviene bajar a semanal (3 GET) cuando el detector pase sus fixtures.
- **El mayor riesgo operativo es re-indexar en sitio.** `--reingest` borra la colección antes de
  reconstruirla (~50 min), y el Bash del agente se corta mucho antes. El resultado es un índice vacío
  o a medias que `audit` usa sin preguntar. Regla: **siempre azul/verde**. Construir el staging es
  preparación; la "ingesta" que tú autorizas es el **swap**. La receta del reporte ya se corrigió así.
- **Separar datos de motor.** Re-indexar arrastra defectos del motor:
  - el chunker no corta en «ARTÍCULO» en mayúsculas (LFPCA: 142 encabezados → 7 etiquetas);
  - los artículos derogados cuentan como verificados;
  - `query` da 🟢 100 fijo.
  
  Se corrigen en una release de motor aparte, para poder atribuir cualquier cambio de veredicto.
- **Nunca sobrescribir, pero sin sobre-ingeniería.** La ley aplicable al acto puede ser la versión
  anterior [fundamentos: VERIFICAR EN DOF/SJF]. Hoy basta con archivar cada PDF reemplazado con su sha
  y sus fechas. La consulta "a fecha" viene después.
- **Incidentes que no esperan:**
  - un escrito de cliente en la carpeta pública del Drive;
  - un archivo que dice ser reglamento y es la LOPJF;
  - un skill de usuario con instrucciones obsoletas que llevan justo al índice mixto.

---

## 2. Lo que sabemos (verificado)

| # | Hecho | Evidencia | Qué implica |
|---|---|---|---|
| 1 | El veredicto global **promedia** los artículos y no ve sus 🔴 | `score_rag` promedio (OpenNotebook.py:~1448); `veredicto_global` solo 🟡 si < 70 (scoring_vvca.py:26-95); las citas 🔴 van a `alerts` (OpenNotebook.py:1374-1379) | «🔴 posible alucinación» y «🟢 apto» a la vez; un tope por artículo no movería el veredicto |
| 2 | `query` da **🟢 100 fijo** a cualquier acierto por metadata | OpenNotebook.py:1613-1621 | Un artículo derogado sale 🟢 en la ruta con la que el agente redacta, igual que una mención dentro de otro artículo |
| 3 | Re-indexar todo tarda **~50 min** (embedding ≈ 90 %) | `created_at` 10:27→11:17 UTC del 19-jun, 25,330 chunks | El cómputo es barato; lo caro es la ventana destructiva y la revisión humana |
| 4 | `ingest` normal **salta** IDs existentes; `--reingest` **borra todo** antes de reconstruir | OpenNotebook.py:499-504, 639-646 | No hay forma segura de actualizar en sitio |
| 5 | `ingest` traga errores por PDF y siempre imprime "INGESTA COMPLETADA" | OpenNotebook.py:659-666 | No sirve como gate: sale 0 aunque falle |
| 6 | `audit` con corpus incompleto y sin TTY **continúa sin preguntar** | OpenNotebook.py:~1800-1808 | Durante una re-indexación en sitio se audita contra un índice parcial |
| 7 | `audit` y `run_regression` **pueden escribir** en el índice al abrirlo | `PersistentClient` + `get_or_create_collection` (OpenNotebook.py:425, 443), migraciones "apply" | Nunca correrlos contra la evidencia (gen-0) sin una copia |
| 8 | El HNSW en disco va atrasado: **935** embeddings en `embeddings_queue` | `max_seq_id` 24,396 (vector) vs 25,330 (metadata) | Copiar el directorio completo y sin escritores; los gates que leen sqlite no prueban el índice vectorial |
| 9 | **11 de 16** rojas ya estaban desactualizadas al indexar | Fechas oficiales del reporte ≤ 19-jun | La procedencia (Drive) es la causa raíz |
| 10 | El chunker no corta en **«ARTÍCULO»** en mayúsculas | LFPCA: 142 encabezados → 7 etiquetas · LFPC 212 → 19 · Const. Jal. 130 → 7 (su chunk 60 dice «4º» y trae otro artículo) · Ley de Amparo bien (271) | Re-indexar arrastra el defecto; arreglarlo cambia todo el corpus |
| 11 | Artículos **derogados** cuentan como verificados | CPF art. 57 = «(Se deroga). Artículo derogado DOF 23-12-1985»; ~570 chunks cortos «se deroga»; ninguna ruta lo detecta | Falso 🟢 por promedio (audit) o directo (query) |
| 12 | El **audit no lee la vigencia** | Ni OpenNotebook.py ni vvca_full.py consultan `reportes/vigencia_corpus/` | 🟢 a texto viejo y 🔴 "alucinación" a artículos nuevos en las 16 rojas |
| 13 | **No hay corpus local de jurisprudencia** | `jurisprudencia/` no existe en ningún checkout | Toda tesis sale 🟡; una reforma deja huérfanas las tesis sobre el texto anterior |
| 14 | «Reglamento organico poder judicial…pdf» **es la LOPJF** | sha256 idéntico `6569965c…` | Fuente fantasma: tipo manual, nunca saldrá 🔴 y congela una LOPJF vieja |
| 15 | **Escrito de cliente en el Drive público** | Un escrito de cliente (tema FOVISSSTE) en la carpeta del corpus con permiso `anyone: reader` (API de Drive). Retirado del Drive y del corpus el 2026-10-09 | 🚨 Regla 8; además `--reingest` indexa todo lo que haya en la carpeta |
| 16 | **Dos checkouts** | Índice, venv y PDF en `itosturre-agente/` (rama `fix/setup-ide-funcional` @3fa814b, sin retrieval por metadata); código nuevo en `itosturre-agente-1/` (= main) sin índice | Auditar desde el hermano corre código viejo; la receta mezcla ambos |
| 17 | Skill de usuario **`itosturre-validator` obsoleto** | SKILL.md:30 y ~128 (`ingest` normal desde rutas WSL/OneDrive), :100 (PDF a Telegram), :104-106 (VVCA manual si falla OpenNotebook) | Lleva al índice mixto, choca con la regla 9 y emitiría semáforos sin corpus |
| 18 | El bridge de WhatsApp **no consume** el RAG | Solo lo menciona en HTML de marketing (bridge-whatsapp/email_agent.py:76) | Las auditorías salen de sesiones de Claude Code: la ventana de mantenimiento es controlable |

---

## 3. ¿Loop, skill o plan? (test de aptitud)

| Sub-tarea | ≥ semanal | Reprueba sola | De punta a punta | "Hecho" objetivo | Veredicto |
|---|---|---|---|---|---|
| Detectar vigencia | ✔ (3 GET) | ✔ | ✔ | ✔ | **Schedule**: ya existe; semanal cuando pase sus fixtures |
| Descargar y validar el PDF oficial | — | ✔ (sha, sello, % de texto, título) | ✔ | ✔ | Script con gate previo a la ingesta |
| Construir el staging | ✘ | ✘ (sale 0 aunque falle) | ✔ (job fuera del Bash del agente) | — | **Preparación**, en una copia |
| Verificar la copia | — | ✔ (con gate nuevo) | ✔ | ✔ | **Lista de gates** (§8) |
| Swap = cambiar lo que leen las auditorías | ✘ | ✘ | ✘ | ✘ Capa 2 | **Tu autorización** |
| Decidir qué versión rige y desde cuándo | ✘ | ✘ | ✘ | ✘ Capa 2 | **Tu decisión** |

Orden infalible aplicado:
1. Piloto manual confiable (CFF).
2. Runbook escrito y, tras 3 corridas limpias, la skill `actualizar-corpus`.
3. La verificación como lista de gates ejecutable.
4. En schedule, solo la detección.

---

## 4. La ruta de una actualización (diseño objetivo)

| Paso | Quién | Tiempo | Qué pasa |
|---|---|---|---|
| 0. Detección | launchd | — | `vigencia_corpus.py`; hoy cada 60 días, propuesta semanal con aviso solo de cambios |
| 1. Triage | Abogado | 10-15 min | Qué entra al lote, priorizado por exposición (citas por ley en asuntos abiertos) × riesgo. Qué hacer con abrogadas, renombradas y A.I./declaratorias |
| 2. Descarga a staging | Agente | ~5 min | Desde el portal oficial, con estos controles:<br>• sha256<br>• sello del PDF ≥ fecha del listado<br>• % de páginas con texto<br>• título = nombre oficial<br>• renombre al nombre canónico<br>• **lista blanca**: solo entra lo que está en el manifiesto |
| 3. Archivo de la versión saliente | Agente | segundos | Se guardan PDF, sha, sello y fechas. Nunca se sobrescribe |
| 4. Construcción del staging | Job en segundo plano o tu Terminal | ~50 min | `CHROMA_PATH=…_next` y `--reingest` en la copia; nunca en el índice en uso |
| 5. Gates | Agente | 5-10 min | §8, cada verde con su artefacto |
| 6. Revisión | Abogado | **≤ 15 min por ciclo** | Diff por artículo **cruzado con las citas de asuntos abiertos** (`audit_rag.json` por caso). Una autorización por lote |
| 7. Swap | Abogado (confirmación tecleada) | segundos | Rename atómico; la versión anterior queda para rollback |
| 8. Constancia | Agente | segundos | Bitácora append-only en `docs/` (sin datos de clientes) + `corpus_version_id` en cada auditoría posterior |
| 9. Distribución | Abogado | minutos | Archivo local con respaldo. El Drive, si se mantiene, solo como espejo de leyes, y se avisa a clientes si toca sus materias |

---

## 5. Matriz impacto × esfuerzo

| | **Esfuerzo bajo-medio** | **Esfuerzo alto** |
|---|---|---|
| **Impacto alto** | **Quick wins:**<br>• retirar el escrito de cliente del Drive<br>• congelar la gen-0<br>• cotejo manual de citas de leyes 🔴<br>• veredicto por precedencia (sin promedio)<br>• resolver identidades<br>• fixtures del detector + detección semanal<br>• piloto azul/verde con CFF<br>• bitácora + `corpus_version_id` | **Apuestas:**<br>• hogar único del RAG con gen-0 + previa<br>• procedencia (lock con sha + URL oficial)<br>• release de motor (chunker, derogados, `query`)<br>• temporalidad (3 fechas, re-auditoría dirigida) |
| **Impacto bajo-medio** | **Rellenos:**<br>• gate estricto (`--estricto`)<br>• sondas de retrieval por Chroma<br>• tratados con revisión anual<br>• calendario manual de desplazamientos (CFPC→CNPCF) | **Evitar por ahora:**<br>• re-indexar en sitio<br>• agendar la actualización<br>• `ingest --solo --reemplazar` (ruta destructiva nueva para ahorrar ~30 min cada 2 meses)<br>• backfill de metadata sobre la gen-0 (escribe en la evidencia)<br>• histórico en la misma colección<br>• revisores-agente sin oráculo<br>• mezclar release de motor y de datos |

---

## 6. Top quick wins (ordenados)

| # | Idea | Qué resuelve | Esfuerzo | Primer paso concreto |
|---|---|---|---|---|
| 1 | **Incidente del Drive** | Regla 8 y re-publicación | Bajo | 1) Retirar el escrito del Drive y de `corpus/`.<br>2) Revisar la actividad del enlace.<br>3) Decidir si se notifica (LFPDPPP).<br>Como la carpeta estuvo en modo Editor, ningún PDF del Drive es confiable hasta cotejarlo con el portal |
| 2 | **Congelar la gen-0** | Evidencia de con qué texto se auditó desde junio, y respaldo | Bajo | Copia de solo lectura de `chroma_db/` y `corpus/` completos + sha256 de los 47 PDF |
| 3 | **Cotejo manual de citas de leyes 🔴** | Cubre el hueco mientras el VVCA no sepa de vigencia | Nulo | Regla operativa: citar del PDF oficial que enlaza el reporte (es lectura, no ingesta) |
| 4 | **Veredicto por precedencia** | El 🟢 global que esconde 🔴, derogados y leyes desactualizadas | Medio | Caso de regresión ficticio que hoy dé «🟢 apto» con un 🔴 adentro (rojo primero). Luego, en `veredicto_global`: quitar el promedio y añadir reglas para artículo 🔴, fuente con vigencia 🔴 y «(Se deroga)», sobre una **copia** del índice |
| 5 | **Resolver identidades** | Fuente fantasma y nombres que mienten | Bajo | Decidir qué era el "Reglamento orgánico" (o retirarlo de `LAW_SOURCE_MAP`); confirmar Movilidad y LPA de Jalisco renombradas |
| 6 | **Fixtures del detector + detección semanal** | La reforma a la CPEUM del 07/10/2026 quedaría invisible hasta 60 días | Bajo | Llevar a la suite los fixtures probados hoy (Frankenstein, A.I./declaratoria) y añadir «LFT 2025 con sello 2015». Después, `ITOS_VIGENCIA_CADA_DIAS=7` con aviso solo de cambios |
| 7 | **Piloto azul/verde con CFF** | La "corrida manual confiable" que exige la metodología | Medio | Receta del reporte, en un hogar de datos nuevo; el primer swap es también la migración; medir tiempos |
| 8 | **Bitácora + `corpus_version_id`** | Constancia de diligencia y procedencia | Bajo | `docs/bitacora-corpus.md` con la entrada gen-0 y la decisión sobre las 16 rojas |

---

## 7. Apuestas grandes

**1. Hogar único del RAG: gen-0 congelada + versión previa**
- *Qué es:* `~/itosturre-data/{corpus,chroma_db,archivo,staging}` (ruta sin espacios), `.env` en
  cada checkout apuntando ahí, swap por rename atómico y la versión previa para rollback. Tres
  generaciones con `flock` es más de lo que hace falta hoy.
- *Por qué mueve la aguja:* elimina la ventana destructiva y la mezcla de checkouts. Hoy los datos
  viven en carpetas ignoradas por git de un checkout viejo (un `git clean -xfd` los borraría).
- *Riesgo principal:* migrar sin copia, o respaldar el sqlite sin el directorio HNSW.
- *Validar primero:* que el piloto con CFF sea la migración.

**2. Procedencia: lock con sha256, URL oficial y sello**
- *Qué es:* `corpus.lock.json` en git, fuera de `reportes/`. Guarda por fuente:
  - sha del PDF y del texto normalizado;
  - URL, sello, fecha de descarga y n_chunks;
  - versiones de chromadb, PyMuPDF y modelo.
  
  El bootstrap verifica los hashes y aborta si no coinciden.
- *Por qué mueve la aguja:* ataca la causa raíz (11 de 16) y hace demostrable qué texto validó cada
  escrito.
- *Riesgo principal:* LeyesBiblio usa una URL fija (`pdf/CFF.pdf`); el sha es justo lo que detecta un
  cambio de contenido sin aviso.
- *Validar primero:* el lock base de los 47 PDF actuales (sale de la gen-0).

**3. Release de motor, separada de la de datos**
- *Qué es:*
  - chunker que reconozca «ARTÍCULO» en mayúsculas y los transitorios como unidad propia;
  - artículos derogados o invalidados nunca 🟢;
  - `query` sin 🟢 100 fijo;
  - normalizar «1o.»/«4º» frente a la cita «art. 1».
- *Por qué mueve la aguja:* LFPCA, LFPC y la Constitución de Jalisco hoy se recuperan mal por
  artículo aunque estuvieran al día.
- *Riesgo principal:* cambia los chunks de todo el corpus, así que va sola y con su regresión.
- *Validar primero:* con el propio PDF como oráculo:
  - las etiquetas coinciden con los encabezados;
  - cada chunk empieza con su encabezado;
  - en las leyes no tocadas, cero cambio colateral byte a byte.
  
  Fixtures: «ARTÍCULO 5.-», «1o.»/«4º», Bis/Ter, «artículo 14» citado dentro de otro artículo,
  transitorios, «(Se deroga)».

**4. Temporalidad**
- *Qué es:* cada versión con su instrumento (decreto, A.I., declaratoria, fe de erratas, abrogación)
  y tres fechas: publicación, inicio de vigencia y fin de vigencia. Además, `fecha_hechos`
  obligatoria en el `caso.json` penal, re-auditoría dirigida con criterios de 🚨 y un calendario
  manual de desplazamientos sin reforma (CFPC → CNPCF; CPC de Jalisco por declaratoria).
- *Por qué mueve la aguja:* publicación ≠ entrada en vigor, y la ley aplicable puede ser la anterior.
- *Riesgo principal:* falsa precisión si las fechas se deducen sin leer los transitorios.
- *Validar primero:* solo archivar (paso 3 de §4). La consulta "a fecha" va después.

---

## 8. Gates de una actualización (lista ejecutable; no es un loop)

```
▸ GATES — ACTUALIZACIÓN DEL CORPUS (se corren sobre el staging, nunca sobre producción)
RAMA: feat/corpus-actualizacion-AAAA-MM (lock + manifiesto + bitácora; los datos fuera de git)
  G1 vigencia por fuente del lote: 🟢 VIGENTE, identidad/decreto confirmados, sin alertas (--estricto)
  G2 sha256(PDF) == lock y URL == url_pdf del listado oficial de hoy
  G3 en las fuentes NO tocadas: texto e IDs idénticos a la versión previa; IDs 0..N-1 contiguos
  G4 un solo sello por fuente, igual al oficial; ninguna indexación mixta
  G5 ≥ 95 % de páginas con texto; etiquetas ≈ encabezados; Δchunks en [0.8, 1.5] o escalado
  G6 check_corpus exit 0 y fuentes indexadas == manifiesto (sin extras: nada de escritos)
  G7 run_regression exit 0 sin cambio de veredicto (un cambio es hallazgo de Capa 2, no se tocan umbrales)
  G8 sondas: artículos reformados devuelven el texto nuevo por consulta de Chroma (no por sqlite)
ROJO PRIMERO: hoy reprueban G1 (16 fuentes), identidad (gemelo LOPJF), G5 (LFPCA, LFPC, Const. Jal.)
  y G2 (sin lock). Si un gate pasa sin el arreglo, el gate está mal.
SI FALLA: corregir la causa con acciones de lista cerrada (re-descargar del portal, renombrar al
  nombre del manifiesto, sacar la fuente del lote) y re-verificar. Si el mismo fallo se repite, se
  escala. Cualquier 🟡 (portal caído, evidencia contradictoria, abrogada, manual) detiene.
AL TERMINAR: tabla antes→después, artículos reformados cruzados con asuntos abiertos, qué sigue rojo
  y por qué, comando de swap listo y NO ejecutado.
```

---

## 9. Secuenciación

**HOY (sin tocar el índice) — hecho el 2026-10-09**
1. ✅ Quitar el `--reingest` sobre el índice en uso de la receta del reporte y de la documentación
   (receta azul/verde en el reporte, README y CONTRIBUTING).
2. ✅ Incidente del Drive: el abogado retiró el escrito del Drive (la API ya no lo encuentra); se
   retiró también del corpus local (a la Papelera de macOS). Nunca estuvo en git.
3. ✅ Gen-0 congelada en `~/itosturre-data/archivo/gen-0_2026-06-19/`: índice completo + los 45 PDF
   indexados, `MANIFEST.sha256` (51/51 verificados), `LEEME.md` con versiones del entorno; solo lectura.
4. ✅ Cotejo manual preparado: Regla 8 en CLAUDE.md + `scripts/cotejo_manual.py`; 19 PDF oficiales
   de las fuentes no-verdes bajados y validados en `~/itosturre-data/cotejo/2026-10-09/` (16
   confirman la última reforma; ⚠️ LFPC: el PDF oficial va atrasado respecto del listado, y CFPC:
   abrogado → ir al decreto en el DOF).
5. ✅ Fuente fantasma descartada: «Reglamento organico…pdf» fuera del corpus, de `LAW_SOURCE_MAP` y
   marcada `descartado` en el manifiesto; sus chunks salen en la primera reconstrucción en staging.
   La regresión dio veredictos idénticos antes y después (corrida sobre copias de la gen-0).

**ESTA SEMANA**
1. ✅ (2026-10-09) Veredicto por precedencia en `veredicto_global`, sin promedio. Reglas para:
   - artículo 🔴;
   - **artículo inexistente en la ley indexada**, detectado por su encabezado: antes «art. 750
     LA» y «art. 9999 CCF» salían 🟢 por similitud;
   - fuente con vigencia no-🟢;
   - «(Se deroga)».
   
   Se probó en rojo primero con 5 invariantes nuevos y un caso fijo en
   `casos_de_prueba/fixtures/`. La regresión corrió sobre copias de la gen-0: 25/25. Con el
   reporte vivo, el caso 001 pasa de 🟢 a 🟡 por sus artículos de la CPEUM (desactualizada).
2. Fixtures del detector de vigencia en la suite. Frankenstein y A.I./declaratoria ya se
   probaron en el scratchpad; falta llevarlos a la suite y añadir «LFT 2025 con sello 2015».
   Después, detección semanal.
3. Dry-run del chunker sin embeddings sobre los 45 PDF, comparado contra la gen-0. Si no reproduce
   el índice, **parar** y entender por qué antes de cualquier actualización.

**ESTE MES**
1. Piloto CFF: staging completo en el hogar de datos nuevo, en segundo plano y fuera del Bash del
   agente. Pasar gates, cruzar el diff con asuntos abiertos, autorizar y hacer el swap. Ese primer
   swap es también la migración, y la gen-0 queda intacta.
2. El resto de las leyes bien segmentadas, en un solo lote (incluye CPEUM).
3. Release de motor: arreglo del chunker con sus pruebas. Luego, LFPCA, LFPC y la Constitución de
   Jalisco.
4. Runbook escrito y, tras 3 corridas limpias, la skill `actualizar-corpus`.

**DESPUÉS**
- Histórico "a fecha".
- Cruce tesis ↔ reformas (requiere el corpus local de jurisprudencia).
- Propagación B2B.
- Un loop, solo si la frecuencia llega a semanal.

**NO hacer todavía**
- Ningún `ingest` ni `--reingest` sobre el índice vivo.
- Ninguna regresión, `check_corpus` ni audit contra la gen-0 sin una copia de por medio.
- Ninguna release que mezcle motor y datos.

---

## 10. Riesgos principales

| # | Riesgo | Prob. | Impacto | ¿Se detecta hoy? | Mitigación |
|---|---|---|---|---|---|
| 1 | Veredicto global por promedio: 🟢 que esconde 🔴, derogados y leyes 🔴 | Alta (es el estado actual) | Crítico | No | Quick win #4 |
| 2 | `--reingest` en sitio interrumpido (Bash del agente, cierre de la tapa) | Alta si lo lanza el agente | Crítico: índice vacío o parcial que `audit` usa sin preguntar | Parcial | Solo staging + job; abortar si falla el borrado |
| 3 | Índice mixto por `ingest` normal (instrucciones en el bootstrap y en el skill `itosturre-validator`) | Alta | Crítico: 🟢 sobre texto viejo | **Sí, desde hoy** (alerta de indexación mixta) | Una sola ruta de actualización; corregir esas instrucciones |
| 4 | Procedencia: Drive sin hashes, curaduría fallida, estuvo en modo Editor | Media | Crítico | No | Lock con sha; descarga del portal oficial |
| 5 | PDF defectuoso (escaneado, truncado, el decreto en vez del texto consolidado) aceptado con exit 0 | Media | Alto | No | Gates G2/G4/G5 previos a la ingesta |
| 6 | Portales rediseñados | Media-baja | Alto | **Mejor desde hoy** (fecha oficial < indexada ⇒ 🟡; URL efectiva en el reporte) | Fixtures HTML en la suite |
| 7 | Sin procedencia por auditoría | Alta | Alto | No | `corpus_version_id` en cada audit y en el Word |
| 8 | Única copia en una laptop; dependencias sin tope; migraciones al abrir | Media | Alto: reconstruir ≠ restaurar | No | Gen-0 + respaldo externo; lockfile; registrar modelo, revisión y dispositivo [MPS vs CPU: NO VERIFICADO] |
| 9 | Prompt injection en un PDF o en el reporte | Baja-media | Alto | No | Solo PDF oficiales con hash; corpus y reportes son datos, no instrucciones |

---

## 11. Decisiones que solo tú puedes tomar (Capa 2)

**Las tres primeras:**
1. **Veredicto desde hoy:** ¿basta un artículo 🔴, una cita de una ley con vigencia 🔴 o un
   artículo derogado para bajar el veredicto global (fin del promedio)? Aceptarlo implica tolerar
   falsos 🟡 seguros, como el del CPC de Jalisco.
2. **Autorización y tu tiempo:** ¿construir el staging es preparación libre y solo el **swap** lleva
   tu «sí» tecleado? ¿Tu revisión se limita al cruce del diff con asuntos abiertos, en ≤ 15 min por
   ciclo?
3. **Drive y procedencia:** ¿retiras el escrito, decides si notificas y dejas de usar el Drive como
   fuente de leyes (portal oficial + archivo local)? ¿Qué documento debía ser el "Reglamento
   orgánico"?

**Después:**
4. Prioridades: ¿qué fuentes son P0/P1 (actualizar en ≤ 7 días)?
5. ¿El corpus debe tener el texto **publicado** o el que **ya rige**? ¿Se conservan ambos?
6. ¿Se re-auditan los escritos auditados desde el 19-jun que citan CFF, LFPCA o CPEUM?
7. Leyes con años de rezago (LFT, Constitución y Código Civil de Jalisco): ¿sustitución íntegra con
   una sola autorización?
8. CFPC (abrogado con vigencia transitoria) y CPC de Jalisco (¿A.I. o declaratoria 9/2022?): ¿se
   conservan, se actualizan o se sustituyen?
9. ¿Quién más puede operar o aprobar (bus factor 1)? ¿Qué se le comunica a Avanzza y por qué canal?

---

## Apéndice A — Crítica de completitud (agente escéptico)

### Huecos que ningún lente cubrió
- El veredicto global por promedio (§2 #1) vuelve inútil cualquier tope de score por artículo; la
  vigencia debe ser regla de precedencia.
- `query` da 🟢 100 fijo: el agente redacta con esa ruta, así que el aviso en CLAUDE.md es solo prompt.
- El tiempo del abogado no tenía presupuesto. Con 11, 19 y 23 años de rezago (LFT, Código Civil y
  Constitución de Jalisco), un diff por artículo es inaprobable. Lo revisable es el cruce con las citas
  de asuntos abiertos.
- El incidente del Drive no tenía plan. El repo es privado (verificado: la API de GitHub da 404 sin
  autenticación), así que la exposición es por el enlace del Drive.
- Desplazamientos sin reforma: el CNPCF desplazará al CFPC, y la declaratoria al CPC de Jalisco, sin
  que cambie su sello. El detector no los ve; basta un calendario manual.
- Tesis: no hay corpus local, y una reforma deja huérfanas las tesis sobre el texto anterior.
- Recuperación ante desastre: hay una sola copia en una laptop, y reconstruir no equivale a restaurar.

### Contradicciones resueltas
- **Cadencia:** la detección es semanal; la actualización va por evento y con autorización.
- **Histórico o directorios:** son capas distintas. Rollback con gen-0 + previa; el "a fecha" es
  otro producto.
- **Vigencia en el VVCA:** antes de re-indexar y de forma permanente, como precedencia.
- **Prioridad:** por exposición × riesgo, no por días de rezago. La CPEUM lleva días de rezago, pero
  probablemente es la más citada.
- **Staging e ingesta:** "ingesta" es cambiar lo que leen las auditorías, es decir, el swap.
- **Backfill de metadata:** escribiría en la gen-0, así que la versión va en un manifiesto lateral.
- **Bitácora:** `reportes/` está ignorado por git, así que bitácora y lock van en `docs/` y en la
  raíz, sin datos de clientes.
- **Drive:** la fuente es el portal oficial y el almacén es un archivo local con respaldo.

### Matar o degradar
- **Matar:**
  - el loop de iteración (queda solo la lista de gates, §8);
  - los revisores-agente sin oráculo;
  - `ingest --solo --reemplazar` (reconstruir completo en staging es igual de seguro);
  - el backfill de metadata sobre la gen-0.
- **Degradar:**
  - la skill, que va después de 3 corridas limpias;
  - las tres generaciones con `flock`, que se reducen a gen-0 + previa;
  - el diff, que pasa de "aprobación" a dato del gate;
  - el histórico "a fecha", el B2B y el escáner de prompt injection, que van para después.

### Hechos en disputa (verificados)
- El checkout hermano no tiene retrieval por metadata (rama `fix/setup-ide-funcional` @3fa814b). El
  `-1` sí: `exact_article_chunks` (:729, solo en `query`) y `metadata_hit` (:1289-1355, en audit).
- El art. 57 CPF derogado: en audit, el piso por metadata es 70 (🟡), pero cuenta como verificado y
  el promedio lo diluye; en `query` sale 🟢 100.
- `run_regression` no escribe directo, pero `ON.audit` abre `PersistentClient` con migraciones
  "apply". Hoy el índice está intacto: sqlite del 19-jun 05:31, HNSW de las 05:15.

## Apéndice B — Correcciones aplicadas hoy a `scripts/vigencia_corpus.py`

Los lentes encontraron defectos en el verificador entregado hoy. Se corrigieron con pruebas (gate en
rojo primero, fixture sintético) y el reporte real se regeneró.

| Defecto | Hallado por | Corrección | Prueba |
|---|---|---|---|
| **Falso 🟢 "Frankenstein"**: reemplazar un PDF de Jalisco + `ingest` normal dejaba el articulado viejo con la tabla de reformas nueva | Operación, red team | Detector de indexación mixta (chunks de corridas separadas por > 2 h: nunca 🟢) y re-ingesta pendiente medida contra el chunk **más viejo** | Fixture: antes 🟢, ahora 🟡 con ambas alertas; el control limpio sigue 🟢 |
| **Falso 🔴 en el CPC de Jalisco**: la última modificación oficial es la «A.I. 9/2022» y el texto indexado ya cita la «Declaratoria General de Inconstitucionalidad 9/2022» | Jurídico | La segunda señal acepta resoluciones de la SCJN (A.I./declaratorias), no solo decretos | Real: CPC de Jalisco pasa a 🟡 «evidencia contradictoria»; el CP de Jalisco y el Registro Civil siguen 🔴 con confianza alta |
| Fecha oficial **anterior** a la indexada daba 🟢 (posible rediseño del portal) | Red team | ⇒ 🟡 «¿cambió el formato del portal?» | Fixture con la fecha alterada |
| Corrida parcial sin rojas salía con 0 | Gates | Sale con 2: «no pude verificar todo» ≠ «todo bien» | Portal de Jalisco caído ⇒ exit 2 |
| La receta del reporte mandaba `--reingest` **sobre el índice en uso** | Los cinco lentes | Receta azul/verde: copia `_next`, construir, verificar con reporte aparte, `mv` dejando `_prev_<fecha>` | Reporte regenerado |
| «database is locked» se trataba como otro esquema y leía sin filtro de colección | Arquitectura | Solo «no such table/column» activa la lectura sin filtro | Revisión de código |
| La URL efectiva de las fuentes oficiales no se veía (se puede redirigir por `.env`) | Red team | El reporte la muestra; `curl` solo acepta https | Reporte regenerado |
