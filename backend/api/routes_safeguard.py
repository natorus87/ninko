"""
Ninko Safeguard API – Globaler Toggle, per-Agent und per-Chat Profil-Zuordnung.

Globale Routen:
    GET  /api/safeguard/status
    POST /api/safeguard/enable           (backward-compat → "moderate" Profil)
    POST /api/safeguard/disable          (backward-compat → "disabled" Profil)

Profil-Zuweisung:
    GET  /api/safeguard/active
    POST /api/safeguard/active           body: {"profile_id": "strict"}

Per-Chat Profil (Session-Scope):
    GET    /api/safeguard/chats/{session_id}/profile
    POST   /api/safeguard/chats/{session_id}/profile   body: {"profile_id": "..."}
    DELETE /api/safeguard/chats/{session_id}/profile

Per-Agent Profil:
    GET    /api/safeguard/agents/{agent_id}/profile
    POST   /api/safeguard/agents/{agent_id}/profile    body: {"profile_id": "..."}
    DELETE /api/safeguard/agents/{agent_id}/profile

Per-Agent Custom Classifier Policy:
    GET    /api/safeguard/agents/{agent_id}/policy
    POST   /api/safeguard/agents/{agent_id}/policy     body: {"policy": "..."}
    DELETE /api/safeguard/agents/{agent_id}/policy

Ältere Per-Agent Toggle-Routen (backward-compat):
    GET  /api/safeguard/agents/{agent_id}
    POST /api/safeguard/agents/{agent_id}/enable
    POST /api/safeguard/agents/{agent_id}/disable
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.redis_client import get_redis
from core.safeguard import ActionCategory

logger = logging.getLogger("ninko.api.safeguard")
router = APIRouter(prefix="/api/safeguard", tags=["Safeguard"])

REDIS_KEY_SAFEGUARD = "ninko:settings:safeguard"


class ProfileAssignRequest(BaseModel):
    profile_id: str


class ClassifierPolicyRequest(BaseModel):
    policy: str


def _get_safeguard(request: Request):
    sg = getattr(request.app.state, "safeguard", None)
    if sg is None:
        raise HTTPException(status_code=503, detail="Safeguard nicht initialisiert.")
    return sg


def _get_profile_store(request: Request):
    sg = _get_safeguard(request)
    if sg.profile_store is None:
        raise HTTPException(status_code=503, detail="SafeguardProfileStore nicht verfügbar.")
    return sg.profile_store


async def _audit_admin_change(
    request: Request,
    text: str,
    *,
    outcome: str = "admin_change",
    rationale: str = "",
) -> None:
    """Audit-Log für privilegierte Safeguard-Änderungen."""
    try:
        sg = _get_safeguard(request)
        await sg._audit_log(
            action="admin_change",
            category=ActionCategory.STATE_CHANGING,
            text=text,
            session_id="api",
            agent_id="safeguard_admin",
            tool_name="api:safeguard",
            outcome=outcome,
            rationale=rationale[:300],
            profile_id=sg.get_active_profile_id(),
        )
    except Exception:
        pass


# ─── Global Status / Toggle (backward-compat) ─────────────────────────────────

@router.get("/status")
async def safeguard_status(request: Request) -> dict:
    """Globalen Safeguard-Status und aktives Profil abrufen."""
    sg = _get_safeguard(request)
    return {
        "enabled": sg.enabled,
        "profile_id": sg.get_active_profile_id(),
    }


@router.post("/enable")
async def safeguard_enable(request: Request) -> dict:
    """Safeguard global aktivieren (setzt Profil auf 'moderate')."""
    sg = _get_safeguard(request)
    sg.enable()
    redis = get_redis()
    await redis.connection.set(REDIS_KEY_SAFEGUARD, sg.get_active_profile_id())
    await _audit_admin_change(
        request,
        "Global safeguard enabled",
        rationale=f"profile={sg.get_active_profile_id()}",
    )
    logger.info("[Safeguard] Global via API aktiviert (Profil: %s).", sg.get_active_profile_id())
    return {"safeguard": "enabled", "profile_id": sg.get_active_profile_id()}


@router.post("/disable")
async def safeguard_disable(request: Request) -> dict:
    """Safeguard global deaktivieren (setzt Profil auf 'disabled')."""
    sg = _get_safeguard(request)
    sg.disable()
    redis = get_redis()
    await redis.connection.set(REDIS_KEY_SAFEGUARD, "disabled")
    await _audit_admin_change(
        request,
        "Global safeguard disabled",
        rationale="profile=disabled",
    )
    logger.warning("[Safeguard] Global via API DEAKTIVIERT.")
    return {"safeguard": "disabled", "profile_id": "disabled"}


# ─── Aktives globales Profil ──────────────────────────────────────────────────

@router.get("/active")
async def get_active_profile(request: Request) -> dict:
    """Aktives globales Profil abrufen."""
    sg = _get_safeguard(request)
    profile_store = _get_profile_store(request)
    profile = await profile_store.get_profile(sg.get_active_profile_id())
    return {
        "profile_id": sg.get_active_profile_id(),
        "profile": profile.to_dict() if profile else None,
    }


@router.post("/active")
async def set_active_profile(body: ProfileAssignRequest, request: Request) -> dict:
    """Globales aktives Profil setzen."""
    sg = _get_safeguard(request)
    try:
        await sg.set_active_profile(body.profile_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await _audit_admin_change(
        request,
        "Global safeguard profile changed",
        rationale=f"profile={body.profile_id}",
    )
    return {"profile_id": body.profile_id}


# ─── Per-Chat Profil ──────────────────────────────────────────────────────────

@router.get("/chats/{session_id}/profile")
async def get_chat_profile(session_id: str, request: Request) -> dict:
    """Aktives Profil für eine Chat-Session abrufen."""
    sg = _get_safeguard(request)
    profile_store = _get_profile_store(request)
    pid = await profile_store.get_chat_profile(session_id)
    if pid is None:
        return {
            "session_id": session_id,
            "profile_id": sg.get_active_profile_id(),
            "source": "global",
        }
    return {"session_id": session_id, "profile_id": pid, "source": "chat"}


@router.post("/chats/{session_id}/profile")
async def set_chat_profile(
    session_id: str,
    body: ProfileAssignRequest,
    request: Request,
) -> dict:
    """Profil für eine Chat-Session setzen (TTL 24h)."""
    profile_store = _get_profile_store(request)
    # Validate profile exists
    profile = await profile_store.get_profile(body.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profil '{body.profile_id}' nicht gefunden.")
    await profile_store.set_chat_profile(session_id, body.profile_id)
    await _audit_admin_change(
        request,
        "Chat safeguard profile changed",
        rationale=f"session={session_id},profile={body.profile_id}",
    )
    return {"session_id": session_id, "profile_id": body.profile_id}


@router.delete("/chats/{session_id}/profile")
async def clear_chat_profile(session_id: str, request: Request) -> dict:
    """Chat-spezifisches Profil entfernen (Fallback auf globales Profil)."""
    profile_store = _get_profile_store(request)
    await profile_store.clear_chat_profile(session_id)
    await _audit_admin_change(
        request,
        "Chat safeguard profile cleared",
        rationale=f"session={session_id}",
    )
    return {"session_id": session_id, "cleared": True}


# ─── Per-Agent Profil ─────────────────────────────────────────────────────────

@router.get("/agents/{agent_id}/profile")
async def get_agent_profile(agent_id: str, request: Request) -> dict:
    """Aktives Profil für einen Agent abrufen."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    pid = await sg.agent_store.get_profile(agent_id)
    return {
        "agent_id": agent_id,
        "profile_id": pid if pid else sg.get_active_profile_id(),
        "source": "agent" if pid else "global",
    }


