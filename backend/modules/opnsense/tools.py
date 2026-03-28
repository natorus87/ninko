"""
OPNsense Modul – LangGraph @tool-Funktionen.
"""

from __future__ import annotations

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
        secret_key = conn.vault_keys.get("OPNSENSE_API_SECRET")
        if secret_key:
            api_secret = await vault.get_secret(secret_key) or api_secret

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


async def _opnsense_request(endpoint: str, connection_id: str = "", method: str = "GET", json_data: dict = None) -> Dict:
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
        logger.error(f"OPNsense API Error: {e}")
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
        if not host:
            raise ValueError("Keine OPNsense-Verbindung konfiguriert.")

        result = await _opnsense_request("/api/core/system/status", connection_id)

        sys = result.get("system", {})
        cpu = sys.get("cpu", 0)
        mem = sys.get("mem", 0)
        disk = sys.get("disk", 0)

        return {
            "firmware": sys.get("firmware"),
            "version": sys.get("version"),
            "uptime": sys.get("uptime"),
            "cpu": cpu,
            "memory": mem,
            "disk": disk,
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
        result = await _opnsense_request("/api/interfaces/overview/get", connection_id)
        interfaces = result.get("interfaces", [])

        return [
            {
                "name": iface.get("name", ""),
                "descr": iface.get("descr", ""),
                "ipaddr": iface.get("ipaddr", ""),
                "subnet": iface.get("subnet"),
                "macaddr": iface.get("macaddr", ""),
                "status": iface.get("status", ""),
                "media": iface.get("media", ""),
                "speed": iface.get("speed"),
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
        result = await _opnsense_request("/api/filter/rule/searchRule", connection_id)
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
        result = await _opnsense_request("/api/nat/rule/searchRule", connection_id)
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
        result = await _opnsense_request("/api/service/searchService", connection_id)
        services = result.get("rows", [])

        return [
            {
                "name": s.get("name", ""),
                "description": s.get("description", ""),
                "enabled": s.get("enabled") == "1",
                "status": s.get("status", ""),
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
            f"/api/service/service/restart/{service_name}",
            connection_id,
            method="POST"
        )

        if result.get("status") == "ok":
            return f"Service '{service_name}' wurde neu gestartet."
        return f"Fehler beim Neustart: {result}"
    except Exception as e:
        logger.error(f"Fehler beim Neustarten des OPNsense Service: %s", e)
        return f"Fehler: {e}"


@tool
async def get_opnsense_logs(lines: int = 50, connection_id: str = "") -> List[str]:
    """
    Ruft die Firewall-Logs ab (letzte einträge).
    Benutze dieses Tool, um Firewall-Blockierungen und Verbindungen zu sehen.
    Use this tool to see firewall logs.
    """
    try:
        result = await _opnsense_request(
            f"/api/filter/log/filter/{lines}",
            connection_id
        )

        logs = result.get("logs", [])
        return logs
    except Exception as e:
        logger.error("Fehler beim Abrufen der OPNsense Logs: %s", e)
        return [f"Fehler: {str(e)}"]
