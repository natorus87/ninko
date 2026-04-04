"""
Jira Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import get_jira_projects, get_jira_issues

logger = logging.getLogger("ninko.modules.jira.routes")
router = APIRouter()


@router.get("/projects")
async def get_projects(connection_id: str = "") -> dict:
    """REST endpoint for the UI frontend."""
    try:
        result = await get_jira_projects.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}


@router.get("/issues")
async def get_issues(
    project_key: str = "", status: str = "open", connection_id: str = ""
) -> dict:
    """Get issues."""
    try:
        result = await get_jira_issues.ainvoke(
            {
                "project_key": project_key,
                "status": status,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(e)}
