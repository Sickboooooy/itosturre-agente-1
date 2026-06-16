# ⚖️ Agente Itosturre — Auditoría Legal Automática

Herramienta para auditar tus demandas, escritos y conceptos de impugnación **en segundos** usando IA.

✨ **Qué hace:**
- 🔍 Verifica que tus citas legales sean correctas
- 📚 Busca jurisprudencia de la Suprema Corte de Justicia
- 📄 Genera reportes en PDF con análisis completo

Hecha por [**Itosturre LegalTech**](https://itosturre.com) para el curso "IA Estratégica para Abogados" (junio 2026).

---

## 📋 Requisitos (¿Qué necesito instalar?)

Antes de empezar, necesitas tres cosas. Si ya las tienes, sáltate este paso:

✅ **Python 3.10+** — [Descargar](https://www.python.org/downloads/)  
✅ **Node.js 18+** — [Descargar](https://nodejs.org/)  
✅ **Claude Code** — [Instalar](https://claude.com/claude-code) (es gratis)

**¿Cómo sé si ya lo tengo?** Abre tu terminal/PowerShell y corre:
```bash
python --version
node --version
```

Si te muestra un número, ¡ya lo tienes! 👍

---

## 🚀 Paso 1: Descargar el repositorio

**Opción A — Por terminal (recomendado):**
```bash
git clone https://github.com/Sickboooooy/itosturre-agente.git
cd itosturre-agente
```

**Opción B — Descargarlo como ZIP:**
1. Ve a https://github.com/Sickboooooy/itosturre-agente
2. Haz clic en **Code** → **Download ZIP**
3. Descomprime en tu computadora
4. Abre terminal en esa carpeta

---

## 📦 Paso 2: Preparar el entorno Python

Esto crea un "entorno virtual" donde viven todas tus herramientas sin contaminarte la compu.

**En Windows (PowerShell):**
```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

**En Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

✅ Cuando veas `(venv)` al inicio de tu terminal, ¡está activado!

---

## 📥 Paso 3: Descargar el corpus legal

Necesitas los **38 PDFs** de leyes y jurisprudencia. Sin esto, la herramienta no funciona.

### 3a. Descarga desde Google Drive
📥 **[Corpus Legal Itosturre](ENLACE_DRIVE_AQUI)**

### 3b. Extrae en la carpeta correcta
Descomprime los PDFs en la carpeta `corpus/`:

```
Tu carpeta itosturre-agente/
├── opennotebook.py
├── scraper_sjf.ts
├── corpus/
│   ├── codigo_civil_federal.pdf
│   ├── ley_federal_trabajo.pdf
│   ├── codigo_penal_federal.pdf
│   └── [35 más PDFs aquí]
└── ...
```

---

## ✅ Paso 4: Instalar herramientas Node (para buscar jurisprudencia)

Ahora instala las librerías de Node (el scraper que busca en la Suprema Corte):

```bash
npm install
```

Espera a que termine. Verás una línea que dice `added X packages`.

---

## 🎯 ¿YA ESTOY LISTO?

Verifica que todo funciona. Corre esto:

```bash
python opennotebook.py --version
```

Si ves un número de versión, ¡**¡¡LISTO!!** 🎉

---

## 💼 AHORA SÍ: Cómo usar la herramienta

### Opción A: 🔍 Auditar tu demanda/escrito

Tienes un archivo `mi_demanda.md` (Word convertido a texto, o cualquier archivo).

**Paso:**
```bash
python opennotebook.py audit --file mi_demanda.md
```

**¿Qué pasa?**
- ✅ Lee tu demanda
- ✅ Verifica cada cita de ley
- ✅ Te muestra un **score VVCA** (0–100)
  - 🟢 **85+** = Bueno, cita seguro
  - 🟡 **60–84** = Ten cuidado, verifica
  - 🔴 **<60** = No confíes, investiga más

**Ejemplo de output:**
```json
{
  "score": 82,
  "estatus": "amarillo",
  "artículos_verificados": [
    {"artículo": "Art. 388 CCF", "score": 0.95, "estatus": "✅"},
    {"artículo": "Art. 51 LFPCA", "score": 0.88, "estatus": "✅"}
  ],
  "alertas": []
}
```

---

### Opción B: 📚 Buscar jurisprudencia de la Suprema Corte

**Quieres encontrar una tesis sobre un tema específico.**

**Paso 1 — Búsqueda simple:**
```bash
npx ts-node scraper_sjf.ts "pensión alimenticia"
```

Reemplaza `"pensión alimenticia"` por tu tema.

**Paso 2 — Búsqueda múltiple (3+ temas):**

Edita el archivo `scraper_batch.ts` y agrega tus temas:
```typescript
const TERMINOS = [
  "pensión alimenticia",
  "incapacidad temporal",
  "divorcio necesario"
];
```

Luego corre:
```bash
npx ts-node scraper_batch.ts
```

**¿Qué obtienes?**
- 📋 Número de registro SJF
- 📖 Texto completo de la tesis
- 📅 Fecha de la jurisprudencia
- 🏛️ Tribunal que la emitió

Resultado guardado en `tesis_final.json`.

---

### Opción C: 📄 Generar PDF con auditoría completa

**Quieres un reporte bonito para el cliente o para llevar al tribunal.**

```bash
python generar_pdf_auditoria.py --draft mi_demanda.md --output auditoria.pdf
```

**¿Qué incluye el PDF?**
- ✅ Análisis de cada artículo citado
- ✅ Score VVCA con semáforo (🟢🟡🔴)
- ✅ Jurisprudencia relevante (top 5)
- ✅ Recomendaciones de cambios
- ✅ Anexo con capturas de SJF

---

## 📚 Flujo del Curso (Sesiones 3-4, junio 2026)

### 📅 Sesión 3 (18 junio — Instalación)
1. Clonas el repo
2. Corres Paso 1 → Paso 4 (arriba)
3. Verificas que todo funciona (Paso 4)
4. Preguntas si algo falla → resolvemos juntos

### 📅 Sesión 4 (25 junio — Caso real)
1. Traes una demanda tuya (o inventada)
2. La conviertes a `.md` o `.txt`
3. Corres: `python opennotebook.py audit --file tu_archivo.md`
4. Interpretas el score VVCA
5. Generas PDF: `python generar_pdf_auditoria.py --draft tu_archivo.md --output resultado.pdf`
6. Lo envías al cliente o lo archivas

---

## ⚠️ Si algo falla...

### "No encuentra OpenNotebook"
```bash
# Asegúrate de activar el entorno:
source venv/bin/activate  # Mac/Linux
.\venv\Scripts\activate   # Windows
```

### "Error de Playwright/Chromium"
```bash
# Instala el navegador:
npx playwright install chromium
npm install
```

### "Corpus no encontrado"
- Verifica que descargaste los PDFs
- Que estén en la carpeta `corpus/`
- Intenta reingestar:
```bash
python OpenNotebook.py ingest --directory corpus/
```

### "¿Por qué me pide Claude Code?"
OpenNotebook funciona mejor con Claude Code porque puede usar IA para verificar citas. Si no tienes Claude Code, aún funciona, pero menos potente.

---

## 📞 Soporte & Preguntas

**Durante el curso (junio 2026):**
- 💬 Pregunta en clase o en Telegram
- 📧 licjorgefab@itosturre.com

**Después del curso:**
- 🔗 https://itosturre.com
- 📱 @itosclaude_bot (Telegram)

---

## ⚖️ Aviso Legal

Esta herramienta es **educativa**. Úsala para aprender, no para reemplazar tu juicio legal.

**Responsabilidad:** Tú eres responsable de las demandas que presentes. OpenNotebook te ayuda a verificar, pero la decisión final es tuya.

**Licencia:** Uso educativo. No comercial.

---

## 👥 Equipo

**Fundadores:**

🏛️ **Lic. Jorge Fabián Martínez Sánchez** — Director Legal & IA  
*25 años de experiencia en Poder Judicial Federal*

💻 **Ing. Aldo Guillermo Madrigal** — CTO & Lead Developer  
*Especialista en Backend y Sistemas Distribuidos*

---

**Itosturre LegalTech © 2026.** Hecho con ⚖️ y ❤️.

---

## 🚦 Estado actual

✅ OpenNotebook — RAG auditoría  
✅ SJF Scraper — Búsqueda jurisprudencia  
✅ PDF Generator — Reportes ejecutivos  
✅ Docs — Listo para alumnos  

🚀 **Lista para el curso junio 2026.**

---

**¿Preguntas? Pregunta en clase. ¡Nos vemos en la sesión 3!** 👨‍⚖️👩‍⚖️
