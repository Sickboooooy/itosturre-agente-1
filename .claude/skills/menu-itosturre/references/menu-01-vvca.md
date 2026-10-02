# MENÚ 1 — AUDITORÍA VVCA

Cuando el usuario seleccione **1** o mencione "validar", "auditar", "revisar respuesta de IA":

```
════════════════════════════════════════════════
  🔍 AUDITORÍA VVCA — Verificación Anti-Alucinación
════════════════════════════════════════════════

¿Qué quieres auditar?

  A) Texto completo de respuesta LLM (pégalo aquí)
  B) Solo una cita jurisprudencial específica
  C) Solo una referencia normativa (artículo + ley)
  D) Archivo de texto ya guardado en el proyecto

¿Con qué profundidad?

  1) Rápida — solo artículos vs. corpus (sin SJF en vivo)
  2) Completa — corpus + cotejo de tesis en SJF en vivo
  3) Ultra — completa + material para reporte Word (.docx)

[ ← Volver al menú principal: escribe 0 ]
```

**Después de recibir el texto a auditar (comandos REALES):**

```bash
# A/C) Texto o cita pegada:
python vvca_full.py --caso auditorias/<slug> --texto "<texto pegado>"

# D) Archivo guardado:
python vvca_full.py --caso auditorias/<slug> --borrador <ruta.md>

# Profundidad 2/3 (SJF en vivo): añade los registros IUS detectados en el texto
python vvca_full.py --caso auditorias/<slug> --borrador <ruta.md> \
    --contexto auditorias/<slug>/caso.json --registros 2024783 2003551
```

`vvca_full.py` corre: gate de cobertura (`check_corpus`) → audit RAG (`OpenNotebook.py`) →
scraper SJF (si hay `--registros`) → capturas RAG → `vvca_full.json`. El `.docx` final es un
paso manual por caso (ver MENÚ 1 → opción 1 más abajo).

**Formato de respuesta VVCA obligatorio** (leer del JSON `vvca_summary` y `retrieved_sources`):
```
════════════════════════════════════════════════
  VEREDICTO VVCA: [🟢/🟡/🔴] [razón]
════════════════════════════════════════════════

  Tesis auditadas: N
  ─ [🟢] cita_1 — VERIFICADA (Reg. XXXXX · rubro coincide)
  ─ [🔴] cita_2 — BLOQUEADA · rubro discrepante (USO PROHIBIDO)
  ─ [🟡] cita_3 — no encontrada en corpus local · verificar en SJF

  Artículos verificados: N
  ─ [🟢] art. 16 CPEUM — score 88 · encontrado en corpus
  ─ [🟡] art. 5 LGV  — NO VERIFICABLE · ley no indexada (re-indexar)

  Score RAG (arts) : 82.0 · Score SJF (tesis) : sin citas

════════════════════════════════════════════════
  ⚠️ Capa 1 (automatizada): 🟢 acredita existencia y
  ubicación del precepto en el corpus local, no que
  diga lo que el escrito afirma. La pertinencia al
  caso es Capa 2 — requiere tu criterio experto.
════════════════════════════════════════════════

¿Qué hacemos ahora?
  1) Generar reporte Word (paso manual por caso, ver auditorias/<slug>/)
  2) Auditar otro texto
  3) Redactar el escrito corregido
  4) Volver al menú principal
```

> **🟡 NO VERIFICABLE ≠ 🔴 alucinación.** Regla permanente: está en `CLAUDE.md`
> (sección REGLAS DE CITA Y COMPETENCIA).
>
> **Lectura del JSON (R4c):** `score_rag`/`score_sjf` en `null` significan "sin citas" en esa
> dimensión (`rag_sin_citas`/`sjf_sin_citas`) o "sin puntaje" (todas no verificables): nunca
> mostrarlos como 0.00. El alcance del 🟢 está en `alcance_verificacion` (y en
> `alcance_verificacion_tesis` para las tesis). Las alertas "🟡 PRECEPTO DEROGADO" (también de
> una fracción o inciso citados), "🟡 POSIBLE DEROGACIÓN", "🟡 UNIDAD CITADA NO COTEJADA",
> "🟡 EVIDENCIA INCOMPLETA" y "🟡 EVIDENCIA DE OTRO ORDENAMIENTO" se reportan tal cual; una
> cita de párrafo o fracción no se da por verificada con el solo encabezado del artículo
> (ver `docs/PROTOCOLO_VVCA.md`).

---

