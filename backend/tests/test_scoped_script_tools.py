"""Regression tests for agents.script_tools.make_scoped_script_tools().

A dynamic agent must only be able to invoke the script-tools explicitly
selected for it, even though run_script_tool/list_script_tools take the
target tool_name as a plain string argument (not a per-script tool).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import agents.script_tools as script_tools


async def test_scoped_run_script_tool_rejects_tool_outside_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(script_tools, "execute_script_tool", AsyncMock())
    run_tool, _ = script_tools.make_scoped_script_tools(frozenset({"allowed-tool"}))

    result = await run_tool.coroutine(tool_name="other-tool")

    assert "nicht freigegeben" in result
    script_tools.execute_script_tool.assert_not_awaited()


async def test_scoped_run_script_tool_allows_tool_in_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        script_tools,
        "execute_script_tool",
        AsyncMock(return_value={"status": "succeeded", "stdout": "ok"}),
    )
    monkeypatch.setattr("core.auth.get_current_tenant_id", lambda: "default")
    run_tool, _ = script_tools.make_scoped_script_tools(frozenset({"allowed-tool"}))

    result = await run_tool.coroutine(tool_name="allowed-tool")

    assert result == "ok"
    script_tools.execute_script_tool.assert_awaited_once_with("default", "allowed-tool", None)


async def test_scoped_list_script_tools_filters_to_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        script_tools,
        "get_available_script_tools",
        AsyncMock(
            return_value=[
                {"name": "allowed-tool", "description": "Allowed one"},
                {"name": "other-tool", "description": "Not allowed"},
            ]
        ),
    )
    monkeypatch.setattr("core.auth.get_current_tenant_id", lambda: "default")
    _, list_tool = script_tools.make_scoped_script_tools(frozenset({"allowed-tool"}))

    result = await list_tool.coroutine()

    assert "allowed-tool" in result
    assert "other-tool" not in result


async def test_unscoped_run_script_tool_is_unaffected(monkeypatch) -> None:
    """The plain module-level tool (used by the main Orchestrator) must keep
    working unrestricted after the make_scoped_script_tools() refactor."""
    monkeypatch.setattr(
        script_tools,
        "execute_script_tool",
        AsyncMock(return_value={"status": "succeeded", "stdout": "ok"}),
    )
    monkeypatch.setattr("core.auth.get_current_tenant_id", lambda: "default")

    result = await script_tools.run_script_tool.coroutine(tool_name="any-tool")

    assert result == "ok"
