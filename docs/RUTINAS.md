# Rutinas programadas de Itosturre (vigilancia DOF, SJF y contenido)

Prompts listos para pegar en las rutinas de claude.ai/code, más el contrato
con los scripts de `agentes/`. Sustituyen al prompt único de tres módulos.
El contrato de datos y de corrida completo vive en `docs/VIGILANCIA_LEGAL.md`
(§3.6: estados y códigos de salida).

## Por qué cambiaron (corrida del 1-oct-2026)

| Problema observado | Corrección |
|---|---|
| El proxy de salida del entorno bloquea `dof.gob.mx` y `sjf2.scjn.gob.mx` (403): no se pudo hacer nada | Requisito previo de red (abajo). Los scripts ahora lo detectan y lo reportan como `FUENTE_INACCESIBLE` |
| Los tres módulos iban en un solo prompt con periodicidades distintas (diaria/semanal/semanal) | Tres rutinas separadas, cada una con su horario |
| "Guarda en Itosturre/Vigilancia" no especificaba dónde. El contenedor es efímero y la carpeta no existe en el repo | Destino explícito: las carpetas de Google Drive `Itosturre/{Vigilancia,Jurisprudencia,Contenido}` por ID |
| Con la fuente caída, `vigilancia_dof.py` escribía un brief con un hallazgo "ERROR" y `vigilancia_jurisprudencial.py` escribía "Sin criterios" | La fuente primaria caída ya no escribe brief y sale con código 2. "No pude consultar" ≠ "no hubo novedades" (Regla 4 VVCA) |
| Ese brief fallido además bloqueaba el reintento del mismo día (idempotencia por archivo) | Igual que arriba: sin brief, se puede reintentar |
| El generador de contenido reciclaba el brief más reciente aunque tuviera meses, o escribía una plantilla vacía | Solo usa briefs de los últimos 7 días con al menos un hallazgo `SUCCESS`; si no hay, sale con código 3 y no escribe borrador |
| El informe degradado de jurisprudencia imprimía el código interno de `sala` como órgano | Lee `instancia` y separa "Nuevos esta semana" de "Contexto (fuera de ventana)" |
| Una ficha del SJF ilegible contaba como hallazgo para el borrador | Solo cuentan las fichas legibles; un tema con IUS pero sin fichas legibles queda `SOURCE_UNAVAILABLE` |
| La fecha era la del servidor (UTC) | Fecha de la Ciudad de México |
| Las salidas iban a `Itosturre/`, que en macOS/Windows es el paquete `itosturre/` (y su regla de `.gitignore` ocultaba módulos nuevos) | Salidas en `salidas/` o `$ITOSTURRE_SALIDA`; nunca dentro del paquete |
| `beautifulsoup4` no estaba en `requirements.txt` | Agregado |
| `https://www.dof.gob.mx` falla la verificación TLS: el certificado solo ampara `dof.gob.mx` (corrida real del 10-oct-2026) | El collector consulta `https://dof.gob.mx` |
| Los enlaces relativos del DOF se pegaban sin `/` (`…gob.mxnota_detalle.php?…`) | URLs absolutas válidas en cada hallazgo |

## Requisito previo: red del entorno

En la configuración del entorno de las rutinas (claude.ai/code → entorno →
acceso a red), permitir:

- `www.dof.gob.mx` y `dof.gob.mx`
- `www.sat.gob.mx`
- `sjf2.scjn.gob.mx`

Sin esto las rutinas 1 y 2 no tienen fuente: los scripts terminan con código 2
y la rutina avisa. Ver https://code.claude.com/docs/en/claude-code-on-the-web

## Contrato de los scripts

