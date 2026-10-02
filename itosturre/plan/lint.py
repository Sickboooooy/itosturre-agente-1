"""Reglas observables del auditor de planes (PL-001 … PL-014, y PL-015 … PL-020 con paquete).

Cada regla verifica algo que se puede comprobar mirando el ledger (y, para PL-014,
el documento): campos presentes, vocabulario, hosts, fechas, hashes y referencias.
Ninguna regla hace inferencia semántica ni decide si un criterio es pertinente al
caso — eso sigue siendo Capa 2, decisión del abogado.

Con un paquete de evidencia (``paquete=`` o un ``cotejo=`` ya calculado) se agregan
las reglas del cotejo de identidad (``identidad.py``), PL-015 … PL-019. Viven en
``REGLAS_COTEJO`` y no en ``REGLAS``: sin paquete el lint es el de PR-1 (el resumen
trae además la clave ``ADVERTENCIA``, siempre en 0) y el Gold Set de planes (que no
admite paquete) sigue midiendo PL-001 … PL-014.

PL-007 exige los campos de identificación según el tipo de fuente del criterio
(``ledger.CAMPOS_POR_TIPO_FUENTE``, piloto D8): los diez de la tesis del SJF o los de una
sentencia internacional (caso, serie y número, fecha, párrafo). El tipo lo declara
``identificacion_criterio.tipo_fuente``; sin él, se infiere de las evidencias citadas
(todas de la Corte IDH → sentencia internacional) y, si no, es tesis del SJF.

Un hallazgo es un dict ``{regla, severidad, objetivo, mensaje}``. El plan queda
bloqueado si existe al menos un hallazgo ``BLOQUEANTE``; ``ADVERTENCIA`` (PL-018: evidencia
citada sin cotejar en un agregado CONFORME; PL-019: artículo remitido sin cotejar) nunca
bloquea. Una afirmación compuesta cuya parte sin cotejar no genera menciones (p. ej. una
fecha del DOF) solo produce PL-018: se recomienda descomponerla para que cada parte cite su
propia evidencia (el kit no lo hace por el operador).

PL-020 (PR-4, también solo con paquete o con un ``fidelidad=`` ya calculado): señales del
cotejo de fidelidad (``fidelidad.py``) que ninguna decisión humana atiende, según la
política de precisión (ronda 2, criterio por defecto; el responsable puede endurecerlo):
una señal de precisión ``alta`` (modo de procedibilidad distinto, plazo distinto para la
misma condición, inicio del cómputo distinto) es BLOQUEANTE en una afirmación VERIFICADO y
ALTA en otro estado; cualquier otra señal (``revisar``: modales, negación, cuantificadores,
excepciones, órgano, cifras sin condición, cifra ausente, omisiones, alineación ambigua) es
ADVERTENCIA "señal a revisar" en cualquier estado. La decisión que las atiende declara
``fidelidad`` con el plan, la afirmación, su ``contenido_sha256`` vigente, la versión del
motor y la huella, el código, la fuente, el artículo y el ``sha256_documento`` de cada
señal, y tiene responsable humano; si la afirmación es VERIFICADO, además una resolución y
la decisión APROBADA (``fidelidad.problemas_decision_fidelidad``). Si cambia cualquiera de
esos datos, deja de valer: una decisión vieja o ajena no atiende una señal nueva.
El cotejo de fidelidad nunca emite CONFORME: sin señales no hay hallazgo, pero tampoco
aprobación ni validación.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Sequence

# Fuente única de hosts oficiales (D2: plan depende de evidencia, nunca al revés).
# Se reexportan con los mismos nombres para no romper a quien los importe de aquí.
from ..evidencia.fuentes import HOSTS_CANONICOS, HOSTS_OFICIALES, host_de, url_oficial
from .estados import (
    APROBADO,
    CONTRADICCION,
    INEXISTENTE,
    REQUIERE_DECISION_HUMANA,
    VERIFICADO,
    es_marcador_pendiente,
    normalizar_estado,
    problema_persona,
    problemas_aprobacion,
)
from .fidelidad import (
    ALTA as PRECISION_ALTA,
    SENALES,
    FidelidadLedger,
    cotejar_fidelidad,
    problemas_decision_fidelidad,
    senales_pendientes,
)
from .identidad import (
    CONFORME,
    DISCREPANTE,
    PASOS,
    SIN_EVIDENCIA,
    CotejoLedger,
    Extractor,
    cotejar_ledger,
    decision_atiende,
    decisiones_candidatas,
    problemas_decision_advertencias,
)
from .ledger import (
    CAMPOS_POR_TIPO_FUENTE,
    HOSTS_SENTENCIA_INTERNACIONAL,
    HOSTS_TESIS,
    NATURALEZAS_OFICIALES,
    SENTENCIA_INTERNACIONAL,
    TESIS_SJF,
    TIPOS_FUENTE_CRITERIO,
    LedgerInvalido,
    fecha_iso,
    validar_esquema,
)
from .menciones import RANGO, esta_cubierta, extraer_menciones, indice_cobertura

BLOQUEANTE = "BLOQUEANTE"
ALTA = "ALTA"
MEDIA = "MEDIA"
ADVERTENCIA = "ADVERTENCIA"  # visible y nunca bloquea (PL-018, PL-019, señales "a revisar" de PL-020)
SEVERIDADES = (BLOQUEANTE, ALTA, MEDIA, ADVERTENCIA)
_RANGO = {severidad: indice for indice, severidad in enumerate(SEVERIDADES)}

REGLAS = {
    "PL-001": "Estado fuera del vocabulario único",
    "PL-002": "VERIFICADO sin evidencias",
    "PL-003": "VERIFICADO apoyado en evidencia no oficial",
    "PL-004": "VERIFICADO con evidencia sin ubicación",
    "PL-005": "VERIFICADO con evidencia sin extracto literal suficiente",
    "PL-006": "VERIFICADO con fecha de consulta inválida o posterior al documento",
    "PL-007": "Criterio judicial VERIFICADO con identificación incompleta",
    "PL-008": "INEXISTENTE sin evidencia oficial",
    "PL-009": "Propuesta o inferencia del agente marcada VERIFICADO",
    "PL-010": "Aprobación inválida",
    "PL-011": "Contradicción mal declarada",
    "PL-012": "Decisión sin responsable humano",
    "PL-013": "IDs duplicados o referencias colgantes",
    "PL-014": "Mención del documento sin afirmación que la cubra",
}

# Reglas del cotejo de identidad: solo se evalúan con un paquete de evidencia.
REGLAS_COTEJO = {
    "PL-015": "VERIFICADO con evidencia DISCREPANTE en el cotejo de identidad",
    "PL-016": "VERIFICADO sin ninguna evidencia CONFORME en el cotejo de identidad",
    "PL-017": "Advertencias de la fuente sin decisión humana que las atienda",
    "PL-018": "Evidencia citada sin cotejar en una afirmación CONFORME",
    "PL-019": "Artículo remitido sin cotejar",
    "PL-020": "Señales de fidelidad sin decisión humana que las atienda",
}

ACCIONES = {
    "PL-001": "Sustituir por un estado del vocabulario único (itosturre/plan/estados.py).",
    "PL-002": "Adjuntar evidencia oficial o degradar a NO VERIFICADO.",
    "PL-003": "Sustituir por fuente oficial (https, host permitido) o degradar a NO VERIFICADO.",
    "PL-004": "Indicar la ubicación exacta en la fuente (artículo, página o registro).",
    "PL-005": "Transcribir el extracto literal (20 caracteres o más) de la fuente.",
    "PL-006": "Registrar la fecha real de consulta (AAAA-MM-DD, no posterior al documento).",
    "PL-007": (
        "Completar la identificación del criterio según su fuente: los diez campos de la tesis "
        "desde el SJF, o caso, serie_numero, fecha y parrafo de la sentencia internacional."
    ),
    "PL-008": "Aportar fuente oficial que acredite la inexistencia o cambiar a NO VERIFICABLE.",
    "PL-009": "Reclasificar como CANDIDATO o REQUIERE DECISIÓN HUMANA y pedir aprobación humana.",
    "PL-010": "Recabar nueva aprobación humana sobre el contenido vigente.",
    "PL-011": "Declarar la contradicción con todas sus afirmaciones y ligarla a una decisión.",
    "PL-012": "Asignar un responsable humano a la decisión.",
    "PL-013": "Corregir el ID duplicado o la referencia inexistente.",
    "PL-014": "Registrar una afirmación que cubra la mención o retirarla del documento.",
    "PL-015": "Corregir el ledger o la evidencia según la fuente registrada, o degradar a NO VERIFICADO.",
    "PL-016": "Registrar la evidencia en el paquete y completar el vínculo, o degradar a NO VERIFICABLE.",
    "PL-017": "Registrar una decisión humana APROBADA con advertencias_fuente (evidencia, sha256_documento, códigos y resolución).",
    "PL-018": (
        "Revisar a mano lo que solo sostiene esa evidencia (tipo de fuente no soportado o sin "
        "vínculo) o sustituirla por evidencia cotejable; el CONFORME no lo cubre. Mejor: "
        "descomponer la afirmación para que cada parte cite su propia evidencia."
    ),
    "PL-019": (
        "Si la afirmación dice algo del artículo remitido, citar su propia evidencia; si solo "
        "describe la remisión, revisar a mano que el artículo remitido sea el que se afirma."
    ),
    "PL-020": (
        "Leer el tramo oficial y corregir la afirmación, o registrar una decisión humana con "
        "`fidelidad` (plan, afirmación, contenido_sha256, version_motor y huella de cada señal; "
        "`plan_audit.py fidelidad` imprime el bloque; resolución y APROBADA si es VERIFICADO)."
    ),
}

EXTRACTO_MINIMO = 20
_NATURALEZAS_NO_OFICIALES = frozenset({"secundaria", "sistema", "busqueda"})


def es_evidencia_oficial(evidencia: dict, hosts: Iterable[str] = HOSTS_OFICIALES) -> bool:
    """Naturaleza oficial declarada **y** URL oficial comprobable."""
    return evidencia.get("naturaleza") in NATURALEZAS_OFICIALES and url_oficial(
        evidencia.get("url"), hosts
    )


def _texto(valor: Any) -> str:
    """Texto con espacios colapsados; ``""`` si no es texto o es un marcador pendiente."""
    if not isinstance(valor, str) or es_marcador_pendiente(valor):
        return ""
    return " ".join(valor.split())


def _problema_campo(valor: Any) -> str | None:
    """Motivo por el que un campo de identificación no cuenta como dato (``None`` si cuenta).

    Solo vale un texto no vacío que no sea marcador pendiente: ``false``, ``0``, listas
    u objetos cuentan como faltantes.
    """
    if valor is None:
        return "ausente"
    if not isinstance(valor, str):
        return f"no es texto ({type(valor).__name__})"
    if not valor.strip():
        return "vacío"
    if es_marcador_pendiente(valor):
        return "marcador pendiente"
    return None


class _Auditoria:
    """Índices del ledger y acumulador de hallazgos para una sola pasada de lint."""

    def __init__(self, ledger: dict, hosts: frozenset[str]) -> None:
        self.ledger = ledger
        self.hosts = hosts
        self.hallazgos: list[dict] = []
        self._vistos: set[tuple[str, str, str]] = set()
        self.fecha_documento = fecha_iso(ledger["plan"]["fecha_documento"])
        self.afirmaciones: list[dict] = ledger.get("afirmaciones") or []
        self.evidencias: list[dict] = ledger.get("evidencias") or []
        self.contradicciones: list[dict] = ledger.get("contradicciones") or []
        self.decisiones: list[dict] = ledger.get("decisiones") or []

        self.evidencias_por_id: dict[str, list[dict]] = defaultdict(list)
        for evidencia in self.evidencias:
            self.evidencias_por_id[evidencia["id"]].append(evidencia)
        self.ids_afirmaciones = {a["id"] for a in self.afirmaciones}
        self.ids_decisiones = {d["id"] for d in self.decisiones}
        self.estados = {
            id(a): normalizar_estado(a["verificacion"].get("estado"))
            for a in self.afirmaciones
        }
        self.verificadas = [a for a in self.afirmaciones if self.estado(a) == VERIFICADO]
        self.evidencias_de_verificadas = {
            ev_id for a in self.verificadas for ev_id in self.evidencias_citadas(a)
        }

    def estado(self, afirmacion: dict) -> str | None:
        return self.estados[id(afirmacion)]

    @staticmethod
    def evidencias_citadas(afirmacion: dict) -> list[str]:
        return list(afirmacion["verificacion"].get("evidencias") or [])

    def emitir(self, regla: str, severidad: str, objetivo: str, mensaje: str) -> None:
        clave = (regla, objetivo, mensaje)
        if clave in self._vistos:
            return
        self._vistos.add(clave)
        self.hallazgos.append(
            {"regla": regla, "severidad": severidad, "objetivo": objetivo, "mensaje": mensaje}
        )

    # ── PL-001 ──────────────────────────────────────────────────────────────
    def estados_fuera_de_vocabulario(self) -> None:
        for afirmacion in self.afirmaciones:
            if self.estado(afirmacion) is not None:
                continue
            crudo = afirmacion["verificacion"].get("estado")
            detalle = (
                "APROBADO no es estado de verificación: se registra en `aprobacion`"
                if normalizar_estado(crudo, admitir_aprobado=True) == APROBADO
                else "no pertenece al vocabulario único"
            )
            self.emitir(
                "PL-001", BLOQUEANTE, afirmacion["id"], f"Estado {crudo!r}: {detalle}."
            )
        for coleccion, nombre in ((self.contradicciones, "contradicción"), (self.decisiones, "decisión")):
            for item in coleccion:
                if normalizar_estado(item["estado"], admitir_aprobado=True) is None:
                    self.emitir(
                        "PL-001",
                        BLOQUEANTE,
                        item["id"],
                        f"Estado de {nombre} {item['estado']!r} fuera del vocabulario único.",
                    )

    # ── PL-002 … PL-007, PL-009 ─────────────────────────────────────────────
    def verificadas_sin_soporte(self) -> None:
        for afirmacion in self.verificadas:
            objetivo = afirmacion["id"]
            citadas = self.evidencias_citadas(afirmacion)
            resueltas = [ev_id for ev_id in citadas if ev_id in self.evidencias_por_id]
            if not resueltas:
                motivo = "no cita evidencias" if not citadas else "ninguna evidencia citada existe"
                self.emitir("PL-002", BLOQUEANTE, objetivo, f"VERIFICADO pero {motivo}.")
            for ev_id in resueltas:
                for evidencia in self.evidencias_por_id[ev_id]:
                    self._revisar_evidencia_de_verificado(objetivo, evidencia)
            if afirmacion["tipo"] == "criterio_judicial":
                self._revisar_identificacion_criterio(afirmacion)
            if afirmacion["autor"] == "agente" and afirmacion["tipo"] in {"propuesta", "inferencia"}:
                self.emitir(
                    "PL-009",
                    BLOQUEANTE,
                    objetivo,
                    f"Una {afirmacion['tipo']} del agente no puede quedar VERIFICADO: "
                    "requiere decisión humana.",
                )

    def _revisar_evidencia_de_verificado(self, objetivo: str, evidencia: dict) -> None:
        ev_id = evidencia["id"]
        naturaleza = evidencia.get("naturaleza")
        if naturaleza in _NATURALEZAS_NO_OFICIALES:
            self.emitir(
                "PL-003",
                BLOQUEANTE,
                objetivo,
                f"Evidencia {ev_id} de naturaleza '{naturaleza}' no sostiene un VERIFICADO.",
            )
        url = evidencia.get("url")
        if not _texto(url):
            self.emitir(
                "PL-003",
                BLOQUEANTE,
                objetivo,
                f"Evidencia {ev_id}: URL vacía o marcador pendiente ({url!r}).",
            )
        elif not url_oficial(url, self.hosts):
            mensaje = f"Evidencia {ev_id}: URL {url!r} no es https de un host oficial permitido."
            canonico = HOSTS_CANONICOS.get(host_de(url))
            if canonico:
                mensaje += f" Usar el host canónico {canonico}."
            self.emitir("PL-003", BLOQUEANTE, objetivo, mensaje)
        if not _texto(evidencia.get("ubicacion")):
            self.emitir(
                "PL-004",
                BLOQUEANTE,
                objetivo,
                f"Evidencia {ev_id} sin ubicación en la fuente (vacía o marcador pendiente).",
            )
        extracto_crudo = evidencia.get("extracto")
        extracto = _texto(extracto_crudo)
        if len(extracto) < EXTRACTO_MINIMO:
            detalle = (
                "es un marcador pendiente"
                if es_marcador_pendiente(extracto_crudo)
                else f"tiene {len(extracto)} caracteres"
            )
            self.emitir(
                "PL-005",
                BLOQUEANTE,
                objetivo,
                f"Evidencia {ev_id}: el extracto literal {detalle} (mínimo {EXTRACTO_MINIMO}).",
            )
        consulta = fecha_iso(evidencia.get("fecha_consulta"))
        if consulta is None:
            self.emitir(
                "PL-006",
                BLOQUEANTE,
                objetivo,
                f"Evidencia {ev_id}: fecha_consulta {evidencia.get('fecha_consulta')!r} "
                "no es AAAA-MM-DD válida.",
            )
        elif self.fecha_documento is not None and consulta > self.fecha_documento:
            self.emitir(
                "PL-006",
                BLOQUEANTE,
                objetivo,
                f"Evidencia {ev_id}: consultada el {consulta.isoformat()}, después de la "
                f"fecha del documento ({self.fecha_documento.isoformat()}).",
            )

    def tipo_fuente_criterio(self, afirmacion: dict) -> tuple[str, str | None]:
        """``(tipo de fuente, problema)`` del criterio (PEN-01 D8): el declarado en
        ``identificacion_criterio.tipo_fuente`` o, sin él, el que indican las evidencias
        citadas (todas de un host de sentencias internacionales → sentencia internacional);
        por omisión, tesis del SJF. Un valor fuera de vocabulario es un problema y se
        exigen los campos de tesis (falla cerrado)."""
        identificacion = afirmacion.get("identificacion_criterio") or {}
        declarado = identificacion.get("tipo_fuente") if isinstance(identificacion, dict) else None
        hosts = [
            host_de(evidencia.get("url"))
            for ev_id in self.evidencias_citadas(afirmacion)
            for evidencia in self.evidencias_por_id.get(ev_id, [])
        ]
        de_sentencia = [h for h in hosts if h in HOSTS_SENTENCIA_INTERNACIONAL]
        de_tesis = [h for h in hosts if h in HOSTS_TESIS]
        if declarado is not None:
            if not (isinstance(declarado, str) and declarado.strip().lower() in TIPOS_FUENTE_CRITERIO):
                return TESIS_SJF, (
                    f"tipo_fuente {declarado!r} fuera de vocabulario ({', '.join(TIPOS_FUENTE_CRITERIO)})"
                )
            tipo = declarado.strip().lower()
            # Ronda 2: el tipo declarado debe corresponder a la fuente de las evidencias; si
            # no, el hallazgo impide eludir los campos de un tipo declarando el otro.
            if tipo == SENTENCIA_INTERNACIONAL and (de_tesis or not de_sentencia):
                return tipo, (
                    "tipo_fuente 'sentencia_internacional' incompatible con las evidencias citadas "
                    "(se requiere al menos una sentencia de la Corte IDH y ninguna tesis del SJF)"
                )
            if tipo == TESIS_SJF and de_sentencia:
                return tipo, (
                    "tipo_fuente 'tesis_sjf' incompatible con las evidencias citadas (cita "
                    "sentencias de la Corte IDH)"
                )
            return tipo, None
        if hosts and len(de_sentencia) == len(hosts):
            return SENTENCIA_INTERNACIONAL, None
        return TESIS_SJF, None

    def _revisar_identificacion_criterio(self, afirmacion: dict) -> None:
        identificacion = afirmacion.get("identificacion_criterio") or {}
        tipo, problema = self.tipo_fuente_criterio(afirmacion)
        faltantes = [problema] if problema else []
        for campo in CAMPOS_POR_TIPO_FUENTE[tipo]:
            motivo = _problema_campo(identificacion.get(campo))
            if motivo:
                faltantes.append(f"{campo} ({motivo})")
        if faltantes:
            etiqueta = "" if tipo == TESIS_SJF else " (sentencia internacional)"
            self.emitir(
                "PL-007",
                BLOQUEANTE,
                afirmacion["id"],
                f"Identificación del criterio{etiqueta} incompleta: " + ", ".join(faltantes) + ".",
            )

    # ── PL-008 ──────────────────────────────────────────────────────────────
    def inexistentes_sin_prueba(self) -> None:
        for afirmacion in self.afirmaciones:
            if self.estado(afirmacion) != INEXISTENTE:
                continue
            evidencias = [
                evidencia
                for ev_id in self.evidencias_citadas(afirmacion)
                for evidencia in self.evidencias_por_id.get(ev_id, [])
            ]
            # Una consulta sin resultados no prueba la inexistencia aunque se haya
            # hecho en un portal oficial: no cuenta como evidencia oficial.
            oficiales = [
                e
                for e in evidencias
                if es_evidencia_oficial(e, self.hosts)
                and _texto(e.get("extracto"))
                and e.get("resultados") != 0
            ]
            if oficiales:
                continue
            if evidencias and all(
                e.get("naturaleza") == "busqueda" or e.get("resultados") == 0 for e in evidencias
            ):
                mensaje = (
                    "INEXISTENTE apoyado solo en búsquedas sin resultados: no encontrar no "
                    "prueba la inexistencia."
                )
            else:
                mensaje = (
                    "INEXISTENTE sin evidencia oficial (naturaleza oficial, URL oficial y "
                    "extracto) que lo acredite."
                )
            self.emitir("PL-008", BLOQUEANTE, afirmacion["id"], mensaje)

    # ── PL-010 ──────────────────────────────────────────────────────────────
    def aprobaciones_invalidas(self) -> None:
        for afirmacion in self.afirmaciones:
            problemas = problemas_aprobacion(afirmacion)
            if problemas:
                self.emitir(
                    "PL-010",
                    BLOQUEANTE,
                    afirmacion["id"],
                    "Aprobación inválida: " + "; ".join(problemas) + ".",
                )

    # ── PL-011 ──────────────────────────────────────────────────────────────
    def contradicciones_mal_declaradas(self) -> None:
        declaradas = {
            af_id for contradiccion in self.contradicciones for af_id in contradiccion["afirmaciones"]
        }
        for afirmacion in self.afirmaciones:
            if self.estado(afirmacion) == CONTRADICCION and afirmacion["id"] not in declaradas:
                self.emitir(
                    "PL-011",
                    ALTA,
                    afirmacion["id"],
                    "Afirmación en CONTRADICCIÓN que no figura en ninguna contradicción declarada.",
                )
        for contradiccion in self.contradicciones:
            objetivo = contradiccion["id"]
            if len(set(contradiccion["afirmaciones"])) < 2:
                self.emitir(
                    "PL-011",
                    ALTA,
                    objetivo,
                    "Una contradicción necesita al menos dos afirmaciones distintas.",
                )
            estado = normalizar_estado(contradiccion["estado"], admitir_aprobado=True)
            if (
                estado is not None
                and estado not in {CONTRADICCION, REQUIERE_DECISION_HUMANA}
                and not _texto(contradiccion.get("decision_id"))
            ):
                self.emitir(
                    "PL-011",
                    ALTA,
                    objetivo,
                    f"Contradicción en estado {estado} sin decision_id que documente cómo se resolvió.",
                )

    # ── PL-012 ──────────────────────────────────────────────────────────────
    def decisiones_sin_responsable(self) -> None:
        for decision in self.decisiones:
            responsable = decision.get("responsable")
            motivo = problema_persona(responsable)
            if motivo is None:
                continue
            if motivo == "vacío":
                mensaje = "Decisión sin responsable asignado."
            else:
                mensaje = f"Responsable {responsable.strip()!r} no identifica a una persona humana ({motivo})."
            estado = normalizar_estado(decision["estado"], admitir_aprobado=True)
            if estado == APROBADO:
                mensaje += " Una decisión APROBADA debe identificar a la persona que la tomó."
            self.emitir("PL-012", ALTA, decision["id"], mensaje)

    # ── PL-013 ──────────────────────────────────────────────────────────────
    def ids_y_referencias(self) -> None:
        apariciones: dict[str, list[tuple[str, dict]]] = defaultdict(list)
        for nombre, coleccion in (
            ("afirmacion", self.afirmaciones),
            ("evidencia", self.evidencias),
            ("contradiccion", self.contradicciones),
            ("decision", self.decisiones),
        ):
            for item in coleccion:
                apariciones[item["id"]].append((nombre, item))
        for item_id, lista in apariciones.items():
            if len(lista) < 2:
                continue
            afecta = any(
                (nombre == "afirmacion" and self.estado(item) == VERIFICADO)
                or (nombre == "evidencia" and item_id in self.evidencias_de_verificadas)
                for nombre, item in lista
            )
            tipos = ", ".join(nombre for nombre, _ in lista)
            self.emitir(
                "PL-013",
                BLOQUEANTE if afecta else MEDIA,
                item_id,
                f"ID duplicado ({len(lista)} apariciones: {tipos}).",
            )

        todos = set(apariciones)
        for afirmacion in self.afirmaciones:
            verificada = self.estado(afirmacion) == VERIFICADO
            for ev_id in self.evidencias_citadas(afirmacion):
                if ev_id not in self.evidencias_por_id:
                    self.emitir(
                        "PL-013",
                        BLOQUEANTE if verificada else MEDIA,
                        afirmacion["id"],
                        f"Cita la evidencia inexistente {ev_id}.",
                    )
        for contradiccion in self.contradicciones:
            for af_id in contradiccion["afirmaciones"]:
                if af_id not in self.ids_afirmaciones:
                    self.emitir(
                        "PL-013",
                        MEDIA,
                        contradiccion["id"],
                        f"Refiere la afirmación inexistente {af_id}.",
                    )
            decision_id = _texto(contradiccion.get("decision_id"))
            if decision_id and decision_id not in self.ids_decisiones:
                self.emitir(
                    "PL-013",
                    MEDIA,
                    contradiccion["id"],
                    f"Refiere la decisión inexistente {decision_id}.",
                )
        for decision in self.decisiones:
            for bloqueado in decision.get("bloquea") or []:
                if bloqueado not in todos:
                    self.emitir(
                        "PL-013",
                        MEDIA,
                        decision["id"],
                        f"Bloquea el elemento inexistente {bloqueado}.",
                    )

    # ── PL-015 … PL-019 (cotejo de identidad) ───────────────────────────────
    def cotejo_de_identidad(self, cotejo: CotejoLedger) -> None:
        # Un cotejo calculado sobre otro contenido no se reutiliza: es un error de uso
        # (entrada equivocada), no una propiedad del plan; por eso ValueError y no un
        # hallazgo, que haría parecer auditado un ledger que no se cotejó.
        problemas = cotejo.problemas_correspondencia(self.ledger)
        if problemas or [a.afirmacion for a in cotejo.afirmaciones] != [a["id"] for a in self.afirmaciones]:
            raise ValueError(
                "el cotejo de identidad no corresponde a este ledger: "
                + ("; ".join(problemas) or "afirmaciones distintas")
            )
        for afirmacion, agregado in zip(self.afirmaciones, cotejo.afirmaciones):
            objetivo = afirmacion["id"]
            verificada = self.estado(afirmacion) == VERIFICADO
            if verificada:
                for par in agregado.pares:
                    if par.resultado == DISCREPANTE:
                        self.emitir(
                            "PL-015",
                            BLOQUEANTE,
                            objetivo,
                            f"Evidencia {par.evidencia} DISCREPANTE en el cotejo de identidad "
                            f"(paso {par.paso}, {PASOS.get(par.paso, '—')}): "
                            + "; ".join(m.resumen() for m in par.motivos[:3])
                            + ".",
                        )
                sin_conforme = not any(par.resultado == CONFORME for par in agregado.pares)
                if sin_conforme or agregado.resultado == SIN_EVIDENCIA:
                    detalle = "; ".join(
                        [
                            f"{par.evidencia}: {par.resultado}"
                            + (f" ({par.motivos[0].resumen()})" if par.motivos else "")
                            for par in agregado.pares
                        ]
                        + [m.resumen() for m in agregado.motivos]
                    ) or "no cita evidencias"
                    self.emitir(
                        "PL-016",
                        BLOQUEANTE,
                        objetivo,
                        "VERIFICADO sin respaldo CONFORME en el cotejo de identidad "
                        f"({detalle}). Sin evidencia CONFORME que cubra lo que la afirmación "
                        "menciona, sostiene a lo sumo NO VERIFICABLE.",
                    )
            for par in agregado.pares:
                if par.resultado == CONFORME and par.requiere_decision_humana:
                    self._decision_sobre_advertencias(objetivo, verificada, par)
            # PL-018 (PEN-01 D6): el CONFORME descansa en las demás evidencias; lo que solo
            # sostienen las no cotejadas queda sin verificar. Visible, no bloquea.
            sin_cotejar = agregado.pares_sin_cotejar
            if sin_cotejar:
                detalle = "; ".join(
                    f"{par.evidencia}: {par.resultado}"
                    + (f" ({par.motivos[0].resumen()})" if par.motivos else "")
                    for par in sin_cotejar
                )
                self.emitir(
                    "PL-018",
                    ADVERTENCIA,
                    objetivo,
                    f"Evidencia citada sin cotejar en una afirmación que quedó CONFORME por sus demás "
                    f"evidencias ({detalle}). Lo que solo esa evidencia sostiene no queda verificado "
                    "por el cotejo de identidad.",
                )
            # PL-019 (D1, ronda 2): artículo eximido como remisión documentada por la fuente.
            if agregado.remitidos:
                self.emitir(
                    "PL-019",
                    ADVERTENCIA,
                    objetivo,
                    f"Artículo remitido sin cotejar: {', '.join(agregado.remitidos)}. La afirmación lo "
                    "presenta como remisión y el extracto CONFORME de la ley citada lo nombra con la "
                    "misma ley, pero su contenido no se cotejó.",
                )

    def _decision_sobre_advertencias(self, objetivo: str, verificada: bool, par: Any) -> None:
        """PL-017. Una decisión atiende las advertencias de la fuente de una evidencia solo
        si declara en ``advertencias_fuente`` la evidencia, el ``sha256_documento`` (o la
        ``huella_registro``) vigente, los códigos que resuelve y una resolución no vacía,
        y su responsable es una persona humana (como en PL-012). Para sostener un
        VERIFICADO debe estar APROBADA (como una contradicción resuelta en PL-011); para
        otros estados basta con que esté registrada para esa evidencia y esa fuente."""
        codigos = ", ".join(par.codigos_advertencia)
        if any(decision_atiende(d, par, aprobada=verificada) for d in self.decisiones):
            return
        candidatas = decisiones_candidatas(self.decisiones, par)
        porque = "; ".join(
            f"{d['id']}: "
            + (
                "no está APROBADA"
                if verificada
                and not problemas_decision_advertencias(d, par)
                and normalizar_estado(d["estado"], admitir_aprobado=True) != APROBADO
                else ", ".join(problemas_decision_advertencias(d, par, exigir_resolucion=verificada))
            )
            for d in candidatas
        )
        detalle = f" Decisiones que no la atienden: {porque}." if porque else ""
        if verificada:
            self.emitir(
                "PL-017",
                BLOQUEANTE,
                objetivo,
                f"VERIFICADO apoyado en {par.evidencia}, cuya fuente trae advertencias ({codigos}), "
                "sin una decisión humana APROBADA que declare advertencias_fuente "
                f"(evidencia {par.evidencia}, sha256_documento vigente, códigos y resolución).{detalle}",
            )
        else:
            self.emitir(
                "PL-017",
                ALTA,
                objetivo,
                f"La fuente de {par.evidencia} trae advertencias ({codigos}) sin una decisión humana "
                "registrada que las atienda (advertencias_fuente con la evidencia y el "
                f"sha256_documento vigente).{detalle}",
            )

    # ── PL-020 (cotejo de fidelidad, PR-4) ──────────────────────────────────
    def fidelidad(self, fidelidad: FidelidadLedger) -> None:
        """Señales de fidelidad sin decisión humana que las atienda (ver el docstring)."""
        # Igual que el cotejo: uno calculado sobre otro contenido es un error de uso.
        problemas = fidelidad.problemas_correspondencia(self.ledger)
        if problemas:
            raise ValueError("el cotejo de fidelidad no corresponde a este ledger: " + "; ".join(problemas))
        for resultado in fidelidad.afirmaciones:
            if resultado.resultado != SENALES:
                continue
            afirmacion = self.afirmaciones[resultado.indice]
            if afirmacion["id"] != resultado.afirmacion:
                raise ValueError("el cotejo de fidelidad no corresponde a este ledger: afirmaciones distintas")
            verificada = self.estado(afirmacion) == VERIFICADO
            plan = self.ledger["plan"].get("id")
            pendientes = senales_pendientes(resultado, afirmacion, self.decisiones, verificada=verificada, plan=plan)
            altas = [s for s in pendientes if s.precision == PRECISION_ALTA]
            a_revisar = [s for s in pendientes if s.precision != PRECISION_ALTA]
            if altas:
                self.emitir(
                    "PL-020",
                    BLOQUEANTE if verificada else ALTA,
                    afirmacion["id"],
                    self._mensaje_fidelidad(altas, "señal(es) de alta precisión", afirmacion, verificada, plan),
                )
            if a_revisar:
                self.emitir(
                    "PL-020",
                    ADVERTENCIA,
                    afirmacion["id"],
                    self._mensaje_fidelidad(a_revisar, "señal(es) a revisar", afirmacion, verificada, plan),
                )

    def _mensaje_fidelidad(self, senales: list, clase: str, afirmacion: dict, verificada: bool, plan: Any) -> str:
        partes = []
        for senal in senales:
            fuente = " ".join(senal.tramo_fuente.split())
            if len(fuente) > 160:
                fuente = fuente[:159] + "…"
            partes.append(f"{senal.codigo} [{senal.severidad}] — {senal.detalle}"
                          + (f"; fuente: «{fuente}»" if fuente else ""))
        candidatas = [d for d in self.decisiones if isinstance(d.get("fidelidad"), dict)
                      and d["fidelidad"].get("afirmacion") == afirmacion["id"]]
        porque = "; ".join(
            f"{d['id']}: " + ", ".join(problemas_decision_fidelidad(d, afirmacion, senales[0], verificada=verificada,
                                                                    plan=plan))
            for d in candidatas
        )
        detalle = f" Decisiones que no las atienden: {porque}." if porque else ""
        return (
            f"Fidelidad: {len(senales)} {clase} con el texto oficial sin decisión humana que la(s) atienda: "
            + " | ".join(partes)
            + ". Las reglas deterministas no sustituyen la lectura del abogado."
            + detalle
        )

    # ── PL-014 ──────────────────────────────────────────────────────────────
    def cobertura(self, documento: str) -> None:
        textos: list[str] = []
        for afirmacion in self.afirmaciones:
            textos.extend(afirmacion.get("referencias") or [])
            textos.append(afirmacion["texto"])
        indice = indice_cobertura(textos)
        reportadas: set[tuple] = set()
        for mencion in extraer_menciones(documento):
            clave = (mencion.tipo, mencion.clave, *mencion.calificadores)
            if clave in reportadas or esta_cubierta(mencion, indice):
                continue
            reportadas.add(clave)
            mensaje = (
                f"Mención «{mencion.original}» ({mencion.normalizada}) sin afirmación "
                "que la cubra."
            )
            if mencion.tipo == RANGO and mencion.detalle:
                mensaje += f" {mencion.detalle[:1].upper()}{mencion.detalle[1:]}: solo la cubre el mismo rango."
            if mencion.ambigua:
                mensaje += " Mención ambigua: no identifica el ordenamiento."
            self.emitir("PL-014", BLOQUEANTE, f"documento:L{mencion.linea}", mensaje)


def lint_ledger(
    ledger: dict,
    *,
    documento: str | None = None,
    hosts_oficiales: Iterable[str] = HOSTS_OFICIALES,
    paquete: Any = None,
    cotejo: CotejoLedger | None = None,
    extractores: Sequence[Extractor] = (),
    fidelidad: FidelidadLedger | None = None,
) -> list[dict]:
    """Aplica PL-001 … PL-014 y devuelve los hallazgos ordenados por severidad y regla.

    Lanza ``LedgerInvalido`` si el ledger no cumple el esquema ``plan-ledger/1.0``.
    PL-014 solo se evalúa cuando se pasa ``documento``. PL-015 … PL-019 solo se evalúan
    con un paquete de evidencia ya cargado (``paquete``) o con su ``cotejo`` ya
    calculado (``identidad.cotejar_ledger``); PL-020, con el paquete o con un cotejo de
    ``fidelidad`` ya calculado (``fidelidad.cotejar_fidelidad``). Sin ninguno, el
    resultado es idéntico al del lint sin cotejo. Un ``cotejo`` o una ``fidelidad``
    calculados sobre otro contenido del ledger lanzan ``ValueError``. ``extractores`` se
    pasan al cotejo (relación original–texto de las leyes).
    """
    if paquete is not None and (cotejo is not None or fidelidad is not None):
        raise ValueError("pasar paquete o cotejo/fidelidad ya calculados, no ambos")
    errores = validar_esquema(ledger)
    if errores:
        raise LedgerInvalido(errores)
    if paquete is not None:
        cache: dict = {}  # identidad y fidelidad comparten la re-extracción de cada PDF
        cotejo = cotejar_ledger(ledger, paquete, extractores=extractores, cache=cache)
        fidelidad = cotejar_fidelidad(ledger, paquete, cotejo=cotejo, extractores=extractores, cache=cache)
    auditoria = _Auditoria(ledger, frozenset(hosts_oficiales))
    auditoria.estados_fuera_de_vocabulario()
    auditoria.verificadas_sin_soporte()
    auditoria.inexistentes_sin_prueba()
    auditoria.aprobaciones_invalidas()
    auditoria.contradicciones_mal_declaradas()
    auditoria.decisiones_sin_responsable()
    auditoria.ids_y_referencias()
    if documento is not None:
        auditoria.cobertura(documento)
    if cotejo is not None:
        auditoria.cotejo_de_identidad(cotejo)
    if fidelidad is not None:
        auditoria.fidelidad(fidelidad)
    return sorted(
        auditoria.hallazgos,
        key=lambda h: (_RANGO[h["severidad"]], h["regla"]),
    )


def esta_bloqueado(hallazgos: Iterable[dict]) -> bool:
    """``True`` si hay al menos un hallazgo BLOQUEANTE."""
    return any(h["severidad"] == BLOQUEANTE for h in hallazgos)


def resumen_severidades(hallazgos: Iterable[dict]) -> dict[str, int]:
    """Conteo de hallazgos por severidad, con las tres claves siempre presentes."""
    conteo = {severidad: 0 for severidad in SEVERIDADES}
    for hallazgo in hallazgos:
        conteo[hallazgo["severidad"]] += 1
    return conteo
