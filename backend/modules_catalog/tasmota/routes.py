"""
Tasmota Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import get_tasmota_status, get_tasmota_sensors, get_tasmota_power

logger = logging.getLogger("ninko.modules.tasmota.routes")
router = APIRouter()


@router.get("/status")
async def get_status(connection_id: str = "") -> dict:
    """REST-Endpunkt für das UI-Frontend - allgemeiner Status."""
    try:
        result = await get_tasmota_status.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/sensors")
async def get_sensors(connection_id: str = "") -> dict:
    """REST-Endpunkt für Sensor-Daten."""
    try:
        result = await get_tasmota_sensors.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/power")
async def get_power(connection_id: str = "") -> dict:
    """REST-Endpunkt für Power-Status."""
    try:
        result = await get_tasmota_power.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
