# Cimientos para prospección B2B responsable

**Estado:** fase 1 · procesamiento local · sin scraping ni envíos automáticos.

## Alcance

`itosturre/leads/` recibe un CSV o TSV obtenido por una fuente autorizada y produce una
tabla normalizada para revisión humana. El módulo no navega Google Maps, no comprueba
números contra WhatsApp y no envía mensajes.

La arquitectura separa cinco decisiones que antes estaban mezcladas:

1. **Procedencia:** de dónde salió el registro y cuándo se capturó.
2. **Identidad:** nombre, dominio y teléfono normalizado.
3. **Ajuste al ICP:** evidencia positiva y negativa de práctica fiscal.
4. **Disponibilidad del canal:** si existe un número con WhatsApp.
5. **Permiso:** si la persona aceptó recibir mensajes y si existe una exclusión.

Disponibilidad nunca equivale a consentimiento. Una exclusión prevalece sobre cualquier
score, canal u override manual.

El esquema 1.1 también separa `manual_contact_candidate` de `contact_eligible`. El primero
identifica un número empresarial público que un operador podría valorar individualmente; el
segundo exige consentimiento verificable. `wa_policy_status`, `repep_status` y
`mexican_law_status` evitan presentar política de plataforma y legislación como equivalentes.

## Uso

Los archivos reales deben guardarse bajo `leads_data/`, ruta local ignorada por Git:

```powershell
python scripts/prepare_leads.py leads_data\entrada.csv `
  --output leads_data\normalizados.csv `
  --suppression leads_data\no_contactar.csv `
  --source-type licensed_directory `
  --source-query "despachos fiscales Guadalajara"
```

El archivo de exclusión puede identificar registros por `phone` o `website`/`domain` y
debe contener, cuando sea posible, `reason` y `recorded_at`.

## Semáforo de calificación

| Segmento | Significado | Acción |
|---|---|---|
| `fiscal_prioritario` | Evidencia fuerte de defensa o litigio fiscal | Revisar sitio y contacto |
| `fiscal_posible` | Señales fiscales generales | Enriquecer antes de decidir |
| `revision_manual` | Información insuficiente | No contactar todavía |
| `no_objetivo` | Evidencia de otra especialidad | Excluir de la campaña fiscal |

La clasificación es explicable: `icp_positive_evidence` e `icp_negative_evidence` conservan
los términos activados. `manual_segment` permite corregir casos revisados por una persona.

## Guardas de contacto

`contact_eligible=true` sólo aparece cuando:

- el registro no está en la lista de exclusión;
- no existe una negativa de consentimiento;
- el ICP está marcado como `fiscal_prioritario` o `fiscal_posible`;
- `whatsapp_opt_in=yes`; y
- `whatsapp_available=yes`.

Incluso entonces, `contact_status=ready_for_human_review`: la salida exige aprobación humana
y no autoriza un envío automático.

## Siguiente fase

La fuente de datos se implementará como adaptador independiente únicamente después de
definir su licencia, términos de uso, campos disponibles y límites de conservación. Ningún
adaptador podrá saltarse la normalización, la supresión o la aprobación humana.
