"""OPNsense module — LangGraph @tool functions."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.tls import get_connection_verify_arg
from core.vault import get_vault
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.opnsense.tools")


async def _get_opnsense_auth(connection_id: str = "") -> tuple:
    """
    Helper: loads auth data from ConnectionManager or environment variables.
    Returns: (host, (api_key, api_secret), verify_arg)
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("opnsense", connection_id)
        if not conn:
            raise ValueError(f"OPNsense connection with ID '{connection_id}' not found.")
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

        verify = await get_connection_verify_arg(conn, "opnsense", default_verify=True)
        return host, (api_key, api_secret), verify

    host = os.environ.get("OPNSENSE_HOST", "")
    api_key = os.environ.get("OPNSENSE_API_KEY", "")
    api_secret = os.environ.get("OPNSENSE_API_SECRET", "")

    if not host:
        raise ValueError(
            _t(
                de="Keine OPNsense-Verbindung konfiguriert. Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, oder die Env-Variablen OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET setzen.",
                en="No OPNsense connection configured. Please create a connection in the dashboard under Settings → Module → gear icon, or set the environment variables OPNSENSE_HOST, OPNSENSE_API_KEY, OPNSENSE_API_SECRET.",
            )
        )

    verify_ssl = os.environ.get("OPNSENSE_VERIFY_SSL", "true").lower() == "true"
    if verify_ssl:
        ca_path = os.environ.get("OPNSENSE_CA_CERT_PATH", "").strip()
        if ca_path:
            return host, (api_key, api_secret), ca_path
    return host, (api_key, api_secret), verify_ssl


async def _opnsense_request(endpoint: str, connection_id: str = "", method: str = "GET", json_data: dict | None = None) -> Any:
    """Sends a request to the OPNsense API."""
    host, auth, verify = await _get_opnsense_auth(connection_id)

    if not host:
        raise ValueError("No OPNsense host address provided.")

    url = f"https://{host}{endpoint}"

    try:
        async with httpx.AsyncClient(timeout=30.0, verify=verify) as client:
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
        raise ValueError(f"OPNsense API error: {e}")


@tool
async def get_opnsense_system_status(connection_id: str = "") -> Dict:
    """
    Retrieves the system status of the OPNsense firewall (version, uptime, CPU, RAM, disk).
    Use this tool to get general system information about the OPNsense firewall.
    """
    try:
        host, _, _ = await _get_opnsense_auth(connection_id)

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
        logger.error("Failed to retrieve OPNsense system status: %s", e)
        return {"error": str(e)}


