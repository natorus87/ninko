"""Semantic index over module descriptions, capabilities and routing keywords."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.evidence.confidence import lexical_similarity


@dataclass(frozen=True)
class ModuleSemanticDocument:
    name: str
    text: str
    fields: tuple[str, ...] = ()


class ModuleSemanticIndex:
    """Small deterministic module index used before introducing vector search."""

    def __init__(self, documents: list[ModuleSemanticDocument]) -> None:
        self._documents = documents

    @classmethod
    def from_registry(cls, registry: Any) -> "ModuleSemanticIndex":
        documents: list[ModuleSemanticDocument] = []
        for module in registry.list_modules():
            parts = [
                module.name,
                getattr(module, "display_name", ""),
                getattr(module, "description", ""),
                " ".join(getattr(module, "routing_keywords", []) or []),
                " ".join(getattr(module, "agent_capabilities", []) or []),
            ]
            documents.append(ModuleSemanticDocument(name=module.name, text=" ".join(parts)))
        return cls(documents)

    def rank(self, query: str, limit: int = 4) -> list[tuple[str, float, str]]:
        """Return ranked module candidates as (module, score, reason)."""
        ranked: list[tuple[str, float, str]] = []
        for document in self._documents:
            score = lexical_similarity(query, document.text)
            if score > 0:
                ranked.append((document.name, score, "semantic module description match"))
        ranked.sort(key=lambda item: item[1], reverse=True)
        return ranked[:limit]
