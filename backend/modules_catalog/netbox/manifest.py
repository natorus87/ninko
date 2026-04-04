"""Netbox module manifest."""

from pydantic import Literal

ModuleCategory = Literal[
    "monitoring", "network", "storage", "security", "communication"
]


class ModuleManifest:
    name = "netbox"
    category: ModuleCategory = "network"
    version = "1.0.0"
    description = {
        "de": "NetBox DCIM & IPAM – Devices, Circuits, IP-Adresses, VLANs, Rack-Management",
        "en": "NetBox DCIM & IPAM – Devices, Circuits, IP-Adresses, VLANs, Rack-Management",
    }
    routing_keywords = [
        "netbox",
        "dcim",
        "ipam",
        "device",
        "rack",
        "vlan",
        "ipaddress",
        "circuit",
    ]
    api_prefix = "netbox"
    dashboard_tab = "netbox"
    health_check = "check_netbox_health"


module_manifest = ModuleManifest()


async def check_netbox_health(connection_id: str = "") -> dict:
    """Health check for Netbox API."""
    from modules_catalog.netbox.tools import get_netbox_status

    try:
        result = await get_netbox_status(connection_id)
        return {"status": "healthy", "info": result}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
