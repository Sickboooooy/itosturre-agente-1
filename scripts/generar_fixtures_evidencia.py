#!/usr/bin/env python3
"""Genera los fixtures de ``tests/fixtures/evidencia/`` desde material oficial descargado.

NO corre en CI ni en las pruebas: necesita PyMuPDF (``fitz``) y los originales, que no
se versionan. Las pruebas solo leen lo que este script dejó escrito, sin red.

Entrada (``--origen``): una carpeta con los PDF de LeyesBiblio tal como los sirve
``https://www.diputados.gob.mx/LeyesBiblio/pdf/<ARCHIVO>`` y los renders del SJF
``sjf_<registro>.txt`` (``document.body.innerText`` de
``https://sjf2.scjn.gob.mx/detalle/tesis/<registro>``).

Salida:
  - ``leyesbiblio_<LEY>.json``: texto de páginas concretas extraído con
    ``fitz.Page.get_text()`` (modo por omisión), con la huella de cada página.
  - ``sjf_<registro>.txt``: copia byte a byte del render (sin tocar fines de línea).
  - ``manifiesto.json``: procedencia de cada fixture (URL oficial, huella y tamaño del
    original, extractor y versión, páginas, metadatos del PDF y fecha de consulta
    cuando se conoce; si no, ``null`` con la nota "no registrada").

Salida determinista: JSON con llaves ordenadas, UTF-8 y ``\\n``. Ejecutar dos veces
sobre los mismos originales produce los mismos bytes.

Uso:
  python scripts/generar_fixtures_evidencia.py --origen <carpeta>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent
DESTINO = REPO / "tests" / "fixtures" / "evidencia"
URL_LEYESBIBLIO = "https://www.diputados.gob.mx/LeyesBiblio/pdf/{archivo}"
URL_SJF = "https://sjf2.scjn.gob.mx/detalle/tesis/{registro}"
NO_REGISTRADA = "no registrada"

# Páginas (base 1) de cada ley y para qué sirven en las pruebas.
LEYES = {
    "CNPP.pdf": {
        "paginas": [1, 52, 54, 139, 155],
        "proposito": (
            "primera página con encabezado; art. 1o., 167 y Único en el cuerpo; nota partida "
            "'…25-11-2022 / y publicada DOF…'; frontera TRANSITORIOS; 'Artículo Primero.-' "
            "repetido en transitorios de decretos"
        ),
    },
    "CPF.pdf": {
        "paginas": [1, 147, 151],
        "proposito": (
            "art. 1o.- en el cuerpo y 'ARTICULO 1°.-' en un decreto de reforma: sin la página "
            "de la frontera (p. 147) el encabezado es ambiguo"
        ),
    },
    "CPEUM.pdf": {
        "paginas": [43, 71, 74, 75, 144],
        "proposito": (
            "páginas con muchas notas de reforma: partidas en dos líneas, recorridas, fe de "
            "erratas, '(2 reformas)', 'Reforma DOF …: Derogó …' con fechas internas"
        ),
    },
    "CFF.pdf": {
        "paginas": [2, 30, 148],
        "proposito": (
            "art. 4o.- frente a 4o.-A.-; notas de multas y cantidades compiladas por "
            "resolución miscelánea, partidas en dos líneas"
        ),
    },
    "LAmp.pdf": {
        "paginas": [1],
        "proposito": "título del encabezado en dos líneas",
    },
}

# Fecha de consulta del render y huella SHA-256 del innerText (con LF) que imprimió el
# script de captura, solo cuando el operador las registró.
SJF = {
    "2006224": {
        "sha256_impresa_en_captura": None,
        "fecha_consulta": None,
        "nota_fecha": (
            f"{NO_REGISTRADA}: render del material PEN-01; el script de captura imprimió la "
            "hora UTC en consola, pero no quedó registrada con el archivo"
        ),
        "proposito": (
            "regresión del bug de época: el banner dice Duodécima Época antes del ancla y la "
            "tesis es de la Décima; jurisprudencia con fecha de publicación y de obligatoriedad"
        ),
    },
    "2031931": {
        "sha256_impresa_en_captura": "4fa85f1c1ae4b347d668595ac787e3f9bc67711cd6094ce47b36e02ee9b1b00e",
        "fecha_consulta": "2026-10-01T19:57Z",
        "nota_fecha": "aportada por el operador al entregar el render",
        "proposito": (
            "discrepancia real de la fuente: campo 'Duodécima Época' y clave con sufijo (11a.)"
        ),
    },
    "2032506": {
        "sha256_impresa_en_captura": "821674b6e0613567003d19f0022cd4d77f7d9dbf8dcc37d7b71526e3b21ccb89",
        "fecha_consulta": "2026-10-01T19:57Z",
        "nota_fecha": "aportada por el operador al entregar el render",
        "proposito": "aislada de la Duodécima Época, clave (12a.), dos materias",
    },
}


def _sha256(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _escribir_json(ruta: Path, contenido: object) -> bytes:
    datos = (json.dumps(contenido, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode("utf-8")
    ruta.write_bytes(datos)
    return datos


def generar(origen: Path, destino: Path) -> list[dict]:
    import fitz  # PyMuPDF: dependencia solo de este generador.

    destino.mkdir(parents=True, exist_ok=True)
    entradas: list[dict] = []
    for archivo, spec in LEYES.items():
        crudo = (origen / archivo).read_bytes()
        documento = fitz.open(stream=crudo, filetype="pdf")
        paginas = []
        for numero in spec["paginas"]:
            texto = documento[numero - 1].get_text()
            paginas.append(
                {
                    "numero": numero,
                    "texto": texto,
                    "sha256_texto": _sha256(texto.encode("utf-8")),
                }
            )
        nombre = f"leyesbiblio_{Path(archivo).stem}.json"
        datos = _escribir_json(
            destino / nombre,
            {"archivo": archivo, "total_paginas_pdf": documento.page_count, "paginas": paginas},
        )
        metadatos = documento.metadata or {}
        entradas.append(
            {
                "archivo": nombre,
                "sha256_archivo": _sha256(datos),
                "tipo": "ley_leyesbiblio",
                "proposito": spec["proposito"],
                "url_oficial": URL_LEYESBIBLIO.format(archivo=archivo),
                "medio": "descarga_https",
                "original": {
                    "archivo": archivo,
                    "sha256": _sha256(crudo),
                    "bytes": len(crudo),
                    "media_type": "application/pdf",
                    "paginas_pdf": documento.page_count,
                    "metadatos_pdf": {
                        clave: metadatos.get(clave)
                        for clave in ("title", "author", "creator", "creationDate", "modDate")
                    },
                },
                "extractor": "PyMuPDF fitz.Page.get_text() (modo por omisión)",
                "version_extractor": f"PyMuPDF {fitz.VersionBind} / MuPDF {fitz.VersionFitz}",
                "paginas": spec["paginas"],
                "fecha_consulta": None,
                "nota_fecha": f"{NO_REGISTRADA}: el PDF se descargó para PEN-01 sin registrar la hora",
            }
        )
        documento.close()

    for registro, spec in SJF.items():
        nombre = f"sjf_{registro}.txt"
        crudo = (origen / nombre).read_bytes()
        # El script de captura escribió el innerText en modo texto de Windows (LF →
        # CRLF). Se reconstruye la huella con LF y, si la captura imprimió la suya, deben
        # coincidir: si no, el archivo no es lo capturado y no se genera nada.
        lf = _sha256(crudo.replace(b"\r\n", b"\n"))
        captura = spec["sha256_impresa_en_captura"]
        if captura is not None and captura != lf:
            raise SystemExit(f"{nombre}: la huella LF {lf} no coincide con la de la captura {captura}")
        (destino / nombre).write_bytes(crudo)
        entradas.append(
            {
                "archivo": nombre,
                "sha256_archivo": _sha256(crudo),
                "tipo": "tesis_sjf",
                "proposito": spec["proposito"],
                "url_oficial": URL_SJF.format(registro=registro),
                "medio": "render_navegador",
                "original": {
                    "archivo": nombre,
                    "sha256": _sha256(crudo),
                    "bytes": len(crudo),
                    "media_type": "text/plain; charset=utf-8",
                    "sha256_innertext_lf": {
                        "valor": lf,
                        "origen": (
                            "reconstruida (CRLF→LF) y coincidente con la huella impresa en la captura"
                            if captura is not None
                            else "reconstruida (CRLF→LF); sin huella de captura registrada"
                        ),
                        "sha256_impresa_en_captura": captura,
                    },
                },
                "extractor": (
                    "Playwright sync_api + Chromium headless (revisión chromium-1234 según el "
                    "script de captura del operador): document.body.innerText"
                ),
                "version_extractor": NO_REGISTRADA,
                "paginas": None,
                "fecha_consulta": spec["fecha_consulta"],
                "nota_fecha": spec["nota_fecha"],
            }
        )
    return entradas


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--origen", required=True, type=Path, help="carpeta con los originales")
    parser.add_argument("--destino", type=Path, default=DESTINO, help="carpeta de fixtures")
    args = parser.parse_args(argv)
    entradas = generar(args.origen, args.destino)
    _escribir_json(
        args.destino / "manifiesto.json",
        {
            "esquema": "manifiesto-fixtures-evidencia/1.0",
            "generador": "scripts/generar_fixtures_evidencia.py",
            "descripcion": (
                "Procedencia de los fixtures de la capa de evidencia. Textos oficiales "
                "literales; ningún dato de tesis o ley es inventado. Las variantes "
                "sintéticas viven en las pruebas, rotuladas como tales."
            ),
            "fixtures": entradas,
        },
    )
    for entrada in entradas:
        print(f"{entrada['archivo']}: {entrada['sha256_archivo']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
