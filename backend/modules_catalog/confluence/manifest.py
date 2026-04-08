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
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="8" y1="13" x2="16" y2="13"/><line x1="8" y1="17" x2="13" y2="17"/></svg>',
    },
    health_check=check_confluence_health,
)
