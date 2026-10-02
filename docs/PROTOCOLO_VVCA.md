# Protocolo VVCA — Especificación técnica

VVCA = **V**erificación · **V**alidación · **C**ontextualización · **A**uditabilidad.
Este documento describe cómo `OpenNotebook.py` + `scoring_vvca.py` materializan el Protocolo
Anti-Alucinación del prompt Itosturre. Es la referencia de implementación, no el prompt.

## 1. Dos scores independientes (no se promedian)

| Score | Qué mide | Fuente |
|---|---|---|
| `score_rag` | Artículos citados vs. corpus indexado | ChromaDB (estático) |
| `score_sjf` | Tesis citadas vs. corpus local de jurisprudencia | corpus local (estático) |

No existe un "score global" compuesto. El **veredicto** es una decisión binaria con razón.

## 2. Semáforo por referencia

`vvca_score()` parte de la distancia coseno y ajusta por coincidencia de fuente:

```
base = (1 − distancia) * 100
base −= 15  si la fuente recuperada no es la esperada
base −= 10  si la cita no traía ley identificable
```

| Semáforo | Score | Lectura |
|---|---|---|
| 🟢 | ≥ 85 | Citar con seguridad |
| 🟡 | 60–84 | Citar con reserva — verificar |
| 🔴 | < 60 | No citar — investigar |

`COSINE_THRESHOLD = 0.25` (e5-large normalizado: distancia = 1 − similitud). Por debajo se
considera verificado; por encima se levanta alerta de coincidencia débil. El valor anterior
(0.50) era laxo: aceptaba similitud 0.50 (texto sólo tangencialmente relacionado).

## 3. Veredicto binario (`veredicto_global`)

Reglas en orden de precedencia:

1. `tesis_discrepantes > 0` → **🔴 bloqueante** — registro real con rubro que NO coincide con
   el invocado (alucinación o cita maliciosa). USO PROCESAL PROHIBIDO.
   *Criterio:* se marca discrepante cuando el solapamiento de palabras clave (>4 chars) entre
   el rubro real y el invocado es **< 40%** (`OpenNotebook.py`, `build_vvca_tesis`). Es el
   umbral del 🔴 bloqueante — el más fuerte del sistema; ajustarlo con cuidado.
2. `tesis_superadas > 0` → **🔴 bloqueante** — la cita existe, pero el criterio ya no
   está vigente.
3. `normativa_refutada > 0` → **🔴 bloqueante** — al menos una cita normativa quedó
   refutada. El promedio no puede ocultarla.
4. `tesis_no_encontradas > 0` → **🟡** — ausentes del corpus local; *no confirmadas como falsas*
   (el corpus puede estar incompleto).
5. `normativa_no_verificable > 0` → **🟡** — al menos una cita normativa tiene evidencia
   parcial o insuficiente.
6. `score_rag < 70` → **🟡** — artículos con verificación insuficiente.
7. en otro caso → **🟢**.

La distinción entre una cita refutada y una no verificable es crítica: "rubro discrepante"
o "fuente incorrecta" (peligroso) ≠ "no encontrada"
(corpus incompleto). Nunca se tratan igual.

El `score_rag` es descriptivo. El veredicto global sigue la peor traza: una sola cita roja
bloquea y una sola cita amarilla impide declarar el documento apto, aunque el promedio sea alto.

## 4. Guards de resolución de artículos (anti-falso-veredicto)

**Extracción (R4b).** Cada artículo citado es una referencia propia, con su designación
completa:

- Sufijos y letras se conservan: `247 Ter`, `2o. Bis`, `4o.-A`, `29-A`, `32-B Quáter` (antes
  "247 Ter" se auditaba como el 247 y "4o.-A" como el 4o).
- Enumeraciones y rangos: `arts. 14, 16 y 19`, `467 a 471` y `155–157` producen una
  referencia por artículo (antes solo se auditaba el primero). En `artículo 471, 3 días` o
  `10 de junio` el número no es artículo.
- Enumeraciones con leyes intercaladas se leen por segmentos, cada uno con **su** ley:
  "los artículos 14 de la CPEUM y 42 del CFF"; "17 de la Ley de Amparo y 107
  constitucional"; "16 y 19 de la CPEUM, así como 167 del CNPP".
