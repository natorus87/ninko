"""
Tests für core/agent_jobs.py — einmalige Hintergrund-Ausführung von Agenten.
"""

from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agent_jobs import (
    JOB_TTL_SECONDS,
    MAX_JOBS_PER_AGENT,
    AgentJobManager,
    _job_key,
)
from core.agent_events import (
    get_agent_run_id,
    on_agent_event,
    remove_agent_event_listener,
)
from core.agent_protocol import TOOL_APPROVAL_SENTINEL
from core.agent_protocol import APPROVAL_REQUIRED_MESSAGE
from schemas.execution import AgentEvent, AgentEventType, AgentRequest, AgentResponse


def _store_backed_redis() -> MagicMock:
    store: dict[str, str] = {}
    lists: dict[str, list[str]] = {}

    redis_mock = MagicMock()
    redis_mock._store = store
    redis_mock._lists = lists

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

    async def _lrange(key, start, stop):
        return lists.get(key, [])[start : stop + 1 if stop >= 0 else None]

    redis_mock.connection.get = AsyncMock(side_effect=_get)
    redis_mock.connection.set = AsyncMock(side_effect=_set)
    redis_mock.connection.lpush = AsyncMock(side_effect=_lpush)
    redis_mock.connection.ltrim = AsyncMock(side_effect=_ltrim)
    redis_mock.connection.lrange = AsyncMock(side_effect=_lrange)
    redis_mock.publish_event = AsyncMock(return_value=True)
    return redis_mock


def _agent(response: str = "Alles erledigt.", delay: float = 0.0):
    agent = MagicMock()

    async def _invoke(
        message: str,
        chat_history=None,
        session_id: str = "",
        confirmed: bool = False,
    ):
        if delay:
            await asyncio.sleep(delay)
        return response, False

    agent.invoke = _invoke
    return agent


def _manager_with(redis_mock, agent) -> AgentJobManager:
    pool = MagicMock()
    pool.get_agent_by_id = MagicMock(return_value=(agent, "Test-Agent"))
    return AgentJobManager(redis=redis_mock, agent_pool=pool)


async def _wait_terminal(
    manager: AgentJobManager, tenant: str, job_id: str, timeout: float = 2.0
) -> dict:
    async def _poll():
        while True:
            job = await manager.get_job(tenant, job_id)
            if job and job["status"] in ("succeeded", "failed", "cancelled"):
                return job
            await asyncio.sleep(0.01)

    return await asyncio.wait_for(_poll(), timeout=timeout)


