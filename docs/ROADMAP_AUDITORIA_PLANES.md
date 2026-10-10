# Hoja de ruta: auditoría de planeación legal de alto nivel

**Estado:** v1.9 · 2-oct-2026 · base `main@0912868`
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
| PR-2 | `feat/evidencia-pura` | `itosturre/evidencia/` (C7): registro `evidencia/1.0` con validación estructural por lista de problemas y `comprobar_integridad` aparte (recalcula huellas y relee la fuente; sin ella un registro no sostiene VERIFICADO); hosts oficiales y `url_oficial` como fuente única (plan los reexporta); huellas SHA-256 y JSON canónico; parser del innerText del SJF anclado en "Registro digital:" con estructura validada (rubro, campos de una línea, publicación y obligatoriedad contadas en todo el texto); limpieza de LeyesBiblio con título plausible y consensuado; ubicación de artículos cuerpo/transitorios/indeterminada; notas de reforma con gramática completa e invariante de fechas; fixtures oficiales literales con manifiesto de procedencia | Integrado en `main` tras la revisión externa (ronda 2) |
| PR-3 | `feat/cotejo-identidad` | Cotejo de identidad (C9): paquete de evidencia direccionado por contenido (`itosturre/evidencia/paquete.py`, único módulo de la capa con E/S de archivos; publicación que falla si el destino existe —enlace duro u `O_EXCL`—, huella verificada al leer, rechazo de enlaces simbólicos y junctions con contención por ruta real, solo registros íntegros y sin ambigüedad); `itosturre/plan/identidad.py` coteja cada par (afirmación, evidencia) en el orden vínculo → registro → integridad (+ relación original–texto de las leyes por re-extracción con extractor inyectado) → documento y versión (+ registros/claves que menciona la afirmación) → ubicación (sin rangos; + artículo y ley que menciona la afirmación) → campos y extracto, con CONFORME / DISCREPANTE / SIN_EVIDENCIA (NO_COTEJADO para INEXISTENTE), cobertura de menciones por afirmación y `requiere_decision_humana` cuando la fuente trae advertencias; el cotejo lleva la huella del ledger y del paquete; reglas PL-015…PL-017 solo con paquete (`REGLAS_COTEJO`), PL-017 con decisiones `advertencias_fuente` ligadas a la fuente vigente; CLI `cotejar`, `lint --paquete` (ninguna salida dentro del paquete) y `evidencia agregar-tesis` / `agregar-ley` (origen del texto, páginas declaradas comprobadas, título frente a la URL); sección de cotejo en el reporte; campo opcional `ultima_reforma_dof` en las evidencias del ledger | Integrado en `main` tras la revisión externa (ronda 2) |
| R4a | `fix/vvca-nucleo-probable` | Núcleo VVCA probable en CI sin cambiar comportamiento: carga perezosa de PyMuPDF/ChromaDB/LangChain/sentence-transformers en `OpenNotebook.py` (`import OpenNotebook` con la biblioteca estándar; dependencia faltante → mensaje claro y código 1); costuras `audit(..., *, collection=None, encode=None)`; dobles `tests/vvca_falsos.py`; caracterización `tests/test_vvca_nucleo.py` con el registro `DEFECTOS_CONOCIDOS` (R4-D01…D14). Puerta antes/después sobre el corpus real: salidas idénticas salvo campos de reloj | Integrado en `main` |
| R4b | `fix/vvca-extraccion-ley` (propuesta) | Extracción de referencias y resolución de ley (R4-D01…D06) en `itosturre/audit/referencias.py`. Ronda 1: designación con sufijo (`247 Ter`, `2o. Bis`, `4o.-A`, `32-B Quáter`), una referencia por artículo en enumeraciones y rangos, ley por palabra completa, "constitución" sola no es la CPEUM, encabezado exacto sin sufijos no pedidos, ley no identificada → 🟡 NO VERIFICABLE con motivo, sufijo sin encabezado → 🟡. Ronda 2 (rechazo de Codex, 7 hallazgos + 2 del coordinador): la ley solo se asocia por **vínculo sintáctico** (derecha pegada al precepto; izquierda pegada o posesiva; vínculos en conflicto → no identificada; varias leyes solo con "respectivamente"); ordenamiento concreto fuera del catálogo o de otra entidad bloquea la inferencia; claves estatales con la entidad completa; sufijo en minúscula; enumeraciones por segmentos con leyes intercaladas; rangos > 20 y números no extraídos con certeza → 🟡 COBERTURA INCOMPLETA; contexto previo solo de oraciones anteriores y, desde otro párrafo sin encabezado inequívoco, ley por confirmar (🟡). Ronda 3 (segunda revisión de Codex, 6 hallazgos): "respectivamente" sin repetir la preposición y reparto que no cuadra → grupo no identificado; rangos largos con ordinales → extremos + cobertura incompleta; `;` no hace desaparecer un miembro de la enumeración; ordenamientos fuera del catálogo cuentan como antecedentes del genérico (dos o más → ambiguo); "numeral"/"precepto" como cabeza y "Carta Magna" como genérico; pop-up con advertencia "LEY POR CONFIRMAR" y aviso de cobertura pendiente sin captura falsa; criterio del responsable (1-oct-2026) fijado por prueba. Sin re-ingesta. Campos añadidos `law_method`, `law_unidentified_reason`, `group_raw`, `law_requires_confirmation`, `coverage_gap` (ronda 3: `law_requires_confirmation` en `retrieved_sources`, `ley_por_confirmar`/`motivo_ley` en el pop-up, `cobertura_pendiente` en `vvca_full.json`). Puerta antes/después sobre el corpus real con cada diferencia atribuida; `run_regression` 🟢 | Integrado en `main` |
| R4c | `fix/vvca-veredicto-honesto` (propuesta) | Veredicto honesto (R4-D08, D09, D11, D12) sin tocar umbrales ni la fórmula de `vvca_score`: precepto derogado ("Artículo N.- (Se deroga)" tras el encabezado exacto, en la ley citada) → 🟡 PRECEPTO DEROGADO, nunca 🟢 (criterio por defecto); la fuente esperada nunca se borra (evidencia de otro ordenamiento → 🟡, −15 alcanzable, "Fuente correcta" solo si coincide; preferencia por la ley citada en el respaldo sin filtro); el 🟢 enuncia solo lo verificado; dimensión sin citas = `null` + ⚪ (sin artículos ni tesis → 🟡 "Sin citas detectadas"); conteo de no verificables junto al subpuntaje; alcance explícito (`alcance_verificacion`, disclaimer 🟢). Pop-ups con "PRECEPTO DEROGADO" junto a "LEY POR CONFIRMAR"; "FUENTE NO COINCIDE" con el semáforo de la cita. R4-D10 pendiente de decisión del responsable (diseño preparado). Ronda 2 (rechazo de Codex + coordinador): la unidad citada (fracción, inciso, párrafo…) se coteja en el texto (fracción derogada → 🟡 PRECEPTO DEROGADO de la unidad; no ubicable → 🟡 UNIDAD CITADA NO COTEJADA); variantes inequívocas de la fórmula ("DEROGADO.", "Derogado", "(Se deroga.)", "Se derogan.") y fórmula ambigua → 🟡 POSIBLE DEROGACIÓN; encabezado sin cuerpo → continuación del mismo precepto o 🟡 EVIDENCIA INCOMPLETA; tesis `partial` cuentan en el veredicto (`tesis_ok` solo verificadas); 🟢 de "solo tesis" retenido (🟡) hasta R4d; alcance de tesis en Telegram; `None` tolerado en `capturar_rag` y en el Gold Set solo con "sin citas". Puerta ronda 1 → ronda 2 sin 🟢 nuevos; `run_regression` 🟢; Gold Set v1 y v2 sin cambios | Integrado en `main` |
| R4d | `fix/vvca-jurisprudencia` (propuesta) | Jurisprudencia determinista (R4-D07, D13, D14) en `itosturre/audit/jurisprudence.py`, sin tocar umbrales ni la clasificación [PR]/[SCJN-I]: registros en cualquier caja ("REGISTRO DIGITAL", "Registro Digital", "registro IUS"; "Registro", "Reg." o "IUS" solo con contexto de tesis; 6 o 7 dígitos, nunca "N/AAAA"; enumeraciones con ",", "y", "o", "y/o", "/" y conector no reconocido → 🟡 COBERTURA INCOMPLETA); contexto del rubro sin cruzar el registro anterior y marcador pegado a la derecha ("registro digital N, de rubro: «…»"); rubro invocado extraído (marcador, comillas o mayúsculas, sin encabezados ni órganos) y cotejado normalizado (NFKD sin acentos, casefold, sin puntuación no numérica: "1.4.14" ≠ "1/4/14"): 🟢 solo con igualdad literal sin marca de supresión ni texto omitido tras el marcador; marca de supresión → 🟡 RUBRO PARCIAL; otra mención de tesis entre rubro y registro → 🟡 RUBRO NO ASOCIADO; polaridad invertida (lista cerrada de negaciones y antónimos) o traslape < 40 % → 🔴; otra diferencia → 🟡; sin rubro invocado → 🟡 (solo acredita el registro). Vigencia nunca "vigente" sin fuente (`no_consultada`/`no_reconocida` como aviso ℹ️ en `avisos`, sin cambiar el semáforo; pérdida en cualquier campo prevalece; conflicto → 🟡; `promover_tesis.py` ya no la asume); el puente de memoria solo bloquea por pérdida. Telegram: todas las alertas completas y avisos aparte. Ronda 2 (rechazo de Codex y del coordinador): cuatro falsos verdes del cotejo, vigencia en conflicto, encabezado u órgano como rubro, falsos positivos de registro, Telegram, puente; la retención del 🟢 de "solo tesis" **se mantiene** (adjudicación del 2-oct-2026). Puerta antes/después sobre el corpus real; `run_regression` 🟢; Gold Set v1 y v2 sin cambios | Integrado en `main` |
| D10 | `fix/vvca-inexistencia-acreditada` (propuesta) | R4-D10 con el criterio del responsable (2-oct-2026, opción C): un artículo no localizado en una ley indexada solo es 🔴 con prueba positiva de inexistencia sobre el cuerpo de la ley (antes de la primera línea TRANSITORIOS); si no, 🟡 NO LOCALIZADO (nunca "alucinación"). Función pura `itosturre/audit/inexistencia.py` (`preparar_ley` una vez por ley); la prueba se busca en todas las rutas de "no localizado"; 🔴 ARTÍCULO INEXISTENTE ACREDITADO con la prueba, la página y la versión indexada (traza `refuted`, método `corpus_estructura`); distancia alta sin metadata → 60–84. Ronda 2 (rechazo de Codex por falsos rojos; la prueba se abstiene ante cualquier ambigüedad): vecinos solo DENTRO DE UN MISMO FRAGMENTO y sin ninguna línea candidata entre ellos ("3 Bis.-", "3o.-", "ARTÍ-\nCULO 3 BIS.-", "Art 3 Bis", "artículo 42…", números) ni mención del citado en el texto (enumeraciones, rangos, "N Bis" suelto); número solo con margen (N ≥ último + max(10, ⌈5 %⌉); entre último + 1 y el margen, 🟡 POSTERIOR AL ÚLTIMO ARTÍCULO de la versión indexada), sin candidata mayor en el cuerpo, sin frontera dudosa y con control de densidad de páginas; identidad documental (título o decreto con la denominación del catálogo); solo con la ley ligada por vínculo sintáctico explícito; contexto previo con dos ordenamientos → ley no identificada; versión indexada en toda alerta. Regla 4 de `CLAUDE.md`/`AGENTS.md` separa tesis y normas (pendiente de aprobación). Puerta antes/después sobre el corpus real: "art. 9999" 🔴 en 30 leyes íntegras y verificables; último + 1 siempre 🟡; ningún otro 🔴 nuevo; `run_regression` 🟢; Gold Set v1 y v2 sin cambios | Integrado en `main` |
| Kit PEN-01 | `fix/kit-piloto-pen01` (propuesta) | Correcciones del kit tras el piloto PEN-01 (defectos D1–D10 del informe local del piloto; no confundir con las decisiones D1–D7 de esta hoja): **D4** citas "SIGLA número" en `menciones.py` ("CNPP 167", "CFF 113 Bis", "CPEUM 1º", "LAmp 217"; sin siglas ajenas ni números que no son artículos; nunca "LA"); **D5** rangos con el contrato del VVCA (`MAX_RANGO`, `RANGO` de cobertura incompleta) sin perder lo que sigue ("105, 108-112 y 114"); **D1** remisión documentada por la fuente (mención en el extracto CONFORME de una ley de la misma afirmación → nota visible, no cobertura); **D3** ubicación "Encabezado…" cotejada por igualdad contra título y última reforma del registro (+ `LNMASCMP.pdf` en `ARCHIVOS_LEYESBIBLIO`); **D2** extracto de tesis contra la región del render (rubro, texto, fuente, precedentes); **D10** evidencia de tesis para un hecho sin `identificacion_criterio` (URL, registro y extracto literal); **D8** PL-007 por tipo de fuente (`tipo_fuente`: tesis del SJF o sentencia internacional: caso, serie y número, fecha, párrafo); **D6** PL-018 ADVERTENCIA "evidencia citada sin cotejar" en un agregado CONFORME (y `es_hallazgo`); **D7** caché por documento y extractor (piloto: 36 → 7 re-extracciones, 22 → 7 s); **D9** aviso de CRLF en `agregar-tesis` con las dos huellas; comando `evidencia articulo` (texto exacto que usa el cotejo); **V1** `tesis_rojas` del VVCA solo cuenta rojas reales (sin cambiar veredictos). Puerta del piloto: los 4 hallazgos verdaderos siguen; de los 20 falsos positivos, 11 desaparecen y 9 quedan justificados (6 tipos no soportados DOF/Corte IDH; 3 PL-007 de sentencias ahora con un esquema satisfacible); PL-014 ve 57 menciones (antes 30), todas cubiertas; ningún falso verde nuevo (comprobado contra los originales). **Ronda 2** (rechazo de Codex y del coordinador; principio: relajar una regla nunca crea un CONFORME sobre algo que no se cotejó): D1 solo exime un artículo citado con la misma ley que le da el extracto, fuera de `referencias` y presentado como remisión, y aun así advierte (PL-019); D3 exige identidad reconocida del ordenamiento afirmado y no acredita vigencia ni contenido normativo; D10 nunca acepta el banner ni el pie y solo un `hecho_aportado` omite la identificación; D2 no acepta para un criterio extractos de precedentes, contendientes ni notas; D4 conserva la letra ("29-A") y valida cada número; D8 exige compatibilidad del `tipo_fuente` declarado. Piloto: 23 BLOQUEANTES + 2 ADVERTENCIAS (ronda 1: 18 + 3); los 4 verdaderos siguen; vuelven a bloquear AF-SCT01-06, AF-SCT05-02 y AF-SCT05-07 (D1) y se suman AF-SCT03-02 y AF-SCT03-04 (D2: hechos sobre la ficha tipificados como criterio judicial). D11 (responsables "Itosturre/JustIA") queda para el responsable | Integrado en `main` |
| PR-4 | `feat/fidelidad-determinista` (propuesta) | Fidelidad determinista (C10, motor 2.0 tras la ronda 2): `itosturre/plan/fidelidad.py` (puro) compara lo que afirma cada `texto_normativo`, `inferencia` o `propuesta` con el texto oficial del artículo de sus pares CONFORME o, si no tiene, de sus `referencias` "art. N SIGLA" resueltas en el paquete con el rigor de la identidad (ley única por archivo y título, pasos a–c, artículo único en el cuerpo); señales por categoría con severidad, precisión, huella y tramos literales lado a lado: procedibilidad, plazos y cifras (palabras, separador de miles, rangos como par, hábiles/naturales/"de calendario", UMA, pesos, salario mínimo, días multa; cada cifra ligada a su condición), inicio del cómputo, modales (con sinónimos de prohibición y mandato implícito del futuro), negación (paridad, emparejada por complemento), excepciones y condiciones (contenido comparado), cuantificadores y órgano (familias cerradas); alineación por cobertura con abstención si es ambigua; fuente truncada = incompleta. Resultado `SENALES` / `SIN_SENALES_DETECTADAS` ("sin señales detectadas por reglas deterministas; revisión del abogado obligatoria") / `NO_COTEJABLE`, **nunca CONFORME**. PL-020 (solo con paquete) por precisión: solo modo de procedibilidad distinto, plazo distinto para la misma condición e inicio del cómputo distinto bloquean en VERIFICADO (ALTA en otro estado); todo lo demás es ADVERTENCIA "señal a revisar"; decisión humana `fidelidad` ligada al plan, la afirmación, la versión del motor y la huella de cada señal. CLI `fidelidad` (sale ≠ 0 si nada fue cotejable), sección en el reporte, protocolo en la ayuda; caché de re-extracción compartida con la identidad. Gold Set de fidelidad 2.0 (casos sintéticos y pares adversariales como puerta en CI; límites documentados y 22 candidatos del piloto aparte). Puerta del piloto: CFF 113 Bis — contradicción en AF-SCT05-06 y REGLA-SCT05 (denuncia frente a querella de la SHCP) y omisión en AF-SCT05-04 | Integrado en `main` |
| Exposición | `feat/menu16-auditar-plan` (propuesta) | MENÚ 16 "Auditar plan jurídico" en la sección nueva "🧭 Planeación legal" del menú principal de `CLAUDE.md`/`AGENTS.md` (y "CÓMO SE ABREN LOS MENÚS" 1-16); `menu-itosturre/references/menu-16-auditar-plan.md` en las dos copias de la skill (flujo guiado A–F con una pregunta a la vez: carpeta del asunto, evidencia oficial con la fecha de consulta del abogado, ledger con extractos de `evidencia articulo`, `cotejar` → `fidelidad` → `lint --paquete --documento --md`, lectura de identidad y fidelidad, decisiones humanas y aprobación con `hash`, firma solo humana, límites honestos y remisión a los MENÚS 1, 3, 6 y 8); Regla absoluta 10 (APROBADO solo lo firma una persona identificada; VERIFICADO solo con evidencia oficial con procedencia cotejada CONFORME; dentro del ledger el VVCA, el RAG y la memoria localizan sin acreditar; la fidelidad solo señala; no modifica la Regla 3 del protocolo anti-alucinación). CLI `plantilla` (`itosturre/plan/plantilla.py`, fricción principal del piloto PEN-01): ledger válido con colecciones vacías y un ejemplo por tipo rotulado `[ASIGNAR]` que el lint marca (PL-001), sin datos jurídicos, nunca sobrescribe y aplica la política de rutas D7; `lint` lista además los campos con marcadores pendientes. Se expone con C8 (DOF y Corte IDH) y D11 aún pendientes, declarados como límites del MENÚ 16 | Implementado y probado; texto de `CLAUDE.md`/`AGENTS.md` pendiente de aprobación del responsable |

