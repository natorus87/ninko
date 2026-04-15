"""Unit tests for the deterministic task pre-structuring components (unittest version)."""

from __future__ import annotations

import unittest
from typing import List

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.prestructure import (
    DeterministicTaskSketchBuilder,
    ModuleMetadata,
    InputNormalizer,
    IntentDetector,
    RiskAssessor,
    EntityExtractor,
    ModuleRanker,
    RoutingHintInferencer,
    build_task_sketch,
    normalize,
    extract_entities,
)
from core.prestructure.schemas import RiskInfo


# Sample module metadata for testing
TEST_MODULES: List[ModuleMetadata] = [
    ModuleMetadata(
        name="kubernetes",
        keywords=["kubernetes", "k8s", "pod", "deployment", "namespace", "cluster"],
        entities=["kubernetes", "pod", "deployment", "service", "ingress"],
        domain="kubernetes",
    ),
    ModuleMetadata(
        name="gitlab",
        keywords=[
            "gitlab",
            "pipeline",
            "merge request",
            "runner",
            "deployment",
            "repo",
        ],
        entities=["gitlab", "pipeline", "job", "runner", "mr"],
        domain="gitlab",
    ),
    ModuleMetadata(
        name="postgresql",
        keywords=["postgres", "postgresql", "database", "sql"],
        entities=["postgresql", "database", "table"],
        domain="database",
    ),
    ModuleMetadata(
        name="traefik",
        keywords=["traefik", "ingress", "proxy", "loadbalancer"],
        entities=["traefik", "ingress", "router"],
        domain="network",
    ),
]


