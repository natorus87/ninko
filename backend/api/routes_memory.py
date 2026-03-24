"""
Kumio Memory API – CRUD für Semantic Memory.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from schemas.memory import (
    MemoryStoreRequest,
    MemoryStoreResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryEntry,
    MemoryStatsResponse,
)
from core.memory import get_memory

logger = logging.getLogger("kumio.api.memory")
router = APIRouter(prefix="/api/memory", tags=["Memory"])


@router.post("/store", response_model=MemoryStoreResponse)
async def store_memory(body: MemoryStoreRequest) -> MemoryStoreResponse:
    """Speichert einen neuen Eintrag im Semantic Memory."""
    memory = get_memory()
    doc_id = await memory.store(
        content=body.content,
        category=body.category,
        metadata=body.metadata,
    )
    return MemoryStoreResponse(id=doc_id, category=body.category)


@router.post("/search", response_model=MemorySearchResponse)
async def search_memory(body: MemorySearchRequest) -> MemorySearchResponse:
    """Semantische Suche im Memory."""
    memory = get_memory()
    results = await memory.search(
        query=body.query,
        top_k=body.top_k,
        category=body.category,
    )
    return MemorySearchResponse(
        query=body.query,
        results=[MemoryEntry(**r) for r in results],
        total=len(results),
    )


@router.get("/incidents", response_model=MemorySearchResponse)
async def get_incidents(
    query: str = "Letzte Incidents",
    top_k: int = 10,
) -> MemorySearchResponse:
    """Gibt die letzten Incidents aus dem Memory zurück."""
    memory = get_memory()
    results = await memory.get_recent_incidents(query=query, top_k=top_k)
    return MemorySearchResponse(
        query=query,
        results=[MemoryEntry(**r) for r in results],
        total=len(results),
    )


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats() -> MemoryStatsResponse:
    """Statistiken des Semantic Memory."""
    memory = get_memory()
    stats = memory.get_stats()
    return MemoryStatsResponse(**stats)