PR-2 corrige la lectura de la época en la capa Python; el scraper TypeScript
(`services/itosturre-scraper`, `vvca_audit.ts:418`) sigue tomando la época del banner
hasta R5.

## Siguientes PR (orden propuesto)

El orden no cambia con PR-3. PR-4 se apoya en lo que PR-3 deja resuelto: un par
CONFORME ya garantiza qué documento, qué versión y qué artículo (texto acotado entre su
encabezado y el siguiente) respaldan la afirmación, que es la entrada que necesita el
cotejo de fidelidad.

1. **R4 · Núcleo VVCA**, partido en PR pequeños (crítica externa: PR pequeños y nunca
   `expectedFailure` como criterio de aceptación). R4a dejó el núcleo probable en CI y
   cada defecto fijado por una prueba que afirma la salida ACTUAL; el PR que lo corrige
   cambia esa prueba a sabiendas (registro `DEFECTOS_CONOCIDOS` en
   `tests/test_vvca_nucleo.py`).
   - **R4b · Extracción y resolución de ley:** R4-D01 a R4-D06 — integrado en `main`.
   - **R4c · Veredicto honesto** con alcance explícito ("existencia y ubicación"):
     R4-D08, D09, D11 y D12 — integrado en `main`.
   - **R4d · Jurisprudencia determinista** (detección de registros y cotejo de rubro):
     R4-D07, R4-D13 y R4-D14 — integrado en `main`.
   - **D10 · Artículo no localizado** (criterio del responsable, 2-oct-2026: opción C):
     R4-D10 — integrado en `main`.

   | ID | PR | Defecto (comportamiento actual, fijado en R4a) | Comportamiento correcto esperado |
   |---|---|---|---|
   | R4-D01 | R4b (corregido) | `ARTICLE_RE` pierde Ter/Quáter y la letra de "4o.-A": "artículo 247 Ter del CPF" se audita como art. 247 (🟢 en el corpus real) | Conservar el sufijo y buscar ese precepto |
   | R4-D02 | R4b (corregido) | Enumeraciones: "arts. 14, 16 y 19" (y "Los artículos 14, 16, 19 y 20 CPEUM" del caso versionado) solo extraen el 14; `extract_article_numbers` no reconoce "arts." | Una referencia por artículo enumerado |
   | R4-D03 | R4b (corregido) | Ley por subcadena: "perito Olivares" → art. 10 LIVA | Coincidencia por palabra o abreviatura completa |
   | R4-D04 | R4b (corregido) | "la constitución de la sociedad" → CPEUM | "constitución" sin denominación no identifica la CPEUM |
   | R4-D05 | R4b (corregido) | Hallazgo R4a: la ventana derecha de 100 caracteres prevalece y cruza párrafos: "CFF Art. 42." seguido de un párrafo constitucional se audita como art. 42 CPEUM; un "Art. 5" suelto toma la ley del párrafo siguiente | Prevalece la ley adyacente en la misma oración |
   | R4-D06 | R4b (corregido) | `has_exact_article_heading` acepta "Artículo 4o.-A.-", "1004-A.-" y "29-B." como encabezado de 4o, 1004 y 29; el chunker los etiqueta con el número base (CFF 4o.-A, LIVA 2o.-B/C/D) y entran como candidatos | Tras el número solo cabe el cierre del encabezado |
   | R4-D07 | R4d (corregido) | "REGISTRO DIGITAL: …" y "Registro Digital: …" no se detectan; la tesis desaparece de la auditoría | Detección sin distinguir mayúsculas |
   | R4-D08 | R4c (corregido) | Un fragmento "(Se deroga)" sale 🟢 verified (corpus real: art. 64 CFF, 2o LIVA, 209 Bis CFF) | Un derogado nunca es 🟢 |
   | R4-D09 | R4c (corregido) | `source_match` es True por construcción; si el filtro por fuente falla, la evidencia de otro ordenamiento sale 🟢 con "Fuente correcta"; la penalización −15 es inalcanzable | Comparar siempre con la fuente esperada |
   | R4-D10 | D10 (corregido; opción C del responsable) | Sin coincidencia confiable en una fuente indexada → `refuted` y "Posible alucinación" (🔴 bloqueante); la rama "Alucinación detectada" solo se alcanza si el índice no devuelve vecinos | "No localizado" es no verificable (🟡) salvo prueba positiva de inexistencia en el cuerpo de la ley (🔴 acreditado) |
   | R4-D11 | R4c (corregido) | El 🟢 dice "Normativa y jurisprudencia verificadas" sin tesis citadas (corpus real: "CFF Art. 42.") | La razón enuncia solo lo verificado |
   | R4-D12 | R4c (corregido) | Hallazgo R4a: sin tesis, "SJF 0.0 🔴 (0/0 tesis ok)"; sin artículos, 🟡 "Artículos con verificación insuficiente (RAG: 0.0)" aunque las tesis estén verificadas | "Sin citas" en esa dimensión |
   | R4-D13 | R4d (corregido) | Cotejo de rubro sin NFD: el mismo rubro sin acentos se bloquea como discrepante (falso 🔴) | Normalizar NFD y mayúsculas (Regla 1) |
   | R4-D14 | R4d (corregido) | El cotejo ignora palabras de menos de 5 letras: el rubro con el sentido invertido ("NO ES …") pasa 🟢 | Detectar negaciones o exigir coincidencia literal normalizada |

