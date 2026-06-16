"""
Push de prospectos calificados (JSON del PoC) al Notion "Pipeline CRM B2B".
Stage = Prospecto, Fuente = LinkedIn. Idempotente por LinkedIn URL.

Requiere en .env:
  NOTION_TOKEN  -> token de una integración interna de Notion con acceso a la DB
  NOTION_DB_ID  -> id de la base Pipeline CRM B2B (default ya puesto)

Uso:
  python to_notion.py                  # último data/prospectos_*.json
  python to_notion.py archivo.json     # archivo específico
  python to_notion.py --dry-run        # muestra qué crearía, sin escribir
  python to_notion.py --solo-altos     # solo fit == "Alto"
"""
import os, sys, json, glob
from pathlib import Path

from dotenv import load_dotenv
from notion_client import Client

load_dotenv()

# Pipeline CRM B2B (database id). Ver memoria project-crm-b2b.
DB_ID = os.getenv("NOTION_DB_ID", "135e263c9c4246cb80f8d54d730aaa23")
ESPECIALIDADES = {"Fiscal", "Laboral", "Familiar", "Civil", "Penal",
                  "Amparo", "Mercantil", "Administrativo", "Migratorio"}
TIPOS = {"Pequeño", "Mediano", "Bufete Corporativo", "Premium"}


def ultimo_json():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        return Path(args[0])
    files = sorted(glob.glob(str(Path(__file__).parent / "data" / "prospectos_*.json")))
    if not files:
        sys.exit("No hay data/prospectos_*.json (corre primero prospect.py)")
    return Path(files[-1])


def to_props(p):
    nombre = p.get("nombre") or p.get("despacho") or "(sin nombre)"
    despacho = p.get("despacho") or nombre
    esp = [e for e in (p.get("especialidad") or []) if e in ESPECIALIDADES]
    tipo = p.get("tipo_despacho") if p.get("tipo_despacho") in TIPOS else None
    notas = (f"Fit {p.get('fit','?')} · act. digital {p.get('actividad_digital','?')} · "
             f"{p.get('seguidores','?')} seg. · {p.get('razon','')} (término: {p.get('_termino','')})")
    pr = {
        "Despacho": {"title": [{"text": {"content": despacho[:200]}}]},
        "Contacto": {"rich_text": [{"text": {"content": nombre[:200]}}]},
        "Stage": {"select": {"name": "Prospecto"}},
        "Fuente": {"select": {"name": "LinkedIn"}},
        "Notas": {"rich_text": [{"text": {"content": notas[:1900]}}]},
    }
    if p.get("linkedin_url"):
        pr["LinkedIn URL"] = {"url": p["linkedin_url"]}
    if p.get("ciudad"):
        pr["Ciudad"] = {"rich_text": [{"text": {"content": str(p["ciudad"])[:200]}}]}
    if esp:
        pr["Especialidad"] = {"multi_select": [{"name": e} for e in esp]}
    if tipo:
        pr["Tipo Despacho"] = {"select": {"name": tipo}}
    return pr


def ya_existe(notion, url):
    if not url:
        return False
    try:
        r = notion.databases.query(
            database_id=DB_ID,
            filter={"property": "LinkedIn URL", "url": {"equals": url}},
            page_size=1,
        )
        return bool(r.get("results"))
    except Exception:
        return False  # si la query falla, no bloquea la creación


def main():
    dry = "--dry-run" in sys.argv
    solo_altos = "--solo-altos" in sys.argv

    data = json.loads(ultimo_json().read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = [data]
    if solo_altos:
        data = [p for p in data if isinstance(p, dict) and p.get("fit") == "Alto"]

    token = os.getenv("NOTION_TOKEN")
    if not dry and not token:
        sys.exit("Falta NOTION_TOKEN en .env")
    notion = Client(auth=token) if token else None

    creados = saltados = 0
    for p in data:
        if not isinstance(p, dict) or "_raw" in p:
            continue
        if dry:
            print(f"DRY · {p.get('nombre')} — {p.get('despacho')} — fit {p.get('fit')}")
            continue
        if ya_existe(notion, p.get("linkedin_url")):
            saltados += 1
            print(f"⏭️  ya existe: {p.get('nombre')}")
            continue
        notion.pages.create(parent={"database_id": DB_ID}, properties=to_props(p))
        creados += 1
        print(f"✅ {p.get('nombre')}")

    print(f"\nCreados: {creados} · saltados (dup): {saltados}")


if __name__ == "__main__":
    main()
