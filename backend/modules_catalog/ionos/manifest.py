"""
IONOS DNS Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.ionos")


async def check_ionos_health() -> dict:
    """Health-Check für IONOS-Verbindung."""
    try:
        from modules.ionos.tools import _ionos_request

        result = await _ionos_request("GET", "zones")
        if isinstance(result, list):
            zone_count = len(result)
        else:
            zone_count = 0
            
        return {
            "status": "ok",
            "detail": f"IONOS verbunden, {zone_count} Zonen gefunden",
        }
    except Exception as e:
        return {"status": "error", "detail": f"IONOS API nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="ionos",
    display_name="IONOS DNS",
    description="IONOS DNS Zonen und Records Management.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=True,
    env_prefix="IONOS_",
    required_secrets=[],
    optional_secrets=["IONOS_API_KEY"],
    routing_keywords=[
        "ionos", "dns", "zone", "domain", "record", "cname", "a record", "txt record", "ionos api"
    ],
    api_prefix="/api/ionos",
    dashboard_tab={"id": "ionos", "label": "IONOS", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path><path d="M2 12h20"></path></svg>'},
    health_check=check_ionos_health,
)