2. **PR-4 · Fidelidad determinista** (plazos, modales, negaciones, excepciones,
   cuantificadores) sobre pares ya CONFORME en identidad; nunca emite CONFORME por sí sola.
   **Integrado en `main`** (rama `feat/fidelidad-determinista`): además de los
   pares CONFORME, resuelve las `referencias` de propuestas e inferencias sin evidencia y suma
   procedibilidad e inicio del cómputo (recomendación n.º 1 del piloto PEN-01). Ronda 2 (la
   revisión externa rechazó la ronda 1 por falsos bloqueantes y falsos negativos): política
   de precisión, pares adversariales como puerta, decisiones ligadas a la huella de cada
   señal y a la versión del motor, fuente truncada como incompleta y salida ≠ 0 si nada fue
   cotejable.
3. **Exposición**: MENÚ 16 y regla absoluta "APROBADO solo humano" cuando el CLI esté
   probado con un piloto. El piloto PEN-01 (2-oct-2026) ya re-corrió el kit
   (`evidencia agregar-*` → ledger → `cotejar` → `lint`); sus correcciones son el PR
   "Kit PEN-01". **Implementado y probado** (rama propuesta `feat/menu16-auditar-plan`):
   MENÚ 16, Regla absoluta 10 y CLI `plantilla` (fricción principal del piloto: el ledger
   se construía entero a mano). Se expone con el soporte de DOF y Corte IDH (C8) aún
   pendiente, declarado como límite en el propio menú. El responsable aprobó el texto exacto
   de los cambios a `CLAUDE.md`/`AGENTS.md` y decidió D11 (2-oct-2026).

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
  LAmp, LNEP y (desde el kit PEN-01) LNMASCMP, siempre confirmada con el título del
  encabezado. Otras leyes: las menciones de artículo **con** ley quedan SIN_EVIDENCIA hasta
  agregarlas.
