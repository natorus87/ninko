"""
Ninko Metrics API – Token-Usage und Cost Tracking.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

from core.metrics import get_token_metrics, get_token_metrics_range
from core.auth import auth_tenant_id, resolve_request_auth

logger = logging.getLogger("ninko.api.metrics")
router = APIRouter(prefix="/api/metrics", tags=["Metrics"])


class AgentTokenMetrics(BaseModel):
    """Token-Metrics für einen Agenten."""

    prompt: int = 0
    completion: int = 0
    total: int = 0
    cost_usd: float = 0.0


class TokenMetricsResponse(BaseModel):
    """Response für Token-Metrics."""

    date: str
    agents: dict[str, AgentTokenMetrics]
    totals: AgentTokenMetrics


class TokenMetricsRangeResponse(BaseModel):
    """Response für Token-Metrics über einen Zeitraum."""

    since: str
    until: str
    agents: dict[str, AgentTokenMetrics]
    totals: AgentTokenMetrics


@router.get("/tokens", response_model=TokenMetricsResponse)
async def get_token_usage_metrics(
    request: Request,
    date: str | None = Query(
        None, description="ISO-Datum (YYYY-MM-DD), default: heute"
    ),
    agent_name: str | None = Query(None, description="Filter nach Agent"),
) -> TokenMetricsResponse:
    """
    Holt Token-Usage-Metrics für ein spezifisches Datum.

    Returns:
        Token-Metrics pro Agent und aggregierte Totals.
    """
    _ = auth_tenant_id(resolve_request_auth(request))

    data = await get_token_metrics(date=date, agent_name=agent_name)

    # Konvertiere zu Pydantic-Modellen
    agents = {
        name: AgentTokenMetrics(**metrics)
        for name, metrics in data.get("agents", {}).items()
    }
    totals = AgentTokenMetrics(**data.get("totals", {}))

    return TokenMetricsResponse(
        date=data.get("date", date or "today"),
        agents=agents,
        totals=totals,
    )


@router.get("/tokens/range", response_model=TokenMetricsRangeResponse)
async def get_token_usage_range(
    request: Request,
    since: str = Query(..., description="Start-Datum (YYYY-MM-DD)"),
    until: str | None = Query(
        None, description="End-Datum (YYYY-MM-DD), default: heute"
    ),
) -> TokenMetricsRangeResponse:
    """
    Aggregiert Token-Usage-Metrics über einen Datumsbereich.

    Returns:
        Aggregierte Token-Metrics über alle Tage im Bereich.
    """
    _ = auth_tenant_id(resolve_request_auth(request))

    data = await get_token_metrics_range(since=since, until=until)

    agents = {
        name: AgentTokenMetrics(**metrics)
        for name, metrics in data.get("agents", {}).items()
    }
    totals = AgentTokenMetrics(**data.get("totals", {}))

    return TokenMetricsRangeResponse(
        since=data.get("since", since),
        until=data.get("until", until or "today"),
        agents=agents,
        totals=totals,
    )
