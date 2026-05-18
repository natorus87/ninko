"""Output-format regression tests for migrated catalog modules.

Structured tool data must render as Markdown tables in tool-only fallbacks and
be appended to short AI answers for the modules covered by response
augmentation. These tests protect the postprocess layer from leaking raw Python
repr, raw JSON, or module-specific column collisions into the frontend.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from agents.middleware.base import MiddlewareContext
from agents.middleware.postprocess import ResponseExtractionMiddleware
from langchain_core.messages import AIMessage, ToolMessage

TABLE_AUGMENT_MODULES = [
    "kubernetes",
    "proxmox",
    "docker",
    "linux_server",
    "checkmk",
    "opnsense",
    "zabbix",
]
HIGH_RISK_MODULES = [
    "proxmox",
    "docker",
    "linux_server",
    "checkmk",
    "opnsense",
    "zabbix",
]


@pytest.mark.parametrize("agent_name", HIGH_RISK_MODULES)
async def test_raw_python_repr_tool_output_is_rendered_as_markdown_table(
    agent_name: str,
) -> None:
    """Phase 5: structured list output renders as Markdown, not raw JSON."""
    middleware = ResponseExtractionMiddleware()
    raw = "[{'name': 'web', 'status': 'running', 'cpu': 12}]"
    ctx = MiddlewareContext(
        agent_name=agent_name,
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_unknown")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "| Name | Status | Cpu |" in ctx.response
    assert "| web | running | 12 |" in ctx.response
    # No raw JSON code block and no raw Python repr in the final answer.
    assert "```json" not in ctx.response
    assert "'name': 'web'" not in ctx.response


@pytest.mark.parametrize("agent_name", HIGH_RISK_MODULES)
async def test_ai_response_passes_through_unchanged(agent_name: str) -> None:
    middleware = ResponseExtractionMiddleware()
    ctx = MiddlewareContext(
        agent_name=agent_name,
        result={
            "messages": [
                ToolMessage(content="{}", tool_call_id="c1", name="status"),
                AIMessage(content="The system looks healthy."),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response == "The system looks healthy."


@pytest.mark.parametrize("agent_name", HIGH_RISK_MODULES)
async def test_thinking_tags_are_stripped_from_ai_response(agent_name: str) -> None:
    middleware = ResponseExtractionMiddleware()
    ctx = MiddlewareContext(
        agent_name=agent_name,
        result={
            "messages": [
                AIMessage(
                    content="<think>internal scratchpad</think>Final answer."
                ),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "<think>" not in ctx.response
    assert "internal scratchpad" not in ctx.response
    assert ctx.response.strip() == "Final answer."


@pytest.mark.parametrize("agent_name", HIGH_RISK_MODULES)
async def test_already_sanitized_tool_output_keeps_redactions(agent_name: str) -> None:
    """Postprocess must respect upstream secret sanitization."""
    middleware = ResponseExtractionMiddleware()
    raw = "[{'name': 'api', 'token': '<REDACTED>'}]"
    ctx = MiddlewareContext(
        agent_name=agent_name,
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_secrets")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "<REDACTED>" in ctx.response


@pytest.mark.parametrize("agent_name", HIGH_RISK_MODULES)
async def test_markdown_tool_output_is_preserved(agent_name: str) -> None:
    """If a tool already returns Markdown (e.g. a table), it must pass through."""
    middleware = ResponseExtractionMiddleware()
    raw = "| Host | Status |\n| --- | --- |\n| node1 | UP |"
    ctx = MiddlewareContext(
        agent_name=agent_name,
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_hosts")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response == raw


async def test_empty_messages_returns_default() -> None:
    middleware = ResponseExtractionMiddleware()
    ctx = MiddlewareContext(agent_name="proxmox", result={"messages": []})

    await middleware.post_process(ctx)

    assert ctx.response == "Keine Antwort generiert."


# --- Phase 5: module-specific column hints ----------------------------------


async def test_docker_list_containers_uses_preferred_columns() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = (
        "[{'name': 'web', 'image': 'nginx:latest', 'status': 'running', "
        "'ports': '80:8080', 'created': '2h', 'extra': 'ignored'}]"
    )
    ctx = MiddlewareContext(
        agent_name="docker",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_containers")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "| Name | Image | Status | Ports | Created |" in ctx.response
    assert "| web | nginx:latest | running | 80:8080 | 2h |" in ctx.response
    # Columns not in the hint list must be dropped (no "extra" column).
    assert "Extra" not in ctx.response


async def test_proxmox_list_all_vms_uses_preferred_columns() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = (
        "[{'vmid': 100, 'name': 'web-srv', 'status': 'running', "
        "'node': 'pve1', 'cpu': 0.12, 'mem': '2G', 'uptime': '5d'}]"
    )
    ctx = MiddlewareContext(
        agent_name="proxmox",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_all_vms")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "| Vmid | Name | Status | Node | Cpu | Mem | Uptime |" in ctx.response
    assert "| 100 | web-srv | running | pve1 | 0.12 | 2G | 5d |" in ctx.response


async def test_dict_tool_output_renders_as_two_column_table() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = "{'version': '7.0', 'uptime': '12d', 'hostname': 'fw1'}"
    ctx = MiddlewareContext(
        agent_name="opnsense",
        result={
            "messages": [
                ToolMessage(
                    content=raw,
                    tool_call_id="c1",
                    name="get_opnsense_system_status",
                )
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "| Feld | Wert |" in ctx.response
    assert "| version | 7.0 |" in ctx.response
    assert "```json" not in ctx.response


async def test_non_tabular_structure_falls_back_to_json_code_block() -> None:
    """Lists of primitives cannot be rendered as a table — JSON fence is OK."""
    middleware = ResponseExtractionMiddleware()
    raw = "['one', 'two', 'three']"
    ctx = MiddlewareContext(
        agent_name="docker",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_strings")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "```json" in ctx.response
    assert '"one"' in ctx.response


async def test_empty_list_returns_clear_message() -> None:
    middleware = ResponseExtractionMiddleware()
    ctx = MiddlewareContext(
        agent_name="docker",
        result={
            "messages": [
                ToolMessage(content="[]", tool_call_id="c1", name="list_containers")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response == "Keine Einträge gefunden."


async def test_explicit_json_request_keeps_structured_tool_output_as_json() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = "[{'name': 'web', 'status': 'running'}]"
    ctx = MiddlewareContext(
        message="Gib mir JSON für die Container.",
        agent_name="docker",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_containers")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response.startswith("```json")
    assert '"name": "web"' in ctx.response
    assert "| Name | Status |" not in ctx.response


# --- Module-qualified column hints (Finding 1) ------------------------------


async def test_kubernetes_list_services_keeps_k8s_columns() -> None:
    """`list_services` exists in Kubernetes AND Linux Server. The K8s lookup
    must not be shadowed by the Linux Server column hint."""
    middleware = ResponseExtractionMiddleware()
    raw = (
        "[{'namespace': 'default', 'name': 'web', 'type': 'ClusterIP', "
        "'cluster_ip': '10.0.0.1', 'external_ip': '<none>', "
        "'ports': '80/TCP', 'age': '2d'}]"
    )
    ctx = MiddlewareContext(
        agent_name="kubernetes",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_services")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert (
        "| Namespace | Name | Type | Cluster IP | External IP | Ports | Age |"
        in ctx.response
    )
    # Linux Server columns (load/active/sub) must not appear.
    assert "Load" not in ctx.response
    assert "Active" not in ctx.response


async def test_linux_server_list_services_uses_systemd_columns() -> None:
    """Same tool name `list_services` on Linux Server resolves to systemd columns."""
    middleware = ResponseExtractionMiddleware()
    raw = (
        "[{'name': 'nginx.service', 'load': 'loaded', 'active': 'active', "
        "'sub': 'running', 'description': 'A high performance web server'}]"
    )
    ctx = MiddlewareContext(
        agent_name="linux_server",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_services")
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "| Name | Load | Active | Sub | Description |" in ctx.response
    # Kubernetes columns must not leak in.
    assert "Cluster IP" not in ctx.response
    assert "Namespace" not in ctx.response


# --- AI-response + tool-table augmentation for high-risk modules (Finding 2)


async def test_proxmox_short_ai_response_gets_tool_table_appended() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = (
        "[{'vmid': 100, 'name': 'web-srv', 'status': 'running', "
        "'node': 'pve1', 'cpu': 0.12, 'mem': '2G', 'uptime': '5d'}]"
    )
    ctx = MiddlewareContext(
        agent_name="proxmox",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_all_vms"),
                AIMessage(content="Eine VM läuft."),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "Eine VM läuft." in ctx.response
    assert "| Vmid | Name | Status | Node | Cpu | Mem | Uptime |" in ctx.response
    assert "| 100 | web-srv | running | pve1 | 0.12 | 2G | 5d |" in ctx.response


async def test_docker_short_ai_response_gets_tool_table_appended() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = (
        "[{'name': 'web', 'image': 'nginx:latest', 'status': 'running', "
        "'ports': '80:8080', 'created': '2h'}]"
    )
    ctx = MiddlewareContext(
        agent_name="docker",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_containers"),
                AIMessage(content="One container is running."),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "One container is running." in ctx.response
    assert "| Name | Image | Status | Ports | Created |" in ctx.response
    assert "| web | nginx:latest | running | 80:8080 | 2h |" in ctx.response


@pytest.mark.parametrize("agent_name", TABLE_AUGMENT_MODULES)
async def test_short_ai_response_gets_tool_table_appended_for_all_modules(
    agent_name: str,
) -> None:
    middleware = ResponseExtractionMiddleware()
    raw = "[{'name': 'web', 'status': 'running'}]"
    ctx = MiddlewareContext(
        agent_name=agent_name,
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_unknown"),
                AIMessage(content="Looks healthy."),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "Looks healthy." in ctx.response
    assert "| Name | Status |" in ctx.response
    assert "| web | running |" in ctx.response


async def test_short_ai_response_uses_latest_renderable_tool_table() -> None:
    middleware = ResponseExtractionMiddleware()
    renderable_raw = "[{'name': 'web', 'status': 'running'}]"
    non_tabular_raw = "['status-ok']"
    ctx = MiddlewareContext(
        agent_name="docker",
        result={
            "messages": [
                ToolMessage(
                    content=renderable_raw,
                    tool_call_id="c1",
                    name="list_unknown",
                ),
                ToolMessage(
                    content=non_tabular_raw,
                    tool_call_id="c2",
                    name="get_summary",
                ),
                AIMessage(content="One service is healthy."),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "One service is healthy." in ctx.response
    assert "| Name | Status |" in ctx.response
    assert "| web | running |" in ctx.response
    assert "status-ok" not in ctx.response


async def test_explicit_json_request_does_not_append_tool_table_to_ai_response() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = "[{'name': 'web', 'status': 'running'}]"
    ctx = MiddlewareContext(
        message="Wie ist der Status? Bitte als JSON.",
        agent_name="docker",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_unknown"),
                AIMessage(content='{"summary": "healthy"}'),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response == '{"summary": "healthy"}'
    assert "| Name | Status |" not in ctx.response


async def test_proxmox_ai_response_with_existing_table_is_not_doubled() -> None:
    """If the AI already produced a Markdown table, the postprocess must not
    append another one."""
    middleware = ResponseExtractionMiddleware()
    raw = "[{'vmid': 100, 'name': 'web-srv', 'status': 'running', 'node': 'pve1'}]"
    ai_with_table = (
        "Übersicht:\n\n| Vmid | Name | Status |\n| --- | --- | --- |\n"
        "| 100 | web-srv | running |"
    )
    ctx = MiddlewareContext(
        agent_name="proxmox",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_all_vms"),
                AIMessage(content=ai_with_table),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response == ai_with_table


async def test_non_migrated_module_does_not_get_table_appended() -> None:
    """Modules outside the high-risk migration scope keep the AI answer as-is."""
    middleware = ResponseExtractionMiddleware()
    raw = "[{'name': 'web', 'status': 'running'}]"
    ctx = MiddlewareContext(
        agent_name="discord",  # not in _TABLE_AUGMENT_MODULES
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="list_unknown"),
                AIMessage(content="All good."),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert ctx.response == "All good."


async def test_web_search_unhelpful_ai_response_uses_tool_results() -> None:
    middleware = ResponseExtractionMiddleware()
    raw = (
        "[{'title': 'Example News', 'url': 'https://example.test/news', "
        "'content': 'A concise result snippet.'}]"
    )
    ctx = MiddlewareContext(
        agent_name="web_search",
        result={
            "messages": [
                ToolMessage(content=raw, tool_call_id="c1", name="perform_web_search"),
                AIMessage(content="Ich werde jetzt die aktuellen Nachrichten suchen."),
            ]
        },
    )

    await middleware.post_process(ctx)

    assert "**Example News**" in ctx.response
    assert "https://example.test/news" in ctx.response
    assert "Ich werde jetzt" not in ctx.response


# --- Zabbix agent constructor (Finding 3) -----------------------------------


def test_zabbix_agent_source_uses_baseagent_signature() -> None:
    """Regression: zabbix used to call `super().__init__()` without args plus a
    non-existent `_register_tools`. The source must now pass `name`,
    `system_prompt` and `tools` to ``BaseAgent.__init__`` and must not reference
    the removed `_register_tools` helper.

    We assert against the source rather than importing the module because the
    full module pulls in heavy runtime deps (``aiosqlite`` etc.) that are not
    part of the unit-test environment.
    """
    source = Path("backend/modules_catalog/zabbix/agent.py").read_text(encoding="utf-8")

    assert "_register_tools" not in source
    assert 'name="zabbix"' in source
    assert "system_prompt=self.system_prompt" in source
    assert "tools=[" in source
