---
name: protocolo-materia
description: Genera o actualiza un "protocolo de materia" para el sistema de agentes de destino. Es un JSON con las cinco secciones de la plantilla (jerarquía normativa, principios rectores, métodos de argumentación, fuentes de verificación y advertencias), más palabras de activación, datos indispensables y objeciones típicas. Corre un bucle verificado (goal-loop) - A1 mapa normativo desde el RAG local, A2 jurisprudencia desde las páginas públicas del SJF con el scraper con navegador, A3 redacción, A4 gates G1–G4 y A5 revisión de diseño, con paro por éxito, hueco de corpus, estancamiento o tope. Se activa cuando el usuario pide un protocolo de materia, la siguiente materia del plan de protocolos (civil, laboral, administrativo, seguridad social, familiar, consumidor, mercantil), rehacer o actualizar uno (v1.1), o menciona la plantilla del protocolo de materia o el goal-loop de protocolos.
---

# Protocolo de materia: el bucle verificado

Esta skill empaqueta la corrida que produjo `penal_materia` (piloto F1) y `constitucional_materia`
(F3). La parte determinista vive en `scripts/protocolo_materia.py` y en los gates
(`itosturre/protocolos/`, CLI `scripts/protocolo_gates.py`). La parte que necesita un modelo son los
agentes A1, A2 y A5, cuyas plantillas están en `references/`, y la redacción A3, que hace el
orquestador con `references/a3_redaccion.md`.

## Reglas que no se negocian

- **El bucle ordena y verifica; no certifica.** APROBADO solo lo firma el abogado, ligado al
  `sha256` del protocolo. Ni el script ni ningún agente firman.
- **Los hechos salen de la fuente.** Las normas, de los extractos literales del RAG (A1). Las tesis,
  de la captura de su página pública en el SJF (A2). La verificación de citas, del corpus (G3).
  Ningún agente le cree a otro sobre un hecho, y nada se cita de memoria.
- **Regla 3.** La captura del SJF no acredita la cita. Promover una tesis al corpus local
  (`scripts/promover_tesis.py`) escribe en el corpus: solo se hace por orden expresa del abogado.
- **SJF solo con el scraper con navegador** sobre páginas públicas (`docs/CONFIABILIDAD_VVCA.md`).
  Nunca el microservicio interno ni otros endpoints.
- **Las salidas viven fuera del repo** (`PROTOCOLOS_DIR`, por omisión
  `~/itosturre-data/protocolos-justia/`). Son entregables del sistema de destino. La ficha procesal
  (`fichas_simulador.json`) y la descripción del destino (`destino.json`) también son datos de
  fuera: nunca se copian al repo, ni tampoco su código.
- **Enfoque nacional** (criterio del operador, 11-oct-2026). Los protocolos valen para todo el país
  y no distinguen por el código de una entidad: eso exigiría uno por cada entidad. Lo local se
  remite a la ley de la entidad del asunto con [VERIFICAR EN: …]. `preparar` bloquea las leyes
  locales (`LEY_LOCAL`). G2 reprueba nombrar una entidad (`R5_ENTIDAD_FEDERATIVA`) y G3, citar un
  artículo de una ley local (`LEY_LOCAL`). Ver `references/a3_redaccion.md`.
- **Capa 2**, es decir pertinencia, completitud doctrinal y estrategia, va a una lista para el
  abogado. A5 aconseja; no aprueba hechos ni criterio.

## El bucle, paso a paso

Antes de empezar, define la variable `PY`: el intérprete del venv con el corpus, con `CHROMA_PATH`
apuntando al índice (`docs/ENTORNO.md`). Los comandos son `"$PY" scripts/protocolo_materia.py …`, y
`<carpeta>` es `$PROTOCOLOS_DIR/<materia>_materia`.

1. **Elegir la materia.** `references/materias.md` tiene el catálogo y la preparación del corpus.
   Completar el corpus de una materia es ingesta, y la ingesta solo se hace por orden expresa.
   Ante un 🔴 federal con rezago corto, revisa el historial oficial de la ley antes de pedir una
   re-ingesta: el de la LFPC era el acuerdo anual de montos, no una reforma (igual el Código de
   Comercio y la LGSM: «Cantidades actualizadas por Acuerdo»).
2. **Precondición.**

   ```
   preparar <materia> --leyes "…" "…" --ley-principal "de la …" [--ley-no-indexada "de la …"]
   ```

   Comprueba en el último reporte de vigencia el semáforo de cada ley y corre los fixtures que
   deben reprobar: rol, formato, artículo inexistente, ley no indexada y un control en verde.
   También cuenta las tesis del corpus local de jurisprudencia. Si sale 1, **no se sigue**: o hay
   una ley en 🔴 o fuera del índice (decide el abogado), o un gate que no reprueba (se corrige el
   gate primero).
