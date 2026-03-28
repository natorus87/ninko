"""
OPNsense Modul – LangGraph @tool-Funktionen.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.opnsense.tools")


async def _get_opnsense_auth(connection_id: str = "") -> tuple:
    """
    Hilfsfunktion: Lädt Auth-Daten aus dem ConnectionManager oder Env-Variablen.
    Returns: (host, (api_key, api_secret))
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("opnsense", connection_id)
        if not conn:
            raise ValueError(f"OPNsense-Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("opnsense")

    if conn:
        host = conn.config.get("host", "")
        api_key = conn.config.get("api_key", "")
        api_secret = conn.config.get("api_secret", "")

        vault = get_vault()
        api_key_vk = conn.vault_keys.get("api_key")
        if api_key_vk:
            api_key = await vault.get_secret(api_key_vk) or api_key
        secret_vk = conn.vault_keys.get("OPNSENSE_API_SECRET")
        if secret_vk:
            api_secret = await vault.get_secret(secret_vk) or api_secret

        return host, (api_key, api_secret)

    host = os.environ.get("OPNSENSE_HOST", "")
    api_key = os.environ.get("OPNSENSE_API_KEY", "")
    api_secret = os.environ.get("OPNSENSE_API_SECRET", "")

    if not host:
        raise ValueError(
            "Keine OPNsense-Verbindung konfiguriert. "
            "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
            "oder die Env-Variablen OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET setzen."
        )

    return host, (api_key, api_secret)


async def _opnsense_request(endpoint: str, connection_id: str = "", method: str = "GET", json_data: dict | None = None) -> Any:
    """Sendet eine Anfrage an die OPNsense API."""
    host, auth = await _get_opnsense_auth(connection_id)

    if not host:
        raise ValueError("Keine OPNsense-Host-Adresse angegeben.")

    url = f"https://{host}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            if method == "GET":
                resp = await client.get(url, auth=auth)
            elif method == "POST":
                resp = await client.post(url, auth=auth, json=json_data)
            elif method == "DELETE":
                resp = await client.delete(url, auth=auth)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPError as e:
        logger.error("OPNsense API Error: %s", e)
        raise ValueError(f"OPNsense API Fehler: {e}")


@tool
async def get_opnsense_system_status(connection_id: str = "") -> Dict:
    """
    Ruft den System-Status der OPNsense Firewall ab (Version, Uptime, CPU, RAM, Disk).
    Benutze dieses Tool, um allgemeine Systeminformationen zu erhalten.
    Use this tool to get general system information about the OPNsense firewall.
    """
    try:
        host, _ = await _get_opnsense_auth(connection_id)

        time_data, fw_data, mem_data, disk_data = await asyncio.gather(
            _opnsense_request("/api/diagnostics/system/systemTime", connection_id),
            _opnsense_request("/api/core/firmware/info", connection_id),
            _opnsense_request("/api/diagnostics/system/systemResources", connection_id),
            _opnsense_request("/api/diagnostics/system/systemDisk", connection_id),
        )

        mem = mem_data.get("memory", {})
        mem_total = int(mem.get("total") or 1)
        mem_used = int(mem.get("used") or 0)
        mem_pct = round(mem_used / mem_total * 100)

        devices = disk_data.get("devices", [])
        disk_pct = devices[0].get("used_pct", 0) if devices else 0

        loadavg = time_data.get("loadavg", "0, 0, 0")
        load_1m = float(loadavg.split(",")[0].strip()) if loadavg else 0.0

        return {
            "version": fw_data.get("product_version", ""),
            "firmware": fw_data.get("product_id", "OPNsense"),
            "uptime": time_data.get("uptime", ""),
            "cpu": load_1m,
            "memory": mem_pct,
            "disk": disk_pct,
            "host": host,
        }
    except Exception as e:
        logger.error("Fehler beim Abrufen des OPNsense System-Status: %s", e)
        return {"error": str(e)}


@tool
async def get_opnsense_interfaces(connection_id: str = "") -> List[Dict]:
    """
    Ruft alle Netzwerk-Interfaces der OPNsense ab (LAN, WAN, OPT, etc.).
    Benutze dieses Tool, um Interface-Informationen wie IP, MAC, Status zu erhalten.
    Use this tool to get network interface information.
    """
    try:
        result = await _opnsense_request("/api/interfaces/overview/interfacesInfo", connection_id, method="POST", json_data={})
        interfaces = result.get("rows", [])

        return [
            {
                "name": iface.get("device", ""),
                "descr": iface.get("description", ""),
                "ipaddr": iface.get("addr4", ""),
                "ipv6": iface.get("addr6", ""),
                "macaddr": iface.get("macaddr", ""),
                "status": iface.get("status", ""),
                "media": iface.get("media", ""),
                "enabled": iface.get("enabled", False),
            }
            for iface in interfaces
        ]
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense Interfaces: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_gateways(connection_id: str = "") -> List[Dict]:
    """
    Ruft den Status aller Gateways ab (Name, IP, Status, Latenz).
    Benutze dieses Tool, um Gateway-Verbindungen und deren Status zu überprüfen.
    Use this tool to check gateway status and latency.
    """
    try:
        result = await _opnsense_request("/api/routes/gateway/status", connection_id)
        gateways = result.get("gateways", [])

        return [
            {
                "name": gw.get("name", ""),
                "ip": gw.get("ip", ""),
                "status": gw.get("status", ""),
                "rtt": gw.get("rtt"),
                "rttdev": gw.get("rttdev"),
            }
            for gw in gateways
        ]
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense Gateways: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_firewall_rules(connection_id: str = "", interface: str = "") -> List[Dict]:
    """
    Ruft die Firewall-Regeln ab. Optional gefiltert nach Interface (z.B. 'wan', 'lan').
    Benutze dieses Tool, um aktive Firewall-Regeln anzuzeigen.
    Use this tool to list active firewall rules.
    """
    try:
        result = await _opnsense_request("/api/firewall/filter/searchRule", connection_id)
        rules = result.get("rows", [])

        if interface:
            rules = [r for r in rules if interface.lower() in r.get("interface", "").lower()]

        return [
            {
                "uuid": r.get("uuid", ""),
                "sequence": r.get("sequence"),
                "enabled": r.get("enabled"),
                "action": r.get("action"),
                "interface": r.get("interface"),
                "protocol": r.get("protocol"),
                "source": r.get("source"),
                "destination": r.get("destination"),
                "descr": r.get("descr"),
            }
            for r in rules[:50]
        ]
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense Firewall-Regeln: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_nat_rules(connection_id: str = "") -> List[Dict]:
    """
    Ruft die NAT-Regeln (Port Forwarding, Outbound NAT) ab.
    Benutze dieses Tool, um NAT-Regeln anzuzeigen.
    Use this tool to list NAT rules.
    """
    try:
        result = await _opnsense_request("/api/firewall/filter/searchRule?type=nat", connection_id)
        rules = result.get("rows", [])

        return [
            {
                "uuid": r.get("uuid", ""),
                "sequence": r.get("sequence"),
                "enabled": r.get("enabled"),
                "interface": r.get("interface"),
                "protocol": r.get("protocol"),
                "source": r.get("source"),
                "destination": r.get("destination"),
                "target": r.get("target"),
                "target_port": r.get("target_port"),
                "descr": r.get("descr"),
            }
            for r in rules[:50]
        ]
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense NAT-Regeln: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_services(connection_id: str = "") -> List[Dict]:
    """
    Ruft den Status aller Services ab (DHCP, DNS, VPN, etc.).
    Benutze dieses Tool, um zu sehen welche Dienste laufen.
    Use this tool to check which services are running.
    """
    try:
        result = await _opnsense_request("/api/core/service/search", connection_id)
        services = result.get("rows", [])

        return [
            {
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "running": bool(s.get("running", 0)),
                "locked": bool(s.get("locked", 0)),
            }
            for s in services
        ]
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense Services: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_dhcp_leases(connection_id: str = "") -> List[Dict]:
    """
    Ruft die aktuellen DHCP-Leases ab (vergebene IP-Adressen).
    Benutze dieses Tool, um verbundene Geräte im Netzwerk zu sehen.
    Use this tool to see DHCP leases and connected devices.
    """
    try:
        result = await _opnsense_request("/api/dhcpv4/leases/searchLease", connection_id)
        leases = result.get("rows", [])

        return [
            {
                "ip": lease.get("ip", ""),
                "mac": lease.get("mac", ""),
                "hostname": lease.get("hostname"),
                "starts": lease.get("starts"),
                "ends": lease.get("ends"),
                "state": lease.get("state"),
            }
            for lease in leases
        ]
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense DHCP-Leases: %s", e)
        return [{"error": str(e)}]


@tool
async def restart_opnsense_service(service_name: str, connection_id: str = "") -> str:
    """
    Startet einen OPNsense Service neu (z.B. 'unbound', 'dhcpd', 'openvpn').
    Benutze dieses Tool, um einen Dienst neu zu starten.
    Use this tool to restart a service on OPNsense.
    """
    try:
        result = await _opnsense_request(
            f"/api/core/service/restart/{service_name}",
            connection_id,
            method="POST"
        )

        if result.get("status") == "ok":
            return f"Service '{service_name}' wurde neu gestartet."
        return f"Fehler beim Neustart: {result}"
    except Exception as e:
        logger.error("Fehler beim Neustarten des OPNsense Service: %s", e)
        return f"Fehler: {e}"


@tool
async def get_opnsense_logs(lines: int = 50, connection_id: str = "") -> List[Dict]:
    """
    Ruft die Firewall-Logs ab (letzte Einträge).
    Benutze dieses Tool, um Firewall-Blockierungen und Verbindungen zu sehen.
    Use this tool to see firewall logs.
    """
    try:
        result = await _opnsense_request("/api/diagnostics/firewall/log", connection_id)
        # API returns a list directly
        entries = result if isinstance(result, list) else result.get("rows", [])

        return [
            {
                "timestamp": e.get("__timestamp__", ""),
                "action": e.get("action", ""),
                "interface": e.get("interface", ""),
                "src": e.get("src", ""),
                "dst": e.get("dst", ""),
                "srcport": e.get("srcport", ""),
                "dstport": e.get("dstport", ""),
                "proto": e.get("protoname", ""),
                "label": e.get("label", ""),
            }
            for e in entries[:lines]
        ]
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense Logs: %s", e)
        return [{"error": str(e)}]