@tool
async def get_opnsense_interfaces(connection_id: str = "") -> List[Dict]:
    """
    Retrieves all network interfaces of the OPNsense firewall (LAN, WAN, OPT, etc.).
    Use this tool to get network interface information (IP, MAC, status).
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
        logger.error("Failed to retrieve OPNsense interfaces: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_gateways(connection_id: str = "") -> List[Dict]:
    """
    Retrieves the status of all gateways (name, IP, status, latency).
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
        logger.error("Failed to retrieve OPNsense gateways: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_firewall_rules(connection_id: str = "", interface: str = "") -> List[Dict]:
    """
    Retrieves firewall rules. Optionally filtered by interface (e.g. 'wan', 'lan').
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
        logger.error("Failed to retrieve OPNsense firewall rules: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_nat_rules(connection_id: str = "") -> List[Dict]:
    """
    Retrieves NAT rules (port forwarding, outbound NAT).
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
        logger.error("Failed to retrieve OPNsense NAT rules: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_services(connection_id: str = "") -> List[Dict]:
    """
    Retrieves the status of all services (DHCP, DNS, VPN, etc.).
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
        logger.error("Failed to retrieve OPNsense services: %s", e)
        return [{"error": str(e)}]


@tool
async def get_opnsense_dhcp_leases(connection_id: str = "") -> List[Dict]:
    """
    Retrieves current DHCP leases (assigned IP addresses).
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
        logger.error("Failed to retrieve OPNsense DHCP leases: %s", e)
        return [{"error": str(e)}]


@tool
async def create_opnsense_firewall_rule(
    interface: str,
    action: str,
    protocol: str,
    source: str,
    destination: str,
    description: str = "",
    connection_id: str = ""
) -> str:
    """
    Creates a new firewall rule on OPNsense.
    Use this tool to add a firewall rule. Requires confirmation.
    """
    try:
        payload = {
            "rule": {
                "interface": interface,
                "action": action,
                "protocol": protocol,
                "source": source,
                "destination": destination,
                "descr": description,
                "enabled": "1",
            }
        }
        result = await _opnsense_request(
            "/api/firewall/filter/addRule",
            connection_id,
            method="POST",
            json_data=payload
        )
        if result.get("status") == "ok":
            return _t(
                de=f"Firewall-Regel erstellt: {description}",
                en=f"Firewall rule created: {description}",
            )
        return _t(
            de=f"Fehler beim Erstellen der Regel: {result}",
            en=f"Error creating rule: {result}",
        )
    except Exception as e:
        logger.error("Failed to create OPNsense firewall rule: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
        )


@tool
async def delete_opnsense_firewall_rule(rule_uuid: str, connection_id: str = "") -> str:
    """
    Deletes a firewall rule by UUID. Use this tool to remove a firewall rule. Requires confirmation.
    """
    try:
        result = await _opnsense_request(
            f"/api/firewall/filter/deleteRule/{rule_uuid}",
            connection_id,
            method="POST"
        )
        if result.get("status") == "ok":
            return _t(
                de=f"Firewall-Regel {rule_uuid} gelöscht.",
                en=f"Firewall rule {rule_uuid} deleted.",
            )
        return _t(
            de=f"Fehler beim Löschen der Regel: {result}",
            en=f"Error deleting rule: {result}",
        )
    except Exception as e:
        logger.error("Failed to delete OPNsense firewall rule: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
        )


@tool
async def create_opnsense_nat_rule(
    interface: str,
    protocol: str,
    source: str,
    destination: str,
    target: str,
    target_port: str,
    description: str = "",
    connection_id: str = ""
) -> str:
    """
    Creates a new NAT rule (port forwarding) on OPNsense.
    Use this tool to add a NAT rule. Requires confirmation.
    """
    try:
        payload = {
            "rule": {
                "interface": interface,
                "protocol": protocol,
                "source": source,
                "destination": destination,
                "target": target,
                "target_port": target_port,
                "descr": description,
                "enabled": "1",
            }
        }
        result = await _opnsense_request(
            "/api/firewall/filter/addRule",
            connection_id,
            method="POST",
            json_data=payload
        )
        if result.get("status") == "ok":
            return _t(
                de=f"NAT-Regel erstellt: {description}",
                en=f"NAT rule created: {description}",
            )
        return _t(
            de=f"Fehler beim Erstellen der NAT-Regel: {result}",
            en=f"Error creating NAT rule: {result}",
        )
    except Exception as e:
        logger.error("Failed to create OPNsense NAT rule: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
        )


@tool
async def delete_opnsense_nat_rule(rule_uuid: str, connection_id: str = "") -> str:
    """
    Deletes a NAT rule by UUID. Use this tool to remove a NAT rule. Requires confirmation.
    """
    try:
        result = await _opnsense_request(
            f"/api/firewall/filter/deleteRule/{rule_uuid}",
            connection_id,
            method="POST"
        )
        if result.get("status") == "ok":
            return _t(
                de=f"NAT-Regel {rule_uuid} gelöscht.",
                en=f"NAT rule {rule_uuid} deleted.",
            )
        return _t(
            de=f"Fehler beim Löschen der NAT-Regel: {result}",
            en=f"Error deleting NAT rule: {result}",
        )
    except Exception as e:
        logger.error("Failed to delete OPNsense NAT rule: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
        )


@tool
async def restart_opnsense_service(service_name: str, connection_id: str = "") -> str:
    """
    Restarts an OPNsense service (e.g. 'unbound', 'dhcpd', 'openvpn').
    Use this tool to restart a service on OPNsense.
    """
    try:
        result = await _opnsense_request(
            f"/api/core/service/restart/{service_name}",
            connection_id,
            method="POST"
        )

        if result.get("status") == "ok":
            return _t(
                de=f"Service '{service_name}' wurde neu gestartet.",
                en=f"Service '{service_name}' has been restarted.",
            )
        return _t(
            de=f"Fehler beim Neustart: {result}",
            en=f"Restart failed: {result}",
        )
    except Exception as e:
        logger.error("Failed to restart OPNsense service: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
        )


@tool
async def get_opnsense_logs(lines: int = 50, connection_id: str = "") -> List[Dict]:
    """
    Retrieves firewall logs (latest entries).
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
        logger.error("Failed to retrieve OPNsense logs: %s", e)
        return [{"error": str(e)}]
