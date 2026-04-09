"""
Ninko Audit API – Tool-Usage Events und Audit Trail.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from core.audit import get_audit_events, get_audit_dates, get_audit_stats
from core.auth import auth_tenant_id, resolve_request_auth

logger = logging.getLogger("ninko.api.audit")
router = APIRouter(prefix="/api/audit", tags=["Audit"])


class ToolEventEntry(BaseModel):
    """Ein einzelnes Tool-Audit-Event."""

    agent_name: str
    tool_name: str
    args: dict[str, Any]
    session_id: str
    timestamp: str
    duration_ms: float
    result_size: int
    error: str | None
    is_readonly: bool


class AuditEventsResponse(BaseModel):
    """Response für Tool-Audit-Events."""

    date: str
    total: int
    events: list[ToolEventEntry]


class AuditDatesResponse(BaseModel):
    """Verfügbare Audit-Daten."""

    dates: list[str]


class AuditStatsResponse(BaseModel):
    """Statistiken für einen Audit-Tag."""

    date: str
    total_events: int
    readonly_count: int
    error_count: int
    unique_agents: int
    agents: list[str]


@router.get("/tools", response_model=AuditEventsResponse)
async def get_tool_audit_events(
    request: Request,
    date: str | None = Query(
        None, description="ISO-Datum (YYYY-MM-DD), default: heute"
    ),
    agent_name: str | None = Query(None, description="Filter nach Agent"),
    tool_name: str | None = Query(None, description="Filter nach Tool"),
    limit: int = Query(100, ge=1, le=1000, description="Max. Anzahl Events"),
) -> AuditEventsResponse:
    """
    Holt Tool-Audit-Events aus Redis mit optionaler Filterung.

    Returns:
        Liste von Tool-Events (neueste zuerst) für das angegebene Datum.
    """
    _ = auth_tenant_id(resolve_request_auth(request))
    events = await get_audit_events(
        date=date,
        agent_name=agent_name,
        tool_name=tool_name,
        limit=limit,
    )

    return AuditEventsResponse(
        date=date or "today",
        total=len(events),
        events=[ToolEventEntry(**e) for e in events],
    )


@router.get("/tools/dates", response_model=AuditDatesResponse)
async def get_available_dates(
    request: Request,
) -> AuditDatesResponse:
    """
    Gibt alle verfügbaren Audit-Datum-Keys zurück.

    Returns:
        Liste von YYYY-MM-DD Strings (neueste zuerst), für die Audit-Daten vorhanden sind.
    """
    _ = auth_tenant_id(resolve_request_auth(request))
    dates = await get_audit_dates()
    return AuditDatesResponse(dates=dates)


@router.get("/tools/stats", response_model=AuditStatsResponse)
async def get_audit_statistics(
    request: Request,
    date: str | None = Query(
        None, description="ISO-Datum (YYYY-MM-DD), default: heute"
    ),
) -> AuditStatsResponse:
    """
    Statistik für einen Tag (oder heute).

    Returns:
        Aggregierte Statistik: total_events, readonly_count, error_count, unique_agents
    """
    _ = auth_tenant_id(resolve_request_auth(request))
    stats = await get_audit_stats(date=date)
    return AuditStatsResponse(**stats)
