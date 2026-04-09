"""
Ninko Metrics – Token-Usage und Cost Tracking für LLM-Calls.

Baut auf dem Event-System aus Phase 1 auf.
Speichert Token-Usage pro Agent und Tag in Redis.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.redis_client import get_redis
from core.config import get_settings

logger = logging.getLogger("ninko.metrics")

_KEY_PREFIX = "ninko:metrics:tokens"


@dataclass
class TokenUsage:
    """Token-Usage für einen LLM-Call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float = 0.0


@dataclass
class LLMProviderCosts:
    """Kosten-Konfiguration für einen LLM Provider."""

    cost_per_1k_input: float = 0.0
    cost_per_1k_output: float = 0.0
    is_cloud_provider: bool = False


def _get_provider_costs() -> LLMProviderCosts:
    """
    Lädt die Kosten-Konfiguration aus den Settings.

    Für lokale Provider (Ollama, LM Studio) sind die Kosten 0.
    Für Cloud-Provider können Kosten pro 1k Tokens konfiguriert werden.
    """
    try:
        settings = get_settings()
        backend = getattr(settings, "LLM_BACKEND", "ollama").lower()

        # Lokale Provider haben keine Kosten
        if backend in ("ollama", "lmstudio", "local"):
            return LLMProviderCosts(is_cloud_provider=False)

        # Cloud-Provider: Kosten aus Settings laden (falls konfiguriert)
        cost_input = float(getattr(settings, "LLM_COST_PER_1K_INPUT", 0.0) or 0.0)
        cost_output = float(getattr(settings, "LLM_COST_PER_1K_OUTPUT", 0.0) or 0.0)

        return LLMProviderCosts(
            cost_per_1k_input=cost_input,
            cost_per_1k_output=cost_output,
            is_cloud_provider=True,
        )
    except Exception:
        return LLMProviderCosts(is_cloud_provider=False)


def _calculate_cost(usage: TokenUsage, costs: LLMProviderCosts) -> float:
    """
    Berechnet die Kosten für einen LLM-Call.

    Formula: (prompt_tokens / 1000 * cost_per_1k_input) +
             (completion_tokens / 1000 * cost_per_1k_output)
    """
    if not costs.is_cloud_provider:
        return 0.0

    input_cost = (usage.prompt_tokens / 1000.0) * costs.cost_per_1k_input
    output_cost = (usage.completion_tokens / 1000.0) * costs.cost_per_1k_output

    return round(input_cost + output_cost, 6)


async def record_llm_tokens(
    agent_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int | None = None,
) -> None:
    """
    Speichert Token-Usage für einen Agenten in Redis.

    Args:
        agent_name: Name des Agenten
        prompt_tokens: Anzahl Input-Tokens
        completion_tokens: Anzahl Output-Tokens
        total_tokens: Gesamt-Tokens (optional, default: prompt + completion)
    """
    try:
        redis = get_redis()
        if redis is None:
            return

        total = total_tokens or (prompt_tokens + completion_tokens)
        costs = _get_provider_costs()

        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
        )
        usage.cost_usd = _calculate_cost(usage, costs)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_KEY_PREFIX}:{date_str}"

        # HINCRBY für atomare Zählung pro Agent
        field = agent_name or "unknown"

        # Aktuelle Werte holen und addieren
        current = await redis.connection.hget(key, field)
        if current:
            try:
                data = json.loads(current)
                prompt_tokens += data.get("prompt", 0)
                completion_tokens += data.get("completion", 0)
                total = prompt_tokens + completion_tokens
                usage.cost_usd += data.get("cost_usd", 0.0)
            except json.JSONDecodeError:
                pass

        # Speichern
        value = json.dumps(
            {
                "prompt": prompt_tokens,
                "completion": completion_tokens,
                "total": total,
                "cost_usd": round(usage.cost_usd, 6),
            }
        )

        pipe = redis.connection.pipeline()
        pipe.hset(key, field, value)
        pipe.expire(key, 86400 * 30)  # 30 Tage Retention
        await pipe.execute()

        logger.debug(
            "Token-Usage recorded: %s | prompt=%d, completion=%d, cost=$%.6f",
            agent_name,
            prompt_tokens,
            completion_tokens,
            usage.cost_usd,
        )

    except Exception as exc:
        logger.debug("Token-Tracking fehlgeschlagen (ignoriert): %s", exc)


