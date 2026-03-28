"""
OPNsense Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from modules.opnsense.tools import get_opnsense_system_status, get_opnsense_interfaces, get_opnsense_services

logger = logging.getLogger("ninko.modules.opnsense.routes")
router = APIRouter()


@router.get("/status")
async def get_status(connection_id: str = "") -> dict:
    """REST-Endpunkt für das UI-Frontend - System-Status."""
    try:
        result = await get_opnsense_system_status.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/interfaces")
async def get_interfaces(connection_id: str = "") -> dict:
    """REST-Endpunkt für Interfaces."""
    try:
        result = await get_opnsense_interfaces.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/services")
async def get_services(connection_id: str = "") -> dict:
    """REST-Endpunkt für Services."""
    try:
        result = await get_opnsense_services.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
