"""
Template Modul – LangGraph @tool-Funktionen.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.template.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """
    Hilfsfunktion: Lädt Konfiguration und Secrets aus dem ConnectionManager.

    Best-Practice Pattern:
    1. Zuerst ConnectionManager (UI-Verbindungen aus Redis + Vault)
    2. Dann Fallback auf Env-Variablen (z.B. TEMPLATE_URL, TEMPLATE_API_KEY)
    3. Erst dann ValueError wenn gar nichts konfiguriert ist
    """
    # ── 1. ConnectionManager ──
    if connection_id:
        conn = await ConnectionManager.get_connection("template", connection_id)
        if not conn:
            raise ValueError(f"Template-Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("template")

    if conn:
        base_url = conn.config.get("url", "")
        vault = get_vault()
        api_key = None
        api_key_path = conn.vault_keys.get("TEMPLATE_API_KEY")
        if api_key_path:
            api_key = await vault.get_secret(api_key_path)
        return {"base_url": base_url, "api_key": api_key}

    # ── 2. Env-Fallback ──
    base_url = os.environ.get("TEMPLATE_URL", "")
    api_key = os.environ.get("TEMPLATE_API_KEY", "")

    if not base_url:
        raise ValueError(
            "Keine Template-Verbindung konfiguriert. "
            "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
            "oder die Env-Variablen TEMPLATE_URL / TEMPLATE_API_KEY setzen."
        )

    return {"base_url": base_url, "api_key": api_key}


# ═══════════════════════════════════════════════════════
# Agent Tools (Dem LLM zugänglich)
#
# WICHTIG: Docstrings müssen präzise sein — das LLM liest sie zur Tool-Auswahl!
# Empfehlung: Docstrings auf Deutsch schreiben (Default-Sprache).
# Bei englischer UI (LANGUAGE=en) wird das Tool dennoch korrekt gewählt,
# da das LLM den Kontext versteht.
#
# Tool-Status-Labels (für den Lade-Spinner im Chat) in base_agent._TOOL_LABELS
# eintragen:
#   "beispiel_tool": ("Führe Beispiel aus", "Running example"),
#   "lade_daten":    ("Lade Daten",         "Loading data"),
# ═══════════════════════════════════════════════════════

@tool
async def beispiel_tool(parameter: str, connection_id: str = "") -> str:
    """
    Ein einfaches Beispiel-Tool.
    Benutze dieses Tool, wenn der User nach einem Beispiel oder Test fragt.
    Use this tool when the user asks for an example or a test.
    """
    try:
        client = await _get_api_client(connection_id)
        # TODO: Hier den echten API-Aufruf durchführen
        return f"Das Beispiel-Tool wurde erfolgreich mit Parameter '{parameter}' ausgeführt."
    except Exception as e:
        logger.error("Fehler im beispiel_tool: %s", e)
        return f"Fehler: {e}"


@tool
async def lade_daten(connection_id: str = "") -> dict:
    """
    Lädt Beispieldaten von der API.
    Benutze dies, wenn der User nach Daten-Auswertungen fragt.
    Use this when the user asks for data analysis or reports.
    """
    try:
        client = await _get_api_client(connection_id)
        # TODO: Hier den echten API-Aufruf durchführen
        return {
            "status": "success",
            "items": [1, 2, 3],
            "source": client["base_url"],
        }
    except Exception as e:
        return {"error": str(e)}
