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
    version="1.0.0",
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
        "icon": "🔀",
    },
    health_check=check_cisco_health,
)
