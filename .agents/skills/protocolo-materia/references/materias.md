# Materias del catálogo y preparación del corpus

Hay 9 materias en el catálogo del simulador de destino: `civil`, `penal`, `laboral`, `mercantil`,
`familiar`, `administrativo`, `constitucional`, `consumidor` y `seguridad_social`. Fiscal ya tiene
sus protocolos propios. La clave del protocolo es `<materia>_materia` y la versión empieza en `v1`.

La preparación de abajo es la del 10-oct-2026. **No la des por buena: `preparar` la comprueba
contra el último reporte de vigencia.** 🟡 exige cotejo antes de citar (Regla 8). 🔴, o una ley que
no aparece en el índice, detiene el bucle hasta que decida el abogado (Reglas 7 y 8).

**Enfoque nacional (11-oct-2026):** la tabla lista solo normas que rigen en todo el país. Las leyes de
Jalisco que hay en el corpus no entran en los protocolos. Lo local se remite a la ley de la entidad
del asunto (ver `a3_redaccion.md`).

| Materia | Normas nacionales en el RAG (vigencia) | Lo que depende de cada entidad o falta | Estado (11-oct-2026, tarde) |
|---|---|---|---|
| penal | CPEUM, CNPP, CPF (en lo federal), LFDO, LNEP, Ley Nacional de Extinción de Dominio, LGV; CADH ⚪ y PIDCP ⚪ | Delitos del fuero común: código penal de la entidad | v2 nacional en EXITO |
| constitucional | CPEUM, Ley de Amparo, LOPJF; CADH ⚪ y PIDCP ⚪ | Ley reglamentaria del artículo 105 (no indexada) | v1 en EXITO, ya nacional |
| laboral | LFT, LFTSE, CPEUM | Ley orgánica del Centro Federal de Conciliación (no indexada) | v1 en EXITO, ya nacional |
| administrativo | LFPA, LFPCA, LOTFJA, CPEUM | Procedimiento y justicia administrativa locales; Ley General de Responsabilidades Administrativas (no indexada) | v2 nacional en EXITO |
| seguridad_social | LSS, Ley del ISSSTE, Ley del INFONAVIT, LFT | Ley de los Sistemas de Ahorro para el Retiro (no indexada) | v1 en EXITO, ya nacional |
| familiar | CNPCF, LGDNNA, CPEUM, CCF (en lo federal o como referencia); Convención sobre los Derechos del Niño ⚪ | Derecho familiar sustantivo: código civil o familiar de la entidad | v2 nacional en EXITO |
| civil | CNPCF, CCF (en lo federal o como referencia), CPEUM; CFPC 🟡 (abrogado, con vigencia transitoria) | Derecho civil sustantivo: código civil de la entidad | v2 nacional en EXITO (la v1 de Jalisco quedó archivada) |
| consumidor | LFPC, Reglamento de la LFPC, CPEUM, CNPCF, LFPA, LFPCA | Ordenamiento procesal civil local, supletorio del arbitraje de estricto derecho; Código de Comercio (no indexado) | v1 nacional en EXITO (el 🔴 de la LFPC era el acuerdo anual de montos, no una reforma) |
| mercantil | — | **Código de Comercio, LGSM y LGTOC no están indexados** | **No** |

⚪ = el reporte de vigencia no tiene una fuente oficial con qué compararlo (tratados).

## Cómo llenar `config.json` para una materia nueva

`preparar` crea `config.json` con los campos vacíos. Antes de `prompts`, el orquestador los llena:

- `leyes`: solo normas nacionales (`preparar` bloquea las locales). Van con sus nombres o etiquetas tal como aparecen en el reporte de vigencia (`fuente`,
  `etiqueta` o `nombre_oficial`). Ejemplos: «LEY DE AMPARO», «CPEUM», «Ley Federal del Trabajo».
- `ley_principal`: la frase de cita de la ley principal, tal como iría tras el número de artículo.
  Por ejemplo, «de la Ley Federal del Trabajo» o «del Código Civil Federal». Con ella se arma el
  fixture del artículo inexistente.
- `ley_no_indexada` (opcional): la frase de cita de una ley que la materia necesita y no está en el
  corpus. Sin ella, el fixture usa una ley ficticia.
  Elige una ley nacional o federal, nunca una local: el enfoque es nacional.
- `alcance` (opcional): una frase si la materia es más estrecha que su nombre.
- `temas_a1`: qué debe mapear A1 en las secciones I, II, III y V. La IV casi no necesita el RAG.
- `temas_a2`: los temas de jurisprudencia. `advertencias_a2`: trampas de época o de ley abrogada.
- `contexto_a5`: lo que A5 debe saber sin verificarlo, como reformas recientes, discrepancias que
  halló A1 o tesis que se dejaron fuera a propósito.
- `presupuesto` y `modelos`: los topes de cada agente y el modelo con que corre. «heredar» usa el
  del orquestador.

En `ejemplos/` están las configuraciones con que se corrieron penal y constitucional.
