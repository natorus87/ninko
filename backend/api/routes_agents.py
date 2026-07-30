"""
Ninko Agents API – CRUD für Agenten-Definitionen.
Persistenz via Redis (ninko:agents).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field

from core.auth import auth_tenant_id, resolve_request_auth
from core.agent_event_journal import (
    AgentEventJournal,
    JournaledAgentEvent,
    get_agent_event_journal,
    normalize_event_cursor,
)
from core.redis_client import get_redis
from core.module_registry import get_registry
from schemas.execution import AgentEvent, AgentEventType
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
_TERMINAL_AGENT_EVENTS = {
    AgentEventType.COMPLETED,
    AgentEventType.FAILED,
    AgentEventType.CANCELLED,
    AgentEventType.APPROVAL_REQUIRED,
}
_TERMINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}
_MAX_EVENT_STREAMS_PER_PRINCIPAL = 5
_MAX_EVENT_STREAMS_GLOBAL = 16
_MAX_EVENT_STREAM_SECONDS = 300.0
_active_event_streams: dict[str, int] = {}
_active_event_stream_total = 0
_active_event_streams_lock = asyncio.Lock()


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


def _agent_event_sse_frame(item: JournaledAgentEvent) -> str:
    """Serialize one journal item as a resumable SSE frame."""
    return (
        f"id: {item.cursor}\n"
        f"event: {item.event.type.value}\n"
        f"data: {item.event.model_dump_json()}\n\n"
    )


async def _stream_agent_events(
    request: Request,
    journal: AgentEventJournal,
    *,
    tenant_id: str,
    session_id: str,
    after: str,
    run_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Replay persisted events and then wait for live Redis Stream entries."""
    cursor = normalize_event_cursor(after)
    deadline = time.monotonic() + _MAX_EVENT_STREAM_SECONDS
    matched_run_ids = {run_id} if run_id is not None else set()
    while (
        time.monotonic() < deadline
        and not await request.is_disconnected()
    ):
        items = await journal.read_after(
            tenant_id=tenant_id,
            session_id=session_id,
            after=cursor,
        )
        scanned_cursor = getattr(
            items,
            "scanned_cursor",
            items[-1].cursor if items else cursor,
        )
        cursor_advanced = scanned_cursor != cursor
        if cursor_advanced:
            cursor = scanned_cursor
        if not items:
            if cursor_advanced:
                continue
            items = await journal.wait_after(
                tenant_id=tenant_id,
                session_id=session_id,
                after=cursor,
            )
            scanned_cursor = getattr(
                items,
                "scanned_cursor",
                items[-1].cursor if items else cursor,
            )
            if scanned_cursor != cursor:
                cursor = scanned_cursor
        if not items:
            yield ": keepalive\n\n"
            continue

        for item in items:
            event = item.event
            matches_run = (
                run_id is None
                or event.run_id in matched_run_ids
                or event.parent_run_id in matched_run_ids
                or (
                    event.parent_run_id is not None
                    and event.parent_run_id.startswith(f"{run_id}:")
                )
            )
            if matches_run:
                matched_run_ids.add(event.run_id)
                yield _agent_event_sse_frame(item)
            if (
                run_id is not None
                and event.run_id == run_id
                and event.type in _TERMINAL_AGENT_EVENTS
            ):
                return
        await asyncio.sleep(0)


async def _reserve_event_stream(principal: str) -> None:
    global _active_event_stream_total
    async with _active_event_streams_lock:
        active = _active_event_streams.get(principal, 0)
        if active >= _MAX_EVENT_STREAMS_PER_PRINCIPAL:
            raise HTTPException(
                status_code=429,
                detail="Zu viele gleichzeitige AgentEvent-Streams",
            )
        if _active_event_stream_total >= _MAX_EVENT_STREAMS_GLOBAL:
            raise HTTPException(
                status_code=503,
                detail="AgentEvent-Stream-Kapazität ist ausgelastet",
            )
        _active_event_streams[principal] = active + 1
        _active_event_stream_total += 1


async def _release_event_stream(principal: str) -> None:
    global _active_event_stream_total
    async with _active_event_streams_lock:
        remaining = _active_event_streams.get(principal, 0) - 1
        if remaining > 0:
            _active_event_streams[principal] = remaining
        else:
            _active_event_streams.pop(principal, None)
        _active_event_stream_total = max(0, _active_event_stream_total - 1)


async def _limited_event_stream(
    principal: str,
    generator: AsyncGenerator[str, None],
) -> AsyncGenerator[str, None]:
    try:
        async for frame in generator:
            yield frame
    finally:
        await _release_event_stream(principal)


def _event_stream_response(
    generator: AsyncGenerator[str, None],
    *,
    initial_cursor: str | None = None,
) -> StreamingResponse:
    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    if initial_cursor is not None:
        headers["X-Agent-Event-Cursor"] = initial_cursor
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers=headers,
    )


