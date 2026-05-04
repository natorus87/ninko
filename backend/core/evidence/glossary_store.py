"""Configurable key-value glossary backend for semantic resolution."""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.evidence.confidence import lexical_similarity, normalize_term


class GlossaryEntry(BaseModel):
    """One canonical domain concept and its aliases."""

    canonical: str
    aliases: list[str] = Field(default_factory=list)
    module: str
    field: str | None = None
    description: str = ""

    def terms(self) -> list[str]:
        return [self.canonical, *self.aliases]


class GlossaryMatch(BaseModel):
    """Best glossary match for an input term."""

    term: str
    entry: GlossaryEntry
    score: float
    matched_alias: str


class GlossaryStore:
    """In-memory glossary store; replaceable by RAG/vector backend later."""

    def __init__(self, entries: list[GlossaryEntry] | None = None) -> None:
        self._entries = entries or []

    @classmethod
    def with_defaults(cls) -> "GlossaryStore":
        return cls([
            GlossaryEntry(
                canonical="postgresql",
                aliases=["postgres", "datenbank", "database", "sql", "fakturaverarbeitung"],
                module="postgresql",
                field="database",
                description="PostgreSQL database and invoice processing storage",
            ),
            GlossaryEntry(
                canonical="business_partner_id",
                aliases=[
                    "businesspartner_id",
                    "business partner",
                    "gp_id",
                    "GP_Id",
                    "geschäftspartner",
                ],
                module="business",
                field="business_partner_id",
                description="Canonical business partner identifier",
            ),
            GlossaryEntry(
                canonical="blocked_status",
                aliases=["blockiert", "blocked", "sperre", "störung", "failure", "failed"],
                module="status",
                field="status",
                description="Status values that indicate a blocked process",
            ),
        ])

    def add(self, entry: GlossaryEntry) -> None:
        self._entries.append(entry)

    def entries(self) -> list[GlossaryEntry]:
        return list(self._entries)

    def find_best(self, term: str) -> GlossaryMatch | None:
        """Find the closest glossary entry for a term."""
        normalized = normalize_term(term)
        if not normalized:
            return None

        best: GlossaryMatch | None = None
        for entry in self._entries:
            for alias in entry.terms():
                alias_norm = normalize_term(alias)
                if not alias_norm:
                    continue
                if alias_norm in normalized or normalized in alias_norm:
                    score = 1.0 if alias_norm == normalized else 0.86
                else:
                    score = lexical_similarity(normalized, alias_norm)
                    if score < 0.78:
                        continue
                if best is None or score > best.score:
                    best = GlossaryMatch(term=term, entry=entry, score=score, matched_alias=alias)
        return best
