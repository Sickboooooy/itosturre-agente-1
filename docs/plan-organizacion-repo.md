# Plan de organización del repo `itosturre-agente`

> **Estado actualizado: 31-jul-2026.** El mapa operativo vigente está en
> [`docs/ARQUITECTURA.md`](ARQUITECTURA.md). Este documento conserva el diagnóstico de
> Graphify y el historial de decisiones. Las acciones ya ejecutadas se señalan abajo.

**Fecha:** 17-jul-2026 · **Base:** mapa de conocimiento generado con [graphify](https://github.com/Graphify-Labs/graphify) (AST local, sin LLM) sobre 149 archivos de código → 1,166 nodos, 1,847 aristas, 125 comunidades. Mapa en `graphify-out/` (gitignorado; `graph.html` es interactivo, ábrelo en el navegador).

## Diagnóstico (qué reveló el grafo)

El auditor legal —el producto real— son **~200 KB** de Python en la raíz (`OpenNotebook.py`, `vvca_full.py`, `scoring_vvca.py`, `router_competencia.py`, `capturar_rag.py` + `scripts/`). Está **enterrado** bajo proyectos ajenos:

- **`services/` = 482 MB, 7 subproyectos**, la mayoría negocios distintos al auditor legal.
- Los "nodos-dios" del grafo **no son la lógica legal** — son validadores de XML de Office (`BaseSchemaValidator`, `DOCXSchemaValidator`), o sea código vendoreado de las skills, triplicado bajo `.claude/skills/{docx,pptx,xlsx}`.
- Cruce entre proyectos ajenos detectado por el grafo: `scraper_final.ts → test-avanzza.mjs` (SJF enredado con CFDI-GEN).
- **Cero ciclos de importación** → el desorden es **organizacional (proyectos mal colocados), no algorítmico.** Ordenar = mover cosas de lugar, no reescribir código.

## Clasificación de `services/`

| Subproyecto | Tamaño | ¿Repo propio? | Estado git padre | ¿Es producto? | Acción |
|---|---|---|---|---|---|
| `itosturre-scraper` | 51M | sí | **submódulo oficial** (`.gitmodules`) | **SÍ** (SJF, en CLAUDE.md) | **dejar** |
| `itosturre-skills` | 283K | sí | **submódulo oficial** (`.gitmodules`) | **SÍ** (skills jurídicas) | **hecho: dejar** |
| `cfdi-gen` | 16M | sí (embebido) | `??` sin trackear | no — SaaS Avanzza (duplica `Desktop\CFDI-GEN demo`) | **gitignorar** (P0) → luego relocalizar |
| `itosturre-wa` | 397K | sí (embebido) | `??` sin trackear | no (bridge WhatsApp/Telegram) | **gitignorar** (P0) |
| `bridge-whatsapp` | 210K | sí (embebido) | `??` sin trackear | no | **gitignorar** (P0) |
| `linkedin-prospector` | 416M | no | trackeado (6 archivos fuente) | no (PoC marketing/CRM) | fuente OK; `.venv` (416M) = basura local (P2) |
| `notion` | 10K | no | trackeado | no (helper CRM) | decidir: ¿mover fuera? (P2) |

> Nota: los 4 con "repo propio embebido" son un anti-patrón de git (repos dentro de repos). Por eso salen como `??` — el git padre no entra a trackearlos.

## Acciones priorizadas

### P0 — Callar el ruido de git (hecho en rama `feat/repo-tidy-graphify`)
Gitignorar los 3 repos embebidos ajenos. **No mueve ni borra archivos** — solo quita el `??` de `git status` y evita que un `git add -A` los arrastre. Reversible (editar `.gitignore`).
```gitignore
# Repos embebidos ajenos al auditor legal (proyectos separados con su propio .git)
services/cfdi-gen/
services/itosturre-wa/
services/bridge-whatsapp/
```
`itosturre-skills` NO se gitignora aquí: es producto y debe volverse submódulo (P1).

### P1 — Dar límites explícitos
1. ✅ **`itosturre-skills` como submódulo.** Ejecutado; comparte el mismo límite explícito
   que `itosturre-scraper` y figura en `.gitmodules`.
2. ✅ **Mapa arquitectónico y fuentes canónicas.** Documentados en
   `docs/ARQUITECTURA.md`; las superficies Claude/Codex se validan con
   `scripts/check_agent_surfaces.py`.
3. ⏳ **Empaquetar el core** en `itosturre/` o `src/`. Sigue diferido: cambia rutas de
   importación y exige ejecutar `scripts/run_regression.py` después de cada extracción.

### P2 — Relocalizar negocios ajenos y limpiar disco
- **`cfdi-gen`**: una vez gitignorado, se puede **borrar de aquí** — pero SOLO tras confirmar que `Desktop\CFDI-GEN demo` está actualizado (es su hogar real). No auto-borrar.
- **`linkedin-prospector/.venv`** (416M): basura local regenerable. Si el disco importa: `rm -rf services/linkedin-prospector/.venv` (se recrea con `python -m venv`). Los 6 archivos fuente trackeados están bien.
- **`bridge-whatsapp`, `itosturre-wa`, `notion`, `linkedin-prospector`**: decidir si cada uno se va a su propio repo (recomendado para los que son negocio aparte) o se documenta como externo.
- ✅ **`fetch_tesis_detalle.py`:** deprecado como implementación independiente; permanece
  temporalmente como fachada hacia `services/itosturre-scraper/vvca_audit.ts`.

### No tocar
- Triplicación de validadores Office bajo `.claude/skills/{docx,pptx,xlsx}`: es cómo se empaquetan las skills (cada una trae su copia). Intencional.
- `auditorias/` (14M): work product de clientes, ya gitignorado. Correcto.

## Cómo re-generar / consultar el mapa
```bash
# venv de graphify (aislado, en scratch de la sesión) — o instalar: pip install graphifyy
VENV=<ruta_al_venv_graphify>/Scripts/python
# Re-mapear (AST local, sin API key, respeta .gitignore):
$VENV -m graphify extract . --code-only --out graphify-out-tmp
$VENV -m graphify cluster-only graphify-out-tmp --no-label   # regenera GRAPH_REPORT.md sin LLM
# Consultar el grafo:
$VENV -m graphify query "¿qué llama a audit()?" --graph graphify-out/graph.json
$VENV -m graphify path "audit()" "veredicto_global()" --graph graphify-out/graph.json
```
En Antigravity (skill instalado en `~/.gemini/config/skills/graphify/`): recargar y usar `/graphify .`.
```
