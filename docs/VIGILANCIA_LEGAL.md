# Vigilancia legal automatizada — DOF/SAT + SJF

**Estado:** vigente desde 11-sep-2026 · reparación arquitectónica del watch programado.
**Alcance:** `agentes/vigilancia_dof.py`, `agentes/vigilancia_jurisprudencial.py`,
`agentes/contenido_linkedin.py`, `itosturre/vigilancia/`.

**Por qué existe:** una tarea programada intentó ejecutar esta vigilancia directamente
dentro de una sesión cloud de Claude Code cuya política de red bloquea (403 en el proxy
de egress) las conexiones salientes a `dof.gob.mx`, `sat.gob.mx` y `sjf2.scjn.gob.mx`. El
watch no falló por un bug de un solo comando: falló porque la arquitectura asumía que el
proceso que orquesta la vigilancia tiene, por definición, acceso directo a esas fuentes.
Este documento fija el contrato que evita repetir ese error, con o sin ese entorno de
por medio.

---

## 1. Diagnóstico de causa raíz

Dos capas distintas, ambas necesarias para que esto vuelva a pasar:

1. **La tarea programada invocó a Claude en modo "navega tú mismo"** (un prompt en lenguaje
   natural pidiendo revisar el DOF/SAT/SJF) en vez de invocar los watchers deterministas que
   ya existen en `agentes/`. Ese prompt vive en la configuración de la tarea programada de
   la cuenta, no en este repositorio — no se puede corregir con un commit; ver §6.
