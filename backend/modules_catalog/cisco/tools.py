"""
Cisco Module — LangGraph @tool functions.
Cisco Network Devices API (NX-API, REST API).
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

logger = logging.getLogger("ninko.modules.cisco.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get Cisco API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("cisco", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Cisco-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Cisco connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("cisco")

    if conn:
        host = conn.config.get("host", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("CISCO_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("CISCO_PASSWORD", "")
        return {"host": host, "user": user, "password": password}

    host = os.environ.get("CISCO_HOST", "")
    user = os.environ.get("CISCO_USER", "")
    vault = get_vault()
    password = await vault.get_secret("CISCO_PASSWORD")

    if not host:
        raise ValueError(
            _t(
                de="Keine Cisco-Verbindung konfiguriert.",
                en="No Cisco connection configured.",
            )
        )

    return {"host": host, "user": user, "password": password}


async def _cisco_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to Cisco device API."""
    host = client["host"]
    url = f"https://{host}/api{path}"

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.request(method, url, json=json, ssl=False) as resp:
            resp.raise_for_status()
            return await resp.json()


async def _nxapi_request(client: dict, commands: list[str]) -> list[str]:
    """Execute NX-API CLI commands."""
    host = client["host"]
    url = f"https://{host}/api/mo/cli.json"

    payload = {
        "ins_api": {
            "version": "1.0",
            "type": "cli_show",
            "chunk": "0",
            "sid": "1",
            "input": commands[0],
            "output_format": "json",
        }
    }

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.post(url, json=payload, ssl=False) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return [data.get("ins_api", {}).get("body", "")]


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def get_cisco_device_info(connection_id: str = "") -> str:
    """
    Get device information (hostname, model, version, uptime).
    Use this to see basic device info.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/platform/mgmt/operational", client)

        lines = ["🔰 " + _t(de="Geräteinfo", en="Device info")]
        lines.append(f"  Hostname: {data.get('hostname', '-')}")
        lines.append(f"  Model: {data.get('model', '-')}")
        lines.append(f"  Version: {data.get('version', '-')}")
        lines.append(f"  Uptime: {data.get('uptime', '-')}")
        if data.get("serial"):
            lines.append(f"  Serial: {data.get('serial')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_cisco_device_info failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_cisco_interfaces(connection_id: str = "") -> str:
    """
    List all network interfaces and their status.
    Use this to see all ports and their state.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/interfaces", client)

        ifaces = data.get("interface", [])
        if not ifaces:
            return _t(de="Keine Interfaces gefunden", en="No interfaces found")

        lines = ["🔀 " + _t(de="Interfaces", en="Interfaces")]
        for i in ifaces[:20]:
            status = i.get("oper_status", "unknown")
            status_icon = "🟢" if status == "up" else "🔴" if status == "down" else "🟡"
            name = i.get("name", "-")
            speed = i.get("speed", "")
            desc = i.get("description", "")
            lines.append(f"  {status_icon} {name} {speed}")
            if desc:
                lines.append(f"      {desc}")

        total = len(ifaces)
        lines.append(f"\n✓ {total} Interfaces")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_interfaces failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_cisco_interface_details(interface: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific interface.
    Use this to see full interface statistics.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", f"/interfaces/{interface}", client)

        lines = ["🔀 " + _t(de="Interface-Details", en="Interface details")]
        lines.append(f"  {interface}")
        lines.append(f"  Status: {data.get('oper_status', '-')}")
        lines.append(f"  Speed: {data.get('speed', '-')}")
        lines.append(f"  Duplex: {data.get('duplex', '-')}")
        lines.append(f"  Description: {data.get('description', '-')}")
        lines.append(f"  MTU: {data.get('mtu', '-')}")

        stats = data.get("counters", {})
        if stats:
            lines.append(f"  In: {stats.get('inOctets', 0)} bytes")
            lines.append(f"  Out: {stats.get('outOctets', 0)} bytes")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_cisco_interface_details failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_cisco_vlans(connection_id: str = "") -> str:
    """
    List all VLANs on the device.
    Use this to see configured VLANs.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/vlans", client)

        vlans = data.get("vlan", [])
        if not vlans:
            return _t(de="Keine VLANs gefunden", en="No VLANs found")

        lines = ["🏷️ " + _t(de="VLANs", en="VLANs")]
        for v in vlans[:20]:
            status = v.get("status", "active")
            status_icon = "✅" if status == "active" else "📦"
            lines.append(f"  {status_icon} VLAN {v.get('id')}: {v.get('name', '-')}")

        total = len(vlans)
        lines.append(f"\n✓ {total} VLANs")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_vlans failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_cisco_routes(connection_id: str = "") -> str:
    """
    List routing table entries.
    Use this to see active routes.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/routing/routes", client)

        routes = data.get("route", [])
        if not routes:
            return _t(de="Keine Routen gefunden", en="No routes found")

        lines = ["🛤️ " + _t(de="Routen", en="Routes")]
        for r in routes[:15]:
            dest = r.get("destination", "-")
            gateway = r.get("next_hop", "-")
            iface = r.get("interface", "-")
            metric = r.get("metric", "")
            lines.append(f"  {dest} → {gateway} ({iface}) {metric}")

        total = len(routes)
        lines.append(f"\n✓ {total} Routen")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_routes failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_cisco_mac_addresses(connection_id: str = "") -> str:
    """
    List MAC address table.
    Use this to see learned MAC addresses.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/l2/multicast/mac", client)

        macs = data.get("mac", [])
        if not macs:
            return _t(de="Keine MAC-Adressen", en="No MAC addresses")

        lines = ["📠 " + _t(de="MAC-Table", en="MAC table")]
        for m in macs[:15]:
            vlan = m.get("vlan", "-")
            mac = m.get("address", "-")
            iface = m.get("interface", "-")
            lines.append(f"  VLAN {vlan}: {mac} → {iface}")

        total = len(macs)
        lines.append(f"\n✓ {total} MAC-Adressen")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_cisco_mac_addresses failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_cisco_poe_status(connection_id: str = "") -> str:
    """
    Get PoE (Power over Ethernet) status.
    Use this to see PoE port status.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _cisco_request("GET", "/interface/poe", client)

        ports = data.get("port", [])
        if not ports:
            return _t(de="Keine PoE-Ports", en="No PoE ports")

        lines = ["⚡ " + _t(de="PoE-Status", en="PoE status")]
        for p in ports[:15]:
            name = p.get("name", "-")
            status = p.get("status", "-")
            power = p.get("allocated_power", "0")
            lines.append(f"  {name}: {status} ({power}W)")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_cisco_poe_status failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def enable_cisco_interface(interface: str, connection_id: str = "") -> str:
    """
    Enable a network interface.
    Use this to bring up a port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "PUT",
            f"/interfaces/{interface}",
            client,
            json={"admin_status": "up"},
        )
        return _t(
            de=f"✅ Interface aktiviert: {interface}",
            en=f"✅ Interface enabled: {interface}",
        )
    except Exception as e:
        logger.error("enable_cisco_interface failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def disable_cisco_interface(interface: str, connection_id: str = "") -> str:
    """
    Disable a network interface.
    Use this to shut down a port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "PUT",
            f"/interfaces/{interface}",
            client,
            json={"admin_status": "down"},
        )
        return _t(
            de=f"✅ Interface deaktiviert: {interface}",
            en=f"✅ Interface disabled: {interface}",
        )
    except Exception as e:
        logger.error("disable_cisco_interface failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def create_cisco_vlan(
    vlan_id: int, vlan_name: str, connection_id: str = ""
) -> str:
    """
    Create a new VLAN.
    Use this to add a VLAN.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "POST",
            "/vlans",
            client,
            json={"id": vlan_id, "name": vlan_name, "admin_status": "active"},
        )
        return _t(
            de=f"✅ VLAN erstellt: {vlan_id} ({vlan_name})",
            en=f"✅ VLAN created: {vlan_id} ({vlan_name})",
        )
    except Exception as e:
        logger.error("create_cisco_vlan failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def set_cisco_interface_vlan(
    interface: str, vlan_id: int, connection_id: str = ""
) -> str:
    """
    Assign a port to a VLAN.
    Use this to set port VLAN membership.
    """
    try:
        client = await _get_api_client(connection_id)
        await _cisco_request(
            "PUT",
            f"/interfaces/{interface}",
            client,
            json={"vlan": vlan_id},
        )
        return _t(
            de=f"✅ Interface {interface} → VLAN {vlan_id}",
            en=f"✅ Interface {interface} → VLAN {vlan_id}",
        )
    except Exception as e:
        logger.error("set_cisco_interface_vlan failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