async def get_token_metrics(
    date: str | None = None,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """
    Holt Token-Metrics für ein Datum oder alle Agenten.

    Args:
        date: ISO-Datum (YYYY-MM-DD) oder None für heute
        agent_name: Optional Filter nach Agent

    Returns:
        Dict mit metrics pro Agent und totals
    """
    try:
        redis = get_redis()
        if redis is None:
            return {"date": date or "today", "agents": {}, "totals": {}}

        date_str = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_KEY_PREFIX}:{date_str}"

        if agent_name:
            # Einzelner Agent
            data = await redis.connection.hget(key, agent_name)
            if not data:
                return {"date": date_str, "agents": {}, "totals": {}}

            try:
                metrics = json.loads(data)
                return {
                    "date": date_str,
                    "agents": {agent_name: metrics},
                    "totals": metrics,
                }
            except json.JSONDecodeError:
                return {"date": date_str, "agents": {}, "totals": {}}
        else:
            # Alle Agenten
            all_data = await redis.connection.hgetall(key)
            agents: dict[str, dict] = {}

            total_prompt = 0
            total_completion = 0
            total_cost = 0.0

            for field, value in all_data.items():
                try:
                    agent = field.decode() if isinstance(field, bytes) else field
                    metrics = json.loads(
                        value.decode() if isinstance(value, bytes) else value
                    )
                    agents[agent] = metrics

                    total_prompt += metrics.get("prompt", 0)
                    total_completion += metrics.get("completion", 0)
                    total_cost += metrics.get("cost_usd", 0.0)
                except (json.JSONDecodeError, AttributeError):
                    continue

            return {
                "date": date_str,
                "agents": agents,
                "totals": {
                    "prompt": total_prompt,
                    "completion": total_completion,
                    "total": total_prompt + total_completion,
                    "cost_usd": round(total_cost, 6),
                },
            }

    except Exception as exc:
        logger.warning("Token-Metrics Query fehlgeschlagen: %s", exc)
        return {"date": date or "today", "agents": {}, "totals": {}}


async def get_token_metrics_range(
    since: str,
    until: str | None = None,
) -> dict[str, Any]:
    """
    Aggregiert Token-Metrics über einen Datumsbereich.

    Args:
        since: Start-Datum (YYYY-MM-DD)
        until: End-Datum (YYYY-MM-DD) oder None für heute

    Returns:
        Aggregierte Metrics über alle Tage im Bereich
    """
    try:
        redis = get_redis()
        if redis is None:
            return {"since": since, "until": until, "agents": {}, "totals": {}}

        until_str = until or datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Alle Tage im Bereich abfragen
        from datetime import datetime as dt

        start = dt.strptime(since, "%Y-%m-%d")
        end = dt.strptime(until_str, "%Y-%m-%d")

        aggregated: dict[str, dict] = {}
        total_prompt = 0
        total_completion = 0
        total_cost = 0.0

        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            key = f"{_KEY_PREFIX}:{date_str}"

            try:
                day_data = await redis.connection.hgetall(key)
                for field, value in day_data.items():
                    try:
                        agent = field.decode() if isinstance(field, bytes) else field
                        metrics = json.loads(
                            value.decode() if isinstance(value, bytes) else value
                        )

                        if agent not in aggregated:
                            aggregated[agent] = {
                                "prompt": 0,
                                "completion": 0,
                                "total": 0,
                                "cost_usd": 0.0,
                            }

                        aggregated[agent]["prompt"] += metrics.get("prompt", 0)
                        aggregated[agent]["completion"] += metrics.get("completion", 0)
                        aggregated[agent]["total"] += metrics.get("total", 0)
                        aggregated[agent]["cost_usd"] += metrics.get("cost_usd", 0.0)

                        total_prompt += metrics.get("prompt", 0)
                        total_completion += metrics.get("completion", 0)
                        total_cost += metrics.get("cost_usd", 0.0)
                    except (json.JSONDecodeError, AttributeError):
                        continue
            except Exception:
                pass

            current = dt.fromordinal(current.toordinal() + 1)

        # Runden
        for agent in aggregated:
            aggregated[agent]["cost_usd"] = round(aggregated[agent]["cost_usd"], 6)

        return {
            "since": since,
            "until": until_str,
            "agents": aggregated,
            "totals": {
                "prompt": total_prompt,
                "completion": total_completion,
                "total": total_prompt + total_completion,
                "cost_usd": round(total_cost, 6),
            },
        }

    except Exception as exc:
        logger.warning("Token-Metrics Range Query fehlgeschlagen: %s", exc)
        return {"since": since, "until": until, "agents": {}, "totals": {}}
