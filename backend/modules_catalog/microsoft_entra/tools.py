"""
Microsoft Entra Module — LangGraph @tool functions.
Microsoft Graph API (Azure AD / Entra ID).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.microsoft_entra.tools")

GRAPH_URL = "https://graph.microsoft.com/v1.0"


async def _get_token(connection_id: str = "") -> str:
    """Get access token using client credentials flow."""
    if connection_id:
        conn = await ConnectionManager.get_connection("microsoft_entra", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Entra-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Entra connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("microsoft_entra")

    if conn:
        tenant_id = conn.config.get("tenant_id", "")
        client_id = conn.config.get("client_id", "")
        vault = get_vault()
        client_secret = None
        secret_path = conn.vault_keys.get("ENTRA_CLIENT_SECRET")
        if secret_path:
            client_secret = await vault.get_secret(secret_path)
        if not client_secret:
            client_secret = os.environ.get("ENTRA_CLIENT_SECRET", "")
    else:
        tenant_id = os.environ.get("ENTRA_TENANT_ID", "")
        client_id = os.environ.get("ENTRA_CLIENT_ID", "")
        vault = get_vault()
        client_secret = await vault.get_secret("ENTRA_CLIENT_SECRET")

    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            _t(
                de="Keine Entra-Verbindung konfiguriert.",
                en="No Entra connection configured.",
            )
        )

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


async def _graph_request(
    method: str, path: str, token: str, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to Microsoft Graph."""
    url = f"{GRAPH_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        async with session.request(method, url, json=json) as resp:
            if resp.status == 204:
                return {"status": "OK"}
            resp.raise_for_status()
            return await resp.json()


# ═══════════════════════════════════════════════════════
# Read-only tools
# ════════════════════════════════════════════════��══════


