"""Tests for EvidenceTrace construction."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.evidence import ConstellationResult, FieldResolution, build_evidence_trace


class TestEvidenceTrace(unittest.TestCase):
    def test_ready_trace_when_high_confidence_and_no_contradictions(self):
        resolution = FieldResolution(
            term="fakturaverarbeitung",
            resolved_to="database",
            source_module="postgresql",
            confidence="high",
            score=1.0,
            reason="Glossary match",
        )
        constellation = ConstellationResult(
            conclusion="The data constellation supports a blocked/problem conclusion.",
            confidence=0.9,
            supporting_fields=[resolution],
            applied_rules=["status_blocked_classification"],
            contradictions=[],
            trace=["postgresql.status='blocked'"],
        )

        trace = build_evidence_trace("s1", "t1", [resolution], constellation)

        self.assertTrue(trace.ready_for_synthesis)
        self.assertIsNone(trace.escalation_reason)
        self.assertIn("Evidence Trace", trace.to_markdown())

    def test_unresolved_resolution_blocks_ready_for_synthesis(self):
        resolution = FieldResolution(
            term="unknown",
            resolved_to="",
            source_module="",
            confidence="unresolved",
            score=0.0,
            reason="No match",
        )
        constellation = ConstellationResult(
            conclusion="No structured evidence was available for validation.",
            confidence=0.0,
        )

        trace = build_evidence_trace("s1", "t1", [resolution], constellation)

        self.assertFalse(trace.ready_for_synthesis)
        self.assertIn("unknown", trace.escalation_reason or "")


if __name__ == "__main__":
    unittest.main()
