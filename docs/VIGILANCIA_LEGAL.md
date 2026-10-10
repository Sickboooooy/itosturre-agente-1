# Vigilancia legal automatizada — DOF/SAT + SJF

**Estado:** vigente desde 11-sep-2026 · reparación arquitectónica del watch programado.
Actualizado el 10-oct-2026 con el contrato de corrida (§3.6): salidas fuera del paquete,
fecha de la Ciudad de México, códigos de salida y ningún brief cuando la fuente primaria
no responde.
**Alcance:** `agentes/vigilancia_dof.py`, `agentes/vigilancia_jurisprudencial.py`,
`agentes/contenido_linkedin.py`, `itosturre/vigilancia/` (`contrato.py` por fuente,
`rutina.py` por corrida). Prompts de las rutinas programadas: `docs/RUTINAS.md`.

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
Evidence — items + contrato .json (itosturre/vigilancia/contrato.py) junto al .md,
        │  y el estado de la corrida .estado.json (itosturre/vigilancia/rutina.py)
        │  SI la fuente primaria no respondió → sin .md, solo .estado.json, salida 2
        ▼
Validator — agentes/contenido_linkedin.py: validar() antes de generar nada,
        solo con briefs vigentes (últimos 7 días)
        ▼
Content Generator — agentes/contenido_linkedin.py: genera SOLO si hay ≥1 hallazgo
        con status SUCCESS; si no, no escribe borrador: deja el motivo en
        borrador-YYYY-MM-DD.estado.json y sale con código 3.
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
salidas/Vigilancia/2026-09-11.md            # para el abogado
salidas/Vigilancia/2026-09-11.json          # contrato: para cualquier consumidor automatizado
salidas/Vigilancia/2026-09-11.estado.json   # estado de la corrida (§3.6)
salidas/Jurisprudencia/semana-2026-W37.md
salidas/Jurisprudencia/semana-2026-W37.json # fichas crudas con su SHA-256 (cadena de custodia)
salidas/Jurisprudencia/semana-2026-W37.estado.json
```

`contenido_linkedin.py` **lee el `.json`, nunca re-deriva el estado parseando el Markdown**
— el Markdown está redactado para humanos (puede reformular, resumir, traducir a prosa) y
no es una fuente confiable para decidir programáticamente si hubo o no un hallazgo real.

La raíz de salida es `$ITOSTURRE_SALIDA` o, por omisión, `salidas/` en la raíz del repo
(una ruta relativa se resuelve desde la raíz, no desde el directorio actual). Es contenido
generado y regenerable — no código — así que está en `.gitignore` (`/salidas/`, ver también
`docs/POLITICA_DATOS.md`).

**Por qué ya no es `Itosturre/`:** en macOS y Windows (sistemas de archivos sin distinción de
mayúsculas) `Itosturre/` y el paquete de código `itosturre/` son la misma carpeta: los briefs
caían dentro del paquete y la regla `/Itosturre/` de `.gitignore` ignoraba también cualquier
módulo nuevo de `itosturre/`, que nunca habría llegado al repo. `rutina.validar_salida()`
rechaza, sin distinguir mayúsculas, cualquier salida dentro del paquete, y
`tests/test_vigilancia_rutina.py` falla si una regla de `.gitignore` vuelve a ignorarlo.

### 3.5 Observabilidad

`itosturre.vigilancia.contrato.registrar_evento(evento, **datos)` anexa una línea JSON a
`salidas/eventos.jsonl` (junto a las salidas, nunca dentro del paquete). Eventos válidos
(los únicos que la función acepta):

```
watch_started · collector_started · source_requested · source_success ·
source_unavailable · validation_started · validation_passed · validation_failed ·
draft_generated · draft_blocked
```

Nunca se registran secretos ni credenciales — solo nombre de fuente, estado, y metadatos
operativos (`n_items`, `retryable`, `motivo`).

### 3.6 Contrato de corrida: estado y código de salida

`itosturre/vigilancia/rutina.py` fija lo que cada corrida deja para quien la orquesta (cron,
rutina programada, CI). Toda corrida que consulta escribe `<clave>.estado.json` (`clave` =
nombre del brief sin `.md`) con `estado`, `codigo_salida`, la hora de la Ciudad de México y el
resumen por fuente (status, errores, reintentable, número de hallazgos, entorno):

| Script | Situación | Brief/borrador | `estado` | Salida |
|---|---|---|---|---|
| `vigilancia_dof.py` | DOF y SAT respondieron | sí | `OK` | 0 |
| | SAT no respondió (secundaria) | sí, con ❌ SAT | `PARCIAL` | 0 |
| | DOF no respondió (primaria; el SAT ni se consulta) | **no** | `FUENTE_INACCESIBLE` | 2 |
| `vigilancia_jurisprudencial.py` | los 5 temas respondieron | sí | `OK` | 0 |
| | alguno no respondió | sí, con ❌ en ese tema | `PARCIAL` | 0 |
| | ninguno respondió | **no** | `FUENTE_INACCESIBLE` | 2 |
| `contenido_linkedin.py` | ≥1 hallazgo `SUCCESS` en un brief vigente | sí | `OK` | 0 |
| | sin briefs vigentes, fuentes caídas o sin novedades | **no** | `SIN_INSUMOS` (+ `motivo`) | 3 |

Una salida 1 es un error no previsto o de configuración (p. ej. `$ITOSTURRE_SALIDA` dentro del
paquete). Un tema del SJF cuya búsqueda devolvió IUS pero ninguna ficha legible queda
`SOURCE_UNAVAILABLE`: no hay criterio verificado, y una ficha con `_error` nunca cuenta como
hallazgo para el generador de contenido.

La **fecha operativa** es la de la Ciudad de México (`rutina.hoy_mx()`), no la del servidor:
los contenedores de las rutinas corren en UTC. Sin base de zonas IANA (Windows sin el paquete
`tzdata`) se usa UTC-6 fijo, que da la misma fecha porque la Ciudad de México no tiene horario
de verano desde octubre de 2022.

---

## 4. Regla del bloqueo de contenido (`contenido_linkedin.py`)

```python
es_valido, motivo = validar(contexto)
if not es_valido:
    # Sin borrador: ni post genérico ni aviso en su lugar. El motivo va al estado.
    rutina.registrar_estado(OUTPUT_DIR, OUTPUT_FILE.stem, rutina.SIN_INSUMOS, motivo=motivo, ...)
    return rutina.EXIT_SIN_INSUMOS
