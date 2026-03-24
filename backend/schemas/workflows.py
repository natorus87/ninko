"""
Kumio – Pydantic-Modelle für Workflow-Definitionen und Runs.
"""

from __future__ import annotations

from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
import uuid


# ── Workflow Node ────────────────────────────────────

class NodePosition(BaseModel):
    x: float = 0.0
    y: float = 0.0


class WorkflowNode(BaseModel):
    """Ein Node im Workflow-DAG."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: Literal["trigger", "agent", "condition", "loop", "variable", "end"] = "agent"
    label: str = ""
    config: dict = Field(default_factory=dict)
    # config examples:
    #   trigger:   {"mode": "manual" | "cron", "cron": "0 8 * * *", "webhook": false}
    #   agent:     {"agent_id": "...", "input_variable": "input"}
    #   condition: {"expression": "output.contains('error')", "true_label": "Fehler", "false_label": "OK"}
    #   loop:      {"mode": "foreach" | "while", "variable": "items", "condition": "i < 10"}
    #   variable:  {"name": "myVar", "value": "static_or_{template}"}
    #   end:       {"status": "succeeded" | "failed"}
    position: NodePosition = Field(default_factory=NodePosition)


# ── Workflow Edge ────────────────────────────────────

class WorkflowEdge(BaseModel):
    """Gerichtete Verbindung zwischen zwei Nodes."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    source_id: str
    target_id: str
    label: str = ""   # z.B. "true" / "false"


# ── Workflow Definition ──────────────────────────────

class WorkflowVariable(BaseModel):
    name: str
    value: str = ""


class WorkflowDefinition(BaseModel):
    """Vollständige Workflow-Definition (DAG)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    variables: list[WorkflowVariable] = Field(default_factory=list)
    enabled: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkflowCreate(BaseModel):
    """Payload zum Erstellen/Aktualisieren eines Workflows."""
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    nodes: list[WorkflowNode] = Field(default_factory=list)
    edges: list[WorkflowEdge] = Field(default_factory=list)
    variables: list[WorkflowVariable] = Field(default_factory=list)
    enabled: bool = True


# ── Workflow Run ─────────────────────────────────────

class WorkflowRunStep(BaseModel):
    """Ergebnis eines einzelnen Steps in einem Run."""
    node_id: str
    node_type: str
    node_label: str = ""
    status: Literal["pending", "running", "succeeded", "failed", "skipped"] = "pending"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    output: Optional[str] = None
    error: Optional[str] = None


class WorkflowRun(BaseModel):
    """Ein Workflow-Ausführungsprotokoll."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    workflow_name: str = ""
    status: Literal["idle", "running", "succeeded", "failed"] = "idle"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    steps: list[WorkflowRunStep] = Field(default_factory=list)
    variables: dict = Field(default_factory=dict)
    error: Optional[str] = None
    triggered_by: str = "manual"


class WorkflowListResponse(BaseModel):
    workflows: list[WorkflowDefinition] = Field(default_factory=list)
    total: int = 0


class WorkflowRunListResponse(BaseModel):
    runs: list[WorkflowRun] = Field(default_factory=list)
    total: int = 0
