# 🧠 Brainstorm Itosturre — Roadmap de mejoras

> Generado con un workflow multi-agente (16 agentes Opus · 99 ideas · 14 lentes + crítica de
> completitud + síntesis). Documento de trabajo para el Lic. Jorge Fabián Martínez Sánchez.
> La IA valida, el abogado decide.

## 1. Resumen ejecutivo

- **Primero blinda la tubería, luego añade materias.** El foso (conocimiento del 3er Circuito) ya está probado en las skills; lo que hoy amenaza el producto no es falta de features sino la **fragilidad de los cimientos de confiabilidad**: scraper SJF como punto único de falla, corpus estático sin conciencia temporal, y plazos que el propio sistema-prompt confiesa que "no garantiza". Esas tres grietas hacen humo a media docena de ideas de plazos y vigencia.
- **La jugada de negocio evidente es profundizar en fiscal, no dispersarse.** El único cliente activo (Avanzza) es fiscalista y el producto NO cubre fiscal. Land-and-expand con demanda comprobada > abrir seis materias nuevas con bus factor 1.
- **El falso verde es el riesgo ignorado.** Todo el diseño obsesiona con "no inventar citas", pero nadie cubre el 🟢 equivocado (cita real, rubro correcto, criterio muerto). La **detección de vigencia de tesis** (superada/interrumpida) es el VVCA de verdad y el diferenciador más honesto y citable.
- **La filosofía "la IA valida, el abogado decide" debe defenderse activamente.** Tres ideas (predictor de juez, perfilador de ponente, estimador de escenarios) la contradicen frontalmente y, tras la Reforma Judicial 2024-2025 (jueces electos), se construyen sobre arena movediza. Matarlas o degradarlas a "dossier de criterios auditables sin predicción".
- **Privacidad es prerrequisito, no feature paralela.** No se puede vender "modo víctima/DDHH máxima protección" y "onboarding de fotos de expediente por WhatsApp" a la vez sin resolver primero dónde vive el PII antes de que salga a la nube.
- **El activo defendible de largo plazo son las skills de foro puro** (vicios de notificación, simulador de admisión/prevención, router de competencia) que Harvey/CoCounsel/Lexis+ no pueden replicar porque no han estado dentro de un tribunal mexicano.
- **Reforma Judicial 2024-2025 es la tensión de fondo menos atendida:** reconfigura órganos, competencias y ponentes. Cualquier idea anclada a "sé qué juez hace qué" debe tratarla como riesgo al foso, no asumir estabilidad.

---

## 2. Matriz impacto × esfuerzo

| | **Esfuerzo bajo-medio** | **Esfuerzo alto** |
|---|---|---|
| **Impacto alto** | **Quick wins:** Vigencia de tesis · Calendario CJF de plazos · Router de competencia determinista · Detector de vicios de notificación · Simulador de admisión/prevención · Freemium VVCA WhatsApp · Certificado de Validación · Clasificador [J]/[TA]/[PR]/[SCJN-I] · Disclaimer graduado · Explicabilidad del veredicto | **Apuestas grandes:** Medios-defensa-fiscal · Vigilancia DOF con diff por artículo · Versionado temporal del corpus · Panel de plazos del despacho · Traductor Jurídico↔Ciudadano |
| **Impacto bajo-medio** | **Rellenos:** Scoring literal de artículos · Chunking por fracción · Capa 2 asistida · Bitácora de overrides · Catálogo de cobertura vivo · Explainer LFPDPPP en español · Formatos de trámites ciudadanos | **Evitar (o degradar):** Predictor de criterio del juez · Perfilador de ponente · Reranker cross-encoder · Detección de contradicciones (cruce CT) · Licenciamiento a Colegios · Marketplace UGC de plantillas · Watcher expediente electrónico con e.firma · Bot multicanal con memoria |

---

## 3. Top 10 quick wins (ordenados)

