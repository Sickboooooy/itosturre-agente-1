# Propuesta: adelgazar `CLAUDE.md` sin perder comportamiento

**Fecha:** 10-sep-2026 · **Estado:** propuesta para revisión — **sin cambios aplicados**
**Origen:** §3.5 de `docs/auditoria-memoria-contextual-10sep2026.md`

---

## Nota previa: `AGENTS.md` es un derivado, no un segundo archivo

`AGENTS.md` es byte a byte igual a `CLAUDE.md` salvo dos líneas de encabezado, y
`scripts/check_agent_surfaces.py --write` lo regenera. No hay que editarlo a mano
ni cuenta como trabajo aparte: **todo cambio en `CLAUDE.md` se propaga con un
comando** y el gate de CI verifica que no se desincronicen.

---

## FASE 1 — Medición

### Totales

| Métrica | Valor |
|---|---|
| Bytes | 40 663 |
| Líneas | 857 |
| Caracteres | 35 242 |
| **Tokens estimados** | **~10 523** (±15 %) |
| Secciones (`##`) | 26 |

**Sobre la estimación de tokens.** No hay tokenizador de Claude en local y no se
hizo ninguna llamada de red. Se usó un modelo por partes: ~4 caracteres por token
para texto latino y ~1 token por carácter para emoji y dibujo de caja (`═ ─ │ 🔴
⚖️ 1️⃣`). La distinción importa porque el archivo está lleno de marcos ASCII-art y
emoji de menú: ocupan 1 carácter en pantalla, 3 bytes en UTF-8 y de 1 a 3 tokens.
Contarlos como `bytes/4` subestima; contarlos como caracteres los ignora. **Es una
estimación declarada, no una medición.** Confirma la magnitud del problema —
~10.5k tokens en cada turno— pero no debe usarse para facturar.

### Tabla por sección

| # | SECCIÓN | TOKENS | % TOTAL | CLASIFICACIÓN | ACCIÓN |
|---:|---|---:|---:|---|---|
| 1 | (cabecera del archivo) | 334 | 3.2 % | **OBSOLETA** + REDUNDANTE | Recortar a ~90 |
| 2 | IDENTIDAD DEL AGENTE | 197 | 1.9 % | **CRÍTICA** | Mantener |
| 3 | PROTOCOLO DE INICIO OBLIGATORIO | 465 | 4.4 % | **CRÍTICA** | Mantener íntegra |
| 4 | REGLA DE ORO: SIEMPRE OFRECE OPCIONES | 106 | 1.0 % | **CRÍTICA** | Mantener |
| 5 | MENÚ 1 — AUDITORÍA VVCA | 920 | 8.7 % | CONTEXTUAL · 62 CRÍTICA | Mover 858 · **rescatar 62** |
| 6 | MENÚ 2 — REDACCIÓN DE ESCRITOS | 876 | 8.3 % | CONTEXTUAL · 142 CRÍTICA | Mover 734 · **rescatar 142** |
| 7 | MENÚ 3 — INVESTIGACIÓN JURISPRUDENCIAL | 1 006 | 9.6 % | CONTEXTUAL · 142 CRÍTICA · 330 REFERENCIA | Mover 864 · **rescatar 142** |
| 8 | MENÚ 4 — ANÁLISIS DE DOCUMENTO | 307 | 2.9 % | CONTEXTUAL | Mover |
| 9 | MENÚ 5 — CONSULTA NORMATIVA | 296 | 2.8 % | CONTEXTUAL | Mover |
| 10 | MENÚ 6 — ESTRATEGIA PROCESAL | 282 | 2.7 % | CONTEXTUAL | Mover |
| 11 | MENÚ 7 — PLAZOS Y TÉRMINOS | 384 | 3.6 % | CONTEXTUAL | Mover |
| 12 | MENÚ 8 — COMPETENCIA ORGÁNICA | 504 | 4.8 % | CONTEXTUAL · 186 CRÍTICA | Mover 318 · **rescatar 186** |
| 13 | MENÚ 9 — HISTORIAL DE AUDITORÍAS | 156 | 1.5 % | **REDUNDANTE** (es `ls auditorias/`) | Mover |
| 14 | MENÚ 10 — CRONOLOGÍA DE EXPEDIENTE | 324 | 3.1 % | CONTEXTUAL + REDUNDANTE¹ | Mover |
| 15 | MENÚ 11 — BORRADOR DE ESCRITO | 138 | 1.3 % | CONTEXTUAL + REDUNDANTE¹ | Mover |
| 16 | MENÚ 12 — PREPARACIÓN DE TESTIGOS | 322 | 3.1 % | CONTEXTUAL + REDUNDANTE¹ | Mover |
| 17 | MENÚ 13 — REVISIÓN DE CONTRATO | 350 | 3.3 % | CONTEXTUAL + REDUNDANTE¹ | Mover |
| 18 | MENÚ 14 — TRIAJE DE NDAs | 302 | 2.9 % | CONTEXTUAL + REDUNDANTE¹ | Mover |
| 19 | MENÚ 15 — DEFENSA FISCAL | 490 | 4.7 % | CONTEXTUAL + REDUNDANTE¹ | Mover |
| 20 | PROTOCOLO ANTI-ALUCINACIÓN (NÚCLEO VVCA) | 860 | 8.2 % | **CRÍTICA** | Mantener íntegra |
| 21 | JERARQUÍA NORMATIVA | 120 | 1.1 % | **CRÍTICA** | Mantener |
| 22 | HERRAMIENTAS DISPONIBLES EN EL IDE | 959 | 9.1 % | Mixta: ~280 CRÍTICA / ~680 **OBSOLETA**+REFERENCIA | Recortar a ~280 |
| 23 | ESTILO DE RESPUESTA | 172 | 1.6 % | **CRÍTICA** | Mantener |
| 24 | ADVERTENCIA FIJA | 222 | 2.1 % | **REDUNDANTE**² | Puntero (~35) |
| 25 | REGLAS ABSOLUTAS | 318 | 3.0 % | **CRÍTICA** | Mantener íntegra |
| 26 | RETORNO AL MENÚ | 115 | 1.1 % | **CRÍTICA** | Mantener |
| | **TOTAL** | **10 523** | 100 % | | |