class TestStartJob:
    @pytest.mark.asyncio
    async def test_job_emits_typed_lifecycle_events(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent("Fertig."))
        events: list[AgentEvent] = []
        completed = asyncio.Event()

        async def listener(event: AgentEvent) -> None:
            events.append(event)
            if event.type == AgentEventType.COMPLETED:
                completed.set()

        on_agent_event(listener, tenant_id="default")
        try:
            job = await manager.start_job(
                tenant_id="default",
                agent_id="agent-1",
                prompt="Mach was",
            )
            await _wait_terminal(manager, "default", job["id"])
            await asyncio.wait_for(completed.wait(), timeout=1)
        finally:
            remove_agent_event_listener(listener)

        assert [event.type for event in events] == [
            AgentEventType.STARTED,
            AgentEventType.COMPLETED,
        ]
        assert {event.run_id for event in events} == {job["id"]}
        assert {event.session_id for event in events} == {
            f"default:job-{job['id']}"
        }

    @pytest.mark.asyncio
    async def test_job_lifecycle_succeeded(self):
        redis_mock = _store_backed_redis()
        agent = _agent("Fertig: alles grün.")
        manager = _manager_with(redis_mock, agent)

        job = await manager.start_job(
            tenant_id="default", agent_id="agent-1", prompt="Mach was", triggered_by="api"
        )
        assert job["status"] == "pending"

        final = await _wait_terminal(manager, "default", job["id"])
        assert final["status"] == "succeeded"
        assert "grün" in final["result"]
        assert final["duration_ms"] is not None

        # Event publiziert
        events = [c.args[0] for c in redis_mock.publish_event.await_args_list]
        assert any(e["type"] == "agent_job_finished" and e["status"] == "succeeded" for e in events)

        # Persistiert mit TTL
        set_kwargs = [c.kwargs for c in redis_mock.connection.set.await_args_list if c.kwargs]
        assert any(kw.get("ex") == JOB_TTL_SECONDS for kw in set_kwargs)

    @pytest.mark.asyncio
    async def test_error_response_marks_failed(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent("Fehler: Modul nicht erreichbar"))

        job = await manager.start_job(
            tenant_id="default", agent_id="agent-1", prompt="Mach was"
        )
        final = await _wait_terminal(manager, "default", job["id"])
        assert final["status"] == "failed"

    @pytest.mark.asyncio
    async def test_approval_required_response_is_not_marked_succeeded(self):
        redis_mock = _store_backed_redis()
        sentinel = f'{TOOL_APPROVAL_SENTINEL}{{"tool_name":"restart_server"}}'
        manager = _manager_with(redis_mock, _agent(sentinel))

        with patch(
            "core.agent_jobs.discard_pending_approval",
            new=AsyncMock(),
        ) as discard_pending:
            job = await manager.start_job(
                tenant_id="default",
                agent_id="agent-1",
                prompt="Starte den Server neu",
            )
            final = await _wait_terminal(manager, "default", job["id"])

        assert final["status"] == "failed"
        assert final["error"] == APPROVAL_REQUIRED_MESSAGE
        assert final["result"] == APPROVAL_REQUIRED_MESSAGE
        discard_pending.assert_awaited_once_with(
            f"default:job-{job['id']}",
            redis=redis_mock,
        )

    @pytest.mark.asyncio
    async def test_native_protocol_agent_runs_without_legacy_invoke(self):
        class NativeAgent:
            id = "agent-1"
            name = "Native Agent"
            description = "Native contract test"

            def __init__(self) -> None:
                self.requests: list[AgentRequest] = []
                self.run_contexts: list[str] = []

            async def run(self, request: AgentRequest) -> AgentResponse:
                self.requests.append(request)
                self.run_contexts.append(get_agent_run_id())
                return AgentResponse(
                    text="Nativ fertig.",
                    agent_id=self.id,
                    agent_name=self.name,
                )

        redis_mock = _store_backed_redis()
        native_agent = NativeAgent()
        manager = _manager_with(redis_mock, native_agent)

        job = await manager.start_job(
            tenant_id="default",
            agent_id="agent-1",
            prompt="Prüfe nativ",
        )
        final = await _wait_terminal(manager, "default", job["id"])

        assert final["status"] == "succeeded"
        assert final["result"] == "Nativ fertig."
        assert native_agent.requests[0].message == "Prüfe nativ"
        assert native_agent.run_contexts == [job["id"]]

    @pytest.mark.asyncio
    async def test_unknown_agent_raises(self):
        redis_mock = _store_backed_redis()
        pool = MagicMock()
        pool.get_agent_by_id = MagicMock(return_value=(None, ""))
        manager = AgentJobManager(redis=redis_mock, agent_pool=pool)
        with pytest.raises(ValueError, match="nicht im Pool"):
            await manager.start_job(tenant_id="default", agent_id="ghost", prompt="x")

    @pytest.mark.asyncio
    async def test_timeout_marks_failed(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent(delay=5.0))

        with patch("core.agent_jobs.JOB_TIMEOUT_SECONDS", 0.05):
            job = await manager.start_job(
                tenant_id="default", agent_id="agent-1", prompt="Langsam"
            )
            final = await _wait_terminal(manager, "default", job["id"])
        assert final["status"] == "failed"
        assert "Timeout" in final["error"]


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_during_started_listener_still_finalizes_job(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent(delay=5.0))
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def listener(event: AgentEvent) -> None:
            if event.type == AgentEventType.STARTED:
                started.set()
                await asyncio.Event().wait()
            if event.type == AgentEventType.CANCELLED:
                cancelled.set()

        on_agent_event(listener, tenant_id="default")
        try:
            job = await manager.start_job(
                tenant_id="default",
                agent_id="agent-1",
                prompt="Langsam",
            )
            await asyncio.wait_for(started.wait(), timeout=1)
            await manager.cancel_job("default", job["id"])
            await asyncio.wait_for(cancelled.wait(), timeout=1)
            final = await _wait_terminal(manager, "default", job["id"])
        finally:
            remove_agent_event_listener(listener)

        assert final["status"] == "cancelled"
        assert final["finish_reason"] == "cancelled"
        assert final["finished_at"] is not None

    @pytest.mark.asyncio
    async def test_cancel_recovered_job_uses_normal_terminal_lifecycle(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent())
        job = {
            "id": "recovered-job",
            "tenant_id": "default",
            "agent_id": "agent-1",
            "agent_name": "Test-Agent",
            "prompt": "Alt",
            "status": "running",
            "finish_reason": None,
            "result": None,
            "error": None,
            "triggered_by": "api",
            "created_at": "2026-07-29T00:00:00+00:00",
            "started_at": "2026-07-29T00:00:01+00:00",
            "finished_at": None,
            "duration_ms": None,
        }
        await manager._persist(job)
        events: list[AgentEvent] = []

        async def listener(event: AgentEvent) -> None:
            events.append(event)

        on_agent_event(listener, tenant_id="default")
        try:
            final = await manager.cancel_job("default", job["id"])
        finally:
            remove_agent_event_listener(listener)

        assert final["status"] == "cancelled"
        assert final["finish_reason"] == "cancelled"
        assert final["duration_ms"] is not None
        assert [event.type for event in events] == [AgentEventType.CANCELLED]
        redis_events = [
            call.args[0]
            for call in redis_mock.publish_event.await_args_list
        ]
        assert redis_events[-1]["type"] == "agent_job_finished"
        assert redis_events[-1]["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_running_job(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent(delay=5.0))

        job = await manager.start_job(
            tenant_id="default", agent_id="agent-1", prompt="Langsam"
        )
        await asyncio.sleep(0.05)  # Job in running bringen

        result = await manager.cancel_job("default", job["id"])
        assert result["status"] == "cancelled"

        final = await _wait_terminal(manager, "default", job["id"])
        assert final["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_terminal_job_raises(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent())
        job = await manager.start_job(
            tenant_id="default", agent_id="agent-1", prompt="Schnell"
        )
        await _wait_terminal(manager, "default", job["id"])
        with pytest.raises(ValueError, match="bereits beendet"):
            await manager.cancel_job("default", job["id"])

    @pytest.mark.asyncio
    async def test_cancel_unknown_job_raises(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent())
        with pytest.raises(ValueError, match="nicht gefunden"):
            await manager.cancel_job("default", "gibt-es-nicht")


class TestListJobs:
    @pytest.mark.asyncio
    async def test_list_jobs_filters_expired_entries(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent())

        job = await manager.start_job(
            tenant_id="default", agent_id="agent-1", prompt="A"
        )
        await _wait_terminal(manager, "default", job["id"])

        # Toten Index-Eintrag simulieren (Job-Key per TTL verschwunden)
        redis_mock._lists["ninko:agent:jobs:index:default:agent-1"].append("abgelaufen-123")

        jobs = await manager.list_jobs("default", "agent-1")
        assert [j["id"] for j in jobs] == [job["id"]]

    @pytest.mark.asyncio
    async def test_index_trimmed_to_max(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent())
        index_key = "ninko:agent:jobs:index:default:agent-1"
        redis_mock._lists[index_key] = [f"alt-{i}" for i in range(MAX_JOBS_PER_AGENT)]

        job = await manager.start_job(
            tenant_id="default", agent_id="agent-1", prompt="A"
        )
        await _wait_terminal(manager, "default", job["id"])
        assert len(redis_mock._lists[index_key]) == MAX_JOBS_PER_AGENT
        assert redis_mock._lists[index_key][0] == job["id"]


class TestTenantScoping:
    @pytest.mark.asyncio
    async def test_job_key_is_tenant_scoped(self):
        assert _job_key("Kunde A", "j1") == "ninko:agent:job:kunde_a:j1"

    @pytest.mark.asyncio
    async def test_get_job_other_tenant_not_found(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent())
        job = await manager.start_job(
            tenant_id="default", agent_id="agent-1", prompt="A"
        )
        await _wait_terminal(manager, "default", job["id"])
        assert await manager.get_job("kunde-b", job["id"]) is None


class TestShutdown:
    @pytest.mark.asyncio
    async def test_shutdown_cancels_and_awaits_running_tasks(self):
        manager = _manager_with(_store_backed_redis(), _agent())
        finalized = asyncio.Event()

        async def running_job() -> None:
            try:
                await asyncio.Future()
            finally:
                finalized.set()

        task = asyncio.create_task(running_job())
        manager._running["job-1"] = task
        await asyncio.sleep(0)

        await manager.shutdown()

        assert task.cancelled()
        assert finalized.is_set()
