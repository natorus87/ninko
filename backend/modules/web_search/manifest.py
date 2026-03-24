"""
Web Search Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations
import os
import httpx
import logging
from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.web_search")

async def check_web_search_health() -> dict:
    """Health-Check für SearXNG-Verbindung."""
    try:
        searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(searxng_url)
            
            if response.status_code == 200:
                return {
                    "status": "ok",
                    "detail": "SearXNG ist erreichbar"
                }
            else:
                return {
                    "status": "error",
                    "detail": f"SearXNG nicht erreichbar. Status Code: {response.status_code}"
                }
    except Exception as e:
        return {"status": "error", "detail": f"SearXNG nicht erreichbar: {e}"}

module_manifest = ModuleManifest(
    name="web_search",
    display_name="Web Search",
    description="Ermöglicht der KI Web-Suchen über eine lokale SearXNG-Instanz durchzuführen.",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="NINKO_MODULE_WEB_SEARCH", 
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "suche", "internet", "web", "googeln", "web search", "searxng", "news", "nachrichten",
        "aktueller preis", "aktuelle kurse", "aktuelle news", "was kostet", "wie teuer"
    ],
    api_prefix="/api/web-search",
    dashboard_tab={
        "id": "web_search",
        "label": "Web Search",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
    },
    health_check=check_web_search_health,
)