2. **Aunque la tarea invocara los scripts correctos, éstos no distinguían** "consultamos la
   fuente y no había novedades" de "no pudimos consultar la fuente": ante cualquier excepción
   de red, `vigilancia_dof.py` seguía adelante y redactaba un brief con `hallazgos = []`
   (indistinguible de un día sin publicaciones); `vigilancia_jurisprudencial.py` devolvía
   `[]` de IUS tanto si la búsqueda falló como si genuinamente no había resultados; y
   `contenido_linkedin.py` generaba un post con cualquier texto que hubiera en el brief más
   reciente, sin verificar si ese texto describía una consulta real. `docs/SJF_OPERATIVA.md`
   ya advertía sobre este patrón ("nunca entregues un resultado vacío disfrazado de 'sin
   hallazgos'") pero el código no lo aplicaba todavía.

La causa raíz **no** es que falte un scraper, un submódulo, o una librería. Los tres
watchers ya usan HTTP directo (`requests`) o el microservicio público del SJF — nunca
dependieron de `services/itosturre-scraper` (ese submódulo es para la búsqueda estratégica
en vivo del Menú 3 / skill `scjn-api`, un flujo distinto). Verificado: ninguno de los tres
scripts importa nada de `services/`.

---

## 2. Qué entorno ejecuta qué

```
Orquestador (tarea programada / cron / quien invoque el watch)
        │  invoca, NO asume acceso directo a las fuentes
        ▼
Collector — agentes/vigilancia_dof.py, vigilancia_jurisprudencial.py
        │  requests HTTP directo a dof.gob.mx / sat.gob.mx / sjf2.scjn.gob.mx
        │  SI el entorno del Collector no tiene egress autorizado → SOURCE_UNAVAILABLE
        ▼
Evidence — items + contrato .json (itosturre/vigilancia/contrato.py) junto al .md
        ▼
Validator — agentes/contenido_linkedin.py: validar() antes de generar nada
        ▼
Content Generator — agentes/contenido_linkedin.py: genera SOLO si hay ≥1 hallazgo
        con status SUCCESS; si no, escribe LinkedIn: NOT_GENERATED con el motivo.
```

- **El Collector necesita, él mismo, acceso de red autorizado** a `dof.gob.mx`, `sat.gob.mx`
  y `sjf2.scjn.gob.mx`. No hay forma de que el Orquestador "le preste" acceso: si el proceso
  Python de `agentes/vigilancia_dof.py` corre en una máquina/contenedor cuya política de
  red bloquea esos hosts, el resultado es `SOURCE_UNAVAILABLE` — por diseño, no por bug.
- **Entornos que sí tienen ese acceso** (verificar antes de programar el cron):
  el equipo del operador (Windows, según `docs/ENTORNO.md`) con salida de internet normal;
  o cualquier VM/contenedor propio cuya política de egress no bloquee esos tres dominios.
- **Entornos que NO lo tienen, documentados:** una sesión cloud de Claude Code / Claude en
  la nube corriendo bajo el proxy de egress con política restrictiva (confirmado: 403 a
  `dof.gob.mx:443` y `sjf2.scjn.gob.mx:443` el 11-sep-2026). Ejecutar el watch ahí SIEMPRE
  producirá `SOURCE_UNAVAILABLE` para las tres fuentes — eso es correcto, no hay que
  "arreglarlo" añadiendo un proxy o un bypass (ver §7).
- **`services/itosturre-scraper` y `services/itosturre-skills` son irrelevantes para este
  watch.** Ambos son submódulos Git (`git submodule status` los muestra sin inicializar en
  un clon fresco: `git submodule update --init --recursive` los trae). Se usan para la
  búsqueda estratégica en vivo con Playwright del Menú 3 (`vvca_audit.ts`), no para
  `vigilancia_dof.py` / `vigilancia_jurisprudencial.py`. No fue necesario tocarlos ni
  inicializarlos para esta reparación.

---

## 3. Legal Data Availability Contract

Contrato fijo, implementado en `itosturre/vigilancia/contrato.py`, usado por los tres
watchers y por cualquier consumidor futuro de sus resultados.

### 3.1 `ResultadoFuente` — resultado de UN collector para UNA fuente

```python
ResultadoFuente(
    source="DOF",                 # o "SAT", o "SJF:<tema>"
    status="SUCCESS",              # ver estados abajo
    retrieved_at="2026-09-11T18:03:00+00:00",
    items=[...],                   # SOLO si status == SUCCESS (puede ser [] si no hubo novedades)
    evidence=[...],                # lo que la fuente entregue (URL, hash) — nunca inferido
    errors=[...],                  # detalle del fallo si status != SUCCESS
    execution_environment="Linux/host-abc",
    retryable=False,
)
```

**Invariante forzada por código** (`ResultadoFuente.__post_init__`): un `status` distinto de
`SUCCESS` nunca lleva `items` — si algo intenta construir ese estado inconsistente, lanza
`ValueError` en el momento, no en producción.

### 3.2 Estados mínimos

| Estado | Significado | ¿Reintentable? |
|---|---|---|
| `SUCCESS` | La fuente respondió; `items` puede estar vacío (genuinamente sin novedades) | n/a |
| `SOURCE_UNAVAILABLE` | No se pudo consultar la fuente (red, bloqueo de política, 5xx) | Depende del caso concreto |
| `AUTH_REQUIRED` | La fuente exige autenticación/autorización que no se tiene | No |
| `PARSER_ERROR` | La fuente respondió pero el cuerpo no se pudo interpretar | No (cambió el contrato de la fuente) |
| `VALIDATION_FAILED` | La respuesta no pasó una validación de forma esperada | No |
| `TIMEOUT` | La fuente no respondió a tiempo | Sí |
| `UNKNOWN_ERROR` | Cualquier otra falla no clasificada | Sí (conservador) |

`itosturre.vigilancia.contrato.clasificar_excepcion_red(exc)` mapea una excepción de
`requests` a `(status, retryable, mensaje)`. La distinción operativa clave:

- Un **bloqueo de política de red del entorno** (`ProxyError`, o un `ConnectionError` cuyo
  mensaje delata un 403/CONNECT rechazado) → `SOURCE_UNAVAILABLE`, `retryable=False`.
  Reintentar en el MISMO entorno nunca lo resuelve.
- Un **timeout** → `TIMEOUT`, `retryable=True`.
- Cualquier otro error de red → `SOURCE_UNAVAILABLE`, `retryable=True` (conservador: no se
  asume un bloqueo de política sin evidencia en el mensaje).

`agentes/vigilancia_jurisprudencial.py::_http()` usa esta clasificación para **cortar los
reintentos exponenciales (2s/4s/8s) de inmediato** cuando el error no es reintentable, en
vez de agotar ~14 segundos por tema sin ninguna posibilidad de éxito.

### 3.3 "Sin novedades" vs. "no pude consultar" — la distinción que este contrato existe para proteger

| Situación | `status` | `items` | Texto que debe aparecer en el reporte |
|---|---|---|---|
| Se consultó la fuente, no había nada relevante | `SUCCESS` | `[]` | *"Sin hallazgos/criterios identificados hoy/esta semana"* |
| No se pudo consultar la fuente | `SOURCE_UNAVAILABLE` (u otro estado de error) | `[]` | *"❌ SOURCE_UNAVAILABLE — no se pudo consultar [fuente]"* |

Confundir ambas filas es exactamente el error de fondo que el protocolo anti-alucinación de
`CLAUDE.md` prohíbe (Regla 4 y Regla 7): un silencio no verificado no es una ausencia
verificada. Antes de esta reparación, el código producía la fila 1 en ambos casos.

### 3.4 Persistencia: sidecar `.json` junto al `.md`

Cada watcher guarda, junto al brief/informe legible en Markdown, un `.json` del mismo nombre
con el contrato crudo (`itosturre.vigilancia.contrato.guardar_sidecar`):

```
Itosturre/Vigilancia/2026-09-11.md    # para el abogado
Itosturre/Vigilancia/2026-09-11.json  # para cualquier consumidor automatizado
Itosturre/Jurisprudencia/semana-2026-W37.md
Itosturre/Jurisprudencia/semana-2026-W37.json
```

`contenido_linkedin.py` **lee el `.json`, nunca re-deriva el estado parseando el Markdown**
— el Markdown está redactado para humanos (puede reformular, resumir, traducir a prosa) y
no es una fuente confiable para decidir programáticamente si hubo o no un hallazgo real.

`Itosturre/` es la carpeta de salida de estos tres watchers (briefs, contratos, borradores,
log de eventos). Es contenido generado y regenerable — no código — así que está en
`.gitignore` (`/Itosturre/`, ver también `docs/POLITICA_DATOS.md`).

### 3.5 Observabilidad

`itosturre.vigilancia.contrato.registrar_evento(evento, **datos)` anexa una línea JSON a
`Itosturre/eventos.jsonl`. Eventos válidos (los únicos que la función acepta):

```
watch_started · collector_started · source_requested · source_success ·
source_unavailable · validation_started · validation_passed · validation_failed ·
draft_generated · draft_blocked
```

Nunca se registran secretos ni credenciales — solo nombre de fuente, estado, y metadatos
operativos (`n_items`, `retryable`, `motivo`).

---

## 4. Regla del bloqueo de contenido (`contenido_linkedin.py`)

```python
es_valido, motivo = validar(contexto)
if not es_valido:
    # LinkedIn: NOT_GENERATED — se escribe el motivo, nunca un post genérico
    ...
```

`validar()` distingue dos motivos de bloqueo (ambos con el mismo resultado — no se genera
nada — pero registrados distinto, porque son jurídica y operativamente diferentes):

- **`SOURCE_UNAVAILABLE`** — ninguna fuente pudo consultarse, o las que respondieron no
  aportaron ningún hallazgo utilizable.
- **`SIN_HALLAZGOS`** — las fuentes SÍ se consultaron (status `SUCCESS`) pero no había nada
  noticiable. Esto no es un fallo: simplemente no hay post que escribir hoy.

Si **al menos una** fuente aporta ≥1 hallazgo validado (`status == SUCCESS` y `items` no
vacío), la generación continúa usando **solo** esas fuentes — las marcadas
`SOURCE_UNAVAILABLE` se excluyen explícitamente del prompt al LLM, con una instrucción que
prohíbe tratarlas como si fueran un "sin novedades".

---

## 5. Idempotencia

Los tres watchers usan el mismo mecanismo, ya existente y suficiente para el caso de uso
(ejecución diaria/semanal vía cron): si el archivo de salida del día/semana ya existe, el
script no vuelve a golpear la red ni a regenerar contenido — simplemente termina.

```
Itosturre/Vigilancia/{YYYY-MM-DD}.md          — una vez por día
Itosturre/Jurisprudencia/semana-{YYYY-Www}.md — una vez por semana
Itosturre/Contenido/borrador-{YYYY-MM-DD}.md  — una vez por día
```

Esto se conserva incluso cuando el resultado del día fue `SOURCE_UNAVAILABLE` o
`NOT_GENERATED`: es una decisión deliberada (no ejecutar dos veces el mismo día), documentada
aquí para quien necesite forzar un reintento manual — borrar el archivo del día antes de
volver a invocar el script es la vía explícita para eso, no se añadió un flag `--force`
porque no hacía falta para el caso de uso actual.

---

## 6. Cómo ejecutar el watch manualmente

Desde la raíz del repositorio, en un entorno con egress autorizado hacia las tres fuentes
(ver §2):

```bash
python agentes/vigilancia_dof.py
python agentes/vigilancia_jurisprudencial.py
python agentes/contenido_linkedin.py
```

Variables de entorno relevantes:

- `ANTHROPIC_API_KEY` — opcional. Sin ella, los tres scripts corren en modo degradado/
  placeholder (datos crudos, sin redacción LLM) en vez de fallar.
- `ITOSTURRE_EXEC_ENV` — opcional, recomendado en producción. Identifica en qué máquina
  corrió el collector (queda en el contrato `.json` y ayuda a diagnosticar un
  `SOURCE_UNAVAILABLE` sin adivinar). Ejemplo: `ITOSTURRE_EXEC_ENV="oficina-jorge-win11"`.

**Recomendación para la tarea programada de la cuenta:** su prompt almacenado debe invocar
estos tres comandos (o un wrapper que los llame en orden) en un entorno con acceso real a
DOF/SAT/SJF — nunca pedirle a Claude que "revise el DOF/SAT/SJF" en lenguaje libre dentro de
una sesión cuya política de red no lo permite. Ese cambio de configuración vive en la
plataforma de tareas programadas, no en este repositorio, y debe hacerlo quien administre esa
tarea.

---

## 7. Diagnosticar `SOURCE_UNAVAILABLE`

1. Abrir el `.json` del día/semana en `Itosturre/Vigilancia/` o `Itosturre/Jurisprudencia/`.
2. Por cada fuente con `status != "SUCCESS"`, leer `errors` y `execution_environment`.
3. Si `retryable: false` y el mensaje menciona bloqueo de política/proxy/403 en el CONNECT:
   **no reintentar en el mismo entorno.** Ejecutar el watcher en un entorno distinto (ver §2)
   o pedir que se autorice esa salida de red en la política del entorno actual —
   **nunca** desde el código: no instalar un proxy propio, no cambiar DNS, no simular la
   respuesta de la fuente. La restricción es de infraestructura/política, no un bug de este
   repositorio, y "arreglarla" con un bypass técnico convertiría un control de seguridad
   deliberado en un agujero — y encima seguiría sin darle al collector acceso *autorizado*.
4. Si `retryable: true` (timeout, error 5xx, error de red genérico sin evidencia de bloqueo):
   puede ser transitorio — reintentar más tarde es razonable.
5. Si el estado es `PARSER_ERROR`: la fuente probablemente cambió su formato de respuesta
   (p. ej. el microservicio del SJF cambió su contrato JSON). No es un problema de red;
   requiere actualizar el parser del collector correspondiente.

---

## 8. Verificar que la evidencia jurídica es auténtica

- **SJF:** cada ficha de `vigilancia_jurisprudencial.py` lleva `hash_sha256`, calculado sobre
  los bytes crudos de la respuesta `GET /tesis/{ius}` — reproducible con
  `hashlib.sha256(requests.get(url, headers=HEADERS).content).hexdigest()` contra el mismo
  IUS. Es cadena de custodia mínima, no una firma criptográfica de la SCJN.
- **DOF/SAT:** el collector actual NO captura evidencia más allá de la URL y el texto
  extraído (no hay hash ni captura de pantalla). Esta es una limitación documentada, no un
  supuesto de autenticidad — antes de citar un hallazgo de DOF/SAT en un escrito o post,
  ábrelo en `dof.gob.mx`/`sat.gob.mx` y verifica manualmente, tal como exige el protocolo
  anti-alucinación general de `CLAUDE.md`.
- Ningún campo de localización (IUS, época, sala, fecha, rubro) se completa por inferencia
  cuando la fuente no lo entrega — queda `⚠️ no disponible` o vacío, nunca relleno.

---

## 9. Cómo se impide la generación de contenido sin fuentes

Ver §4. Resumen operativo: `agentes/contenido_linkedin.py` **no puede** llegar a redactar un
post (ni siquiera el modo placeholder sin LLM) sin que `validar()` haya devuelto
`es_valido=True`, lo cual exige al menos un `ResultadoFuente` con `status == SUCCESS` y
`items` no vacío en el contrato `.json` de vigilancia o de jurisprudencia. No existe una ruta
de código que genere el post "por si acaso" cuando la validación falla.

---

## 10. Pruebas

```bash
python -m unittest tests.test_vigilancia_contrato tests.test_vigilancia_watch -v
```

Cubren:

- El contrato (`ResultadoFuente`, clasificación de excepciones, observabilidad, sidecar
  `.json`) de forma aislada, sin red.
- Los 5 escenarios de este encargo, con red simulada (`unittest.mock`) — ninguna prueba
  depende de acceso real a DOF/SAT/SJF:
  - **A.** Todas las fuentes disponibles → hay hallazgo → se genera el post de LinkedIn.
  - **B.** DOF bloqueado, SAT/SJF disponibles → no se inventa DOF; el proceso sigue con lo
    válido.
  - **C.** SJF bloqueado → no se afirma ningún criterio jurisprudencial.
  - **D.** Todas las fuentes bloqueadas → `Watch result: SOURCE_UNAVAILABLE` en ambos
    watchers y `LinkedIn: NOT_GENERATED` en el generador de contenido. (Se prueba también la
    variante "fuentes disponibles pero sin hallazgos", que bloquea por `SIN_HALLAZGOS` en
    vez de `SOURCE_UNAVAILABLE` — son motivos distintos.)
  - **E.** Ejecución repetida el mismo día/semana → no duplica briefs, informes ni borradores,
    y no vuelve a golpear la red.
  - Un caso adicional verifica que un bloqueo de política de red corta los reintentos
    exponenciales del collector SJF en el primer intento (no gasta 14 s intentando algo que
    no puede resolverse en el mismo entorno).

---

## 11. Limitaciones que siguen dependiendo de infraestructura externa a este repositorio

- **El acceso real a DOF/SAT/SJF no se puede resolver desde el código.** Esta reparación
  hace que la ausencia de acceso se reporte de forma correcta y controlada — no le da acceso
  a un entorno que no lo tiene, ni debía hacerlo.
- **La configuración de la tarea programada de la cuenta** (qué prompt/comando dispara este
  watch, y en qué entorno corre) vive fuera de este repositorio. La recomendación de §6 no
  se puede aplicar con un commit aquí.
- **DOF/SAT no tienen captura de evidencia forense** (a diferencia del SJF, que sí tiene
  hash SHA-256 por ficha). Añadir eso — por ejemplo, guardar el HTML crudo o una captura,
  siguiendo el patrón de `capturar_rag.py`/`vvca_audit.ts` — es una extensión futura, fuera
  del alcance mínimo de esta reparación.
