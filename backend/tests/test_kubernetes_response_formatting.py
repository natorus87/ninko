"""Regression tests for Kubernetes chat response formatting."""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from agents.middleware.base import MiddlewareContext
from agents.middleware.postprocess import (
    ResponseExtractionMiddleware,
    _format_kubernetes_tool_fallback,
)


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
