#!/usr/bin/env python3
"""Importa la memoria histórica a la memoria contextual buscable.

Dos orígenes, ambos con el mismo problema: el conocimiento existe pero no se
puede consultar.

1. **Memorias en Markdown** (``~/.claude/projects/…/memory/``). Diecisiete
   archivos escritos a mano que hoy solo se recuperan cargándolos enteros. Ahí
   está, entre otras cosas, la corrección de que para deserción de pruebas la vía
   correcta es revocación y no apelación — un criterio de foro que no se deduce
   de ningún código y que nadie puede buscar (fuga F7 del informe).

2. **``jurisprudencia/vvca_corrections.json``**. Un log de correcciones real,
   pero monolítico: se lee entero con ``json.loads`` y solo sirve para mover un
   umbral. El archivo **no se toca**; ``OpenNotebook.py calibrate`` sigue
   leyéndolo igual que siempre.

Los archivos largos se parten por encabezados de Markdown. Un archivo de 13 KB
como un solo evento devolvería 13 KB por cualquier coincidencia; partido por
secciones, la búsqueda devuelve el párrafo que importa. Esa granularidad es el
punto de todo el ejercicio.

Idempotente: reejecutar no duplica (el ``event_uid`` se deriva del contenido).

Uso:
  python scripts/importar_memorias_md.py --dry-run
  python scripts/importar_memorias_md.py
  python scripts/importar_memorias_md.py --origen /ruta/a/memory --sin-correcciones
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from itosturre.memoria import MemoriaNoDisponible, MemoriaStore  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

#: Un archivo por debajo de este tamaño se importa entero; por encima, se parte.
UMBRAL_PARTIR = 1200

#: Correspondencia entre el `metadata.type` del frontmatter y la taxonomía.
TIPO_POR_CLASE = {
    "feedback": ("user_correction", 1),
    "project": ("important_context", 2),
    "user": ("important_context", 2),
    "reference": ("important_context", 3),
}

#: Tamaño máximo de un evento antes de partirlo por párrafos.
UMBRAL_EVENTO = 1600

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
#: Encabezado Markdown ordinario.
_ENCABEZADO = re.compile(r"^#{1,4}\s+(.+)$", re.M)
#: Encabezado de facto: estas memorias usan una línea en negrita como título de
#: sección mucho más que `##`. Ignorarlo dejaba archivos de 5 KB como un solo
#: evento, y una búsqueda devolvía el archivo entero en vez del párrafo útil.
_PSEUDO = re.compile(r"^\*\*(.+?)\*\*", re.M)

#: Señales de que una sección recoge criterio JURÍDICO corregido por el operador.
#:
#: Deliberadamente estrecho. Una primera versión aceptaba "corregido por",
#: "regla absoluta" o "PJF" sueltos y marcaba como corrección de criterio
#: secciones sobre remotes de git y reorganización de carpetas; al llevar esas
#: el bono más alto de la taxonomía, copaban el top de casi cualquier búsqueda y
#: enterraban la corrección real. Un falso positivo aquí no añade ruido: desplaza
#: la respuesta correcta.
#: Nota: `corrigió \w+` estuvo aquí y hubo que quitarlo — capturaba "corrigió a",
#: "corrigió del" en notas sobre arreglos de código. El verbo suelto no distingue
#: "corrigió un bug" de "corrigió el criterio procesal"; solo la frase completa lo
#: hace.
_SENAL_CRITERIO = re.compile(
    r"corrección (clave|de criterio) de \w+|criterio (PJF|de Fabián)|"
    r"con su criterio PJF|la vía correcta es|no es (la vía|apelación|procedente)",
    re.IGNORECASE,
)


def _leer_frontmatter(texto: str) -> tuple[dict[str, str], str]:
    """Extrae los campos planos del frontmatter. Sin dependencia de YAML."""
    coincidencia = _FRONTMATTER.match(texto)
    if not coincidencia:
        return {}, texto
    campos: dict[str, str] = {}
    for linea in coincidencia.group(1).splitlines():
        if ":" in linea:
            clave, _, valor = linea.partition(":")
            campos[clave.strip().lstrip("- ")] = valor.strip()
    return campos, texto[coincidencia.end():]


def _dividir_por(patron: re.Pattern[str], texto: str) -> list[tuple[str, str]]:
    """Divide ``texto`` en ``(título, bloque)`` por cada coincidencia del patrón.

    La línea del encabezado se conserva dentro del bloque: es contenido real y
    aporta términos al índice.
    """
    marcas = [(m.start(), m.group(1).strip()) for m in patron.finditer(texto)]
    if not marcas:
        return [("", texto.strip())]
    salida: list[tuple[str, str]] = []
    preambulo = texto[: marcas[0][0]].strip()
    if preambulo:
        salida.append(("", preambulo))
    for indice, (inicio, titulo) in enumerate(marcas):
        fin = marcas[indice + 1][0] if indice + 1 < len(marcas) else len(texto)
        bloque = texto[inicio:fin].strip()
        if bloque:
            salida.append((titulo, bloque))
    return salida


def _por_parrafos(titulo: str, texto: str) -> list[tuple[str, str]]:
    """Último recurso: agrupa párrafos hasta ``UMBRAL_EVENTO`` sin partir ninguno.

    Nunca corta a mitad de párrafo. Un fragmento cortado parece completo y puede
    inducir a error al leerlo fuera de contexto — justo lo que este sistema
    existe para evitar.
    """
    if len(texto) <= UMBRAL_EVENTO:
        return [(titulo, texto)]
    salida: list[tuple[str, str]] = []
    acumulado: list[str] = []
    largo = 0
    for parrafo in re.split(r"\n\s*\n", texto):
        parrafo = parrafo.strip()
        if not parrafo:
            continue
        if acumulado and largo + len(parrafo) > UMBRAL_EVENTO:
            salida.append((titulo, "\n\n".join(acumulado)))
            acumulado, largo = [], 0
        acumulado.append(parrafo)
        largo += len(parrafo)
    if acumulado:
        salida.append((titulo, "\n\n".join(acumulado)))
    return salida


def _secciones(cuerpo: str) -> list[tuple[str, str]]:
    """Parte el cuerpo en pares ``(título, texto)`` con tres niveles de corte.

    Encabezados ``#`` → encabezados en negrita → agrupación de párrafos. Cada
    nivel solo actúa sobre lo que el anterior dejó demasiado grande.
    """
    salida: list[tuple[str, str]] = []
    for titulo, bloque in _dividir_por(_ENCABEZADO, cuerpo):
        if len(bloque) <= UMBRAL_PARTIR:
            salida.append((titulo, bloque))
            continue
        subsecciones = _dividir_por(_PSEUDO, bloque)
        if len(subsecciones) > 1:
            for subtitulo, subbloque in subsecciones:
                compuesto = f"{titulo} · {subtitulo}" if titulo and subtitulo else (
                    titulo or subtitulo
                )
                salida.extend(_por_parrafos(compuesto, subbloque))
        else:
            salida.extend(_por_parrafos(titulo, bloque))
    return [(t, x) for t, x in salida if x]


def eventos_de_archivo(ruta: Path) -> list[dict]:
    """Convierte un archivo de memoria en uno o varios eventos."""
    texto = ruta.read_text(encoding="utf-8", errors="replace")
    campos, cuerpo = _leer_frontmatter(texto)
    clase = campos.get("type", "project")
    tipo, importancia = TIPO_POR_CLASE.get(clase, ("important_context", 2))
    titulo = campos.get("name") or ruta.stem
    descripcion = campos.get("description", "").strip()
    marca = datetime.fromtimestamp(ruta.stat().st_mtime, tz=timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")

    partes = _secciones(cuerpo) if len(cuerpo) > UMBRAL_PARTIR else [("", cuerpo.strip())]
    eventos: list[dict] = []
    for encabezado, contenido in partes:
        if not contenido:
            continue
        if encabezado:
            resumen = f"{titulo} · {encabezado}"
        else:
            resumen = descripcion or f"{titulo}: {contenido.splitlines()[0][:120]}"

        tipo_final, imp_final = tipo, importancia
        if _SENAL_CRITERIO.search(contenido):
            tipo_final, imp_final = "correccion_criterio_pjf", 1

        eventos.append({
            "event_type": tipo_final,
            "summary": resumen[:200],
            "details": contenido,
            "importance": imp_final,
            "timestamp": marca,
            "metadata": {"origen": "memoria_md", "archivo": ruta.name, "clase": clase},
        })
    return eventos


def eventos_de_correcciones(ruta: Path) -> list[dict]:
    """Convierte ``vvca_corrections.json`` en eventos. No modifica el archivo."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    eventos = []
    for entrada in datos if isinstance(datos, list) else []:
        referencia = entrada.get("ref", "?")
        eventos.append({
            "event_type": "correccion_criterio_pjf",
            "summary": f"{referencia}: el semáforo correcto es "
                       f"{entrada.get('semaforo_correcto', '?')} "
                       f"(el sistema auditó {entrada.get('score_auditado', '?')})",
            "details": {
                "nota": entrada.get("nota"),
                "referencia": referencia,
                "semaforo_correcto": entrada.get("semaforo_correcto"),
                "score_auditado": entrada.get("score_auditado"),
            },
            "importance": 1,
            "timestamp": entrada.get("timestamp"),
            "metadata": {"origen": "vvca_corrections"},
        })
    return eventos


