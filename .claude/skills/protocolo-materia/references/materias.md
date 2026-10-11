# Materias del catálogo y preparación del corpus

Hay 9 materias en el catálogo del simulador de destino: `civil`, `penal`, `laboral`, `mercantil`,
`familiar`, `administrativo`, `constitucional`, `consumidor` y `seguridad_social`. Fiscal ya tiene
sus protocolos propios. La clave del protocolo es `<materia>_materia` y la versión empieza en `v1`.

La preparación de abajo es la del 10-oct-2026. **No la des por buena: `preparar` la comprueba
contra el último reporte de vigencia.** 🟡 exige cotejo antes de citar (Regla 8). 🔴, o una ley que
no aparece en el índice, detiene el bucle hasta que decida el abogado (Reglas 7 y 8).

| Materia | Leyes en el RAG (vigencia) | Huecos posibles | ¿Lista? |
|---|---|---|---|
| penal | CPEUM, CPF, CNPP, Código Penal de Jalisco, LFDO, LNEP, Ley Nacional de Extinción de Dominio, LGV | — | Hecha (v1, F1) |
| constitucional | CPEUM, Ley de Amparo, LOPJF, Constitución de Jalisco; CADH ⚪ y PIDCP ⚪ | Ley reglamentaria del artículo 105 (no indexada) | Hecha (v1, F3) |
| laboral | LFT, LFTSE | Ley orgánica del Centro Federal de Conciliación | Sí |
| administrativo | LFPA, LFPCA, LOTFJA, LPA de Jalisco, Ley de Justicia Administrativa de Jalisco | Ley General de Responsabilidades Administrativas | Sí |
| seguridad_social | LSS, Ley del ISSSTE, Ley del INFONAVIT | — | Sí |
| familiar | CNPCF, CCF, Código Civil de Jalisco, LGDNNA; Convención sobre los Derechos del Niño ⚪ | — | Sí |
| civil | CCF, Código Civil de Jalisco, CNPCF, Ley del Notariado de Jalisco; CFPC 🟡, CPC de Jalisco 🟡, Registro Civil de Jalisco 🟡 | Cotejo de las tres en 🟡 | Sí, con cotejo |
| consumidor | Reglamento de la LFPC; **LFPC 🔴** (la versión indexada no está vigente) | Re-indexar la LFPC vigente | **No** |
| mercantil | — | **Código de Comercio, LGSM y LGTOC no están indexados** | **No** |

⚪ = el reporte de vigencia no tiene una fuente oficial con qué compararlo (tratados).

## Cómo llenar `config.json` para una materia nueva

`preparar` crea `config.json` con los campos vacíos. Antes de `prompts`, el orquestador los llena:

- `leyes`: nombres o etiquetas de las leyes tal como aparecen en el reporte de vigencia (`fuente`,
  `etiqueta` o `nombre_oficial`). Ejemplos: «LEY DE AMPARO», «CPEUM», «Ley Federal del Trabajo».
- `ley_principal`: la frase de cita de la ley principal, tal como iría tras el número de artículo.
  Por ejemplo, «de la Ley Federal del Trabajo» o «del Código Civil Federal». Con ella se arma el
  fixture del artículo inexistente.
- `ley_no_indexada` (opcional): la frase de cita de una ley que la materia necesita y no está en el
  corpus. Sin ella, el fixture usa una ley ficticia.
- `alcance` (opcional): una frase si la materia es más estrecha que su nombre.
- `temas_a1`: qué debe mapear A1 en las secciones I, II, III y V. La IV casi no necesita el RAG.
- `temas_a2`: los temas de jurisprudencia. `advertencias_a2`: trampas de época o de ley abrogada.
- `contexto_a5`: lo que A5 debe saber sin verificarlo, como reformas recientes, discrepancias que
  halló A1 o tesis que se dejaron fuera a propósito.
- `presupuesto` y `modelos`: los topes de cada agente y el modelo con que corre. «heredar» usa el
  del orquestador.

En `ejemplos/` están las configuraciones con que se corrieron penal y constitucional.
