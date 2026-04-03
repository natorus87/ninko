"""
Redmine Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import get_redmine_projects, get_redmine_issues

logger = logging.getLogger("ninko.modules.redmine.routes")
router = APIRouter()


@router.get("/projects")
async def get_projects(connection_id: str = "") -> dict:
    """REST endpoint for the UI frontend."""
    try:
        result = await get_redmine_projects.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.get("/issues")
async def get_issues(
    project_id: str = "", status: str = "open", connection_id: str = ""
) -> dict:
    """Get issues."""
    try:
        result = await get_redmine_issues.ainvoke(
            {
                "project_id": project_id,
                "status": status,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
