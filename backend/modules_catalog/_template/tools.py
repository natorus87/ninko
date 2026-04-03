"""
Template Module — LangGraph @tool functions.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.template.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """
    Helper: loads config and secrets from ConnectionManager.

    Best-practice pattern:
    1. ConnectionManager first (UI connections from Redis + Vault)
    2. Fallback to env vars (e.g. TEMPLATE_URL, TEMPLATE_API_KEY)
    3. ValueError only if nothing is configured
    """
    # ── 1. ConnectionManager ──
    if connection_id:
        conn = await ConnectionManager.get_connection("template", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Template-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Template connection with ID '{connection_id}' not found.",
                )
            )
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
            _t(
                de=(
                    "Keine Template-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen TEMPLATE_URL / TEMPLATE_API_KEY setzen."
                ),
                en=(
                    "No Template connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars TEMPLATE_URL / TEMPLATE_API_KEY."
                ),
            )
        )

    return {"base_url": base_url, "api_key": api_key}


# ═══════════════════════════════════════════════════════
# Agent Tools (exposed to LLM)
#
# IMPORTANT: Docstrings must be precise — the LLM reads them for tool selection.
# ALWAYS write docstrings in English.
#
# Tool status labels (chat loading spinner) in base_agent._TOOL_LABELS:
#   "beispiel_tool": ("Führe Beispiel aus", "Running example"),
#   "lade_daten":    ("Lade Daten",         "Loading data"),
#
# SAFEGUARD — _TOOL_READONLY (backend/core/safeguard.py):
# All read-only tools (get_*, list_*, search_*, inspect_*, check_*)
# MUST be registered in _TOOL_READONLY so the safeguard classifier
# skips them without an LLM call.
# Rule:
#   READ-ONLY  → get_*/list_*/search_*/inspect_*/check_*/ha_get_* → add to _TOOL_READONLY
#   WRITE/ACTION → start_*/stop_*/restart_*/delete_*/create_*/set_*/add_*/update_* → do NOT add
# ═══════════════════════════════════════════════════════

@tool
async def beispiel_tool(parameter: str, connection_id: str = "") -> str:
    """
    Run a simple example operation against the API.
    Use this tool when the user asks for an example or a test.
    """
    try:
        client = await _get_api_client(connection_id)
        # TODO: implement the real API call here
        logger.info("beispiel_tool called with parameter=%s", parameter)
        return f"Example tool executed successfully with parameter '{parameter}'."
    except Exception as e:
        logger.error("beispiel_tool failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
        )


@tool
async def lade_daten(connection_id: str = "") -> dict:
    """
    Load sample data from the API.
    Use this when the user asks for data analysis or reports.
    """
    try:
        client = await _get_api_client(connection_id)
        # TODO: implement the real API call here
        logger.info("lade_daten called")
        return {
            "status": "success",
            "items": [1, 2, 3],
            "source": client["base_url"],
        }
    except Exception as e:
        logger.error("lade_daten failed: %s", e)
        return {"error": str(e)}
