"""
Docker Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from modules.docker.tools import (
    list_containers,
    inspect_container,
    start_container as start_container_tool,
    stop_container as stop_container_tool,
    restart_container as restart_container_tool,
    remove_container as remove_container_tool,
    get_container_logs,
    get_container_stats,
    list_images,
    list_volumes,
    get_docker_info,
    get_docker_version,
    get_docker_disk_usage,
)

logger = logging.getLogger("kumio.modules.docker.routes")
router = APIRouter()


# ═══════════════════════════════════════════════════════
# Container Endpoints
# ═══════════════════════════════════════════════════════

@router.get("/containers")
async def containers(all: bool = True, connection_id: str = ""):
    """Alle Docker-Container."""
    return await list_containers.ainvoke({"all": all, "connection_id": connection_id})


@router.get("/containers/{container_id}")
async def container_inspect(container_id: str, connection_id: str = ""):
    """Detaillierte Container-Informationen."""
    return await inspect_container.ainvoke({"container_id": container_id, "connection_id": connection_id})


@router.post("/containers/{container_id}/start")
async def container_start(container_id: str, connection_id: str = ""):
    """Container starten."""
    return await start_container_tool.ainvoke({"container_id": container_id, "connection_id": connection_id})


@router.post("/containers/{container_id}/stop")
async def container_stop(container_id: str, timeout: int = 10, connection_id: str = ""):
    """Container stoppen."""
    return await stop_container_tool.ainvoke({"container_id": container_id, "timeout": timeout, "connection_id": connection_id})


@router.post("/containers/{container_id}/restart")
async def container_restart(container_id: str, timeout: int = 10, connection_id: str = ""):
    """Container neu starten."""
    return await restart_container_tool.ainvoke({"container_id": container_id, "timeout": timeout, "connection_id": connection_id})


@router.delete("/containers/{container_id}")
async def container_remove(container_id: str, force: bool = False, connection_id: str = ""):
    """Container entfernen."""
    return await remove_container_tool.ainvoke({"container_id": container_id, "force": force, "connection_id": connection_id})


@router.get("/containers/{container_id}/logs")
async def container_logs(container_id: str, tail: int = 100, connection_id: str = ""):
    """Container-Logs abrufen."""
    return await get_container_logs.ainvoke({"container_id": container_id, "tail": tail, "connection_id": connection_id})


@router.get("/containers/{container_id}/stats")
async def container_stats(container_id: str, connection_id: str = ""):
    """Container-Ressourcen-Statistiken."""
    return await get_container_stats.ainvoke({"container_id": container_id, "connection_id": connection_id})


# ═══════════════════════════════════════════════════════
# Image Endpoints
# ═══════════════════════════════════════════════════════

@router.get("/images")
async def images(all: bool = False, connection_id: str = ""):
    """Alle Docker-Images."""
    return await list_images.ainvoke({"all": all, "connection_id": connection_id})


# ═══════════════════════════════════════════════════════
# Volume Endpoints
# ═══════════════════════════════════════════════════════

@router.get("/volumes")
async def volumes(connection_id: str = ""):
    """Alle Docker-Volumes."""
    return await list_volumes.ainvoke({"connection_id": connection_id})


# ═══════════════════════════════════════════════════════
# System Endpoints
# ═══════════════════════════════════════════════════════

@router.get("/info")
async def docker_info(connection_id: str = ""):
    """Docker-System-Informationen."""
    return await get_docker_info.ainvoke({"connection_id": connection_id})


@router.get("/version")
async def docker_version(connection_id: str = ""):
    """Docker-Version."""
    return await get_docker_version.ainvoke({"connection_id": connection_id})


@router.get("/disk-usage")
async def disk_usage(connection_id: str = ""):
    """Docker-Speicherauslastung."""
    return await get_docker_disk_usage.ainvoke({"connection_id": connection_id})
