#!/usr/bin/env python3
"""Bucle de un protocolo de materia: la parte determinista de la skill `protocolo-materia`.

Los agentes (A1 RAG, A2 SJF, A3 redacción, A5 revisión de diseño) los orquesta la skill.
Este script hace lo que no necesita un modelo:

  preparar   carpeta de la materia (fuera del repo), config.json, precondición de corpus
             según el último reporte de vigencia y fixtures que deben reprobar
  prompts    arma los prompts de A1, A2 y A5 con las plantillas de la skill y config.json
  escribir   guarda un borrador solo si pasa G1 (y respalda la versión anterior)
  gates      corre G1–G4, deja gates_iterN.json y el historial, y decide seguir o parar
  evidencia  arma evidencia_sjf/ y <clave>.evidencia.json con las tesis citadas
  revisar    coteja lo que entregaron A1 (extractos literales del RAG) y A2 (datos idénticos a
             la captura del SJF) y mide los topes del presupuesto
  medir      anota tokens y minutos de un agente en estado.json
  cerrar     vuelca el último reporte a la evidencia y cierra estado.json

Las salidas viven fuera del repositorio (por omisión ~/itosturre-data/protocolos-justia/,
o PROTOCOLOS_DIR): son entregables del sistema de destino, no de Itosturre. El script
nunca firma: APROBADO es de una persona identificada y se liga al sha256 del protocolo.

Uso:
  python scripts/protocolo_materia.py preparar <materia> --leyes "LEY DE AMPARO" "CPEUM" ...
         --ley-principal "de la Ley de Amparo" [--ley-no-indexada "de la Ley …"] [--sin-rag]
  python scripts/protocolo_materia.py prompts  <carpeta> [--agentes a1 a2 a5]
  python scripts/protocolo_materia.py escribir <carpeta> <borrador.json>
  python scripts/protocolo_materia.py gates    <carpeta> [--cambio "…"] [--origen A5] [--sin-rag]
  python scripts/protocolo_materia.py evidencia <carpeta> --citadas <registro> ...
  python scripts/protocolo_materia.py revisar  <carpeta>
  python scripts/protocolo_materia.py medir    <carpeta> --agente A1 --tokens N --minutos M
  python scripts/protocolo_materia.py cerrar   <carpeta>

G3 usa el índice de CHROMA_PATH y el intérprete actual (el del venv con el corpus).
Salida: 0 éxito · 1 seguir (o precondición no cumplida) · 2 uso o archivo inválido ·
4 paro del bucle (hueco de corpus, mismo fallo dos vueltas seguidas o tope de iteraciones).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.protocolos.contrato import (  # noqa: E402
    ERROR, MATERIAS, SECCIONES, canonizar, clave_esperada, es_fuente_local, norm, validar_esquema,
)
from itosturre.protocolos.gates import GATES, correr_gates, huella  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SKILL = REPO / ".claude" / "skills" / "protocolo-materia"
PLANTILLAS = SKILL / "references"
BASE_POR_OMISION = Path.home() / "itosturre-data" / "protocolos-justia"
REPORTES_VIGENCIA = REPO / "reportes" / "vigencia_corpus"
NOMBRE_PLANTILLA = "Plantilla_Base_Protocolo_de_Materia_Complemento_del_Agente.docx"

MAX_ITERACIONES = 8
PRIORIDAD = ("G1", "G2", "G3", "G4")
# Fallos que no se arreglan reescribiendo: falta la fuente en el corpus (Regla 7).
HUECO_DE_CORPUS = {"TESIS_FUERA_DEL_CORPUS", "NO_VERIFICABLE", "AUDITORIA_NO_UTILIZABLE"}
EXITO, SEGUIR, PARO = "EXITO", "SEGUIR", "PARO"
SALIDA = {EXITO: 0, SEGUIR: 1, PARO: 4}
PRESUPUESTO = {"consultas_a1": 35, "terminos_a2": 6, "registros_a2": 12, "hallazgos_a5": 12}
# Ley ficticia para el fixture de ley no indexada cuando la materia no tiene un hueco conocido.
LEY_FICTICIA = "de la Ley General de Prueba de Protocolos de Materia"
SECCIONES_A1 = {
    "I": "I. Jerarquía normativa propia",
    "II": "II. Principios rectores con su fundamento y sus límites",
    "III": "III. Métodos con anclaje normativo",
    "V": "V. Advertencias particulares",
}
USO_CAMPOS = (
    "`instrucciones` → todos los agentes; `objecionesTipicas` → el agente adversario "
    "(«por dónde se cae el asunto»); `datosIndispensables` → el analista de hechos («lo que "
    "un especialista pregunta siempre»; marcará indispensable solo el más determinante); "
    "`palabras` → activación determinista (al menos dos coincidencias, por subcadena "
    "normalizada sin acentos, en el mensaje del usuario)."
)

Auditor = Callable[[str], dict]


# ── utilidades ────────────────────────────────────────────────────────────────


def ahora() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def leer_json(ruta: Path, defecto: Any = ...) -> Any:
    try:
        return json.loads(Path(ruta).read_text(encoding="utf-8"))
    except FileNotFoundError:
        if defecto is not ...:
            return defecto
        raise SystemExit(f"❌ No existe {ruta}") from None
    except (OSError, ValueError) as exc:
        raise SystemExit(f"❌ No se pudo leer {ruta}: {exc}") from None


def escribir_json(ruta: Path, datos: Any) -> None:
    """Escritura atómica: o queda el archivo nuevo completo o el anterior intacto."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporal, ruta)