```

`validar()` distingue tres motivos de bloqueo (todos con el mismo resultado — no se escribe
borrador, el motivo queda en `borrador-YYYY-MM-DD.estado.json` y la salida es 3 — pero
registrados distinto, porque son jurídica y operativamente diferentes):

- **`SIN_INSUMOS`** — no hay briefs vigentes (últimos 7 días) de ninguna de las dos
  vigilancias. Un brief viejo no se recicla como si fuera "lo de esta semana".
- **`SOURCE_UNAVAILABLE`** — las fuentes de los briefs vigentes no pudieron consultarse, o
  sus contratos `.json` faltan o son ilegibles (no se puede verificar que hubo consulta).
- **`SIN_HALLAZGOS`** — las fuentes SÍ se consultaron (status `SUCCESS`) pero no había nada
  noticiable. Esto no es un fallo: simplemente no hay post que escribir hoy.

No se escribe un aviso `NOT_GENERATED` en lugar del borrador: con el nombre del borrador del
día, ese aviso bloquearía la corrida posterior que sí tuviera insumos.

Si **al menos una** fuente aporta ≥1 hallazgo validado (`status == SUCCESS` y `items` no
vacío), la generación continúa usando **solo** esas fuentes — las marcadas
`SOURCE_UNAVAILABLE` se excluyen explícitamente del prompt al LLM, con una instrucción que
prohíbe tratarlas como si fueran un "sin novedades".

---

## 5. Idempotencia

Los tres scripts usan el mismo mecanismo: si el archivo de salida del día/semana ya existe, el
script no vuelve a golpear la red ni a regenerar contenido — termina con salida 0 y **no toca
el `.estado.json`**, que sigue describiendo la corrida que sí consultó.

```
salidas/Vigilancia/{YYYY-MM-DD}.md          — una vez por día
salidas/Jurisprudencia/semana-{YYYY-Www}.md — una vez por semana
salidas/Contenido/borrador-{YYYY-MM-DD}.md  — una vez por día
```

**Una corrida fallida no escribe ese archivo** (fuente primaria caída, ningún tema del SJF,
ningún insumo para el borrador): así la guarda no bloquea el reintento del mismo día o semana.
Antes, la guarda junto con "escribir siempre" dejaba el periodo sin vigilancia real y sin
posibilidad de reintento ("pozo envenenado"). Un resultado `PARCIAL` sí escribe el brief y
cierra el periodo; para reintentarlo, borrar el `.md` (y su `.json`) antes de volver a invocar
el script — no se añadió un flag `--force` porque no hacía falta para el caso de uso actual.

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

- `ANTHROPIC_API_KEY` — opcional. Sin ella (o sin la librería `anthropic`), los tres scripts
  corren en modo degradado/placeholder (datos crudos, sin redacción LLM) en vez de fallar.
- `ITOSTURRE_MODELO` — opcional. Modelo para la redacción vía API; una sola definición para
  los tres scripts (`rutina.modelo()`), ningún agente fija el modelo en su código.
- `ITOSTURRE_SALIDA` — opcional. Raíz de salidas (por omisión `salidas/`); nunca dentro del
  paquete `itosturre/` (§3.4).
- `ITOSTURRE_WHATSAPP` — opcional. Número del CTA del borrador (`wa.me/<número>`); sin ella
  queda el marcador `[número]`.
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

1. Abrir el `.estado.json` del día/semana en `salidas/Vigilancia/` o
   `salidas/Jurisprudencia/` (existe aunque no se haya escrito brief; el `.json` del contrato
   solo existe junto a un brief).
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
python -m unittest tests.test_vigilancia_contrato tests.test_vigilancia_rutina tests.test_vigilancia_watch -v
```

