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
    force_module: str | None = Field(
        default=None,
        description="Wenn gesetzt, wird die Nachricht direkt an dieses Modul geroutet (bypasses 4-Tier-Analyse).",
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
    routing_confidence: float | None = Field(
        default=None,
        description="Routing-Konfidenz [0.0, 1.0]. None = ReAct-Loop. < 0.7 = unsicheres Keyword-Routing.",
    )


class ChatHistoryResponse(BaseModel):
    """Chat-Verlauf einer Session."""

    session_id: str
    messages: list[ChatMessage]
    total: int


class ChatStreamChunk(BaseModel):
    """Ein SSE-Chunk im Chat-Stream-Format (siehe ``_stream_frame``)."""

    type: str
    request_id: str
    message_id: str


class ChatCancelResponse(BaseModel):
    """Antwort auf den Cancel-Endpoint (Abbruch einer laufenden Verarbeitung)."""

    status: str
    session_id: str
    message: str = ""


class ChatConfirmResponse(BaseModel):
    """Antwort auf den Confirm-Endpoint (Bestätigung einer ausstehenden Aktion)."""

    status: str
    session_id: str
    message: str = ""


class SessionListResponse(BaseModel):
    """Liste der persistenten UI-Konversationen (``/api/chat/ui-history``)."""

    conversations: list[dict] = Field(default_factory=list)


class SessionMessagesResponse(BaseModel):
    """Persistenter Konversationseintrag (``/api/chat/ui-history``)."""

    status: str
    session_id: str = ""
    count: int = 0
    message: str = ""


# ── History replace (PLAN.md 2.4, M1 Security) ────────────────────


class HistoryMessage(BaseModel):
    """Eine einzelne Nachricht in der Chat-History (PUT /api/chat/history)."""

    model_config = {"extra": "forbid"}

    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=32_768)


class HistoryUpdateRequest(BaseModel):
    """Body für PUT /api/chat/history/{session_id}."""

    model_config = {"extra": "forbid"}

    messages: list[HistoryMessage] = Field(..., max_length=500)


# ── UI History (PLAN.md 2.4, M2 Security) ─────────────────────────


class UiHistoryEntry(BaseModel):
    """Persistenter UI-History-Eintrag (POST /api/chat/ui-history).

    Felder mit ``Optional[...]`` sind optional, weil das Frontend je nach
    Conversation-Typ unterschiedliche Felder sendet. ``extra="forbid"``
    fängt Schema-Drift früh ab (z. B. wenn das Frontend neue Felder einführt
    ohne Server-Migration).
    """

    model_config = {"extra": "forbid"}

    id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(default="", max_length=512)
    messages: list[HistoryMessage] = Field(default_factory=list)
    createdAt: float = 0.0
    updatedAt: float = 0.0
