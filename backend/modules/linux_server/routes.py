"""
Linux Server Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from modules.linux_server.tools import (
    run_command,
    get_system_info,
    get_disk_usage,
    get_top_processes,
    list_services,
    service_action as service_action_tool,
    get_journal,
    get_network_info,
)

logger = logging.getLogger("kumio.modules.linux_server.routes")
router = APIRouter()


@router.get("/info")
async def system_info(connection_id: str = ""):
    """System-Informationen abrufen."""
    return await get_system_info.ainvoke({"connection_id": connection_id})


@router.get("/disk")
async def disk_usage(connection_id: str = ""):
    """Festplattennutzung."""
    return await get_disk_usage.ainvoke({"connection_id": connection_id})


@router.get("/processes")
async def processes(sort_by: str = "cpu", count: int = 10, connection_id: str = ""):
    """Aktivste Prozesse."""
    return await get_top_processes.ainvoke({"sort_by": sort_by, "count": count, "connection_id": connection_id})


@router.get("/services")
async def services(status_filter: str = "all", connection_id: str = ""):
    """Systemd-Services auflisten."""
    return await list_services.ainvoke({"status_filter": status_filter, "connection_id": connection_id})


@router.post("/service/{service_name}/{action}")
async def service_action(service_name: str, action: str, connection_id: str = ""):
    """Service-Aktion ausführen."""
    return await service_action_tool.ainvoke({"service": service_name, "action": action, "connection_id": connection_id})


@router.get("/journal")
async def journal(service: str = "", lines: int = 50, connection_id: str = ""):
    """Journal-Logs abrufen."""
    return await get_journal.ainvoke({"service": service, "lines": lines, "connection_id": connection_id})


@router.get("/network")
async def network(connection_id: str = ""):
    """Netzwerk-Informationen."""
    return await get_network_info.ainvoke({"connection_id": connection_id})


@router.post("/command")
async def execute_command(cmd: str, connection_id: str = ""):
    """Befehl ausführen."""
    return await run_command.ainvoke({"cmd": cmd, "connection_id": connection_id})
