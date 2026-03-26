"""
Ninko Chat Schemas – Pydantic-Modelle für Chat-API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Einzelne Chat-Nachricht."""

    role: Literal["user", "assistant", "system", "system_compaction"] = "user"
    content: str
    timestamp: datetime | None = None


class ChatRequest(BaseModel):
    """Eingehende Chat-Anfrage."""

    message: str = Field(..., min_length=1, max_length=10000)
    session_id: str = Field(default="default")
    language: str = Field(default="de")
    confirmed: bool = Field(
        default=False,
        description="Explizite Bestätigung für destruktive/state-ändernde Aktionen (Safeguard)",
    )


class ChatResponse(BaseModel):
    """Antwort auf eine Chat-Anfrage."""

    response: str
    module_used: str | None = None
    session_id: str
    context_budget: dict | None = None
    compacted: bool = False
    timestamp: datetime = Field(default_factory=datetime.now)
    confirmation_required: bool = False
    safeguard: dict | None = None


class ChatHistoryResponse(BaseModel):
    """Chat-Verlauf einer Session."""

    session_id: str
    messages: list[ChatMessage]
    total: int