def _event_cursor(
    request: Request,
    after: str | None,
    last_event_id: str | None = None,
) -> str:
    try:
        return normalize_event_cursor(
            after
            if after is not None
            else last_event_id
            if last_event_id is not None
            else request.headers.get("last-event-id")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _event_stream_principal(request: Request, tenant_id: str) -> str:
    auth_ctx = resolve_request_auth(request)
    username = str((auth_ctx or {}).get("username") or "anonymous")
    return f"{tenant_id}:{username}"


async def _assert_existing_session_access(
    request: Request,
    scoped_session_id: str,
) -> None:
    auth_ctx = resolve_request_auth(request)
    username = str((auth_ctx or {}).get("username") or "")
    if not username:
        raise HTTPException(status_code=401, detail="Authentifizierung erforderlich")
    owner = await get_redis().get_session_owner(scoped_session_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Session nicht gefunden")
    if owner != username:
        raise HTTPException(status_code=403, detail="Kein Zugriff auf diese Session")


@router.get(
    "/events/stream",
    responses={
        401: {"description": "Authentication required"},
        403: {"description": "Session belongs to another user"},
        404: {"description": "Session has no existing owner"},
        429: {"description": "Per-user stream limit reached"},
        503: {"description": "Process stream capacity reached"},
    },
)
async def stream_session_agent_events(
    request: Request,
    session_id: str = Query(min_length=1, max_length=256),
    after: str | None = Query(default=None, max_length=41),
    tail: bool = Query(default=False),
    run_id: str | None = Query(default=None, min_length=1, max_length=128),
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
        max_length=41,
    ),
) -> StreamingResponse:
    """Replay and follow events for an existing, user-owned chat session.

    Frames use SSE ``id: <milliseconds>-<sequence>``, ``event: <type>`` and a
    JSON ``data`` payload. Replay starts strictly after ``after`` or
    ``Last-Event-ID``; the query parameter wins and the default is ``0-0``.
    ``tail=true`` starts at the server-side stream tail and cannot be combined
    with an explicit cursor. The selected tail is returned in
    ``X-Agent-Event-Cursor``. Comment frames are keepalives. Reconnect after
    the five-minute limit.
    A user may hold five streams; the process accepts sixteen in total.
    This read endpoint never claims an ownerless session.
    """
    from api.routes_chat import _tenant_session_id

    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scoped_session_id = _tenant_session_id(request, session_id)
    header_cursor = last_event_id or request.headers.get("last-event-id")
    if tail and (after is not None or header_cursor is not None):
        raise HTTPException(
            status_code=400,
            detail="tail kann nicht mit einem AgentEvent-Cursor kombiniert werden",
        )
    cursor = "0-0" if tail else _event_cursor(request, after, last_event_id)
    await _assert_existing_session_access(request, scoped_session_id)
    journal = get_agent_event_journal()
    if tail:
        cursor = await journal.latest_cursor(
            tenant_id=tenant_id,
            session_id=scoped_session_id,
        )
    principal = _event_stream_principal(request, tenant_id)
    await _reserve_event_stream(principal)
    return _event_stream_response(
        _limited_event_stream(
            principal,
            _stream_agent_events(
                request,
                journal,
                tenant_id=tenant_id,
                session_id=scoped_session_id,
                after=cursor,
                run_id=run_id,
            ),
        ),
        initial_cursor=cursor,
    )


@router.get(
    "/jobs/{job_id}/events",
    responses={
        204: {"description": "Terminal cursor is already fully caught up"},
        404: {"description": "Job not found in the current tenant"},
        410: {"description": "Retained event history is no longer available"},
        429: {"description": "Per-user stream limit reached"},
        503: {"description": "Process stream capacity reached"},
    },
)
async def stream_agent_job_events(
    job_id: str,
    request: Request,
    after: str | None = Query(default=None, max_length=41),
    last_event_id: str | None = Header(
        default=None,
        alias="Last-Event-ID",
        max_length=41,
    ),
) -> Response:
    """Replay and follow lifecycle events for one tenant-owned Agent Job.

    The cursor and frame contract matches the session stream. Terminal jobs
    return 410 when no retained history exists from ``0-0`` and 204 when a
    nonzero cursor is already caught up. A partial journal missing its terminal
    row is repaired from the authoritative job snapshot before streaming.
    Streams last at most five minutes and share the documented admission limits.
    """
    from core.agent_jobs import get_agent_job_manager

    tenant_id = auth_tenant_id(resolve_request_auth(request))
    job = await get_agent_job_manager().get_job(tenant_id, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' nicht gefunden")
    cursor = _event_cursor(request, after, last_event_id)
    journal = get_agent_event_journal()
    job_tenant_id = str(job["tenant_id"])
    job_session_id = f"{job_tenant_id}:job-{job_id}"
    if job.get("status") in _TERMINAL_JOB_STATUSES:
        replay = await journal.read_after(
            tenant_id=job_tenant_id,
            session_id=job_session_id,
            after=cursor,
            limit=500,
        )
        if not replay:
            if cursor != "0-0":
                return Response(status_code=204)
            raise HTTPException(
                status_code=410,
                detail="AgentEvent-Historie für diesen Job ist nicht mehr verfügbar",
            )
        has_terminal = any(
            item.event.run_id == job_id
            and item.event.type in _TERMINAL_AGENT_EVENTS
            for item in replay
        )
        if not has_terminal:
            terminal_type = {
                "succeeded": AgentEventType.COMPLETED,
                "cancelled": AgentEventType.CANCELLED,
            }.get(str(job.get("status")), AgentEventType.FAILED)
            await journal.append(
                AgentEvent(
                    type=terminal_type,
                    tenant_id=job_tenant_id,
                    session_id=job_session_id,
                    run_id=job_id,
                    agent_id=str(job.get("agent_id") or "unknown"),
                    data={
                        "status": str(job.get("status")),
                        "duration_ms": job.get("duration_ms"),
                        "recovered_from_job": True,
                    },
                )
            )
    principal = _event_stream_principal(request, tenant_id)
    await _reserve_event_stream(principal)
    return _event_stream_response(
        _limited_event_stream(
            principal,
            _stream_agent_events(
                request,
                journal,
                tenant_id=job_tenant_id,
                session_id=job_session_id,
                after=cursor,
                run_id=job_id,
            ),
        )
    )


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
