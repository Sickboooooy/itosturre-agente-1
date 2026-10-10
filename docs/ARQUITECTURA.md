# Arquitectura de `itosturre-agente`

**Estado:** vigente desde 31-jul-2026  
**Alcance:** repositorio padre del auditor VVCA y sus integraciones oficiales.

## Propósito y límites

`itosturre-agente` contiene el núcleo local de verificación jurídica, la orquestación del
pipeline VVCA y la configuración necesaria para que los agentes apliquen ese protocolo.
El scraper SJF y el catálogo de skills son productos con ciclo de vida propio y se integran
como submódulos. El corpus, los índices y los productos de cliente son datos locales, no
código fuente.

```text
Entrada (escrito/caso)
        |
        v
vvca_full.py ------------------------------+
        |                                   |
        v                                   v
OpenNotebook.py                       services/itosturre-scraper
  | extracción de citas                | consulta estratégica SJF
  | recuperación corpus                | vigencia + evidencia visual
  | auditoría normativa                +--------------------------+
  v                                                               |
scoring_vvca.py <--------------------------------------------------+
  | veredicto y semáforo
  v
auditorias/<caso>/vvca_full.json + capturas
```

La consulta SJF en vivo mejora la estrategia y aporta evidencia, pero no sustituye el
corpus local como fuente del veredicto anti-alucinación. Esta separación es una invariante
del producto.

## Componentes

| Componente | Responsabilidad | Persistencia |
|---|---|---|
| `OpenNotebook.py` | Ingesta, recuperación RAG, extracción y auditoría de citas. Se importa sin dependencias pesadas (carga perezosa) y `audit()` admite colección y codificador inyectados para pruebas (R4a) | Código padre |
| `scoring_vvca.py` | Semáforo y veredicto VVCA | Código padre |
| `vvca_full.py` | Orquestación del pipeline completo | Código padre |
| `capturar_rag.py` | Evidencia visual de fuentes recuperadas | Código padre |
| `router_competencia.py` | Enrutamiento determinista de competencia orgánica | Código padre |
| `scripts/` | Bootstrap, cobertura, promoción y regresión | Código padre |
| `agentes/` | Automatizaciones auxiliares de vigilancia y contenido (prompts de las rutinas programadas: `docs/RUTINAS.md`) | Código padre |
| `itosturre/vigilancia/` | Contrato de datos por fuente (SUCCESS/SOURCE_UNAVAILABLE/...) y observabilidad (`contrato.py`); contrato de corrida — salidas fuera del paquete, fecha de la Ciudad de México, estado y códigos de salida (`rutina.py`) — para los watchers DOF/SAT/SJF — ver `docs/VIGILANCIA_LEGAL.md` | Código padre |
| `itosturre/audit/` | Políticas VVCA puras y trazabilidad, sin dependencias RAG. `referencias.py` (R4b): extracción de artículos (sufijos, enumeraciones, rangos) y resolución del ordenamiento por oración y palabra completa; `evidence.py`: encabezado exacto del precepto y definición única del encabezado auténtico; `inexistencia.py` (D10): prueba positiva de inexistencia de un artículo en el cuerpo de la ley indexada (se abstiene ante cualquier ambigüedad); `fragmentacion.py` (4-oct-2026): corte y etiqueta de los fragmentos de la ingesta con esa misma definición, y métricas de cobertura para `ingest --simular` | Código padre |
| `itosturre/leads/` | Normalización, deduplicación, ICP y supresión de prospectos; sin recolección ni envíos | Código padre |
| `itosturre/memoria/` | Memoria contextual: eventos, índice FTS5, ranking y snapshots; sin dependencias externas | Código padre |
| `memoria_cli.py` | Interfaz de la memoria contextual | Código padre |
| `itosturre/plan/` · `plan_audit.py` | Auditor determinista de planes sobre ledger `plan-ledger/1.0`: vocabulario de estados, evidencia oficial, aprobación humana ligada al hash del contenido y cobertura de menciones (PL-001…PL-014; también citas "SIGLA número" y rangos); con un paquete de evidencia, cotejo de identidad (`identidad.py`, C9) y reglas PL-015…PL-019, y cotejo de fidelidad determinista (`fidelidad.py`, C10: señales por categoría, nunca CONFORME) con PL-020. CLI: `plantilla` (ledger de partida con ejemplos `[ASIGNAR]`, `plantilla.py`; MENÚ 16), `lint`, `hash`, `cotejar`, `fidelidad`, `evidencia agregar-tesis`, `evidencia agregar-ley` y `evidencia articulo` (texto exacto del artículo que usa el cotejo). Sin red ni LLM, separado del VVCA | Código padre |
| `itosturre/evidencia/` | Capa de evidencia pura (C7): registro `evidencia/1.0` (URL oficial, fecha de consulta aportada por quien llama, huellas del original y del derivado), fuente única de hosts oficiales, huellas y JSON canónico, parser del SJF anclado en "Registro digital:", limpieza de LeyesBiblio con invariantes, ubicación de artículos (cuerpo / transitorios / indeterminada) y notas de reforma con gramática completa. `validar_registro` es solo estructural y **no habilita VERIFICADO**: hace falta además `comprobar_integridad`, que recalcula las huellas desde el original y el derivado y vuelve a leer la fuente. Solo biblioteca estándar; sin red ni reloj. La única E/S de archivos es `paquete.py`: almacén direccionado por contenido (`registros/<huella>.json`, `objetos/<sha256>`), publicación que falla si el destino existe (enlace duro o `O_EXCL`, nunca comprobar-y-reemplazar), huella verificada en cada lectura y rechazo de enlaces simbólicos y puntos de reanálisis (raíz, `registros/`, `objetos/` y cada archivo, con contención por ruta real); solo guarda registros íntegros con sus artefactos. `plan` puede importarla; ella no importa `plan` ni `audit` | Código padre |
| `scripts/generar_fixtures_evidencia.py` | Regenera `tests/fixtures/evidencia/` desde originales descargados (requiere PyMuPDF); no corre en CI | Código padre |
| `services/itosturre-scraper/` | SJF en vivo, TypeScript y Playwright | Submódulo |
| `services/itosturre-skills/` | Skills jurídicas distribuibles | Submódulo |
| `.claude/skills/` | Fuente versionada de skills vendorizadas | Código padre |
| `.agents/skills/` | Adaptación Codex generada y verificada | Código padre generado |

## Clases de datos

| Clase | Rutas | Política |
|---|---|---|
| Memoria contextual | `~/.itosturre/memoria/*.db` | **Fuera del repositorio**; local, reconstruible; contiene decisiones del despacho |
| Fuente jurídica | `corpus/`, `jurisprudencia/` | Local; no versionar documentos pesados |
| Índice regenerable | `chroma_db/`, `graphify-out/` | Local; reconstruible |
| Producto de cliente | `auditorias/` | Local, confidencial, nunca versionar |
| Paquetes de evidencia de un asunto | `auditorias/<asunto>/plan/…` o fuera del repositorio | Local, confidencial, nunca versionar (D7). `plan_audit.py evidencia agregar-*` y `plantilla --salida` rechazan escribir dentro del repositorio fuera de una zona que la política de datos prohíbe versionar |
| Prospectos B2B | `leads_data/` | Local; incluye consentimientos y exclusiones; nunca versionar |
| Casos sintéticos | `casos_de_prueba/` | Versionados; la regresión usa una lista cerrada |
| Fixtures de evidencia oficial | `tests/fixtures/evidencia/` | Versionados; texto oficial literal (páginas de LeyesBiblio, renders del SJF) con procedencia en `manifiesto.json`; bytes exactos (`.gitattributes`, sin conversión de fin de línea); cada archivo autorizado en `config/data-policy.json` |
| Dependencias | `venv/`, `node_modules/` | Local; regenerables |

## Flujo de evidencia de planes (C7 → C10)

```text
plan_audit.py plantilla --plan-id ID --titulo T --fecha AAAA-MM-DD --salida auditorias/<asunto>/plan/ledger.json
        |  ledger de partida: colecciones vacías + un ejemplo por tipo rotulado [ASIGNAR] (sin datos jurídicos)
        v
innerText del SJF / PDF de LeyesBiblio (obtenidos por el operador; sin red)
        |  plan_audit.py evidencia agregar-tesis | agregar-ley  (--fecha-consulta del operador)
        v
paquete de evidencia  registros/<huella>.json + objetos/<sha256>   (solo si pasa la integridad)
        |  publicación exclusiva (enlace duro / O_EXCL), sin enlaces simbólicos ni junctions
        |  imprime sha256_documento y un bloque de evidencia para pegar
        v
        |  plan_audit.py evidencia articulo --paquete DIR --sha256 H --articulo N
        |  imprime el texto exacto del artículo que usará el cotejo (zona, páginas) y el encabezado
        v
ledger plan-ledger/1.0  evidencias[]: url + sha256_documento + ubicacion + extracto
        |                (+ ultima_reforma_dof opcional para leyes; ubicacion "Artículo N" o "Encabezado…")
        |                decisiones[].advertencias_fuente para las advertencias de la fuente
        |                identificacion_criterio.tipo_fuente: tesis_sjf | sentencia_internacional
        v
plan_audit.py cotejar --ledger L --paquete DIR      → CONFORME / DISCREPANTE / SIN_EVIDENCIA por par
plan_audit.py fidelidad --ledger L --paquete DIR    → SENALES / SIN_SENALES_DETECTADAS / NO_COTEJABLE por afirmación
plan_audit.py lint --ledger L --paquete DIR         → PL-001…PL-014 + PL-015…PL-020
```

