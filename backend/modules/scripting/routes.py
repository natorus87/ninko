"""
Scripting MVP Module – FastAPI Router.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from core.auth import auth_tenant_id, resolve_request_auth
from core.redis_client import get_redis
from modules.codelab.tools import execute_code
from modules.scripting.schemas import (
    Script,
    ScriptCreate,
    ScriptExecutionRequest,
    ScriptExecutionResult,
    ScriptExecutionHistory,
    ScriptListResponse,
    ScriptUpdate,
)

logger = logging.getLogger("ninko.modules.scripting.routes")
router = APIRouter(prefix="/api/scripting", tags=["Scripting"])

REDIS_SCRIPTS_KEY = "ninko:scripting:scripts"
REDIS_EXECUTIONS_KEY = "ninko:scripting:executions"


def _tenant_scripts_key(tenant_id: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    return f"{REDIS_SCRIPTS_KEY}:{t}"


def _tenant_executions_key(tenant_id: str) -> str:
    t = (tenant_id or "default").strip().lower().replace(" ", "_")
    return f"{REDIS_EXECUTIONS_KEY}:{t}"


async def _load_scripts(redis, tenant_id: str) -> list[dict]:
    raw = await redis.connection.get(_tenant_scripts_key(tenant_id))
    return json.loads(raw) if raw else []


async def _save_scripts(redis, tenant_id: str, scripts: list[dict]) -> None:
    await redis.connection.set(_tenant_scripts_key(tenant_id), json.dumps(scripts))


async def _load_executions(redis, tenant_id: str) -> list[dict]:
    raw = await redis.connection.get(_tenant_executions_key(tenant_id))
    return json.loads(raw) if raw else []


async def _save_executions(redis, tenant_id: str, executions: list[dict]) -> None:
    await redis.connection.set(
        _tenant_executions_key(tenant_id), json.dumps(executions)
    )


def _public_script(script: dict) -> dict:
    s = dict(script)
    s.pop("tenant_id", None)
    s.pop("code", None)
    return s


@router.get("/scripts", response_model=ScriptListResponse)
async def list_scripts(request: Request) -> ScriptListResponse:
    """Alle Scripts auflisten."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)
    public = [_public_script(s) for s in scripts]
    return ScriptListResponse(scripts=[Script(**s) for s in public], total=len(public))


@router.get("/scripts/{script_id}")
async def get_script(script_id: str, request: Request) -> dict:
    """Ein Script abrufen (inkl. Code)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)
    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        raise HTTPException(
            status_code=404, detail=f"Script '{script_id}' nicht gefunden"
        )
    return _public_script(script)


@router.get("/scripts/{script_id}/code")
async def get_script_code(script_id: str, request: Request) -> dict:
    """Nur den Code eines Scripts abrufen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)
    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        raise HTTPException(
            status_code=404, detail=f"Script '{script_id}' nicht gefunden"
        )
    return {"id": script_id, "code": script.get("code", "")}


@router.post("/scripts", status_code=201)
async def create_script(body: ScriptCreate, request: Request) -> dict:
    """Neues Script erstellen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)

    if any(s["name"] == body.name for s in scripts):
        raise HTTPException(
            status_code=409, detail=f"Script '{body.name}' existiert bereits"
        )

    now = datetime.now(timezone.utc).isoformat()
    script = {
        "id": str(uuid.uuid4()),
        "name": body.name,
        "description": body.description,
        "code": body.code,
        "language": body.language,
        "timeout": body.timeout,
        "tags": body.tags,
        "created_at": now,
        "updated_at": now,
        "created_by": "",
        "run_count": 0,
        "last_run_at": None,
        "last_run_status": "idle",
        "tenant_id": tenant_id,
    }
    scripts.append(script)
    await _save_scripts(redis, tenant_id, scripts)
    logger.info("Script erstellt: %s (%s)", script["name"], script["id"])
    return {"id": script["id"], "status": "created"}


@router.put("/scripts/{script_id}")
async def update_script(script_id: str, body: ScriptUpdate, request: Request) -> dict:
    """Script aktualisieren."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)

    idx = next((i for i, s in enumerate(scripts) if s["id"] == script_id), None)
    if idx is None:
        raise HTTPException(
            status_code=404, detail=f"Script '{script_id}' nicht gefunden"
        )

    now = datetime.now(timezone.utc).isoformat()
    updated = scripts[idx].copy()

    if body.name is not None:
        if any(s["name"] == body.name and s["id"] != script_id for s in scripts):
            raise HTTPException(
                status_code=409, detail=f"Script '{body.name}' existiert bereits"
            )
        updated["name"] = body.name
    if body.description is not None:
        updated["description"] = body.description
    if body.code is not None:
        updated["code"] = body.code
    if body.timeout is not None:
        updated["timeout"] = body.timeout
    if body.tags is not None:
        updated["tags"] = body.tags

    updated["updated_at"] = now
    scripts[idx] = updated
    await _save_scripts(redis, tenant_id, scripts)
    logger.info("Script aktualisiert: %s", script_id)
    return {"id": script_id, "status": "updated"}


