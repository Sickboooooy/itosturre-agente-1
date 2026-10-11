"""Gates G3 y G4 — las citas del protocolo se someten a la fuente, no a un agente.

G3 (normas): cada referencia a un artículo pasa por el auditor VVCA del corpus local
(`OpenNotebook.py audit`, 100 % local). El gate exige que TODAS salgan verificadas: un 🔴
reprueba; un 🟡 también, pero con el camino correcto según su causa — ley no indexada
(Regla 7: decide el abogado: completar el corpus o marcar [VERIFICAR EN DOF]), versión
indexada no vigente (Regla 8: cotejo con `scripts/cotejo_manual.py articulo`), cobertura
incompleta o cita ligada a más de una ley (en ambos casos, reescribir la cita en la
convención auditable). Antes del auditor se revisa
la convención de citación: "artículo 31, fracción IV", no "31-IV".

G4 (jurisprudencia): toda tesis citada lleva su registro digital, y ese registro debe
tener en la evidencia su captura de la página pública del SJF hecha con el scraper con
navegador (estado_consulta VERIFICADO, vigente). Esa captura NO acredita la cita por sí
sola (Regla 3: el SJF en vivo propone; las citas se verifican contra el corpus): es el
insumo para promoverla al corpus local de jurisprudencia con `scripts/promover_tesis.py`,
paso que decide el abogado, y es G3, contra ese corpus, quien la da por verificada. Sin
captura no hay cita: se quita o se marca [VERIFICAR EN SJF].
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

from itosturre.protocolos.contrato import AVISO, ERROR, Hallazgo, es_fuente_local, norm, textos

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

Auditor = Callable[[str], dict]

# Fracción pegada al artículo con guion ("31-IV"): el extractor no la separa y la cita no se
# puede auditar. Se exigen dos o más numerales romanos para no confundirla con artículos
# como 17-H, 17-I o 69-B.
_NOTACION_RE = re.compile(r"\b(\d{1,4})-([IVXL]{2,})\b")

_REGISTRO_RE = re.compile(r"\b(?:registro(?:\s+digital)?|ius)\s*(?:n[uú]m\.?|no\.?)?\s*:?\s*(\d{6,7})\b", re.I)
# Alertas del auditor que no reprueban G3 (11-oct-2026): la tesis del corpus local citada por
# clave y registro, sin rubro transcrito, como pide la plantilla del protocolo.
AVISOS_G3 = frozenset({"TESIS_SIN_RUBRO_TRANSCRITO"})
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
    if "sin rubro invocado" in t:
        return "TESIS_SIN_RUBRO_TRANSCRITO", (
            "la tesis está en el corpus local y se cita por clave y registro, sin rubro: G4 coteja la "
            "clave contra la captura del SJF; que el criterio respalde lo afirmado lo revisan A3 y A5")
    if "registro digital" in t and "corpus de jurisprudencia" in t:
        return "TESIS_FUERA_DEL_CORPUS", (
            "Reglas 3 y 7: decide el abogado — promoverla al corpus local con scripts/promover_tesis.py "
            "desde su captura del SJF, o quitarla o marcarla [VERIFICAR EN SJF]")
    if "cobertura incompleta" in t:
        return "COBERTURA_INCOMPLETA", "reescribir la cita en la convención auditable"
    # "LEY NO IDENTIFICADA" tiene varias causas. Solo un ordenamiento fuera del corpus es la
    # Regla 7 (más abajo); una cita ligada a más de una ley o a ninguna es de redacción.
    if "ley no identificada" in t and ("vinculos en conflicto" in t or "ambiguo" in t):
        return "LEY_AMBIGUA", (
            "la cita queda ligada a más de una ley: escribir la ley junto al artículo, quitar de "
            "su izquierda las palabras que el auditor lee como ordenamiento ('norma' en singular, "
            "'ley' o 'código' sueltos, 'tratados') y unir las series con 'y'")
    if "ley no identificada" in t and ("no liga" in t or "no tiene un antecedente" in t or "sin denominacion" in t):
        return "CITA_SIN_LEY", (
            "la cita no nombra la ley: escribirla junto al artículo (p. ej. «artículo 123 de la CPEUM»)")
    # Antes que la Regla 7: el motivo de la sigla menciona "ley no indexada" y "corpus".
    if "ley no identificada" in t and "sigla fuera del catalogo" in t:
        return "SIGLA_DESCONOCIDA", (
            "el auditor no reconoce la sigla: escribir la denominación de la ley (p. ej. «Ley del "
            "ISSSTE»), una sigla reconocida, o definirla antes de usarla («Ley del ISSSTE (LISSSTE)»)")
    if "no vigente" in t or "vigencia" in t:
        return "VIGENCIA", "Regla 8: cotejar con scripts/cotejo_manual.py articulo antes de citar"
    if "no indexad" in t or "no verificable" in t or "corpus" in t:
        return "NO_VERIFICABLE", ("Regla 7: decide el abogado — completar el corpus o marcar "
                                  "[VERIFICAR EN DOF]")
    if "inexistente" in t or "refutad" in t:
        return refutada
    return "ALERTA", "revisar la cita contra la fuente oficial"


# ── Regla 8: ley en 🟡 → cotejo de cada artículo contra el PDF oficial (11-oct-2026) ─────────
# El auditor da 🟢 a un artículo que existe en la versión indexada aunque el reporte de vigencia
# tenga la ley en 🟡; CLAUDE.md (Regla 8) exige entonces cotejarlo con la fuente oficial antes de
# citar su texto. G3 lo pide aquí: cada artículo de una ley en 🟡 pasa por `cotejo_manual.py`.
Cotejador = Callable[[str, list[str]], dict[str, str]]
_COTEJO_TITULO_RE = re.compile(r"^## Cotejo · .*? · artículo (?P<articulo>.+?)\s*$")
_COTEJO_RESULTADO_RE = re.compile(r"^- \*\*Resultado \(Capa 1\):\*\*\s*(?P<resultado>.+?)\s*$")


def leyes_no_verdes(directorio: Optional[Path] = None) -> dict[str, str]:
    """Fuente indexada → etiqueta de las leyes en 🟡 del último reporte de vigencia."""
    directorio = directorio or REPO_ROOT / "reportes" / "vigencia_corpus"
    reportes = sorted(directorio.glob("vigencia_*.json"))
    if not reportes:
        return {}
    try:
        filas = json.loads(reportes[-1].read_text(encoding="utf-8")).get("filas") or []
    except (OSError, ValueError):
        return {}
    return {
        f["fuente"]: f.get("etiqueta") or f["fuente"]
        for f in filas
        if isinstance(f, dict) and f.get("semaforo") == "🟡" and f.get("fuente")
    }


def resultados_cotejo(salida: str) -> dict[str, str]:
    """Artículo → línea de resultado de las fichas que imprime `cotejo_manual.py articulo`."""
    resultados: dict[str, str] = {}
    articulo: Optional[str] = None
    for linea in salida.splitlines():
        titulo = _COTEJO_TITULO_RE.match(linea)
        if titulo:
            articulo = titulo.group("articulo")
            continue
        resultado = _COTEJO_RESULTADO_RE.match(linea)
        if resultado and articulo is not None:
            resultados[articulo] = resultado.group("resultado")
            articulo = None
    return resultados


def cotejador_local(ley: str, articulos: list[str]) -> dict[str, str]:
    """Corre `scripts/cotejo_manual.py articulo` (lectura del PDF oficial ya preparado)."""
    resultado = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "cotejo_manual.py"), "articulo", ley, *articulos],
        cwd=REPO_ROOT, capture_output=True, text=True, env=os.environ.copy(), check=False,
    )
    return resultados_cotejo(resultado.stdout)


def _regla_8(informe: dict, no_verdes: Optional[dict[str, str]],
             cotejador: Optional[Cotejador]) -> list[Hallazgo]:
    por_ley: dict[str, list[str]] = {}
    for fuente in informe.get("retrieved_sources") or []:
        if not isinstance(fuente, dict) or fuente.get("ref_type") != "normativa":
            continue
        archivo, articulo = fuente.get("source_file"), str(fuente.get("article") or "").strip()
        if archivo and articulo and articulo not in por_ley.setdefault(archivo, []):
            por_ley[archivo].append(articulo)
    if not por_ley:
        return []
    if no_verdes is None:
        no_verdes = leyes_no_verdes()
    hallazgos: list[Hallazgo] = []
    for archivo, articulos in por_ley.items():
        if archivo not in no_verdes:
            continue
        etiqueta = no_verdes[archivo]
        resultados = (cotejador or cotejador_local)(etiqueta, articulos)
        for articulo in articulos:
            resultado = resultados.get(articulo, "")
            if resultado.startswith("🟢"):
                continue
            if resultado.startswith("🔴"):
                hallazgos.append(_h(
                    "G3", ERROR, "COTEJO_DIFIERE",
                    f"Regla 8: artículo {articulo} de {etiqueta} (ley en 🟡): {resultado[:160]} → citar "
                    "el texto oficial de la ficha de cotejo, nunca el del RAG"))
            else:
                hallazgos.append(_h(
                    "G3", ERROR, "COTEJO_PENDIENTE",
                    f"Regla 8: artículo {articulo} de {etiqueta} (ley en 🟡): "
                    f"{resultado[:160] or 'sin resultado del cotejo'} → cotejarlo con "
                    "`scripts/cotejo_manual.py articulo` (`preparar` si falta el PDF oficial), o quitar "
                    "el número y marcar [VERIFICAR EN: fuente oficial]"))
    return hallazgos


def _leyes_locales(informe: dict) -> list[Hallazgo]:
    """Enfoque nacional (11-oct-2026): un artículo que resuelve a una ley estatal o municipal no
    se cita; lo local se remite a la ley de la entidad del asunto."""
    hallazgos: list[Hallazgo] = []
    vistos: set[tuple[str, str]] = set()
    for fuente in informe.get("retrieved_sources") or []:
        if not isinstance(fuente, dict) or fuente.get("ref_type") != "normativa":
            continue
        archivo, articulo = fuente.get("source_file") or "", str(fuente.get("article") or "").strip()
        if archivo and es_fuente_local(archivo) and (archivo, articulo) not in vistos:
            vistos.add((archivo, articulo))
            hallazgos.append(_h(
                "G3", ERROR, "LEY_LOCAL",
                f"artículo {articulo} de «{archivo}»: es una ley local y el protocolo es nacional → "
                "remitir a la ley de la entidad del asunto [VERIFICAR EN: …], sin citar artículos de "
                "un código estatal"))
    return hallazgos


def auditar_normas(
    protocolo: dict, auditor: Optional[Auditor] = None, *,
    no_verdes: Optional[dict[str, str]] = None, cotejador: Optional[Cotejador] = None,
) -> tuple[list[Hallazgo], dict]:
    """Hallazgos de G3 y el JSON del auditor (para la evidencia). ``no_verdes`` (fuente →
    etiqueta de las leyes en 🟡; por omisión, el último reporte de vigencia) y ``cotejador``
    (por omisión, `cotejo_manual.py`) aplican la Regla 8."""
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
        severidad = AVISO if codigo in AVISOS_G3 else ERROR
        hallazgos.append(_h("G3", severidad, codigo, f"{str(alerta)[:300]} → {camino}"))
    hallazgos += _regla_8(informe, no_verdes, cotejador)
    hallazgos += _leyes_locales(informe)

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


def _clave_normal(clave: str) -> str:
    return re.sub(r"\s+", "", clave).lower()


def _claves_por_registro(protocolo: dict) -> dict[str, set[str]]:
    """Clave de tesis citada justo antes de cada registro ("1a./J. 49/2025 (11a.), registro
    digital 2030412"): con ella G4 ata la cita a la captura del SJF."""
    pares: dict[str, set[str]] = {}
    for _, texto in textos(protocolo):
        for m in _REGISTRO_RE.finditer(texto):
            previas = list(_CLAVE_TESIS_RE.finditer(texto, max(0, m.start() - 60), m.start()))
            if previas:
                pares.setdefault(m.group(1), set()).add(previas[-1].group(0))
    return pares


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
    pares = _claves_por_registro(protocolo)
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
        captura = _clave_normal(str(tesis.get("numero_tesis") or ""))
        for clave in sorted(pares.get(registro, ())):
            if captura and not captura.startswith(_clave_normal(clave)):
                hallazgos.append(_h(
                    "G4", ERROR, "TESIS_CLAVE_DISCREPANTE",
                    f"registro {registro}: se cita como '{clave}', pero la captura del SJF dice "
                    f"'{tesis.get('numero_tesis')}'"))
        vigencia = norm(str(tesis.get("estado_vigencia") or ""))
        if vigencia and vigencia not in ("vigente",):
            hallazgos.append(_h(
                "G4", ERROR, "TESIS_NO_VIGENTE", f"registro {registro}: estado de vigencia '{vigencia}'"))
    return hallazgos
