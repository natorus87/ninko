"""Rule-based risk assessment for task pre-structuring."""

from __future__ import annotations

from typing import List, Set

from core.prestructure.schemas import Intent, RiskInfo
from core.prestructure.normalizer import NormalizedInput


class RiskAssessor:
    """
    Deterministic risk assessment using keyword and pattern matching.

    Evaluates destructive potential, write intent, and approval requirements
    without LLM calls.
    """

    # Risk level marker categories
    DELETE_VERBS: Set[str] = {
        "loesche",
        "loesch",
        "delete",
        "remove",
        "drop",
        "reset",
        "truncate",
        "purge",
        "destroy",
        "kill",
        "terminate",
        "aufloesen",
        "aufloesung",
        "zerschneiden",
        "zerstoeren",
    }

    WRITE_VERBS: Set[str] = {
        "starte",
        "start",
        "stoppe",
        "stop",
        "aendere",
        "aender",
        "update",
        "change",
        "deploye",
        "deploy",
        "trigger",
        "triggere",
        "erstelle",
        "erstell",
        "create",
        "write",
        "schreibe",
        "setze",
        "setz",
        "restart",
        "neustart",
        "reboot",
        "aktiviere",
        "aktivier",
        "deaktiviere",
        "deaktivier",
        "installiere",
        "upgraden",
        "upgrade",
        "migrate",
        "migriere",
        "kopiere",
        "verschiebe",
        "copy",
        "move",
    }

    PRODUCTION_IMPACT_MARKERS: Set[str] = {
        "prod",
        "production",
        "produktion",
        "live",
        "main",
        "master",
        "production-",
        "prod-",
        "critical",
        "kritisch",
        "wichtig",
        "wichtige",
        "extern",
        "external",
        "kunde",
        "kunden",
        "customer",
    }

    DESTRUCTIVE_CONTEXTS: Set[str] = {
        "alle",
        "alle",
        "everything",
        "all",
        "komplett",
        "komplett",
        "complete",
        "total",
        "massenweise",
        "batch",
        "bulk",
    }

    SENSITIVE_SYSTEMS: Set[str] = {
        "datenbank",
        "database",
        "db",
        "postgres",
        "postgresql",
        "mysql",
        "mariadb",
        "vault",
        "secrets",
        "secrets",
        "production",
        "prod-cluster",
        "master-node",
        "etcd",
        "control-plane",
        "firewall",
        "gateway",
    }

    def assess(
        self,
        intent: Intent,
        normalized: NormalizedInput,
        entities: List[str],
    ) -> RiskInfo:
        """
        Assess risk level based on intent, tokens, and extracted entities.

        Returns RiskInfo with level, flags, and reason codes.
        """
        tokens = set(normalized.tokens)
        normalized_text = normalized.normalized

        # Check for delete intent (critical)
        has_delete_verb = bool(tokens & self.DELETE_VERBS)

        # Check for write intent
        has_write_verb = bool(tokens & self.WRITE_VERBS)

        # Check for production impact markers
        has_production_context = any(
            marker in normalized_text for marker in self.PRODUCTION_IMPACT_MARKERS
        )

        # Check for sensitive systems in entities
        sensitive_systems_found = [
            e for e in entities if any(s in e.lower() for s in self.SENSITIVE_SYSTEMS)
        ]
        has_sensitive_system = len(sensitive_systems_found) > 0

        # Check for destructive contexts
        has_destructive_context = bool(tokens & self.DESTRUCTIVE_CONTEXTS)

        # Determine risk level and flags
        if has_delete_verb:
            return self._build_critical_risk(
                has_sensitive_system, has_production_context, sensitive_systems_found
            )

        if has_write_verb:
            if has_destructive_context or (
                has_production_context and has_sensitive_system
            ):
                return self._build_high_risk(
                    True, True, has_production_context, sensitive_systems_found
                )
            return self._build_high_risk(
                False, False, has_production_context, sensitive_systems_found
            )

        if intent in ("investigate", "answer", "summarize", "compare"):
            return self._build_low_risk("READ_ONLY_DIAGNOSTIC")

        # Default: medium risk for unknown/unclassified actions
        return self._build_medium_risk()

    def _build_critical_risk(
        self,
        has_sensitive_system: bool,
        has_production_context: bool,
        sensitive_systems: List[str],
    ) -> RiskInfo:
        """Build RiskInfo for critical risk level."""
        reason_codes = ["DELETE_VERB_DETECTED"]

        if has_sensitive_system:
            reason_codes.append("SENSITIVE_SYSTEM_TARGET")
        if has_production_context:
            reason_codes.append("PRODUCTION_IMPACT_POSSIBLE")

        return RiskInfo(
            level="critical",
            destructive_potential=True,
            write_intent_detected=True,
            external_side_effects_possible=True,
            approval_required=True,
            reason_codes=reason_codes,
        )

    def _build_high_risk(
        self,
        destructive_potential: bool,
        external_side_effects: bool,
        has_production_context: bool,
        sensitive_systems: List[str],
    ) -> RiskInfo:
        """Build RiskInfo for high risk level."""
        reason_codes = ["WRITE_VERB_DETECTED"]

        if destructive_potential:
            reason_codes.append("DESTRUCTIVE_CONTEXT_DETECTED")
        if has_production_context:
            reason_codes.append("PRODUCTION_IMPACT_POSSIBLE")
        if sensitive_systems:
            reason_codes.append("SENSITIVE_SYSTEM_TARGET")

        return RiskInfo(
            level="high",
            destructive_potential=destructive_potential,
            write_intent_detected=True,
            external_side_effects_possible=external_side_effects
            or has_production_context,
            approval_required=True,
            reason_codes=reason_codes,
        )

    def _build_medium_risk(self) -> RiskInfo:
        """Build RiskInfo for medium risk level."""
        return RiskInfo(
            level="medium",
            destructive_potential=False,
            write_intent_detected=False,
            external_side_effects_possible=False,
            approval_required=False,
            reason_codes=["DEFAULT_CONSERVATIVE"],
        )

    def _build_low_risk(self, reason_code: str) -> RiskInfo:
        """Build RiskInfo for low risk level."""
        return RiskInfo(
            level="low",
            destructive_potential=False,
            write_intent_detected=False,
            external_side_effects_possible=False,
            approval_required=False,
            reason_codes=[reason_code],
        )


def assess_risk(
    intent: Intent,
    normalized: NormalizedInput,
    entities: List[str],
) -> RiskInfo:
    """Convenience function for risk assessment."""
    assessor = RiskAssessor()
    return assessor.assess(intent, normalized, entities)
