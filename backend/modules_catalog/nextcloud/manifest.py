"""
Nextcloud Module – Manifest.

File Sync, Share, and Collaboration.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.nextcloud")


async def check_nextcloud_health() -> dict:
    """Health check for Nextcloud API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("nextcloud")
        if not conn:
            host = os.environ.get("NEXTCLOUD_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            user = os.environ.get("NEXTCLOUD_USER", "")
            vault = get_vault()
            password = await vault.get_secret("NEXTCLOUD_PASSWORD")
            if not user or not password:
                return {"status": "error", "detail": "Missing credentials"}

            async with aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(user, password),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(
                    f"{host.rstrip('/')}/ocs/v2.php/cloud/capabilities"
                ) as resp:
                    if resp.status == 200:
                        return {
                            "status": "ok",
                            "detail": f"Nextcloud reachable at {host}",
                        }
                    return {"status": "error", "detail": f"HTTP {resp.status}"}

        base_url = conn.config.get("url", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("NEXTCLOUD_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("NEXTCLOUD_PASSWORD", "")

        if not base_url or not user or not password:
            return {"status": "error", "detail": "Missing config"}

        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(user, password),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(
                f"{base_url.rstrip('/')}/ocs/v2.php/cloud/capabilities"
            ) as resp:
                if resp.status == 200:
                    return {"status": "ok", "detail": "Nextcloud reachable"}
                return {"status": "error", "detail": f"HTTP {resp.status}"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="nextcloud",
    display_name="Nextcloud",
    description=(
        "Nextcloud / OwnCloud: file sync and share, files, folders, shares, "
        "users, collaboration, cloud storage."
    ),
    version="1.0.1",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="NEXTCLOUD_",
    required_secrets=["NEXTCLOUD_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "nextcloud",
        "next cloud",
        "fileshare",
        "file share",
        "owncloud",
        "cloud storage",
    ],
    api_prefix="/api/nextcloud",
    dashboard_tab={
        "id": "nextcloud",
        "label": "Nextcloud",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/><path d="M9 16l2 2 4-4"/></svg>',
    },
    health_check=check_nextcloud_health,
)