El cotejo de identidad comprueba, en este orden y fallando cerrado: vínculo (huella del
original y URL exacta; un solo registro) → registro utilizable → integridad con los
objetos del paquete y, para leyes, **relación original–texto** (el texto extraído se
reproduce re-extrayendo el PDF con el mismo extractor y versión que declara el registro;
`Extractor` inyectado, PyMuPDF en la CLI; sin él → SIN_EVIDENCIA) → documento y versión
(registro digital de la tesis; registros y claves que menciona la afirmación; última
reforma de la ley; día de la consulta) → ubicación (artículo único en el cuerpo, sin
rangos ni enumeraciones; artículos y ley que menciona la afirmación frente al artículo
ubicado y al ordenamiento, fijado por archivo **y** título del encabezado) → campos
críticos y extracto. Por afirmación, cada registro, clave o artículo mencionado debe
quedar cubierto por una evidencia CONFORME. Un CONFORME cuya fuente trae advertencias
requiere decisión humana. Identidad no es fidelidad (PR-4) y el cotejo nunca aprueba ni
cambia estados (D3). El cotejo lleva la huella del ledger y del paquete sobre los que se
calculó: `lint_ledger(..., cotejo=)` rechaza (`ValueError`) uno de otro contenido.

Correcciones tras el piloto PEN-01 (informe local del piloto, no versionado; defectos
D1–D10 del kit), con la ronda 2 tras la revisión externa. Principio: relajar una regla
nunca crea un CONFORME sobre algo que no se cotejó.