3. **Configurar.** Llena en `<carpeta>/config.json` los campos `temas_a1`, `temas_a2`,
   `advertencias_a2`, `alcance` y `contexto_a5` (ver `references/ejemplos/`). Después corre
   `prompts <carpeta>`, que escribe `prompts/a1.md` y `prompts/a2.md`.
4. **Investigar.** Lanza A1 y A2 en paralelo, en segundo plano, con el texto exacto de esos prompts
   (Agent, `general-purpose`; `model` según `config.modelos`). Al terminar cada uno, anota su
   costo con `medir <carpeta> --agente A1 --tokens N --minutos M`, con los datos de la
   notificación. Después corre `revisar <carpeta>`, que coteja lo que entregaron contra la
   fuente:
   - cada extracto de A1 debe ser literal de la salida cruda del RAG;
   - cada dato de A2 debe coincidir con la captura del scraper;
   - además mide los topes del presupuesto.

   Si sale 1, no redactes sobre ese material: lo no literal o lo que difiere no se usa.
5. **Redactar (A3).** Sigue `references/a3_redaccion.md`. Escribe el borrador en JSON y corre:

   ```
   escribir <carpeta> <borrador.json>
   evidencia <carpeta> --citadas <registro> …
   ```

   `escribir` no guarda un borrador que no pase G1 y respalda la versión anterior.
6. **Bucle (A4).**

   ```
   gates <carpeta> --cambio "qué cambió"
   ```

   Lee el reporte completo (`gates_iterN.json`), no el resumen. Atiende **solo** el fallo que
   indica el veredicto, con el cambio mínimo, sin reescribir lo que ya pasó. Después `escribir` y
   `gates` otra vez.
7. **Revisión de diseño (A5).** Cuando todo esté en verde o solo quede el hueco de corpus, corre
   `prompts <carpeta> --agentes a5` y lanza A5 con ese texto.
   - Aplica sus hallazgos ALTA, y los MEDIA o BAJA que respalden los extractos de A1, nunca de
     memoria.
   - Lo demás va a `revision_diseno.pendiente_capa2` en la evidencia.
   - Luego `gates --origen A5 --cambio "…"` y vuelve al paso 6.
8. **Cerrar.** Corre `cerrar <carpeta>`. Escribe `LEEME.md` con la decisión pendiente y la lista
   Capa 2 (copia la estructura del de constitucional). Entrega al usuario el resultado con opciones
   numeradas: promover tesis, revisar Capa 2, firmar o la siguiente materia.
9. **Firma (la hace el abogado, no el agente).** El abogado corre `firmar <carpeta>` en su propia
   terminal. El comando hace lo siguiente:
   - se niega sin terminal interactiva, así que el agente no puede ejecutarlo;
   - solo firma la versión con G1–G4 en verde;
   - pide nombre completo y cédula profesional, y que se reescriban los primeros 12 caracteres de
     la huella;
   - registra `aprobacion` con la huella sha256 completa.

   Si el protocolo cambia después (`escribir`, o una edición que detecten `gates` o `cerrar`), la
   firma vuelve a PENDIENTE y la anterior pasa a `historial_firmas`. El agente solo da al abogado
   el comando y la huella de cada versión.

## Cuándo para el bucle (`gates`)

| Veredicto | Salida | Qué hacer |
|---|---|---|
| `EXITO` | 0 | G1–G4 en verde: A5, si aún no se hizo, y después la firma del abogado |
| `SEGUIR` | 1 | Atender el único fallo indicado. Prioridad: G1 > G2 > G3 > G4 |
| `PARO HUECO_DE_CORPUS` | 4 | Solo quedan `TESIS_FUERA_DEL_CORPUS`, `NO_VERIFICABLE` o `AUDITORIA_NO_UTILIZABLE` (Regla 7). Antes de aceptarlo, confirma que la ley de un `NO_VERIFICABLE` no es el nombre incompleto de una ley indexada. Decide el abogado |
| `PARO ESTANCADO` | 4 | El mismo conjunto de fallos dos vueltas seguidas: el diagnóstico está mal. Escala al abogado; no lo saltes |
| `PARO TOPE` | 4 | 8 iteraciones sin llegar a verde |

`LEY_AMBIGUA`, `CITA_SIN_LEY`, `SIGLA_DESCONOCIDA`, `COBERTURA_INCOMPLETA`, `LEY_LOCAL` y
`R5_ENTIDAD_FEDERATIVA` **no** son hueco de corpus: son redacción de la cita.

`COTEJO_PENDIENTE` y `COTEJO_DIFIERE` (Regla 8) tampoco son hueco de corpus. G3 coteja contra el PDF
oficial cada artículo de una ley en 🟡 del reporte de vigencia (`cotejo_manual.py`). Si difiere, se cita
el texto oficial; si no se localiza, se quita el número y se marca [VERIFICAR EN].