- **Nada desaparece en silencio.** Un rango de más de 20 artículos conserva sus extremos y
  deja una referencia `🟡 COBERTURA INCOMPLETA` ("rango de N artículos: solo se auditaron
  los extremos"); un número ligado a una ley que no se puede extraer con certeza ("…, al
  igual que el 42 del CFF") también queda como cobertura incompleta. Cuentan como no
  verificables: el veredicto global no puede ser 🟢.

**Resolución de la ley: solo por vínculo sintáctico acreditable.** Si no lo hay o hay más de
un candidato, la ley queda no identificada (🟡, con motivo). Nunca se asocia una ley que solo
aparece en la misma oración. Las coincidencias son por palabra o abreviatura completa
("perito Olivares" ya no es la LIVA).

1. **A la derecha, pegada al precepto:** "artículo 16 de la/del …", "art. 16 CPEUM",
   "16 constitucional", tras fracción/párrafo/inciso del mismo precepto ("artículo 107,
   fracción V, inciso a), de la Ley de Amparo"). "El artículo 5 establece que conforme a la
   Ley de Amparo…" no liga el 5 a la Ley de Amparo.
2. **A la izquierda:** pegada a la cabeza ("La Ley de Amparo, en su artículo 16", "CFF Art.
   42") o por posesivo con un único ordenamiento previo en la oración ("La Ley de Amparo
   regula el juicio, y en su artículo 217…"). Prevalece sobre una mención posterior no
   ligada; si la izquierda y la derecha nombran leyes distintas, hay **vínculos en
   conflicto** y la ley queda no identificada. La ley que otro artículo ya tomó a su derecha
   no sirve a la izquierda ("el artículo 16 de la CPEUM y el artículo 5…": el 5 queda sin ley).
3. **Varias leyes para un grupo** solo se reparten con "respectivamente" y el mismo número de
   leyes que de artículos ("Los artículos 14 y 16, de la CPEUM y del CFF, respectivamente");
   si no, todo el grupo queda no identificado. Nunca se comparte la primera ley.
4. **Coordinación pura** ("el artículo 14 y el artículo 16 de la CPEUM", "CFF Art. 42 y Art.
   43") comparte el vínculo; "así como" o "en relación con" solo lo comparten con un
   distributivo ("…, ambos de la CPEUM").
5. **Contexto previo / sticky-law** — último recurso, solo con oraciones anteriores (≤600
   caracteres hacia atrás). Se marca `law_inferred=True`. Dentro del mismo párrafo sigue como
   antes. Si la mención está en **otro párrafo**, la ley queda **por confirmar**
   (`law_requires_confirmation=True`): el semáforo se limita a 🟡 (ni 🟢 ni 🔴) con la alerta
   "LEY POR CONFIRMAR — ley inferida de otro párrafo: confirmar el ordenamiento", salvo que
   la mención sea un encabezado inequívoco (una línea que es solo la denominación de la ley:
   "## Código Fiscal de la Federación"). "### A. Orden constitucional mexicano (CPEUM)" no lo
   es: los artículos bajo ese encabezado quedan por confirmar.

Reglas de identificación:

- "Constitución" sin denominación ("Constitución Política de los Estados Unidos Mexicanos",
  "Constitución Federal", "Constitución General de la República") ni abreviatura (CPEUM) no
  identifica la CPEUM ("la constitución de la sociedad" no es la Constitución);
  "constitucional" solo cuenta junto al precepto ("artículo 16 constitucional").
- Un genérico ligado al artículo ("de la ley", "del código", "de la Constitución", "del
  ordenamiento citado", "dicha ley, en su artículo") solo se resuelve si antes se nombra
  **un único** ordenamiento de ese tipo; si no hay ninguno o hay varios, la ley queda no
  identificada. Un antecedente de otro párrafo deja la ley por confirmar.
- Un ordenamiento concreto que no está en el catálogo ("Código de Comercio", "Ley General de
  Salud", "ley fiscal", "Constitución local"), o uno de otra entidad ("Código Penal para el
  Estado de México", "Ley de Carrera Judicial del Estado de Jalisco"), deja la ley no
  identificada con el motivo "ordenamiento fuera del catálogo" y bloquea cualquier inferencia.
  Las claves estatales del catálogo exigen la entidad completa ("Código Penal para el Estado
  Libre y Soberano de Jalisco").

Comportamiento al auditar (`audit()`):

- **Coincidencia de metadata `source+article`** → no basta por sí sola. Entre todos los
  fragmentos candidatos se prefiere el que contiene el encabezado exacto (`Artículo N.-`).
  Una mención interna como "conforme al artículo 42" se conserva como evidencia auditable,
  pero queda en 🟡 y nunca acredita por sí sola el precepto citado.
- **Ley identificada pero ausente del corpus** → `🟡 NO VERIFICABLE`. *No* se reporta como
  "alucinación": el corpus simplemente no la contiene. (Guard P0 — antes producía un falso 🔴
  que tachaba de falsa una cita válida, p. ej. LGV/PIDCP.)
- **Artículo sin ley identificada** (R4b) → `🟡 NO VERIFICABLE — LEY NO IDENTIFICADA`
  con el motivo para el abogado (no se nombra el ordenamiento; genérico sin antecedente
  inequívoco; ordenamiento fuera del catálogo; alias sin fuente en el corpus). No se busca
  el número en todo el corpus: eso sería adivinar la ley. Cuenta como amarillo y nunca es
  🟢 ni 🔴. (Antes un "Art. 5" suelto se cotejaba por número contra el código que saliera
  más parecido: 🟡 con el score capado a 84 o, con distancia alta, 🔴.)
- **Precepto con sufijo sin su encabezado exacto** (R4b) → `🟡 NO VERIFICABLE`. El índice
  actual etiqueta `4o.-A`, `247 Bis` o `29-A Bis` con el número base, así que la búsqueda
  por metadata devuelve el artículo base y sus variantes; solo un fragmento con el
  encabezado exacto ("Artículo 247 Ter.-") acredita el precepto. Lo mismo si se cita el
  número base y el índice solo ofrece variantes con sufijo. Nunca 🟢 contra el artículo
  base ni 🔴: no se acreditó que el precepto no exista. (Una re-ingesta con la etiqueta
  completa eliminaría esta limitación; R4b no re-ingesta.)
- **Cobertura incompleta** (R4b) → `🟡 COBERTURA INCOMPLETA` (traza `not_verifiable`,
  método `cobertura_extraccion`): rango recortado o número ligado a una ley que no se
  extrajo con certeza. Auditar esos artículos por separado.
- **Ley por confirmar** (R4b) → a lo sumo 🟡 (traza `partial`), aunque el fragmento
  coincida, y nunca 🔴: el cotejo se hizo contra una ley inferida de otro párrafo.
- **Tesis citada no encontrada** en el corpus local → `🟡 NO VERIFICABLE` (no confirmada
  falsa); cuenta en `amarillos`, no en `rojos`, coherente con el veredicto.
- **No encontrado con la fuente esperada** → 🔴 alerta crítica (posible alucinación).

> El guard 🟡 NO VERIFICABLE para una ley ausente solo se ejerce con `--force`; sin `--force`
> la auditoría se **detiene** antes con `status: corpus_incomplete` (ver §5).

## 5. Cobertura del corpus

Antes de auditar, `check_corpus_coverage()` compara las leyes referenciadas contra lo indexado.
Si faltan y no se pasó `--force`, la auditoría se **detiene** (`status: corpus_incomplete`) en
vez de auditar a ciegas. `scripts/check_corpus.py` hace lo análogo contra todo `LAW_SOURCE_MAP`
y se usa como gate (sale != 0 si hay ausentes).

## 6. Higiene del corpus

- Solo **ordenamientos** entran al corpus estatutario. Las compilaciones de tesis
  (`*_Tesis_Completas`, `listado-de-tesis`) están en `EXCLUDE_PATTERNS` y van por jurisprudencia.
- Documentos personales/de cliente (actas, CURP, estados de cuenta, escritos) están excluidos.
- Ordenamientos fuera de jurisdicción (p. ej. Nuevo León) se excluyen para no contaminar casos
  de Jalisco por coincidencia de número de artículo.

## 7. Calibración

`OpenNotebook.py correct` registra discrepancias observadas; `OpenNotebook.py calibrate`
analiza falsos positivos/negativos y sugiere ajustar `COSINE_THRESHOLD`. Toda recalibración del
umbral debe validarse contra `casos_de_prueba/` antes de fijarse.

La semilla reproducible vive en `tests/fixtures/vvca_gold_set_v1.json` y se ejecuta con
`python scripts/evaluate_gold_set.py`. Su estado `seed_synthetic` significa que funciona como
gate de regresión, no como validación empírica definitiva de los umbrales.

## 8. Trazabilidad

`OpenNotebook.audit()` genera `traceability.records` para todas las referencias, incluso las
no verificables o refutadas. El esquema, los estados y el hash de evidencia se describen en
`docs/CONFIABILIDAD_VVCA.md`. `vvca_full.py` persiste la traza en
`<caso>/vvca_traceability.json`.

## 9. SJF en vivo

El scraper es una herramienta estratégica separada y no alimenta `score_sjf`. Consulta los
dos portales públicos con fallback, conserva cada intento y distingue ausencia confirmada de
fallo técnico. No consume endpoints internos no documentados. Véase
`docs/CONFIABILIDAD_VVCA.md`.

## 10. Estados y fallo cerrado del pipeline

`vvca_full.py` persiste un estado global en `vvca_full.json`:

- `ok`: todos los pasos esenciales solicitados terminaron y sus salidas cumplen contrato;
- `partial`: el operador autorizó expresamente continuar con `--force` o
  `--allow-partial-sjf`;
- `failed`: un paso esencial falló, produjo JSON inválido o no generó el artefacto esperado.

Son fallos bloqueantes: código no cero de OpenNotebook; salida RAG no JSON o con
`status != "ok"`; fallo del scraper solicitado; ausencia, falta de frescura o schema distinto
de 2.0 en `auditoria_vvca.json`; y fallo de una captura solicitada. En esos casos el pipeline
guarda diagnóstico, devuelve código 1 y no imprime el mensaje de conclusión exitosa.

`--no-sjf` y `--no-rag-capture` son omisiones explícitas y quedan registradas como `skipped`.
La memoria contextual es accesoria: un fallo suyo se registra como `warning` y no cambia una
auditoría válida.
