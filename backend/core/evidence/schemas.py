"""Pydantic schemas for Ninko's evidence layer."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

ConfidenceLevel = Literal["high", "uncertain", "unresolved"]


class FieldResolution(BaseModel):
    """Resolution of one user/domain term to a module field or canonical concept."""

    term: str
    resolved_to: str
    source_module: str
    confidence: ConfidenceLevel
    reason: str
    score: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("term", "reason")
    @classmethod
    def required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value must not be empty")
        return value


class SemanticResolutionResult(BaseModel):
    """Semantic resolver output passed from TaskSketch to the planner."""

    query: str
    candidate_modules: list[str] = Field(default_factory=list)
    resolutions: list[FieldResolution] = Field(default_factory=list)
    unresolved_terms: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    escalation_required: bool = False
    escalation_reason: str | None = None

    @property
    def has_uncertainty(self) -> bool:
        return self.escalation_required or any(
            resolution.confidence != "high" for resolution in self.resolutions
        )


class EvidenceFact(BaseModel):
    """A structured fact extracted from executor output."""

    source_module: str
    field: str
    value: Any
    description: str = ""


class ConstellationResult(BaseModel):
    """Validation result for collected executor evidence."""

    conclusion: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_fields: list[FieldResolution] = Field(default_factory=list)
    applied_rules: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    trace: list[str] = Field(default_factory=list)


class EvidenceTrace(BaseModel):
    """Audit trace passed to synthesis."""

    session_id: str
    turn_id: str
    resolutions: list[FieldResolution] = Field(default_factory=list)
    constellation: ConstellationResult
    ready_for_synthesis: bool
    escalation_reason: str | None = None

    def to_markdown(self) -> str:
        """Render a compact audit trace for the synthesizer/chat output."""
        lines = [
            "### Evidence Trace",
            f"- Ready for synthesis: {str(self.ready_for_synthesis).lower()}",
            f"- Conclusion: {self.constellation.conclusion}",
            f"- Confidence: {self.constellation.confidence:.2f}",
        ]
        if self.escalation_reason:
            lines.append(f"- Escalation: {self.escalation_reason}")
        if self.resolutions:
            lines.append("- Resolutions:")
            for resolution in self.resolutions:
                lines.append(
                    "  - "
                    f"{resolution.term} -> {resolution.resolved_to} "
                    f"({resolution.source_module}, {resolution.confidence}, {resolution.score:.2f})"
                )
        if self.constellation.applied_rules:
            lines.append("- Applied rules: " + ", ".join(self.constellation.applied_rules))
        if self.constellation.contradictions:
            lines.append("- Contradictions: " + "; ".join(self.constellation.contradictions))
        if self.constellation.trace:
            lines.append("- Trace:")
            for item in self.constellation.trace:
                lines.append(f"  - {item}")
        return "\n".join(lines)
