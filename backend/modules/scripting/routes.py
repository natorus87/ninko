"""
Scripting MVP Module – FastAPI Router.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from core.auth import auth_tenant_id, resolve_request_auth
from core.redis_client import get_redis
from modules.codelab.tools import execute_code
from modules.scripting.schemas import (
    ScriptCreate,
    ScriptExecutionRequest,
    ScriptExecutionResult,
    ScriptExecutionHistory,
    ScriptListResponse,
    ScriptSummary,
    ScriptUpdate,
    ScriptToolInvocation,
    ScriptToolInvocationHistory,
)

logger = logging.getLogger("ninko.modules.scripting.routes")
router = APIRouter()

REDIS_SCRIPTS_KEY = "ninko:scripting:scripts"
REDIS_EXECUTIONS_KEY = "ninko:scripting:executions"
REDIS_TOOL_INVOCATIONS_KEY = "ninko:scripting:tool_invocations"

_TOOL_NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")


def _validate_tool_name(name: str | None) -> None:
    """Validiert den Tool-Namen (slug-Format)."""
    if name is None:
        return
    if not name:
        raise HTTPException(status_code=400, detail="Tool-Name darf nicht leer sein")
    if len(name) > 50:
        raise HTTPException(status_code=400, detail="Tool-Name darf maximal 50 Zeichen haben")
    if not _TOOL_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail="Tool-Name darf nur Kleinbuchstaben, Zahlen, Unterstriche und Bindestriche enthalten",
        )


def _is_tool_name_unique(
    scripts: list[dict], tool_name: str, exclude_script_id: str | None = None
) -> bool:
    """Prüft ob der Tool-Name im Tenant eindeutig ist."""
    for script in scripts:
        if script.get("tool_name") == tool_name:
            if exclude_script_id and script["id"] == exclude_script_id:
                continue
            return False
    return True


def _normalize_tenant_id(tenant_id: str) -> str:
    return (tenant_id or "default").strip().lower().replace(" ", "_") or "default"


def _tenant_scripts_key(tenant_id: str) -> str:
    return f"{REDIS_SCRIPTS_KEY}:{_normalize_tenant_id(tenant_id)}"


def _tenant_executions_key(tenant_id: str) -> str:
    return f"{REDIS_EXECUTIONS_KEY}:{_normalize_tenant_id(tenant_id)}"


async def _load_scripts(redis, tenant_id: str) -> list[dict]:
    scoped_key = _tenant_scripts_key(tenant_id)
    raw = await redis.connection.get(scoped_key)
    if raw:
        return json.loads(raw)

    # Backward compatibility: ältere Daten lagen im globalen Key ohne Tenant-Suffix.
    if _normalize_tenant_id(tenant_id) == "default":
        legacy_raw = await redis.connection.get(REDIS_SCRIPTS_KEY)
        if legacy_raw:
            scripts = json.loads(legacy_raw)
            await redis.connection.set(scoped_key, json.dumps(scripts))
            logger.info(
                "Legacy scripts nach tenant-scoped key migriert: tenant=%s count=%d",
                tenant_id or "default",
                len(scripts),
            )
            return scripts
    return []


async def _save_scripts(redis, tenant_id: str, scripts: list[dict]) -> None:
    await redis.connection.set(_tenant_scripts_key(tenant_id), json.dumps(scripts))


async def _load_executions(redis, tenant_id: str) -> list[dict]:
    scoped_key = _tenant_executions_key(tenant_id)
    raw = await redis.connection.get(scoped_key)
    if raw:
        return json.loads(raw)

    # Backward compatibility: ältere Daten lagen im globalen Key ohne Tenant-Suffix.
    if _normalize_tenant_id(tenant_id) == "default":
        legacy_raw = await redis.connection.get(REDIS_EXECUTIONS_KEY)
        if legacy_raw:
            executions = json.loads(legacy_raw)
            await redis.connection.set(scoped_key, json.dumps(executions))
            logger.info(
                "Legacy executions nach tenant-scoped key migriert: tenant=%s count=%d",
                tenant_id or "default",
                len(executions),
            )
            return executions
    return []


async def _save_executions(redis, tenant_id: str, executions: list[dict]) -> None:
    await redis.connection.set(_tenant_executions_key(tenant_id), json.dumps(executions))


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
    return ScriptListResponse(
        scripts=[ScriptSummary(**s) for s in public],
        total=len(public),
    )


@router.get("/scripts/{script_id}", response_model=ScriptSummary)
async def get_script(script_id: str, request: Request) -> ScriptSummary:
    """Ein Script abrufen (ohne Code)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)
    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' nicht gefunden")
    return ScriptSummary(**_public_script(script))


