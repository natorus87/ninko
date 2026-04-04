"""
Synology Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import get_synology_system_info, get_synology_storage, get_synology_packages

logger = logging.getLogger("ninko.modules.synology.routes")
router = APIRouter()


@router.get("/status")
async def get_status(connection_id: str = "") -> dict:
    """REST endpoint for the UI frontend."""
    try:
        result = await get_synology_system_info.ainvoke(
            {"connection_id": connection_id}
        )
        return {"status": "ok", "data": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}


@router.get("/storage")
async def get_storage(connection_id: str = "") -> dict:
    """Get storage information."""
    try:
        result = await get_synology_storage.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}


@router.get("/packages")
async def get_packages(connection_id: str = "") -> dict:
    """Get installed packages."""
    try:
        result = await get_synology_packages.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}
