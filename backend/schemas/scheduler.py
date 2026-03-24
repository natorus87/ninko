"""
Kumio Scheduler Schemas – Geplante Aufgaben (CronJobs).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ScheduledTaskCreate(BaseModel):
    """Request: Neue geplante Aufgabe erstellen."""

    name: str = Field(..., min_length=1, max_length=100, description="Name der Aufgabe")
    cron: str = Field(..., description="Cron-Ausdruck (z.B. '*/5 * * * *')")
    prompt: str = Field("", description="Natürlichsprachiger Auftrag an den Agenten")
    workflow_id: Optional[str] = Field(None, description="ID des auszuführenden Workflows")
    target_module: Optional[str] = Field(
        None, description="Optional: Zielmodul (z.B. 'kubernetes'). Leer = Orchestrator entscheidet."
    )
    enabled: bool = True


class ScheduledTaskUpdate(BaseModel):
    """Request: Aufgabe aktualisieren."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    cron: Optional[str] = None
    prompt: Optional[str] = None
    workflow_id: Optional[str] = None
    target_module: Optional[str] = None
    enabled: Optional[bool] = None


class ScheduledTaskInfo(BaseModel):
    """Response: Aufgaben-Details."""

    id: str
    name: str
    cron: str
    prompt: str = ""
    workflow_id: Optional[str] = None
    target_module: Optional[str] = None
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    last_result: Optional[str] = None  # "ok" | "error" | "pending"


class ScheduledTaskListResponse(BaseModel):
    """Response: Liste aller geplanten Aufgaben."""

    tasks: list[ScheduledTaskInfo]
    total: int


class TaskExecutionLog(BaseModel):
    """Response: Ein Ausführungs-Log-Eintrag."""

    task_id: str
    task_name: str
    timestamp: datetime
    status: str  # "ok" | "error"
    module_used: Optional[str] = None
    prompt: str
    response: str
    duration_ms: int = 0
