"""
Ninko Scheduler API – CRUD für geplante Aufgaben.
"""

from __future__ import annotations

import logging

from croniter import croniter
from fastapi import APIRouter, HTTPException, Request

from schemas.scheduler import (
    ScheduledTaskCreate,
    ScheduledTaskDeleteResponse,
    ScheduledTaskInfo,
    ScheduledTaskListResponse,
    ScheduledTaskUpdate,
    TaskExecutionLog,
)

logger = logging.getLogger("ninko.api.scheduler")
router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])


def _get_scheduler(request: Request) -> object:
    """Holt den SchedulerAgent aus dem App-State."""
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        raise HTTPException(
            status_code=503,
            detail="Scheduler-Agent nicht verfügbar.",
        )
    return scheduler


# ── Tasks CRUD ─────────────────────────────────────


@router.get("/tasks", response_model=ScheduledTaskListResponse)
async def list_tasks(request: Request) -> ScheduledTaskListResponse:
    """Alle geplanten Aufgaben auflisten."""
    scheduler = _get_scheduler(request)
    tasks = await scheduler.get_all_tasks()
    return ScheduledTaskListResponse(
        tasks=[ScheduledTaskInfo(**t) for t in tasks],
        total=len(tasks),
    )


def _validate_cron(cron_expr: str | None) -> None:
    """Validiert einen Cron-Ausdruck. Raises HTTPException bei ungültigem Format."""
    if cron_expr is None:
        return
    if not croniter.is_valid(cron_expr):
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Cron-Ausdruck: '{cron_expr}'. Beispiel: '*/5 * * * *'",
        )


@router.post("/tasks", status_code=201, response_model=ScheduledTaskInfo)
async def create_task(request: Request, body: ScheduledTaskCreate) -> ScheduledTaskInfo:
    """Neue geplante Aufgabe erstellen."""
    _validate_cron(body.cron)
    scheduler = _get_scheduler(request)

    try:
        task = await scheduler.create_task(body.model_dump())
        return ScheduledTaskInfo(**task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.put("/tasks/{task_id}", response_model=ScheduledTaskInfo)
async def update_task(
    request: Request, task_id: str, body: ScheduledTaskUpdate
) -> ScheduledTaskInfo:
    """Geplante Aufgabe aktualisieren."""
    _validate_cron(body.cron)
    scheduler = _get_scheduler(request)

    try:
        task = await scheduler.update_task(task_id, body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not task:
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden.")
    return ScheduledTaskInfo(**task)


@router.delete("/tasks/{task_id}", response_model=ScheduledTaskDeleteResponse)
async def delete_task(request: Request, task_id: str) -> ScheduledTaskDeleteResponse:
    """Geplante Aufgabe löschen."""
    scheduler = _get_scheduler(request)
    deleted = await scheduler.delete_task(task_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden.")
    return ScheduledTaskDeleteResponse(id=task_id, deleted=True)


@router.put("/tasks/{task_id}/toggle", response_model=ScheduledTaskInfo)
async def toggle_task(request: Request, task_id: str) -> ScheduledTaskInfo:
    """Aufgabe aktivieren/deaktivieren."""
    scheduler = _get_scheduler(request)
    task = await scheduler.toggle_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden.")
    return ScheduledTaskInfo(**task)


@router.post("/tasks/{task_id}/run")
async def run_task(request: Request, task_id: str) -> dict:
    """Aufgabe sofort manuell ausführen."""
    scheduler = _get_scheduler(request)
    result = await scheduler.run_task_now(task_id)

    if result is None:
        raise HTTPException(status_code=404, detail="Aufgabe nicht gefunden.")

    return {
        "task_id": task_id,
        "status": result.get("status", "unknown"),
        "response_preview": result.get("response", "")[:300],
        "duration_ms": result.get("duration_ms", 0),
        "module_used": result.get("module_used"),
    }


@router.get("/tasks/{task_id}/logs", response_model=list[TaskExecutionLog])
async def get_task_logs(
    request: Request, task_id: str, limit: int = 20
) -> list[TaskExecutionLog]:
    """Ausführungs-Logs einer Aufgabe abrufen."""
    scheduler = _get_scheduler(request)
    logs = await scheduler.get_task_logs(task_id, limit=min(limit, 50))
    return [TaskExecutionLog(**entry) for entry in logs]
