"""
Template Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import beispiel_tool

logger = logging.getLogger("ninko.modules.template.routes")
router = APIRouter()


@router.get("/status")
async def get_status(connection_id: str = "") -> dict:
    """
    REST-Endpunkt für das UI-Frontend.
    connection_id wird aus dem Query-Parameter übernommen und an das Tool weitergegeben.
    REQUIRED: Route path and logger/module identifiers should be adjusted in copied modules.
    """
    try:
        result = await beispiel_tool.ainvoke({"parameter": "status-check", "connection_id": connection_id})
        return {"status": "ok", "data": result}
    except (ValueError, TypeError, KeyError) as exc:
        logger.error("template status route failed: %s", exc)
        return {"status": "error", "detail": "Request failed. Check server logs."}
