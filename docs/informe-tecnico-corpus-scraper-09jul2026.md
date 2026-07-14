# Informe técnico — Corpus RAG legal + Scraper SJF

**Fecha:** 07 y 09 de julio de 2026 · **Alcance:** trabajo real de auditoría VVCA sobre un expediente familiar en litigio (datos anonimizados aquí — sin nombres de partes ni identificadores de la menor). Pensado como material de apoyo para demo/curso, no como documentación de producto.

---

## 1. Qué es cada componente

**Corpus RAG legal** (`OpenNotebook.py` + ChromaDB): 44 leyes y códigos federales/estatales (Jalisco) indexados como embeddings semánticos (`intfloat/multilingual-e5-large`). Ante una cita ("artículo N de la Ley X"), hace búsqueda semántica + filtro literal por artículo y devuelve el **texto real** del corpus, con score 0-100 y semáforo VVCA — nunca el contenido "de memoria" del modelo.

**Scraper SJF** (`services/itosturre-scraper/*.ts`, Playwright): abre un **navegador Chromium real** (headless) y navega en vivo a `sjf2.scjn.gob.mx` para verificar que una tesis/jurisprudencia citada existe, coincide su rubro/número/época, y sigue vigente. Guarda capturas de pantalla del detalle consultado. Usa caché local de 30 días (`.sjf_cache/`) para no re-scrapear lo ya verificado recientemente — pero cualquier registro nuevo dispara una conexión real al sitio.

---

## 2. Qué se auditó en esta sesión (números reales)

- **5 escritos procesales completos** auditados de punta a punta (recurso de apelación, 2 recursos de revocación, un desahogo de vista, un escrito de prórroga), todos del mismo expediente familiar real.
- **6 tesis/jurisprudencias distintas verificadas en vivo** contra el SJF — las 6 coincidieron **verbatim** (rubro y cuerpo completo, carácter por carácter) con el texto oficial, y las 6 salieron **vigentes**.
- **1 tesis citada por su clave (sin registro digital) NO se pudo localizar** tras 3 estrategias de búsqueda distintas (por tema, por rubro exacto, por clave) — el sistema la marcó **🟡 NO VERIFICABLE**, explícitamente distinto de "falsa". No inventó un registro para rellenar el hueco.
- **~30 artículos de ley distintos** verificados contra el corpus (Código de Procedimientos Civiles y Código Civil de Jalisco), con extracción del texto literal para comparar contra lo que cada escrito afirmaba que decían.

## 3. El hallazgo más útil para la demo: "existe pero dice otra cosa"

El error más peligroso — y el más difícil de vender en una demo simple — **no es la cita inventada**. Es la cita que **sí existe en la ley, pero se le atribuye un contenido que no tiene.** El score de similitud semántica (RAG puro) no distingue esto: un escrito con estos errores marcó 83-85 de score general — "se ve bien" — porque los números de artículo aparecían correctamente en el texto. Hizo falta comparar el **contenido literal** de cada artículo contra lo que el escrito afirmaba que decía.

Ejemplos reales encontrados hoy (anonimizados de contexto, con número de artículo real):

| Se citó | Se afirmó que decía | Lo que realmente dice | Patrón |
|---|---|---|---|
| Art. 145 CPCJ | "Faculta al juez para adecuar plazos" | Regula **liquidación de costas** | Número correcto, contenido ajeno |
| Art. 294 CPCJ | "Faculta al juez a recabar pruebas de oficio" (repetido en 3 escritos distintos) | Regula el deber de **terceros** de auxiliar al tribunal | Error que se copió entre escritos sin corregirse |
| Art. 1004/1006 Código Civil | "Regulan el usufructo vitalicio" | Regulan **condominio** (zonificación, constitución) | Institución jurídica equivocada por completo |
| Art. 299 y 305 CPCJ | Citados como fundamento vigente | Ambos artículos están **derogados** ("Se deroga") | Norma muerta citada como viva |
| Art. 83 CPCJ | Usado para "congruencia" en un escrito | Usado para "fundamentación y motivación" en otro | **El mismo número, mal en un documento, bien en otro** — prueba que no basta memorizar "el artículo X está mal", hay que verificar el uso específico cada vez |

Este último caso (art. 83) es el más contundente para una demo: el mismo número de artículo fue correcto en dos escritos y equivocado en un tercero, según el argumento que se le atribuía. Un sistema que solo revisara "¿existe el artículo 83 en la ley?" habría dado 🟢 en los tres casos. Solo comparando el contenido literal contra la afirmación específica se detecta el error.

## 4. Cómo se blindó contra falsos negativos (relevante para el "¿y si el AI acierta?")

Durante la sesión encontramos un caso propio: el sistema inicialmente reportó un artículo (294 CPCJ) como "no recuperable del corpus" — parecía un hueco de indexación. Al investigar a fondo, el artículo **sí estaba** en la base vectorial, perfectamente indexado — solo que, al pedir pocos resultados (top-4) en una búsqueda semántica, quedó empatado en score justo fuera del corte, porque su contenido real (deber de terceros) es temáticamente distante de la pregunta ("facultad del juez"). No es una alucinación del sistema, es una limitación conocida de la búsqueda por similitud pura.

Se corrigió agregando un mecanismo de verificación literal: cuando el texto de una consulta nombra un artículo explícito ("artículo 294"), el sistema ahora garantiza que se muestre su texto exacto, sin importar si rankeó bien o mal semánticamente. Esto es exactamente el tipo de garantía que distingue "un RAG genérico" de "un sistema diseñado para verificación legal" — la pregunta correcta no es "¿el modelo suena seguro?", es "¿me puede mostrar el texto exacto del artículo N, sin excusas?".

## 5. Evidencia forense (el punto de las capturas)

Cada tesis verificada en vivo genera un archivo `.png` con la captura de pantalla del detalle real en `sjf2.scjn.gob.mx` — el mismo tipo de evidencia que se usa en la demo propuesta. No es una simulación ni una respuesta de texto: es el navegador real llegando a la página real y capturándola. En esta sesión se generaron capturas de las 6 tesis verificadas, más el JSON con metadata completa (rubro, tipo de tesis, sala/instancia, época, estado de vigencia) de cada una.

## 6. Mejoras de código encontradas y corregidas en esta misma sesión

1. **Filtro de ley por alias**: antes exigía el nombre exacto del archivo PDF para filtrar una consulta por ley; un alias legible ("código de procedimientos civiles de Jalisco") devolvía 0 resultados en silencio en vez de error. Corregido reutilizando el resolutor de aliases que ya existía en el sistema.
2. **Conexión del scraper en Windows**: el lanzador del scraper fallaba en Windows porque `npx` requiere resolución especial de extensión (`.CMD`) que Python no hace por defecto sin ayuda. Corregido, y además el fallo del scraper ya no tira el resto de la auditoría (antes perdía todo el trabajo previo si el scraper fallaba).
3. **Fallback literal por artículo** (descrito en el punto 4).

Validado con la suite de regresión del proyecto — sin romper nada existente.

---

## 7. Resumen ejecutable para el pitch del curso

- **No es "la IA no alucina"** — es "la IA muestra la fuente exacta, y cuando no puede verificarla, lo dice en vez de inventar".
- El error más común y más peligroso no es la cita fantasma — es la cita real mal aplicada. Eso requiere comparar contenido, no solo existencia.
- La verificación en vivo produce evidencia (capturas + JSON), no solo una afirmación de "ya lo revisé".
- El mismo artículo puede estar bien citado en un documento y mal en otro — la verificación tiene que ser por afirmación específica, no por número de artículo memorizado.
