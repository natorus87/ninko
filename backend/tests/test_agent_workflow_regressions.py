from __future__ import annotations

import json
import sys
import types

import pytest

from api.routes_agents import _extract_json_from_llm_response
from agents.orchestrator import OrchestratorAgent
from core.agent_pool import DynamicAgentPool
from core.workflow_engine import WorkflowEngine


def test_extract_json_from_llm_response_preserves_valid_json() -> None:
    spec = _extract_json_from_llm_response(
        '<think>internal</think>\n```json\n{"name": "K8s Agent", "description": "x"}\n```'
    )

    assert spec == {"name": "K8s Agent", "description": "x"}


@pytest.mark.asyncio
async def test_orchestrator_routes_infra_status_without_llm(monkeypatch) -> None:
    orchestrator = object.__new__(OrchestratorAgent)
    calls: list[dict[str, object]] = []

    def _display(module: str) -> str:
        return module.title()

    async def _invoke(module: str, **kwargs: object) -> tuple[str, str, bool]:
        calls.append({"module": module, **kwargs})
        return f"{module} ok", module, False

    monkeypatch.setattr(orchestrator, "_module_display_name", _display)
    monkeypatch.setattr(orchestrator, "_invoke_module_agent", _invoke)

    result = await orchestrator._try_infra_status_fast_path(
        message="wie ist der status von proxmox",
        chat_history=[],
        session_id="test-session",
        confirmed=False,
        wants_stream=True,
    )

    assert result == ("proxmox ok", "proxmox", False)
    assert calls[0]["module"] == "proxmox"
    assert calls[0]["wants_stream"] is True


@pytest.mark.asyncio
async def test_dynamic_agent_pool_sync_updates_and_removes_live_agent(monkeypatch) -> None:
    fake_base_agent_module = types.ModuleType("agents.base_agent")

    class FakeBaseAgent:
        def __init__(self, name: str, system_prompt: str, tools: list) -> None:
            self.name = name
            self.system_prompt = system_prompt
            self.tools = tools
            self.closed = False

        async def aclose(self) -> None:
            self.closed = True

    fake_base_agent_module.BaseAgent = FakeBaseAgent
    monkeypatch.setitem(sys.modules, "agents.base_agent", fake_base_agent_module)

    pool = DynamicAgentPool()
    monkeypatch.setattr(pool, "_get_dynamic_tools", lambda: [])

    await pool.sync_agent(
        {
            "id": "agent-1",
            "name": "Original",
            "description": "Old",
            "system_prompt": "Old prompt",
            "enabled": True,
            "tenant_id": "default",
        }
    )
    agent, name = pool.get_agent_by_id("agent-1")
    assert agent is not None
    assert name == "Original"
    assert agent.system_prompt == "Old prompt"

    await pool.sync_agent(
        {
            "id": "agent-1",
            "name": "Updated",
            "description": "New",
            "system_prompt": "New prompt",
            "enabled": True,
            "tenant_id": "default",
        }
    )
    agent, name = pool.get_agent_by_id("agent-1")
    assert agent is not None
    assert name == "Updated"
    assert agent.system_prompt == "New prompt"

    assert await pool.remove_agent("agent-1", tenant_id="default") is True
    agent, name = pool.get_agent_by_id("agent-1")
    assert agent is None
    assert name == ""


class _FakeRedisConnection:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str) -> bool:
        self.values[key] = value
        return True


class _FakeRedis:
    def __init__(self) -> None:
        self.connection = _FakeRedisConnection()


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def route(self, message: str, **_: object) -> tuple[str, str, bool, dict]:
        self.messages.append(message)
        return (
            f"done: {message}",
            "orchestrator",
            False,
            {"compaction_summary": None, "routing_confidence": 0.9, "tier_used": 1},
        )


@pytest.mark.asyncio
async def test_workflow_engine_executes_join_node_once() -> None:
    redis = _FakeRedis()
    orchestrator = _FakeOrchestrator()
    workflow = {
        "id": "default::diamond",
        "tenant_id": "default",
        "name": "Diamond",
        "version": 1,
        "nodes": [
            {"id": "start", "type": "trigger", "label": "Start", "config": {}},
            {"id": "left", "type": "agent", "label": "Left", "config": {"prompt": "left"}},
            {"id": "right", "type": "agent", "label": "Right", "config": {"prompt": "right"}},
            {"id": "join", "type": "agent", "label": "Join", "config": {"prompt": "join"}},
        ],
        "edges": [
            {"source_id": "start", "target_id": "left", "label": ""},
            {"source_id": "start", "target_id": "right", "label": ""},
            {"source_id": "left", "target_id": "join", "label": ""},
            {"source_id": "right", "target_id": "join", "label": ""},
        ],
        "variables": [],
    }

    engine = WorkflowEngine(redis, orchestrator)
    await engine.execute(workflow, "run-1")

    assert orchestrator.messages == ["left", "right", "join"]
    runs_key = next(
        key for key in redis.connection.values if key.startswith("ninko:workflow:runs:")
    )
    runs = json.loads(redis.connection.values[runs_key])
    assert runs[0]["status"] == "succeeded"
