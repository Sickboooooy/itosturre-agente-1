# Migración de `fetch_tesis_detalle.py`

**Estado:** deprecado desde 31-jul-2026.

El script Python de la raíz duplicaba navegación Playwright y solo devolvía el texto bruto
del `body`. El scraper consolidado añade estructura, vigencia, caché, evidencia y evaluación
contextual. Por ello, `fetch_tesis_detalle.py` es ahora una fachada temporal que delega en
`services/itosturre-scraper/vvca_audit.ts`.

## Sustitución CLI

Antes:

```bash
python fetch_tesis_detalle.py 2031913 tesis_2031913_raw.json
```

Ahora:

```bash
cd services/itosturre-scraper
npx ts-node --esm vvca_audit.ts --out ../../auditorias/<caso> --no-cache 2031913
```

Para varias tesis y un caso completo:

```bash
python vvca_full.py --caso auditorias/<caso> --borrador borrador.md \
  --contexto caso.json --registros 2031913 2031207
```

## Compatibilidad temporal

La función Python `fetch(registro)` continúa disponible y conserva `registro`, `url` y
`body_text`. El resultado enriquecido vive bajo `vvca`. La captura temporal no se conserva;
quien necesite evidencia debe invocar directamente el scraper con un directorio de salida.

La fachada podrá eliminarse cuando no existan consumidores de `fetch()` fuera de este
repositorio. No deben agregarse nuevas dependencias o lógica de scraping al archivo deprecado.

