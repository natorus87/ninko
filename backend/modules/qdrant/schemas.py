"""
Qdrant Modul – Pydantic Schemas.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class KnowledgeEntry(BaseModel):
    """Einzelner Wissens-Eintrag in Qdrant."""

    id: str = ""
    title: str = ""
    content: str = ""
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    chunk_index: int = 0
    chunk_total: int = 1
    score: Optional[float] = None
    created_at: str = ""


class CollectionInfo(BaseModel):
    """Metadaten einer Qdrant-Collection."""

    name: str
    vectors_count: int = 0
    points_count: int = 0
    status: str = "unknown"
    vector_size: int = 0
    distance: str = "Cosine"


class SearchRequest(BaseModel):
    """API-Request für semantische Suche."""

    query: str
    collection: str = ""
    top_k: int = Field(default=5, ge=1, le=50)
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    score_threshold: float = Field(default=0.0, ge=0.0, le=1.0)


class AddEntryRequest(BaseModel):
    """API-Request zum Hinzufügen eines Wissens-Eintrags."""

    content: str = Field(..., min_length=1)
    title: str = ""
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    source: str = ""
    collection: str = ""


class BatchAddRequest(BaseModel):
    """API-Request für Batch-Import mehrerer Einträge."""

    entries: list[AddEntryRequest]
    collection: str = ""


class CreateCollectionRequest(BaseModel):
    """API-Request zum Erstellen einer neuen Collection."""

    name: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_\-]+$")
    description: str = ""


class DeleteEntryRequest(BaseModel):
    """API-Request zum Löschen nach Filter."""

    collection: str = ""
    category: Optional[str] = None
    source: Optional[str] = None