| # | Idea | Qué resuelve | Esfuerzo | Primer paso concreto |
|---|------|--------------|----------|----------------------|
| 1 | **Vigencia de tesis (superada/interrumpida/sustituida)** | El falso verde más grave: rubro correcto + criterio muerto marcado 🟢 | Medio | Parsear el bloque "notas" del detalle SJF en `fetch_tesis_detalle.py`; añadir estado `SUPERADA` que dispara 🔴 independiente del rubro; cachear estado por registro IUS |
| 2 | **Clasificador [J]/[TA]/[PR]/[SCJN-I]** | Hoy trata como orientador un precedente SCJN vinculante desde 2021; confunde [PR] de otro circuito como obligatorio | Medio | Extender `build_vvca_tesis` con tabla clave→fuerza (`P./J.`, `1a./J.`, `PR.`+región, `PC.`) + mapa Plenos Regionales→circuito; propagar sello al veredicto |
| 3 | **Explicabilidad del veredicto (traza por cita)** | Convierte la "A" de auditabilidad en artefacto; el abogado no puede defender una caja negra | Bajo | Serializar lo que ya calculan `build_vvca`/`build_vvca_tesis` (distancia coseno, umbral, law_inferred, overlap) como ficha por cita en `vvca_full.json` y Word |
| 4 | **Disclaimer graduado por riesgo** | El pie fijo se vuelve invisible; cuando hay 🔴/🚨 real el sistema debe frenar y exigir acuse | Bajo | Leer `vvca_full.json` en `escrito-judicial`/`docx`: 🟢 estándar, 🟡 lista de pendientes, 🔴 bloque con iniciales del abogado |
| 5 | **Router de competencia orgánica determinista** | Error #1 de los LLM: mandar a la SCJN lo que va a Pleno Regional | Medio | Convertir MENÚ 8 en árbol de decisión codificado (tipo+materia+circuito→órgano+sede+turnado+fundamento); 🚨 si presentar mal cuesta instancia |
| 6 | **Scoring literal de artículos (fuzzy-match de entrecomillado)** | Coseno da 🟢 a paráfrasis que tergiversa "72 h" vs "96 h", "podrá" vs "deberá" | Bajo | Extraer fragmento entrecomillado del escrito y correr `rapidfuzz` contra el texto del corpus; reportar "cita literal: X% / DISCREPA" |
| 7 | **Chunking por fracción/inciso** | Un 🟢 a nivel artículo oculta que la fracción citada (causal 61 LA) está mal | Medio | Refinar `_SPLIT_PATTERNS`/`extract_section_label` para reconocer fracción (I,II…), inciso, párrafo; guardar en metadata; re-ingerir |
| 8 | **Freemium VVCA por WhatsApp (3 gratis/mes)** | Hace tangible el valor antes de pagar; acorta el ciclo B2B largo | Bajo | Contador de cuota por número en Notion sobre el endpoint `/audit` ya existente; free = solo semáforo, sin PDF ni SJF por registro |
| 9 | **Capa 2 asistida (pre-cálculo de pertinencia)** | El triaje de 15-20 tesis por caso es 100% manual | Bajo | Exponer `scorePorContexto` (ya implementado en `vvca_audit.ts`) etiquetado "Capa 2 — SUGERENCIA, decide el abogado"; nunca altera el veredicto |
| 10 | **Bitácora de overrides + Certificado de Validación** | Da evidencia de diligencia (Capa 2) y hace defendible tanto el bloqueo como la excepción legítima | Bajo-Medio | Journal append-only `auditorias/_bitacora_overrides.jsonl` al punto donde `vvca_full.py` devuelve `apto:false`; certificado con hash SHA-256 + versión de corpus + **lenguaje explícito de límites (Capa 1 ≠ garantía)** |

> Nota sobre el #8 y #10: el freemium debe lanzarse **después** de resolver caché/resiliencia del SJF (ver §7); y el Certificado necesita el disclaimer de límites o se vuelve boomerang ante un falso verde.

---

## 4. Top 5 apuestas grandes

**1. Calendario CJF de días inhábiles como servicio de plazos**
- *Qué es:* Ingestar (scrapear + versionar) el calendario y las circulares de suspensión del CJF —incluyendo suspensiones sobrevenidas y por circuito— y conectarlo al motor del MENÚ 7, con siembra opcional en Google Calendar.
- *Por qué mueve la aguja:* Cierra el único hueco que el propio CLAUDE.md confiesa ("el agente no garantiza días de suspensión"). Sin esto, media docena de ideas de plazos son humo. Convierte una advertencia defensiva en producto vendible ("seguro anti-prescripción").
- *Riesgo principal:* Fechas mal cargadas dan falsa seguridad (peor que no dar nada). Distinguir calendario federal (amparo) vs. local (TJAJ) es una trampa; el mismo acto tiene dos calendarios según el foro.
- *Validar primero:* Un **golden set** de ~30 cómputos con respuesta conocida (por Fabián) para medir exactitud antes de venderlo como garantía; y que las circulares de suspensión del 3er Circuito estén realmente disponibles en fuente pública estable.