@tool
async def list_entra_users(connection_id: str = "") -> str:
    """
    List users in Microsoft Entra ID.
    Use this to get all users or search for specific users.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/users", token)
        users = data.get("value", [])
        if not users:
            return _t(de="Keine Benutzer gefunden", en="No users found")

        lines = ["👥 " + _t(de="Benutzer", en="Users")]
        for u in users[:15]:
            enabled = "✅" if u.get("accountEnabled", True) else "❌"
            lines.append(
                f"  {enabled} {u.get('displayName', '-')} <{u.get('userPrincipalName', '-')}>"
            )

        total = data.get("@odata.nextLink")
        count = len(users)
        if total:
            lines.append(f"\n💡 {count}+ Benutzer (sehe nach mehr)")
        else:
            lines.append(f"\n✓ {count} Benutzer gesamt")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_entra_users failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def search_entra_user(query: str, connection_id: str = "") -> str:
    """
    Search for a user by name or email.
    Use this when looking for a specific user.
    """
    try:
        token = await _get_token(connection_id)
        filter_escape = query.replace("'", "''")
        data = await _graph_request(
            "GET",
            f"/users?$filter=startswith(displayName,'{filter_escape}') or startswith(mail,'{filter_escape}') or startswith(userPrincipalName,'{filter_escape}')&$top=10",
            token,
        )
        users = data.get("value", [])
        if not users:
            return _t(
                de=f"Kein Benutzer gefunden für '{query}'",
                en=f"No user found for '{query}'",
            )

        lines = [f"🔍 " + _t(de="Suchergebnisse", en="Search results") + f" '{query}'"]
        for u in users:
            enabled = "✅" if u.get("accountEnabled", True) else "❌"
            lines.append(
                f"  {enabled} {u.get('displayName', '-')}\n    {u.get('userPrincipalName', '-')}"
            )
            if u.get("jobTitle"):
                lines.append(f"    📋 {u.get('jobTitle')}")
            if u.get("department"):
                lines.append(f"    🏢 {u.get('department')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("search_entra_user failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_user_details(user_principal_name: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific user.
    Use this to get full user details including manager, device, licenses.
    """
    try:
        token = await _get_token(connection_id)
        user_id = user_principal_name.replace("@", "_").replace(".", "_")
        user = await _graph_request("GET", f"/users/{user_id}", token)

        lines = ["👤 " + _t(de="Benutzerdetails", en="User details")]
        lines.append(f"  {user.get('displayName', '-')}")
        lines.append(f"  📧 {user.get('userPrincipalName', '-')}")
        if user.get("mail"):
            lines.append(f"  📫 {user.get('mail')}")
        if user.get("jobTitle"):
            lines.append(f"  📋 {user.get('jobTitle')}")
        if user.get("department"):
            lines.append(f"  🏢 {user.get('department')}")
        if user.get("officeLocation"):
            lines.append(f"  📍 {user.get('officeLocation')}")

        status = "✅ Aktiv" if user.get("accountEnabled") else "❌ Deaktiviert"
        lines.append(f"  Status: {status}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_user_details failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_entra_groups(connection_id: str = "") -> str:
    """
    List groups in Microsoft Entra ID.
    Use this to get all groups or security groups.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/groups", token)
        groups = data.get("value", [])
        if not groups:
            return _t(de="Keine Gruppen gefunden", en="No groups found")

        lines = ["👥 " + _t(de="Gruppen", en="Groups")]
        for g in groups[:15]:
            sec = "🔒" if g.get("securityEnabled") else "📧"
            dyn = "⚡" if "DynamicMembership" in g.get("groupTypes", []) else ""
            lines.append(f"  {sec}{dyn} {g.get('displayName', '-')}")

        count = len(groups)
        lines.append(f"\n✓ {count} Gruppen gesamt")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_entra_groups failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_group_members(group_name: str, connection_id: str = "") -> str:
    """
    Get members of a specific group.
    Use this to see who belongs to a group.
    """
    try:
        token = await _get_token(connection_id)
        search = f"/groups?$filter=startswith(displayName,'{group_name}')"
        data = await _graph_request("GET", search, token)
        groups = data.get("value", [])
        if not groups:
            return _t(
                de=f"Gruppe nicht gefunden: {group_name}",
                en=f"Group not found: {group_name}",
            )

        group = groups[0]
        group_id = group["id"]

        members = await _graph_request("GET", f"/groups/{group_id}/members", token)
        mems = members.get("value", [])
        if not mems:
            return _t(
                de=f"Keine Mitglieder in '{group.get('displayName')}'",
                en=f"No members in '{group.get('displayName')}'",
            )

        lines = [
            f"👥 "
            + _t(de="Gruppenmitglieder", en="Group members")
            + f": {group.get('displayName')}"
        ]
        for m in mems:
            obj_type = m.get("@odata.type", "#microsoft.graphirectoryObject")
            if "user" in obj_type.lower():
                icon = "👤"
            elif "group" in obj_type.lower():
                icon = "👥"
            else:
                icon = "📦"
            lines.append(f"  {icon} {m.get('displayName', '-')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_group_members failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_entra_applications(connection_id: str = "") -> str:
    """
    List registered applications in Entra ID.
    Use this to see all Azure AD applications.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/applications", token)
        apps = data.get("value", [])
        if not apps:
            return _t(de="Keine Anwendungen gefunden", en="No applications found")

        lines = ["📱 " + _t(de="Anwendungen", en="Applications")]
        for a in apps[:15]:
            lines.append(f"  • {a.get('displayName', '-')}")
            if a.get("publisherDomain"):
                lines.append(f"    Herausgeber: {a.get('publisherDomain')}")

        count = len(apps)
        lines.append(f"\n✓ {count} Anwendungen gesamt")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_entra_applications failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_entra_devices(connection_id: str = "") -> str:
    """
    List registered devices in Entra ID.
    Use this to see all devices registered in the tenant.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/devices", token)
        devices = data.get("value", [])
        if not devices:
            return _t(de="Keine Geräte gefunden", en="No devices found")

        lines = ["💻 " + _t(de="Geräte", en="Devices")]
        for d in devices[:15]:
            os = d.get("operatingSystem", "-")
            compliant = "✅" if d.get("isCompliant") else "❌"
            lines.append(f"  {compliant} {d.get('displayName', '-')} ({os})")

        count = len(devices)
        lines.append(f"\n✓ {count} Geräte gesamt")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_entra_devices failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def create_entra_user(
    display_name: str,
    user_principal_name: str,
    password: str,
    connection_id: str = "",
) -> str:
    """
    Create a new user in Microsoft Entra ID.
    Use this to create a new user account.
    """
    try:
        token = await _get_token(connection_id)
        user_data = {
            "accountEnabled": True,
            "displayName": display_name,
            "mailNickname": display_name.replace(" ", ""),
            "userPrincipalName": user_principal_name,
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password": password,
            },
        }
        result = await _graph_request("POST", "/users", token, json=user_data)
        return _t(
            de=f"✅ Benutzer erstellt: {result.get('userPrincipalName')}",
            en=f"✅ User created: {result.get('userPrincipalName')}",
        )
    except Exception as e:
        logger.error("create_entra_user failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def disable_entra_user(user_principal_name: str, connection_id: str = "") -> str:
    """
    Disable a user account.
    Use this to disable a user's access.
    """
    try:
        token = await _get_token(connection_id)
        user_id = user_principal_name.replace("@", "_").replace(".", "_")
        await _graph_request(
            "PATCH",
            f"/users/{user_id}",
            token,
            json={"accountEnabled": False},
        )
        return _t(
            de=f"✅ Benutzer deaktiviert: {user_principal_name}",
            en=f"✅ User disabled: {user_principal_name}",
        )
    except Exception as e:
        logger.error("disable_entra_user failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def reset_entra_user_password(
    user_principal_name: str,
    new_password: str,
    connection_id: str = "",
) -> str:
    """
    Reset a user's password.
    Use this to reset a user's password.
    """
    try:
        token = await _get_token(connection_id)
        user_id = user_principal_name.replace("@", "_").replace(".", "_")
        await _graph_request(
            "PATCH",
            f"/users/{user_id}",
            token,
            json={
                "passwordProfile": {
                    "forceChangePasswordNextSignIn": False,
                    "password": new_password,
                }
            },
        )
        return _t(
            de=f"✅ Passwort zurückgesetzt für: {user_principal_name}",
            en=f"✅ Password reset for: {user_principal_name}",
        )
    except Exception as e:
        logger.error("reset_entra_user_password failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def create_entra_group(
    display_name: str,
    description: str = "",
    security_enabled: bool = True,
    connection_id: str = "",
) -> str:
    """
    Create a new security group.
    Use this to create a new group.
    """
    try:
        token = await _get_token(connection_id)
        group_data = {
            "displayName": display_name,
            "description": description,
            "mailEnabled": False,
            "securityEnabled": security_enabled,
        }
        result = await _graph_request("POST", "/groups", token, json=group_data)
        return _t(
            de=f"✅ Gruppe erstellt: {result.get('displayName')}",
            en=f"✅ Group created: {result.get('displayName')}",
        )
    except Exception as e:
        logger.error("create_entra_group failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def add_user_to_group(
    user_principal_name: str,
    group_name: str,
    connection_id: str = "",
) -> str:
    """
    Add a user to a group.
    Use this to add a user to a security group.
    """
    try:
        token = await _get_token(connection_id)

        search = f"/groups?$filter=displayName eq '{group_name}'"
        data = await _graph_request("GET", search, token)
        groups = data.get("value", [])
        if not groups:
            return _t(
                de=f"Gruppe nicht gefunden: {group_name}",
                en=f"Group not found: {group_name}",
            )

        group_id = groups[0]["id"]

        user_id = user_principal_name.replace("@", "_").replace(".", "_")
        await _graph_request(
            "POST",
            f"/groups/{group_id}/members/$ref",
            token,
            json={
                "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"
            },
        )
        return _t(
            de=f"✅ Benutzer zur Gruppe hinzugefügt: {user_principal_name} → {group_name}",
            en=f"✅ User added to group: {user_principal_name} → {group_name}",
        )
    except Exception as e:
        logger.error("add_user_to_group failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
