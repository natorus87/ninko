"""Netbox module API routes."""

from fastapi import APIRouter, Query

from core.schemas import ApiResponse

router = APIRouter(prefix="/netbox", tags=["netbox"])


@router.get("/status")
async def get_status(connection_id: str = "") -> ApiResponse:
    """Get Netbox server status."""
    from modules_catalog.netbox.tools import get_netbox_status

    try:
        result = await get_netbox_status(connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/sites")
async def get_sites(connection_id: str = "") -> ApiResponse:
    """List all sites."""
    from modules_catalog.netbox.tools import list_netbox_sites

    try:
        result = await list_netbox_sites(connection_id)
        return ApiResponse(data={"sites": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/sites/{site_id}")
async def get_site(site_id: int, connection_id: str = "") -> ApiResponse:
    """Get site details."""
    from modules_catalog.netbox.tools import get_netbox_site

    try:
        result = await get_netbox_site(site_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/devices")
async def get_devices(
    site_id: int = None, role: str = "", connection_id: str = ""
) -> ApiResponse:
    """List all devices."""
    from modules_catalog.netbox.tools import list_netbox_devices

    try:
        result = await list_netbox_devices(site_id, role, connection_id)
        return ApiResponse(data={"devices": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/devices/{device_id}")
async def get_device(device_id: int, connection_id: str = "") -> ApiResponse:
    """Get device details."""
    from modules_catalog.netbox.tools import get_netbox_device

    try:
        result = await get_netbox_device(device_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/devices/{device_id}/interfaces")
async def get_device_interfaces(device_id: int, connection_id: str = "") -> ApiResponse:
    """Get device interfaces."""
    from modules_catalog.netbox.tools import get_netbox_device_interfaces

    try:
        result = await get_netbox_device_interfaces(device_id, connection_id)
        return ApiResponse(data={"interfaces": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/racks")
async def get_racks(site_id: int = None, connection_id: str = "") -> ApiResponse:
    """List all racks."""
    from modules_catalog.netbox.tools import list_netbox_racks

    try:
        result = await list_netbox_racks(site_id, connection_id)
        return ApiResponse(data={"racks": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/racks/{rack_id}")
async def get_rack(rack_id: int, connection_id: str = "") -> ApiResponse:
    """Get rack details."""
    from modules_catalog.netbox.tools import get_netbox_rack

    try:
        result = await get_netbox_rack(rack_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/vlans")
async def get_vlans(
    site_id: int = None, group: str = "", connection_id: str = ""
) -> ApiResponse:
    """List all VLANs."""
    from modules_catalog.netbox.tools import list_netbox_vlans

    try:
        result = await list_netbox_vlans(site_id, group, connection_id)
        return ApiResponse(data={"vlans": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/prefixes")
async def get_prefixes(
    site_id: int = None, vlan_id: int = None, connection_id: str = ""
) -> ApiResponse:
    """List all prefixes."""
    from modules_catalog.netbox.tools import list_netbox_prefixes

    try:
        result = await list_netbox_prefixes(site_id, vlan_id, connection_id)
        return ApiResponse(data={"prefixes": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/ip-addresses")
async def get_ip_addresses(
    device_id: int = None, interface: str = "", connection_id: str = ""
) -> ApiResponse:
    """List all IP addresses."""
    from modules_catalog.netbox.tools import list_netbox_ip_addresses

    try:
        result = await list_netbox_ip_addresses(device_id, interface, connection_id)
        return ApiResponse(data={"ip_addresses": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/circuits")
async def get_circuits(provider: str = "", connection_id: str = "") -> ApiResponse:
    """List all circuits."""
    from modules_catalog.netbox.tools import list_netbox_circuits

    try:
        result = await list_netbox_circuits(provider, connection_id)
        return ApiResponse(data={"circuits": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/cables")
async def get_cables(connection_id: str = "") -> ApiResponse:
    """List all cables."""
    from modules_catalog.netbox.tools import list_netbox_cables

    try:
        result = await list_netbox_cables(connection_id)
        return ApiResponse(data={"cables": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/clusters")
async def get_clusters(site_id: int = None, connection_id: str = "") -> ApiResponse:
    """List all clusters."""
    from modules_catalog.netbox.tools import list_netbox_clusters

    try:
        result = await list_netbox_clusters(site_id, connection_id)
        return ApiResponse(data={"clusters": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)
