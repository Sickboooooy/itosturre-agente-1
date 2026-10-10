"""
contenido_linkedin.py — Módulo Generador de Contenido LinkedIn · Itosturre

Lee los briefs VIGENTES (últimos 7 días) de salidas/Vigilancia y
salidas/Jurisprudencia —y, sobre todo, sus contratos crudos (.json)— y redacta
1 borrador de post para LinkedIn ÚNICAMENTE si hay al menos un hallazgo
proveniente de una fuente que sí pudo consultarse (status SUCCESS en el
contrato, ver itosturre.vigilancia). Un brief viejo no se recicla.

Bloqueo obligatorio (protocolo Itosturre): si ninguna fuente aportó un hallazgo
validado —no hay briefs vigentes, no pudieron consultarse (SOURCE_UNAVAILABLE) o
se consultaron y no hubo novedades (SIN_HALLAZGOS)— este módulo NO escribe
borrador: deja el motivo en borrador-YYYY-MM-DD.estado.json y sale con código 3.
Redactar un borrador "genérico" sería fabricar la apariencia de una vigilancia
que no ocurrió; escribir un aviso en su lugar bloquearía el reintento del día.

Tono: técnico-práctico, SIN alarmismo, SIN prometer resultados.
Framing: "20 años de experiencia en el PJF".
Audiencia: contadores y empresarios PYME.
NO publica — deja el borrador en salidas/Contenido/ para revisión.
CTA: número de WhatsApp en $ITOSTURRE_WHATSAPP (si falta, queda "[número]").

Uso:
    python agentes/contenido_linkedin.py
"""

import os
import sys
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from itosturre.vigilancia import SUCCESS, leer_sidecar, registrar_evento, rutina  # noqa: E402

# ── Rutas ─────────────────────────────────────────────────────────────────────

VIGILANCIA_DIR = rutina.SALIDA_DIR / "Vigilancia"
JURISPRUDENCIA_DIR = rutina.SALIDA_DIR / "Jurisprudencia"
OUTPUT_DIR = rutina.SALIDA_DIR / "Contenido"
HOY = rutina.hoy_mx()
DATE_STR = HOY.strftime("%Y-%m-%d")
OUTPUT_FILE = OUTPUT_DIR / f"borrador-{DATE_STR}.md"


def _whatsapp() -> str:
    return os.environ.get("ITOSTURRE_WHATSAPP", "").strip() or "[número]"


# ── Lectura de briefs + contrato crudo ─────────────────────────────────────────

def leer_archivo_mas_reciente(directorio: Path) -> Optional[tuple[str, str]]:
    """Lee el brief vigente (últimos 7 días) más reciente. Devuelve (nombre,
    contenido) o None: un brief viejo no es "lo de esta semana" y no se recicla."""
    for archivo in rutina.briefs_vigentes(directorio, HOY):
        try:
            return archivo.name, archivo.read_text(encoding="utf-8")
        except OSError:
            continue
    return None


def _contrato_de(directorio: Path, nombre_md: str) -> Optional[Any]:
    """Carga el sidecar .json que corresponde al .md más reciente de `directorio`.
    None si no existe o es ilegible — nunca se sustituye por contenido inventado."""
    ruta_json = directorio / Path(nombre_md).with_suffix(".json").name
    return leer_sidecar(ruta_json)


def _items_validados(contrato: Any) -> tuple[int, list[str]]:
    """Cuenta hallazgos NUEVOS de entradas con status SUCCESS y lista las fuentes
    que NO lo tuvieron. Un contrato ausente o ilegible cuenta 0 — nunca se asume
    contenido que no se pudo verificar —, una ficha que no se pudo leer
    (`_error`) no es un hallazgo y uno con `novedad: false` (p. ej. una tesis
    anterior a la ventana de la semana) no es noticia: no basta para un post.
    Un item sin la marca cuenta como novedad (DOF/SAT: la portada del día y los
    comunicados recientes)."""
    if not contrato:
        return 0, []
    entradas = contrato.values() if isinstance(contrato, dict) else contrato
    total = 0
    indisponibles: list[str] = []
    for entrada in entradas:
        if not isinstance(entrada, dict):
            continue
        if entrada.get("status") == SUCCESS:
            total += sum(
                1 for item in entrada.get("items", [])
                if isinstance(item, dict) and not item.get("_error") and item.get("novedad", True)
            )
        else:
            indisponibles.append(f"{entrada.get('source', '?')} ({entrada.get('status', '?')})")
    return total, indisponibles


