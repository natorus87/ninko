"""
Netgear Module – Manifest.

Netgear Switches, Routers, and Access Points.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.netgear")


async def check_netgear_health() -> dict:
    """Health check for Netgear API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("netgear")
        if not conn:
            host = os.environ.get("NETGEAR_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            user = os.environ.get("NETGEAR_USER", "admin")
            vault = get_vault()
            password = await vault.get_secret("NETGEAR_PASSWORD")
            if not password:
                return {"status": "error", "detail": "Missing password"}

            auth = aiohttp.BasicAuth(user, password)
            async with aiohttp.ClientSession(
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(f"http://{host}/sysinfo") as resp:
                    if resp.status == 200:
                        return {
                            "status": "ok",
                            "detail": f"Netgear reachable at {host}",
                        }
                    return {"status": "error", "detail": f"HTTP {resp.status}"}

        host = conn.config.get("host", "")
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("NETGEAR_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("NETGEAR_PASSWORD", "")

        if not host or not password:
            return {"status": "error", "detail": "Missing config"}

        auth = aiohttp.BasicAuth(user, password)
        async with aiohttp.ClientSession(
            auth=auth,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(f"http://{host}/sysinfo") as resp:
                if resp.status == 200:
                    return {"status": "ok", "detail": "Netgear reachable"}
                return {"status": "error", "detail": f"HTTP {resp.status}"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="netgear",
    display_name="Netgear",
    description=(
        "Netgear network devices: ProSafe switches (GS108, GS110, GS116), "
        "routers, access points. Port status, VLANs, traffic management."
    ),
    version="1.0.2",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="NETGEAR_",
    required_secrets=["NETGEAR_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "netgear",
        "netgear switch",
        "netgear router",
        "netgear ap",
        "netgear access point",
        "gs108",
        "gs110",
        "gs116",
        "prosafe",
    ],
    api_prefix="/api/netgear",
    dashboard_tab={
        "id": "netgear",
        "label": "Netgear",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"/><path d="M1.42 9a16 16 0 0 1 21.16 0"/><path d="M8.53 16.11a6 6 0 0 1 6.95 0"/><circle cx="12" cy="20" r="1" fill="currentColor" stroke="none"/></svg>',
    },
    health_check=check_netgear_health,
)
