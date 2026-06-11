"""
Ninko Workflows API – CRUD + Run-Management.
Persistenz via Redis (ninko:workflows, ninko:workflow:runs).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from core.auth import auth_tenant_id, resolve_request_auth
from core.redis_client import get_redis
from schemas.workflows import (
    WorkflowDefinition,
    WorkflowCreate,
    WorkflowListResponse,
    WorkflowRun,
    WorkflowRunListResponse,
    DebateCreateRequest,
    DebateVoteRequest,
)
from schemas.mutations import MutationResponse

logger = logging.getLogger("ninko.api.workflows")
router = APIRouter(prefix="/api/workflows", tags=["Workflows"])
_bg_workflow_tasks: set[asyncio.Task] = set()

REDIS_KEY_WORKFLOWS = "ninko:workflows"
REDIS_KEY_RUNS_PREFIX = "ninko:workflow:runs:"
REDIS_KEY_RUN_INDEX = "ninko:workflow:run_index"
REDIS_KEY_WORKFLOW_VERSIONS = "ninko:workflow:versions"
MAX_RUNS_PER_WORKFLOW = 50
MAX_VERSIONS_PER_WORKFLOW = 25


def _track_workflow_task(task: asyncio.Task) -> None:
    """Hält Background-Tasks referenziert und loggt ungefangene Exceptions."""
    _bg_workflow_tasks.add(task)

    def _on_done(done_task: asyncio.Task) -> None:
        _bg_workflow_tasks.discard(done_task)
        try:
            exc = done_task.exception()
        except asyncio.CancelledError:
            return
        if exc:
            logger.exception("Workflow-Background-Task abgestürzt: %s", exc)

    task.add_done_callback(_on_done)


def _tenant_key(base: str, tenant_id: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    return f"{base}:{t or 'default'}"


def _tenant_workflow_id(tenant_id: str, workflow_id: str) -> str:
    return f"{(tenant_id or 'default').strip().lower()}::{workflow_id}"


def _public_workflow_id(tenant_scoped_workflow_id: str) -> str:
    return (
        tenant_scoped_workflow_id.split("::", 1)[1]
        if "::" in tenant_scoped_workflow_id
        else tenant_scoped_workflow_id
    )


def _versions_key(tenant_id: str, scoped_workflow_id: str) -> str:
    return f"{_tenant_key(REDIS_KEY_WORKFLOW_VERSIONS, tenant_id)}:{scoped_workflow_id}"


async def _load_workflows(redis, tenant_id: str) -> list[dict]:
    raw = await redis.connection.get(_tenant_key(REDIS_KEY_WORKFLOWS, tenant_id))
    return json.loads(raw) if raw else []


async def _save_workflows(redis, tenant_id: str, workflows: list[dict]) -> None:
    await redis.connection.set(_tenant_key(REDIS_KEY_WORKFLOWS, tenant_id), json.dumps(workflows))


async def _mark_workflow_run_failed(
    redis,
    *,
    tenant_id: str,
    workflow_id: str,
    run_id: str,
    error: str,
) -> None:
    runs_key = f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{workflow_id}"
    runs_raw = await redis.connection.get(runs_key)
    runs = json.loads(runs_raw) if runs_raw else []
    now = datetime.now(timezone.utc).isoformat()
    for run in runs:
        if run.get("id") == run_id:
            run["status"] = "failed"
            run["error"] = error
            run["finished_at"] = now
            run["updated_at"] = now
            break
    await redis.connection.set(runs_key, json.dumps(runs))


@router.get("/", response_model=WorkflowListResponse)
async def list_workflows(request: Request) -> WorkflowListResponse:
    """Alle Workflows auflisten."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    workflows = await _load_workflows(redis, tenant_id)
    # Letzten Run-Status anreichern
    enriched = []
    for wf in workflows:
        wf_id = wf["id"]
        public_id = _public_workflow_id(wf_id)
        runs_raw = await redis.connection.get(
            f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{wf_id}"
        )
        runs = json.loads(runs_raw) if runs_raw else []
        if runs:
            latest = runs[-1]
            wf["last_run_status"] = latest.get("status", "idle")
            wf["last_run_at"] = latest.get("started_at")
        else:
            wf["last_run_status"] = "idle"
            wf["last_run_at"] = None
        wf["id"] = public_id
        enriched.append(wf)
    return WorkflowListResponse(
        workflows=[WorkflowDefinition(**w) for w in enriched], total=len(enriched)
    )


