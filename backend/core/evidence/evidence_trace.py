"""Helpers for constructing evidence traces."""

from __future__ import annotations

from core.evidence.schemas import ConstellationResult, EvidenceTrace, FieldResolution


def build_evidence_trace(
    session_id: str,
    turn_id: str,
    resolutions: list[FieldResolution],
    constellation: ConstellationResult,
    escalation_reason: str | None = None,
) -> EvidenceTrace:
    """Build a ready/not-ready EvidenceTrace from resolver and validator output."""
    unresolved = [
        resolution.term
        for resolution in resolutions
        if resolution.confidence == "unresolved"
    ]
    reason = escalation_reason
    if unresolved and reason is None:
        reason = "Unresolved semantic terms: " + ", ".join(unresolved)
    ready = not reason and not constellation.contradictions and constellation.confidence >= 0.6
    return EvidenceTrace(
        session_id=session_id,
        turn_id=turn_id,
        resolutions=resolutions,
        constellation=constellation,
        ready_for_synthesis=ready,
        escalation_reason=reason,
    )
