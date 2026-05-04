"""Routing hint inference for orchestrator guidance."""

from __future__ import annotations

from typing import List

from core.prestructure.schemas import (
    Intent,
    Complexity,
    RiskInfo,
    RoutingHints,
    WorkerType,
    RankedModule,
)


class RoutingHintInferencer:
    """
    Infer routing hints based on task characteristics.

    Provides orchestrator guidance on worker type, delegation,
    and execution strategy without LLM calls.
    """

    def infer(
        self,
        intent: Intent,
        complexity: Complexity,
        needs_tools: bool,
        risk: RiskInfo,
        candidate_modules: List[RankedModule],
    ) -> RoutingHints:
        """
        Infer routing hints from task characteristics.

        Returns RoutingHints with preferred worker type and delegation flags.
        """
        worker_type = self._determine_worker_type(
            intent, complexity, needs_tools, risk, candidate_modules
        )

        should_delegate = self._should_delegate(
            intent, complexity, needs_tools, candidate_modules
        )

        should_avoid_direct_answer = self._should_avoid_direct_answer(
            intent, needs_tools, risk
        )

        should_collect_state = self._should_collect_state(intent, needs_tools)

        return RoutingHints(
            preferred_worker_type=worker_type,
            should_delegate=should_delegate,
            should_avoid_direct_answer=should_avoid_direct_answer,
            should_collect_state_before_answer=should_collect_state,
        )

    def _determine_worker_type(
        self,
        intent: Intent,
        complexity: Complexity,
        needs_tools: bool,
        risk: RiskInfo,
        candidate_modules: List[RankedModule],
    ) -> WorkerType:
        """Determine preferred worker type based on task characteristics."""
        # Direct answer: simple answer requests, no tools needed, low risk
        if intent == "answer" and complexity == "simple" and not needs_tools:
            return "direct_answer"

        # Operator: explicit action with write intent
        if intent == "act" and risk.write_intent_detected:
            return "operator"

        # Workflow: explicit workflow markers only.
        if intent == "workflow":
            return "workflow"

        # Planner: multi-step or ambiguous situations
        if complexity in ("multi_step", "compound") or len(candidate_modules) > 1:
            return "planner"

        # Explorer: single-module investigate with read-only execution
        if intent == "investigate":
            return "explorer"

        # Default to planner for safety
        return "planner"

    def _should_delegate(
        self,
        intent: Intent,
        complexity: Complexity,
        needs_tools: bool,
        candidate_modules: List[RankedModule],
    ) -> bool:
        """Determine if task should be delegated to specialized worker."""
        # Delegate if tools needed
        if needs_tools:
            return True

        # Delegate if multi-step or compound
        if complexity in ("multi_step", "compound"):
            return True

        # Delegate if multiple candidate modules
        if len(candidate_modules) > 1:
            return True

        # Delegate investigate and act intents
        if intent in ("investigate", "act"):
            return True

        # Don't delegate simple answer questions
        if intent == "answer" and complexity == "simple":
            return False

        return True

    def _should_avoid_direct_answer(
        self,
        intent: Intent,
        needs_tools: bool,
        risk: RiskInfo,
    ) -> bool:
        """Determine if direct answer should be avoided."""
        # Always avoid direct answer if tools needed
        if needs_tools:
            return True

        # Avoid direct answer for investigate
        if intent == "investigate":
            return True

        # Avoid direct answer for risky operations
        if risk.level in ("high", "critical"):
            return True

        return False

    def _should_collect_state(self, intent: Intent, needs_tools: bool) -> bool:
        """Determine if fresh state should be collected before answering."""
        return intent == "investigate" and needs_tools


def infer_routing_hints(
    intent: Intent,
    complexity: Complexity,
    needs_tools: bool,
    risk: RiskInfo,
    candidate_modules: List[RankedModule],
) -> RoutingHints:
    """Convenience function for routing hint inference."""
    inferencer = RoutingHintInferencer()
    return inferencer.infer(intent, complexity, needs_tools, risk, candidate_modules)