def fuera_del_repo(ruta: Path, que: str) -> Path:
    ruta = Path(ruta).expanduser().resolve()
    if ruta == REPO or REPO in ruta.parents:
        raise SystemExit(f"❌ {que} ({ruta}) está dentro del repositorio: los protocolos y su evidencia "
                         "son entregables del sistema de destino y viven fuera (PROTOCOLOS_DIR).")
    return ruta


def base_de(ruta: Optional[Path]) -> Path:
    return fuera_del_repo(ruta or Path(os.environ.get("PROTOCOLOS_DIR") or BASE_POR_OMISION),
                          "La carpeta base")


def palabras_por_seccion(protocolo: dict) -> list[int]:
    return [len(str(s).split()) for s in canonizar(protocolo).get("instrucciones") or []]


class Carpeta:
    """La carpeta de una materia: config.json, estado.json, historial.jsonl y el protocolo."""

    def __init__(self, ruta: Path):
        self.ruta = fuera_del_repo(ruta, "La carpeta de la materia")
        self.config: dict = leer_json(self.ruta / "config.json")
        self.clave: str = self.config["clave"]

    @property
    def protocolo(self) -> Path:
        return self.ruta / f"{self.clave}.json"

    @property
    def evidencia(self) -> Path:
        return self.ruta / f"{self.clave}.evidencia.json"

    def estado(self) -> dict:
        return leer_json(self.ruta / "estado.json", {})

    def guardar_estado(self, estado: dict) -> None:
        escribir_json(self.ruta / "estado.json", estado)

    def historial(self) -> list[dict]:
        ruta = self.ruta / "historial.jsonl"
        if not ruta.exists():
            return []
        return [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]

    def anotar(self, entrada: dict) -> None:
        with open(self.ruta / "historial.jsonl", "a", encoding="utf-8") as archivo:
            archivo.write(json.dumps(entrada, ensure_ascii=False) + "\n")

    def ficha(self) -> Optional[dict]:
        ruta = self.config.get("fichas")
        if not ruta or not Path(ruta).exists():
            return None
        fichas = leer_json(Path(ruta))
        return fichas.get(self.config["materia"]) if isinstance(fichas, dict) else None


# ── precondición: corpus, jurisprudencia local y fixtures ──────────────────────


def ultimo_reporte_vigencia(directorio: Path = REPORTES_VIGENCIA) -> Optional[Path]:
    reportes = sorted(Path(directorio).glob("vigencia_*.json"))
    return reportes[-1] if reportes else None


def estado_de_leyes(reporte: Optional[dict], leyes: list[str]) -> list[dict]:
    """Semáforo de cada ley pedida según el reporte de vigencia (fuente, etiqueta o nombre).

    🟢 y ⚪ (tratados) permiten avanzar; 🟡 exige cotejo antes de citar (Regla 8); 🔴 o una
    ley que no aparece en el índice bloquean: decide el abogado (Reglas 7 y 8)."""
    filas = (reporte or {}).get("filas") or []
    resultado = []
    for ley in leyes:
        buscada = norm(ley).replace(".pdf", "").strip()
        halladas = [
            f for f in filas
            if buscada and any(buscada in norm(str(f.get(campo) or "")) for campo in ("fuente", "etiqueta", "nombre_oficial"))
        ]
        if not halladas:
            resultado.append({"ley": ley, "semaforo": "⛔", "estado": "NO_INDEXADA", "condicion": "BLOQUEA"})
            continue
        for fila in halladas:
            semaforo = fila.get("semaforo") or "?"
            condicion = "OK" if semaforo in ("🟢", "⚪") else "COTEJO" if semaforo == "🟡" else "BLOQUEA"
            estado = fila.get("estado")
            if es_fuente_local(str(fila.get("fuente") or "")):
                # Enfoque nacional (11-oct-2026): una ley local no entra en un protocolo de materia.
                condicion, estado = "BLOQUEA", "LEY_LOCAL (enfoque nacional)"
            resultado.append({"ley": ley, "fuente": fila.get("fuente"), "semaforo": semaforo,
                              "estado": estado, "version_indexada": fila.get("version_indexada"),
                              "condicion": condicion})
    return resultado


