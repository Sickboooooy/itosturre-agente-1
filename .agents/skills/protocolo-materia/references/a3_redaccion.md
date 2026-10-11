# A3: cómo redactar el protocolo para que pase los gates a la primera

A3 es el orquestador. Redacta **solo** con lo que respaldan el mapa de A1 (extractos literales del
RAG) y las tesis de A2 con captura VERIFICADO. Lo que no tenga respaldo no se escribe como hecho:
se marca `[VERIFICAR EN: fuente]` o va a la lista Capa 2 de la evidencia.

## Antes de escribir

- Lee el mapa de A1 completo (extracto por extracto, no el resumen del agente) y sus `huecos`.
- De cada tesis que vayas a citar, lee el `texto_completo` de su captura
  (`investigacion/a2/verif_*/auditoria_vvca.json`). Descríbela por lo que dice su texto, no solo
  por el rubro.
- Lee la ficha procesal de la materia (`fichas`, en `config.json`): lo que ya dice no se repite.

## Estructura (G1)

- Cinco secciones con su rótulo exacto, en orden. Usa las frases de la plantilla:
  - **I.** «Cuando el asunto sea …, tu análisis respeta esta cadena: … → … Nunca inviertas este
    orden.» Si hay un parámetro sin jerarquía, como el de derechos humanos, dilo en el cierre.
    La cadena sigue la jerarquía normativa de CLAUDE.md (decisión del operador, 11-oct-2026):
    CPEUM y tratados → jurisprudencia de la SCJN y de los Plenos Regionales → leyes federales y
    nacionales → jurisprudencia de los Tribunales Colegiados de Circuito, en su circuito → leyes
    locales → reglamentos. Si el fondo depende del fuero, la ley federal va antes de la
    jurisprudencia de los TCC y la de la entidad, después.
  - **II.** «… rigen de forma especialmente estricta: … Señala cuando un argumento del usuario o de
    la contraparte los pase por alto.»
  - **III.** «De los métodos generales que ya conoces, … los que con más frecuencia deciden un caso
    son: (1) … Prioriza estos cuando el caso lo permita, sin descartar los demás si el caso concreto
    los exige.»
  - **IV.** «Además del Semanario Judicial de la Federación, que ya verificas para cualquier materia,
    … deben preferirse, cuando el dato esté disponible: …». Lleva la fecha de corte de la
    verificación, la regla temporal propia de la materia y el cierre
    «… márcalo como [VERIFICAR EN: fuente correspondiente]; nunca lo presentes como dato duro.»
  - **V.** «Antes de avanzar, verifica: (1) …».
- Tope: **260 palabras por sección**. Cuéntalas antes de guardar; `escribir` no guarda un borrador
  que no pase G1. Si una sección se pasa, recorta redacción, nunca condiciones. Agrupa las citas de
  un mismo inciso en un solo paréntesis y lleva a las objeciones, que no tienen tope, lo que solo
  necesita el adversario.
- Declara el alcance si la materia del catálogo es más estrecha que su nombre. Ejemplo:
  «constitucional» cubre en la práctica el amparo, no las controversias ni las acciones de
  inconstitucionalidad.

## Enfoque nacional (G2 R5 y G3 LEY_LOCAL)

El protocolo vale para todo el país; hacer uno por entidad no es viable. Por eso:

- El ancla es lo que rige en toda la República: la CPEUM y los tratados, los códigos nacionales
  (CNPCF, CNPP), las leyes generales (LGDNNA, LGV…), las federales en lo federal y la
  jurisprudencia de la SCJN y de los Plenos Regionales.
- Lo sustantivo local se remite, sin citar artículos de ningún estado: «el código civil de la
  entidad del asunto [VERIFICAR EN: periódico oficial de la entidad]». Las fuentes de IV también
  son genéricas: «el periódico oficial de la entidad», «el boletín judicial del tribunal
  local».
