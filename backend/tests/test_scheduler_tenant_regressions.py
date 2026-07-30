"""
Regressionstests für den SchedulerAgent:
- Bug: Workflow-Tasks lasen den globalen Key 'ninko:workflows' statt des
  tenant-scoped Keys → 'Workflow nicht gefunden'.
- Tasks tragen jetzt tenant_id/source; Legacy-Tasks fallen auf 'default'.
- run_task_now startet im Hintergrund und blockiert den Aufrufer nicht.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.scheduler_agent import SchedulerAgent, _task_tenant
from core.agent_protocol import APPROVAL_REQUIRED_MESSAGE, TOOL_APPROVAL_SENTINEL
from schemas.execution import AgentFinishReason, AgentRequest, AgentResponse
from schemas.execution import AgentEventType


def _store_backed_redis() -> MagicMock:
    """Mock-Redis, dessen get/set/lpush auf einem Dict-Store arbeiten."""
    store: dict[str, str] = {}
    lists: dict[str, list[str]] = {}

    redis_mock = MagicMock()
    redis_mock._store = store

    async def _get(key):
        return store.get(key)

    async def _set(key, value, *args, **kwargs):
        store[key] = value
        return True

    async def _lpush(key, value):
        lists.setdefault(key, []).insert(0, value)
        return len(lists[key])

    async def _ltrim(key, start, stop):
        lists[key] = lists.get(key, [])[start : stop + 1]
        return True

    redis_mock.connection.get = AsyncMock(side_effect=_get)
    redis_mock.connection.set = AsyncMock(side_effect=_set)
    redis_mock.connection.lpush = AsyncMock(side_effect=_lpush)
    redis_mock.connection.ltrim = AsyncMock(side_effect=_ltrim)
    redis_mock.connection.delete = AsyncMock(return_value=True)
    redis_mock.publish_event = AsyncMock(return_value=True)
    return redis_mock


def _make_scheduler(redis_mock, orchestrator=None) -> SchedulerAgent:
    with patch("agents.scheduler_agent.get_redis", return_value=redis_mock):
        return SchedulerAgent(
            registry=MagicMock(),
            orchestrator=orchestrator or MagicMock(),
        )


def _trivial_workflow(scoped_id: str) -> dict:
    return {
        "id": scoped_id,
        "tenant_id": "default",
        "name": "Trivial",
        "nodes": [
            {"id": "n1", "type": "trigger", "label": "Start", "config": {"mode": "manual"}},
            {"id": "n2", "type": "end", "label": "Ende", "config": {"status": "succeeded"}},
        ],
        "edges": [{"id": "e1", "source_id": "n1", "target_id": "n2"}],
        "variables": [],
    }


class TestTaskTenant:
    def test_legacy_task_defaults_to_default(self):
        assert _task_tenant({"id": "t1"}) == "default"

    def test_explicit_tenant_normalized(self):
        assert _task_tenant({"tenant_id": " Kunde-A "}) == "kunde-a"


class TestWorkflowTaskTenantScoping:
    @pytest.mark.asyncio
    async def test_workflow_task_reads_tenant_scoped_key(self):
        """Ohne Fix las der Scheduler 'ninko:workflows' (global) und fand nichts."""
        redis_mock = _store_backed_redis()
        scoped_id = "default::wf-1"
        redis_mock._store["ninko:workflows:default"] = json.dumps(
            [_trivial_workflow(scoped_id)]
        )

        scheduler = _make_scheduler(redis_mock)
        task = {
            "id": "task-1",
            "name": "Workflow-Task",
            "cron": "* * * * *",
            "workflow_id": "wf-1",
            "tenant_id": "default",
        }
        redis_mock._store["ninko:scheduler:tasks"] = json.dumps([task])

        log_entry = await scheduler._execute_task(task)

        assert log_entry["status"] == "ok", log_entry.get("response")
        assert "SUCCEEDED" in log_entry["response"]
        # Runs liegen unter dem tenant-scoped Key
        runs_key = f"ninko:workflow:runs::default{scoped_id}"
        assert any("workflow:runs" in k and "default" in k for k in redis_mock._store), (
            f"Keine tenant-scoped Runs gefunden, Keys: {list(redis_mock._store)} ({runs_key})"
        )

    @pytest.mark.asyncio
    async def test_missing_workflow_reports_error(self):
        redis_mock = _store_backed_redis()
        scheduler = _make_scheduler(redis_mock)
        task = {
            "id": "task-2",
            "name": "Kaputt",
            "cron": "* * * * *",
            "workflow_id": "gibt-es-nicht",
            "tenant_id": "default",
        }
        redis_mock._store["ninko:scheduler:tasks"] = json.dumps([task])

        log_entry = await scheduler._execute_task(task)
        assert log_entry["status"] == "error"
        assert "nicht gefunden" in log_entry["response"]


class TestCreateTaskStoresTenant:
    @pytest.mark.asyncio
    async def test_create_task_persists_tenant_and_source(self):
        redis_mock = _store_backed_redis()
        scheduler = _make_scheduler(redis_mock)

        task = await scheduler.create_task(
            {
                "name": "Mit Tenant",
                "cron": "0 8 * * *",
                "prompt": "Tu was",
                "tenant_id": "Kunde-A",
                "source": "workflow_trigger",
            }
        )
        assert task["tenant_id"] == "kunde-a"
        assert task["source"] == "workflow_trigger"

        stored = json.loads(redis_mock._store["ninko:scheduler:tasks"])
        assert stored[0]["tenant_id"] == "kunde-a"

    @pytest.mark.asyncio
    async def test_create_task_without_tenant_defaults(self):
        redis_mock = _store_backed_redis()
        scheduler = _make_scheduler(redis_mock)
        task = await scheduler.create_task({"name": "Ohne", "cron": "0 8 * * *"})
        assert task["tenant_id"] == "default"


class TestAgentProtocolExecution:
    @pytest.mark.asyncio
    async def test_native_agent_finish_reason_controls_task_status(self):
        class NativeAgent:
            id = "agent-1"
            name = "Native Agent"
            description = "Native scheduler test"

            def __init__(self) -> None:
                self.requests: list[AgentRequest] = []

            async def run(self, request: AgentRequest) -> AgentResponse:
                self.requests.append(request)
                return AgentResponse(
                    text="Provider nicht erreichbar",
                    agent_id=self.id,
                    agent_name=self.name,
                    finish_reason=AgentFinishReason.FAILED,
                )

        redis_mock = _store_backed_redis()
        native_agent = NativeAgent()
        pool = MagicMock()
        pool.get_agent_by_id.return_value = (native_agent, native_agent.name)
        scheduler = _make_scheduler(redis_mock)
        task = {
            "id": "task-agent",
            "name": "Native Agent Task",
            "cron": "* * * * *",
            "prompt": "Prüfe den Status",
            "agent_id": native_agent.id,
            "tenant_id": "default",
        }
        redis_mock._store["ninko:scheduler:tasks"] = json.dumps([task])

        with patch("core.agent_pool.get_agent_pool", return_value=pool):
            log_entry = await scheduler._execute_task(task)

        assert log_entry["status"] == "error"
        assert native_agent.requests[0].session_id == "default:scheduler-task-agent"

    @pytest.mark.asyncio
    async def test_orchestrator_legacy_error_maps_to_structured_status(self):
        redis_mock = _store_backed_redis()
        orchestrator = MagicMock()
        orchestrator.route = AsyncMock(
            return_value=(
                "Error: Provider nicht erreichbar",
                None,
                False,
                {
                    "compaction_summary": None,
                    "routing_confidence": None,
                    "tier_used": 2,
                },
            )
        )
        scheduler = _make_scheduler(redis_mock, orchestrator)
        task = {
            "id": "task-orchestrator",
            "name": "Orchestrator Task",
            "cron": "* * * * *",
            "prompt": "Prüfe den Status",
            "tenant_id": "default",
        }
        redis_mock._store["ninko:scheduler:tasks"] = json.dumps([task])

        log_entry = await scheduler._execute_task(task)

        assert log_entry["status"] == "error"
        orchestrator.route.assert_awaited_once_with(
            message="Prüfe den Status",
            chat_history=[],
            session_id="default:scheduler-task-orchestrator",
            confirmed=False,
            force_module=None,
        )

    @pytest.mark.asyncio
    async def test_scheduler_emits_started_and_terminal_events(self):
        redis_mock = _store_backed_redis()
        orchestrator = MagicMock()
        orchestrator.route = AsyncMock(
            return_value=("done", None, False, {})
        )
        scheduler = _make_scheduler(redis_mock, orchestrator)
        task = {
            "id": "task-events",
            "name": "Event Task",
            "cron": "* * * * *",
            "prompt": "Prüfe den Status",
            "tenant_id": "default",
        }
        emitted = AsyncMock()

        with patch("agents.scheduler_agent.emit_agent_event", emitted):
            await scheduler._execute_task(task)

        events = [call.args[0] for call in emitted.await_args_list]
        assert [event.type for event in events] == [
            AgentEventType.STARTED,
            AgentEventType.COMPLETED,
        ]
        assert events[0].run_id == events[1].run_id
        assert events[0].session_id == "default:scheduler-task-events"

    @pytest.mark.asyncio
    async def test_approval_required_is_cleaned_up_and_not_logged_as_sentinel(self):
        redis_mock = _store_backed_redis()
        sentinel = f'{TOOL_APPROVAL_SENTINEL}{{"tool_name":"restart_server"}}'
        legacy_agent = MagicMock()
        legacy_agent.invoke = AsyncMock(return_value=(sentinel, False))
        pool = MagicMock()
        pool.get_agent_by_id.return_value = (legacy_agent, "Legacy Agent")
        scheduler = _make_scheduler(redis_mock)
        task = {
            "id": "task-approval",
            "name": "Approval Task",
            "cron": "* * * * *",
            "prompt": "Starte den Server neu",
            "agent_id": "agent-1",
            "tenant_id": "default",
        }
        redis_mock._store["ninko:scheduler:tasks"] = json.dumps([task])

        with patch("core.agent_pool.get_agent_pool", return_value=pool):
            log_entry = await scheduler._execute_task(task)

        assert log_entry["status"] == "error"
        assert log_entry["response"] == APPROVAL_REQUIRED_MESSAGE
        redis_mock.connection.delete.assert_awaited_with(
            "ninko:safeguard_tool_pending:default:scheduler-task-approval"
        )


class TestRunTaskNowAsync:
    @pytest.mark.asyncio
    async def test_run_task_now_returns_immediately(self):
        redis_mock = _store_backed_redis()
        scheduler = _make_scheduler(redis_mock)
        task = await scheduler.create_task(
            {"name": "Langsam", "cron": "0 8 * * *", "prompt": "Warte"}
        )

        started = asyncio.Event()
        release = asyncio.Event()

        async def _slow_execute(_task):
            started.set()
            await release.wait()
            return {"status": "ok"}

        scheduler._execute_task = _slow_execute

        result = await asyncio.wait_for(scheduler.run_task_now(task["id"]), timeout=1.0)
        assert result == {"task_id": task["id"], "status": "started"}

        await asyncio.wait_for(started.wait(), timeout=1.0)
        # Zweiter Aufruf während der Task läuft → already_running
        second = await scheduler.run_task_now(task["id"])
        assert second["status"] == "already_running"

        release.set()
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_run_task_now_unknown_task_returns_none(self):
        redis_mock = _store_backed_redis()
        scheduler = _make_scheduler(redis_mock)
        assert await scheduler.run_task_now("gibt-es-nicht") is None