Cuando el abogado promueve las tesis citadas al corpus local (`scripts/promover_tesis.py`), G3 las halla
y deja el aviso `TESIS_SIN_RUBRO_TRANSCRITO`: el protocolo las cita por clave y registro, sin rubro, y
el aviso no reprueba. Lo que ata la cita a la tesis es G4: la clave escrita junto al registro debe ser
la de la captura del SJF (`TESIS_CLAVE_DISCREPANTE` si no). Con eso el protocolo puede llegar a `EXITO`. Solo un `NO_VERIFICABLE` por «ordenamiento fuera del catálogo» es la Regla 7.

## Costo medido (constitucional, 10-oct-2026)

| Agente | Tokens | Minutos | Trabajo |
|---|---|---|---|
| A1 | ~346 mil | 30 | 35 consultas |
| A2 | ~274 mil | 21 | 6 términos y 12 registros |
| A5 | ~252 mil | 17 | revisión de diseño |

En total fueron 64 minutos y unos 871 mil tokens en subagentes, sin contar la orquestación. Eso es
mucho más de lo que estimaba el plan (120–250 mil por materia). Hay dos palancas en `config.json`:
`presupuesto` y `modelos`.

**Con Sonnet en A1 y A2 (laboral, 10-oct-2026):**

| Agente | Tokens | Minutos | Calidad según `revisar` |
|---|---|---|---|
| A1 | ~405 mil | 29 | 176 de 176 extractos literales |
| A2 | ~353 mil | 24 | 0 diferencias en 48 datos (8 tesis y 2 temas sin cubrir) |
| A5 (modelo principal) | ~311 mil | 22 | — |

La calidad comprobable se mantuvo y los gates pararon en el mismo punto. Los tokens subieron
entre 17 % y 29 %: el ahorro depende de que el precio por token de Sonnet sea menor. Mide siempre
con `revisar` y `medir` antes de cambiar el modelo de un agente.

**Administrativo (11-oct-2026, Sonnet en A1 y A2):**

| Agente | Tokens | Minutos | Llamadas | Calidad según `revisar` |
|---|---|---|---|---|
| A1 | ~142 mil | 7 | 17 | 79 de 79 extractos literales, con 43 consultas (8 más que el tope) |
| A2 | ~87 mil | 2.5 | 8 | 0 diferencias en 30 datos |
| A5 (modelo principal) | ~191 mil | 10 | — | — |

En total fueron unos 421 mil tokens en 26 minutos, menos de la mitad que en laboral. La diferencia
no fue el modelo sino el número de llamadas: A2 corrió todos los términos en una búsqueda y todos
los registros en una verificación, y A1 agrupó sus consultas en un script. Las plantillas ya lo
piden. Ojo: A1 se pasó del tope de consultas; `revisar` lo reporta.

**Seguridad social (11-oct-2026, Sonnet en A1 y A2):** A1 ~115 mil tokens en 17 llamadas, A2 ~82 mil en 7 llamadas, A5 ~193 mil
(modelo principal). En total fueron ~391 mil tokens y 24 minutos, con 0 diferencias y extractos 100 % literales según
`revisar`. Con las plantillas agrupadas, el costo de una materia quedó en ~400 mil tokens.

**Consumidor (11-oct-2026, Sonnet en A1 y A2):** A1 ~147 mil tokens en 25 llamadas (38 consultas, tres más que el tope),
A2 ~92 mil en 7 llamadas, A5 ~196 mil (modelo principal). En total fueron ~435 mil tokens y 18 minutos, con 0 diferencias
y extractos 100 % literales según `revisar`; EXITO en la iteración 2, y en la 3 tras A5.

**Mercantil (11-oct-2026, con el corpus indexado ese día):** A1 ~112 mil tokens en 13 llamadas (35 consultas), A2 ~85 mil en
6 llamadas, A5 ~192 mil. En total ~388 mil tokens y 17 minutos; hueco de corpus en la iteración 3 (solo la tesis citada).

## Archivos de la carpeta de una materia

```
config.json                 lo que necesitan los prompts (leyes, temas, contexto, presupuesto)
estado.json                 precondición, etapa, iteración, último veredicto y medición
historial.jsonl             una línea por corrida de gates (errores, veredicto, cambio)
<clave>.json                el protocolo; <clave>.iterN.json son las versiones anteriores
<clave>.evidencia.json      tesis, candidatas Capa 2, notas de cita, gates, revisión y firma
gates.json, gates_iterN.json
prompts/                    los prompts exactos que recibieron A1, A2 y A5
investigacion/              a1_mapa_normativo.json, a1_raw/ y a2/ (búsquedas y capturas)
evidencia_sjf/              solo las tesis citadas: insumo de promover_tesis.py
fixtures/                   los casos en rojo de la precondición
a5_revision.json, LEEME.md
```