def obtener_contexto() -> dict[str, Any]:
    """Recopila el contenido y el contrato crudo de los briefs más recientes."""
    contexto: dict[str, Any] = {}

    resultado_vig = leer_archivo_mas_reciente(VIGILANCIA_DIR)
    if resultado_vig:
        contexto["vigilancia_nombre"], contexto["vigilancia_contenido"] = resultado_vig
        contrato_vig = _contrato_de(VIGILANCIA_DIR, contexto["vigilancia_nombre"])
    else:
        contexto["vigilancia_nombre"] = "sin datos"
        contexto["vigilancia_contenido"] = (
            "No hay briefs vigentes (últimos 7 días) de vigilancia DOF/SAT. "
            "Ejecuta primero `python agentes/vigilancia_dof.py`."
        )
        contrato_vig = None

    resultado_jur = leer_archivo_mas_reciente(JURISPRUDENCIA_DIR)
    if resultado_jur:
        contexto["jurisprudencia_nombre"], contexto["jurisprudencia_contenido"] = resultado_jur
        contrato_jur = _contrato_de(JURISPRUDENCIA_DIR, contexto["jurisprudencia_nombre"])
    else:
        contexto["jurisprudencia_nombre"] = "sin datos"
        contexto["jurisprudencia_contenido"] = (
            "No hay informes vigentes (últimos 7 días) de jurisprudencia. "
            "Ejecuta primero `python agentes/vigilancia_jurisprudencial.py`."
        )
        contrato_jur = None

    n_vig, indisp_vig = _items_validados(contrato_vig)
    n_jur, indisp_jur = _items_validados(contrato_jur)
    contexto["n_items_validos_vigilancia"] = n_vig
    contexto["n_items_validos_jurisprudencia"] = n_jur
    contexto["fuentes_indisponibles"] = indisp_vig + indisp_jur
    contexto["tiene_brief_vigilancia"] = resultado_vig is not None
    contexto["tiene_brief_jurisprudencia"] = resultado_jur is not None
    contexto["tiene_contrato_vigilancia"] = contrato_vig is not None
    contexto["tiene_contrato_jurisprudencia"] = contrato_jur is not None
    return contexto


# ── Validación (bloquea la generación sin hallazgo verificado) ────────────────

def validar(contexto: dict[str, Any]) -> tuple[bool, str]:
    """Decide si hay al menos un hallazgo validado para basar el post.

    Devuelve (es_valido, motivo). `motivo` está vacío cuando es_valido=True.
    """
    total = contexto["n_items_validos_vigilancia"] + contexto["n_items_validos_jurisprudencia"]
    if total > 0:
        return True, ""

    if not contexto["tiene_brief_vigilancia"] and not contexto["tiene_brief_jurisprudencia"]:
        return (
            False,
            "SIN_INSUMOS — no hay briefs vigentes (últimos 7 días) de vigilancia ni de "
            "jurisprudencia (ejecuta primero vigilancia_dof.py y vigilancia_jurisprudencial.py; "
            "si salieron con código 2, la fuente no se pudo consultar).",
        )
    if not contexto["tiene_contrato_vigilancia"] and not contexto["tiene_contrato_jurisprudencia"]:
        return (
            False,
            "SOURCE_UNAVAILABLE — los briefs vigentes no traen su contrato .json legible: "
            "no se puede verificar que provengan de una consulta real.",
        )
    if contexto["fuentes_indisponibles"]:
        return (
            False,
            "SOURCE_UNAVAILABLE — todas las fuentes consultables quedaron sin "
            f"verificar: {', '.join(contexto['fuentes_indisponibles'])}.",
        )
    return (
        False,
        "SIN_HALLAZGOS — las fuentes se consultaron correctamente pero no hubo "
        "novedades relevantes con las que redactar un post.",
    )


