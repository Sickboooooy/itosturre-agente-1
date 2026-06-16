"""
PoC LinkedIn Prospector — investigación / calificación de fit, NO mensajería.
Usa browser-use con tu Chrome real (sesión ya iniciada) + Claude self-hosted.

⚠️ ToS: este script SOLO lee perfiles públicos y califica el fit. NO envía
solicitudes de conexión ni mensajes — eso queda 100% manual. No automatizamos
outreach: LinkedIn restringe cuentas por mensajería agéntica de terceros.

Uso:
    python prospect.py                # usa los términos del día (L/M/V)
    python prospect.py "abogado fiscal Guadalajara"   # término ad-hoc
"""
import asyncio, json, os, sys, datetime as dt
from pathlib import Path

from dotenv import load_dotenv
from browser_use import Agent, Browser
from browser_use.llm import ChatAnthropic

load_dotenv()

# Términos rotativos por día (Master Plan · Pipeline 1)
TERMINOS = {
    0: ["abogado litigante Guadalajara", "abogado familiar Zapopan"],        # lunes
    2: ["abogado laboral Jalisco", "abogado fiscal litigante Guadalajara"],  # miércoles
    4: ["abogado amparo Guadalajara", "litigante civil Tlaquepaque"],        # viernes
}

OUT_DIR = Path(__file__).parent / "data"
OUT_DIR.mkdir(exist_ok=True)
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-0")
N_PERFILES = int(os.getenv("N_PERFILES", "10"))
MAX_STEPS = int(os.getenv("MAX_STEPS", "40"))

TASK = """Eres asistente de prospección B2B para Itosturre LegalTech (IA para despachos legales en Jalisco).

OBJETIVO: en LinkedIn busca el término «{term}» y revisa los primeros {n} resultados de PERSONAS.

REGLAS ESTRICTAS (NO violar):
- SOLO lee información pública del resultado/perfil.
- PROHIBIDO hacer clic en "Conectar", "Seguir", "Mensaje", "Enviar" o cualquier acción que modifique algo.
- No abras chats, no cambies nada en la cuenta. Eres de SOLO LECTURA.

Para cada persona evalúa el fit como posible cliente (despacho que podría contratar IA legal):
- tipo_despacho: Pequeño / Mediano / Bufete Corporativo / Premium (estimado)
- especialidad: materia(s) legal(es) visibles
- actividad_digital: alta / media / baja (¿publica seguido?)
- fit: Alto / Medio / Bajo + razon (1 frase)

Devuelve SOLO un JSON array con objetos de esta forma exacta:
{{"nombre":"", "despacho":"", "linkedin_url":"", "ciudad":"", "especialidad":[], "tipo_despacho":"", "actividad_digital":"", "seguidores":"", "fit":"", "razon":""}}
"""


def terminos_de_hoy():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        return args
    return TERMINOS.get(dt.date.today().weekday(), TERMINOS[0])


async def correr(term, browser, llm):
    agent = Agent(task=TASK.format(term=term, n=N_PERFILES), llm=llm, browser=browser)
    history = await agent.run(max_steps=MAX_STEPS)
    raw = history.final_result() or "[]"
    try:  # extraer el JSON aunque venga con texto alrededor
        data = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
    except Exception:
        data = {"_raw": raw}
    return data


async def main():
    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("❌ Falta ANTHROPIC_API_KEY en .env")

    llm = ChatAnthropic(model=MODEL, temperature=0.0)

    profile = os.getenv("CHROME_PROFILE")
    if not profile:
        profs = Browser.list_chrome_profiles()
        print("Perfiles de Chrome disponibles:")
        for i, p in enumerate(profs, 1):
            print(f"  {i}. {p.get('directory')} — {p.get('name', '')}")
        profile = profs[int(input("Elige #: ")) - 1]["directory"]
    browser = Browser.from_system_chrome(profile_directory=profile)

    fecha = dt.date.today().isoformat()
    todos = []
    for term in terminos_de_hoy():
        print(f"\n🔎 Buscando: {term}")
        res = await correr(term, browser, llm)
        if isinstance(res, list):
            for r in res:
                r["_termino"] = term
            todos.extend(res)
        else:
            todos.append(res)

    out = OUT_DIR / f"prospectos_{fecha}.json"
    out.write_text(json.dumps(todos, ensure_ascii=False, indent=2), encoding="utf-8")
    altos = [r for r in todos if isinstance(r, dict) and r.get("fit") == "Alto"]
    print(f"\n✅ {len(todos)} perfiles · {len(altos)} fit ALTO → {out}")
    print("➡️  Revisa el JSON y envía las conexiones MANUALMENTE (sin automatizar).")


if __name__ == "__main__":
    asyncio.run(main())