- `menciones.py` no expande enumeraciones de registros ("registros digitales 1 y 2"):
  solo cuenta el primero; tampoco reconoce claves de tesis aisladas de TCC (se suplen con
  búsqueda literal de la clave de la fuente). Los rangos de artículos sí se expanden desde
  el kit PEN-01.
- Los artículos con letra ("4o.-A") no tienen clave en `menciones.py`: una afirmación que
  los menciona queda SIN_EVIDENCIA, nunca CONFORME.
- La relación original–texto solo se acredita con el mismo extractor y versión: un
  cambio de versión de PyMuPDF deja las leyes registradas en SIN_EVIDENCIA hasta volver a
  registrarlas (falla cerrado).
- Los enlaces duros a archivos externos no se detectan (no son enlaces simbólicos ni
  puntos de reanálisis); su contenido sigue verificado por huella en cada lectura.

Pendientes derivados de R4b:

- El chunker sigue etiquetando `4o.-A`, `247 Bis` o `29-A Bis` con el número base: una
  re-ingesta con la etiqueta completa permitiría verificar por metadata los preceptos con
  sufijo (hoy se exige el encabezado exacto en el texto y, si falta, quedan 🟡).
- ~~Con todas las citas normativas no verificables, `score_rag` vale 0.0 y `semaforo_rag` 🔴
  aunque el veredicto sea 🟡~~ — resuelto en R4c (`null` y 🟡).
