"""
Microsoft Entra ID Module – Manifest.

Formerly Azure Active Directory (Azure AD).
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.microsoft_entra")


async def check_microsoft_entra_health() -> dict:
    """Health check for Microsoft Graph API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("microsoft_entra")
        if not conn:
            tenant_id = os.environ.get("ENTRA_TENANT_ID", "")
            if not tenant_id:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            client_id = os.environ.get("ENTRA_CLIENT_ID", "")
            vault = get_vault()
            client_secret = await vault.get_secret("ENTRA_CLIENT_SECRET")
            if not client_id or not client_secret:
                return {"status": "error", "detail": "Missing credentials in Vault"}

            token = await _get_token_client_credentials(
                tenant_id, client_id, client_secret
            )
            async with aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(
                    "https://graph.microsoft.com/v1.0/$delta?$deltaToken=latest"
                ) as resp:
                    return {
                        "status": "ok",
                        "detail": "Microsoft Graph API reachable (Env)",
                    }

        tenant_id = conn.config.get("tenant_id", "")
        client_id = conn.config.get("client_id", "")
        vault = get_vault()
        client_secret = None
        secret_path = conn.vault_keys.get("ENTRA_CLIENT_SECRET")
        if secret_path:
            client_secret = await vault.get_secret(secret_path)

        if not tenant_id or not client_id or not client_secret:
            return {"status": "error", "detail": "Missing config"}

        token = await _get_token_client_credentials(tenant_id, client_id, client_secret)
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get(
                "https://graph.microsoft.com/v1.0/$delta?$deltaToken=latest"
            ) as resp:
                return {"status": "ok", "detail": "Microsoft Graph API reachable"}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


async def _get_token_client_credentials(
    tenant_id: str, client_id: str, client_secret: str
) -> str:
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
    name="microsoft_entra",
    display_name="Microsoft Entra",
    description="Microsoft Entra ID (formerly Azure AD) – Users, Groups, Applications, and Identity Management.",
    version="1.0.1",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="ENTRA_",
    required_secrets=["ENTRA_CLIENT_SECRET"],
    optional_secrets=[],
    routing_keywords=[
        "entra",
        "azure ad",
        "microsoft identity",
        "office 365",
        "microsoft 365",
        "o365",
        "azure portal",
        "ms identity",
    ],
    api_prefix="/api/microsoft_entra",
    dashboard_tab={
        "id": "microsoft_entra",
        "label": "Entra ID",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><circle cx="12" cy="10" r="2"/><path d="M8 16c0-2.2 1.8-4 4-4s4 1.8 4 4"/></svg>',
    },
    health_check=check_microsoft_entra_health,
)
