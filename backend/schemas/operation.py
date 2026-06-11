"""
Ninko Operation Journal Schemas – API-Wrapper für das Transaction-Journal.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class OperationJournalEntry(BaseModel):
    """Ein einzelner Journal-Eintrag (aus Redis-Hash)."""

    id: str
    timestamp: Optional[Any] = None
    updated_at: Optional[Any] = None
    status: str = Field("", description="pending_confirmation | confirmed | executed | failed | rolled_back")
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    module: Optional[str] = None
    tool_name: Optional[str] = None
    text: Optional[str] = None
    rationale: Optional[str] = None
    rollback_required: Optional[str] = None
    rollback_hint: Optional[str] = None
    rollback_notes: Optional[str] = None
    result_summary: Optional[str] = None
    error: Optional[str] = None
    metadata: Optional[str] = None

    model_config = {"extra": "allow"}


class OperationListResponse(BaseModel):
    """Response: Liste von Journal-Einträgen."""

    entries: list[OperationJournalEntry]
    count: int


class OperationUpdateResponse(BaseModel):
    """Response: Erfolgreiche Update-Operation (Rollback-Note / Rollback-Complete)."""

    tx_id: str
    updated: Optional[bool] = None
    status: Optional[str] = None
