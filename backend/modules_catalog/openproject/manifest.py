"""
OpenProject Module – Manifest.

Project Management and Team Collaboration.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.openproject")


async def check_openproject_health() -> dict:
    """Health check for OpenProject API."""
    try:
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

            async with aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(f"{host.rstrip('/')}/api/v3") as resp:
                    if resp.status == 200:
                        return {
                            "status": "ok",
                            "detail": f"OpenProject reachable at {host}",
                        }
                    return {"status": "error", "detail": f"HTTP {resp.status}"}

        base_url = conn.config.get("url", "")
        api_key = conn.config.get("api_key", "")
        if not api_key:
            vault = get_vault()
            vault_key = conn.vault_keys.get("OPENPROJECT_API_KEY")
            if vault_key:
                api_key = await vault.get_secret(vault_key)

        if not base_url or not api_key:
            return {"status": "error", "detail": "Missing config"}

        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(f"{base_url.rstrip('/')}/api/v3") as resp:
                if resp.status == 200:
                    return {"status": "ok", "detail": "OpenProject reachable"}
                return {"status": "error", "detail": f"HTTP {resp.status}"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="openproject",
    display_name="OpenProject",
    description="OpenProject Enterprise – Project Management, Tasks, Time Tracking, and Team Collaboration.",
    version="1.0.0",
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
        "icon": "📊",
    },
    health_check=check_openproject_health,
)
