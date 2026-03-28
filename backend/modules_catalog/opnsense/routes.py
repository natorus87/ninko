"""
OPNsense Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from modules.opnsense.tools import get_opnsense_system_status, get_opnsense_interfaces, get_opnsense_services

logger = logging.getLogger("ninko.modules.opnsense.routes")
router = APIRouter()


class ApiResponse(BaseModel):
    status: str
    data: Any = None
    detail: str = ""


@router.get("/status", response_model=ApiResponse)
async def get_status(connection_id: str = "") -> ApiResponse:
    """REST-Endpunkt für das UI-Frontend - System-Status."""
    try:
        result = await get_opnsense_system_status.ainvoke({"connection_id": connection_id})
        return ApiResponse(status="ok", data=result)
    except Exception as e:
        return ApiResponse(status="error", detail=str(e))


@router.get("/interfaces", response_model=ApiResponse)
async def get_interfaces(connection_id: str = "") -> ApiResponse:
    """REST-Endpunkt für Interfaces."""
    try:
        result = await get_opnsense_interfaces.ainvoke({"connection_id": connection_id})
        return ApiResponse(status="ok", data=result)
    except Exception as e:
        return ApiResponse(status="error", detail=str(e))


@router.get("/services", response_model=ApiResponse)
async def get_services(connection_id: str = "") -> ApiResponse:
    """REST-Endpunkt für Services."""
    try:
        result = await get_opnsense_services.ainvoke({"connection_id": connection_id})
        return ApiResponse(status="ok", data=result)
    except Exception as e:
        return ApiResponse(status="error", detail=str(e))
