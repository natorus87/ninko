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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.workflow_engine import WorkflowCancelledError, WorkflowEngine
from schemas.execution import (
    AgentEventType,
    AgentFinishReason,
    AgentRequest,
    AgentResponse,
)


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
    fake_orchestrator.route = AsyncMock(
        return_value=(
            "OK",
            None,
            False,
            {
                "compaction_summary": None,
                "routing_confidence": None,
                "tier_used": None,
            },
        )
    )

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


@pytest.mark.asyncio
async def test_workflow_accepts_native_protocol_orchestrator() -> None:
    class NativeOrchestrator:
        id = "native-orchestrator"
        name = "Native Orchestrator"
        description = "Common execution contract"

        def __init__(self) -> None:
            self.requests: list[AgentRequest] = []

        async def run(self, request: AgentRequest) -> AgentResponse:
            self.requests.append(request)
            return AgentResponse(
                text="Nativ abgeschlossen",
                agent_id=self.id,
                agent_name=self.name,
            )

    native_orchestrator = NativeOrchestrator()
    engine = WorkflowEngine(MagicMock(), native_orchestrator)

    output, next_label = await engine._execute_node(
        node_type="agent",
        config={"agent_id": "proxmox", "prompt": "Prüfe VM"},
        variables={},
        tenant_id="default",
        parent_run_id="run-1",
        workflow_session_id="default:workflow-run-1",
    )

    assert output == "Nativ abgeschlossen"
    assert next_label is None
    assert native_orchestrator.requests == [
        AgentRequest(
            message="Prüfe VM",
            session_id="default:workflow-run-1",
            confirmed=True,
            target="proxmox",
        )
    ]


@pytest.mark.asyncio
async def test_workflow_raises_for_structured_agent_failure() -> None:
    class FailingOrchestrator:
        id = "native-orchestrator"
        name = "Native Orchestrator"
        description = "Common execution contract"

        async def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                text="Provider nicht erreichbar",
                agent_id=self.id,
                agent_name=self.name,
                finish_reason=AgentFinishReason.FAILED,
            )

    engine = WorkflowEngine(MagicMock(), FailingOrchestrator())

    with pytest.raises(RuntimeError, match="Provider nicht erreichbar"):
        await engine._execute_node(
            node_type="agent",
            config={"agent_id": "proxmox", "prompt": "Prüfe VM"},
            variables={},
            tenant_id="default",
            parent_run_id="run-1",
            workflow_session_id="default:workflow-run-1",
        )


@pytest.mark.asyncio
async def test_structured_cancellation_is_not_retried() -> None:
    class CancelledOrchestrator:
        id = "native-orchestrator"
        name = "Native Orchestrator"
        description = "Common execution contract"

        def __init__(self) -> None:
            self.call_count = 0

        async def run(self, request: AgentRequest) -> AgentResponse:
            self.call_count += 1
            return AgentResponse(
                text="Abgebrochen",
                agent_id=self.id,
                agent_name=self.name,
                finish_reason=AgentFinishReason.CANCELLED,
            )

    orchestrator = CancelledOrchestrator()
    engine = WorkflowEngine(MagicMock(), orchestrator)

    with pytest.raises(WorkflowCancelledError, match="Abgebrochen"):
        await engine._execute_with_retries(
            node_type="agent",
            config={"prompt": "Prüfe VM", "retries": 3},
            variables={},
            tenant_id="default",
            parent_run_id="run-1",
            workflow_session_id="default:workflow-run-1",
        )

    assert orchestrator.call_count == 1


@pytest.mark.asyncio
async def test_asyncio_cancellation_is_persisted_as_cancelled() -> None:
    started = asyncio.Event()

    class BlockingOrchestrator:
        id = "native-orchestrator"
        name = "Native Orchestrator"
        description = "Common execution contract"

        async def run(self, request: AgentRequest) -> AgentResponse:
            started.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    fake_redis = MagicMock()
    fake_redis.connection.get = AsyncMock(return_value=None)
    fake_redis.connection.set = AsyncMock(return_value=None)
    engine = WorkflowEngine(fake_redis, BlockingOrchestrator())
    engine._ensure_run_entry = AsyncMock()
    engine._update_run = AsyncMock()

    task = asyncio.create_task(
        engine.execute(_build_agent_workflow(), "cancelled-run")
    )
    await asyncio.wait_for(started.wait(), timeout=1)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert any(
        call.args[3] == "cancelled"
        for call in engine._update_run.await_args_list
    )


@pytest.mark.asyncio
async def test_workflow_emits_started_and_completed_lifecycle_events() -> None:
    fake_redis = MagicMock()
    fake_redis.connection.get = AsyncMock(return_value=None)
    fake_redis.connection.set = AsyncMock(return_value=None)
    engine = WorkflowEngine(fake_redis, None)
    emitted = AsyncMock()

    with patch("core.workflow_engine.emit_agent_event", emitted):
        await engine.execute(
            _build_agent_workflow(),
            "workflow-run",
            parent_run_id="scheduler-run",
        )

    events = [call.args[0] for call in emitted.await_args_list]
    assert [event.type for event in events] == [
        AgentEventType.STARTED,
        AgentEventType.COMPLETED,
    ]
    assert all(event.run_id == "workflow-run" for event in events)
    assert all(event.parent_run_id == "scheduler-run" for event in events)
