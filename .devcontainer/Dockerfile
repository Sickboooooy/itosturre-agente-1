# Imagen base oficial de Dev Containers con Python 3.11
# Python 3.11 = compatible con pydantic v1/v2, sentence-transformers, chromadb 1.x
# (Python 3.14 genera warnings de pydantic v1 en cada ejecución)
FROM mcr.microsoft.com/devcontainers/python:3.11-bullseye

# ── Dependencias de sistema para Playwright/Chromium ──────────────────────────
# Chromium en Linux necesita estas libs; sin ellas playwright install falla silenciosamente
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Chromium core
    libglib2.0-0 \
    libnss3 \
    libdbus-1-3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    libgtk-3-0 \
    # Fuentes para capturas SJF (caracteres legales mexicanos con tildes)
    fonts-liberation \
    fonts-noto \
    fonts-noto-cjk \
    # Utilidades
    curl \
    wget \
    jq \
    git \
    && rm -rf /var/lib/apt/lists/*

# ── Python packages ───────────────────────────────────────────────────────────
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt

# python-docx no está en requirements.txt (es el generador Word canónico)
RUN pip install --no-cache-dir python-docx

# ── Configuración de encoding global ─────────────────────────────────────────
ENV PYTHONIOENCODING=utf-8
ENV PYTHONUTF8=1
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
