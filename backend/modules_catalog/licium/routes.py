"""
Licium module — FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import (
    search_licium,
    list_licium_tree,
    get_licium_wiki_meta,
    setup_licium_wiki,
    lint_licium_wiki,
    append_licium_log,
    _licium_session,
    _get_wiki_meta_raw,
)

logger = logging.getLogger("ninko.modules.licium.routes")
router = APIRouter()


@router.get("/status")
async def get_status(connection_id: str = "") -> dict:
    """Verbindungsstatus und Wiki-Statistiken."""
    try:
        async with _licium_session(connection_id) as (client, _):
            meta = await _get_wiki_meta_raw(client)

            info_resp = await client.get("/api/system/info")
            system_info = info_resp.json() if info_resp.status_code == 200 else {}

            tree_resp = await client.get("/api/tree")
            note_count = 0
            if tree_resp.status_code == 200:
                from .tools import _flatten_tree
                tree = tree_resp.json()
                nodes = tree if isinstance(tree, list) else tree.get("children", [])
                all_nodes = _flatten_tree(nodes)
                note_count = sum(1 for n in all_nodes if n.get("type") == "note")

            return {
                "status": "ok",
                "connected": True,
                "wiki_initialized": meta.get("initialized", False),
                "note_count": note_count,
                "licium_version": system_info.get("version", "?"),
                "meta": meta,
            }
    except (ValueError, RuntimeError, Exception) as exc:
        logger.warning("licium status check failed: %s", exc)
        return {"status": "error", "connected": False, "detail": str(exc)}


@router.get("/tree")
async def get_tree(connection_id: str = "") -> dict:
    """Gibt die Notiz-Baumstruktur zurück."""
    try:
        result = await list_licium_tree.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "tree": result}
    except (ValueError, RuntimeError, Exception) as exc:
        logger.error("licium tree route failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@router.post("/search")
async def search(body: dict) -> dict:
    """Semantische Suche in der Wissensdatenbank."""
    try:
        query = body.get("query", "")
        connection_id = body.get("connection_id", "")
        if not query:
            return {"status": "error", "detail": "query required"}
        result = await search_licium.ainvoke({"query": query, "connection_id": connection_id})
        return {"status": "ok", "results": result}
    except (ValueError, RuntimeError, Exception) as exc:
        logger.error("licium search route failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@router.post("/setup")
async def setup_wiki(connection_id: str = "") -> dict:
    """Initialisiert die Wiki-Ordnerstruktur (idempotent)."""
    try:
        result = await setup_licium_wiki.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "detail": result}
    except (ValueError, RuntimeError, Exception) as exc:
        logger.error("licium setup route failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@router.post("/lint")
async def lint_wiki(connection_id: str = "") -> dict:
    """Führt einen Wiki-Gesundheitscheck durch."""
    try:
        result = await lint_licium_wiki.ainvoke({"connection_id": connection_id})
        await append_licium_log.ainvoke({
            "operation": "lint",
            "title": "health-check",
            "connection_id": connection_id,
        })
        return {"status": "ok", "report": result}
    except (ValueError, RuntimeError, Exception) as exc:
        logger.error("licium lint route failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@router.get("/meta")
async def get_wiki_meta(connection_id: str = "") -> dict:
    """Gibt die Metadaten der Wiki-Struktur zurück."""
    try:
        result = await get_licium_wiki_meta.ainvoke({"connection_id": connection_id})
        return {"status": "ok", "meta": result}
    except (ValueError, RuntimeError, Exception) as exc:
        logger.error("licium meta route failed: %s", exc)
        return {"status": "error", "detail": str(exc)}


@router.get("/log")
async def get_log(connection_id: str = "") -> dict:
    """Gibt die letzten Log-Einträge zurück."""
    try:
        async with _licium_session(connection_id) as (client, _):
            meta = await _get_wiki_meta_raw(client)
            log_id = meta.get("log_note_id")
            if not log_id:
                return {"status": "ok", "entries": [], "detail": "Wiki not initialized"}

            resp = await client.get(f"/api/notes/{log_id}")
            resp.raise_for_status()
            content = resp.json().get("content_markdown", "") or ""

            lines = [l for l in content.split("\n") if l.startswith("## [")]
            return {"status": "ok", "entries": lines[-20:]}
    except (ValueError, RuntimeError, Exception) as exc:
        logger.error("licium log route failed: %s", exc)
        return {"status": "error", "detail": str(exc)}
