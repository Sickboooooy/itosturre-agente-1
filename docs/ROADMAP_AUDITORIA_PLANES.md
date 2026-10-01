# Hoja de ruta: auditoría de planeación legal de alto nivel

**Estado:** v1.2 · 1-oct-2026 · base `main@ec86da1`
**Origen:** cuatro propuestas independientes (producto, evidencia oficial, motor de planes,
remediación del núcleo), crítica externa de Codex sobre la hoja de ruta y revisión de código
cruzada de los dos primeros PR. Toda decisión jurídica sigue siendo del responsable.

## Objetivo

Auditar planes jurídicos —estrategias procesales, delimitación de materias, mapas de
fuentes, diseño de protocolos y entregables tipo PEN, incluidos los generados por LLM—
con el método FUENTE → EVIDENCIA → COTEJO DE IDENTIDAD → REGLA PROPUESTA → COTEJO DE
FIDELIDAD → APROBACIÓN HUMANA → INCORPORACIÓN.

| Caso | Entrada → salida | Medida |
|---|---|---|
| UC1 | Entregable tipo PEN → disciplina, estado por afirmación, tabla de decisiones | Violaciones por plan; % de afirmaciones con estado |
| UC2 | Memo de estrategia → afirmaciones de fundamento, vía, órgano y plazo con estado | Conflictos de competencia detectados |
| UC3 | Regla redactada + extracto oficial → diferencias de fidelidad | Falsos verdes de fidelidad = 0 |
| UC4 | Mapa de fuentes → paquete de evidencia reproducible | Evidencias re-verificables por hash |

## Decisiones adoptadas

| ID | Decisión | Motivo |
|---|---|---|
| D1 | El ledger JSON (`plan-ledger/1.0`) es el modelo canónico; el parser de Markdown se pospone | Extraer solo IDs y estados aparenta una cobertura que no existe |
| D2 | Paquetes separados: `itosturre/plan/` (auditor) y, más adelante, `itosturre/evidencia/`; `itosturre/audit/` sigue siendo del VVCA | Dependencias unidireccionales y contratos compartidos |
| D3 | La verificación se separa de la aprobación; APROBADO exige persona humana, fecha y `contenido_sha256` del contenido aprobado; editar invalida | Una aprobación no debe sobrevivir a un cambio de texto |
| D4 | El RAG y el VVCA son localizadores (máximo CANDIDATO); un documento solo es evidencia si pasa por la capa de procedencia (URL oficial, hash, fecha) | El índice local no guarda procedencia |
| D5 | `traceability` 1.0 se conserva; cualquier mapeo de los ocho estados será explícito y versionado | Evitar pérdida silenciosa de estados |
| D6 | Host canónico del DOF: `dof.gob.mx` (el certificado no cubre `www`) | Reproducibilidad con TLS verificado |
| D7 | Evidencia y bitácoras por asunto en `auditorias/<matter-id>/plan/`; caché de evidencia fuera del repo | Datos del cliente locales; `gitignore` no basta como control de confidencialidad |

## Estado

| PR | Rama | Contenido | Estado |
|---|---|---|---|
| R3 | `fix/telegram-opt-in` | Telegram solo con `--telegram`; fallos de envío visibles (código 3, auditoría `partial`); token redactado; imports perezosos en `capturar_rag.py` | Integrado en `main` |
| PR-1 | `feat/plan-audit-ledger` | `itosturre/plan/`, `plan_audit.py` (`lint` y `hash`), reglas PL-001 a PL-014, Gold Set de planes | Integrado en `main` |
| R1 | `fix/git-strategy-generico` | `git_strategy.sh` genérico: rama `fix/<slug>` o `feat/<slug>`, commit solo de rutas declaradas con mensaje propio, política de datos antes del commit, gates antes del merge; hook opcional `.githooks/pre-commit` | Integrado en `main` |
| R2 | `fix/memoria-procedencia` | Procedencia en la memoria: no capturar mensajes de subagentes ni avisos del sistema como "correcciones de criterio"; sobre reinyectado escapado; purga con simulación por defecto | Integrado en `main` |
| PR-2 | `feat/evidencia-pura` | `itosturre/evidencia/` (C7): registro `evidencia/1.0` con validación estructural por lista de problemas y `comprobar_integridad` aparte (recalcula huellas y relee la fuente; sin ella un registro no sostiene VERIFICADO); hosts oficiales y `url_oficial` como fuente única (plan los reexporta); huellas SHA-256 y JSON canónico; parser del innerText del SJF anclado en "Registro digital:" con estructura validada (rubro, campos de una línea, publicación y obligatoriedad contadas en todo el texto); limpieza de LeyesBiblio con título plausible y consensuado; ubicación de artículos cuerpo/transitorios/indeterminada; notas de reforma con gramática completa e invariante de fechas; fixtures oficiales literales con manifiesto de procedencia | Implementado y probado tras la revisión externa (ronda 2) |

