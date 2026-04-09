"""
Ninko Agents API – CRUD für Agenten-Definitionen.
Persistenz via Redis (ninko:agents).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import auth_tenant_id, resolve_request_auth
from core.redis_client import get_redis
from schemas.agents import AgentDefinition, AgentCreate, AgentListResponse

logger = logging.getLogger("ninko.api.agents")
router = APIRouter(prefix="/api/agents", tags=["Agents"])


class AgentGenerateRequest(BaseModel):
    use_case: str
    allowed_modules: list[str] = []


REDIS_KEY = "ninko:agents"


def _tenant_key(tenant_id: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    return f"{REDIS_KEY}:{t or 'default'}"


async def _load_agents(redis, tenant_id: str) -> list[dict]:
    raw = await redis.connection.get(_tenant_key(tenant_id))
    return json.loads(raw) if raw else []


async def _save_agents(redis, tenant_id: str, agents: list[dict]) -> None:
    await redis.connection.set(_tenant_key(tenant_id), json.dumps(agents))


def _public_agent(agent: dict) -> dict:
    a = dict(agent)
    a.pop("tenant_id", None)
    return a


@router.get("/", response_model=AgentListResponse)
async def list_agents(request: Request) -> AgentListResponse:
    """Alle konfigurierten Agenten auflisten."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)
    pub = [_public_agent(a) for a in agents]
    return AgentListResponse(agents=[AgentDefinition(**a) for a in pub], total=len(pub))


@router.post("/", status_code=201)
async def create_agent(body: AgentCreate, request: Request) -> dict:
    """Neuen Agenten erstellen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)

    now = datetime.now(timezone.utc).isoformat()
    new_agent = AgentDefinition(
        **body.model_dump(),
        created_at=now,
        updated_at=now,
    )
    agents.append({**new_agent.model_dump(), "tenant_id": tenant_id})
    await _save_agents(redis, tenant_id, agents)
    logger.info("Agent erstellt: %s (%s)", new_agent.name, new_agent.id)
    return {"id": new_agent.id, "status": "created"}


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request) -> dict:
    """Einen Agenten abrufen (inkl. Soul MD wenn vorhanden)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_id}' nicht gefunden"
        )

    # Soul MD anhängen (wenn vorhanden)
    try:
        from core.soul_manager import get_soul_manager

        soul = get_soul_manager().get_soul(agent.get("name", ""))
        if soul:
            agent["soul_md"] = soul
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ):
        pass

    return _public_agent(agent)


@router.put("/{agent_id}")
async def update_agent(agent_id: str, body: AgentCreate, request: Request) -> dict:
    """Agenten bearbeiten."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)

    idx = next((i for i, a in enumerate(agents) if a["id"] == agent_id), None)
    if idx is None:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_id}' nicht gefunden"
        )

    now = datetime.now(timezone.utc).isoformat()
    updated = {
        **agents[idx],
        **body.model_dump(),
        "id": agent_id,
        "updated_at": now,
        "tenant_id": tenant_id,
    }
    agents[idx] = updated
    await _save_agents(redis, tenant_id, agents)
    logger.info("Agent aktualisiert: %s", agent_id)
    return {"id": agent_id, "status": "updated"}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, request: Request) -> dict:
    """Agenten löschen (inkl. Soul MD Cleanup)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)
    deleted_agent = next((a for a in agents if a["id"] == agent_id), None)
    if not deleted_agent:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_id}' nicht gefunden"
        )

    agents = [a for a in agents if a["id"] != agent_id]
    await _save_agents(redis, tenant_id, agents)

    # Soul MD des gelöschten Agenten aufräumen
    try:
        from core.soul_manager import get_soul_manager

        agent_name = deleted_agent.get("name", "")
        if agent_name:
            await get_soul_manager().delete_soul(agent_name)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning("Soul-Cleanup für Agent '%s' fehlgeschlagen: %s", agent_id, exc)

    logger.info("Agent gelöscht: %s", agent_id)
    return {"id": agent_id, "deleted": True}


@router.get("/templates")
async def get_agent_templates() -> dict:
    """Built-in Agent-Vorlagen für den Agent Builder zurückgeben."""
    from core.agent_templates import AGENT_TEMPLATES

    return {"templates": AGENT_TEMPLATES}


