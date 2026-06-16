# LinkedIn Prospector (PoC) — browser-use + Claude

Reemplaza la dependencia de **Cowork/computer-use** para la **investigación y calificación** de prospectos en LinkedIn (Master Plan · Pipeline 1). Maneja tu Chrome real con un agente Claude self-hosted y vuelca prospectos calificados a JSON.

## 🚦 Alcance y candado de ToS

- ✅ **Solo lectura**: busca, lee perfiles públicos, califica fit, exporta JSON.
- ❌ **NO** envía conexiones ni mensajes (mensajería agéntica de terceros viola el ToS de LinkedIn y restringe cuentas). El envío lo haces **tú a mano**.
- El prompt del agente prohíbe explícitamente clicar Conectar/Seguir/Mensaje.

## Setup

```bash
cd services/linkedin-prospector

# Recomendado: venv con Python 3.12 (browser-use puede no tener wheels para 3.14 aún)
py -3.12 -m venv .venv
.venv\Scripts\activate          # PowerShell:  .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env          # y rellena ANTHROPIC_API_KEY
```

> Si solo tienes Python 3.14 global y `pip install` falla por wheels, instala 3.12 (o usa `uv`). browser-use trae un core en Rust; necesita Python ≥3.11.

## Correr

1. Abre **Chrome** normal y verifica que tu sesión de **LinkedIn** está iniciada.
2. Cierra Chrome (browser-use reusa el perfil; no puede haber otra instancia usando ese perfil).
3. Ejecuta:

```bash
python prospect.py                      # términos del día (L/M/V)
python prospect.py "abogado fiscal Guadalajara"   # término ad-hoc
```

La primera vez te lista los perfiles de Chrome para elegir (o fija `CHROME_PROFILE` en `.env`).

Salida → `data/prospectos_AAAA-MM-DD.json` con: nombre, despacho, `linkedin_url`, ciudad, especialidad, tipo_despacho, actividad_digital, fit (Alto/Medio/Bajo), razón.

## Siguiente paso (Notion)

El JSON sale con los campos alineados al CRM (`LinkedIn URL`, `Ciudad`, `Especialidad`). El push a **Notion Pipeline CRM B2B** (`collection://499a93b7-4b5b-43db-8fc5-b7421f067f41`, Stage = Prospecto) lo construimos aparte — como acordamos, las piezas de Notion van poco a poco. El PoC deja el JSON listo para ingerir.

## Smoke test (sin LinkedIn)

Para validar que el toolchain corre antes de apuntarlo a LinkedIn, prueba una tarea inocua:

```bash
python -c "import asyncio; from browser_use import Agent; from browser_use.llm import ChatAnthropic; asyncio.run(Agent(task='Ve a example.com y dime el título', llm=ChatAnthropic(model='claude-sonnet-4-0')).run(max_steps=5))"
```
