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
from pydantic import BaseModel, Field

from core.auth import auth_tenant_id, resolve_request_auth
from core.redis_client import get_redis
from core.module_registry import get_registry
from schemas.agents import (
    AgentDefinition,
    AgentCreate,
    AgentListResponse,
    AgentJobInfo,
    AgentJobListResponse,
    AgentJobRunRequest,
    AgentJobRunResponse,
)

logger = logging.getLogger("ninko.api.agents")
router = APIRouter(prefix="/api/agents", tags=["Agents"])


class AgentGenerateRequest(BaseModel):
    use_case: str
    allowed_modules: list[str] = []


class AgentCard(BaseModel):
    name: str
    display_name: str
    description: str = ""
    version: str = ""
    capabilities: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    api_prefix: str = ""
    has_dashboard_tab: bool = False


class AgentCardsResponse(BaseModel):
    cards: list[AgentCard]
    total: int


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


def _infer_modules_from_use_case(use_case: str) -> list[str]:
    use_case_lower = use_case.lower()
    keywords_to_modules = {
        "kubernetes": ["kubernetes"],
        "k8s": ["kubernetes"],
        "pod": ["kubernetes"],
        "container": ["kubernetes", "docker"],
        "docker": ["docker"],
        "linux": ["linux_server"],
        "server": ["linux_server"],
        "ssh": ["linux_server"],
        "proxmox": ["proxmox"],
        "vm": ["proxmox"],
        "firewall": ["opnsense"],
        "dns": ["pihole"],
        "blocking": ["pihole"],
        "smart home": ["homeassistant"],
        "home assistant": ["homeassistant"],
        "licht": ["homeassistant"],
        "heizung": ["homeassistant"],
        "ticket": ["glpi"],
        "helpdesk": ["glpi"],
        "monitoring": ["checkmk"],
        "alert": ["checkmk"],
        "github": ["github"],
        "gitlab": ["gitlab"],
        "ci/cd": ["github", "gitlab"],
        "pipeline": ["github", "gitlab"],
        "web_search": ["web_search"],
        "recherche": ["web_search"],
        "suchen": ["web_search"],
        "internet": ["web_search"],
        "bild": ["image_gen"],
        "image": ["image_gen"],
        "foto": ["image_gen"],
    }

    suggested = set()
    for keyword, modules in keywords_to_modules.items():
        if keyword in use_case_lower:
            suggested.update(modules)

    return list(suggested)[:4]


def _build_minimal_spec(use_case: str, inferred_modules: list[str]) -> dict:
    name = use_case.split()[:3]
    name = " ".join(name) if name else "Custom Agent"
    name = name[:40]

    modules_str = ", ".join(inferred_modules) if inferred_modules else "web_search"

    return {
        "name": name,
        "description": f"Agent für: {use_case[:80]}",
        "system_prompt": f"""Du bist ein spezialisierter Agent für: {use_case}

## Aufgaben
- Analysiere Anfragen im Kontext von: {use_case}
- Nutze verfügbare Module für spezifische Operationen
- Dokumentiere durchgeführte Aktionen

## Arbeitsweise
- Präzise und effizient
- Ergebnisse strukturiert aufbereiten
- Bei Unklarheiten nachfragen

## Kritische Aktionen
- Destruktive Operationen immer bestätigen lassen
- Keine autonomen Änderungen ohne Freigabe

## Verfügbare Module
{modules_str}""",
        "suggested_modules": inferred_modules if inferred_modules else ["web_search"],
    }


def _extract_json_from_llm_response(raw: str) -> dict:
    """Extract JSON from LLM response - handles Markdown and formatting issues."""
    import re

    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()

    patterns = [
        (r"```json\s*(.*?)```", re.DOTALL),
        (r"```\s*(.*?)```", re.DOTALL),
        (r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", re.DOTALL),
    ]

    for pattern, flags in patterns:
        if pattern.startswith("```"):
            matches = re.findall(pattern, raw, flags)
        else:
            matches = [re.search(pattern, raw, flags)]
        for match in matches:
            if match is None:
                continue
            text = match.strip() if isinstance(match, str) else match.group().strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                fixed = re.sub(r",\s*\}", "}", text)
                fixed = re.sub(r",\s*\]", "]", fixed)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    continue

    raise ValueError(f"No valid JSON found in LLM response. Raw (first 500 chars): {raw[:500]}")


def _validate_agent_spec(spec: dict, use_case: str, inferred_modules: list[str]) -> dict:
    """Validate and complete agent specification ensuring all required fields exist."""
    validated = {
        "name": spec.get("name", "").strip() or f"Agent für {use_case[:30]}",
        "description": spec.get("description", "").strip() or f"Spezialisiert für: {use_case[:80]}",
        "system_prompt": spec.get("system_prompt", "").strip(),
        "suggested_modules": spec.get("suggested_modules", inferred_modules) or inferred_modules,
    }

    if not validated["system_prompt"]:
        validated["system_prompt"] = _build_minimal_spec(use_case, inferred_modules)[
            "system_prompt"
        ]

    if not isinstance(validated["suggested_modules"], list):
        validated["suggested_modules"] = inferred_modules
    else:
        validated["suggested_modules"] = [
            m for m in validated["suggested_modules"] if isinstance(m, str) and m.strip()
        ]
        if not validated["suggested_modules"]:
            validated["suggested_modules"] = inferred_modules

    validated["name"] = validated["name"][:60]
    validated["description"] = validated["description"][:200]

    return validated


@router.get("/", response_model=AgentListResponse)
async def list_agents(request: Request) -> AgentListResponse:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)
    pub = [_public_agent(a) for a in agents]
    return AgentListResponse(agents=[AgentDefinition(**a) for a in pub], total=len(pub))


