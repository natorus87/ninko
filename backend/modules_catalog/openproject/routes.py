"""
OpenProject Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("ninko.modules.openproject.routes")

router = APIRouter(tags=["openproject"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_openproject_health

    return await check_openproject_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get OpenProject status for dashboard."""
    try:
        from .tools import _get_api_client, _op_request

        client = await _get_api_client(connection_id)
        projects = await _op_request("GET", "/projects", client)
        work_packages = await _op_request("GET", "/work_packages?pageSize=1", client)
        users = await _op_request("GET", "/users", client)

        return {
            "projects_count": len(projects.get("_embedded", {}).get("elements", [])),
            "work_packages_count": len(
                work_packages.get("_embedded", {}).get("elements", [])
            ),
            "users_count": len(users.get("_embedded", {}).get("elements", [])),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
