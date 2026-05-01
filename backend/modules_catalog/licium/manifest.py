"""
Licium module — Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.licium")


async def check_licium_health(connection_id: str = "") -> dict:
    """Health check für Licium API."""
    try:
        import httpx
        from core.connections import ConnectionManager
        from core.vault import get_vault
        from core.tls import get_connection_verify_arg

        vault = get_vault()
        conn = await ConnectionManager.get_default_connection("licium")

        if conn:
            base_url = conn.config.get("base_url", "").rstrip("/")
            username = conn.config.get("username", "")
            pw_key = conn.vault_keys.get("LICIUM_PASSWORD", "")
            password = await vault.get_secret(pw_key) if pw_key else ""
        else:
            import os
            base_url = os.environ.get("LICIUM_BASE_URL", "").rstrip("/")
            username = os.environ.get("LICIUM_USERNAME", "")
            password = os.environ.get("LICIUM_PASSWORD", "")

        if not base_url:
            return {"status": "error", "detail": "LICIUM_BASE_URL not configured"}
        if not username or not password:
            return {"status": "error", "detail": "Licium credentials not configured"}

        verify_arg = await get_connection_verify_arg(conn, "licium", default_verify=True)
        async with httpx.AsyncClient(base_url=base_url, verify=verify_arg, timeout=10.0) as client:
            resp = await client.post("/api/login", json={"username": username, "password": password})
            if resp.status_code == 200:
                info_resp = await client.get("/api/system/info")
                info = info_resp.json() if info_resp.status_code == 200 else {}
                return {
                    "status": "ok",
                    "detail": f"Licium reachable (v{info.get('version', '?')})",
                }
            return {"status": "error", "detail": f"Login failed: HTTP {resp.status_code}"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="licium",
    display_name="Licium Wiki",
    description="Licium Wissensdatenbank – Notizen erstellen, semantisch suchen, Inhalte strukturieren und als LLM-Wiki verwalten (Karpathy-Pattern: Ingest, Query, Lint).",
    version="1.0.1",
    author="Ninko Team",
    enabled_by_default=False,
    env_prefix="LICIUM_",
    required_secrets=["LICIUM_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "licium", "wiki", "wissensdatenbank", "knowledge base", "notiz", "notizen",
        "knowledge", "wissen", "second brain", "ingest", "dokumentation", "artikel",
        "semantic search", "semantisch", "wiki seite", "wiki-seite",
    ],
    api_prefix="/api/licium",
    dashboard_tab={
        "id": "licium",
        "label": "Licium Wiki",
        "icon": '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>',
    },
    health_check=check_licium_health,
)
