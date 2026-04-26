# Agente Itosturre — Auditoría Legal Asistida por IA

Herramienta educativa para investigación jurídica asistida: **OpenNotebook** (RAG auditoría) + **SJF Scraper** (jurisprudencia) + **PDF Auditor** (reportes).

Desarrollado por [Itosturre LegalTech](https://itosturre.com) para el curso "IA Estratégica para Abogados" (junio 2026).

---

## Requisitos

- **Python 3.10+** (OpenNotebook + PDF tools)
- **Node 18+** (SJF Scraper vía Playwright)
- **Claude Code** (recomendado para integración)

---

## Instalación rápida

### 1. Clonar repo
```bash
git clone https://github.com/Sickboooooy/itosturre-agente.git
cd itosturre-agente
```

### 2. Setup Python
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Setup Node (scraper SJF)
```bash
npm install
```

### 4. Descargar corpus legal
Descarga los **38 PDFs** desde: [Google Drive — Corpus Legal Itosturre](ENLACE_DRIVE_AQUI)

Extrae en la carpeta `corpus/`:
```bash
# Estructura esperada:
corpus/
├── codigo_civil_federal.pdf
├── ley_federal_trabajo.pdf
├── codigo_penal_federal.pdf
└── [35+ más]
```

---

## Uso

### A. OpenNotebook — Auditoría de demandas/escritos
Verifica citas de ley y jurisprudencia contra el corpus:

```bash
python3 opennotebook.py audit --file mi_demanda.md
```

Output: JSON con puntuación VVCA (Verificación, Validación, Contextualización, Auditabilidad).

### B. SJF Scraper — Buscar jurisprudencia
Extrae tesis de la Suprema Corte de Justicia:

```bash
# Búsqueda simple (1 término)
npx ts-node scraper_sjf.ts "pensión alimenticia"

# Búsqueda batch (3+ términos)
npx ts-node scraper_batch.ts
# (edita scraper_batch.ts para términos)
```

Output: JSON con tesis + registro SJF + texto completo.

### C. PDF Auditoría — Reporte ejecutivo
Genera PDF con auditoría + capturas de SJF:

```bash
python3 generar_pdf_auditoria.py --draft mi_demanda.md --output auditoria.pdf
```

Output: PDF con análisis completo + anexo de tesis.

---

## Estructura del repo

```
itosturre-agente/
├── opennotebook.py              # RAG auditoría legal
├── scraper_sjf.ts               # Scraper Playwright → SJF
├── scraper_batch.ts             # Batch scraper (multi-términos)
├── generar_pdf_auditoria.py     # PDF generator
├── sjf_capturas.py              # Screenshot helper
├── corpus/                       # PDFs corpus legal (descargar)
├── requirements.txt             # Python deps
├── package.json                 # Node deps
├── tsconfig.json                # TypeScript config
├── setup.sh                      # Auto-setup script
└── README.md                     # Este archivo
```

---

## Flujo educativo (Sesiones 3-4, junio 2026)

**Sesión 3 (18 jun):** Instalación + primeros pasos
- Clonar repo
- Setup venv + npm
- Descargar corpus
- Prueba: `python3 opennotebook.py --version`

**Sesión 4 (25 jun):** Caso real
- Traer demanda propia
- Ejecutar `opennotebook.py audit --file`
- Interpretar score VVCA
- Exportar PDF con `generar_pdf_auditoria.py`

---

## Troubleshooting

### "No se encuentra OpenNotebook"
```bash
# Asegúrate de estar en venv:
source venv/bin/activate
python3 opennotebook.py --version
```

### "Error de Playwright / Chromium"
```bash
# Instala navegador:
npx playwright install chromium
npm install
```

### "Corpus no encontrado"
- Verifica que descargaste los PDFs en `corpus/`
- Intenta re-ingestar: `python3 opennotebook.py ingest --directory corpus/`

---

## Licencia & Autoría

Itosturre LegalTech © 2026. Uso educativo. No para producción sin supervisión legal.

**Desarrollado por:** Lic. Jorge Fabián Martínez Sánchez (SCJN, 20+ años).  
**Socio:** Lic. Efrén Martínez Sánchez.

---

## Soporte

- 📧 Email: despachos-gdl@itosturre.com
- 🔗 Web: https://itosturre.com
- 📱 Telegram: @itosclaude_bot

**Nota:** Este repo es educativo. Para uso en litigios reales, contacta al despacho.
