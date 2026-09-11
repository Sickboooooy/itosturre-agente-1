# MENÚ 10 — CRONOLOGÍA DE EXPEDIENTE (skill `cronologia-expediente`)

Cuando el usuario seleccione **10** o mencione "cronología", "línea de tiempo", "expediente",
"constancias", "foliado", "fojas" → invocar la skill **`cronologia-expediente`**.

```
════════════════════════════════════════════════
  📑 CRONOLOGÍA DE EXPEDIENTE (litigio)
════════════════════════════════════════════════

¿Qué me das de entrada?
  A) Carpeta con el expediente digitalizado (PDF/imágenes)
  B) Un solo PDF (constancias en un archivo)
  C) Expediente + caso.json (órgano, partes, materia)

¿Qué priorizo?
  1) Línea de tiempo completa foja por foja
  2) Solo plazos por vencer y pruebas omitidas
  3) Solo inconsistencias fácticas entre las partes
  4) Todo (cronología + plazos + inconsistencias + pruebas)
```
Produce: tabla cronológica anclada a foliado · inconsistencias 🔴/🟡/⚪ · plazos 🚨 · pruebas.
Si el PDF está escaneado → OCR con skill `pdf` primero. Salida: `cronologia-<expediente>.md`.

---

