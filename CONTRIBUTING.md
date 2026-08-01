# Contribuir a Itosturre-Agente

Guía corta para trabajar en el repo sin romper las garantías legales del sistema.

## Verificaciones antes de proponer cambios

```bash
# Consistencia de instrucciones y skills para Claude/Codex
python scripts/check_agent_surfaces.py

# Regresión completa del núcleo (requiere corpus local)
python scripts/run_regression.py

# Parser de vigencia del scraper (offline)
python scripts/test_scraper_offline.py
```

`CLAUDE.md` y `.claude/skills/` son las fuentes canónicas. No edites manualmente
`AGENTS.md` o `.agents/skills/`; después de cambiar una fuente ejecuta:

```bash
python scripts/check_agent_surfaces.py --write
```

La descripción de componentes, límites y clases de datos está en
[`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

## 1. Invariante innegociable: Protocolo Anti-Alucinación

El núcleo del producto es **no inventar fuentes**. Cualquier cambio debe preservar estas
reglas (ver `docs/PROTOCOLO_VVCA.md`):

- El sistema **nunca** afirma como verificado un artículo/tesis que no encontró en el corpus
  o en el SJF. Si no lo encuentra, lo marca 🟡/🔴 con razón, no lo maquilla.
- Una ley **ausente del corpus** se reporta **🟡 NO VERIFICABLE** — *no* como "alucinación".
- Un artículo citado **sin ley identificable** no recibe 🟢 ciego: se advierte o se infiere
  la ley por sección (`law_inferred`), nunca se da por bueno contra un código al azar.
- El **veredicto** es binario con razón explícita; una tesis con rubro discrepante bloquea
  (🔴) por sí sola, sin importar el score RAG.

Si un cambio relaja cualquiera de estas reglas, **no se mergea** sin justificación escrita.

## 2. Disciplina de ramas

Nunca trabajes directo en `main`. Usa el helper:

```bash
bash scripts/git_strategy.sh 0   # crea/cambia a la rama de trabajo (arrastra tu WIP)
bash scripts/git_strategy.sh 1   # commit
bash scripts/git_strategy.sh 2   # push
bash scripts/git_strategy.sh 3   # merge a main (pide confirmación)
```

Nunca uses `--force` ni `--no-verify`. Si un hook falla, arrégla la causa.

## 3. Antes de auditar o commitear: verifica el corpus

```bash
python scripts/check_corpus.py        # debe dar "0 fuentes ausentes"
python -m py_compile OpenNotebook.py scoring_vvca.py vvca_full.py
```

Si tocaste el motor (`OpenNotebook.py` / `scoring_vvca.py`), corre la regresión sobre
`casos_de_prueba/` y confirma que:
- `caso_001_prision_preventiva.md` se mantiene 🟢 sin alertas, y
- los artículos constitucionales/de tratados resuelven a CPEUM/CADH (no a códigos locales).

## 4. Agregar una ley al corpus

1. Consigue el **PDF oficial** (diputados.gob.mx/LeyesBiblio · DOF · congreso estatal).
2. Cópialo a la base de ingesta (`INGEST_ALLOWED_BASE` del `.env`).
3. Si tiene alias/abreviatura, añádelo a `LAW_ALIASES`, `LAW_SOURCE_MAP` y `_LEGAL_NORMALIZER`
   en `OpenNotebook.py` (las tres tablas, con el **nombre exacto del archivo**).
4. Re-indexa: `python OpenNotebook.py ingest --directory "<carpeta>"`.
5. Verifica con `python scripts/check_corpus.py` que ya no aparece como ausente.

> Las **compilaciones de tesis** (`*_Tesis_Completas`, `listado-de-tesis`) van por la ruta
> de jurisprudencia, **no** al corpus estatutario — están en `EXCLUDE_PATTERNS`. No las
> indexes como si fueran leyes.

## 5. Secretos

- Nunca commitees `.env` (ya está en `.gitignore`). Solo se versionan los `*.env.example`.
- Claves de API (Anthropic, Grok, Groq, Telegram, Notion) van en `.env` o en el entorno del
  hosting (Vercel server-side), nunca en el cliente ni en el código.

## 6. Estilo

Sigue el código que rodea tu cambio: mismos nombres, misma densidad de comentarios, mismas
convenciones. Los comentarios explican el *por qué* (sobre todo en los guards de verificación),
no el *qué*.
