---
name: menu-itosturre
description: Despliega el detalle de cualquiera de las dieciséis opciones del menú principal de Itosturre (submenús, preguntas guiadas, comandos y formatos de salida). Se activa cuando el usuario elige un número del menú (1 a 16, o "opción 3", "la 7") o describe una de esas necesidades - validar o auditar una respuesta de IA (VVCA), redactar un escrito procesal, investigar jurisprudencia o tesis en el SJF, analizar un documento legal, consultar normativa o un artículo, plantear estrategia procesal, calcular plazos y términos, determinar competencia orgánica, ver el historial de auditorías, construir la cronología de un expediente, preparar testigos o interrogatorio, revisar un contrato con redlining, triar NDAs en lote, armar la defensa fiscal contra actos del SAT, o auditar un plan jurídico contra evidencia oficial (ledger, cotejo de identidad y fidelidad). Alias: /menu, /menú, /opciones.
---

# Menús operativos de Itosturre

Esta skill guarda el **detalle** de las dieciséis opciones del menú principal. El
menú principal en sí, la identidad del agente y todas las reglas permanentes
—anti-alucinación, jerarquía normativa, reglas absolutas, protocolo de citas,
criterio penal reforzado, motor de competencia— viven en `CLAUDE.md` y están
cargadas siempre. **Aquí no hay ninguna regla de seguridad ni de verificación:
solo procedimiento e interfaz.**

## Cómo usar esta skill

Identifica qué opción pidió el usuario y **lee únicamente ese archivo** de
`references/`. No los cargues todos: el motivo de que existan por separado es
que una sesión típica usa uno.

| Opción | Tema | Archivo |
|---|---|---|
| 1 | Auditoría VVCA (validar respuesta de IA) | `references/menu-01-vvca.md` |
| 2 | Redacción de escrito procesal | `references/menu-02-redaccion.md` |
| 3 | Investigación jurisprudencial / SJF | `references/menu-03-jurisprudencia.md` |
| 4 | Análisis de documento legal | `references/menu-04-analisis-documento.md` |
| 5 | Consulta normativa | `references/menu-05-consulta-normativa.md` |
| 6 | Estrategia procesal | `references/menu-06-estrategia-procesal.md` |
| 7 | Cómputo de plazos y términos | `references/menu-07-plazos.md` |
| 8 | Competencia orgánica | `references/menu-08-competencia.md` |
| 9 | Historial de auditorías | `references/menu-09-historial.md` |
| 10 | Cronología de expediente | `references/menu-10-cronologia.md` |
| 11 | Borrador de escrito / demanda | `references/menu-11-escrito-judicial.md` |
| 12 | Preparación de testigos e interrogatorio | `references/menu-12-prep-testigos.md` |
| 13 | Revisión de contrato + redlining | `references/menu-13-revision-contrato.md` |
| 14 | Triaje masivo de NDAs | `references/menu-14-triaje-nda.md` |
| 15 | Defensa fiscal (SAT · TFJA · amparo) | `references/menu-15-defensa-fiscal.md` |
| 16 | Auditar plan jurídico (ledger · evidencia oficial · identidad · fidelidad) | `references/menu-16-auditar-plan.md` |

Si la petición encaja en dos opciones, presenta ambas numeradas y deja elegir
(Regla de oro: nunca una pregunta abierta si puede ser una lista).

Si no encaja en ninguna, vuelve al menú principal de `CLAUDE.md`.

## Qué NO está aquí

Estas reglas rigen **siempre**, se abra o no un menú, y por eso viven en el
núcleo permanente. Si al leer un submenú echas en falta alguna, está en
`CLAUDE.md`, no perdida:

- **Protocolo de citas** — campos obligatorios de toda tesis; prohibición de
  inventarlos.
- **Criterio reforzado en materia penal** — exigir 🟢 antes de insertar una cita
  en un escrito penal.
- **Motor determinista de competencia** — `router_competencia.py`; contradicción
  va a Pleno Regional y amparo directo a TCC, nunca a la SCJN de oficio.
- **🟡 NO VERIFICABLE ≠ 🔴 alucinación** — una ley fuera del corpus se re-indexa,
  no se descarta la cita.
- **Protocolo anti-alucinación (Reglas 1-7)**, **jerarquía normativa** y las
  **diez reglas absolutas** (la 10: APROBADO solo humano en la auditoría de planes).

Las notas operativas de búsqueda en el portal SJF están en
`docs/SJF_OPERATIVA.md`. El entorno de ejecución, en `docs/ENTORNO.md`.