| PR-3 | `feat/cotejo-identidad` | Cotejo de identidad (C9): paquete de evidencia direccionado por contenido (`itosturre/evidencia/paquete.py`, único módulo de la capa con E/S de archivos; publicación que falla si el destino existe —enlace duro u `O_EXCL`—, huella verificada al leer, rechazo de enlaces simbólicos y junctions con contención por ruta real, solo registros íntegros y sin ambigüedad); `itosturre/plan/identidad.py` coteja cada par (afirmación, evidencia) en el orden vínculo → registro → integridad (+ relación original–texto de las leyes por re-extracción con extractor inyectado) → documento y versión (+ registros/claves que menciona la afirmación) → ubicación (sin rangos; + artículo y ley que menciona la afirmación) → campos y extracto, con CONFORME / DISCREPANTE / SIN_EVIDENCIA (NO_COTEJADO para INEXISTENTE), cobertura de menciones por afirmación y `requiere_decision_humana` cuando la fuente trae advertencias; el cotejo lleva la huella del ledger y del paquete; reglas PL-015…PL-017 solo con paquete (`REGLAS_COTEJO`), PL-017 con decisiones `advertencias_fuente` ligadas a la fuente vigente; CLI `cotejar`, `lint --paquete` (ninguna salida dentro del paquete) y `evidencia agregar-tesis` / `agregar-ley` (origen del texto, páginas declaradas comprobadas, título frente a la URL); sección de cotejo en el reporte; campo opcional `ultima_reforma_dof` en las evidencias del ledger | Implementado y probado tras la revisión externa (ronda 2) |

PR-2 corrige la lectura de la época en la capa Python; el scraper TypeScript
(`services/itosturre-scraper`, `vvca_audit.ts:418`) sigue tomando la época del banner
hasta R5.

## Siguientes PR (orden propuesto)

El orden no cambia con PR-3. PR-4 se apoya en lo que PR-3 deja resuelto: un par
CONFORME ya garantiza qué documento, qué versión y qué artículo (texto acotado entre su
encabezado y el siguiente) respaldan la afirmación, que es la entrada que necesita el
cotejo de fidelidad.

1. **R4 · Núcleo VVCA probable en CI** y corrección de extracción, resolución de ley,
   detección de tesis y veredicto con alcance explícito ("existencia y ubicación").
   Incluye un falso positivo comprobado: `has_exact_article_heading` de
   `itosturre/audit/evidence.py` acepta "Artículo 4o.-A.-" cuando se pide el "4o".
2. **PR-4 · Fidelidad determinista** (plazos, modales, negaciones, excepciones,
   cuantificadores) sobre pares ya CONFORME en identidad; nunca emite CONFORME por sí sola.
3. **Exposición**: MENÚ 16 y regla absoluta "APROBADO solo humano" cuando el CLI esté
   probado con un piloto (re-correr PEN-01 con el kit: `evidencia agregar-*` →
   ledger → `cotejar`).

Pendientes derivados de PR-2, sin lugar asignado en el orden: **R5** (época del scraper
anclada en "Registro digital:") y **C8** (descarga y caché de evidencia fuera del repo:
red y reloj que producen registros `evidencia/1.0`). Desde PR-3, C8 tiene destino: debe
escribir en un paquete con `guardar_evidencia`; mientras tanto, `evidencia agregar-*`
cubre el camino manual sin red.

Pendientes derivados de PR-3:

- Tipos de fuente sin cotejo (DOF, Corte IDH, `sjfsemanal`): hoy SIN_EVIDENCIA con
  motivo "tipo no soportado".
- `[PR]` y `[SCJN-I]` en `fuerza_vinculante` no se mapean a un tipo de tesis: el par no
  puede ser CONFORME hasta que el clasificador los distinga (Regla 6 de `CLAUDE.md`).
- Artículos con ordinal escrito ("Artículo Único", "Primero") no se interpretan en la
  ubicación del ledger (SIN_EVIDENCIA, nunca falso verde).
- La comprobación de integridad de PR-2 reconstruye una ley con el total de páginas del
  encabezado: si el encabezado "N de M" discrepa del PDF, `agregar-ley` rechaza el
  registro (falla cerrado, pero no admite esa ley hasta ajustar `integridad.py`).
- Correspondencia archivo → ordenamiento (`ARCHIVOS_LEYESBIBLIO`): CPEUM, CNPP, CPF, CFF,
  LAmp y LNEP, siempre confirmada con el título del encabezado. Otras leyes: las menciones
  de artículo **con** ley quedan SIN_EVIDENCIA hasta agregarlas.
- `menciones.py` no expande enumeraciones de registros ("registros digitales 1 y 2"):
  solo cuenta el primero; tampoco reconoce claves de tesis aisladas de TCC (se suplen con
  búsqueda literal de la clave de la fuente).
- Los artículos con letra ("4o.-A") no tienen clave en `menciones.py`: una afirmación que
  los menciona queda SIN_EVIDENCIA, nunca CONFORME.
- La relación original–texto solo se acredita con el mismo extractor y versión: un
  cambio de versión de PyMuPDF deja las leyes registradas en SIN_EVIDENCIA hasta volver a
  registrarlas (falla cerrado).
- Los enlaces duros a archivos externos no se detectan (no son enlaces simbólicos ni
  puntos de reanálisis); su contenido sigue verificado por huella en cada lectura.

## Qué no construir

Un juez LLM que califique planes; equivalencias entre 🟢 VVCA y VERIFICADO; consumo del
microservicio interno del SJF; envíos automáticos o LLM externo dentro del flujo;
decisiones guardadas en la memoria contextual; detección semántica automática de
contradicciones; interfaz web.

## Decisiones pendientes del responsable

- Regla 3 de `CLAUDE.md` (el RAG como fuente de verificación) frente a D4.
- Cuarentena de `agentes/vigilancia_jurisprudencial.py`, que consume el microservicio interno.
- Lista de responsables no humanos: hoy rechaza cargos como "Agente del MP" (falla cerrado).
- Cobertura cuando la ley aparece a la izquierda del artículo ("la Ley de Amparo, en su
  artículo 217"): hoy produce hallazgos de más, nunca un falso verde.
