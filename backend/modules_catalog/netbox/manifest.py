"""NetBox module manifest."""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_netbox_health(connection_id: str = "") -> dict:
    """Health check for NetBox API."""
    from .tools import get_netbox_status

    try:
        result = await get_netbox_status(connection_id)
        return {"status": "ok", "detail": "NetBox reachable", "info": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="netbox",
    display_name="NetBox",
    description="NetBox DCIM & IPAM – Devices, Circuits, IP-Adressen, VLANs und Rack-Management.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="NETBOX_",
    required_secrets=["NETBOX_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "netbox",
        "dcim",
        "ipam",
        "rack",
        "vlan",
        "ip address",
        "circuit",
    ],
    api_prefix="/api/netbox",
    dashboard_tab={
        "id": "netbox",
        "label": "NetBox",
        "icon": "🧭",
    },
    health_check=check_netbox_health,
)