@router.post("/", status_code=201)
async def create_workflow(body: WorkflowCreate, request: Request) -> dict:
    """Neuen Workflow erstellen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    workflows = await _load_workflows(redis, tenant_id)
    now = datetime.now(timezone.utc).isoformat()
    scoped_id = _tenant_workflow_id(tenant_id, body.id)
    if any(w.get("id") == scoped_id for w in workflows):
        raise HTTPException(status_code=409, detail=f"Workflow '{body.id}' existiert bereits")
    new_wf = WorkflowDefinition(
        **{**body.model_dump(), "id": scoped_id},
        version=1,
        created_at=now,
        updated_at=now,
    )
    workflows.append({**new_wf.model_dump(), "tenant_id": tenant_id})
    await _save_workflows(redis, tenant_id, workflows)
    logger.info("Workflow erstellt: %s (%s)", new_wf.name, scoped_id)
    return {"id": body.id, "status": "created"}


@router.get("/templates")
async def get_workflow_templates() -> dict:
    """Returns all built-in workflow templates."""
    from core.workflow_templates import get_workflow_templates

    return {"templates": get_workflow_templates()}


@router.get("/templates/{template_id}")
async def get_workflow_template_definition(template_id: str) -> dict:
    """Returns a specific template with full definition (nodes, edges)."""
    from core.workflow_templates import load_template_definition

    definition = load_template_definition(template_id)
    if not definition:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' nicht gefunden")
    return definition


@router.post("/templates/{template_id}/instantiate")
async def instantiate_workflow_template(
    template_id: str, request: Request, name: str | None = None
) -> dict:
    """Creates a new workflow from a template."""
    from core.workflow_templates import instantiate_template

    instance = instantiate_template(template_id, name)
    if not instance:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' nicht gefunden")

    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    workflows = await _load_workflows(redis, tenant_id)
    public_id = str(instance["id"])
    scoped_id = _tenant_workflow_id(tenant_id, public_id)

    if any(w.get("id") == scoped_id for w in workflows):
        raise HTTPException(status_code=409, detail=f"Workflow '{public_id}' existiert bereits")

    now = datetime.now(timezone.utc).isoformat()
    workflow_def = WorkflowDefinition(
        **{**instance, "id": scoped_id},
        created_at=now,
        updated_at=now,
    )
    workflows.append({**workflow_def.model_dump(), "tenant_id": tenant_id})
    await _save_workflows(redis, tenant_id, workflows)

    logger.info("Workflow aus Template erstellt: %s (%s)", workflow_def.name, scoped_id)
    return {"id": public_id, "status": "created", "template_id": template_id}


@router.get("/debates")
async def list_debates(request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.debate_service import DebateService
    from core.llm_factory import llm_factory
    debate_service = DebateService(redis, request.app.state.orchestrator, llm_factory)
    debates = await debate_service.list_debates(tenant_id)
    return {"debates": debates, "total": len(debates)}


@router.get("/debates/{debate_id}")
async def get_debate(debate_id: str, request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.debate_service import DebateService
    from core.llm_factory import llm_factory
    debate_service = DebateService(redis, request.app.state.orchestrator, llm_factory)
    result = await debate_service.get_debate_result(debate_id, tenant_id)
    if not result:
        raise HTTPException(status_code=404, detail="Debate not found")
    return result


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str, request: Request) -> dict:
    """Einzelnen Workflow abrufen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    workflows = await _load_workflows(redis, tenant_id)
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)
    wf = next((w for w in workflows if w["id"] == scoped_id), None)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")
    wf = {**wf, "id": workflow_id}
    return wf


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowCreate, request: Request) -> dict:
    """Workflow bearbeiten."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    workflows = await _load_workflows(redis, tenant_id)
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)
    idx = next((i for i, w in enumerate(workflows) if w["id"] == scoped_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")
    now = datetime.now(timezone.utc).isoformat()

    # Alte Version in Historie sichern
    versions_key = _versions_key(tenant_id, scoped_id)
    versions_raw = await redis.connection.get(versions_key)
    versions = json.loads(versions_raw) if versions_raw else []
    previous = workflows[idx]
    versions.append(
        {
            "version": int(previous.get("version", 1) or 1),
            "saved_at": now,
            "workflow": previous,
        }
    )
    if len(versions) > MAX_VERSIONS_PER_WORKFLOW:
        versions = versions[-MAX_VERSIONS_PER_WORKFLOW:]
    await redis.connection.set(versions_key, json.dumps(versions))

    next_version = int(previous.get("version", 1) or 1) + 1
    workflows[idx] = {
        **workflows[idx],
        **body.model_dump(),
        "id": scoped_id,
        "version": next_version,
        "updated_at": now,
    }
    await _save_workflows(redis, tenant_id, workflows)
    logger.info("Workflow aktualisiert: %s", workflow_id)
    return {"id": workflow_id, "status": "updated", "version": next_version}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str, request: Request) -> dict:
    """Workflow löschen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    workflows = await _load_workflows(redis, tenant_id)
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)
    original_len = len(workflows)
    workflows = [w for w in workflows if w["id"] != scoped_id]
    if len(workflows) == original_len:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")
    await _save_workflows(redis, tenant_id, workflows)
    await redis.connection.delete(f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{scoped_id}")
    await redis.connection.delete(_versions_key(tenant_id, scoped_id))
    # Veraltete Run-Index-Einträge für diesen Workflow bereinigen
    run_index_key = _tenant_key(REDIS_KEY_RUN_INDEX, tenant_id)
    index_raw = await redis.connection.get(run_index_key)
    if index_raw:
        run_index = json.loads(index_raw)
        run_index = {k: v for k, v in run_index.items() if v != scoped_id}
        await redis.connection.set(run_index_key, json.dumps(run_index))
    logger.info("Workflow gelöscht: %s", workflow_id)
    return {"id": workflow_id, "deleted": True}


@router.post("/{workflow_id}/run", status_code=202)
async def run_workflow(workflow_id: str, request: Request) -> dict:
    """Workflow asynchron starten."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    workflows = await _load_workflows(redis, tenant_id)
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)
    wf = next((w for w in workflows if w["id"] == scoped_id), None)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")

    orchestrator = getattr(request.app.state, "orchestrator", None)
    if orchestrator is None:
        raise HTTPException(status_code=503, detail="Workflow-Engine nicht initialisiert")

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Initial-Run-Eintrag
    run = WorkflowRun(
        id=run_id,
        workflow_id=workflow_id,
        workflow_name=wf.get("name", ""),
        workflow_version=int(wf.get("version", 1) or 1),
        status="running",
        started_at=now,
        updated_at=now,
        steps=[],
        triggered_by="manual",
    )

    # Run in Redis speichern
    runs_key = f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{scoped_id}"
    runs_raw = await redis.connection.get(runs_key)
    runs = json.loads(runs_raw) if runs_raw else []
    runs.append(run.model_dump())
    if len(runs) > MAX_RUNS_PER_WORKFLOW:
        runs = runs[-MAX_RUNS_PER_WORKFLOW:]
    await redis.connection.set(runs_key, json.dumps(runs))

    # Run-Index tenant-scoped speichern
    run_index_key = _tenant_key(REDIS_KEY_RUN_INDEX, tenant_id)
    index_raw = await redis.connection.get(run_index_key)
    run_index = json.loads(index_raw) if index_raw else {}
    run_index[run_id] = scoped_id
    await redis.connection.set(run_index_key, json.dumps(run_index))

    # Workflow asynchron in Background ausführen
    try:
        from core.workflow_engine import WorkflowEngine

        engine = WorkflowEngine(redis, orchestrator)
        _track_workflow_task(asyncio.create_task(engine.execute(wf, run_id)))
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
        logger.warning("Workflow-Engine konnte nicht gestartet werden: %s", exc)
        await _mark_workflow_run_failed(
            redis,
            tenant_id=tenant_id,
            workflow_id=scoped_id,
            run_id=run_id,
            error=f"Workflow-Engine konnte nicht gestartet werden: {exc}",
        )
        raise HTTPException(
            status_code=500,
            detail="Workflow-Engine konnte nicht gestartet werden",
        ) from exc

    return {"run_id": run_id, "status": "running"}


@router.get("/{workflow_id}/versions")
async def list_workflow_versions(workflow_id: str, request: Request) -> dict:
    """Versionen eines Workflows auflisten (neueste zuerst)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)
    workflows = await _load_workflows(redis, tenant_id)
    current = next((w for w in workflows if w["id"] == scoped_id), None)
    if current is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")
    versions_raw = await redis.connection.get(_versions_key(tenant_id, scoped_id))
    versions = json.loads(versions_raw) if versions_raw else []
    versions = [
        {
            "version": int(current.get("version", 1) or 1),
            "saved_at": current.get("updated_at") or current.get("created_at"),
            "workflow": current,
            "current": True,
        },
        *list(reversed(versions)),
    ]
    return {"workflow_id": workflow_id, "versions": versions, "total": len(versions)}


