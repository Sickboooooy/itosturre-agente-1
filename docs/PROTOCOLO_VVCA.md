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

**Dimensión sin citas (R4c, R4-D12).** Si el escrito no cita artículos (o tesis), esa dimensión
dice "sin citas": `score_rag`/`score_sjf` valen `null`, `semaforo_rag`/`semaforo_sjf` son ⚪
(neutro) y `rag_sin_citas`/`sjf_sin_citas` valen `true`. Si hay citas pero ninguna con
evidencia evaluable (todas no verificables), el puntaje también es `null` y el semáforo es 🟡
(🔴 solo si alguna quedó refutada). Antes ambas situaciones salían "0.0 🔴" ("SJF 0.0 🔴 (0/0
tesis ok)"). Con puntaje, el semáforo de la dimensión sigue siendo el de su promedio, pero el
`summary` dice junto al subpuntaje cuántas citas quedaron no verificables o refutadas ("RAG
92.0 🟢 (2 arts; 1 no verificable)"): un 🟢 del promedio nunca las oculta.

## 2. Semáforo por referencia

`vvca_score()` parte de la distancia coseno y ajusta por coincidencia de fuente:

```
base = (1 − distancia) * 100
base −= 15  si la fuente recuperada no es la esperada
base −= 10  si la cita no traía ley identificable
```

La fórmula no cambió en R4c. Lo que cambió es que la penalización −15 ya es alcanzable: antes
`audit()` borraba la fuente esperada cuando el filtro por fuente fallaba y la comparación era
verdadera por construcción (R4-D09). Sobre el puntaje base se aplican límites que fijan 🟡 en
ambos sentidos (60–84): ley por confirmar (R4b), evidencia de otro ordenamiento y precepto
derogado (R4c).

| Semáforo | Score | Lectura |
|---|---|---|
| 🟢 | ≥ 85 | Existencia y ubicación verificadas en el corpus local (cotejar contenido; ver "Alcance del 🟢") |
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
5. `tesis_parciales > 0` → **🟡** "N/T tesis con verificación parcial" (R4c, ronda 2): una tesis
   localizada con puntaje menor a 85 (p. ej. aislada, 72) deja traza `partial` y cuenta en el
   veredicto como una cita normativa parcial. `tesis_ok` cuenta solo las verificadas (antes
   contaba las parciales y un escrito con solo una tesis aislada salía 🟢).
6. `normativa_no_verificable > 0` → **🟡** — al menos una cita normativa tiene evidencia
   parcial o insuficiente.
7. `score_rag < 70` (o sin puntaje) → **🟡** — artículos con verificación insuficiente. No
   aplica si no se citó ningún artículo (`articulos_total == 0`, R4c): una dimensión sin citas
   no es una dimensión insuficiente.
8. sin artículos ni tesis → **🟡** "Sin citas detectadas: no hay normativa ni jurisprudencia
   que verificar" (R4c). Un 🟢 sería vacío; la extracción automática puede omitir un formato.
9. solo tesis, sin artículos → **🟡** "Jurisprudencia localizada; cotejo de sentido del rubro
   pendiente (R4d)". **Transitorio** (ver abajo).
10. en otro caso → **🟢**, con una razón que enuncia solo lo verificado (R4c, R4-D11):
   "Normativa y jurisprudencia verificadas" o "Normativa verificada; sin tesis citadas".

`veredicto_global` recibe `articulos_total` y `tesis_parciales` (nuevos, opcionales). El flujo
real (`audit()`) los pasa siempre; sin `articulos_total` —llamadas anteriores a R4c, como el
Gold Set v1— no se distingue "sin artículos" de "artículos con 0 puntos" y la regla 7 se aplica
como antes.

**Retención transitoria del 🟢 de "solo tesis" (R4c, ronda 2; condicionada por R4-D14).** Un
escrito que solo cita tesis, todas localizadas con rubro coincidente, ya no sale "Artículos con
verificación insuficiente (RAG: 0.0)", pero tampoco 🟢: su único sustento sería el cotejo del
rubro, que hoy es léxico y deja pasar un rubro con el sentido invertido (R4-D13, R4-D14). Queda
🟡 "Jurisprudencia localizada; cotejo de sentido del rubro pendiente (R4d)" mientras
`scoring_vvca.RETENER_VERDE_SOLO_TESIS` sea `True`. R4d la pondrá en `False` al corregir D13/D14
(lo registra `DEFECTOS_CONOCIDOS["R4-D14"]["condiciona"]`); entonces la razón será
"Jurisprudencia verificada; sin artículos citados". Con esta retención R4c no produce ningún 🟢
nuevo.

La distinción entre una cita refutada y una no verificable es crítica: "rubro discrepante"
o "fuente incorrecta" (peligroso) ≠ "no encontrada"
(corpus incompleto). Nunca se tratan igual.

El `score_rag` es descriptivo. El veredicto global sigue la peor traza: una sola cita roja
bloquea y una sola cita amarilla impide declarar el documento apto, aunque el promedio sea alto.

### Alcance del 🟢 (R4c)

Un 🟢 acredita **existencia y ubicación del precepto en el corpus local** (en tesis: el registro
existe en el corpus local de jurisprudencia y el rubro invocado coincide léxicamente). **No**
significa que el precepto diga lo que el escrito afirma ni que sea pertinente al caso (Capa 2).
El resultado lo dice en tres lugares: `alcance_verificacion` en cada referencia de
`retrieved_sources` y en `vvca_summary` (más `alcance_verificacion_tesis`), y el texto del
`disclaimer` 🟢 que se muestra al abogado ("Alcance del 🟢: existencia y ubicación del precepto
en el corpus local (en tesis, registro y rubro); no significa que lo citado diga lo que el
escrito afirma"). Cuando el veredicto es 🟢, la salida `--format telegram` añade "Alcance
(normas): …" si hay artículos y "Alcance (tesis): …" si hay tesis (ambas si hay ambos).

Si la cita designa una **unidad** del precepto (fracción, inciso, párrafo…), el 🟢 exige además
haber cotejado esa unidad en el texto (ver §4, "Unidad citada"): el encabezado del artículo no
basta.

## 4. Guards de resolución de artículos (anti-falso-veredicto)

**Extracción (R4b).** Cada artículo citado es una referencia propia, con su designación
completa:

- Sufijos y letras se conservan: `247 Ter`, `2o. Bis`, `4o.-A`, `29-A`, `32-B Quáter` (antes
  "247 Ter" se auditaba como el 247 y "4o.-A" como el 4o).
- Cabeza del precepto: "artículo(s)", "art(s).", "numeral(es)" y "precepto(s)" seguidos de
  número ("se vulnera el numeral 16 de la Carta Magna"). Tras otro número o un apartado
  ("artículo 9, numeral 2, del Reglamento"; "artículo 16, apartado A, numeral 3") "numeral"
  califica al mismo precepto y no abre otra referencia.
- Enumeraciones y rangos: `arts. 14, 16 y 19`, `467 a 471` y `155–157` producen una
  referencia por artículo (antes solo se auditaba el primero), también con ordinales
  (`1o. a 4o.` → 1o, 2o, 3o, 4o). En `artículo 471, 3 días` o `10 de junio` el número no es
  artículo.
- Enumeraciones con leyes intercaladas se leen por segmentos, cada uno con **su** ley:
  "los artículos 14 de la CPEUM y 42 del CFF"; "17 de la Ley de Amparo y 107
  constitucional"; "16 y 19 de la CPEUM, así como 167 del CNPP".
- Un punto y coma no corta la enumeración cuando lo sigue otro número con **su propia** ley
  ("los artículos 14 de la CPEUM; 42 del CFF"). Un número tras ";" sin ley ligada no es
  artículo ("; el plazo es de 16 días").
- **Nada desaparece en silencio.** Un rango de más de 20 artículos, con o sin ordinales
  (`1-25`, `1º-25º`, `1o.-25o.`, `1°-25°`), conserva sus extremos y deja una referencia
  `🟡 COBERTURA INCOMPLETA` ("rango de N artículos: solo se auditaron los extremos"); un
  número ligado a una ley que no se puede extraer con certeza ("…, al igual que el 42 del
  CFF"; "…; también el 42 del CFF") también queda como cobertura incompleta. Cuentan como no
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
   leyes que de artículos ("Los artículos 14 y 16, de la CPEUM y del CFF, respectivamente";
   también sin repetir la preposición: "…de la CPEUM y el CFF, respectivamente"); si el
   número no cuadra, o "respectivamente" acompaña a una sola ley, todo el grupo queda no
   identificado. Nunca se comparte la primera ley. Sin "respectivamente", "El artículo 16 de
   la CPEUM y el CFF establecen…" liga el 16 solo a la CPEUM.
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
  "constitucional" solo cuenta junto al precepto ("artículo 16 constitucional"). "Carta
  Magna" se trata igual que "la Constitución": es un genérico, no una denominación.
- Un genérico ligado al artículo ("de la ley", "del código", "de la Constitución", "de la
  Carta Magna", "del ordenamiento citado", "dicha ley, en su artículo") solo se resuelve si
  antes se nombra **un único** ordenamiento de ese tipo; si no hay ninguno o hay varios, la
  ley queda no identificada. Los ordenamientos concretos fuera del catálogo también cuentan
  como antecedentes: "La Ley de Amparo y la Ley General de Salud rigen. El artículo 5 de la
  ley…" es ambiguo (🟡), y si el único antecedente está fuera del catálogo el motivo lo dice.
  Un antecedente de otro párrafo deja la ley por confirmar.
- Un ordenamiento concreto que no está en el catálogo ("Código de Comercio", "Ley General de
  Salud", "ley fiscal", "Constitución local"), o uno de otra entidad ("Código Penal para el
  Estado de México", "Ley de Carrera Judicial del Estado de Jalisco"), deja la ley no
  identificada con el motivo "ordenamiento fuera del catálogo" y bloquea cualquier inferencia.
  Las claves estatales del catálogo exigen la entidad completa ("Código Penal para el Estado
  Libre y Soberano de Jalisco").

**Criterio del responsable (1-oct-2026).** El responsable jurídico confirmó el criterio B:
"de la Constitución" (y "Carta Magna", "Ley Fundamental", "Norma Suprema") sin la
denominación completa ni un antecedente inequívoco queda 🟡 hasta que el abogado confirme el
ordenamiento; **nunca** se asume la CPEUM de forma automática. Es un criterio jurídico
adoptado para este sistema, no un valor por defecto técnico: un escrito puede citar una
constitución local o extranjera y la auditoría no debe decidirlo por el abogado. Lo fija la
prueba `test_criterio_del_responsable_1oct2026_constitucion_sin_denominacion`
(`tests/test_vvca_nucleo.py`).

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
  extrajo con certeza. Auditar esos artículos por separado. `vvca_full.py` las lista en
  `cobertura_pendiente`, en `warnings` (paso `cobertura`) y en stderr, y el resumen del envío
  opcional a Telegram lo advierte (`capturar_rag.py --cobertura-pendiente N`). No se genera
  captura para lo no auditado: una captura sería una evidencia falsa.
- **Ley por confirmar** (R4b) → a lo sumo 🟡 (traza `partial`), aunque el fragmento
  coincida, y nunca 🔴: el cotejo se hizo contra una ley inferida de otro párrafo.
  `retrieved_sources` lleva `law_requires_confirmation`, y el pop-up de `vvca_full.py`
  muestra la página con la advertencia visible "LEY POR CONFIRMAR — <motivo>. La página
  acredita la ubicación del precepto en el candidato, no que el escrito cite ese
  ordenamiento" (campos `ley_por_confirmar` y `motivo_ley` del ítem).
- **Precepto derogado** (R4c, R4-D08) → `🟡 PRECEPTO DEROGADO` (traza `partial`), nunca 🟢.
  Se detecta **solo** en la primera línea con contenido que sigue al encabezado exacto del
  precepto citado, en la evidencia de la ley citada (se salta el ruido de página: cabeceras de
  la Cámara, "127 de 380", la denominación en mayúsculas). Ronda 2: cualquier fórmula
  **inequívoca**, con o sin paréntesis, punto dentro o fuera, en cualquier caja y número:
  "(Se deroga).", "(Se deroga.)", "Se deroga", "Se derogan.", "DEROGADO.", "Derogado",
  "(Derogada)", "(DEROGADO, P.O. 5 DE SEPTIEMBRE DE 2009)", seguida o no de la nota "Artículo
  derogado DOF …". Una fórmula de derogación junto al encabezado que **no** es inequívoca
  ("(Se deroga primer párrafo).", "Se derogan los artículos …") ya no se ignora:
  `🟡 POSIBLE DEROGACIÓN` (traza `partial`, puntaje 60–84; `derogacion_ambigua`). No cuentan
  una fracción derogada dentro del cuerpo (salvo que se cite esa fracción, ver "Unidad
  citada"), ni "Quedan derogadas las disposiciones…" ni el "(Se deroga)" de otro artículo del
  mismo fragmento. La alerta explica que el texto vigente no contiene
  norma y pide verificar si el escrito cita una versión anterior del precepto o un régimen
  transitorio aplicable. El puntaje se limita a 60–84 y sustituye las alertas de distancia
  (COTEJAR / ALERTA ALTA): el precepto sí se ubicó. `retrieved_sources` lleva
  `precepto_derogado`, y el pop-up de `vvca_full.py` muestra la página con la advertencia
  "PRECEPTO DEROGADO" (la página acredita la derogación, no el contenido que el escrito le
  atribuye), junto a la de "LEY POR CONFIRMAR" si también aplica.
  **Criterio por defecto, no decisión del responsable:** 🟡. El responsable puede endurecerlo
  (p. ej. 🔴 cuando el escrito no invoca un régimen transitorio); hoy un precepto derogado no
  bloquea por sí solo.
- **Unidad citada** (R4c, ronda 2) → si la cita designa fracción, inciso, párrafo, apartado,
  base o "in fine" ("artículo 31, fracción I, del CCF"; "artículo 16, primer párrafo";
  "artículo 1o., párrafo tercero"; "artículo 107, fracción V, inciso a)"), también antes del
  artículo ("párrafo tercero del artículo 1o."; "fracción II del artículo 31"; "inciso a) de
  la fracción III del artículo 107"; "último párrafo del artículo 16"), y con ordinales en
  palabra (primero…décimo primero, último, penúltimo) o número ("párrafo 2°", "2o.
  párrafo"), la extracción la guarda en `unidad_citada` y la
  auditoría la coteja en el cuerpo del precepto. Solo fracciones (romano al inicio de línea:
  "I.", "II.-") e incisos ("a)") se ubican en el texto, y solo si su marca aparece **una** vez
  (una fracción I repetida en dos apartados no es inequívoca). Resultado:
  - unidad derogada → `🟡 PRECEPTO DEROGADO` de **la unidad** ("la fracción I del artículo 31
    dice que se deroga (el resto del artículo no se declara derogado)"); `unidad_derogada`,
    `precepto_derogado` sigue `false`; puntaje 60–84, traza `partial`;
  - unidad no ubicada con certeza (fracción ausente o repetida; párrafo, apartado, base, "in
    fine", que no se pueden ubicar en el texto del PDF) → `🟡 UNIDAD CITADA NO COTEJADA` con
    el motivo (`unidad_no_cotejada`); tope 84 (nunca 🟢), sin piso;
  - unidad ubicada y vigente → el semáforo de siempre (`unidad_cotejada: true`).
  Una cita del artículo completo se coteja como antes. Consecuencia: toda cita de párrafo queda
  🟡 hasta que el cotejo de párrafos sea fiable (p. ej. "artículo 19, párrafo 2°"). Una unidad
  que precede al artículo solo se le asocia si la cadena termina pegada a la cabeza con
  "del"/"de la"/"de los": "el segundo párrafo de la sentencia … el artículo 16" o "la fracción
  II de la Ley de Amparo" no son unidades del artículo.
- **Evidencia incompleta** (R4c, ronda 2) → un fragmento con el encabezado exacto pero sin
  cuerpo suficiente ("…\nArtículo 64.-" al final del fragmento, o "Artículo 64.- Las") no
  autoriza 🟢. Se busca la continuación entre los candidatos del **mismo** precepto (misma
  fuente, misma etiqueta de artículo, `chunk_index` consecutivo, como la ingesta guarda los
  subfragmentos) y se coteja el cuerpo reunido (derogación y unidad incluidas;
  `fragmentos_continuacion` en la explicabilidad). Si no se localiza: `🟡 EVIDENCIA
  INCOMPLETA` (`evidencia_incompleta`), tope 84, sin piso.
  Ninguno de estos topes toca la rama de distancia alta sin metadata (R4-D10): su severidad no
  cambia.
- **Evidencia de otro ordenamiento** (R4c, R4-D09) → `🟡 EVIDENCIA DE OTRO ORDENAMIENTO`
  (traza `not_verifiable`): la fuente esperada nunca se borra. Si ChromaDB rechaza el filtro
  por fuente, la consulta sin filtro prefiere los fragmentos de la ley citada; si ninguno lo
  es, la evidencia es de otro ordenamiento y no acredita ni refuta la cita (puntaje con −15 y
  límite 60–84; nunca 🟢 ni 🔴). "Fuente correcta" solo aparece cuando la fuente coincide de
  verdad; si no, "Fuente distinta: se encontró en '…', se esperaba '…'". La derogación de un
  fragmento de otro ordenamiento no se atribuye a la cita. El pop-up "FUENTE NO COINCIDE" usa
  el semáforo de la cita (ya no un 🔴 fijo).
- **Tesis citada no encontrada** en el corpus local → `🟡 NO VERIFICABLE` (no confirmada
  falsa); cuenta en `amarillos`, no en `rojos`, coherente con el veredicto.
- **No encontrado con la fuente esperada** → 🔴 alerta crítica (posible alucinación).
  Pendiente de decisión del responsable (R4-D10, toca la Regla 4 de `CLAUDE.md`): R4c no
  cambió su severidad.

### Qué cambia para el abogado (R4c)

| Antes | Después |
|---|---|
| "Artículo 64.- (Se deroga)." salía 🟢 verificado | 🟡 PRECEPTO DEROGADO con la página y el aviso de versión anterior / régimen transitorio (también "DEROGADO.", "Derogado", "(Se deroga.)", "Se derogan.") |
| "(Se deroga primer párrafo)." junto al encabezado se ignoraba | 🟡 POSIBLE DEROGACIÓN |
| "artículo 31, fracción I, del CCF" salía 🟢 aunque la fracción I dice "(Se deroga)" | 🟡 PRECEPTO DEROGADO de la fracción I (el artículo no se declara derogado) |
| Una cita de fracción, inciso o párrafo se acreditaba con el encabezado del artículo | La unidad se coteja; si no se ubica con certeza, 🟡 UNIDAD CITADA NO COTEJADA |
| Un encabezado sin cuerpo podía salir 🟢 | Se reúne la continuación del mismo precepto o 🟡 EVIDENCIA INCOMPLETA |
| Una tesis aislada (72) contaba como "ok": solo tesis aislada → 🟢 | 🟡 "N/T tesis con verificación parcial" |
| Si el filtro por fuente fallaba, el artículo de otra ley salía 🟢 "Fuente correcta" | 🟡 EVIDENCIA DE OTRO ORDENAMIENTO ("Fuente distinta") o la evidencia de la ley citada |
| 🟢 "Normativa y jurisprudencia verificadas" sin tesis citadas | 🟢 "Normativa verificada; sin tesis citadas" |
| "SJF 0.0 🔴 (0/0 tesis ok)"; "RAG 0.0 🔴" con todas las normas no verificables | "SJF sin citas"; "RAG — 🟡 (N arts; N no verificables)" |
| Solo tesis verificadas: 🟡 "Artículos con verificación insuficiente (RAG: 0.0)" | 🟡 "Jurisprudencia localizada; cotejo de sentido del rubro pendiente (R4d)" (transitorio) |
| Sin ninguna cita: 🟡 "Artículos con verificación insuficiente (RAG: 0.0)" | 🟡 "Sin citas detectadas: no hay normativa ni jurisprudencia que verificar" |
| El 🟢 no decía qué acreditaba | "Alcance del 🟢: existencia y ubicación del precepto en el corpus local; no significa que lo citado diga lo que el escrito afirma" |

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
