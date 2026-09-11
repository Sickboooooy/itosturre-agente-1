# Benchmark de memoria contextual — Itosturre

Generado por `scripts/benchmark_memoria.py` · 131 eventos reales en memoria · base de 312.0 KB.

Los tokens son una **estimación** (bytes ÷ 4 para prosa en español), no una tokenización real. Sirven para comparar órdenes de magnitud, no para facturar.

## 1. Acierto de recuperación — la métrica que manda

Ahorrar contexto perdiendo la respuesta correcta no es una mejora. Diez preguntas reales cuya respuesta está en la memoria histórica del proyecto:

| Pregunta | Acierto | Eventos | Bytes |
|---|:--:|--:|--:|
| que me corrigio Fabian sobre la via contra desercion de pr | ✅ | 4 | 3283 |
| clave de Anthropic expuesta en produccion sin resolver | ✅ | 5 | 3362 |
| rama reconcile-jurisprudencia bloqueador SJF | ✅ | 5 | 2640 |
| gotcha del IDE Antigravity al mover archivos en services | ✅ | 5 | 4086 |
| que bot de Telegram usa el canal | ✅ | 3 | 3086 |
| leyes que faltaban del corpus LGV PIDCP | ✅ | 5 | 3495 |
| formato al recomendar correcciones tras auditoria VVCA | ✅ | 7 | 3905 |
| caso de derechos humanos del 28 de mayo de 2004 | ✅ | 5 | 3981 |
| skill fiscal escrita pero sin commitear | ✅ | 4 | 3181 |
| bug de npx en vvca_full.py en Windows | ✅ | 5 | 3607 |

**Acierto: 10/10** · latencia media 0.50 ms (máx. 0.76 ms) · 3462 bytes de media por consulta.

## 2. ANTES vs. DESPUÉS

| | ANTES (memorias .md) | DESPUÉS (recuperación selectiva) |
|---|---|---|
| Unidades | 17 archivos | top-k acotado por presupuesto |
| Contexto por consulta | 76.1 KB (cargar todo) | 3462 B (media) |
| Tokens aprox. | ~19,488 | ~865 |
| Eventos enviados | todos | 4-7 |
| Latencia | lectura de 17 archivos | 0.50 ms |
| Selectividad | ninguna | BM25 + importancia + recencia |

**Ahorro de contexto por consulta: 95.6%.**

Matiz honesto: hoy `MEMORY.md` (4.1 KB) se carga en cada sesión y los archivos completos solo al consultarlos. La comparación de arriba es contra el coste de **responder una pregunta concreta**, que es el caso de uso que este sistema sustituye.

## 3. Escenarios del encargo

| Escenario | Antes | Después |
|---|---|---|
| Decisión antigua entre 10,000 eventos | no existía | recuperada en 0.68 ms |
| Tras muchos eventos | degradación lineal | 101 B, 1 eventos |
| Sesión nueva | `MEMORY.md` completo | snapshot de 1129 B |
| Tras compactación | **todo perdido** | snapshot restaurable de 1129 B |
| Errores previos | no existía | consulta por `error_detected` |
| Archivos modificados | no existía | consulta por `file_path` |

## 4. Escala

- 10,000 eventos sintéticos ingeridos en 830 ms.
- Base resultante: 4124.0 KB.
- Consulta sobre esos 10,000 eventos: **0.68 ms**, devuelve **101 bytes**.

Es la promesa del encargo comprobada: **la base crece, el contexto no**. Con 10,000 eventos en disco, lo que llega al modelo sigue siendo 101 bytes.

## 5. Snapshot de continuidad

- 131 eventos condensados en **1129 bytes** (0.80 ms).
- No lleva datos, lleva referencias: un resumen por sección más el comando que recupera el detalle. Por eso no crece con la base.

## 6. Coste de los hooks de captura automática

| Camino | Trabajo propio | Bloquea el turno |
|---|---:|---|
| Descarte (lectura, comando trivial) | 0.001 ms | no (`async`) |
| Captura (edición → escribe en SQLite) | 5.65 ms | no (`async`) |
| Snapshot (`PreCompact`) | ~23 ms | sí, una vez por compactación |
| Restauración (`SessionStart`) | ~20 ms | sí, una vez por sesión |

**El arranque del proceso domina y no es nuestro.** Medido en el shell: ~140 ms de pared por hook, de los que ~45 ms son arrancar el intérprete a secas. El trabajo propio es tres órdenes de magnitud menor en el camino de descarte, que es el habitual.

Por eso el diseño evita pagarlo en vez de intentar reducirlo:

1. **El `matcher` filtra antes de lanzar nada.** `Read`, `Grep` y `Glob` no están en él: para una lectura el hook no llega a existir.
2. **La captura es `async`.** No bloquea el turno; el coste de pared sale del camino crítico.
3. Solo `SessionStart` y `PreCompact` son síncronos, y ocurren una vez por sesión y por compactación respectivamente.

## 7. El otro frente: el prompt permanente

La memoria no reduce el prompt base — son problemas distintos y se atacaron por separado. `CLAUDE.md` pasó de ~10 523 a ~4 372 tokens por turno al mover el detalle de los quince menús a la skill `menu-itosturre` y el entorno a `docs/ENTORNO.md` (ver `docs/propuesta-adelgazar-claude-md.md`).

Sumando ambos frentes: ~6 150 tokens menos **por turno** de prompt permanente, más ~95 % menos de contexto cada vez que hay que recordar algo del historial.
