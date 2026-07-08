"""
Tests für core/workflow_cron_sync.py — Auto-Sync zwischen Workflow-Cron-
Triggern und Scheduler-Tasks.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.workflow_cron_sync import (
    WORKFLOW_TRIGGER_SOURCE,
    remove_workflow_cron_trigger,
    sync_workflow_cron_trigger,
)


def _workflow(cron: str | None, *, enabled: bool = True, wf_id: str = "default::wf-1") -> dict:
    trigger_config = {"mode": "cron", "cron": cron} if cron else {"mode": "manual"}
    return {
        "id": wf_id,
        "name": "Mein Workflow",
        "enabled": enabled,
        "nodes": [
            {"id": "n1", "type": "trigger", "label": "Start", "config": trigger_config},
            {"id": "n2", "type": "end", "label": "Ende", "config": {}},
        ],
        "edges": [{"source_id": "n1", "target_id": "n2"}],
    }


def _scheduler(existing_tasks: list[dict] | None = None) -> MagicMock:
    scheduler = MagicMock()
    scheduler.get_all_tasks = AsyncMock(return_value=existing_tasks or [])
    scheduler.create_task = AsyncMock(return_value={"id": "task-neu"})
    scheduler.update_task = AsyncMock(return_value={"id": "task-alt"})
    scheduler.delete_task = AsyncMock(return_value=True)
    return scheduler


def _existing_task(task_id: str = "task-alt") -> dict:
    return {
        "id": task_id,
        "name": "Workflow-Trigger: Mein Workflow",
        "cron": "0 6 * * *",
        "workflow_id": "wf-1",
        "tenant_id": "default",
        "source": WORKFLOW_TRIGGER_SOURCE,
    }


@pytest.mark.asyncio
async def test_sync_creates_task_for_cron_trigger():
    scheduler = _scheduler()
    with patch("agents.scheduler_agent.get_scheduler_agent", return_value=scheduler):
        result = await sync_workflow_cron_trigger(_workflow("0 8 * * *"), "default")

    assert result == "0 8 * * *"
    scheduler.create_task.assert_awaited_once()
    data = scheduler.create_task.await_args.args[0]
    assert data["workflow_id"] == "wf-1"
    assert data["source"] == WORKFLOW_TRIGGER_SOURCE
    assert data["tenant_id"] == "default"


@pytest.mark.asyncio
async def test_sync_updates_existing_task_without_duplicate():
    scheduler = _scheduler([_existing_task()])
    with patch("agents.scheduler_agent.get_scheduler_agent", return_value=scheduler):
        result = await sync_workflow_cron_trigger(_workflow("0 9 * * *"), "default")

    assert result == "0 9 * * *"
    scheduler.create_task.assert_not_awaited()
    scheduler.update_task.assert_awaited_once()
    assert scheduler.update_task.await_args.args[1]["cron"] == "0 9 * * *"


@pytest.mark.asyncio
async def test_sync_removes_task_when_trigger_switched_to_manual():
    scheduler = _scheduler([_existing_task()])
    with patch("agents.scheduler_agent.get_scheduler_agent", return_value=scheduler):
        result = await sync_workflow_cron_trigger(_workflow(None), "default")

    assert result is None
    scheduler.delete_task.assert_awaited_once_with("task-alt")
    scheduler.create_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_removes_task_when_workflow_disabled():
    scheduler = _scheduler([_existing_task()])
    with patch("agents.scheduler_agent.get_scheduler_agent", return_value=scheduler):
        result = await sync_workflow_cron_trigger(
            _workflow("0 8 * * *", enabled=False), "default"
        )

    assert result is None
    scheduler.delete_task.assert_awaited_once_with("task-alt")


@pytest.mark.asyncio
async def test_remove_deletes_matching_tasks():
    scheduler = _scheduler([_existing_task(), _existing_task("task-2")])
    with patch("agents.scheduler_agent.get_scheduler_agent", return_value=scheduler):
        await remove_workflow_cron_trigger("default", "wf-1")

    assert scheduler.delete_task.await_count == 2


@pytest.mark.asyncio
async def test_remove_ignores_foreign_tenant_and_manual_tasks():
    foreign = {**_existing_task("task-fremd"), "tenant_id": "kunde-b"}
    manual = {**_existing_task("task-manuell"), "source": None}
    scheduler = _scheduler([foreign, manual])
    with patch("agents.scheduler_agent.get_scheduler_agent", return_value=scheduler):
        await remove_workflow_cron_trigger("default", "wf-1")

    scheduler.delete_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_tolerates_missing_scheduler():
    with patch("agents.scheduler_agent.get_scheduler_agent", return_value=None):
        assert await sync_workflow_cron_trigger(_workflow("0 8 * * *"), "default") is None
        await remove_workflow_cron_trigger("default", "wf-1")
