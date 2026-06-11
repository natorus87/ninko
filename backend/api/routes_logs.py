"""
Ninko Logs API – Zentrales Log-Panel.
Liest Einträge aus der Redis-Liste ninko:logs.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from core.auth import auth_tenant_id, resolve_request_auth
from core.redis_client import get_redis
from schemas.logs import LogClearResponse, LogEntry, LogListResponse

logger = logging.getLogger("ninko.api.logs")
router = APIRouter(prefix="/api/logs", tags=["Logs"])

REDIS_LOG_KEY = "ninko:logs"
MAX_LOG_ENTRIES = 10000


@router.get("/", response_model=LogListResponse)
async def get_logs(
    request: Request,
    level: Optional[str] = Query(None, description="Komma-getrennte Level: INFO,WARN,ERROR,CRIT"),
    category: Optional[str] = Query(None, description="Kategorie: agent,workflow,module,system,llm"),
    source: Optional[str] = Query(None, description="Quell-Agent oder Workflow-Name"),
    search: Optional[str] = Query(None, description="Freitextsuche in Message"),
    from_ts: Optional[float] = Query(None, description="Unix-Timestamp von"),
    to_ts: Optional[float] = Query(None, description="Unix-Timestamp bis"),
    limit: int = Query(500, le=2000),
) -> LogListResponse:
    """Log-Einträge mit optionalen Filtern abrufen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))

    # Alle Einträge laden (neueste zuerst via LRANGE von Index 0)
    raw_entries = await redis.connection.lrange(REDIS_LOG_KEY, 0, MAX_LOG_ENTRIES - 1)

    entries = []
    levels_filter = {l.strip().upper() for l in level.split(",")} if level else None

    for raw in raw_entries:
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            continue

        if str(entry.get("tenant_id", "default")).strip().lower() != tenant_id:
            continue

        # Level-Filter
        if levels_filter and entry.get("level", "").upper() not in levels_filter:
            continue

        # Kategorie-Filter
        if category and entry.get("category", "").lower() != category.lower():
            continue

        # Quell-Filter
        if source and source.lower() not in entry.get("source", "").lower():
            continue

        # Zeitraum-Filter
        if from_ts and entry.get("timestamp_unix", 0) < from_ts:
            continue
        if to_ts and entry.get("timestamp_unix", 0) > to_ts:
            continue

        # Freitextsuche
        if search and search.lower() not in entry.get("message", "").lower():
            continue

        entries.append(entry)

        if len(entries) >= limit:
            break

    return LogListResponse(
        entries=[LogEntry(**e) for e in entries],
        total=len(entries),
    )


@router.delete("/", response_model=LogClearResponse)
async def clear_logs(request: Request) -> LogClearResponse:
    """Log-Einträge des aktuellen Tenants löschen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    raw_entries = await redis.connection.lrange(REDIS_LOG_KEY, 0, MAX_LOG_ENTRIES - 1)
    kept: list[str] = []
    removed = 0
    for raw in raw_entries:
        try:
            entry = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            continue
        if str(entry.get("tenant_id", "default")).strip().lower() == tenant_id:
            removed += 1
            continue
        kept.append(raw)
    pipe = redis.connection.pipeline()
    pipe.delete(REDIS_LOG_KEY)
    if kept:
        pipe.rpush(REDIS_LOG_KEY, *kept)
        pipe.ltrim(REDIS_LOG_KEY, 0, MAX_LOG_ENTRIES - 1)
    await pipe.execute()
    return {"cleared": True, "removed": removed}