@router.get("/scripts/{script_id}/code")
async def get_script_code(script_id: str, request: Request) -> dict:
    """Nur den Code eines Scripts abrufen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)
    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' nicht gefunden")
    return {"id": script_id, "code": script.get("code", "")}


@router.post("/scripts", status_code=201)
async def create_script(body: ScriptCreate, request: Request) -> dict:
    """Neues Script erstellen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)

    if any(s["name"] == body.name for s in scripts):
        raise HTTPException(status_code=409, detail=f"Script '{body.name}' existiert bereits")

    if body.tool_enabled:
        _validate_tool_name(body.tool_name)
        if not body.tool_name:
            raise HTTPException(
                status_code=400,
                detail="Tool-Name ist erforderlich wenn 'Als Tool verfügbar' aktiviert ist",
            )
        if not _is_tool_name_unique(scripts, body.tool_name):
            raise HTTPException(
                status_code=409,
                detail=f"Tool-Name '{body.tool_name}' wird bereits von einem anderen Script verwendet",
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
        "tool_enabled": body.tool_enabled,
        "tool_name": body.tool_name if body.tool_enabled else None,
        "tool_description": body.tool_description if body.tool_enabled else None,
        "tool_input_schema": body.tool_input_schema if body.tool_enabled else None,
    }
    scripts.append(script)
    await _save_scripts(redis, tenant_id, scripts)

    if script["tool_enabled"]:
        from agents.script_tools import invalidate_script_tool_cache

        invalidate_script_tool_cache(tenant_id)

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
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' nicht gefunden")

    now = datetime.now(timezone.utc).isoformat()
    updated = scripts[idx].copy()

    if body.name is not None:
        if any(s["name"] == body.name and s["id"] != script_id for s in scripts):
            raise HTTPException(status_code=409, detail=f"Script '{body.name}' existiert bereits")
        updated["name"] = body.name
    if body.description is not None:
        updated["description"] = body.description
    if body.code is not None:
        updated["code"] = body.code
    if body.language is not None:
        updated["language"] = body.language
    if body.timeout is not None:
        updated["timeout"] = body.timeout
    if body.tags is not None:
        updated["tags"] = body.tags

    if body.tool_enabled is not None:
        updated["tool_enabled"] = body.tool_enabled
        if not body.tool_enabled:
            updated["tool_name"] = None
            updated["tool_description"] = None
            updated["tool_input_schema"] = None

    if body.tool_name is not None and updated.get("tool_enabled"):
        _validate_tool_name(body.tool_name)
        if not _is_tool_name_unique(scripts, body.tool_name, script_id):
            raise HTTPException(
                status_code=409,
                detail=f"Tool-Name '{body.tool_name}' wird bereits von einem anderen Script verwendet",
            )
        updated["tool_name"] = body.tool_name

    if body.tool_description is not None and updated.get("tool_enabled"):
        updated["tool_description"] = body.tool_description

    if body.tool_input_schema is not None and updated.get("tool_enabled"):
        updated["tool_input_schema"] = body.tool_input_schema

    if updated.get("tool_enabled") and not updated.get("tool_name"):
        raise HTTPException(
            status_code=400,
            detail="Tool-Name ist erforderlich wenn 'Als Tool verfügbar' aktiviert ist",
        )

    updated["updated_at"] = now
    scripts[idx] = updated
    await _save_scripts(redis, tenant_id, scripts)

    from agents.script_tools import invalidate_script_tool_cache

    invalidate_script_tool_cache(tenant_id)

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
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' nicht gefunden")

    scripts = [s for s in scripts if s["id"] != script_id]
    await _save_scripts(redis, tenant_id, scripts)

    from agents.script_tools import invalidate_script_tool_cache

    invalidate_script_tool_cache(tenant_id)

    logger.info("Script gelöscht: %s", script_id)
    return {"id": script_id, "deleted": True}


@router.post("/scripts/{script_id}/execute")
async def execute_script(
    script_id: str,
    request: Request,
    body: ScriptExecutionRequest | None = None,
) -> ScriptExecutionResult:
    """Script ausführen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)

    script = next((s for s in scripts if s["id"] == script_id), None)
    if not script:
        raise HTTPException(status_code=404, detail=f"Script '{script_id}' nicht gefunden")

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
async def list_all_executions(request: Request, limit: int = 50) -> ScriptExecutionHistory:
    """Alle Ausführungen abrufen (tenant-scoped)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    executions = await _load_executions(redis, tenant_id)
    executions = executions[:limit]

    return ScriptExecutionHistory(
        executions=[ScriptExecutionResult(**e) for e in executions],
        total=len(executions),
    )


# ── Tool-Registry Endpoints ────────────────────────────────────────────────


@router.get("/tools", response_model=list[ScriptSummary])
async def list_tool_scripts(request: Request) -> list[ScriptSummary]:
    """Alle als Tool aktivierten Scripts auflisten."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)
    tool_scripts = [s for s in scripts if s.get("tool_enabled")]
    return [ScriptSummary(**_public_script(s)) for s in tool_scripts]


@router.get("/tools/{tool_name}", response_model=ScriptSummary)
async def get_tool_by_name(tool_name: str, request: Request) -> ScriptSummary:
    """Ein Script als Tool anhand seines Tool-Namens abrufen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)
    script = next(
        (s for s in scripts if s.get("tool_enabled") and s.get("tool_name") == tool_name), None
    )
    if not script:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' nicht gefunden")
    return ScriptSummary(**_public_script(script))


