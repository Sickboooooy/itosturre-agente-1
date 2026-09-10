# MENÚ 5 — CONSULTA NORMATIVA

```
════════════════════════════════════════════════
  📖 CONSULTA NORMATIVA
════════════════════════════════════════════════

¿Qué necesitas?
  A) Texto de un artículo específico → [artículo] de [ley]
  B) Vigencia de una norma
  C) Comparar dos versiones de una norma (reforma)
  D) Jerarquía aplicable a un conflicto de normas
  E) Catálogo de leyes disponibles en el corpus

¿La norma es?
  1) Federal   2) Jalisco   3) Tratado internacional   4) No sé
```

**Herramienta real (búsqueda semántica en el corpus):**
```bash
python OpenNotebook.py query "<consulta>" --n 5
python scripts/check_corpus.py          # E) catálogo / cobertura del corpus
```

La respuesta incluye: texto del artículo (del corpus, **no de memoria**) · vigencia · si hay
reforma reciente, advertirlo. Si no está en corpus: `[FUENTE NO INDEXADA — verificar en dof.gob.mx]`.

---

