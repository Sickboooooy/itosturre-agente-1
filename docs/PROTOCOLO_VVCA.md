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
derogado (R4c). Desde D10 también la distancia alta sin metadata: una cita normativa con
evidencia nunca queda bajo 60 por la distancia; su único 🔴 es la **inexistencia acreditada**
(§4, criterio del responsable del 2-oct-2026).

**Verde determinista (criterio del responsable, 3-oct-2026: opción A).** Con **evidencia
completa** una cita normativa es 🟢 por regla determinista: `build_vvca` fija el puntaje en
`max(puntaje por similitud, 85)` y la distancia coseno deja de decidir entre 🟢 y 🟡 en esa ruta.
La consulta que construye `audit()` es corta ("Artículo 109 cnpp") y su distancia al fragmento
que trae el encabezado exacto no mide la existencia del precepto: antes, con evidencia completa,
salían 🟡 solo por distancia los 51 artículos de la CPEUM de una muestra de 60 y 50 de 60 del
CNPP. Evidencia completa = **todas** a la vez:

- `metadata_hit` de `audit()`: candidato por metadata `source+article`, encabezado exacto en el
  fragmento seleccionado, fuente recuperada igual a la esperada y (ronda 2) etiqueta `article`
  del fragmento ELEGIDO entre los candidatos; si la consulta exacta falla o vuelve vacía, la
  evidencia del respaldo semántico ya no hereda la metadata;
- (ronda 2) encabezado **auténtico**: prefijo con "A" mayúscula ("Artículo", "ARTÍCULO",
  "Art.") y cierre no seguido de "," ni ";". "artículo 41." que el PDF dejó al inicio de una
  línea es una remisión (el chunker la toma por encabezado y etiqueta el fragmento con el 41) y
  "Artículo 2o., fracción I, inciso H." es una cita: solo con ellas, tope 84 y `🟡 COTEJAR …
  solo se ubicó una remisión`. Entre varios candidatos se prefieren los auténticos, y el cuerpo,
  la derogación y la unidad citada se cotejan desde esa misma ocurrencia;
- (ronda 2) **ubicación en el cuerpo** acreditada (`itosturre/audit/ubicacion.py`, con la
  frontera TRANSITORIOS y sus controles de credibilidad de la prueba de inexistencia,
  `frontera_creible`): (i) con dos o más encabezados auténticos distintos, solo si la frontera
  es creíble y exactamente uno queda antes de ella (ese se elige); (ii) con uno solo tras una
  frontera creíble, no (transitorio o decreto); (iii) con uno solo y frontera no creíble o
  ausente, sí. El mismo pasaje repetido en fragmentos consecutivos de la misma página cuenta
  una vez. Si no se acredita: tope 84 y `🟡 UBICACIÓN NO ACREDITADA` con el motivo;
- ley identificada (`source_file`) y **no** por confirmar (`law_requires_confirmation`);
- precepto no derogado, sin unidad derogada ni derogación ambigua;
- sin unidad citada no cotejada (`unidad_no_cotejada`) ni evidencia incompleta;
- distancia ≤ `COSINE_THRESHOLD` (0.25). **Salvaguarda de anomalía:** con metadata y encabezado
  pero distancia mayor que el umbral se conserva el comportamiento anterior (piso 70, `🟡
  COTEJAR`). En el corpus real las distancias con evidencia completa van de 0.116 a 0.193.

El puntaje por similitud queda como dato informativo (`explicabilidad.score_similitud`, junto a
`explicabilidad.verde_determinista: true`), y `V_verificacion` lo dice: "Verificación
determinista: artículo localizado por metadata (ley y artículo) con su encabezado exacto en la
ley citada; existencia y ubicación en la versión indexada, no vigencia ni contenido. Distancia
informativa: dist=0.170 (≤ umbral 0.25; puntaje por similitud 83)". Todos los topes (ley por
confirmar, otra fuente, derogación, unidad no cotejada, evidencia incompleta, sin ley) se
aplican después y siguen dejando 🟡; la traza es `verified` como antes (metadata y puntaje ≥ 85).
El 🟢 de una norma significa lo que dice su alcance (`ALCANCE_NORMATIVA`): el precepto existe y
está ubicado en la versión indexada; **no** que esté vigente ni que diga lo que afirma el escrito.
**Fuera de esa ruta** (búsqueda semántica sin metadata) la distancia sigue decidiendo como antes.
`vvca_score` y `vvca_semaforo` no cambian (los usa `scripts/evaluate_gold_set.py`).

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
   el invocado o con el sentido invertido (alucinación o cita maliciosa). USO PROCESAL
   PROHIBIDO. *Criterio (R4d):* cotejo determinista del rubro (§3 bis): traslape de palabras
   normalizado **< 40 %** o polaridad distinta ("NO ES…", "IMPROCEDENTE"…). El umbral del
   40 % no cambió; es el del 🔴 bloqueante — el más fuerte del sistema; ajustarlo con cuidado.
2. `tesis_superadas > 0` → **🔴 bloqueante** — la cita existe, pero el criterio ya no
   está vigente.
3. `normativa_refutada > 0` → **🔴 bloqueante** — al menos una cita normativa quedó
   refutada. El promedio no puede ocultarla. Desde D10 una cita normativa solo queda refutada
   con prueba positiva de inexistencia en el cuerpo de la ley indexada (§4); "no localizada"
   sin prueba es 🟡.
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
9. solo tesis, sin artículos → **🟡** "Jurisprudencia localizada; 🟢 de solo tesis retenido
   (transitorio) hasta validar el cotejo del rubro con un corpus de tesis mayor". **Transitorio**
   (ver abajo).
10. en otro caso → **🟢**, con una razón que enuncia solo lo verificado (R4c, R4-D11):
   "Normativa y jurisprudencia verificadas" o "Normativa verificada; sin tesis citadas".

`veredicto_global` recibe `articulos_total` y `tesis_parciales` (nuevos, opcionales). El flujo
real (`audit()`) los pasa siempre; sin `articulos_total` —llamadas anteriores a R4c, como el
Gold Set v1— no se distingue "sin artículos" de "artículos con 0 puntos" y la regla 7 se aplica
como antes.

**Retención transitoria del 🟢 de "solo tesis" (R4c, ronda 2; se mantiene tras R4d).** R4c
retuvo como 🟡 el 🟢 de un escrito que solo cita tesis, porque su único sustento era un cotejo
léxico del rubro que dejaba pasar el sentido invertido (R4-D13, R4-D14). R4d corrigió ambos
(§3 bis), pero por adjudicación del 2-oct-2026 (Codex y coordinador) la retención **se
mantiene**: `scoring_vvca.RETENER_VERDE_SOLO_TESIS = True` hasta validar el cotejo con un corpus
de tesis mayor que las 10 actuales (lo registra `DEFECTOS_CONOCIDOS["R4-D14"]["condiciona"]`).
Mientras tanto, un escrito con solo tesis, aunque cada rubro coincida literalmente, queda 🟡
"Jurisprudencia localizada; 🟢 de solo tesis retenido (transitorio) hasta validar el cotejo del
rubro con un corpus de tesis mayor". Con la bandera en `False` la razón sería "Jurisprudencia
verificada; sin artículos citados". Un escrito con artículos verificados y tesis con rubro
literal sí puede ser 🟢.

