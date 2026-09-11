# MENÚ 15 — DEFENSA FISCAL (skill `medios-defensa-fiscal`)

Cuando el usuario seleccione **15** o mencione "SAT", "crédito fiscal", "liquidación",
"recurso de revocación", "juicio de nulidad", "TFJA", "buzón tributario", "visita domiciliaria",
"PAE", "embargo fiscal", "caducidad", "prescripción" → invocar la skill **`medios-defensa-fiscal`**.

```
════════════════════════════════════════════════
  💰 DEFENSA FISCAL (SAT → revocación → TFJA → amparo)
════════════════════════════════════════════════

¿Qué resolución te notificó la autoridad?
  A) Crédito fiscal / liquidación (determinación de contribuciones)
  B) Multa o requerimiento
  C) Negativa o resolución recaída a una instancia del contribuyente

¿Qué priorizo?
  1) Solo mapa de vías y plazos
  2) Análisis de vicios de la resolución
  3) Borrador de agravios (todo lo anterior)
```
Produce: reloj procesal · mapa de vías con pros/contras (revocación OPTATIVA → juicio de
nulidad → amparo directo ante TCC, **nunca SCJN directo**) · vicios con semáforo (competencia,
notificación 134-138 CFF, 38 CFF, fiscalización 42-50 CFF, caducidad 67 / prescripción 146) ·
agravios **forma antes que fondo**. Fecha de notificación obligatoria (sin ella → 🚨).
Amparo SIEMPRE vía `router_competencia` (MENÚ 8). RISAT no indexado — no citar de memoria.
RMF, LFDC, PRODECON y LOTFJA indexadas (20-jul-2026, curso IA contadores) — ojo: la
RMF numera por "Regla N.N.N.", no por "Artículo", así que el match literal exacto por
número NO aplica ahí (solo recuperación semántica); verificar reglas específicas contra
el DOF antes de citarlas en un escrito.
Salida: `defensa-fiscal-<asunto>.md`.

---

