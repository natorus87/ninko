"""Deterministic confidence scoring helpers for the evidence layer."""

from __future__ import annotations

from difflib import SequenceMatcher

from core.evidence.schemas import ConfidenceLevel

HIGH_CONFIDENCE_THRESHOLD = 0.78
UNCERTAIN_CONFIDENCE_THRESHOLD = 0.45


def normalize_term(value: str) -> str:
    """Normalize text for deterministic matching."""
    return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())


def lexical_similarity(left: str, right: str) -> float:
    """Return a stable 0..1 similarity score for two strings."""
    left_norm = normalize_term(left)
    right_norm = normalize_term(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(overlap, sequence)


def confidence_level(score: float) -> ConfidenceLevel:
    """Map a numeric score to the evidence layer's public confidence levels."""
    if score >= HIGH_CONFIDENCE_THRESHOLD:
        return "high"
    if score >= UNCERTAIN_CONFIDENCE_THRESHOLD:
        return "uncertain"
    return "unresolved"