¹ Los menús 10-15 reproducen lo que ya dice la `description` de cada skill, y esas
descripciones **se cargan solas** en cada sesión (están en el listado de skills
disponibles). Hoy esa información se paga dos veces.

² Verificado: el texto exacto de la advertencia ya está en
`escrito-judicial/SKILL.md:111` y `medios-defensa-fiscal/SKILL.md:303` — es decir,
en las skills que efectivamente generan el escrito.

### Agregados

| Bloque | Tokens | % |
|---|---:|---:|
| Los 15 MENÚs | **6 657** | **63.3 %** |
| Todo lo demás | 3 868 | 36.8 % |

**Casi dos tercios del prompt permanente son los menús, y en una sesión típica se
usa uno.**

### Obsolescencia verificada (no supuesta)

Cada punto se comprobó contra el estado real del repositorio:

| Línea | Dice | Realidad |
|---|---|---|
| 728 | "ENTORNO PYTHON DE ESTE EQUIPO (**macOS** · Python 3.14.2)" | Windows 11 |
| 732-741 | "ejecuta SIEMPRE … `./venv/bin/python`" (6 veces) | `./venv/bin/python` **no existe**; es `./venv/Scripts/python.exe` |
| 740 | "Corpus: **47** PDFs" | `check_corpus.py` → **48** presentes de 48 esperados |
| 9 | "Se descartaron … **SQLite** … quedan como roadmap" | SQLite está implementado desde hoy (`itosturre/memoria/`) |
| 3 vs 856 | "Versión 2.1 · Julio 2026" | El pie dice "Prompt v2.0 · Junio 2026" |

La primera es la peor: **la instrucción operativa más repetida del archivo está
mal en esta máquina**, y se paga en cada turno para decir algo incorrecto.

---

## FASE 2 — Arquitectura propuesta

### El hallazgo que condiciona todo el diseño

Hay **cuatro reglas críticas enterradas dentro de cuerpos de menú**. Mover los
menús sin rescatarlas primero rompería el agente:

