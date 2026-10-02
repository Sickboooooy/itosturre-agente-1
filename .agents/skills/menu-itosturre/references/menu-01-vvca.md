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
  ─ [🟢] cita_1 — VERIFICADA (Reg. XXXXX · rubro coincide literalmente)
  ─ [🔴] cita_2 — BLOQUEADA · rubro discrepante (USO PROHIBIDO)
  ─ [🟡] cita_3 — no encontrada en corpus local · verificar en SJF

  Artículos verificados: N
  ─ [🟢] art. 16 CPEUM — score 88 · encontrado en corpus
  ─ [🟡] art. 5 LGV  — NO VERIFICABLE · ley no indexada (re-indexar)
  ─ [🟡] art. N ley  — NO LOCALIZADO · no se acredita que no exista (cotejar)
  ─ [🟡] art. N ley  — POSTERIOR AL ÚLTIMO ARTÍCULO de la versión indexada
  ─ [🔴] art. N ley  — INEXISTENTE ACREDITADO · <la prueba, con la página>

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
> **Artículo no localizado en una ley indexada (D10, criterio del responsable del
> 2-oct-2026):** solo es 🔴 con prueba positiva de inexistencia en el cuerpo de la ley, y la
> prueba se abstiene ante cualquier ambigüedad. La alerta "🔴 ARTÍCULO INEXISTENTE
> ACREDITADO" dice la prueba y la versión indexada ("en el cuerpo de LEY (versión indexada:
> Última Reforma DOF …) el art. 911 pasa al art. 912 sin el 911 Bis (pág. X)" o "el cuerpo de
> LEY (versión indexada: …) termina en el art. M; se cita el N") y bloquea el documento; se
> reporta tal cual (una reforma posterior a esa versión se coteja en la fuente oficial). "🟡
> POSTERIOR AL ÚLTIMO ARTÍCULO": el número sigue al último de la versión indexada sin
> superarlo por el margen: verificar si una reforma lo adicionó. Sin prueba, "🟡 NO
> LOCALIZADO" (no se acredita que no exista: puede ser un hueco del índice). La prueba solo
> se intenta si el escrito liga la ley al artículo de forma explícita ("artículo 16 de la
> CPEUM", "la Ley de Amparo, en su artículo 217"); si la oración anterior nombra dos leyes,
> la ley queda no identificada. Nunca decir "alucinación" de un artículo que solo no se
> localizó.
>
> **Lectura del JSON (R4c):** `score_rag`/`score_sjf` en `null` significan "sin citas" en esa
> dimensión (`rag_sin_citas`/`sjf_sin_citas`) o "sin puntaje" (todas no verificables): nunca
> mostrarlos como 0.00. El alcance del 🟢 está en `alcance_verificacion` (y en
> `alcance_verificacion_tesis` para las tesis). Las alertas "🟡 PRECEPTO DEROGADO" (también de
> una fracción o inciso citados), "🟡 POSIBLE DEROGACIÓN", "🟡 UNIDAD CITADA NO COTEJADA",
> "🟡 EVIDENCIA INCOMPLETA" y "🟡 EVIDENCIA DE OTRO ORDENAMIENTO" se reportan tal cual; una
> cita de párrafo o fracción no se da por verificada con el solo encabezado del artículo
> (ver `docs/PROTOCOLO_VVCA.md`).
>
> **Tesis (R4d):** "rubro coincide" significa igualdad **literal** normalizada (sin acentos,
> mayúsculas ni puntuación no numérica; "1.4.14" no es "1/4/14"), sin "…" ni texto omitido
> entre "de rubro:" y el rubro; `vvca.cotejo_rubro` dice el resultado. Las alertas "🔴 RUBRO
> DISCREPANTE — SENTIDO INVERTIDO", "🔴 RUBRO DISCREPANTE", "🟡 RUBRO PARCIAL", "🟡 RUBRO NO
> COINCIDE LITERALMENTE", "🟡 RUBRO NO ASOCIADO CON CERTEZA", "🟡 SIN RUBRO INVOCADO" (la tesis
> solo acredita su registro), "🟡 RUBRO NO DISPONIBLE", "🟡 VIGENCIA EN CONFLICTO" y "🟡
> COBERTURA INCOMPLETA" (registro no extraído con certeza) se reportan tal cual, con el rubro
> original. Los avisos de `avisos` ("ℹ️ VIGENCIA NO CONSULTADA" / "ℹ️ VIGENCIA NO
> RECONOCIDA") son informativos: no cambian el semáforo ni cuentan en `alerts_count`, pero se
> le dicen al abogado (`estado_vigencia: no_consultada` nunca es "vigente"). Un escrito con
> solo tesis sigue 🟡 transitorio aunque los rubros coincidan. Para citar parte de un rubro,
> marcar la supresión con "…".

---

