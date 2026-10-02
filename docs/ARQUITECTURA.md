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
| `agentes/` | Automatizaciones auxiliares de vigilancia y contenido | Código padre |
| `itosturre/audit/` | Políticas VVCA puras y trazabilidad, sin dependencias RAG. `referencias.py` (R4b): extracción de artículos (sufijos, enumeraciones, rangos) y resolución del ordenamiento por oración y palabra completa; `evidence.py`: encabezado exacto del precepto | Código padre |
| `itosturre/leads/` | Normalización, deduplicación, ICP y supresión de prospectos; sin recolección ni envíos | Código padre |
| `itosturre/memoria/` | Memoria contextual: eventos, índice FTS5, ranking y snapshots; sin dependencias externas | Código padre |
| `memoria_cli.py` | Interfaz de la memoria contextual | Código padre |
| `itosturre/plan/` · `plan_audit.py` | Auditor determinista de planes sobre ledger `plan-ledger/1.0`: vocabulario de estados, evidencia oficial, aprobación humana ligada al hash del contenido y cobertura de menciones (PL-001…PL-014); con un paquete de evidencia, cotejo de identidad (`identidad.py`, C9) y reglas PL-015…PL-017. CLI: `lint`, `hash`, `cotejar`, `evidencia agregar-tesis` y `evidencia agregar-ley`. Sin red ni LLM, separado del VVCA | Código padre |
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
| Paquetes de evidencia de un asunto | `auditorias/<asunto>/plan/…` o fuera del repositorio | Local, confidencial, nunca versionar (D7). `plan_audit.py evidencia agregar-*` rechaza escribir dentro del repositorio fuera de una zona que la política de datos prohíbe versionar |
| Prospectos B2B | `leads_data/` | Local; incluye consentimientos y exclusiones; nunca versionar |
| Casos sintéticos | `casos_de_prueba/` | Versionados; la regresión usa una lista cerrada |
| Fixtures de evidencia oficial | `tests/fixtures/evidencia/` | Versionados; texto oficial literal (páginas de LeyesBiblio, renders del SJF) con procedencia en `manifiesto.json`; bytes exactos (`.gitattributes`, sin conversión de fin de línea); cada archivo autorizado en `config/data-policy.json` |
| Dependencias | `venv/`, `node_modules/` | Local; regenerables |

## Flujo de evidencia de planes (C7 → C9)

```text
innerText del SJF / PDF de LeyesBiblio (obtenidos por el operador; sin red)
        |  plan_audit.py evidencia agregar-tesis | agregar-ley  (--fecha-consulta del operador)
        v
paquete de evidencia  registros/<huella>.json + objetos/<sha256>   (solo si pasa la integridad)
        |  publicación exclusiva (enlace duro / O_EXCL), sin enlaces simbólicos ni junctions
        |  imprime sha256_documento y un bloque de evidencia para pegar
        v
ledger plan-ledger/1.0  evidencias[]: url + sha256_documento + ubicacion + extracto
        |                (+ ultima_reforma_dof opcional para leyes)
        |                decisiones[].advertencias_fuente para las advertencias de la fuente
        v
plan_audit.py cotejar --ledger L --paquete DIR      → CONFORME / DISCREPANTE / SIN_EVIDENCIA por par
plan_audit.py lint --ledger L --paquete DIR         → PL-001…PL-014 + PL-015…PL-017
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

| Regla | Severidad | Cuándo |
|---|---|---|
| PL-015 | BLOQUEANTE | VERIFICADO que cita una evidencia DISCREPANTE |
| PL-016 | BLOQUEANTE | VERIFICADO sin evidencia CONFORME, o cuyas menciones no cubre ninguna evidencia CONFORME (sostiene a lo sumo NO VERIFICABLE) |
| PL-017 | BLOQUEANTE si VERIFICADO; ALTA si no | Evidencia CONFORME con advertencias de la fuente sin una decisión con `advertencias_fuente` (evidencia, `sha256_documento` o `huella_registro` vigentes, códigos y resolución) y responsable humano; para VERIFICADO, además APROBADA |

Las reglas del cotejo viven en `REGLAS_COTEJO`, no en `REGLAS`: sin `--paquete` el lint,
sus salidas y el Gold Set de planes son los de PR-1. Ninguna salida de `lint`
(`--json`/`--md`) puede quedar dentro del paquete.

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
R4-D10 queda pendiente de decisión del responsable y R4-D07/D13/D14 se corrigieron en R4d
(sección siguiente).

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
    unidad no cotejada o evidencia incompleta → tope 84 sin piso (la rama de R4-D10 no cambia).
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
clasificación de fuerza vinculante (`[PR]`/`[SCJN-I]` siguen manuales, Regla 6). R4-D10 sigue
pendiente de decisión del responsable.

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
| Núcleo VVCA (caracterización) | `python -m unittest -v tests.test_vvca_nucleo tests.test_vvca_referencias` | Cada push/PR (dentro de la suite); colección y codificador falsos, sin corpus ni modelo; fija el comportamiento actual y los defectos de `DEFECTOS_CONOCIDOS` (D01–D06 corregidos en R4b; D08, D09, D11 y D12 en R4c) |
| Gold Set de planes | `python scripts/evaluate_plan_gold_set.py` | Cada push/PR; falla si un caso no pasa o una regla PL-001…PL-014 queda sin caso |
| Cotejo de identidad | `python -m unittest -v tests.test_plan_identidad` | Cada push/PR (dentro de la suite); paquetes armados en temporales desde los fixtures oficiales, con un extractor sintético inyectado para las leyes; cubre PL-015…PL-017, que el Gold Set no admite porque no tiene paquete. Las pruebas de enlaces simbólicos de archivo se omiten donde el sistema no permite crearlos (Windows sin privilegio) y corren en el CI Linux; la de PyMuPDF se omite sin `fitz` |
| Regresión VVCA | `python scripts/run_regression.py` | Gate local antes de merge; requiere corpus |
| Política de datos | `python scripts/check_sensitive_paths.py` | Cada push/PR |

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
