"""Pertenencia al cuerpo de la ley del encabezado elegido (verde determinista, ronda 2).

Criterio adjudicado por el coordinador (3-oct-2026, ronda 2 del verde determinista): la
primera aparición del encabezado no acredita por sí sola que el fragmento sea del CUERPO de
la ley. Un decreto introductorio u otra ley compilada antes del cuerpo, o una ley cuyos
encabezados en MAYÚSCULAS el chunker no etiqueta (y solo un transitorio "Artículo 1º.-" queda
como candidato por metadata), darían un 🟢 determinista con la ubicación equivocada.

Con los encabezados AUTÉNTICOS del artículo citado entre los candidatos de la ley citada
(``ocurrencias_encabezado``) y la frontera TRANSITORIOS con sus controles de credibilidad
(``itosturre.audit.inexistencia.frontera_creible``):

(i)   dos o más encabezados auténticos distintos: solo se acredita la ubicación si la frontera
      es creíble y exactamente uno queda antes de ella (ese se elige); si no, "ubicación
      ambigua" (tope 84 en ``build_vvca``);
(ii)  uno solo, tras una frontera creíble: transitorio o decreto, no el cuerpo (tope 84);
(iii) uno solo y la frontera no es creíble o no existe: se admite.

El mismo pasaje repetido por la ingesta (fragmentos consecutivos de la misma página con el
mismo texto tras el encabezado) cuenta una sola vez. Función pura (biblioteca estándar).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from .evidence import _indice, _without_accents, ocurrencias_encabezado
from .inexistencia import es_frontera_transitorios

SIN_AUTENTICO = "sin_encabezado_autentico"
UNICO = "unico"
EN_CUERPO = "unico_antes_de_la_frontera"
AMBIGUO = "ambiguo"
TRAS_FRONTERA = "tras_la_frontera"
NO_ACREDITADA = frozenset({AMBIGUO, TRAS_FRONTERA})

_VENTANA_PASAJE = 160   # caracteres tras el encabezado con que se compara un pasaje repetido


def _desplazamiento_frontera(normalizado: str) -> Optional[int]:
    """Posición de la primera línea TRANSITORIOS en un texto sin acentos, o None."""
    posicion = 0
    for linea in normalizado.split("\n"):
        if es_frontera_transitorios(linea):
            return posicion
        posicion += len(linea) + 1
    return None


def _mismo_pasaje(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """¿``b`` repite el pasaje de ``a``? Fragmentos consecutivos, misma página y el mismo
    texto tras el encabezado (uno puede estar truncado por el fin del fragmento)."""
    if a["chunk_index"] is None or b["chunk_index"] != a["chunk_index"] + 1:
        return False
    if a["pagina"] != b["pagina"]:
        return False
    corto, largo = sorted((a["pasaje"], b["pasaje"]), key=len)
    return len(corto) >= 20 and largo.startswith(corto)


def ubicar_en_cuerpo(
    documentos: Sequence[str],
    metadatas: Sequence[Mapping[str, Any] | None],
    articulo: str,
    fuente: Optional[str],
    frontera: Mapping[str, Any],
) -> dict[str, Any]:
    """Aplica las reglas (i)–(iii) a los resultados de la consulta (``documentos`` y
    ``metadatas``, en el orden de ChromaDB). Devuelve ``estado``, ``indice`` (el resultado
    que acredita la ubicación, o None), ``motivo`` (para el abogado si no se acredita),
    ``encabezados`` (auténticos distintos), ``paginas``, ``frontera_creible`` y
    ``motivo_frontera``."""
    ocurrencias = []
    for indice, documento in enumerate(documentos):
        metadata = (metadatas[indice] if indice < len(metadatas) else None) or {}
        if metadata.get("source") != fuente:
            continue
        normalizado = _without_accents(documento)
        for ocurrencia in ocurrencias_encabezado(documento, articulo):
            if not ocurrencia["autentico"]:
                continue
            ocurrencias.append({
                "indice": indice,
                "chunk_index": _indice(metadata),
                "inicio": ocurrencia["inicio"],
                "pagina": str(metadata.get("page", "?")),
                "pasaje": " ".join(
                    normalizado[ocurrencia["inicio"]:ocurrencia["inicio"] + _VENTANA_PASAJE].split()
                ),
                "normalizado": normalizado,
            })
    salida: dict[str, Any] = {
        "estado": SIN_AUTENTICO,
        "indice": None,
        "motivo": "",
        "encabezados": 0,
        "paginas": [],
        "frontera_creible": bool(frontera.get("creible")),
        "motivo_frontera": frontera.get("motivo", ""),
    }
    if not ocurrencias:
        return salida

    ocurrencias.sort(key=lambda o: (
        o["chunk_index"] is None, o["chunk_index"] or 0, o["inicio"], o["indice"]
    ))
    distintas: list[dict[str, Any]] = []
    for ocurrencia in ocurrencias:
        if distintas and _mismo_pasaje(distintas[-1], ocurrencia):
            continue
        distintas.append(ocurrencia)
    salida["encabezados"] = len(distintas)
    salida["paginas"] = [o["pagina"] for o in distintas]

    def antes_de_la_frontera(ocurrencia: Mapping[str, Any]) -> Optional[bool]:
        if not frontera.get("creible") or ocurrencia["chunk_index"] is None:
            return None
        limite = frontera.get("chunk_index")
        if ocurrencia["chunk_index"] != limite:
            return ocurrencia["chunk_index"] < limite
        desplazamiento = _desplazamiento_frontera(ocurrencia["normalizado"])
        return None if desplazamiento is None else ocurrencia["inicio"] < desplazamiento

    posiciones = [antes_de_la_frontera(o) for o in distintas]
    usable = bool(frontera.get("creible")) and None not in posiciones
    articulo_txt = f"artículo {articulo}"
    if len(distintas) >= 2:
        previas = [o for o, antes in zip(distintas, posiciones) if antes]
        if usable and len(previas) == 1:
            salida.update(estado=EN_CUERPO, indice=previas[0]["indice"])
            return salida
        paginas = ", ".join(salida["paginas"][:6])
        if usable:
            detalle = f"{len(previas)} antes de la frontera TRANSITORIOS"
        else:
            detalle = (
                f"la frontera TRANSITORIOS no lo desambigua "
                f"({salida['motivo_frontera'] or 'no utilizable'})"
            )
        salida.update(
            estado=AMBIGUO,
            motivo=(
                f"ubicación ambigua: el encabezado del {articulo_txt} aparece "
                f"{len(distintas)} veces en el PDF (págs. {paginas}); {detalle}"
            ),
        )
        return salida
    unica = distintas[0]
    if usable and posiciones[0] is False:
        salida.update(
            estado=TRAS_FRONTERA,
            motivo=(
                f"el único encabezado del {articulo_txt} está tras la frontera TRANSITORIOS "
                f"(pág. {unica['pagina']}): es de un transitorio o de un decreto, no del cuerpo "
                f"de la ley"
            ),
        )
        return salida
    salida.update(estado=UNICO, indice=unica["indice"])
    return salida
