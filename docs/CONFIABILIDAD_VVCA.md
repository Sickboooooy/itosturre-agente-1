# Confiabilidad VVCA: SJF, Gold Set y trazabilidad

**Estado:** implementación inicial · 31-jul-2026
**Alcance:** controles de Capa 1; la pertinencia y decisión jurídica siguen bajo revisión humana.

## Acceso resiliente al Semanario Judicial

El scraper consulta exclusivamente las interfaces web públicas, en este orden:

1. `https://sjf2.scjn.gob.mx`
2. `https://sjfsemanal.scjn.gob.mx`
3. caché local por registro, cuando está habilitada y vigente

Cada intento conserva portal, URL, fecha, resultado y clase de fallo. Los estados son:

| Estado | Significado | Semáforo |
|---|---|---|
| `VERIFICADO` | El detalle fue extraído de un portal público o caché identificada | según contenido |
| `NO_ENCONTRADO` | Ambos portales respondieron de forma concluyente que no existe | 🔴 |
| `NO_VERIFICABLE` | Hubo bloqueo, desafío anti-bots no resuelto, red, timeout u otro fallo técnico | 🟡 |
| `LAYOUT_INCOMPATIBLE` | El portal respondió, pero cambió la estructura esperada | 🟡 |

Un fallo técnico nunca se presenta como “sin jurisprudencia”. La salida
`auditoria_vvca.json` usa el esquema 2.0 e incluye `trazabilidad_consulta` por tesis y
`consultas_busqueda` para búsquedas de alternativas.

### Por qué no se consume directamente el microservicio interno

La SCJN confirmó que el microservicio de tesis existe y sirve a las interfaces del SJF,
pero clasificó como reservados el catálogo de endpoints, autenticación, estructura de datos
y manejo de errores. También advirtió que el acceso directo fuera del sistema puede afectar
su infraestructura. Por ello Itosturre no descubre ni automatiza endpoints internos sin una
API oficialmente documentada y autorizada.

Fuente: [Resolución CT-VT/A-8-2025 del Comité de Transparencia de la SCJN](https://www.scjn.gob.mx/sites/default/files/resoluciones/2025-04/CT-VT-A-8-2025.pdf),
pp. 3–6.

## Gold Set jurídico

`tests/fixtures/vvca_gold_set_v1.json` es una **semilla sintética**, libre de datos de cliente.
Contiene casos de cita normativa exacta, fuente discrepante, coincidencia débil, rubro
jurisprudencial discrepante, tesis ausente del corpus, criterio superado, verificación parcial
y documento sin discrepancias.

Se evalúa con:

```bash
python scripts/evaluate_gold_set.py
python scripts/evaluate_gold_set.py --json
```

El resultado actual sirve como gate de regresión. **No demuestra todavía que los umbrales
85/60 estén empíricamente calibrados.** Para ello se necesita una segunda versión curada por
el operador con citas reales confirmadas contra fuentes oficiales, revisión doble y métricas
de falsos positivos y falsos negativos.

El arnés de esa segunda versión vive en `tests/fixtures/vvca_gold_set_v2.json` y documenta su
proceso en `docs/GOLD_SET_V2.md`. Mientras sea `curation_template` o `curation_draft`, el
evaluador devuelve código 2 para impedir que un borrador incompleto se confunda con evidencia
de calibración. El primer lote contenía 10 candidatos verdes reproducibles: la revisión humana
aprobó 9 y rechazó 1 como falso verde por evidencia insuficiente. El reporte v2 separa `false_green`, `false_red`,
subclasificación, sobreclasificación y matriz de confusión; un falso verde nunca se diluye en
la exactitud global.

El falso verde del artículo 42 CFF originó un guard adicional: el match de metadata ya no basta;
la evidencia debe contener el encabezado exacto del precepto. La ejecución corregida selecciona
la página 91 en lugar de la remisión interna de la página 105. El caso rechazado permanece en el
Gold Set como antecedente histórico y la salida remediada requiere revisión expresa independiente.

**Verde determinista (criterio del responsable, 3-oct-2026: opción A).** Con evidencia completa
(metadata `source+article`, encabezado exacto, fuente coincidente, ley identificada y no por
confirmar, sin derogación, unidad sin cotejar ni evidencia incompleta, distancia ≤ 0.25) la cita
normativa es 🟢 por regla determinista; la distancia queda como dato informativo
(`explicabilidad.score_similitud`). Detalle en `docs/PROTOCOLO_VVCA.md` §2. Consecuencia para el
Gold Set v2: `scripts/evaluate_gold_set.py` sigue evaluando `vvca_score`/`vvca_semaforo` con el
`input.distance` observado el 16-sep (sin cambios), pero de punta a punta los 9 verdes aprobados
salen 🟢 (antes CNPP 109/113/131 y CFF 38 salían 🟡 por distancia). La re-observación de
`input`/`candidate_evidence` es decisión del operador; el fixture no se edita aquí.

## Trazabilidad por referencia

`OpenNotebook.audit()` devuelve `traceability`, con una traza por cada referencia procesada,
incluidas las que no pudieron verificarse. Cada registro contiene:

- identificador estable `trace_id`;
- referencia y tipo;
- archivo, URL y localizador de la fuente;
- método y fecha de recuperación;
- estado: `verified`, `partial`, `not_verifiable` o `refuted` (una cita normativa solo queda
  `refuted` con prueba positiva de inexistencia en el cuerpo de la ley indexada, método
  `corpus_estructura`, D10; una tesis, con rubro discrepante o sentido invertido);
- score, semáforo y razón;
- SHA-256 del fragmento recuperado;
- metadata explicativa del cálculo;
- indicador obligatorio de revisión humana.

`vvca_full.py` conserva el conjunto en `<caso>/vvca_traceability.json`. El hash acredita que
el fragmento usado no cambió entre revisiones; no sustituye la captura, el texto fuente ni la
revisión de Capa 2.

## Gates offline

```bash
python -m unittest discover -s tests -p "test_*.py"
python scripts/evaluate_gold_set.py
python scripts/test_scraper_offline.py
```

La última orden valida tanto el parser de vigencia como el orden de fallback y la
clasificación de fallos, sin tocar el SJF.
