"""
Ubiquiti Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.ubiquiti.routes")

router = APIRouter(prefix="/api/ubiquiti", tags=["ubiquiti"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_ubiquiti_health

    return await check_ubiquiti_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get UniFi status for dashboard."""
    try:
        from .tools import _get_api_client, UnifiSession

        client = await _get_api_client(connection_id)
        async with UnifiSession(client) as unifi:
            devices = await unifi.request("/stat/device")
            clients = await unifi.request("/stat/sta")
            wlans = await unifi.request("/rest/wlanconf")

        return {
            "devices_count": len(devices),
            "clients_count": len(clients),
            "wlans_count": len(wlans),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"error": str(exc)}
