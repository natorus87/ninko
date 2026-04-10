"""
OpenProject Module – Manifest.

Project Management and Team Collaboration.
"""

from __future__ import annotations

import logging
import os

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.openproject")


async def check_openproject_health() -> dict:
    """Health check for OpenProject API."""
    try:
        import httpx
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("openproject")
        if not conn:
            host = os.environ.get("OPENPROJECT_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            api_key = os.environ.get("OPENPROJECT_API_KEY", "")
            if not api_key:
                vault = get_vault()
                api_key = await vault.get_secret("OPENPROJECT_API_KEY")
            if not api_key:
                return {"status": "error", "detail": "Missing API key"}

            async with httpx.AsyncClient(
                headers={"Authorization": f"Bearer {api_key}"}, timeout=10.0
            ) as client:
                resp = await client.get(f"{host.rstrip('/')}/api/v3")
                if resp.status_code == 200:
                    return {
                        "status": "ok",
                        "detail": f"OpenProject reachable at {host}",
                    }
                return {"status": "error", "detail": f"HTTP {resp.status_code}"}

        base_url = conn.config.get("url", "")
        api_key = conn.config.get("api_key", "")
        if not api_key:
            vault = get_vault()
            vault_key = conn.vault_keys.get("OPENPROJECT_API_KEY")
            if vault_key:
                api_key = await vault.get_secret(vault_key)

        if not base_url or not api_key:
            return {"status": "error", "detail": "Missing config"}

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=10.0
        ) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/v3")
            if resp.status_code == 200:
                return {"status": "ok", "detail": "OpenProject reachable"}
            return {"status": "error", "detail": f"HTTP {resp.status_code}"}

    except httpx.HTTPStatusError as e:
        return {"status": "error", "detail": f"HTTP {e.response.status_code}: {e.response.text[:100]}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="openproject",
    display_name="OpenProject",
    description="OpenProject Enterprise – Project Management, Tasks, Time Tracking, and Team Collaboration.",
    version="1.0.2",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="OPENPROJECT_",
    required_secrets=["OPENPROJECT_API_KEY"],
    optional_secrets=[],
    routing_keywords=[
        "openproject",
        "open project",
        "projektmanagement",
        "project management",
        "task management",
        "ticket",
    ],
    api_prefix="/api/openproject",
    dashboard_tab={
        "id": "openproject",
        "label": "OpenProject",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/><rect x="5" y="12" width="6" height="3" rx="1"/><rect x="5" y="17" width="9" height="1" rx="0.5"/><rect x="13" y="12" width="4" height="3" rx="1"/></svg>',
    },
    health_check=check_openproject_health,
)
