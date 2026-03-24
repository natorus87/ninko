"""
Kumio Memory Schemas – Pydantic-Modelle für Semantic Memory API.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """Ein Eintrag im Semantic Memory."""

    id: str
    content: str
    metadata: dict = {}
    distance: float | None = None


class MemoryStoreRequest(BaseModel):
    """Anfrage zum Speichern im Memory."""

    content: str = Field(..., min_length=1)
    category: str = Field(default="general")
    metadata: dict = Field(default_factory=dict)


class MemoryStoreResponse(BaseModel):
    """Antwort nach Memory-Speicherung."""

    id: str
    category: str
    stored_at: datetime = Field(default_factory=datetime.now)


class MemorySearchRequest(BaseModel):
    """Suchanfrage im Memory."""

    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    category: str | None = None


class MemorySearchResponse(BaseModel):
    """Suchergebnis aus dem Memory."""

    query: str
    results: list[MemoryEntry]
    total: int


class MemoryStatsResponse(BaseModel):
    """Statistiken des Semantic Memory."""

    collection: str
    document_count: int
