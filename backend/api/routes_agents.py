"""
Kumio Agents API – CRUD für Agenten-Definitionen.
Persistenz via Redis (kumio:agents).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from core.redis_client import get_redis
from schemas.agents import AgentDefinition, AgentCreate, AgentListResponse

logger = logging.getLogger("kumio.api.agents")
router = APIRouter(prefix="/api/agents", tags=["Agents"])

REDIS_KEY = "kumio:agents"


async def _load_agents(redis) -> list[dict]:
    raw = await redis.connection.get(REDIS_KEY)
    return json.loads(raw) if raw else []


async def _save_agents(redis, agents: list[dict]) -> None:
    await redis.connection.set(REDIS_KEY, json.dumps(agents))


@router.get("/", response_model=AgentListResponse)
async def list_agents() -> AgentListResponse:
    """Alle konfigurierten Agenten auflisten."""
    redis = get_redis()
    agents = await _load_agents(redis)
    return AgentListResponse(agents=[AgentDefinition(**a) for a in agents], total=len(agents))


@router.post("/", status_code=201)
async def create_agent(body: AgentCreate) -> dict:
    """Neuen Agenten erstellen."""
    redis = get_redis()
    agents = await _load_agents(redis)

    now = datetime.now(timezone.utc).isoformat()
    new_agent = AgentDefinition(
        **body.model_dump(),
        created_at=now,
        updated_at=now,
    )

    agents.append(new_agent.model_dump())
    await _save_agents(redis, agents)
    logger.info("Agent erstellt: %s (%s)", new_agent.name, new_agent.id)
    return {"id": new_agent.id, "status": "created"}


@router.get("/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    """Einen Agenten abrufen (inkl. Soul MD wenn vorhanden)."""
    redis = get_redis()
    agents = await _load_agents(redis)
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nicht gefunden")

    # Soul MD anhängen (wenn vorhanden)
    try:
        from core.soul_manager import get_soul_manager
        soul = get_soul_manager().get_soul(agent.get("name", ""))
        if soul:
            agent["soul_md"] = soul
    except Exception:
        pass

    return agent


@router.put("/{agent_id}")
async def update_agent(agent_id: str, body: AgentCreate) -> dict:
    """Agenten bearbeiten."""
    redis = get_redis()
    agents = await _load_agents(redis)

    idx = next((i for i, a in enumerate(agents) if a["id"] == agent_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nicht gefunden")

    now = datetime.now(timezone.utc).isoformat()
    updated = {
        **agents[idx],
        **body.model_dump(),
        "id": agent_id,
        "updated_at": now,
    }
    agents[idx] = updated
    await _save_agents(redis, agents)
    logger.info("Agent aktualisiert: %s", agent_id)
    return {"id": agent_id, "status": "updated"}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str) -> dict:
    """Agenten löschen (inkl. Soul MD Cleanup)."""
    redis = get_redis()
    agents = await _load_agents(redis)
    deleted_agent = next((a for a in agents if a["id"] == agent_id), None)
    if not deleted_agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nicht gefunden")

    agents = [a for a in agents if a["id"] != agent_id]
    await _save_agents(redis, agents)

    # Soul MD des gelöschten Agenten aufräumen
    try:
        from core.soul_manager import get_soul_manager
        agent_name = deleted_agent.get("name", "")
        if agent_name:
            await get_soul_manager().delete_soul(agent_name)
    except Exception as exc:
        logger.warning("Soul-Cleanup für Agent '%s' fehlgeschlagen: %s", agent_id, exc)

    logger.info("Agent gelöscht: %s", agent_id)
    return {"id": agent_id, "deleted": True}


@router.post("/{agent_id}/duplicate", status_code=201)
async def duplicate_agent(agent_id: str) -> dict:
    """Agenten duplizieren."""
    redis = get_redis()
    agents = await _load_agents(redis)
    original = next((a for a in agents if a["id"] == agent_id), None)
    if not original:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nicht gefunden")

    now = datetime.now(timezone.utc).isoformat()
    duplicate = {
        **original,
        "id": str(uuid.uuid4()),
        "name": f"{original['name']} (Kopie)",
        "created_at": now,
        "updated_at": now,
    }
    agents.append(duplicate)
    await _save_agents(redis, agents)
    logger.info("Agent dupliziert: %s → %s", agent_id, duplicate["id"])
    return {"id": duplicate["id"], "status": "created"}