La distinción entre una cita refutada y una no verificable es crítica: "rubro discrepante"
o "fuente incorrecta" (peligroso) ≠ "no encontrada"
(corpus incompleto). Nunca se tratan igual.

El `score_rag` es descriptivo. El veredicto global sigue la peor traza: una sola cita roja
bloquea y una sola cita amarilla impide declarar el documento apto, aunque el promedio sea alto.

### Alcance del 🟢 (R4c)

Un 🟢 acredita **existencia y ubicación del precepto en el corpus local** (en tesis: el registro
existe en el corpus local de jurisprudencia y el rubro invocado coincide literalmente, una vez
normalizado; R4d). **No**
significa que el precepto diga lo que el escrito afirma ni que sea pertinente al caso (Capa 2).
El resultado lo dice en tres lugares: `alcance_verificacion` en cada referencia de
`retrieved_sources` y en `vvca_summary` (más `alcance_verificacion_tesis`), y el texto del
`disclaimer` 🟢 que se muestra al abogado ("Alcance del 🟢: existencia y ubicación del precepto
en el corpus local (en tesis, registro y rubro literal); no significa que lo citado diga lo que
el escrito afirma"). Si alguna tesis localizada quedó sin cotejo del rubro (no se transcribió o
la fuente no lo registra), `alcance_verificacion_tesis` lo dice ("N tesis sin cotejo del rubro:
solo existencia del registro") y el `alcance_verificacion` de esa tesis es
`ALCANCE_JURISPRUDENCIA_SIN_RUBRO`. Cuando el veredicto es 🟢, la salida `--format telegram`
añade "Alcance (normas): …" si hay artículos y "Alcance (tesis): …" si hay tesis (ambas si hay
ambos).

Si la cita designa una **unidad** del precepto (fracción, inciso, párrafo…), el 🟢 exige además
haber cotejado esa unidad en el texto (ver §4, "Unidad citada"): el encabezado del artículo no
basta.

## 3 bis. Jurisprudencia determinista (R4d)

Funciones puras en `itosturre/audit/jurisprudence.py`; `OpenNotebook.build_vvca_tesis` las
aplica a cada tesis localizada en el corpus local de jurisprudencia. Ronda 2 (rechazo de Codex
y del coordinador): se cerraron cuatro falsos verdes reproducidos con el rubro real de 2006224
(negación antes del rubro, marca de supresión, identificadores, rubro de otra tesis) y la
vigencia en conflicto; ver "Qué cambia para el abogado (R4d)".

**Detección del registro (R4-D07).** En cualquier caja: "Registro digital: N", "REGISTRO
DIGITAL: N", "Registro Digital N" (con o sin dos puntos), "registro IUS N", y, solo con contexto
de tesis en el párrafo (tesis, jurisprudencia, rubro, título y subtítulo, Semanario, Gaceta,
época o una clave "P./J.", "J/7", "(10a.)"), "Registro: N", "Reg. N", "registro número N" o "IUS
N" (`OpenNotebook.REGISTRO_TESIS_RE` y `_es_registro_de_tesis`). El número tiene 6 o 7 dígitos
(los registros digitales del SJF): no lo son un número de 8 dígitos ("Registro: 20261002 de la
oficialía", forma de fecha o folio) ni el de un expediente "N/AAAA" ("Reg. 2006224/2026").
Antes "REGISTRO DIGITAL: …" y "Registro Digital: …" no se detectaban y la tesis desaparecía de la
auditoría. En plural o en enumeración ("registros digitales N y M", "N / M", "N/M", "N y/o M",
"N o M") cada número es una tesis; como no se puede saber qué rubro corresponde a cada una,
ninguna recibe rubro (🟡 sin cotejo del rubro). Un número de registro pegado a la enumeración
con un conector no reconocido ("N así como M") no se omite: queda `🟡 COBERTURA INCOMPLETA`
(traza `not_verifiable`, método `cobertura_extraccion`, que `vvca_full.py` lista en
`cobertura_pendiente`).

**Rubro invocado** (`extraer_rubro_invocado`). Se busca en el párrafo del registro, en el texto
que lo precede (hasta 1 500 caracteres, sin cruzar el registro anterior: antes eran 400
caracteres que podían contener el rubro de otra tesis):

1. tras el último marcador explícito ("de rubro:", "cuyo rubro es", "de título y subtítulo:",
   "lleva por título", "bajo el epígrafe", "intitulada"; "RUBRO" en mayúsculas solo con dos
   puntos), el primer texto entre comillas o en negritas (en cualquier caja) o la primera corrida
   de mayúsculas;
2. sin marcador, el texto entre comillas o negritas en mayúsculas, o la corrida de mayúsculas
   (tres o más palabras, quince o más letras) más cercana al registro, sin la clave ni la época
   ("P./J. 3/2019", "(10a.)"). No cuentan la línea de un encabezado ("III. …", "## …") ni un
   texto hecho solo de palabras de órganos, publicaciones o encabezados (lista cerrada:
   "SUPREMA CORTE DE JUSTICIA DE LA NACIÓN", "PRIMER TRIBUNAL COLEGIADO EN MATERIA PENAL DEL
   TERCER CIRCUITO", "JURISPRUDENCIA APLICABLE AL CASO CONCRETO").

Entre el marcador y el rubro solo puede mediar una **fórmula introductoria** de la lista cerrada
`FORMULAS_INTRODUCTORIAS` ("y texto", "y texto siguientes", "es", "que dice", "que a la letra
dice", "del tenor siguiente", "literal"…). Cualquier otro texto omitido ("de rubro: no es cierto
que «…»") queda en `texto_omitido` e impide "coincide" (🟡). Si entre el rubro y el registro hay
**otra mención de tesis**, jurisprudencia, criterio, precedente o ejecutoria que no sea la
etiqueta de la clave ("tesis 2a./J. 58/2010", "Tesis: P./J. 20/2014"), la del tipo ("Tipo:
Jurisprudencia") ni vaya seguida solo de calificativos ("jurisprudencia obligatoria"), o el
párrafo invoca varios rubros ("de rubros «A» y «B»"), la asociación es incierta
(`asociacion_incierta`): 🟡 `rubro_no_asociado`, nunca 🟢 ni 🔴. Consecuencia: en el formato de
bloque (rubro, texto de la tesis, registro) el texto suele mencionar "tesis" o "criterio" y la
tesis queda 🟡.

Un marcador **pegado a la derecha** del registro ("registro digital 164618, de rubro y texto:
«…»") prevalece (`extraer_rubro_posterior`, con la misma regla de fórmulas), y lo consumido ya
no es contexto de la tesis siguiente. Un texto entre comillas en minúsculas sin marcador **no**
se toma como rubro (suele citar el texto de la tesis o de una norma).

**Cotejo** (`cotejar_rubro`), en este orden; la comparación normaliza (`normalizar_rubro`: NFKD
sin acentos —NFD más la descomposición de compatibilidad, para que "1º" sea "1o"—, casefold,
sin puntuación **no numérica**, espacios colapsados; Regla 1 de `CLAUDE.md`). El separador que
toca un dígito se conserva: "REGLA 1.4.14." y "1/4/14." no son iguales, ni "69-B" y "69 B". Las
alertas y el reporte muestran siempre el rubro **original**, con acentos:

| Resultado (`cotejo_rubro`) | Condición | Semáforo de la tesis |
|---|---|---|
| `rubro_no_asociado` | asociación incierta con el registro (arriba) | 🟡 a lo sumo 84, "RUBRO NO ASOCIADO CON CERTEZA"; solo acredita el registro |
| `parcial` | marca de supresión ("…", "...", "[…]", "(…)", o la ventana recortada) y lo transcrito aparece en el real en orden y solo con huecos donde está la marca ("ES COMPUTABLE…" debe ser el inicio del real). Con marca **nunca** hay "coincide", aunque lo transcrito sea todo el rubro | 🟡 a lo sumo 84, "RUBRO PARCIAL" |
| `coincide` | igualdad normalizada, sin marca de supresión ni texto omitido tras el marcador | 95 jurisprudencia 🟢 / 72 aislada 🟡 |
| `discrepante` | traslape de palabras normalizado < 40 % (sobre el texto con menos palabras; las palabras cortas cuentan, salvo una lista cerrada de palabras vacías: artículos, preposiciones, conjunciones) | 🔴 0, bloqueante |
| `invertido` | traslape ≥ 40 % y polaridad distinta (lista cerrada, abajo) | 🔴 0, bloqueante ("SENTIDO INVERTIDO") |
| `no_literal` | cualquier otra diferencia; también la igualdad con texto omitido tras el marcador | 🟡 a lo sumo 84, "RUBRO NO COINCIDE LITERALMENTE" |
| `sin_rubro_invocado` | el escrito no transcribe un rubro identificable | 🟡 a lo sumo 84: la tesis solo acredita la existencia del registro |
| `sin_rubro_fuente` | la fuente local no registra el rubro | 🟡 a lo sumo 84 |

Ningún heurístico de traslape concede 🟢: solo la igualdad literal normalizada. Si el rubro se
tomó sin marcador (comillas o mayúsculas) y su traslape es < 40 %, antes del 🔴 se mira el
párrafo de la cita: si comparte 40 % o más de las palabras del real, el texto tomado como rubro
pudo no serlo y la tesis queda 🟡 `no_literal`.

**Polaridad (lista cerrada; ampliarla es decisión del responsable).** Hay inversión si difiere:

- el total de negaciones: *no, ni, sin, nunca, jamás, tampoco, ningún, ninguno, ninguna, nadie,
  nada* ("NO … NI …" y "NO … NO …" tienen la misma polaridad);
- por par, la forma negativa de un antónimo por prefijo: *improcedente/improcedencia*
  (procedente), *ilegal/ilegalidad* (legal), *inconstitucional/inconstitucionalidad*
  (constitucional), *inaplicable* (aplicable), *inválido/invalidez* (válido), *ilícito/
  ilicitud* (lícito), *incompetente/incompetencia* (competente), *infundado* (fundado),
  *inoperante* (operante), *ineficaz* (eficaz), *inexistente/inexistencia* (existente),
  *imprescriptible* (prescriptible), *inadmisible* (admisible), *injustificado*
  (justificado), *innecesario* (necesario), *inexigible* (exigible), *insuficiente*
  (suficiente), *inimputable* (imputable), con sus plurales;
- en un par simétrico mencionado por ambos rubros, el lado usado: *conceder/otorgar* ↔
  *negar/denegar*, *oportuno* ↔ *extemporáneo*, *permitir* ↔ *prohibir*, *obligatorio* ↔
  *optativo/potestativo*.

Consecuencia deliberada: un tramo del rubro transcrito **sin** marca de supresión que omite una
negación del real se trata como sentido invertido (🔴); para citar parte de un rubro hay que
marcar la supresión con "…" (🟡 RUBRO PARCIAL). Y un antónimo fuera de la lista ("INCOMPUTABLE")
no se detecta como inversión, pero tampoco es 🟢 (queda 🟡 no literal).

**Vigencia (criterio por defecto, no decisión del responsable).** `normalizar_vigencia` lee
**todos** los campos de vigencia del corpus (`estado_vigencia`, `vigencia`). `estado_vigencia`
solo vale "vigente", "superada", "interrumpida" o "sustituida" si el corpus o el scraper lo
registraron. Una pérdida registrada en **cualquier** campo prevalece sobre "no consultada" o un
valor desconocido y bloquea como antes (regla 2); también cuenta como pérdida un valor cuya
primera palabra lo es ("superada por contradicción"). Dos campos con dato y valores distintos son
un conflicto (`vigencia_en_conflicto`): si alguno es pérdida, bloquea; si no, el estado es
`en_conflicto` (🟡, puntaje a lo sumo 84, alerta "🟡 VIGENCIA EN CONFLICTO"). Sin dato vale
`no_consultada` (antes se asumía "vigente") y un valor desconocido, `no_reconocida` (se conserva
el original en `vigencia_registrada`). Ninguno de los dos cambia el semáforo: la auditoría añade
un **aviso** informativo ("ℹ️ VIGENCIA NO CONSULTADA" / "ℹ️ VIGENCIA NO RECONOCIDA") en
`avisos` (con `avisos_count`), no en `alerts`: `alerts_count` conserva su significado anterior.
`scripts/promover_tesis.py` ya no escribe "vigente" por defecto al promover tesis del scraper.

**Alertas por tesis localizada** (antes solo la traza decía la discrepancia): "🔴 RUBRO
DISCREPANTE — SENTIDO INVERTIDO", "🔴 RUBRO DISCREPANTE", "🟡 RUBRO PARCIAL", "🟡 RUBRO NO
COINCIDE LITERALMENTE", "🟡 RUBRO NO ASOCIADO CON CERTEZA", "🟡 SIN RUBRO INVOCADO", "🟡 RUBRO NO
DISPONIBLE", "🟡 VIGENCIA EN CONFLICTO", cada una con el rubro invocado y el real originales.
La salida `--format telegram` muestra todas las alertas completas que quepan en el mensaje (si
no, "… y N alerta(s) más" remite al JSON) y agrupa los avisos por tipo con todos sus registros.
Campos añadidos: `avisos`, `avisos_count`; `vvca.cotejo_rubro`; en la explicabilidad,
`cotejo_rubro`, `motivo_cotejo`, `rubro_invocado_metodo`, `rubro_truncado`, `polaridad`,
`texto_omitido`, `asociacion_incierta`, `vigencia_registrada`, `vigencia_campos` y
`vigencia_en_conflicto` (`rubro_real` y `rubro_invocado` ahora completos; `rubro_invocado` es el
rubro extraído, no el contexto); en `vvca_summary`, `tesis_por_cotejo_rubro` y
`tesis_por_vigencia`. La memoria contextual (`itosturre/memoria/puente.py`) solo registra una
cita bloqueada por vigencia si es superada, interrumpida o sustituida, y distingue el rubro con
el sentido invertido.

### Qué cambia para el abogado (R4d)

| Antes | Después |
|---|---|
| "REGISTRO DIGITAL: …" o "Registro Digital: …": la tesis no se auditaba | Se audita como cualquier otra (también "registro IUS"; "IUS", "Reg." o "Registro" solos, con contexto de tesis) |
| "Registro: 20261002 de la oficialía" se auditaba como tesis | No es un registro (8 dígitos, sin contexto de tesis); tampoco "Reg. 2006224/2026" |
| "registros digitales N y M", "N / M": solo se detectaba el primero (o ninguno) | Una tesis por número; un conector no reconocido deja 🟡 COBERTURA INCOMPLETA |
| El mismo rubro sin acentos: 🔴 discrepante (falso rojo) | 🟢 si coincide literalmente |
| Rubro con el sentido invertido ("NO ES COMPUTABLE"): 🟢 | 🔴 RUBRO DISCREPANTE — SENTIDO INVERTIDO |
| "de rubro: no es cierto que «…»" con el rubro exacto: 🟢 | 🟡 RUBRO NO COINCIDE LITERALMENTE (texto omitido) |
| Rubro completo seguido de "…": 🟢 | 🟡 RUBRO PARCIAL |
| "1.4.14." en lugar de "1/4/14.", "69 B" en lugar de "69-B": 🟢 | 🟡 RUBRO NO COINCIDE LITERALMENTE |
| Rubro de otra tesis antes del registro ("…; se invoca otra tesis con registro …"): 🟢 | 🟡 RUBRO NO ASOCIADO CON CERTEZA |
| Rubro truncado o parafraseado con 40 % de palabras comunes: 🟢 | 🟡 RUBRO PARCIAL / RUBRO NO COINCIDE LITERALMENTE |
| Registro sin rubro transcrito: 🟢 o 🔴 según las palabras del párrafo | 🟡 SIN RUBRO INVOCADO (solo acredita el registro) |
| Encabezado u órgano en mayúsculas junto al registro: 🔴 falso | 🟡 sin rubro invocado |
| Segunda tesis sin rubro tras otra con rubro: heredaba el contexto (🔴 falso) | 🟡 sin rubro invocado |
| Vigencia sin dato: "vigente" | "no_consultada" con aviso ℹ️ aparte (sin cambiar el semáforo) |
| `estado_vigencia: no_consultada` y `vigencia: superada`: no bloqueaba | 🔴 vigencia perdida (cualquier campo) |
| Solo tesis con rubro literal: 🟡 transitorio (R4c) | Sigue 🟡 transitorio (retención mantenida, ver §3) |

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
   es: los artículos bajo ese encabezado quedan por confirmar. Desde D10 (ronda 2), si la
   oración de la mención más cercana nombra **más de un ordenamiento** ("La Ley de Amparo
   regula la jurisprudencia y la CPEUM fija sus bases. El artículo 217…"), el contexto previo
   es ambiguo: la ley queda **no identificada** (🟡, "el contexto previo es ambiguo: la oración
   anterior nombra varios ordenamientos"), no la última mención. Ninguna prueba de la
   caracterización R4b cambió con esto.

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
- Una sigla que el catálogo no reconoce, pegada al artículo ("el artículo 248 de la
  LISSSTE"), deja la ley no identificada con el motivo "sigla fuera del catálogo" (🟡): puede
  ser una ley no indexada o una abreviatura distinta de una ley del corpus. Antes heredaba por
  contexto previo la ley nombrada antes y daba un falso 🟢 (11-oct-2026). Si el texto define
  la sigla antes de usarla ("Ley del ISSSTE (LISSSTE)"), la cita toma esa ley.

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
  pero queda en 🟡 y nunca acredita por sí sola el precepto citado. Con metadata, encabezado
  exacto y el resto de la evidencia completa, la cita es 🟢 determinista (§2).
- **Ordinales (3-oct-2026)** → el indicador ordinal masculino no cambia el artículo: "1" ≡
  "1o" ≡ "1º" ≡ "1°" al comparar designaciones (candidatos por metadata, encabezado exacto,
  cuerpo del precepto, variantes con sufijo; la prueba de inexistencia ya era tolerante). El
  chunker etiqueta "Artículo 1o." como `1o`, "Artículo 1º" como `1º` y "Artículo 1." o
  "Artículo 1°" como `1`; `_article_candidates` pide todas esas etiquetas. El número se compara
  completo ("1" nunca es "10", "11" ni "1o.-A") y los sufijos se siguen exigiendo exactos
  ("4o.-A" no es "4"; "4-A" sí es "4o.-A"). El femenino ("1a", "1ª") no se usa en la numeración
  de artículos y solo coincide consigo mismo. Antes "CPEUM Art. 1." o "CFF Art. 9." no tenían
  candidatos por metadata y caían a la búsqueda semántica, que mostraba la evidencia de otro
  artículo (CFF 9 → "Artículo 91-C. (Se deroga)"). Sin metadata (ruta semántica), un
  encabezado que solo coincide por la equivalencia ubica el precepto pero no da 🟢: tope 84 y
  `🟡 COTEJAR … con otra grafía del ordinal` (`explicabilidad.ordinal_equivalente`), para no
  ampliar el 🟢 de esa ruta. Nunca un 🔴: "CPEUM Art. 1." frente a encabezados "1o." no
  acredita inexistencia. Ronda 2: la equivalencia se activa explícitamente
  (`patron_articulo(..., ordinal_equivalente=True)`); el comportamiento por defecto de
  `patron_articulo` y `patron_variante_con_sufijo` sigue siendo la comparación literal. Un
  sufijo partido en la línea siguiente ("Artículo 1o.\nBis.-", "Artículo 1o.\n-A.-") impide el
  encabezado del número base (solo un sufijo latino o "-Letra" con su cierre; una letra suelta
  como "Artículo 26.\nA. El Estado…" o "Artículo 37.\nA) Ningún…" sigue siendo el encabezado del
  26 o del 37). En la extracción, "°" seguido de un sufijo es el ordinal y se conserva con él:
  "CFF Art. 4°-A." → `4°-A` (antes `4`, que con la equivalencia habría acreditado el art. 4o.) y
  "artículo 1°. Bis del CFF" → `1°. Bis` con su ley (antes `1` sin ley).
- **Primera aparición** → si varios fragmentos de la **misma fuente** traen el encabezado
  exacto, se prefieren los auténticos (ronda 2) y, entre ellos, el de menor `chunk_index`, no el
  de menor distancia; la frontera del cuerpo (§2) decide si esa ubicación se acredita. Sin
  `chunk_index` entero o con fuentes distintas, decide el ranking.
  Corrige ubicaciones en transitorios o decretos: "Código Civil Federal Art. 1." salía 🟢 con
  "Artículo 1.- Se reforma el artículo 17 del Código Civil para el Distrito Federal…" (pág. 335)
  y ahora con el art. 1o. del cuerpo (pág. 1); "CFF Art. 21." con el texto del art. 21
  reproducido en una aclaración de un decreto de reforma, tras los transitorios (pág. 320), y
  ahora pág. 33; "CPEUM Art. 4o." con la línea "artículo 4o.; y se adicionan…" (pág. 200) y
  ahora pág. 12.
- **Tratados internacionales (criterio del responsable, 4-oct-2026, opción A)** → el
  encabezado "Artículo N" / "ARTÍCULO N" / "Artículo Nº" **solo al final de su línea**, sin
  punto ni guion, es auténtico **únicamente** en las fuentes que el catálogo registra como
  tratado internacional (`OpenNotebook.TRATADOS_INTERNACIONALES`: CADH, CDN y PIDCP; nunca por
  el nombre del archivo). Las leyes nacionales siguen exigiendo el cierre (las líneas
  "Artículo N" sin cierre del Código Civil de Jalisco no son encabezados). Es la misma
  definición que ya usaba la ingesta (`evidence._fin_de_linea_autentico`: "A" mayúscula,
  prefijo y número en la misma línea, sin sufijo en la línea siguiente y la línea siguiente sin
  continuar una oración), activada con `fin_de_linea=True` según la fuente esperada en la
  selección de evidencia y el encabezado auténtico, la ubicación en el cuerpo (los tratados no
  tienen frontera TRANSITORIOS: dos encabezados distintos son ubicación ambigua y, desde la
  ronda 2, uno solo se admite —regla iii— únicamente si encaja en la secuencia de encabezados de
  la fuente: el anterior es el N−1 y el siguiente el N+1 cuando existen; si no, `🟡 UBICACIÓN NO
  ACREDITADA`), el cuerpo del precepto (empieza tras el encabezado y tras la línea de título de
  la CADH —"Obligación de Respetar los Derechos", también con una línea en blanco antes—, que no
  cuenta como cuerpo; acaba en el siguiente encabezado o, desde la ronda 2, en cualquier línea
  candidata con "A" mayúscula y número, también partida "Artículo⏎9" aunque no se autentique;
  la continuación se une sin su solapamiento comprobado) con el cotejo de la unidad, y la
  existencia de D10 (sin frontera, D10 se abstiene: un artículo inexistente de un tratado queda
  🟡, nunca 🔴). Un título solo nunca completa la evidencia (ronda 2,
  `cuerpo_suficiente_tratado`: la primera línea sin puntuación final se separa de forma
  conservadora como posible título y el resto debe bastar; `_es_titulo` no es la única
  salvaguarda). **La ingesta usa el mismo registro (ronda 2):** `fragmentar(...,
  fin_de_linea=...)` solo corta en "Artículo N" sin cierre en un PDF registrado como tratado; en
  las leyes nacionales el cierre es obligatorio (el Código Civil de Jalisco ya no corta en las
  líneas "Artículo N" de su Declaratoria; las fuentes indexadas no cambian sin re-ingesta).
  Con metadata y evidencia completa la cita es 🟢 determinista (`explicabilidad`
  `encabezado_fin_de_linea: true`, informativo); **sin metadata** (ruta semántica) el
  encabezado sin cierre ubica pero no da 🟢 (tope 84, `🟡 COTEJAR … encabezado sin cierre`),
  como la equivalencia ordinal. Para añadir un tratado: indexarlo, añadir sus denominaciones a
  `LAW_SOURCE_MAP`, su archivo a `TRATADOS_INTERNACIONALES` (una prueba exige que esté en el
  catálogo) y medir antes→después todos sus artículos.
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
  completa eliminaría esta limitación; R4b no re-ingesta.) Desde D10, si el cuerpo de la ley
  acredita que el precepto no existe, es 🔴 (ver "Artículo no localizado" abajo).
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
  Una cita del artículo completo se coteja como antes. Consecuencia: toda cita de párrafo **por
  posición** queda 🟡 hasta que el cotejo de párrafos sea fiable (p. ej. "artículo 19, párrafo
  2°", "párrafo segundo"). **Párrafo numerado (4-oct-2026):** "artículo 8.1", "artículo 8º.1",
  "artículo 8, numeral 1", "artículo 8, párrafo 1" (número sin indicador ordinal), "8.1 y
  8.2", "párrafos 1 y 2", "numerales 1, 2 y 3" y "los párrafos 1 y 2 del artículo 8" son el
  artículo 8 con la unidad `parrafo_numerado` (`describir_unidad`: "párrafo numerado 1"); con
  "8.2, inciso h)" también el inciso dentro del párrafo. **Ronda 2 (adjudicado): el cotejo
  POSITIVO del párrafo numerado solo en los tratados internacionales registrados**, también en
  cualquier llamada que no lo active (`cotejar_unidad(..., parrafos_numerados=False)` por
  omisión); en una ley nacional "párrafo 1", "numeral 1" o "N.M" quedan como antes, `🟡 UNIDAD
  CITADA NO COTEJADA` ("párrafo 1" suele ser el primer párrafo por posición: en el corpus real
  "artículo 20-Ter, párrafo 1, del CFF" salía 🟢 casando la línea "1." de una lista). En un
  tratado se ubica la línea que empieza con
  "1." (seguido de un blanco o del fin de línea; no "1.e.", "1.1" ni "2016."), solo si aparece
  **una** vez antes de cualquier línea de notas ("Nota", "Notas explicativas"), si las marcas
  del cuerpo son exactamente 1, 2, 3… (sin saltos ni repeticiones; desde la ronda 2 la línea
  repetida por el solapamiento de los subfragmentos solo se descuenta si el solapamiento está
  COMPROBADO: la continuación consecutiva empieza repitiendo exactamente el final de lo reunido)
  y si antes del "1." no hay fracciones ni incisos (una lista "1. … 2. …" dentro de una
  fracción no es la numeración de los párrafos). Si la línea no se
  ubica, `🟡 UNIDAD CITADA NO COTEJADA` (nunca 🟢 del artículo completo). **Listas (ronda 2,
  falla cerrada):** "incisos c), d) y f)", "incisos a, b y c", "fracción I y II", "fracciones
  I, II y IV", "apartados A y B", "párrafos primero y segundo" y "los incisos a) y b) de la
  fracción III del artículo 107" se extraen completas, y el 🟢 exige que TODAS las unidades se
  coteje(n) ("8.2, incisos a) y z)" → 🟡 porque z) no existe). Lo que entre las unidades leídas
  y la ley ligada parezca una unidad no extraída ("apartado A y B", "inciso a) y z") deja la
  cita como `🟡 COBERTURA INCOMPLETA`, nunca auditada sin ella. **Falla cerrada:**
  "N.M" nunca se reduce en silencio a "N": "artículo 8. 1" (punto con blancos), "8.1.2" u
  "8.100" quedan como `🟡 COBERTURA INCOMPLETA`; en "artículo 8, párrafo 1, y 25" el 25 no se
  absorbe como párrafo (solo la palabra en plural admite una lista). Medición del 4-oct-2026:
  ninguna de las 49 fuentes del índice usa designaciones de artículo con punto ("Artículo 1.1",
  "ARTÍCULO 2.15"; las "1.1." de la RMF son reglas, no artículos), así que "N.M" tras la cabeza
  es siempre artículo N, párrafo M. "numeral 1o." (con ordinal) es una unidad no cotejable
  (antes se perdía y la cita se auditaba sin ella). Una unidad
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
  Ninguno de estos topes toca la rama de distancia alta sin metadata: esa la resolvió D10
  (abajo).
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
- **Artículo no localizado en una ley indexada** (D10, R4-D10) → 🔴 **solo con prueba
  positiva de inexistencia**; en cualquier otro caso 🟡. **Criterio del responsable
  (2-oct-2026): opción C.** Es un criterio jurídico adoptado para este sistema (Regla 4 de
  `CLAUDE.md`): "no lo encontré" no es "no existe" (puede ser un hueco del índice), y solo
  una observación positiva del cuerpo de la ley justifica bloquear el documento. Antes:
  "🔴 ALERTA ALTA … Posible alucinación" (evidencia sin metadata y con distancia mayor que el
  umbral) y "🔴 ALERTA CRÍTICA … Alucinación detectada" (consulta sin vecinos). **Ronda 2
  (rechazo por falsos rojos):** la prueba se **abstiene** ante cualquier ambigüedad; es
  preferible perder un 🔴 que emitir uno falso.
  La prueba (`itosturre/audit/inexistencia.py`, pura) se busca en todas las rutas en que el
  precepto no se localiza en la evidencia de la ley citada —sufijo sin encabezado exacto,
  evidencia insuficiente, distancia alta, consulta sin vecinos—, y **solo si la ley se ligó
  al artículo por vínculo sintáctico explícito** (`law_method` `adyacente_derecha`,
  `adyacente_izquierda` o `posesivo`; la coordinación hereda el de su artículo): con la ley
  del contexto previo, de un antecedente o de un encabezado, inferida o por confirmar, o con
  evidencia de otro ordenamiento, nunca. Examina el **cuerpo** de la ley (lo anterior a la
  primera línea "TRANSITORIOS") en los fragmentos indexados de esa fuente, leídos por metadata
  y preparados una vez por auditoría (`preparar_ley`). Solo dos pruebas son válidas:
  1. **Vecinos en el mismo fragmento.** El encabezado del artículo inmediatamente anterior
     según la numeración (N < N Bis < N Ter…; N < N-A < N-B…; N-B < N-B Bis < N-C) y el del
     siguiente que existe aparecen seguidos **dentro de un mismo fragmento**, cada uno una
     sola vez en el cuerpo, sin ninguna línea candidata entre ellos: otro encabezado, un
     ordinal en palabra, una línea que empiece con "artículo"/"art." y un número en cualquier
     caja, o con un número ("3 Bis.-", "3o.-", "1."), también con la palabra partida por un
     guion ("ARTÍ-\nCULO 3 BIS.-"). La continuidad entre fragmentos ya **no** cuenta: un
     texto repetido (una nota o una cabecera idéntica) no prueba que dos fragmentos sean la
     misma aparición, y la ingesta corta en cada artículo sin solapar. Si conviven sufijos de
     letra y latinos del mismo número ("70-A" y "70 Bis"), su orden no es uniforme y no hay
     prueba.
  2. **Número muy superior al último artículo.** El cuerpo está completo en el índice
     (`chunk_index` contiguos desde el 0 hasta el fragmento de la frontera), su último
     encabezado es el de mayor número, ninguna línea candidata del cuerpo ("ARTICULO 225 …",
     "148 Bis …", "50.- Texto") ni ninguna línea con forma de artículo tras la frontera
     ("ARTÍCULO 7 …", "455 ter") tiene un número mayor (frontera dudosa), la **densidad** de
     páginas no delata texto perdido (los fragmentos consecutivos que empiezan en la misma
     página no pueden abarcar, hasta el siguiente, más de 1 + caracteres / 800 páginas; la
     metadata solo guarda la página de inicio de cada fragmento), y el número citado alcanza
     el **margen**: N ≥ último + max(10, ⌈5 % del último⌉). Entre el último + 1 y el margen no
     hay prueba (una reforma posterior a la versión indexada pudo adicionarlo): `🟡 POSTERIOR
     AL ÚLTIMO ARTÍCULO` — "el art. N es posterior al último artículo de la VERSIÓN INDEXADA
     de '<ley>' (art. M, pág. X; Última Reforma DOF …): verificar si una reforma lo adicionó".
  Salvaguardas comunes: **identidad documental** (P5): el fragmento 0 empieza con una
  denominación del catálogo para esa fuente (título del encabezado) o el decreto que la
  expide la nombra ("decreta: Código…", "se expide la Ley…"); si no se comprueba —o el
  catálogo no tiene una denominación completa—, no hay prueba. Un encabezado del artículo
  citado en cualquier parte de la fuente, con cualquier ordinal ("4" frente a "4o.") y también
  "N.- (Se deroga)", acredita **existencia**. Una mención del artículo citado en cualquier
  parte de la fuente (cuerpo y transitorios) tras "artículo(s)"/"art(s).", también en una
  enumeración o un rango ("arts. 136, 137 y 138", "467 a 471"), o —si lleva sufijo— "N Bis"
  suelto, impide la prueba. Sin línea TRANSITORIOS no hay cuerpo delimitado; fragmentos sin
  `chunk_index` entero, repetidos o de otra fuente, tampoco. Toda alerta de inexistencia cita
  la **versión indexada** (fecha de "Última Reforma DOF" —u otra fórmula del encabezado:
  "Nueva Ley DOF", "Código abrogado DOF", "Última reforma P.O."— o "versión indexada sin
  fecha").
  - **Con prueba** → `🔴 ARTÍCULO INEXISTENTE ACREDITADO` (traza `refuted`, método
    `corpus_estructura`, puntaje 0) con la prueba exacta: "en el cuerpo de '<ley>' (versión
    indexada: Última Reforma DOF …) el art. 911 pasa al art. 912 sin el 911 Bis (pág. X)" o
    "el cuerpo de '<ley>' (versión indexada: …) termina en el art. M (pág. X); se cita el N",
    y la indicación de cotejar en la fuente oficial una reforma posterior a esa versión.
    **Bloquea el documento** como toda cita normativa refutada (regla 3 del veredicto): la
    Regla absoluta 2 habla del rubro discrepante; este bloqueo es por inexistencia acreditada.
    `retrieved_sources` lleva la evidencia original de la prueba (el fragmento de los vecinos,
    o el del último artículo y el de la frontera) y `inexistencia_acreditada`.
  - **Sin prueba** → las dos rutas que eran 🔴 pasan a `🟡 NO LOCALIZADO`: "no se encontró el
    art. N en la ley indexada '<ley>'; no se acredita que no exista (puede ser un hueco del
    índice): cotejar en la fuente oficial" (traza `not_verifiable`; con evidencia, puntaje
    60–84 y el motivo en `inexistencia_no_acreditada`). Si el fragmento sí trae el
    encabezado exacto (ubicado) pero coincide poco y sin metadata, `🟡 COTEJAR` (traza
    `partial`). Las demás rutas sin prueba conservan su 🟡 (NO VERIFICABLE del sufijo,
    EVIDENCIA INSUFICIENTE), salvo el caso "posterior al último", que en cualquier ruta usa su
    alerta propia sin cambiar el estado ni el puntaje de la ruta. Nunca la palabra
    "alucinación".
  - **Límites del índice actual:** la prueba 1 solo se cumple cuando dos artículos comparten
    fragmento (leyes con "ARTÍCULO" en mayúsculas o encabezados con sangría), y los
    encabezados repetidos por el solapamiento de subfragmentos la impiden; "19 Ter CPEUM"
    queda 🟡. La página es la de la metadata del fragmento (inicio del fragmento en el índice):
    en leyes con fragmentos de varios artículos puede no ser la del encabezado. Una página
    perdida por la extracción del PDF no deja hueco de `chunk_index`; el margen, la densidad y
    las demás salvaguardas reducen ese riesgo, pero no lo eliminan.

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
| Solo tesis verificadas: 🟡 "Artículos con verificación insuficiente (RAG: 0.0)" | 🟡 "Jurisprudencia localizada; …" (transitorio; R4d lo mantiene) |
| Sin ninguna cita: 🟡 "Artículos con verificación insuficiente (RAG: 0.0)" | 🟡 "Sin citas detectadas: no hay normativa ni jurisprudencia que verificar" |
| El 🟢 no decía qué acreditaba | "Alcance del 🟢: existencia y ubicación del precepto en el corpus local; no significa que lo citado diga lo que el escrito afirma" |

### Qué cambia para el abogado (D10)

| Antes | Después |
|---|---|
| Distancia alta sin metadata y sin encabezado: "🔴 ALERTA ALTA … Posible alucinación" (bloqueaba) | 🟡 NO LOCALIZADO (no se acredita que no exista), salvo prueba positiva |
| Consulta sin vecinos en una ley indexada: "🔴 ALERTA CRÍTICA … Alucinación detectada" | 🟡 NO LOCALIZADO, salvo prueba positiva |
| Encabezado ubicado, sin metadata y con distancia alta: 🔴 ALERTA ALTA | 🟡 COTEJAR (el precepto sí se ubicó) |
| "art. 9999 CFF", "art. 1000 de la Ley de Amparo", "art. 5000 CPEUM": 🟡 EVIDENCIA INSUFICIENTE | 🔴 ARTÍCULO INEXISTENTE ACREDITADO ("el cuerpo … (versión indexada: Última Reforma DOF 14-11-2025) termina en el art. 263; se cita el 9999") |
| "art. 264 CFF", "art. 137 CPEUM", "art. 272 de la Ley de Amparo" (último + 1): 🟡 EVIDENCIA INSUFICIENTE | 🟡 POSTERIOR AL ÚLTIMO ARTÍCULO (verificar si una reforma lo adicionó) |
| "art. 911 Bis CPCJ" (911 y 912 en el mismo fragmento): 🟡 NO VERIFICABLE | 🔴 ARTÍCULO INEXISTENTE ACREDITADO ("el art. 911 pasa al art. 912 sin el 911 Bis") |
| "art. 19 Ter CPEUM", "art. 70 Ter CFF": 🟡 NO VERIFICABLE | Igual (vecinos en fragmentos distintos, o sufijos de letra y latinos) |
| "La Ley de Amparo … y la CPEUM …. El artículo 217 …": se cotejaba contra la CPEUM | 🟡 LEY NO IDENTIFICADA (contexto previo ambiguo) |
| "… de la LSS. El artículo 248 de la LISSSTE": 🟢 contra la Ley del Seguro Social | 🟡 LEY NO IDENTIFICADA (sigla fuera del catálogo) |

### Qué cambia para el abogado (verde determinista y ordinales, 3-oct-2026)

Medido con el corpus real (main@ba26a93 frente a este cambio; 60 artículos de cada ley, citados
como "LEY Art. N."):

| Antes | Después |
|---|---|
| 🟡 con metadata, encabezado exacto y fuente correcta, solo por distancia: CPEUM 51/60, CNPP 50/60, CFF 39/60, Ley de Amparo 7/60; además CPEUM y CFF 1–9 (citados sin ordinal) 🟡 sin metadata | 🟢 determinista en los 240 (distancia de los nuevos 🟢: 0.129 a 0.193); el puntaje por similitud queda informativo |
| "CNPP Art. 109." (Gold Set v2, aprobado 🟢): 84 🟡 | 85 🟢 (similitud 84) |
| "CPEUM Art. 1." o "CFF Art. 9.": 🟡 EVIDENCIA INSUFICIENTE con la evidencia de otro artículo ("Artículo 91-C. (Se deroga)") | 🟢 con el encabezado "Artículo 1o." / "Artículo 9o." (pág. 1 / 5) |
| "Código Civil Federal Art. 1.": 🟢 con un decreto de reforma (pág. 335) | 🟢 con el art. 1o. del cuerpo (pág. 1) |
| "CFF Art. 4-A.": 🟡 NO VERIFICABLE | 🟢 con "Artículo 4o.-A.-" (pág. 3) |
| Derogado, fracción derogada, párrafo citado, ley por confirmar, 29-A frente a 29 | Sin cambio de semáforo (🟡) |
| "CFF Art. 9999." 🔴 inexistente acreditado · "CFF Art. 264." 🟡 posterior al último | Igual |
| Remisión al inicio de línea tomada por encabezado: "artículo 134/135 de la LFPC" 🟢 con «artículo 134. Se adiciona…»; "artículo 41 del CCF" 🟢 con «artículo 41. La Procuraduría…» (texto del 40) | 🟡 COTEJAR (solo remisión) en la LFPC; 🟢 con «Artículo 41. Las Formas del Registro Civil…» (pág. 7) en el CCF |
| Encabezado repetido: "artículo 54 del CCF" 🟢 con un art. 54 transcrito en otro precepto (pág. 197) | 🟡 UBICACIÓN NO ACREDITADA (5 encabezados antes de la frontera) |
| "artículo 496 del CFPC" 🟢 con el art. 496 de un decreto de reforma (pág. 126; el cuerpo termina en el art. 626, pág. 63) | 🟡 UBICACIÓN NO ACREDITADA (tras la frontera) |
| "CFF Art. 4°-A." 🟡 con otra evidencia (se extraía "4") | 🟢 con "Artículo 4o.-A.-" (pág. 3), nunca con el art. 4o. |

### Qué cambia para el abogado (tratados y párrafos numerados, 4-oct-2026)

Medido con el corpus real (main@6d55881 frente a este cambio, sin re-ingestar; "artículo N de
la <tratado>" para todos los artículos de cada tratado):

| Antes | Después |
|---|---|
| CADH 82/82, CDN 54/54 y PIDCP 53/53 artículos 🟡 (la auditoría exigía el cierre del encabezado) | 🟢 determinista los 189, con metadata, encabezado del artículo citado al inicio del fragmento y ubicación única (`encabezado_fin_de_linea`) |
| "artículo 8.1 de la CADH", "14.3 del PIDCP", "3.1 de la CDN": se auditaba el artículo completo (el ".1" se perdía) | 🟢 solo si la línea "1." se ubica en el cuerpo (`unidad_cotejada`); "artículo N.1" sale 🟢 en 108 de los 189 artículos —todos con esa línea en el índice— y 🟡 UNIDAD CITADA NO COTEJADA en los que no tienen párrafos numerados o tienen una numeración dudosa (CDN art. 24: 1, 2, 4) |
| "artículo 8, numeral 1" / "párrafo 1": unidad no cotejable (🟡) | párrafo numerado: 🟢 si se ubica la línea (solo en tratados) |
| Ley nacional: "artículo 20-Ter.1 del CFF" 🟢 (el ".1" se perdía); "20-Ter, párrafo 1" 🟡 | 🟡 UNIDAD CITADA NO COTEJADA en ambos (también INFONAVIT 19 y 25, LFT 513, LNED 9) |
| "8.2, incisos c), d) y f)" solo cotejaba el c) | 🟢 si los tres se cotejan; "incisos a) y z)" 🟡 |
| Ingesta (`--simular`) del Código Civil de Jalisco: cortaba en sus 10 líneas "Artículo N" de la Declaratoria (3 193 encabezados) | No corta (3 183, cobertura del cuerpo 100 %); CADH, CDN y PIDCP igual que antes |
| "artículo 8.9 de la CADH" (sin párrafo 9) | 🟡 UNIDAD CITADA NO COTEJADA (nunca 🟢 del art. 8) |
| "artículo 8. 1 de la CADH" (punto con blanco): art. 8 completo | 🟡 COBERTURA INCOMPLETA |
| "artículo 8, párrafos 1 y 2, de la CADH": el 8 sin ley y el 2 como "posible artículo" | art. 8 con los párrafos 1 y 2 |
| Artículo inexistente de un tratado (90 CADH, 60 CDN, 99 PIDCP): 🟡 | Igual (sin frontera TRANSITORIOS, D10 se abstiene; nunca 🔴) |
| Código Civil de Jalisco 1–60; CPEUM, CNPP, CFF y Ley de Amparo 1–60; 30 de la LFPC y 30 del CFPC | Sin cambios (0 🟢 nuevos, 0 🟢 perdidos, 0 🔴 nuevos) |

### Qué cambia para el abogado (vigencia del corpus y ruta `query`, 9-oct-2026)

El 🟢 normativo acredita existencia y ubicación en la **versión indexada**. `audit` y `query`
leen ahora el último reporte de `scripts/vigencia_corpus.py` (`ITOS_VIGENCIA_REPORTE` o el más
reciente de `reportes/vigencia_corpus/`) y lo aplican solo si se hizo sobre el mismo índice
(`CHROMA_PATH`) y la ley conserva los fragmentos que el reporte registró. Si la da por
DESACTUALIZADA o ABROGADA (`itosturre.audit.vigencia`): tope 84 (traza `partial`) y, para una
inexistencia probada sobre esa versión, 🟡 (traza `not_verifiable`). Nunca 🔴 por vigencia. Cada
cita trae `vigencia_fuente`; el resumen, `vigencia_corpus` (estado del reporte y cuántas citas
toca), y la razón del 🟡, "(N por versión indexada no vigente)".

La ruta `query` (`consultar_corpus`) ya no da semáforo por parecido a un artículo nombrado: le
pide el veredicto a `audit` (`match: articulo_citado`) y los pasajes cercanos van como
`contexto` con ⚪. Sin artículo nombrado (`semantico`), el semáforo mide el parecido, nunca es 🔴
(⚪) y no es 🟢 en una ley no vigente. El respaldo literal (`literal`) exige encabezado auténtico
y es 🟡.

Medido con el corpus real de este equipo (49 fuentes; `feat/vigencia-corpus-v2`@fd41ca5 frente a
este cambio, copias idénticas del índice y el reporte de vigencia de la copia: CPEUM, LFT y CFF
desactualizadas; Ley de Amparo, CPF, CCF y CNPP vigentes):

| Antes | Después |
|---|---|
| `audit` "artículo 16 / 19 de la CPEUM", "artículo 15 de la LFT" (versión indexada de 2015): 🟢 85 | 🟡 84 VERSIÓN INDEXADA NO VIGENTE (versión indexada, oficial y comando de cotejo) |
| `query` "artículo 750 de la Ley de Amparo" (inexistente): 🟢 87 con el «Artículo 5o» | 🔴 0, el veredicto de `audit` (inexistencia acreditada) |
| `query` "artículo 9999 del Código Civil Federal": 🟢 86 con el «Artículo 2699» | 🔴 0 (inexistencia acreditada) |
| `query` "artículo 57 del Código Penal Federal" (derogado): 🟢 100 «literal» | 🟡 84 PRECEPTO DEROGADO |
| `query` "artículo 16 de la CPEUM", "artículo 15 de la LFT": 🟢 100 «literal» | 🟡 84 (versión no vigente) |
| `query` "artículo 873-K de la LFT" (adicionado DOF 01-05-2019; no está en la versión indexada): 🟢 87 con un pasaje que remite al art. 879 | ⚪ contexto: el artículo no se ubicó y el pasaje no se presenta como veredicto |
| Prueba de inexistencia (D10) sobre una versión que el reporte da por no vigente: 🔴 | 🟡 INEXISTENTE EN UNA VERSIÓN NO VIGENTE (prueba sintética; en este índice los 9 artículos de la LFT adicionados en 2019 que se probaron ya salían 🟡 NO VERIFICABLE) |
| `audit` "artículo 750 LA", "9999 CCF" (leyes vigentes) y "57 CPF" (derogado) | Igual: 🔴, 🔴 y 🟡 |
| Sin reporte, reporte de otro índice o anterior a la re-ingesta de la ley | Sin cambio de semáforo; `vigencia_corpus.estado` dice por qué |

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