- El Código Civil Federal y el Código Penal Federal rigen solo en lo federal. Si se usan como
  referencia para orientar el análisis, el protocolo lo dice expresamente: «en lo federal» o
  «como referencia; confirma la regla en el código de la entidad».
- G2 reprueba nombrar una entidad (`R5_ENTIDAD_FEDERATIVA`), también en `palabras`. G3
  reprueba citar un artículo de una ley local (`LEY_LOCAL`). «México», solo, es el país y no
  cuenta.

## Lo que la plantilla prohíbe (G2)

- Nada de rol («Eres…», «actúa como…»), formato de salida ni campos del simulador, ni la regla
  genérica de no inventar. Solo las fuentes DONDE verificar.
- No repitas la ficha. G2 reprueba una oración que reúna el 60 % o más de las palabras de contenido
  de sus `etapas` o su `estandar`. Separa con «;» o «:» lo que tenga que mencionar esos términos.
  Nombrar el código o rozar los principios solo avisa.

## Citas que el auditor sí coteja (G3)

- Forma: «artículo 17 de la Ley de Amparo», «artículos 17, 18 y 22 de la Ley de Amparo»,
  «artículo 107, fracción I, de la CPEUM», «artículos 179 a 184 de la LISR». Nunca «31-IV».
- Las series se unen con «y», no con «o»: «alguno de los artículos 19 y 20 de la CPEUM».
- Las siglas que el auditor reconoce ahorran palabras: CPEUM, LFT, LFTSE, CNPP, PIDCP. Pruébalas con
  `OpenNotebook.py audit --text` antes de usar una nueva. Nombra la ley completa una vez, por
  ejemplo «la Ley Federal del Trabajo, LFT (artículo 1 de la LFT)», y luego usa la sigla. Así se
  mantiene el tope de 260 palabras sin quitar condiciones. Una sigla que el auditor no reconoce
  («LISSSTE») da `SIGLA_DESCONOCIDA`: escribe la denominación («Ley del ISSSTE») o define la
  sigla antes de usarla, «Ley del ISSSTE (LISSSTE)». Esto último solo funciona con el auditor
  de `fix/auditor-sigla-desconocida`; sin él, la sigla puede heredar la ley de la oración
  anterior y salir en falso 🟢.
- De una ley en 🟡 (por ejemplo, el CFPC, abrogado con vigencia transitoria), G3 coteja cada artículo citado contra el PDF oficial (Regla 8).
  Cita solo los que salgan 🟢 COINCIDE. Si uno no se localiza (`COTEJO_PENDIENTE`), enuncia la regla sin
  el número y márcala [VERIFICAR EN: fuente oficial].
- Todo artículo lleva su ley al lado, aunque se sobreentienda. Si escribes «del artículo 123»
  suelto, el gate da `CITA_SIN_LEY`.
- Nada a la **izquierda** de una cita que el auditor lea como otro ordenamiento: «norma» en
  singular, «ley», «código» o «reglamento» sueltos, «tratados», o una ley distinta en la misma
  oración. «Normas generales», en plural, no estorba, y tampoco «disposiciones legales». Por
  ejemplo, «en su lugar rige la ley (artículo 123 de la CPEUM)» falla. Si el gate da
  `LEY_AMBIGUA`, ese es el problema.
- Tampoco funciona el nombre de **otra** ley, aunque esté completo, justo antes de una cita entre
  paréntesis. «… que enumera la LOTFJA (artículo 2 de la LFPCA)» falla. Lo que debe ir junto a la
  cita es la misma ley: «… resoluciones definitivas, LFPCA (artículo 2 de la LFPCA; artículo 3 de
  la LOTFJA)». Dentro del paréntesis, separa con «;» las citas de leyes distintas.
