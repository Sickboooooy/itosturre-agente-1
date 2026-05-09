# Caso de Prueba 001 — Impugnación Prisión Preventiva Justificada

**Fecha:** 2026-05-08  
**Motor:** OpenNotebook v3.1 · scoring_vvca.py  
**Validación operador:** Lic. Fabián Martínez Sánchez (20 años PJF)  
**Resultado:** CASO DE PRUEBA OFICIAL — alucinación jurisprudencial total detectada

---

## Descripción del caso

Documento recibido: estrategia de impugnación de prisión preventiva justificada
en materia federal, con 9 artículos constitucionales/procesales y 5 tesis
jurisprudenciales del Semanario Judicial de la Federación.

Los artículos son correctos. Las 5 tesis son **alucinaciones completas** —
los números de registro existen en el SJF pero pertenecen a materias
completamente distintas (laboral, medio ambiente, interés legítimo).

---

## Resultado de la auditoría (v4 — arquitectura dual)

```
NORMATIVA (RAG):       89.6 / 100  🟢   9/9 artículos ok
JURISPRUDENCIA (SJF):   0.0 / 100  🔴   0/5 tesis correctas

VEREDICTO:  🔴 NO APTO — USO PROCESAL PROHIBIDO
Razón:      5/5 tesis con rubro discrepante — bloqueante
Acción:     Sustituir tesis antes de cualquier uso procesal
```

**Apto para uso procesal:** No  
**Decisión de arquitectura:** scores separados, no promediados. Las tesis rojas
son bloqueantes por sí solas — una sola tesis falsa hace el veredicto NO APTO
independientemente del score RAG.

---

## Las 5 tesis con discrepancia de rubro

| Registro | Lo que el documento afirma | Lo que SJF muestra | Detección |
|---|---|---|---|
| 2019456 | P./J. 3/2019 · Pleno · **Prisión preventiva constitucional** | 2a./J. 51/2019 · 2a Sala · **Interés Legítimo** (Materia: Común) | Sistema ✅ · Fabián ✅ |
| 2005823 | 1a./J. 11/2014 · 1a Sala · **Presunción de inocencia** | 2a./J. 23/2014 · 2a Sala · **Trabajadores de confianza** (Laboral) | Sistema ✅ · Fabián ✅ |
| 2022147 | 1a./J. 26/2020 · 1a Sala · **Medidas cautelares proporcionalidad** | 2a. XVI/2020 · 2a Sala · **Consulta pública medioambiental** (Aislada) | Sistema ✅ · Fabián ✅ |
| 2010891 | 1a. CCCXL/2015 · 1a Sala · **Prisión preventiva no automática** | PC.III.P. J/7 P · Plenos Circuito · **Violencia intrafamiliar Jalisco** | Sistema ✅ · Fabián ✅ |
| 2025134 | I.1o.P. J/7 · TCC Penal · **Delincuencia organizada** | I.2o.T.4 L · TCC Laboral · **Prórroga contrato temporal** | Sistema ✅ · Fabián ✅ |

---

## Artículos verificados — 9/9 correctos

| Referencia | Corpus | Score |
|---|---|---|
| Art. 19 párrafo 2° CPEUM | CPEUM.pdf pág. 252 | 91 🟢 |
| Arts. 14, 16, 19, 20 CPEUM | CPEUM.pdf pág. 174 | 88–91 🟢 |
| Art. 107 Fr. V CPEUM | CPEUM.pdf pág. 174 | 90 🟢 |
| Arts. 155–157, 164–165, 169 Fr. II CNPP | CodigoNacionalProcedPenales.pdf | 87–89 🟢 |
| Arts. 467–471 CNPP | CodigoNacionalProcedPenales.pdf pág. 133 | 87 🟢 |
| Art. 170 Fr. I Ley de Amparo | LEY DE AMPARO.pdf pág. 100 | 92 🟢 |

---

## Tesis sustitutos verificados en SJF

| Registro | Tesis | Tipo | Prioridad |
|---|---|---|---|
| **2028965** | 1a./J. 113/2024 (11a.) · Primera Sala SCJN · Medidas cautelares art. 157 CNPP | **Jurisprudencia obligatoria** | ⭐ Máxima |
| 2027130 | (II Región)1o.18 P (11a.) · PPJ carga de la prueba | Aislada | Refuerzo |
| 2027129 | (II Región)1o.19 P (11a.) · PPJ información en medios | Aislada | Refuerzo |
| 2027126 | (II Región)1o.14 P (11a.) · PPJ interpretación sistemática | Aislada | Refuerzo |
| 2026023 | I.9o.P.65 P (11a.) · PPJ peligro de sustracción | Aislada | Alternativa |
| 2017691 | I.1o.P.119 P (10a.) · Medidas cautelares sistema acusatorio | Aislada | Contexto |

---

## Score proyectado post-corrección

Con las tesis reales sustituidas (Reg. 2028965 jurisprudencia + 2 aisladas TCC):

```
Jurisprudencia ≈ (95 + 72 + 72) / 3 = 79.7  × 0.50 = 39.8
Normativa       = 89.6                × 0.25 = 22.4
Estrategia      = 75.0                × 0.15 = 11.25
Auditabilidad   = 60.0                × 0.10 =  6.0
Ponderado bruto = 79.45
Penalización    = 0  (0/3 tesis falsas)
Score proyectado ≈ 79.0  →  🟡 APTO (umbral: ≥ 70)
```

---

## Flujo de demostración (3 minutos)

```
1. "Le di esta estrategia a ChatGPT"              → mostrar respuesta LLM
2. "Itosturre la auditó"                          → score 0.0 / PROHIBIDO
3. "Detectó las 5 tesis falsas automáticamente"   → tabla con columna Sistema/Fabián
4. "Y propuso sustitutos reales del SJF"          → sección sustitutos con prioridades
5. "Yo verifiqué y confirmé"                      → firma del operador en el PDF
```

**Este flujo es el producto.**

---

## Decisión de diseño documentada

**¿Por qué score 0 (no 15) para tesis con rubro discrepante?**

Un registro SJF real con rubro falso es procesalmente **más peligroso** que
un registro inexistente:

- Un registro inexistente es rechazado de inmediato por el actuario o el juez
- Un registro real con rubro falso puede engañar a un juzgador menos diligente,
  quien lo busca en el SJF, lo encuentra con ese número, y no detecta que
  el criterio no aplica al argumento invocado

Por tanto: `rubro_mismatch = True → score = 0` (no crédito parcial).
Implementado en `OpenNotebook.py → build_vvca_tesis()`.

---

## Archivos de evidencia

- `caso_001_prision_preventiva_audit_v3.pdf` — reporte PDF oficial con firma operador
- `../scoring_vvca.py` — módulo de score compuesto ponderado

---

*Generado por Itosturre LegalTech · OpenNotebook v3.1 · 2026-05-08*
