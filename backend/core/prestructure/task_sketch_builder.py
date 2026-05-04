"""Deterministic TaskSketch builder - main orchestration component."""

from __future__ import annotations

import time
from typing import List, Optional, Dict, Any

from core.prestructure.schemas import (
    TaskSketch,
    SourceInfo,
    TaskInfo,
    RiskInfo,
    ScopeInfo,
    ScopeEntities,
    ConstraintInfo,
    UncertaintyInfo,
    DebugInfo,
    RankedModule,
    ModuleMetadata,
    Intent,
    Complexity,
    ExecutionMode,
    TaskSketchBuildResult,
)
from core.prestructure.normalizer import InputNormalizer, NormalizedInput
from core.prestructure.intent_detector import IntentDetector
from core.prestructure.risk_assessor import RiskAssessor
from core.prestructure.entity_extractor import EntityExtractor
from core.prestructure.module_ranker import ModuleRanker
from core.prestructure.routing_hints import RoutingHintInferencer


class DeterministicTaskSketchBuilder:
    """
    Main builder that transforms user input into structured TaskSketch.

    Orchestrates all pre-structure components deterministically
    without LLM calls or tool execution.
    """

    def __init__(
        self,
        module_metadata: Optional[List[ModuleMetadata]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.normalizer = InputNormalizer()
        self.intent_detector = IntentDetector()
        self.risk_assessor = RiskAssessor()
        self.entity_extractor = EntityExtractor()
        self.module_ranker = ModuleRanker(module_metadata or [])
        self.routing_inferencer = RoutingHintInferencer()
        self.config = config or {}

    def build(
        self,
        user_message: str,
        session_id: Optional[str] = None,
        conversation_turn_id: Optional[str] = None,
        recent_turns: Optional[List[Dict[str, Any]]] = None,
    ) -> TaskSketchBuildResult:
        """
        Build TaskSketch from user message.

        Pipeline:
        1. Normalize input
        2. Detect intent
        3. Extract goals
        4. Detect complexity
        5. Extract entities
        6. Rank candidate modules
        7. Infer task flags
        8. Assess risk
        9. Infer constraints
        10. Infer routing hints
        11. Calculate uncertainty
        12. Collect debug info
        """
        start_time = time.perf_counter()

        # Step 1: Normalize input
        normalized = self.normalizer.normalize(user_message)

        # Step 2: Detect intent
        intent, confidence, intent_scores = self.intent_detector.detect_with_confidence(
            normalized
        )

        # Step 3: Extract goals
        primary_goal, secondary_goals, requested_output = self._extract_goals(
            user_message, intent, normalized
        )

        # Step 4: Detect complexity
        complexity = self._detect_complexity(normalized, secondary_goals)

        # Step 5: Extract entities
        entities = self.entity_extractor.extract(normalized)

        # Step 6: Rank candidate modules
        ranked_modules = self.module_ranker.rank(normalized, entities, top_n=5)

        # Step 7: Infer task flags
        task_flags = self._infer_task_flags(intent, normalized, entities)

        # Step 8: Assess risk
        entity_list = (
            entities.systems + entities.services + entities.hosts + entities.resources
        )
        risk = self.risk_assessor.assess(intent, normalized, entity_list)

        # Step 9: Infer constraints
        constraints = self._infer_constraints(intent, normalized, risk)

        # Step 10: Infer routing hints
        routing = self.routing_inferencer.infer(
            intent, complexity, task_flags["needs_tools"], risk, ranked_modules
        )

        # Step 11: Calculate uncertainty
        uncertainty = self._calculate_uncertainty(
            intent, ranked_modules, entities, confidence, primary_goal
        )

        # Step 12: Collect debug info
        debug = self._collect_debug_info(
            normalized, intent_scores, ranked_modules, intent
        )

        # Build TaskSketch
        sketch = TaskSketch(
            version="1.0",
            source=SourceInfo(
                user_message=user_message,
                conversation_turn_id=conversation_turn_id,
                session_id=session_id,
            ),
            task=TaskInfo(
                intent=intent,
                primary_goal=primary_goal,
                secondary_goals=secondary_goals,
                requested_output=requested_output,
                complexity=complexity,
                needs_tools=task_flags["needs_tools"],
                needs_fresh_state=task_flags["needs_fresh_state"],
                needs_evidence=task_flags["needs_evidence"],
                user_explicit_action_request=intent == "act",
            ),
            risk=risk,
            scope=ScopeInfo(
                domain=self.entity_extractor.extract_domain(entities),
                candidate_modules=[m.module for m in ranked_modules],
                candidate_modules_ranked=ranked_modules,
                multi_module=len(ranked_modules) > 1,
                entities=entities,
            ),
            constraints=constraints,
            routing_hints=routing,
            uncertainty=uncertainty,
            debug=debug,
        )

        build_time_ms = (time.perf_counter() - start_time) * 1000

        # Validate
        valid, validation_errors = self._validate_sketch(sketch)

        return TaskSketchBuildResult(
            sketch=sketch,
            build_time_ms=build_time_ms,
            valid=valid,
            validation_errors=validation_errors,
        )

    def _extract_goals(
        self, user_message: str, intent: Intent, normalized: NormalizedInput
    ) -> tuple[str, List[str], List[str]]:
        """Extract primary goal, secondary goals, and requested output types."""
        # Primary goal: simplified version of user message
        primary_goal = self._normalize_goal(user_message)

        # Secondary goals: detected from secondary intents or sub-tasks
        secondary_goals: List[str] = []

        # Check for compound goals (multiple systems mentioned)
        systems = self.entity_extractor.extract(normalized).systems
        if len(systems) > 1:
            for system in systems:
                secondary_goals.append(f"Prüfung von {system}")

        # Requested output types
        requested_output: List[str] = []
        normalized_text = normalized.normalized

        if any(
            marker in normalized_text
            for marker in [
                "naechster schritt",
                "next step",
                "siguiente paso",
                "prochaine etape",
                "prossimo passo",
            ]
        ):
            requested_output.append("next_step")
        if any(
            marker in normalized_text
            for marker in [
                "warum",
                "schuld",
                "why",
                "root cause",
                "cause",
                "por que",
                "porque",
                "pourquoi",
                "perche",
            ]
        ):
            requested_output.append("diagnosis")
        if any(
            marker in normalized_text
            for marker in [
                "mach es",
                "ausfuehren",
                "execute",
                "run",
                "do it",
                "iniciar",
                "detener",
                "reiniciar",
            ]
        ):
            requested_output.append("execution")
        if any(
            marker in normalized_text
            for marker in [
                "erklaere",
                "was ist",
                "explain",
                "what is",
                "describe",
                "que es",
                "c est quoi",
                "che cos e",
            ]
        ):
            requested_output.append("answer")
        if any(
            marker in normalized_text
            for marker in [
                "fasse zusammen",
                "zusammenfassen",
                "summarize",
                "summary",
                "resumen",
                "resumir",
                "resume",
                "resumer",
                "riassumi",
            ]
        ):
            requested_output.append("summary")
        if any(
            marker in normalized_text
            for marker in [
                "plan",
                "vorgehen",
                "strategy",
                "planificar",
                "planifier",
                "pianificare",
            ]
        ):
            requested_output.append("plan")
        if any(
            marker in normalized_text
            for marker in [
                "vergleich",
                "unterschied",
                "compare",
                "difference",
                "comparar",
                "comparer",
                "confronto",
            ]
        ):
            requested_output.append("comparison")

        # Default based on intent
        if not requested_output:
            intent_to_output: Dict[Intent, str] = {
                "answer": "answer",
                "investigate": "diagnosis",
                "act": "execution",
                "plan": "plan",
                "workflow": "plan",
                "compare": "comparison",
                "summarize": "summary",
                "unknown": "answer",
            }
            requested_output.append(intent_to_output.get(intent, "answer"))

        return primary_goal, secondary_goals, requested_output

    def _normalize_goal(self, user_message: str) -> str:
        """Create a normalized primary goal description."""
        # Truncate and clean
        goal = user_message.strip()
        if len(goal) > 100:
            goal = goal[:97] + "..."
        return goal

    def _detect_complexity(
        self, normalized: NormalizedInput, secondary_goals: List[str]
    ) -> Complexity:
        """Detect complexity level based on connectors and goal count."""
        tokens = normalized.tokens
        normalized_text = normalized.normalized

        # Count goal indicators
        goal_count = 1 + len(secondary_goals)

        # Count connectors (complexity indicators)
        connectors = [
            "und",
            "oder",
            "falls",
            "wenn",
            "danach",
            "und dann",
            "anschliessend",
        ]
        connector_count = sum(1 for c in connectors if c in tokens)

        # Detect compound patterns
        if goal_count >= 3 or connector_count >= 2:
            return "compound"

        if goal_count == 2 or connector_count == 1:
            return "multi_step"

        # Check for explicit multi-step language
        if any(
            marker in normalized_text
            for marker in ["zuerst", "dann", "danach", "schritt", "step"]
        ):
            return "multi_step"

        return "simple"

    def _infer_task_flags(
        self, intent: Intent, normalized: NormalizedInput, entities: ScopeEntities
    ) -> Dict[str, bool]:
        """Infer task flags (needs_tools, needs_fresh_state, needs_evidence)."""
        normalized_text = normalized.normalized
        tokens = set(normalized.tokens)

        # needs_tools: diagnosis, state checking, live system interaction
        needs_tools = False
        if intent == "investigate":
            needs_tools = True
        if any(t in tokens for t in ["pruef", "check", "status", "nachschauen"]):
            needs_tools = True
        if entities.systems or entities.clusters or entities.namespaces:
            needs_tools = True

        # needs_fresh_state: time-related requests
        needs_fresh_state = False
        time_markers = ["gerade", "jetzt", "aktuell", "seit", "nach", "vor", "letzten"]
        if any(marker in normalized_text for marker in time_markers):
            needs_fresh_state = True
        if entities.time_refs:
            needs_fresh_state = True

        # needs_evidence: investigate, compare, or risky actions
        needs_evidence = False
        if intent == "investigate":
            needs_evidence = True
        if intent == "compare":
            needs_evidence = True

        return {
            "needs_tools": needs_tools,
            "needs_fresh_state": needs_fresh_state,
            "needs_evidence": needs_evidence,
        }

    def _infer_constraints(
        self, intent: Intent, normalized: NormalizedInput, risk: RiskInfo
    ) -> ConstraintInfo:
        """Infer execution constraints based on intent and risk."""
        # Execution mode
        if intent in ("answer", "investigate"):
            execution_mode: ExecutionMode = "read_only"
        elif risk.write_intent_detected and risk.approval_required:
            execution_mode = "guarded_write"
        else:
            execution_mode = "planner_decides"

        # Response style
        normalized_text = normalized.normalized
        response_style = "normal"
        if any(
            w in normalized_text
            for w in [
                "kurz",
                "kurz und knapp",
                "kurze",
                "bueff",
                "bueff",
                "bueff",
                "knapp",
            ]
        ):
            response_style = "concise"
        elif any(
            w in normalized_text
            for w in ["detailliert", "ausfuehrlich", "ausfuehrlich", "alle details"]
        ):
            response_style = "detailed"

        # must_not_do / must_include based on risk
        must_not_do: List[str] = []
        must_include: List[str] = []

        if risk.level in ("high", "critical"):
            must_not_do.append("destructive_changes_without_approval")

        if risk.level in ("medium", "high", "critical"):
            must_include.append("evidence")
            must_include.append("safe_next_step")

        if intent == "investigate":
            must_include.append("evidence")

        if any(
            marker in normalized_text
            for marker in [
                "naechster schritt",
                "naechsten schritt",
                "next step",
                "sicherer schritt",
                "safe next step",
            ]
        ):
            must_include.append("safe_next_step")

        return ConstraintInfo(
            execution_mode=execution_mode,
            time_sensitivity="normal",
            response_style=response_style,  # type: ignore
            must_not_do=must_not_do,
            must_include=list(dict.fromkeys(must_include)),
            user_constraints=[],
        )

    def _calculate_uncertainty(
        self,
        intent: Intent,
        ranked_modules: List[RankedModule],
        entities: ScopeEntities,
        confidence: float,
        primary_goal: str,
    ) -> UncertaintyInfo:
        """Calculate uncertainty indicators."""
        ambiguous = False
        missing_info: List[str] = []
        open_questions: List[str] = []

        # Check for ambiguous intent
        if intent == "unknown":
            ambiguous = True
            missing_info.append("intent_unclear")

        # Check for multiple candidate modules
        if len(ranked_modules) > 1:
            top_score = ranked_modules[0].score
            second_score = ranked_modules[1].score if len(ranked_modules) > 1 else 0
            if top_score - second_score < 0.15:
                ambiguous = True
                missing_info.append("module_ambiguous")

        # Check for missing critical entities
        if intent == "investigate" and not entities.systems:
            missing_info.append("target_system_missing")
            if not ranked_modules:
                ambiguous = True

        if "namespace" in primary_goal.lower() and not entities.namespaces:
            missing_info.append("namespace_missing")

        if "cluster" in primary_goal.lower() and not entities.clusters:
            missing_info.append("cluster_missing")

        adjusted_confidence = confidence
        if missing_info:
            adjusted_confidence = min(adjusted_confidence, 0.65)

        return UncertaintyInfo(
            ambiguous=ambiguous,
            missing_information=missing_info,
            open_questions=open_questions,
            confidence=round(adjusted_confidence, 2),
        )

    def _collect_debug_info(
        self,
        normalized: NormalizedInput,
        intent_scores: Dict[str, float],
        ranked_modules: List[RankedModule],
        intent: Intent,
    ) -> DebugInfo:
        """Collect debug information for traceability."""
        matched_rules: List[str] = []

        # Add intent detection rules
        matched_rules.append(f"INTENT_{intent.upper()}")

        # Add high-scoring intents
        for intent_name, score in intent_scores.items():
            if score > 0:
                matched_rules.append(f"INTENT_{intent_name.upper()}_{int(score)}")

        # Add module matching rules
        for rm in ranked_modules:
            matched_rules.append(f"MODULE_{rm.module.upper()}")

        return DebugInfo(
            matched_rules=matched_rules,
            tokens={
                "normalized_input": normalized.tokens[:50],  # Limit tokens stored
            },
        )

    def _validate_sketch(self, sketch: TaskSketch) -> tuple[bool, List[str]]:
        """Validate the generated TaskSketch."""
        errors: List[str] = []

        # Check required fields
        if not sketch.source.user_message:
            errors.append("Missing user_message in source")

        if not sketch.task.primary_goal:
            errors.append("Missing primary_goal in task")

        # Validate confidence range
        if not 0 <= sketch.uncertainty.confidence <= 1:
            errors.append(f"Invalid confidence value: {sketch.uncertainty.confidence}")

        # Validate module scores
        for rm in sketch.scope.candidate_modules_ranked:
            if not 0 <= rm.score <= 1:
                errors.append(f"Invalid module score for {rm.module}: {rm.score}")

        return len(errors) == 0, errors

    def update_module_metadata(self, module_metadata: List[ModuleMetadata]) -> None:
        """Update the module metadata used for ranking."""
        self.module_ranker = ModuleRanker(module_metadata)


# Convenience function for direct usage
def build_task_sketch(
    user_message: str,
    session_id: Optional[str] = None,
    module_metadata: Optional[List[ModuleMetadata]] = None,
) -> TaskSketch:
    """Build TaskSketch with default configuration."""
    builder = DeterministicTaskSketchBuilder(module_metadata)
    result = builder.build(user_message, session_id)
    return result.sketch