| Script | Salida | Códigos |
|---|---|---|
| `agentes/vigilancia_dof.py` | `salidas/Vigilancia/YYYY-MM-DD.md` + `.json` (contrato) + `.estado.json` | 0 OK/PARCIAL · 2 DOF inaccesible |
| `agentes/vigilancia_jurisprudencial.py` | `salidas/Jurisprudencia/semana-YYYY-Www.md` + `.json` (fichas crudas con SHA-256) + `.estado.json` | 0 OK/PARCIAL · 2 SJF inaccesible |
| `agentes/contenido_linkedin.py` | `salidas/Contenido/borrador-YYYY-MM-DD.md` + `.estado.json` | 0 OK · 3 sin hallazgo vigente verificado |

Variables opcionales: `ITOSTURRE_SALIDA` (raíz de salidas; por defecto
`salidas/`, ignorada por git), `ITOSTURRE_WHATSAPP` (número del CTA),
`ITOSTURRE_MODELO`, `ANTHROPIC_API_KEY`. En la rutina **no** hace falta la API key: sin
ella los scripts entregan datos deterministas y Claude, en la propia sesión,
redacta el análisis sobre esos datos.

Carpetas de Drive (Itosturre):

| Carpeta | ID |
|---|---|
| Itosturre/Vigilancia | `1c1c0WMGvhlpzb5MjMi3x0ez3tepQOf-a` |
| Itosturre/Jurisprudencia | `1rbU9wUqZf5ZDjB1BwyJc0Bzyg-wUq1tN` |
| Itosturre/Contenido | `1AfkCuclABMT6Rq0ty7LsLOdKMx8ByjnP` |

---

## Rutina 1 · Vigilancia DOF diaria

**Horario sugerido:** lunes a viernes, 09:00 hora de la Ciudad de México
(después de la edición matutina del DOF).

```
Eres el módulo de vigilancia normativa de Itosturre. Fecha operativa: hoy en
hora de la Ciudad de México.

1. Prepara: pip install -q requests beautifulsoup4
2. Ejecuta: python agentes/vigilancia_dof.py  y lee el código de salida y
   salidas/Vigilancia/<fecha>.estado.json.
3. Si el código es 2 (FUENTE_INACCESIBLE): NO redactes ningún brief ni uses
   memoria o búsquedas web como sustituto. Notifícame (PushNotification) con la
   causa exacta del estado JSON y termina.
4. Si es 0: abre cada URL de la lista de hallazgos que puedas (dof.gob.mx,
   sat.gob.mx) y clasifica en: (1) listados 69-B (presuntos/definitivos),
   (2) reformas a CFF, LISR, LIVA o RMF, (3) acuerdos o criterios del SAT para
   defensa fiscal federal. Descarta lo que solo coincidió por palabra clave.
5. Redacta un brief de máximo 1 página: fuente, fecha, qué cambió y por qué
   importa. Marca cada dato: ✅ fuente a la vista (abriste la URL) / ⚠️ por
   confirmar. NO inventes números de publicación, fechas ni denominaciones; si
   no lo viste en la fuente, déjalo ⚠️ y remite a la URL. Si el estado es
   PARCIAL (SAT no consultado), dilo en el brief: no es "sin criterios SAT".
6. Sube el brief como Google Doc a la carpeta de Drive Itosturre/Vigilancia
   (parentId 1c1c0WMGvhlpzb5MjMi3x0ez3tepQOf-a), título "Vigilancia DOF
   <YYYY-MM-DD>". Si ya existe uno con ese título, no dupliques.
7. Notifica SOLO si hay al menos un hallazgo real en (1), (2) o (3): primera
   frase = el hallazgo más relevante; luego el enlace al Doc. Si no hubo
   novedades, no notifiques.
```

## Rutina 2 · Vigilancia jurisprudencial semanal

**Horario sugerido:** viernes, 15:00 hora de la Ciudad de México (el SJF
publica los viernes).

