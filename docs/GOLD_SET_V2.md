# Gold Set VVCA v2 — curaduría jurídica

**Estado:** arnés implementado; 10 candidatos verdes reproducibles y pendientes de revisión del operador.
**Archivo:** `tests/fixtures/vvca_gold_set_v2.json`.

## Propósito

La versión 1 es una semilla sintética útil para regresión, pero no permite afirmar que los
umbrales 85/60 estén calibrados empíricamente. La versión 2 añade procedencia, revisión humana
y métricas explícitas de falsos verdes y falsos rojos.

Este conjunto cubre **citas VVCA**. El Gold Set de cómputo de plazos será independiente y solo
se construirá cuando exista una fuente versionada de días inhábiles y suspensiones del CJF.
Mezclar ambos problemas produciría una apariencia de cobertura que hoy no existe.

## Regla de verdad de referencia

Un caso solo cuenta como aprobado cuando un abogado revisa la fuente pública y completa:

- `source_type`: `DOF`, `SJF` o `corpus_oficial`;
- `source_locator`: URL, registro, artículo, página o combinación suficiente para repetir el cotejo;
- `verified_at`: fecha ISO `AAAA-MM-DD`;
- `reviewed_by`: identificador del revisor, sin datos de cliente;
- `review_status`: `approved`.

Los estados `pending` y `rejected` pueden guardarse durante la curaduría, pero impiden que el
dataset se presente como listo para calibración. No se admiten escritos ni expedientes reales:
solo fuentes jurídicas públicas y observaciones técnicas despersonalizadas.

La etiqueta de un caso `pending` es solo una **propuesta de clasificación**. No adquiere valor
de verdad jurídica hasta que el operador coteja la versión oficial vigente, completa los campos
de revisión y cambia expresamente el estado a `approved`. La coincidencia con el PDF local
demuestra reproducibilidad contra esa instantánea del corpus; no sustituye la comprobación de
vigencia en la fuente oficial.

## Avance de curaduría

- 10/10 candidatos 🟢 preparados: 4 de Ley de Amparo, 3 de CNPP y 3 de CFF;
- 0/10 candidatos 🟢 aprobados por el operador;
- 0/10 candidatos 🟡 preparados;
- 0/10 candidatos 🔴 preparados.

Cada candidato verde conserva `audit_input`, fecha de observación, score observado, método de
recuperación y `trace_id` en `candidate_evidence`. Esos datos permiten repetir el hallazgo sin
convertir automáticamente la observación técnica en aprobación jurídica.

### Lote verde listo para revisión

| Caso | Referencia candidata | Instantánea local | Score observado |
|---|---|---|---:|
| `green_amparo_art_17` | Ley de Amparo, art. 17 | pág. PDF 8 | 86 |
| `green_amparo_art_61` | Ley de Amparo, art. 61 | pág. PDF 23 | 88 |
| `green_amparo_art_108` | Ley de Amparo, art. 108 | pág. PDF 40 | 87 |
| `green_amparo_art_124` | Ley de Amparo, art. 124 | pág. PDF 45 | 86 |
| `green_cnpp_art_109` | CNPP, art. 109 | pág. PDF 29 | 86 |
| `green_cnpp_art_113` | CNPP, art. 113 | pág. PDF 32 | 87 |
| `green_cnpp_art_131` | CNPP, art. 131 | pág. PDF 37 | 87 |
| `green_cff_art_38` | CFF, art. 38 | pág. PDF 83 | 85 |
| `green_cff_art_42` | CFF, art. 42 | pág. PDF 105 | 86 |
| `green_cff_art_137` | CFF, art. 137 | pág. PDF 205 | 85 |

Para aprobar un renglón, el operador debe cotejar el artículo contra la versión oficial vigente,
confirmar que el localizador y la etiqueta verde son correctos, y llenar `verified_at` y
`reviewed_by`. Si existe reforma, error de página o ambigüedad, se corrige o se marca `rejected`;
nunca se aprueba por el solo hecho de que el score sea verde.

## Caso mínimo

```json
{
  "id": "identificador_estable",
  "category": "cita_verdadera",
  "component": "score",
  "input": {
    "distance": 0.1,
    "source_match": true,
    "has_source_file": true
  },
  "expected": {
    "semaforo": "🟢"
  },
  "ground_truth": {
    "source_type": "DOF",
    "source_locator": "[COMPLETAR: URL + ordenamiento + artículo]",
    "verified_at": "[COMPLETAR: AAAA-MM-DD]",
    "reviewed_by": "[COMPLETAR: revisor]",
    "review_status": "pending"
  }
}
```

La etiqueta esperada definitiva la fija el operador después del cotejo. Antes de eso puede
existir una etiqueta candidata, siempre con `review_status: pending`. El score numérico no es
verdad jurídica y por eso es opcional en v2: exigirlo haría circular la calibración. El modelo
no llena por sí mismo los campos de aprobación ni cambia `review_status` a `approved`.

## Meta mínima

- 30 casos aprobados: 10 verdes, 10 amarillos y 10 rojos;
- representación de normativa exacta, fuente discrepante, ley no identificada, corpus
  incompleto, rubro jurisprudencial discrepante y vigencia perdida;
- cero datos de cliente;
- cero falsos verdes para considerar superado el gate;
- revisión de todo cambio de umbral contra v1 y v2.

## Evaluación

```bash
python scripts/evaluate_gold_set.py
python scripts/evaluate_gold_set.py --file tests/fixtures/vvca_gold_set_v2.json
python scripts/evaluate_gold_set.py --file tests/fixtures/vvca_gold_set_v2.json --json
```

Mientras el archivo conserve `status: curation_template` o `curation_draft`, el comando sale
con código `2`: la estructura puede ser válida, pero todavía no es un gate jurídico. Solo
`operator_curated`, con el mínimo y la distribución 10/10/10 aprobados, puede aspirar a
`release_ready: true`.

## Métricas

- `false_green`: el sistema produjo 🟢 cuando la verdad de referencia era 🟡 o 🔴;
- `false_red`: el sistema produjo 🔴 cuando la verdad de referencia era 🟢;
- `underclassified`: el sistema asignó menos riesgo que el operador;
- `overclassified`: el sistema asignó más riesgo que el operador;
- `confusion_matrix`: cruce completo esperado → observado;
- `by_category`: aciertos y fallos por familia jurídica.

La exactitud agregada nunca sustituye la regla bloqueante: un falso verde conserva visibilidad
propia y no se diluye en un promedio.
