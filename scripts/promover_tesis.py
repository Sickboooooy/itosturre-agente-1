#!/usr/bin/env python3
"""
promover_tesis.py — Glue scraper → corpus de jurisprudencia.

Cierra el ciclo de la vigencia de tesis: toma la salida del scraper SJF
(auditorias/<caso>/auditoria_vvca.json → verificados[]) y hace UPSERT de cada tesis
aplicable en un archivo del corpus local (jurisprudencia/*.json), CARGANDO el campo
`estado_vigencia`. A partir de ahí OpenNotebook.build_vvca_tesis lo lee y
scoring_vvca.veredicto_global convierte una tesis superada en 🔴 bloqueante.

Sin este paso, `estado_vigencia` se queda en el JSON del scraper y nunca llega al veredicto.

Uso:
  python scripts/promover_tesis.py --auditoria auditorias/<caso>/auditoria_vvca.json
  python scripts/promover_tesis.py --auditoria <...> --destino jurisprudencia/<archivo>.json
  python scripts/promover_tesis.py --auditoria <...> --incluir-propuestas   # también las propuestas
  python scripts/promover_tesis.py --auditoria <...> --dry-run              # no escribe, solo reporta

Seguridad: UPSERT por `registro` (no reescribe el corpus a ciegas). No promueve DESCARTADO ni
tesis con error/registro vacío. Escribe UTF-8, indent=2.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO = Path(__file__).resolve().parent.parent

# Campos que vive el corpus local (subconjunto del objeto del scraper). Alineado con
# jurisprudencia/712-2023_tesis_verificadas.json + estado_vigencia (glue de vigencia).
CAMPOS_CORPUS = ("registro", "numero_tesis", "rubro", "texto_completo",
                 "tipo_tesis", "materia", "estado_vigencia", "notas_vigencia")


def item_corpus(t: dict) -> dict:
    """Proyecta una tesis del scraper al esquema del corpus; default vigente."""
    out = {k: t.get(k, "") for k in CAMPOS_CORPUS}
    ev = str(out.get("estado_vigencia") or "vigente").strip().lower()
    out["estado_vigencia"] = ev if ev in ("vigente", "superada", "interrumpida", "sustituida") else "vigente"
    return out


def promovible(t: dict) -> bool:
    """Aplicable/parcial/propuesta con datos mínimos; nunca DESCARTADO ni error."""
    if not str(t.get("registro", "")).strip():
        return False
    if not str(t.get("rubro", "")).strip() or t.get("rubro", "").startswith("ERROR"):
        return False
    return t.get("estado") != "DESCARTADO"


def main() -> int:
    ap = argparse.ArgumentParser(description="Promueve tesis del scraper SJF al corpus local.")
    ap.add_argument("--auditoria", required=True, help="Ruta a auditoria_vvca.json del scraper")
    ap.add_argument("--destino", default=None,
                    help="Archivo del corpus (default: jurisprudencia/<stem>_promovidas.json)")
    ap.add_argument("--incluir-propuestas", action="store_true",
                    help="También promueve el arreglo 'propuestas' (no solo 'verificados')")
    ap.add_argument("--dry-run", action="store_true", help="No escribe; solo reporta")
    args = ap.parse_args()

    aud_path = Path(args.auditoria)
    if not aud_path.exists():
        print(f"❌ No existe: {aud_path}")
        return 1
    data = json.loads(aud_path.read_text(encoding="utf-8"))

    origen = list(data.get("verificados", []))
    if args.incluir_propuestas:
        origen += list(data.get("propuestas", []))

    destino = Path(args.destino) if args.destino else (
        REPO / "jurisprudencia" / f"{aud_path.parent.name or aud_path.stem}_promovidas.json"
    )
    corpus: list[dict] = []
    if destino.exists():
        try:
            corpus = json.loads(destino.read_text(encoding="utf-8"))
            if not isinstance(corpus, list):
                corpus = []
        except json.JSONDecodeError:
            print(f"⚠️  {destino.name} no es un JSON de lista válido — se recrea.")
            corpus = []

    idx = {str(it.get("registro")): i for i, it in enumerate(corpus)}
    nuevas = actualizadas = saltadas = 0
    superadas: list[str] = []

    print(f"── Promoción de tesis · {aud_path} → {destino.name} ──")
    for t in origen:
        if not promovible(t):
            saltadas += 1
            continue
        item = item_corpus(t)
        reg = str(item["registro"])
        if item["estado_vigencia"] != "vigente":
            superadas.append(f"{reg} ({item['estado_vigencia']})")
        if reg in idx:
            corpus[idx[reg]] = item
            actualizadas += 1
            print(f"  ↻ {reg}  {item['estado_vigencia']:12} {item['numero_tesis']}")
        else:
            idx[reg] = len(corpus)
            corpus.append(item)
            nuevas += 1
            print(f"  ＋ {reg}  {item['estado_vigencia']:12} {item['numero_tesis']}")

    print(f"\n  Nuevas: {nuevas} · Actualizadas: {actualizadas} · Saltadas (descartadas/error): {saltadas}")
    if superadas:
        print(f"  🔴 Vigencia perdida (bloquearán el veredicto): {', '.join(superadas)}")

    if args.dry_run:
        print("  (dry-run — no se escribió nada)")
        return 0

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ Corpus escrito: {destino} ({len(corpus)} tesis)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
