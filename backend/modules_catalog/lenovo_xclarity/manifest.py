"""
Lenovo XClarity Module – Manifest.

Lenovo XClarity Administrator for ThinkSystem/ThinkBlade server management.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.lenovo_xclarity")


async def check_lenovo_xclarity_health() -> dict:
    """Health check for Lenovo XClarity API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("lenovo_xclarity")
        if not conn:
            host = os.environ.get("XCLARITY_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            user = os.environ.get("XCLARITY_USER", "admin")
            vault = get_vault()
            password = await vault.get_secret("XCLARITY_PASSWORD")
            if not password:
                return {
                    "status": "error",
                    "detail": "XCLARITY_PASSWORD not found in Vault",
                }

            async with aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(user, password),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(f"https://{host}/api/login") as resp:
                    if resp.status == 204:
                        return {
                            "status": "ok",
                            "detail": f"XClarity reachable at {host}",
                        }
                    return {"status": "error", "detail": f"HTTP {resp.status}"}

        base_url = conn.config.get("url", "")
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("XCLARITY_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("XCLARITY_PASSWORD", "")

        if not base_url or not password:
            return {"status": "error", "detail": "Missing config"}

        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(user, password),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(f"{base_url.rstrip('/')}/api/login") as resp:
                if resp.status == 204:
                    return {"status": "ok", "detail": "XClarity reachable"}
                return {"status": "error", "detail": f"HTTP {resp.status}"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="lenovo_xclarity",
    display_name="Lenovo XClarity",
    description="Lenovo XClarity Administrator – ThinkSystem/ThinkBlade Server Management, Monitoring, and Firmware Updates.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="XCLARITY_",
    required_secrets=["XCLARITY_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "xclarity",
        "lenovo",
        "lenovo xclarity",
        "think system",
        "thinkblade",
        "lenovo server",
        "lenovo bmc",
    ],
    api_prefix="/api/lenovo_xclarity",
    dashboard_tab={
        "id": "lenovo_xclarity",
        "label": "XClarity",
        "icon": "🖥️",
    },
    health_check=check_lenovo_xclarity_health,
)
