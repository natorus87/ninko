"""
Cisco Network Devices Module – Manifest.

Cisco Switches, Routers, and Nexus devices management.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.cisco")


async def check_cisco_health() -> dict:
    """Health check for Cisco device API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("cisco")
        if not conn:
            host = os.environ.get("CISCO_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            user = os.environ.get("CISCO_USER", "")
            vault = get_vault()
            password = await vault.get_secret("CISCO_PASSWORD")
            if not user or not password:
                return {"status": "error", "detail": "Missing credentials"}

            async with aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(user, password),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(f"https://{host}/api/versions") as resp:
                    if resp.status == 200:
                        return {
                            "status": "ok",
                            "detail": f"Cisco device reachable at {host}",
                        }
                    return {"status": "error", "detail": f"HTTP {resp.status}"}

        host = conn.config.get("host", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("CISCO_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("CISCO_PASSWORD", "")

        if not host or not user or not password:
            return {"status": "error", "detail": "Missing config"}

        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(user, password),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(f"https://{host}/api/versions") as resp:
                if resp.status == 200:
                    return {"status": "ok", "detail": "Cisco device reachable"}
                return {"status": "error", "detail": f"HTTP {resp.status}"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="cisco",
    display_name="Cisco",
    description="Cisco Network Devices – Switches, Routers, Nexus – Interface Status, VLANs, Routing, and Port Management.",
    version="1.0.1",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="CISCO_",
    required_secrets=["CISCO_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "cisco",
        "switch",
        "router",
        "cisco switch",
        "cisco router",
        "ios",
        "nexus",
        "catalyst",
        "network port",
        "vlan",
    ],
    api_prefix="/api/cisco",
    dashboard_tab={
        "id": "cisco",
        "label": "Cisco",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="8" width="18" height="8" rx="2"/><circle cx="7.5" cy="12" r="1.5" fill="currentColor" stroke="none"/><circle cx="11.5" cy="12" r="1.5" fill="currentColor" stroke="none"/><path d="M16 10h3"/><path d="M16 14h3"/><path d="M7.5 8V5"/><path d="M12 8V5"/><path d="M16.5 8V5"/><path d="M7.5 16v3"/><path d="M16.5 16v3"/></svg>',
    },
    health_check=check_cisco_health,
)