- **Menciones** (`menciones.py`): citas "SIGLA número" ("CNPP 167", "CFF 113 Bis", "CPEUM
  1º", "LAmp 217") con la ley de la sigla, sin siglas ajenas al diccionario ni números que
  no son artículos (años, fechas, montos, folios, unidades; nunca "LA"); rangos con el
  contrato del VVCA (`MAX_RANGO`; uno mayor deja sus intermedios como `RANGO` de cobertura
  incompleta) y sin perder lo que sigue al rango ("105, 108-112 y 114"). Ronda 2: la letra
  de un artículo cuenta ("29-A" y "4o.-A" son otros artículos, también en `clave_articulo`)
  y cada número de una enumeración o rango pasa la misma validación que el primero
  ("CFF 28, 29-A y 30" da tres menciones; "CFF 28, 10.5" una).
- **Remisión documentada por la fuente (ronda 2):** un artículo se exime de evidencia
  propia solo si la afirmación lo cita **con ley**, el extracto CONFORME de una ley citada
  por la misma afirmación lo nombra con la **misma** ley, no está en sus `referencias` y el
  texto lo presenta como remisión en cada aparición ("el art. 108 CFF remite al art. 400
  Bis del CPF"). Aun así no se coteja: advertencia PL-019 y el agregado no es "todo
  conforme". Sin ley, con otra ley, en `referencias` o como fundamento propio: PL-016.
- **Encabezado del compilado:** ubicación "Encabezado…" (con página y "de M" opcionales,
  que deben ser los del encabezado registrado); el extracto debe ser **igual** al título o a
  la línea "Última(s) Reforma(s) DOF …" y a `titulo`/`ultima_reforma_dof` del registro; la
  afirmación **debe** nombrar, con sigla o nombre del catálogo, el ordenamiento de la
  evidencia y ningún otro (sin él, con uno fuera del catálogo o con otro además:
  SIN_EVIDENCIA). La cabecera solo acredita denominación, última reforma y páginas: si
  todas las evidencias CONFORME de una afirmación son de cabecera y el texto dice algo más
  (vigencia, contenido normativo, otra fecha u otro número), el agregado queda
  SIN_EVIDENCIA. `LNMASCMP.pdf` se suma a `ARCHIVOS_LEYESBIBLIO` (título confirmado contra
  `LEYES`).
- **Tesis (ronda 2):** el extracto de un criterio judicial solo vale si sale de la propia
  tesis: los campos de su ficha (fuente, instancia…), su rubro, su texto o su frase de
  publicación (`sjf.region_criterio`); de precedentes, contendientes o notas (pueden traer
  rubros de otras tesis) queda SIN_EVIDENCIA, y del banner o del pie del portal,
  DISCREPANTE. Solo un `hecho_aportado` puede omitir `identificacion_criterio`: coteja URL,
  huella, registro mencionado y extracto literal (obligatorio) en la ficha, del ancla al
  pie (`sjf.region_tesis`), nunca en el banner.
- **Evidencia citada sin cotejar:** un agregado CONFORME con pares SIN_EVIDENCIA lo dice en
  una nota y en `pares_sin_cotejar`, cuenta como hallazgo del cotejo y el lint lo reporta
  como PL-018 (ADVERTENCIA, no bloquea). Una afirmación compuesta cuya parte sin cotejar
  no genera menciones (p. ej. una fecha que solo da un DOF) solo advierte: se recomienda
  descomponerla para que cada parte cite su propia evidencia.
- **PL-007 por tipo de fuente:** `identificacion_criterio.tipo_fuente` (`tesis_sjf`, por
  omisión, con los diez campos de siempre; `sentencia_internacional`: `caso`,
  `serie_numero`, `fecha`, `parrafo`); sin él, un criterio cuyas evidencias son todas de
  la Corte IDH se lee como sentencia internacional. Ronda 2: el tipo declarado debe ser
  compatible con las evidencias (`sentencia_internacional` exige alguna de la Corte IDH y
  ninguna del SJF; `tesis_sjf` no puede citar la Corte IDH); si no, PL-007. Esquema en
  `ledger.py`.
- **Caché:** pasos a–c una vez por evidencia equivalente (huella, URL, naturaleza) y
  re-extracción una vez por documento y extractor (huella del original, nombre y versión):
  el cotejo del piloto pasó de 36 re-extracciones (22 s) a 7 (7 s).
- **`evidencia agregar-tesis`** advierte si el archivo trae CRLF e imprime la huella del
  archivo (`sha256_documento`) y la del texto con LF (la del innerText capturado).

| Regla | Severidad | Cuándo |
|---|---|---|
| PL-015 | BLOQUEANTE | VERIFICADO que cita una evidencia DISCREPANTE |
| PL-016 | BLOQUEANTE | VERIFICADO sin evidencia CONFORME, o cuyas menciones no cubre ninguna evidencia CONFORME (sostiene a lo sumo NO VERIFICABLE) |
| PL-017 | BLOQUEANTE si VERIFICADO; ALTA si no | Evidencia CONFORME con advertencias de la fuente sin una decisión con `advertencias_fuente` (evidencia, `sha256_documento` o `huella_registro` vigentes, códigos y resolución) y responsable humano; para VERIFICADO, además APROBADA |
| PL-018 | ADVERTENCIA (no bloquea) | Afirmación cuyo agregado quedó CONFORME por unas evidencias y cita otras SIN_EVIDENCIA (p. ej. un DOF, tipo no soportado): lo que solo esas sostienen no está cotejado |
| PL-019 | ADVERTENCIA (no bloquea) | Artículo remitido sin cotejar: eximido como remisión documentada por la fuente (misma ley en el extracto CONFORME, fuera de `referencias`, presentado como remisión) |
| PL-020 | Señal de precisión `alta`: BLOQUEANTE en VERIFICADO, ALTA en otro estado. Señal `revisar`: ADVERTENCIA ("señal a revisar") en cualquier estado | Señal de fidelidad (`fidelidad.py`) sin una decisión humana con `fidelidad` ligada al plan, la afirmación (`contenido_sha256` vigente), la versión del motor y la huella, el código, la fuente, el artículo y el `sha256_documento` de cada señal; para VERIFICADO, además resolución y APROBADA |

Las reglas del cotejo viven en `REGLAS_COTEJO`, no en `REGLAS`: sin `--paquete` el lint,
sus hallazgos y el Gold Set de planes son los de PR-1 (el resumen por severidad trae además
`ADVERTENCIA`, siempre en 0 sin paquete). Ninguna salida de `lint` (`--json`/`--md`) puede
quedar dentro del paquete.

### Cotejo de fidelidad (C10, PR-4)

Identidad no es fidelidad: un par CONFORME garantiza qué documento, qué versión y qué artículo
respaldan la afirmación; `itosturre/plan/fidelidad.py` compara después lo que la afirmación
**afirma** con lo que el artículo **dice**. Es puro (sin red, reloj ni LLM), lee el paquete
solo a través de `identidad` y **nunca emite CONFORME**: por afirmación da `SENALES`,
`SIN_SENALES_DETECTADAS` o `NO_COTEJABLE` (con motivo; nunca se lee como inexistencia).
`SIN_SENALES_DETECTADAS` se rotula siempre "sin señales detectadas por reglas deterministas;
revisión del abogado obligatoria" (`ETIQUETA_SIN_SENALES`) en la CLI, el JSON y el reporte. No
aprueba ni cambia estados (D3). Motor `VERSION_MOTOR = "2.0"` (ronda 2, tras la revisión
externa que rechazó la ronda 1).

- **Alcance:** afirmaciones `texto_normativo`, `inferencia` y `propuesta`; las demás quedan
  fuera de alcance y una `INEXISTENTE` es NO_COTEJABLE.
- **Texto oficial:** el artículo completo (`tramo_articulo`) de cada par CONFORME de ley; si
  la afirmación no tiene ninguno, sus `referencias` "art. N SIGLA" resueltas contra el paquete
  con el rigor de la identidad (una sola ley del paquete con ese ordenamiento por archivo y
  título, pasos a–c con relación original–texto, artículo único en el cuerpo; el ordinal no
  distingue, como en `clave_articulo`). Lo que no se resuelve queda como motivo o nota
  ("fuentes parciales"): así se cotejan las propuestas e inferencias sin evidencia citada
  (piloto PEN-01: AF-SCT05-06 y REGLA-SCT05). Identidad y fidelidad comparten la caché de
  re-extracción (`cotejar_ledger(cache=)`, `consultar_articulo(cache=)`, `ley_registrada`).
- **Fuente truncada** (el artículo puede continuar en páginas no recibidas, `tramo.truncado`):
  es fuente incompleta; no se emiten señales que dependan de una ausencia en ella (cifra
  ausente, modo de procedibilidad distinto, cifras o marcas que faltan en su última oración).
- **Unidad de comparación:** cláusulas de la afirmación (`;` y fin de oración) frente a
  oraciones del artículo (sin las notas de reforma, `reformas.extraer_notas`), alineadas por
  cobertura de raíces de contenido (fracción de las raíces de la cláusula presentes en la
  oración; el coseno solo desempata), mínimo dos raíces (tres para modal, negación,
  excepciones, cuantificadores y órgano). Si la cláusula nombra un órgano, solo compiten
  oraciones compatibles. Las palabras del inicio del cómputo no deciden la alineación; la
  cifra con su unidad cuenta como una raíz. Las cláusulas que se alinean con la misma
  oración son hermanas (reordenar o separar una oración no "omite" nada).
- **Alineación ambigua:** si un rival tiene puntaje cercano (`FRACCION_RIVAL`) o un órgano
  distinto y cambiaría el resultado, el motor se abstiene y emite `alineacion.ambigua`
  ("revisar"); nunca sale una señal alta de una alineación ambigua.
- **Política de precisión** (ronda 2; criterio por defecto pendiente de confirmación del
  responsable, que puede endurecerlo): cada código tiene una precisión fija en `CODIGOS`.
  Solo tres son `alta` y bloquean en VERIFICADO: `procedibilidad.modo_distinto` (modo
  explícito en la fuente no truncada), `plazos_cifras.distinto_misma_condicion` (cada cifra
  se liga a su condición: "si se tratare de…", "contra…", "tratándose de…", "en los casos
  de…" o un paréntesis tras la cifra; deben compartir `MINIMO_CONDICION` raíces) e
  `inicio_computo.distinto` (distinto del de todas las oraciones candidatas con la misma
  cifra). Todo lo demás —modales, negación, cuantificadores, excepciones y condiciones,
  órgano, cifras sin condición, montos, cifra ausente y todas las omisiones— es `revisar`:
  ADVERTENCIA en cualquier estado.
- **Categorías y códigos** (`CODIGOS`, listas cerradas en el módulo; ampliarlas es decisión del
  responsable):

  | Categoría | Contradicción | Omisión |
  |---|---|---|
  | Procedibilidad (querella, denuncia, de oficio, declaratoria, a petición de parte, SHCP) | modo sin intersección con los del artículo (**alta**); modo que la afirmación niega y el artículo prevé | habla de persecución o procedencia sin el requisito que el artículo impone; requisito de la SHCP sin nombrarla |
  | Plazos y cifras (número + unidad de tiempo, en dígitos con separador de miles o palabras; hábiles/naturales, "de calendario" = naturales; rangos como par; montos: UMA, pesos, "$", salario mínimo, días multa) | plazo distinto para la misma condición (**alta**); número, unidad, calificador o rango distintos de la oración alineada; cifra ausente del texto oficial (solo con fuentes completas y no truncadas) | — |
  | Inicio del cómputo (surta efectos, notificación, momento a momento, publicación, entrada en vigor, conocimiento, "siguientes a / a partir de" + suceso) | inicio distinto (**alta**) | plazo coincidente cuya oración fija un inicio que la afirmación no dice |
  | Modales (deber, facultad, prohibición; "no le está permitido", "le está prohibido", "ninguno … podrá"; mandato implícito del futuro: "se interpondrá", "ordenará") | atenuación, refuerzo o cambio | — |
  | Negación (paridad de la cadena: "no podrá no admitir" es afirmativo) | el mismo predicado, emparejado por complemento, con polaridad distinta | — |
  | Excepciones y condiciones (salvo, excepto, con excepción de, a menos que, sino; siempre que, cuando…) | excepción con contenido distinto | presentes en la oración alineada y ausentes en la cláusula y en sus hermanas |
  | Cuantificadores (universal, negativo, exclusivo) | añadido | omitido uno negativo o exclusivo |
  | Órgano (familias cerradas: jurisdiccional, Ministerio Público, defensor, policía) | órgano de otra familia | — |

  Equivalencia lógica: "no podrá … salvo/sino …" frente a "solo/únicamente …" (en cualquier
  sentido) no genera señales de negación, cuantificador, excepción ni modal.
- **Señal:** código, categoría, severidad (contradicción, omisión o indeterminada), precisión,
  detalle, tramo literal de la afirmación y tramo literal de la fuente (subcadenas exactas;
  un tramo largo se recorta a una ventana literal), marcas, descriptor y artículo de la fuente,
  huellas de los documentos y `huella` (SHA-256 del código, la fuente, el artículo, los
  documentos y los dos tramos).
- **Decisión humana** (`decisiones[].fidelidad`, bloque que imprime `plan_audit.py fidelidad`
  con `plantilla_decision`): `plan`, `afirmacion`, `contenido_sha256` vigente de la afirmación
  (`plan_audit.py hash`), `version_motor` y `senales` con la `huella`, el `codigo`, la
  `fuente`, el `articulo` y el `sha256_documento` (texto o lista) de cada señal que atiende,
  con responsable humano; para una afirmación VERIFICADO, además `resolucion` no vacía y la
  decisión APROBADA (como PL-017: en otros estados basta la decisión registrada). Si cambia
  cualquiera de esos datos (otro plan, otro texto, otro artículo del mismo PDF, otros tramos,
  otra versión de las reglas), deja de valer: una decisión vieja o ajena no atiende una señal
  nueva.
- **CLI:** `fidelidad` sale 0 sin señales, 1 con señales **o si nada fue cotejable** (todo
  NO_COTEJABLE o nada en alcance; `FidelidadLedger.nada_cotejable`) y 2 con entrada inválida.
- **Limitaciones conocidas** (fijadas por prueba y por los casos `LIM-*` del Gold Set, que no
  son puerta): sin análisis sintáctico; la procedibilidad se lee por artículo y no por delito
  (el art. 92 CFF prevé los tres modos: LIM-01); no se señalan enumeraciones incompletas dentro
  de una excepción (LIM-02), órganos fuera de las familias cerradas (LIM-03), sujeto omitido,
  generalizaciones de contenido ni la omisión de "todos"; una cifra que aparece en varias
  oraciones no alineadas no se atribuye; el texto entre corchetes que la fuente declara
  inválido se coteja como texto; tesis, DOF y Corte IDH no tienen texto de artículo
  (NO_COTEJABLE).

### Plantilla del ledger y exposición (MENÚ 16)

`plan_audit.py plantilla` (`itosturre/plan/plantilla.py`, pura) responde al paso más costoso del
piloto PEN-01: construir el ledger a mano. Escribe un `plan-ledger/1.0` válido con `evidencias`,
`contradicciones` y `decisiones` vacías y una afirmación de ejemplo por tipo (`EJEMPLO-TN`, `-CJ`,
`-HA`, `-INF`, `-PROP`): texto, referencias e identificación del criterio son marcadores
`[ASIGNAR]`, el autor es `agente` (la opción más estricta, PL-009) y el estado es `[ASIGNAR]`,
fuera del vocabulario, así que el lint marca cada ejemplo BLOQUEANTE (PL-001) hasta que se
sustituya o se retire. Las notas de llenado van en llaves `_instrucciones`, que el esquema
ignora. Ningún dato jurídico (ni artículos, ni tesis, ni URLs, ni fechas de consulta); la fecha
del documento la da el operador. Con `--salida` aplica la política de rutas del paquete
(`motivo_ruta_paquete`, D7), crea las carpetas que falten y escribe con creación exclusiva
(nunca sobrescribe); sin `--salida` imprime el JSON y la guía va a stderr. Sale 0 o 2.

`lint` informa además, en una línea de la consola (no en `--json` ni en `--md`), cuántos campos
del ledger conservan un marcador pendiente (`[ASIGNAR]`, `[COMPLETAR]`, `[VERIFICAR…`, `[NO
VERIFICADA`) y dónde (`afirmaciones[ID].campo`), sin contar las notas `_*`. Un marcador nunca
cuenta como dato, pero las reglas solo lo señalan en ciertos campos (un marcador en el texto
de una afirmación no lo señala ninguna): la línea los hace visibles todos. No cambia
hallazgos ni códigos de salida.

El flujo guiado vive en la skill `menu-itosturre` (`references/menu-16-auditar-plan.md`):
carpeta del asunto, evidencia oficial, ledger, `cotejar` → `fidelidad` → `lint`, lectura de cada
resultado, decisiones humanas y aprobación, con los límites declarados (DOF y Corte IDH sin
cotejo, fidelidad determinista y parcial, el kit nunca aprueba). La Regla absoluta 10 de
`CLAUDE.md`/`AGENTS.md` fija que APROBADO solo lo firma una persona identificada y que, dentro
del ledger, el VVCA, el RAG y la memoria localizan sin acreditar; la Regla 3 del protocolo
anti-alucinación sigue rigiendo la verificación de citas en escritos.

## Núcleo VVCA: costuras y pruebas sin corpus (R4a)

`OpenNotebook.py` ya no importa PyMuPDF, ChromaDB, LangChain ni sentence-transformers
al tope. `_cargar_dependencias()` las importa juntas, una sola vez y en el orden del
antiguo import, la primera vez que se usan (`get_embedder`, `get_collection`,
`extract_text_from_pdf`, `ingest`). Así `import OpenNotebook` funciona con la biblioteca
estándar y el CI (Python 3.11 sin paquetes) ejerce la extracción, la resolución de ley y
el veredicto.

- **Dependencia faltante al usarla:** `DependenciaFaltante` (subclase de
  `ModuleNotFoundError`) dice qué paquete falta y cómo instalarlo; la CLI imprime
  `❌ OpenNotebook necesita el paquete …` y sale con código 1, el mismo que producía el
  `ImportError` al importar. Diferencias deliberadas: falla al usar la dependencia y no
  al importar (`--help`, `correct`, `calibrate` y `scripts/check_corpus.py` ya no exigen
  los paquetes; `audit --file` inexistente informa primero el archivo), sin traceback; y
  `ingest` carga las cuatro antes de abrir la colección, de modo que `--clear` nunca
  borra y luego aborta. `python-dotenv` se carga ahora antes que esos paquetes: una
  variable de `.env` que lean al importarse (p. ej. de `huggingface_hub`) empieza a surtir
  efecto; el `.env` actual no define ninguna.
- **Costuras de `audit()`** (solo por nombre; la CLI no las usa):
  `audit(text, verbose=False, allow_incomplete_corpus=False, *, collection=None, encode=None)`.
  `collection` sustituye la colección de ChromaDB (`count`, `get`, `query`) y `encode`
  el codificador de consultas (`encode_query`, modelo e5 con prefijo `"query: "`). Con una
  colección inyectada no se carga el modelo, no se abre ChromaDB y no se comprueba
  `CHROMA_PATH`, que solo sirve para abrir la colección persistente; `count() == 0` se
  comprueba igual. Con ambos en `None` el camino es el de siempre (modelo → `CHROMA_PATH`
  → colección), comprobado con la puerta antes/después sobre el corpus real.
- **Dobles de prueba** (`tests/vvca_falsos.py`): `FakeCollection` emula solo `count`,
  `get` y `query` con filtros `$and`/`$eq`/`$in`, `include` y distancia coseno;
  `CodificadorFalso` asigna un eje a cada consulta registrada, de modo que la prueba fija
  el texto exacto de la consulta y la distancia de cada fragmento; `importar_opennotebook()`
  importa el módulo sin dejar el `.env` ni el logging en el proceso de pruebas. Cualquier
  uso no emulado lanza `UsoNoEmulado` (deriva de `BaseException` para que los
  `except Exception` de `audit()` no lo conviertan en un camino de respaldo silencioso).
- **Caracterización** (`tests/test_vvca_nucleo.py`): fija el comportamiento ACTUAL de
  `extract_references`, la resolución de ley, `_article_candidates`, `build_vvca`,
  `build_vvca_tesis`, `check_corpus_coverage`, `audit` y `veredicto_global`, incluidos los
  defectos conocidos. `DEFECTOS_CONOCIDOS` registra cada uno (ID, PR que lo corrige,
  comportamiento correcto) y su prueba lleva el ID en el nombre: el PR que lo corrija
  cambia esa prueba a sabiendas; no hay `expectedFailure`. Cada prueba fija
  `JURISPRUDENCIA_PATH` en un temporal y `COSINE_THRESHOLD` en 0.25: nunca lee la
  jurisprudencia del operador ni depende de su `.env`.

Cómo probar el núcleo: `python -m unittest -v tests.test_vvca_nucleo` (con el venv o con
un Python 3.11 sin paquetes). Los dobles no reproducen distancias ni fragmentos reales: la
calidad de la recuperación sigue dependiendo de `scripts/run_regression.py`.

## Extracción de referencias y resolución de ley (R4b)

`extract_references` delega los artículos en `itosturre/audit/referencias.py` (biblioteca
estándar; `tests/test_vvca_referencias.py` prueba sus unidades). Corrige R4-D01…D06:

- **Designación** completa (`247 Ter`, `2o. Bis`, `4o.-A`, `29-A`, `32-B Quáter`); el grado
  (`259°`) sigue fuera. `ARTICLE_RE` se conserva con el mismo contrato de grupos.
- **Cabeza:** "artículo(s)", "art(s).", "numeral(es)" y "precepto(s)" seguidos de número;
  "numeral" tras otro número o un apartado ("artículo 9, numeral 2") califica al precepto y
  no abre referencia.
- **Enumeraciones y rangos:** una referencia por artículo (`arts. 14, 16 y 19`; `467 a 471`;
  `155–157`; `1o. a 4o.` con el ordinal en los intermedios); un número seguido de una unidad
  o un mes (`471, 3 días`, `10 de junio`) o un ordinal adjetivo (`2o. párrafo`) no es
  artículo. Las enumeraciones se leen por segmentos, cada uno con su ley ("14 de la CPEUM y
  42 del CFF", ", así como 167 del CNPP"); tras `;` el segmento sigue solo si trae su propio
  enlace derecho ("14 de la CPEUM; 42 del CFF"). `raw` va de la cabeza del grupo al
  artículo; `group_raw`, de la cabeza al último artículo del grupo.
- **Cobertura incompleta** (`coverage_gap`): un rango de más de `MAX_RANGO` (20) artículos,
  con o sin ordinales (`1º-25º`, `1o.-25o.`, `1°-25°`), conserva sus extremos y añade una
  referencia "N a M" con el motivo; un número ligado a una ley que no se extrajo con certeza
  (sin cabeza reconocible, también tras `;`) también. `audit()`
  las reporta `🟡 COBERTURA INCOMPLETA` (traza `not_verifiable`, método
  `cobertura_extraccion`), de modo que el veredicto no puede ser 🟢.
- **Ley por vínculo sintáctico** (catálogo de patrones por palabra completa desde
  `LAW_SOURCE_MAP` y `LAW_ALIASES`; una clave contenida en otra mayor no cuenta aparte; una
  mención seguida de "del Estado de…", "para el Estado de…" o "de la Ciudad de…" es otro
  ordenamiento). Enlace derecho con gramática explícita: calificadores del precepto →
  "ambos"/"todos" → "de"/"del" → determinantes → ley; varias leyes unidas por "y de/del" (o,
  ante "respectivamente", por "y el/la" sin repetir la preposición) solo se reparten con
  "respectivamente" y el mismo número que artículos; "respectivamente" con una sola ley o con
  un número distinto deja el grupo no identificado. Enlace izquierdo pegado
  a la cabeza o posesivo ("en su artículo") con un único ordenamiento en la oración; si
  izquierda y derecha difieren, ley no identificada (vínculos en conflicto). Coordinación
  pura comparte el enlace (hacia adelante o hacia atrás); "así como"/"en relación con" solo
  con distributivo. Sin vínculo: contexto previo en oraciones anteriores (≤ 600 caracteres,
  `law_inferred=True`); desde otro párrafo y sin encabezado inequívoco,
  `law_requires_confirmation=True`. Un ordenamiento concreto fuera del catálogo (ligado o el
  más cercano antes) deja la ley no identificada, y cuenta como candidato del genérico ("de
  la ley"): con más de un candidato, ambiguo. "Carta Magna" es un genérico de tipo
  constitución (criterio del responsable, 1-oct-2026: sin denominación ni antecedente
  inequívoco, 🟡; nunca CPEUM automática). Las oraciones se cortan en párrafo,
  elemento de lista o fila de tabla Markdown, `;`, `?`, `!`, `|` y punto final que no cierra
  una abreviatura. Campos añadidos por referencia: `law_method` (`adyacente_derecha`,
  `adyacente_izquierda`, `posesivo`, `antecedente`, `contexto_previo`, `encabezado`,
  `contexto_previo_otro_parrafo`), `law_unidentified_reason`, `group_raw`,
  `law_requires_confirmation` y `coverage_gap` (y `law_method` en `retrieved_sources`).
- **`audit()`:** sin `source_file`, 🟡 NO VERIFICABLE — LEY NO IDENTIFICADA con el motivo,
  sin consultar el corpus (traza `not_verifiable`, método `resolucion_ley`). Un precepto con
  sufijo sin su encabezado exacto, o un número base del que el índice solo ofrece variantes
  con sufijo (en cualquier caja: `4o.-a`), es 🟡 NO VERIFICABLE (traza `not_verifiable`, sin
  entrada en `retrieved_sources`): el chunker etiqueta `4o.-A` como `4o` y `247 Bis` como
  `247`. Una re-ingesta con la etiqueta completa eliminaría esa ambigüedad; R4b no
  re-ingesta. Con `law_requires_confirmation`, `build_vvca` limita el score a 60–84 (🟡) y
  la traza queda `partial` con la alerta "LEY POR CONFIRMAR" (único ajuste de semáforo de
  R4b; el resto del veredicto es R4c).
- **Consumidores:** `extract_article_numbers` y `exact_article_chunks` (comando `query`)
  y `capturar_rag._contains_article_header` (pop-ups) comparan la designación con su
  sufijo; `vvca_full.py` deduplica por `(fuente, artículo)` y ya distingue `247` de `247 Ter`.
  `retrieved_sources` lleva `law_requires_confirmation`; el ítem del pop-up, `ley_por_confirmar`
  y `motivo_ley` (advertencia visible en la página); `vvca_full.json`, `cobertura_pendiente`
  (y un warning del paso `cobertura`), que `capturar_rag.py --cobertura-pendiente N` añade al
  resumen del envío opcional, sin captura para lo no auditado.

## Veredicto honesto (R4c)

Corrige R4-D08, D09, D11 y D12 sin tocar umbrales (85/60) ni la fórmula de `vvca_score`;
R4-D07/D13/D14 se corrigieron en R4d y R4-D10 en D10 (secciones siguientes).

- **Precepto derogado (D08):** `itosturre/audit/evidence.py::precepto_derogado(texto,
  artículo)` (pura) reconoce "(Se deroga)", "Se deroga." o "(Derogado)" solo como lo primero
  que sigue al encabezado exacto del precepto citado (el mismo que acredita
  `has_exact_article_heading`). `audit()` la aplica únicamente a evidencia de la ley citada
  con encabezado exacto; `build_vvca(..., derogado=True)` limita el puntaje a 60–84, la traza
  queda `partial` y la alerta "🟡 PRECEPTO DEROGADO" sustituye a COTEJAR / ALERTA ALTA. 🟡 es
  el criterio por defecto (documentado en `docs/PROTOCOLO_VVCA.md`).
- **Fuente esperada (D09):** el respaldo sin filtro ya no hace `expected_source = None`;
  `_preferir_fuente` reduce los resultados a la ley citada si alguno lo es, y `source_match`
  compara de verdad. Evidencia de otro ordenamiento: −15 de `vvca_score` (ahora alcanzable) y
  límite 60–84 en `build_vvca`, traza `not_verifiable`, alerta "🟡 EVIDENCIA DE OTRO
  ORDENAMIENTO", `metadata_hit` solo con fuente coincidente y `filtro_fuente_fallido` en la
  explicabilidad. La rama "LEY NO IDENTIFICADA — coincidencia por número" quedó inalcanzable
  y se retiró.
- **Veredicto y resumen (D11, D12):** `veredicto_global(..., articulos_total=None)` (nuevo
  argumento opcional): sin artículos la regla "RAG < 70" no aplica; sin artículos ni tesis,
  🟡 "Sin citas detectadas"; el 🟢 enuncia solo lo verificado. `policy.semaforo_dimension`
  da ⚪ (`SEMAFORO_SIN_CITAS`) a una dimensión sin citas y 🟡/🔴 a una sin puntaje;
  `score_rag`/`score_sjf` valen `None` sin evidencia evaluable (antes 0.0). El `summary`
  dice "sin citas" y cuenta las no verificables y refutadas junto al subpuntaje.
- **Ronda 2 (revisión de Codex y del coordinador):**
  - `evidence.py`: `clasificar_derogacion` (fórmula inequívoca → `DEROGADO`; fórmula que
    empieza como derogación pero no lo es → `DEROGACION_AMBIGUA`), sobre la primera línea con
    contenido tras el encabezado, saltando el ruido de página; `reconstruir_cuerpo` (cuerpo
    hasta el encabezado de otro artículo, con la continuación del mismo precepto: misma
    fuente y etiqueta, `chunk_index` consecutivo); `cuerpo_suficiente`; `cotejar_unidad`
    (fracción por romano al inicio de línea e inciso por "a)", solo si la marca es única;
    párrafo, apartado, base, "in fine" → no cotejada) y `cotejar_precepto`, que `audit()`
    aplica a la evidencia de la ley citada con encabezado exacto.
  - `referencias.py`: `unidad_citada` por referencia (`unidades_citadas`: fracción,
    fracciones, párrafo, inciso, apartado, "in fine"…, entre el artículo y su ley, también
    tras un ordinal con punto: "artículo 1o., párrafo tercero"; `unidades_previas`: la cadena
    que precede a la cabeza y termina pegada a ella con "del"/"de la"/"de los": "párrafo
    tercero del artículo 1o.", "inciso a) de la fracción III del artículo 107") y la clave
    de fracción ya no vive dentro de otra palabra ("frente a") y admite "fracc.".
  - `build_vvca(..., *, unidad_derogada, derogacion_ambigua, unidad_no_cotejada,
    evidencia_incompleta)`: derogación de la unidad o ambigua → 60–84 (traza `partial`);
    unidad no cotejada o evidencia incompleta → tope 84 sin piso (la rama de R4-D10 la resolvió
    D10: piso 60 con distancia alta sin metadata).
  - `veredicto_global(..., tesis_parciales=0)`: tesis `partial` → 🟡; `tesis_ok` = solo
    verificadas. `RETENER_VERDE_SOLO_TESIS` (transitorio) retiene el 🟢 de "solo tesis"; R4d
    lo mantiene hasta validar el cotejo con un corpus de tesis mayor.
    `OpenNotebook.formato_telegram` (función aparte) muestra el alcance de cada dimensión con
    citas. `capturar_rag.semaforo(None)` → ⚪; `evaluate_gold_set` admite
    `null` en `score_rag`/`score_sjf` solo con `articulos_total: 0` / `tesis_total: 0`.
- **Alcance explícito:** `policy.ALCANCE_NORMATIVA` / `ALCANCE_JURISPRUDENCIA` en cada
  referencia (`alcance_verificacion`) y en `vvca_summary` (`alcance_verificacion`,
  `alcance_verificacion_tesis`); el `disclaimer` 🟢 lo dice al abogado.
- **Contrato JSON:** solo campos añadidos (`precepto_derogado`, `alcance_verificacion`,
  `rag_sin_citas`, `sjf_sin_citas`, `alcance_verificacion_tesis`, `tesis_parciales`; por
  referencia, `unidad_citada` (también en `extract_references`), `unidad_cotejada`,
  `unidad_derogada`, `unidad_no_cotejada`, `derogacion_ambigua`, `evidencia_incompleta`; en la
  explicabilidad, `precepto_derogado`, `unidad_derogada`, `derogacion_ambigua`,
  `unidad_no_cotejada`, `evidencia_incompleta`, `fragmentos_continuacion` y
  `filtro_fuente_fallido` solo cuando aplican). Cambio de significado pedido en la ronda 2:
  `tesis_ok` cuenta solo las tesis verificadas. Cambio de tipo
  pedido por D12: `score_rag`/`score_sjf` pueden ser `null` y `semaforo_*` puede ser ⚪.
  Consumidores revisados: `vvca_full.py` (ítem del pop-up con `precepto_derogado`; conteos
  `precepto_derogado` y `fuente_no_coincide` en el paso), `capturar_rag.py` (aviso "PRECEPTO
  DEROGADO" junto al de "LEY POR CONFIRMAR"; pop-up "FUENTE NO COINCIDE" con el semáforo de la
  cita), la salida `--format telegram` (muestra "sin citas" y el alcance),
  `itosturre/memoria/puente.py` (guarda los puntajes tal cual; admite `null`),
  `scripts/run_regression.py` y `scripts/evaluate_gold_set.py` (sin cambios) y la skill
  `menu-itosturre` (MENÚ 1: `null` = sin citas).

## Jurisprudencia determinista (R4d)

Corrige R4-D07, D13 y D14 sin tocar umbrales (85/60 y el 40 % del traslape) ni la
clasificación de fuerza vinculante (`[PR]`/`[SCJN-I]` siguen manuales, Regla 6). R4-D10 se
resolvió después, en D10.

- **Registros (D07):** `OpenNotebook.REGISTRO_TESIS_RE` sin distinguir mayúsculas ("Registro
  digital", con o sin dos puntos; "registro IUS"; "Registro", "Reg.", "registro número" o
  "IUS" solo con contexto de tesis en el párrafo, `_es_registro_de_tesis`); número de 6 o 7
  dígitos, nunca de 8 ni "N/AAAA"; en plural o enumeración (",", "y", "o", "y/o", "/"), una
  referencia por número (`registro_en_enumeracion`, sin rubro asociado); un número con un
  conector no reconocido queda como referencia `coverage_gap` (🟡 COBERTURA INCOMPLETA,
  método `cobertura_extraccion`).
  `ctx_invocado` (≤ `VENTANA_RUBRO` = 1 500 caracteres) no cruza el registro anterior (antes,
  400 caracteres que podían contener el rubro de otra tesis); `ctx_recortado` si la ventana
  cortó; `ctx_posterior` con el marcador pegado a la derecha ("registro digital N, de rubro:
  «…»"), que prevalece y deja de contar como contexto de la tesis siguiente.
- **Rubro invocado:** `itosturre/audit/jurisprudence.py` (pura, stdlib):
  `extraer_rubro_invocado` (tras "rubro"/"título y subtítulo"/"epígrafe"/"lleva por
  título"/"intitulada", el primer texto entre comillas o negritas o la primera corrida de
  mayúsculas; sin marcador, el texto entre comillas en mayúsculas o la corrida de mayúsculas
  más cercana al registro, sin la clave, la época, encabezados ni órganos) y
  `extraer_rubro_posterior`. Comillas en minúsculas sin marcador no son rubro. Ronda 2:
  `texto_omitido` (lo que media entre el marcador y el rubro si no está en
  `FORMULAS_INTRODUCTORIAS`) impide "coincide"; `asociacion_incierta` (otra mención de tesis
  entre el rubro y el registro; varios rubros) da `rubro_no_asociado` (🟡).
- **Cotejo (D13, D14):** `cotejar_rubro` → `rubro_no_asociado` / `parcial` / `coincide` /
  `discrepante` / `invertido` / `no_literal` / `sin_rubro_invocado` / `sin_rubro_fuente`
  (`RUBRO_*`; la marca de supresión se evalúa antes de la igualdad), con `normalizar_rubro`
  (NFKD sin acentos, casefold, sin puntuación no numérica: "1.4.14" ≠ "1/4/14", "69-b" ≠ "69
  b"), `traslape_rubro` (la fórmula de
  siempre con palabras cortas, salvo `PALABRAS_VACIAS`) y `diferencias_polaridad`
  (`NEGACIONES`, `ANTONIMOS_NEGATIVOS`, `PARES_SIMETRICOS`: listas cerradas).
  `build_vvca_tesis`: `coincide` → 95/72; `discrepante`/`invertido` → 0 (`rubro_mismatch`,
  🔴); el resto → `min(base, 84)` (🟡, traza `partial`). Un error al construir el semáforo de
  una tesis ya no la hace desaparecer: queda 🟡 NO VERIFICABLE.
- **Vigencia:** `normalizar_vigencia` → `{"estado", "registrado", "conflicto", "valores"}`,
  leyendo `estado_vigencia` y `vigencia`: una pérdida en cualquier campo prevalece; campos con
  dato distintos sin pérdida → `en_conflicto` (🟡, alerta); sin dato `no_consultada`, valor
  desconocido `no_reconocida`, nunca "vigente" sin fuente, como aviso ℹ️ en `avisos` (no en
  `alerts`) sin cambiar el semáforo. `scripts/promover_tesis.py` ya no escribe "vigente" por
  defecto y solo anuncia como vigencia perdida superada/interrumpida/sustituida.
- **Veredicto:** `scoring_vvca.RETENER_VERDE_SOLO_TESIS = True` (se mantiene por adjudicación
  del 2-oct-2026 hasta validar el cotejo con un corpus de tesis mayor).
- **Telegram:** `formato_telegram` muestra todas las alertas completas que quepan en
  `LIMITE_TELEGRAM` ("… y N alerta(s) más" remite al JSON) y agrupa los avisos por tipo.
- **Contrato JSON:** campos añadidos (`avisos` y `avisos_count` en el resultado;
  `vvca.cotejo_rubro`; en la explicabilidad, `cotejo_rubro`, `motivo_cotejo`,
  `rubro_invocado_metodo`, `rubro_truncado`, `polaridad`, `texto_omitido`,
  `asociacion_incierta`, `vigencia_registrada`, `vigencia_campos`, `vigencia_en_conflicto`;
  `vvca_summary.tesis_por_cotejo_rubro` y `tesis_por_vigencia`; en la referencia extraída,
  opcionales, `ctx_recortado`, `registro_en_enumeracion`, `ctx_posterior` y `coverage_gap`).
  Cambios de valor: `estado_vigencia` puede ser `no_consultada`, `no_reconocida` o
  `en_conflicto`; `explicabilidad.rubro_invocado` es el rubro extraído (antes 160 caracteres
  del contexto) y `rubro_real` va completo; `ALCANCE_JURISPRUDENCIA` dice "coincidencia literal
  (normalizada)" y `alcance_verificacion_tesis` cuenta las tesis sin cotejo del rubro
  (`ALCANCE_JURISPRUDENCIA_SIN_RUBRO` por tesis); `alerts` lleva las alertas del cotejo y
  `alerts_count` conserva su significado (los avisos van aparte). Consumidores revisados:
  `vvca_full.py` y `capturar_rag.py` (no leen campos de tesis; las referencias de cobertura
  de tesis entran en `cobertura_pendiente`), `run_regression.py` y `evaluate_gold_set.py`
  (sin cambios; `estado_vigencia` sigue presente), `formato_telegram`, skill `menu-itosturre`
  (MENÚ 1, actualizada) e `itosturre/memoria/puente.py` (corregido en la ronda 2: solo bloquea
  por vigencia superada/interrumpida/sustituida y registra el motivo y la polaridad del
  cotejo).

## Artículo no localizado: prueba positiva de inexistencia (D10)

Corrige R4-D10 con el criterio que decidió el responsable jurídico (2-oct-2026, opción C) sin
tocar umbrales (85/60), la fórmula de `vvca_score` ni las demás rutas. Toca la Regla 4 de
`CLAUDE.md`/`AGENTS.md`. Ronda 2 (rechazo de Codex por falsos rojos): la prueba se abstiene
ante cualquier ambigüedad.

- **`itosturre/audit/inexistencia.py`** (pura, stdlib): `preparar_ley(fragmentos,
  denominaciones)` → `LeyPreparada` (orden por `chunk_index`, texto sin acentos con los
  guiones de fin de línea unidos, frontera TRANSITORIOS —mismo criterio que
  `itosturre.evidencia.leyesbiblio.es_frontera_transitorios`, sin importar esa capa—,
  cuerpo, encabezados, identidad documental, versión indexada y densidad de páginas), una vez
  por ley; `evaluar_inexistencia(ley, artículo)` → `{"acreditada", "prueba", "motivo"}` (y
  `posterior_al_ultimo` entre el último + 1 y el margen); `describir_prueba` /
  `describir_posterior` (frases para el abogado). Encabezados: el exacto de
  `evidence._ENCABEZADO_SIGUIENTE` (grupo `designacion` añadido, sin cambiar qué reconoce;
  una letra suelta tras un espacio, "20.- A.", no se ordena), el de ordinal en palabra y la
  **línea candidata** (`_LINEA_CANDIDATA`: "Artículo/ARTÍCULO/Art" + número sin cierre, o un
  número con sufijo latino o con su cierre seguido de texto). Dos pruebas:
  1. *Vecinos en el mismo fragmento*: anterior y siguiente según la numeración, seguidos,
     únicos en el cuerpo, sin línea candidata ni línea que empiece con "art…"+número o con un
     número entre ellos. Sin continuidad entre fragmentos (ni deduplicación por
     solapamiento).
  2. *Número muy superior al último*: `chunk_index` contiguos desde el 0 hasta la frontera,
     último encabezado = el de mayor número, ninguna candidata del cuerpo ni línea con forma
     de artículo tras la frontera con número mayor, densidad sin señal de pérdida (por tramo
     de fragmentos con la misma página de inicio: páginas hasta el siguiente ≤ 1 + caracteres
     / 800, descontando 200 de solapamiento por subfragmento) y N ≥ último + max(10, ⌈5 %⌉).
  Comunes: identidad documental (título del encabezado del fragmento 0 o decreto que la
  expide con una denominación completa del catálogo), encabezado del citado en ninguna parte
  de la fuente (cualquier ordinal; "(Se deroga)" acredita existencia), sin mención del citado
  en todo el texto (tras "artículo(s)", en enumeraciones y rangos, o "N Bis" suelto).
- **`audit()`:** cuando el precepto no se localiza en la evidencia de la ley citada (sin
  encabezado exacto, fuente coincidente, ley no "por confirmar"), `_evaluar_inexistencia`
  exige un `law_method` explícito (`METODOS_LEY_EXPLICITA`: `adyacente_derecha`,
  `adyacente_izquierda`, `posesivo`; nunca `law_inferred`) y lee y prepara la ley una vez por
  auditoría (`leyes_preparadas`, con los textos originales para la evidencia), con las
  denominaciones de `LAW_SOURCE_MAP` para esa fuente. Rutas: sufijo sin encabezado (R4b),
  evidencia insuficiente, distancia alta y consulta sin vecinos. Con prueba:
  `_registrar_inexistencia` → traza `refuted` (método `corpus_estructura`, puntaje 0), alerta
  "🔴 ARTÍCULO INEXISTENTE ACREDITADO" con la prueba, la página y la versión indexada,
  entrada en `retrieved_sources` con la evidencia original de la prueba y el campo añadido
  `inexistencia_acreditada`. Sin prueba, cada ruta conserva su 🟡; las dos que eran 🔴 pasan a
  "🟡 NO LOCALIZADO" (traza `not_verifiable`; con evidencia, puntaje 60–84 e
  `inexistencia_no_acreditada`) y el encabezado ubicado con distancia alta sin metadata, a
  "🟡 COTEJAR" (`partial`). Con `posterior_al_ultimo`, cualquier ruta usa la alerta "🟡
  POSTERIOR AL ÚLTIMO ARTÍCULO" sin cambiar estado ni puntaje.
- **`referencias.py` (`_resolver_previo`):** si la oración de la mención más cercana del
  contexto previo nombra más de un ordenamiento, la ley queda no identificada ("el contexto
  previo es ambiguo") en vez de tomar la última mención. Ninguna prueba de R4b cambió.
- **`build_vvca(..., no_localizado=False)`:** distancia alta sin metadata → 60–84 (antes,
  con distancia > 0.40, el puntaje caía bajo 60 sin prueba); "Coincidencia débil" ya no dice
  "posible alucinación".
- **Contrato JSON:** campos añadidos (`inexistencia_acreditada` en la entrada 🔴; en la
  explicabilidad o la traza, `inexistencia_acreditada`, `no_localizado`,
  `inexistencia_no_acreditada` y `posterior_al_ultimo` cuando aplican); método de traza nuevo
  `corpus_estructura`. Consumidores revisados: `vvca_full.py` y `capturar_rag.py` (la entrada
  🔴 entra al pop-up como "NÚMERO DE ARTÍCULO NO CONFIRMADO", sin página de PDF como prueba de
  ubicación; sin cambios), `scoring_vvca.veredicto_global` (una refutada bloquea, sin
  cambios), `formato_telegram`, `run_regression.py` y `evaluate_gold_set.py` (sin cambios) y
  la skill `menu-itosturre` (MENÚ 1, actualizada).

## Corte y etiqueta de la ingesta; re-ingesta por fuente (4-oct-2026)

Orden expresa del responsable jurídico (4-oct-2026). El corte de "ley" exigía "rt" en
minúscula (`(?=\n[Aa]rt[íi]?(?:culo)?s?\.?\s+\d+)`): los encabezados en MAYÚSCULAS no cortaban
ni etiquetaban (CFPC, LFPC, LFPCA, CDN y Constitución de Jalisco quedaban con 0–1.5 % de sus
encabezados al inicio de un fragmento etiquetado) y las remisiones en minúscula al inicio de
línea ("artículo 41.") cortaban y etiquetaban fragmentos con un número ajeno (459 fragmentos
en 42 fuentes, medido con `--simular` y la gramática de la ronda 2; los 2 254 fragmentos etiquetados de la RMF, que se
ordena por reglas y no por artículos, llevaban etiquetas de remisiones).

- **Definición única** (`itosturre/audit/evidence.py`): `_es_autentico` ("A" mayúscula en el
  prefijo y cierre no seguido de "," ni ";") la usan `ocurrencias_encabezado` (auditoría) y
  `encabezados_autenticos` (ingesta). Este último reconoce el encabezado de CUALQUIER artículo
  con el prefijo y el cierre de `_encabezado_exacto` y la designación genérica
  `referencias.patron_designacion_cualquiera` (gramática de `patron_articulo`); con
  `fin_de_linea=True` admite además la designación sola al final de su línea (tratados:
  "Artículo 51", "ARTÍCULO 1"), salvo que la línea siguiente continúe una oración
  (`_fin_de_linea_autentico`). **Decisión del responsable (4-oct-2026, opción A):** la
  auditoría y la ingesta la aceptan ÚNICAMENTE en los tratados internacionales registrados en
  el catálogo (`OpenNotebook.TRATADOS_INTERNACIONALES`: CADH, CDN, PIDCP), con el parámetro
  `fin_de_linea` según la fuente (auditoría: `select_article_evidence`,
  `ocurrencias_encabezado`, `ubicar_en_cuerpo`, `reconstruir_cuerpo`/`cotejar_precepto` y
  `preparar_ley` de D10; ingesta, desde la ronda 2: `fragmentar`, `medir` y
  `verificar_identidad`, que `fragmentos_de_pdf` y `reingestar_fuentes` llaman con el nombre del
  PDF). En las leyes nacionales el cierre es obligatorio, así que los arts. 1–10 de la
  "Declaratoria" que el Código Civil de Jalisco trae tras sus TRANSITORIOS no son encabezados
  ni cortan. Ver `docs/PROTOCOLO_VVCA.md` §4 ("Tratados internacionales" y "Párrafo
  numerado"). Coherencia comprobada en las 49 fuentes (cifras de la ronda 2, abajo).
- **`itosturre/audit/fragmentacion.py`** (pura, stdlib): `detectar_tipo` (cuenta los
  encabezados auténticos, también en MAYÚSCULAS), `cortes`/`etiqueta` (contratos y
  resoluciones sin cambios), `fragmentar(páginas, max_caracteres, subdividir)` y `medir`
  (fragmentos, etiquetados, encabezados del cuerpo y del documento, cobertura y etiquetas sin
  encabezado al inicio). Etiqueta: la regla anterior `\d+[\w\-]*` aplicada a la línea del
  encabezado sin acentos ('1o', '496', '1º', '1' para "1°", '4o' para "4o.-A", '29-A',
  '58-1', '247' para "247 Bis"); solo se quita un guion final ('10-' → '10'). Página: la de la
  línea del encabezado (también si está partido entre líneas). Desde la ronda 2 también cortan
  "ARTICULO 65 Bis 1." o "63 QUINTUS.-" (etiqueta '65', '63') y la línea TRANSITORIOS.
- **`OpenNotebook.py`:** `ingest` usa `fragmentar`; sin flags, una fuente ya indexada con otra
  fragmentación se omite (`pendientes_sin_mezcla`; antes se completaba por ID y mezclaba).
  `ingest --fuente ARCHIVO.pdf [--fuente …] [--simular] [--json]` → `reingestar_fuentes`:
  valida (al menos una fuente; nombre exacto de un PDF de la carpeta, no excluido, sin
  repetir), fragmenta y codifica ANTES de escribir (`encode_passages`, el mismo cálculo que la
  función de la colección), respalda en memoria los fragmentos de la fuente, `delete(where=
  {"source": …})`, comprueba que no queda ninguno ni hay IDs ocupados, agrega y verifica IDs,
  textos y metadatos; ante cualquier fallo restaura el respaldo (`ReingestaFallida`, salida 1).
  `--simular` abre la colección sin crearla y no escribe. `--fuente` no se combina con
  `--clear`/`--reingest` (que siguen borrando la colección entera). Costuras para pruebas:
  `collection`, `codificar`, `extraer`, `subdividir`.
- **Pruebas:** `tests/test_ingesta_fragmentacion.py` (sin dependencias; textos sintéticos) y
  `ColeccionEscribible` en `tests/vvca_falsos.py` (`add`/`delete` más estrictos que ChromaDB y
  fallo de escritura inyectable). Procedimiento operativo en `docs/ENTORNO.md`.

**Ronda 2 (correcciones del coordinador y de la revisión externa, 4-oct-2026).** Una sola
gramática de designaciones (`referencias.py`) para la extracción, el encabezado exacto, las
variantes con sufijo, la prueba de inexistencia y la ingesta:

- **Designaciones nuevas:** subnúmero pegado "N-M" con M < N ("58-1" de la LFPCA; con M ≥ N es
  un rango: "14-16" → 14, 15, 16); número tras el sufijo latino ("65 Bis 1", "211 bis 7",
  "343 Ter 2"); sufijos latinos más allá de "decies" (`LATINOS`, con grafías: "Undecies" …
  "Vicies", "Sexies Decies"/"Sexdecies") y "quintus" (mismo lugar que "quinquies" en el orden,
  pero se coteja tal cual). `PartesArticulo` añade `subnumero` y `numero_latino`;
  `clave_orden` (D10) los ordena ("58" < "58-1" < "59"; "65 Bis" < "65 Bis 1" < "65 Ter") y el
  subnúmero es una familia de sufijo más. `canon_caja` da la misma caja a etiquetas y
  candidatos ("29-a" → "29-A"). Antes "58-1" se extraía como 58 y 1, y "65 Bis 1" como "65 Bis":
  en el corpus real eso daba 🟢 contra OTRO artículo (38 casos medidos, todos corregidos).
- **Falla cerrada:** si el texto continúa la designación extraída sin capturarla entera ("65
  Bis 123", "5 bis 10 días", "247 Bis Ter", "247 Undevicies", "65 Bis 1-3"), la referencia es
  🟡 COBERTURA INCOMPLETA con la razón (nunca se coteja la designación truncada).
- **Encabezado partido entre líneas** ("ARTICULO\n508.-"; 4 en el corpus: CFPC, LFPPI y dos
  reglamentos de movilidad): en la definición única (`evidence._PREFIJO_ENCABEZADO`,
  `_ENCABEZADO_CUALQUIERA`, `_ENCABEZADO_SIGUIENTE`) y en la existencia de D10, solo con
  "Artículo" solo al final de su línea y la designación con su cierre en la siguiente. Cambia
  la auditoría también de fuentes no re-ingestadas (LFPPI 367 y RegMovilidad 9 pasan a 🟢).
- **TRANSITORIOS:** el cuerpo del precepto (`reconstruir_cuerpo`) se detiene en esa línea
  (`es_frontera_transitorios`, ahora en `evidence` y reexportada por `inexistencia`) y la
  ingesta corta en ella.
- **Seguridad de `--fuente`:** fase 1 sin escrituras para todas las fuentes
  (`paginas_incompletas`, `verificar_identidad`, colisiones de IDs; `ReingestaRechazada`); fase
  2 con respaldo DURABLE por fuente (`itosturre-respaldo-fuente/1`: ids, documentos, metadatos
  y vectores float32 en base64 con huella SHA-256, fuera del repositorio y del índice) y
  `ingest --restaurar` (`restaurar_respaldo`, tolerancia de vector 1e-6: ChromaDB vuelve a
  normalizar al guardar). La ingesta sin flags con fuentes omitidas sale con código 3
  (`SALIDA_MIGRACION_PENDIENTE`) y `bootstrap_corpus.sh` lo respeta.
- **Comprobado en las 49 fuentes:** las 18 611 líneas con cierre que corta la ingesta (4
  partidas) son exactamente las que la auditoría acepta como encabezado auténtico de alguna
  lectura de su designación. Fuera de esta gramática quedan `itosturre/plan/` (sus propias
  listas de sufijos latinos) y el pop-up de `capturar_rag.py`.
- **Pruebas:** `tests/test_vvca_designaciones.py` (gramática, encabezado partido,
  TRANSITORIOS, D10 y casos del coordinador de punta a punta) y las de seguridad en
  `tests/test_ingesta_fragmentacion.py`.

## Fuentes canónicas

1. `CLAUDE.md` contiene la política operativa compartida. `AGENTS.md` es su adaptación
   para Codex y solo puede diferir en el encabezado de plataforma.
2. `.claude/skills/` es la fuente vendorizada. `.agents/skills/` conserva el mismo árbol;
   únicamente tres `SKILL.md` aplican sustituciones de plataforma documentadas.
3. `scripts/check_agent_surfaces.py` verifica esas reglas y puede regenerar las superficies
   derivadas con `--write`.
4. `services/itosturre-skills/` es la fuente de las skills jurídicas propias del producto;
   no debe editarse como si fuera una carpeta ordinaria del repositorio padre.

## Contratos de prueba

| Nivel | Comando | Uso |
|---|---|---|
| Estático | `python -m compileall -q ...` | Cada push/PR |
| Superficies de agente | `python scripts/check_agent_surfaces.py` | Cada push/PR |
| Parser y resiliencia SJF offline | `python scripts/test_scraper_offline.py` | Cada push/PR |
| Gold Set VVCA | `python scripts/evaluate_gold_set.py` | Cada push/PR |
| Gold Set jurídico v2 | `python scripts/evaluate_gold_set.py --file tests/fixtures/vvca_gold_set_v2.json` | Curaduría del operador; no es gate hasta 30 casos aprobados |
| Orquestador fail-closed | `python -m unittest -v tests.test_vvca_full` | Cada push/PR |
| Núcleo VVCA (caracterización) | `python -m unittest -v tests.test_vvca_nucleo tests.test_vvca_referencias` | Cada push/PR (dentro de la suite); colección y codificador falsos, sin corpus ni modelo; fija el comportamiento actual y los defectos de `DEFECTOS_CONOCIDOS` (D01–D06 corregidos en R4b; D08, D09, D11 y D12 en R4c; D07, D13 y D14 en R4d; D10 en D10, con `tests.test_vvca_inexistencia`) |
| Gold Set de planes | `python scripts/evaluate_plan_gold_set.py` | Cada push/PR; falla si un caso no pasa o una regla PL-001…PL-014 queda sin caso |
| Gold Set de fidelidad | `python scripts/evaluate_fidelidad_gold_set.py [--paquete DIR]` | Cada push/PR; esquema `fidelidad-gold-set/2.0`: casos sintéticos rotulados contra texto de ley real copiado de los fixtures o del paquete del piloto PEN-01, y pares adversariales contra fuentes `sintetico_adversarial` rotuladas: falla si una categoría o un código de precisión alta no tiene recall 100 %, si un control fiel da señales, si una señal alta aparece donde no se espera (falso bloqueante) o si un texto no es literal (`sha256_texto`; subcadena exacta del fixture en CI; con `--paquete`, del artículo que reconstruye el paquete local). Los casos `LIM-*` (límites documentados) y los 22 candidatos del piloto (`pendiente_responsable`) se miden aparte y no son puerta |
| Cotejo de fidelidad | `python -m unittest -v tests.test_plan_fidelidad` | Cada push/PR (dentro de la suite); motor con páginas literales de los fixtures (cada oración frente a su página no da señales), política de precisión, pares adversariales de la revisión externa y del coordinador, fuente truncada, alineación ambigua, cotejo del ledger con paquetes temporales (pares CONFORME, referencias, NO_COTEJABLE, ley ambigua, caché compartida; ley sintética rotulada para las señales de precisión alta), PL-020 con decisiones ligadas a la huella de cada señal, reporte, CLI (salida ≠ 0 si nada fue cotejable) y Gold Set |
| Cotejo de identidad | `python -m unittest -v tests.test_plan_identidad` | Cada push/PR (dentro de la suite); paquetes armados en temporales desde los fixtures oficiales, con un extractor sintético inyectado para las leyes; cubre PL-015…PL-019, que el Gold Set no admite porque no tiene paquete, y las correcciones del piloto PEN-01 (clases `Piloto*`, CRLF de `agregar-tesis` y `evidencia articulo`). Las pruebas de enlaces simbólicos de archivo se omiten donde el sistema no permite crearlos (Windows sin privilegio) y corren en el CI Linux; la de PyMuPDF se omite sin `fitz` |
| Plantilla de ledger | `python -m unittest -v tests.test_plan_plantilla` | Cada push/PR (dentro de la suite); esquema válido, un ejemplo por tipo, ningún dato jurídico (ni cifras, ni URLs, ni menciones), lint que marca cada ejemplo (PL-001) y queda limpio sin ellos, marcadores pendientes, CLI (nunca sobrescribe, política de rutas D7, sin `--salida` imprime el JSON, entrada inválida → 2) |
| Gramática de designaciones (ronda 2) | `python -m unittest -v tests.test_vvca_designaciones` | Cada push/PR (dentro de la suite); "58-1" frente a "14-16", "65 Bis 1", latinos extendidos, falla cerrada, encabezado partido, cuerpo hasta TRANSITORIOS, orden de D10 y auditoría de punta a punta con la colección falsa |
| Tratados y párrafos numerados (4-oct-2026) | `python -m unittest -v tests.test_vvca_tratados` | Cada push/PR (dentro de la suite); registro `TRATADOS_INTERNACIONALES` (cada fuente en `LAW_SOURCE_MAP`; el nombre del archivo no decide), encabezado sin cierre solo con `fin_de_linea` y con la salvaguarda de la ingesta, misma definición que `encabezados_autenticos`, cuerpo tras la línea de título, ubicación sin frontera, D10 que se abstiene, extracción "8.1"/"numeral 1"/"párrafo 1"/"párrafos 1 y 2" con falla cerrada ("8. 1", "8.1.2") y auditoría de punta a punta con la colección falsa (🟢 con metadata, tope 84 sin ella, ley nacional sin cambios). Ronda 2: párrafo numerado solo en tratados, listas de incisos/fracciones/apartados completas (o cobertura incompleta), secuencia de encabezados, cuerpo hasta cualquier candidato, solapamiento comprobado, notas, título solo y el mismo registro en el cortador de la ingesta |
| Corte de la ingesta y re-ingesta por fuente | `python -m unittest -v tests.test_ingesta_fragmentacion` | Cada push/PR (dentro de la suite); encabezados que cortan y que no (MAYÚSCULAS, tratados, remisiones, citas, apartados), etiquetas compatibles con las anteriores y con `_article_candidates`, misma definición que la auditoría, `fragmentar`/`medir`, y `reingestar_fuentes` con `ColeccionEscribible`: se niega sin fuente, borra solo la pedida, IDs y metadatos coherentes, nunca mezcla, `--simular` sin escrituras, restauración ante fallo, CLI |
| Regresión VVCA | `python scripts/run_regression.py` | Gate local antes de merge; requiere corpus |
| Política de datos | `python scripts/check_sensitive_paths.py` | Cada push/PR |
| Watchers DOF/SAT/SJF (offline, red simulada) | `python -m unittest tests.test_vigilancia_contrato tests.test_vigilancia_rutina tests.test_vigilancia_watch` | Cada push/PR (dentro de la suite); fuente caída ≠ "sin novedades", sin brief ni borrador cuando no hay insumo (salidas 2 y 3) y reintento posible, SJF con búsqueda completa y fichas desde la búsqueda (el detalle es un extra tras un anti-bots que no se evade), solo las novedades sostienen un borrador, salidas fuera del paquete y `.gitignore` que no oculte módulos de `itosturre/`, fecha de la Ciudad de México, modelo único |

La regresión VVCA no se ejecuta en CI compartido porque requiere el corpus local y el modelo
de embeddings. Un resultado verde de CI no reemplaza ese gate local: desde R4a el CI ejerce
la lógica del núcleo con dobles, pero no la recuperación real.

## Decisiones vigentes

- El repositorio padre es Python; no existe un proyecto Node en la raíz.
- Las dependencias Node pertenecen exclusivamente al submódulo del scraper.
- `fetch_tesis_detalle.py` es solo una fachada deprecada; `vvca_audit.ts` es la
  implementación canónica para consultar registros SJF.
- Los dos submódulos oficiales son `itosturre-scraper` e `itosturre-skills`.
- La modularización de `OpenNotebook.py` comenzó por funciones puras bajo `itosturre/audit/`.
  Las siguientes extracciones serán incrementales, conservarán la CLI y pasarán la regresión.
  Desde R4a el módulo se importa sin dependencias pesadas y `audit()` es probable con
  dobles; las correcciones del núcleo (R4b–R4d) cambian las pruebas de caracterización a
  sabiendas. R4b movió la extracción y la resolución de ley a `itosturre/audit/referencias.py`;
  R4c, la detección de derogación (`evidence.py`) y el semáforo por dimensión y el alcance
  (`policy.py`); R4d, el cotejo del rubro y la vigencia de las tesis (`jurisprudence.py`).
- `vvca_full.py` falla cerrado ante errores de RAG, SJF o evidencia. La degradación solo se
  permite mediante flags explícitos y queda registrada como `status: partial`.
- Ninguna automatización debe enviar mensajes o publicar contenido sin aprobación humana.
- Los watchers de `agentes/` (`vigilancia_dof.py`, `vigilancia_jurisprudencial.py`) requieren
  que SU PROPIO proceso corra en un entorno con egress autorizado hacia dof.gob.mx, sat.gob.mx
  y sjf2.scjn.gob.mx — no asumen que el orquestador que los invoca lo tiene. Si una fuente no
  puede consultarse, el resultado queda en `SOURCE_UNAVAILABLE` (nunca en un "sin novedades"
  fabricado); si es la fuente primaria, no se escribe brief y la salida es 2, para que el
  reintento sea posible. `contenido_linkedin.py` no escribe borrador (salida 3) cuando no hay
  ningún hallazgo validado en briefs de los últimos 7 días. Las salidas van a `salidas/` (o
  `$ITOSTURRE_SALIDA`), nunca a `Itosturre/`: en macOS y Windows es el paquete `itosturre/`.
  Ver `docs/VIGILANCIA_LEGAL.md`.
