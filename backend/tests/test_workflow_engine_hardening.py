"""
Regressionstests für die Härtung der WorkflowEngine:
- Unbekannter Node-Typ failt den Step (statt Pseudo-Erfolg)
- Unbekannte Condition-Expression failt den Step (statt still True)
- Subflow-Zyklus und -Tiefe werden begrenzt
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow_engine import (
    MAX_SUBFLOW_DEPTH,
    REDIS_KEY_RUNS_PREFIX,
    WorkflowEngine,
    _tenant_key,
)


def _workflow(workflow_id: str, nodes: list[dict], edges: list[dict]) -> dict:
    return {
        "id": workflow_id,
        "tenant_id": "default",
        "name": f"wf {workflow_id}",
        "nodes": nodes,
        "edges": edges,
        "variables": [],
    }


async def _run(engine: WorkflowEngine, workflow: dict, run_id: str = "run-1") -> None:
    await engine.execute(workflow, run_id)


def _last_run_state(mock_redis) -> dict:
    """Extrahiert den zuletzt geschriebenen Run-Zustand aus den set()-Aufrufen."""
    for call in reversed(mock_redis.connection.set.call_args_list):
        key = call.args[0]
        if "workflow:runs" in key:
            runs = json.loads(call.args[1])
            if runs:
                return runs[-1]
    return {}


@pytest.fixture
def redis_with_runs(mock_redis):
    """mock_redis, dessen get() die zuletzt via set() geschriebenen Runs zurückliefert."""
    store: dict[str, str] = {}

    async def _set(key, value, *args, **kwargs):
        store[key] = value
        return True

    async def _get(key):
        return store.get(key)

    mock_redis.connection.set = type(mock_redis.connection.set)(side_effect=_set)
    mock_redis.connection.get = type(mock_redis.connection.get)(side_effect=_get)
    mock_redis._store = store
    return mock_redis


def _run_from_store(redis_mock, workflow_id: str, tenant: str = "default") -> dict:
    key = f"{_tenant_key(REDIS_KEY_RUNS_PREFIX, tenant)}{workflow_id}"
    runs = json.loads(redis_mock._store.get(key, "[]"))
    assert runs, f"Keine Runs unter {key}"
    return runs[-1]


class TestUnknownNodeType:
    @pytest.mark.asyncio
    async def test_unknown_node_type_fails_run(self, redis_with_runs):
        engine = WorkflowEngine(redis_with_runs, orchestrator=None)
        wf = _workflow(
            "default::wf-unknown",
            nodes=[{"id": "n1", "type": "teleport", "label": "Nope", "config": {}}],
            edges=[],
        )
        await _run(engine, wf)
        run = _run_from_store(redis_with_runs, "default::wf-unknown")
        assert run["status"] == "failed"
        assert "Unbekannter Node-Typ" in (run.get("error") or "")


class TestUnknownCondition:
    @pytest.mark.asyncio
    async def test_unknown_condition_fails_step(self, redis_with_runs):
        engine = WorkflowEngine(redis_with_runs, orchestrator=None)
        wf = _workflow(
            "default::wf-cond",
            nodes=[
                {"id": "c1", "type": "condition", "label": "Kaputt",
                 "config": {"expression": "definitiv kein muster"}},
            ],
            edges=[],
        )
        await _run(engine, wf)
        run = _run_from_store(redis_with_runs, "default::wf-cond")
        assert run["status"] == "failed"
        assert "Unbekannte Condition-Expression" in (run.get("error") or "")

    def test_literal_true_false_still_work(self, mock_redis):
        engine = WorkflowEngine(mock_redis, orchestrator=None)
        assert engine._evaluate_condition("true", "", {}) is True
        assert engine._evaluate_condition("False", "", {}) is False

    def test_known_expressions_still_work(self, mock_redis):
        engine = WorkflowEngine(mock_redis, orchestrator=None)
        assert engine._evaluate_condition("output.contains('err')", "ERROR", {}) is True
        assert engine._evaluate_condition("len(output) > 2", "abc", {}) is True
        assert engine._evaluate_condition("variable.x == 5", "", {"x": "5"}) is True


class TestSubflowGuards:
    @pytest.mark.asyncio
    async def test_subflow_self_cycle_aborts(self, redis_with_runs):
        wf_id = "default::wf-loop"
        wf = _workflow(
            wf_id,
            nodes=[{"id": "s1", "type": "subflow", "label": "Ich selbst",
                    "config": {"workflow_id": "wf-loop"}}],
            edges=[],
        )
        # Workflow-Liste in den Store legen, damit der Subflow-Lookup ihn findet
        redis_with_runs._store["ninko:workflows:default"] = json.dumps([wf])
        engine = WorkflowEngine(redis_with_runs, orchestrator=None)
        await _run(engine, wf)
        run = _run_from_store(redis_with_runs, wf_id)
        assert run["status"] == "failed"
        assert "Subflow-Zyklus" in (run.get("error") or "")

    @pytest.mark.asyncio
    async def test_subflow_depth_limit(self, redis_with_runs):
        wf_id = "default::wf-deep"
        wf = _workflow(
            wf_id,
            nodes=[{"id": "s1", "type": "subflow", "label": "Tiefer",
                    "config": {"workflow_id": "wf-other"}}],
            edges=[],
        )
        other = _workflow("default::wf-other", nodes=[{"id": "e", "type": "end",
                          "label": "Ende", "config": {}}], edges=[])
        redis_with_runs._store["ninko:workflows:default"] = json.dumps([wf, other])
        # Engine startet bereits mit maximaler Ahnen-Tiefe
        stack = tuple(f"default::anc-{i}" for i in range(MAX_SUBFLOW_DEPTH))
        engine = WorkflowEngine(redis_with_runs, orchestrator=None, subflow_stack=stack)
        await _run(engine, wf)
        run = _run_from_store(redis_with_runs, wf_id)
        assert run["status"] == "failed"
        assert "Subflow-Tiefe" in (run.get("error") or "")
