"""
Confluence Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import get_confluence_spaces, get_confluence_pages

logger = logging.getLogger("ninko.modules.confluence.routes")
router = APIRouter()


@router.get("/spaces")
async def get_spaces(connection_id: str = "") -> dict:
    """REST endpoint for the UI frontend."""
    try:
        result = await get_confluence_spaces.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


@router.get("/pages")
async def get_pages(space_id: str = "", connection_id: str = "") -> dict:
    """Get pages."""
    try:
        result = await get_confluence_pages.ainvoke(
            {
                "space_id": space_id,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}
