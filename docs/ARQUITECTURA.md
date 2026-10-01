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
| `itosturre/audit/` | Políticas VVCA puras y trazabilidad, sin dependencias RAG | Código padre |
| `itosturre/leads/` | Normalización, deduplicación, ICP y supresión de prospectos; sin recolección ni envíos | Código padre |
| `itosturre/memoria/` | Memoria contextual: eventos, índice FTS5, ranking y snapshots; sin dependencias externas | Código padre |
| `memoria_cli.py` | Interfaz de la memoria contextual | Código padre |
| `itosturre/plan/` · `plan_audit.py` | Auditor determinista de planes sobre ledger `plan-ledger/1.0`: vocabulario de estados, evidencia oficial, aprobación humana ligada al hash del contenido y cobertura de menciones (PL-001…PL-014); sin red ni LLM, separado del VVCA | Código padre |
| `itosturre/evidencia/` | Capa de evidencia pura (C7): registro `evidencia/1.0` (URL oficial, fecha de consulta aportada por quien llama, huellas del original y del derivado), fuente única de hosts oficiales, huellas y JSON canónico, parser del SJF anclado en "Registro digital:", limpieza de LeyesBiblio con invariantes, ubicación de artículos (cuerpo / transitorios / indeterminada) y notas de reforma con gramática completa. `validar_registro` es solo estructural y **no habilita VERIFICADO**: hace falta además `comprobar_integridad`, que recalcula las huellas desde el original y el derivado y vuelve a leer la fuente. Solo biblioteca estándar; sin red, reloj ni escritura. `plan` puede importarla; ella no importa `plan` ni `audit` | Código padre |
| `scripts/generar_fixtures_evidencia.py` | Regenera `tests/fixtures/evidencia/` desde originales descargados (requiere PyMuPDF); no corre en CI | Código padre |
| `services/itosturre-scraper/` | SJF en vivo, TypeScript y Playwright | Submódulo |
| `services/itosturre-skills/` | Skills jurídicas distribuibles | Submódulo |
| `.claude/skills/` | Fuente versionada de skills vendorizadas | Código padre |
| `.agents/skills/` | Adaptación Codex generada y verificada | Código padre generado |

## Clases de datos

| Clase | Rutas | Política |
|---|---|---|
| Memoria contextual | `~/.itosturre/memoria/*.db` | **Fuera del repositorio**; local, reconstruible; contiene decisiones del despacho |
| Fuente jurídica | `corpus/`, `jurisprudencia/` | Local; no versionar documentos pesados |
| Índice regenerable | `chroma_db/`, `graphify-out/` | Local; reconstruible |
| Producto de cliente | `auditorias/` | Local, confidencial, nunca versionar |
| Prospectos B2B | `leads_data/` | Local; incluye consentimientos y exclusiones; nunca versionar |
| Casos sintéticos | `casos_de_prueba/` | Versionados; la regresión usa una lista cerrada |
| Fixtures de evidencia oficial | `tests/fixtures/evidencia/` | Versionados; texto oficial literal (páginas de LeyesBiblio, renders del SJF) con procedencia en `manifiesto.json`; bytes exactos (`.gitattributes`, sin conversión de fin de línea); cada archivo autorizado en `config/data-policy.json` |
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
| Parser y resiliencia SJF offline | `python scripts/test_scraper_offline.py` | Cada push/PR |
| Gold Set VVCA | `python scripts/evaluate_gold_set.py` | Cada push/PR |
| Gold Set jurídico v2 | `python scripts/evaluate_gold_set.py --file tests/fixtures/vvca_gold_set_v2.json` | Curaduría del operador; no es gate hasta 30 casos aprobados |
| Orquestador fail-closed | `python -m unittest -v tests.test_vvca_full` | Cada push/PR |
| Gold Set de planes | `python scripts/evaluate_plan_gold_set.py` | Cada push/PR; falla si un caso no pasa o una regla PL queda sin caso |
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
- `vvca_full.py` falla cerrado ante errores de RAG, SJF o evidencia. La degradación solo se
  permite mediante flags explícitos y queda registrada como `status: partial`.
- Ninguna automatización debe enviar mensajes o publicar contenido sin aprobación humana.
