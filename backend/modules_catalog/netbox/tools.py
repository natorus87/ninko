"""Netbox module — LangGraph @tool functions."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.netbox.tools")


async def _get_netbox_config(connection_id: str = "") -> dict:
    """Load Netbox config and secrets from ConnectionManager."""
    if connection_id:
        conn = await ConnectionManager.get_connection("netbox", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Netbox-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Netbox connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Netbox avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión Netbox con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Netbox con ID '{connection_id}' non trovata.",
                    nl=f"Netbox-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Netbox z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Netbox com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のNetbox接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Netbox连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("netbox")

    if conn:
        vault = get_vault()
        token = conn.vault_keys.get("NETBOX_TOKEN")
        token_value = (
            await vault.get_secret(token) if token else conn.config.get("token", "")
        )
        return {
            "url": conn.config.get("url", ""),
            "token": token_value,
        }

    url = os.environ.get("NETBOX_URL", "")
    token = os.environ.get("NETBOX_TOKEN", "")

    if not url:
        raise ValueError(
            _t(
                de="Keine Netbox-Verbindung konfiguriert. Bitte Netbox-URL in den Einstellungen setzen.",
                en="No Netbox connection configured. Please set Netbox URL in settings.",
                fr="Aucune connexion Netbox configurée. Veuillez définir l'URL Netbox dans les paramètres.",
                es="No hay conexión Netbox configurada. Por favor configure la URL de Netbox en la configuración.",
                it="Nessuna connessione Netbox configurata. Per favore imposta l'URL di Netbox nelle impostazioni.",
                nl="Geen Netbox-verbinding geconfigureerd. Stel alstublieft de Netbox-URL in in de instellingen.",
                pl="Nie skonfigurowano połączenia Netbox. Ustaw adres URL Netbox w ustawieniach.",
                pt="Nenhuma conexão Netbox configurada. Por favor, defina a URL do Netbox nas configurações.",
                ja="Netbox接続が設定されていません。設定でNetboxのURLを設定してください。",
                zh="未配置Netbox连接。请在设置中设置Netbox URL。",
            )
        )

    return {"url": url, "token": token}


async def _netbox_request(
    method: str, endpoint: str, url: str, token: str, json_data: dict = None
) -> Any:
    """Make a request to Netbox API."""
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        if method == "GET":
            resp = await client.get(f"{url}{endpoint}", headers=headers)
        elif method == "POST":
            resp = await client.post(
                f"{url}{endpoint}", headers=headers, json=json_data
            )
        elif method == "PUT":
            resp = await client.put(f"{url}{endpoint}", headers=headers, json=json_data)
        elif method == "PATCH":
            resp = await client.patch(
                f"{url}{endpoint}", headers=headers, json=json_data
            )
        elif method == "DELETE":
            resp = await client.delete(f"{url}{endpoint}", headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise ValueError(f"Netbox API error: {resp.status_code} - {resp.text}")

        return resp.json()


@tool("get_netbox_status")
async def get_netbox_status(connection_id: str = "") -> Dict:
    """
    Get Netbox server status and version.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        Dict with version, status, and info
    """
    config = await _get_netbox_config(connection_id)
    result = await _netbox_request("GET", "/api/", config["url"], config["token"])

    return {
        "version": result.get("version", "unknown"),
        "api_version": result.get("api_version", "unknown"),
        "plugins": result.get("plugins", []),
        "status": "online",
    }


@tool("list_netbox_sites")
async def list_netbox_sites(connection_id: str = "") -> List[Dict]:
    """
    List all sites in Netbox.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        List of site objects
    """
    config = await _get_netbox_config(connection_id)
    result = await _netbox_request(
        "GET", "/api/dcim/sites/", config["url"], config["token"]
    )

    sites = []
    for site in result.get("results", []):
        sites.append(
            {
                "id": site.get("id"),
                "name": site.get("name"),
                "slug": site.get("slug"),
                "status": site.get("status", {}).get("label"),
                "facility": site.get("facility"),
                "asn": site.get("asn"),
            }
        )

    return sites


@tool("get_netbox_site")
async def get_netbox_site(site_id: int, connection_id: str = "") -> Dict:
    """
    Get detailed site information.

    Args:
        site_id: Netbox site ID
        connection_id: Optional connection ID for named connection

    Returns:
        Site details
    """
    config = await _get_netbox_config(connection_id)
    result = await _netbox_request(
        "GET", f"/api/dcim/sites/{site_id}/", config["url"], config["token"]
    )

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "slug": result.get("slug"),
        "status": result.get("status", {}).get("label"),
        "facility": result.get("facility"),
        "asn": result.get("asn"),
        "description": result.get("description"),
        "physical_address": result.get("physical_address"),
        "contact": result.get("contact"),
    }


@tool("list_netbox_devices")
async def list_netbox_devices(
    site_id: int = None, role: str = None, connection_id: str = ""
) -> List[Dict]:
    """
    List devices in Netbox.

    Args:
        site_id: Optional site ID to filter devices
        role: Optional device role to filter
        connection_id: Optional connection ID for named connection

    Returns:
        List of device objects
    """
    config = await _get_netbox_config(connection_id)
    params = []
    if site_id:
        params.append(f"site_id={site_id}")
    if role:
        params.append(f"role={role}")

    query = f"?{'&'.join(params)}" if params else ""
    result = await _netbox_request(
        "GET", f"/api/dcim/devices/{query}", config["url"], config["token"]
    )

    devices = []
    for device in result.get("results", []):
        devices.append(
            {
                "id": device.get("id"),
                "name": device.get("name"),
                "display": device.get("display"),
                "status": device.get("status", {}).get("label"),
                "site": device.get("site", {}).get("name"),
                "role": device.get("device_role", {}).get("name"),
                "platform": device.get("platform", {}).get("name"),
                "primary_ip": device.get("primary_ip", {}).get("address")
                if device.get("primary_ip")
                else None,
            }
        )

    return devices


@tool("get_netbox_device")
async def get_netbox_device(device_id: int, connection_id: str = "") -> Dict:
    """
    Get detailed device information.

    Args:
        device_id: Netbox device ID
        connection_id: Optional connection ID for named connection

    Returns:
        Device details including interfaces, IP addresses
    """
    config = await _get_netbox_config(connection_id)
    result = await _netbox_request(
        "GET", f"/api/dcim/devices/{device_id}/", config["url"], config["token"]
    )

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "display": result.get("display"),
        "status": result.get("status", {}).get("label"),
        "site": result.get("site", {}).get("name"),
        "role": result.get("device_role", {}).get("name"),
        "platform": result.get("platform", {}).get("name"),
        "primary_ip": result.get("primary_ip", {}).get("address")
        if result.get("primary_ip")
        else None,
        "serial": result.get("serial"),
        "asset_tag": result.get("asset_tag"),
        "description": result.get("description"),
    }


@tool("list_netbox_racks")
async def list_netbox_racks(site_id: int = None, connection_id: str = "") -> List[Dict]:
    """
    List racks in Netbox.

    Args:
        site_id: Optional site ID to filter racks
        connection_id: Optional connection ID for named connection

    Returns:
        List of rack objects
    """
    config = await _get_netbox_config(connection_id)
    params = f"?site_id={site_id}" if site_id else ""
    result = await _netbox_request(
        "GET", f"/api/dcim/racks/{params}", config["url"], config["token"]
    )

    racks = []
    for rack in result.get("results", []):
        racks.append(
            {
                "id": rack.get("id"),
                "name": rack.get("name"),
                "site": rack.get("site", {}).get("name"),
                "status": rack.get("status", {}).get("label"),
                "u_height": rack.get("u_height"),
            }
        )

    return racks


@tool("get_netbox_rack")
async def get_netbox_rack(rack_id: int, connection_id: str = "") -> Dict:
    """
    Get detailed rack information.

    Args:
        rack_id: Netbox rack ID
        connection_id: Optional connection ID for named connection

    Returns:
        Rack details including devices
    """
    config = await _get_netbox_config(connection_id)
    result = await _netbox_request(
        "GET", f"/api/dcim/racks/{rack_id}/", config["url"], config["token"]
    )

    devices = []
    for dev in result.get("devices", []):
        devices.append(
            {
                "name": dev.get("name"),
                "role": dev.get("device_role", {}).get("name"),
                "face": dev.get("face", {}).get("label"),
                "position": dev.get("position"),
            }
        )

    return {
        "id": result.get("id"),
        "name": result.get("name"),
        "site": result.get("site", {}).get("name"),
        "status": result.get("status", {}).get("label"),
        "u_height": result.get("u_height"),
        "devices": devices,
    }


@tool("list_netbox_vlans")
async def list_netbox_vlans(
    site_id: int = None, group: str = None, connection_id: str = ""
) -> List[Dict]:
    """
    List VLANs in Netbox.

    Args:
        site_id: Optional site ID to filter VLANs
        group: Optional VLAN group to filter
        connection_id: Optional connection ID for named connection

    Returns:
        List of VLAN objects
    """
    config = await _get_netbox_config(connection_id)
    params = []
    if site_id:
        params.append(f"site_id={site_id}")
    if group:
        params.append(f"group={group}")

    query = f"?{'&'.join(params)}" if params else ""
    result = await _netbox_request(
        "GET", f"/api/ipam/vlans/{query}", config["url"], config["token"]
    )

    vlans = []
    for vlan in result.get("results", []):
        vlans.append(
            {
                "id": vlan.get("id"),
                "vid": vlan.get("vid"),
                "name": vlan.get("name"),
                "site": vlan.get("site", {}).get("name") if vlan.get("site") else None,
                "group": vlan.get("group", {}).get("name")
                if vlan.get("group")
                else None,
                "status": vlan.get("status", {}).get("label"),
                "description": vlan.get("description"),
            }
        )

    return vlans


@tool("list_netbox_prefixes")
async def list_netbox_prefixes(
    site_id: int = None, vlan_id: int = None, connection_id: str = ""
) -> List[Dict]:
    """
    List IP prefixes in Netbox.

    Args:
        site_id: Optional site ID to filter prefixes
        vlan_id: Optional VLAN ID to filter prefixes
        connection_id: Optional connection ID for named connection

    Returns:
        List of prefix objects
    """
    config = await _get_netbox_config(connection_id)
    params = []
    if site_id:
        params.append(f"site_id={site_id}")
    if vlan_id:
        params.append(f"vlan_id={vlan_id}")

    query = f"?{'&'.join(params)}" if params else ""
    result = await _netbox_request(
        "GET", f"/api/ipam/prefixes/{query}", config["url"], config["token"]
    )

    prefixes = []
    for prefix in result.get("results", []):
        prefixes.append(
            {
                "id": prefix.get("id"),
                "prefix": prefix.get("prefix"),
                "family": prefix.get("family"),
                "site": prefix.get("site", {}).get("name")
                if prefix.get("site")
                else None,
                "vlan": prefix.get("vlan", {}).get("name")
                if prefix.get("vlan")
                else None,
                "status": prefix.get("status", {}).get("label"),
                "description": prefix.get("description"),
            }
        )

    return prefixes


@tool("list_netbox_ip_addresses")
async def list_netbox_ip_addresses(
    device_id: int = None, interface: str = None, connection_id: str = ""
) -> List[Dict]:
    """
    List IP addresses in Netbox.

    Args:
        device_id: Optional device ID to filter IPs
        interface: Optional interface name to filter
        connection_id: Optional connection ID for named connection

    Returns:
        List of IP address objects
    """
    config = await _get_netbox_config(connection_id)
    params = []
    if device_id:
        params.append(f"device_id={device_id}")
    if interface:
        params.append(f"interface={interface}")

    query = f"?{'&'.join(params)}" if params else ""
    result = await _netbox_request(
        "GET", f"/api/ipam/ip-addresses/{query}", config["url"], config["token"]
    )

    ips = []
    for ip in result.get("results", []):
        ips.append(
            {
                "id": ip.get("id"),
                "address": ip.get("address"),
                "family": ip.get("family"),
                "status": ip.get("status", {}).get("label"),
                "device": ip.get("device", {}).get("name")
                if ip.get("device")
                else None,
                "interface": ip.get("interface", {}).get("name")
                if ip.get("interface")
                else None,
            }
        )

    return ips[:100]


@tool("list_netbox_circuits")
async def list_netbox_circuits(
    provider: str = None, connection_id: str = ""
) -> List[Dict]:
    """
    List circuits in Netbox.

    Args:
        provider: Optional provider to filter circuits
        connection_id: Optional connection ID for named connection

    Returns:
        List of circuit objects
    """
    config = await _get_netbox_config(connection_id)
    params = f"?provider={provider}" if provider else ""
    result = await _netbox_request(
        "GET", f"/api/circuits/circuits/{params}", config["url"], config["token"]
    )

    circuits = []
    for circuit in result.get("results", []):
        circuits.append(
            {
                "id": circuit.get("id"),
                "cid": circuit.get("cid"),
                "provider": circuit.get("provider", {}).get("name"),
                "type": circuit.get("type", {}).get("label"),
                "status": circuit.get("status", {}).get("label"),
                "description": circuit.get("description"),
            }
        )

    return circuits


@tool("list_netbox_cables")
async def list_netbox_cables(connection_id: str = "") -> List[Dict]:
    """
    List cables in Netbox.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        List of cable objects
    """
    config = await _get_netbox_config(connection_id)
    result = await _netbox_request(
        "GET", "/api/dcim/cables/", config["url"], config["token"]
    )

    cables = []
    for cable in result.get("results", []):
        cables.append(
            {
                "id": cable.get("id"),
                "status": cable.get("status", {}).get("label"),
                "a_termination": str(cable.get("a_termination", {})),
                "b_termination": str(cable.get("b_termination", {})),
            }
        )

    return cables[:50]


@tool("list_netbox_clusters")
async def list_netbox_clusters(
    site_id: int = None, connection_id: str = ""
) -> List[Dict]:
    """
    List clusters in Netbox.

    Args:
        site_id: Optional site ID to filter clusters
        connection_id: Optional connection ID for named connection

    Returns:
        List of cluster objects
    """
    config = await _get_netbox_config(connection_id)
    params = f"?site_id={site_id}" if site_id else ""
    result = await _netbox_request(
        "GET", f"/api/virtualization/clusters/{params}", config["url"], config["token"]
    )

    clusters = []
    for cluster in result.get("results", []):
        clusters.append(
            {
                "id": cluster.get("id"),
                "name": cluster.get("name"),
                "type": cluster.get("type", {}).get("name"),
                "site": cluster.get("site", {}).get("name")
                if cluster.get("site")
                else None,
            }
        )

    return clusters


@tool("get_netbox_device_interfaces")
async def get_netbox_device_interfaces(
    device_id: int, connection_id: str = ""
) -> List[Dict]:
    """
    List interfaces for a specific device.

    Args:
        device_id: Netbox device ID
        connection_id: Optional connection ID for named connection

    Returns:
        List of interface objects
    """
    config = await _get_netbox_config(connection_id)
    result = await _netbox_request(
        "GET",
        f"/api/dcim/devices/{device_id}/interfaces/",
        config["url"],
        config["token"],
    )

    interfaces = []
    for iface in result.get("results", []):
        interfaces.append(
            {
                "id": iface.get("id"),
                "name": iface.get("name"),
                "type": iface.get("type", {}).get("label"),
                "enabled": iface.get("enabled"),
                "description": iface.get("description"),
                "mac_address": iface.get("mac_address"),
                "ip_addresses": [
                    ip.get("address") for ip in iface.get("ip_addresses", [])
                ],
            }
        )

    return interfaces
