"""Corre los gates de un protocolo de materia y arma el reporte con su evidencia.

G1 contrato · G2 complemento, no sustituto · G3 normas (RAG local) · G4 jurisprudencia
(evidencia del SJF). G5 (activación por palabras en el registro de destino) y G6
(fidelidad) quedan fuera de esta primera versión: G5 solo aplica si el protocolo se
inyecta por el registro de protocolos, y G6 solo señala, nunca aprueba.

Un ERROR en cualquier gate reprueba el protocolo. Los AVISOS van al abogado. La
aprobación final es siempre humana y se liga a la huella `sha256` del contenido.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from itosturre.protocolos.citas import Auditor, auditar_normas, verificar_jurisprudencia
from itosturre.protocolos.contrato import ERROR, Hallazgo, canonizar, validar_esquema
from itosturre.protocolos.lint import lint

GATES = ("G1", "G2", "G3", "G4")


def huella(protocolo: dict) -> str:
    """SHA-256 del protocolo en JSON canónico (claves ordenadas, compacto, UTF-8)."""
    canonico = json.dumps(protocolo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


@dataclass
class Reporte:
    clave: str
    sha256: str
    hallazgos: list[Hallazgo] = field(default_factory=list)
    gates_corridos: list[str] = field(default_factory=list)
    auditoria_rag: Optional[dict] = None
    generado: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def ok(self) -> bool:
        return not any(h.severidad == ERROR for h in self.hallazgos)

    def estado_gate(self, gate: str) -> str:
        if gate not in self.gates_corridos:
            return "NO_CORRIDO"
        return "ERROR" if any(h.gate == gate and h.severidad == ERROR for h in self.hallazgos) else "OK"

    def to_dict(self) -> dict:
        return {
            "clave": self.clave,
            "sha256": self.sha256,
            "generado": self.generado,
            "ok": self.ok,
            "gates": {g: self.estado_gate(g) for g in GATES},
            "hallazgos": [h.to_dict() for h in self.hallazgos],
            "auditoria_rag": self.auditoria_rag,
        }


def correr_gates(
    protocolo: dict,
    *,
    ficha: Optional[dict] = None,
    evidencia: Optional[dict] = None,
    auditor: Optional[Auditor] = None,
    con_rag: bool = True,
) -> Reporte:
    """Corre G1–G4. Si G1 reprueba, los demás no se corren: no se auditan citas de un
    protocolo que ni siquiera tiene la forma correcta."""
    es_objeto = isinstance(protocolo, dict)
    reporte = Reporte(clave=str(canonizar(protocolo).get("clave", "")) if es_objeto else "",
                      sha256=huella(protocolo) if es_objeto else "")
    reporte.hallazgos += validar_esquema(protocolo)
    reporte.gates_corridos.append("G1")
    if not reporte.ok:
        return reporte

    reporte.hallazgos += lint(protocolo, ficha)
    reporte.gates_corridos.append("G2")
    if con_rag:
        hallazgos, informe = auditar_normas(protocolo, auditor)
        reporte.hallazgos += hallazgos
        reporte.auditoria_rag = informe
        reporte.gates_corridos.append("G3")
    reporte.hallazgos += verificar_jurisprudencia(protocolo, evidencia)
    reporte.gates_corridos.append("G4")
    return reporte
