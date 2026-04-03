"""
Redmine Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging
from typing import Any
from fastapi import APIRouter, Request

from .tools import (
    call_redmine_hrm_api,
    call_redmine_reporting_api,
    create_redmine_hrm_attendance,
    get_redmine_hrm_attendance,
    get_redmine_hrm_attendances,
    get_redmine_hrm_holidays,
    get_redmine_hrm_user_capacity,
    get_redmine_issues,
    get_redmine_project_budgets,
    get_redmine_projects,
    get_redmine_reporting_budgets,
    get_redmine_reporting_time_logs,
)

logger = logging.getLogger("ninko.modules.redmine.routes")
router = APIRouter()
_REDMINE_ROUTE_EXCEPTIONS = (ValueError, TypeError, KeyError, RuntimeError)


@router.get("/projects")
async def get_projects(connection_id: str = "") -> dict[str, Any]:
    """REST endpoint for the UI frontend."""
    try:
        result = await get_redmine_projects.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine projects route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/issues")
async def get_issues(
    project_id: str = "", status: str = "open", connection_id: str = ""
) -> dict[str, Any]:
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
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine issues route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.api_route("/hrm", methods=["GET", "POST", "PUT", "DELETE"])
async def hrm_proxy(
    request: Request,
    endpoint: str,
    connection_id: str = "",
    params_json: str = "",
    payload_json: str = "",
    method: str = "",
) -> dict[str, Any]:
    """
    Proxy for AlphaNodes HRM endpoints.
    method supports GET/POST/PUT/DELETE, endpoint is relative to hrm prefix.
    """
    try:
        result = await call_redmine_hrm_api.ainvoke(
            {
                "method": method or request.method,
                "endpoint": endpoint,
                "params": params_json,
                "payload": payload_json,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine hrm proxy route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.api_route("/reporting", methods=["GET", "POST", "PUT", "DELETE"])
async def reporting_proxy(
    request: Request,
    endpoint: str,
    connection_id: str = "",
    params_json: str = "",
    payload_json: str = "",
    method: str = "",
) -> dict[str, Any]:
    """
    Proxy for AlphaNodes Reporting endpoints.
    method supports GET/POST/PUT/DELETE, endpoint is relative to reporting prefix.
    """
    try:
        result = await call_redmine_reporting_api.ainvoke(
            {
                "method": method or request.method,
                "endpoint": endpoint,
                "params": params_json,
                "payload": payload_json,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine reporting proxy route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/hrm/attendances")
async def hrm_attendances(
    from_date: str = "",
    to_date: str = "",
    user_id: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict[str, Any]:
    try:
        result = await get_redmine_hrm_attendances.ainvoke(
            {
                "from_date": from_date,
                "to_date": to_date,
                "user_id": user_id,
                "limit": limit,
                "offset": offset,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine hrm_attendances route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.post("/hrm/attendances")
async def hrm_create_attendance(
    attendance_payload: dict[str, Any],
    connection_id: str = "",
) -> dict[str, Any]:
    try:
        result = await create_redmine_hrm_attendance.ainvoke(
            {"attendance_payload": attendance_payload, "connection_id": connection_id}
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine hrm_create_attendance route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/hrm/attendances/{attendance_id}")
async def hrm_attendance_by_id(
    attendance_id: str, connection_id: str = ""
) -> dict[str, Any]:
    try:
        result = await get_redmine_hrm_attendance.ainvoke(
            {"attendance_id": attendance_id, "connection_id": connection_id}
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine hrm_attendance_by_id route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/hrm/users/{user_id}/capacity")
async def hrm_user_capacity(
    user_id: str,
    from_date: str = "",
    to_date: str = "",
    connection_id: str = "",
) -> dict[str, Any]:
    try:
        result = await get_redmine_hrm_user_capacity.ainvoke(
            {
                "user_id": user_id,
                "from_date": from_date,
                "to_date": to_date,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine hrm_user_capacity route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/hrm/holidays")
async def hrm_holidays(
    from_date: str = "",
    to_date: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict[str, Any]:
    try:
        result = await get_redmine_hrm_holidays.ainvoke(
            {
                "from_date": from_date,
                "to_date": to_date,
                "limit": limit,
                "offset": offset,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine hrm_holidays route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/reporting/budgets")
async def reporting_budgets(
    from_date: str = "",
    to_date: str = "",
    user_id: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict[str, Any]:
    try:
        result = await get_redmine_reporting_budgets.ainvoke(
            {
                "from_date": from_date,
                "to_date": to_date,
                "user_id": user_id,
                "limit": limit,
                "offset": offset,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine reporting_budgets route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/projects/{project_id}/budgets")
async def project_budgets(
    project_id: str,
    from_date: str = "",
    to_date: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict[str, Any]:
    try:
        result = await get_redmine_project_budgets.ainvoke(
            {
                "project_id": project_id,
                "from_date": from_date,
                "to_date": to_date,
                "limit": limit,
                "offset": offset,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine project_budgets route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}


@router.get("/reporting/time_logs")
async def reporting_time_logs(
    from_date: str = "",
    to_date: str = "",
    user_id: str = "",
    project_id: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict[str, Any]:
    try:
        result = await get_redmine_reporting_time_logs.ainvoke(
            {
                "from_date": from_date,
                "to_date": to_date,
                "user_id": user_id,
                "project_id": project_id,
                "limit": limit,
                "offset": offset,
                "connection_id": connection_id,
            }
        )
        return {"status": "ok", "data": result}
    except _REDMINE_ROUTE_EXCEPTIONS:
        logger.exception("redmine reporting_time_logs route failed")
        return {"status": "error", "detail": "Request failed. Check server logs."}
