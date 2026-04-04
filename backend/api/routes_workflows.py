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
    WorkflowDefinition, WorkflowCreate, WorkflowListResponse,
    WorkflowRun, WorkflowRunListResponse
)

logger = logging.getLogger("ninko.api.workflows")
router = APIRouter(prefix="/api/workflows", tags=["Workflows"])

REDIS_KEY_WORKFLOWS = "ninko:workflows"
REDIS_KEY_RUNS_PREFIX = "ninko:workflow:runs:"
REDIS_KEY_RUN_INDEX = "ninko:workflow:run_index"
MAX_RUNS_PER_WORKFLOW = 50


def _tenant_key(base: str, tenant_id: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    return f"{base}:{t or 'default'}"


def _tenant_workflow_id(tenant_id: str, workflow_id: str) -> str:
    return f"{(tenant_id or 'default').strip().lower()}::{workflow_id}"


def _public_workflow_id(tenant_scoped_workflow_id: str) -> str:
    return tenant_scoped_workflow_id.split("::", 1)[1] if "::" in tenant_scoped_workflow_id else tenant_scoped_workflow_id


async def _load_workflows(redis, tenant_id: str) -> list[dict]:
    raw = await redis.connection.get(_tenant_key(REDIS_KEY_WORKFLOWS, tenant_id))
    return json.loads(raw) if raw else []


async def _save_workflows(redis, tenant_id: str, workflows: list[dict]) -> None:
    await redis.connection.set(_tenant_key(REDIS_KEY_WORKFLOWS, tenant_id), json.dumps(workflows))


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
        runs_raw = await redis.connection.get(f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{wf_id}")
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
    return WorkflowListResponse(workflows=[WorkflowDefinition(**w) for w in enriched], total=len(enriched))


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
    new_wf = WorkflowDefinition(**{**body.model_dump(), "id": scoped_id}, created_at=now, updated_at=now)
    workflows.append(new_wf.model_dump())
    await _save_workflows(redis, tenant_id, workflows)
    logger.info("Workflow erstellt: %s (%s)", new_wf.name, scoped_id)
    return {"id": body.id, "status": "created"}


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
    workflows[idx] = {**workflows[idx], **body.model_dump(), "id": scoped_id, "updated_at": now}
    await _save_workflows(redis, tenant_id, workflows)
    logger.info("Workflow aktualisiert: %s", workflow_id)
    return {"id": workflow_id, "status": "updated"}


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

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Initial-Run-Eintrag
    run = WorkflowRun(
        id=run_id,
        workflow_id=workflow_id,
        workflow_name=wf.get("name", ""),
        status="running",
        started_at=now,
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
        orchestrator = request.app.state.orchestrator
        engine = WorkflowEngine(redis, orchestrator)
        asyncio.create_task(engine.execute(wf, run_id))
    except (RuntimeError, ValueError, TypeError, KeyError, OSError) as exc:
        logger.warning("Workflow-Engine konnte nicht gestartet werden: %s", exc)

    return {"run_id": run_id, "status": "running"}



@router.get("/{workflow_id}/runs", response_model=WorkflowRunListResponse)
async def get_workflow_runs(workflow_id: str, request: Request) -> WorkflowRunListResponse:
    """Run-Historie eines Workflows."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scoped_id = _tenant_workflow_id(tenant_id, workflow_id)
    runs_raw = await redis.connection.get(f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{scoped_id}")
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
        runs_raw = await redis.connection.get(f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant_id)}{workflow_id}")
        runs = json.loads(runs_raw) if runs_raw else []
        run = next((r for r in runs if r["id"] == run_id), None)
        if run:
            return run

    raise HTTPException(status_code=404, detail=f"Run '{run_id}' nicht gefunden")
