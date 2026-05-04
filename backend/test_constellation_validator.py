"""Tests for evidence constellation validation."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.evidence import ConstellationValidator, EvidenceFact


class TestConstellationValidator(unittest.TestCase):
    def test_blocked_status_supports_problem_conclusion(self):
        validator = ConstellationValidator()

        result = validator.validate([
            EvidenceFact(source_module="postgresql", field="status", value="blocked"),
            EvidenceFact(source_module="postgresql", field="pending_invoices", value=4),
        ])

        self.assertIn("blocked/problem", result.conclusion)
        self.assertGreaterEqual(result.confidence, 0.8)
        self.assertIn("status_blocked_classification", result.applied_rules)
        self.assertTrue(result.supporting_fields)

    def test_contradictory_status_does_not_create_silent_conclusion(self):
        validator = ConstellationValidator()

        result = validator.validate([
            EvidenceFact(source_module="erp", field="status", value="ok"),
            EvidenceFact(source_module="postgresql", field="status", value="blocked"),
        ])

        self.assertTrue(result.contradictions)
        self.assertIn("contradictory", result.conclusion)
        self.assertLess(result.confidence, 0.6)

    def test_numeric_problem_signal_with_ok_status_is_contradiction(self):
        validator = ConstellationValidator()

        result = validator.validate([
            EvidenceFact(source_module="erp", field="status", value="ok"),
            EvidenceFact(source_module="erp", field="failed_jobs", value=2),
        ])

        self.assertTrue(result.contradictions)
        self.assertIn("numeric_positive_problem_signal", result.applied_rules)


if __name__ == "__main__":
    unittest.main()