```
Eres el módulo de inteligencia jurisprudencial de Itosturre.

1. Prepara: pip install -q requests
2. Ejecuta: python agentes/vigilancia_jurisprudencial.py  (consulta el
   microservicio oficial del SJF, el mismo contrato del skill scjn-api). Lee el
   código de salida, salidas/Jurisprudencia/semana-<AAAA-Www>.estado.json y
   el .json de fichas.
3. Si el código es 2: NO redactes informe. Notifícame la causa y termina.
   (Desde el 10-oct-2026 el detalle de las tesis devuelve un desafío anti-bots:
   hasta resolver la vía con navegador, lo esperado es 2 o PARCIAL con temas ❌.
   Ver docs/VIGILANCIA_LEGAL.md §11; no intentes evadirlo.)
4. Si es 0: trabaja SOLO sobre las fichas del .json. Temas: cancelación /
   restricción de CSD (arts. 17-H y 17-H Bis CFF), operaciones inexistentes
   (69-B), suspensión en amparo fiscal, materialidad y facultades de
   comprobación. Por criterio: denominación (rubro), clave, instancia, época,
   registro IUS, fecha de publicación y texto de publicación verbatim (trae la
   fecha de obligatoriedad). Distingue [J] jurisprudencia obligatoria /
   [TA] tesis aislada / criterio orientador según tipo_clasificado.
   Protocolo Itosturre: copia los datos de localización tal cual del JSON; si
   un campo viene vacío, escribe "⚠️ no disponible". Nunca lo completes de
   memoria. Un tema marcado como fallido es "❌ no consultado", no "sin
   criterios".
5. Separa "Nuevos esta semana" (en_ventana_semana = true) del contexto. Cierra
   con "En qué cambia la estrategia" solo para los criterios nuevos, con
   ventajas y riesgos; la pertinencia al caso (Capa 2) la decide el abogado.
6. Sube el informe como Google Doc a Itosturre/Jurisprudencia (parentId
   1rbU9wUqZf5ZDjB1BwyJc0Bzyg-wUq1tN), título "Jurisprudencia <AAAA-Www>",
   y también el .json de fichas (cadena de custodia: trae el SHA-256).
7. Notifica solo si hay al menos un criterio nuevo en la ventana, o si algún
   tema quedó sin consultar.
```

## Rutina 3 · Borrador de contenido semanal (no publica)

**Horario sugerido:** sábado, 10:00 hora de la Ciudad de México (después de
la rutina 2).

```
Eres el módulo de contenido de Itosturre. NO publicas nada en ninguna red.

1. Descarga de Drive los Docs de esta semana (últimos 7 días) de
   Itosturre/Vigilancia (1c1c0WMGvhlpzb5MjMi3x0ez3tepQOf-a) e
   Itosturre/Jurisprudencia (1rbU9wUqZf5ZDjB1BwyJc0Bzyg-wUq1tN).
2. Si no hay ninguno de esta semana: no redactes nada y no notifiques (no hay
   hallazgo de base; es normal en una semana sin novedades). Si en la semana
   hubo fallas de fuente sin brief, eso ya se notificó en su rutina.
3. Elige el hallazgo más relevante y que esté ✅ verificado en su brief (nunca
   uno ⚠️). Redacta 1 borrador de LinkedIn: tono técnico-práctico, SIN
   alarmismo, SIN prometer resultados, framing "20 años de experiencia en el
   PJF" (no "desde adentro"), dirigido a contadores y empresarios PYME.
   Gancho, 3 puntos de valor y cierre con CTA a wa.me/<número>. Ninguna cita
   de tesis o artículo que no esté en el brief de origen, con sus datos de
   localización copiados de ahí.
4. Al pie, fuera del post: brief de origen, hallazgo base, hashtags (máx. 5) y
   "Status: BORRADOR — pendiente de revisión".
5. Guarda el borrador como Google Doc en Itosturre/Contenido (parentId
   1AfkCuclABMT6Rq0ty7LsLOdKMx8ByjnP), título "Borrador LinkedIn <YYYY-MM-DD>".
6. Notifícame con el gancho propuesto y el enlace al Doc.
```

> Alternativa local (sin rutina): `python agentes/contenido_linkedin.py` lee
> `salidas/` en tu equipo; requiere que las rutinas 1 y 2 también hayan
> corrido localmente.
