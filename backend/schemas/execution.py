"""Typed contracts for agent execution boundaries."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator


class AgentRequest(BaseModel):
    """Provider-neutral input for one non-streaming agent run."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)
    chat_history: list[dict[str, Any]] = Field(default_factory=list)
    session_id: str = ""
    confirmed: bool = False
    target: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def message_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message darf nicht leer sein")
        return value

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class AgentFinishReason(str, Enum):
    """Why an agent run stopped."""

    COMPLETED = "completed"
    APPROVAL_REQUIRED = "approval_required"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentResponse(BaseModel):
    """Provider-neutral result of one agent run."""

    model_config = ConfigDict(extra="forbid")

    text: str
    agent_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    module: str | None = None
    did_compact: bool = False
    compaction_summary: str | None = None
    routing_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tier_used: int | None = Field(default=None, ge=0)
    finish_reason: AgentFinishReason = AgentFinishReason.COMPLETED
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class AgentEventType(str, Enum):
    """Stable event discriminator for streaming and durable execution."""

    STARTED = "started"
    STATUS = "status"
    TOKEN = "token"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentEvent(BaseModel):
    """Serializable event emitted by an agent execution boundary.

    ``run_id`` identifies the current job, pipeline, step, or tool execution;
    ``parent_run_id`` links nested executions to their logical parent.
    ``tenant_id`` is the normalized tenant scope derived from the session.
    The meaning of ``data`` depends on ``type`` and producers must keep it
    JSON-compatible and free of secrets. The frozen model prevents field
    reassignment, while the event bus provides deep-copy isolation for the
    nested ``data`` mapping during fan-out.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        max_length=128,
    )
    type: AgentEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tenant_id: str = Field(max_length=128)
    session_id: str = Field(max_length=512)
    run_id: str = Field(max_length=256)
    parent_run_id: str | None = Field(default=None, max_length=256)
    agent_id: str = Field(max_length=128)
    data: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator(
        "event_id",
        "tenant_id",
        "session_id",
        "run_id",
        "agent_id",
    )
    @classmethod
    def identifiers_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("event identifiers dürfen nicht leer sein")
        return normalized
