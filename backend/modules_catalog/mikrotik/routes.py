"""
MikroTik Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.mikrotik.routes")

router = APIRouter(tags=["mikrotik"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_mikrotik_health

    return await check_mikrotik_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get MikroTik status for dashboard."""
    try:
        from .tools import _get_api_client, MikroTikSession

        client = await _get_api_client(connection_id)
        async with MikroTikSession(client) as mt:
            identity = await mt.request("GET", "/system/identity")
            ifaces = await mt.request("GET", "/interface")
            routes = await mt.request("GET", "/ip/route")
            leases = await mt.request("GET", "/ip/dhcp-server/lease")

        return {
            "hostname": identity[0].get("name", ""),
            "interfaces_count": len(ifaces),
            "routes_count": len(routes),
            "dhcp_leases_count": len(leases),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"error": str(exc)}
