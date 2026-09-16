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
| `NO_VERIFICABLE` | Hubo bloqueo, red, timeout u otro fallo técnico | 🟡 |
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
de calibración. El borrador contiene ya 10 candidatos verdes reproducibles, pero siguen en
`pending` hasta el cotejo expreso del operador. El reporte v2 separa `false_green`, `false_red`,
subclasificación, sobreclasificación y matriz de confusión; un falso verde nunca se diluye en
la exactitud global.

## Trazabilidad por referencia

`OpenNotebook.audit()` devuelve `traceability`, con una traza por cada referencia procesada,
incluidas las que no pudieron verificarse. Cada registro contiene:

- identificador estable `trace_id`;
- referencia y tipo;
- archivo, URL y localizador de la fuente;
- método y fecha de recuperación;
- estado: `verified`, `partial`, `not_verifiable` o `refuted`;
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