| Regla | Vive hoy en | Tokens | Por qué es crítica |
|---|---|---:|---|
| **Protocolo de citas** (denominación, clave, órgano, época, IUS, fecha de obligatoriedad, `[J]`/`[TA]`, "NUNCA inventar") | MENÚ 3 | 142 | Determina la forma de toda cita jurisprudencial. Anti-alucinación. |
| **Criterio reforzado en materia penal** (exigir 🟢 antes de insertar cita en escrito penal; vigencia CNPP vs. CFPP) | MENÚ 2 | 142 | Prisión preventiva, vinculación, prescripción. Impacto de libertad. |
| **Motor determinista de competencia** ("evita el error #1 de los LLM": contradicción → **Pleno Regional**, no SCJN; amparo directo → **TCC**, no SCJN) | MENÚ 8 | 186 | Equivocar el órgano pierde la instancia. |
| **Nota 🟡 NO VERIFICABLE ≠ 🔴 alucinación** | MENÚ 1 | 62 | Distinción de fondo del protocolo VVCA. |
| | | **532** | **Suben al núcleo permanente antes de mover nada** |

Nada de esto es opcional y nada de esto debería haber vivido nunca dentro de un
menú de interfaz.

### La separación

```
CLAUDE.md  (~3 350 tokens, SIEMPRE cargado)
   │   Identidad · protocolo de inicio · menú principal · reglas absolutas
   │   Protocolo anti-alucinación íntegro · jerarquía normativa
   │   Las 4 reglas rescatadas · comandos reales · estilo
   │
   ├──► Skill `menu-itosturre`     ← BAJO DEMANDA, determinista
   │       SKILL.md (router, ~400 tok)
   │       references/menu-01-vvca.md … menu-15-fiscal.md
   │       Se invoca cuando el usuario elige un número o describe la necesidad.
   │       Carga el router + UN menú, no los quince.
   │
   ├──► docs/                       ← CONSULTA PUNTUAL
   │       docs/ENTORNO.md          (setup, venv, bootstrap del corpus)
   │       docs/SJF_OPERATIVA.md    (notas de búsqueda en el portal)
   │       docs/ARQUITECTURA.md     (ya existe)
   │
   └──► Memoria contextual          ← HECHOS, NUNCA REGLAS
           Decisiones, correcciones, alertas, veredictos, huecos de corpus.
```

### El criterio de reparto (la regla que decide cada caso)

| Destino | Qué va ahí | Prueba |
|---|---|---|
| **`CLAUDE.md`** | Lo que debe ser verdad **aunque nadie lo pida** | ¿Puede el agente hacer daño si esto no está cargado? → sí ⇒ permanente |
| **Skill** | Lo que se necesita **entero cuando se necesita, y nunca antes** | ¿Es un procedimiento completo para una tarea concreta? |
| **`docs/`** | Lo que consulta un humano o se lee una vez | ¿Es setup, historia o detalle de plataforma? |
| **Memoria** | Lo que **pasó** | ¿Es un hecho fechado, no una instrucción? |

### Sobre tu pregunta de la memoria contextual

Preguntas si algunas instrucciones pueden pasar al sistema de memoria que
acabamos de construir. **Para instrucciones, no** — y coincido con el límite que
tú mismo pusiste, pero conviene decir el motivo técnico, porque es el mismo que
hace la memoria buena para lo suyo:

> **La recuperación es probabilística.** `recall()` devuelve top-k por BM25 bajo
> un techo de bytes. Una instrucción que solo rige cuando la búsqueda la
> devuelve es una instrucción que **a veces no rige**. Para una regla de
> seguridad o anti-alucinación, "casi siempre" es lo mismo que "no".

Una skill es distinta: una vez invocada, su contenido entra **completo y
determinista**. Por eso los menús pueden irse a una skill y las reglas no.

La memoria sí sustituye a `CLAUDE.md` en una cosa: **contexto histórico**. Pero
`CLAUDE.md` hoy casi no tiene historia (solo el changelog de la cabecera, 334
tokens). El grueso del ahorro no viene de la memoria, viene de la skill.

### Sobre las carpetas que propones

Propones `docs/ memory/ architecture/ development/ legal/ testing/`. Lo he
evaluado y **no lo recomiendo**: `docs/` tiene hoy 13 archivos planos y funciona;
cinco subdirectorios nuevos para mover dos documentos es estructura por
adelantado. `memory/` además chocaría con la regla `/memoria/` de `.gitignore`
que acabamos de añadir.

