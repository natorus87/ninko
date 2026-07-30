"""Regression tests for request-bound safeguard tool confirmations."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents import base_agent
from agents.base_agent import BaseAgent


@pytest.mark.asyncio
async def test_resume_rejects_stale_approval_id_for_identical_tool_call() -> None:
    session_id = "default:tool-confirmation"
    agent = object.__new__(BaseAgent)
    agent.name = "test-agent"
    redis = SimpleNamespace(
        connection=SimpleNamespace(
            get=AsyncMock(
                return_value=json.dumps(
                    {"approval_id": "current-approval"}
                )
            )
        )
    )
    base_agent._paused_sg_agents[session_id] = (MagicMock(), {})
    base_agent._paused_sg_agents_ts[session_id] = 0.0

    try:
        with patch("core.redis_client.get_redis", return_value=redis):
            response, did_compact = await agent.resume_safeguard_tool(
                session_id,
                expected_approval_id="stale-approval",
            )
    finally:
        base_agent._paused_sg_agents.pop(session_id, None)
        base_agent._paused_sg_agents_ts.pop(session_id, None)

    assert "nicht mehr gültig" in response
    assert did_compact is False
