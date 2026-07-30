"""Durable Redis Stream journal for typed agent execution events."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

import redis.asyncio as aioredis

from core.agent_events import tenant_id_from_session
from core.config import get_settings
from core.redaction import is_sensitive_key, redact_text
from core.redis_client import RedisClient, get_redis
from core.tool_error_handling import sanitize_tool_output
from schemas.execution import AgentEvent

logger = logging.getLogger("ninko.agent_event_journal")

_CURSOR_PATTERN = re.compile(r"^[0-9]+-[0-9]+$", re.ASCII)
_STREAM_PREFIX = "ninko:agent_events"
_DEFAULT_MAX_EVENTS = 500
_DEFAULT_TTL_SECONDS = 86_400
_MAX_CURSOR_LENGTH = 41
_MAX_STREAM_ID_PART = (2**64) - 1
_MAX_EVENT_BYTES = 65_536


def normalize_event_cursor(cursor: str | None) -> str:
    """Validate a public Redis Stream cursor and return the replay origin."""
    normalized = "0-0" if cursor is None else cursor.strip()
    if (
        len(normalized) > _MAX_CURSOR_LENGTH
        or not _CURSOR_PATTERN.fullmatch(normalized)
    ):
        raise ValueError("Ungültiger AgentEvent-Cursor")
    milliseconds, sequence = normalized.split("-", 1)
    if (
        int(milliseconds) > _MAX_STREAM_ID_PART
        or int(sequence) > _MAX_STREAM_ID_PART
    ):
        raise ValueError("Ungültiger AgentEvent-Cursor")
    return normalized


def _normalize_tenant(tenant_id: str) -> str:
    return (tenant_id or "default").strip().lower().replace(" ", "_") or "default"


def _stream_key(tenant_id: str, session_id: str) -> str:
    tenant = _normalize_tenant(tenant_id)
    session_digest = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    return f"{_STREAM_PREFIX}:{tenant}:{session_digest}"


def _field(fields: dict[Any, Any], name: str) -> Any:
    return fields.get(name, fields.get(name.encode("utf-8")))


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _sanitize_event_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return "..."
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(sanitize_tool_output(value), limit=2_000)
    if isinstance(value, list):
        return [
            _sanitize_event_value(item, depth=depth + 1)
            for item in value[:50]
        ]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, item in list(value.items())[:100]:
            key = str(raw_key)[:120]
            sanitized[key] = (
                "***"
                if is_sensitive_key(key)
                else _sanitize_event_value(item, depth=depth + 1)
            )
        return sanitized
    return redact_text(sanitize_tool_output(str(value)), limit=2_000)


def _safe_persisted_event(event: AgentEvent) -> AgentEvent:
    sanitized = event.model_copy(
        update={"data": _sanitize_event_value(event.data)}
    )
    if len(sanitized.model_dump_json().encode("utf-8")) > _MAX_EVENT_BYTES:
        sanitized = event.model_copy(update={"data": {"truncated": True}})
    if len(sanitized.model_dump_json().encode("utf-8")) > _MAX_EVENT_BYTES:
        raise ValueError("AgentEvent überschreitet die Persistenzgrenze")
    return sanitized


@dataclass(frozen=True)
class JournaledAgentEvent:
    """One persisted event together with its resumable Redis Stream cursor."""

    cursor: str
    event: AgentEvent


class JournaledAgentEventBatch(list[JournaledAgentEvent]):
    """Decoded entries plus the last raw cursor scanned, including poison rows."""

    def __init__(
        self,
        events: list[JournaledAgentEvent],
        *,
        scanned_cursor: str,
    ) -> None:
        super().__init__(events)
        self.scanned_cursor = scanned_cursor


class AgentEventJournal:
    """Tenant-scoped Redis Stream persistence with bounded retention.

    By default, each session retains approximately 500 events for 24 hours.
    Redis applies an approximate MAXLEN trim, and every append refreshes the
    journal TTL without changing the independently configured session-owner
    retention.
    """

    def __init__(
        self,
        redis: RedisClient | None = None,
        *,
        read_connection: Any = None,
        max_events: int = _DEFAULT_MAX_EVENTS,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        """Create a journal and its blocking-read connection contract.

        Production defaults to a dedicated 20-connection read pool so XREAD
        cannot exhaust Ninko's shared Redis pool. Injected Redis or read
        connections remain caller-owned; :meth:`close` only closes the
        production pool created by this constructor.
        """
        if max_events <= 0:
            raise ValueError("max_events muss größer als 0 sein")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds muss größer als 0 sein")
        self._redis = redis or get_redis()
        if read_connection is not None:
            self._read_connection = read_connection
            self._owns_read_connection = False
        elif redis is not None:
            self._read_connection = redis.connection
            self._owns_read_connection = False
        else:
            self._read_connection = aioredis.from_url(
                get_settings().REDIS_URL,
                decode_responses=True,
                encoding="utf-8",
                max_connections=20,
            )
            self._owns_read_connection = True
        self._max_events = max_events
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def stream_key(tenant_id: str, session_id: str) -> str:
        """Return the opaque Redis key for a tenant-owned session stream."""
        return _stream_key(tenant_id, session_id)

    @staticmethod
    def _assert_event_scope(event: AgentEvent) -> None:
        derived_tenant = _normalize_tenant(
            tenant_id_from_session(event.session_id)
        )
        if derived_tenant != _normalize_tenant(event.tenant_id):
            raise ValueError("AgentEvent tenant_id passt nicht zur session_id")

    async def append(self, event: AgentEvent) -> str:
        """Atomically append an event, trim its stream and refresh retention."""
        self._assert_event_scope(event)
        key = _stream_key(event.tenant_id, event.session_id)
        persisted_event = _safe_persisted_event(event)
        pipeline = self._redis.connection.pipeline(transaction=True)
        pipeline.xadd(
            key,
            {"event": persisted_event.model_dump_json()},
            maxlen=self._max_events,
            approximate=True,
        )
        pipeline.expire(key, self._ttl_seconds)
        results = await pipeline.execute()
        return _text(results[0])

    async def read_after(
        self,
        *,
        tenant_id: str,
        session_id: str,
        after: str | None = None,
        limit: int = 100,
    ) -> JournaledAgentEventBatch:
        """Replay up to ``limit`` valid events strictly after a cursor."""
        cursor = normalize_event_cursor(after)
        bounded_limit = min(max(limit, 1), 500)
        key = _stream_key(tenant_id, session_id)
        entries = await self._read_connection.xrange(
            key,
            min=f"({cursor}",
            max="+",
            count=bounded_limit,
        )
        return self._decode_entries(entries, fallback_cursor=cursor)

    async def latest_cursor(
        self,
        *,
        tenant_id: str,
        session_id: str,
    ) -> str:
        """Return the current server-side stream tail, or ``0-0`` if empty."""
        key = _stream_key(tenant_id, session_id)
        entries = await self._read_connection.xrevrange(
            key,
            max="+",
            min="-",
            count=1,
        )
        return _text(entries[0][0]) if entries else "0-0"

    async def wait_after(
        self,
        *,
        tenant_id: str,
        session_id: str,
        after: str,
        timeout_ms: int = 15_000,
        limit: int = 100,
    ) -> JournaledAgentEventBatch:
        """Block until new events arrive after a validated cursor."""
        cursor = normalize_event_cursor(after)
        bounded_timeout = min(max(timeout_ms, 1), 30_000)
        bounded_limit = min(max(limit, 1), 500)
        key = _stream_key(tenant_id, session_id)
        streams = await self._read_connection.xread(
            {key: cursor},
            count=bounded_limit,
            block=bounded_timeout,
        )
        if not streams:
            return JournaledAgentEventBatch([], scanned_cursor=cursor)
        return self._decode_entries(
            streams[0][1],
            fallback_cursor=cursor,
        )

    async def delete_session(self, *, tenant_id: str, session_id: str) -> None:
        """Delete all persisted AgentEvents for a session."""
        await self._redis.connection.delete(
            _stream_key(tenant_id, session_id)
        )

    async def close(self) -> None:
        """Close the dedicated blocking-read pool when this journal owns it."""
        if self._owns_read_connection:
            await self._read_connection.aclose()

    @staticmethod
    def _decode_entries(
        entries: list[Any],
        *,
        fallback_cursor: str,
    ) -> JournaledAgentEventBatch:
        decoded: list[JournaledAgentEvent] = []
        scanned_cursor = fallback_cursor
        invalid_count = 0
        error_type = "Unknown"
        for cursor, fields in entries:
            scanned_cursor = _text(cursor)
            try:
                event_json = _field(fields, "event")
                if event_json is None:
                    raise ValueError("event field fehlt")
                decoded.append(
                    JournaledAgentEvent(
                        cursor=_text(cursor),
                        event=AgentEvent.model_validate_json(event_json),
                    )
                )
            except (TypeError, ValueError) as exc:
                invalid_count += 1
                error_type = type(exc).__name__
        if invalid_count:
            logger.warning(
                "%d ungültige AgentEvent-Journal-Einträge übersprungen (%s)",
                invalid_count,
                error_type,
            )
        return JournaledAgentEventBatch(
            decoded,
            scanned_cursor=scanned_cursor,
        )


_journal: AgentEventJournal | None = None


def get_agent_event_journal() -> AgentEventJournal:
    """Return Ninko's lazy process-wide AgentEvent journal."""
    global _journal
    if _journal is None:
        _journal = AgentEventJournal()
    return _journal
