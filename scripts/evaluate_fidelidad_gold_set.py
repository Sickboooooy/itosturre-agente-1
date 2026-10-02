#!/usr/bin/env python3
"""Evalúa el Gold Set del cotejo de fidelidad determinista (PR-4, ronda 2).

Dos poblaciones que no se mezclan:

* **Casos sintéticos** (``cases``, ``review_status: "sintetico"``): afirmaciones sintéticas
  con un defecto sembrado por categoría y controles fieles, contra texto de ley real copiado
  literalmente, más los pares adversariales de la revisión externa (fuentes sintéticas
  rotuladas, origen ``sintetico_adversarial``). Son **puerta**:

  - cada categoría de ``fidelidad.CATEGORIAS`` tiene al menos un caso con defecto y recall
    100 % (la señal esperada, con su categoría, severidad y precisión);
  - cada código de precisión alta (``fidelidad.CODIGOS_ALTA``) tiene al menos un caso y
    recall 100 % con ese código;
  - un control fiel no da señales (``tolerancia: "sin_senales"``, por omisión) o no da
    señales de precisión alta (``"sin_bloqueantes"``), ni ninguno de sus
    ``codigos_prohibidos``;
  - **ningún** caso da una señal de precisión alta que no espere: un falso positivo nunca
    puede bloquear.

  Un caso ``limite_documentado`` fija un falso negativo conocido: se informa, no es puerta
  (salvo la regla de que nunca dé una señal alta no esperada).
* **Candidatos del piloto PEN-01** (``candidatos_piloto``): pares propuestos por un agente,
  ``review_status: "pendiente_responsable"``. Se miden aparte (detectados, no detectados,
  falsos positivos y cuántos de ellos serían de precisión alta) y **no** son puerta. Un
  candidato que el responsable jurídico apruebe (``"aprobado_responsable"``) entra en la
  puerta con la verdad que él fije en ``verdad_responsable`` (``"fiel"`` o ``"cambia"``); la
  propuesta del operador nunca se reescribe.

Literalidad: cada texto de fuente coincide con su ``sha256_texto``; los de origen
``fixture`` deben ser subcadena exacta de la página del fixture (en CI); los de
``paquete_piloto`` solo se comprueban con ``--paquete DIR`` (paquete local del piloto, que
no se versiona); los ``sintetico_adversarial`` deben llevar un ``rotulo`` que los declare
sintéticos.

Códigos de salida: 0 puerta superada · 1 algún caso falla, falta una categoría o un código
alto, o un texto no es literal · 2 dataset inválido.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from itosturre.plan.fidelidad import (  # noqa: E402
    ALINEACION,
    ALTA,
    CATEGORIAS,
    CODIGOS,
    CODIGOS_ALTA,
    PRECISIONES,
    SEVERIDADES,
    VERSION_MOTOR,
    FuenteTexto,
    comparar,
)

DEFAULT_GOLD_SET = REPO / "tests" / "fixtures" / "fidelidad_gold_set_v1.json"
SCHEMA_VERSION = "fidelidad-gold-set/2.0"
SINTETICO = "sintetico"
PENDIENTE = "pendiente_responsable"
APROBADO = "aprobado_responsable"
ORIGENES = ("fixture", "paquete_piloto", "sintetico_adversarial")
CONTROL = "control_fiel"
TOLERANCIAS = ("sin_senales", "sin_bloqueantes")
CATEGORIAS_CASO = (*CATEGORIAS, ALINEACION)


class FidelidadGoldSetInvalido(ValueError):
    """El dataset no cumple el contrato del Gold Set de fidelidad."""


def _texto(valor: Any, ubicacion: str) -> str:
    if not isinstance(valor, str) or not valor.strip():
        raise FidelidadGoldSetInvalido(f"{ubicacion} debe ser texto no vacío")
    return valor


def _validar_fuentes(fuentes: Any) -> None:
    if not isinstance(fuentes, dict) or not fuentes:
        raise FidelidadGoldSetInvalido("fuentes debe ser un objeto no vacío")
    for clave, fuente in fuentes.items():
        if not isinstance(fuente, dict) or fuente.get("origen") not in ORIGENES:
            raise FidelidadGoldSetInvalido(f"fuentes.{clave}: origen debe ser uno de {list(ORIGENES)}")
        _texto(fuente.get("texto"), f"fuentes.{clave}.texto")
        _texto(fuente.get("descriptor"), f"fuentes.{clave}.descriptor")
        _texto(fuente.get("sha256_texto"), f"fuentes.{clave}.sha256_texto")
        if fuente["origen"] == "sintetico_adversarial" and "sintético" not in str(fuente.get("rotulo") or ""):
            raise FidelidadGoldSetInvalido(f"fuentes.{clave}: una fuente sintética debe llevar un rótulo que lo diga")
        if "truncado" in fuente and not isinstance(fuente["truncado"], bool):
            raise FidelidadGoldSetInvalido(f"fuentes.{clave}.truncado debe ser booleano")


def _validar_caso(caso: Any, indice: int, fuentes: dict, vistos: set[str]) -> None:
    ubicacion = f"cases[{indice}]"
    if not isinstance(caso, dict):
        raise FidelidadGoldSetInvalido(f"{ubicacion} debe ser un objeto")
    caso_id = _texto(caso.get("id"), f"{ubicacion}.id")
    if caso_id in vistos:
        raise FidelidadGoldSetInvalido(f"id duplicado: {caso_id}")
    vistos.add(caso_id)
    if caso.get("review_status") != SINTETICO:
        raise FidelidadGoldSetInvalido(f"{ubicacion}.review_status debe ser {SINTETICO!r}")
    if caso.get("categoria") not in (*CATEGORIAS_CASO, CONTROL):
        raise FidelidadGoldSetInvalido(f"{ubicacion}.categoria {caso.get('categoria')!r} fuera de vocabulario")
    _texto(caso.get("afirmacion"), f"{ubicacion}.afirmacion")
    claves = caso.get("fuentes")
    if not isinstance(claves, list) or not claves or any(c not in fuentes for c in claves):
        raise FidelidadGoldSetInvalido(f"{ubicacion}.fuentes debe listar claves de 'fuentes'")
    esperado = caso.get("esperado")
    if not isinstance(esperado, list):
        raise FidelidadGoldSetInvalido(f"{ubicacion}.esperado debe ser una lista")
    for senal in esperado:
        if (not isinstance(senal, dict) or senal.get("categoria") not in CATEGORIAS_CASO
                or senal.get("severidad") not in SEVERIDADES or senal.get("precision") not in PRECISIONES):
            raise FidelidadGoldSetInvalido(f"{ubicacion}.esperado: categoría, severidad o precisión fuera de vocabulario")
        if senal.get("codigo") is not None and senal["codigo"] not in CODIGOS:
            raise FidelidadGoldSetInvalido(f"{ubicacion}.esperado: código {senal['codigo']!r} desconocido")
        if senal["precision"] == ALTA and senal.get("codigo") not in CODIGOS_ALTA:
            raise FidelidadGoldSetInvalido(f"{ubicacion}.esperado: una señal alta declara su código de precisión alta")
    if (caso["categoria"] == CONTROL) != (not esperado):
        raise FidelidadGoldSetInvalido(f"{ubicacion}: un control fiel no espera señales y un defecto sí")
    if caso["categoria"] != CONTROL and caso["categoria"] not in {s["categoria"] for s in esperado}:
        raise FidelidadGoldSetInvalido(f"{ubicacion}: la señal esperada debe ser de su categoría")
    if caso.get("tolerancia", "sin_senales") not in TOLERANCIAS:
        raise FidelidadGoldSetInvalido(f"{ubicacion}.tolerancia debe ser uno de {list(TOLERANCIAS)}")
    prohibidos = caso.get("codigos_prohibidos", [])
    if not isinstance(prohibidos, list) or any(c not in CODIGOS for c in prohibidos):
        raise FidelidadGoldSetInvalido(f"{ubicacion}.codigos_prohibidos debe listar códigos conocidos")
    if not isinstance(caso.get("limite_documentado", False), bool):
        raise FidelidadGoldSetInvalido(f"{ubicacion}.limite_documentado debe ser booleano")


def validar_dataset(data: Any) -> dict:
    """Valida la forma del dataset (no el resultado del motor)."""
    if not isinstance(data, dict):
        raise FidelidadGoldSetInvalido("la raíz debe ser un objeto JSON")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise FidelidadGoldSetInvalido(f"schema_version no soportado: {data.get('schema_version')!r}")
    fuentes = data.get("fuentes")
    _validar_fuentes(fuentes)
    casos = data.get("cases")
    if not isinstance(casos, list) or not casos:
        raise FidelidadGoldSetInvalido("cases debe ser una lista no vacía")
    vistos: set[str] = set()
    for indice, caso in enumerate(casos):
        _validar_caso(caso, indice, fuentes, vistos)
    piloto = data.get("candidatos_piloto")
    if piloto is not None:
        candidatos = piloto.get("candidatos") if isinstance(piloto, dict) else None
        if not isinstance(candidatos, list):
            raise FidelidadGoldSetInvalido("candidatos_piloto.candidatos debe ser una lista")
        for indice, candidato in enumerate(candidatos):
            ubicacion = f"candidatos_piloto.candidatos[{indice}]"
            if not isinstance(candidato, dict):
                raise FidelidadGoldSetInvalido(f"{ubicacion} debe ser un objeto")
            _texto(candidato.get("texto_afirmacion"), f"{ubicacion}.texto_afirmacion")
            _texto(candidato.get("texto_oficial"), f"{ubicacion}.texto_oficial")
            _texto(candidato.get("propuesta_operador"), f"{ubicacion}.propuesta_operador")
            estado = candidato.get("review_status")
            if estado not in (PENDIENTE, APROBADO):
                raise FidelidadGoldSetInvalido(f"{ubicacion}.review_status {estado!r} no soportado")
            if estado == APROBADO and candidato.get("verdad_responsable") not in ("fiel", "cambia"):
                raise FidelidadGoldSetInvalido(f"{ubicacion}: aprobado sin verdad_responsable ('fiel' o 'cambia')")
    return data


def _pagina_fixture(fuente: dict) -> str | None:
    ruta = REPO / str(fuente.get("archivo") or "")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return next((p.get("texto") for p in datos.get("paginas", []) if p.get("numero") == fuente.get("pagina")), None)


def verificar_literalidad(fuentes: dict, paquete: str | None = None) -> dict:
    """Problemas de literalidad por fuente y fuentes del piloto no comprobadas."""
    problemas: list[str] = []
    no_comprobadas: list[str] = []
    consulta = None
    if paquete:
        import plan_audit  # perezoso: la CLI trae el extractor PyMuPDF
        from itosturre.evidencia.paquete import cargar_paquete
        from itosturre.plan.identidad import consultar_articulo

        cargado = cargar_paquete(paquete)
        extractores = plan_audit._extractores_disponibles()
        cache: dict = {}

        def consulta(fuente: dict):  # noqa: E306
            return consultar_articulo(cargado, articulo=fuente["articulo"], sha256=fuente.get("sha256_documento"),
                                      url=fuente.get("url"), extractores=extractores, cache=cache)
    for clave, fuente in fuentes.items():
        texto = fuente["texto"]
        if hashlib.sha256(texto.encode("utf-8")).hexdigest() != fuente["sha256_texto"]:
            problemas.append(f"{clave}: el texto no coincide con su sha256_texto (editado)")
        if fuente["origen"] == "fixture":
            pagina = _pagina_fixture(fuente)
            if pagina is None or texto not in pagina:
                problemas.append(f"{clave}: no es subcadena exacta de {fuente.get('archivo')} p. {fuente.get('pagina')}")
        elif fuente["origen"] == "paquete_piloto":
            if consulta is None:
                no_comprobadas.append(clave)
                continue
            try:
                resultado = consulta(fuente)
            except ValueError as error:
                problemas.append(f"{clave}: no se pudo releer en el paquete ({error})")
                continue
            if resultado.tramo is None or texto not in resultado.tramo.texto:
                problemas.append(f"{clave}: no es subcadena exacta del artículo que reconstruye el paquete")
    return {"problemas": problemas, "no_comprobadas": no_comprobadas}


def _senales(afirmacion: str, fuentes: list[dict]) -> list[dict]:
    textos = [FuenteTexto(f["descriptor"], f["texto"], f.get("sha256_documento"), f.get("articulo"),
                          bool(f.get("truncado"))) for f in fuentes]
    return [s.como_dict() for s in comparar(afirmacion, textos)]


def _coincide(senal: dict, esperado: dict) -> bool:
    return (senal["categoria"] == esperado["categoria"] and senal["severidad"] == esperado["severidad"]
            and senal["precision"] == esperado["precision"]
            and (esperado.get("codigo") is None or senal["codigo"] == esperado["codigo"]))


def evaluar_caso(caso: dict, fuentes: dict) -> dict:
    senales = _senales(caso["afirmacion"], [fuentes[c] for c in caso["fuentes"]])
    esperados = caso["esperado"]
    faltan = [e for e in esperados if not any(_coincide(s, e) for s in senales)]
    codigos_altos_esperados = {e.get("codigo") for e in esperados if e["precision"] == ALTA}
    altas_no_esperadas = sorted({s["codigo"] for s in senales
                                 if s["precision"] == ALTA and s["codigo"] not in codigos_altos_esperados})
    prohibidos = sorted({s["codigo"] for s in senales} & set(caso.get("codigos_prohibidos", [])))
    if caso["categoria"] == CONTROL:
        if caso.get("tolerancia", "sin_senales") == "sin_senales":
            control_ok = not senales
        else:
            control_ok = not any(s["precision"] == ALTA for s in senales)
        aprobado = control_ok and not prohibidos
    else:
        aprobado = not faltan and not prohibidos
    aprobado = aprobado and not altas_no_esperadas
    return {
        "id": caso["id"],
        "categoria": caso["categoria"],
        "limite_documentado": bool(caso.get("limite_documentado")),
        "passed": aprobado,
        "faltan": faltan,
        "altas_no_esperadas": altas_no_esperadas,
        "prohibidos": prohibidos,
        "senales": [{"codigo": s["codigo"], "precision": s["precision"], "severidad": s["severidad"],
                     "detalle": s["detalle"]} for s in senales],
        "adicionales": sorted({s["codigo"] for s in senales if not any(_coincide(s, e) for e in esperados)}),
        "esperado": esperados,
    }


def evaluar_candidato(candidato: dict) -> dict:
    fuente = candidato.get("fuente") or {}
    descriptor = " ".join(str(x) for x in (fuente.get("ordenamiento"), fuente.get("articulo")) if x) or "texto oficial"
    senales = _senales(candidato["texto_afirmacion"], [{"descriptor": descriptor, "texto": candidato["texto_oficial"]}])
    aprobado = candidato.get("review_status") == APROBADO
    verdad = candidato.get("verdad_responsable") if aprobado else candidato["propuesta_operador"]
    fiel = verdad == "fiel"
    if fiel:
        calificacion = "falso_positivo" if senales else "sin_senales_correcto"
    else:
        calificacion = "detectado" if senales else "no_detectado"
    return {
        "id": candidato.get("id"),
        "afirmacion": candidato.get("afirmacion_id"),
        "review_status": candidato.get("review_status"),
        "propuesta_operador": candidato["propuesta_operador"],
        "verdad_usada": verdad,
        "calificacion": calificacion,
        "senales": [s["codigo"] for s in senales],
        "altas": [s["codigo"] for s in senales if s["precision"] == ALTA],
        "cambios_propuestos": [c.get("categoria") for c in candidato.get("cambios_detectados") or []],
    }


def _metricas_candidatos(resultados: list[dict]) -> dict:
    cambia = [r for r in resultados if r["verdad_usada"] != "fiel"]
    fieles = [r for r in resultados if r["verdad_usada"] == "fiel"]
    detectados = sum(r["calificacion"] == "detectado" for r in cambia)
    return {
        "total": len(resultados),
        "con_cambio": len(cambia),
        "detectados": detectados,
        "detectados_alta": sum(bool(r["altas"]) for r in cambia),
        "no_detectados": len(cambia) - detectados,
        "recall": round(detectados / len(cambia), 4) if cambia else None,
        "fieles": len(fieles),
        "falsos_positivos": sum(r["calificacion"] == "falso_positivo" for r in fieles),
        "falsos_positivos_alta": sum(bool(r["altas"]) for r in fieles),
    }


def evaluar_gold_set(ruta: Path, paquete: str | None = None) -> dict:
    try:
        data = json.loads(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FidelidadGoldSetInvalido(f"no se pudo leer {ruta}: {exc}") from exc
    validar_dataset(data)
    fuentes = data["fuentes"]
    literalidad = verificar_literalidad(fuentes, paquete)
    resultados = [evaluar_caso(caso, fuentes) for caso in data["cases"]]
    puerta_casos = [r for r in resultados if not r["limite_documentado"]]

    recall: dict[str, dict] = {}
    for categoria in CATEGORIAS:
        propios = [r for r in puerta_casos if r["categoria"] == categoria]
        detectados = sum(r["passed"] for r in propios)
        recall[categoria] = {"casos": len(propios), "detectados": detectados,
                             "recall": round(detectados / len(propios), 4) if propios else None}
    recall_alta: dict[str, dict] = {}
    for codigo in sorted(CODIGOS_ALTA):
        propios = [r for r in puerta_casos if any(e.get("codigo") == codigo for e in r["esperado"])]
        detectados = sum(not any(e.get("codigo") == codigo for e in r["faltan"]) for r in propios)
        recall_alta[codigo] = {"casos": len(propios), "detectados": detectados,
                               "recall": round(detectados / len(propios), 4) if propios else None}
    controles = [r for r in resultados if r["categoria"] == CONTROL]
    sin_caso = [c for c, datos in recall.items() if not datos["casos"]]
    altas_sin_caso = [c for c, datos in recall_alta.items() if not datos["casos"]]
    bloqueantes_falsos = [r["id"] for r in resultados if r["altas_no_esperadas"]]
    limites = [r for r in resultados if r["limite_documentado"]]

    candidatos = (data.get("candidatos_piloto") or {}).get("candidatos") or []
    evaluados = [evaluar_candidato(c) for c in candidatos]
    pendientes = [r for r in evaluados if r["review_status"] == PENDIENTE]
    aprobados = [r for r in evaluados if r["review_status"] == APROBADO]
    aprobados_fallan = [r["id"] for r in aprobados if r["calificacion"] in ("falso_positivo", "no_detectado")]

    puerta = (
        all(r["passed"] for r in puerta_casos)
        and not bloqueantes_falsos
        and not sin_caso
        and not altas_sin_caso
        and bool(controles)
        and not literalidad["problemas"]
        and not aprobados_fallan
    )
    return {
        "gold_set": str(ruta),
        "version_motor": VERSION_MOTOR,
        "total_sinteticos": len(resultados),
        "passed": sum(r["passed"] for r in puerta_casos),
        "puerta_casos": len(puerta_casos),
        "recall_por_categoria": recall,
        "recall_precision_alta": recall_alta,
        "categorias_sin_caso": sin_caso,
        "codigos_alta_sin_caso": altas_sin_caso,
        "controles": len(controles),
        "controles_con_senales": [r["id"] for r in controles if r["senales"]],
        "bloqueantes_no_esperados": bloqueantes_falsos,
        "limites_documentados": [{"id": r["id"], "detectado": not r["faltan"], "senales": r["senales"]}
                                 for r in limites],
        "literalidad": literalidad,
        "candidatos_pendientes": {"metricas": _metricas_candidatos(pendientes), "resultados": pendientes},
        "candidatos_aprobados": {"metricas": _metricas_candidatos(aprobados), "resultados": aprobados,
                                 "fallan": aprobados_fallan},
        "gate_passed": puerta,
        "results": resultados,
    }


def _imprimir(reporte: dict) -> None:
    print(f"Gold Set de fidelidad (motor {reporte['version_motor']}): {reporte['passed']}/{reporte['puerta_casos']} "
          "casos sintéticos de la puerta correctos")
    for resultado in reporte["results"]:
        marca = "✅" if resultado["passed"] else "❌"
        if resultado["limite_documentado"]:
            marca = "📌"
        partes = []
        if resultado["categoria"] == CONTROL and resultado["senales"]:
            partes.append(f"señales en un control: {[(s['codigo'], s['precision']) for s in resultado['senales']]}")
        if resultado["faltan"]:
            partes.append(f"faltan {[(e['categoria'], e['precision']) for e in resultado['faltan']]}")
        if resultado["altas_no_esperadas"]:
            partes.append(f"señal ALTA no esperada {resultado['altas_no_esperadas']}")
        if resultado["prohibidos"]:
            partes.append(f"códigos prohibidos {resultado['prohibidos']}")
        if resultado["passed"] and resultado["adicionales"] and resultado["categoria"] != CONTROL:
            partes.append(f"señales adicionales: {resultado['adicionales']}")
        print(f"  {marca} {resultado['id']} [{resultado['categoria']}]" + (" — " + "; ".join(partes) if partes else ""))
    print("Recall por categoría (casos con defecto de la puerta):")
    for categoria, datos in reporte["recall_por_categoria"].items():
        valor = "sin caso" if datos["recall"] is None else f"{datos['recall']:.2f}"
        print(f"  {categoria}: {datos['detectados']}/{datos['casos']} · recall {valor}")
    print("Recall de las señales de precisión alta (bloquean en VERIFICADO):")
    for codigo, datos in reporte["recall_precision_alta"].items():
        valor = "sin caso" if datos["recall"] is None else f"{datos['recall']:.2f}"
        print(f"  {codigo}: {datos['detectados']}/{datos['casos']} · recall {valor}")
    print(f"Controles fieles: {reporte['controles']} · con señales: {len(reporte['controles_con_senales'])}"
          + (f" {reporte['controles_con_senales']}" if reporte["controles_con_senales"] else ""))
    print(f"Señales de precisión alta no esperadas (falsos bloqueantes): {len(reporte['bloqueantes_no_esperados'])}"
          + (f" {reporte['bloqueantes_no_esperados']}" if reporte["bloqueantes_no_esperados"] else ""))
    if reporte["limites_documentados"]:
        print(f"Límites documentados (no son puerta): {len(reporte['limites_documentados'])}")
    literalidad = reporte["literalidad"]
    for problema in literalidad["problemas"]:
        print(f"❌ Literalidad: {problema}")
    if literalidad["no_comprobadas"]:
        print(f"⚠️  {len(literalidad['no_comprobadas'])} fuente(s) del paquete del piloto sin comprobar contra el "
              "paquete (pasar --paquete con el paquete local); sha256_texto sí comprobado")
    metricas = reporte["candidatos_pendientes"]["metricas"]
    if metricas["total"]:
        print(f"Candidatos del piloto PEN-01 pendientes del responsable (NO son puerta): {metricas['total']}")
        print(f"  con cambio propuesto: {metricas['con_cambio']} · detectados {metricas['detectados']} "
              f"(con señal alta {metricas['detectados_alta']}) · no detectados {metricas['no_detectados']} · "
              f"fieles propuestos {metricas['fieles']} · falsos positivos {metricas['falsos_positivos']} "
              f"(alta {metricas['falsos_positivos_alta']})")
        for resultado in reporte["candidatos_pendientes"]["resultados"]:
            print(f"  · {resultado['id']} {resultado['afirmacion']} [{resultado['propuesta_operador']}] → "
                  f"{resultado['calificacion']} {resultado['senales'] or ''}")
    if reporte["candidatos_aprobados"]["metricas"]["total"]:
        print(f"Candidatos aprobados por el responsable (puerta): {reporte['candidatos_aprobados']['metricas']}")
    if reporte["categorias_sin_caso"]:
        print(f"❌ Categorías sin caso: {reporte['categorias_sin_caso']}")
    if reporte["codigos_alta_sin_caso"]:
        print(f"❌ Códigos de precisión alta sin caso: {reporte['codigos_alta_sin_caso']}")
    print("Puerta: " + ("🟢 superada" if reporte["gate_passed"] else "❌ no superada"))
    print("Nota: SIN_SENALES_DETECTADAS = sin señales detectadas por reglas deterministas; revisión del abogado "
          "obligatoria. El Gold Set mide reglas deterministas, no pertinencia jurídica.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluar el Gold Set del cotejo de fidelidad")
    parser.add_argument("--file", type=Path, default=DEFAULT_GOLD_SET)
    parser.add_argument("--paquete", help="Paquete local del piloto PEN-01 para comprobar sus textos (opcional)")
    parser.add_argument("--json", action="store_true", help="Emitir el reporte como JSON")
    args = parser.parse_args()
    try:
        reporte = evaluar_gold_set(args.file, args.paquete)
    except FidelidadGoldSetInvalido as exc:
        print(f"❌ Gold Set de fidelidad inválido: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(reporte, ensure_ascii=False, indent=2))
    else:
        _imprimir(reporte)
    return 0 if reporte["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