Propongo **dos archivos nuevos en `docs/` plano** y las referencias de menú
dentro de la propia skill (que es donde el mecanismo de carga bajo demanda ya
existe y no hay que inventar nada). Si `docs/` pasa de ~20 archivos, se
reorganiza entonces, con motivo.

---

## FASE 3 — Lo que NO puede desaparecer

Inventario completo por categoría. **Todo lo de esta lista permanece en
`CLAUDE.md`**, íntegro y textual.

### Seguridad
- Regla absoluta **#8**: nunca guardar datos de clientes reales en el repo.
- Regla absoluta **#9**: los datos del despacho nunca salen hacia APIs de
  terceros; `OpenNotebook.py` corre 100 % local. *(Y la coda: si algún día se
  añade un LLM externo al flujo de auditoría, esta regla es la primera a revisar.)*
- Regla absoluta **#4**: jamás commitear a `main`; ramas vía `git_strategy.sh`.

### Anti-alucinaciones
- **Protocolo anti-alucinación completo** (Reglas 1-7), 860 tokens, sin tocar una
  coma. Incluye la Regla 7 (corpus parcial no baja el score) y la distinción
  🟡 no verificable ≠ 🔴 refutada.
- Reglas absolutas **#1** (jamás inventar cita), **#2** (jamás promediar; un 🔴
  bloquea), **#3** (Capa 2 no es automatizable), **#7** (🚨 alerta procesal).
- **Protocolo de citas** — rescatado del MENÚ 3.
- **Nota 🟡 NO VERIFICABLE** — rescatada del MENÚ 1.

### Fuentes jurídicas
- **Jerarquía normativa** completa (8 niveles + pro persona, art. 1° CPEUM).
- **Regla 2**: artículos del corpus, nunca de memoria del modelo.
- **Regla 3**: audit (verifica citas) ≠ scraper SJF (mejora la estrategia). El SJF
  en vivo **no vota** el veredicto.
- **Criterio reforzado penal** — rescatado del MENÚ 2.

### Restricciones arquitectónicas
- **Motor determinista de competencia** — rescatado del MENÚ 8.
- Lista de **comandos reales** (qué existe de verdad vs. qué es roadmap). Esta
  distinción es anti-alucinación aplicada a la propia herramienta: sin ella el
  agente inventa flags.
- El reporte Word es **paso manual por caso**; no hay generador genérico.

### Reglas de edición y de trato
- Regla absoluta **#6**: si el operador corrige un criterio con su experiencia
  PJF, se incorpora **sin réplica**.
- Regla absoluta **#5**: siempre presentar opciones.
- **Regla de oro** (convertir preguntas abiertas en opciones numeradas).
- **Protocolo de inicio** y **menú principal**: definen el arranque de cada
  conversación. Se quedan **textuales** — si el menú principal se fuera a la
  skill, el agente tendría que invocarla antes de saludar.

### Comportamiento MCP
No aplica: **este repositorio no contiene un MCP** (§0.1 del informe de
auditoría). No hay instrucciones MCP que preservar.

### Tests
**Hueco detectado, no regresión.** `CLAUDE.md` no dice nada de pruebas; los
contratos viven en `docs/ARQUITECTURA.md` y `CONTRIBUTING.md`. Un agente que
edita código debería saber que existe un gate de regresión antes de mergear.
Propongo **añadir ~40 tokens** con los tres comandos de verificación. Es la única
adición neta de la propuesta.

---

## FASE 4 — Propuesta

### A. `CLAUDE.md` actual

26 secciones · 857 líneas · 40 663 bytes · **~10 523 tokens en cada turno**.
63 % son menús. Contiene 5 puntos de obsolescencia verificada y 4 reglas críticas
enterradas en cuerpos de menú.

### B. `CLAUDE.md` propuesto