@router.post("/generate")
async def generate_agent_spec(body: AgentGenerateRequest) -> dict:
    """
    Generiert eine Agent-Spezifikation (Name, System-Prompt, Beschreibung) aus einem Use-Case.
    Ruft das aktive LLM auf um einen hochwertigen, strukturierten System-Prompt zu erstellen.
    """
    use_case = body.use_case.strip()
    if not use_case:
        raise HTTPException(status_code=422, detail="use_case darf nicht leer sein")

    try:
        from core.llm_factory import get_llm_client
        from core.module_registry import get_registry
        from langchain_core.messages import HumanMessage

        # Verfügbare Module für Kontext
        try:
            registry = get_registry()
            all_modules = [
                f"{m.name} ({m.description[:60]})"
                for m in registry.list_manifests()
                if m.enabled_by_default
            ]
            module_context = (
                ", ".join(all_modules[:12])
                if all_modules
                else "kubernetes, linux_server, docker, pihole, homeassistant"
            )
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            ImportError,
            json.JSONDecodeError,
        ):
            module_context = "kubernetes, linux_server, docker, pihole, homeassistant, opnsense, glpi, telegram"

        allowed_hint = ""
        if body.allowed_modules:
            allowed_hint = f"\nBevorzugte Module: {', '.join(body.allowed_modules)}"

        prompt = f"""Du bist ein Agent-Builder-Experte für das Ninko IT-Operations-System.

Erstelle für den folgenden Use-Case eine vollständige, hochwertige Agent-Spezifikation.

USE-CASE: {use_case}{allowed_hint}

VERFÜGBARE MODULE: {module_context}

ANFORDERUNGEN AN DEN SYSTEM-PROMPT:
- Klar strukturiert mit ## Aufgaben, ## Arbeitsweise, ## Kritische Aktionen, ## Eskalation
- Spezifische, handlungsorientierte Bullet-Points
- Destruktive Aktionen explizit gegattet ("immer bestätigen lassen")
- Eskalationsregel: "Aufgabe außerhalb Scope → an Ninko zurückgeben"
- Module via call_module_agent("<modul>", "...") erwähnen wenn relevant
- Kompakt: 200–400 Zeichen

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt ohne Markdown-Umrahmung:
{{
  "name": "Kurzer funktionsbeschreibender Name (max 4 Wörter)",
  "description": "Ein präziser Satz was der Agent konkret macht",
  "system_prompt": "Vollständiger System-Prompt auf Deutsch",
  "suggested_modules": ["modul1", "modul2"]
}}"""

        llm = get_llm_client(max_tokens=600)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        raw = response.content if hasattr(response, "content") else str(response)

        # <think>-Blöcke entfernen (Thinking-Modelle)
        import re

        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # Erstes JSON-Objekt extrahieren
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError("Kein JSON in LLM-Antwort gefunden")

        import json

        spec = json.loads(m.group())

        return {
            "name": spec.get("name", ""),
            "description": spec.get("description", ""),
            "system_prompt": spec.get("system_prompt", ""),
            "suggested_modules": spec.get("suggested_modules", []),
        }

    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning("Agent-Generierung fehlgeschlagen: %s", exc)
        raise HTTPException(
            status_code=500, detail=f"Generierung fehlgeschlagen: {exc}"
        )


@router.post("/{agent_id}/duplicate", status_code=201)
async def duplicate_agent(agent_id: str, request: Request) -> dict:
    """Agenten duplizieren."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)
    original = next((a for a in agents if a["id"] == agent_id), None)
    if not original:
        raise HTTPException(
            status_code=404, detail=f"Agent '{agent_id}' nicht gefunden"
        )

    now = datetime.now(timezone.utc).isoformat()
    duplicate = {
        **original,
        "id": str(uuid.uuid4()),
        "name": f"{original['name']} (Kopie)",
        "created_at": now,
        "updated_at": now,
        "tenant_id": tenant_id,
    }
    agents.append(duplicate)
    await _save_agents(redis, tenant_id, agents)
    logger.info("Agent dupliziert: %s → %s", agent_id, duplicate["id"])
    return {"id": duplicate["id"], "status": "created"}


# ── AgentCards Endpoint ───────────────────────────────────────

from core.module_registry import get_registry
from pydantic import Field


class AgentCard(BaseModel):
    """AgentCard – strukturierte Modul-Information für externe Integrationen."""

    name: str
    display_name: str
    description: str = ""
    version: str = ""
    capabilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    api_prefix: str = ""
    has_dashboard_tab: bool = False


class AgentCardsResponse(BaseModel):
    """Response für AgentCards."""

    cards: list[AgentCard]
    total: int


@router.get("/cards", response_model=AgentCardsResponse)
async def get_agent_cards(request: Request) -> AgentCardsResponse:
    """
    Gibt alle Module als strukturierte AgentCards zurück.

    Nützlich für externe Integrationen und das Routing-Debugging.
    """
    _ = auth_tenant_id(resolve_request_auth(request))

    registry = get_registry()
    if not registry:
        return AgentCardsResponse(cards=[], total=0)

    cards: list[AgentCard] = []
    for manifest in registry.list_modules():
        cards.append(
            AgentCard(
                name=manifest.name,
                display_name=manifest.display_name,
                description=manifest.description,
                version=manifest.version,
                capabilities=manifest.agent_capabilities,
                keywords=manifest.routing_keywords,
                api_prefix=manifest.api_prefix,
                has_dashboard_tab=bool(manifest.dashboard_tab),
            )
        )

    return AgentCardsResponse(cards=cards, total=len(cards))