Cubren:

- El contrato por fuente (`ResultadoFuente`, clasificación de excepciones, bloqueo de
  política frente a timeout, observabilidad, sidecar `.json`) de forma aislada, sin red.
- El contrato de corrida (`rutina.py`): salida por omisión y por variable, rechazo de rutas
  dentro del paquete con cualquier mayúscula, que `.gitignore` no ignore módulos nuevos de
  `itosturre/` (con `core.ignorecase=true` forzado, también en Linux), fecha de la Ciudad de
  México y su respaldo UTC-6, briefs vigentes, estados y códigos de salida, modelo único.
- Los escenarios de los watchers con red simulada (`unittest.mock`) — ninguna prueba depende
  de acceso real a DOF/SAT/SJF ni a la API de Anthropic:
  - **A.** Todas las fuentes disponibles → brief, informe y borrador.
  - **B.** DOF caído → sin brief (salida 2) y el SAT ni se consulta; el SJF sigue y sostiene
    el borrador. **B2.** SAT caído → brief `PARCIAL` que lo dice.
  - **C.** SJF caído → sin informe (salida 2) y una sola petición; detalle ilegible → el tema
    no cuenta como criterio. **C2.** Un tema caído → informe `PARCIAL` sin "sin criterios" en
    ese tema.
  - **D.** Todo caído → ningún brief, informe ni borrador (salidas 2, 2 y 3). **D2.** Fuentes
    disponibles sin novedades → sin borrador por `SIN_HALLAZGOS`.
  - **E.** Ejecución repetida → no duplica, no vuelve a golpear la red, no pisa el estado.
  - **F.** Una corrida fallida no bloquea el reintento del día o la semana.
  - Piezas sueltas: `None` ≠ `[]` en la búsqueda del SJF, corte de reintentos ante bloqueo de
    política, informe degradado con "Nuevos esta semana"/"Contexto" e instancia, briefs viejos
    que no se reciclan, CTA por variable, y la rama con LLM con un `anthropic` falso (modelo
    configurado, aviso de fuente caída, caída al modo sin LLM si falta la librería).

---

## 11. Limitaciones que siguen dependiendo de infraestructura externa a este repositorio

- **El acceso real a DOF/SAT/SJF no se puede resolver desde el código.** Esta reparación
  hace que la ausencia de acceso se reporte de forma correcta y controlada — no le da acceso
  a un entorno que no lo tiene, ni debía hacerlo.
- **La configuración de la tarea programada de la cuenta** (qué prompt/comando dispara este
  watch, y en qué entorno corre) vive fuera de este repositorio. La recomendación de §6 no
  se puede aplicar con un commit aquí.
- **Detalle del SJF tras un desafío anti-bots (verificado el 10-oct-2026).** El POST de
  búsqueda del microservicio responde JSON, pero `GET /tesis/{ius}` devuelve la página de
  Incapsula en lugar de la ficha. El watcher marca esos temas `SOURCE_UNAVAILABLE` (no
  reintentable) con ese diagnóstico, no escribe informe si ningún tema queda verificable y
  **no intenta evadir el control**. Leer el detalle requiere la vía con navegador del repo
  (`services/itosturre-scraper`, `vvca_audit.ts`): decisión de arquitectura pendiente.
- **DOF sin `www`.** El certificado del portal solo ampara `dof.gob.mx`; con `www` la
  verificación TLS falla por nombre. El collector usa `https://dof.gob.mx` y resuelve los
  enlaces relativos de la portada con `urljoin`. Nunca desactivar la verificación TLS.
- **SAT lento.** En la corrida real del 10-oct-2026 `www.sat.gob.mx` no respondió en 20 s
  (`TIMEOUT`): el brief salió `PARCIAL` con el aviso, como dicta el contrato.
- **DOF/SAT no tienen captura de evidencia forense** (a diferencia del SJF, que sí tiene
  hash SHA-256 por ficha). Añadir eso — por ejemplo, guardar el HTML crudo o una captura,
  siguiendo el patrón de `capturar_rag.py`/`vvca_audit.ts` — es una extensión futura, fuera
  del alcance mínimo de esta reparación.
