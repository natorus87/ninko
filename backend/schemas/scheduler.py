"""
Ninko Scheduler Schemas – Geplante Aufgaben (CronJobs).
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
    agent_id: Optional[str] = Field(None, description="ID eines Dynamic Agent aus dem AgentPool")
    security_workflow_id: Optional[str] = Field(
        None, description="ID eines Security-Audit-Workflows (z.B. 'container_image_audit')"
    )
    security_target_id: Optional[str] = Field(
        None, description="ID des SecurityTarget für security_workflow_id (beide zusammen erforderlich)"
    )
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
    agent_id: Optional[str] = None
    security_workflow_id: Optional[str] = None
    security_target_id: Optional[str] = None
    target_module: Optional[str] = None
    enabled: Optional[bool] = None


class ScheduledTaskInfo(BaseModel):
    """Response: Aufgaben-Details."""

    id: str
    name: str
    cron: str
    prompt: str = ""
    workflow_id: Optional[str] = None
    agent_id: Optional[str] = None
    security_workflow_id: Optional[str] = None
    security_target_id: Optional[str] = None
    target_module: Optional[str] = None
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    last_result: Optional[str] = None  # "ok" | "error" | "pending"
    tenant_id: Optional[str] = None
    source: Optional[str] = None  # z.B. "workflow_trigger" für auto-synchronisierte Tasks


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


class ScheduledTaskDeleteResponse(BaseModel):
    """Response: Aufgabe erfolgreich gelöscht."""

    id: str
    deleted: bool


class ScheduledTaskRunResponse(BaseModel):
    """Response: Manueller Task-Run wurde im Hintergrund gestartet."""

    task_id: str
    status: str  # "started" | "already_running"
