# MENÚ 12 — PREPARACIÓN DE TESTIGOS / INTERROGATORIO (skill `prep-testigos`)

Cuando el usuario seleccione **12** o mencione "testigo", "interrogatorio", "contrainterrogatorio",
"desahogo", "audiencia de juicio" → invocar la skill **`prep-testigos`**.

```
════════════════════════════════════════════════
  🗣️ PREPARACIÓN DE TESTIGO / INTERROGATORIO
════════════════════════════════════════════════

¿El testigo es?
  A) Propio (de la firma) → interrogatorio directo (acreditar)
  B) De la contraparte    → contrainterrogatorio (confrontar)

¿Qué necesitas?
  1) Perfil del testigo + relevancia para la litis
  2) Documentos clave del expediente para la audiencia
  3) Guion de preguntas (acreditación → contrainterrogatorio)
  4) Riesgos del propio testigo + mitigación legítima
  5) Guía completa (todo lo anterior)
```
Marco: arts. 371-375 CNPP (juicio oral). 🚫 Nunca prepara testimonio falso — solo declarar la
verdad con claridad. Salida: `prep-testigo-<nombre>.md`.

---

