"""Lifecycle helpers for non-interactive agent approval requests."""

from __future__ import annotations

from typing import Any


async def discard_pending_approval(
    session_id: str,
    *,
    redis: Any = None,
) -> None:
    """Ask the safeguard owner to discard a run that cannot be resumed."""
    from agents.base_agent import discard_pending_safeguard

    await discard_pending_safeguard(session_id, redis=redis)
