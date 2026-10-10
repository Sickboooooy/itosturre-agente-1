"""Gates G3 y G4 — las citas del protocolo se someten a la fuente, no a un agente.

G3 (normas): cada referencia a un artículo pasa por el auditor VVCA del corpus local
(`OpenNotebook.py audit`, 100 % local). El gate exige que TODAS salgan verificadas: un 🔴
reprueba; un 🟡 también, pero con el camino correcto según su causa — ley no indexada
(Regla 7: decide el abogado: completar el corpus o marcar [VERIFICAR EN DOF]), versión
indexada no vigente (Regla 8: cotejo con `scripts/cotejo_manual.py articulo`) o cobertura
incompleta (reescribir la cita en la convención auditable). Antes del auditor se revisa
la convención de citación: "artículo 31, fracción IV", no "31-IV".

G4 (jurisprudencia): toda tesis citada lleva su registro digital, y ese registro debe
estar en la evidencia con la verificación del scraper con navegador sobre la página
pública del SJF (estado_consulta VERIFICADO). Sin evidencia no hay cita: se quita o se
marca [VERIFICAR EN SJF]. El SJF en vivo propone; la evidencia capturada es la que acredita.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from itosturre.protocolos.contrato import AVISO, ERROR, Hallazgo, norm, textos

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

Auditor = Callable[[str], dict]

# Fracción pegada al artículo con guion ("31-IV"): el extractor no la separa y la cita no se
# puede auditar. Se exigen dos o más numerales romanos para no confundirla con artículos
# como 17-H, 17-I o 69-B.
_NOTACION_RE = re.compile(r"\b(\d{1,4})-([IVXL]{2,})\b")

_REGISTRO_RE = re.compile(r"\b(?:registro(?:\s+digital)?|ius)\s*(?:n[uú]m\.?|no\.?)?\s*:?\s*(\d{6,7})\b", re.I)
_CLAVE_TESIS_RE = re.compile(
    r"\b(?:\d{1,2}a|P|PR\.[A-Z.]+|[IVX]+\.\d+o\.[A-Z.]*)\s*\./?\s*J\.\s*\d+/\d{4}", re.I)


def _h(gate: str, severidad: str, codigo: str, mensaje: str, ruta: str = "") -> Hallazgo:
    return Hallazgo(gate, severidad, codigo, mensaje, ruta)


def texto_auditable(protocolo: dict) -> str:
    return "\n\n".join(texto for _, texto in textos(protocolo))


def revisar_notacion(protocolo: dict) -> list[Hallazgo]:
    hallazgos = []
    for ruta, texto in textos(protocolo):
        for m in _NOTACION_RE.finditer(texto):
            hallazgos.append(_h(
                "G3", ERROR, "NOTACION_NO_AUDITABLE",
                f"'{m.group(0)}' no se puede auditar: escribir «artículo {m.group(1)}, fracción "
                f"{m.group(2)}»", ruta))
    return hallazgos


def auditor_local(texto: str) -> dict:
    """Corre `OpenNotebook.py audit --text` (RAG local) y devuelve su JSON.

    Usa el intérprete actual; el índice se toma de CHROMA_PATH, como el resto del repo.
    La salida estándar es solo el JSON: los registros van a stderr."""
    resultado = subprocess.run(
        [sys.executable, str(REPO_ROOT / "OpenNotebook.py"), "audit", "--text", texto],
        cwd=REPO_ROOT, capture_output=True, text=True, env=os.environ.copy(), check=False,
    )
    salida = resultado.stdout
    if "{" not in salida:
        raise RuntimeError(f"el auditor no devolvió JSON (código {resultado.returncode}): "
                           f"{resultado.stderr.strip()[-400:]}")
    return json.loads(salida[salida.index("{"):])


def _causa(alerta: str) -> tuple[str, str]:
    """Clasifica una alerta del auditor en (código, camino a seguir)."""
    t = norm(alerta)
    refutada = ("REFUTADA", "la cita es falsa: quitarla o corregirla con la fuente")
    if alerta.lstrip().startswith("🔴"):  # el semáforo del auditor manda sobre el texto
        return refutada
    if "cobertura incompleta" in t:
        return "COBERTURA_INCOMPLETA", "reescribir la cita en la convención auditable"
    if "no vigente" in t or "vigencia" in t:
        return "VIGENCIA", "Regla 8: cotejar con scripts/cotejo_manual.py articulo antes de citar"
    if "no indexad" in t or "no verificable" in t or "corpus" in t:
        return "NO_VERIFICABLE", ("Regla 7: decide el abogado — completar el corpus o marcar "
                                  "[VERIFICAR EN DOF]")
    if "inexistente" in t or "refutad" in t:
        return refutada
    return "ALERTA", "revisar la cita contra la fuente oficial"


def auditar_normas(protocolo: dict, auditor: Optional[Auditor] = None) -> tuple[list[Hallazgo], dict]:
    """Hallazgos de G3 y el JSON del auditor (para la evidencia)."""
    hallazgos = revisar_notacion(protocolo)
    informe = (auditor or auditor_local)(texto_auditable(protocolo))
    resumen = informe.get("vvca_summary") or {}

    if informe.get("status") != "ok":
        hallazgos.append(_h(
            "G3", ERROR, "AUDITORIA_NO_UTILIZABLE",
            f"el auditor terminó con status '{informe.get('status')}' (p. ej. corpus incompleto): "
            "Regla 7 — decide el abogado: completar el corpus o continuar con la advertencia visible"))
    for alerta in list(informe.get("alerts") or []) + list(informe.get("avisos") or []):
        codigo, camino = _causa(str(alerta))
        hallazgos.append(_h("G3", ERROR, codigo, f"{str(alerta)[:300]} → {camino}"))

    total = int(resumen.get("articulos_total") or 0)
    ok = int(resumen.get("articulos_ok") or 0)
    if total == 0:
        hallazgos.append(_h(
            "G3", AVISO, "SIN_CITAS_NORMATIVAS",
            "el protocolo no cita ningún artículo auditable: la jerarquía normativa (sección I) "
            "suele exigir artículos concretos"))
    elif ok < total and not any(h.gate == "G3" and h.severidad == ERROR for h in hallazgos):
        hallazgos.append(_h(
            "G3", ERROR, "CITAS_SIN_VERIFICAR",
            f"solo {ok} de {total} artículos salieron verificados"))
    for campo in ("normativa_refutada", "normativa_no_verificable"):
        if int(resumen.get(campo) or 0) and not any(h.gate == "G3" and h.severidad == ERROR for h in hallazgos):
            hallazgos.append(_h("G3", ERROR, campo.upper(), f"{campo}: {resumen.get(campo)}"))
    return hallazgos, informe


def tesis_citadas(protocolo: dict) -> tuple[set[str], list[tuple[str, str]]]:
    """(registros citados, [(ruta, clave)] de claves de tesis citadas)."""
    registros: set[str] = set()
    claves: list[tuple[str, str]] = []
    for ruta, texto in textos(protocolo):
        registros.update(m.group(1) for m in _REGISTRO_RE.finditer(texto))
        claves.extend((ruta, m.group(0)) for m in _CLAVE_TESIS_RE.finditer(texto))
    return registros, claves


def verificar_jurisprudencia(protocolo: dict, evidencia: Optional[dict]) -> list[Hallazgo]:
    """Hallazgos de G4. Si el protocolo no cita tesis concretas, no hay nada que verificar."""
    registros, claves = tesis_citadas(protocolo)
    hallazgos: list[Hallazgo] = []
    if claves and not registros:
        for ruta, clave in claves:
            hallazgos.append(_h(
                "G4", ERROR, "TESIS_SIN_REGISTRO",
                f"la tesis '{clave}' se cita sin registro digital: sin registro no se puede verificar",
                ruta))
    verificadas = {
        str(t.get("registro")): t
        for t in ((evidencia or {}).get("tesis") or [])
        if isinstance(t, dict)
    }
    for registro in sorted(registros):
        tesis = verificadas.get(registro)
        if tesis is None:
            hallazgos.append(_h(
                "G4", ERROR, "TESIS_SIN_EVIDENCIA",
                f"registro {registro}: no hay evidencia de su verificación en el SJF (página pública "
                "con el scraper con navegador); quitarla o marcarla [VERIFICAR EN SJF]"))
            continue
        if tesis.get("estado_consulta") != "VERIFICADO":
            hallazgos.append(_h(
                "G4", ERROR, "TESIS_NO_VERIFICADA",
                f"registro {registro}: estado_consulta {tesis.get('estado_consulta')!r}"))
        if not (tesis.get("rubro") or "").strip():
            hallazgos.append(_h("G4", ERROR, "TESIS_SIN_RUBRO", f"registro {registro}: la evidencia no trae rubro"))
        vigencia = norm(str(tesis.get("estado_vigencia") or ""))
        if vigencia and vigencia not in ("vigente",):
            hallazgos.append(_h(
                "G4", ERROR, "TESIS_NO_VIGENTE", f"registro {registro}: estado de vigencia '{vigencia}'"))
    return hallazgos
