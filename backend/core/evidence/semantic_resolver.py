"""Semantic resolver between TaskSketch and planner routing."""

from __future__ import annotations

import re
from typing import Any

from core.evidence.confidence import (
    HIGH_CONFIDENCE_THRESHOLD,
    UNCERTAIN_CONFIDENCE_THRESHOLD,
    confidence_level,
    lexical_similarity,
    normalize_term,
)
from core.evidence.glossary_store import GlossaryStore
from core.evidence.module_semantic_index import ModuleSemanticIndex
from core.evidence.schemas import FieldResolution, SemanticResolutionResult

_TOKEN_RE = re.compile(r"[\wäöüÄÖÜß-]{3,}", re.UNICODE)
_STOPWORDS = {
    "bitte",
    "prüfe",
    "prüfen",
    "pruefe",
    "pruefen",
    "check",
    "zeige",
    "warum",
    "wieso",
    "ist",
    "sind",
    "der",
    "die",
    "das",
    "und",
    "oder",
    "mit",
    "von",
    "für",
    "fuer",
    "eine",
    "einen",
    "alle",
    "bestehend",
    "bestehende",
    "bestehenden",
    "ingest",
    "ingeste",
    "ins",
    "lies",
    "meine",
    "ninko",
    "ninko wiki",
    "notiz",
    "notizen",
    "sie",
    "wiki",
}


class SemanticResolver:
    """Resolve terms, fields and semantic module candidates deterministically."""

    def __init__(
        self,
        glossary: GlossaryStore | None = None,
        module_index: ModuleSemanticIndex | None = None,
    ) -> None:
        self.glossary = glossary or GlossaryStore.with_defaults()
        self.module_index = module_index or ModuleSemanticIndex([])

    @classmethod
    def from_registry(
        cls,
        registry: Any,
        glossary: GlossaryStore | None = None,
    ) -> "SemanticResolver":
        return cls(
            glossary=glossary or GlossaryStore.with_defaults(),
            module_index=ModuleSemanticIndex.from_registry(registry),
        )

    def resolve(
        self,
        query: str,
        candidate_modules: list[str] | None = None,
    ) -> SemanticResolutionResult:
        """Resolve user terms against glossary and semantic module descriptions."""
        candidate_modules = candidate_modules or []
        candidate_module_terms = {normalize_term(module): module for module in candidate_modules}
        terms = self._extract_terms(query)
        resolutions: list[FieldResolution] = []
        unresolved_terms: list[str] = []

        for term in terms:
            if term in candidate_module_terms:
                module = candidate_module_terms[term]
                resolutions.append(FieldResolution(
                    term=term,
                    resolved_to=module,
                    source_module=module,
                    confidence="high",
                    score=1.0,
                    reason="Explicit candidate module reference",
                ))
                continue

            glossary_match = self.glossary.find_best(term)
            if glossary_match and glossary_match.score >= UNCERTAIN_CONFIDENCE_THRESHOLD:
                entry = glossary_match.entry
                resolved_to = entry.field or entry.canonical
                level = confidence_level(glossary_match.score)
                resolutions.append(FieldResolution(
                    term=term,
                    resolved_to=resolved_to,
                    source_module=entry.module,
                    confidence=level,
                    score=glossary_match.score,
                    reason=f"Glossary match via '{glossary_match.matched_alias}'",
                ))
                if level == "unresolved":
                    unresolved_terms.append(term)
                continue

            module_match = self._best_module_match(term)
            if module_match and module_match[1] >= UNCERTAIN_CONFIDENCE_THRESHOLD:
                module, score, reason = module_match
                resolutions.append(FieldResolution(
                    term=term,
                    resolved_to=module,
                    source_module=module,
                    confidence=confidence_level(score),
                    score=score,
                    reason=reason,
                ))
            else:
                unresolved_terms.append(term)

        semantic_modules = self._rank_modules(query, candidate_modules, resolutions)
        confidence = self._overall_confidence(resolutions, unresolved_terms)
        escalation_required = bool(unresolved_terms)
        escalation_reason = None
        if escalation_required:
            escalation_reason = "Unresolved semantic terms: " + ", ".join(unresolved_terms[:8])

        return SemanticResolutionResult(
            query=query,
            candidate_modules=semantic_modules,
            resolutions=resolutions,
            unresolved_terms=unresolved_terms,
            confidence=confidence,
            escalation_required=escalation_required,
            escalation_reason=escalation_reason,
        )

    def _extract_terms(self, query: str) -> list[str]:
        raw_terms = [normalize_term(match.group(0)) for match in _TOKEN_RE.finditer(query)]
        terms: list[str] = []
        for term in raw_terms:
            if term in _STOPWORDS or term in terms:
                continue
            terms.append(term)
        return terms[:16]

    def _best_module_match(self, term: str) -> tuple[str, float, str] | None:
        ranked = self.module_index.rank(term, limit=1)
        if not ranked:
            return None
        return ranked[0]

    def _rank_modules(
        self,
        query: str,
        task_sketch_modules: list[str],
        resolutions: list[FieldResolution],
    ) -> list[str]:
        scores: dict[str, float] = {}
        for index, module in enumerate(task_sketch_modules):
            scores[module] = max(scores.get(module, 0.0), 0.7 - (index * 0.05))
        for module, score, _reason in self.module_index.rank(query):
            scores[module] = max(scores.get(module, 0.0), score)
        for resolution in resolutions:
            if resolution.source_module in {"status", "business"}:
                continue
            scores[resolution.source_module] = max(
                scores.get(resolution.source_module, 0.0),
                resolution.score,
            )
        return [
            module
            for module, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
            if score >= UNCERTAIN_CONFIDENCE_THRESHOLD
        ][:4]

    def _overall_confidence(
        self,
        resolutions: list[FieldResolution],
        unresolved_terms: list[str],
    ) -> float:
        if not resolutions and unresolved_terms:
            return 0.0
        if not resolutions:
            return 1.0
        average = sum(resolution.score for resolution in resolutions) / len(resolutions)
        unresolved_penalty = min(len(unresolved_terms) * 0.12, 0.5)
        high_bonus = 0.05 if all(
            resolution.score >= HIGH_CONFIDENCE_THRESHOLD for resolution in resolutions
        ) else 0.0
        return max(0.0, min(1.0, average - unresolved_penalty + high_bonus))


def field_mapping_confidence(left: str, right: str) -> FieldResolution:
    """Resolve heterogeneous field names to a canonical field with confidence."""
    score = lexical_similarity(left, right)
    known_business_partner_aliases = {
        "businesspartner id",
        "gp id",
        "business partner id",
    }
    is_known_business_partner = (
        normalize_term(left) in known_business_partner_aliases
        and normalize_term(right) in known_business_partner_aliases
    )
    if is_known_business_partner:
        canonical = "business_partner_id"
        score = max(score, 0.72)
    else:
        canonical = right
    return FieldResolution(
        term=left,
        resolved_to=canonical,
        source_module="field_mapping",
        confidence=confidence_level(score),
        score=score,
        reason=f"Field-name similarity to '{right}'",
    )
