"""
Checkmk Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from modules.checkmk.tools import (
    checkmk_get_alerts,
    checkmk_get_hosts,
    checkmk_get_services,
)

logger = logging.getLogger("ninko.modules.checkmk.routes")
router = APIRouter()


@router.get("/status")
async def get_status(connection_id: str = "") -> dict:
    """
    REST-Endpunkt für das UI-Frontend.
    Liefert aggregierte Statusdaten für das Dashboard.
    """
    try:
        hosts_result = await checkmk_get_hosts.ainvoke({"connection_id": connection_id})
        services_result = await checkmk_get_services.ainvoke({"connection_id": connection_id})
        alerts_result = await checkmk_get_alerts.ainvoke({"connection_id": connection_id, "max_results": 10})

        return {
            "status": "ok",
            "hosts": hosts_result,
            "services": services_result,
            "alerts": alerts_result,
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/hosts")
async def get_hosts(connection_id: str = "") -> dict:
    """Gibt die Liste der Hosts zurück."""
    try:
        result = await checkmk_get_hosts.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/services")
async def get_services(connection_id: str = "", host_name: str = "") -> dict:
    """Gibt die Liste der Services zurück."""
    try:
        result = await checkmk_get_services.ainvoke({"connection_id": connection_id, "host_name": host_name})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/alerts")
async def get_alerts(connection_id: str = "", max_results: int = 20) -> dict:
    """Gibt aktuelle Alarme zurück."""
    try:
        result = await checkmk_get_alerts.ainvoke({"connection_id": connection_id, "max_results": max_results})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/health")
async def health_check(connection_id: str = "") -> dict:
    """Health-Check Endpunkt."""
    try:
        await checkmk_get_hosts.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "detail": "Checkmk erreichbar"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
