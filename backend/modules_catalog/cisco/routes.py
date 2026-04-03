"""
Cisco Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.cisco.routes")

router = APIRouter(prefix="/api/cisco", tags=["cisco"])


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    from .manifest import check_cisco_health

    return await check_cisco_health()


@router.get("/status")
async def get_status(connection_id: str = ""):
    """Get Cisco device status for dashboard."""
    try:
        from .tools import _get_api_client, _cisco_request

        client = await _get_api_client(connection_id)
        device = await _cisco_request("GET", "/platform/mgmt/operational", client)
        ifaces = await _cisco_request("GET", "/interfaces", client)
        vlans = await _cisco_request("GET", "/vlans", client)

        return {
            "hostname": device.get("hostname", ""),
            "model": device.get("model", ""),
            "interfaces_count": len(ifaces.get("interface", [])),
            "vlans_count": len(vlans.get("vlan", [])),
        }
    except Exception as e:
        return {"error": str(e)}
