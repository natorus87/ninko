"""
Ninko – Pipeline Events.

Strukturierte Events für die Pipeline-Ausführung: routing_started,
pipeline_created, step_started/completed/failed, confirmation_required,
pipeline_completed/failed.

Baut auf demselben Listener-Muster wie core/events.py auf,
ist aber speziell auf Pipeline-Observability zugeschnitten.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Awaitable

logger = logging.getLogger("ninko.pipeline_events")


class PipelineEventType(str, Enum):
    ROUTING_STARTED = "routing_started"
    ROUTING_COMPLETED = "routing_completed"
    PIPELINE_CREATED = "pipeline_created"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    CONFIRMATION_REQUIRED = "confirmation_required"
    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"


@dataclass
class PipelineEvent:
    """Strukturiertes Event der Pipeline-Engine."""

    type: PipelineEventType
    pipeline_id: str
    session_id: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    data: dict[str, Any] = field(default_factory=dict)

    # ── Factory-Methoden ──────────────────────────────────────────────────────

    @classmethod
    def routing_started(cls, session_id: str, message_preview: str = "") -> "PipelineEvent":
        return cls(
            type=PipelineEventType.ROUTING_STARTED,
            pipeline_id="",
            session_id=session_id,
            data={"message_preview": message_preview[:120]},
        )

    @classmethod
    def routing_completed(
        cls,
        session_id: str,
        tier: int,
        target_module: str | None = None,
        duration_ms: float = 0.0,
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.ROUTING_COMPLETED,
            pipeline_id="",
            session_id=session_id,
            data={"tier": tier, "target_module": target_module, "duration_ms": duration_ms},
        )

    @classmethod
    def pipeline_created(
        cls,
        pipeline_id: str,
        session_id: str,
        step_count: int,
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.PIPELINE_CREATED,
            pipeline_id=pipeline_id,
            session_id=session_id,
            data={"step_count": step_count},
        )

    @classmethod
    def step_started(
        cls,
        step_id: str,
        session_id: str,
        module: str,
        idx: int,
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.STEP_STARTED,
            pipeline_id="",
            session_id=session_id,
            data={"step_id": step_id, "module": module, "step_index": idx},
        )

    @classmethod
    def step_completed(
        cls,
        step_id: str,
        session_id: str,
        module: str,
        duration_ms: float = 0.0,
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.STEP_COMPLETED,
            pipeline_id="",
            session_id=session_id,
            data={"step_id": step_id, "module": module, "duration_ms": duration_ms},
        )

    @classmethod
    def step_failed(
        cls,
        step_id: str,
        session_id: str,
        module: str,
        error: str = "",
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.STEP_FAILED,
            pipeline_id="",
            session_id=session_id,
            data={"step_id": step_id, "module": module, "error": error},
        )

    @classmethod
    def confirmation_required(
        cls,
        step_id: str,
        session_id: str,
        module: str,
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.CONFIRMATION_REQUIRED,
            pipeline_id="",
            session_id=session_id,
            data={"step_id": step_id, "module": module},
        )

    @classmethod
    def pipeline_completed(
        cls,
        pipeline_id: str,
        session_id: str,
        status: str,
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.PIPELINE_COMPLETED,
            pipeline_id=pipeline_id,
            session_id=session_id,
            data={"status": status},
        )

    @classmethod
    def pipeline_failed(
        cls,
        pipeline_id: str,
        session_id: str,
        error: str = "",
    ) -> "PipelineEvent":
        return cls(
            type=PipelineEventType.PIPELINE_FAILED,
            pipeline_id=pipeline_id,
            session_id=session_id,
            data={"error": error},
        )


# ── Listener-Registry ─────────────────────────────────────────────────────────

PipelineEventListener = Callable[[PipelineEvent], Awaitable[None]]
_listeners: list[PipelineEventListener] = []
_listener_lock = asyncio.Lock()


async def emit_pipeline_event(event: PipelineEvent) -> None:
    """Emittiert ein PipelineEvent an alle registrierten Listener."""
    logger.debug(
        "PipelineEvent: %s | session=%s | data=%s",
        event.type.value,
        event.session_id,
        event.data,
    )
    async with _listener_lock:
        listeners = _listeners.copy()

    for fn in listeners:
        try:
            await fn(event)
        except Exception as exc:
            logger.warning("PipelineEvent Listener %s fehlgeschlagen: %s", fn.__name__, exc)


def on_pipeline_event(fn: PipelineEventListener) -> PipelineEventListener:
    """Dekorator: Registriert eine Async-Funktion als PipelineEvent-Listener."""
    _listeners.append(fn)
    return fn


def remove_pipeline_listener(fn: PipelineEventListener) -> None:
    """Entfernt einen registrierten Listener."""
    if fn in _listeners:
        _listeners.remove(fn)