def _reject_reserved_agent_name(name: str) -> None:
    """Blockt reservierte Built-in-Agent-Namen (verhindert Soul-/Routing-Kollision)."""
    from core.agent_pool import _RESERVED_AGENT_NAMES

    if (name or "").strip().casefold() in _RESERVED_AGENT_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"Agent-Name '{name}' ist reserviert und nicht erlaubt.",
        )


def _validate_agent_create(body: AgentCreate) -> None:
    _reject_reserved_agent_name(body.name)

    from core.agent_pool import _MAX_SYSTEM_PROMPT_CHARS

    if len(body.system_prompt or "") > _MAX_SYSTEM_PROMPT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"System-Prompt zu lang ({len(body.system_prompt)} Zeichen, "
                f"max. {_MAX_SYSTEM_PROMPT_CHARS})."
            ),
        )


@router.post("/", status_code=201)
async def create_agent(body: AgentCreate, request: Request) -> dict:
    _validate_agent_create(body)
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))

    now = datetime.now(timezone.utc).isoformat()
    new_agent = AgentDefinition(
        **body.model_dump(),
        created_at=now,
        updated_at=now,
    )
    # Geteilter Lock mit dem DynamicAgentPool: verhindert Lost Updates zwischen
    # API-Write und pool.register auf ninko:agents:<tenant>.
    from core.agent_pool import get_agents_redis_lock

    async with get_agents_redis_lock():
        agents = await _load_agents(redis, tenant_id)
        agents.append({**new_agent.model_dump(), "tenant_id": tenant_id})
        await _save_agents(redis, tenant_id, agents)
    await _sync_agent_pool({**new_agent.model_dump(), "tenant_id": tenant_id})
    logger.info("Agent erstellt: %s (%s)", new_agent.name, new_agent.id)
    return {"id": new_agent.id, "status": "created"}


@router.get("/templates")
async def get_agent_templates() -> dict:
    from core.agent_templates import AGENT_TEMPLATES

    return {"templates": AGENT_TEMPLATES}


@router.get("/cards", response_model=AgentCardsResponse)
async def get_agent_cards(request: Request) -> AgentCardsResponse:
    """Return all modules as structured AgentCards for external integrations."""
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


