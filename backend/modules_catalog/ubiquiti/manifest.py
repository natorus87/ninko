"""
Ubiquiti Module – Manifest.

UniFi devices – Switches, Routers, Access Points.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.ubiquiti")


async def check_ubiquiti_health() -> dict:
    """Health check for UniFi Controller API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("ubiquiti")
        if not conn:
            host = os.environ.get("UNIFI_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            user = os.environ.get("UNIFI_USER", "")
            vault = get_vault()
            password = await vault.get_secret("UNIFI_PASSWORD")
            if not user or not password:
                return {"status": "error", "detail": "Missing credentials"}

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                login = await session.post(
                    f"https://{host}/api/login",
                    json={"username": user, "password": password},
                    ssl=False,
                )
                if login.status == 200:
                    return {"status": "ok", "detail": f"UniFi reachable at {host}"}
                return {"status": "error", "detail": f"HTTP {login.status}"}

        host = conn.config.get("host", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("UNIFI_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("UNIFI_PASSWORD", "")

        if not host or not user or not password:
            return {"status": "error", "detail": "Missing config"}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            login = await session.post(
                f"https://{host}/api/login",
                json={"username": user, "password": password},
                ssl=False,
            )
            if login.status == 200:
                return {"status": "ok", "detail": "UniFi reachable"}
            return {"status": "error", "detail": f"HTTP {login.status}"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="ubiquiti",
    display_name="Ubiquiti",
    description="Ubiquiti UniFi – Switches, Routers, Access Points – Device Status, Clients, Traffic, and WLAN Management.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="UNIFI_",
    required_secrets=["UNIFI_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "ubiquiti",
        "unifi",
        "unifi switch",
        "unifi router",
        "unifi ap",
        "unifi access point",
        "edgerouter",
        "edgeswitch",
        "airmax",
    ],
    api_prefix="/api/ubiquiti",
    dashboard_tab={
        "id": "ubiquiti",
        "label": "Ubiquiti",
        "icon": "📡",
    },
    health_check=check_ubiquiti_health,
)