- Catálogo: denominaciones fuera de él quedan como ley no identificada (🟡): p. ej.
  "Código de Comercio", "Ley General de Salud". "Ley Fundamental", "Norma Suprema", "Carta
  Magna" o "la Constitución" sin denominación completa ni antecedente inequívoco quedan 🟡
  por **criterio del responsable (1-oct-2026)** (`docs/PROTOCOLO_VVCA.md` §4): no es un
  hueco del catálogo que deba cerrarse mapeándolas a la CPEUM. Claves que siguen siendo frases genéricas o de institución (protegidas por la
  regla de "otra entidad", pero no por la entidad completa): "carrera judicial", "ley de
  carrera judicial", "delincuencia organizada", "extinción de dominio", "derechos del
  niño", "derechos del contribuyente", "miscelánea fiscal", "issste", "fovissste",
  "infonavit", "prodecon" y el alias "Ejecución Penal" (sin fuente). El PDF
  `Reglamento organico poder judicial de la federación 2026.pdf` contiene el texto de la
  Ley Orgánica del Poder Judicial de la Federación (duplicado del de la LOPJF). Ampliar o
  depurar `LAW_SOURCE_MAP` es decisión del responsable: **9-oct-2026, descartado** — se
  retiró su clave (la cita del reglamento queda 🟡) y `scripts/fuentes_oficiales.json` lo
  marca `descartado`.
