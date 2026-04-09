from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.data_analysis_subagent import (
    get_subagent_for_session,
    list_active_subagents,
)
from core.redis_client import get_redis

logger = logging.getLogger("ninko.api.routes_subagent")
router = APIRouter()


class RetryStepRequest(BaseModel):
    session_id: str = Field(..., description="Session ID der Subagent-Ausführung")
    module: str = Field(..., description="Modul-Name (z.B. 'jira', 'glpi')")
    step_id: str = Field(..., description="ID des fehlgeschlagenen Steps")


class RetryStepResponse(BaseModel):
    status: str = Field(..., description="success oder error")
    result: dict | None = Field(None, description="Ergebnis bei success")
    error: str | None = Field(None, description="Fehlermeldung bei error")
    suggested_retry: bool = Field(False, description="Ob Retry empfohlen wird")


class AbortSubagentRequest(BaseModel):
    session_id: str = Field(..., description="Session ID der Subagent-Ausführung")
    module: str = Field(..., description="Modul-Name")


class AbortSubagentResponse(BaseModel):
    status: str = Field(..., description="success oder error")
    message: str = Field(..., description="Status-Nachricht")


class SubagentStatusResponse(BaseModel):
    active: list[dict] = Field(
        default_factory=list, description="Liste aktiver Subagents"
    )


class StepListResponse(BaseModel):
    steps: list[dict] = Field(default_factory=list, description="Liste aller Steps")


@router.post("/retry-step", response_model=RetryStepResponse)
async def retry_step(request: RetryStepRequest) -> RetryStepResponse:
    subagent = get_subagent_for_session(request.session_id, request.module)
    if not subagent:
        return RetryStepResponse(
            status="error",
            error="No active subagent found for this session and module",
            suggested_retry=False,
        )

    result = await subagent.retry_step(request.step_id)

    return RetryStepResponse(
        status=result.get("status", "error"),
        result=result.get("result"),
        error=result.get("error"),
        suggested_retry=result.get("suggested_retry", False),
    )


@router.post("/abort", response_model=AbortSubagentResponse)
async def abort_subagent(request: AbortSubagentRequest) -> AbortSubagentResponse:
    from agents.data_analysis_subagent import _cleanup_subagent

    _cleanup_subagent(request.session_id, request.module)

    return AbortSubagentResponse(
        status="success",
        message=f"Subagent for module '{request.module}' has been aborted",
    )


@router.get("/status", response_model=SubagentStatusResponse)
async def list_subagents() -> SubagentStatusResponse:
    active = list_active_subagents()

    result = [
        {"session_id": key.split(":")[0], "module": key.split(":")[1], "key": key}
        for key, module in active.items()
    ]

    return SubagentStatusResponse(active=result)


@router.get("/steps/{session_id}", response_model=StepListResponse)
async def get_subagent_steps(session_id: str) -> StepListResponse:
    try:
        redis = get_redis()
        key = f"ninko:subagent:steps:{session_id}"
        raw_steps = await redis.connection.lrange(key, 0, 99)

        steps = []
        for raw in raw_steps:
            try:
                import json

                step = json.loads(raw)
                steps.append(step)
            except Exception:
                continue

        return StepListResponse(steps=steps)
    except Exception as e:
        logger.warning("Fehler beim Laden der Subagent-Steps: %s", e)
        return StepListResponse(steps=[])
