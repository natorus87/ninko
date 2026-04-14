"""Pydantic schemas for deterministic task pre-structuring.

This module defines the data models for the TaskSketch builder,
which transforms user messages into structured, deterministic
descriptions before planner execution.
"""

from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Type aliases for clarity
Intent = Literal[
    "answer",
    "investigate",
    "act",
    "plan",
    "workflow",
    "compare",
    "summarize",
    "unknown",
]
Complexity = Literal["simple", "multi_step", "compound", "unknown"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ExecutionMode = Literal["read_only", "guarded_write", "planner_decides"]
WorkerType = Literal["direct_answer", "explorer", "operator", "planner", "workflow"]
Domain = Literal[
    "infra",
    "kubernetes",
    "gitlab",
    "monitoring",
    "network",
    "database",
    "files",
    "general",
    "unknown",
]


class SourceInfo(BaseModel):
    """Information about the source of the request."""

    user_message: str
    conversation_turn_id: Optional[str] = None
    session_id: Optional[str] = None


class RankedModule(BaseModel):
    """A module candidate with ranking score and reasoning."""

    module: str
    score: float = Field(ge=0.0, le=1.0)
    reasons: List[str] = Field(default_factory=list)


class TaskInfo(BaseModel):
    """Core task classification and requirements."""

    intent: Intent
    primary_goal: str
    secondary_goals: List[str] = Field(default_factory=list)
    requested_output: List[str] = Field(default_factory=list)
    complexity: Complexity
    needs_tools: bool
    needs_fresh_state: bool
    needs_evidence: bool
    user_explicit_action_request: bool = False

    @field_validator("requested_output")
    @classmethod
    def validate_output_types(cls, v: List[str]) -> List[str]:
        allowed = {
            "answer",
            "diagnosis",
            "next_step",
            "plan",
            "execution",
            "comparison",
            "summary",
            "report",
        }
        return [item for item in v if item in allowed]


class RiskInfo(BaseModel):
    """Risk assessment for the task."""

    level: RiskLevel
    destructive_potential: bool = False
    write_intent_detected: bool = False
    external_side_effects_possible: bool = False
    approval_required: bool = False
    reason_codes: List[str] = Field(default_factory=list)


class ScopeEntities(BaseModel):
    """Extracted entities from the user message."""

    systems: List[str] = Field(default_factory=list)
    services: List[str] = Field(default_factory=list)
    hosts: List[str] = Field(default_factory=list)
    namespaces: List[str] = Field(default_factory=list)
    clusters: List[str] = Field(default_factory=list)
    resources: List[str] = Field(default_factory=list)
    time_refs: List[str] = Field(default_factory=list)


class ScopeInfo(BaseModel):
    """Scope and domain classification."""

    domain: Domain = "unknown"
    candidate_modules: List[str] = Field(default_factory=list)
    candidate_modules_ranked: List[RankedModule] = Field(default_factory=list)
    multi_module: bool = False
    entities: ScopeEntities = Field(default_factory=ScopeEntities)


class ConstraintInfo(BaseModel):
    """Execution constraints and requirements."""

    execution_mode: ExecutionMode = "planner_decides"
    time_sensitivity: Literal["normal", "urgent", "unknown"] = "normal"
    response_style: Literal["concise", "normal", "detailed", "unknown"] = "normal"
    must_not_do: List[str] = Field(default_factory=list)
    must_include: List[str] = Field(default_factory=list)
    user_constraints: List[str] = Field(default_factory=list)


class RoutingHints(BaseModel):
    """Hints for the orchestrator routing decision."""

    preferred_worker_type: WorkerType = "planner"
    should_delegate: bool = True
    should_avoid_direct_answer: bool = False
    should_collect_state_before_answer: bool = False


class UncertaintyInfo(BaseModel):
    """Explicit uncertainty markers."""

    ambiguous: bool = False
    missing_information: List[str] = Field(default_factory=list)
    open_questions: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class DebugInfo(BaseModel):
    """Debug information for traceability."""

    matched_rules: List[str] = Field(default_factory=list)
    tokens: Dict[str, List[str]] = Field(default_factory=dict)


class TaskSketch(BaseModel):
    """
    Complete task sketch produced by the deterministic pre-structurer.

    This is the primary output format that feeds into the planner,
    providing a structured, deterministic interpretation of the user's request.
    """

    version: str = "1.0"
    source: SourceInfo
    task: TaskInfo
    risk: RiskInfo
    scope: ScopeInfo
    constraints: ConstraintInfo
    routing_hints: RoutingHints
    uncertainty: UncertaintyInfo
    debug: DebugInfo

    def model_dump_json_safe(self) -> dict:
        """Return a JSON-serializable dict with all nested models converted."""
        return self.model_dump(mode="json")


class ModuleMetadata(BaseModel):
    """
    Lightweight metadata for a module, used by the pre-structurer.

    This is a deterministic, rule-friendly subset of ModuleManifest
    that enables fast keyword/entity matching without LLM interpretation.
    """

    name: str
    keywords: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    domain: str = "general"
    read_only_capabilities: List[str] = Field(default_factory=list)
    write_capabilities: List[str] = Field(default_factory=list)

    @classmethod
    def from_manifest(cls, manifest: dict) -> "ModuleMetadata":
        """Create ModuleMetadata from a ModuleManifest dict."""
        return cls(
            name=manifest.get("name", ""),
            keywords=manifest.get("routing_keywords", []),
            entities=manifest.get("entities", []),
            domain=manifest.get("domain", "general"),
            read_only_capabilities=manifest.get("read_only_capabilities", []),
            write_capabilities=manifest.get("write_capabilities", []),
        )


class TaskSketchBuildResult(BaseModel):
    """Result wrapper including timing and validation info."""

    sketch: TaskSketch
    build_time_ms: float
    valid: bool
    validation_errors: List[str] = Field(default_factory=list)