@router.post("/{workflow_id}/versions/{version}/restore")
async def restore_workflow_version(workflow_id: str, version: int, request: Request) -> dict:
    """Stellt eine ältere Version als neue aktuelle Version wieder her."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)

    workflows = await _load_workflows(redis, tenant_id)
    idx = next((i for i, w in enumerate(workflows) if w["id"] == scoped_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")

    versions_key = _versions_key(tenant_id, scoped_id)
    versions_raw = await redis.connection.get(versions_key)
    versions = json.loads(versions_raw) if versions_raw else []
    target = next((v for v in versions if int(v.get("version", 0)) == version), None)
    if not target:
        raise HTTPException(status_code=404, detail=f"Version '{version}' nicht gefunden")

    now = datetime.now(timezone.utc).isoformat()
    current = workflows[idx]
    versions.append(
        {
            "version": int(current.get("version", 1) or 1),
            "saved_at": now,
            "workflow": current,
        }
    )
    if len(versions) > MAX_VERSIONS_PER_WORKFLOW:
        versions = versions[-MAX_VERSIONS_PER_WORKFLOW:]

    restored = dict(target.get("workflow", {}))
    restored["id"] = scoped_id
    restored["version"] = int(current.get("version", 1) or 1) + 1
    restored["updated_at"] = now
    workflows[idx] = restored

    await _save_workflows(redis, tenant_id, workflows)
    await redis.connection.set(versions_key, json.dumps(versions))
    return {"id": workflow_id, "status": "restored", "version": restored["version"]}


@router.get("/{workflow_id}/runs", response_model=WorkflowRunListResponse)
async def get_workflow_runs(workflow_id: str, request: Request) -> WorkflowRunListResponse:
    """Run-Historie eines Workflows."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)
    runs_raw = await redis.connection.get(
        f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{scoped_id}"
    )
    runs = json.loads(runs_raw) if runs_raw else []
    # Neueste zuerst
    runs = list(reversed(runs))
    return WorkflowRunListResponse(runs=[WorkflowRun(**r) for r in runs], total=len(runs))


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str, request: Request) -> dict:
    """Live-Status eines einzelnen Runs (Polling)."""
    redis = get_redis()
    # Suche in allen Workflow-Runs nach dem Run
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    run_index_key = _tenant_key(REDIS_KEY_RUN_INDEX, tenant_id)
    index_raw = await redis.connection.get(run_index_key)
    run_index = json.loads(index_raw) if index_raw else {}
    workflow_id = run_index.get(run_id)

    if workflow_id:
        runs_raw = await redis.connection.get(
            f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{workflow_id}"
        )
        runs = json.loads(runs_raw) if runs_raw else []
        run = next((r for r in runs if r["id"] == run_id), None)
        if run:
            return run

    raise HTTPException(status_code=404, detail=f"Run '{run_id}' nicht gefunden")


