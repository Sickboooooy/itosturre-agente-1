# Protocolo VVCA — Especificación técnica

VVCA = **V**erificación · **V**alidación · **C**ontextualización · **A**uditabilidad.
Este documento describe cómo `OpenNotebook.py` + `scoring_vvca.py` materializan el Protocolo
Anti-Alucinación del prompt Itosturre. Es la referencia de implementación, no el prompt.

## 1. Dos scores independientes (no se promedian)

| Score | Qué mide | Fuente |
|---|---|---|
| `score_rag` | Artículos citados vs. corpus indexado | ChromaDB (estático) |
| `score_sjf` | Tesis citadas vs. SJF | scraper / corpus local de jurisprudencia (dinámico) |

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
  número → `🟡 LEY NO IDENTIFICADA`, nunca 🟢 ciego. (Guard P0 — antes un "Art. 5" suelto
  podía matchear el Art. 5 de cualquier código y pasar verde.)
- **No encontrado con la fuente esperada** → 🔴 alerta crítica (posible alucinación).

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
