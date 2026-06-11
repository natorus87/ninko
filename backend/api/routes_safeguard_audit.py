"""
Ninko Safeguard Audit API — read and clear the safeguard audit log.

Routes:
    GET    /api/safeguard/audit       — retrieve audit entries (with optional filters)
    DELETE /api/safeguard/audit       — clear the audit log
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from core.redis_client import get_redis
from core.safeguard import ActionCategory, SafeguardMiddleware
from schemas.safeguard import (
    SafeguardAuditClearResponse,
    SafeguardAuditListResponse,
    SafeguardMetricsResponse,
)

logger = logging.getLogger("ninko.api.safeguard_audit")
router = APIRouter(prefix="/api/safeguard/audit", tags=["Safeguard Audit"])

AUDIT_LOG_KEY = "ninko:safeguard_audit"
MAX_ENTRIES = 5000


@router.get("/", response_model=SafeguardAuditListResponse)
async def get_audit_log(
    category: Optional[str] = Query(None, description="Filter by category: DESTRUCTIVE, STATE_CHANGING, PROMPT_INJECTION, UNKNOWN"),
    action: Optional[str] = Query(None, description="Filter by action: user_message, tool_confirmed, classifier_error"),
    outcome: Optional[str] = Query(None, description="Filter by outcome: pending, confirmed, auto_approved, fail_safe, fail_open"),
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    session_id: Optional[str] = Query(None, description="Filter by session ID"),
    from_ts: Optional[float] = Query(None, description="Unix timestamp start"),
    to_ts: Optional[float] = Query(None, description="Unix timestamp end"),
    search: Optional[str] = Query(None, description="Free-text search in text/rationale"),
    limit: int = Query(200, le=2000),
) -> SafeguardAuditListResponse:
    """Retrieve safeguard audit log entries with optional filters."""
    redis = get_redis()
    raw_entries = await redis.connection.lrange(AUDIT_LOG_KEY, 0, MAX_ENTRIES - 1)

    entries = []
    for raw in raw_entries:
        try:
            entry = json.loads(raw)
        except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError, json.JSONDecodeError):
            continue

        if category and entry.get("category", "").upper() != category.upper():
            continue
        if action and entry.get("action", "").lower() != action.lower():
            continue
        if outcome and entry.get("outcome", "").lower() != outcome.lower():
            continue
        if agent_id and agent_id.lower() not in entry.get("agent_id", "").lower():
            continue
        if session_id and session_id.lower() not in entry.get("session_id", "").lower():
            continue
        if from_ts and entry.get("timestamp", 0) < from_ts:
            continue
        if to_ts and entry.get("timestamp", 0) > to_ts:
            continue
        if search:
            search_lower = search.lower()
            text_match = search_lower in entry.get("text", "").lower()
            rationale_match = search_lower in entry.get("rationale", "").lower()
            if not text_match and not rationale_match:
                continue

        entries.append(entry)
        if len(entries) >= limit:
            break

    return SafeguardAuditListResponse(entries=entries, total=len(entries))


@router.get("/metrics", response_model=SafeguardMetricsResponse)
async def get_safeguard_metrics(request: Request) -> SafeguardMetricsResponse:
    """Return safeguard latency percentiles and path breakdown from recent checks."""
    sg: SafeguardMiddleware | None = getattr(request.app.state, "safeguard", None)
    if sg is None:
        return SafeguardMetricsResponse()
    data = await sg.get_metrics()
    return SafeguardMetricsResponse(**data)


@router.delete("/", response_model=SafeguardAuditClearResponse)
async def clear_audit_log(request: Request) -> SafeguardAuditClearResponse:
    """Clear the safeguard audit log."""
    try:
        sg: SafeguardMiddleware | None = getattr(request.app.state, "safeguard", None)
        if sg is not None:
            await sg._audit_log(
                action="admin_change",
                category=ActionCategory.STATE_CHANGING,
                text="Safeguard audit log cleared",
                session_id="api",
                agent_id="safeguard_admin",
                tool_name="api:safeguard/audit",
                outcome="admin_change",
                rationale="manual clear",
                profile_id=sg.get_active_profile_id(),
            )
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError, json.JSONDecodeError):
        pass

    redis = get_redis()
    await redis.connection.delete(AUDIT_LOG_KEY)
    logger.info("[Safeguard/Audit] Audit log cleared via API.")
    return SafeguardAuditClearResponse()
