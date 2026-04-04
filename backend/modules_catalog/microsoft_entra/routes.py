"""
Microsoft Entra Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.microsoft_entra.routes")

router = APIRouter(prefix="/api/microsoft_entra", tags=["microsoft_entra"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_microsoft_entra_health

    return await check_microsoft_entra_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get Entra ID status for dashboard."""
    try:
        from .tools import _get_token, _graph_request

        token = await _get_token(connection_id)
        users = await _graph_request("GET", "/users?$top=1", token)
        groups = await _graph_request("GET", "/groups?$top=1", token)
        devices = await _graph_request("GET", "/devices?$top=1", token)

        return {
            "users_count": len(users.get("value", [])),
            "groups_count": len(groups.get("value", [])),
            "devices_count": len(devices.get("value", [])),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"error": str(exc)}
