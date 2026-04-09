"""
Ninko Audit Trail – Redis-Persistenz für Tool-Usage Events.

Speichert Tool-Events für 7 Tage in Redis (10k Events/Tag).
Bietet API für Queries mit Filterung nach Datum und Agent.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from core.events import ToolEvent, on_tool_event
from core.redis_client import get_redis

logger = logging.getLogger("ninko.audit")

# Konstanten für Redis-Storage
_MAX_EVENTS_PER_DAY = 9999  # 0-indexed → 10k Events
_RETENTION_DAYS = 7
_KEY_PREFIX = "ninko:audit:tools"


async def _persist_tool_event(event: ToolEvent) -> None:
    """
    Persistiert ein ToolEvent in Redis (LPUSH + LTRIM + EXPIRE).

    Key-Schema: ninko:audit:tools:YYYY-MM-DD
    """
    try:
        redis = get_redis()
        if redis is None:
            logger.warning("Redis nicht verfügbar – Audit-Event verworfen")
            return

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_KEY_PREFIX}:{date_str}"

        # Event als JSON serialisieren
        event_dict = {
            "agent_name": event.agent_name,
            "tool_name": event.tool_name,
            "args": event.args,
            "session_id": event.session_id,
            "timestamp": event.timestamp,
            "duration_ms": event.duration_ms,
            "result_size": event.result_size,
            "error": event.error,
            "is_readonly": event.is_readonly,
        }

        pipe = redis.connection.pipeline()
        pipe.lpush(key, json.dumps(event_dict, default=str))
        pipe.ltrim(key, 0, _MAX_EVENTS_PER_DAY)
        pipe.expire(key, _RETENTION_DAYS * 86400)
        await pipe.execute()

        logger.debug(
            "Audit-Event persistiert: %s.%s", event.agent_name, event.tool_name
        )

    except Exception as exc:
        logger.warning("Audit-Persistenz fehlgeschlagen (nicht blockierend): %s", exc)


# Automatisch registrieren als Event-Listener
@on_tool_event
async def _auto_persist(event: ToolEvent) -> None:
    """Automatische Persistenz für alle Tool-Events."""
    await _persist_tool_event(event)


async def get_audit_events(
    date: str | None = None,
    agent_name: str | None = None,
    tool_name: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    Holt Tool-Audit-Events aus Redis mit optionaler Filterung.

    Args:
        date: ISO-Datum (YYYY-MM-DD) oder None für heute
        agent_name: Filter nach Agent (optional)
        tool_name: Filter nach Tool (optional)
        limit: Max. Anzahl Events (default: 100)

    Returns:
        Liste von Event-Dicts (neueste zuerst)
    """
    try:
        redis = get_redis()
        if redis is None:
            return []

        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_KEY_PREFIX}:{date_str}"

        # LRANGE 0..limit-1 → neueste Events zuerst (durch LPUSH)
        raw_events = await redis.connection.lrange(key, 0, limit - 1)

        results: list[dict[str, Any]] = []
        for raw in raw_events:
            try:
                event = json.loads(raw)

                # Filter anwenden
                if agent_name and event.get("agent_name") != agent_name:
                    continue
                if tool_name and event.get("tool_name") != tool_name:
                    continue

                results.append(event)
            except json.JSONDecodeError:
                logger.warning("Korruptes Audit-Event in Redis: %s", raw[:100])
                continue

        return results

    except Exception as exc:
        logger.warning("Audit-Query fehlgeschlagen: %s", exc)
        return []


async def get_audit_dates() -> list[str]:
    """
    Gibt alle verfügbaren Audit-Datum-Keys zurück.

    Returns:
        Liste von YYYY-MM-DD Strings (neueste zuerst)
    """
    try:
        redis = get_redis()
        if redis is None:
            return []

        # Scan nach Keys mit Pattern ninko:audit:tools:*
        keys = []
        cursor = 0
        pattern = f"{_KEY_PREFIX}:*"

        while True:
            cursor, partial = await redis.connection.scan(
                cursor, match=pattern, count=100
            )
            keys.extend(partial)
            if cursor == 0:
                break

        # Extrahiere Datum aus Keys und sortiere absteigend
        dates = []
        for key in keys:
            try:
                date_str = (
                    key.decode().split(":")[-1]
                    if isinstance(key, bytes)
                    else key.split(":")[-1]
                )
                dates.append(date_str)
            except (IndexError, AttributeError):
                continue

        return sorted(dates, reverse=True)

    except Exception as exc:
        logger.warning("Audit-Dates-Query fehlgeschlagen: %s", exc)
        return []


async def get_audit_stats(date: str | None = None) -> dict[str, Any]:
    """
    Statistik für einen Tag (oder heute).

    Returns:
        Dict mit total_events, readonly_count, error_count, agents
    """
    events = await get_audit_events(date=date, limit=10000)

    agents: set[str] = set()
    readonly_count = 0
    error_count = 0

    for e in events:
        agents.add(e.get("agent_name", "unknown"))
        if e.get("is_readonly"):
            readonly_count += 1
        if e.get("error"):
            error_count += 1

    return {
        "date": date or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "total_events": len(events),
        "readonly_count": readonly_count,
        "error_count": error_count,
        "unique_agents": len(agents),
        "agents": sorted(list(agents)),
    }