def jurisprudencia_local() -> dict:
    """Cuántas tesis tiene el corpus local de jurisprudencia (la ruta que usa el auditor)."""
    ruta = Path(os.environ.get("JURISPRUDENCIA_PATH") or REPO / "jurisprudencia")
    archivos = sorted(ruta.rglob("*.json")) if ruta.exists() else []
    tesis = 0
    for archivo in archivos:
        try:
            datos = json.loads(archivo.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tesis += len(datos) if isinstance(datos, list) else 0
    return {"ruta": str(ruta), "archivos": len(archivos), "tesis": tesis}


def _minimo(materia: str, clave: str) -> dict:
    return {
        "clave": clave, "version": "v1", "nombre": "Fixture del bucle (no es un protocolo)",
        "materia": materia, "palabras": ["fixture uno", "fixture dos"],
        "datosIndispensables": ["Dato de prueba."], "objecionesTipicas": ["Objeción de prueba."],
        "instrucciones": [SECCIONES[0] + " Rige el artículo 1o de la CPEUM."]
                         + [s + " Texto de prueba." for s in SECCIONES[1:]],
    }


def fixtures(materia: str, clave: str, config: dict) -> dict[str, tuple[dict, list[str], bool]]:
    """nombre → (protocolo, códigos de ERROR esperados, ¿necesita el RAG?)."""

    def con(i: int, extra: str) -> dict:
        p = _minimo(materia, clave)
        p["instrucciones"][i] += " " + extra
        return p

    principal = config["ley_principal"]
    ajena = config.get("ley_no_indexada") or LEY_FICTICIA
    return {
        "rojo_rol": (con(0, "Eres el juez que resuelve el asunto."), ["R1_ROL"], False),
        "rojo_formato": (con(3, "Devuelve faseActual con la etapa del juicio."), ["R2_FORMATO_SALIDA"], False),
        "rojo_entidad": (con(1, "En Jalisco rige otro plazo."), ["R5_ENTIDAD_FEDERATIVA"], False),
        "rojo_inexistente": (con(0, f"También rige el artículo 9999 {principal}."), ["REFUTADA"], True),
        "rojo_no_indexada": (con(0, f"También rige el artículo 19 {ajena}."), ["NO_VERIFICABLE"], True),
        "verde_control": (_minimo(materia, clave), [], True),
    }


def correr_fixtures(carpeta: Carpeta, *, con_rag: bool, auditor: Optional[Auditor] = None) -> dict:
    ficha = carpeta.ficha()
    resultado = {}
    for nombre, (protocolo, esperados, necesita_rag) in fixtures(
            carpeta.config["materia"], carpeta.clave, carpeta.config).items():
        destino = carpeta.ruta / "fixtures" / f"{nombre}.json"
        escribir_json(destino, protocolo)
        if necesita_rag and not con_rag:
            resultado[nombre] = {"esperado": esperados, "obtenido": None, "ok": None,
                                 "nota": "sin RAG: no se corrió"}
            continue
        datos = correr_gates(protocolo, ficha=ficha, con_rag=necesita_rag, auditor=auditor).to_dict()
        escribir_json(destino.with_name(f"{nombre}.gates.json"), datos)
        obtenidos = sorted({h["codigo"] for h in datos["hallazgos"] if h["severidad"] == ERROR})
        ok = set(esperados) <= set(obtenidos) if esperados else not obtenidos
        resultado[nombre] = {"esperado": esperados, "obtenido": obtenidos, "ok": ok}
    return resultado


def _plantilla_por_omision(base: Path) -> Path:
    for candidata in (base / NOMBRE_PLANTILLA, Path.home() / "Downloads" / NOMBRE_PLANTILLA):
        if candidata.exists():
            return candidata
    return base / NOMBRE_PLANTILLA


def preparar(materia: str, base: Path, *, leyes: Optional[list[str]] = None,
             ley_principal: Optional[str] = None, ley_no_indexada: Optional[str] = None,
             fichas: Optional[Path] = None, plantilla: Optional[Path] = None, con_rag: bool = True,
             auditor: Optional[Auditor] = None, reporte_vigencia: Optional[Path] = None) -> tuple[int, dict]:
    if materia not in MATERIAS:
        raise SystemExit(f"❌ '{materia}' no está en el catálogo: {', '.join(MATERIAS)}")
    clave = clave_esperada(materia)
    ruta = base / clave
    for sub in ("investigacion", "evidencia_sjf", "fixtures", "prompts"):
        (ruta / sub).mkdir(parents=True, exist_ok=True)

    config = leer_json(ruta / "config.json", {})
    config.update({"materia": materia, "clave": clave})
    if leyes:
        config["leyes"] = list(leyes)
    if ley_principal:
        config["ley_principal"] = ley_principal
    if ley_no_indexada:
        config["ley_no_indexada"] = ley_no_indexada
    if not config.get("ley_principal"):
        raise SystemExit("❌ Falta --ley-principal (p. ej. \"de la Ley de Amparo\"): sin él no hay "
                         "fixture que pruebe que G3 reprueba un artículo inexistente en esta materia.")
    config["fichas"] = str(fichas or config.get("fichas") or base / "fichas_simulador.json")
    config["plantilla"] = str(plantilla or config.get("plantilla") or _plantilla_por_omision(base))
    for campo, vacio in (("alcance", ""), ("temas_a1", {}), ("temas_a2", []), ("advertencias_a2", []),
                         ("contexto_a5", []), ("presupuesto", dict(PRESUPUESTO)),
                         ("modelos", {"a1": "heredar", "a2": "heredar", "a5": "heredar"})):
        config.setdefault(campo, vacio)
    escribir_json(ruta / "config.json", config)

    carpeta = Carpeta(ruta)
    reporte = reporte_vigencia or ultimo_reporte_vigencia()
    corpus = estado_de_leyes(leer_json(reporte, None) if reporte else None, config.get("leyes") or [])
    resultado_fixtures = correr_fixtures(carpeta, con_rag=con_rag, auditor=auditor)
    estado = carpeta.estado()
    estado.setdefault("inicio", ahora())
    estado.setdefault("iteracion", 0)
    estado.update({"materia": materia, "clave": clave, "precondicion": {
        "fecha": ahora(), "reporte_vigencia": reporte.name if reporte else None, "corpus": corpus,
        "fixtures": resultado_fixtures, "corpus_jurisprudencia_local": jurisprudencia_local()}})

    problemas = []
    if not reporte:
        problemas.append("no hay reporte de vigencia (python scripts/vigencia_corpus.py)")
    if not config.get("leyes"):
        problemas.append("config.json no declara las leyes de la materia (--leyes)")
    problemas += [f"{c['ley']}: {c['semaforo']} {c['estado']}" for c in corpus if c["condicion"] == "BLOQUEA"]
    problemas += [f"el fixture {n} no reprobó como debía: esperado {r['esperado']}, obtenido {r['obtenido']}"
                  for n, r in resultado_fixtures.items() if r["ok"] is False]
    estado["etapa"] = "investigación (A1, A2)" if not problemas else "precondición no cumplida"
    estado["precondicion"]["problemas"] = problemas
    carpeta.guardar_estado(estado)
    return (0 if not problemas else 1), estado


# ── prompts de los agentes ─────────────────────────────────────────────────────

_MARCA = re.compile(r"\{\{(\w+)\}\}")


def renderizar(plantilla: str, valores: dict[str, str]) -> str:
    faltan = sorted({m.group(1) for m in _MARCA.finditer(plantilla)} - set(valores))
    if faltan:
        raise SystemExit(f"❌ Faltan valores para la plantilla: {', '.join(faltan)}")
    return _MARCA.sub(lambda m: str(valores[m.group(1)]), plantilla)


def _vinetas(elementos: Any) -> str:
    if isinstance(elementos, str):
        elementos = [elementos]
    return "\n".join(f"- {e}" for e in elementos or [])


def _temas_a1(temas: dict) -> str:
    lineas = []
    for seccion, rotulo in SECCIONES_A1.items():
        valor = temas.get(seccion)
        if valor:
            texto = "; ".join(valor) if isinstance(valor, list) else str(valor)
            lineas.append(f"- {rotulo}: {texto}")
    return "\n".join(lineas)


def _ficha(ficha: Optional[dict]) -> str:
    if not ficha:
        return "(no se recibió la ficha procesal de la materia: no mapees la tramitación ni el estándar probatorio)"
    partes = [("código aplicable", "codigo"), ("etapas", "etapas"), ("principios", "principios"), ("estándar", "estandar")]
    return "; ".join(f"{rotulo} «{ficha[campo]}»" for rotulo, campo in partes if ficha.get(campo)) + "."


def _versiones(estado: dict) -> str:
    filas = (estado.get("precondicion") or {}).get("corpus") or []
    if not isinstance(filas, list):   # estado.json de una corrida anterior a este script
        filas = []
    datos = [f"«{f['fuente']}» ({f['version_indexada']})" for f in filas
             if isinstance(f, dict) and f.get("fuente") and f.get("version_indexada")]
    if not datos:
        return ""
    return (" Versiones indexadas: " + "; ".join(datos) + ". No supongas que su texto coincide con versiones "
            "anteriores que recuerdes: repórtalo tal como lo trae el fragmento.")


def valores(carpeta: Carpeta) -> dict[str, str]:
    c = carpeta.config
    estado = carpeta.estado()
    destino = leer_json(carpeta.ruta.parent / "destino.json", {})
    presupuesto = {**PRESUPUESTO, **(c.get("presupuesto") or {})}
    ajena = c.get("ley_no_indexada")
    protocolo = leer_json(carpeta.protocolo, None)
    return {
        "materia": c["materia"], "MATERIA": c["materia"].upper().replace("_", " "), "clave": carpeta.clave,
        "alcance": f"; {c['alcance']}" if c.get("alcance") else "",
        "repo": str(REPO), "python": sys.executable,
        "chroma": os.environ.get("CHROMA_PATH") or "<definir CHROMA_PATH: ver docs/ENTORNO.md>",
        "scraper": str(REPO / "services" / "itosturre-scraper"), "carpeta": str(carpeta.ruta),
        "leyes": ", ".join(f"«{ley}»" for ley in c.get("leyes") or []),
        "versiones": _versiones(estado),
        "no_indexada": (f" La ley citada como «{ajena}» NO está indexada: no la busques; si un tema depende "
                        "de ella, anótalo en \"huecos\".") if ajena else "",
        "ficha": _ficha(carpeta.ficha()),
        "temas_a1": _temas_a1(c.get("temas_a1") or {}),
        "temas_a2": _vinetas(c.get("temas_a2")),
        "advertencias_a2": "\n".join(f"Cuidado: {a}" for a in c.get("advertencias_a2") or []),
        "contexto_a5": _vinetas(c.get("contexto_a5")) or "- (sin contexto adicional)",
        **{k: str(v) for k, v in presupuesto.items()},
        "destino": destino.get("descripcion") or "un sistema de agentes jurídicos",
        "uso_campos": destino.get("uso_campos") or USO_CAMPOS,
        "plantilla": c.get("plantilla", ""), "fichas": c.get("fichas", ""),
        "protocolo": str(carpeta.protocolo),
        "palabras_por_seccion": ", ".join(map(str, palabras_por_seccion(protocolo))) if protocolo else "",
    }


PLANTILLA_DE = {"a1": "a1_cartografo.md", "a2": "a2_investigador.md", "a5": "a5_revisor.md"}


def prompts(carpeta: Carpeta, agentes: list[str], plantillas: Path = PLANTILLAS) -> list[Path]:
    c = carpeta.config
    requisitos = {
        "a1": [("leyes", c.get("leyes")), ("temas_a1", c.get("temas_a1"))],
        "a2": [("temas_a2", c.get("temas_a2"))],
        "a5": [(f"{carpeta.clave}.json", carpeta.protocolo.exists())],
    }
    faltan = [f"{agente}: {nombre}" for agente in agentes for nombre, valor in requisitos[agente] if not valor]
    if faltan:
        raise SystemExit("❌ config.json o la carpeta no están listos para: " + "; ".join(faltan))
    datos = valores(carpeta)
    escritos = []
    for agente in agentes:
        texto = renderizar((plantillas / PLANTILLA_DE[agente]).read_text(encoding="utf-8"), datos)
        destino = carpeta.ruta / "prompts" / f"{agente}.md"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        escritos.append(destino)
    return escritos


# ── borrador, gates y decisión del bucle ───────────────────────────────────────


def escribir(carpeta: Carpeta, borrador: dict) -> tuple[int, list[str]]:
    """Guarda el borrador como <clave>.json solo si pasa G1; respalda la versión anterior."""
    mensajes = [f"{h.codigo} [{h.ruta}]: {h.mensaje}" for h in validar_esquema(borrador) if h.severidad == ERROR]
    if isinstance(borrador, dict) and canonizar(borrador).get("clave") != carpeta.clave:
        mensajes.append(f"CLAVE: el borrador no es de {carpeta.clave}")
    if mensajes:
        return 1, mensajes
    if carpeta.protocolo.exists():
        respaldo = carpeta.ruta / f"{carpeta.clave}.iter{carpeta.estado().get('iteracion', 0)}.json"
        if not respaldo.exists():
            shutil.copy2(carpeta.protocolo, respaldo)
    escribir_json(carpeta.protocolo, borrador)
    return 0, [f"palabras por sección: {palabras_por_seccion(borrador)} · sha256 {huella(borrador)[:12]}"]


def _firmas(errores: list[dict]) -> list[list[str]]:
    return sorted([h["gate"], h["codigo"], h.get("ruta", ""), h["mensaje"][:160]] for h in errores)


def decidir(datos: dict, iteracion: int, previas: Optional[list] = None) -> dict:
    """EXITO, SEGUIR (con el único fallo a atender) o PARO (hueco de corpus, estancado, tope)."""
    errores = [h for h in datos["hallazgos"] if h["severidad"] == ERROR]
    incompletos = [g for g in GATES if datos["gates"].get(g) == "NO_CORRIDO"]
    if not errores:
        if incompletos:
            return {"estado": SEGUIR, "motivo": f"sin errores, pero sin correr {', '.join(incompletos)}: "
                                                "no hay éxito sin todos los gates"}
        return {"estado": EXITO, "motivo": "G1–G4 en verde"}
    resto = [h for h in errores if h["codigo"] not in HUECO_DE_CORPUS]
    if not resto:
        return {"estado": PARO, "paro": "HUECO_DE_CORPUS",
                "motivo": "solo quedan fuentes que no están en el corpus (Regla 7): decide el abogado — "
                          "promover las tesis con scripts/promover_tesis.py, completar el corpus o quitar las citas",
                "pendientes": sorted({h["codigo"] for h in errores})}
    if iteracion >= MAX_ITERACIONES:
        return {"estado": PARO, "paro": "TOPE", "motivo": f"{MAX_ITERACIONES} iteraciones sin llegar a verde"}
    if previas is not None and _firmas(errores) == previas:
        return {"estado": PARO, "paro": "ESTANCADO",
                "motivo": "el mismo fallo dos vueltas seguidas: el diagnóstico está mal; escalar al abogado"}
    elegido = min(resto, key=lambda h: PRIORIDAD.index(h["gate"]) if h["gate"] in PRIORIDAD else len(PRIORIDAD))
    return {"estado": SEGUIR, "motivo": f"{elegido['gate']} {elegido['codigo']}",
            "fallo": {k: elegido.get(k) for k in ("gate", "codigo", "ruta", "mensaje")}}


def iteracion(carpeta: Carpeta, *, con_rag: bool = True, auditor: Optional[Auditor] = None,
              cambio: Optional[str] = None, origen: Optional[str] = None) -> tuple[dict, dict]:
    protocolo = leer_json(carpeta.protocolo)
    evidencia = leer_json(carpeta.evidencia, None)
    datos = correr_gates(protocolo, ficha=carpeta.ficha(), evidencia=evidencia, con_rag=con_rag,
                         auditor=auditor).to_dict()
    estado = carpeta.estado()
    n = int(estado.get("iteracion", 0)) + 1
    escribir_json(carpeta.ruta / f"gates_iter{n}.json", datos)
    escribir_json(carpeta.ruta / "gates.json", datos)
    anteriores = [e for e in carpeta.historial() if "errores" in e]
    previas = anteriores[-1]["errores"] if anteriores else None
    veredicto = decidir(datos, n, previas)
    errores = [h for h in datos["hallazgos"] if h["severidad"] == ERROR]
    entrada = {"iteracion": n, "fecha": ahora(), "gates": datos["gates"], "sha256": datos["sha256"],
               "errores": _firmas(errores), "veredicto": veredicto["estado"], "motivo": veredicto["motivo"]}
    if cambio:
        entrada["cambio"] = cambio
    if origen:
        entrada["origen"] = origen
    carpeta.anotar(entrada)
    estado.update({"iteracion": n, "ultimo_veredicto": veredicto,
                   "etapa": {EXITO: "gates en verde: pasa a revisión de diseño (A5) o a la firma del abogado",
                             SEGUIR: f"iteración {n}: atender {veredicto['motivo']}",
                             PARO: f"detenido: {veredicto.get('paro')}"}[veredicto["estado"]]})
    carpeta.guardar_estado(estado)
    return datos, veredicto


# ── evidencia, medición y cierre ──────────────────────────────────────────────


def evidencia(carpeta: Carpeta, citadas: list[str]) -> tuple[int, list[str]]:
    """evidencia_sjf/ con solo las tesis citadas (insumo de promover_tesis.py) y la evidencia
    hermana del protocolo; las demás verificadas quedan como candidatas para el abogado."""
    verificados: dict[str, dict] = {}
    capturas: dict[str, Path] = {}
    cabecera: dict = {}
    for auditoria in sorted((carpeta.ruta / "investigacion" / "a2").rglob("auditoria_vvca.json")):
        datos = leer_json(auditoria)
        cabecera = cabecera or {k: v for k, v in datos.items() if k not in ("verificados", "propuestas")}
        for tesis in datos.get("verificados") or []:
            registro = str(tesis.get("registro"))
            verificados[registro] = tesis
            capturas[registro] = auditoria.parent / f"sjf_{registro}.png"
    citadas = [str(r) for r in citadas]
    faltan = [r for r in citadas if verificados.get(r, {}).get("estado_consulta") != "VERIFICADO"]
    if faltan:
        return 1, [f"sin captura VERIFICADO del SJF: {', '.join(faltan)} — sin captura no hay cita "
                   "(quitarla o marcarla [VERIFICAR EN SJF])"]
    destino = carpeta.ruta / "evidencia_sjf"
    destino.mkdir(parents=True, exist_ok=True)
    escribir_json(destino / "auditoria_vvca.json", {
        **cabecera, "verificados": [verificados[r] for r in citadas], "propuestas": [],
        "_nota": "Solo las tesis citadas en el protocolo: insumo de scripts/promover_tesis.py si el abogado "
                 "decide promoverlas al corpus local de jurisprudencia (Regla 3)."})
    for registro in citadas:
        if capturas[registro].exists():
            shutil.copy2(capturas[registro], destino / capturas[registro].name)
    # Las candidatas son las que A2 propuso (sus "verificadas"), no todo lo que el scraper
    # verificó: A2 descarta a propósito aisladas, duplicadas o de ley abrogada.
    propuesta_a2 = leer_json(carpeta.ruta / "investigacion" / "a2" / "a2_jurisprudencia.json", None)
    temas = {str(t.get("registro")): t.get("tema") for t in (propuesta_a2 or {}).get("verificadas") or []}
    propuestas = set(temas) if propuesta_a2 is not None else set(verificados)

    def ficha(registro: str, citada: bool) -> dict:
        t = verificados[registro]
        return {"registro": registro, "numero_tesis": t.get("numero_tesis"), "rubro": t.get("rubro"),
                "tipo": t.get("tipo_tesis"), "instancia": t.get("sala"), "epoca": t.get("epoca"),
                "fuente": t.get("fuente"), "estado_consulta": t.get("estado_consulta"),
                "estado_vigencia": t.get("estado_vigencia"),
                "url": t.get("url") or f"https://sjf2.scjn.gob.mx/detalle/tesis/{registro}",
                "consultado_en": t.get("consultado_en") or t.get("capturado_en"), "tema": temas.get(registro),
                "captura": (f"evidencia_sjf/sjf_{registro}.png" if citada
                            else str(capturas[registro].relative_to(carpeta.ruta)))}

    actual = leer_json(carpeta.evidencia, {})
    protocolo = leer_json(carpeta.protocolo, {})
    candidatas = [ficha(r, False) for r, t in verificados.items()
                  if r not in citadas and r in propuestas and t.get("estado_consulta") == "VERIFICADO"]
    # Rehacer la evidencia no pierde lo que ya tenía: las candidatas agregadas a mano (aunque A2 las
    # hubiera descartado) y las tesis que dejan de citarse vuelven a candidatas. Quitar una candidata
    # es decisión del abogado y se hace a mano.
    vistas = set(citadas) | {t["registro"] for t in candidatas}
    for previa in (actual.get("tesis_candidatas_capa2") or []) + (actual.get("tesis") or []):
        registro = str(previa.get("registro"))
        if registro not in vistas:
            vistas.add(registro)
            candidatas.append(ficha(registro, False) if registro in verificados else previa)
    actual.update({
        "clave": carpeta.clave, "version": canonizar(protocolo).get("version") if protocolo else None,
        "tesis": [ficha(r, True) for r in citadas],
        "tesis_candidatas_capa2": candidatas,
    })
    actual.setdefault("notas_de_cita", [])
    actual.setdefault("aprobacion", {"estado": "PENDIENTE", "abogado": None, "fecha": None, "contenido_sha256": None})
    escribir_json(carpeta.evidencia, actual)
    return 0, [f"{len(citadas)} tesis citadas con captura; {len(actual['tesis_candidatas_capa2'])} candidatas"]


def _plano(texto: str) -> str:
    """Texto comparable: sin escapes de salto de línea y con los espacios colapsados."""
    return re.sub(r"\s+", " ", str(texto).replace("\\n", " ").replace("\\t", " ")).strip()


CAMPOS_A2 = {"numero_tesis": "numero_tesis", "rubro": "rubro", "epoca": "epoca", "fuente": "fuente",
             "instancia": "sala", "tipo": "tipo_tesis"}


def revisar(carpeta: Carpeta) -> dict:
    """Coteja con la fuente lo que entregaron A1 y A2 (ningún agente le cree a otro sobre un
    hecho): cada extracto de A1 debe ser literal de la salida cruda del RAG, y cada dato de A2
    debe coincidir con la captura del scraper. Mide también los topes del presupuesto."""
    investigacion = carpeta.ruta / "investigacion"
    presupuesto = {**PRESUPUESTO, **(carpeta.config.get("presupuesto") or {})}
    resultado: dict = {}
    mapa = leer_json(investigacion / "a1_mapa_normativo.json", None)
    if mapa is not None:
        crudo_dir = investigacion / "a1_raw"
        crudo = " ".join(_plano(p.read_text(encoding="utf-8", errors="ignore"))
                         for p in sorted(crudo_dir.rglob("*")) if p.is_file()) if crudo_dir.exists() else ""
        items = mapa.get("items") or []
        ajenos = [(i, it) for i, it in enumerate(items) if not crudo or _plano(it.get("extracto", "")) not in crudo]
        resultado["a1"] = {
            "items": len(items), "literales": len(items) - len(ajenos) if crudo else None,
            "sin_salida_cruda": not crudo,
            "no_literales": [{"item": i, "articulo": it.get("articulo"), "extracto": str(it.get("extracto", ""))[:120]}
                             for i, it in ajenos][:25] if crudo else [],
            "consultas": mapa.get("consultas_realizadas"), "tope_consultas": presupuesto["consultas_a1"],
            "huecos": len(mapa.get("huecos") or []),
        }
    propuesta = leer_json(investigacion / "a2" / "a2_jurisprudencia.json", None)
    if propuesta is not None:
        capturas: dict[str, dict] = {}
        for auditoria in sorted((investigacion / "a2").rglob("auditoria_vvca.json")):
            for tesis in leer_json(auditoria).get("verificados") or []:
                capturas[str(tesis.get("registro"))] = tesis
        diferencias, sin_captura, cotejados = [], [], 0
        for tesis in propuesta.get("verificadas") or []:
            registro = str(tesis.get("registro"))
            captura = capturas.get(registro)
            if not captura or captura.get("estado_consulta") != "VERIFICADO":
                sin_captura.append(registro)
                continue
            for propio, del_scraper in CAMPOS_A2.items():
                if tesis.get(propio) is None:
                    continue
                cotejados += 1
                if _plano(tesis[propio]) != _plano(captura.get(del_scraper) or ""):
                    diferencias.append({"registro": registro, "campo": propio, "a2": str(tesis[propio])[:90],
                                        "scraper": str(captura.get(del_scraper))[:90]})
        resultado["a2"] = {
            "verificadas": len(propuesta.get("verificadas") or []), "campos_cotejados": cotejados,
            "diferencias": diferencias, "sin_captura_verificada": sin_captura,
            "terminos": len(propuesta.get("terminos") or []), "tope_terminos": presupuesto["terminos_a2"],
            "registros_con_detalle": len(capturas), "tope_registros": presupuesto["registros_a2"],
        }
    return resultado


def medir(carpeta: Carpeta, agente: str, tokens: int, minutos: float) -> dict:
    estado = carpeta.estado()
    medicion = estado.setdefault("medicion", {})
    medicion[agente] = {"tokens": tokens, "minutos": minutos}
    medicion["tokens_subagentes"] = sum(v["tokens"] for k, v in medicion.items()
                                        if isinstance(v, dict) and "tokens" in v)
    carpeta.guardar_estado(estado)
    return estado


def cerrar(carpeta: Carpeta) -> tuple[int, list[str]]:
    reporte = leer_json(carpeta.ruta / "gates.json")
    protocolo = leer_json(carpeta.protocolo)
    if reporte.get("sha256") != huella(protocolo):
        return 1, ["el último reporte no corresponde al protocolo actual: corre `gates` antes de cerrar"]
    estado = carpeta.estado()
    veredicto = estado.get("ultimo_veredicto") or {}
    actual = leer_json(carpeta.evidencia, {})
    actual["version"] = canonizar(protocolo).get("version")   # la evidencia describe la versión que se cierra
    actual["gates"] = {"reporte": "gates.json", "estado": reporte["gates"], "sha256_protocolo": reporte["sha256"],
                       "veredicto": veredicto}
    actual.setdefault("aprobacion", {"estado": "PENDIENTE", "abogado": None, "fecha": None, "contenido_sha256": None})
    escribir_json(carpeta.evidencia, actual)
    fin = dt.datetime.now(dt.timezone.utc)
    estado["fin"] = fin.isoformat(timespec="seconds")
    if estado.get("inicio"):
        inicio = dt.datetime.fromisoformat(estado["inicio"])
        estado["minutos_totales"] = round((fin - inicio).total_seconds() / 60, 1)
    estado["etapa"] = (f"cerrado ({veredicto.get('paro') or veredicto.get('estado') or 'sin veredicto'}): "
                       "pendiente la revisión y la firma del abogado")
    carpeta.guardar_estado(estado)
    return 0, [estado["etapa"], f"sha256 {reporte['sha256'][:12]} · gates {reporte['gates']}"]


# ── CLI ───────────────────────────────────────────────────────────────────────


def _resumen_gates(datos: dict, n: int, veredicto: dict) -> str:
    estados = " · ".join(f"{g} {datos['gates'][g]}" for g in GATES)
    lineas = [f"{'🟢' if datos['ok'] else '🔴'} {datos['clave']} — iteración {n} — {estados} — "
              f"sha256 {datos['sha256'][:12]}"]
    conteo: dict[tuple[str, str], int] = {}
    for h in datos["hallazgos"]:
        if h["severidad"] == ERROR:
            conteo[(h["gate"], h["codigo"])] = conteo.get((h["gate"], h["codigo"]), 0) + 1
    lineas += [f"   {g} {c} ×{k}" for (g, c), k in sorted(conteo.items())]
    icono = {EXITO: "✅", SEGUIR: "➡️", PARO: "⏹"}[veredicto["estado"]]
    lineas.append(f"{icono} {veredicto['estado']}{' ' + veredicto['paro'] if veredicto.get('paro') else ''}: "
                  f"{veredicto['motivo']}")
    if veredicto.get("fallo"):
        lineas.append(f"   → {veredicto['fallo']['mensaje'][:400]}")
    return "\n".join(lineas)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Bucle determinista de un protocolo de materia")
    sub = parser.add_subparsers(dest="orden", required=True)

    p = sub.add_parser("preparar")
    p.add_argument("materia")
    p.add_argument("--base", type=Path)
    p.add_argument("--leyes", nargs="+")
    p.add_argument("--ley-principal")
    p.add_argument("--ley-no-indexada")
    p.add_argument("--fichas", type=Path)
    p.add_argument("--plantilla", type=Path)
    p.add_argument("--sin-rag", action="store_true")

    p = sub.add_parser("prompts")
    p.add_argument("carpeta", type=Path)
    p.add_argument("--agentes", nargs="+", choices=sorted(PLANTILLA_DE), default=["a1", "a2"])

    p = sub.add_parser("escribir")
    p.add_argument("carpeta", type=Path)
    p.add_argument("borrador", type=Path)

    p = sub.add_parser("gates")
    p.add_argument("carpeta", type=Path)
    p.add_argument("--cambio")
    p.add_argument("--origen")
    p.add_argument("--sin-rag", action="store_true")

    p = sub.add_parser("evidencia")
    p.add_argument("carpeta", type=Path)
    p.add_argument("--citadas", nargs="+", required=True)

    p = sub.add_parser("revisar")
    p.add_argument("carpeta", type=Path)

    p = sub.add_parser("medir")
    p.add_argument("carpeta", type=Path)
    p.add_argument("--agente", required=True)
    p.add_argument("--tokens", type=int, required=True)
    p.add_argument("--minutos", type=float, required=True)

    p = sub.add_parser("cerrar")
    p.add_argument("carpeta", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.orden == "preparar":
            codigo, estado = preparar(
                args.materia, base_de(args.base), leyes=args.leyes, ley_principal=args.ley_principal,
                ley_no_indexada=args.ley_no_indexada, fichas=args.fichas, plantilla=args.plantilla,
                con_rag=not args.sin_rag)
            pre = estado["precondicion"]
            for c in pre["corpus"]:
                print(f"{c['semaforo']} {c['ley']} → {c.get('fuente') or c['estado']} {c.get('version_indexada') or ''}")
            for nombre, r in pre["fixtures"].items():
                marca = "✅" if r["ok"] else "⚪" if r["ok"] is None else "❌"
                print(f"{marca} fixture {nombre}: esperado {r['esperado'] or 'sin errores'}, obtenido {r['obtenido']}")
            juris = pre["corpus_jurisprudencia_local"]
            print(f"📚 corpus local de jurisprudencia: {juris['tesis']} tesis en {juris['archivos']} archivo(s)"
                  + (" — toda tesis citada se detendrá en hueco de corpus" if not juris["tesis"] else ""))
            print(("✅ " if codigo == 0 else "❌ ") + estado["etapa"]
                  + "".join(f"\n   · {x}" for x in pre.get("problemas") or []))
            return codigo
        carpeta = Carpeta(args.carpeta)
        if args.orden == "prompts":
            for ruta in prompts(carpeta, args.agentes):
                print(f"📝 {ruta}")
            return 0
        if args.orden == "escribir":
            codigo, mensajes = escribir(carpeta, leer_json(args.borrador))
            print(("✅ escrito " + str(carpeta.protocolo) if codigo == 0 else "❌ no se escribió: no pasa G1"))
            for m in mensajes:
                print(f"   {m}")
            return codigo
        if args.orden == "gates":
            datos, veredicto = iteracion(carpeta, con_rag=not args.sin_rag, cambio=args.cambio, origen=args.origen)
            print(_resumen_gates(datos, carpeta.estado()["iteracion"], veredicto))
            return SALIDA[veredicto["estado"]]
        if args.orden == "revisar":
            informe = revisar(carpeta)
            estado = carpeta.estado()
            estado["revision_agentes"] = {**informe, "fecha": ahora()}
            carpeta.guardar_estado(estado)
            print(json.dumps(informe, ensure_ascii=False, indent=2))
            a1, a2 = informe.get("a1") or {}, informe.get("a2") or {}
            falla = (a1.get("literales") is not None and a1["literales"] < a1["items"]) or bool(a2.get("diferencias")) \
                or bool(a2.get("sin_captura_verificada"))
            return 1 if falla else 0
        if args.orden == "evidencia":
            codigo, mensajes = evidencia(carpeta, args.citadas)
        elif args.orden == "medir":
            estado = medir(carpeta, args.agente, args.tokens, args.minutos)
            codigo, mensajes = 0, [f"tokens de subagentes: {estado['medicion']['tokens_subagentes']}"]
        else:
            codigo, mensajes = cerrar(carpeta)
        for m in mensajes:
            print(("✅ " if codigo == 0 else "❌ ") + m)
        return codigo
    except SystemExit as exc:
        if isinstance(exc.code, str):
            print(exc.code, file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
