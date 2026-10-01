"""Capa de evidencia pura (C7): procedencia, huellas y lectores de fuentes oficiales.

Un documento solo es evidencia si trae procedencia verificable (D4): URL oficial,
fecha de consulta y huellas del original y del derivado. El RAG y el VVCA solo
localizan. ``validar_registro`` revisa la forma; ``comprobar_integridad`` recalcula
las huellas desde los artefactos y vuelve a leer la fuente. Solo un registro que pasa
ambas puede sostener un VERIFICADO. Aquí no hay red, reloj ni escritura de archivos; la descarga y la caché
son otro componente (C8).

Dependencias (D2): ``itosturre/plan`` puede importar este paquete; este paquete no
importa ``plan`` ni ``audit`` (VVCA).
"""

from .esquema import (
    EPOCAS,
    MARCADORES_PENDIENTES,
    MEDIOS,
    SCHEMA_VERSION,
    TIPO_LEY_LEYESBIBLIO,
    TIPO_TESIS_SJF,
    TIPOS,
    TipoEvidencia,
    advertencia,
    construir_registro,
    crear_extracto,
    es_marcador_pendiente,
    fecha_consulta_valida,
    validar_registro,
)
from .fuentes import (
    HOSTS_CANONICOS,
    HOSTS_OFICIALES,
    host_de,
    motivo_url_no_oficial,
    url_leyesbiblio,
    url_oficial,
    url_tesis_sjf,
)
from .huellas import (
    es_sha256,
    huella_registro,
    json_canonico,
    normalizar_para_cotejo,
    sha256_bytes,
    sha256_texto,
)
from .integridad import comprobar_integridad
from .leyesbiblio import (
    DocumentoLeyesBiblio,
    PaginaLimpia,
    UbicacionArticulo,
    limpiar_documento,
    limpiar_pagina,
    ubicar_articulo,
    verificar_documento,
    verificar_pagina,
)
from .reformas import (
    NotaReforma,
    ResultadoNotas,
    extraer_notas,
    invariante_fechas,
    parsear_nota,
    verificar_fechas,
)
from .sjf import ErrorSJF, TesisSJF, derivado_canonico, parsear_tesis

__all__ = [
    "EPOCAS",
    "HOSTS_CANONICOS",
    "HOSTS_OFICIALES",
    "MARCADORES_PENDIENTES",
    "MEDIOS",
    "SCHEMA_VERSION",
    "TIPOS",
    "TIPO_LEY_LEYESBIBLIO",
    "TIPO_TESIS_SJF",
    "DocumentoLeyesBiblio",
    "ErrorSJF",
    "NotaReforma",
    "PaginaLimpia",
    "ResultadoNotas",
    "TesisSJF",
    "TipoEvidencia",
    "UbicacionArticulo",
    "advertencia",
    "comprobar_integridad",
    "construir_registro",
    "crear_extracto",
    "derivado_canonico",
    "es_marcador_pendiente",
    "es_sha256",
    "extraer_notas",
    "fecha_consulta_valida",
    "host_de",
    "huella_registro",
    "invariante_fechas",
    "json_canonico",
    "limpiar_documento",
    "limpiar_pagina",
    "motivo_url_no_oficial",
    "normalizar_para_cotejo",
    "parsear_nota",
    "parsear_tesis",
    "sha256_bytes",
    "sha256_texto",
    "ubicar_articulo",
    "url_leyesbiblio",
    "url_oficial",
    "url_tesis_sjf",
    "validar_registro",
    "verificar_documento",
    "verificar_fechas",
    "verificar_pagina",
]
