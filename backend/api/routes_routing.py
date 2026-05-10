"""
Ninko Routing-Admin-API (R12) – Korrektur-Statistiken und Reset.

Endpunkte:
  GET  /api/routing/corrections  → Statistiken (Admin)
  DELETE /api/routing/corrections → Reset (Admin)
"""

from __future__ import annotations

from fastapi import APIRouter, Request, HTTPException

from core.auth import ROLE_ADMIN, resolve_request_auth, role_allows
from core.routing_telemetry import get_routing_telemetry

router = APIRouter(prefix="/api/routing", tags=["Routing"])


def _require_admin(request: Request) -> None:
    auth = resolve_request_auth(request)
    role = str(auth.get("role", "")) if isinstance(auth, dict) else None
    if not role_allows(ROLE_ADMIN, role):
        raise HTTPException(status_code=403, detail="Admin-Zugriff erforderlich.")


@router.get("/corrections")
async def get_routing_corrections(request: Request) -> dict:
    """Gibt Routing-Korrektur-Statistiken zurück.

    Zeigt, welche Auto-Routing-Entscheidungen der User durch force_module
    korrigiert hat, und wie häufig.
    """
    _require_admin(request)
    telemetry = get_routing_telemetry()
    if telemetry is None:
        return {"total": 0, "by_pair": {}, "recent": []}
    return await telemetry.get_stats()


@router.delete("/corrections")
async def reset_routing_corrections(request: Request) -> dict:
    """Setzt Korrektur-Log und Statistiken zurück (Admin-Aktion)."""
    _require_admin(request)
    telemetry = get_routing_telemetry()
    if telemetry is None:
        return {"status": "noop"}
    await telemetry.reset_stats()
    return {"status": "reset"}
