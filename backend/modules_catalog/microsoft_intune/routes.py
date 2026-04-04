"""
Microsoft Intune Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.microsoft_intune.routes")

router = APIRouter(prefix="/api/microsoft_intune", tags=["microsoft_intune"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_microsoft_intune_health

    return await check_microsoft_intune_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get Intune status for dashboard."""
    try:
        from .tools import _get_token, _graph_request

        token = await _get_token(connection_id)
        devices = await _graph_request(
            "GET", "/deviceManagement/managedDevices?$top=1", token
        )
        policies = await _graph_request(
            "GET", "/deviceManagement/deviceConfigurations?$top=1", token
        )
        apps = await _graph_request(
            "GET", "/deviceAppManagement/mobileApps?$top=1", token
        )

        return {
            "devices_count": len(devices.get("value", [])),
            "policies_count": len(policies.get("value", [])),
            "apps_count": len(apps.get("value", [])),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"error": str(e)}
