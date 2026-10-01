# Hoja de ruta: auditoría de planeación legal de alto nivel

**Estado:** v1 · 1-oct-2026 · base `main@533ea22`
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
| R3 | `fix/telegram-opt-in` | Telegram solo con `--telegram`; fallos de envío visibles (código 3, auditoría `partial`); token redactado; imports perezosos en `capturar_rag.py` | Implementado y probado, sin commit |
| PR-1 | `feat/plan-audit-ledger` | `itosturre/plan/`, `plan_audit.py` (`lint` y `hash`), reglas PL-001 a PL-014, Gold Set de planes | Integrado en `main` |
| R1 | `fix/git-strategy-generico` | `git_strategy.sh` genérico: rama `fix/<slug>` o `feat/<slug>`, commit solo de rutas declaradas con mensaje propio, política de datos antes del commit, gates antes del merge; hook opcional `.githooks/pre-commit` | Implementado y probado |

R3 también está integrado en `main`.

## Siguientes PR (orden propuesto)

1. **R2 · Procedencia en la memoria**: no capturar mensajes de subagentes ni avisos del
   sistema como "correcciones de criterio"; escapar el sobre reinyectado; comando de purga
   con simulación por defecto.
3. **PR-2 · Evidencia pura**: esquema `evidencia/1.0`, parser del SJF anclado en
   "Registro digital:" (corrige la época tomada del banner), limpieza de LeyesBiblio con
   invariantes y parser de notas de reforma; fixtures públicos sin red.
4. **PR-3 · Cotejo de identidad** contra la evidencia registrada (hash, encabezado exacto,
   subcadena normalizada, última reforma; rubro por igualdad normalizada).
5. **R4 · Núcleo VVCA probable en CI** y corrección de extracción, resolución de ley,
   detección de tesis y veredicto con alcance explícito ("existencia y ubicación").
6. **PR-4 · Fidelidad determinista** (plazos, modales, negaciones, excepciones,
   cuantificadores); nunca emite CONFORME por sí sola.
7. **Exposición**: MENÚ 16 y regla absoluta "APROBADO solo humano" cuando el CLI esté
   probado con un piloto (re-correr PEN-01 con el kit).

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
