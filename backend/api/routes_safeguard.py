"""
Ninko Safeguard API – Globaler und per-Agent Toggle.

Globale Routen:
    GET  /api/safeguard/status
    POST /api/safeguard/enable
    POST /api/safeguard/disable

Per-Agent Routen:
    GET  /api/safeguard/agents/{agent_id}
    POST /api/safeguard/agents/{agent_id}/enable
    POST /api/safeguard/agents/{agent_id}/disable
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from core.redis_client import get_redis

logger = logging.getLogger("ninko.api.safeguard")
router = APIRouter(prefix="/api/safeguard", tags=["Safeguard"])

REDIS_KEY_SAFEGUARD = "ninko:settings:safeguard"


def _get_safeguard(request: Request):
    sg = getattr(request.app.state, "safeguard", None)
    if sg is None:
        raise HTTPException(status_code=503, detail="Safeguard nicht initialisiert.")
    return sg


# ─── Global Toggle ─────────────────────────────────────────────────────────────

@router.get("/status")
async def safeguard_status(request: Request) -> dict:
    """Globalen Safeguard-Status abrufen."""
    sg = _get_safeguard(request)
    return {"enabled": sg.enabled}


@router.post("/enable")
async def safeguard_enable(request: Request) -> dict:
    """Safeguard global aktivieren."""
    sg = _get_safeguard(request)
    sg.enable()
    redis = get_redis()
    await redis.connection.set(REDIS_KEY_SAFEGUARD, "true")
    logger.info("[Safeguard] Global via API aktiviert.")
    return {"safeguard": "enabled"}


@router.post("/disable")
async def safeguard_disable(request: Request) -> dict:
    """Safeguard global deaktivieren (autonomer Modus)."""
    sg = _get_safeguard(request)
    sg.disable()
    redis = get_redis()
    await redis.connection.set(REDIS_KEY_SAFEGUARD, "false")
    logger.warning("[Safeguard] Global via API DEAKTIVIERT.")
    return {"safeguard": "disabled"}


# ─── Per-Agent Toggle ──────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}")
async def agent_safeguard_status(agent_id: str, request: Request) -> dict:
    """Per-Agent Safeguard-Status abrufen."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    state = await sg.agent_store.get_safeguard(agent_id)
    return {
        "agent_id": agent_id,
        # None → globaler Toggle gilt, True/False → explizit gesetzt
        "safeguard_enabled": state if state is not None else sg.enabled,
        "source": "agent" if state is not None else "global",
    }


@router.post("/agents/{agent_id}/enable")
async def agent_safeguard_enable(agent_id: str, request: Request) -> dict:
    """Safeguard für einen spezifischen Agent aktivieren."""
    sg = _get_safeguard(request)
    await sg.enable_for_agent(agent_id)
    return {"agent_id": agent_id, "safeguard": "enabled"}


@router.post("/agents/{agent_id}/disable")
async def agent_safeguard_disable(agent_id: str, request: Request) -> dict:
    """Safeguard für einen spezifischen Agent deaktivieren (autonomer Modus)."""
    sg = _get_safeguard(request)
    await sg.disable_for_agent(agent_id)
    return {"agent_id": agent_id, "safeguard": "disabled"}
