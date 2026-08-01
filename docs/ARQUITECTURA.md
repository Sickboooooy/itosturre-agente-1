# Arquitectura de `itosturre-agente`

**Estado:** vigente desde 31-jul-2026  
**Alcance:** repositorio padre del auditor VVCA y sus integraciones oficiales.

## Propósito y límites

`itosturre-agente` contiene el núcleo local de verificación jurídica, la orquestación del
pipeline VVCA y la configuración necesaria para que los agentes apliquen ese protocolo.
El scraper SJF y el catálogo de skills son productos con ciclo de vida propio y se integran
como submódulos. El corpus, los índices y los productos de cliente son datos locales, no
código fuente.

```text
Entrada (escrito/caso)
        |
        v
vvca_full.py ------------------------------+
        |                                   |
        v                                   v
OpenNotebook.py                       services/itosturre-scraper
  | extracción de citas                | consulta estratégica SJF
  | recuperación corpus                | vigencia + evidencia visual
  | auditoría normativa                +--------------------------+
  v                                                               |
scoring_vvca.py <--------------------------------------------------+
  | veredicto y semáforo
  v
auditorias/<caso>/vvca_full.json + capturas
```

La consulta SJF en vivo mejora la estrategia y aporta evidencia, pero no sustituye el
corpus local como fuente del veredicto anti-alucinación. Esta separación es una invariante
del producto.

## Componentes

| Componente | Responsabilidad | Persistencia |
|---|---|---|
| `OpenNotebook.py` | Ingesta, recuperación RAG, extracción y auditoría de citas | Código padre |
| `scoring_vvca.py` | Semáforo y veredicto VVCA | Código padre |
| `vvca_full.py` | Orquestación del pipeline completo | Código padre |
| `capturar_rag.py` | Evidencia visual de fuentes recuperadas | Código padre |
| `router_competencia.py` | Enrutamiento determinista de competencia orgánica | Código padre |
| `scripts/` | Bootstrap, cobertura, promoción y regresión | Código padre |
| `agentes/` | Automatizaciones auxiliares de vigilancia y contenido | Código padre |
| `itosturre/audit/` | Políticas VVCA puras, comprobables y sin dependencias RAG | Código padre |
| `services/itosturre-scraper/` | SJF en vivo, TypeScript y Playwright | Submódulo |
| `services/itosturre-skills/` | Skills jurídicas distribuibles | Submódulo |
| `.claude/skills/` | Fuente versionada de skills vendorizadas | Código padre |
| `.agents/skills/` | Adaptación Codex generada y verificada | Código padre generado |

## Clases de datos

| Clase | Rutas | Política |
|---|---|---|
| Fuente jurídica | `corpus/`, `jurisprudencia/` | Local; no versionar documentos pesados |
| Índice regenerable | `chroma_db/`, `graphify-out/` | Local; reconstruible |
| Producto de cliente | `auditorias/` | Local, confidencial, nunca versionar |
| Casos sintéticos | `casos_de_prueba/` | Versionados; la regresión usa una lista cerrada |
| Dependencias | `venv/`, `node_modules/` | Local; regenerables |

## Fuentes canónicas

1. `CLAUDE.md` contiene la política operativa compartida. `AGENTS.md` es su adaptación
   para Codex y solo puede diferir en el encabezado de plataforma.
2. `.claude/skills/` es la fuente vendorizada. `.agents/skills/` conserva el mismo árbol;
   únicamente tres `SKILL.md` aplican sustituciones de plataforma documentadas.
3. `scripts/check_agent_surfaces.py` verifica esas reglas y puede regenerar las superficies
   derivadas con `--write`.
4. `services/itosturre-skills/` es la fuente de las skills jurídicas propias del producto;
   no debe editarse como si fuera una carpeta ordinaria del repositorio padre.

## Contratos de prueba

| Nivel | Comando | Uso |
|---|---|---|
| Estático | `python -m compileall -q ...` | Cada push/PR |
| Superficies de agente | `python scripts/check_agent_surfaces.py` | Cada push/PR |
| Parser SJF offline | `python scripts/test_scraper_offline.py` | Cada push/PR |
| Regresión VVCA | `python scripts/run_regression.py` | Gate local antes de merge; requiere corpus |
| Política de datos | `python scripts/check_sensitive_paths.py` | Cada push/PR |

La regresión VVCA no se ejecuta en CI compartido porque requiere el corpus local y el modelo
de embeddings. Un resultado verde de CI no reemplaza ese gate local.

## Decisiones vigentes

- El repositorio padre es Python; no existe un proyecto Node en la raíz.
- Las dependencias Node pertenecen exclusivamente al submódulo del scraper.
- `fetch_tesis_detalle.py` es solo una fachada deprecada; `vvca_audit.ts` es la
  implementación canónica para consultar registros SJF.
- Los dos submódulos oficiales son `itosturre-scraper` e `itosturre-skills`.
- La modularización de `OpenNotebook.py` comenzó por funciones puras bajo `itosturre/audit/`.
  Las siguientes extracciones serán incrementales, conservarán la CLI y pasarán la regresión.
- Ninguna automatización debe enviar mensajes o publicar contenido sin aprobación humana.
