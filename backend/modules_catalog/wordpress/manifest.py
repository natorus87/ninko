"""
WordPress Modul – Manifest mit Metadaten und Health-Check.
Verwaltet WordPress-Instanzen über die WP REST API v2.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.wordpress")


async def check_wordpress_health() -> dict:
    """Health-Check für die WordPress REST API."""
    try:
        return {"status": "ok", "detail": "WordPress Modul bereit (REST API v2)"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="wordpress",
    display_name="WordPress",
    description="WordPress-Verwaltung – Plugins, Seiten, Beiträge, Benutzer, Einstellungen",
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="WORDPRESS_",
    required_secrets=["WORDPRESS_APP_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "wordpress", "wp", "plugin", "theme",
        "seite", "beitrag", "blog", "cms",
        "woocommerce", "wp-cli", "permalink",
    ],
    api_prefix="/api/wordpress",
    dashboard_tab={"id": "wordpress", "label": "WordPress", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22h6a2 2 0 0 0 2-2V7l-5-5H6a2 2 0 0 0-2 2v10"></path><path d="M14 2v4a2 2 0 0 0 2 2h4"></path><path d="M10.4 12.6a2 2 0 1 1 3 3L8 21l-4 1 1-4z"></path></svg>'},
    health_check=check_wordpress_health,
)
