"""Rule-based intent detection for deterministic classification."""

from __future__ import annotations

from typing import Dict, List, Tuple

from core.prestructure.schemas import Intent
from core.prestructure.normalizer import NormalizedInput


class IntentDetector:
    """
    Deterministic intent detection using keyword and phrase matching.

    Based on verb analysis, question structure, and action/diagnosis markers.
    No LLM calls - pure rule-based scoring.
    """

    # Intent marker categories with scoring weights
    INVESTIGATE_MARKERS: List[str] = [
        "pruef",
        "check",
        "inspect",
        "investigate",
        "diagnose",
        "analysiere",
        "untersuche",
        "analyze",
        "analyse",
        "finde heraus",
        "find out",
        "look into",
        "woran liegt",
        "schuld",
        "cause",
        "root cause",
        "diagnose",
        "warum funktioniert nicht",
        "why does not work",
        "problem",
        "issue",
        "fehler",
        "status pruefen",
        "status",
        "status check",
        "sieh nach",
        "schaue nach",
        "guck nach",
        "schauen",
        "schau",
        "nachschauen",
        "nachschau",
        "was ist los",
        "was geht",
        "wie steht es um",
        "wie sieht es aus",
        "zeig mir",
        "zeigen",
        "ueberpruefe",
        "ueberpruef",
        "kontrolliere",
        "kontrollier",
        "analyse",
        "analysieren",
        "untersuchen",
        "ermittle",
        "ermitteln",
        "feststellen",
        "feststelle",
        "identifiziere",
        "identifizieren",
        "anzeigen",
        "zeige",
        "show",
        "por que",
        "porque",
        "pourquoi",
        "perche",
        "revisa",
        "revisar",
        "verifica",
        "verificar",
        "verifie",
        "verifier",
        "controlla",
        "controllare",
    ]

    ACT_MARKERS: List[str] = [
        "starte",
        "start",
        "stoppe",
        "stop",
        "shutdown",
        "halte an",
        "aendere",
        "aender",
        "change",
        "update",
        "deploye",
        "deploy",
        "deployen",
        "release",
        "loesche",
        "loesch",
        "delete",
        "remove",
        "fuehre aus",
        "fuehr aus",
        "ausfuehren",
        "execute",
        "run",
        "do it",
        "setze",
        "setz",
        "trigger",
        "triggere",
        "trigger",
        "erstelle",
        "erstell",
        "create",
        "erzeugen",
        "erzeuge",
        "restart",
        "neustart",
        "neu starten",
        "neu starte",
        "reboot",
        "aktiviere",
        "aktivier",
        "aktivieren",
        "deaktiviere",
        "deaktivier",
        "deaktivieren",
        "installiere",
        "installieren",
        "install",
        "upgraden",
        "upgrade",
        "migrate",
        "migriere",
        "kopiere",
        "verschiebe",
        "verschieben",
        "reset",
        "zuruecksetzen",
        "schreibe",
        "schreiben",
        "send",
        "post",
        "iniciar",
        "detener",
        "reiniciar",
        "eliminar",
        "borrar",
        "supprimer",
        "effacer",
        "redemarrer",
        "avviare",
        "ferma",
        "riavvia",
    ]

    PLAN_MARKERS: List[str] = [
        "plan",
        "planen",
        "wie soll ich",
        "schritt fuer schritt",
        "vorgehen",
        "strategie",
        "konzept",
        "roadmap",
        "step by step",
        "strategy",
        "approach",
        "wie gehe ich vor",
        "wie mache ich",
        "wie sollte ich",
        "wie wuerdest du",
        "wie wuerdest",
        "how should i",
        "how do i plan",
        "planificar",
        "planifier",
        "pianificare",
    ]

    WORKFLOW_MARKERS: List[str] = [
        "workflow",
        "automation",
        "automatisieren",
        "automatisierung",
        "pipeline",
        "sequenz",
        "chain",
        "kette",
        "mehrstufig",
        "mehrstufige",
        "abfolge",
        "prozess",
        "prozessablauf",
        "orchestration",
    ]

    COMPARE_MARKERS: List[str] = [
        "vergleich",
        "vergleiche",
        "vergleichen",
        "unterschied",
        "besser",
        "versus",
        "vs",
        "pros und cons",
        "vor und nachteile",
        "alternativen",
        "alternativen",
        "optionen",
        "option",
        "welche ist besser",
        "welches ist besser",
        "compare",
        "comparison",
        "difference",
        "comparar",
        "comparer",
        "confronto",
    ]

    SUMMARIZE_MARKERS: List[str] = [
        "zusammenfassen",
        "fass zusammen",
        "fasse zusammen",
        "summary",
        "zusammenfassung",
        "resuemee",
        "resumee",
        "ueberblick",
        "overview",
        "kurz und knapp",
        "in kuerze",
        "summarize",
        "recap",
        "tl dr",
        "tldr",
        "resumen",
        "resumir",
        "resume",
        "resumer",
        "riassumi",
        "riepilogo",
    ]

    ANSWER_MARKERS: List[str] = [
        "was ist",
        "was sind",
        "wie funktioniert",
        "wie funktioniert",
        "erklaere",
        "erklaeren",
        "beschreibe",
        "beschreiben",
        "wie geht",
        "wie mache ich",
        "was bedeutet",
        "was heisst",
        "definiere",
        "definition",
        "wie wird",
        "what is",
        "how does",
        "explain",
        "describe",
        "define",
        "que es",
        "que significa",
        "c est quoi",
        "che cos e",
    ]

    # Priority order: higher index = higher priority
    INTENT_PRIORITY: List[Intent] = [
        "unknown",
        "answer",
        "summarize",
        "compare",
        "plan",
        "workflow",
        "investigate",
        "act",
    ]

    # Hypothetical markers - reduce act score if these are present
    HYPOTHETICAL_MARKERS: List[str] = [
        "soll ich",
        "sollte ich",
        "wenn ich",
        "falls ich",
        "was waere wenn",
        "wie waere es",
        "theoretisch",
        "in der theorie",
        "angenommen",
        "nehmen wir an",
    ]

    def detect(self, normalized: NormalizedInput) -> Tuple[Intent, Dict[str, float]]:
        """
        Detect intent from normalized input.

        Returns the detected intent and score distribution for debugging.
        """
        scores: Dict[str, float] = {
            "answer": 0.0,
            "investigate": 0.0,
            "act": 0.0,
            "plan": 0.0,
            "workflow": 0.0,
            "compare": 0.0,
            "summarize": 0.0,
            "unknown": 0.0,
        }

        tokens = normalized.tokens
        normalized_text = normalized.normalized

        # Score each intent based on markers
        scores["investigate"] += (
            self._count_matches(tokens, self.INVESTIGATE_MARKERS) * 3.0
        )
        scores["act"] += self._count_matches(tokens, self.ACT_MARKERS) * 4.0
        scores["plan"] += self._count_matches(tokens, self.PLAN_MARKERS) * 3.0
        scores["workflow"] += self._count_matches(tokens, self.WORKFLOW_MARKERS) * 3.0
        scores["compare"] += self._count_matches(tokens, self.COMPARE_MARKERS) * 3.0
        scores["summarize"] += self._count_matches(tokens, self.SUMMARIZE_MARKERS) * 3.0

        # Answer is fallback - only gets score if no other intent matched
        if max(scores.values()) == 0:
            if any(t in tokens for t in ["was", "wie", "erklaere", "beschreibe"]):
                scores["answer"] += 2.0

        # Hypothetical correction: reduce act score if hypothetical markers present
        if self._has_hypothetical_context(tokens, normalized_text):
            if scores["investigate"] > 0 and scores["act"] > 0:
                # Investigation takes priority over hypothetical action
                scores["act"] *= 0.3

        # Handle ambiguous "check and tell me next step" patterns
        if scores["investigate"] > 0 and self._has_next_step_marker(
            tokens, normalized_text
        ):
            # Boost investigate, reduce act if present
            scores["investigate"] *= 1.2
            scores["act"] *= 0.5

        # Determine best intent
        best_intent_key = max(scores.items(), key=lambda x: x[1])[0]

        # If all scores are 0, return unknown
        if scores[best_intent_key] == 0:
            best_intent_key = "unknown"

        # Apply priority-based resolution for ties
        best_intent: Intent = self._resolve_by_priority(scores, best_intent_key)

        return best_intent, scores

    def _count_matches(self, tokens: List[str], markers: List[str]) -> int:
        """Count how many markers appear in tokens (phrase matching)."""
        count = 0
        normalized_text = " ".join(tokens)

        # Check multi-word phrases first
        for marker in markers:
            if " " in marker:
                if marker in normalized_text:
                    count += 1
            else:
                if marker in tokens:
                    count += 1

        return count

    def _has_hypothetical_context(
        self, tokens: List[str], normalized_text: str
    ) -> bool:
        """Check if the request is hypothetical (not actual action)."""
        for marker in self.HYPOTHETICAL_MARKERS:
            if " " in marker:
                if marker in normalized_text:
                    return True
            else:
                if marker in tokens:
                    return True
        return False

    def _has_next_step_marker(self, tokens: List[str], normalized_text: str) -> bool:
        """Check if user asks for next step (suggests investigation)."""
        next_step_markers = [
            "naechster schritt",
            "naechster sicherer schritt",
            "nächster schritt",
            "was soll ich als naechstes",
            "was soll ich als nächstes",
            "was ist der naechste schritt",
            "wie gehe ich weiter",
            "was mache ich dann",
        ]
        for marker in next_step_markers:
            if marker in normalized_text:
                return True
        return False

    def _resolve_by_priority(
        self, scores: Dict[str, float], current_best: str
    ) -> Intent:
        """
        Resolve ties using priority order.

        If multiple intents have similar scores (within 1.0 point),
        use the priority list to pick the winner.
        """
        best_score = scores[current_best]

        # Find all intents with similar scores (within 1.0)
        tied_intents = [
            intent
            for intent, score in scores.items()
            if abs(score - best_score) <= 1.0 and score > 0
        ]

        if len(tied_intents) <= 1:
            return current_best  # type: ignore[return-value]

        # Pick the one with highest priority
        for intent in reversed(self.INTENT_PRIORITY):
            if intent in tied_intents:
                return intent

        return current_best  # type: ignore[return-value]

    def detect_with_confidence(
        self, normalized: NormalizedInput
    ) -> Tuple[Intent, float, Dict[str, float]]:
        """
        Detect intent and calculate confidence score.

        Confidence is based on:
        - Score gap between top 2 intents
        - Absolute score of winner
        - Presence of strong markers
        """
        intent, scores = self.detect(normalized)

        if intent == "unknown":
            return intent, 0.0, scores

        # Calculate confidence
        sorted_scores = sorted(scores.values(), reverse=True)
        winner_score = sorted_scores[0]
        runner_up_score = sorted_scores[1] if len(sorted_scores) > 1 else 0

        # Gap-based confidence
        gap = winner_score - runner_up_score
        confidence = min(0.9, 0.4 + (gap * 0.1))

        # Boost for strong absolute scores
        if winner_score >= 8.0:
            confidence = min(0.95, confidence + 0.1)

        return intent, confidence, scores


def detect_intent(normalized: NormalizedInput) -> Intent:
    """Convenience function for intent detection."""
    detector = IntentDetector()
    intent, _ = detector.detect(normalized)
    return intent


def detect_intent_with_confidence(normalized: NormalizedInput) -> Tuple[Intent, float]:
    """Convenience function for intent detection with confidence."""
    detector = IntentDetector()
    intent, confidence, _ = detector.detect_with_confidence(normalized)
    return intent, confidence
