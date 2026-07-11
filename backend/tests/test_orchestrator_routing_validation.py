"""Regression tests: function-calling routing must reject hallucinated tool
names (e.g. 'call_module_agent' from the ReAct prompt) and self-heal poisoned
route-cache entries instead of failing every similar request until TTL expiry."""

from __future__ import annotations

import json
import types
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage

import agents.orchestrator as orch_mod
from agents.orchestrator import OrchestratorAgent


def _bare_orchestrator(module_names: list[str]) -> OrchestratorAgent:
    orchestrator = object.__new__(OrchestratorAgent)
    orchestrator.registry = types.SimpleNamespace(
        list_modules=lambda: [
            types.SimpleNamespace(name=n, description=f"{n} module")
            for n in module_names
        ]
    )
    return orchestrator


class _FakeLLM:
    def __init__(self, response: AIMessage) -> None:
        self._response = response

    async def ainvoke(self, messages, **kwargs):
        return self._response


def _patch_fc_route(monkeypatch, orchestrator, llm_response: AIMessage) -> dict:
    """Patch the FC route dependencies; return recorder dict."""
    rec: dict = {"cache_sets": [], "react": 0, "dispatched": []}

    monkeypatch.setattr(orchestrator, "_get_routing_mode", AsyncMock(return_value=(True, "auto")))
    monkeypatch.setattr(orchestrator, "_route_cache_exact_get", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_route_cache_semantic_get", AsyncMock(return_value=None))
    monkeypatch.setattr(orchestrator, "_dynamic_prompt_appendix", AsyncMock(return_value=""))

    async def _cache_set(text, names):
        rec["cache_sets"].append(names)

    monkeypatch.setattr(orchestrator, "_route_cache_exact_set", _cache_set)
    monkeypatch.setattr(orchestrator, "_route_cache_semantic_set", _cache_set)

    async def _react(*args, **kwargs):
        rec["react"] += 1
        return "react ok", None, False, {"tier_used": 2}

    monkeypatch.setattr(orchestrator, "_fallback_to_react_loop", _react)

    async def _dispatch(tool_calls, *args, **kwargs):
        rec["dispatched"].append([tc["name"] for tc in tool_calls])
        return "dispatched", tool_calls[0]["name"], False, None

    monkeypatch.setattr(orchestrator, "_dispatch_tool_calls", _dispatch)
    monkeypatch.setattr(orch_mod, "get_llm", lambda: _FakeLLM(llm_response))
    return rec


@pytest.mark.asyncio
async def test_fc_route_falls_back_to_react_on_hallucinated_tool(monkeypatch) -> None:
    """'call_module_agent' ist kein Modul — nicht dispatchen, nicht cachen."""
    orchestrator = _bare_orchestrator(["fritzbox", "kubernetes"])
    response = AIMessage(
        content="",
        tool_calls=[{
            "name": "call_module_agent",
            "args": {"query": "Wie ist der Status meiner Fritzbox?"},
            "id": "tc1",
        }],
    )
    rec = _patch_fc_route(monkeypatch, orchestrator, response)

    text, module, did_compact, meta = await orchestrator._llm_route_with_function_calling(
        "Wie ist der Status meiner Fritzbox?", None, "test_session", False
    )

    assert text == "react ok"
    assert rec["react"] == 1
    assert rec["dispatched"] == []
    assert rec["cache_sets"] == []


@pytest.mark.asyncio
async def test_fc_route_drops_invalid_but_keeps_valid_tool_calls(monkeypatch) -> None:
    orchestrator = _bare_orchestrator(["fritzbox"])
    response = AIMessage(
        content="",
        tool_calls=[
            {"name": "run_pipeline", "args": {"query": "x"}, "id": "tc1"},
            {"name": "fritzbox", "args": {"query": "Status?"}, "id": "tc2"},
        ],
    )
    rec = _patch_fc_route(monkeypatch, orchestrator, response)

    text, module, _, _ = await orchestrator._llm_route_with_function_calling(
        "Wie ist der Status meiner Fritzbox?", None, "test_session", False
    )

    assert text == "dispatched"
    assert module == "fritzbox"
    assert rec["react"] == 0
    assert rec["dispatched"] == [["fritzbox"]]
    assert rec["cache_sets"] == [["fritzbox"], ["fritzbox"]]


@pytest.mark.asyncio
async def test_fc_route_dispatches_and_caches_valid_module(monkeypatch) -> None:
    orchestrator = _bare_orchestrator(["fritzbox"])
    response = AIMessage(
        content="",
        tool_calls=[{"name": "fritzbox", "args": {"query": "Status?"}, "id": "tc1"}],
    )
    rec = _patch_fc_route(monkeypatch, orchestrator, response)

    text, module, _, _ = await orchestrator._llm_route_with_function_calling(
        "Wie ist der Status meiner Fritzbox?", None, "test_session", False
    )

    assert (text, module) == ("dispatched", "fritzbox")
    assert rec["cache_sets"] == [["fritzbox"], ["fritzbox"]]


class _FakeRedisConn:
    def __init__(self, values: dict[str, str]) -> None:
        self.values = values
        self.deleted: list[str] = []
        self.zremoved: list[str] = []

    async def get(self, key):
        return self.values.get(key)

    async def delete(self, *keys):
        self.deleted.extend(keys)

    async def zrevrange(self, key, start, stop):
        return [k for k in self.values if k.startswith("ninko:toolcall:sem:")]

    async def mget(self, keys):
        return [self.values.get(k) for k in keys]

    async def zrem(self, key, *members):
        self.zremoved.extend(members)


@pytest.mark.asyncio
async def test_exact_cache_purges_entry_with_unknown_module(monkeypatch) -> None:
    orchestrator = _bare_orchestrator(["fritzbox"])
    key = (
        f"{OrchestratorAgent._TOOL_CALL_CACHE_PREFIX}exact:"
        f"{OrchestratorAgent._normalize_query_for_cache('status fritzbox')}"
    )
    conn = _FakeRedisConn({key: json.dumps({"module_names": ["call_module_agent"]})})
    monkeypatch.setattr(
        orch_mod, "get_redis", lambda: types.SimpleNamespace(connection=conn)
    )

    result = await orchestrator._route_cache_exact_get("status fritzbox")

    assert result is None
    assert conn.deleted == [key]


@pytest.mark.asyncio
async def test_exact_cache_returns_valid_entry(monkeypatch) -> None:
    orchestrator = _bare_orchestrator(["fritzbox"])
    key = (
        f"{OrchestratorAgent._TOOL_CALL_CACHE_PREFIX}exact:"
        f"{OrchestratorAgent._normalize_query_for_cache('status fritzbox')}"
    )
    conn = _FakeRedisConn({key: json.dumps({"module_names": ["fritzbox"]})})
    monkeypatch.setattr(
        orch_mod, "get_redis", lambda: types.SimpleNamespace(connection=conn)
    )

    result = await orchestrator._route_cache_exact_get("status fritzbox")

    assert result == ["fritzbox"]
    assert conn.deleted == []


@pytest.mark.asyncio
async def test_semantic_cache_purges_entry_with_unknown_module(monkeypatch) -> None:
    orchestrator = _bare_orchestrator(["fritzbox"])
    sem_key = "ninko:toolcall:sem:deadbeef"
    conn = _FakeRedisConn({
        sem_key: json.dumps({
            "module_names": ["call_module_agent"],
            "embedding": [1.0, 0.0],
        })
    })
    monkeypatch.setattr(
        orch_mod, "get_redis", lambda: types.SimpleNamespace(connection=conn)
    )
    monkeypatch.setattr(
        orch_mod,
        "get_embeddings",
        lambda: types.SimpleNamespace(embed_query=lambda q: [1.0, 0.0]),
    )

    result = await orchestrator._route_cache_semantic_get("status fritzbox")

    assert result is None
    assert sem_key in conn.deleted
    assert sem_key in conn.zremoved
