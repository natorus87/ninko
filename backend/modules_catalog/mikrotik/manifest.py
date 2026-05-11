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
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="mikrotik",
    display_name="MikroTik",
    description=(
        "MikroTik RouterOS / RouterBoard: switches, routers, wireless. "
        "Interface status, routing, firewall, queues, WireGuard, CAPsMAN."
    ),
    version="1.0.1",
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
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="8" rx="2"/><circle cx="7.5" cy="12" r="1.5" fill="currentColor" stroke="none"/><path d="M13 10h5"/><path d="M13 14h5"/><path d="M8 8V4l4-2 4 2v4"/><path d="M8 16v4"/><path d="M16 16v4"/></svg>',
    },
    health_check=check_mikrotik_health,
)