@router.get("/{agent_id}")
async def get_agent(agent_id: str, request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)
    agent = next((a for a in agents if a["id"] == agent_id), None)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nicht gefunden")

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
    _validate_agent_create(body)
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.agent_pool import get_agents_redis_lock

    now = datetime.now(timezone.utc).isoformat()
    async with get_agents_redis_lock():
        agents = await _load_agents(redis, tenant_id)
        idx = next((i for i, a in enumerate(agents) if a["id"] == agent_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nicht gefunden")

        updated = {
            **agents[idx],
            **body.model_dump(),
            "id": agent_id,
            "updated_at": now,
            "tenant_id": tenant_id,
        }
        agents[idx] = updated
        await _save_agents(redis, tenant_id, agents)
    await _sync_agent_pool(updated)
    logger.info("Agent aktualisiert: %s", agent_id)
    return {"id": agent_id, "status": "updated"}


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str, request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.agent_pool import get_agents_redis_lock

    async with get_agents_redis_lock():
        agents = await _load_agents(redis, tenant_id)
        deleted_agent = next((a for a in agents if a["id"] == agent_id), None)
        if not deleted_agent:
            raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' nicht gefunden")

        agents = [a for a in agents if a["id"] != agent_id]
        await _save_agents(redis, tenant_id, agents)
    await _remove_agent_from_pool(agent_id, tenant_id)

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

    # Per-Agent-Overrides entfernen (sonst bleiben verwaiste, sicherheitsrelevante
    # Einträge wie safeguard_enabled=false unbegrenzt in ninko:agent_configs).
    try:
        from core.agent_config_store import AgentConfigStore

        await AgentConfigStore().delete_config(agent_id)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning("Config-Cleanup für Agent '%s' fehlgeschlagen: %s", agent_id, exc)

    # Referenzierende Scheduler-Tasks deaktivieren, sonst werfen sie bei jedem
    # Cron-Lauf ValueError ("Agent nicht im Pool gefunden").
    try:
        from agents.scheduler_agent import get_scheduler_agent

        scheduler = get_scheduler_agent()
        if scheduler is not None:
            for task in await scheduler.get_all_tasks():
                if task.get("agent_id") == agent_id and task.get("enabled", True):
                    await scheduler.update_task(task["id"], {"enabled": False})
                    logger.info(
                        "Scheduler-Task '%s' deaktiviert (Agent '%s' gelöscht).",
                        task["id"],
                        agent_id,
                    )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning(
            "Scheduler-Task-Cleanup für Agent '%s' fehlgeschlagen: %s", agent_id, exc
        )

    logger.info("Agent gelöscht: %s", agent_id)
    return {"id": agent_id, "deleted": True}


@router.post("/generate")
async def generate_agent_spec(body: AgentGenerateRequest) -> dict:
    """Generate agent specification from use case using LLM with robust fallback."""
    use_case = body.use_case.strip()
    if not use_case:
        raise HTTPException(status_code=422, detail="use_case darf nicht leer sein")

    inferred_modules = _infer_modules_from_use_case(use_case)
    generation_log = {
        "use_case": use_case,
        "inferred_modules": inferred_modules,
        "allowed_modules": body.allowed_modules,
        "step": "init",
        "raw_response": None,
        "error": None,
    }

    try:
        generation_log["step"] = "registry_lookup"
        try:
            registry = get_registry()
            all_modules = [
                f"{m.name} ({m.description[:60]})"
                for m in registry.list_modules()
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
        ):
            module_context = (
                "kubernetes, linux_server, docker, pihole, homeassistant, opnsense, glpi, telegram"
            )

        allowed_hint = ""
        if body.allowed_modules:
            allowed_hint = f"\nBevorzugte Module: {', '.join(body.allowed_modules)}"
        elif inferred_modules:
            allowed_hint = f"\nBevorzugte Module: {', '.join(inferred_modules)}"

        prompt = f"""Du bist ein Agent-Builder-Experte für das Ninko IT-Operations-System.

Erstelle für den folgenden Use-Case eine vollständige, hochwertige Agent-Spezifikation.

USE-CASE: {use_case}{allowed_hint}

VERFÜGBARE MODULE: {module_context}

ANFORDERUNGEN AN DEN SYSTEM-PROMPT:
- Klar strukturiert mit ## Aufgaben, ## Arbeitsweise, ## Kritische Aktionen, ## Eskalation
- Spezifische, handlungsorientierte Bullet-Points
- Destruktive Aktionen explizit gekennzeichnet ("immer bestätigen lassen")
- Eskalationsregel: "Aufgabe außerhalb Scope → an Ninko zurückgeben"
- Module via call_module_agent("<modul>", "...") erwähnen wenn relevant
- Kompakt: 200–400 Zeichen

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt:
{{
  "name": "Kurzer funktionsbeschreibender Name (max 4 Wörter)",
  "description": "Ein präziser Satz was der Agent konkret macht",
  "system_prompt": "Vollständiger System-Prompt auf Deutsch",
  "suggested_modules": ["modul1", "modul2"]
}}"""

        generation_log["step"] = "llm_invoke"
        from core.llm_factory import get_llm
        from langchain_core.messages import HumanMessage
        import asyncio

        llm = get_llm()

        AGENT_GENERATION_TIMEOUT_SECONDS = 30.0
        try:
            response = await asyncio.wait_for(
                llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=AGENT_GENERATION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError as exc:
            raise RuntimeError(
                "LLM-Aufruf für Agent-Generierung hat Timeout "
                f"({AGENT_GENERATION_TIMEOUT_SECONDS}s) überschritten"
            ) from exc

        raw = response.content if hasattr(response, "content") else str(response)
        generation_log["raw_response"] = raw[:2000]

        generation_log["step"] = "json_extract"
        spec = _extract_json_from_llm_response(raw)

        generation_log["step"] = "validate"
        validated = _validate_agent_spec(spec, use_case, inferred_modules)

        result = {
            **validated,
            "_generation_info": {
                "used_inferred_modules": bool(inferred_modules and not body.allowed_modules),
                "fallback_used": False,
            },
        }

        logger.info("Agent-Spezifikation generiert: %s", result["name"])
        return result

    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        generation_log["step"] = f"error_{generation_log['step']}"
        generation_log["error"] = str(exc)
        logger.warning(
            "Agent-Generierung fehlgeschlagen (Fallback wird verwendet): %s | Log: %s",
            exc,
            json.dumps(generation_log, ensure_ascii=False),
        )

        fallback = _build_minimal_spec(use_case, inferred_modules)
        fallback["_generation_info"] = {
            "used_inferred_modules": bool(inferred_modules),
            "fallback_used": True,
            "original_error": str(exc)[:100],
        }
        return fallback


@router.post("/{agent_id}/duplicate", status_code=201)
async def duplicate_agent(agent_id: str, request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    agents = await _load_agents(redis, tenant_id)
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
        "tenant_id": tenant_id,
    }
    agents.append(duplicate)
    await _save_agents(redis, tenant_id, agents)
    await _sync_agent_pool(duplicate)
    logger.info("Agent dupliziert: %s → %s", agent_id, duplicate["id"])
    return {"id": duplicate["id"], "status": "created"}


# ── Agent Jobs: einmalige Hintergrund-Ausführung ─────


def _public_job(job: dict) -> AgentJobInfo:
    j = dict(job)
    j.pop("tenant_id", None)
    return AgentJobInfo(**j)


@router.post("/{agent_id}/run", status_code=202, response_model=AgentJobRunResponse)
async def run_agent(agent_id: str, body: AgentJobRunRequest, request: Request) -> AgentJobRunResponse:
    """Führt einen Agenten einmalig als Hintergrund-Job aus."""
    from core.agent_jobs import get_agent_job_manager

    tenant_id = auth_tenant_id(resolve_request_auth(request))
    manager = get_agent_job_manager()
    try:
        job = await manager.start_job(
            tenant_id=tenant_id,
            agent_id=agent_id,
            prompt=body.prompt,
            triggered_by="api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AgentJobRunResponse(job_id=job["id"], agent_id=agent_id, status=job["status"])


@router.get("/{agent_id}/jobs", response_model=AgentJobListResponse)
async def list_agent_jobs(agent_id: str, request: Request, limit: int = 20) -> AgentJobListResponse:
    """Job-Historie eines Agenten (neueste zuerst)."""
    from core.agent_jobs import get_agent_job_manager

    tenant_id = auth_tenant_id(resolve_request_auth(request))
    jobs = await get_agent_job_manager().list_jobs(tenant_id, agent_id, limit=limit)
    return AgentJobListResponse(jobs=[_public_job(j) for j in jobs], total=len(jobs))


@router.get("/jobs/{job_id}", response_model=AgentJobInfo)
async def get_agent_job(job_id: str, request: Request) -> AgentJobInfo:
    """Status/Ergebnis eines einzelnen Agent-Jobs."""
    from core.agent_jobs import get_agent_job_manager

    tenant_id = auth_tenant_id(resolve_request_auth(request))
    job = await get_agent_job_manager().get_job(tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' nicht gefunden")
    return _public_job(job)


@router.post("/jobs/{job_id}/cancel", response_model=AgentJobInfo)
async def cancel_agent_job(job_id: str, request: Request) -> AgentJobInfo:
    """Bricht einen laufenden/wartenden Agent-Job ab."""
    from core.agent_jobs import get_agent_job_manager

    tenant_id = auth_tenant_id(resolve_request_auth(request))
    manager = get_agent_job_manager()
    try:
        job = await manager.cancel_job(tenant_id, job_id)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "nicht gefunden" in detail else 409
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return _public_job(job)


async def _sync_agent_pool(agent: dict) -> None:
    """Keep API-created or edited agents available in the live DynamicAgentPool."""
    try:
        from core.agent_pool import get_agent_pool

        await get_agent_pool().sync_agent(agent)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning("Live-Agent-Pool-Sync fehlgeschlagen (%s): %s", agent.get("id"), exc)


async def _remove_agent_from_pool(agent_id: str, tenant_id: str) -> None:
    """Remove deleted agents from the live DynamicAgentPool."""
    try:
        from core.agent_pool import get_agent_pool

        await get_agent_pool().remove_agent(agent_id, tenant_id=tenant_id)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        logger.warning("Live-Agent-Pool-Remove fehlgeschlagen (%s): %s", agent_id, exc)