**2. Medios-defensa-fiscal (recurso de revocación → JCA → amparo)**
- *Qué es:* Skill que ingiere la resolución del SAT (crédito, multa, cancelación de sello 17-H Bis), mapea la vía idónea con su riesgo, computa plazos fiscales (30 días) y arma el esqueleto de agravios por vicios de forma (38 CFF, competencia, notificación 134 CFF). Reusa `escrito-judicial` + VVCA.
- *Por qué mueve la aguja:* Es la jugada land-and-expand obvia: Avanzza es fiscalista y el producto no cubre fiscal. Demanda comprobada, cliente que ya confía, corpus fiscal reutilizable para el par comercial y el freemium.
- *Riesgo principal:* Concentración en un solo cliente como validador; el playbook de vicios del SAT requiere curaduría fina de foro (cuello de botella humano = Fabián).
- *Validar primero:* Indexar CFF + LFPCA + Ley Orgánica TFJA al corpus y correr **VVCA end-to-end con un escrito fiscal real** (pendiente conocido en memoria) antes de empaquetar.

**3. Detector de vicios de notificación (nulidad por emplazamiento defectuoso)**
- *Qué es:* Se engancha a la salida de `cronologia-expediente` y audita cada razón actuarial contra el checklist forense de una notificación válida (fecha/hora, identificación del actuario, cercioramiento, instructivo, testigos, surtimiento). Marca 🟢/🟡/🔴 con la foja y el requisito faltante; deja la valoración al abogado.
- *Por qué mueve la aguja:* Es el **foso más puro del banco**: el secretario *es* quien redacta esas razones. Imposible de replicar por Harvey/CoCounsel. El emplazamiento defectuoso es de las causas más frecuentes de nulidad y de reapertura de plazos.
- *Riesgo principal:* Codificar el checklist por vía (personal, cédula, instructivo, edictos, electrónica) es trabajo experto denso; falsos positivos erosionan confianza.
- *Validar primero:* Que `cronologia-expediente` extraiga las razones actuariales con fidelidad suficiente; probar el checklist contra casos de prueba con vicios conocidos.

**4. Vigilancia DOF con re-ingesta y diff por artículo (VVCA temporal)**
- *Qué es:* Mergear y correr el módulo de vigilancia DOF (hoy en rama sin mergear), que al detectar reforma de una ley del corpus dispare: descarga, re-ingesta con nueva fecha de corte, diff artículo-por-artículo, y alerta a Slack/Gmail. Alimenta el sello de vigencia por chunk.
- *Por qué mueve la aguja:* El corpus se desactualiza en silencio; citar la versión anterior de un artículo reformado (invisible para un RAG estático, marcado 🟢) puede invalidar un concepto de violación. Da conciencia temporal al verificador.
- *Riesgo principal:* Esfuerzo alto de infraestructura; requiere metadato de fecha de reforma por chunk (hoy no se guarda). Legalidad/estabilidad del scraping del DOF.
- *Validar primero:* Correr **de verdad** la rama de vigilancia (nunca se ha corrido) con una reforma real; capturar `fecha_ultima_reforma_dof` y `fecha_corte_corpus` en `ingest`.

