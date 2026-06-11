"""
Ninko – Pydantic-Response-Modelle fuer Routing-Admin-Endpoints (routes_routing.py).

Schemas fuer:
  - GET    /api/routing/corrections   → Korrektur-Statistiken
  - DELETE /api/routing/corrections   → Reset
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoutingStatsResponse(BaseModel):
    """Aggregierte Routing-Korrektur-Statistiken."""
    total: int = 0
    by_pair: dict[str, int] = Field(default_factory=dict)
    recent: list[dict] = Field(default_factory=list)


class RoutingResetResponse(BaseModel):
    """Antwort nach Reset (DELETE /api/routing/corrections)."""
    status: str  # "reset" | "noop"
