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

    async def _invoke(message: str, chat_history=None):
        if delay:
            await asyncio.sleep(delay)
        return response, False

    agent.invoke = _invoke
    return agent


def _manager_with(redis_mock, agent) -> AgentJobManager:
    pool = MagicMock()
    pool.get_agent_by_id = MagicMock(return_value=(agent, "Test-Agent"))
    with (
        patch("core.redis_client.get_redis", return_value=redis_mock),
        patch("core.agent_pool.get_agent_pool", return_value=pool),
    ):
        manager = AgentJobManager()
        manager._pool_patch = pool  # Referenz fürs Testleben halten
    manager._test_pool = pool
    return manager


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
    async def test_job_lifecycle_succeeded(self):
        redis_mock = _store_backed_redis()
        agent = _agent("Fertig: alles grün.")
        manager = _manager_with(redis_mock, agent)

        with patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool):
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

        with patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool):
            job = await manager.start_job(
                tenant_id="default", agent_id="agent-1", prompt="Mach was"
            )
        final = await _wait_terminal(manager, "default", job["id"])
        assert final["status"] == "failed"

    @pytest.mark.asyncio
    async def test_unknown_agent_raises(self):
        redis_mock = _store_backed_redis()
        pool = MagicMock()
        pool.get_agent_by_id = MagicMock(return_value=(None, ""))
        with patch("core.redis_client.get_redis", return_value=redis_mock):
            manager = AgentJobManager()
        with (
            patch("core.agent_pool.get_agent_pool", return_value=pool),
            pytest.raises(ValueError, match="nicht im Pool"),
        ):
            await manager.start_job(tenant_id="default", agent_id="ghost", prompt="x")

    @pytest.mark.asyncio
    async def test_timeout_marks_failed(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent(delay=5.0))

        with (
            patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool),
            patch("core.agent_jobs.JOB_TIMEOUT_SECONDS", 0.05),
        ):
            job = await manager.start_job(
                tenant_id="default", agent_id="agent-1", prompt="Langsam"
            )
            final = await _wait_terminal(manager, "default", job["id"])
        assert final["status"] == "failed"
        assert "Timeout" in final["error"]


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_running_job(self):
        redis_mock = _store_backed_redis()
        manager = _manager_with(redis_mock, _agent(delay=5.0))

        with patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool):
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
        with patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool):
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

        with patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool):
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

        with patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool):
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
        with patch("core.agent_pool.get_agent_pool", return_value=manager._test_pool):
            job = await manager.start_job(
                tenant_id="default", agent_id="agent-1", prompt="A"
            )
        await _wait_terminal(manager, "default", job["id"])
        assert await manager.get_job("kunde-b", job["id"]) is None
