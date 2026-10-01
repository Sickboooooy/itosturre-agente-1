"""Vocabulario único de estados del operador y aprobación ligada al contenido.

Dos dimensiones distintas que no deben mezclarse:

* **Verificación** (siete estados, campo ``verificacion.estado``): qué se sabe de la
  afirmación frente a las fuentes.
* **Aprobación** (campo ``aprobacion``): una persona humana aprobó *este* contenido
  exacto. ``APROBADO`` no es un estado de verificación; una afirmación solo se
  *muestra* como ``APROBADO`` cuando su aprobación es válida, y la aprobación se
  invalida en cuanto se edita el texto o el tipo (``contenido_sha256``).

Todas las funciones son puras: sin E/S, sin red y sin LLM.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Mapping

from .ledger import fecha_iso

CANDIDATO = "CANDIDATO"
VERIFICADO = "VERIFICADO"
NO_VERIFICADO = "NO VERIFICADO"
NO_VERIFICABLE = "NO VERIFICABLE"
INEXISTENTE = "INEXISTENTE"
CONTRADICCION = "CONTRADICCIÓN"
REQUIERE_DECISION_HUMANA = "REQUIERE DECISIÓN HUMANA"

ESTADOS_VERIFICACION = (
    CANDIDATO,
    VERIFICADO,
    NO_VERIFICADO,
    NO_VERIFICABLE,
    INEXISTENTE,
    CONTRADICCION,
    REQUIERE_DECISION_HUMANA,
)

# Dimensión de aprobación (no es estado de verificación).
APROBADO = "APROBADO"
# Lo que se muestra cuando el estado declarado está fuera del vocabulario.
ESTADO_INVALIDO = "ESTADO INVÁLIDO"

# Tokens de agente o sistema. Un responsable es no humano si su valor completo es uno
# de estos tokens ("Claude", "IA") o si empieza por uno seguido de una palabra de
# modelo/versión ("Claude Opus 5.5", "gpt-4o", "Codex CLI"). "Claude Martínez" y
# "Talbot" son personas válidas. "Itosturre" y "JustIA" NO están aquí a propósito: el
# operador los usa como responsables ("Itosturre (responsable jurídico)").
TOKENS_AGENTE = frozenset(
    {
        "agente",
        "ia",
        "llm",
        "bot",
        "sistema",
        "claude",
        "codex",
        "gpt",
        "chatgpt",
        "gemini",
        "grok",
        "copilot",
        "openai",
        "anthropic",
    }
)
PALABRAS_MODELO = frozenset(
    {
        "opus",
        "sonnet",
        "haiku",
        "fable",
        "cli",
        "code",
        "chat",
        "mini",
        "pro",
        "flash",
        "ultra",
        "turbo",
        "max",
        "nano",
        "api",
        "vvca",
    }
)
# Palabras que delatan a un agente en cualquier posición ("Claude (agente)",
# "itosclaude_bot", "revisión por IA").
PALABRAS_AGENTE_SUELTAS = frozenset({"agente", "llm", "bot", "ia"})

# Marcadores que emiten las skills cuando falta un dato: nunca cuentan como valor.
MARCADORES_PENDIENTES = ("[ASIGNAR", "[COMPLETAR", "[VERIFICAR", "[NO VERIFICADA")
MINIMO_LETRAS_PERSONA = 3

_TOKEN_RE = re.compile(r"[a-z]+|\d+(?:\.\d+)*")


def _sin_acentos(texto: str) -> str:
    return "".join(
        caracter
        for caracter in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caracter) != "Mn"
    )


def _clave_estado(texto: str) -> str:
    return " ".join(_sin_acentos(texto).upper().split())


_ESTADO_POR_CLAVE = {_clave_estado(estado): estado for estado in ESTADOS_VERIFICACION}


def normalizar_estado(texto: Any, *, admitir_aprobado: bool = False) -> str | None:
    """Devuelve la forma canónica del estado o ``None`` si está fuera del vocabulario.

    Tolera mayúsculas/minúsculas, acentos y espacios repetidos (``"contradiccion"`` →
    ``"CONTRADICCIÓN"``). Rechaza sinónimos y símbolos (``CONFIRMADO``, ``OK``,
    ``PENDIENTE``, ``✅``, ``🟢``). ``APROBADO`` solo se admite con
    ``admitir_aprobado=True`` (estado de decisiones y contradicciones resueltas),
    nunca como estado de verificación de una afirmación.
    """
    if not isinstance(texto, str):
        return None
    clave = _clave_estado(texto)
    if admitir_aprobado and clave == APROBADO:
        return APROBADO
    return _ESTADO_POR_CLAVE.get(clave)


def texto_canonico(texto: Any) -> str:
    """Texto en NFC con espacios colapsados; base del hash de contenido."""
    return " ".join(unicodedata.normalize("NFC", str(texto or "")).split())


def contenido_sha256(afirmacion: Mapping[str, Any]) -> str:
    """SHA-256 del tipo y el texto canónico de la afirmación.

    Liga la aprobación al contenido exacto: cualquier edición sustantiva del texto o
    del tipo cambia el hash e invalida la aprobación previa. Cambios de espacios o de
    forma de normalización Unicode no lo alteran.
    """
    tipo = str(afirmacion.get("tipo") or "").strip()
    carga = f"{tipo}\n{texto_canonico(afirmacion.get('texto'))}"
    return hashlib.sha256(carga.encode("utf-8")).hexdigest()


def es_marcador_pendiente(valor: Any) -> bool:
    """``True`` si el texto contiene un marcador de dato faltante (``[ASIGNAR]``…)."""
    if not isinstance(valor, str):
        return False
    normalizado = _sin_acentos(valor).upper()
    return any(marcador in normalizado for marcador in MARCADORES_PENDIENTES)


def responsable_no_humano(nombre: Any) -> bool:
    """``True`` si el nombre identifica a un agente, modelo o sistema.

    Reglas: el valor completo es un token de agente; o empieza por un token de agente
    seguido de una palabra de modelo, otro token de agente o una versión numérica; o
    contiene la palabra suelta ``agente``, ``llm``, ``bot`` o ``ia``.
    """
    if not isinstance(nombre, str):
        return False
    tokens = _TOKEN_RE.findall(_sin_acentos(nombre).lower())
    if not tokens:
        return False
    if len(tokens) == 1 and tokens[0] in TOKENS_AGENTE:
        return True
    if tokens[0] in TOKENS_AGENTE and len(tokens) > 1:
        segundo = tokens[1]
        if segundo in PALABRAS_MODELO or segundo in TOKENS_AGENTE or segundo[0].isdigit():
            return True
    return bool(PALABRAS_AGENTE_SUELTAS.intersection(tokens))


def problema_persona(valor: Any) -> str | None:
    """Motivo por el que ``valor`` no identifica a una persona humana (``None`` si sí).

    Se usa para ``aprobacion.por`` y ``decisiones[].responsable``.
    """
    if not isinstance(valor, str) or not valor.strip():
        return "vacío"
    if es_marcador_pendiente(valor):
        return "marcador pendiente"
    if sum(caracter.isalpha() for caracter in valor) < MINIMO_LETRAS_PERSONA:
        return f"no identifica a una persona (menos de {MINIMO_LETRAS_PERSONA} letras)"
    if responsable_no_humano(valor):
        return "es un agente o sistema"
    return None


def responsable_humano(nombre: Any) -> bool:
    """``True`` si el valor identifica a una persona humana (ver ``problema_persona``)."""
    return problema_persona(nombre) is None


def problemas_aprobacion(afirmacion: Mapping[str, Any]) -> list[str]:
    """Motivos por los que la aprobación de la afirmación no es válida (``[]`` si lo es).

    Sin aprobación (``null`` o ausente) no hay problemas que reportar.
    """
    aprobacion = afirmacion.get("aprobacion")
    if aprobacion is None:
        return []
    if not isinstance(aprobacion, Mapping):
        return ["la aprobación no es un objeto"]

    problemas: list[str] = []
    por = aprobacion.get("por")
    en = aprobacion.get("en")
    sha = aprobacion.get("contenido_sha256")
    faltantes = [
        campo
        for campo, valor in (("por", por), ("en", en), ("contenido_sha256", sha))
        if not (isinstance(valor, str) and valor.strip())
    ]
    if faltantes:
        problemas.append("faltan campos de aprobación: " + ", ".join(faltantes))
    if isinstance(por, str) and por.strip():
        motivo = problema_persona(por)
        if motivo:
            problemas.append(f"'por' no identifica a una persona humana ({por.strip()!r}: {motivo})")
    if isinstance(en, str) and en.strip() and fecha_iso(en) is None:
        problemas.append(f"fecha de aprobación inválida ({en!r}); se espera AAAA-MM-DD")
    if (
        isinstance(sha, str)
        and sha.strip()
        and sha.strip().lower() != contenido_sha256(afirmacion)
    ):
        problemas.append(
            "contenido_sha256 no coincide con el contenido actual "
            "(se editó la afirmación o la aprobación corresponde a otra)"
        )
    return problemas


def aprobacion_valida(afirmacion: Mapping[str, Any]) -> bool:
    """``True`` solo si existe aprobación y no tiene ningún problema."""
    return afirmacion.get("aprobacion") is not None and not problemas_aprobacion(afirmacion)


def estado_mostrado(afirmacion: Mapping[str, Any]) -> str:
    """Estado que se muestra al operador.

    ``APROBADO`` si la aprobación es válida; en otro caso el estado de verificación
    canónico, o ``ESTADO INVÁLIDO`` si el declarado está fuera del vocabulario.
    """
    if aprobacion_valida(afirmacion):
        return APROBADO
    verificacion = afirmacion.get("verificacion")
    estado = (
        normalizar_estado(verificacion.get("estado"))
        if isinstance(verificacion, Mapping)
        else None
    )
    return estado or ESTADO_INVALIDO
