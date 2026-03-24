"""
GLPI Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.glpi")


async def check_glpi_health() -> dict:
    """Health-Check für GLPI-API-Verbindung."""
    try:
        import httpx
        from core.vault import get_vault

        vault = get_vault()
        base_url = os.environ.get("GLPI_BASE_URL", "")
        if not base_url:
            return {"status": "error", "detail": "GLPI_BASE_URL nicht konfiguriert"}

        app_token = await vault.get_secret("GLPI_APP_TOKEN")
        user_token = await vault.get_secret("GLPI_USER_TOKEN")

        if not app_token or not user_token:
            return {"status": "error", "detail": "GLPI Tokens nicht im Vault"}

        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.get(
                f"{base_url}/apirest.php/initSession",
                headers={
                    "App-Token": app_token,
                    "Authorization": f"user_token {user_token}",
                },
            )
            if resp.status_code == 200:
                session = resp.json().get("session_token", "")
                # Session sofort beenden
                await client.get(
                    f"{base_url}/apirest.php/killSession",
                    headers={
                        "App-Token": app_token,
                        "Session-Token": session,
                    },
                )
                return {"status": "ok", "detail": "GLPI API erreichbar"}
            else:
                return {"status": "error", "detail": f"HTTP {resp.status_code}: {resp.text[:100]}"}

    except Exception as e:
        return {"status": "error", "detail": f"GLPI nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="glpi",
    display_name="GLPI Helpdesk",
    description="GLPI Helpdesk Integration – Tickets, Incidents, SLA-Tracking",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="GLPI_",
    required_secrets=["GLPI_APP_TOKEN", "GLPI_USER_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "ticket", "incident", "helpdesk", "glpi", "störung",
        "anfrage", "support", "sla", "lösung", "followup",
        "schließen", "öffnen", "zuweisen", "melden",
    ],
    api_prefix="/api/glpi",
    dashboard_tab={"id": "glpi", "label": "Helpdesk", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 9a3 3 0 0 1 0 6v2a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-2a3 3 0 0 1 0-6V7a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"></path><path d="M13 5v2"></path><path d="M13 17v2"></path><path d="M13 11v2"></path></svg>'},
    health_check=check_glpi_health,
)