class TestNormalizer(unittest.TestCase):
    """Tests for the InputNormalizer component."""

    def test_basic_normalization(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize("Prüf bitte ob PostgreSQL schuld ist!")

        self.assertEqual(result.original, "Prüf bitte ob PostgreSQL schuld ist!")
        self.assertIn("pruef", result.normalized)
        self.assertIn("postgresql", result.normalized)
        self.assertEqual(
            result.tokens, ["pruef", "bitte", "ob", "postgresql", "schuld", "ist"]
        )

    def test_umlaut_transformation(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize("Überprüfe die Änderungen in der Datenbank")

        self.assertIn("ueberpruefe", result.normalized)
        # Umlaut ä -> ae
        has_aenderungen = "aenderungen" in result.normalized
        has_ae = "ae" in result.normalized
        self.assertTrue(has_aenderungen or has_ae)

    def test_special_character_cleanup(self):
        normalizer = InputNormalizer()
        result = normalizer.normalize("Check im Namespace 'payments' die Pods!!!")

        self.assertNotIn("'", result.normalized)
        self.assertNotIn("!", result.normalized)
        self.assertIn("payments", result.tokens)

    def test_quick_normalize(self):
        normalizer = InputNormalizer()
        result = normalizer.quick_normalize("Grüße aus München")

        self.assertIn("gruesse", result)
        self.assertIn("muenchen", result)


class TestIntentDetector(unittest.TestCase):
    """Tests for the IntentDetector component."""

    def test_investigate_intent_detection(self):
        detector = IntentDetector()
        normalized = normalize("Prüf bitte ob PostgreSQL schuld ist")

        intent, scores = detector.detect(normalized)

        self.assertEqual(intent, "investigate")
        self.assertGreater(scores["investigate"], scores["act"])

    def test_act_intent_detection(self):
        detector = IntentDetector()
        normalized = normalize("Starte den Runner neu und trigger die Pipeline")

        intent, scores = detector.detect(normalized)

        self.assertEqual(intent, "act")
        self.assertGreater(scores["act"], 0)

    def test_plan_intent_detection(self):
        detector = IntentDetector()
        normalized = normalize("Wie soll ich die Migration planen?")

        intent, scores = detector.detect(normalized)

        self.assertEqual(intent, "plan")

    def test_answer_intent_detection(self):
        detector = IntentDetector()
        normalized = normalize("Was ist SafeGuard in Ninko?")

        intent, scores = detector.detect(normalized)

        self.assertEqual(intent, "answer")

    def test_hypothetical_context_detection(self):
        detector = IntentDetector()
        normalized = normalize("Prüf bitte und sag mir den nächsten Schritt")

        intent, scores = detector.detect(normalized)

        # Should be investigate despite action-like phrasing
        self.assertEqual(intent, "investigate")

    def test_unknown_intent_for_unclear_input(self):
        detector = IntentDetector()
        normalized = normalize("Kannst du mal danach schauen?")

        intent, scores = detector.detect(normalized)

        # Ambiguous input should result in investigate or unknown
        self.assertIn(intent, ("investigate", "unknown"))


class TestRiskAssessor(unittest.TestCase):
    """Tests for the RiskAssessor component."""

    def test_critical_risk_for_delete_verbs(self):
        assessor = RiskAssessor()
        normalized = normalize("Lösche alle Pods im Cluster")
        entities = ["kubernetes", "pods"]

        risk = assessor.assess("act", normalized, entities)

        self.assertEqual(risk.level, "critical")
        self.assertTrue(risk.destructive_potential)
        self.assertTrue(risk.approval_required)
        self.assertIn("DELETE_VERB_DETECTED", risk.reason_codes)

    def test_high_risk_for_write_verbs(self):
        assessor = RiskAssessor()
        normalized = normalize("Starte den Service neu")
        entities = ["kubernetes"]

        risk = assessor.assess("act", normalized, entities)

        self.assertEqual(risk.level, "high")
        self.assertTrue(risk.write_intent_detected)
        self.assertIn("WRITE_VERB_DETECTED", risk.reason_codes)

    def test_low_risk_for_investigate(self):
        assessor = RiskAssessor()
        normalized = normalize("Prüf bitte den Status")
        entities = []

        risk = assessor.assess("investigate", normalized, entities)

        self.assertEqual(risk.level, "low")
        self.assertFalse(risk.write_intent_detected)
        self.assertIn("READ_ONLY_DIAGNOSTIC", risk.reason_codes)

    def test_production_impact_detection(self):
        assessor = RiskAssessor()
        normalized = normalize("Deploye auf prod-eu")
        entities = ["kubernetes"]

        risk = assessor.assess("act", normalized, entities)

        self.assertEqual(risk.level, "high")
        self.assertTrue(risk.external_side_effects_possible)


class TestEntityExtractor(unittest.TestCase):
    """Tests for the EntityExtractor component."""

    def test_kubernetes_entities_extraction(self):
        extractor = EntityExtractor()
        normalized = normalize("Check im Cluster prod-eu im Namespace billing die Pods")

        entities = extractor.extract(normalized)

        self.assertIn("kubernetes", entities.systems)
        self.assertIn("prod-eu", entities.clusters)
        self.assertIn("billing", entities.namespaces)
        self.assertIn("pods", entities.resources)

    def test_gitlab_entities_extraction(self):
        extractor = EntityExtractor()
        normalized = normalize("Prüf die Pipeline im GitLab")

        entities = extractor.extract(normalized)

        self.assertIn("gitlab", entities.systems)
        self.assertIn("pipeline", entities.resources)

    def test_multiple_systems_detection(self):
        extractor = EntityExtractor()
        normalized = normalize("Prüf ob PostgreSQL oder der Ingress schuld ist")

        entities = extractor.extract(normalized)

        self.assertIn("postgresql", entities.systems)

    def test_domain_inference(self):
        extractor = EntityExtractor()
        normalized = normalize("Check die Kubernetes Pods")

        entities = extractor.extract(normalized)
        domain = extractor.extract_domain(entities)

        self.assertEqual(domain, "kubernetes")


class TestModuleRanker(unittest.TestCase):
    """Tests for the ModuleRanker component."""

    def test_ranking_by_keywords(self):
        ranker = ModuleRanker(TEST_MODULES)
        normalized = normalize("Prüf die GitLab Pipeline")
        entities = extract_entities(normalized)

        ranked = ranker.rank(normalized, entities, top_n=3)

        self.assertGreater(len(ranked), 0)
        self.assertEqual(ranked[0].module, "gitlab")
        self.assertGreater(ranked[0].score, 0)
        self.assertTrue(any("keyword" in r for r in ranked[0].reasons))

    def test_ranking_by_system_entity(self):
        ranker = ModuleRanker(TEST_MODULES)
        normalized = normalize("Probleme mit PostgreSQL")
        entities = extract_entities(normalized)

        ranked = ranker.rank(normalized, entities, top_n=3)

        self.assertTrue(any(r.module == "postgresql" for r in ranked))

    def test_top_n_limit(self):
        ranker = ModuleRanker(TEST_MODULES)
        normalized = normalize("Kubernetes und GitLab Probleme")
        entities = extract_entities(normalized)

        ranked = ranker.rank(normalized, entities, top_n=2)

        self.assertLessEqual(len(ranked), 2)


class TestRoutingHintInferencer(unittest.TestCase):
    """Tests for the RoutingHintInferencer component."""

    def test_direct_answer_for_simple_answer(self):
        inferencer = RoutingHintInferencer()
        risk = RiskInfo(level="low")

        hints = inferencer.infer("answer", "simple", False, risk, [])

        self.assertEqual(hints.preferred_worker_type, "direct_answer")
        self.assertFalse(hints.should_avoid_direct_answer)

    def test_explorer_for_investigate(self):
        inferencer = RoutingHintInferencer()
        risk = RiskInfo(level="low")

        hints = inferencer.infer("investigate", "simple", True, risk, [])

        self.assertEqual(hints.preferred_worker_type, "explorer")
        self.assertTrue(hints.should_avoid_direct_answer)

    def test_operator_for_write_actions(self):
        inferencer = RoutingHintInferencer()
        risk = RiskInfo(level="high", write_intent_detected=True)

        hints = inferencer.infer("act", "simple", True, risk, [])

        self.assertEqual(hints.preferred_worker_type, "operator")

    def test_delegation_for_tools_needed(self):
        inferencer = RoutingHintInferencer()
        risk = RiskInfo(level="low")

        hints = inferencer.infer("investigate", "simple", True, risk, [])

        self.assertTrue(hints.should_delegate)


class TestDeterministicTaskSketchBuilder(unittest.TestCase):
    """Integration tests for the full TaskSketch builder."""

    def test_build_simple_answer_request(self):
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build("Wie funktioniert SafeGuard in Ninko?")

        self.assertTrue(result.valid)
        self.assertLess(result.build_time_ms, 50)  # Should be fast
        self.assertEqual(result.sketch.task.intent, "answer")
        self.assertFalse(result.sketch.task.needs_tools)
        self.assertEqual(
            result.sketch.routing_hints.preferred_worker_type, "direct_answer"
        )
        self.assertEqual(result.sketch.risk.level, "low")

    def test_build_diagnose_multiple_systems(self):
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build(
            "Mein GitLab spinnt seit dem letzten Deployment, prüf bitte ob PostgreSQL oder der Ingress schuld ist und sag mir den nächsten sicheren  Schritt."
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.sketch.task.intent, "investigate")
        self.assertIn(result.sketch.task.complexity, ("multi_step", "compound"))
        self.assertTrue(result.sketch.task.needs_tools)
        self.assertTrue(result.sketch.task.needs_evidence)
        self.assertTrue(result.sketch.routing_hints.should_avoid_direct_answer)

        # Check candidate modules
        module_names = [m.module for m in result.sketch.scope.candidate_modules_ranked]
        self.assertTrue("gitlab" in module_names or "postgresql" in module_names)

    def test_build_explicit_action(self):
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build("Starte den Runner neu und trigger danach die Pipeline.")

        self.assertTrue(result.valid)
        self.assertEqual(result.sketch.task.intent, "act")
        self.assertTrue(result.sketch.risk.write_intent_detected)
        self.assertTrue(result.sketch.risk.approval_required)
        self.assertEqual(result.sketch.routing_hints.preferred_worker_type, "operator")

    def test_build_planning_request(self):
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build(
            "Wie sollte ich die Migration von Traefik v2 auf v3 planen?"
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.sketch.task.intent, "plan")

    def test_build_unclear_request(self):
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build("Kannst du mal danach schauen?")

        # Vague input is detected as investigate (not unknown) but with missing system info
        self.assertEqual(result.sketch.task.intent, "investigate")
        self.assertIn(
            "target_system_missing", result.sketch.uncertainty.missing_information
        )
        self.assertTrue(result.sketch.routing_hints.should_delegate)

    def test_build_kubernetes_status_check(self):
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build(
            "Check bitte im Cluster prod-eu im Namespace billing die Pods nach dem letzten Rollout."
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.sketch.task.intent, "investigate")
        self.assertEqual(result.sketch.scope.domain, "kubernetes")
        self.assertIn("prod-eu", result.sketch.scope.entities.clusters)
        self.assertIn("billing", result.sketch.scope.entities.namespaces)
        self.assertIn("pods", result.sketch.scope.entities.resources)

    def test_reproducibility(self):
        """Same input should produce same output."""
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)

        result1 = builder.build("Prüf die GitLab Pipeline")
        result2 = builder.build("Prüf die GitLab Pipeline")

        self.assertEqual(result1.sketch.task.intent, result2.sketch.task.intent)
        self.assertEqual(result1.sketch.task.complexity, result2.sketch.task.complexity)
        self.assertEqual(
            result1.sketch.routing_hints.preferred_worker_type,
            result2.sketch.routing_hints.preferred_worker_type,
        )

    def test_convenience_function(self):
        sketch = build_task_sketch("Was ist Kubernetes?", module_metadata=TEST_MODULES)

        self.assertEqual(sketch.task.intent, "answer")
        self.assertEqual(sketch.source.user_message, "Was ist Kubernetes?")


class TestTaskSketchPlannerIntegration(unittest.TestCase):
    """Tests for TaskSketch and Planner integration."""

    def test_task_sketch_includes_risk_info(self):
        """TaskSketch should include risk assessment for Planner consumption."""
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build("Lösche alle Pods im production Namespace")

        self.assertTrue(result.valid)
        # High risk for delete operations
        self.assertEqual(result.sketch.risk.level, "critical")
        self.assertTrue(result.sketch.risk.destructive_potential)
        self.assertTrue(result.sketch.risk.approval_required)

    def test_task_sketch_includes_constraints(self):
        """TaskSketch should include constraints for Planner validation."""
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build(
            "Prüf den GitLab Status und sag mir den nächsten Schritt"
        )

        self.assertTrue(result.valid)
        # Should require evidence for investigate intent
        self.assertTrue(result.sketch.task.needs_evidence)
        # Should include safe_next_step in must_include
        self.assertIn("safe_next_step", result.sketch.constraints.must_include)

    def test_task_sketch_candidate_modules_ranked(self):
        """TaskSketch should provide ranked candidate modules."""
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build("Check die PostgreSQL Datenbank und GitLab Pipeline")

        self.assertTrue(result.valid)
        # Should have multiple candidate modules
        self.assertTrue(len(result.sketch.scope.candidate_modules_ranked) >= 2)
        # Each ranked module should have a score and reasons
        for ranked in result.sketch.scope.candidate_modules_ranked:
            self.assertGreater(ranked.score, 0)
            self.assertTrue(len(ranked.reasons) > 0)

    def test_task_sketch_routing_hints_for_planner(self):
        """TaskSketch should provide routing hints for orchestrator decisions."""
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)

        # Multi-module compound query should suggest planner
        result = builder.build(
            "Mein GitLab spinnt seit dem letzten Deployment, prüf bitte ob PostgreSQL "
            "oder der Ingress schuld ist und sag mir den nächsten sicheren Schritt."
        )

        self.assertTrue(result.valid)
        self.assertTrue(result.sketch.routing_hints.should_avoid_direct_answer)
        self.assertEqual(result.sketch.routing_hints.preferred_worker_type, "planner")
        self.assertTrue(result.sketch.routing_hints.should_collect_state_before_answer)

    def test_task_sketch_uncertainty_marking(self):
        """TaskSketch should mark uncertainty when input is ambiguous."""
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)
        result = builder.build("Kannst du mal schauen?")

        self.assertTrue(result.valid)
        # Should be marked as ambiguous
        self.assertTrue(result.sketch.uncertainty.ambiguous)
        self.assertTrue(len(result.sketch.uncertainty.missing_information) > 0)
        # Should have low confidence
        self.assertLess(result.sketch.uncertainty.confidence, 0.7)

    def test_task_sketch_execution_mode(self):
        """TaskSketch should determine appropriate execution mode."""
        builder = DeterministicTaskSketchBuilder(TEST_MODULES)

        # Read-only diagnostic
        result1 = builder.build("Was ist Kubernetes?")
        self.assertEqual(result1.sketch.constraints.execution_mode, "read_only")

        # Write operation should be guarded
        result2 = builder.build("Starte die Pipeline")
        self.assertEqual(result2.sketch.constraints.execution_mode, "guarded_write")


if __name__ == "__main__":
    unittest.main(verbosity=2)