@router.post("/agents/{agent_id}/profile")
async def set_agent_profile(
    agent_id: str,
    body: ProfileAssignRequest,
    request: Request,
) -> dict:
    """Profil für einen Agent setzen."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    # Validate profile exists
    profile = await sg._get_profile(body.profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profil '{body.profile_id}' nicht gefunden.")
    await sg.agent_store.set_profile(agent_id, body.profile_id)
    await _audit_admin_change(
        request,
        "Agent safeguard profile changed",
        rationale=f"agent={agent_id},profile={body.profile_id}",
    )
    return {"agent_id": agent_id, "profile_id": body.profile_id}


@router.delete("/agents/{agent_id}/profile")
async def clear_agent_profile(agent_id: str, request: Request) -> dict:
    """Per-Agent Profil entfernen (Fallback auf globales Profil)."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    await sg.agent_store.clear_profile(agent_id)
    await _audit_admin_change(
        request,
        "Agent safeguard profile cleared",
        rationale=f"agent={agent_id}",
    )
    return {"agent_id": agent_id, "cleared": True}


# ─── Per-Agent Toggle (backward-compat) ──────────────────────────────────────

@router.get("/agents/{agent_id}")
async def agent_safeguard_status(agent_id: str, request: Request) -> dict:
    """Per-Agent Safeguard-Status abrufen (backward-compat)."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    state = await sg.agent_store.get_safeguard(agent_id)
    pid = await sg.agent_store.get_profile(agent_id)
    return {
        "agent_id": agent_id,
        "safeguard_enabled": state if state is not None else sg.enabled,
        "profile_id": pid if pid else sg.get_active_profile_id(),
        "source": "agent" if (state is not None or pid) else "global",
    }


@router.post("/agents/{agent_id}/enable")
async def agent_safeguard_enable(agent_id: str, request: Request) -> dict:
    """Safeguard für einen Agent aktivieren (backward-compat)."""
    sg = _get_safeguard(request)
    await sg.enable_for_agent(agent_id)
    await _audit_admin_change(
        request,
        "Agent safeguard enabled",
        rationale=f"agent={agent_id}",
    )
    return {"agent_id": agent_id, "safeguard": "enabled"}


@router.post("/agents/{agent_id}/disable")
async def agent_safeguard_disable(agent_id: str, request: Request) -> dict:
    """Safeguard für einen Agent deaktivieren (backward-compat)."""
    sg = _get_safeguard(request)
    await sg.disable_for_agent(agent_id)
    await _audit_admin_change(
        request,
        "Agent safeguard disabled",
        rationale=f"agent={agent_id}",
    )
    return {"agent_id": agent_id, "safeguard": "disabled"}


# ─── Per-Agent Classifier Policy ──────────────────────────────────────────────

@router.get("/agents/{agent_id}/policy")
async def get_agent_classifier_policy(agent_id: str, request: Request) -> dict:
    """Custom safeguard classifier policy für einen Agent abrufen."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    policy = await sg.agent_store.get_classifier_policy(agent_id)
    return {
        "agent_id": agent_id,
        "policy": policy or "",
        "has_custom_policy": policy is not None,
    }


@router.post("/agents/{agent_id}/policy")
async def set_agent_classifier_policy(
    agent_id: str,
    body: ClassifierPolicyRequest,
    request: Request,
) -> dict:
    """Custom safeguard classifier policy für einen Agent setzen."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    if not body.policy.strip():
        raise HTTPException(status_code=400, detail="Policy text must not be empty.")
    await sg.agent_store.set_classifier_policy(agent_id, body.policy)
    await _audit_admin_change(
        request,
        "Agent safeguard policy set",
        rationale=f"agent={agent_id},policy_len={len(body.policy)}",
    )
    return {"agent_id": agent_id, "policy_set": True}


@router.delete("/agents/{agent_id}/policy")
async def clear_agent_classifier_policy(agent_id: str, request: Request) -> dict:
    """Custom safeguard classifier policy für einen Agent entfernen."""
    sg = _get_safeguard(request)
    if sg.agent_store is None:
        raise HTTPException(status_code=503, detail="AgentConfigStore nicht verfügbar.")
    await sg.agent_store.clear_classifier_policy(agent_id)
    await _audit_admin_change(
        request,
        "Agent safeguard policy cleared",
        rationale=f"agent={agent_id}",
    )
    return {"agent_id": agent_id, "policy_cleared": True}
