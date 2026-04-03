"""
Ubiquiti Module — LangGraph @tool functions.
Ubiquiti UniFi Controller API.
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

logger = logging.getLogger("ninko.modules.ubiquiti.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get UniFi API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("ubiquiti", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Ubiquiti-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Ubiquiti connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("ubiquiti")

    if conn:
        host = conn.config.get("host", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("UNIFI_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("UNIFI_PASSWORD", "")
        return {"host": host, "user": user, "password": password}

    host = os.environ.get("UNIFI_HOST", "")
    user = os.environ.get("UNIFI_USER", "")
    vault = get_vault()
    password = await vault.get_secret("UNIFI_PASSWORD")

    if not host:
        raise ValueError(
            _t(
                de="Keine Ubiquiti-Verbindung konfiguriert.",
                en="No Ubiquiti connection configured.",
            )
        )

    return {"host": host, "user": user, "password": password}


class UnifiSession:
    def __init__(self, client: dict):
        self.host = client["host"]
        self.user = client["user"]
        self.password = client["password"]
        self.session = None
        self.cookies = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        login = await self.session.post(
            f"https://{self.host}/api/login",
            json={"username": self.user, "password": self.password},
            ssl=False,
        )
        login.raise_for_status()
        self.cookies = login.cookies
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def request(self, path: str) -> list:
        url = f"https://{self.host}/api/s/default{path}"
        async with self.session.get(url, cookies=self.cookies, ssl=False) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("data", [])


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_ubiquiti_devices(connection_id: str = "") -> str:
    """
    List all UniFi devices.
    Use this to see all switches, routers, and APs.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        if not devices:
            return _t(de="Keine Geräte gefunden", en="No devices found")

        lines = ["📡 " + _t(de="Geräte", en="Devices")]
        for d in devices[:20]:
            state = d.get("state", 0)
            state_icon = "🟢" if state == 1 else "🔴"
            name = d.get("name", "-") or d.get("mac", "-")[:8]
            model = d.get("model", "-")
            lines.append(f"  {state_icon} {name} ({model})")

        total = len(devices)
        lines.append(f"\n✓ {total} Geräte")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_ubiquiti_devices failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_ubiquiti_clients(connection_id: str = "") -> str:
    """
    List all clients (wired and wireless).
    Use this to see connected users.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            clients = await unifi.request("/stat/sta")

        if not clients:
            return _t(de="Keine Clients gefunden", en="No clients found")

        lines = ["👥 " + _t(de="Clients", en="Clients")]
        for c in clients[:15]:
            wired = c.get("is_wired", False)
            icon = "💻" if wired else "📱"
            name = c.get("hostname", "-") or c.get("name", "-") or c.get("mac", "-")[:8]
            ip = c.get("ip", "-")
            signal = c.get("signal", 0)
            lines.append(f"  {icon} {name} ({ip}) signal:{signal}")

        total = len(clients)
        lines.append(f"\n✓ {total} Clients")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_ubiquiti_clients failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_ubiquiti_device(device_name: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific device.
    Use this to see device stats.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        device = next(
            (
                d
                for d in devices
                if d.get("name") == device_name or device_name in d.get("mac", "")
            ),
            None,
        )
        if not device:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        lines = ["📡 " + _t(de="Gerätedetails", en="Device details")]
        lines.append(f"  Name: {device.get('name', '-')}")
        lines.append(f"  Model: {device.get('model', '-')}")
        lines.append(f"  Version: {device.get('version', '-')}")
        lines.append(f"  IP: {device.get('ip', '-')}")
        lines.append(f"  Uptime: {device.get('uptime', 0) / 3600:.1f} hours")
        lines.append(f"  State: {device.get('state', 0)}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_ubiquiti_device failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_ubiquiti_wlans(connection_id: str = "") -> str:
    """
    List wireless networks (SSIDs).
    Use this to see configured WiFi networks.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            wlans = await unifi.request("/rest/wlanconf")

        if not wlans:
            return _t(de="Keine WLANs gefunden", en="No WLANs found")

        lines = ["📶 " + _t(de="WLANs", en="WLANs")]
        for w in wlans[:15]:
            enabled = "✅" if w.get("enabled") else "❌"
            ssid = w.get("name", "-")
            security = w.get("security", "-")
            lines.append(f"  {enabled} {ssid} ({security})")

        total = len(wlans)
        lines.append(f"\n✓ {total} WLANs")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_ubiquiti_wlans failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_ubiquiti_switch_ports(connection_id: str = "") -> str:
    """
    List switch ports and their status.
    Use this to see port states on UniFi switches.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        lines = ["🔀 " + _t(de="Switch-Ports", en="Switch ports")]
        switches = [d for d in devices if "sw" in d.get("type", "")]
        for s in switches[:5]:
            name = s.get("name", "-")
            ports = s.get("port_table", [])
            lines.append(f"  📦 {name}:")
            for p in ports[:8]:
                pname = p.get("name", f"Port {p.get('port_idx')}")
                poe = "⚡" if p.get("poe_enable") else ""
                lines.append(f"      {pname} {poe}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_ubiquiti_switch_ports failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_ubiquiti_network_stats(connection_id: str = "") -> str:
    """
    Get network traffic statistics.
    Use this to see throughput.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        total_rx = sum(int(d.get("rx_bytes", 0)) for d in devices)
        total_tx = sum(int(d.get("tx_bytes", 0)) for d in devices)

        lines = ["📊 " + _t(de="Netzwerk-Stats", en="Network stats")]
        lines.append(f"  RX: {total_rx / 1024 / 1024 / 1024:.2f} GB")
        lines.append(f"  TX: {total_tx / 1024 / 1024 / 1024:.2f} GB")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_ubiquiti_network_stats failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_ubiquiti_firewall_rules(connection_id: str = "") -> str:
    """
    List firewall rules.
    Use this to see configured firewall rules.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            rules = await unifi.request("/rest/firewallrule")

        if not rules:
            return _t(de="Keine Firewall-Regeln", en="No firewall rules")

        lines = ["🛡️ " + _t(de="Firewall-Regeln", en="Firewall rules")]
        for r in rules[:15]:
            action = r.get("action", "-")
            src = r.get("src_address", "any")
            dst = r.get("dst_address", "any")
            lines.append(f"  {action}: {src} → {dst}")

        total = len(rules)
        lines.append(f"\n✓ {total} Regeln")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_ubiquiti_firewall_rules failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def restart_ubiquiti_device(device_name: str, connection_id: str = "") -> str:
    """
    Restart a UniFi device.
    Use this to reboot an AP, switch, or router.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")

        device = next(
            (
                d
                for d in devices
                if d.get("name") == device_name or device_name in d.get("mac", "")
            ),
            None,
        )
        if not device:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
            )

        mac = device["mac"]
        await unifi.request(f"/cmd/devmgr/reboot/{mac}")

        return _t(
            de=f"✅ Gerät wird neu gestartet: {device_name}",
            en=f"✅ Device restarting: {device_name}",
        )
    except Exception as e:
        logger.error("restart_ubiquiti_device failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def enable_ubiquiti_wlan(wlan_name: str, connection_id: str = "") -> str:
    """
    Enable a wireless network.
    Use this to enable a WiFi SSID.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            wlans = await unifi.request("/rest/wlanconf")

        wlan = next(
            (
                w
                for w in wlans
                if w.get("name") == wlan_name or w.get("ssid") == wlan_name
            ),
            None,
        )
        if not wlan:
            return _t(
                de=f"WLAN nicht gefunden: {wlan_name}",
                en=f"WLAN not found: {wlan_name}",
            )

        _id = wlan["_id"]
        await unifi.request(f"/rest/wlanconf/{_id}", json={"enabled": True})

        return _t(
            de=f"✅ WLAN aktiviert: {wlan_name}",
            en=f"✅ WLAN enabled: {wlan_name}",
        )
    except Exception as e:
        logger.error("enable_ubiquiti_wlan failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def disable_ubiquiti_wlan(wlan_name: str, connection_id: str = "") -> str:
    """
    Disable a wireless network.
    Use this to disable a WiFi SSID.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            wlans = await unifi.request("/rest/wlanconf")

        wlan = next(
            (
                w
                for w in wlans
                if w.get("name") == wlan_name or w.get("ssid") == wlan_name
            ),
            None,
        )
        if not wlan:
            return _t(
                de=f"WLAN nicht gefunden: {wlan_name}",
                en=f"WLAN not found: {wlan_name}",
            )

        _id = wlan["_id"]
        await unifi.request(f"/rest/wlanconf/{_id}", json={"enabled": False})

        return _t(
            de=f"✅ WLAN deaktiviert: {wlan_name}",
            en=f"✅ WLAN disabled: {wlan_name}",
        )
    except Exception as e:
        logger.error("disable_ubiquiti_wlan failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def kick_ubiquiti_client(mac_address: str, connection_id: str = "") -> str:
    """
    Disconnect a client from the network.
    Use this to kick a client.
    """
    try:
        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            payload = {"mac": mac_address, "cmd": "kick"}
            await unifi.request("/cmd/stamgr", json=payload)

        return _t(
            de=f"✅ Client getrennt: {mac_address}",
            en=f"✅ Client disconnected: {mac_address}",
        )
    except Exception as e:
        logger.error("kick_ubiquiti_client failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
