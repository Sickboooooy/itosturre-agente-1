#!/usr/bin/env python3
"""plan_audit.py — auditor determinista de planes sobre ledger ``plan-ledger/1.0``.

Valida reglas observables (PL-001 … PL-014) sobre el ledger de afirmaciones,
evidencias, contradicciones y decisiones de un plan y, si se pasa el documento,
que cada artículo (también en la forma "CNPP 167" y con rangos "108-112"), registro
digital o clave de tesis mencionado esté cubierto por una afirmación. Con un paquete de
evidencia (``--paquete``) coteja además la identidad de cada evidencia citada
(PL-015 … PL-019) y la fidelidad de cada afirmación normativa al texto oficial (PL-020).
Sin red y sin LLM: no sustituye la verificación VVCA ni la decisión del abogado.

Uso:
  python plan_audit.py lint --ledger plan.ledger.json
  python plan_audit.py lint --ledger plan.ledger.json --documento plan.md \\
      --json hallazgos.json --md reporte.md [--paquete DIR]
  python plan_audit.py hash --ledger plan.ledger.json [--afirmacion A1]
  python plan_audit.py cotejar --ledger plan.ledger.json --paquete DIR [--json]
  python plan_audit.py fidelidad --ledger plan.ledger.json --paquete DIR [--json]
  python plan_audit.py evidencia agregar-tesis --paquete DIR --archivo innerText.txt \\
      --url https://sjf2.scjn.gob.mx/detalle/tesis/NNNNNNN --fecha-consulta AAAA-MM-DD \\
      [--registro NNNNNNN]
  python plan_audit.py evidencia agregar-ley --paquete DIR --pdf LEY.pdf \\
      --url https://www.diputados.gob.mx/LeyesBiblio/pdf/LEY.pdf --fecha-consulta AAAA-MM-DD \\
      [--paginas-json paginas.json --extractor … --version-extractor …]
  python plan_audit.py evidencia articulo --paquete DIR --articulo N \\
      (--sha256 HUELLA_DEL_PDF | --url https://www.diputados.gob.mx/LeyesBiblio/pdf/LEY.pdf)

Códigos de salida de ``lint``: 0 sin hallazgos BLOQUEANTES · 1 con BLOQUEANTES ·
2 entrada inválida (archivo ilegible, JSON roto, esquema inválido, paquete inexistente,
--json/--md que coinciden entre sí o con una entrada, o destino no escribible).
PL-018 (evidencia citada sin cotejar en una afirmación CONFORME) y PL-019 (artículo
remitido sin cotejar) son ADVERTENCIA: se muestran y nunca bloquean.

``cotejar`` (cotejo de identidad, C9): por cada par (afirmación, evidencia citada)
informa CONFORME, DISCREPANTE o SIN_EVIDENCIA (NO_COTEJADO para afirmaciones
INEXISTENTE). Orden: vínculo (sha256_documento + URL exacta) → registro utilizable →
integridad → documento y versión (registro digital; última reforma; fecha de consulta)
→ ubicación (artículo único en el cuerpo) → campos y extracto. El cotejo informa: no
aprueba ni cambia estados. Salida: 0 todo conforme y sin hallazgos (cada par
CONFORME sin decisión humana pendiente y paquete sin problemas; un par NO_COTEJADO
también cuenta como hallazgo) · 1 hallazgos · 2 entrada inválida.

El cotejo también exige que la afirmación mencione el documento de su evidencia
(registro, clave o artículo y ley en ``texto``/``referencias``) y, para leyes, que el
texto extraído provenga del PDF: se re-extrae con PyMuPDF si el registro declara ese
mismo extractor y versión; si no es posible, la evidencia queda SIN_EVIDENCIA.

Ubicaciones admitidas en una evidencia de ley: "Artículo N" (un único artículo) o
"Encabezado…" ("Encabezado de la página 1 de 414"), cuyo extracto debe ser igual al
título o a la línea "Última(s) Reforma(s) DOF dd-mm-aaaa" del encabezado. En una tesis,
el extracto puede venir de cualquier campo del render (rubro, texto, fuente,
precedentes, notas); una afirmación que no es criterio judicial (un hecho sobre el
portal) no necesita ``identificacion_criterio``.

``evidencia articulo`` imprime el texto exacto del artículo que usará el cotejo (zona,
páginas y advertencias de ubicación) y los datos del encabezado, para copiar extractos
literales: 0 artículo ubicado · 1 no ubicado sin ambigüedad o relación original–texto
no comprobable · 2 entrada inválida.

``evidencia agregar-tesis`` / ``agregar-ley`` registran un documento oficial ya obtenido
(innerText del SJF o PDF de LeyesBiblio; sin red) en el paquete, solo si el registro
pasa la comprobación de integridad, e imprimen el ``sha256_documento`` y un bloque de
evidencia listo para pegar en el ledger. La fecha de consulta la da siempre el
operador. ``agregar-tesis`` advierte si el archivo trae fines de línea CRLF (el
innerText de un navegador usa LF: el archivo se reescribió en modo texto) e imprime las
dos huellas: la del archivo, que es el ``sha256_documento``, y la del texto con LF.
``agregar-ley`` extrae el texto con PyMuPDF (``fitz``; origen "extraido") o lo
toma de ``--paginas-json`` (formato de ``tests/fixtures/evidencia/leyesbiblio_*.json``;
origen "declarado"): las páginas declaradas se rechazan si el extractor declarado está
disponible y no las reproduce desde ese PDF; y se rechaza un documento cuyo título de
encabezado no corresponde al archivo de la URL (CPEUM, CNPP, CPF, CFF, LAmp, LNEP). Un
paquete dentro del repositorio solo se acepta en una zona ignorada por la política de
datos (``auditorias/<asunto>/plan/``, D7); fuera del repositorio, en cualquier lugar.
Ninguna salida (``--json``/``--md``) puede quedar dentro del paquete.

``fidelidad`` (cotejo de fidelidad determinista, C10/PR-4): para cada afirmación
``texto_normativo``, ``inferencia`` o ``propuesta`` compara lo que afirma con el texto oficial
del artículo de sus pares CONFORME o, si no tiene, de sus ``referencias`` ("art. N SIGLA")
resueltas en el paquete con el mismo rigor que la identidad. Emite señales por categoría
(procedibilidad, plazos y cifras, inicio del cómputo, modales, negación, excepciones y
condiciones, cuantificadores, órgano), cada una con severidad (contradicción, omisión o
alineación ambigua), precisión (``alta`` o ``revisar``), huella y los tramos literales de la
afirmación y de la fuente. Resultado por afirmación: SENALES · SIN_SENALES_DETECTADAS ·
NO_COTEJABLE (con motivo). **Nunca emite CONFORME**: SIN_SENALES_DETECTADAS se rotula
siempre "sin señales detectadas por reglas deterministas; revisión del abogado
obligatoria". Salida: 0 sin señales · 1 con señales o si nada fue cotejable (todo
NO_COTEJABLE) · 2 entrada inválida.

Protocolo de uso de la fidelidad:
  1. Registrar la evidencia (``evidencia agregar-*``) y cotejar la identidad (``cotejar``).
  2. ``fidelidad --ledger L --paquete DIR``: leer cada señal con los dos tramos lado a lado;
     un NO_COTEJABLE dice por qué no hubo texto oficial (nunca acredita inexistencia); una
     fuente TRUNCADA es incompleta (no se señalan ausencias en ella).
  3. Corregir la afirmación según el texto oficial, o registrar una decisión humana en
     ``decisiones[]``: el comando imprime el bloque por afirmación, con ``"fidelidad":
     {"plan", "afirmacion", "contenido_sha256", "version_motor", "senales": [{"huella",
     "codigo", "fuente", "articulo", "sha256_documento"}], "resolucion"}``. El responsable
     llena ``id``, ``responsable`` (humano), ``estado`` y ``resolucion`` (si la afirmación es
     VERIFICADO, la resolución es obligatoria y la decisión debe estar APROBADA). Si cambia el
     plan, el texto o tipo de la afirmación, la fuente, el artículo, los tramos de la señal o
     la versión del motor, deja de valer: una decisión vieja o ajena no atiende una señal nueva.
  4. ``lint --paquete DIR``: PL-020 según la precisión (criterio por defecto, pendiente de
     confirmación del responsable): una señal ``alta`` sin atender (modo de procedibilidad
     distinto, plazo distinto para la misma condición, inicio del cómputo distinto) es
     BLOQUEANTE en una afirmación VERIFICADO y ALTA en otros estados; toda otra señal
     (``revisar``) es ADVERTENCIA "señal a revisar" en cualquier estado.
  5. SIN_SENALES_DETECTADAS no es conformidad: la afirmación sigue necesitando la lectura y,
     en su caso, la aprobación humana.

``hash`` imprime el ``contenido_sha256`` vigente de cada afirmación, que es el valor
que debe registrar la persona que la aprueba (``aprobacion.contenido_sha256``) o que
atiende sus señales de fidelidad (``decisiones[].fidelidad.contenido_sha256``).

En Windows anteponer el intérprete del venv: ``./venv/Scripts/python.exe``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.evidencia.esquema import fecha_consulta_valida, validar_registro  # noqa: E402
from itosturre.evidencia.huellas import sha256_bytes, sha256_texto  # noqa: E402
from itosturre.evidencia.leyesbiblio import SEPARADOR_PAGINAS, limpiar_documento  # noqa: E402
from itosturre.evidencia.leyesbiblio import registro_evidencia as registro_ley  # noqa: E402
from itosturre.evidencia.paquete import (  # noqa: E402
    ErrorPaquete,
    RegistroRechazado,
    cargar_paquete,
    guardar_evidencia,
)
from itosturre.evidencia.sjf import ErrorSJF, derivado_canonico, parsear_tesis  # noqa: E402
from itosturre.evidencia.sjf import registro_evidencia as registro_tesis  # noqa: E402
from itosturre.plan import (  # noqa: E402
    LedgerInvalido,
    cargar_ledger,
    contenido_sha256,
    cotejar_fidelidad,
    cotejar_ledger,
    esta_bloqueado,
    lint_ledger,
    reporte_markdown,
    resumen_severidades,
)
from itosturre.plan.fidelidad import AVISO as AVISO_FIDELIDAD  # noqa: E402
from itosturre.plan.fidelidad import ETIQUETA_SIN_SENALES, plantilla_decision  # noqa: E402
from itosturre.plan.fidelidad import RESULTADOS as RESULTADOS_FIDELIDAD  # noqa: E402
from itosturre.plan.fidelidad import SENALES as FIDELIDAD_SENALES  # noqa: E402
from itosturre.plan.fidelidad import VERSION_MOTOR as VERSION_MOTOR_FIDELIDAD  # noqa: E402
from itosturre.plan.identidad import (  # noqa: E402
    ARCHIVOS_LEYESBIBLIO,
    ESTADO_SOSTENIBLE,
    NO_COTEJADO_CAMPO,
    OBSERVACION,
    PASOS,
    RESULTADOS,
    Extractor,
    consultar_articulo,
    titulo_corresponde,
)

SALIDA_OK = 0
SALIDA_BLOQUEADO = 1
SALIDA_ENTRADA_INVALIDA = 2

POLITICA_DATOS = REPO / "config" / "data-policy.json"
ZONAS_PAQUETE_POR_OMISION = ("auditorias/",)
EXTRACTOR_FITZ = "PyMuPDF fitz.Page.get_text() (modo por omisión)"
FUERZA_POR_TIPO = {"Jurisprudencia": "[J] Obligatoria", "Aislada": "[TA] Orientadora"}
ASIGNAR = "[ASIGNAR]"


def _extractor_pymupdf() -> Extractor | None:
    """Extractor PyMuPDF (``fitz``, dependencia opcional) o ``None`` si no está instalado."""
    try:
        import fitz  # PyMuPDF: importación perezosa.
    except ImportError:
        return None

    def extraer(datos: bytes) -> list[str]:
        documento = fitz.open(stream=datos, filetype="pdf")
        try:
            return [pagina.get_text() for pagina in documento]
        finally:
            documento.close()

    version = f"PyMuPDF {getattr(fitz, 'VersionBind', '?')} / MuPDF {getattr(fitz, 'VersionFitz', '?')}"
    return Extractor(EXTRACTOR_FITZ, version, extraer)


def _extractores_disponibles() -> list[Extractor]:
    """Extractores con los que el cotejo puede acreditar la relación original–texto."""
    extractor = _extractor_pymupdf()
    return [extractor] if extractor is not None else []


def _utf8() -> None:
    # Consola Windows (cp1252) no codifica acentos ni símbolos: forzar UTF-8.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def _entrada_invalida(errores: list[str], titulo: str = "Entrada inválida") -> int:
    print(f"❌ {titulo}:", file=sys.stderr)
    for error in errores:
        print(f"  - {error}", file=sys.stderr)
    return SALIDA_ENTRADA_INVALIDA


def _misma_ruta(primera: str, segunda: str) -> bool:
    """Compara rutas resueltas (sin distinguir mayúsculas en Windows) o, si ambas
    existen, con ``os.path.samefile`` (detecta enlaces y alias)."""
    a, b = Path(primera), Path(segunda)
    try:
        if a.exists() and b.exists():
            return os.path.samefile(a, b)
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return os.path.normcase(os.path.abspath(primera)) == os.path.normcase(
            os.path.abspath(segunda)
        )


def _dentro_de(ruta: str, carpeta: str) -> bool:
    """``True`` si la ruta real de ``ruta`` es ``carpeta`` o queda dentro de ella (realpath)."""
    real = os.path.normcase(os.path.realpath(os.path.abspath(ruta)))
    base = os.path.normcase(os.path.realpath(os.path.abspath(carpeta)))
    try:
        return os.path.commonpath([real, base]) == base
    except ValueError:  # otra unidad en Windows
        return False


def _validar_destinos(args: argparse.Namespace) -> list[str]:
    """Errores de --json/--md: colisiones entre sí o con las entradas, y destinos no
    escribibles. Se valida todo antes de escribir el primer archivo."""
    entradas = [
        (nombre, ruta)
        for nombre, ruta in (("--ledger", args.ledger), ("--documento", args.documento))
        if ruta
    ]
    salidas = [
        (nombre, ruta) for nombre, ruta in (("--json", args.json), ("--md", args.md)) if ruta
    ]
    errores: list[str] = []
    if len(salidas) == 2 and _misma_ruta(salidas[0][1], salidas[1][1]):
        errores.append("--json y --md apuntan al mismo archivo")
    paquete = getattr(args, "paquete", None)
    for salida, ruta_salida in salidas:
        for entrada, ruta_entrada in entradas:
            if _misma_ruta(ruta_salida, ruta_entrada):
                errores.append(f"{salida} coincide con {entrada}: sobrescribiría la entrada")
        if paquete and _dentro_de(ruta_salida, paquete):
            errores.append(f"{salida} apunta dentro del paquete de evidencia {paquete}: no se escribe ahí")
        destino = Path(ruta_salida)
        if destino.is_dir():
            errores.append(f"{salida} apunta a un directorio: {ruta_salida}")
        elif not destino.parent.is_dir():
            errores.append(f"{salida}: no existe el directorio {destino.parent}")
    return errores


def cmd_lint(args: argparse.Namespace) -> int:
    errores = _validar_destinos(args)
    if errores:
        return _entrada_invalida(errores)
    try:
        ledger = cargar_ledger(args.ledger)
    except LedgerInvalido as exc:
        return _entrada_invalida(exc.errores)

    documento = None
    if args.documento:
        try:
            documento = Path(args.documento).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            return _entrada_invalida([f"no se pudo leer el documento {args.documento}: {exc}"])

    cotejo = None
    fidelidad = None
    if args.paquete:
        try:
            paquete = cargar_paquete(args.paquete)
            extractores = _extractores_disponibles()
            cache: dict = {}  # identidad y fidelidad comparten la re-extracción de cada PDF
            cotejo = cotejar_ledger(ledger, paquete, extractores=extractores, cache=cache)
            fidelidad = cotejar_fidelidad(ledger, paquete, cotejo=cotejo, extractores=extractores, cache=cache)
        except (ErrorPaquete, OSError) as exc:
            return _entrada_invalida([f"paquete de evidencia: {exc}"])

    hallazgos = lint_ledger(ledger, documento=documento, cotejo=cotejo, fidelidad=fidelidad)
    bloqueado = esta_bloqueado(hallazgos)
    severidades = resumen_severidades(hallazgos)

    escrituras: list[tuple[str, str]] = []
    if args.json:
        salida = {
            "schema_version": ledger["schema_version"],
            "plan": ledger["plan"],
            "documento": args.documento,
            "bloqueado": bloqueado,
            "resumen": severidades,
            "hallazgos": hallazgos,
        }
        if cotejo is not None:
            salida["paquete"] = args.paquete
            salida["cotejo"] = cotejo.como_dict()
        if fidelidad is not None:
            salida["fidelidad"] = fidelidad.como_dict()
        escrituras.append((args.json, json.dumps(salida, ensure_ascii=False, indent=2) + "\n"))
    if args.md:
        escrituras.append((args.md, reporte_markdown(ledger, hallazgos, cotejo, fidelidad)))
    for destino, contenido in escrituras:
        try:
            Path(destino).write_text(contenido, encoding="utf-8")
        except OSError as exc:
            return _entrada_invalida([f"no se pudo escribir {destino}: {exc}"], "Error de escritura")

    conteo = " · ".join(f"{severidad}={n}" for severidad, n in severidades.items())
    print(f"Auditoría de plan {ledger['plan']['id']}: {len(hallazgos)} hallazgo(s) · {conteo}")
    for hallazgo in hallazgos:
        print(
            f"  [{hallazgo['severidad']}] {hallazgo['regla']} {hallazgo['objetivo']}: "
            f"{hallazgo['mensaje']}"
        )
    if documento is None:
        print("  (PL-014 de cobertura no evaluada: no se pasó --documento)")
    if cotejo is not None:
        print(f"  Cotejo de identidad: {_resumen_cotejo(cotejo)}")
    if fidelidad is not None:
        print(f"  Cotejo de fidelidad: {_resumen_fidelidad(fidelidad)}")
    print(
        "Resultado: BLOQUEADO"
        if bloqueado
        else "Resultado: sin hallazgos bloqueantes (no equivale a aprobación jurídica)"
    )
    return SALIDA_BLOQUEADO if bloqueado else SALIDA_OK


def cmd_hash(args: argparse.Namespace) -> int:
    try:
        ledger = cargar_ledger(args.ledger)
    except LedgerInvalido as exc:
        return _entrada_invalida(exc.errores)
    afirmaciones = ledger["afirmaciones"]
    if args.afirmacion:
        afirmaciones = [a for a in afirmaciones if a["id"] == args.afirmacion]
        if not afirmaciones:
            return _entrada_invalida([f"no existe la afirmación {args.afirmacion}"])
    for afirmacion in afirmaciones:
        print(f"{afirmacion['id']}\t{contenido_sha256(afirmacion)}")
    return SALIDA_OK


# ── Cotejo de identidad ──────────────────────────────────────────────────────


def _resumen_cotejo(cotejo) -> str:
    resumen = cotejo.resumen()
    partes = [f"{resultado}={resumen[resultado]}" for resultado in RESULTADOS]
    partes.append(f"requieren decisión humana={resumen['requieren_decision_humana']}")
    return f"{len(cotejo.pares)} par(es) · " + " · ".join(partes)


def _describir_fuente(par) -> str:
    partes = [par.documento_fuente or "sin registro"]
    if par.version_fuente:
        partes.append(f"última reforma DOF {par.version_fuente}")
    if par.fecha_consulta_fuente:
        partes.append(f"consulta {par.fecha_consulta_fuente}")
    return " · ".join(partes)


def cmd_cotejar(args: argparse.Namespace) -> int:
    try:
        ledger = cargar_ledger(args.ledger)
    except LedgerInvalido as exc:
        return _entrada_invalida(exc.errores)
    try:
        cotejo = cotejar_ledger(ledger, cargar_paquete(args.paquete), extractores=_extractores_disponibles())
    except (ErrorPaquete, OSError) as exc:
        return _entrada_invalida([f"paquete de evidencia: {exc}"])

    if args.json:
        salida = {
            "schema_version": ledger["schema_version"],
            "plan": ledger["plan"],
            "paquete": args.paquete,
            **cotejo.como_dict(),
        }
        print(json.dumps(salida, ensure_ascii=False, indent=2))
        return SALIDA_OK if cotejo.todo_conforme else SALIDA_BLOQUEADO

    print(f"Cotejo de identidad · plan {ledger['plan']['id']} · paquete {args.paquete}")
    print(f"  huella del ledger {cotejo.huella_ledger} · huella del paquete {cotejo.huella_paquete}")
    for problema in cotejo.problemas_paquete:
        print(f"  ⚠ problema del paquete: {problema}")
    for par in cotejo.pares:
        etiqueta = par.resultado
        if par.requiere_decision_humana:
            codigos = ", ".join(sorted({str(a.get("codigo", "?")) for a in par.advertencias_fuente}))
            etiqueta += f" · requiere decisión humana: {codigos}"
        paso = f" (paso {par.paso}, {PASOS[par.paso]})" if par.paso in PASOS else ""
        print(f"  [{etiqueta}] {par.afirmacion} ← {par.evidencia}{paso} · {_describir_fuente(par)}")
        for motivo in par.motivos:
            print(f"      - {motivo.resumen()}")
        for nota in par.notas:
            if nota.clase in (NO_COTEJADO_CAMPO, OBSERVACION):
                prefijo = "no cotejado" if nota.clase == NO_COTEJADO_CAMPO else "observación"
                print(f"      · {prefijo} — {nota.resumen()}")
        for aviso in par.advertencias_fuente:
            print(f"      ! advertencia de la fuente [{aviso.get('codigo')}]: {aviso.get('mensaje')}")
    if cotejo.afirmaciones:
        print("Por afirmación:")
        for agregado in cotejo.afirmaciones:
            sostiene = ESTADO_SOSTENIBLE[agregado.resultado]
            extra = f" · sostiene a lo sumo {sostiene}" if sostiene else ""
            if agregado.requiere_decision_humana:
                extra += " · requiere decisión humana"
            if not agregado.pares:
                extra += " · sin evidencias citadas"
            if agregado.es_hallazgo:
                extra += " · HALLAZGO"
            print(f"  {agregado.afirmacion} ({agregado.estado_declarado or 'estado inválido'}): "
                  f"{agregado.resultado}{extra}")
            for motivo in agregado.motivos:
                print(f"      - {motivo.resumen()}")
            for nota in agregado.notas:
                print(f"      · {nota.resumen()}")
    print(f"Resumen: {_resumen_cotejo(cotejo)}")
    print(
        "Resultado: todo conforme (el cotejo informa; no aprueba ni cambia estados)"
        if cotejo.todo_conforme
        else "Resultado: con hallazgos (el cotejo informa; no aprueba ni cambia estados)"
    )
    return SALIDA_OK if cotejo.todo_conforme else SALIDA_BLOQUEADO


# ── Cotejo de fidelidad (PR-4) ──────────────────────────────────────────────


def _resumen_fidelidad(fidelidad) -> str:
    resumen = fidelidad.resumen()
    partes = [f"{resultado}={resumen[resultado]}" for resultado in RESULTADOS_FIDELIDAD]
    partes.append(f"señales alta={resumen['alta']}")
    partes.append(f"a revisar={resumen['revisar']}")
    partes.append(f"fuera de alcance={resumen['fuera_de_alcance']}")
    texto = f"{len(fidelidad.afirmaciones)} afirmación(es) · " + " · ".join(partes)
    if fidelidad.nada_cotejable:
        texto += " · NADA FUE COTEJABLE"
    return texto


def _plano(texto: str) -> str:
    return " ".join(str(texto or "").split())


def cmd_fidelidad(args: argparse.Namespace) -> int:
    try:
        ledger = cargar_ledger(args.ledger)
    except LedgerInvalido as exc:
        return _entrada_invalida(exc.errores)
    try:
        paquete = cargar_paquete(args.paquete)
        extractores = _extractores_disponibles()
        cache: dict = {}
        cotejo = cotejar_ledger(ledger, paquete, extractores=extractores, cache=cache)
        fidelidad = cotejar_fidelidad(ledger, paquete, cotejo=cotejo, extractores=extractores, cache=cache)
    except (ErrorPaquete, OSError) as exc:
        return _entrada_invalida([f"paquete de evidencia: {exc}"])
    con_senales = any(r.resultado == FIDELIDAD_SENALES for r in fidelidad.afirmaciones)
    # Nada cotejable (todo NO_COTEJABLE o nada en alcance) no es "sin señales": sale ≠ 0.
    codigo_salida = SALIDA_BLOQUEADO if con_senales or fidelidad.nada_cotejable else SALIDA_OK

    if args.json:
        salida = {
            "schema_version": ledger["schema_version"],
            "plan": ledger["plan"],
            "paquete": args.paquete,
            **fidelidad.como_dict(),
        }
        print(json.dumps(salida, ensure_ascii=False, indent=2))
        return codigo_salida

    plan = ledger["plan"]["id"]
    print(f"Cotejo de fidelidad · plan {plan} · paquete {args.paquete} · motor {VERSION_MOTOR_FIDELIDAD}")
    print(f"  huella del ledger {fidelidad.huella_ledger} · huella del paquete {fidelidad.huella_paquete}")
    for resultado in fidelidad.afirmaciones:
        fuentes = "; ".join(
            f"{f.descriptor} ({'evidencias ' + ', '.join(f.evidencias) if f.origen == 'par_conforme' else 'referencia «' + str(f.referencia) + '»'})"
            + (" · TRUNCADA" if f.truncado else "")
            for f in resultado.fuentes
        ) or "—"
        print(f"  [{resultado.etiqueta}] {resultado.afirmacion} ({resultado.tipo} · "
              f"{resultado.estado_declarado or 'estado inválido'}) · fuentes: {fuentes}")
        for motivo in resultado.motivos:
            print(f"      · motivo: {motivo}")
        for nota in resultado.notas:
            print(f"      · nota: {nota}")
        for senal in resultado.senales:
            nivel = "ALTA PRECISIÓN" if senal.precision == "alta" else "señal a revisar"
            print(f"      - [{nivel} · {senal.severidad}] {senal.codigo} — {senal.detalle}")
            print(f"          afirmación: «{_plano(senal.tramo_afirmacion)}»")
            documentos = ", ".join(sha[:12] + "…" for sha in senal.sha256_documentos) or "—"
            print(f"          fuente ({senal.fuente} · sha256 {documentos}): "
                  f"«{_plano(senal.tramo_fuente) or 'la cifra no aparece en el texto oficial'}»")
            print(f"          huella de la señal: {senal.huella}")
        if resultado.senales:
            print("      bloque de decisión para decisiones[] (los campos [ASIGNAR] son del responsable):")
            bloque = json.dumps(plantilla_decision(plan, resultado), ensure_ascii=False, indent=2)
            print("\n".join("        " + linea for linea in bloque.splitlines()))
    if fidelidad.fuera_de_alcance:
        print(f"  Fuera de alcance (criterio judicial, hecho aportado): {', '.join(fidelidad.fuera_de_alcance)}")
    print(f"Resumen: {_resumen_fidelidad(fidelidad)}")
    print(f"Aviso: {AVISO_FIDELIDAD}")
    if fidelidad.nada_cotejable:
        print("Resultado: nada fue cotejable (ninguna afirmación tuvo texto oficial que comparar; no equivale a "
              "fidelidad)")
    elif con_senales:
        print("Resultado: con señales (el cotejo informa; no aprueba ni cambia estados)")
    else:
        print(f"Resultado: {ETIQUETA_SIN_SENALES} (no equivale a conformidad ni a validación)")
    return codigo_salida


# ── Registro de evidencia en un paquete ─────────────────────────────────────


def _zonas_ignoradas() -> tuple[str, ...]:
    """Prefijos que la política de datos prohíbe versionar (y ``.gitignore`` ignora)."""
    try:
        politica = json.loads(POLITICA_DATOS.read_text(encoding="utf-8"))
        zonas = tuple(
            zona
            for zona in politica.get("forbidden_tracked_prefixes", [])
            if isinstance(zona, str) and zona.endswith("/")
        )
    except (OSError, ValueError, AttributeError):
        zonas = ()
    return zonas or ZONAS_PAQUETE_POR_OMISION


def motivo_ruta_paquete(ruta: str | Path) -> str | None:
    """Por qué no se debe escribir un paquete en ``ruta`` (``None`` si se puede).

    Fuera del repositorio: siempre se puede. Dentro: solo en una zona que la política
    de datos prohíbe versionar (``forbidden_tracked_prefixes``: ``auditorias/``…), para
    que la evidencia de un asunto nunca quede como candidata a commit (D7).
    """
    destino = os.path.normcase(os.path.realpath(os.path.abspath(ruta)))
    repo = os.path.normcase(os.path.realpath(REPO))
    try:
        dentro = os.path.commonpath([destino, repo]) == repo
    except ValueError:  # otra unidad en Windows: fuera del repositorio
        dentro = False
    if not dentro:
        return None
    relativa = os.path.relpath(destino, repo).replace(os.sep, "/") + "/"
    zonas = _zonas_ignoradas()
    # normcase en Windows pasa a minúsculas y cambia "/" por "\\": se deshace el cambio.
    prefijos = [os.path.normcase(zona).replace(os.sep, "/") for zona in zonas]
    if relativa != "./" and any(relativa.startswith(prefijo) for prefijo in prefijos):
        return None
    return (
        f"el paquete {ruta} quedaría dentro del repositorio fuera de una zona ignorada "
        f"({', '.join(zonas)}): usar auditorias/<asunto>/plan/ (D7) o una ruta fuera del repositorio"
    )


def _fecha_ledger(fecha_consulta: str) -> str:
    return fecha_consulta[:10]


def _imprimir_registro(
    registro: dict, huella: str, bloques: list[tuple[str, dict]], avisos: tuple[str, ...] = ()
) -> None:
    print(f"Registro guardado: registros/{huella}.json ({registro['tipo']})")
    print(f"sha256_documento: {registro['original']['sha256']}")
    for aviso in avisos:
        print(f"⚠ {aviso}")
    for aviso in registro.get("advertencias") or []:
        print(f"⚠ advertencia de la fuente [{aviso.get('codigo')}]: {aviso.get('mensaje')}")
    for titulo, bloque in bloques:
        print(f"\n{titulo}:")
        print(json.dumps(bloque, ensure_ascii=False, indent=2))
    print(
        "\nLos campos [ASIGNAR] son del operador. El cotejo de identidad comprueba lo que se "
        "pegue; no aprueba nada."
    )


def _guardar(paquete: str, registro: dict, **artefactos) -> str | int:
    problemas = validar_registro(registro)
    if problemas:
        return _entrada_invalida(problemas, "Registro de evidencia inválido")
    try:
        return guardar_evidencia(paquete, registro, **artefactos)
    except RegistroRechazado as exc:
        return _entrada_invalida([str(exc)], "Registro rechazado")
    except (ErrorPaquete, OSError) as exc:
        return _entrada_invalida([f"no se pudo escribir en el paquete: {exc}"], "Error de escritura")


def _comprobar_comunes(args: argparse.Namespace) -> list[str]:
    errores = []
    motivo = motivo_ruta_paquete(args.paquete)
    if motivo:
        errores.append(motivo)
    if not fecha_consulta_valida(args.fecha_consulta):
        errores.append(
            f"--fecha-consulta {args.fecha_consulta!r}: se espera AAAA-MM-DD o fecha-hora ISO con "
            "zona explícita (la da el operador; nunca se toma del reloj)"
        )
    return errores


def aviso_fines_de_linea(original: bytes) -> str | None:
    """Aviso si el innerText trae CRLF (PEN-01 D9): un navegador entrega LF, así que el archivo se
    reescribió (p. ej. en modo texto en Windows) y su huella no es la del texto capturado.

    Se imprimen las dos huellas: la del archivo (``sha256_documento``, la que usa el
    paquete) y la del mismo texto con LF (la que se habría calculado al capturar)."""
    crlf, lf = b"\r\n", b"\n"
    if crlf not in original:
        return None
    # Python 3.11: sin barras invertidas dentro de las expresiones de un f-string.
    huella_lf = sha256_bytes(original.replace(crlf, lf))
    return (
        "el archivo trae fines de línea CRLF; el innerText de un navegador usa LF, así que se "
        "reescribió después de capturarse. Huella del archivo (sha256_documento, la que usa el "
        f"paquete): {sha256_bytes(original)} · huella del mismo texto con LF (la del innerText "
        f"capturado): {huella_lf}. Si el plan cita la huella de la captura, no coincidirá con la "
        "del archivo preservado: preservar el archivo tal como se capturó (escritura binaria o "
        "newline=\"\")."
    )


def cmd_agregar_tesis(args: argparse.Namespace) -> int:
    errores = _comprobar_comunes(args)
    if args.registro is not None and not args.registro.isdigit():
        errores.append(f"--registro {args.registro!r}: debe ser el registro digital (solo dígitos)")
    if errores:
        return _entrada_invalida(errores)
    try:
        original = Path(args.archivo).read_bytes()
    except OSError as exc:
        return _entrada_invalida([f"no se pudo leer {args.archivo}: {exc}"])
    try:
        texto = original.decode("utf-8")
        registro = registro_tesis(
            original,
            url=args.url,
            fecha_consulta=args.fecha_consulta,
            registro_esperado=args.registro,
        )
        tesis = parsear_tesis(texto, registro_esperado=registro["metadatos"]["registro"])
    except UnicodeDecodeError:
        return _entrada_invalida([f"{args.archivo} no es texto UTF-8 (innerText del SJF)"])
    except ErrorSJF as exc:
        return _entrada_invalida([f"no se puede identificar la tesis: {exc}"])
    huella = _guardar(args.paquete, registro, original=original, derivado=derivado_canonico(tesis))
    if isinstance(huella, int):
        return huella

    metadatos = registro["metadatos"]
    evidencia = {
        "id": ASIGNAR,
        "naturaleza": "portal_oficial",
        "url": args.url,
        "ubicacion": f"Registro digital {metadatos['registro']}",
        "extracto": metadatos["rubro"] or ASIGNAR,
        "fecha_consulta": _fecha_ledger(args.fecha_consulta),
        "sha256_documento": registro["original"]["sha256"],
        "consulta": None,
        "resultados": None,
    }
    identificacion = {
        "rubro": metadatos["rubro"] or ASIGNAR,
        "clave": metadatos["clave"] or ASIGNAR,
        "organo": ASIGNAR,
        "epoca": metadatos["epoca"] or ASIGNAR,
        "registro": metadatos["registro"],
        "integracion": ASIGNAR,
        "publicacion": metadatos["fecha_publicacion"] or ASIGNAR,
        "obligatoriedad": metadatos["fecha_obligatoriedad"] or ASIGNAR,
        "fuerza_vinculante": FUERZA_POR_TIPO.get(metadatos["tipo_tesis"] or "", ASIGNAR),
        "alcance": ASIGNAR,
    }
    aviso = aviso_fines_de_linea(original)
    _imprimir_registro(
        registro,
        huella,
        [
            ("Bloque de evidencia para el ledger (evidencias[])", evidencia),
            (
                "Datos de la fuente para identificacion_criterio de la afirmación "
                f"(instancia según la fuente: {metadatos['instancia']!r})",
                identificacion,
            ),
        ],
        (aviso,) if aviso else (),
    )
    return SALIDA_OK


def _paginas_de_json(ruta: str, archivo: str) -> tuple[list[str], list[int], int | None, dict]:
    """Páginas ya extraídas (formato de ``tests/fixtures/evidencia/leyesbiblio_*.json``)."""
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"no se pudo leer --paginas-json {ruta}: {exc}") from exc
    if not isinstance(datos, dict) or not isinstance(datos.get("paginas"), list) or not datos["paginas"]:
        raise ValueError("--paginas-json: se espera un objeto con 'paginas' (lista no vacía)")
    if datos.get("archivo") not in (None, archivo):
        raise ValueError(f"--paginas-json es de {datos['archivo']!r} y la URL apunta a {archivo!r}")
    textos, numeros = [], []
    for indice, pagina in enumerate(datos["paginas"]):
        numero = pagina.get("numero") if isinstance(pagina, dict) else None
        texto = pagina.get("texto") if isinstance(pagina, dict) else None
        if isinstance(numero, bool) or not isinstance(numero, int) or numero < 1 or not isinstance(texto, str):
            raise ValueError(f"--paginas-json: paginas[{indice}] necesita 'numero' (entero ≥ 1) y 'texto'")
        if "sha256_texto" in pagina and pagina["sha256_texto"] != sha256_texto(texto):
            raise ValueError(f"--paginas-json: la huella de la página {numero} no coincide con su texto")
        textos.append(texto)
        numeros.append(numero)
    total = datos.get("total_paginas_pdf")
    if total is not None and (isinstance(total, bool) or not isinstance(total, int) or total < 1):
        raise ValueError("--paginas-json: 'total_paginas_pdf' debe ser entero positivo o null")
    return textos, numeros, total, datos


def _paginas_de_pdf(pdf: bytes) -> tuple[list[str], list[int], int, Extractor]:
    extractores = _extractores_disponibles()
    if not extractores:
        raise ValueError(
            "PyMuPDF (fitz) no está instalado: instálelo en el venv o pase --paginas-json con "
            "las páginas ya extraídas"
        )
    extractor = extractores[0]
    try:
        textos = list(extractor.extraer(pdf))
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de lectura es entrada inválida
        raise ValueError(f"no se pudo extraer el texto del PDF: {exc}") from exc
    return textos, list(range(1, len(textos) + 1)), len(textos), extractor


def _verificar_paginas_declaradas(
    pdf: bytes, textos: list[str], numeros: list[int], extractor: str, version: str
) -> tuple[bool | None, str]:
    """¿Las páginas declaradas salen de ese PDF? ``True``/``False``, o ``None`` si no se
    puede comprobar (no hay un extractor disponible con el mismo nombre y versión)."""
    candidatos = [e for e in _extractores_disponibles() if e.nombre == extractor and e.version == version]
    if not candidatos:
        return None, (
            f"no hay un extractor {extractor!r} versión {version!r} disponible para comprobar que las "
            "páginas declaradas provienen del PDF"
        )
    try:
        reextraidas = list(candidatos[0].extraer(pdf))
    except Exception as exc:  # noqa: BLE001
        return False, f"el PDF no se pudo re-extraer con {extractor} {version}: {exc}"
    if any(n > len(reextraidas) for n in numeros):
        return False, f"el PDF tiene {len(reextraidas)} página(s) y se declara la {max(numeros)}"
    distintas = [n for n, texto in zip(numeros, textos) if reextraidas[n - 1] != texto]
    if distintas:
        return False, f"las páginas declaradas {distintas} no son las que se extraen de ese PDF"
    return True, "páginas declaradas comprobadas por re-extracción del PDF"


def cmd_agregar_ley(args: argparse.Namespace) -> int:
    errores = _comprobar_comunes(args)
    archivo = unquote(PurePosixPath(urlsplit(args.url).path).name) if isinstance(args.url, str) else ""
    if not archivo:
        errores.append(f"--url {args.url!r}: no termina en el nombre del PDF de LeyesBiblio")
    if errores:
        return _entrada_invalida(errores)
    try:
        pdf = Path(args.pdf).read_bytes()
    except OSError as exc:
        return _entrada_invalida([f"no se pudo leer {args.pdf}: {exc}"])
    avisos: list[str] = []
    try:
        if args.paginas_json:
            textos, numeros, total, datos = _paginas_de_json(args.paginas_json, archivo)
            extractor = args.extractor or datos.get("extractor")
            version = args.version_extractor or datos.get("version_extractor")
            origen = "declarado"
        else:
            if args.extractor or args.version_extractor:
                raise ValueError("--extractor y --version-extractor solo se aceptan con --paginas-json")
            textos, numeros, total, herramienta = _paginas_de_pdf(pdf)
            extractor, version = herramienta.nombre, herramienta.version
            origen = "extraido"
    except ValueError as exc:
        return _entrada_invalida([str(exc)])
    faltan = [
        nombre
        for nombre, valor in (("--extractor", extractor), ("--version-extractor", version))
        if not (isinstance(valor, str) and valor.strip())
    ]
    if faltan:
        return _entrada_invalida(
            [f"con --paginas-json hay que declarar {', '.join(faltan)} (procedencia del texto)"]
        )
    if origen == "declarado":
        comprobado, mensaje = _verificar_paginas_declaradas(pdf, textos, numeros, extractor, version)
        if comprobado is False:
            return _entrada_invalida([mensaje], "Las páginas declaradas no provienen de ese PDF")
        if comprobado is None:
            avisos.append(
                f"{mensaje}: el registro queda como texto declarado y el cotejo dará SIN_EVIDENCIA "
                "(relación original–texto no comprobable) hasta que pueda re-extraerse"
            )
    con_salto = [n for n, texto in zip(numeros, textos) if SEPARADOR_PAGINAS in texto]
    if con_salto:
        return _entrada_invalida(
            [f"las páginas {con_salto} contienen un salto de página (\\f), que la convención de huellas reserva"]
        )
    try:
        documento = limpiar_documento(textos, numeros=numeros, total_paginas=total)
    except ValueError as exc:
        return _entrada_invalida([f"páginas inválidas: {exc}"])
    sigla = ARCHIVOS_LEYESBIBLIO.get(archivo)
    if sigla is not None and documento.titulo and not titulo_corresponde(documento.titulo, sigla):
        return _entrada_invalida(
            [f"el título del encabezado {documento.titulo!r} no corresponde al archivo {archivo} ({sigla}) de la URL"],
            "El documento no es el de la URL",
        )
    if sigla is not None and not documento.titulo:
        avisos.append(f"el documento no fija un título en su encabezado: no se pudo contrastar con {archivo}")
    if sigla is None:
        avisos.append(
            f"{archivo} no tiene correspondencia registrada con un ordenamiento: las menciones de "
            "artículo con ley de las afirmaciones quedarán SIN_EVIDENCIA"
        )
    registro = registro_ley(
        documento,
        archivo=archivo,
        url=args.url,
        fecha_consulta=args.fecha_consulta,
        original_sha256=sha256_bytes(pdf),
        original_bytes=len(pdf),
        extractor=extractor,
        version_extractor=version,
    )
    # Cómo se obtuvo el texto: "extraido" (por esta herramienta) o "declarado" (--paginas-json).
    registro["metadatos"]["origen_texto"] = origen
    huella = _guardar(
        args.paquete,
        registro,
        original=pdf,
        derivado=documento.texto,
        texto_extraido=documento.texto_extraido,
    )
    if isinstance(huella, int):
        return huella
    evidencia = {
        "id": ASIGNAR,
        "naturaleza": "compilado_oficial",
        "url": args.url,
        "ubicacion": "[ASIGNAR: Artículo N]",
        "extracto": "[ASIGNAR: transcripción literal del artículo]",
        "fecha_consulta": _fecha_ledger(args.fecha_consulta),
        "sha256_documento": registro["original"]["sha256"],
        "ultima_reforma_dof": registro["metadatos"]["ultima_reforma_dof"],
        "consulta": None,
        "resultados": None,
    }
    _imprimir_registro(
        registro,
        huella,
        [(f"Bloque de evidencia para el ledger (evidencias[]; páginas {numeros[0]}–{numeros[-1]}"
          f" de {total or '?'})", evidencia)],
    )
    if registro["metadatos"]["ultima_reforma_dof"] is None:
        print("⚠ La fuente no fija una única 'Última Reforma DOF': el cotejo no podrá fijar la versión.")
    print(f"Origen del texto: {origen} ({extractor} · {version})")
    for aviso in avisos:
        print(f"⚠ {aviso}")
    return SALIDA_OK


def cmd_articulo(args: argparse.Namespace) -> int:
    """Texto exacto del artículo que usará el cotejo (fricción n.º 1 del piloto PEN-01)."""
    if not args.sha256 and not args.url:
        return _entrada_invalida(["hay que indicar --sha256 (huella del PDF registrado) o --url"])
    try:
        paquete = cargar_paquete(args.paquete)
    except (ErrorPaquete, OSError) as exc:
        return _entrada_invalida([f"paquete de evidencia: {exc}"])
    try:
        consulta = consultar_articulo(
            paquete, articulo=args.articulo, sha256=args.sha256, url=args.url,
            extractores=_extractores_disponibles(),
        )
    except ValueError as exc:
        return _entrada_invalida([str(exc)])

    print(f"Documento: {consulta.archivo or '—'} · {consulta.url}")
    print(f"sha256_documento: {consulta.sha256_documento}")
    if consulta.motivos:
        print("No se puede mostrar el texto que usaría el cotejo (pasos a–c):")
        for motivo in consulta.motivos:
            print(f"  - {motivo.resumen()}")
        return SALIDA_BLOQUEADO
    ordenamiento = consulta.ordenamiento or f"sin correspondencia ({consulta.motivo_ordenamiento})"
    print(f"Título: {consulta.titulo or '—'} · ordenamiento: {ordenamiento}")
    print(f"Última reforma DOF (registro): {consulta.ultima_reforma_dof or '—'} · "
          f"línea del encabezado: «{consulta.linea_ultima_reforma or '—'}» · "
          f"total de páginas: {consulta.total_paginas or '—'}")
    ubicacion = consulta.ubicacion
    for aviso in ubicacion.advertencias:
        print(f"  ! ubicación [{aviso.get('codigo')}]: {aviso.get('mensaje')}")
    if consulta.tramo is None:
        print(f"El artículo {consulta.articulo!r} no se ubica sin ambigüedad en el cuerpo: el cotejo "
              "daría SIN_EVIDENCIA (esto no acredita que no exista).")
        for coincidencia in (*ubicacion.coincidencias, *ubicacion.variantes_cercanas):
            print(f"  · p. {coincidencia.pagina} · zona {coincidencia.zona} · «{coincidencia.linea.strip()}»")
        return SALIDA_BLOQUEADO
    tramo = consulta.tramo
    unica = ubicacion.unica
    paginas = (f"página {tramo.pagina_inicial}" if tramo.pagina_inicial == tramo.pagina_final
               else f"páginas {tramo.pagina_inicial}–{tramo.pagina_final}")
    print(f"Artículo {unica.identificador} · zona {unica.zona} · {paginas} · ubicación para el ledger: "
          f"\"Artículo {unica.identificador}\"")
    if tramo.truncado:
        print("  ! el texto puede continuar en páginas no incluidas en el registro (truncado)")
    print("──── texto que usa el cotejo (el extracto debe ser subcadena literal; se compara sin "
          "acentos, mayúsculas ni espacios repetidos) ────")
    print(tramo.texto)
    print("──── fin del artículo ────")
    return SALIDA_OK


def main(argv: list[str] | None = None) -> int:
    _utf8()
    parser = argparse.ArgumentParser(
        description="Auditor determinista de planes sobre ledger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    lint = sub.add_parser("lint", help="Aplicar las reglas PL-001 … PL-014 (y PL-015 … PL-020 con --paquete)")
    lint.add_argument("--ledger", required=True, help="Ledger JSON plan-ledger/1.0")
    lint.add_argument("--documento", help="Documento del plan (.md/.txt) para PL-014")
    lint.add_argument("--json", help="Escribir los hallazgos en este archivo JSON")
    lint.add_argument("--md", help="Escribir el reporte Markdown en este archivo")
    lint.add_argument(
        "--paquete",
        help="Paquete de evidencia: agrega el cotejo de identidad (PL-015 … PL-019) y el de fidelidad (PL-020)",
    )
    lint.set_defaults(func=cmd_lint)

    hash_ = sub.add_parser("hash", help="Calcular el contenido_sha256 de las afirmaciones")
    hash_.add_argument("--ledger", required=True, help="Ledger JSON plan-ledger/1.0")
    hash_.add_argument("--afirmacion", help="ID de una sola afirmación")
    hash_.set_defaults(func=cmd_hash)

    cotejar = sub.add_parser(
        "cotejar", help="Cotejo de identidad de cada evidencia citada contra un paquete de evidencia"
    )
    cotejar.add_argument("--ledger", required=True, help="Ledger JSON plan-ledger/1.0")
    cotejar.add_argument("--paquete", required=True, help="Directorio del paquete de evidencia")
    cotejar.add_argument("--json", action="store_true", help="Imprimir el cotejo como JSON")
    cotejar.set_defaults(func=cmd_cotejar)

    fidelidad = sub.add_parser(
        "fidelidad",
        help="Cotejo de fidelidad determinista: señales entre lo que afirma el plan y el texto oficial (nunca CONFORME)",
    )
    fidelidad.add_argument("--ledger", required=True, help="Ledger JSON plan-ledger/1.0")
    fidelidad.add_argument("--paquete", required=True, help="Directorio del paquete de evidencia")
    fidelidad.add_argument("--json", action="store_true", help="Imprimir el cotejo de fidelidad como JSON")
    fidelidad.set_defaults(func=cmd_fidelidad)

    evidencia = sub.add_parser(
        "evidencia", help="Registrar evidencia oficial ya obtenida en un paquete (sin red) o consultar un artículo"
    )
    acciones = evidencia.add_subparsers(dest="accion", required=True)

    tesis = acciones.add_parser("agregar-tesis", help="Registrar el innerText del detalle de una tesis del SJF")
    tesis.add_argument("--paquete", required=True, help="Directorio del paquete (se crea si no existe)")
    tesis.add_argument("--archivo", required=True, help="innerText capturado (bytes exactos, UTF-8)")
    tesis.add_argument("--url", required=True, help="https://sjf2.scjn.gob.mx/detalle/tesis/<registro>")
    tesis.add_argument("--fecha-consulta", required=True, help="AAAA-MM-DD o fecha-hora ISO con zona (la da el operador)")
    tesis.add_argument("--registro", help="Registro digital esperado (falla si el texto es de otro)")
    tesis.set_defaults(func=cmd_agregar_tesis)

    ley = acciones.add_parser("agregar-ley", help="Registrar el PDF de una ley de LeyesBiblio")
    ley.add_argument("--paquete", required=True, help="Directorio del paquete (se crea si no existe)")
    ley.add_argument("--pdf", required=True, help="PDF descargado de LeyesBiblio (el original)")
    ley.add_argument("--url", required=True, help="https://www.diputados.gob.mx/LeyesBiblio/pdf/<archivo>.pdf")
    ley.add_argument("--fecha-consulta", required=True, help="AAAA-MM-DD o fecha-hora ISO con zona (la da el operador)")
    ley.add_argument("--paginas-json", help="Páginas ya extraídas (JSON); evita necesitar PyMuPDF")
    ley.add_argument("--extractor", help="Extractor del texto (obligatorio con --paginas-json si el JSON no lo trae)")
    ley.add_argument("--version-extractor", help="Versión del extractor (ídem)")
    ley.set_defaults(func=cmd_agregar_ley)

    articulo = acciones.add_parser(
        "articulo",
        help="Imprimir el texto exacto de un artículo que usará el cotejo (para copiar extractos)",
    )
    articulo.add_argument("--paquete", required=True, help="Directorio del paquete de evidencia")
    articulo.add_argument("--articulo", required=True, help="Artículo: 19, 1o., 113 Bis o \"Artículo 19\"")
    articulo.add_argument("--sha256", help="sha256_documento del PDF registrado (lo imprime agregar-ley)")
    articulo.add_argument("--url", help="URL exacta de LeyesBiblio con la que se registró")
    articulo.set_defaults(func=cmd_articulo)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