# ── Generación con Claude ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el módulo de contenido de Itosturre, especializado en comunicación legal-fiscal
para contadores y empresarios PYME en México.

Voz y tono:
- Técnico-práctico: explicas con precisión, sin jerga innecesaria
- Sin alarmismo: informas, no asustas
- Sin promesas de resultados: orientas, no garantizas
- Framing: "20 años de experiencia en el Poder Judicial Federal" (no "desde adentro")
- Cercano pero profesional; puedes usar "te" para hablar directamente al lector

Restricciones absolutas:
- NO prometras resultados ni éxito garantizado
- NO uses tono de urgencia manipuladora ("¡actúa ya antes de que sea tarde!")
- NO inventes datos normativos; si un hallazgo no tiene base, no lo uses
- NO uses contenido de una fuente marcada SOURCE_UNAVAILABLE en el brief — trátala
  como si no existiera, no como "sin novedades"
- NO publiques: solo genera el borrador para revisión humana"""


def generar_borrador(contexto: dict[str, Any]) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _borrador_placeholder(contexto, "ANTHROPIC_API_KEY no configurada")
    try:
        import anthropic
    except ImportError:
        return _borrador_placeholder(contexto, "librería anthropic no instalada")

    client = anthropic.Anthropic(api_key=api_key)

    nota_indisponibles = (
        f"\nFuentes marcadas SOURCE_UNAVAILABLE en esta ejecución (NO usar su contenido "
        f"como si fuera un hallazgo verificado): {', '.join(contexto['fuentes_indisponibles'])}\n"
        if contexto["fuentes_indisponibles"] else ""
    )

    prompt = f"""Tienes acceso a los siguientes materiales de inteligencia normativa de Itosturre.
Ya se verificó que al menos uno contiene un hallazgo de una fuente con status SUCCESS
({contexto['n_items_validos_vigilancia']} de vigilancia DOF/SAT,
{contexto['n_items_validos_jurisprudencia']} de jurisprudencia SJF).
{nota_indisponibles}
---
BRIEF DE VIGILANCIA DOF/SAT ({contexto['vigilancia_nombre']}):
{contexto['vigilancia_contenido'][:3000]}

---
INFORME JURISPRUDENCIAL ({contexto['jurisprudencia_nombre']}):
{contexto['jurisprudencia_contenido'][:3000]}

---

Con base en el hallazgo MÁS RELEVANTE y VERIFICADO de estos materiales, redacta 1 borrador de post para LinkedIn.

ESTRUCTURA DEL POST (máx. 1,200 caracteres, sin emojis excesivos):

**GANCHO (primera línea)**
Una oración que detenga el scroll. Orientada al problema real del contador o empresario PYME.
No usar "¿Sabías que...?" ni "¡ATENCIÓN!". Puede ser una afirmación directa o una pregunta genuina.

**CUERPO — 3 puntos de valor**
Punto 1: Qué cambió / cuál es el criterio / cuál es el riesgo real
Punto 2: Por qué le importa a un contador o empresario PYME
Punto 3: Qué se puede hacer al respecto (orientación, no promesa)

**CIERRE CON CTA**
Invita a agendar una consulta o conversación vía WhatsApp: wa.me/{_whatsapp()}
Firma: Lic. Jorge Fabián Martínez | Itosturre LegalTech | 20 años PJF

---

TAMBIÉN incluye al final del archivo (fuera del post visible):

## Metadatos del borrador
- Fecha: {DATE_STR}
- Fuente principal: [nombre del brief o informe usado]
- Hallazgo base: [qué dato normativo/jurisprudencial motivó el post]
- Temas: [hashtags sugeridos, máx. 5]
- Status: BORRADOR — pendiente de revisión por Lic. Jorge Fabián Martínez

## Variante alternativa (opcional)
[Una segunda versión del gancho si el primero es muy formal o muy coloquial]"""

    try:
        response = client.messages.create(
            model=rutina.modelo(),
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        borrador = response.content[0].text
        return f"# Borrador LinkedIn — {DATE_STR}\n\n{borrador}"
    except anthropic.APIError as e:
        print(f"  ⚠️ Error API Claude: {e}")
        return _borrador_placeholder(contexto, f"error de la API: {e}")


def _borrador_placeholder(contexto: dict[str, Any], motivo: str) -> str:
    return f"""# Borrador LinkedIn — {DATE_STR}

