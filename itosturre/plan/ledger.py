"""Carga y validación estructural del ledger de planes (esquema ``plan-ledger/1.0``).

El ledger es un dict JSON. Este módulo solo verifica la *forma* (tipos, enumeraciones,
campos obligatorios); las reglas de contenido (estados, evidencia, aprobaciones,
cobertura) viven en ``lint.py``. Un ledger estructuralmente inválido no se audita:
la CLI termina con código 2.

Decisiones de esquema:
  - ``afirmaciones`` y ``evidencias`` son obligatorias (pueden ser listas vacías);
    ``contradicciones`` y ``decisiones`` son opcionales y su ausencia equivale a ``[]``.
  - Los IDs duplicados y las referencias colgantes NO son errores estructurales: son
    hallazgos PL-013, para que el reporte los muestre junto con lo demás.
  - Las llaves desconocidas se ignoran (compatibilidad hacia adelante).
  - Llaves opcionales del cotejo de identidad (PR-3). Este esquema no las valida (son
    llaves desconocidas para ``plan-ledger/1.0``); las interpretan ``identidad.py`` y
    ``lint.py`` (PL-017):

    * ``evidencias[].ultima_reforma_dof`` (``AAAA-MM-DD``): versión de la ley en la que
      se apoya la afirmación. Si viene, debe coincidir con la ``ultima_reforma_dof`` del
      registro del paquete; un valor no interpretable impide el CONFORME.
    * ``decisiones[].advertencias_fuente``: decisión humana sobre las advertencias de la
      fuente de una evidencia (p. ej. ``epoca_discrepante``)::

          {"evidencia": "E6",
           "sha256_documento": "<huella del original vigente>",   # o "huella_registro"
           "codigos": ["epoca_discrepante"],
           "resolucion": "<qué se adopta y por qué>"}

      Solo atiende las advertencias si la evidencia y la huella son las vigentes (si la
      fuente cambia, deja de valer), declara todos los códigos de la fuente, trae una
      resolución no vacía y su responsable es humano; para sostener un VERIFICADO,
      además, la decisión debe estar APROBADA. ``bloquea`` por sí solo no basta.

  - Identificación del criterio por tipo de fuente (piloto PEN-01, D8). Llave opcional
    ``afirmaciones[].identificacion_criterio.tipo_fuente``, que interpreta PL-007:

    * ``"tesis_sjf"`` (por omisión): los diez campos ``CAMPOS_CRITERIO`` de la tesis del
      SJF (rubro, clave, órgano, época, registro, integración, publicación,
      obligatoriedad, fuerza vinculante y alcance), sin cambios.
    * ``"sentencia_internacional"`` (p. ej. Corte IDH): ``CAMPOS_SENTENCIA_INTERNACIONAL``
      — ``caso`` ("… vs. México"), ``serie_numero`` ("Serie C No. …"), ``fecha`` (de la
      sentencia) y ``parrafo`` (párrafo o punto resolutivo citado). Una sentencia no tiene
      rubro, clave, época ni registro digital: exigírselos era imposible de satisfacer.

    Sin ``tipo_fuente``, una identificación cuyas evidencias citadas son todas de
    ``HOSTS_SENTENCIA_INTERNACIONAL`` se lee como sentencia internacional; cualquier otra,
    como tesis del SJF. Un ``tipo_fuente`` fuera de ``TIPOS_FUENTE_CRITERIO`` es hallazgo
    PL-007 (y se exigen los campos de tesis). El tipo declarado debe ser compatible con las
    evidencias (ronda 2): ``sentencia_internacional`` exige al menos una de la Corte IDH y
    ninguna de ``HOSTS_TESIS``; ``tesis_sjf`` no puede citar sentencias de la Corte IDH. Si
    no lo es, PL-007.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "plan-ledger/1.0"

TIPOS_AFIRMACION = (
    "texto_normativo",
    "criterio_judicial",
    "hecho_aportado",
    "inferencia",
    "propuesta",
)
AUTORES = ("agente", "humano", "fuente")
NATURALEZAS = (
    "publicacion_oficial",
    "compilado_oficial",
    "portal_oficial",
    "secundaria",
    "sistema",
    "busqueda",
)
NATURALEZAS_OFICIALES = frozenset(
    {"publicacion_oficial", "compilado_oficial", "portal_oficial"}
)
CAMPOS_CRITERIO = (
    "rubro",
    "clave",
    "organo",
    "epoca",
    "registro",
    "integracion",
    "publicacion",
    "obligatoriedad",
    "fuerza_vinculante",
    "alcance",
)
# Identificación del criterio por tipo de fuente (piloto PEN-01, D8). Ver el docstring.
TESIS_SJF = "tesis_sjf"
SENTENCIA_INTERNACIONAL = "sentencia_internacional"
TIPOS_FUENTE_CRITERIO = (TESIS_SJF, SENTENCIA_INTERNACIONAL)
CAMPOS_SENTENCIA_INTERNACIONAL = ("caso", "serie_numero", "fecha", "parrafo")
CAMPOS_POR_TIPO_FUENTE = {
    TESIS_SJF: CAMPOS_CRITERIO,
    SENTENCIA_INTERNACIONAL: CAMPOS_SENTENCIA_INTERNACIONAL,
}
# Hosts cuyas evidencias, si son todas las que cita el criterio, lo hacen sentencia
# internacional cuando la identificación no declara ``tipo_fuente``.
HOSTS_SENTENCIA_INTERNACIONAL = frozenset({"www.corteidh.or.cr"})
# Hosts de tesis: una ``sentencia_internacional`` declarada no puede citarlos (ronda 2).
HOSTS_TESIS = frozenset({"sjf2.scjn.gob.mx", "sjfsemanal.scjn.gob.mx"})

_FECHA_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LedgerInvalido(ValueError):
    """El ledger no se pudo leer o no cumple el esquema ``plan-ledger/1.0``."""

    def __init__(self, errores: list[str]) -> None:
        self.errores = list(errores)
        resumen = "; ".join(self.errores[:5])
        if len(self.errores) > 5:
            resumen += f"; (+{len(self.errores) - 5} errores más)"
        super().__init__(resumen)


def fecha_iso(valor: Any) -> date | None:
    """Devuelve la fecha si ``valor`` es exactamente ``AAAA-MM-DD`` válido; si no, ``None``.

    Se exige el formato con guiones antes de ``date.fromisoformat`` porque desde
    Python 3.11 ese método también acepta variantes como ``20241231``.
    """
    if not isinstance(valor, str) or not _FECHA_RE.match(valor.strip()):
        return None
    try:
        return date.fromisoformat(valor.strip())
    except ValueError:
        return None


def _texto_no_vacio(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _requerir_texto(obj: dict, campo: str, ubicacion: str, errores: list[str]) -> None:
    if not _texto_no_vacio(obj.get(campo)):
        errores.append(f"{ubicacion}.{campo}: debe ser texto no vacío")


def _texto_opcional(obj: dict, campo: str, ubicacion: str, errores: list[str]) -> None:
    valor = obj.get(campo)
    if valor is not None and not isinstance(valor, str):
        errores.append(f"{ubicacion}.{campo}: debe ser texto o null")


def _lista_de_textos(
    obj: dict, campo: str, ubicacion: str, errores: list[str], *, requerida: bool
) -> None:
    if campo not in obj or obj[campo] is None:
        if requerida:
            errores.append(f"{ubicacion}.{campo}: es obligatorio (lista de textos)")
        return
    valor = obj[campo]
    if not isinstance(valor, list) or not all(_texto_no_vacio(item) for item in valor):
        errores.append(f"{ubicacion}.{campo}: debe ser lista de textos no vacíos")


def _enumeracion(
    obj: dict, campo: str, opciones: tuple[str, ...], ubicacion: str, errores: list[str]
) -> None:
    if obj.get(campo) not in opciones:
        errores.append(
            f"{ubicacion}.{campo}: {obj.get(campo)!r} no es uno de {list(opciones)}"
        )


def _coleccion(
    ledger: dict, campo: str, errores: list[str], *, requerida: bool
) -> list:
    if campo not in ledger or ledger[campo] is None:
        if requerida:
            errores.append(f"{campo}: es obligatorio (lista)")
        return []
    valor = ledger[campo]
    if not isinstance(valor, list):
        errores.append(f"{campo}: debe ser una lista")
        return []
    return valor


def _validar_afirmacion(item: Any, ubicacion: str, errores: list[str]) -> None:
    if not isinstance(item, dict):
        errores.append(f"{ubicacion}: debe ser un objeto")
        return
    _requerir_texto(item, "id", ubicacion, errores)
    _requerir_texto(item, "texto", ubicacion, errores)
    _enumeracion(item, "tipo", TIPOS_AFIRMACION, ubicacion, errores)
    _enumeracion(item, "autor", AUTORES, ubicacion, errores)
    _lista_de_textos(item, "referencias", ubicacion, errores, requerida=False)

    verificacion = item.get("verificacion")
    if not isinstance(verificacion, dict):
        errores.append(f"{ubicacion}.verificacion: debe ser un objeto")
    else:
        sub = f"{ubicacion}.verificacion"
        _requerir_texto(verificacion, "estado", sub, errores)
        _lista_de_textos(verificacion, "evidencias", sub, errores, requerida=False)
        _texto_opcional(verificacion, "motivo", sub, errores)

    for campo in ("identificacion_criterio", "aprobacion"):
        valor = item.get(campo)
        if valor is not None and not isinstance(valor, dict):
            errores.append(f"{ubicacion}.{campo}: debe ser un objeto o null")


def _validar_evidencia(item: Any, ubicacion: str, errores: list[str]) -> None:
    if not isinstance(item, dict):
        errores.append(f"{ubicacion}: debe ser un objeto")
        return
    _requerir_texto(item, "id", ubicacion, errores)
    _enumeracion(item, "naturaleza", NATURALEZAS, ubicacion, errores)
    for campo in (
        "url",
        "ubicacion",
        "extracto",
        "fecha_consulta",
        "sha256_documento",
        "consulta",
    ):
        _texto_opcional(item, campo, ubicacion, errores)
    resultados = item.get("resultados")
    if resultados is not None and (
        isinstance(resultados, bool) or not isinstance(resultados, int) or resultados < 0
    ):
        errores.append(f"{ubicacion}.resultados: debe ser entero no negativo o null")


def _validar_contradiccion(item: Any, ubicacion: str, errores: list[str]) -> None:
    if not isinstance(item, dict):
        errores.append(f"{ubicacion}: debe ser un objeto")
        return
    _requerir_texto(item, "id", ubicacion, errores)
    _lista_de_textos(item, "afirmaciones", ubicacion, errores, requerida=True)
    _texto_opcional(item, "descripcion", ubicacion, errores)
    _requerir_texto(item, "estado", ubicacion, errores)
    _texto_opcional(item, "decision_id", ubicacion, errores)


def _validar_decision(item: Any, ubicacion: str, errores: list[str]) -> None:
    if not isinstance(item, dict):
        errores.append(f"{ubicacion}: debe ser un objeto")
        return
    _requerir_texto(item, "id", ubicacion, errores)
    _requerir_texto(item, "pregunta", ubicacion, errores)
    _texto_opcional(item, "responsable", ubicacion, errores)
    _requerir_texto(item, "estado", ubicacion, errores)
    _lista_de_textos(item, "bloquea", ubicacion, errores, requerida=False)


def validar_esquema(ledger: Any) -> list[str]:
    """Devuelve los errores estructurales del ledger (lista vacía si es válido)."""
    if not isinstance(ledger, dict):
        return ["raíz: debe ser un objeto JSON"]
    errores: list[str] = []
    if ledger.get("schema_version") != SCHEMA_VERSION:
        errores.append(
            f"schema_version: se esperaba {SCHEMA_VERSION!r}, "
            f"se recibió {ledger.get('schema_version')!r}"
        )

    plan = ledger.get("plan")
    if not isinstance(plan, dict):
        errores.append("plan: debe ser un objeto")
    else:
        _requerir_texto(plan, "id", "plan", errores)
        _requerir_texto(plan, "titulo", "plan", errores)
        if fecha_iso(plan.get("fecha_documento")) is None:
            errores.append("plan.fecha_documento: debe ser una fecha AAAA-MM-DD válida")

    validadores = (
        ("afirmaciones", True, _validar_afirmacion),
        ("evidencias", True, _validar_evidencia),
        ("contradicciones", False, _validar_contradiccion),
        ("decisiones", False, _validar_decision),
    )
    for campo, requerida, validador in validadores:
        for indice, item in enumerate(
            _coleccion(ledger, campo, errores, requerida=requerida)
        ):
            validador(item, f"{campo}[{indice}]", errores)
    return errores


def cargar_ledger(ruta: str | Path) -> dict:
    """Lee un ledger JSON (UTF-8, con o sin BOM) y lo valida; lanza ``LedgerInvalido``."""
    ruta = Path(ruta)
    try:
        # utf-8-sig: PowerShell 5.1 escribe UTF-8 con BOM por defecto.
        crudo = ruta.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerInvalido([f"no se pudo leer {ruta}: {exc}"]) from exc
    try:
        ledger = json.loads(crudo)
    except json.JSONDecodeError as exc:
        raise LedgerInvalido([f"JSON inválido en {ruta}: {exc}"]) from exc
    errores = validar_esquema(ledger)
    if errores:
        raise LedgerInvalido(errores)
    return ledger
