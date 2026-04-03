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
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="nextcloud",
    display_name="Nextcloud",
    description="Nextcloud File Sync and Share – Files, Folders, Shares, Users, and Collaboration.",
    version="1.0.0",
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
        "icon": "☁️",
    },
    health_check=check_nextcloud_health,
)
