# Política de datos, confidencialidad y artefactos

**Versión:** 1.0 · 31-jul-2026  
**Ámbito:** desarrollo y operación local de `itosturre-agente`.

Esta política es una barrera técnica y operativa; no sustituye el análisis de secreto
profesional, privilegio, protección de datos o instrucciones particulares del cliente.

## Principios

1. **Procesamiento local por defecto.** Expedientes, auditorías, corpus e índices permanecen
   en el equipo del operador. No se incorporan al repositorio ni a CI.
2. **Un asunto por contexto.** Cada ejecución y carpeta de auditoría corresponde a un solo
   expediente o matter ID. No se mezclan clientes ni asuntos para “aprovechar contexto”.
3. **Mínima divulgación.** El scraper SJF recibe registros IUS y navega fuentes públicas;
   no debe transmitir el expediente ni datos personales al portal.
4. **Sin envíos automáticos.** Telegram, correo, Slack u otros conectores requieren aprobación
   humana antes de divulgar resultados o documentos.
5. **Casos de prueba sintéticos.** La regresión usa una lista cerrada declarada en
   `config/data-policy.json`; nunca descubre archivos mediante `glob("*.md")`.
6. **No inferir autorización.** Que un archivo sea accesible localmente no autoriza a
   incorporarlo a pruebas, reportes públicos, commits o conectores.

## Clasificación

| Nivel | Ejemplos | Ubicación permitida | Git/CI |
|---|---|---|---|
| Pública | Código, documentación, leyes oficiales redistribuibles | Árbol versionado | Permitido |
| Interna | Configuración no secreta, playbooks genéricos | Árbol versionado con revisión | Permitido |
| Confidencial | Escritos, cronologías, datos de partes, estrategia | `auditorias/` o carpeta local del asunto | Prohibido |
| Confidencial | Prospectos, teléfonos, consentimiento y listas de exclusión | `leads_data/` | Prohibido |
| Restringida | Credenciales, tokens, secretos, datos sensibles | `.env` o almacén seguro local | Prohibido |
| Regenerable | ChromaDB, cachés, capturas temporales, mapa Graphify | Rutas ignoradas | Prohibido |

## Rutas y controles

- `auditorias/`: producto de trabajo confidencial por asunto.
- `leads_data/`: prospectos B2B, procedencia, consentimiento y supresiones; nunca se versiona.
- `corpus/*.pdf`: fuente jurídica local; se distribuye fuera de Git.
- `chroma_db/` y `jurisprudencia/`: índices y datos promovidos, reconstruibles.
- `graphify-out/`: mapa regenerable que puede revelar estructura o nombres locales.
- `.env`, `.env.local`, `.claude/settings.local.json`: secretos o configuración individual.
- `casos_de_prueba/`: solo fixtures expresamente permitidos en `config/data-policy.json`.

`python scripts/check_sensitive_paths.py` verifica estas reglas antes de cada push y en CI.
El control inspecciona rutas, no contenidos confidenciales.

## Flujo por asunto

1. Crear `auditorias/<matter-id-no-nominal>/` y usar identificadores no descriptivos cuando
   sea posible.
2. Mantener `caso.json`, borradores, capturas y resultados dentro de esa carpeta.
3. Ejecutar herramientas locales; pasar al scraper únicamente registros IUS y, si se usa
   contexto, confirmar que el archivo no contiene datos personales innecesarios.
4. Revisar manualmente cualquier entregable y sus citas antes de compartirlo.
5. Al cerrar el asunto, el abogado responsable decide conservación o eliminación conforme
   a la política institucional. El agente no elimina expedientes automáticamente.

## Uso de servicios y conectores externos

Antes de usar información real con un servicio externo deben estar resueltas cuatro capas:
contrato del proveedor, infraestructura, configuración de permisos y separación por asunto.
Las acciones de escritura o envío permanecen en “requiere aprobación”. La instalación local
de este repositorio no acredita por sí misma esas cuatro capas.

## Incidentes

Si un archivo confidencial entra al índice Git, a CI o a un conector no autorizado:

1. detener la distribución y conservar evidencia mínima del incidente;
2. revocar o rotar credenciales comprometidas;
3. avisar al responsable del asunto y a seguridad/privacidad;
4. retirar el dato del historial mediante el procedimiento aprobado por el administrador;
5. documentar causa y control preventivo antes de reanudar el flujo.

No se debe “corregir” silenciosamente un incidente borrando archivos sin preservar la
trazabilidad necesaria.
