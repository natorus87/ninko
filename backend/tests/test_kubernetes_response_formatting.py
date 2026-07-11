"""Regression tests for Kubernetes chat response formatting."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agents.middleware.base import MiddlewareContext
from agents.middleware.postprocess import (
    ResponseExtractionMiddleware,
    _format_kubernetes_tool_fallback,
)


def _import_real_base_agent():
    import importlib
    import sys

    import agents
    import agents.base_agent as base_agent

    if not hasattr(base_agent, "get_memory"):
        sys.modules.pop("agents.base_agent", None)
        if hasattr(agents, "base_agent"):
            delattr(agents, "base_agent")
        base_agent = importlib.import_module("agents.base_agent")
    return base_agent


def test_kubernetes_node_tool_output_formats_as_markdown_table() -> None:
    raw = """[
      {
        "name": "hz-cb-ub-01",
        "status": "Ready",
        "roles": ["<none>"],
        "version": "v1.32.9",
        "os_image": "Ubuntu 24.04.3 LTS",
        "internal_ip": "192.168.1.23",
        "age": "146d0h"
      }
    ]"""

    formatted = _format_kubernetes_tool_fallback(raw, tool_name="list_nodes")

    assert "| Name | Status | Roles | Version | Internal IP | OS | Age |" in formatted
    assert "| hz-cb-ub-01 | Ready | <none> | v1.32.9 | 192.168.1.23 | Ubuntu 24.04.3 LTS | 146d0h |" in formatted
    assert "```json" not in formatted


@pytest.mark.asyncio
async def test_kubernetes_short_ai_response_gets_tool_table_appended() -> None:
    middleware = ResponseExtractionMiddleware()
    ctx = MiddlewareContext(
        agent_name="kubernetes",
        result={
            "messages": [
                ToolMessage(
                    content="{'nodes': 1, 'namespaces': 7, 'total_pods': 19, "
                    "'running_pods': 19, 'failing_pods': 0, 'deployments': 15}",
                    tool_call_id="call-1",
                    name="get_cluster_status",
                ),
                AIMessage(
                    content="Der Cluster ist gesund. Alle 19 Pods laufen, keine Ausfälle."
                ),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "Der Cluster ist gesund" in ctx.response
    assert "| Metrik | Wert |" in ctx.response
    assert "| Status | ✅ Gesund |" in ctx.response
    assert "| Pods gesamt | 19 |" in ctx.response


@pytest.mark.asyncio
async def test_leaked_tool_plan_narration_is_stripped_from_final_response() -> None:
    """Regression: the model sometimes leaks its tool-calling plan as prose into
    the final (no-more-tool_calls) message instead of only the user-facing
    answer, with no separator between narration and real content."""
    middleware = ResponseExtractionMiddleware()
    ctx = MiddlewareContext(
        agent_name="kubernetes",
        result={
            "messages": [
                AIMessage(
                    content=(
                        "I will call get_cluster_status to get the overall cluster status.\n"
                        "I will call list_namespaces to confirm the licium namespace exists.\n"
                        "I will call list_ingresses with namespace=\"licium\" to check for services.\n"
                        "I will call list_endpoints with namespace=\"licium\" to check for active services.\n"
                        "This avoids the non-existent list_pods tool and uses the available tools "
                        "to provide a status overview.✅ Status des licium Namespaces\n\n"
                        "Der Namespace licium ist aktiv und im Cluster vorhanden.\n\n"
                        "| Namespace | Status |\n|---|---|\n| licium | ✅ Active |\n"
                    )
                ),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response.startswith("✅ Status des licium Namespaces")
    assert "I will call" not in ctx.response
    assert "| licium | ✅ Active |" in ctx.response


@pytest.mark.asyncio
async def test_legitimate_response_starting_with_i_will_is_not_touched() -> None:
    """The narration filter must not touch replies that merely happen to open
    with an "I will …" sentence unrelated to tool-calling."""
    middleware = ResponseExtractionMiddleware()
    original = (
        "I will explain how Kubernetes namespaces work in general terms.\n\n"
        "## Übersicht\nNamespaces isolieren Ressourcen innerhalb eines Clusters."
    )
    ctx = MiddlewareContext(
        agent_name="kubernetes",
        result={"messages": [AIMessage(content=original)]},
    )

    await middleware.post_process(ctx)

    assert ctx.response == original


def test_simple_cluster_status_request_uses_fast_path_detector(monkeypatch) -> None:
    import importlib

    base_agent = _import_real_base_agent()

    monkeypatch.setattr(base_agent, "get_memory", lambda: object())
    monkeypatch.setattr(base_agent, "get_context_manager", lambda: object())
    monkeypatch.setattr(base_agent, "get_llm", lambda: object())
    monkeypatch.setattr(base_agent, "create_react_agent", lambda **_: object())

    kubernetes_agent_module = importlib.import_module("modules_catalog.kubernetes.agent")

    assert kubernetes_agent_module._is_simple_cluster_status_request(
        "Wie ist der Status von Kubernetes?"
    )
    assert kubernetes_agent_module._is_simple_cluster_status_request(
        "[Telegram Chat-ID: 1260743556]\nWie ist der Status von Kubernetes?"
    )
    assert not kubernetes_agent_module._is_simple_cluster_status_request(
        "Wie ist der Status der Kubernetes Pods?"
    )


@pytest.mark.asyncio
async def test_simple_cluster_status_request_invokes_tool_once(monkeypatch) -> None:
    import importlib

    base_agent = _import_real_base_agent()

    monkeypatch.setattr(base_agent, "get_memory", lambda: object())
    monkeypatch.setattr(base_agent, "get_context_manager", lambda: object())
    monkeypatch.setattr(base_agent, "get_llm", lambda: object())
    monkeypatch.setattr(base_agent, "create_react_agent", lambda **_: object())

    kubernetes_agent_module = importlib.import_module("modules_catalog.kubernetes.agent")
    from modules_catalog.kubernetes.agent import KubernetesAgent

    calls = 0

    async def fake_ainvoke(_self, args: dict) -> str:
        nonlocal calls
        calls += 1
        return str({
            "nodes": 1,
            "namespaces": 7,
            "total_pods": 19,
            "running_pods": 19,
            "failing_pods": 0,
            "deployments": 15,
        })

    monkeypatch.setattr(
        type(kubernetes_agent_module.get_cluster_status),
        "ainvoke",
        fake_ainvoke,
    )

    response, did_compact = await KubernetesAgent().invoke(
        "Wie ist der Status von Kubernetes?",
        session_id="test-session",
    )

    assert calls == 1
    assert did_compact is False
    assert "Der Kubernetes-Cluster wirkt gesund." in response
    assert "| Pods gesamt | 19 |" in response


def test_cluster_status_formatter_rejects_plain_text(monkeypatch) -> None:
    import importlib

    base_agent = _import_real_base_agent()

    monkeypatch.setattr(base_agent, "get_memory", lambda: object())
    monkeypatch.setattr(base_agent, "get_context_manager", lambda: object())
    monkeypatch.setattr(base_agent, "get_llm", lambda: object())
    monkeypatch.setattr(base_agent, "create_react_agent", lambda **_: object())

    kubernetes_agent_module = importlib.import_module("modules_catalog.kubernetes.agent")

    with pytest.raises(ValueError, match="non-structured response"):
        kubernetes_agent_module._format_cluster_status("cluster unavailable")
