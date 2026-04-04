"""Zabbix module API routes."""

from typing import Optional

from fastapi import APIRouter, Query

from core.connections import ConnectionManager
from core.schemas import ApiResponse
from agents.base_agent import _t

router = APIRouter(prefix="/zabbix", tags=["zabbix"])


@router.get("/status")
async def get_status(connection_id: str = "") -> ApiResponse:
    """Get Zabbix server status."""
    from modules_catalog.zabbix.tools import get_zabbix_status

    try:
        result = await get_zabbix_status(connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/hosts")
async def get_hosts(connection_id: str = "") -> ApiResponse:
    """List all Zabbix hosts."""
    from modules_catalog.zabbix.tools import list_zabbix_hosts

    try:
        result = await list_zabbix_hosts(connection_id)
        return ApiResponse(data={"hosts": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/hosts/{host_id}")
async def get_host(host_id: str, connection_id: str = "") -> ApiResponse:
    """Get host details."""
    from modules_catalog.zabbix.tools import get_zabbix_host

    try:
        result = await get_zabbix_host(host_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/items")
async def get_items(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """List monitoring items."""
    from modules_catalog.zabbix.tools import list_zabbix_items

    try:
        result = await list_zabbix_items(host_id, connection_id)
        return ApiResponse(data={"items": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/triggers")
async def get_triggers(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """List triggers."""
    from modules_catalog.zabbix.tools import list_zabbix_triggers

    try:
        result = await list_zabbix_triggers(host_id, connection_id)
        return ApiResponse(data={"triggers": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/problems")
async def get_problems(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """Get current problems."""
    from modules_catalog.zabbix.tools import get_zabbix_problems

    try:
        result = await get_zabbix_problems(host_id, connection_id)
        return ApiResponse(data={"problems": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/graphs")
async def get_graphs(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """List graphs."""
    from modules_catalog.zabbix.tools import list_zabbix_graphs

    try:
        result = await list_zabbix_graphs(host_id, connection_id)
        return ApiResponse(data={"graphs": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/groups")
async def get_groups(connection_id: str = "") -> ApiResponse:
    """List host groups."""
    from modules_catalog.zabbix.tools import get_zabbix_host_group

    try:
        result = await get_zabbix_host_group(connection_id)
        return ApiResponse(data={"groups": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/templates")
async def get_templates(connection_id: str = "") -> ApiResponse:
    """List templates."""
    from modules_catalog.zabbix.tools import list_zabbix_templates

    try:
        result = await list_zabbix_templates(connection_id)
        return ApiResponse(data={"templates": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/actions")
async def get_actions(connection_id: str = "") -> ApiResponse:
    """List actions."""
    from modules_catalog.zabbix.tools import list_zabbix_actions

    try:
        result = await list_zabbix_actions(connection_id)
        return ApiResponse(data={"actions": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.get("/history/{item_id}")
async def get_history(
    item_id: str, limit: int = 50, connection_id: str = ""
) -> ApiResponse:
    """Get item history."""
    from modules_catalog.zabbix.tools import get_zabbix_history

    try:
        result = await get_zabbix_history(item_id, "", limit, connection_id)
        return ApiResponse(data={"history": result})
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.post("/hosts")
async def create_host(
    host_name: str, ip: str, group_id: str = "1", connection_id: str = ""
) -> ApiResponse:
    """Create a new host."""
    from modules_catalog.zabbix.tools import create_zabbix_host

    try:
        result = await create_zabbix_host(host_name, ip, group_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)


@router.delete("/hosts/{host_id}")
async def delete_host(host_id: str, connection_id: str = "") -> ApiResponse:
    """Delete a host."""
    from modules_catalog.zabbix.tools import delete_zabbix_host

    try:
        result = await delete_zabbix_host(host_id, connection_id)
        return ApiResponse(data=result)
    except Exception as e:
        return ApiResponse(error=str(e), success=False)
