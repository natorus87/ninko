"""
Netgear Module — LangGraph @tool functions.
Netgear Switch/Router HTTP API.
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

logger = logging.getLogger("ninko.modules.netgear.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get Netgear API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("netgear", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Netgear-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Netgear connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("netgear")

    if conn:
        host = conn.config.get("host", "")
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("NETGEAR_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("NETGEAR_PASSWORD", "")
        return {"host": host, "user": user, "password": password}

    host = os.environ.get("NETGEAR_HOST", "")
    user = os.environ.get("NETGEAR_USER", "admin")
    vault = get_vault()
    password = await vault.get_secret("NETGEAR_PASSWORD")

    if not host:
        raise ValueError(
            _t(
                de="Keine Netgear-Verbindung konfiguriert.",
                en="No Netgear connection configured.",
            )
        )

    return {"host": host, "user": user, "password": password}


async def _netgear_request(client: dict, path: str) -> dict:
    """Make authenticated request to Netgear device."""
    host = client["host"]
    url = f"http://{host}{path}"

    auth = aiohttp.BasicAuth(client["user"], client["password"])

    async with aiohttp.ClientSession(
        auth=auth,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.get(url) as resp:
            if resp.status == 401:
                raise Exception("Authentication failed")
            resp.raise_for_status()
            try:
                return await resp.json()
            except Exception:
                text = await resp.text()
                return {"raw": text}


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def get_netgear_sysinfo(connection_id: str = "") -> str:
    """
    Get system information.
    Use this to see basic device info.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/sysinfo")

        if "raw" in data:
            return _t(
                de="Gerät antwortet, aber kein JSON", en="Device responds but not JSON"
            )

        lines = ["📶 " + _t(de="Geräteinfo", en="Device info")]
        lines.append(f"  Model: {data.get('model', '-')}")
        lines.append(f"  Description: {data.get('description', '-')}")
        lines.append(f"  Firmware: {data.get('firmware_version', '-')}")
        lines.append(f"  MAC: {data.get('mac_addr', '-')}")
        lines.append(f"  Uptime: {data.get('uptime', '-')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_netgear_sysinfo failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_netgear_ports(connection_id: str = "") -> str:
    """
    List all ports and their status.
    Use this to see all switch ports.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/portinfo")

        ports = data.get("port_info", [])
        if not ports:
            ports = data.get("ports", [])

        if not ports:
            return _t(de="Keine Ports gefunden", en="No ports found")

        lines = ["🔀 " + _t(de="Ports", en="Ports")]
        for p in ports[:20]:
            name = p.get("port", p.get("id", "-"))
            status = p.get("link_status", p.get("status", "unknown"))
            status_icon = "🟢" if status == "Up" or status == "1" else "🔴"
            speed = p.get("speed", p.get("current_speed", "-"))
            duplex = p.get("duplex", "-")
            lines.append(f"  {status_icon} Port {name}: {speed}/{duplex}")

        total = len(ports)
        lines.append(f"\n✓ {total} Ports")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_ports failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_netgear_vlans(connection_id: str = "") -> str:
    """
    List configured VLANs.
    Use this to see VLAN configuration.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/vlan")

        vlans = data.get("vlan", [])
        if not vlans:
            vlans = data.get("vlans", [])

        if not vlans:
            return _t(de="Keine VLANs gefunden", en="No VLANs found")

        lines = ["🏷️ " + _t(de="VLANs", en="VLANs")]
        for v in vlans[:20]:
            vid = v.get("vid", v.get("vlan_id", "-"))
            name = v.get("name", v.get("vlan_name", "-"))
            lines.append(f"  VLAN {vid}: {name}")

        total = len(vlans)
        lines.append(f"\n✓ {total} VLANs")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_vlans failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_netgear_port_stats(port: str, connection_id: str = "") -> str:
    """
    Get port statistics.
    Use this to see traffic counters for a port.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, f"/portstats/{port}")

        if "raw" in data:
            return _t(de=f"Port nicht gefunden: {port}", en=f"Port not found: {port}")

        lines = ["📊 " + _t(de="Port-Stats", en="Port stats")]
        lines.append(f"  Port {port}")
        rx = data.get("rx_bytes", "0")
        tx = data.get("tx_bytes", "0")
        lines.append(f"  RX: {int(rx) / 1024 / 1024:.2f} MB")
        lines.append(f"  TX: {int(tx) / 1024 / 1024:.2f} MB")
        lines.append(f"  RX Packets: {data.get('rx_packets', '-')}")
        lines.append(f"  TX Packets: {data.get('tx_packets', '-')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_netgear_port_stats failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_netgear_arp(connection_id: str = "") -> str:
    """
    List ARP table.
    Use this to see connected devices.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/arp")

        arp = data.get("arp", [])
        if not arp:
            return _t(de="Keine ARP-Einträge", en="No ARP entries")

        lines = ["📠 " + _t(de="ARP-Table", en="ARP table")]
        for a in arp[:15]:
            ip = a.get("ip_address", a.get("ip", "-"))
            mac = a.get("mac_address", a.get("mac", "-"))
            age = a.get("age", "0")
            lines.append(f"  {ip} → {mac} (age:{age})")

        total = len(arp)
        lines.append(f"\n✓ {total} Einträge")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_arp failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_netgear_lldp(connection_id: str = "") -> str:
    """
    List LLDP neighbors.
    Use this to see connected devices via LLDP.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _netgear_request(client, "/lldp")

        neighbors = data.get("lldp", [])
        if not neighbors:
            return _t(de="Keine LLDP-Nachbarn", en="No LLDP neighbors")

        lines = ["🔗 " + _t(de="LLDP-Nachbarn", en="LLDP neighbors")]
        for n in neighbors[:15]:
            local = n.get("local_port", "-")
            remote = n.get("chassis_id", n.get("device_id", "-"))
            name = n.get("port_id", "-")
            lines.append(f"  Port {local} → {name} ({remote})")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_netgear_lldp failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def enable_netgear_port(port: str, connection_id: str = "") -> str:
    """
    Enable a port.
    Use this to enable a switch port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _netgear_request(client, f"/port/{port}/enable")
        return _t(
            de=f"✅ Port aktiviert: {port}",
            en=f"✅ Port enabled: {port}",
        )
    except Exception as e:
        logger.error("enable_netgear_port failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def disable_netgear_port(port: str, connection_id: str = "") -> str:
    """
    Disable a port.
    Use this to disable a switch port.
    """
    try:
        client = await _get_api_client(connection_id)
        await _netgear_request(client, f"/port/{port}/disable")
        return _t(
            de=f"✅ Port deaktiviert: {port}",
            en=f"✅ Port disabled: {port}",
        )
    except Exception as e:
        logger.error("disable_netgear_port failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def reboot_netgear(connection_id: str = "") -> str:
    """
    Reboot the Netgear device.
    Use this to restart the device.
    """
    try:
        client = await _get_api_client(connection_id)
        await _netgear_request(client, "/reboot")
        return _t(
            de="✅ Gerät wird neu gestartet",
            en="✅ Device rebooting",
        )
    except Exception as e:
        logger.error("reboot_netgear failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
