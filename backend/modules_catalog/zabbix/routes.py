"""Zabbix module API routes."""

from fastapi import APIRouter

from core.schemas import ApiResponse

router = APIRouter(tags=["zabbix"])


@router.get("/status")
async def get_status(connection_id: str = "") -> ApiResponse:
    """Get Zabbix server status."""
    from modules_catalog.zabbix.tools import get_zabbix_status

    try:
        result = await get_zabbix_status.ainvoke({"connection_id": connection_id})
        return ApiResponse(data=result)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/hosts")
async def get_hosts(connection_id: str = "") -> ApiResponse:
    """List all Zabbix hosts."""
    from modules_catalog.zabbix.tools import list_zabbix_hosts

    try:
        result = await list_zabbix_hosts.ainvoke({"connection_id": connection_id})
        return ApiResponse(data={"hosts": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/hosts/{host_id}")
async def get_host(host_id: str, connection_id: str = "") -> ApiResponse:
    """Get host details."""
    from modules_catalog.zabbix.tools import get_zabbix_host

    try:
        result = await get_zabbix_host.ainvoke(
            {"host_id": host_id, "connection_id": connection_id}
        )
        return ApiResponse(data=result)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/items")
async def get_items(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """List monitoring items."""
    from modules_catalog.zabbix.tools import list_zabbix_items

    try:
        result = await list_zabbix_items.ainvoke(
            {"host_id": host_id, "connection_id": connection_id}
        )
        return ApiResponse(data={"items": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/triggers")
async def get_triggers(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """List triggers."""
    from modules_catalog.zabbix.tools import list_zabbix_triggers

    try:
        result = await list_zabbix_triggers.ainvoke(
            {"host_id": host_id, "connection_id": connection_id}
        )
        return ApiResponse(data={"triggers": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/problems")
async def get_problems(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """Get current problems."""
    from modules_catalog.zabbix.tools import get_zabbix_problems

    try:
        result = await get_zabbix_problems.ainvoke(
            {"host_id": host_id, "connection_id": connection_id}
        )
        return ApiResponse(data={"problems": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/graphs")
async def get_graphs(host_id: str = "", connection_id: str = "") -> ApiResponse:
    """List graphs."""
    from modules_catalog.zabbix.tools import list_zabbix_graphs

    try:
        result = await list_zabbix_graphs.ainvoke(
            {"host_id": host_id, "connection_id": connection_id}
        )
        return ApiResponse(data={"graphs": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/groups")
async def get_groups(connection_id: str = "") -> ApiResponse:
    """List host groups."""
    from modules_catalog.zabbix.tools import get_zabbix_host_group

    try:
        result = await get_zabbix_host_group.ainvoke({"connection_id": connection_id})
        return ApiResponse(data={"groups": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/templates")
async def get_templates(connection_id: str = "") -> ApiResponse:
    """List templates."""
    from modules_catalog.zabbix.tools import list_zabbix_templates

    try:
        result = await list_zabbix_templates.ainvoke({"connection_id": connection_id})
        return ApiResponse(data={"templates": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/actions")
async def get_actions(connection_id: str = "") -> ApiResponse:
    """List actions."""
    from modules_catalog.zabbix.tools import list_zabbix_actions

    try:
        result = await list_zabbix_actions.ainvoke({"connection_id": connection_id})
        return ApiResponse(data={"actions": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.get("/history/{item_id}")
async def get_history(
    item_id: str, limit: int = 50, connection_id: str = ""
) -> ApiResponse:
    """Get item history."""
    from modules_catalog.zabbix.tools import get_zabbix_history

    try:
        result = await get_zabbix_history.ainvoke(
            {
                "item_id": item_id,
                "from_time": "",
                "limit": limit,
                "connection_id": connection_id,
            }
        )
        return ApiResponse(data={"history": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.post("/hosts")
async def create_host(
    host_name: str, ip: str, group_id: str = "1", connection_id: str = ""
) -> ApiResponse:
    """Create a new host."""
    from modules_catalog.zabbix.tools import create_zabbix_host

    try:
        result = await create_zabbix_host.ainvoke(
            {
                "host_name": host_name,
                "ip": ip,
                "group_id": group_id,
                "connection_id": connection_id,
            }
        )
        return ApiResponse(data=result)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)


@router.delete("/hosts/{host_id}")
async def delete_host(host_id: str, connection_id: str = "") -> ApiResponse:
    """Delete a host."""
    from modules_catalog.zabbix.tools import delete_zabbix_host

    try:
        result = await delete_zabbix_host.ainvoke(
            {"host_id": host_id, "connection_id": connection_id}
        )
        return ApiResponse(data=result)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(error=str(exc), success=False)
