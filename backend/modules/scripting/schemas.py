"""
Scripting MVP Module – Pydantic Schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ScriptCreate(BaseModel):
    """Schema für das Erstellen eines neuen Scripts."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    code: str = Field(..., min_length=1, max_length=50000)
    language: Literal["python", "bash"] = "python"
    timeout: int = Field(default=30, ge=1, le=300)
    tags: list[str] = Field(default_factory=list)


class ScriptUpdate(BaseModel):
    """Schema für das Aktualisieren eines Scripts."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    code: str | None = Field(default=None, min_length=1, max_length=50000)
    language: Literal["python", "bash"] | None = None
    timeout: int | None = Field(default=None, ge=1, le=300)
    tags: list[str] | None = None


class Script(BaseModel):
    """Vollständiges Script-Schema."""

    id: str
    name: str
    description: str = ""
    code: str
    language: str = "python"
    timeout: int = 30
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    created_by: str = ""
    run_count: int = 0
    last_run_at: datetime | None = None
    last_run_status: Literal["idle", "running", "succeeded", "failed"] = "idle"


class ScriptSummary(BaseModel):
    """Öffentliche Script-Zusammenfassung ohne Quellcode."""

    id: str
    name: str
    description: str = ""
    language: str = "python"
    timeout: int = 30
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    created_by: str = ""
    run_count: int = 0
    last_run_at: datetime | None = None
    last_run_status: Literal["idle", "running", "succeeded", "failed"] = "idle"


class ScriptListResponse(BaseModel):
    """Response für Script-Listen."""

    scripts: list[ScriptSummary]
    total: int


class ScriptExecutionRequest(BaseModel):
    """Schema für Script-Ausführung."""

    timeout: int | None = Field(default=None, ge=1, le=300)
    environment_vars: dict[str, str] = Field(default_factory=dict)


class ScriptExecutionResult(BaseModel):
    """Schema für Script-Ausführungsergebnis."""

    id: str
    script_id: str
    script_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["running", "succeeded", "failed", "timeout", "cancelled"]
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: float = 0.0
    executed_by: str = ""
    triggered_by: Literal["manual", "api", "workflow", "scheduler"] = "manual"


class ScriptExecutionHistory(BaseModel):
    """Response für Script-Ausführungshistorie."""

    executions: list[ScriptExecutionResult]
    total: int
