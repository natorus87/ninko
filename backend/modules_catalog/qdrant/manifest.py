"""
Qdrant Module — Manifest with metadata and health check.
"""

from __future__ import annotations

import logging
import os

import httpx

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.qdrant")


async def check_qdrant_health() -> dict:
    """Health check for Qdrant connection."""
    from core.connections import ConnectionManager

    try:
        conn = await ConnectionManager.get_default_connection("qdrant")
        if conn:
            url = conn.config.get("url", "").rstrip("/")
        else:
            url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")

        if not url:
            return {"status": "error", "detail": "No Qdrant URL configured"}

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/healthz")
            if response.status_code == 200:
                return {"status": "ok", "detail": f"Qdrant reachable ({url})"}
            return {
                "status": "error",
                "detail": f"Qdrant responded with HTTP {response.status_code}",
            }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": f"Qdrant not reachable: {exc}"}


module_manifest = ModuleManifest(
    name="qdrant",
    display_name="Qdrant Knowledge Bank",
    description=(
        "Qdrant knowledge bank: central AI knowledge base for IT documentation, "
        "runbooks, and reference content. Semantic vector search with payload "
        "filtering by category and tags."
    ),
    version="1.1.3",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="NINKO_MODULE_QDRANT",
    required_secrets=[],
    optional_secrets=["api_key"],
    routing_keywords=[
        "wissen", "knowledge", "wissensdatenbank", "qdrant",
        "dokumentation", "nachschlagen", "wissensbank", "fachbibliothek",
        "runbook", "runbooks", "prozessbeschreibung", "handbuch",
        "knowledge base", "wissenssuche", "fachwissen",
    ],
    api_prefix="/api/qdrant",
    dashboard_tab={
        "id": "qdrant",
        "label": "Knowledge Bank",
        "icon": (
            '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round">'
            '<ellipse cx="12" cy="5" rx="9" ry="3"></ellipse>'
            '<path d="M3 5v14c0 1.66 4.03 3 9 3s9-1.34 9-3V5"></path>'
            '<path d="M3 12c0 1.66 4.03 3 9 3s9-1.34 9-3"></path>'
            "</svg>"
        ),
    },
    health_check=check_qdrant_health,
)
