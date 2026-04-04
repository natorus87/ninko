"""
MikroTik Module – Manifest.

MikroTik RouterOS devices – Switches, Routers, Wireless.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.mikrotik")


async def check_mikrotik_health() -> dict:
    """Health check for MikroTik API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("mikrotik")
        if not conn:
            host = os.environ.get("MIKROTIK_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            user = os.environ.get("MIKROTIK_USER", "admin")
            vault = get_vault()
            password = await vault.get_secret("MIKROTIK_PASSWORD")
            if not password:
                return {"status": "error", "detail": "Missing password"}

            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                resp = await session.post(
                    f"https://{host}/rest/login",
                    json=[user, password, ""],
                    ssl=False,
                )
                if resp.status == 201:
                    return {"status": "ok", "detail": f"MikroTik reachable at {host}"}
                return {"status": "error", "detail": f"HTTP {resp.status}"}

        host = conn.config.get("host", "")
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("MIKROTIK_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("MIKROTIK_PASSWORD", "")

        if not host or not password:
            return {"status": "error", "detail": "Missing config"}

        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            resp = await session.post(
                f"https://{host}/rest/login",
                json=[user, password, ""],
                ssl=False,
            )
            if resp.status == 201:
                return {"status": "ok", "detail": "MikroTik reachable"}
            return {"status": "error", "detail": f"HTTP {resp.status}"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="mikrotik",
    display_name="MikroTik",
    description="MikroTik RouterOS – Switches, Routers, Wireless – Interface Status, Routing, Firewall, and Queue Management.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="MIKROTIK_",
    required_secrets=["MIKROTIK_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "mikrotik",
        "routeros",
        "router board",
        "mikrotik router",
        "mikrotik switch",
        "wireguard",
        "wireless",
        "capsman",
    ],
    api_prefix="/api/mikrotik",
    dashboard_tab={
        "id": "mikrotik",
        "label": "MikroTik",
        "icon": "📡",
    },
    health_check=check_mikrotik_health,
)
