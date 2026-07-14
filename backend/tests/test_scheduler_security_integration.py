"""Tests fuer die Scheduler-Integration von Security-Workflows (Task 9).

Deterministischer Pfad in scheduler_agent.py._execute_task(): security_workflow_id
+ security_target_id -> modules.security.workflows.run_security_workflow() DIREKT,
OHNE Orchestrator/LLM-Umweg (Auftragsprinzip: kein ReAct-Fallback bei Security-
Aufgaben). trigger_type=CRON wird explizit gesetzt, damit policy.py intrusive-
Profile korrekt vom automatischen Scheduling ausschliesst.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.scheduler_agent import SchedulerAgent


def _store_backed_redis() -> MagicMock:
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


def _make_scheduler(redis_mock) -> SchedulerAgent:
    with patch("agents.scheduler_agent.get_redis", return_value=redis_mock):
        return SchedulerAgent(registry=MagicMock(), orchestrator=MagicMock())


pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_security_task_calls_run_security_workflow_directly_not_orchestrator():
    """Der Security-Pfad darf NIE ueber self.orchestrator.route() laufen."""
    redis_mock = _store_backed_redis()
    scheduler = _make_scheduler(redis_mock)
    scheduler.orchestrator.route = AsyncMock(side_effect=AssertionError("Orchestrator haette nie aufgerufen werden duerfen"))

    fake_target = SimpleNamespace(id="target-1")
    fake_result = SimpleNamespace(
        total_findings=3, executed_scanner_ids=["trivy"], skipped_scanner_ids=[],
    )

    task = {
        "id": "task-1", "name": "Nightly Image Scan", "cron": "0 2 * * *",
        "security_workflow_id": "container_image_audit", "security_target_id": "target-1",
        "tenant_id": "default",
    }

    with (
        patch("modules.security.db.get_target", AsyncMock(return_value=fake_target)),
        patch("modules.security.workflows.run_security_workflow", AsyncMock(return_value=fake_result)) as mock_run,
    ):
        log_entry = await scheduler._execute_task(task)

    assert log_entry["status"] == "ok"
    assert log_entry["module_used"] == "security"
    assert "3 Findings" in log_entry["response"]
    scheduler.orchestrator.route.assert_not_called()
    # trigger_type muss explizit CRON sein (nicht MANUAL) — sonst wuerde policy.py
    # intrusive Profile faelschlich als manuell ausgeloest durchwinken.
    from modules.security.models import TriggerType

    _, kwargs = mock_run.call_args
    assert kwargs["trigger_type"] == TriggerType.CRON


@pytest.mark.asyncio
async def test_security_task_missing_target_reports_error():
    redis_mock = _store_backed_redis()
    scheduler = _make_scheduler(redis_mock)

    task = {
        "id": "task-1", "name": "Broken Task", "cron": "0 2 * * *",
        "security_workflow_id": "container_image_audit", "security_target_id": "does-not-exist",
        "tenant_id": "default",
    }
    with patch("modules.security.db.get_target", AsyncMock(return_value=None)):
        log_entry = await scheduler._execute_task(task)

    assert log_entry["status"] == "error"
    assert "does-not-exist" in log_entry["response"]


@pytest.mark.asyncio
async def test_security_task_response_lists_skipped_scanners():
    redis_mock = _store_backed_redis()
    scheduler = _make_scheduler(redis_mock)

    fake_target = SimpleNamespace(id="target-1")
    fake_result = SimpleNamespace(
        total_findings=0, executed_scanner_ids=[], skipped_scanner_ids=["garak"],
    )
    task = {
        "id": "task-1", "name": "AI Audit", "cron": "0 3 * * *",
        "security_workflow_id": "ai_platform_audit", "security_target_id": "target-1",
        "tenant_id": "default",
    }
    with (
        patch("modules.security.db.get_target", AsyncMock(return_value=fake_target)),
        patch("modules.security.workflows.run_security_workflow", AsyncMock(return_value=fake_result)),
    ):
        log_entry = await scheduler._execute_task(task)

    assert log_entry["status"] == "ok"
    assert "garak" in log_entry["response"]
    assert "Uebersprungen" in log_entry["response"]


@pytest.mark.asyncio
async def test_security_task_takes_priority_over_workflow_id_if_both_set():
    """security_workflow_id hat Vorrang vor workflow_id, falls beide gesetzt sind
    (sollte in der Praxis nicht vorkommen, aber der deterministische Pfad muss
    Vorrang haben — kein Fallback auf den Orchestrator-Workflow-Pfad)."""
    redis_mock = _store_backed_redis()
    scheduler = _make_scheduler(redis_mock)

    fake_target = SimpleNamespace(id="target-1")
    fake_result = SimpleNamespace(total_findings=0, executed_scanner_ids=["trivy"], skipped_scanner_ids=[])
    task = {
        "id": "task-1", "name": "Both set", "cron": "0 2 * * *",
        "workflow_id": "some-other-workflow",
        "security_workflow_id": "container_image_audit", "security_target_id": "target-1",
        "tenant_id": "default",
    }
    with (
        patch("modules.security.db.get_target", AsyncMock(return_value=fake_target)),
        patch("modules.security.workflows.run_security_workflow", AsyncMock(return_value=fake_result)),
    ):
        log_entry = await scheduler._execute_task(task)

    assert log_entry["module_used"] == "security"


@pytest.mark.asyncio
async def test_create_task_persists_security_fields():
    redis_mock = _store_backed_redis()
    redis_mock._store["ninko:scheduler:tasks"] = json.dumps([])
    scheduler = _make_scheduler(redis_mock)

    task = await scheduler.create_task({
        "name": "Nightly Repo Audit", "cron": "0 1 * * *",
        "security_workflow_id": "git_repository_audit", "security_target_id": "target-42",
    })
    assert task["security_workflow_id"] == "git_repository_audit"
    assert task["security_target_id"] == "target-42"


@pytest.mark.asyncio
async def test_update_task_can_change_security_fields():
    redis_mock = _store_backed_redis()
    existing_task = {
        "id": "task-1", "name": "X", "cron": "0 1 * * *", "security_workflow_id": "container_image_audit",
        "security_target_id": "old-target", "tenant_id": "default",
    }
    redis_mock._store["ninko:scheduler:tasks"] = json.dumps([existing_task])
    scheduler = _make_scheduler(redis_mock)

    updated = await scheduler.update_task("task-1", {"security_target_id": "new-target"})
    assert updated["security_target_id"] == "new-target"
