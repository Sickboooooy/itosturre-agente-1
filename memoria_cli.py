#!/usr/bin/env python3
"""memoria_cli.py — memoria contextual de Itosturre desde la línea de comandos.

La memoria guarda **decisiones**, no derecho. Nunca es fuente de una cita: los
artículos salen del corpus (``OpenNotebook.py query``) y las tesis del SJF. Lo
que vive aquí es lo que hoy se pierde entre sesiones — correcciones de criterio,
alertas procesales, huecos de corpus, tareas a medias.

Uso:
  python memoria_cli.py registrar correccion_criterio_pjf "Para deserción de pruebas
      la vía correcta es REVOCACIÓN, no apelación" --archivo OpenNotebook.py
  python memoria_cli.py buscar "revocacion desercion pruebas"
  python memoria_cli.py buscar "" --tipos alerta_procesal plazo_detectado
  python memoria_cli.py snapshot                 # construye y guarda
  python memoria_cli.py reanudar                 # consume el último snapshot
  python memoria_cli.py stats
  python memoria_cli.py tipos
  python memoria_cli.py olvidar --tipos user_correction correccion_criterio_pjf \
      --procedencia-no-humana                    # simulación: lista, no borra
  python memoria_cli.py olvidar --tipos user_correction correccion_criterio_pjf \
      --procedencia-no-humana --aplicar          # borra (solo este proyecto)

En Windows anteponer el intérprete del venv: ``./venv/Scripts/python.exe``.
En macOS/Linux: ``./venv/bin/python``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.memoria import (  # noqa: E402
    TIPOS,
    MemoriaNoDisponible,
    MemoriaStore,
    construir_snapshot,
    formato_evento,
    tipo_valido,
)
from itosturre.memoria.store import filtros_de_olvido, validar_fecha  # noqa: E402


def _utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


def _abrir(args: argparse.Namespace) -> MemoriaStore:
    return MemoriaStore(raiz=getattr(args, "raiz", None) or REPO,
                        session_id=getattr(args, "sesion", None))


def cmd_registrar(args: argparse.Namespace) -> int:
    if not tipo_valido(args.tipo):
        print(f"⚠️  Tipo '{args.tipo}' fuera de la taxonomía. Se registrará igualmente,")
        print("    pero no recibirá bono de ranking. Ver: memoria_cli.py tipos")
    detalles = args.detalles
    if detalles and detalles.lstrip().startswith("{"):
        try:
            detalles = json.loads(detalles)
        except json.JSONDecodeError:
            pass  # se guarda como texto plano
    with _abrir(args) as store:
        fila = store.record(
            args.tipo,
            args.resumen,
            details=detalles,
            file_path=args.archivo,
            importance=args.importancia,
        )
        if fila.get("redacted"):
            print("🔒 Se enmascaró contenido sensible antes de persistir.")
        print(f"✅ Evento registrado ({fila.get('event_type')}) · uid {fila.get('event_uid')}")
    return 0


def cmd_buscar(args: argparse.Namespace) -> int:
    with _abrir(args) as store:
        resultado = store.recall(
            args.consulta,
            limite=args.limite,
            max_bytes=args.max_bytes,
            tipos=args.tipos,
            desde=args.desde,
            con_detalles=args.detalles,
        )
    if args.json:
        print(json.dumps(resultado, ensure_ascii=False, indent=2))
        return 0

    print("═" * 64)
    print(f"  MEMORIA · {resultado['project_id']}")
    print("═" * 64)
    if not resultado["eventos"]:
        print("  (sin coincidencias)")
    for evento in resultado["eventos"]:
        marca = f"{evento.get('score', 0):.3f}"
        print(f"  [{marca}] {formato_evento(evento, con_detalles=args.detalles)}")
    print("─" * 64)
    print(
        f"  {resultado['n_devueltos']}/{resultado['n_candidatos']} candidatos · "
        f"{resultado['bytes']}/{resultado['max_bytes']} bytes · "
        f"{resultado['ms']} ms · modo {resultado['modo']} · "
        f"{resultado['total_en_memoria']} eventos en memoria"
    )
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    with _abrir(args) as store:
        eventos = store.recall("", limite=args.limite, max_bytes=10 ** 7)["eventos"]
        texto = construir_snapshot(
            eventos,
            project_id=store.project_id,
            session_id=store.session_id,
            total_en_memoria=store._total(),
            max_bytes=args.max_bytes,
        )
        if not args.solo_mostrar:
            store.guardar_snapshot(texto)
    print(texto)
    if not args.solo_mostrar:
        print(f"\n💾 Snapshot guardado ({len(texto.encode('utf-8'))} bytes).", file=sys.stderr)
    return 0


def cmd_reanudar(args: argparse.Namespace) -> int:
    with _abrir(args) as store:
        texto = store.consumir_snapshot() if not args.sin_consumir else store.ultimo_snapshot()
        if texto is None:
            eventos = store.recall("", limite=40, max_bytes=10 ** 7)["eventos"]
            texto = construir_snapshot(
                eventos,
                project_id=store.project_id,
                session_id=store.session_id,
                total_en_memoria=store._total(),
            )
    print(texto)
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with _abrir(args) as store:
        datos = store.estadisticas()
    if args.json:
        print(json.dumps(datos, ensure_ascii=False, indent=2))
        return 0
    print("═" * 64)
    print(f"  MEMORIA · {datos['project_id']}")
    print("═" * 64)
    print(f"  Base        : {datos['db']}")
    print(f"  Tamaño      : {datos['db_bytes'] / 1024:.1f} KB")
    print(f"  Eventos     : {datos['total']}  (redactados: {datos['redactados']})")
    print(f"  Sesiones    : {datos['sesiones']} · snapshots: {datos['snapshots']}")
    print(f"  Rango       : {datos['desde']} → {datos['hasta']}")
    if datos["por_tipo"]:
        print("  Por tipo:")
        for tipo, n in datos["por_tipo"].items():
            print(f"    {n:>5}  {tipo}")
    return 0


def cmd_tipos(_args: argparse.Namespace) -> int:
    print("═" * 72)
    print("  TAXONOMÍA DE EVENTOS")
    print("═" * 72)
    for tipo in sorted(TIPOS.values(), key=lambda t: (-t.bono, t.nombre)):
        print(f"  {tipo.nombre:<26} imp={tipo.importancia}  bono={tipo.bono:.2f}")
        print(f"  {'':<26} {tipo.descripcion}")
    return 0


def cmd_reindexar(args: argparse.Namespace) -> int:
    with _abrir(args) as store:
        store.reindexar()
    print("✅ Índice FTS reconstruido desde la tabla de eventos.")
    return 0


def _fecha(valor: str) -> str:
    try:
        return validar_fecha(valor)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _describir_filtros(filtros: dict) -> str:
    partes = []
    if filtros.get("tipos"):
        partes.append("tipos=" + ",".join(filtros["tipos"]))
    if filtros.get("desde"):
        partes.append(f"desde={filtros['desde']}")
    if filtros.get("hasta"):
        partes.append(f"hasta={filtros['hasta']}")
    if filtros.get("contiene"):
        partes.append("contiene=(texto)")
    if filtros.get("procedencia_no_humana"):
        partes.append("procedencia-no-humana")
    return " · ".join(partes)


def cmd_olvidar(args: argparse.Namespace) -> int:
    """Purga selectiva. Sin ``--aplicar`` es una simulación que no toca la base."""
    try:
        # Se valida antes de abrir: un error de uso no debe ni tocar la base.
        filtros_de_olvido(tipos=args.tipos, desde=args.desde, hasta=args.hasta,
                          contiene=args.contiene,
                          procedencia_no_humana=args.procedencia_no_humana)
        with _abrir(args) as store:
            resultado = store.olvidar(
                tipos=args.tipos,
                desde=args.desde,
                hasta=args.hasta,
                contiene=args.contiene,
                procedencia_no_humana=args.procedencia_no_humana,
                aplicar=args.aplicar,
            )
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    modo = "APLICADO" if resultado["aplicado"] else "SIMULACIÓN (no se borra nada)"
    print("═" * 64)
    print(f"  OLVIDAR · {resultado['project_id']} · {modo}")
    print(f"  Filtros: {_describir_filtros(resultado['filtros'])}")
    print("═" * 64)
    if not resultado["coincidencias"]:
        print("  (sin coincidencias)")
    for ev in resultado["coincidencias"]:
        resumen = " ".join(str(ev.get("summary") or "").split())[:80]
        fecha = str(ev.get("timestamp") or "")[:10]
        print(f"  #{ev['id']:<6} [{fecha}] {ev['event_type']:<24} {resumen}")
    print("─" * 64)
    total = len(resultado["coincidencias"])
    if resultado["aplicado"]:
        print(f"  🗑️  {resultado['borrados']} evento(s) borrado(s) · "
              f"{resultado['snapshots_consumidos']} snapshot(s) pendiente(s) marcados como "
              "consumidos" + (" · purga registrada (memoria_purga)" if resultado["borrados"] else ""))
    else:
        print(f"  {total} evento(s) coinciden. Para borrarlos, repite el comando con --aplicar.")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8()
    ap = argparse.ArgumentParser(
        description="Memoria contextual de Itosturre",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--raiz", help="Raíz del proyecto (por defecto, el repositorio)")
    ap.add_argument("--sesion", help="Identificador de sesión explícito")
    sub = ap.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("registrar", help="Registrar un evento")
    p.add_argument("tipo")
    p.add_argument("resumen")
    p.add_argument("--detalles", help="Texto o JSON con el detalle")
    p.add_argument("--archivo", help="Ruta relacionada (se ancla al proyecto)")
    p.add_argument("--importancia", type=int, choices=[1, 2, 3, 4])
    p.set_defaults(func=cmd_registrar)

    p = sub.add_parser("buscar", help="Recuperar eventos relevantes")
    p.add_argument("consulta", nargs="?", default="")
    p.add_argument("--limite", type=int, default=12)
    p.add_argument("--max-bytes", type=int, default=4096, dest="max_bytes")
    p.add_argument("--tipos", nargs="*", default=None)
    p.add_argument("--desde", help="Fecha ISO mínima (AAAA-MM-DD)")
    p.add_argument("--detalles", action="store_true", help="Incluir el detalle completo")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_buscar)

    p = sub.add_parser("snapshot", help="Construir (y guardar) el snapshot de continuidad")
    p.add_argument("--limite", type=int, default=60)
    p.add_argument("--max-bytes", type=int, default=2048, dest="max_bytes")
    p.add_argument("--solo-mostrar", action="store_true", help="No persistirlo")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("reanudar", help="Recuperar el estado al reanudar una sesión")
    p.add_argument("--sin-consumir", action="store_true",
                   help="No marcarlo como consumido (para inspección)")
    p.set_defaults(func=cmd_reanudar)

    p = sub.add_parser("stats", help="Estado de la memoria")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_stats)

    sub.add_parser("tipos", help="Listar la taxonomía").set_defaults(func=cmd_tipos)
    sub.add_parser("reindexar", help="Reconstruir el índice FTS").set_defaults(func=cmd_reindexar)

    p = sub.add_parser(
        "olvidar",
        help="Purgar eventos por filtros (simulación salvo --aplicar)",
        description="Borra eventos de ESTE proyecto que cumplan TODOS los filtros. "
                    "Sin --aplicar solo lista las coincidencias. Exige al menos un filtro.",
    )
    p.add_argument("--tipos", nargs="+", metavar="T", help="Tipos de evento")
    p.add_argument("--desde", type=_fecha, metavar="AAAA-MM-DD", help="Día mínimo (inclusive)")
    p.add_argument("--hasta", type=_fecha, metavar="AAAA-MM-DD", help="Día máximo (inclusive)")
    p.add_argument("--contiene", metavar="TEXTO",
                   help="Subcadena en resumen o detalles (sin distinguir mayúsculas ni acentos)")
    p.add_argument("--procedencia-no-humana", action="store_true", dest="procedencia_no_humana",
                   help="Texto guardado que no escribió el operador (subagentes, "
                        "notificaciones, canales, pegados)")
    p.add_argument("--aplicar", action="store_true",
                   help="Borrar de verdad (por defecto es una simulación)")
    p.set_defaults(func=cmd_olvidar)

    args = ap.parse_args(argv)
    try:
        return int(args.func(args))
    except MemoriaNoDisponible as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
