"""
HPE iLO Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.hpe_ilo.routes")

router = APIRouter(tags=["hpe_ilo"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_hpe_ilo_health

    return await check_hpe_ilo_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get iLO and server status for dashboard."""
    try:
        from .tools import _get_api_client, _ilo_request

        client = await _get_api_client(connection_id)
        systems = await _ilo_request("GET", "/systems", client)
        members = systems.get("Members", [])

        if not members:
            return {"error": "No servers found"}

        system = await _ilo_request(
            "GET", members[0]["@odata.id"].replace("/rest/v1", ""), client
        )

        manager = await _ilo_request("GET", "/manager", client)
        hp_manager = manager.get("Oem", {}).get("Hp", {})

        system_oem = system.get("Oem", {})
        hp_system = system_oem.get("Hp", {})

        return {
            "manager": {
                "manager_type": hp_manager.get("ManagerType", ""),
                "firmware_version": hp_manager.get("ManagerVersion", {}).get(
                    "Version", ""
                ),
                "license": hp_manager.get("License", ""),
            },
            "system": {
                "model": system.get("Model", ""),
                "manufacturer": system.get("Manufacturer", ""),
                "serial_number": system.get("SerialNumber", ""),
                "uuid": system.get("UUID", ""),
                "power_state": system.get("PowerState", ""),
                "health": hp_system.get("Health", "OK"),
            },
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"error": str(exc)}
