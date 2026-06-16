"""
Helpers compartidos para el CRM Itosturre en Notion.
Centraliza los IDs de las bases y expone un cliente reutilizable, para que
las piezas de Notion (push de prospectos, sync de clientes, etc.) no repitan
IDs ni lógica de conexión.

IDs verificados — ver memoria project-crm-b2b. Las 3 bases cuelgan de la
página CORE_PAGE, que está ARCHIVADA (restaurar en Notion para no perderla).
"""
import os

from dotenv import load_dotenv

load_dotenv()

# --- Bases del CRM: database_id (para crear páginas con la API oficial) ---
PIPELINE_DB    = "135e263c9c4246cb80f8d54d730aaa23"  # 🏢 Pipeline CRM B2B
CLIENTES_DB    = "24ef8447ab8d410ab96bac42a27058d1"  # 📋 Clientes Activos B2B
EXPEDIENTES_DB = "3fac2fcfc6bf404bb2a79642613e6ca5"  # ⚖️ Expedientes Itosturre

# --- Data sources (collection) — para queries semánticas / MCP ---
PIPELINE_DS    = "499a93b7-4b5b-43db-8fc5-b7421f067f41"
CLIENTES_DS    = "e445ef7b-1189-4256-905d-6fd471630a95"
EXPEDIENTES_DS = "2913adab-f41b-412e-9c25-ae60fe1245be"

# --- Páginas ---
CORE_PAGE      = "2338c35d-2faa-8084-b565-e4faf72931df"  # ⚠️ ARCHIVADA — restaurar
DASHBOARD_PAGE = "3818c35d-2faa-81eb-b60f-dc1d664defc4"  # 🎯 Centro de Mando CRM


def get_client():
    """Cliente de Notion autenticado con NOTION_TOKEN (.env)."""
    from notion_client import Client

    token = os.getenv("NOTION_TOKEN")
    if not token:
        raise RuntimeError("Falta NOTION_TOKEN en .env (integración interna con acceso a la DB)")
    return Client(auth=token)
