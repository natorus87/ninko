"""
MikroTik Module — LangGraph @tool functions.
MikroTik RouterOS REST API.
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

logger = logging.getLogger("ninko.modules.mikrotik.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get MikroTik API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("mikrotik", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"MikroTik-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"MikroTik connection with ID '{connection_id}' not found.",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("mikrotik")

    if conn:
        host = conn.config.get("host", "")
        user = conn.config.get("user", "admin")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("MIKROTIK_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("MIKROTIK_PASSWORD", "")
        return {"host": host, "user": user, "password": password}

    host = os.environ.get("MIKROTIK_HOST", "")
    user = os.environ.get("MIKROTIK_USER", "admin")
    vault = get_vault()
    password = await vault.get_secret("MIKROTIK_PASSWORD")

    if not host:
        raise ValueError(
            _t(
                de="Keine MikroTik-Verbindung konfiguriert.",
                en="No MikroTik connection configured.",
            )
        )

    return {"host": host, "user": user, "password": password}


class MikroTikSession:
    def __init__(self, client: dict):
        self.host = client["host"]
        self.user = client["user"]
        self.password = client["password"]
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
        )
        resp = await self.session.post(
            f"https://{self.host}/rest/login",
            json=[self.user, self.password, ""],
            ssl=False,
        )
        resp.raise_for_status()
        return self

    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()

    async def request(
        self, method: str, path: str, json: Optional[dict] = None
    ) -> list:
        url = f"https://{self.host}/rest{path}"
        async with self.session.request(method, url, json=json, ssl=False) as resp:
            resp.raise_for_status()
            return await resp.json()


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def get_mikrotik_identity(connection_id: str = "") -> str:
    """
    Get router identity and system info.
    Use this to see basic router info.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            identity = await mt.request("GET", "/system/identity")
            resource = await mt.request("GET", "/system/resource")

        lines = ["📡 " + _t(de="Geräteinfo", en="Device info")]
        lines.append(f"  Name: {identity[0].get('name', '-')}")
        lines.append(f"  Model: {resource[0].get('board', '-')}")
        lines.append(f"  Version: {resource[0].get('version', '-')}")
        lines.append(f"  Uptime: {resource[0].get('uptime', '-')}")
        lines.append(f"  CPU: {resource[0].get('cpu-load', '?')}%")
        lines.append(
            f"  Memory: {resource[0].get('free-memory', 0) / 1024 / 1024:.1f} / {resource[0].get('total-memory', 1) / 1024 / 1024:.1f} MB"
        )

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_mikrotik_identity failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_mikrotik_interfaces(connection_id: str = "") -> str:
    """
    List all network interfaces.
    Use this to see all ports and their status.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            ifaces = await mt.request("GET", "/interface")

        lines = ["🔀 " + _t(de="Interfaces", en="Interfaces")]
        for i in ifaces[:20]:
            status = i.get("running", "false")
            status_icon = "🟢" if status == "true" else "🔴"
            name = i.get("name", "-")
            itype = i.get("type", "")
            lines.append(f"  {status_icon} {name} ({itype})")

        total = len(ifaces)
        lines.append(f"\n✓ {total} Interfaces")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_mikrotik_interfaces failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def get_mikrotik_interface_stats(interface: str, connection_id: str = "") -> str:
    """
    Get interface statistics (traffic counters).
    Use this to see bytes/packets transferred.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            stats = await mt.request("GET", f"/interface/{interface}")

        if not stats:
            return _t(
                de=f"Interface nicht gefunden: {interface}",
                en=f"Interface not found: {interface}",
            )

        s = stats[0]
        lines = ["📊 " + _t(de="Interface-Stats", en="Interface stats")]
        lines.append(f"  {interface}")
        lines.append(f"  Status: {s.get('running', '-')}")
        lines.append(f"  RX: {int(s.get('rx-byte', 0)) / 1024 / 1024:.2f} MB")
        lines.append(f"  TX: {int(s.get('tx-byte', 0)) / 1024 / 1024:.2f} MB")
        lines.append(f"  RX Packets: {s.get('rx-packet', '-')}")
        lines.append(f"  TX Packets: {s.get('tx-packet', '-')}")

        return "\n".join(lines)
    except Exception as e:
        logger.error("get_mikrotik_interface_stats failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_mikrotik_routes(connection_id: str = "") -> str:
    """
    List routing table.
    Use this to see active routes.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            routes = await mt.request("GET", "/ip/route")

        lines = ["🛤️ " + _t(de="Routen", en="Routes")]
        for r in routes[:15]:
            dst = r.get("dst-address", "0.0.0.0/0")
            gateway = r.get("gateway", "-")
            dist = r.get("distance", "1")
            lines.append(f"  {dst} → {gateway} (dist:{dist})")

        total = len(routes)
        lines.append(f"\n✓ {total} Routen")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_mikrotik_routes failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_mikrotik_dhcp_leases(connection_id: str = "") -> str:
    """
    List DHCP leases.
    Use this to see DHCP clients.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            leases = await mt.request("GET", "/ip/dhcp-server/lease")

        lines = ["📱 " + _t(de="DHCP-Leases", en="DHCP leases")]
        for l in leases[:15]:
            status = l.get("status", "unknown")
            status_icon = "🟢" if status == "bound" else "🟡"
            addr = l.get("address", "-")
            mac = l.get("mac-address", "-")
            host = l.get("host-name", "")
            lines.append(f"  {status_icon} {addr} ({mac})")
            if host:
                lines.append(f"      {host}")

        total = len(leases)
        lines.append(f"\n✓ {total} Leases")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_mikrotik_dhcp_leases failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_mikrotik_firewall_rules(connection_id: str = "") -> str:
    """
    List firewall filter rules.
    Use this to see firewall rules.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            rules = await mt.request("GET", "/ip/firewall/filter")

        lines = ["🛡️ " + _t(de="Firewall-Regeln", en="Firewall rules")]
        for r in rules[:15]:
            chain = r.get("chain", "-")
            action = r.get("action", "-")
            protocol = r.get("protocol", "")
            src = r.get("src-address", "")
            lines.append(f"  {chain}: {action} ({protocol}) {src}")

        total = len(rules)
        lines.append(f"\n✓ {total} Regeln")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_mikrotik_firewall_rules failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_mikrotik_queues(connection_id: str = "") -> str:
    """
    List simple queues.
    Use this to see bandwidth limits.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            queues = await mt.request("GET", "/queue/simple")

        lines = ["📶 " + _t(de="Queues", en="Queues")]
        for q in queues[:15]:
            name = q.get("name", "-")
            target = q.get("target", "-")
            max_limit = q.get("max-limit", "-")
            lines.append(f"  {name}: {target} → {max_limit}")

        total = len(queues)
        lines.append(f"\n✓ {total} Queues")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_mikrotik_queues failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def list_mikrotik_wireless_clients(connection_id: str = "") -> str:
    """
    List active wireless clients.
    Use this to see connected WiFi clients.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            clients = await mt.request("GET", "/interface/wireless/registration-table")

        lines = ["📶 " + _t(de="Wireless-Clients", en="Wireless clients")]
        for c in clients[:15]:
            mac = c.get("mac-address", "-")
            signal = c.get("signal", "0")
            rate = c.get("rx-rate", "-")
            lines.append(f"  📱 {mac} signal:{signal}dBm rate:{rate}")

        total = len(clients)
        lines.append(f"\n✓ {total} Clients")

        return "\n".join(lines)
    except Exception as e:
        logger.error("list_mikrotik_wireless_clients failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def enable_mikrotik_interface(interface: str, connection_id: str = "") -> str:
    """
    Enable an interface.
    Use this to enable a port.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            await mt.request("PUT", f"/interface/{interface}", {"disabled": "false"})
        return _t(
            de=f"✅ Interface aktiviert: {interface}",
            en=f"✅ Interface enabled: {interface}",
        )
    except Exception as e:
        logger.error("enable_mikrotik_interface failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def disable_mikrotik_interface(interface: str, connection_id: str = "") -> str:
    """
    Disable an interface.
    Use this to disable a port.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            await mt.request("PUT", f"/interface/{interface}", {"disabled": "true"})
        return _t(
            de=f"✅ Interface deaktiviert: {interface}",
            en=f"✅ Interface disabled: {interface}",
        )
    except Exception as e:
        logger.error("disable_mikrotik_interface failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def reboot_mikrotik(connection_id: str = "") -> str:
    """
    Reboot the MikroTik router.
    Use this to restart the device.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            await mt.request("POST", "/system/reboot", {"hold-time": "3s"})
        return _t(
            de="✅ Router wird neu gestartet",
            en="✅ Router rebooting",
        )
    except Exception as e:
        logger.error("reboot_mikrotik failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def create_mikrotik_firewall_rule(
    chain: str,
    action: str,
    protocol: str = "",
    src_address: str = "",
    dst_address: str = "",
    connection_id: str = "",
) -> str:
    """
    Create a firewall rule.
    Use this to add a firewall filter rule.
    """
    try:
        client = await _get_api_client(connection_id)
        rule = {
            "chain": chain,
            "action": action,
            "protocol": protocol,
            "src-address": src_address,
            "dst-address": dst_address,
        }
        async with MikroTikSession(client) as mt:
            await mt.request("POST", "/ip/firewall/filter", rule)
        return _t(
            de=f"✅ Firewall-Regel erstellt: {chain} → {action}",
            en=f"✅ Firewall rule created: {chain} → {action}",
        )
    except Exception as e:
        logger.error("create_mikrotik_firewall_rule failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")


@tool
async def add_mikrotik_ip_address(
    address: str,
    interface: str,
    connection_id: str = "",
) -> str:
    """
    Add an IP address to an interface.
    Use this to assign an IP to a port.
    """
    try:
        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            await mt.request(
                "POST", "/ip/address", {"address": address, "interface": interface}
            )
        return _t(
            de=f"✅ IP-Adresse hinzugefügt: {address} auf {interface}",
            en=f"✅ IP address added: {address} on {interface}",
        )
    except Exception as e:
        logger.error("add_mikrotik_ip_address failed: %s", e)
        return _t(de=f"Fehler: {e}", en=f"Error: {e}")
