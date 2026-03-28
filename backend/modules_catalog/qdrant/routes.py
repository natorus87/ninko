"""
Qdrant Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .schemas import (
    AddEntryRequest,
    BatchAddRequest,
    CreateCollectionRequest,
    DeleteEntryRequest,
    SearchRequest,
)
from .tools import (
    add_knowledge,
    delete_knowledge_by_id,
    get_collection_stats,
    list_knowledge_collections,
    search_knowledge,
)

logger = logging.getLogger("ninko.modules.qdrant.routes")
router = APIRouter()


def _error(msg: str, status: int = 502) -> JSONResponse:
    logger.warning("Qdrant API Fehler: %s", msg)
    return JSONResponse({"error": str(msg)}, status_code=status)


# ── Collections ────────────────────────────────────────────────────────────────

@router.get("/collections")
async def get_collections(connection_id: str = ""):
    """Alle Collections mit Statistiken."""
    try:
        return await list_knowledge_collections.ainvoke({"connection_id": connection_id})
    except Exception as e:
        return _error(str(e))


@router.get("/collections/{name}/stats")
async def collection_stats(name: str, connection_id: str = ""):
    """Statistiken einer einzelnen Collection."""
    try:
        return await get_collection_stats.ainvoke(
            {"collection": name, "connection_id": connection_id}
        )
    except Exception as e:
        return _error(str(e))


@router.post("/collections")
async def create_collection(req: CreateCollectionRequest, connection_id: str = ""):
    """Neue leere Collection erstellen."""
    try:
        from .tools import _get_qdrant_client, _ensure_collection

        client, _ = await _get_qdrant_client(connection_id)
        await _ensure_collection(client, req.name)
        return {"message": f"Collection '{req.name}' erstellt.", "name": req.name}
    except Exception as e:
        return _error(str(e))


# ── Suche ──────────────────────────────────────────────────────────────────────

@router.post("/search")
async def search(req: SearchRequest, connection_id: str = ""):
    """Semantische Suche in der Wissensbank."""
    try:
        results = await search_knowledge.ainvoke({
            "query": req.query,
            "collection": req.collection,
            "top_k": req.top_k,
            "category": req.category or "",
            "tags": ",".join(req.tags) if req.tags else "",
            "connection_id": connection_id,
        })
        # Score-Threshold clientseitig anwenden
        if req.score_threshold > 0:
            results = [r for r in results if r.get("score", 1.0) >= req.score_threshold]
        return results
    except Exception as e:
        return _error(str(e))


# ── Einträge verwalten ─────────────────────────────────────────────────────────

@router.post("/entries")
async def add_entry(req: AddEntryRequest, connection_id: str = ""):
    """Einzelnen Eintrag zur Wissensbank hinzufügen."""
    try:
        msg = await add_knowledge.ainvoke({
            "content": req.content,
            "title": req.title,
            "category": req.category,
            "tags": ",".join(req.tags),
            "source": req.source,
            "collection": req.collection,
            "connection_id": connection_id,
        })
        return {"message": msg}
    except Exception as e:
        return _error(str(e))


@router.post("/entries/batch")
async def batch_add_entries(req: BatchAddRequest, connection_id: str = ""):
    """Mehrere Einträge in einem Request hinzufügen."""
    results = []
    for entry in req.entries:
        try:
            collection = entry.collection or req.collection
            msg = await add_knowledge.ainvoke({
                "content": entry.content,
                "title": entry.title,
                "category": entry.category,
                "tags": ",".join(entry.tags),
                "source": entry.source,
                "collection": collection,
                "connection_id": connection_id,
            })
            results.append({"title": entry.title, "status": "ok", "message": msg})
        except Exception as e:
            results.append({"title": entry.title, "status": "error", "message": str(e)})

    ok = sum(1 for r in results if r["status"] == "ok")
    return {"imported": ok, "total": len(results), "results": results}


@router.delete("/entries/{point_id}")
async def delete_entry(point_id: str, collection: str = "", connection_id: str = ""):
    """Einzelnen Eintrag per ID löschen."""
    try:
        msg = await delete_knowledge_by_id.ainvoke({
            "point_id": point_id,
            "collection": collection,
            "connection_id": connection_id,
        })
        return {"message": msg}
    except Exception as e:
        return _error(str(e))


@router.post("/entries/delete-by-filter")
async def delete_by_filter(req: DeleteEntryRequest, connection_id: str = ""):
    """Mehrere Einträge per Payload-Filter löschen (Kategorie oder Quelle)."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from .tools import _get_qdrant_client

        if not req.category and not req.source:
            return _error("Mindestens category oder source muss angegeben werden.", 400)

        client, default_collection = await _get_qdrant_client(connection_id)
        target = req.collection or default_collection

        conditions = []
        if req.category:
            conditions.append(FieldCondition(key="category", match=MatchValue(value=req.category)))
        if req.source:
            conditions.append(FieldCondition(key="source", match=MatchValue(value=req.source)))

        await client.delete(
            collection_name=target,
            points_selector=Filter(must=conditions),
        )
        return {"message": f"Einträge mit Filter gelöscht aus '{target}'."}
    except Exception as e:
        return _error(str(e))


# ── Einträge durchblättern ─────────────────────────────────────────────────────

@router.get("/entries")
async def list_entries(
    collection: str = "",
    limit: int = 20,
    offset: int = 0,
    category: str = "",
    connection_id: str = "",
):
    """Einträge aus einer Collection auflisten (mit Pagination und optionalem Kategorie-Filter)."""
    try:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        from .tools import _get_qdrant_client

        client, default_collection = await _get_qdrant_client(connection_id)
        target = collection or default_collection
        limit = max(1, min(100, limit))

        scroll_filter = None
        if category:
            scroll_filter = Filter(
                must=[FieldCondition(key="category", match=MatchValue(value=category))]
            )

        points, next_offset = await client.scroll(
            collection_name=target,
            scroll_filter=scroll_filter,
            limit=limit,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )

        return {
            "collection": target,
            "entries": [
                {
                    "id": str(p.id),
                    "title": p.payload.get("title", ""),
                    "category": p.payload.get("category", ""),
                    "tags": p.payload.get("tags", []),
                    "source": p.payload.get("source", ""),
                    "created_at": p.payload.get("created_at", ""),
                    "chunk_index": p.payload.get("chunk_index", 0),
                    "chunk_total": p.payload.get("chunk_total", 1),
                    "content_preview": p.payload.get("content", "")[:200],
                }
                for p in points
            ],
            "next_offset": next_offset,
        }
    except Exception as e:
        return _error(str(e))
