"""
Qdrant Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import os

import httpx

from core.module_registry import ModuleManifest

logger = logging.getLogger("kumio.modules.qdrant")


async def check_qdrant_health() -> dict:
    """Health-Check für Qdrant-Verbindung."""
    from core.connections import ConnectionManager

    try:
        conn = await ConnectionManager.get_default_connection("qdrant")
        if conn:
            url = conn.config.get("url", "").rstrip("/")
        else:
            url = os.getenv("QDRANT_URL", "http://localhost:6333").rstrip("/")

        if not url:
            return {"status": "error", "detail": "Keine Qdrant-URL konfiguriert"}

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/healthz")
            if response.status_code == 200:
                return {"status": "ok", "detail": f"Qdrant erreichbar ({url})"}
            return {
                "status": "error",
                "detail": f"Qdrant antwortet mit HTTP {response.status_code}",
            }
    except Exception as e:
        return {"status": "error", "detail": f"Qdrant nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="qdrant",
    display_name="Qdrant Knowledge Bank",
    description=(
        "Zentrale KI-Wissensbank auf Basis von Qdrant. "
        "Speichert und durchsucht Fachwissen, IT-Dokumentation und Runbooks "
        "per semantischer Vektorsuche mit Payload-Filterung nach Kategorie und Tags."
    ),
    version="1.0.0",
    author="Kumio Team",
    enabled_by_default=False,
    env_prefix="KUMIO_MODULE_QDRANT",
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
