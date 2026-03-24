"""
Microsoft Teams Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import httpx

from core.module_registry import ModuleManifest
from core.vault import get_vault
from .bot import get_teams_access_token

logger = logging.getLogger("ninko.modules.teams")


async def check_teams_health(connection_id: str = "") -> dict:
    """Health-Check für den Teams Bot via Azure/BotFramework OAuth Token Endpoint."""
    try:
        token = await get_teams_access_token(connection_id)
        if token:
            return {"status": "ok", "detail": "Erfolgreich an Microsoft Bot Framework authentifiziert."}
        else:
            return {"status": "warning", "detail": "Kein gültiges Token erhalten oder konfiguriert."}
    except Exception as e:
        return {"status": "error", "detail": f"Authentifizierung fehlgeschlagen: {e}"}


module_manifest = ModuleManifest(
    name="teams",
    display_name="Microsoft Teams",
    description="Ermöglicht das Chatten mit dem Ninko Orchestrator über Microsoft Teams",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="TEAMS_",
    required_secrets=[],
    optional_secrets=["MICROSOFT_APP_ID", "MICROSOFT_APP_PASSWORD"],
    routing_keywords=[
        "teams", "microsoft", "botframework", "ms teams"
    ],
    api_prefix="/api/teams",
    dashboard_tab={"id": "teams", "label": "Teams", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>'},
    health_check=check_teams_health,
)
