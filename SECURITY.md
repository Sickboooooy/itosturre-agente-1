# Política de seguridad

## Alcance soportado

Se mantiene la rama principal y la versión desplegada más reciente. El proyecto no publica
todavía una matriz estable de versiones; cualquier tabla genérica de ejemplo se considera
inválida hasta que existan releases etiquetados.

## Reporte responsable

No abras un issue público si el reporte contiene credenciales, datos personales, información
de un expediente o instrucciones para explotar una vulnerabilidad. Comunícalo directamente
al responsable del repositorio y proporciona solamente la evidencia mínima necesaria.

Incluye:

- componente y versión o commit afectado;
- impacto observado y condiciones para reproducirlo;
- si hubo exposición de secretos o producto de cliente;
- mitigación temporal aplicada, si existe.

No incluyas expedientes completos ni tokens reales. Las credenciales comprometidas deben
rotarse; borrarlas de un commit posterior no las vuelve seguras.

## Datos legales y secretos

La política operativa está en [`docs/POLITICA_DATOS.md`](docs/POLITICA_DATOS.md). Antes de
proponer cambios ejecuta:

```bash
python scripts/check_sensitive_paths.py
```

El repositorio nunca debe contener `auditorias/`, bases ChromaDB, corpus PDF, archivos `.env`
ni configuración local con credenciales.