def localizar_memorias() -> Path | None:
    """Busca el directorio de memorias de Claude Code para este proyecto."""
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return None
    for candidato in sorted(base.glob("*itosturre-agente*/memory")):
        if candidato.is_dir():
            return candidato
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--origen", help="Directorio con las memorias .md")
    ap.add_argument("--sin-correcciones", action="store_true",
                    help="No importar jurisprudencia/vvca_corrections.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="Mostrar qué se importaría, sin escribir")
    ap.add_argument("--reemplazar", action="store_true",
                    help="Sustituir lo importado antes por estos mismos orígenes "
                         "(necesario si cambió el criterio de conversión). No toca "
                         "eventos registrados a mano.")
    args = ap.parse_args()

    eventos: list[dict] = []

    origen = Path(args.origen) if args.origen else localizar_memorias()
    if origen and origen.is_dir():
        archivos = sorted(p for p in origen.glob("*.md") if p.name != "MEMORY.md")
        print(f"📂 Memorias Markdown: {origen}  ({len(archivos)} archivos)")
        for archivo in archivos:
            propios = eventos_de_archivo(archivo)
            eventos.extend(propios)
            print(f"   · {archivo.name:<42} → {len(propios)} evento(s)")
    else:
        print("⚠️  No se encontró el directorio de memorias .md (usa --origen).")

    correcciones = REPO / "jurisprudencia" / "vvca_corrections.json"
    if not args.sin_correcciones and correcciones.exists():
        propios = eventos_de_correcciones(correcciones)
        eventos.extend(propios)
        print(f"📂 {correcciones.name} → {len(propios)} evento(s) (archivo intacto)")

    if not eventos:
        print("Nada que importar.")
        return 0

    print(f"\nTotal a importar: {len(eventos)} eventos")
    if args.dry_run:
        print("(dry-run: no se escribió nada)")
        return 0

    try:
        with MemoriaStore(raiz=REPO) as store:
            if args.reemplazar:
                borrados = sum(
                    store.borrar_por_origen(o) for o in ("memoria_md", "vvca_corrections")
                )
                if borrados:
                    print(f"♻️  {borrados} evento(s) de importaciones previas sustituidos.")
            antes = store.estadisticas()["total"]
            store.record_lote(eventos)
            store.reindexar()
            despues = store.estadisticas()["total"]
    except MemoriaNoDisponible as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 3

    print(f"✅ Importación completa: {despues - antes} nuevos, "
          f"{len(eventos) - (despues - antes)} ya existían. Total: {despues}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
