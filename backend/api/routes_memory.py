"""
Ninko Memory API – CRUD für Semantic Memory.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from schemas.memory import (
    MemoryStoreRequest,
    MemoryStoreResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryEntry,
    MemoryStatsResponse,
)
from core.memory import get_memory
from core.auth import auth_tenant_id, resolve_request_auth

logger = logging.getLogger("ninko.api.memory")
router = APIRouter(prefix="/api/memory", tags=["Memory"])


def _tenant_category(tenant_id: str, category: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    c = (category or "general").strip()
    return f"tenant::{t}::{c}"


def _extract_public_category(scoped_category: str) -> str:
    raw = (scoped_category or "").strip()
    if raw.startswith("tenant::") and "::" in raw:
        return raw.split("::", 2)[-1]
    return raw


@router.post("/store", response_model=MemoryStoreResponse)
async def store_memory(body: MemoryStoreRequest, request: Request) -> MemoryStoreResponse:
    """Speichert einen neuen Eintrag im Semantic Memory."""
    memory = get_memory()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scoped_category = _tenant_category(tenant_id, body.category)
    meta = dict(body.metadata or {})
    meta["tenant_id"] = tenant_id
    meta["category_public"] = body.category
    doc_id = await memory.store(
        content=body.content,
        category=scoped_category,
        metadata=meta,
    )
    return MemoryStoreResponse(id=doc_id, category=body.category)


@router.post("/search", response_model=MemorySearchResponse)
async def search_memory(body: MemorySearchRequest, request: Request) -> MemorySearchResponse:
    """Semantische Suche im Memory."""
    memory = get_memory()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scoped_category = _tenant_category(tenant_id, body.category) if body.category else None
    results = await memory.search(
        query=body.query,
        top_k=body.top_k,
        category=scoped_category,
    )
    for item in results:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if metadata:
            metadata["category_public"] = _extract_public_category(str(metadata.get("category", "")))
            item["metadata"] = metadata
    return MemorySearchResponse(
        query=body.query,
        results=[MemoryEntry(**r) for r in results],
        total=len(results),
    )


@router.get("/incidents", response_model=MemorySearchResponse)
async def get_incidents(
    request: Request,
    query: str = "Letzte Incidents",
    top_k: int = 10,
) -> MemorySearchResponse:
    """Gibt die letzten Incidents aus dem Memory zurück."""
    memory = get_memory()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    results = await memory.search(
        query=query,
        top_k=top_k,
        category=_tenant_category(tenant_id, "incident"),
    )
    for item in results:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        if metadata:
            metadata["category_public"] = _extract_public_category(str(metadata.get("category", "")))
            item["metadata"] = metadata
    return MemorySearchResponse(
        query=query,
        results=[MemoryEntry(**r) for r in results],
        total=len(results),
    )


@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(request: Request) -> MemoryStatsResponse:
    """Statistiken des Semantic Memory."""
    _ = auth_tenant_id(resolve_request_auth(request))
    memory = get_memory()
    stats = memory.get_stats()
    return MemoryStatsResponse(**stats)
