"""Cotejo de identidad (C9): ¿la evidencia citada es el documento oficial registrado?

Para cada par (afirmación, evidencia citada) se comprueba, contra un paquete de
evidencia (``itosturre/evidencia/paquete.py``), que la evidencia del ledger es un
documento oficial registrado con procedencia (D4), que sus datos identificatorios y su
extracto coinciden con él y que la afirmación habla de ese documento (registro, clave o
artículo que menciona). **Identidad no es fidelidad:** aquí no se compara lo que la
afirmación dice con lo que la fuente dice (eso es PR-4). **Verificación no es
aprobación (D3):** el cotejo informa; nunca aprueba ni cambia estados del ledger.

Resultado por par: ``CONFORME`` | ``DISCREPANTE`` | ``SIN_EVIDENCIA`` (más
``NO_COTEJADO`` para afirmaciones ``INEXISTENTE``: la inexistencia exige prueba
positiva y queda fuera de este cotejo). Cada resultado trae sus motivos (campo, valor
del ledger, valor de la fuente) y las advertencias heredadas del registro.

Orden de comprobaciones; cada paso falla cerrado y el cotejo se detiene en el primero
que falla (salvo el f, que reúne todos los campos):

  a. **Vínculo.** La evidencia trae ``sha256_documento``; su naturaleza es oficial; su
     URL corresponde a un tipo soportado (tesis del SJF o ley de LeyesBiblio; DOF y
     Corte IDH → "tipo no soportado"); el paquete tiene exactamente un registro cuyo
     ``original.sha256`` es ese y cuya ``fuente.url`` es exactamente esa URL. Ninguno,
     o más de uno (ambigüedad: no se elige) → SIN_EVIDENCIA.
  b. **Registro utilizable.** ``validar_registro`` sin problemas → si no, SIN_EVIDENCIA.
  c. **Integridad.** Con los objetos del paquete, ``comprobar_integridad`` sin
     problemas. Objeto ausente → SIN_EVIDENCIA (no comprobable). Objeto o registro
     alterado, o problemas de integridad → DISCREPANTE. Ley: además, **relación
     original–texto**: el texto extraído registrado debe reproducirse re-extrayendo el
     original con un extractor inyectado del mismo nombre y versión que el registro
     declara. Sin ese extractor, o si la re-extracción falla → SIN_EVIDENCIA ("relación
     original–texto no comprobable"); si se re-extrae y difiere → DISCREPANTE.
  d. **Documento y versión (antes que rubro o subcadena).** Tesis: el
     ``identificacion_criterio.registro`` de la afirmación es el registro digital de la
     fuente, antes que nada; después, los registros digitales y claves que la
     afirmación menciona en ``texto`` o ``referencias`` deben incluir los de la fuente
     (si menciona alguno y ninguno es el de la fuente → DISCREPANTE). Ley: el
     ordenamiento ya quedó fijado por URL + huella; la versión es
     ``metadatos.ultima_reforma_dof`` del registro y, si la evidencia del ledger trae
     ``ultima_reforma_dof`` (campo opcional, AAAA-MM-DD), debe coincidir; si no lo
     trae, el resultado expone la versión de la fuente. En ambos tipos, la
     ``fecha_consulta`` del ledger es el día de ``fuente.fecha_consulta`` del registro
     (tal como está escrito, sin conversión de zona horaria).
  e. **Ubicación.** Ley: el artículo de ``ubicacion`` (parser estricto: exactamente un
     artículo; enumeraciones y rangos no) debe ser ``unica`` en el cuerpo según
     ``ubicar_articulo`` sobre el documento reconstruido del paquete; zona
     indeterminada, ambigua, solo en transitorios o sin coincidencia → SIN_EVIDENCIA
     con las advertencias de ``ubicar_articulo`` (nunca se lee como inexistencia).
     Después, los artículos que la afirmación menciona (con su ordenamiento, si lo
     dice) se contrastan con el artículo ubicado y el ordenamiento de la evidencia
     (``ordenamiento_de``: archivo de la URL **y** título del encabezado deben
     corresponder a la misma sigla de ``menciones.LEYES``; sin correspondencia no se
     supone nada): si alguno coincide, sigue; si ninguno coincide y alguno no se puede
     decidir → SIN_EVIDENCIA; si todos contradicen → DISCREPANTE. Tesis: un registro
     digital mencionado en ``ubicacion`` debe ser el de la fuente.
  f. **Campos y extracto.** Tesis: clave, época, tipo frente a ``fuerza_vinculante``
     (``[J]`` ↔ Jurisprudencia, ``[TA]`` ↔ Aislada) y rubro por igualdad normalizada
     son críticos: si faltan en el ledger o en la fuente, el par no puede ser
     CONFORME. Fechas de publicación y obligatoriedad se cotejan solo si el ledger las
     da en forma interpretable (``lunes 28 de abril de 2014`` o ISO); con varias fechas,
     si ninguna coincide → DISCREPANTE y si alguna coincide → SIN_EVIDENCIA
     (ambigüedad). Órgano, integración y alcance no tienen correspondencia confiable y
     se reportan "no cotejado". Ley: el ``extracto`` debe ser subcadena normalizada del
     texto del artículo ubicado (no del documento entero). Un extracto rotulado como
     sintético o con marcadores pendientes nunca es conforme.
  g. **Advertencias de la fuente.** Un CONFORME cuyo registro trae advertencias (p. ej.
     ``epoca_discrepante`` del registro 2031931) se marca
     ``requiere_decision_humana=True``. No se resuelve aquí: lo atiende una decisión
     humana con ``advertencias_fuente`` (``problemas_decision_advertencias``).

Agregado por afirmación: INEXISTENTE → NO_COTEJADO; cualquier DISCREPANTE domina; es
CONFORME solo si hay algún par CONFORME **y** cada registro, clave o artículo que la
afirmación menciona queda cubierto por un par CONFORME (registros y claves se exigen si
la afirmación es ``criterio_judicial`` o cita alguna tesis; artículos, si es
``texto_normativo`` o cita alguna ley). En otro caso, SIN_EVIDENCIA. Una afirmación
sin menciones identificables deja una nota visible. ``ESTADO_SOSTENIBLE`` documenta el
estado más fuerte que cada resultado puede sostener: SIN_EVIDENCIA ⇒ a lo sumo
``NO VERIFICABLE``.

Rubro: se compara con ``normalizar_para_cotejo`` tras quitar comillas envolventes y
**un** punto final, que la práctica de cita suele omitir; cualquier otro signo cuenta.

Época de una fuente discrepante: si el registro trae ``epoca_discrepante``, se acepta
la época del ledger que coincida con cualquiera de las dos que reporta la fuente (campo o
sufijo de la clave) y el par queda en ``requiere_decision_humana``.

El cotejo lleva la huella del ledger (``huella_ledger``) y la del paquete sobre las que
se calculó; ``CotejoLedger.problemas_correspondencia`` detecta un cotejo reutilizado
con otro contenido.

Puro: sin red, reloj ni E/S propia. Lee el paquete solo a través del objeto ya cargado
que recibe (``buscar``, ``objeto(huella)``, ``problemas`` y ``huella()``) y re-extrae
con los ``Extractor`` que se le inyectan.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlsplit

from ..evidencia.esquema import (
    EPOCAS,
    TIPO_LEY_LEYESBIBLIO,
    TIPO_TESIS_SJF,
    es_marcador_pendiente,
    validar_registro,
)
from ..evidencia.fuentes import (
    HOST_LEYESBIBLIO,
    HOST_SJF,
    RUTA_LEYESBIBLIO,
    RUTA_TESIS_SJF,
    host_de,
    url_oficial,
)
from ..evidencia.huellas import es_sha256, normalizar_para_cotejo
from ..evidencia.integridad import comprobar_integridad
from ..evidencia.leyesbiblio import (
    SEPARADOR_PAGINAS,
    CoincidenciaArticulo,
    DocumentoLeyesBiblio,
    encabezado_articulo,
    es_frontera_transitorios,
    identificador_canonico,
    limpiar_documento,
    ubicar_articulo,
)
from ..evidencia.paquete import ObjetoCorrupto
from ..evidencia.sjf import ErrorSJF, TesisSJF, parsear_tesis
from .estados import (
    APROBADO,
    INEXISTENTE,
    NO_VERIFICABLE,
    NO_VERIFICADO,
    VERIFICADO,
    normalizar_estado,
    problema_persona,
)
from .ledger import NATURALEZAS_OFICIALES, LedgerInvalido, fecha_iso, validar_esquema
from .menciones import ARTICULO, CLAVE, LEYES, REGISTRO, Mencion, extraer_menciones

ESQUEMA_COTEJO = "cotejo-identidad/1.0"

CONFORME = "CONFORME"
DISCREPANTE = "DISCREPANTE"
SIN_EVIDENCIA = "SIN_EVIDENCIA"
NO_COTEJADO = "NO_COTEJADO"
RESULTADOS = (CONFORME, DISCREPANTE, SIN_EVIDENCIA, NO_COTEJADO)

# Estado de verificación más fuerte que cada resultado puede sostener. Es informativo:
# el cotejo nunca cambia estados (D3). CONFORME sostiene VERIFICADO sujeto a lo que
# decida la persona responsable si ``requiere_decision_humana``; nunca APROBADO.
ESTADO_SOSTENIBLE = MappingProxyType(
    {
        CONFORME: VERIFICADO,
        DISCREPANTE: NO_VERIFICADO,
        SIN_EVIDENCIA: NO_VERIFICABLE,
        NO_COTEJADO: None,
    }
)

PASOS = MappingProxyType(
    {
        "a": "vínculo",
        "b": "registro utilizable",
        "c": "integridad",
        "d": "documento y versión",
        "e": "ubicación",
        "f": "campos y extracto",
        "h": "menciones de la afirmación",
    }
)

# Clases de motivo.
DISCREPANCIA = "discrepancia"  # el ledger contradice a la fuente → DISCREPANTE
NO_COMPROBABLE = "sin_evidencia"  # no se puede establecer la identidad → SIN_EVIDENCIA
NO_COTEJADO_CAMPO = "no_cotejado"  # informativo: el campo no se comparó
OBSERVACION = "observacion"  # informativo: coincide con reserva

CAMPOS_CRITICOS_TESIS = ("registro", "clave", "rubro", "epoca", "fuerza_vinculante")
CAMPOS_NO_COTEJADOS_TESIS = ("organo", "integracion", "alcance")
# Igual que PL-005: menos de 20 caracteres no acreditan nada como subcadena.
EXTRACTO_MINIMO = 20

TIPOS_SOPORTADOS = (TIPO_TESIS_SJF, TIPO_LEY_LEYESBIBLIO)

# Archivo de LeyesBiblio → sigla de ``menciones.LEYES``. La correspondencia solo se usa
# si además el título del encabezado del documento registrado es un nombre de esa
# sigla (``ordenamiento_de``): un nombre de archivo mal supuesto aquí nunca produce un
# ordenamiento equivocado, solo "sin correspondencia".
ARCHIVOS_LEYESBIBLIO = MappingProxyType(
    {
        "CPEUM.pdf": "CPEUM",
        "CNPP.pdf": "CNPP",
        "CPF.pdf": "CPF",
        "CFF.pdf": "CFF",
        "LAmp.pdf": "LA",
        "LNEP.pdf": "LNEP",
    }
)

# Llave opcional de una decisión del ledger (esquema 1.0 la ignora) con la que una
# persona atiende las advertencias de la fuente de una evidencia.
CAMPO_DECISION_ADVERTENCIAS = "advertencias_fuente"


# ── Resultados ───────────────────────────────────────────────────────────────


def _recortar(valor: Any, limite: int = 160) -> Any:
    if isinstance(valor, str) and len(valor) > limite:
        return valor[: limite - 1] + "…"
    return valor


@dataclass(frozen=True)
class Motivo:
    """Por qué un par no es CONFORME (o qué no se cotejó). Los valores van crudos."""

    paso: str
    campo: str
    clase: str
    detalle: str
    ledger: Any = None
    fuente: Any = None

    def resumen(self) -> str:
        valores = [
            f"{nombre} {_recortar(valor, 80)!r}"
            for nombre, valor in (("ledger", self.ledger), ("fuente", self.fuente))
            if valor is not None
        ]
        texto = f"{self.campo}: {self.detalle}"
        return texto + (f" ({'; '.join(valores)})" if valores else "")

    def como_dict(self) -> dict:
        return {
            "paso": self.paso,
            "campo": self.campo,
            "clase": self.clase,
            "detalle": self.detalle,
            "ledger": self.ledger,
            "fuente": self.fuente,
        }


@dataclass(frozen=True)
class ResultadoPar:
    """Cotejo de una evidencia citada por una afirmación."""

    afirmacion: str
    evidencia: str
    resultado: str
    paso: str | None  # paso en el que se detuvo (None si CONFORME o NO_COTEJADO)
    motivos: tuple[Motivo, ...] = ()
    notas: tuple[Motivo, ...] = ()  # no cotejado u observaciones (no impiden CONFORME)
    advertencias_fuente: tuple[dict, ...] = ()
    advertencias_ubicacion: tuple[dict, ...] = ()
    requiere_decision_humana: bool = False
    tipo_fuente: str | None = None
    documento_fuente: str | None = None
    version_fuente: str | None = None
    fecha_consulta_fuente: str | None = None
    huella_registro: str | None = None
    sha256_documento: str | None = None  # huella del original registrado
    registro_fuente: str | None = None  # tesis: registro digital
    clave_fuente: str | None = None  # tesis: clave
    articulo_fuente: str | None = None  # ley: identificador del artículo ubicado
    ordenamiento_fuente: str | None = None  # ley: sigla (``ordenamiento_de``)
    origen_texto: str | None = None  # ley: "extraido" | "declarado" | None

    @property
    def codigos_advertencia(self) -> tuple[str, ...]:
        return tuple(sorted({str(a.get("codigo", "?")) for a in self.advertencias_fuente}))

    def como_dict(self) -> dict:
        return {
            "afirmacion": self.afirmacion,
            "evidencia": self.evidencia,
            "resultado": self.resultado,
            "paso": self.paso,
            "motivos": [m.como_dict() for m in self.motivos],
            "notas": [m.como_dict() for m in self.notas],
            "advertencias_fuente": [dict(a) for a in self.advertencias_fuente],
            "advertencias_ubicacion": [dict(a) for a in self.advertencias_ubicacion],
            "requiere_decision_humana": self.requiere_decision_humana,
            "tipo_fuente": self.tipo_fuente,
            "documento_fuente": self.documento_fuente,
            "version_fuente": self.version_fuente,
            "fecha_consulta_fuente": self.fecha_consulta_fuente,
            "huella_registro": self.huella_registro,
            "sha256_documento": self.sha256_documento,
            "registro_fuente": self.registro_fuente,
            "clave_fuente": self.clave_fuente,
            "articulo_fuente": self.articulo_fuente,
            "ordenamiento_fuente": self.ordenamiento_fuente,
            "origen_texto": self.origen_texto,
        }


@dataclass(frozen=True)
class ResultadoAfirmacion:
    """Agregado de los pares de una afirmación."""

    afirmacion: str
    estado_declarado: str | None
    resultado: str
    requiere_decision_humana: bool
    pares: tuple[ResultadoPar, ...]
    motivos: tuple[Motivo, ...] = ()  # menciones no cubiertas por pares CONFORME
    notas: tuple[Motivo, ...] = ()

    @property
    def estado_sostenible(self) -> str | None:
        return ESTADO_SOSTENIBLE[self.resultado]

    @property
    def es_hallazgo(self) -> bool:
        """``True`` si este agregado impide decir "todo conforme".

        Con pares: todo lo que no es CONFORME limpio. Sin pares: una afirmación que se
        declara VERIFICADO o INEXISTENTE (o con estado inválido) sin evidencias que
        cotejar.
        """
        if self.pares:
            return self.resultado != CONFORME or self.requiere_decision_humana
        return self.estado_declarado in (VERIFICADO, INEXISTENTE, None)

    def como_dict(self) -> dict:
        return {
            "afirmacion": self.afirmacion,
            "estado_declarado": self.estado_declarado,
            "resultado": self.resultado,
            "requiere_decision_humana": self.requiere_decision_humana,
            "estado_sostenible": self.estado_sostenible,
            "evidencias": [p.evidencia for p in self.pares],
            "motivos": [m.como_dict() for m in self.motivos],
            "notas": [m.como_dict() for m in self.notas],
            "es_hallazgo": self.es_hallazgo,
        }


def huella_ledger(ledger: Mapping[str, Any]) -> str:
    """SHA-256 de una serialización determinista del ledger (llaves ordenadas)."""
    texto = json.dumps(ledger, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CotejoLedger:
    """Cotejo de todo el ledger. ``afirmaciones`` sigue el orden del ledger.

    ``huella_ledger`` y ``huella_paquete`` identifican el contenido sobre el que se
    calculó: un cotejo no se reutiliza con otro ledger (``problemas_correspondencia``).
    """

    afirmaciones: tuple[ResultadoAfirmacion, ...]
    problemas_paquete: tuple[str, ...] = ()
    huella_ledger: str | None = None
    huella_paquete: str | None = None

    @property
    def pares(self) -> tuple[ResultadoPar, ...]:
        return tuple(par for agregado in self.afirmaciones for par in agregado.pares)

    def resumen(self) -> dict[str, int]:
        conteo = {resultado: 0 for resultado in RESULTADOS}
        for par in self.pares:
            conteo[par.resultado] += 1
        conteo["requieren_decision_humana"] = sum(p.requiere_decision_humana for p in self.pares)
        conteo["afirmaciones_con_hallazgo"] = sum(a.es_hallazgo for a in self.afirmaciones)
        return conteo

    @property
    def todo_conforme(self) -> bool:
        """Paquete sin problemas y ninguna afirmación con hallazgo (``es_hallazgo``)."""
        return not self.problemas_paquete and not any(a.es_hallazgo for a in self.afirmaciones)

    def problemas_correspondencia(self, ledger: Mapping[str, Any], paquete: Any = None) -> list[str]:
        """Por qué este cotejo no corresponde al ``ledger`` (y al ``paquete``, si se da)."""
        problemas = []
        if self.huella_ledger != huella_ledger(ledger):
            problemas.append(
                "el cotejo se calculó sobre otro contenido del ledger (huella "
                f"{self.huella_ledger} frente a {huella_ledger(ledger)}): volver a cotejar"
            )
        if paquete is not None:
            actual = _huella_de_paquete(paquete)
            if actual != self.huella_paquete:
                problemas.append(
                    f"el cotejo se calculó sobre otro estado del paquete ({self.huella_paquete} frente a {actual})"
                )
        return problemas

    def como_dict(self) -> dict:
        return {
            "esquema": ESQUEMA_COTEJO,
            "huella_ledger": self.huella_ledger,
            "huella_paquete": self.huella_paquete,
            "resumen": self.resumen(),
            "todo_conforme": self.todo_conforme,
            "problemas_paquete": list(self.problemas_paquete),
            "pares": [par.como_dict() for par in self.pares],
            "afirmaciones": [agregado.como_dict() for agregado in self.afirmaciones],
        }


def _huella_de_paquete(paquete: Any) -> str | None:
    huella = getattr(paquete, "huella", None)
    return huella() if callable(huella) else None


@dataclass(frozen=True)
class Extractor:
    """Extractor de texto por página de un original, inyectado (la capa no importa PyMuPDF).

    ``extraer(original)`` devuelve el texto de **todas** las páginas, en orden. Solo
    se usa si ``nombre`` y ``version`` son exactamente los que declara el registro.
    """

    nombre: str
    version: str
    extraer: Callable[[bytes], Sequence[str]]


# ── Normalizaciones y lectores estrictos de valores del ledger ──────────────


def _valor_texto(valor: Any) -> tuple[str | None, str | None]:
    """``(texto, None)`` si es dato utilizable; ``(None, motivo)`` si no lo es."""
    if valor is None:
        return None, "ausente"
    if not isinstance(valor, str):
        return None, f"no es texto ({type(valor).__name__})"
    if not valor.strip():
        return None, "vacío"
    if es_marcador_pendiente(valor):
        return None, "marcador pendiente"
    return valor, None


_REGISTRO_LEDGER = re.compile(r"^(?:(?:registro|reg\.)(?:\s+digital)?(?:\s+ius)?\s*(?:no\.?)?\s*[:#]?\s*)?(\d{1,8})\.?$")


def _registro_ledger(valor: str) -> str | None:
    """Registro digital del ledger ("2006224", "Registro digital: 2006224"); ``None`` si no."""
    coincidencia = _REGISTRO_LEDGER.match(normalizar_para_cotejo(valor))
    return str(int(coincidencia.group(1))) if coincidencia else None


_ORDINALES_EPOCA = {
    normalizar_para_cotejo(epoca.split()[0]): epoca for epoca in EPOCAS
}
_EPOCA_NUMERICA = re.compile(r"^\(?\s*(\d{1,2})\s*a\.?\s*\)?$")


def _epoca_canonica(valor: str) -> str | None:
    """"Décima Época", "décima", "10a. Época", "(10a.)" → "Décima Época"; ``None`` si no."""
    texto = re.sub(r"\bepoca\b", " ", normalizar_para_cotejo(valor))
    texto = " ".join(texto.split()).strip(" .,;")
    if texto in _ORDINALES_EPOCA:
        return _ORDINALES_EPOCA[texto]
    numero = _EPOCA_NUMERICA.match(texto)
    if numero and 5 <= int(numero.group(1)) <= 12:
        return EPOCAS[int(numero.group(1)) - 5]
    return None


def _tipo_de_fuerza(valor: str) -> str | None:
    """``[J]``/"jurisprudencia" → "Jurisprudencia"; ``[TA]``/"aislada" → "Aislada"."""
    texto = normalizar_para_cotejo(valor)
    tipos = set()
    if re.search(r"\[\s*j\s*\]", texto) or re.search(r"\bjurisprudencia\b", texto):
        tipos.add("Jurisprudencia")
    if re.search(r"\[\s*ta\s*\]", texto) or re.search(r"\baislada\b", texto):
        tipos.add("Aislada")
    return tipos.pop() if len(tipos) == 1 else None


def _tipo_de_fuente(valor: Any) -> str | None:
    if not isinstance(valor, str):
        return None
    return {"jurisprudencia": "Jurisprudencia", "aislada": "Aislada"}.get(normalizar_para_cotejo(valor))


_SUFIJO_EPOCA = re.compile(r"\s*\(\s*\d{1,2}\s*a\.?\s*\)\s*$", re.IGNORECASE)


def _forma_clave(valor: str) -> str:
    return re.sub(r"\s+", "", normalizar_para_cotejo(valor))


_COMILLAS = {'"': '"', "“": "”", "«": "»", "'": "'", "‘": "’"}


def forma_rubro(valor: str) -> str:
    """Forma de comparación del rubro: normalizada, sin comillas envolventes ni un punto final."""
    texto = valor.strip()
    if len(texto) >= 2 and _COMILLAS.get(texto[0]) == texto[-1]:
        texto = texto[1:-1]
    texto = normalizar_para_cotejo(texto)
    if texto.endswith("."):
        texto = texto[:-1].rstrip()
    return texto


_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
)
_DIAS = ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo")
_FECHA_LARGA = re.compile(
    r"(?:\b(?P<dia_semana>" + "|".join(_DIAS) + r"),?\s+)?"
    r"\b(?P<dia>\d{1,2})\s+de\s+(?P<mes>" + "|".join(_MESES) + r"|setiembre)\s+de\s+(?P<anio>\d{4})\b"
)
_FECHA_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def fechas_declaradas(valor: str) -> tuple[list[date], list[str]]:
    """Fechas completas que trae un texto del ledger y los problemas de interpretación.

    Reconoce ``[día de la semana] DD de MES de AAAA`` y ``AAAA-MM-DD``. Un día de la
    semana que no corresponde al calendario o una fecha imposible es un problema.
    """
    texto = normalizar_para_cotejo(valor)
    fechas: list[date] = []
    problemas: list[str] = []
    for coincidencia in _FECHA_LARGA.finditer(texto):
        mes = coincidencia.group("mes")
        numero_mes = 9 if mes == "setiembre" else _MESES.index(mes) + 1
        try:
            fecha = date(int(coincidencia.group("anio")), numero_mes, int(coincidencia.group("dia")))
        except ValueError:
            problemas.append(f"fecha imposible {coincidencia.group(0)!r}")
            continue
        dia_semana = coincidencia.group("dia_semana")
        if dia_semana and dia_semana != _DIAS[fecha.weekday()]:
            problemas.append(
                f"{coincidencia.group(0)!r}: el {fecha.isoformat()} fue {_DIAS[fecha.weekday()]}"
            )
        fechas.append(fecha)
    for coincidencia in _FECHA_ISO.finditer(texto):
        fecha = fecha_iso(coincidencia.group(0))
        if fecha is None:
            problemas.append(f"fecha imposible {coincidencia.group(0)!r}")
        else:
            fechas.append(fecha)
    return fechas, problemas


# Rótulos de dato sintético o ficticio (lista cerrada). No basta la palabra suelta
# "sintético": hay textos normativos que la usan ("sustancias sintéticas").
_ROTULO_SINTETICO = re.compile(
    r"[\[(]\s*(?:dato\s+|extracto\s+|rubro\s+)?(?:sintetic|fictici)[oa]s?\b"
    r"|\b(?:sintetic|fictici)[oa]s?\s+de\s+prueba\b"
    r"|\bprueba\s+(?:sintetic|fictici)[oa]s?\b"
)


def rotulado_como_sintetico(valor: str) -> bool:
    """``True`` si el texto se declara sintético o ficticio (nunca cuenta como cita)."""
    return bool(_ROTULO_SINTETICO.search(normalizar_para_cotejo(valor)))


_SUFIJOS_LATINOS = "bis|ter|quater|quinquies|sexies|septies|octies|nonies|decies"
_SUFIJOS = frozenset(_SUFIJOS_LATINOS.split("|"))
_UBICACION_ARTICULO = re.compile(
    r"(?<![\w.])(?P<palabra>art[ií]culos?|arts?\.)\s*"
    r"(?P<id>\d{1,4}"
    r"(?:\s*[oº°](?![a-z0-9])\.?)?"
    # Letra pegada al guion ("4o.-A"): con espacio ("1o.- A quien…") es texto, no letra.
    r"(?:\.?-[A-Z](?![A-Za-z]))?"
    r"(?:\s*-?\s*(?:" + _SUFIJOS_LATINOS + r")(?![a-z]))?)",
    re.IGNORECASE,
)
# Tras el identificador, otro número unido por coma, "y", "a", "al", "hasta" o un guion
# es una enumeración o un rango ("167, 168", "167 y 168", "167 a 170", "167-170").
_CONTINUACION_ARTICULOS = re.compile(
    r"\s*(?:,|;|/|\by\b|\be\b|\ba\b|\bal\b|\bhasta\b|-|–|—)\s*(?:(?:el|los)\s+)?"
    r"(?:art[ií]culos?\s*|arts?\.\s*)?\d",
    re.IGNORECASE,
)


def articulo_de_ubicacion(valor: Any) -> str | None:
    """Identificador del único artículo de la ubicación (``"Artículo 2o."`` → ``"2o"``).

    Parser estricto: exactamente un artículo. Enumeraciones, rangos y el plural
    ("Artículos 167 a 170") no se interpretan. Conserva el ordinal, la letra y el sufijo
    latino, que ``ubicar_articulo`` distingue ("1" ≠ "1o", "4o" ≠ "4o.-A"). ``None`` si
    no se puede interpretar sin ambigüedad.
    """
    texto, problema = _valor_texto(valor)
    if problema:
        return None
    coincidencias = list(_UBICACION_ARTICULO.finditer(texto))
    articulos = [m for m in extraer_menciones(texto) if m.tipo == ARTICULO]
    if len(coincidencias) != 1 or len(articulos) != 1:
        return None
    coincidencia = coincidencias[0]
    palabra = normalizar_para_cotejo(coincidencia.group("palabra"))
    if palabra in ("articulos", "arts."):
        return None
    if _CONTINUACION_ARTICULOS.match(texto, coincidencia.end()):
        return None
    identificador = coincidencia.group("id").strip().rstrip(".").strip()
    numero = re.match(r"\d+", identificador)
    if not numero or articulos[0].clave.split()[1] != str(int(numero.group(0))):
        return None
    return identificador


def clave_articulo(identificador: str) -> str | None:
    """Clave de ``menciones`` de un identificador de artículo (``"1o"`` → ``"art. 1"``).

    ``menciones`` no distingue el ordinal ("1" y "1o." son el mismo artículo) pero sí el
    sufijo latino. Una letra ("4o.-A") o un ordinal escrito ("Único") no tienen clave:
    ``None``, para que nunca coincidan por error con "art. 4".
    """
    canonico = identificador_canonico(identificador)
    numero = re.match(r"\d+", canonico)
    if not numero:
        return None
    resto = canonico[numero.end():]
    base = f"art. {int(numero.group(0))}"
    if not resto:
        return base
    if resto in _SUFIJOS:
        return f"{base} {resto}"
    if resto.startswith("o") and (resto[1:] == "" or resto[1:] in _SUFIJOS):
        return f"{base} {resto[1:]}".rstrip()
    return None


def _base_articulo(identificador: str) -> str | None:
    numero = re.match(r"\d+", identificador_canonico(identificador))
    return str(int(numero.group(0))) if numero else None


def titulo_corresponde(titulo: Any, sigla: str) -> bool:
    """``True`` si el título del encabezado es uno de los nombres de ``sigla`` en ``LEYES``.

    Igualdad normalizada, o el nombre seguido de coma ("LEY DE AMPARO, REGLAMENTARIA…").
    """
    if not isinstance(titulo, str) or sigla not in LEYES:
        return False
    texto = normalizar_para_cotejo(titulo)
    return any(
        texto == normalizar_para_cotejo(nombre) or texto.startswith(normalizar_para_cotejo(nombre) + ",")
        for nombre in LEYES[sigla][1]
    )


def ordenamiento_de(archivo: Any, titulo: Any) -> tuple[str | None, str | None]:
    """``(sigla, None)`` si el archivo y el título del encabezado corresponden a la misma
    sigla de ``menciones.LEYES``; ``(None, motivo)`` si no se puede establecer. Nunca supone."""
    sigla = ARCHIVOS_LEYESBIBLIO.get(archivo) if isinstance(archivo, str) else None
    if sigla is None:
        return None, f"el archivo {archivo!r} no tiene correspondencia registrada con un ordenamiento"
    if not isinstance(titulo, str) or not titulo.strip():
        return None, "el documento no fija un título en su encabezado"
    if not titulo_corresponde(titulo, sigla):
        return None, f"el título del encabezado {titulo!r} no corresponde a {sigla} ({archivo})"
    return sigla, None


# ── Menciones de la afirmación ───────────────────────────────────────────────


@dataclass(frozen=True)
class MencionesAfirmacion:
    """Registros, claves y artículos que la afirmación menciona en ``texto`` y ``referencias``."""

    registros: tuple[str, ...]
    claves: tuple[Mencion, ...]
    articulos: tuple[Mencion, ...]

    @property
    def vacias(self) -> bool:
        return not (self.registros or self.claves or self.articulos)


def menciones_de_afirmacion(afirmacion: Mapping[str, Any]) -> MencionesAfirmacion:
    """Menciones de ``texto`` y ``referencias`` (extractor de ``menciones.py``)."""
    registros: dict[str, None] = {}
    claves: dict[tuple, Mencion] = {}
    articulos: dict[tuple, Mencion] = {}
    for texto in (afirmacion.get("texto"), *(afirmacion.get("referencias") or [])):
        if not isinstance(texto, str):
            continue
        for mencion in extraer_menciones(texto):
            if mencion.tipo == REGISTRO:
                registros[mencion.clave.split()[-1]] = None
            elif mencion.tipo == CLAVE:
                claves.setdefault((mencion.clave, mencion.materia, mencion.epoca), mencion)
            elif mencion.tipo == ARTICULO:
                articulos.setdefault((mencion.clave, mencion.ley), mencion)
    return MencionesAfirmacion(tuple(registros), tuple(claves.values()), tuple(articulos.values()))


def _mencion_de_clave(clave: Any) -> Mencion | None:
    """La clave de la fuente leída como mención (``None`` si ``menciones`` no la reconoce)."""
    if not isinstance(clave, str):
        return None
    encontradas = [m for m in extraer_menciones(clave) if m.tipo == CLAVE]
    return encontradas[0] if len(encontradas) == 1 else None


def _clave_cubierta(mencion: Mencion, fuente: Mencion | None) -> bool:
    """La clave mencionada es la de la fuente (materia y época, si las trae, coinciden)."""
    return (
        fuente is not None
        and mencion.clave == fuente.clave
        and all(
            propio is None or propio == ajeno
            for propio, ajeno in ((mencion.materia, fuente.materia), (mencion.epoca, fuente.epoca))
        )
    )


COINCIDE, DISTINTO, INDETERMINADO = "coincide", "distinto", "indeterminado"


def _contraste_articulo(mencion: Mencion, articulo: str | None, sigla: str | None) -> str:
    """¿La mención de artículo se refiere al artículo ubicado del ordenamiento de la evidencia?"""
    if mencion.ley is None:
        ley = COINCIDE
    elif sigla is None:
        ley = INDETERMINADO  # sin correspondencia de ordenamiento: no se supone
    else:
        ley = COINCIDE if mencion.ley == sigla else DISTINTO
    clave = clave_articulo(articulo) if articulo else None
    if clave is not None:
        art = COINCIDE if mencion.clave == clave else DISTINTO
    else:
        base = _base_articulo(articulo) if articulo else None
        art = INDETERMINADO if base is None or mencion.clave.split()[1] == base else DISTINTO
    if DISTINTO in (ley, art):
        return DISTINTO
    if INDETERMINADO in (ley, art):
        return INDETERMINADO
    return COINCIDE


def _describir_articulo(mencion: Mencion) -> str:
    return mencion.normalizada


# ── Cotejo ───────────────────────────────────────────────────────────────────


def _tipo_por_url(url: Any) -> str | None:
    if not url_oficial(url):
        return None
    ruta = urlsplit(url.strip()).path
    host = host_de(url)
    if host == HOST_SJF and ruta.startswith(RUTA_TESIS_SJF):
        return TIPO_TESIS_SJF
    if host == HOST_LEYESBIBLIO and ruta.startswith(RUTA_LEYESBIBLIO):
        return TIPO_LEY_LEYESBIBLIO
    return None


@dataclass
class _Fuente:
    """Pasos a–c (dependen solo de la evidencia): se calculan una vez por evidencia."""

    resultado: str | None = None  # None si los pasos a–c pasaron
    paso: str | None = None
    motivos: tuple[Motivo, ...] = ()
    tipo: str | None = None
    huella: str | None = None
    registro: Mapping[str, Any] | None = None
    tesis: TesisSJF | None = None
    documento: DocumentoLeyesBiblio | None = None
    ordenamiento: str | None = None
    motivo_ordenamiento: str | None = None

    @property
    def advertencias(self) -> tuple[dict, ...]:
        if self.registro is None or not isinstance(self.registro.get("advertencias"), list):
            return ()
        return tuple(dict(a) for a in self.registro["advertencias"] if isinstance(a, Mapping))

    @property
    def metadatos(self) -> Mapping[str, Any]:
        return (self.registro or {}).get("metadatos") or {}


def _falla(paso: str, motivos: Sequence[Motivo], **datos: Any) -> _Fuente:
    clase = DISCREPANTE if any(m.clase == DISCREPANCIA for m in motivos) else SIN_EVIDENCIA
    return _Fuente(resultado=clase, paso=paso, motivos=tuple(motivos), **datos)


def relacion_original_texto(
    registro: Mapping[str, Any],
    original: bytes,
    texto_extraido: str,
    extractores: Iterable[Extractor],
) -> list[Motivo]:
    """Motivos por los que no se acredita que el texto extraído proviene del original.

    Re-extrae con el extractor inyectado de mismo nombre y versión que declara el
    registro y compara las páginas citadas. Sin extractor o con re-extracción fallida:
    SIN_EVIDENCIA; con re-extracción distinta: DISCREPANTE. ``[]`` si se acredita.
    """
    derivado = registro.get("derivado") or {}
    nombre, version = derivado.get("extractor"), derivado.get("version_extractor")
    extractores = list(extractores)
    candidatos = [e for e in extractores if e.nombre == nombre and e.version == version]
    if not candidatos:
        disponibles = "; ".join(f"{e.nombre} {e.version}" for e in extractores) or "ninguno"
        return [Motivo("c", "texto_extraido", NO_COMPROBABLE,
                       "relación original–texto no comprobable: no hay un extractor del mismo nombre "
                       f"y versión que el registro para re-extraer (disponibles: {disponibles})",
                       fuente=f"{nombre} · {version}")]
    try:
        paginas = [str(pagina) for pagina in candidatos[0].extraer(bytes(original))]
    except Exception as error:  # noqa: BLE001 — cualquier fallo del extractor: no comprobable
        return [Motivo("c", "texto_extraido", NO_COMPROBABLE,
                       f"relación original–texto no comprobable: la re-extracción falló ({error})",
                       fuente=f"{nombre} · {version}")]
    numeros = (registro.get("metadatos") or {}).get("paginas") or []
    if any(numero > len(paginas) for numero in numeros):
        return [Motivo("c", "texto_extraido", DISCREPANCIA,
                       f"el original tiene {len(paginas)} página(s) y el registro cita la {max(numeros)}")]
    if SEPARADOR_PAGINAS.join(paginas[numero - 1] for numero in numeros) != texto_extraido:
        return [Motivo("c", "texto_extraido", DISCREPANCIA,
                       "el texto extraído registrado no es el que se obtiene del original con el mismo "
                       "extractor y versión: no proviene de ese original")]
    return []


def _cotejar_fuente(evidencia: Mapping[str, Any], paquete: Any, extractores: Sequence[Extractor]) -> _Fuente:
    # a. Vínculo ───────────────────────────────────────────────────────────────
    sha, problema = _valor_texto(evidencia.get("sha256_documento"))
    if problema:
        return _falla("a", [Motivo("a", "sha256_documento", NO_COMPROBABLE,
                                   f"sin sha256_documento ({problema}): no hay vínculo con un documento registrado")])
    sha_normal = sha.strip().lower()
    if not es_sha256(sha_normal):
        return _falla("a", [Motivo("a", "sha256_documento", NO_COMPROBABLE,
                                   "no es una huella SHA-256 hexadecimal", ledger=sha)])
    naturaleza = evidencia.get("naturaleza")
    if naturaleza not in NATURALEZAS_OFICIALES:
        return _falla("a", [Motivo("a", "naturaleza", NO_COMPROBABLE,
                                   "naturaleza no oficial: no es evidencia con procedencia", ledger=naturaleza)])
    url = evidencia.get("url")
    tipo = _tipo_por_url(url)
    if tipo is None:
        detalle = (
            f"tipo de fuente no soportado todavía por el cotejo de identidad (host {host_de(url)!r})"
            if url_oficial(url)
            else "URL no oficial (https y host permitido)"
        )
        return _falla("a", [Motivo("a", "url", NO_COMPROBABLE, detalle, ledger=url)])
    candidatos = paquete.buscar(sha_normal, url)
    if not candidatos:
        return _falla("a", [Motivo("a", "sha256_documento", NO_COMPROBABLE,
                                   "el paquete no tiene un registro con esa huella del original y esa URL exacta",
                                   ledger=sha_normal, fuente=url)], tipo=tipo)
    if len(candidatos) > 1:
        return _falla("a", [Motivo("a", "sha256_documento", NO_COMPROBABLE,
                                   "más de un registro distinto para el mismo documento y URL: ambiguo, no se elige",
                                   ledger=sha_normal, fuente=sorted(c.huella for c in candidatos))], tipo=tipo)
    item = candidatos[0]
    registro = item.registro
    datos = {"tipo": tipo, "huella": item.huella, "registro": registro}

    # b. Registro utilizable ───────────────────────────────────────────────────
    problemas = validar_registro(registro)
    if registro.get("tipo") != tipo:
        problemas.append(f"tipo: el registro es {registro.get('tipo')!r} y la URL corresponde a {tipo!r}")
    if problemas:
        return _falla("b", [Motivo("b", "registro", NO_COMPROBABLE, p) for p in problemas], **datos)

    # c. Integridad ────────────────────────────────────────────────────────────
    if item.problema:
        return _falla("c", [Motivo("c", "registro", DISCREPANCIA, item.problema)], **datos)
    metadatos = registro.get("metadatos") or {}
    necesarios = [
        ("original", registro["original"]["sha256"]),
        ("derivado", registro["derivado"]["sha256"]),
    ]
    if tipo == TIPO_LEY_LEYESBIBLIO:
        necesarios.append(("texto_extraido", metadatos.get("sha256_texto_extraido")))
    artefactos: dict[str, bytes] = {}
    motivos: list[Motivo] = []
    for nombre, huella in necesarios:
        try:
            contenido = paquete.objeto(huella)
        except ObjetoCorrupto as error:
            motivos.append(Motivo("c", nombre, DISCREPANCIA, f"objeto alterado: {error}"))
            continue
        if contenido is None:
            motivos.append(Motivo("c", nombre, NO_COMPROBABLE,
                                  f"objeto ausente en el paquete (objetos/{huella}): no comprobable"))
        else:
            artefactos[nombre] = contenido
    if motivos:
        return _falla("c", motivos, **datos)
    textos: dict[str, str] = {}
    for nombre in ("derivado", "texto_extraido"):
        if nombre in artefactos:
            try:
                textos[nombre] = artefactos[nombre].decode("utf-8")
            except UnicodeDecodeError:
                motivos.append(Motivo("c", nombre, DISCREPANCIA, "el objeto no es texto UTF-8"))
    if motivos:
        return _falla("c", motivos, **datos)
    problemas = comprobar_integridad(
        registro,
        original=artefactos["original"],
        derivado=textos["derivado"],
        texto_extraido=textos.get("texto_extraido"),
    )
    if problemas:
        return _falla("c", [Motivo("c", "integridad", DISCREPANCIA, p) for p in problemas], **datos)

    fuente = _Fuente(**datos)
    if tipo == TIPO_TESIS_SJF:
        try:
            fuente.tesis = parsear_tesis(
                artefactos["original"].decode("utf-8"), registro_esperado=metadatos.get("registro")
            )
        except (ErrorSJF, UnicodeDecodeError) as error:  # no ocurre si la integridad pasó
            return _falla("c", [Motivo("c", "original", DISCREPANCIA, f"relectura fallida: {error}")], **datos)
        return fuente

    # Ley: el texto extraído debe provenir del original (re-extracción con el mismo extractor).
    motivos = relacion_original_texto(registro, artefactos["original"], textos["texto_extraido"], extractores)
    if motivos:
        return _falla("c", motivos, **datos)
    # Misma reconstrucción que comprobar_integridad: el documento que se ubica es
    # exactamente el que la integridad validó.
    total = metadatos.get("total_paginas")
    fuente.documento = limpiar_documento(
        textos["texto_extraido"].split(SEPARADOR_PAGINAS),
        numeros=metadatos.get("paginas"),
        total_paginas=total if isinstance(total, int) else None,
    )
    fuente.ordenamiento, fuente.motivo_ordenamiento = ordenamiento_de(
        metadatos.get("archivo"), metadatos.get("titulo")
    )
    return fuente


def _texto_articulo(documento: DocumentoLeyesBiblio, unica: CoincidenciaArticulo) -> tuple[str, bool]:
    """Texto del artículo ubicado y si pudo quedar truncado.

    Va desde su encabezado hasta el siguiente encabezado de artículo o la línea
    TRANSITORIOS. Queda truncado si se interrumpe por una página que no se recibió o
    si el documento recibido termina antes de la última página del PDF.
    """
    lineas = documento.lineas()
    inicio = next(
        i for i, (pagina, indice, _) in enumerate(lineas) if (pagina, indice) == (unica.pagina, unica.indice)
    )
    partes = [lineas[inicio][2]]
    pagina_actual = unica.pagina
    for pagina, _, texto in lineas[inicio + 1 :]:
        if pagina != pagina_actual:
            if pagina != pagina_actual + 1:
                return "\n".join(partes), True
            pagina_actual = pagina
        if encabezado_articulo(texto) is not None or es_frontera_transitorios(texto):
            return "\n".join(partes), False
        partes.append(texto)
    ultima = documento.paginas[-1].numero if documento.paginas else None
    completo = isinstance(documento.total_paginas, int) and ultima == documento.total_paginas
    return "\n".join(partes), not completo


def _cotejar_extracto(
    evidencia: Mapping[str, Any],
    cuerpo: str,
    *,
    requerido: bool,
    donde: str,
    truncado: bool = False,
    documento_completo: str | None = None,
) -> tuple[list[Motivo], list[Motivo]]:
    """``(motivos, notas)`` del extracto del ledger frente al ``cuerpo`` de la fuente."""
    crudo = evidencia.get("extracto")
    if not isinstance(crudo, str) or not crudo.strip():
        if requerido:
            return [Motivo("f", "extracto", NO_COMPROBABLE, "la evidencia no trae extracto literal")], []
        return [], [Motivo("f", "extracto", NO_COTEJADO_CAMPO, "la evidencia no trae extracto")]
    if es_marcador_pendiente(crudo):
        return [Motivo("f", "extracto", NO_COMPROBABLE, "el extracto es un marcador pendiente", ledger=crudo)], []
    if rotulado_como_sintetico(crudo):
        return [Motivo("f", "extracto", NO_COMPROBABLE,
                       "extracto rotulado como sintético o ficticio: no es cita de la fuente",
                       ledger=_recortar(crudo))], []
    normal = normalizar_para_cotejo(crudo)
    if len(normal) < EXTRACTO_MINIMO:
        return [Motivo("f", "extracto", NO_COMPROBABLE,
                       f"extracto de {len(normal)} caracteres: no acredita identidad (mínimo {EXTRACTO_MINIMO})",
                       ledger=crudo)], []
    if normal in normalizar_para_cotejo(cuerpo):
        return [], []
    if truncado:
        return [Motivo("f", "extracto", NO_COMPROBABLE,
                       f"no aparece en {donde}, cuyo texto puede continuar en páginas no incluidas",
                       ledger=_recortar(crudo))], []
    detalle = f"no aparece literal (normalizado) en {donde}"
    if documento_completo is not None and normal in normalizar_para_cotejo(documento_completo):
        detalle += "; sí aparece en otra parte del documento"
    return [Motivo("f", "extracto", DISCREPANCIA, detalle, ledger=_recortar(crudo))], []


def _campo_critico(
    identificacion: Mapping[str, Any], campo: str, fuente: Any, nombre_fuente: str
) -> tuple[str | None, Motivo | None]:
    """Valor del ledger para un campo crítico, o el motivo por el que no se puede cotejar."""
    valor, problema = _valor_texto(identificacion.get(campo))
    if problema:
        return None, Motivo("f", campo, NO_COMPROBABLE,
                            f"campo crítico {problema} en identificacion_criterio")
    if fuente is None:
        return None, Motivo("f", campo, NO_COMPROBABLE,
                            f"la fuente no muestra {nombre_fuente} (o no se pudo leer sin ambigüedad)",
                            ledger=valor)
    return valor, None


def _cotejar_fecha(
    identificacion: Mapping[str, Any], campo: str, fuente: str | None, motivos: list[Motivo], notas: list[Motivo]
) -> None:
    valor, problema = _valor_texto(identificacion.get(campo))
    if problema:
        notas.append(Motivo("f", campo, NO_COTEJADO_CAMPO, f"el ledger no la da ({problema})"))
        return
    fechas, problemas = fechas_declaradas(valor)
    distintas = sorted({f.isoformat() for f in fechas})
    if problemas:
        motivos.append(Motivo("f", campo, DISCREPANCIA, "fecha inconsistente: " + "; ".join(problemas),
                              ledger=valor, fuente=fuente))
    elif not distintas:
        notas.append(Motivo("f", campo, NO_COTEJADO_CAMPO,
                            "el ledger no da una fecha interpretable", ledger=valor))
    elif fuente is None:
        notas.append(Motivo("f", campo, NO_COTEJADO_CAMPO,
                            "la fuente no declara la fecha (o no se pudo leer)", ledger=valor))
    elif fuente not in distintas:
        motivos.append(Motivo("f", campo, DISCREPANCIA,
                              "ninguna fecha del ledger coincide" if len(distintas) > 1 else "la fecha no coincide",
                              ledger=valor, fuente=fuente))
    elif len(distintas) > 1:
        motivos.append(Motivo("f", campo, NO_COMPROBABLE,
                              f"el ledger da {len(distintas)} fechas distintas y solo una es la de la fuente: "
                              "ambiguo, no se elige", ledger=valor, fuente=fuente))


def _textos_afirmacion(afirmacion: Mapping[str, Any]) -> list[str]:
    return [t for t in (afirmacion.get("texto"), *(afirmacion.get("referencias") or [])) if isinstance(t, str)]


def _clave_en_textos(clave: Any, textos: Iterable[str]) -> bool:
    """La clave de la fuente (sin sufijo de época) aparece en los textos, con límites.

    Cubre las claves que ``menciones`` no reconoce (tesis aisladas de TCC): espacios
    flexibles, sin acentos ni mayúsculas, y sin continuar en otro dígito o letra
    ("J/1" no está en "J/12").
    """
    if not isinstance(clave, str) or not clave.strip():
        return False
    base = re.sub(r"\s+", "", normalizar_para_cotejo(_SUFIJO_EPOCA.sub("", clave)))
    if not base:
        return False
    patron = re.compile(r"(?<![\w.])" + r"\s*".join(map(re.escape, base)) + r"(?![\w/])")
    return any(patron.search(normalizar_para_cotejo(texto)) for texto in textos)


def _menciones_tesis(
    afirmacion: Mapping[str, Any], menciones: MencionesAfirmacion, metadatos: Mapping[str, Any]
) -> tuple[list[Motivo], list[Motivo]]:
    """Registros y claves que la afirmación menciona frente a los de la tesis cotejada.

    La afirmación habla de esta tesis si menciona su registro digital o su clave. Si
    menciona registros o claves y ninguno es de esta tesis, la evidencia no corresponde
    a lo que la afirmación identifica: DISCREPANTE. Si no menciona ninguno, nota visible.
    """
    registro = str(int(metadatos["registro"]))
    fuente = _mencion_de_clave(metadatos.get("clave"))
    # La búsqueda literal solo suple a ``menciones`` cuando no reconoce la clave de la
    # fuente; si la reconoce, manda su comparación (que distingue materia y época).
    coincide = (
        registro in menciones.registros
        or any(_clave_cubierta(m, fuente) for m in menciones.claves)
        or (fuente is None and _clave_en_textos(metadatos.get("clave"), _textos_afirmacion(afirmacion)))
    )
    if coincide:
        return [], []
    if not menciones.registros and not menciones.claves:
        return [], [Motivo("d", "afirmacion", NO_COTEJADO_CAMPO,
                           "la afirmación no menciona registro digital ni clave identificables: "
                           "su correspondencia con esta tesis no se cotejó")]
    mencionados = [f"registro {r}" for r in menciones.registros] + [m.normalizada for m in menciones.claves]
    return [Motivo("d", "afirmacion", DISCREPANCIA,
                   "la afirmación menciona otro registro digital o clave que los de la evidencia",
                   ledger=", ".join(mencionados),
                   fuente=f"registro {registro} · {metadatos.get('clave')}")], []


def _cotejar_tesis(
    afirmacion: Mapping[str, Any], evidencia: Mapping[str, Any], fuente: _Fuente, menciones: MencionesAfirmacion
) -> tuple[str, list[Motivo], list[Motivo]]:
    """Pasos d (registro), e y f de una tesis; devuelve ``(paso, motivos, notas)``."""
    metadatos = fuente.metadatos
    tesis = fuente.tesis
    identificacion = afirmacion.get("identificacion_criterio")
    identificacion = identificacion if isinstance(identificacion, Mapping) else {}

    # d. El registro digital, antes que nada.
    valor, problema = _valor_texto(identificacion.get("registro"))
    if problema:
        return "d", [Motivo("d", "registro", NO_COMPROBABLE,
                            f"la afirmación no identifica el registro digital (identificacion_criterio.registro {problema})",
                            fuente=metadatos.get("registro"))], []
    registro = _registro_ledger(valor)
    if registro is None:
        return "d", [Motivo("d", "registro", NO_COMPROBABLE, "registro digital no interpretable",
                            ledger=valor, fuente=metadatos.get("registro"))], []
    if registro != metadatos.get("registro"):
        return "d", [Motivo("d", "registro", DISCREPANCIA, "el registro digital no es el del documento citado",
                            ledger=valor, fuente=metadatos.get("registro"))], []
    # d. Lo que la afirmación menciona (registro, clave) debe ser este documento.
    motivos, notas = _menciones_tesis(afirmacion, menciones, metadatos)
    if motivos:
        return "d", motivos, notas
    motivos = _cotejar_fecha_consulta(evidencia, fuente)
    if motivos:
        return "d", motivos, notas

    # e. Un registro mencionado en la ubicación debe ser el de la fuente.
    ubicacion = evidencia.get("ubicacion")
    if isinstance(ubicacion, str):
        mencionados = sorted({m.clave.split()[-1] for m in extraer_menciones(ubicacion) if m.tipo == REGISTRO})
        if mencionados and mencionados != [str(int(metadatos["registro"]))]:
            return "e", [Motivo("e", "ubicacion", DISCREPANCIA,
                                "la ubicación menciona otro registro digital",
                                ledger=ubicacion, fuente=metadatos.get("registro"))], notas

    # f. Campos críticos, fechas y extracto.
    motivos = []
    clave, motivo = _campo_critico(identificacion, "clave", metadatos.get("clave"), "la clave")
    if motivo:
        motivos.append(motivo)
    elif _forma_clave(clave) != _forma_clave(metadatos["clave"]):
        if _forma_clave(clave) == _forma_clave(_SUFIJO_EPOCA.sub("", metadatos["clave"])):
            motivos.append(Motivo("f", "clave", NO_COMPROBABLE,
                                  "clave sin el sufijo de época que trae la fuente: copiarla completa",
                                  ledger=clave, fuente=metadatos["clave"]))
        else:
            motivos.append(Motivo("f", "clave", DISCREPANCIA, "la clave no coincide",
                                  ledger=clave, fuente=metadatos["clave"]))

    rubro, motivo = _campo_critico(identificacion, "rubro", metadatos.get("rubro"), "el rubro")
    if motivo:
        motivos.append(motivo)
    elif forma_rubro(rubro) != forma_rubro(metadatos["rubro"]):
        motivos.append(Motivo("f", "rubro", DISCREPANCIA,
                              "el rubro no coincide (comparación normalizada, sin el punto final)",
                              ledger=_recortar(rubro), fuente=_recortar(metadatos["rubro"])))

    discrepante = any(a.get("codigo") == "epoca_discrepante" for a in fuente.advertencias)
    epocas_fuente = [metadatos.get("epoca")] + ([metadatos.get("epoca_segun_clave")] if discrepante else [])
    epocas_fuente = [e for e in epocas_fuente if e]
    epoca, motivo = _campo_critico(identificacion, "epoca", epocas_fuente or None, "la época")
    if motivo:
        motivos.append(motivo)
    else:
        canonica = _epoca_canonica(epoca)
        if canonica is None:
            motivos.append(Motivo("f", "epoca", NO_COMPROBABLE, "época no interpretable", ledger=epoca,
                                  fuente=metadatos.get("epoca")))
        elif canonica not in epocas_fuente:
            motivos.append(Motivo("f", "epoca", DISCREPANCIA, "la época no coincide", ledger=epoca,
                                  fuente=" / ".join(epocas_fuente)))
        elif canonica != metadatos.get("epoca"):
            notas.append(Motivo("f", "epoca", OBSERVACION,
                                "coincide con la época que indica la clave, no con el campo de época: "
                                "la fuente es discrepante y la elección es decisión humana",
                                ledger=epoca, fuente=" / ".join(epocas_fuente)))

    tipo_fuente = _tipo_de_fuente(metadatos.get("tipo_tesis"))
    fuerza, motivo = _campo_critico(identificacion, "fuerza_vinculante", tipo_fuente, "un tipo de tesis reconocible")
    if motivo:
        motivos.append(motivo)
    else:
        tipo_ledger = _tipo_de_fuerza(fuerza)
        if tipo_ledger is None:
            motivos.append(Motivo("f", "fuerza_vinculante", NO_COMPROBABLE,
                                  "no interpretable: se espera [J] (Jurisprudencia) o [TA] (Aislada)",
                                  ledger=fuerza, fuente=metadatos.get("tipo_tesis")))
        elif tipo_ledger != tipo_fuente:
            motivos.append(Motivo("f", "fuerza_vinculante", DISCREPANCIA,
                                  f"el ledger indica {tipo_ledger} y la fuente {tipo_fuente}",
                                  ledger=fuerza, fuente=metadatos.get("tipo_tesis")))

    _cotejar_fecha(identificacion, "publicacion", metadatos.get("fecha_publicacion"), motivos, notas)
    _cotejar_fecha(identificacion, "obligatoriedad", metadatos.get("fecha_obligatoriedad"), motivos, notas)
    for campo in CAMPOS_NO_COTEJADOS_TESIS:
        notas.append(Motivo("f", campo, NO_COTEJADO_CAMPO,
                            "sin correspondencia confiable con un campo de la fuente",
                            ledger=identificacion.get(campo)))

    cuerpo = "\n".join(
        parte for parte in (tesis.rubro, tesis.texto, *(s["texto"] for s in tesis.secciones)) if parte
    )
    motivos_extracto, notas_extracto = _cotejar_extracto(evidencia, cuerpo, requerido=False, donde="la tesis")
    return "f", motivos + motivos_extracto, notas + notas_extracto


def _cotejar_fecha_consulta(evidencia: Mapping[str, Any], fuente: _Fuente) -> list[Motivo]:
    registrada = str(fuente.registro["fuente"]["fecha_consulta"])[:10]
    valor = evidencia.get("fecha_consulta")
    fecha = fecha_iso(valor)
    if fecha is None:
        return [Motivo("d", "fecha_consulta", NO_COMPROBABLE, "fecha de consulta del ledger no interpretable (AAAA-MM-DD)",
                       ledger=valor, fuente=registrada)]
    if fecha.isoformat() != registrada:
        return [Motivo("d", "fecha_consulta", DISCREPANCIA,
                       "la fecha de consulta no es la del registro del paquete",
                       ledger=valor, fuente=fuente.registro["fuente"]["fecha_consulta"])]
    return []


def _menciones_ley(
    menciones: MencionesAfirmacion, articulo: str, fuente: _Fuente
) -> tuple[list[Motivo], list[Motivo]]:
    """Artículos (y ordenamientos) que la afirmación menciona frente al artículo ubicado."""
    if not menciones.articulos:
        return [], [Motivo("e", "afirmacion", NO_COTEJADO_CAMPO,
                           "la afirmación no menciona un artículo identificable: su correspondencia "
                           "con este artículo no se cotejó")]
    contrastes = {m: _contraste_articulo(m, articulo, fuente.ordenamiento) for m in menciones.articulos}
    if COINCIDE in contrastes.values():
        return [], []
    mencionados = ", ".join(_describir_articulo(m) for m in menciones.articulos)
    ubicado = f"art. {articulo}" + (f" {fuente.ordenamiento}" if fuente.ordenamiento else "")
    if INDETERMINADO in contrastes.values():
        detalle = "no se puede establecer que la afirmación hable del artículo ubicado"
        if fuente.ordenamiento is None and any(m.ley for m in menciones.articulos):
            detalle += f" (ordenamiento de la evidencia sin correspondencia: {fuente.motivo_ordenamiento})"
        return [Motivo("e", "afirmacion", NO_COMPROBABLE, detalle, ledger=mencionados, fuente=ubicado)], []
    return [Motivo("e", "afirmacion", DISCREPANCIA,
                   "la afirmación menciona otro artículo u ordenamiento que el de la evidencia",
                   ledger=mencionados, fuente=ubicado)], []


def _cotejar_ley(
    evidencia: Mapping[str, Any], fuente: _Fuente, menciones: MencionesAfirmacion
) -> tuple[str, list[Motivo], list[Motivo], tuple[dict, ...], str | None]:
    """Pasos d, e y f de una ley; ``(paso, motivos, notas, avisos de ubicación, artículo)``."""
    metadatos = fuente.metadatos
    documento = fuente.documento

    # d. Versión (el ordenamiento ya quedó fijado por URL + huella) y fecha de consulta.
    motivos = _cotejar_fecha_consulta(evidencia, fuente)
    version = metadatos.get("ultima_reforma_dof")
    if evidencia.get("ultima_reforma_dof") is not None:
        valor = evidencia["ultima_reforma_dof"]
        fecha = fecha_iso(valor) if not es_marcador_pendiente(valor) else None
        if fecha is None:
            motivos.append(Motivo("d", "ultima_reforma_dof", NO_COMPROBABLE,
                                  "versión del ledger no interpretable (AAAA-MM-DD)", ledger=valor, fuente=version))
        elif version is None:
            motivos.append(Motivo("d", "ultima_reforma_dof", NO_COMPROBABLE,
                                  "la fuente no fija una única fecha de última reforma", ledger=valor))
        elif fecha.isoformat() != version:
            motivos.append(Motivo("d", "ultima_reforma_dof", DISCREPANCIA,
                                  "la versión citada no es la del documento registrado", ledger=valor, fuente=version))
    if motivos:
        return "d", motivos, [], (), None

    # e. Ubicación: un único artículo, en el cuerpo, sin ambigüedad.
    ubicacion = evidencia.get("ubicacion")
    articulo = articulo_de_ubicacion(ubicacion)
    if articulo is None:
        return "e", [Motivo("e", "ubicacion", NO_COMPROBABLE,
                            "no se puede interpretar un único artículo en la ubicación "
                            "(enumeraciones, rangos y plurales no se interpretan)", ledger=ubicacion)], [], (), None
    ubicado = ubicar_articulo(documento, articulo)
    avisos = tuple(dict(a) for a in ubicado.advertencias)
    if ubicado.unica is None:
        codigos = [a["codigo"] for a in ubicado.advertencias if a["codigo"] != "sin_frontera_transitorios"]
        return "e", [Motivo("e", "ubicacion", NO_COMPROBABLE,
                            f"el artículo {articulo!r} no se ubica sin ambigüedad en el cuerpo "
                            f"({', '.join(codigos) or 'sin ubicación única'}); esto no acredita que no exista",
                            ledger=ubicacion)], [], avisos, None
    articulo = ubicado.unica.identificador
    # e. Lo que la afirmación menciona (artículo y ordenamiento) debe ser este artículo.
    motivos, notas = _menciones_ley(menciones, articulo, fuente)
    if motivos:
        return "e", motivos, notas, avisos, articulo

    # f. Extracto: subcadena del texto del artículo ubicado.
    texto, truncado = _texto_articulo(documento, ubicado.unica)
    motivos_extracto, notas_extracto = _cotejar_extracto(
        evidencia,
        texto,
        requerido=True,
        donde=f"el texto del artículo {articulo}",
        truncado=truncado,
        documento_completo=documento.texto,
    )
    notas += notas_extracto
    if evidencia.get("ultima_reforma_dof") is None:
        notas.append(Motivo("d", "ultima_reforma_dof", NO_COTEJADO_CAMPO,
                            "el ledger no indica la versión: se expone la de la fuente para el humano",
                            fuente=version))
    if metadatos.get("origen_texto") == "declarado":
        notas.append(Motivo("c", "texto_extraido", OBSERVACION,
                            "texto declarado con --paginas-json; su relación con el original se acreditó "
                            "por re-extracción"))
    return "f", motivos_extracto, notas, avisos, articulo


def cotejar_par(
    afirmacion: Mapping[str, Any],
    evidencia: Mapping[str, Any],
    paquete: Any,
    *,
    extractores: Sequence[Extractor] = (),
    _cache: dict | None = None,
) -> ResultadoPar:
    """Coteja una evidencia citada por una afirmación contra el paquete (pasos a–g)."""
    af_id = str(afirmacion.get("id"))
    ev_id = str(evidencia.get("id"))
    clave_cache = id(evidencia)
    if _cache is not None and clave_cache in _cache:
        fuente = _cache[clave_cache]
    else:
        fuente = _cotejar_fuente(evidencia, paquete, extractores)
        if _cache is not None:
            _cache[clave_cache] = fuente
    datos_fuente: dict[str, Any] = {
        "advertencias_fuente": fuente.advertencias,
        "tipo_fuente": fuente.tipo,
        "huella_registro": fuente.huella,
    }
    if fuente.registro is not None:
        metadatos = fuente.metadatos
        datos_fuente["fecha_consulta_fuente"] = (fuente.registro.get("fuente") or {}).get("fecha_consulta")
        datos_fuente["sha256_documento"] = (fuente.registro.get("original") or {}).get("sha256")
        if fuente.tipo == TIPO_TESIS_SJF:
            datos_fuente["documento_fuente"] = f"registro digital {metadatos.get('registro')}"
            datos_fuente["registro_fuente"] = metadatos.get("registro")
            datos_fuente["clave_fuente"] = metadatos.get("clave")
        else:
            datos_fuente["documento_fuente"] = metadatos.get("archivo")
            datos_fuente["version_fuente"] = metadatos.get("ultima_reforma_dof")
            datos_fuente["ordenamiento_fuente"] = fuente.ordenamiento
            datos_fuente["origen_texto"] = metadatos.get("origen_texto")
    if fuente.resultado is not None:
        return ResultadoPar(af_id, ev_id, fuente.resultado, fuente.paso, fuente.motivos, **datos_fuente)

    menciones = menciones_de_afirmacion(afirmacion)
    avisos: tuple[dict, ...] = ()
    if fuente.tipo == TIPO_TESIS_SJF:
        paso, motivos, notas = _cotejar_tesis(afirmacion, evidencia, fuente, menciones)
    else:
        paso, motivos, notas, avisos, articulo = _cotejar_ley(evidencia, fuente, menciones)
        datos_fuente["articulo_fuente"] = articulo
    if any(m.clase == DISCREPANCIA for m in motivos):
        resultado = DISCREPANTE
    elif motivos:
        resultado = SIN_EVIDENCIA
    else:
        resultado, paso = CONFORME, None
    return ResultadoPar(
        af_id,
        ev_id,
        resultado,
        paso,
        tuple(motivos),
        tuple(notas),
        advertencias_ubicacion=avisos,
        # g. Advertencias de la fuente: un CONFORME con avisos exige decisión humana.
        requiere_decision_humana=resultado == CONFORME and bool(fuente.advertencias),
        **datos_fuente,
    )


def _cobertura(
    afirmacion: Mapping[str, Any], pares: Sequence[ResultadoPar]
) -> tuple[list[Motivo], list[Motivo]]:
    """Menciones de la afirmación que ningún par CONFORME cubre (motivos) y notas."""
    menciones = menciones_de_afirmacion(afirmacion)
    if menciones.vacias:
        return [], [Motivo("h", "afirmacion", NO_COTEJADO_CAMPO,
                           "la afirmación no menciona ningún registro, clave ni artículo identificable: "
                           "su correspondencia con las evidencias no se cotejó")]
    tipo = afirmacion.get("tipo")
    conformes = [p for p in pares if p.resultado == CONFORME]
    exigir_tesis = tipo == "criterio_judicial" or any(p.tipo_fuente == TIPO_TESIS_SJF for p in pares)
    exigir_articulos = tipo == "texto_normativo" or any(p.tipo_fuente == TIPO_LEY_LEYESBIBLIO for p in pares)
    motivos: list[Motivo] = []
    notas: list[Motivo] = []
    if menciones.registros or menciones.claves:
        if exigir_tesis:
            registros = {p.registro_fuente for p in conformes if p.registro_fuente}
            claves = [_mencion_de_clave(p.clave_fuente) for p in conformes if p.clave_fuente]
            faltan = [f"registro {r}" for r in menciones.registros if r not in registros]
            faltan += [m.normalizada for m in menciones.claves if not any(_clave_cubierta(m, c) for c in claves)]
            if faltan:
                motivos.append(Motivo("h", "afirmacion", NO_COMPROBABLE,
                                      "la afirmación menciona tesis que ninguna evidencia CONFORME cubre",
                                      ledger=", ".join(faltan)))
        else:
            notas.append(Motivo("h", "afirmacion", NO_COTEJADO_CAMPO,
                                "registros o claves mencionados sin cotejar: la afirmación no es criterio "
                                "judicial ni cita tesis"))
    if menciones.articulos:
        if exigir_articulos:
            faltan = [
                m.normalizada
                for m in menciones.articulos
                if not any(
                    p.tipo_fuente == TIPO_LEY_LEYESBIBLIO
                    and _contraste_articulo(m, p.articulo_fuente, p.ordenamiento_fuente) == COINCIDE
                    for p in conformes
                )
            ]
            if faltan:
                motivos.append(Motivo("h", "afirmacion", NO_COMPROBABLE,
                                      "la afirmación menciona artículos que ninguna evidencia CONFORME cubre",
                                      ledger=", ".join(faltan)))
        else:
            notas.append(Motivo("h", "afirmacion", NO_COTEJADO_CAMPO,
                                "artículos mencionados sin cotejar: la afirmación no es texto normativo "
                                "ni cita leyes"))
    return motivos, notas


def agregar(
    afirmacion: Mapping[str, Any], estado: str | None, pares: Iterable[ResultadoPar]
) -> ResultadoAfirmacion:
    """Agregado por afirmación (ver el docstring del módulo)."""
    pares = tuple(pares)
    resultados = {par.resultado for par in pares}
    motivos: list[Motivo] = []
    notas: list[Motivo] = []
    if estado == INEXISTENTE:
        resultado = NO_COTEJADO
    elif DISCREPANTE in resultados:
        resultado = DISCREPANTE
    elif CONFORME in resultados:
        motivos, notas = _cobertura(afirmacion, pares)
        resultado = SIN_EVIDENCIA if motivos else CONFORME
    else:
        resultado = SIN_EVIDENCIA
        if not pares:
            motivos.append(Motivo("a", "evidencias", NO_COMPROBABLE, "la afirmación no cita evidencias"))
    return ResultadoAfirmacion(
        str(afirmacion.get("id")),
        estado,
        resultado,
        any(p.requiere_decision_humana for p in pares if p.resultado == CONFORME),
        pares,
        tuple(motivos),
        tuple(notas),
    )


def cotejar_ledger(
    ledger: Mapping[str, Any], paquete: Any, *, extractores: Sequence[Extractor] = ()
) -> CotejoLedger:
    """Coteja cada evidencia referida por cada afirmación del ledger contra el paquete.

    ``paquete`` es un ``itosturre.evidencia.paquete.Paquete`` ya cargado (o un objeto
    con ``problemas``, ``buscar(sha, url)``, ``objeto(huella)`` y ``huella()``).
    ``extractores`` permite acreditar la relación original–texto de las leyes; sin el
    extractor que declara un registro, esas evidencias quedan SIN_EVIDENCIA.
    Lanza ``LedgerInvalido`` si el ledger no cumple ``plan-ledger/1.0``.
    """
    errores = validar_esquema(ledger)
    if errores:
        raise LedgerInvalido(errores)
    extractores = tuple(extractores)
    por_id: dict[str, list[Mapping[str, Any]]] = {}
    for evidencia in ledger.get("evidencias") or []:
        por_id.setdefault(evidencia["id"], []).append(evidencia)
    cache: dict = {}
    agregados: list[ResultadoAfirmacion] = []
    for afirmacion in ledger.get("afirmaciones") or []:
        estado = normalizar_estado(afirmacion["verificacion"].get("estado"))
        pares: list[ResultadoPar] = []
        for ev_id in dict.fromkeys(afirmacion["verificacion"].get("evidencias") or []):
            if estado == INEXISTENTE:
                pares.append(ResultadoPar(
                    afirmacion["id"], ev_id, NO_COTEJADO, None,
                    notas=(Motivo("-", "estado", NO_COTEJADO_CAMPO,
                                  "INEXISTENTE no se coteja en este PR: la inexistencia exige prueba positiva"),),
                ))
                continue
            candidatas = por_id.get(ev_id, [])
            if len(candidatas) != 1:
                detalle = (
                    "la evidencia citada no existe en el ledger"
                    if not candidatas
                    else f"el ID de evidencia está duplicado ({len(candidatas)} veces): ambiguo, no se elige"
                )
                pares.append(ResultadoPar(afirmacion["id"], ev_id, SIN_EVIDENCIA, "a",
                                          (Motivo("a", "evidencia", NO_COMPROBABLE, detalle),)))
                continue
            pares.append(cotejar_par(afirmacion, candidatas[0], paquete, extractores=extractores, _cache=cache))
        agregados.append(agregar(afirmacion, estado, pares))
    return CotejoLedger(
        tuple(agregados),
        tuple(getattr(paquete, "problemas", ()) or ()),
        huella_ledger(ledger),
        _huella_de_paquete(paquete),
    )


# ── Decisiones humanas sobre advertencias de la fuente (PL-017) ──────────────


def decisiones_candidatas(decisiones: Iterable[Mapping[str, Any]], par: ResultadoPar) -> list[Mapping[str, Any]]:
    """Decisiones que dicen referirse a la evidencia del par (por ``advertencias_fuente`` o ``bloquea``)."""
    candidatas = []
    for decision in decisiones:
        datos = decision.get(CAMPO_DECISION_ADVERTENCIAS)
        declarada = isinstance(datos, Mapping) and datos.get("evidencia") == par.evidencia
        if declarada or par.evidencia in (decision.get("bloquea") or []):
            candidatas.append(decision)
    return candidatas


def problemas_decision_advertencias(
    decision: Mapping[str, Any], par: ResultadoPar, *, exigir_resolucion: bool = True
) -> list[str]:
    """Por qué ``decision`` no atiende las advertencias de la fuente del par (``[]`` si sí).

    La decisión debe traer ``advertencias_fuente`` con: ``evidencia`` (el ID del par),
    ``sha256_documento`` o ``huella_registro`` **vigentes** (si la fuente cambia, la
    decisión deja de valer), ``codigos`` que incluyan todos los de la fuente y una
    ``resolucion`` no vacía (p. ej. la época adoptada); y un responsable humano.
    Con ``exigir_resolucion=False`` (decisión registrada pero pendiente) no se exigen
    ``codigos`` ni ``resolucion``.
    """
    problemas = []
    motivo = problema_persona(decision.get("responsable"))
    if motivo:
        problemas.append(f"responsable no válido ({motivo})")
    datos = decision.get(CAMPO_DECISION_ADVERTENCIAS)
    if not isinstance(datos, Mapping):
        return problemas + [f"no declara {CAMPO_DECISION_ADVERTENCIAS} (evidencia, sha256_documento, códigos y resolución)"]
    if datos.get("evidencia") != par.evidencia:
        problemas.append(f"declara la evidencia {datos.get('evidencia')!r}, no {par.evidencia}")
    sha = datos.get("sha256_documento")
    huella = datos.get("huella_registro")
    vigente = (
        isinstance(sha, str) and par.sha256_documento is not None and sha.strip().lower() == par.sha256_documento
    ) or (isinstance(huella, str) and par.huella_registro is not None and huella.strip().lower() == par.huella_registro)
    if not vigente:
        problemas.append(
            "no declara el sha256_documento ni la huella_registro vigentes de la fuente (falta o la fuente cambió)"
        )
    if exigir_resolucion:
        codigos = datos.get("codigos")
        declarados = set(codigos) if isinstance(codigos, list) and all(isinstance(c, str) for c in codigos) else set()
        faltan = sorted(set(par.codigos_advertencia) - declarados)
        if faltan:
            problemas.append("no declara los códigos de advertencia que resuelve: " + ", ".join(faltan))
        _, problema = _valor_texto(datos.get("resolucion"))
        if problema:
            problemas.append(f"resolución {problema}")
    return problemas


def decision_atiende(decision: Mapping[str, Any], par: ResultadoPar, *, aprobada: bool) -> bool:
    """``True`` si la decisión atiende las advertencias del par (``aprobada``: además APROBADA)."""
    if aprobada and normalizar_estado(decision.get("estado"), admitir_aprobado=True) != APROBADO:
        return False
    return not problemas_decision_advertencias(decision, par, exigir_resolucion=aprobada)
