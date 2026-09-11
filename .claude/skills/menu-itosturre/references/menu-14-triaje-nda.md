# MENÚ 14 — TRIAJE MASIVO DE NDAs (skill `triage-nda`)

Cuando el usuario seleccione **14** o mencione "NDA", "acuerdo/convenio de confidencialidad",
"triaje", "clasificar contratos", "carpeta de NDAs" → invocar la skill **`triage-nda`**.

```
════════════════════════════════════════════════
  📑 TRIAJE MASIVO DE NDAs (3 flujos)
════════════════════════════════════════════════

Entrada: carpeta con los NDAs (.docx/.pdf/.md). PDF escaneado → OCR (skill pdf).

Rutea cada NDA a:
  🟢 Aprobación Estándar → firma electrónica del apoderado (sin abogado)
  🟡 Revisión del Asesor → abogado júnior (con puntos ya anotados)
  🔴 Revisión Completa   → abogado sénior (términos inusuales: PI, no competencia…)
```
Marco MX: LFPDPPP (datos), secreto industrial, libertad de trabajo (art. 5 CPEUM).
No se promedia: un solo 🔴 manda el NDA a Revisión Completa. Salida: `triaje-nda-reporte.md`.

---

