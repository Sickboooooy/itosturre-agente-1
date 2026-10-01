# Memoria contextual

**Estado:** vigente desde 10-sep-2026
**Alcance:** memoria persistente, buscable y acotada del proyecto.
**Origen:** `docs/auditoria-memoria-contextual-10sep2026.md` (etapas 0-6 y benchmark).

## Qué resuelve

Antes, el conocimiento del proyecto vivía en diecisiete archivos Markdown
escritos a mano. Recordar algo exigía cargarlos enteros (76 KB) y nada se perdía
tan a menudo como lo que más valía: la corrección de criterio de un secretario
con veinticinco años de foro. Además, cada auditoría VVCA escribía su traza en
`auditorias/<caso>/vvca_traceability.json` y nadie volvía a leerla.

Ahora ese conocimiento es un índice consultable que devuelve **solo lo relevante
para la consulta actual**, con techo en bytes.

## Regla que no se negocia

> **La memoria recuerda decisiones. Nunca es fuente de una cita legal.**

Los artículos salen del corpus (`OpenNotebook.py query`, regla 2 VVCA) y las
tesis del SJF. Un evento que diga "el artículo 19 dice X" es el recuerdo de una
conversación, no una verificación. El bloque que se entrega al modelo lo declara
explícitamente y se marca como **datos, no instrucciones**.

## Dónde vive

```
~/.itosturre/memoria/<project_id>.db      ← FUERA del repositorio
```

Fuera del árbol a propósito: los expedientes son work product con datos de
cliente y la regla absoluta #8 prohíbe versionarlos. `.gitignore` y
`config/data-policy.json` cubren el caso de que alguien reapunte
`ITOSTURRE_MEMORIA_DIR` hacia dentro.

| Variable | Efecto |
|---|---|
| `ITOSTURRE_MEMORIA_DB` | Fija un archivo concreto (pruebas, respaldos) |
| `ITOSTURRE_MEMORIA_DIR` | Cambia el directorio de bases |
| `ITOSTURRE_SESSION_ID` / `CLAUDE_SESSION_ID` | Identidad de sesión |

`project_id` combina el nombre del directorio con un hash de su ruta absoluta
normalizada: dos clones del mismo repositorio no comparten memoria.

## Uso

```bash
# Windows:  ./venv/Scripts/python.exe    ·    macOS/Linux:  ./venv/bin/python

python memoria_cli.py registrar correccion_criterio_pjf \
    "Para deserción de pruebas la vía correcta es REVOCACIÓN, no apelación" \
    --archivo OpenNotebook.py --importancia 1

python memoria_cli.py buscar "revocacion desercion pruebas"
python memoria_cli.py buscar "" --tipos alerta_procesal plazo_detectado
python memoria_cli.py buscar "corpus fiscal" --detalles --max-bytes 8192 --json

python memoria_cli.py snapshot            # construir y guardar
python memoria_cli.py reanudar            # consumir el último snapshot
python memoria_cli.py stats
python memoria_cli.py tipos               # taxonomía completa
python memoria_cli.py reindexar           # reconstruir el índice FTS
python memoria_cli.py olvidar --tipos user_correction --procedencia-no-humana   # simulación
```

