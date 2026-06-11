"""
Unit-tests for WorkflowEngine agent-step: confirmed must be propagated to orchestrator.

Verifies the bugfix for the root cause of the Proxmox-reboot-fails-in-workflow
issue: the workflow engine's `agent` node-type branch was calling
`orchestrator.route(...)` without `confirmed=True`, which caused the safeguard
to pause before any STATE_CHANGING tool call inside the workflow (and the
workflow run hung waiting for user confirmation that never came).

Note: conftest.py sets secure default settings before any core.* import,
so we don't need to set env vars here.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.workflow_engine import WorkflowEngine


def _build_agent_workflow() -> dict:
    """Minimal workflow with one agent-step that should reach the proxmox module."""
    return {
        "id": "default::test-agent-wf",
        "tenant_id": "default",
        "name": "test-agent-wf",
        "description": "Workflow to verify confirmed propagation.",
        "nodes": [
            {
                "id": "start",
                "type": "trigger",
                "label": "Start",
                "config": {"mode": "manual"},
                "position": {"x": 100, "y": 100},
            },
            {
                "id": "reboot",
                "type": "agent",
                "label": "Reboot VM 130",
                "config": {
                    "agent_id": "proxmox",
                    "prompt": "Reboot VM 130 on pve-1",
                },
                "position": {"x": 400, "y": 100},
            },
            {
                "id": "end",
                "type": "end",
                "label": "End",
                "config": {"status": "succeeded"},
                "position": {"x": 700, "y": 100},
            },
        ],
        "edges": [
            {"id": "e1", "source_id": "start", "target_id": "reboot"},
            {"id": "e2", "source_id": "reboot", "target_id": "end"},
        ],
        "variables": [],
        "enabled": True,
    }


@pytest.mark.asyncio
async def test_workflow_agent_step_passes_confirmed_true() -> None:
    """When a workflow runs an agent step, the orchestrator must receive confirmed=True.

    Reason: `execute_workflow` is itself a STATE_CHANGING tool (WRITE_SYSTEM).
    The user has already confirmed the workflow start. Subsequent STATE_CHANGING
    calls inside the workflow (e.g. `reboot_vm`) must NOT pause for another
    confirmation — otherwise the workflow hangs.
    """
    fake_redis = MagicMock()
    fake_redis.connection = MagicMock()
    # The engine writes run snapshots to redis; let it be a no-op.
    fake_redis.connection.set = AsyncMock(return_value=None)
    fake_redis.connection.get = AsyncMock(return_value=None)

    fake_orchestrator = MagicMock()
    fake_orchestrator.route = AsyncMock(return_value=("OK", None, False))

    engine = WorkflowEngine(fake_redis, fake_orchestrator)
    workflow = _build_agent_workflow()
    run_id = "test-run-1234"

    # Run the workflow to completion (or attempt — we only check what route() was called with)
    try:
        await asyncio.wait_for(
            engine.execute(workflow, run_id, triggered_by="AI_Agent"),
            timeout=5.0,
        )
    except Exception:
        # We don't care about the run completing cleanly in this unit-test;
        # we only care about the call to orchestrator.route().
        pass

    # The agent step must have called orchestrator.route() with confirmed=True.
    assert fake_orchestrator.route.await_count >= 1, (
        "Workflow should have invoked orchestrator.route() at least once "
        "for the agent step"
    )

    for call in fake_orchestrator.route.await_args_list:
        kwargs = call.kwargs
        assert kwargs.get("confirmed") is True, (
            f"Workflow agent-step must propagate confirmed=True to orchestrator.route(); "
            f"got kwargs={kwargs}"
        )
        # The force_module must have been propagated for the proxmox agent.
        assert kwargs.get("force_module") == "proxmox", (
            f"force_module should be 'proxmox' as configured in the agent-step; "
            f"got {kwargs.get('force_module')!r}"
        )