@router.delete("/scripts/{script_id}")
async def delete_script(script_id: str, request: Request) -> dict:
    """Script löschen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)

    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        raise HTTPException(
            status_code=404, detail=f"Script '{script_id}' nicht gefunden"
        )

    scripts = [s for s in scripts if s["id"] != script_id]
    await _save_scripts(redis, tenant_id, scripts)
    logger.info("Script gelöscht: %s", script_id)
    return {"id": script_id, "deleted": True}


@router.post("/scripts/{script_id}/execute")
async def execute_script(
    script_id: str,
    body: ScriptExecutionRequest | None = None,
    request: Request | None = None,
) -> ScriptExecutionResult:
    """Script ausführen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request)) if request else "default"
    scripts = await _load_scripts(redis, tenant_id)

    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        raise HTTPException(
            status_code=404, detail=f"Script '{script_id}' nicht gefunden"
        )

    # Update script run status
    now = datetime.now(timezone.utc)
    script["last_run_at"] = now.isoformat()
    script["last_run_status"] = "running"
    script["run_count"] = script.get("run_count", 0) + 1
    await _save_scripts(redis, tenant_id, scripts)

    exec_id = str(uuid.uuid4())
    execution = {
        "id": exec_id,
        "script_id": script_id,
        "script_name": script["name"],
        "started_at": now.isoformat(),
        "finished_at": None,
        "status": "running",
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "duration_ms": 0.0,
        "executed_by": "",
        "triggered_by": "manual",
    }

    executions = await _load_executions(redis, tenant_id)
    executions.insert(0, execution)
    executions = executions[:100]
    await _save_executions(redis, tenant_id, executions)

    timeout = body.timeout if body else None
    if timeout is None:
        timeout = script.get("timeout", 30)

    try:
        result = await execute_code.ainvoke(
            {
                "code": script["code"],
                "language": script.get("language", "python"),
                "timeout": min(timeout, 300),
            }
        )

        finished_at = datetime.now(timezone.utc)
        duration_ms = result.get("duration_ms", 0.0)
        exit_code = result.get("exit_code", 0)
        status = "succeeded" if exit_code == 0 else "failed"

        execution["finished_at"] = finished_at.isoformat()
        execution["status"] = status
        execution["stdout"] = result.get("stdout", "")[:10000]
        execution["stderr"] = result.get("stderr", "")[:5000]
        execution["exit_code"] = exit_code
        execution["duration_ms"] = duration_ms

        script["last_run_status"] = status

    except Exception as e:
        logger.exception("Script execution failed")
        finished_at = datetime.now(timezone.utc)
        execution["finished_at"] = finished_at.isoformat()
        execution["status"] = "failed"
        execution["stderr"] = str(e)[:5000]
        execution["exit_code"] = -1
        script["last_run_status"] = "failed"

    await _save_executions(redis, tenant_id, executions)
    await _save_scripts(redis, tenant_id, scripts)

    return ScriptExecutionResult(**execution)


@router.get("/scripts/{script_id}/executions", response_model=ScriptExecutionHistory)
async def get_script_executions(
    script_id: str, request: Request, limit: int = 20
) -> ScriptExecutionHistory:
    """Ausführungshistorie eines Scripts abrufen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    executions = await _load_executions(redis, tenant_id)
    script_execs = [e for e in executions if e["script_id"] == script_id]
    script_execs = script_execs[:limit]

    return ScriptExecutionHistory(
        executions=[ScriptExecutionResult(**e) for e in script_execs],
        total=len(script_execs),
    )


@router.get("/executions", response_model=ScriptExecutionHistory)
async def list_all_executions(
    request: Request, limit: int = 50
) -> ScriptExecutionHistory:
    """Alle Ausführungen abrufen (tenant-scoped)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    executions = await _load_executions(redis, tenant_id)
    executions = executions[:limit]

    return ScriptExecutionHistory(
        executions=[ScriptExecutionResult(**e) for e in executions],
        total=len(executions),
    )
