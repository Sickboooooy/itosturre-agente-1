# Notion — CRM Itosturre

Hogar de las piezas de integración con Notion (CRM B2B). Se construye **poco a poco**: aquí viven los IDs centralizados, helpers reutilizables y, con el tiempo, las skills/scripts de sincronización.

## Bases del CRM

| Base | database_id | data source |
|---|---|---|
| 🏢 Pipeline CRM B2B | `135e263c9c4246cb80f8d54d730aaa23` | `499a93b7-4b5b-43db-8fc5-b7421f067f41` |
| 📋 Clientes Activos B2B | `24ef8447ab8d410ab96bac42a27058d1` | `e445ef7b-1189-4256-905d-6fd471630a95` |
| ⚖️ Expedientes Itosturre | `3fac2fcfc6bf404bb2a79642613e6ca5` | `2913adab-f41b-412e-9c25-ae60fe1245be` |

Todas bajo la página **Itosturre Consultor Core** (`2338c35d-2faa-8084-b565-e4faf72931df`) — ⚠️ **archivada, restaurar**. Dashboard: **Centro de Mando CRM** (`3818c35d-2faa-81eb-b60f-dc1d664defc4`).

Constantes en [`crm.py`](crm.py) — importar desde ahí, no hardcodear IDs.

## Setup de la integración

1. Crear una **integración interna** en notion.so/my-integrations → copiar el token.
2. Poner `NOTION_TOKEN` en `.env` (ver `.env.example`).
3. En Notion, **compartir cada base** con la integración (••• → Connections).

```python
from crm import get_client, PIPELINE_DB
notion = get_client()
notion.pages.create(parent={"database_id": PIPELINE_DB}, properties={...})
```

## Estado del CRM (upgrade básico → especializado, 16-Jun-2026)

- Campos nuevos en Pipeline (`LinkedIn URL`, `Ciudad`, `Especialidad`, `Responsable`, fórmulas `Probabilidad` y `Pronóstico MXN`), Clientes (`Saldo Pendiente MXN`, `Salud Cliente`) y Expedientes (`Doc Auditoría VVCA`, `Materia/Tema`).
- ⏳ Pendiente manual (la API no crea relaciones cruzadas por DDL): unir Pipeline↔Clientes↔Expedientes + rollup. Pasos en el dashboard.

## Roadmap (poco a poco)

- [ ] `push_prospectos.py` — mover/compartir el `to_notion.py` del PoC LinkedIn aquí, importando `crm.py`
- [ ] `sync_clientes.py` — alta automática Ganado (Pipeline) → Clientes Activos
- [ ] `reporte_cobranza.py` — resumen de `Saldo Pendiente MXN` > 0
- [ ] Skill Claude `notion-crm` — alta/consulta de prospectos por lenguaje natural

## Guardarraíl

No versionar tokens ni datos personales. `.env` está en `.gitignore`. Datos de clientes/casos → fuera del repo.
