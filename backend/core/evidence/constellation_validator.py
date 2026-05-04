"""Rule-based evidence constellation validation."""

from __future__ import annotations

from typing import Any

from core.evidence.schemas import ConstellationResult, EvidenceFact, FieldResolution

BLOCKED_VALUES = {"blocked", "blockiert", "failed", "failure", "error", "störung", "stoerung"}
OK_VALUES = {"ok", "open", "running", "healthy", "success", "resolved", "geschlossen"}


class ConstellationValidator:
    """Validate structured executor evidence before synthesis."""

    def validate(
        self,
        evidence: list[EvidenceFact | dict[str, Any]],
        resolutions: list[FieldResolution] | None = None,
    ) -> ConstellationResult:
        """Evaluate a data constellation and return an auditable conclusion."""
        facts = [
            fact if isinstance(fact, EvidenceFact) else EvidenceFact.model_validate(fact)
            for fact in evidence
        ]
        resolutions = resolutions or []
        trace: list[str] = []
        applied_rules: list[str] = []
        contradictions: list[str] = []

        blocked_facts = []
        ok_facts = []
        numeric_checks: list[tuple[EvidenceFact, bool]] = []

        for fact in facts:
            value_text = str(fact.value).casefold()
            trace.append(f"{fact.source_module}.{fact.field}={fact.value!r}")
            if fact.field.casefold() in {"status", "state", "phase"}:
                applied_rules.append("status_blocked_classification")
                if value_text in BLOCKED_VALUES:
                    blocked_facts.append(fact)
                elif value_text in OK_VALUES:
                    ok_facts.append(fact)
            elif fact.field.casefold() in {"blocked", "is_blocked", "locked"}:
                applied_rules.append("boolean_blocked_classification")
                if bool(fact.value):
                    blocked_facts.append(fact)
                else:
                    ok_facts.append(fact)
            elif isinstance(fact.value, (int, float)) and fact.field.casefold() in {
                "open_errors",
                "failed_jobs",
                "pending_invoices",
            }:
                applied_rules.append("numeric_positive_problem_signal")
                numeric_checks.append((fact, fact.value > 0))

        if blocked_facts and ok_facts:
            contradictions.append(
                "Evidence contains both blocked/error and ok/running status values."
            )
        for fact, indicates_problem in numeric_checks:
            if indicates_problem and ok_facts:
                contradictions.append(
                    f"{fact.source_module}.{fact.field} indicates a problem while "
                    "status evidence is ok."
                )

        problem_numeric_facts = [
            fact for fact, is_problem in numeric_checks if is_problem
        ]
        support = [
            FieldResolution(
                term=fact.field,
                resolved_to=fact.field,
                source_module=fact.source_module,
                confidence="high",
                score=1.0,
                reason="Executor evidence field used by constellation rule",
            )
            for fact in [*blocked_facts, *problem_numeric_facts]
        ]

        if contradictions:
            conclusion = "Evidence is contradictory; no unconditional conclusion is valid."
            confidence = 0.35
        elif blocked_facts or any(is_problem for _fact, is_problem in numeric_checks):
            conclusion = "The data constellation supports a blocked/problem conclusion."
            confidence = 0.85
        elif facts:
            conclusion = "The data constellation does not show a blocked/problem signal."
            confidence = 0.7
        else:
            conclusion = "No structured evidence was available for validation."
            confidence = 0.0

        return ConstellationResult(
            conclusion=conclusion,
            confidence=confidence,
            supporting_fields=[*resolutions, *support],
            applied_rules=sorted(set(applied_rules)),
            contradictions=contradictions,
            trace=trace,
        )

    def validate_pipeline_result(
        self,
        pipeline_result: Any,
        resolutions: list[FieldResolution] | None = None,
    ) -> ConstellationResult:
        """Extract minimal facts from a PipelineResult and validate them."""
        facts: list[EvidenceFact] = []
        for step in getattr(pipeline_result, "steps", []):
            status = getattr(step, "status", "")
            status_value = getattr(status, "value", str(status))
            facts.append(EvidenceFact(
                source_module=getattr(step, "module", "unknown"),
                field="status",
                value=status_value,
                description="Pipeline step execution status",
            ))
            if getattr(step, "error", None):
                facts.append(EvidenceFact(
                    source_module=getattr(step, "module", "unknown"),
                    field="open_errors",
                    value=1,
                    description=str(getattr(step, "error", "")),
                ))
        return self.validate(facts, resolutions=resolutions)
