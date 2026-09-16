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
2. `tesis_no_encontradas > 0` → **🟡** — ausentes del corpus local; *no confirmadas como falsas*
   (el corpus puede estar incompleto).
3. `score_rag < 70` → **🟡** — artículos con verificación insuficiente.
4. en otro caso → **🟢**.

La distinción del punto 1 vs. 2 es crítica: "rubro discrepante" (peligroso) ≠ "no encontrada"
(corpus incompleto). Nunca se tratan igual.

## 4. Guards de resolución de artículos (anti-falso-veredicto)

El parser resuelve la ley de cada artículo en cascada de prioridad:

1. **Ventana local** — derecha (100 chars) → línea → amplia (±150).
2. **Alias** case-sensitive (`LAW_ALIASES`).
3. **Sticky-law** (`resolve_law_source_backward`) — último recurso: la ley del **encabezado
   más cercano hacia atrás** (≤600 chars). Maneja el patrón legal de agrupar artículos bajo
   un título de ley:

   ```
   ### A. Orden constitucional mexicano (CPEUM)
   - Art. 16 — ...
   - Art. 19 — ...
   ```

   Estos se marcan `law_inferred=True` (auditable: resueltos por sección, no por adyacencia).

Comportamiento al auditar (`audit()`):

- **Ley identificada pero ausente del corpus** → `🟡 NO VERIFICABLE`. *No* se reporta como
  "alucinación": el corpus simplemente no la contiene. (Guard P0 — antes producía un falso 🔴
  que tachaba de falsa una cita válida, p. ej. LGV/PIDCP.)
- **Artículo sin ley identificable** (ni siquiera por sticky-law) que igual hace match por
  número → `🟡 LEY NO IDENTIFICADA`, nunca 🟢 ciego. El score del propio source se **capa a
  84** (🟡) en `build_vvca` para que el semáforo tampoco quede verde. (Guard P0 — antes un
  "Art. 5" suelto podía matchear el Art. 5 de cualquier código y pasar verde.)
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
