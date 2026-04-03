"""
Microsoft Intune Module — LangGraph @tool functions.
Microsoft Intune MDM via Microsoft Graph API.
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

logger = logging.getLogger("ninko.modules.microsoft_intune.tools")

GRAPH_URL = "https://graph.microsoft.com/beta"


async def _get_token(connection_id: str = "") -> str:
    """Get access token using client credentials flow."""
    if connection_id:
        conn = await ConnectionManager.get_connection("microsoft_intune", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Intune-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Intune connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("microsoft_intune")

    if conn:
        tenant_id = conn.config.get("tenant_id", "")
        client_id = conn.config.get("client_id", "")
        vault = get_vault()
        client_secret = None
        secret_path = conn.vault_keys.get("INTUNE_CLIENT_SECRET")
        if secret_path:
            client_secret = await vault.get_secret(secret_path)
        if not client_secret:
            client_secret = os.environ.get("INTUNE_CLIENT_SECRET", "")
    else:
        tenant_id = os.environ.get("INTUNE_TENANT_ID", "")
        client_id = os.environ.get("INTUNE_CLIENT_ID", "")
        vault = get_vault()
        client_secret = await vault.get_secret("INTUNE_CLIENT_SECRET")

    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            _t(
                de="Keine Intune-Verbindung konfiguriert.",
                en="No Intune connection configured.",
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
# ═══════════════════════════════════════════════════════


@tool
async def list_intune_devices(connection_id: str = "") -> str:
    """
    List managed devices in Intune.
    Use this to get all enrolled devices.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceManagement/managedDevices?$top=50",
            token,
        )
        devices = data.get("value", [])
        if not devices:
            return _t(de="Keine Geräte gefunden", en="No devices found")

        lines = ["📱 " + _t(de="Verwaltete Geräte", en="Managed devices")]
        for d in devices[:15]:
            os = d.get("operatingSystem", "-")
            os_ver = d.get("osVersion", "")
            compliant = "✅" if d.get("complianceState") == "Compliant" else "❌"
            lines.append(f"  {compliant} {d.get('deviceName', '-')} ({os} {os_ver})")

        total = len(devices)
        lines.append(f"\n✓ {total} Geräte (zeige nur erste 15)")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_intune_devices failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Get details for a specific managed device.
    Use this to see full device information.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        d = devices[0]
        lines = ["📱 " + _t(de="Gerätedetails", en="Device details")]
        lines.append(f"  {d.get('deviceName', '-')}")
        lines.append(f"  OS: {d.get('operatingSystem', '-')} {d.get('osVersion', '')}")
        lines.append(f"  📋 {d.get('userDisplayName', '-')}")
        lines.append(f"  Compliance: {d.get('complianceState', 'unknown')}")
        lines.append(f"  Letzte Sync: {d.get('lastSyncDateTime', '-')[:19]}")
        lines.append(
            f"  Jailbreak: {'Ja' if d.get('jailBreakDetectedState') else 'Nein'}"
        )
        lines.append(f"  Managed: {'Ja' if d.get('isManaged') else 'Nein'}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_intune_device failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_intune_policies(connection_id: str = "") -> str:
    """
    List device configuration policies.
    Use this to see all configuration policies.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceManagement/deviceConfigurations?$top=20",
            token,
        )
        policies = data.get("value", [])
        if not policies:
            return _t(de="Keine Richtlinien gefunden", en="No policies found")

        lines = [
            "📋 " + _t(de="Konfigurationsrichtlinien", en="Configuration policies")
        ]
        for p in policies[:15]:
            plat = p.get("platform", "-")
            lines.append(f"  • {p.get('name', '-')} ({plat})")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_intune_policies failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_intune_compliance_policies(connection_id: str = "") -> str:
    """
    List device compliance policies.
    Use this to see compliance requirements.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceManagement/deviceCompliancePolicies?$top=20",
            token,
        )
        policies = data.get("value", [])
        if not policies:
            return _t(de="Keine Compliance-Richtlinien", en="No compliance policies")

        lines = ["✅ " + _t(de="Compliance-Richtlinien", en="Compliance policies")]
        for p in policies[:15]:
            plat = p.get("platform", "-")
            lines.append(f"  • {p.get('name', '-')} ({plat})")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_intune_compliance_policies failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_intune_apps(connection_id: str = "") -> str:
    """
    List managed apps in Intune.
    Use this to see deployed applications.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceAppManagement/mobileApps?$top=20",
            token,
        )
        apps = data.get("value", [])
        if not apps:
            return _t(de="Keine Apps gefunden", en="No apps found")

        lines = ["📦 " + _t(de="Verwaltete Apps", en="Managed apps")]
        for a in apps[:15]:
            pub = a.get("publisher", "")
            lines.append(f"  • {a.get('displayName', '-')}")
            if pub:
                lines.append(f"    {pub}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_intune_apps failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_intune_device_compliance(
    device_name: str, connection_id: str = ""
) -> str:
    """
    Get compliance status for a device.
    Use this to check if a device meets compliance requirements.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        d = devices[0]
        status = d.get("complianceState", "unknown")
        is_compliant = status == "Compliant"

        lines = ["✅ " + _t(de="Compliance-Status", en="Compliance status")]
        lines.append(f"  {device_name}: {status}")
        if is_compliant:
            lines.append(_t(de="  ✓ Gerät ist konform", en="  ✓ Device is compliant"))
        else:
            lines.append(
                _t(de="  ✗ Gerät ist nicht konform", en="  ✗ Device is not compliant")
            )

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_intune_device_compliance failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def wipe_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Wipe a managed device (factory reset).
    Use this to wipe a lost or stolen device.
    NOTE: This permanently erases all data!
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        device_id = devices[0]["id"]
        await _graph_request(
            "POST",
            f"/deviceManagement/managedDevices/{device_id}/wipe",
            token,
        )
        return _t(
            de=f"✅ Wipe eingeleitet für: {device_name}",
            en=f"✅ Wipe initiated for: {device_name}",
        )
    except Exception as e:
        logger.error("wipe_intune_device failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def retire_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Retire a managed device (remove from management).
    Use this to remove a device from Intune management.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        device_id = devices[0]["id"]
        await _graph_request(
            "POST",
            f"/deviceManagement/managedDevices/{device_id}/retire",
            token,
        )
        return _t(
            de=f"✅ Gerät entfernt aus Management: {device_name}",
            en=f"✅ Device retired: {device_name}",
        )
    except Exception as e:
        logger.error("retire_intune_device failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def sync_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Trigger a remote sync on a managed device.
    Use this to force a device to check in with Intune.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        device_id = devices[0]["id"]
        await _graph_request(
            "POST",
            f"/deviceManagement/managedDevices/{device_id}/syncDevice",
            token,
        )
        return _t(
            de=f"✅ Sync eingeleitet für: {device_name}",
            en=f"✅ Sync initiated for: {device_name}",
        )
    except Exception as e:
        logger.error("sync_intune_device failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def locate_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Get the location of a managed device.
    Use this to locate a lost device.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        d = devices[0]
        loc = d.get("location") or "unbekannt"
        lines = ["📍 " + _t(de="Gerätestandort", en="Device location")]
        lines.append(f"  {device_name}: {loc}")
        return "\n".join(lines)
    except Exception as e:
        logger.error("locate_intune_device failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