- La fracción conserva la expresión anterior (`fr`/`frac` + palabra): "artículo 5 frente
  a…" se lee como fracción "ente" y "fracc. III" como "acc.". No afecta la ley ni el
  semáforo; queda para un PR menor.

Pendientes derivados de R4c:

- ~~R4-D10 ("no localizado" → 🔴 "Alucinación detectada"/"Posible alucinación")~~ — resuelto
  en D10 con la opción C del responsable (2-oct-2026).
- ~~Derogación parcial no detectada ("artículo 31, fracción I, del CCF" salía 🟢 86)~~ —
  resuelto en la ronda 2 (cotejo de la unidad citada). Queda: los párrafos, apartados y bases
  no se ubican en el texto del PDF, así que toda cita de párrafo queda 🟡 (UNIDAD CITADA NO
  COTEJADA) hasta que exista un cotejo de párrafos fiable; una fracción repetida (p. ej. en
  dos apartados) tampoco se coteja.
- 🟢 de "solo tesis" retenido como 🟡 (`scoring_vvca.RETENER_VERDE_SOLO_TESIS`): R4d
  corrigió D13/D14, pero la retención se mantiene (adjudicación del 2-oct-2026) hasta validar
  el cotejo del rubro con un corpus de tesis mayor que las 10 actuales.
- Ordenamiento abrogado completo: el PDF del Código Federal de Procedimientos Civiles lleva
  "Código Abrogado DOF 07-06-2023" en los encabezados de página; R4c no lo detecta, así que
  un artículo suyo cuyo encabezado se ubique puede salir 🟢 (en la puerta, el art. 1 salió 🟡
  por evidencia insuficiente). Detectarlo es decisión del responsable (catálogo de vigencia
  por ordenamiento).
- Fragmentos con varios artículos: en PDFs con "ARTÍCULO" en mayúsculas (CFPC, LFPCA, LFPC)
  el chunker no corta y la etiqueta de metadata no corresponde al precepto; esas citas
  suelen quedar 🟡 (evidencia insuficiente) y su derogación no se detecta (p. ej. art. 69
  LFPCA, art. 136 LFPC en la puerta de R4c). Requiere re-ingesta.
- El respaldo sin filtro conserva `n_results=3`: si la ley citada no está entre los tres
  vecinos, la cita queda 🟡 "evidencia de otro ordenamiento" aunque exista en el corpus.

Pendientes derivados de R4d:

- ~~`itosturre/memoria/puente.py` trataba como vigencia perdida todo `estado_vigencia !=
  "vigente"`~~ — corregido en la ronda 2 de R4d (solo superada/interrumpida/sustituida).
- Retención del 🟢 de "solo tesis": reconsiderarla con un corpus de tesis mayor.
- Formato de bloque (rubro, texto de la tesis, registro): el texto suele mencionar "tesis" o
  "criterio", lo que corta la asociación (🟡 RUBRO NO ASOCIADO). Falla cerrado; afinarlo exige
  distinguir el cuerpo de la propia tesis de la mención de otra.
- La clave mencionada junto al rubro ("tesis 2a./J. 58/2010") no se coteja contra la clave del
  corpus: una clave equivocada no impide "coincide" si el rubro es literal.
- Vigencia sin dato o desconocida: aviso ℹ️ sin cambiar el semáforo (criterio por defecto). El
  responsable puede endurecerlo (p. ej. 🟡 para `no_reconocida`, o exigir vigencia consultada
  para un 🟢).
- Listas cerradas de polaridad (`NEGACIONES`, `ANTONIMOS_NEGATIVOS`, `PARES_SIMETRICOS`):
  un antónimo fuera de ellas ("INCOMPUTABLE") no se detecta como inversión (queda 🟡 no
  literal, nunca 🟢). Ampliarlas es decisión del responsable.
- Un tramo de rubro transcrito sin marca de supresión que omite una negación del real se
  bloquea (🔴 sentido invertido); con "…" queda 🟡 RUBRO PARCIAL.
- Tesis citada solo por su clave, sin registro ("la jurisprudencia 2a./J. 58/2010 sostiene…"):
  no se detecta como referencia (no hay búsqueda por clave en el corpus local).
