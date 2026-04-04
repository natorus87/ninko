"""
Microsoft Intune Module – Manifest.

Mobile Device Management (MDM) via Microsoft Graph API.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.microsoft_intune")


async def check_microsoft_intune_health() -> dict:
    """Health check for Microsoft Intune API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("microsoft_intune")
        if not conn:
            tenant_id = os.environ.get("INTUNE_TENANT_ID", "")
            if not tenant_id:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            client_id = os.environ.get("INTUNE_CLIENT_ID", "")
            vault = get_vault()
            client_secret = await vault.get_secret("INTUNE_CLIENT_SECRET")
            if not client_id or not client_secret:
                return {"status": "error", "detail": "Missing credentials"}

            token = await _get_token(tenant_id, client_id, client_secret)
            async with aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(
                    "https://graph.microsoft.com/beta/deviceManagement/managedDevices"
                ) as resp:
                    return {"status": "ok", "detail": "Intune API reachable (Env)"}

        tenant_id = conn.config.get("tenant_id", "")
        client_id = conn.config.get("client_id", "")
        vault = get_vault()
        client_secret = None
        secret_path = conn.vault_keys.get("INTUNE_CLIENT_SECRET")
        if secret_path:
            client_secret = await vault.get_secret(secret_path)

        if not tenant_id or not client_id or not client_secret:
            return {"status": "error", "detail": "Missing config"}

        token = await _get_token(tenant_id, client_id, client_secret)
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(
                "https://graph.microsoft.com/beta/deviceManagement/managedDevices"
            ) as resp:
                return {"status": "ok", "detail": "Intune API reachable"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}


async def _get_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Get access token using client credentials flow."""
    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["access_token"]


module_manifest = ModuleManifest(
    name="microsoft_intune",
    display_name="Microsoft Intune",
    description="Microsoft Intune MDM – Mobile Device Management, Policies, Apps, and Compliance.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="INTUNE_",
    required_secrets=["INTUNE_CLIENT_SECRET"],
    optional_secrets=[],
    routing_keywords=[
        "intune",
        "mdm",
        "mobile device",
        "device management",
        "endpoint manager",
        "mem",
        "endpoint management",
        "device compliance",
        "device policy",
    ],
    api_prefix="/api/microsoft_intune",
    dashboard_tab={
        "id": "microsoft_intune",
        "label": "Intune",
        "icon": "📱",
    },
    health_check=check_microsoft_intune_health,
)
