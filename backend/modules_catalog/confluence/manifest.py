"""
Confluence Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.confluence")


async def check_confluence_health() -> dict:
    """Health-Check für Confluence API."""
    try:
        from .tools import _get_api_client

        client = await _get_api_client("")
        return {"status": "ok", "detail": "Confluence API reachable"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="confluence",
    display_name="Confluence",
    description="Atlassian Confluence Wiki – Spaces, Pages, Blog Posts, Labels und Suche.",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="CONFLUENCE_",
    required_secrets=["CONFLUENCE_API_KEY"],
    optional_secrets=[],
    routing_keywords=[
        "confluence",
        "wiki",
        "space",
        "seite",
        "page",
        "blog",
        "artikel",
        "dokument",
        "dokumentation",
    ],
    api_prefix="/api/confluence",
    dashboard_tab={
        "id": "confluence",
        "label": "Confluence",
        "icon": "📘",
    },
    health_check=check_confluence_health,
)
