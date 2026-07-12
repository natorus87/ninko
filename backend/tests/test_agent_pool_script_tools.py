"""Regression tests for DynamicAgentPool._get_dynamic_tools() script-tool wiring.

Dynamic agents previously had no way to call script-tools at all; now an
agent with script_tool_names gets a scoped run_script_tool/list_script_tools
pair, restricted to exactly those tool names.
"""

from __future__ import annotations

from core.agent_pool import DynamicAgentPool
from schemas.agents import AgentCreate, AgentDefinition


def _tool_names(tools: list) -> set[str]:
    return {getattr(t, "name", getattr(t, "__name__", "")) for t in tools}


def test_no_script_tools_without_script_tool_names() -> None:
    tools = DynamicAgentPool._get_dynamic_tools({"module_names": []})

    assert "run_script_tool" not in _tool_names(tools)
    assert "list_script_tools" not in _tool_names(tools)


def test_script_tools_added_when_script_tool_names_set() -> None:
    tools = DynamicAgentPool._get_dynamic_tools(
        {"module_names": [], "script_tool_names": ["backup-database"]}
    )

    names = _tool_names(tools)
    assert "run_script_tool" in names
    assert "list_script_tools" in names


def test_dynamic_tools_work_with_no_agent_def() -> None:
    # _instantiate() may be called before an agent_def is fully normalized;
    # _get_dynamic_tools must tolerate None.
    tools = DynamicAgentPool._get_dynamic_tools(None)

    assert "run_script_tool" not in _tool_names(tools)


def test_agent_create_defaults_script_tool_names_to_empty_list() -> None:
    agent = AgentCreate(name="test-agent")

    assert agent.script_tool_names == []


def test_agent_definition_roundtrips_script_tool_names() -> None:
    agent = AgentDefinition(name="test-agent", script_tool_names=["backup-database"])

    assert agent.model_dump()["script_tool_names"] == ["backup-database"]
