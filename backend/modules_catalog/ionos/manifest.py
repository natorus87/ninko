"""
IONOS DNS Module — Manifest with metadata and health check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.ionos")


async def check_ionos_health() -> dict:
    """Health check for IONOS connection."""
    try:
        from .tools import _ionos_request

        result = await _ionos_request("GET", "zones")
        if isinstance(result, list):
            zone_count = len(result)
        else:
            zone_count = 0
            
        return {
            "status": "ok",
            "detail": f"IONOS verbunden, {zone_count} Zonen gefunden",
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": f"IONOS API nicht erreichbar: {exc}"}


module_manifest = ModuleManifest(
    name="ionos",
    display_name="IONOS DNS",
    description="IONOS DNS zones and records management.",
    version="1.1.2",
    author="Ninko",
    enabled_by_default=True,
    env_prefix="IONOS_",
    required_secrets=[],
    optional_secrets=["IONOS_API_KEY"],
    routing_keywords=[
        "ionos", "ionos dns", "zone", "record", "txt record", "ionos api", "dns zone", "dns record"
    ],
    api_prefix="/api/ionos",
    dashboard_tab={"id": "ionos", "label": "IONOS", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path><path d="M2 12h20"></path></svg>'},
    health_check=check_ionos_health,
)
