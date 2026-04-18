"""Message Hub — FastAPI Routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from .schemas import RouteCreate, RouteUpdate

router = APIRouter()


@router.get("/status")
async def get_hub_status() -> dict[str, Any]:
    """Gibt den Status aller Worker und Routing-Statistiken zurück."""
    from .hub import get_message_hub
    from .db import list_routes

    hub = get_message_hub()
    routes = await list_routes()
    active_count = sum(1 for r in routes if r.enabled)

    worker_data: list[dict] = []
    if hub:
        status = hub.get_status()
        worker_data = [w.model_dump() for w in status.workers]

    return {
        "hub_active": hub is not None,
        "workers": worker_data,
        "route_count": len(routes),
        "active_route_count": active_count,
    }


_VALID_CHANNEL_TYPES = {"telegram", "discord", "email"}


@router.get("/routes")
async def list_routes_api(channel_type: str = "") -> list[dict]:
    """Listet alle Routing-Einträge."""
    from .db import list_routes

    if channel_type and channel_type not in _VALID_CHANNEL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Ungültiger channel_type. Erlaubt: {', '.join(sorted(_VALID_CHANNEL_TYPES))}",
        )
    routes = await list_routes(channel_type or None)
    return [r.model_dump() for r in routes]


@router.post("/routes", status_code=201)
async def create_route_api(body: RouteCreate) -> dict:
    """Erstellt einen neuen Routing-Eintrag."""
    from .db import create_route

    try:
        entry = await create_route(body)
        return entry.model_dump()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/routes/{route_id}")
async def get_route_api(route_id: str) -> dict:
    """Gibt einen Routing-Eintrag zurück."""
    from .db import get_route

    entry = await get_route(route_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' nicht gefunden")
    return entry.model_dump()


@router.patch("/routes/{route_id}")
async def update_route_api(route_id: str, body: RouteUpdate) -> dict:
    """Aktualisiert einen Routing-Eintrag."""
    from .db import update_route

    entry = await update_route(route_id, body)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' nicht gefunden")
    return entry.model_dump()


@router.delete("/routes/{route_id}", status_code=204, response_model=None)
async def delete_route_api(route_id: str) -> None:
    """Löscht einen Routing-Eintrag."""
    from .db import delete_route

    deleted = await delete_route(route_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Route '{route_id}' nicht gefunden")


@router.post("/workers/restart")
async def restart_workers() -> dict[str, Any]:
    """Stoppt und startet alle Worker neu (z.B. nach Konfigurationsänderung)."""
    from fastapi import Request
    from .hub import get_message_hub

    hub = get_message_hub()
    if not hub:
        raise HTTPException(status_code=503, detail="Message Hub nicht aktiv")

    await hub.stop()
    await hub.start()
    return {"ok": True, "workers": hub.worker_count}
