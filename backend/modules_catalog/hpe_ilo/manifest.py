"""
HPE iLO Module — Manifest for HPE Integrated Lights-Out (iLO4/iLO5).

This module supports both iLO4 and iLO5 REST APIs - they are compatible.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.hpe_ilo")


async def check_hpe_ilo_health() -> dict:
    """Health check for HPE iLO API connection."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("hpe_ilo")
        if not conn:
            host = os.environ.get("ILO_HOST", "")
            if not host:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            user = os.environ.get("ILO_USER", "Administrator")
            vault = get_vault()
            password = await vault.get_secret("ILO_PASSWORD")
            if not password:
                return {"status": "error", "detail": "ILO_PASSWORD not found in Vault"}

            async with aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(user, password),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(f"https://{host}/rest/v1", ssl=False) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    fw = data.get("Oem", {}).get("Hp", {}).get("Manager", {})
                    return {
                        "status": "ok",
                        "detail": f"iLO reachable at {host} ({fw.get('ManagerType', '?')})",
                    }

        base_url = conn.config.get("url", "")
        user = conn.config.get("user", "Administrator")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("ILO_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)

        if not password:
            password = os.environ.get("ILO_PASSWORD", "")

        if not base_url or not password:
            return {"status": "error", "detail": "Missing URL or password"}

        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(user, password),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(
                f"{base_url.rstrip('/')}/rest/v1", ssl=False
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                fw = data.get("Oem", {}).get("Hp", {}).get("Manager", {})
                return {
                    "status": "ok",
                    "detail": f"iLO reachable ({fw.get('ManagerType', '?')})",
                }

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="hpe_ilo",
    display_name="HPE iLO",
    description=(
        "HPE Integrated Lights-Out (iLO4 / iLO5): server management, "
        "BMC, IPMI for HPE servers via REST API."
    ),
    version="1.0.2",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="ILO_",
    required_secrets=["ILO_PASSWORD"],
    optional_secrets=[],
    routing_keywords=[
        "ilo",
        "hpe",
        "hpe ilo",
        "integrated lights out",
        "server-management",
        "bmc",
        "ipmi",
    ],
    api_prefix="/api/hpe_ilo",
    dashboard_tab={
        "id": "hpe_ilo",
        "label": "HPE iLO",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2"/><rect x="2" y="14" width="20" height="8" rx="2"/><circle cx="6" cy="6" r="1" fill="currentColor" stroke="none"/><line x1="10" y1="6" x2="19" y2="6"/><circle cx="6" cy="18" r="1" fill="currentColor" stroke="none"/><line x1="10" y1="18" x2="19" y2="18"/></svg>',
    },
    health_check=check_hpe_ilo_health,
)