> ⚠️ Borrador generado sin LLM ({motivo})
> Para generar el post completo, configura ANTHROPIC_API_KEY.

## Fuentes disponibles (ya validadas: al menos un hallazgo con status SUCCESS)

- Vigilancia DOF/SAT: {contexto['vigilancia_nombre']} ({contexto['n_items_validos_vigilancia']} hallazgos válidos)
- Jurisprudencia SJF: {contexto['jurisprudencia_nombre']} ({contexto['n_items_validos_jurisprudencia']} hallazgos válidos)

## Estructura sugerida para el post

**GANCHO:** [Identificar el hallazgo más relevante de los briefs y abrir con él]

**Punto 1:** ¿Qué cambió normativamente o jurisprudencialmente?
**Punto 2:** ¿Por qué le importa a contadores/empresarios PYME?
**Punto 3:** ¿Qué medida práctica se puede tomar?

**CIERRE:** Agenda tu consulta → wa.me/{_whatsapp()}
Lic. Jorge Fabián Martínez | Itosturre LegalTech | 20 años PJF

## Metadatos
- Fecha: {DATE_STR}
- Status: BORRADOR — pendiente de revisión
"""


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    print(f"✍️  Generador de Contenido LinkedIn — {DATE_STR}")
    rutina.validar_salida(OUTPUT_DIR)

    if OUTPUT_FILE.exists():
        print(f"  ✅ Borrador del día ya existe: {OUTPUT_FILE.name}")
        return rutina.EXIT_OK

    print("  📖 Leyendo briefs vigentes (últimos 7 días)...")
    contexto = obtener_contexto()
    print(f"     → Vigilancia: {contexto['vigilancia_nombre']} ({contexto['n_items_validos_vigilancia']} hallazgos válidos)")
    print(f"     → Jurisprudencia: {contexto['jurisprudencia_nombre']} ({contexto['n_items_validos_jurisprudencia']} hallazgos válidos)")
    fuentes = [contexto["vigilancia_nombre"], contexto["jurisprudencia_nombre"]]

    registrar_evento("validation_started", modulo="contenido_linkedin")
    es_valido, motivo = validar(contexto)

    if not es_valido:
        # Sin borrador: ni post genérico ni aviso en su lugar (un aviso con el
        # nombre del borrador bloquearía el reintento del día).
        registrar_evento("validation_failed", modulo="contenido_linkedin", motivo=motivo)
        registrar_evento("draft_blocked", modulo="contenido_linkedin", motivo=motivo)
        ruta = rutina.registrar_estado(
            OUTPUT_DIR, OUTPUT_FILE.stem, rutina.SIN_INSUMOS, motivo=motivo, fuentes=fuentes,
            fuentes_indisponibles=contexto["fuentes_indisponibles"],
        )
        print(f"  🚫 Sin borrador: {motivo}")
        print(f"  📋 Estado → {ruta}")
        return rutina.EXIT_SIN_INSUMOS

    n_hallazgos = contexto["n_items_validos_vigilancia"] + contexto["n_items_validos_jurisprudencia"]
    registrar_evento("validation_passed", modulo="contenido_linkedin", n_hallazgos=n_hallazgos)
    print("  🤖 Redactando borrador...")
    borrador = generar_borrador(contexto)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(borrador, encoding="utf-8")
    registrar_evento("draft_generated", modulo="contenido_linkedin")
    rutina.registrar_estado(
        OUTPUT_DIR, OUTPUT_FILE.stem, rutina.OK,
        borrador=OUTPUT_FILE.name, fuentes=fuentes, hallazgos_validos=n_hallazgos,
    )
    size = OUTPUT_FILE.stat().st_size
    print(f"  💾 Borrador guardado → {OUTPUT_FILE} ({size} bytes)")
    print()
    print("  ⚠️  RECUERDA: Este es un BORRADOR. Revísalo antes de publicar.")
    return rutina.EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
