# MENÚ 3 — INVESTIGACIÓN JURISPRUDENCIAL

Cuando el usuario seleccione **3** o mencione "buscar", "tesis", "jurisprudencia", "SJF":

```
════════════════════════════════════════════════
  📚 INVESTIGACIÓN JURISPRUDENCIAL
════════════════════════════════════════════════

¿Qué buscas?
  A) Tesis por tema o palabras clave
  B) Tesis por número de registro (IUS)
  C) Tesis por clave (ej: 1a./J. 15/2020)
  D) Jurisprudencia obligatoria sobre un artículo específico
  E) Criterios recientes de un órgano (sala, pleno, TCC)
  F) Contradicciones de tesis sobre un tema

¿Qué materia?
  1) Común / Constitucional   3) Civil      5) Laboral      7) Fiscal
  2) Penal                    4) Mercantil  6) Administrativa  8) Todas

¿Qué época?
  A) Solo Undécima Época (vigente — desde 2021)
  B) Décima + Undécima Época
  C) Todas las épocas
```

**Herramienta real (scraper SJF, Playwright):**
```bash
cd services/itosturre-scraper
npx ts-node --esm vvca_audit.ts --out <dir> --contexto caso.json <IUS1> <IUS2> ...
```

**Presentar resultados:**
```
Encontré [N] tesis relevantes:
──────────────────────────────────────────────
1. [CLAVE] · [Tipo: J/TA] · [Sala/Órgano]
   "[RUBRO]"
   Registro: [IUS] · Época: [X] · Publicación: [fecha]
   Criterio: [resumen en 2 líneas]
──────────────────────────────────────────────

¿Qué hago con estos resultados?
  1) Ver texto completo de la tesis [número]
  2) Insertar cita en el escrito que estoy redactando
  3) Auditar todas las citas encontradas (VVCA)
  4) Buscar más tesis sobre este tema
  5) Exportar resultados a .txt
```

**Protocolo de citas** — regla permanente, está en `CLAUDE.md` (sección REGLAS DE CITA
Y COMPETENCIA): qué campos lleva toda tesis y la prohibición de inventarlos.

**Notas operativas de búsqueda en SJF** — ver `docs/SJF_OPERATIVA.md`.

---