- El rubro que sigue al registro sin marcador pegado (ficha del SJF pegada: "Registro digital:
  N … Tipo: … RUBRO") no se asocia: la tesis queda 🟡 sin rubro invocado.

Pendientes derivados de D10:

- Prueba de vecinos: desde la ronda 2 solo dentro de un mismo fragmento. La ingesta corta en
  cada encabezado "Artículo N" sin solapar, así que en las leyes con encabezados normales dos
  artículos nunca comparten fragmento ("19 Ter CPEUM" queda 🟡); en las leyes con "ARTÍCULO"
  en mayúsculas los encabezados repetidos por el solapamiento de subfragmentos también la
  impiden. Una re-ingesta que guarde el desplazamiento de cada fragmento en el texto completo
  permitiría observar la continuidad.
- Identidad documental: no se comprueba en ISSSTE, INFONAVIT, LFTSE, LGDNNA (el catálogo no
  tiene la denominación completa del título: "Ley del Instituto…", "de los Trabajadores",
  "de los Derechos"), LFPPI (el catálogo dice "propiedad intelectual"; el PDF es la Ley
  Federal de Protección a la Propiedad Industrial), el "Reglamento orgánico" (su PDF contiene
  la LOPJF), CDN, RMF, LJAJal y el reglamento de movilidad: sin prueba. Completar las
  denominaciones es decisión del responsable (catálogo).
- Página de la prueba: la de la metadata del fragmento (inicio del fragmento en el índice).
  En leyes con fragmentos de varios artículos puede no ser la del encabezado; la paginación
  "N de M" de los compilados de la Cámara permitiría ubicarla.
- Densidad de páginas: en el corpus actual ningún tramo la viola (la peor holgura, 0.70 de
  1, en el CPF); el umbral de 800 caracteres por página es deliberadamente laxo. Las páginas
  sin texto anteriores al primer fragmento no se controlan.
- Sin prueba por número, además: CADH, CDN, PIDCP y LJAJal (sin línea TRANSITORIOS); LNEP
  ("ARTICULO 225" del decreto en el cuerpo), LFDO ("148 Bis" al inicio de línea), LISR
  ("407. …" al inicio de línea), CPJal, Notariado, Movilidad Jal., LIVA e INFONAVIT (frontera
  dudosa: "455 ter", "935 ter", "2016 Bis", "Artículo 123" tras TRANSITORIOS).

Pendientes derivados del kit PEN-01 (piloto del 2-oct-2026):

- DOF y Corte IDH siguen sin cotejo de identidad (SIN_EVIDENCIA, "tipo no soportado"):
  en el piloto quedan 6 PL-016 por eso. Es C8 (identidad de la nota del DOF por `codigo`
  y fecha, huella del contenido y no del HTML, que incrusta la URL).
- PL-014 cubre por mención, no por verificación: copiar el texto del documento en las
  afirmaciones basta para cubrirlo (en el piloto, las 57 menciones quedan cubiertas). No
  se reconocen "N SIGLA" ("167 CNPP"), "CPEUM art. 19" ni la ley a la izquierda (decisión
  pendiente), ni lo que sigue a ";" en "CFF 108; 92 fr. I", ni "LA N" (ambigua con el
  artículo "la"; usar "LAmp N").
- La remisión documentada (D1) solo vale para extractos de leyes que nombran el artículo
  con su ley; un "artículo 40 de esta Constitución" o "los artículos 105, 108…" (sin ley)
  no eximen, y el marcador de remisión es una lista cerrada ("remite", "remisión"). En el
  piloto, AF-SCT01-06, AF-SCT05-02 y AF-SCT05-07 vuelven a bloquear por eso: o se
  reescriben como remisión con ley o se cita la evidencia del artículo remitido.
- Para un criterio judicial, los extractos de precedentes, contendientes y notas no valen
  (ronda 2): los hechos sobre la ficha (integración, notas) van como `hecho_aportado`.
- Afirmaciones compuestas: una parte sin cotejar que no genera menciones (una fecha del
  DOF) solo produce PL-018; se recomienda descomponerlas (el kit no lo impone).
- ~~Fidelidad (PR-4): el piloto dejó defectos que la identidad no ve (CFF 113 Bis exige
  querella y el entregable infiere denuncia; una afirmación generaliza la fr. III del CFF 92
  y ya no la bloquea PL-016, porque su identidad es correcta; omisiones en CNPP 94 y CFF 92).~~
  — PR-4 detecta el CFF 113 Bis (precisión alta: bloquea si la afirmación es VERIFICADO) y,
  como señales a revisar, las omisiones de CFF 92 (sobreseimiento) e inicio del cómputo; no
  detecta la generalización de la fr. III ni la lista incompleta del CNPP 94 (ver
  "Pendientes derivados de PR-4").
- D12 (la nota de reforma del compilado sostiene fechas DOF a lo sumo VERIFICADO) y D13
  (la política D7 depende de desde qué checkout se ejecuta `plan_audit.py`) no se tocaron.
- VVCA: V2 (`HF_HUB_OFFLINE=1` por defecto en `audit`), V3 (citas "SIGLA N" en
  `referencias.py`) y V4 (versión del corpus frente a la del paquete) siguen abiertos.

Pendientes derivados de PR-4 (fidelidad determinista):

- **Política de precisión (ronda 2) — criterio por defecto fijado por el coordinador,
  pendiente de confirmación del responsable:** solo `procedibilidad.modo_distinto`,
  `plazos_cifras.distinto_misma_condicion` e `inicio_computo.distinto` bloquean (en
  VERIFICADO). La cifra ausente y todas las omisiones (requisito de procedibilidad, SHCP,
  inicio del cómputo, excepciones, condiciones, cuantificadores) **no bloquean por defecto**:
  son ADVERTENCIA "señal a revisar", igual que modales, negación, cuantificadores añadidos,
  excepción distinta, órgano distinto, cifras sin condición y la alineación ambigua. El
  responsable puede endurecerlo código por código (`CODIGOS`), siempre con sus casos en el
  Gold Set.
- **Curación de los 22 candidatos del piloto** (`tests/fixtures/fidelidad_gold_set_v1.json`,
  `candidatos_piloto`, `pendiente_responsable`): hasta que el responsable fije
  `verdad_responsable` y los apruebe, se miden aparte y no son puerta. Con el motor 2.0: de 16
  propuestos con cambio se detectan 10 (FID-02, 06, 07, 08, 09, 10, 18, 19, 20, 21; dos con
  precisión alta: FID-09 y FID-10, el CFF 113 Bis) y no 6 (FID-03, 04, 15, 16, 17, 22: forma u
  órgano omitidos, lista de excepciones incompleta, remisión y sujeto/modal fuera de lista,
  generalización, efecto no previsto, denominación); 0 señales en los 6 fieles. Varios
  detectados lo son por una categoría distinta de la que propone el operador (FID-06: SHCP
  omitida; FID-19: condición omitida y alineación ambigua).
- **Límites documentados** (casos `LIM-*` del Gold Set, medidos sin ser puerta): la
  procedibilidad se lee por artículo y no por delito (el art. 92 CFF prevé querella,
  declaratoria y denuncia: asignar a un delito el modo de otro no se detecta, LIM-01); una
  enumeración incompleta dentro de una excepción no se señala (CNPP 94, LIM-02); el órgano solo
  se compara entre familias cerradas (jurisdiccional, Ministerio Público, defensor, policía:
  "Congreso" frente a "legislaturas" no se detecta, LIM-03). Tampoco se señalan el sujeto
  omitido, las generalizaciones de contenido ("recoge los nuevos delitos") ni la omisión de
  "todos"; una cifra presente en varias oraciones no alineadas no se atribuye. La doble
  negación se resuelve por paridad de la cadena y el cambio de órgano dentro de las familias
  cerradas da ADVERTENCIA.
- Listas cerradas de términos (`fidelidad.py`): ampliarlas o depurarlas es decisión del
  responsable, siempre con su caso en el Gold Set. Ronda 2 sumó "de calendario", UMA, pesos,
  "$", salario mínimo, separador de miles, "no le está permitido", "le está prohibido",
  "ninguno … podrá", el mandato implícito del futuro ("se interpondrá", "ordenará") y las
  condiciones "si se tratare de", "contra", "tratándose de", "en los casos de". Siguen fuera:
  "oficiosamente" como modo de procedibilidad (a propósito), "cualquier" como cuantificador,
  "aun cuando".
- La omisión de procedibilidad es amplia a propósito: toda afirmación que hable de
  persecución sin el requisito que su artículo impone recibe ADVERTENCIA (en el piloto,
  también la sostiene AF-SCT05-04).
- `cifra_ausente`: solo con fuentes completas y no truncadas; en el piloto aparece en
  AF-CON02-01 (inferencia, NO VERIFICADO: "180 días" frente al art. 167 CNPP que cita como
  referencia; la cifra viene de un decreto del DOF), hoy ADVERTENCIA.
- Tesis, DOF y Corte IDH no aportan texto de artículo: sus afirmaciones son NO_COTEJABLE
  (C8 para DOF y Corte IDH; para tesis, comparar contra el rubro y el texto sería otro PR).

Pendientes derivados de la Exposición (MENÚ 16):

- El flujo guiado del MENÚ 16 no se ha probado aún con un abogado sobre un asunto real: falta
  un piloto de uso (tiempos y fricciones de cada paso, en especial la construcción del ledger
  con la plantilla).
- La plantilla pone `autor: agente` en los ejemplos (la opción más estricta); el operador debe
  cambiarlo cuando la afirmación la aporta una persona o la fuente.
- La línea de marcadores pendientes de `lint` solo sale en la consola: `--json` y `--md` no la
  incluyen (el reporte Markdown lista hallazgos, no los campos que conservan un marcador).
- D11 decidida por el responsable (2-oct-2026): `responsable_no_humano` rechaza "Itosturre" y
  "JustIA" en cualquier posición (`NOMBRES_SISTEMA` en `itosturre/plan/estados.py`), así que
  PL-012 se dispara; Gold Set de planes con el caso `pl012_responsable_nombre_del_sistema`.

## Qué no construir

Un juez LLM que califique planes; equivalencias entre 🟢 VVCA y VERIFICADO; consumo del
microservicio interno del SJF; envíos automáticos o LLM externo dentro del flujo;
decisiones guardadas en la memoria contextual; detección semántica automática de
contradicciones; interfaz web.

## Decisiones pendientes del responsable

- ~~Regla 3 de `CLAUDE.md` (el RAG como fuente de verificación) frente a D4~~ — resuelto por la
  regla absoluta 10 (2-oct-2026), acotada al ledger: dentro de la auditoría de planes el RAG
  localiza (a lo sumo CANDIDATO); la Regla 3 sigue vigente para las citas de escritos.
- Cuarentena de `agentes/vigilancia_jurisprudencial.py`, que consume el microservicio interno.
- Lista de responsables no humanos: hoy rechaza cargos como "Agente del MP" (falla cerrado).
- ~~D11 del piloto PEN-01: "Itosturre / JustIA" como responsable~~ — decidido (2-oct-2026):
  se rechazan como responsables humanos.
- Cobertura cuando la ley aparece a la izquierda del artículo ("la Ley de Amparo, en su
  artículo 217"): hoy produce hallazgos de más, nunca un falso verde.
- ~~R4-D10: severidad de "no localizado en una ley indexada"~~ — decidido (opción C,
  2-oct-2026; ronda 2 tras el rechazo por falsos rojos). Pendiente: aprobar el texto nuevo de
  la Regla 4 de `CLAUDE.md`/`AGENTS.md` (tesis y normas por separado) antes del merge y
  completar las denominaciones del catálogo que impiden la identidad documental (ver
  "Pendientes derivados de D10").
- Precepto derogado: R4c lo deja 🟡 por defecto; endurecerlo (p. ej. 🔴 salvo régimen
  transitorio invocado) es criterio jurídico del responsable.
- Recuración de `green_cff_art_42` en el Gold Set v2 (el defecto fue de selección de
  evidencia, no de puntaje).
- Exposición (MENÚ 16): aprobar el texto exacto de la Regla absoluta 10 y de la opción 16 del
  menú principal en `CLAUDE.md`/`AGENTS.md` antes del merge de `feat/menu16-auditar-plan`.
- PR-4: curar los 22 candidatos de fidelidad del piloto (verdad del responsable), aprobar las
  listas cerradas de términos y confirmar o endurecer la política de precisión de la ronda 2
  (hoy solo bloquean el modo de procedibilidad distinto, el plazo distinto para la misma
  condición y el inicio del cómputo distinto; la cifra ausente y las omisiones son
  ADVERTENCIA por defecto).
