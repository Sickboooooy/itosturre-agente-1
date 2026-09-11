"""Saneamiento previo a la escritura y a la consulta de la memoria.

Tres defensas, correspondientes a los riesgos E2, E3 y E4 del informe de
auditoría:

* ``redactar``      — enmascara secretos ANTES de que toquen SQLite.
* ``consulta_fts``  — convierte texto libre en una expresión ``MATCH`` inerte.
* ``ruta_relativa`` — ancla toda ruta al proyecto y rechaza la fuga hacia arriba.

Criterio deliberado en la redacción: **sobre-redactar**. Perder el valor de un
campo que resultó inocuo es un inconveniente; escribir un token de bot en una
base que luego se lee entera es una fuga de credenciales. El ``.env`` de este
repositorio contiene ``TELEGRAM_BOT_TOKEN``, así que el caso no es hipotético.

Módulo puro: sin E/S, sin dependencias fuera de la biblioteca estándar.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

REDACTADO = "[REDACTADO]"

#: Nombres de clave cuyo VALOR nunca debe persistirse.
_CLAVE_SECRETA = re.compile(
    r"(authorization|auth_token|access_token|refresh_token|bearer|token|secret|"
    r"password|passwd|pwd|contrasena|contraseña|api[-_]?key|apikey|cookie|"
    r"set-cookie|signature|private[-_]?key|client[-_]?secret|x[-_]?api[-_]?key|"
    r"credential|credencial)",
    re.IGNORECASE,
)

#: Formas de secreto reconocibles dentro de texto libre.
_VALOR_SECRETO: tuple[tuple[re.Pattern[str], str], ...] = (
    # Token de bot de Telegram: 123456789:AAH...
    (re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b"), REDACTADO),
    # Claves de proveedores de modelos y de GitHub.
    (re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{16,}\b"), REDACTADO),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), REDACTADO),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTADO),
    # Cabecera Authorization en texto.
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"), r"\1 " + REDACTADO),
    # Bloques de clave privada PEM.
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        REDACTADO,
    ),
    # Asignaciones tipo CLAVE=valor y `export CLAVE=valor`.
    (
        re.compile(
            r"(?i)\b((?:export\s+)?[A-Z0-9_]*"
            r"(?:TOKEN|SECRET|PASSWORD|PASSWD|APIKEY|API_KEY|CREDENTIAL)[A-Z0-9_]*)"
            r"\s*[=:]\s*\S+"
        ),
        r"\1=" + REDACTADO,
    ),
)


def redactar(valor: Any) -> tuple[Any, bool]:
    """Devuelve ``(valor_saneado, hubo_redaccion)`` recorriendo estructuras anidadas.

    Un diccionario se inspecciona por nombre de clave; cualquier texto, además,
    por forma del valor. Se preserva el tipo de la estructura para que quien
    llama pueda seguir tratándola igual.
    """
    return _redactar(valor, set())


def _redactar(valor: Any, vistos: set[int]) -> tuple[Any, bool]:
    if isinstance(valor, str):
        return _redactar_texto(valor)

    if isinstance(valor, dict):
        if id(valor) in vistos:  # estructura cíclica
            return valor, False
        vistos.add(id(valor))
        salida: dict[Any, Any] = {}
        tocado = False
        for clave, sub in valor.items():
            if isinstance(clave, str) and _CLAVE_SECRETA.search(clave):
                salida[clave] = REDACTADO
                tocado = True
                continue
            salida[clave], sub_tocado = _redactar(sub, vistos)
            tocado = tocado or sub_tocado
        return salida, tocado

    if isinstance(valor, (list, tuple)):
        if id(valor) in vistos:
            return valor, False
        vistos.add(id(valor))
        elementos = []
        tocado = False
        for sub in valor:
            saneado, sub_tocado = _redactar(sub, vistos)
            elementos.append(saneado)
            tocado = tocado or sub_tocado
        return (type(valor)(elementos) if isinstance(valor, tuple) else elementos), tocado

    return valor, False


def _redactar_texto(texto: str) -> tuple[str, bool]:
    salida = texto
    for patron, reemplazo in _VALOR_SECRETO:
        salida = patron.sub(reemplazo, salida)
    return salida, salida != texto


# ─────────────────────────────────────────
# Consulta FTS5
# ─────────────────────────────────────────

#: Un token es una secuencia de letras/dígitos Unicode. Todo lo demás se descarta.
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

#: Palabras vacías del español que solo añaden ruido al ranking BM25.
_VACIAS = frozenset(
    """a al ante bajo con contra de del desde durante en entre hacia hasta la las lo los
    mediante para por segun según sin sobre tras un una unas unos y o u e que qué cual cuál
    como cómo cuando cuándo donde dónde se su sus el ella ellas ellos es son fue era ser
    me mi mis te tu tus le les nos qué""".split()
)


def consulta_fts(texto: str, *, minimo: int = 2) -> str:
    """Convierte texto libre en una expresión ``MATCH`` segura e inerte.

    La sintaxis de ``MATCH`` de FTS5 tiene operadores propios (``"`` para frase,
    ``*`` para prefijo, ``NEAR``, ``OR``, ``-`` para negación). Interpolar texto
    del usuario ahí es inyectable aunque el SQL vaya parametrizado: una consulta
    con comillas sin cerrar aborta la sentencia, y una con ``NEAR`` cambia la
    semántica de la búsqueda.

    La defensa es no intentar escapar: se extraen únicamente tokens
    alfanuméricos Unicode y cada uno se emite como literal entrecomillado. Todo
    operador desaparece por construcción, no por lista negra.

    Devuelve cadena vacía si no queda ningún término útil; quien llama debe
    tratarlo como "sin consulta textual" y no ejecutar el MATCH.
    """
    normalizado = unicodedata.normalize("NFC", texto or "")
    terminos: list[str] = []
    for bruto in _TOKEN.findall(normalizado):
        token = bruto.lower()
        if token in _VACIAS:
            continue
        # Los números cortos importan en derecho ("art. 5", "sala 1"); las
        # palabras de una letra, no.
        if len(token) < minimo and not token.isdigit():
            continue
        if token not in terminos:
            terminos.append(token)

    if not terminos:
        return ""
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terminos)


# ─────────────────────────────────────────
# Rutas
# ─────────────────────────────────────────

def ruta_relativa(ruta: str | None, raiz: str | Path) -> str | None:
    """Ancla ``ruta`` al proyecto y devuelve una ruta POSIX relativa, o ``None``.

    Rechaza cualquier cosa que caiga fuera de ``raiz`` tras resolver ``..`` y
    enlaces: una ruta absoluta ajena, un ascenso con ``../../`` o —en Windows—
    otra unidad. Devolver ``None`` es deliberado: el evento se guarda sin
    ``file_path`` en vez de perderse por completo.
    """
    if not ruta:
        return None
    base = Path(raiz).resolve()
    candidata = Path(ruta)
    try:
        absoluta = (candidata if candidata.is_absolute() else base / candidata).resolve()
        relativa = absoluta.relative_to(base)
    except (ValueError, OSError):
        return None
    texto = relativa.as_posix()
    return texto or None
