"""
Synology Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.synology")


async def check_synology_health() -> dict:
    """Health-Check für Synology DSM API."""
    try:
        from .tools import _get_api_client

        client = await _get_api_client("")
        return {"status": "ok", "detail": "Synology DSM reachable"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="synology",
    display_name="Synology NAS",
    description="Verwalte Synology NAS: System-Status, Storage, Services, Pakete und Tasks.",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="SYNOLOGY_",
    required_secrets=["SYNOLOGY_PASSWORD"],
    optional_secrets=["SYNOLOGY_API_KEY"],
    routing_keywords=[
        "synology",
        "nas",
        "diskstation",
        "dsm",
        "speicher",
        "storage",
        "raid",
        "pakete",
        "packages",
        "apps",
        "backup",
        "hyper backup",
    ],
    api_prefix="/api/synology",
    dashboard_tab={
        "id": "synology",
        "label": "Synology",
        "icon": "💾",
    },
    health_check=check_synology_health,
)
