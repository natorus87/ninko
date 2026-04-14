"""Input normalization for deterministic text processing."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Set


@dataclass
class NormalizedInput:
    """Container for normalized input data."""

    original: str
    normalized: str
    tokens: List[str]
    stopwords_removed: List[str]


class InputNormalizer:
    """
    Normalizes user input for deterministic processing.

    Handles unicode normalization, lowercasing, special character cleanup,
    German umlaut transformation, and tokenization.
    """

    GERMAN_UMLAUT_MAP = {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
        "Ä": "ae",
        "Ö": "oe",
        "Ü": "ue",
    }

    DEFAULT_STOPWORDS: Set[str] = {
        "der",
        "die",
        "das",
        "den",
        "dem",
        "des",
        "ein",
        "eine",
        "einer",
        "einem",
        "einen",
        "und",
        "oder",
        "aber",
        "sondern",
        "denn",
        "weil",
        "obwohl",
        "obgleich",
        "als",
        "wie",
        "wenn",
        "falls",
        "damit",
        "um",
        "zu",
        "bei",
        "mit",
        "von",
        "fuer",
        "durch",
        "ueber",
        "unter",
        "vor",
        "nach",
        "in",
        "an",
        "auf",
        "aus",
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "with",
        "from",
        "to",
        "of",
        "for",
        "by",
        "at",
        "in",
        "on",
    }

    def __init__(self, stopwords: Optional[Set[str]] = None):
        self.stopwords = stopwords or self.DEFAULT_STOPWORDS

    def normalize(self, text: str, remove_stopwords: bool = False) -> NormalizedInput:
        """
        Normalize input text through the full pipeline.

        Steps:
        1. Unicode normalization (NFC)
        2. German umlaut transformation
        3. Lowercasing
        4. Special character cleanup
        5. Tokenization
        6. Optional stopword removal
        """
        original = text

        # Unicode normalization
        normalized = unicodedata.normalize("NFC", text)

        # German umlaut transformation
        normalized = self._transform_umlauts(normalized)

        # Strip diacritics for multilingual robustness (e.g., é -> e)
        normalized = self._strip_diacritics(normalized)

        # Lowercasing
        normalized = normalized.lower()

        # Special character cleanup (keep alphanumeric, spaces, hyphens)
        normalized = self._cleanup_special_chars(normalized)

        # Tokenization
        tokens = self._tokenize(normalized)

        # Stopword removal (optional)
        if remove_stopwords:
            stopwords_removed = [t for t in tokens if t not in self.stopwords]
        else:
            stopwords_removed = tokens[:]

        return NormalizedInput(
            original=original,
            normalized=normalized,
            tokens=tokens,
            stopwords_removed=stopwords_removed,
        )

    def _transform_umlauts(self, text: str) -> str:
        """Transform German umlauts to ASCII equivalents."""
        result = []
        for char in text:
            result.append(self.GERMAN_UMLAUT_MAP.get(char, char))
        return "".join(result)

    def _strip_diacritics(self, text: str) -> str:
        """Remove diacritic marks while keeping base characters."""
        decomposed = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch))

    def _cleanup_special_chars(self, text: str) -> str:
        """
        Remove special characters, keep only:
        - Alphanumeric (ASCII)
        - Whitespace
        - Hyphens (for compound words)
        - Forward slashes (for paths like prod-eu/billing)
        """
        # Replace punctuation with spaces, keep hyphens and slashes
        cleaned = re.sub(r"[^\w\s\-/]", " ", text)
        # Collapse multiple spaces
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip()

    def _tokenize(self, text: str) -> List[str]:
        """Simple whitespace tokenization."""
        if not text:
            return []
        return [t for t in text.split() if t]

    def quick_normalize(self, text: str) -> str:
        """Fast normalization for simple lookups."""
        normalized = unicodedata.normalize("NFC", text)
        normalized = self._transform_umlauts(normalized)
        normalized = self._strip_diacritics(normalized)
        normalized = normalized.lower()
        normalized = self._cleanup_special_chars(normalized)
        return normalized


# Global instance for convenient access
_default_normalizer = InputNormalizer()


def normalize(text: str, remove_stopwords: bool = False) -> NormalizedInput:
    """Normalize text using the default normalizer."""
    return _default_normalizer.normalize(text, remove_stopwords)


def quick_normalize(text: str) -> str:
    """Quick normalization for simple lookups."""
    return _default_normalizer.quick_normalize(text)