Purga selectiva con `olvidar`: ver [Olvidar](#olvidar-purga-selectiva).

Importación de la memoria histórica (idempotente):

```bash
python scripts/importar_memorias_md.py --dry-run
python scripts/importar_memorias_md.py
python scripts/importar_memorias_md.py --reemplazar   # si cambió la conversión
```

`jurisprudencia/vvca_corrections.json` **no se modifica**;
`OpenNotebook.py calibrate` sigue leyéndolo igual.

## Arquitectura

```
eventos          tabla de verdad (id, event_uid, project_id, session_id, …)
eventos_fts      índice FTS5 EXTERNO (content='eventos') — no duplica el texto
sesiones         una fila por sesión
snapshots        continuidad, con bandera `consumido`
```

Tokenizador `unicode61 remove_diacritics 2`. **No `porter`**: es un stemmer solo
de inglés y sin `remove_diacritics` una búsqueda de `revocacion` no encontraría
`revocación` — inaceptable en texto jurídico mexicano.

Puntuación (determinista y auditable, `itosturre/memoria/ranking.py`):

```
score = bm25_norm × peso_importancia × decaimiento_recencia + bono_tipo
```

El decaimiento tiene **suelo 0.3**: una corrección del PJF de hace un año sigue
siendo derecho vigente. Aquí la recencia informa, no manda — al contrario que en
un repositorio de software.

El recorte es **por bytes**, no por número de filas: el contrato con el modelo es
un techo de contexto y un techo en filas no lo garantiza.

## Módulos

| Archivo | Responsabilidad |
|---|---|
| `itosturre/memoria/esquema.py` | DDL, conexión WAL, migración, detección de FTS5 |
| `itosturre/memoria/redaccion.py` | Secretos, saneo de `MATCH`, anclaje de rutas |
| `itosturre/memoria/ranking.py` | Taxonomía, puntuación, presupuesto (puro) |
| `itosturre/memoria/store.py` | `record` / `recall` / sesiones / snapshots |
| `itosturre/memoria/snapshot.py` | Snapshot por referencia, con escape del sobre (puro) |
| `itosturre/memoria/hooks.py` | Qué se captura y procedencia de los prompts (puro salvo `procesar`) |
| `itosturre/memoria/puente.py` | Auditoría VVCA → eventos |
| `memoria_cli.py` | Interfaz de línea de comandos |

## Integraciones

- **`vvca_full.py`** registra el veredicto, las citas bloqueadas y los huecos de
  corpus tras cada auditoría. Aditivo: `vvca_traceability.json` se sigue
  escribiendo igual.
- **`OpenNotebook.py correct`** registra además un `correccion_criterio_pjf`.

Ambas dentro de `try/except`: **un fallo de memoria nunca tumba una auditoría en
curso.** La memoria es accesoria; el trabajo del abogado no lo es.

## Taxonomía

Genéricos: `architecture_decision`, `user_decision`, `user_correction`,
`important_context`, `task_started`, `task_completed`, `error_detected`,
`error_resolved`, `test_failed`, `file_modified`, `git_commit`, `git_branch`,
`dependency_changed`, `configuration_changed`, `session_snapshot`,
`memoria_purga` (rastro de `olvidar`, sin bono y fuera del snapshot).

De dominio: `correccion_criterio_pjf`, `alerta_procesal`, `cita_bloqueada`,
`plazo_detectado`, `corpus_gap`, `vvca_veredicto`.

`file_created` / `file_deleted` / `file_write` se canonizan a `file_modified` —
git ya versiona eso. `test_passed` solo se conserva cuando cierra un fallo
previo: registrar cada prueba verde contamina el índice con lo que nunca se
consulta.

## Seguridad

| Riesgo | Defensa | Prueba |
|---|---|---|
| Secretos en la base | Redacción por nombre de clave y por forma del valor, sobre-redactando | `RedaccionDeSecretos` |
| Inyección en `MATCH` | Solo tokens alfanuméricos, cada uno como literal entrecomillado | `ConsultaFTS` |
| Path traversal | Toda ruta anclada al proyecto; fuera de él se descarta el campo | `RutasAncladas` |
| Cruce entre clientes | `project_id` en **todas** las consultas | `AislamientoEntreProyectos` |
| Evento como instrucción | El bloque se marca como datos | `test_snapshot_marca_su_contenido_como_datos` |
| Resumen que cierra el sobre | Escape de `&`, `<`, `>` en todo texto derivado de eventos | `SobreEscapado` |
| Informe de subagente tomado por corrección | Procedencia antes que marcadores | `ProcedenciaDelPrompt` |
| Memoria contaminada sin forma de limpiarla | `olvidar` (simulación por defecto) | `Olvidar` |

```bash
python -m unittest discover -s tests -p "test_memoria_*.py"
python scripts/benchmark_memoria.py --salida docs/BENCHMARK_MEMORIA.md
```

## Resultados medidos

66 pruebas en verde. Acierto de recuperación **10/10** sobre preguntas reales;
**95.3 %** menos contexto por consulta; **0.77 ms** con 10 000 eventos en base;
snapshot de continuidad en **798 bytes**. Detalle en `docs/BENCHMARK_MEMORIA.md`.

## Captura y restauración automáticas (hooks)

Configurados en `.claude/settings.json`. Entrada única:
`scripts/memoria_hook.sh` → `scripts/memoria_hook.py`.

| Evento | Matcher | Qué hace | `async` |
|---|---|---|:--:|
| `SessionStart` | — | Inyecta el contexto de reanudación (visible: `suppressOutput: false`) | no¹ |
| `PreCompact` | todos | Guarda el snapshot antes de compactar | no² |
| `SessionEnd` | — | Snapshot al cerrar | sí |
| `PostToolUse` | `Write\|Edit\|NotebookEdit\|Bash` | Captura cambios y comandos | sí |
| `PostToolUseFailure` | `Write\|Edit\|Bash` | Captura errores | sí |
| `UserPromptSubmit` | — | Captura decisiones y correcciones | sí |

¹ Necesita devolver `additionalContext`. ² Debe terminar antes de la compactación.

**`Read`, `Grep` y `Glob` no están en ningún matcher**: para una lectura el hook
no llega a existir. Filtrar ahí es lo que evita pagar el arranque de proceso en
el caso más frecuente.

### Qué se captura y qué no

| Se registra | Se descarta |
|---|---|
| Edición de archivo (una vez por archivo y sesión) | Lecturas, búsquedas, listados |
| `git commit` (asunto), rama, merge | `git status`, `diff`, `log` |
| Pruebas en rojo; en verde solo si cierra un fallo | Pruebas verdes sueltas |
| Instalación de dependencias | `ls`, `cd`, `cat`, `echo`, `pwd`… |
| Cambios de configuración | Artefactos: `__pycache__`, `node_modules`, `chroma_db`, `temp/`, `*.log` |
| Prompts del operador con marcador de decisión o corrección | El resto de prompts |
| Solo el texto propio, sin bloques pegados | Prompts de procedencia no humana (subagentes, notificaciones, canales) |

**Se guarda el hecho, no la salida.** "Modificó `store.py`" es un hecho; el diff
es ruido que ya está en git. Ninguna salida de herramienta se persiste completa.

### Sobre los prompts

Un prompt de este proyecto puede contener un expediente con datos de cliente.
Por eso solo se capturan los que llevan un marcador explícito de decisión o
corrección, recortados a 200 caracteres y pasados por el redactor. El
reconocimiento es insensible a acentos: se escribe "la via correcta" tanto como
"la vía correcta".

Desactivable por separado con `ITOSTURRE_MEMORIA_PROMPTS=off`, sin tocar el resto.

### Procedencia: solo cuenta lo que escribió el operador

`UserPromptSubmit` no distingue quién escribió el texto. En la base real
(1-oct-2026), de 21 eventos de corrección, 14 eran informes de subagentes que contenían
"a partir de ahora" o "recuerda que", y uno era un bloque pegado de terceros. Se
reinyectaban en cada arranque como si fueran criterio del operador (regla
absoluta 6). Por eso **la procedencia se mira antes que los marcadores**
(`procedencia_no_humana` y `texto_de_usuario` en `itosturre/memoria/hooks.py`,
funciones puras):

| Marca en el prompt | Motivo anotado |
|---|---|
| `<agent-message` | mensaje de subagente |
| `[Subagent hand-back]` | informe de subagente |
| `<task-notification` | notificación de tarea |
| `<system-reminder` | recordatorio del sistema |
| `[SYSTEM NOTIFICATION` | notificación del sistema |
| `<cross-session-message` | mensaje entre sesiones |
| `<channel source=` | canal externo en cuarentena |
| `<command-name>` / `<command-message>` | comando expandido |

- **Cuarentena de canales.** Un mensaje de Telegram u otro canal externo puede
  venir de cualquiera que alcance el bot: nunca se captura como corrección, por
  mucho que diga "la vía correcta es…". Si el operador quiere conservarlo, lo
  registra él con `memoria_cli.py registrar`.
- **Texto pegado.** Cada bloque `<pasted_content …>…</pasted_content …>` se
  elimina y se clasifica solo el texto restante del operador; lo pegado ni
  dispara la captura ni se guarda. Si lo que queda tiene menos de 12 caracteres,
  no se captura. Un bloque sin cierre se trata como pegado hasta el final. Una
  marca de la tabla **dentro** de lo pegado no descarta el texto propio: es
  contenido que el operador eligió pegar, no un mensaje del arnés.
- **Sin corte por longitud.** Un informe no es sospechoso por largo, sino por su
  procedencia; una corrección larga del operador sigue capturándose.
- **Bitácora sin contenido.** Cada descarte se anota en `hooks.log` como
  `"accion": "descartado", "motivo": "procedencia <motivo>"`, pasado por el
  redactor y sin el texto del prompt.

### El sobre `<memoria-itosturre>` se escapa

Todo texto derivado de eventos que entra en el sobre —resúmenes, fechas, rutas,
la siguiente acción sugerida— se escapa (`&`, `<`, `>`; `html.escape` con
`quote=False`; los atributos de la cabecera, con comillas). Un resumen que
contenga `</memoria-itosturre>` o `<system-reminder>` aparece como
`&lt;/memoria-itosturre&gt;`: sigue siendo legible y ya no puede cerrar el sobre
ni abrir otro. La etiqueta de cierre aparece exactamente una vez.

Los snapshots guardados antes de este cambio pueden no estar escapados: al
restaurar, uno cuyo sobre no esté íntegro (`sobre_integro`) se descarta y se
reconstruye desde los eventos; la bitácora lo anota como `snapshot_descartado`.

### Restauración visible

`SessionStart` emite `suppressOutput: false`: el operador **ve** el bloque que se
inyecta en el contexto del modelo. Antes se ocultaba, y eso permitió que los
informes de subagentes se reinyectaran sesión tras sesión sin que nadie lo
notara. El bloque está acotado a 2 KB; su coste en pantalla es menor que el de
una memoria contaminada en silencio.

### Olvidar (purga selectiva)

```bash
# 1. Simulación (por defecto): lista id, fecha, tipo y 80 caracteres; no borra.
python memoria_cli.py olvidar --tipos user_correction correccion_criterio_pjf \
    --procedencia-no-humana

# 2. Aplicación, tras revisar la lista: mismos filtros + --aplicar.
python memoria_cli.py olvidar --tipos user_correction correccion_criterio_pjf \
    --procedencia-no-humana --aplicar

# Otros filtros, combinables (Y lógico):
python memoria_cli.py olvidar --desde 2026-09-01 --hasta 2026-09-30 --contiene "hand-back"
```

| Filtro | Efecto |
|---|---|
| `--tipos T…` | Tipos de evento (canonizados) |
| `--desde` / `--hasta AAAA-MM-DD` | Rango de días, ambos inclusive |
| `--contiene TEXTO` | Subcadena literal en resumen o detalles, sin distinguir mayúsculas ni acentos |
| `--procedencia-no-humana` | El texto guardado no lo escribió el operador (mismo detector que la captura) |
| `--aplicar` | Borra de verdad; sin él es una simulación |

Garantías:

- **Exige al menos un filtro.** Sin filtros sale con error (código 2): nunca
  "borrar todo" por omisión.
- **Solo el `project_id` actual.** Otros proyectos de la misma base no se tocan.
- **Índice coherente.** El borrado pasa por el disparador `eventos_ad`, que
  retira cada fila del índice FTS externo; una búsqueda posterior ya no la
  encuentra.
- **Sin reinyección.** Los snapshots pendientes del proyecto se marcan como
  consumidos: el siguiente `SessionStart` se reconstruye sin lo borrado.
- **Rastro sin contenido.** Se registra un `memoria_purga` con el número de
  eventos borrados y los filtros usados; de `--contiene` solo consta que se
  usó, no el texto. Los `memoria_purga` nunca se seleccionan para borrar.
- **Transacción única.** O se borra y se audita, o no cambia nada.

`--procedencia-no-humana` mira cualquier tipo de evento: un commit cuyo mensaje
mencione `<system-reminder>` también coincidiría. Por eso se recomienda
combinarlo con `--tipos user_correction correccion_criterio_pjf` y revisar
siempre la simulación antes de `--aplicar`.

### Interruptores

| Variable | Efecto |
|---|---|
| `ITOSTURRE_MEMORIA_HOOKS=off` | Apaga captura y restauración |
| `ITOSTURRE_MEMORIA_PROMPTS=off` | Apaga solo la captura de prompts |
| `ITOSTURRE_MEMORIA_LOG` | Ruta de la bitácora de diagnóstico |

### Coste medido

| Camino | Trabajo propio | Bloquea |
|---|---:|---|
| Descarte | 0.001 ms | no (`async`) |
| Captura | 5.7 ms | no (`async`) |
| Snapshot | ~23 ms | sí, una vez por compactación |
| Restauración | ~20 ms | sí, una vez por sesión |

El coste de pared por hook es de ~140 ms, de los que ~45 ms son arrancar el
intérprete a secas: **domina el arranque del proceso, no este código**. El diseño
lo evita —filtro en el matcher, `async` en la captura— en vez de intentar
reducirlo.

### Diagnóstico

Bitácora JSONL en `~/.itosturre/memoria/hooks.log` (fuera del repositorio, rotada
a 512 KB, redactada). Cada línea dice qué evento ocurrió, qué hook lo procesó, si
se almacenó o descartó, el motivo del descarte, la duración y el error si lo hubo.

```bash
tail -20 ~/.itosturre/memoria/hooks.log
```

### Fallo seguro

El hook **siempre sale con código 0** y **stdout lleva JSON válido o nada**. Un
código distinto puede cortar el turno; salida mal formada contaminaría el
contexto. SQLite inaccesible, payload malformado o disco lleno degradan la
funcionalidad —ese evento no se recuerda— y el agente continúa.

---

## Límites conocidos

- **No reduce el prompt base.** Ese frente se atacó por separado: `CLAUDE.md` pasó
  de ~10 523 a ~4 372 tokens (`docs/propuesta-adelgazar-claude-md.md`).
- **El arranque de proceso por hook (~140 ms) no se puede eliminar**, solo sacar
  del camino crítico. Es inherente a los hooks de tipo `command`.
- **Un hook `async` puede perderse** si la sesión termina antes de que complete.
  Es la contrapartida aceptada de no bloquear el turno: se pierde un evento, no
  el trabajo.
- **Clasificación de prosa importada, heurística.** Convertir Markdown libre en
  tipos de evento produce falsos positivos; el patrón de criterio jurídico se
  mantiene deliberadamente estrecho porque un falso positivo aquí no añade ruido,
  **desplaza la respuesta correcta**.
- **Sin poda automática.** A ~1 KB por evento no es problema en años, pero no hay
  política de retención todavía. La purga existe (`olvidar`), pero es manual.
- **La procedencia depende de las marcas del arnés.** Si Claude Code cambia el
  formato de `<agent-message>`, `<channel>` o `<pasted_content>`, hay que
  actualizar `_NO_HUMANO` en `hooks.py`. Un prompt del operador que mencione
  literalmente una de esas marcas no se captura: error del lado seguro.
- **`olvidar` no reescribe snapshots ya consumidos.** Los marca para que no se
  reinyecten, pero su texto histórico sigue en la tabla `snapshots` y
  `reanudar --sin-consumir` lo mostraría.
- **Permisos del archivo.** `0o700` donde POSIX lo soporta; en Windows el control
  lo lleva la ACL del perfil y no se simula una garantía que el sistema no da.

## Procedencia

Implementación propia en Python sobre la biblioteca estándar. **Cero
dependencias nuevas.** El estudio de `context-mode` (Elastic License 2.0) aportó
ideas de arquitectura —snapshot por referencia, bandera de consumo, pesos de
columna en BM25, redacción sobre-inclusiva—; **no se portó código**. La licencia
ELv2 prohíbe ofrecer el software a terceros como servicio gestionado, lo que es
incompatible con un producto comercial: por eso conceptos sí, código no.
