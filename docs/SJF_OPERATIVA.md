# Operativa de búsqueda en el SJF

**Estado:** vigente desde 10-sep-2026
**Alcance:** notas prácticas para consultar el Semanario Judicial de la Federación,
a mano o vía `services/itosturre-scraper`.
**Por qué existe:** vivía dentro del MENÚ 3 de `CLAUDE.md` y se cargaba en cada
turno aunque no hubiera ninguna búsqueda jurisprudencial en curso.

> Recordatorio del reparto de responsabilidades (Regla 3 VVCA, en `CLAUDE.md`):
> el SJF en vivo sirve para **mejorar la estrategia**, no para votar el veredicto
> anti-alucinación. Las citas se verifican contra el corpus local.

---

**Notas operativas de búsqueda en SJF** (para ti al buscar a mano, y como mejoras sugeridas
—no todas implementadas todavía— para `services/itosturre-scraper`):

- Si `sjf2.scjn.gob.mx` está bloqueado/caído para navegación, prueba `sjfsemanal.scjn.gob.mx`
  (interfaz alterna sobre la misma base). El API pública del microservicio SJF
  (`sjf2.scjn.gob.mx/services/sjftesismicroservice/api/public/`) suele seguir viva aunque el
  front se caiga — si en algún momento se integra, intentar API primero y scraping como
  respaldo. *(Roadmap: hoy el scraper solo navega el front con Playwright.)*
- Al buscar: marca "Todas las semanas", usa comillas para frase exacta, ordena por registro
  descendente (lo más reciente primero).
- El sitio usa JS intensivo — espera 2-3s tras cada navegación/clic antes de leer/capturar.
- Respeta el sitio: no lo satures (evita ráfagas de peticiones paralelas); si necesitas volumen
  alto, hazlo de noche.
- Undécima Época: filtrar solo `tipo:"J"` ya no basta para jurisprudencia obligatoria
  (hay precedentes obligatorios sin reiteración) — revisa también `formasIntegracion`. Los
  Plenos Regionales tienen alcance limitado a su circuito.
- Si cambian los selectores del portal y el scraper falla, repórtalo — **nunca entregues un
  resultado vacío disfrazado de "sin hallazgos"**.

---

## Formato de la cita

El **protocolo de citas** (qué campos lleva toda tesis y la prohibición de
inventarlos) es una regla permanente y vive en `CLAUDE.md`, no aquí.
