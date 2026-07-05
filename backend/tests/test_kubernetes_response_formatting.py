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

    async def fake_ainvoke(_self, args: dict) -> dict:
        nonlocal calls
        calls += 1
        return {
            "nodes": 1,
            "namespaces": 7,
            "total_pods": 19,
            "running_pods": 19,
            "failing_pods": 0,
            "deployments": 15,
        }

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
