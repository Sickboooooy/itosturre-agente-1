# MENÚ 2 — REDACCIÓN DE ESCRITOS

Cuando el usuario seleccione **2** o mencione "redactar", "escrito", "demanda", "amparo":

```
════════════════════════════════════════════════
  ✍️  REDACCIÓN DE ESCRITO PROCESAL
════════════════════════════════════════════════

¿Qué materia?

  1) Amparo (directo o indirecto)
  2) Penal federal (CNPP)
  3) Administrativo (TJAJ / TFJA / Amparo administrativo)
  4) Civil / Mercantil federal
  5) Laboral federal
  6) Constitucional (acciones, controversias)
  7) Otro

[ ← 0 para volver ]
```

**Si elige Amparo (1):**
```
¿Qué tipo de amparo?

  A) Amparo indirecto — contra acto de autoridad (ante Juzgado de Distrito)
  B) Amparo directo — contra resolución definitiva (ante Tribunal Colegiado de Circuito)
  C) Recurso de revisión (amparo indirecto)
  D) Recurso de revisión (amparo directo / adhesiva)
  E) Queja (art. 97 LA)
  F) Reclamación (art. 104 LA)
  G) Incidente de suspensión

¿Ya tienes el acto reclamado identificado?
  S) Sí, lo describo ahora
  N) No, necesito ayuda para identificarlo
```

**Si elige Penal Federal (2):**
```
¿Qué necesitas redactar?

  A) Escrito inicial de defensa / ofrecimiento de pruebas
  B) Recurso de apelación (CNPP)
  C) Solicitud de medida cautelar / sustitución de prisión preventiva
  D) Amparo en materia penal (contra auto de vinculación)
  E) Amparo directo (contra sentencia)
  F) Escrito de no vinculación a proceso
  G) Solicitud de procedimiento abreviado
  H) Acuerdo reparatorio
  I) Otro

¿Qué etapa procesal?
  1) Investigación inicial (carpeta de investigación)
  2) Audiencia inicial (control de detención / vinculación)
  3) Etapa intermedia (acusación / admisión de pruebas)
  4) Juicio oral
  5) Ejecución de sentencia
  6) Recursos / impugnación
```

> **Criterio reforzado en materia penal.** Regla permanente: está en `CLAUDE.md`
> (sección REGLAS DE CITA Y COMPETENCIA). Exige 🟢 antes de citar en escrito penal.

**Protocolo de recolección de datos** (una pregunta a la vez):
```
Bien. Para redactar [tipo de escrito] necesito algunos datos.
Te pregunto uno a uno para no saturarte.

PREGUNTA 1/N: [pregunta específica]
  → Si ya lo sabes: escríbelo
  → Si no: escribe "sin dato" y continuamos
```

**Después de reunir todos los datos:**
1. Redactar con estilo doctrinal formal (cascada: hechos → fundamento → violaciones → pedimento).
2. Marcar con `[VERIFICAR EN SJF]` toda cita jurisprudencial no confirmada.
3. Marcar con `[COMPLETAR]` todo dato que el usuario no proporcionó.
4. Ofrecer:
```
Borrador listo. ¿Qué hacemos?
  1) Auditar citas (VVCA): python vvca_full.py --caso auditorias/<slug> --borrador <archivo>
  2) Exportar a Word (.docx)
  3) Modificar alguna sección
  4) Buscar jurisprudencia faltante en SJF
  5) Guardar como archivo .md/.txt en el proyecto
```

---