@router.post("/tools/{tool_name}/execute", response_model=ScriptExecutionResult)
async def execute_tool(
    tool_name: str,
    request: Request,
    input_data: dict | None = None,
) -> ScriptExecutionResult:
    """Ein als Tool aktiviertes Script ausführen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    scripts = await _load_scripts(redis, tenant_id)

    script = next(
        (s for s in scripts if s.get("tool_enabled") and s.get("tool_name") == tool_name), None
    )
    if not script:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' nicht gefunden")

    script_id = script["id"]
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
        "tool_name": tool_name,
        "tenant_id": tenant_id,
        "input_data": input_data or {},
        "started_at": now.isoformat(),
        "finished_at": None,
        "status": "running",
        "stdout": "",
        "stderr": "",
        "exit_code": None,
        "duration_ms": 0.0,
        "invoked_by": "",
        "invocation_source": "api",
    }

    invocations = await _load_invocations(redis, tenant_id)
    invocations.insert(0, execution)
    invocations = invocations[:100]

    timeout = script.get("timeout", 30)

    try:
        code_with_input = script["code"]
        if input_data:
            input_json = json.dumps(input_data, ensure_ascii=False)
            code_with_input = f"import json\n_ninko_tool_input = json.loads({repr(input_json)})\n\n{code_with_input}"

        result = await execute_code.ainvoke(
            {
                "code": code_with_input,
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

    except asyncio.TimeoutError:
        finished_at = datetime.now(timezone.utc)
        execution["finished_at"] = finished_at.isoformat()
        execution["status"] = "timeout"
        execution["stderr"] = "Execution timeout"
        execution["exit_code"] = -1
        script["last_run_status"] = "failed"
    except Exception as e:
        logger.exception("Tool execution failed")
        finished_at = datetime.now(timezone.utc)
        execution["finished_at"] = finished_at.isoformat()
        execution["status"] = "failed"
        execution["stderr"] = str(e)[:5000]
        execution["exit_code"] = -1
        script["last_run_status"] = "failed"

    await _save_invocations(redis, tenant_id, invocations)
    await _save_scripts(redis, tenant_id, scripts)

    return ScriptExecutionResult(
        id=execution["id"],
        script_id=script_id,
        script_name=script["name"],
        started_at=now,
        finished_at=datetime.fromisoformat(execution["finished_at"])
        if execution["finished_at"]
        else None,
        status=execution["status"],
        stdout=execution["stdout"],
        stderr=execution["stderr"],
        exit_code=execution["exit_code"],
        duration_ms=execution["duration_ms"],
        executed_by=execution["invoked_by"],
        triggered_by="api",
    )


@router.get("/tools/{tool_name}/invocations", response_model=ScriptToolInvocationHistory)
async def get_tool_invocations(
    tool_name: str, request: Request, limit: int = 20
) -> ScriptToolInvocationHistory:
    """Aufruf-Historie eines Tools abrufen."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    invocations = await _load_invocations(redis, tenant_id)
    tool_invocations = [i for i in invocations if i.get("tool_name") == tool_name]
    tool_invocations = tool_invocations[:limit]

    return ScriptToolInvocationHistory(
        invocations=[ScriptToolInvocation(**i) for i in tool_invocations],
        total=len(tool_invocations),
    )


@router.get("/invocations", response_model=ScriptToolInvocationHistory)
async def list_all_invocations(request: Request, limit: int = 50) -> ScriptToolInvocationHistory:
    """Alle Tool-Aufrufe abrufen (tenant-scoped)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    invocations = await _load_invocations(redis, tenant_id)
    invocations = invocations[:limit]

    return ScriptToolInvocationHistory(
        invocations=[ScriptToolInvocation(**i) for i in invocations],
        total=len(invocations),
    )


async def _load_invocations(redis, tenant_id: str) -> list[dict]:
    """Lädt Tool-Invocations aus Redis (tenant-scoped)."""
    scoped_key = f"{REDIS_TOOL_INVOCATIONS_KEY}:{_normalize_tenant_id(tenant_id)}"
    raw = await redis.connection.get(scoped_key)
    if raw:
        return json.loads(raw)
    return []


async def _save_invocations(redis, tenant_id: str, invocations: list[dict]) -> None:
    """Speichert Tool-Invocations in Redis (tenant-scoped)."""
    scoped_key = f"{REDIS_TOOL_INVOCATIONS_KEY}:{_normalize_tenant_id(tenant_id)}"
    await redis.connection.set(scoped_key, json.dumps(invocations))