```
# ITOSTURRE — AGENTE LEGAL MEXICANO · Sistema Prompt              (~90)
   Identidad, autoría, versión coherente. Sin changelog.

## IDENTIDAD DEL AGENTE                                           (197) intacta
## PROTOCOLO DE INICIO OBLIGATORIO + MENÚ PRINCIPAL               (465) intacto
## REGLA DE ORO: SIEMPRE OFRECE OPCIONES                          (106) intacta

## CÓMO SE ABREN LOS MENÚS                                        (~60)  ← NUEVO
   Al elegir un número o describir la necesidad → Skill(menu-itosturre).
   Instrucción directa, no inferencia.

## REGLAS DE CITA Y COMPETENCIA (rescatadas de los menús)          (532) ← NUEVO
   · Protocolo de citas                            (142, del MENÚ 3)
   · Criterio reforzado en materia penal           (142, del MENÚ 2)
   · Motor determinista de competencia · error #1  (186, del MENÚ 8)
   · Nota 🟡 NO VERIFICABLE ≠ 🔴 alucinación        ( 62, del MENÚ 1)

## PROTOCOLO ANTI-ALUCINACIÓN (NÚCLEO VVCA)                       (860) intacto
## JERARQUÍA NORMATIVA                                            (120) intacta

## HERRAMIENTAS (comandos REALES)                                 (~280)
   Comandos verificados, con el intérprete CORRECTO de esta máquina.
   + memoria_cli.py (hoy ausente).  Setup y bootstrap → docs/ENTORNO.md

## VERIFICACIÓN ANTES DE MERGEAR                                  (~40)  ← NUEVO
## ESTILO DE RESPUESTA                                            (172) intacto
## ADVERTENCIA FIJA → puntero a la skill que la emite             (~35)
## REGLAS ABSOLUTAS (1-9)                                         (318) intactas
## RETORNO AL MENÚ                                                (115) intacto
```

### C. Archivos nuevos

| Archivo | Contenido | Tokens |
|---|---|---:|
| `.claude/skills/menu-itosturre/SKILL.md` | Router: número/palabra clave → archivo de referencia | ~400 |
| `…/references/menu-01-vvca.md` … `menu-15-fiscal.md` | Un archivo por menú, texto **movido tal cual** | ~6 125 en total, **uno a la vez** |
| `docs/ENTORNO.md` | venv por plataforma, bootstrap del corpus, `requirements.txt`, gotchas | — |
| `docs/SJF_OPERATIVA.md` | Notas de búsqueda en el portal SJF (hoy MENÚ 3, 330 tok) | — |

`.agents/skills/menu-itosturre/` se genera solo con
`check_agent_surfaces.py --write`.

**Divulgación progresiva dentro de la skill.** Un `SKILL.md` con los quince menús
costaría 6 125 tokens al invocarse: mejor que pagarlos siempre, pero sigue siendo
caro. Con router + un archivo por menú, elegir la opción 3 cuesta **~400 (router)
+ ~1 006 (ese menú)**, no 6 657.

### D. Qué se mueve y adónde

| Origen | Tokens | Destino |
|---|---:|---|
| MENÚs 1-15 (menos lo rescatado y las notas SJF) | 5 795 | Skill `menu-itosturre/references/` |
| Notas operativas de búsqueda SJF (MENÚ 3) | 330 | `docs/SJF_OPERATIVA.md` |
| Entorno Python, venv, bootstrap (sección 22) | ~680 | `docs/ENTORNO.md` (**corregido a Windows**) |
| Changelog v2.1 de la cabecera | ~244 | Se elimina: es historia de git |
| Texto de la advertencia fija | ~187 | Ya está en las dos skills que la emiten |
| 4 reglas críticas | 532 | **Suben** a `CLAUDE.md` |

### E. Tokens antes / después

| | Antes | Después | Δ |
|---|---:|---:|---:|
| **Permanente (cada turno)** | **~10 523** | **~3 350** | **−7 173 (−68 %)** |
| Al usar un menú (una vez) | 0 extra | +~400 router +~300-1 000 menú | — |
| Peor caso: 3 menús en una sesión | 10 523 × N turnos | 3 350 × N + ~2 800 una vez | favorable desde el turno ~2 |

En una conversación de 20 turnos: **~210 000 tokens → ~67 000 + ~3 000 de menús
efectivamente usados**. El ahorro crece con la longitud de la sesión, que es
justo donde hoy duele.

Recordatorio de honestidad: son estimaciones con ±15 %, coherentes con el método
declarado en la Fase 1.

### F. Riesgos

