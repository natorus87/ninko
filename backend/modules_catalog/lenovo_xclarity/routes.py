"""
Lenovo XClarity Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.lenovo_xclarity.routes")

router = APIRouter(prefix="/api/lenovo_xclarity", tags=["lenovo_xclarity"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    from .manifest import check_lenovo_xclarity_health

    return await check_lenovo_xclarity_health()


@router.get("/status")
async def get_status(connection_id: str = ""):
    """Get XClarity status for dashboard."""
    try:
        from .tools import _get_api_client, _xclarity_request

        client = await _get_api_client(connection_id)
        servers = await _xclarity_request("GET", "/servers", client)
        chassis = await _xclarity_request("GET", "/chassis", client)
        storage = await _xclarity_request("GET", "/storage", client)

        return {
            "servers_count": len(servers.get("serverList", [])),
            "chassis_count": len(chassis.get("chassisList", [])),
            "storage_count": len(storage.get("storageList", [])),
        }
    except Exception as e:
        return {"error": str(e)}
