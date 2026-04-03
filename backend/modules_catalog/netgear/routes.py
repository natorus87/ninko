"""
Netgear Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.netgear.routes")

router = APIRouter(prefix="/api/netgear", tags=["netgear"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    from .manifest import check_netgear_health

    return await check_netgear_health()


@router.get("/status")
async def get_status(connection_id: str = ""):
    """Get Netgear device status for dashboard."""
    try:
        from .tools import _get_api_client, _netgear_request

        client = await _get_api_client(connection_id)
        sysinfo = await _netgear_request(client, "/sysinfo")
        ports = await _netgear_request(client, "/portinfo")

        port_list = ports.get("port_info", []) if isinstance(ports, dict) else ports

        return {
            "hostname": sysinfo.get("model", ""),
            "model": sysinfo.get("model", ""),
            "firmware": sysinfo.get("firmware_version", ""),
            "ports_count": len(port_list),
        }
    except Exception as e:
        return {"error": str(e)}
