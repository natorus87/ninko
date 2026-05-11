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
    description=(
        "NetBox DCIM & IPAM: data center inventory and IP address management. "
        "Devices, racks, circuits, IP addresses, VLANs."
    ),
    version="1.0.1",
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
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="6" height="4" rx="1"/><rect x="16" y="2" width="6" height="4" rx="1"/><rect x="9" y="10" width="6" height="4" rx="1"/><rect x="2" y="18" width="6" height="4" rx="1"/><rect x="16" y="18" width="6" height="4" rx="1"/><path d="M5 6v3.5c0 .8.7 1.5 1.5 1.5H9"/><path d="M19 6v3.5c0 .8-.7 1.5-1.5 1.5H15"/><path d="M5 18v-3.5c0-.8.7-1.5 1.5-1.5H9"/><path d="M19 18v-3.5c0-.8-.7-1.5-1.5-1.5H15"/></svg>',
    },
    health_check=check_netbox_health,
)