**5. Traductor bidireccional Jurídico↔Ciudadano (acceso a la justicia)**
- *Qué es:* Toma una resolución/acuerdo real (OCR con skill `pdf`), produce "qué dice de verdad" en lenguaje B1 anclado a foja + "qué debes hacer y para cuándo" con el plazo extraído del MENÚ 7. No opina; solo traduce y señala plazo, con VVCA en los fundamentos.
- *Por qué mueve la aguja:* Ataca la causa #1 de indefensión de facto (perder plazos por no entender la notificación), reusa toda la infra (RAG + VVCA + plazos + OCR) y abre un eje de misión/marca sobre el bridge WhatsApp ya existente.
- *Riesgo principal:* Empuja PII ciudadano a la nube; exige el diccionario curado de fórmulas rituales→consecuencia (aporte de Fabián); responsabilidad si el plazo sale mal.
- *Validar primero:* Resolver **privacidad→nube** (seudonimización antes de enviar) y el calendario CJF (#1) para que el plazo sea exacto; modo sin persistencia de PII.

---

## 5. Ideas por tema

**VVCA / anti-alucinación & corpus**
- Metadato de fecha de reforma por chunk (`fecha_ultima_reforma_dof` + `fecha_corte_corpus`) — base de toda la conciencia temporal.
- Versionado temporal del corpus (`--a-fecha DD-MM-AAAA`): consultar la ley "como estaba" al momento del acto (irretroactividad, ley penal más benéfica).
- Fusión del corpus local de tesis verificadas con metadata rica del SJF en colección ChromaDB propia (arranca offline, no quema el scraper).
- Catálogo de cobertura vivo por materia con semáforo de frescura (extiende `check_corpus.py`, alimenta MENÚ 5 opción E).
- Re-auditoría VVCA longitudinal: revalidar citas de escritos ya presentados (una tesis firme al redactar puede quedar superada antes de alegatos).
- *Evitar por ahora:* reranker cross-encoder (el sticky-law resolver + chunking por fracción resuelven mejor y más barato); cruce completo con contradicciones de tesis (proyecto de datos enorme para caso de cola — la vigencia captura el 80% al 30% del costo).

**Nuevas skills de foro (foso puro)**
- Simulador de auto de admisión/prevención: replica el checklist formal con que el secretario proyecta el auto (personería, acto reclamado ambiguo, autoridades mal señaladas, capítulo de suspensión, arts. 108/175 LA). Ahorra un ciclo procesal.
- Demanda laboral ante Tribunales Laborales post-reforma 2019 (verifica constancia de conciliación prejudicial + calcula finiquito auditable).
- Extinción de dominio (cierra gap de corpus: indexar la LNEDo; juicio autónomo, carga probatoria del afectado).
- Mercantil oral/ejecutivo (cierra el ciclo comercial: del contrato revisado por `review-contract` al cobro judicial; excepciones del 1403 CCom).
- Puente penal Jalisco 3er Circuito ↔ amparo federal.
- *Evitar/degradar:* predictor de criterio del juez, perfilador de ponente, estimador de escenarios — contradicen la filosofía y se deprecian con la Reforma 2024. Si acaso, solo como "dossier de criterios documentados y auditables", nunca predicción.

**Integraciones oficiales**
- Calendario CJF (apuesta #1) — la más segura y de mayor retorno.
- Verificador de constancias SAT/CFDI reusando `cfdi-gen` (validación pública por UUID, sin e.firma) — bajo riesgo, alto valor fiscal.
- Directorio vivo de órganos del CJF para validar el router de competencia contra reestructuraciones (público, sin e.firma).
- *Tratar con cautela (no "difícil pero seguro"):* watcher del expediente electrónico con e.firma y Buzón Tributario — el problema real es **viabilidad legal/términos de uso + custodia de credenciales + LFPDPPP**, no esfuerzo. Callejón potencial.

**Negocio / GTM**
- Profundizar Avanzza (upsell CFDI-GEN → defensa fiscal auditada) y documentarlo como caso de referencia con métricas reales para la prospección LinkedIn.
- Add-on "Guardián de plazos" cobrado por expediente (alto margen; depende del calendario CJF para no vender falsa certeza).
- Facturación CFDI del propio despacho sobre `cfdi-gen` (MVP "borrador listo para timbrar", sin tocar el SAT).
- Curso → funnel medido (alumno recibe freemium + ficha en CRM Notion; medir tasa alumno→cliente).
- *Diferir:* licenciamiento a Colegios/Barras y marketplace UGC — ciclos largos y cuellos de botella humanos para un negocio de 1 persona.

**Ética, responsabilidad profesional & seguridad**
- Certificado de Cadena de Validación con **lenguaje explícito de límites** (Capa 1 ≠ garantía; cubre la asimetría del falso verde).
- Seudonimizador forense reversible pre-nube (extiende `security.py` de `itosturre-wa`) + guardia pre-flight que bloquea PII cruda (mismo patrón "un 🔴 bloquea, no promedia" aplicado a privacidad).
- Modo víctima/DDHH máxima protección (flag en `caso.json`, arts. 20 C CPEUM + LGV; caso Aaron García como plantilla ficticia).
- Cifrado en reposo de `auditorias/` + política de retención/borrado con certificado de destrucción (LFPDPPP, derechos ARCO).
- Aislamiento por matter (colección RAG efímera por expediente; barrera de información / conflicto de interés).
- Explainer LFPDPPP + aviso de privacidad en español mexicano (adaptar el material ABA/inglés).

**Acceso a la justicia**
- Traductor Jurídico↔Ciudadano (apuesta #5) y verificador ciudadano de citas "abogado-IA" (VVCA de cara al público, casi puro trabajo de interfaz).
- Triaje "¿tengo caso?" con ruteo honesto (rutea a IFDP/CEAV, nunca promete resultado).
- Asistente de víctimas: ruta CEAV/RENAVI + reparación integral (crítico: **indexar la LGV**, hoy gap).
- Canal WhatsApp ciudadano de bajo ancho de banda sobre `bridge-whatsapp` (una foto + opciones numeradas, modo sin persistencia).

**Producto / UX**
- Ficha de matter/expediente como fuente única (`caso.json` vivo que todas las skills leen/escriben — deja de re-preguntar el mismo intake).
- Onboarding de asunto en 1 min (OCR→intake→plazo→competencia, con confirmación humana antes de confiar el alta).
- Sync de vencimientos/audiencias a Google Calendar con fundamento y checklist.
- *Diferir:* plugin de Word (Office Add-in) y bot multicanal con memoria — alto valor de UX pero son plumbing, no foso; el add-in además exige exponer el bridge fuera de `127.0.0.1` con auth y cuidado LFPDPPP.

---

## 6. Secuenciación 90 días

**Fase 1 — semanas 1-4 · "Blindar la tubería y medir"**
*Por qué primero:* Sin cimientos de confiabilidad, cada feature nueva multiplica el riesgo de falso verde y de scraper caído. Antes de vender garantías hay que poder medirlas.
- **Golden set de evaluación** (~30 citas + ~30 cómputos de plazo con respuesta conocida, por Fabián) — arnés VVCA v2 implementado; primer lote revisado: 9 verdes aprobados y 1 falso verde detectado por evidencia insuficiente. El conjunto de plazos permanece separado hasta contar con calendario CJF versionado.
- **Caché resiliente + detección de cambio de layout del SJF** — el punto único de falla del foso VVCA (crítico antes de escalar usuarios).
- **Clasificador [J]/[TA]/[PR]/[SCJN-I]** — infraestructura prerrequisito de 5-6 ideas.
- **Vigencia de tesis (superada/interrumpida)** — el falso verde más grave; semilla `fetch_tesis_detalle.py` ya existe.
- **Explicabilidad del veredicto + disclaimer graduado** — bajo esfuerzo, alto retorno de confianza.
- **Validar VVCA end-to-end con un escrito real** (pendiente en memoria) — deja de ser hipótesis.

**Fase 2 — semanas 5-8 · "Cerrar plazos y abrir fiscal"**
*Por qué ahora:* Con el clasificador y la vigencia listos, se puede monetizar sin mentir. Fiscal es el land-and-expand con cliente esperando.
- **Mergear y correr de verdad la vigilancia DOF/SJF** (nunca se ha corrido) + metadato de fecha de reforma por chunk.
- **Calendario CJF de plazos** (apuesta #1) — convierte la advertencia del MENÚ 7 en producto; habilita el "Guardián de plazos".
- **Medios-defensa-fiscal MVP** (apuesta #2): indexar CFF + LFPCA + Ley Orgánica TFJA; skill sobre `escrito-judicial` + VVCA; piloto con Avanzza.
- **Router de competencia determinista** validado contra directorio CJF.
- **Freemium VVCA por WhatsApp** — solo ahora que el SJF tiene caché/resiliencia.

**Fase 3 — semanas 9-12 · "Foso de foro y privacidad→nube"**
*Por qué al final:* Son las skills más difíciles de replicar y los ejes que exigen que privacidad esté resuelta antes de tocar PII real.
- **Detector de vicios de notificación** (apuesta #3) — el foso más puro.
- **Simulador de admisión/prevención** — mismo foso, ahorra ciclo procesal.
- **Seudonimizador pre-nube + guardia pre-flight + cifrado en reposo** — prerrequisito para tocar expedientes reales por WhatsApp.
- **Extinción de dominio** (indexar LNEDo, cierra gap de corpus conocido).
- **Traductor Jurídico↔Ciudadano** (apuesta #5) — ya con calendario CJF + privacidad resueltos.
- **Ficha de matter única (`caso.json` vivo)** — glue que reduce fricción y habilita el panel de cartera.

---

## 7. Riesgos transversales & el foso

**Riesgos que cruzan todo:**
- **Scraper SJF = punto único de falla + legalidad dudosa del scraping.** Todo el foso VVCA de tesis depende de un Playwright contra `sjf2.scjn.gob.mx`. Si el SJF rediseña su DOM o bloquea la IP por volumen, media docena de ideas mueren en silencio. Sin caché/resiliencia/fallback, escalar usuarios es el detonador de la caída. Antes de scrapear DOF/CJF/PJF/Buzón: evaluar términos de uso.
- **Asimetría del falso verde.** El Certificado de Validación protege al abogado ("ejercí diligencia") pero lo incrimina si VVCA marcó 🟢 algo que falló. Necesita lenguaje explícito de límites (Capa 1 ≠ garantía) o se vuelve boomerang de responsabilidad profesional.
- **Nube vs. secreto profesional.** Varias skills razonan sobre hechos con nombres reales mientras otras prometen máxima protección. Privacidad es prerrequisito, no feature paralela: definir el orden antes de empujar PII por freemium/WhatsApp.
- **Reforma Judicial 2024-2025 + bus factor 1.** La elección de jueces reconfigura órganos, competencias y ponentes: deprecia el activo "sé qué juez del 3er Circuito hace qué". Y todo el diferenciador es el conocimiento tácito de una sola persona (Fabián), que además es el cuello de botella para curar playbooks y plantillas. Dispersarse en 8 materias agrava ambos.

**La ventaja defendible de largo plazo:**
- **Skills de foro puro** (vicios de notificación, admisión/prevención, competencia post-2021 por circuito) que solo puede construir quien redactó esas razones y proyectó esos autos — irreplicable por legaltech extranjero traducido.
- **VVCA con rigor forense real:** verificar rubro y vigencia (no solo que el registro exista), no promediar, distinguir [J]/[PR]/[SCJN-I] — la disciplina anti-alucinación como estándar del que Itosturre es autoridad.
- **Coherencia filosófica "la IA valida, el abogado decide"** materializada en artefactos (Certificado de Validación, bitácora de overrides, disclaimer graduado): diligencia documentable que ningún SaaS genérico ofrece, y el único posicionamiento ético sostenible ante el PJF.

---

## Apéndice — Crítica de completitud (agente escéptico)

### Huecos que ningún lente cubrió
- **Fragilidad del scraper SJF como single point of failure** (caché, detección de cambio de layout, fallback, qué pasa con el veredicto si el SJF está caído).
- **Términos de uso / legalidad del scraping** (SJF, DOF, CJF, Buzón, portal PJF) — riesgo existencial ignorado.
- **Responsabilidad por FALSO VERDE** — la asimetría del sello de validación.
- **Evaluación/QA del propio agente** — falta un golden set de citas y plazos con respuesta conocida.
- **Pricing de costos variables** (scraping a escala, WhatsApp Business API) — el freemium puede quemar dinero y banear el SJF.
- **Concentración de cliente (Avanzza) y bus factor = 1** (todo el foso es el criterio tácito de una persona).
- **Materias de alto volumen ausentes:** familiar/sucesorio, migratorio, agrario, justicia cívica; interpretación indígena (art. 2 CPEUM).
- **Reforma Judicial 2024-2025** como terremoto orgánico sin tratamiento propio.

### Sobrevaloradas (matar o degradar)
- Predictor de criterio del tribunal / estimador de escenarios / perfilador de ponente — cruzan la línea ética "validador, no opinador" y se deprecian con la Reforma 2024.
- Watcher del expediente electrónico con e.firma / Buzón Tributario — el problema no es esfuerzo, es viabilidad legal + custodia de credenciales + LFPDPPP.
- Bot multicanal con memoria — plumbing, no foso; riesgo de acción irreversible sin confirmación.
- Reranker cross-encoder — el sticky-law resolver ya existente + chunking por fracción resuelven mejor y más barato.
- Detección de contradicciones (cruce CT) — proyecto de datos enorme para caso de cola; la vigencia captura el 80% al 30% del costo.
- Licenciamiento a Colegios/Barras y marketplace UGC — ciclos largos y cuellos de botella humanos para un negocio de 1 persona.

### Tensiones a resolver (no ignorar)
1. Nube vs. secreto profesional — privacidad ES prerrequisito, no feature paralela.
2. Crecer usuarios (freemium/ciudadano WhatsApp) vs. carga y fragilidad del scraper SJF.
3. "El abogado decide" vs. predictor/perfilador/estimador — no caben ambas.
4. Certificado de Validación (defensa) vs. falso verde (pasivo) — necesita lenguaje de límites.
5. Land-and-expand con Avanzza (fiscal) vs. dispersión en 8 materias — con bus factor 1 es dispersión fatal.
6. Reforma Judicial 2024-2025 vs. el foso "conocimiento del 3er Circuito" — la tensión más peligrosa y menos atendida.