- Unidades que el auditor no ubica con certeza, porque el artículo es largo o el índice lo partió:
  cítalas por el artículo, sin la unidad, y anota la unidad exacta en `notas_de_cita` de la
  evidencia. Casos vistos:
  - el artículo 61 de la Ley de Amparo y sus fracciones;
  - la fracción X del artículo 107 de la CPEUM;
  - el apartado B del artículo 20 de la CPEUM.
- No pegues enumeraciones como «(6)» a un número o a una cita.
- Si una cita a una ley no indexada es indispensable, es Regla 7: no la escribas y anótala como
  hueco.

## Jurisprudencia (G4 y Regla 3)

- Formato: «P./J. 20/2014 (10a.), registro digital 2006224», con la clave justo antes del registro.
  Sin registro, G4 reprueba; y si la clave no es la de la captura del SJF, también
  (`TESIS_CLAVE_DISCREPANTE`). No hace falta transcribir el rubro: promovida la tesis, G3 solo avisa.
- Si A2 no trae jurisprudencia de alcance general pertinente, no cites ninguna. La cadena de I ya
  ordena la jurisprudencia sin nombrarla, y las verificadas quedan como candidatas. Así el
  protocolo puede llegar a `EXITO` sin hueco de corpus (administrativo, 11-oct-2026).
- Cita solo las verificadas por A2 y, de preferencia, las de alcance general de la SCJN. Las de
  Plenos Regionales obligan solo en su región y suelen resolver supuestos específicos: van a
  `tesis_candidatas_capa2`, salvo que el abogado decida otra cosa.
- La captura del SJF no acredita la cita. Mientras el abogado no las promueva al corpus local, las
  tesis citadas detienen el bucle en «hueco de corpus». Es lo esperado, no un error de redacción.
- Si una tesis es anterior a una reforma de la ley que interpreta, no decidas cuál prevalece:
  instruye «señala la diferencia en vez de resolverla» y anótalo como Capa 2.

## Fidelidad (lo que A5 encontró al resumir)

- Las paráfrasis conservan las condiciones y los límites del extracto. Ejemplos:
  - «para condenar» en el estándar de la presunción de inocencia;
  - «cuando la naturaleza del acto lo permita» en la suspensión;
  - «en todo amparo», si la regla es general;
  - por conducto de qué órgano se presenta un recurso y qué pasa si se presenta ante otro.
- Fechas de reforma exactas («adicionado el 16-10-2025»), nunca «en 2025».
- No invites al modelo a completar de memoria una lista que no enumeras. Usa «los supuestos del
  texto vigente», no «los nuevos supuestos».
- La regla temporal de IV depende de la materia: en penal, la fecha de los hechos; en amparo, la
  demanda o el acto y los transitorios. Si no hay respaldo, es Capa 2.

## Campos de lista

- `datosIndispensables`: hechos que el usuario puede dar, no calificaciones jurídicas. El más
  urgente primero: persona detenida, actos que ponen en peligro la vida o la libertad, ejecución
  inminente.
- `objecionesTipicas`: puntos de falla reales, con su cita. Si la materia lo pide, en los dos
  sentidos (quien promueve y quien defiende el acto).
- `palabras`: minúsculas y sin acentos, de alta señal. Ten en cuenta que la coincidencia es por
  subcadena («amparo» coincide dentro de «desamparo») y que se necesitan dos coincidencias. Evita
  términos compartidos con otras materias.
- `_notaVersion`: «v1 (fecha): … Jurisprudencia propuesta por A2 y capturada en el SJF …; por la
  Regla 3 queda por verificar contra el corpus local de jurisprudencia. Pendiente: revisión y firma
  del abogado.» Nunca digas «verificada» de una tesis que solo tiene captura del SJF.

## Después de escribir

1. `escribir` el borrador y `evidencia --citadas <registros>`.
2. Completa `notas_de_cita` en la evidencia: unidades omitidas, discrepancias entre leyes y fechas de
   reforma.
3. `gates`, y atiende solo el fallo que indique el veredicto.