@router.post("/runs/{run_id}/steps/{step_index}/retry", status_code=202)
async def retry_workflow_step(run_id: str, step_index: int, request: Request) -> dict:
    """Einzelnen fehlgeschlagenen Workflow-Step neu ausführen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))

    # Run finden
    run_index_key = _tenant_key(REDIS_KEY_RUN_INDEX, tenant_id)
    index_raw = await redis.connection.get(run_index_key)
    run_index = json.loads(index_raw) if index_raw else {}
    workflow_id = run_index.get(run_id)

    if not workflow_id:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' nicht gefunden")

    # Run laden
    runs_key = f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{workflow_id}"
    runs_raw = await redis.connection.get(runs_key)
    runs = json.loads(runs_raw) if runs_raw else []
    run = next((r for r in runs if r["id"] == run_id), None)

    if not run:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' nicht gefunden")

    # Step validieren
    steps = run.get("steps", [])
    if step_index < 0 or step_index >= len(steps):
        raise HTTPException(status_code=400, detail=f"Ungültiger Step-Index: {step_index}")

    step = steps[step_index]
    if step.get("status") not in ["failed", "error"]:
        raise HTTPException(
            status_code=400, detail="Nur fehlgeschlagene Steps können retry't werden"
        )

    # Workflow laden
    workflows = await _load_workflows(redis, tenant_id)
    wf = next((w for w in workflows if w["id"] == workflow_id), None)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow nicht gefunden")

    # Step zurücksetzen
    step["status"] = "pending"
    step["error"] = None
    step["output"] = None
    step["started_at"] = None
    step["finished_at"] = None
    step["duration_ms"] = None
    step["attempts"] = (step.get("attempts") or 0) + 1

    # Aktualisierten Run speichern
    await redis.connection.set(runs_key, json.dumps(runs))

    # Step asynchron neu ausführen
    try:
        from core.workflow_engine import WorkflowEngine

        orchestrator = getattr(request.app.state, "orchestrator", None)
        if orchestrator is None:
            raise HTTPException(status_code=503, detail="Workflow-Engine nicht initialisiert")
        else:
            engine = WorkflowEngine(redis, orchestrator)
            _track_workflow_task(
                asyncio.create_task(
                    engine.execute_step(wf, run_id, step_index, run.get("variables", {}))
                )
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Step-Retry konnte nicht gestartet werden: %s", exc)
        raise HTTPException(status_code=500, detail=f"Retry konnte nicht gestartet werden: {exc}")

    return {"run_id": run_id, "step_index": step_index, "status": "retrying"}


@router.post("/debates", status_code=201)
async def create_debate(body: DebateCreateRequest, request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.debate_service import DebateService
    from core.llm_factory import llm_factory
    debate_service = DebateService(redis, request.app.state.orchestrator, llm_factory)
    debate = await debate_service.create_debate(
        topic=body.topic,
        mode=body.mode,
        participant_configs=[p.model_dump() for p in body.participants],
        max_rounds=body.max_rounds,
        consensus_threshold=body.consensus_threshold,
        tenant_id=tenant_id,
    )
    return {
        "debate_id": debate.debate_id,
        "topic": debate.topic,
        "mode": debate.mode,
        "status": debate.status,
        "max_rounds": debate.max_rounds,
        "current_round": debate.current_round,
        "participants": [
            {"agent_id": p.agent_id, "role": p.role, "name": p.name} for p in debate.participants
        ],
    }


@router.post("/debates/{debate_id}/run")
async def run_debate(debate_id: str, request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.debate_service import DebateService
    from core.llm_factory import llm_factory
    debate_service = DebateService(redis, request.app.state.orchestrator, llm_factory)
    await debate_service.run_full_debate(debate_id, tenant_id)
    return await debate_service.get_debate_result(debate_id, tenant_id) or {
        "error": "Debate not found"
    }


@router.post("/debates/{debate_id}/round")
async def run_debate_round(debate_id: str, request: Request) -> dict:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.debate_service import DebateService
    from core.llm_factory import llm_factory
    debate_service = DebateService(redis, request.app.state.orchestrator, llm_factory)
    round_result = await debate_service.run_debate_round(debate_id, tenant_id)
    return {
        "debate_id": debate_id,
        "round_number": round_result.round_number,
        "contributions": round_result.contributions,
        "consensus_reached": round_result.consensus_reached,
    }


@router.post("/debates/{debate_id}/vote", response_model=MutationResponse)
async def vote_in_debate(debate_id: str, body: DebateVoteRequest, request: Request) -> MutationResponse:
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    from core.debate_service import DebateService
    from core.llm_factory import llm_factory
    debate_service = DebateService(redis, request.app.state.orchestrator, llm_factory)
    success = await debate_service.vote(
        debate_id=debate_id,
        voter_agent_id=body.voter_agent_id,
        target_agent_id=body.target_agent_id,
        tenant_id=tenant_id,
    )
    return MutationResponse(status="ok" if success else "noop", id=debate_id, data={"vote_recorded": success})
