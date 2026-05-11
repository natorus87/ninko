"""Unit tests for the Function Calling routing implementation."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import agents.orchestrator as orchestrator
from agents.orchestrator import OrchestratorAgent


def _agent_with_manifests(manifests: list[SimpleNamespace]) -> OrchestratorAgent:
    agent = object.__new__(OrchestratorAgent)
    agent.registry = SimpleNamespace(list_modules=lambda: manifests)
    return agent


class TestNormalizeQueryForCache:
    def test_deterministic(self) -> None:
        n1 = OrchestratorAgent._normalize_query_for_cache("show pods")
        n2 = OrchestratorAgent._normalize_query_for_cache("show pods")
        assert n1 == n2

    def test_lowercase(self) -> None:
        n1 = OrchestratorAgent._normalize_query_for_cache("Show Pods")
        n2 = OrchestratorAgent._normalize_query_for_cache("show pods")
        assert n1 == n2

    def test_whitespace_collapsed(self) -> None:
        n1 = OrchestratorAgent._normalize_query_for_cache("show   pods")
        n2 = OrchestratorAgent._normalize_query_for_cache("show pods")
        assert n1 == n2

    def test_punctuation_removed(self) -> None:
        n1 = OrchestratorAgent._normalize_query_for_cache("show pods!")
        n2 = OrchestratorAgent._normalize_query_for_cache("show pods")
        assert n1 == n2

    def test_sha256_format(self) -> None:
        normalized = OrchestratorAgent._normalize_query_for_cache("test")
        assert len(normalized) == 64
        assert all(c in "0123456789abcdef" for c in normalized)


class TestExtractToolCalls:
    def test_empty_tool_calls(self) -> None:
        class Empty:
            tool_calls = []

        agent = _agent_with_manifests([])
        assert agent._extract_tool_calls(Empty()) == []

    def test_none_tool_calls(self) -> None:
        class NoTc:
            tool_calls = None

        agent = _agent_with_manifests([])
        assert agent._extract_tool_calls(NoTc()) == []

    def test_dict_style_args(self) -> None:
        class DictStyle:
            tool_calls = [{"name": "kubernetes", "args": {"query": "show pods"}}]

        agent = _agent_with_manifests([])
        result = agent._extract_tool_calls(DictStyle())
        assert result == [{"name": "kubernetes", "arguments": {"query": "show pods"}}]

    def test_dict_style_arguments(self) -> None:
        class DictStyle:
            tool_calls = [{"name": "telegram", "arguments": {"query": "notify"}}]

        agent = _agent_with_manifests([])
        result = agent._extract_tool_calls(DictStyle())
        assert result[0]["arguments"] == {"query": "notify"}

    def test_no_arguments_fallback_to_empty_dict(self) -> None:
        class NoArgs:
            tool_calls = [{"name": "kubernetes"}]

        agent = _agent_with_manifests([])
        result = agent._extract_tool_calls(NoArgs())
        assert result[0]["arguments"] == {}


class TestBuildToolsSchema:
    def test_schema_structure(self) -> None:
        agent = _agent_with_manifests(
            [
                SimpleNamespace(name="kubernetes", description="Cluster management"),
                SimpleNamespace(name="pihole", description="DNS blocking"),
            ]
        )
        schema = agent._build_module_tools_schema()
        assert len(schema) == 2
        assert schema[0]["type"] == "function"
        assert schema[0]["function"]["name"] == "kubernetes"
        assert schema[0]["function"]["parameters"]["type"] == "object"
        assert "query" in schema[0]["function"]["parameters"]["properties"]

    def test_empty_description_handled(self) -> None:
        agent = _agent_with_manifests([SimpleNamespace(name="test", description="")])
        schema = agent._build_module_tools_schema()
        assert schema[0]["function"]["description"] == ""

    def test_none_description_becomes_empty_string(self) -> None:
        agent = _agent_with_manifests([SimpleNamespace(name="test", description=None)])
        schema = agent._build_module_tools_schema()
        assert schema[0]["function"]["description"] == ""

    def test_empty_manifests(self) -> None:
        agent = _agent_with_manifests([])
        assert agent._build_module_tools_schema() == []

    def test_query_field_is_required(self) -> None:
        agent = _agent_with_manifests([SimpleNamespace(name="test", description="desc")])
        schema = agent._build_module_tools_schema()
        assert "query" in schema[0]["function"]["parameters"]["required"]

    def test_query_field_type_is_string(self) -> None:
        agent = _agent_with_manifests([SimpleNamespace(name="test", description="desc")])
        schema = agent._build_module_tools_schema()
        assert schema[0]["function"]["parameters"]["properties"]["query"]["type"] == "string"


class TestRoutingMode:
    @pytest.mark.asyncio
    async def test_routing_mode_reads_redis_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        agent = _agent_with_manifests([])
        monkeypatch.setattr(
            orchestrator,
            "get_settings",
            lambda: SimpleNamespace(LLM_ENABLE_FUNCTION_CALLING=True, LLM_TOOL_CHOICE="auto"),
        )
        redis = SimpleNamespace(
            connection=SimpleNamespace(
                get=AsyncMock(
                    return_value=json.dumps(
                        {"function_calling_enabled": False, "tool_choice": "none"}
                    )
                )
            )
        )
        monkeypatch.setattr(orchestrator, "get_redis", lambda: redis)

        enabled, tool_choice = await agent._get_routing_mode()

        assert enabled is False
        assert tool_choice == "none"


class TestRoutingContext:
    def test_recent_routing_context_keeps_previous_module_answer(self) -> None:
        context = OrchestratorAgent._recent_routing_context(
            [
                {"role": "user", "content": "Wie ist der Status meiner FritzBox?"},
                {"role": "assistant", "content": "Hier ist der aktuelle Status deiner FRITZ!Box 7590 AX."},
            ]
        )

        assert "FritzBox" in context
        assert "FRITZ!Box" in context

    def test_recent_routing_context_ignores_empty_and_unknown_roles(self) -> None:
        context = OrchestratorAgent._recent_routing_context(
            [
                {"role": "tool", "content": "internal"},
                {"role": "assistant", "content": ""},
                {"role": "user", "content": "wieviele geräte sind aktuell verbunden?"},
            ]
        )

        assert "internal" not in context
        assert "wieviele geräte" in context


class TestPipelineStepGeneration:
    def test_single_tool_call_generates_single_step(self) -> None:
        tool_calls = [{"name": "kubernetes", "arguments": {"query": "show pods"}}]
        steps = [{"module": tc["name"], "task": tc["arguments"].get("query", "")} for tc in tool_calls]
        assert len(steps) == 1
        assert steps[0]["module"] == "kubernetes"

    def test_multiple_tool_calls_generate_multiple_steps(self) -> None:
        tool_calls = [
            {"name": "kubernetes", "arguments": {"query": "check pods"}},
            {"name": "telegram", "arguments": {"query": "notify"}},
        ]
        steps = [{"module": tc["name"], "task": tc["arguments"].get("query", "")} for tc in tool_calls]
        assert len(steps) == 2

    def test_compound_intent_step_order_preserved(self) -> None:
        tool_calls = [
            {"name": "kubernetes", "arguments": {"query": "restart nginx"}},
            {"name": "telegram", "arguments": {"query": "notify team"}},
        ]
        steps = [{"module": tc["name"], "task": tc["arguments"].get("query", "")} for tc in tool_calls]
        assert steps[0]["module"] == "kubernetes"
        assert steps[1]["module"] == "telegram"