| # | Riesgo | Gravedad | Mitigación |
|---|---|---|---|
| R1 | **Perder una regla crítica al mover un menú** | **Crítica** | Las 4 identificadas suben primero (Fase 3). Verificación: `grep` de cada frase clave sobre el `CLAUDE.md` nuevo antes de borrar nada del viejo. |
| R2 | La skill no se invoca cuando toca | Alta | Instrucción **directa** en el núcleo ("al elegir número → Skill"), no inferencia por descripción. Más `description` con los quince números y sus palabras clave. |
| R3 | Un turno extra de latencia al abrir un menú | Baja | Es el precio del diseño y se paga una vez por menú, no por turno. |
| R4 | Desincronización `CLAUDE.md` / `AGENTS.md` | Baja | `check_agent_surfaces.py` ya es gate de CI. |
| R5 | Deriva futura: reglas nuevas escritas dentro de menús | Media | La sección "REGLAS DE CITA Y COMPETENCIA" crea el sitio evidente donde ponerlas. |
| R6 | Menús fuera de la vista → se pudren sin que nadie lo note | Media | Es el riesgo real de todo movimiento a documentación. Sin mitigación automática; se asume. |
| R7 | El operador prefiere ver todo en un archivo | Media | **Decisión tuya.** El texto no se pierde: se mueve completo y sigue en el repo. |

### G. Posibles regresiones

| Comportamiento | ¿Cambia? | Por qué |
|---|---|---|
| Menú principal al iniciar conversación | **No** | El protocolo de inicio y el menú se quedan textuales |
| Ofrecer siempre opciones numeradas | **No** | Regla de oro intacta |
| Veredicto VVCA y semáforo | **No** | Protocolo anti-alucinación intacto; nada de esto depende de los menús |
| Exigir 🟢 en cita penal | **No** | Rescatado al núcleo |
| Competencia: contradicción → Pleno Regional | **No** | Rescatado al núcleo |
| Formato de cita jurisprudencial | **No** | Rescatado al núcleo |
| Advertencia al pie de escritos | **No** | Ya la emiten las skills que generan el escrito |
| Detalle del submenú 1-15 | **Sí** | Aparece tras invocar la skill, no de entrada |
| Comando de entorno Python | **Sí — a mejor** | Hoy dice `./venv/bin/python` en Windows, que **no funciona** |

Regresión candidata más seria: **R2**. Si la skill no se invocara, el agente
tendría el menú principal pero no el detalle de la opción elegida — degradaría a
preguntar en vez de desplegar el submenú. Molesto, no peligroso: ninguna regla de
seguridad ni de verificación depende de los menús una vez hechos los rescates.

---

## Plan de ejecución propuesto (para cuando lo apruebes)

Orden pensado para que **nunca exista un estado intermedio sin las reglas**:

| # | Paso | Verificación |
|---|---|---|
| 1 | Crear la skill con los 15 menús copiados **tal cual** | Los menús existen en dos sitios; nada perdido |
| 2 | Subir las 4 reglas críticas al núcleo de `CLAUDE.md` | `grep` de cada frase clave |
| 3 | `docs/ENTORNO.md` y `docs/SJF_OPERATIVA.md`, corrigiendo Windows y 48 PDFs | Comandos ejecutados de verdad |
| 4 | **Solo ahora** borrar los menús de `CLAUDE.md` | Script que compare frase a frase viejo vs. (nuevo + skill + docs): **cero pérdidas no intencionadas** |
| 5 | `check_agent_surfaces.py --write` | Gate en verde |
| 6 | Medir de nuevo con el mismo script | Confirmar ~3 350 |
| 7 | Prueba de comportamiento: arranque, elegir un menú, auditar una cita | Sin regresión |

El paso 4 merece énfasis: **el borrado es lo último y va detrás de un
verificador**, no de una lectura a ojo. Un archivo de 857 líneas no se poda
fiándose de la vista.

---

## Recomendación

Aprobar. El ahorro es real (~7 200 tokens por turno, −68 %) y el riesgo se
concentra en un punto identificable —las reglas enterradas en menús— que ya está
localizado y medido.

Un matiz honesto sobre el mérito: **lo mejor de este ejercicio no es el ahorro,
es haber encontrado que el criterio penal, el protocolo de citas y la regla de
competencia vivían dentro de menús de interfaz.** Eso era frágil antes de esta
propuesta y lo seguiría siendo sin ella.
