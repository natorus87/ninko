"""Module ranking based on keyword and entity matching."""

from __future__ import annotations

from typing import Dict, List, Optional

from core.prestructure.schemas import RankedModule, ModuleMetadata, ScopeEntities
from core.prestructure.normalizer import NormalizedInput


class ModuleRanker:
    """
    Rank module candidates based on deterministic scoring.

    Uses keyword matching, entity correlation, and domain alignment
    to produce reproducible module rankings.
    """

    # Scoring weights (sum should be <= 1.0 for any single match)
    SCORE_MODULE_NAME_EXACT = 0.50
    SCORE_KEYWORD_EXACT = 0.20
    SCORE_ENTITY_MATCH = 0.15
    SCORE_DOMAIN_ALIGN = 0.10
    SCORE_WEAK_ALIAS = 0.05
    SCORE_CONFLICT_PENALTY = -0.10

    # Maximum score cap
    MAX_SCORE = 1.0

    def __init__(self, module_metadata: List[ModuleMetadata]):
        self.modules = {m.name: m for m in module_metadata}

    def rank(
        self,
        normalized: NormalizedInput,
        entities: ScopeEntities,
        top_n: int = 5,
    ) -> List[RankedModule]:
        """
        Rank modules based on tokens and extracted entities.

        Returns top-N candidates with scores and reasoning.
        """
        tokens = normalized.tokens
        normalized_text = normalized.normalized

        ranked: List[RankedModule] = []

        for name, module in self.modules.items():
            score, reasons = self._calculate_score(
                module, tokens, normalized_text, entities
            )

            if score > 0:
                ranked.append(
                    RankedModule(
                        module=name,
                        score=min(score, self.MAX_SCORE),
                        reasons=reasons,
                    )
                )

        # Sort by score descending
        ranked.sort(key=lambda x: x.score, reverse=True)

        # Return top N
        return ranked[:top_n]

    def _calculate_score(
        self,
        module: ModuleMetadata,
        tokens: List[str],
        normalized_text: str,
        entities: ScopeEntities,
    ) -> tuple[float, List[str]]:
        """Calculate score for a single module."""
        score = 0.0
        reasons: List[str] = []

        module_name_lower = module.name.lower()

        # Exact module name match
        if module_name_lower in tokens:
            score += self.SCORE_MODULE_NAME_EXACT
            reasons.append(f"module_name:{module.name}")
        elif module_name_lower in normalized_text:
            score += self.SCORE_MODULE_NAME_EXACT
            reasons.append(f"module_name:{module.name}")

        # Keyword matches
        keyword_hits = 0
        for keyword in module.keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in tokens:
                score += self.SCORE_KEYWORD_EXACT
                keyword_hits += 1
                reasons.append(f"keyword:{keyword}")
            elif keyword_lower in normalized_text:
                # Phrase match (e.g., "merge request")
                score += self.SCORE_KEYWORD_EXACT
                keyword_hits += 1
                reasons.append(f"keyword_phrase:{keyword}")

        # Entity matches
        entity_matches: List[str] = []
        for entity_type in [entities.systems, entities.services, entities.resources]:
            for entity in entity_type:
                entity_lower = entity.lower()
                if entity_lower in [e.lower() for e in module.entities]:
                    entity_matches.append(entity)
                elif entity_lower in module.keywords:
                    entity_matches.append(entity)

        if entity_matches:
            score += min(len(entity_matches) * self.SCORE_ENTITY_MATCH, 0.30)
            for em in set(entity_matches):
                reasons.append(f"entity:{em}")

        # Domain alignment
        if self._domain_aligns(module, entities):
            score += self.SCORE_DOMAIN_ALIGN
            reasons.append(f"domain:{module.domain}")

        return score, reasons

    def _domain_aligns(self, module: ModuleMetadata, entities: ScopeEntities) -> bool:
        """Check if module domain aligns with extracted entities."""
        # Check if module domain matches any system entity
        for system in entities.systems:
            if module.domain in system or system in module.domain:
                return True

        # Check specific domain mappings
        domain_mappings: Dict[str, List[str]] = {
            "kubernetes": ["cluster", "pod", "deployment", "namespace"],
            "gitlab": ["gitlab", "pipeline", "mr", "runner"],
            "database": ["postgres", "mysql", "redis", "sql"],
            "monitoring": ["checkmk", "prometheus", "grafana", "alert"],
            "network": ["traefik", "nginx", "ingress", "firewall"],
        }

        if module.domain in domain_mappings:
            indicators = domain_mappings[module.domain]
            for indicator in indicators:
                if any(indicator in entity for entity in entities.systems):
                    return True
                if any(indicator in entity for entity in entities.services):
                    return True

        return False

    def find_best_match(
        self,
        normalized: NormalizedInput,
        entities: ScopeEntities,
    ) -> Optional[RankedModule]:
        """Find the single best matching module."""
        ranked = self.rank(normalized, entities, top_n=1)
        return ranked[0] if ranked else None


def rank_modules(
    normalized: NormalizedInput,
    entities: ScopeEntities,
    module_metadata: List[ModuleMetadata],
    top_n: int = 5,
) -> List[RankedModule]:
    """Convenience function for module ranking."""
    ranker = ModuleRanker(module_metadata)
    return ranker.rank(normalized, entities, top_n)


def create_module_metadata_from_registry(registry) -> List[ModuleMetadata]:
    """
    Create ModuleMetadata list from the ModuleRegistry.

    Uses the global registry to extract deterministic metadata for ranking.
    """
    metadata: List[ModuleMetadata] = []

    for manifest in registry.list_modules():
        metadata.append(
            ModuleMetadata(
                name=manifest.name,
                keywords=manifest.routing_keywords,
                entities=[],
                domain=_infer_domain_from_keywords(manifest.routing_keywords),
                read_only_capabilities=manifest.agent_capabilities or [],
                write_capabilities=[],
            )
        )

    return metadata


def _infer_domain_from_keywords(keywords: List[str]) -> str:
    """Infer domain from routing keywords."""
    keyword_set = {k.lower() for k in keywords}

    if any(k in keyword_set for k in ["kubernetes", "k8s", "pod", "cluster"]):
        return "kubernetes"
    if any(k in keyword_set for k in ["gitlab", "pipeline", "runner"]):
        return "gitlab"
    if any(k in keyword_set for k in ["postgres", "mysql", "database", "sql"]):
        return "database"
    if any(k in keyword_set for k in ["checkmk", "monitoring", "alert"]):
        return "monitoring"
    if any(k in keyword_set for k in ["traefik", "nginx", "firewall", "network"]):
        return "network"

    return "general"
