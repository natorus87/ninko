"""
Lenovo XClarity Module — LangGraph @tool functions.
Lenovo XClarity Administrator API.
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

logger = logging.getLogger("ninko.modules.lenovo_xclarity.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get XClarity API client with auth."""
    if connection_id:
        conn = await ConnectionManager.get_connection("lenovo_xclarity", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"XClarity-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"XClarity connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("lenovo_xclarity")

    if conn:
        base_url = conn.config.get("url", "")
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("XCLARITY_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("XCLARITY_PASSWORD", "")
        return {"base_url": base_url, "user": user, "password": password}

    base_url = os.environ.get("XCLARITY_HOST", "")
    user = os.environ.get("XCLARITY_USER", "admin")
    vault = get_vault()
    password = await vault.get_secret("XCLARITY_PASSWORD")

    if not base_url:
        raise ValueError(
            _t(
                de="Keine XClarity-Verbindung konfiguriert.",
                en="No XClarity connection configured.",
            )
        )

    return {"base_url": f"https://{base_url}", "user": user, "password": password}


async def _xclarity_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to XClarity API."""
    base_url = client["base_url"].rstrip("/")
    url = f"{base_url}/api{path}"

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
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
async def list_xclarity_servers(connection_id: str = "") -> str:
    """
    List all managed servers in XClarity.
    Use this to see all ThinkSystem servers.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        if not servers:
            return _t(de="Keine Server gefunden", en="No servers found")

        lines = ["🖥️ " + _t(de="Server", en="Servers")]
        for s in servers[:15]:
            status_icon = (
                "✅"
                if s.get("status") == "OK"
                else "⚠️"
                if s.get("status") == "Warning"
                else "❌"
            )
            name = s.get("hostname", "-") or s.get("uuid", "-")[:8]
            model = s.get("model", "-")
            lines.append(f"  {status_icon} {name} ({model})")

        total = len(servers)
        lines.append(f"\n✓ {total} Server")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_xclarity_servers failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_xclarity_server_details(server_name: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific server.
    Use this to see full server details.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
            )

        lines = ["🖥️ " + _t(de="Serverdetails", en="Server details")]
        lines.append(f"  Hostname: {server.get('hostname', '-')}")
        lines.append(f"  Model: {server.get('model', '-')}")
        lines.append(f"  Type: {server.get('type', '-')}")
        lines.append(f"  UUID: {server.get('uuid', '-')}")
        lines.append(f"  IP: {server.get('ipAddresses', [{}])[0].get('address', '-')}")
        lines.append(f"  Status: {server.get('status', '-')}")

        if server.get("machineType"):
            lines.append(f"  Machine Type: {server.get('machineType')}")
        if server.get("serialNumber"):
            lines.append(f"  Serial: {server.get('serialNumber')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_xclarity_server_details failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_xclarity_chassis(connection_id: str = "") -> str:
    """
    List all managed chassis in XClarity.
    Use this to see all chassis enclosures.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/chassis", client)
        chassis_list = data.get("chassisList", [])
        if not chassis_list:
            return _t(de="Keine Chassis gefunden", en="No chassis found")

        lines = ["📦 " + _t(de="Chassis", en="Chassis")]
        for c in chassis_list[:15]:
            status_icon = "✅" if c.get("status") == "OK" else "⚠️"
            lines.append(
                f"  {status_icon} {c.get('name', '-')} ({c.get('model', '-')})"
            )

        total = len(chassis_list)
        lines.append(f"\n✓ {total} Chassis")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_xclarity_chassis failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_xclarity_storage(connection_id: str = "") -> str:
    """
    List all managed storage in XClarity.
    Use this to see all storage systems.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/storage", client)
        storage_list = data.get("storageList", [])
        if not storage_list:
            return _t(de="Keine Storage gefunden", en="No storage found")

        lines = ["💾 " + _t(de="Storage", en="Storage")]
        for s in storage_list[:15]:
            status_icon = "✅" if s.get("status") == "OK" else "⚠️"
            lines.append(
                f"  {status_icon} {s.get('name', '-')} ({s.get('model', '-')})"
            )

        total = len(storage_list)
        lines.append(f"\n✓ {total} Storage")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_xclarity_storage failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_xclarity_server_health(server_name: str, connection_id: str = "") -> str:
    """
    Get health and alerts for a specific server.
    Use this to check server health status.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
            )

        lines = ["💚 " + _t(de="Server-Gesundheit", en="Server health")]
        lines.append(f"  {server.get('hostname', '-')}")
        lines.append(f"  Status: {server.get('status', '-')}")
        lines.append(f"  Overall Health: {server.get('overallHealth', 'unknown')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_xclarity_server_health failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_xclarity_events(connection_id: str = "") -> str:
    """
    List recent events in XClarity.
    Use this to see recent alerts and warnings.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/events?summary=true", client)
        events = data.get("eventList", [])
        if not events:
            return _t(de="Keine Events", en="No events")

        lines = ["📋 " + _t(de="Letzte Events", en="Recent events")]
        for e in events[:10]:
            severity = e.get("severity", "unknown")
            sev_icon = (
                "🔴"
                if severity in ["critical", "error"]
                else "🟡"
                if severity == "warning"
                else "🟢"
            )
            msg = e.get("message", "-")[:80]
            lines.append(f"  {sev_icon} [{severity}] {msg}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_xclarity_events failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_xclarity_firmware(server_name: str, connection_id: str = "") -> str:
    """
    Get firmware versions for a server.
    Use this to check installed firmware versions.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
            )

        uuid = server.get("uuid")
        fw_data = await _xclarity_request("GET", f"/servers/{uuid}/firmware", client)
        firmware = fw_data.get("firmware", [])

        lines = ["🔧 " + _t(de="Firmware", en="Firmware")]
        for f in firmware[:10]:
            lines.append(f"  {f.get('name', '-')}: {f.get('version', '-')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_xclarity_firmware failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def power_on_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Power on a server.
    Use this to power on a managed server.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/powerOn",
            client,
        )
        return _t(
            de=f"✅ Server wird eingeschaltet: {server_name}",
            en=f"✅ Server powering on: {server_name}",
        )
    except Exception as e:
        logger.error("power_on_xclarity_server failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def power_off_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Power off a server.
    Use this to power off a managed server.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/powerOff",
            client,
        )
        return _t(
            de=f"✅ Server wird ausgeschaltet: {server_name}",
            en=f"✅ Server powering off: {server_name}",
        )
    except Exception as e:
        logger.error("power_off_xclarity_server failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def restart_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Restart a server (reboot).
    Use this to restart a managed server.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/restart",
            client,
        )
        return _t(
            de=f"✅ Server wird neu gestartet: {server_name}",
            en=f"✅ Server restarting: {server_name}",
        )
    except Exception as e:
        logger.error("restart_xclarity_server failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def identify_xclarity_server(server_name: str, connection_id: str = "") -> str:
    """
    Identify a server (blink LED).
    Use this to locate a physical server by blinking its LED.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _xclarity_request("GET", "/servers", client)
        servers = data.get("serverList", [])
        server = next(
            (
                s
                for s in servers
                if s.get("hostname") == server_name or server_name in s.get("uuid", "")
            ),
            None,
        )
        if not server:
            return _t(
                de=f"Server nicht gefunden: {server_name}",
                en=f"Server not found: {server_name}",
            )

        uuid = server.get("uuid")
        await _xclarity_request(
            "PUT",
            f"/servers/{uuid}/actions/identify",
            client,
        )
        return _t(
            de=f"✅ Server-LED wird aktiviert: {server_name}",
            en=f"✅ Server LED activated: {server_name}",
        )
    except Exception as e:
        logger.error("identify_xclarity_server failed: %e", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
