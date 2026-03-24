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


async def _load_workflows(redis) -> list[dict]:
    raw = await redis.connection.get(REDIS_KEY_WORKFLOWS)
    return json.loads(raw) if raw else []


async def _save_workflows(redis, workflows: list[dict]) -> None:
    await redis.connection.set(REDIS_KEY_WORKFLOWS, json.dumps(workflows))


@router.get("/", response_model=WorkflowListResponse)
async def list_workflows() -> WorkflowListResponse:
    """Alle Workflows auflisten."""
    redis = get_redis()
    workflows = await _load_workflows(redis)
    # Letzten Run-Status anreichern
    enriched = []
    for wf in workflows:
        wf_id = wf["id"]
        runs_raw = await redis.connection.get(f"{REDIS_KEY_RUNS_PREFIX}{wf_id}")
        runs = json.loads(runs_raw) if runs_raw else []
        if runs:
            latest = runs[-1]
            wf["last_run_status"] = latest.get("status", "idle")
            wf["last_run_at"] = latest.get("started_at")
        else:
            wf["last_run_status"] = "idle"
            wf["last_run_at"] = None
        enriched.append(wf)
    return WorkflowListResponse(workflows=[WorkflowDefinition(**w) for w in enriched], total=len(enriched))


@router.post("/", status_code=201)
async def create_workflow(body: WorkflowCreate) -> dict:
    """Neuen Workflow erstellen."""
    redis = get_redis()
    workflows = await _load_workflows(redis)
    now = datetime.now(timezone.utc).isoformat()
    new_wf = WorkflowDefinition(**body.model_dump(), created_at=now, updated_at=now)
    workflows.append(new_wf.model_dump())
    await _save_workflows(redis, workflows)
    logger.info("Workflow erstellt: %s (%s)", new_wf.name, new_wf.id)
    return {"id": new_wf.id, "status": "created"}


@router.get("/{workflow_id}")
async def get_workflow(workflow_id: str) -> dict:
    """Einzelnen Workflow abrufen."""
    redis = get_redis()
    workflows = await _load_workflows(redis)
    wf = next((w for w in workflows if w["id"] == workflow_id), None)
    if not wf:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")
    return wf


@router.put("/{workflow_id}")
async def update_workflow(workflow_id: str, body: WorkflowCreate) -> dict:
    """Workflow bearbeiten."""
    redis = get_redis()
    workflows = await _load_workflows(redis)
    idx = next((i for i, w in enumerate(workflows) if w["id"] == workflow_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")
    now = datetime.now(timezone.utc).isoformat()
    workflows[idx] = {**workflows[idx], **body.model_dump(), "id": workflow_id, "updated_at": now}
    await _save_workflows(redis, workflows)
    logger.info("Workflow aktualisiert: %s", workflow_id)
    return {"id": workflow_id, "status": "updated"}


@router.delete("/{workflow_id}")
async def delete_workflow(workflow_id: str) -> dict:
    """Workflow löschen."""
    redis = get_redis()
    workflows = await _load_workflows(redis)
    original_len = len(workflows)
    workflows = [w for w in workflows if w["id"] != workflow_id]
    if len(workflows) == original_len:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' nicht gefunden")
    await _save_workflows(redis, workflows)
    await redis.connection.delete(f"{REDIS_KEY_RUNS_PREFIX}{workflow_id}")
    # Veraltete Run-Index-Einträge für diesen Workflow bereinigen
    index_raw = await redis.connection.get(REDIS_KEY_RUN_INDEX)
    if index_raw:
        run_index = json.loads(index_raw)
        run_index = {k: v for k, v in run_index.items() if v != workflow_id}
        await redis.connection.set(REDIS_KEY_RUN_INDEX, json.dumps(run_index))
    logger.info("Workflow gelöscht: %s", workflow_id)
    return {"id": workflow_id, "deleted": True}


@router.post("/{workflow_id}/run", status_code=202)
async def run_workflow(workflow_id: str, request: Request) -> dict:
    """Workflow asynchron starten."""
    redis = get_redis()
    workflows = await _load_workflows(redis)
    wf = next((w for w in workflows if w["id"] == workflow_id), None)
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
    runs_raw = await redis.connection.get(f"{REDIS_KEY_RUNS_PREFIX}{workflow_id}")
    runs = json.loads(runs_raw) if runs_raw else []
    runs.append(run.model_dump())
    if len(runs) > MAX_RUNS_PER_WORKFLOW:
        runs = runs[-MAX_RUNS_PER_WORKFLOW:]
    await redis.connection.set(f"{REDIS_KEY_RUNS_PREFIX}{workflow_id}", json.dumps(runs))

    # Workflow asynchron in Background ausführen
    try:
        from core.workflow_engine import WorkflowEngine
        orchestrator = request.app.state.orchestrator
        engine = WorkflowEngine(redis, orchestrator)
        asyncio.create_task(engine.execute(wf, run_id))
    except Exception as exc:
        logger.warning("Workflow-Engine konnte nicht gestartet werden: %s", exc)

    return {"run_id": run_id, "status": "running"}



@router.get("/{workflow_id}/runs", response_model=WorkflowRunListResponse)
async def get_workflow_runs(workflow_id: str) -> WorkflowRunListResponse:
    """Run-Historie eines Workflows."""
    redis = get_redis()
    runs_raw = await redis.connection.get(f"{REDIS_KEY_RUNS_PREFIX}{workflow_id}")
    runs = json.loads(runs_raw) if runs_raw else []
    # Neueste zuerst
    runs = list(reversed(runs))
    return WorkflowRunListResponse(runs=[WorkflowRun(**r) for r in runs], total=len(runs))


@router.get("/runs/{run_id}")
async def get_run_status(run_id: str) -> dict:
    """Live-Status eines einzelnen Runs (Polling)."""
    redis = get_redis()
    # Suche in allen Workflow-Runs nach dem Run
    index_raw = await redis.connection.get(REDIS_KEY_RUN_INDEX)
    run_index = json.loads(index_raw) if index_raw else {}
    workflow_id = run_index.get(run_id)

    if workflow_id:
        runs_raw = await redis.connection.get(f"{REDIS_KEY_RUNS_PREFIX}{workflow_id}")
        runs = json.loads(runs_raw) if runs_raw else []
        run = next((r for r in runs if r["id"] == run_id), None)
        if run:
            return run

    raise HTTPException(status_code=404, detail=f"Run '{run_id}' nicht gefunden")
