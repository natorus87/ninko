"""Tests for the typed process-local agent event bus."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.agent_events import (
    AgentEventBus,
    configure_agent_event_persistence,
    emit_agent_event,
    on_agent_event,
    remove_agent_event_listener,
    reset_agent_run_id,
    set_agent_run_id,
)
from schemas.execution import AgentEvent, AgentEventType


def _event() -> AgentEvent:
    return AgentEvent(
        type=AgentEventType.STARTED,
        tenant_id="tenant",
        session_id="tenant:session",
        run_id="run-1",
        agent_id="agent-1",
    )


@pytest.mark.asyncio
async def test_persistence_failure_does_not_block_live_listener(
    caplog: pytest.LogCaptureFixture,
) -> None:
    received: list[AgentEvent] = []
    event = _event()

    async def failing_sink(event: AgentEvent) -> None:
        raise RuntimeError("storage-secret")

    async def listener(event: AgentEvent) -> None:
        received.append(event)

    configure_agent_event_persistence(failing_sink)
    on_agent_event(listener, tenant_id="tenant")
    try:
        await emit_agent_event(event)
    finally:
        configure_agent_event_persistence(None)
        remove_agent_event_listener(listener)

    assert received == [event]
    assert "RuntimeError" in caplog.text
    assert "storage-secret" not in caplog.text


@pytest.mark.asyncio
async def test_event_is_persisted_before_process_local_delivery() -> None:
    call_order: list[str] = []
    event = _event()

    async def persistence_sink(persisted_event: AgentEvent) -> None:
        assert persisted_event == event
        call_order.append("persist")

    async def listener(delivered_event: AgentEvent) -> None:
        assert delivered_event == event
        call_order.append("deliver")

    configure_agent_event_persistence(persistence_sink)
    on_agent_event(listener, tenant_id="tenant")
    try:
        await emit_agent_event(event)
    finally:
        configure_agent_event_persistence(None)
        remove_agent_event_listener(listener)

    assert call_order == ["persist", "deliver"]


@pytest.mark.asyncio
async def test_persistence_timeout_opens_short_circuit_breaker() -> None:
    calls = 0
    event = _event()

    async def hanging_sink(persisted_event: AgentEvent) -> None:
        nonlocal calls
        calls += 1
        await asyncio.Future()

    configure_agent_event_persistence(hanging_sink)
    try:
        await emit_agent_event(event)
        await emit_agent_event(event)
    finally:
        configure_agent_event_persistence(None)

    assert calls == 1


@pytest.mark.asyncio
async def test_listener_failure_does_not_block_other_listeners(caplog) -> None:
    bus = AgentEventBus()
    received: list[AgentEvent] = []

    async def failing_listener(event: AgentEvent) -> None:
        raise RuntimeError("listener broken")

    async def healthy_listener(event: AgentEvent) -> None:
        received.append(event)

    bus.subscribe(failing_listener, allow_all_tenants=True)
    bus.subscribe(healthy_listener, allow_all_tenants=True)

    with caplog.at_level(logging.WARNING, logger="ninko.agent_events"):
        await bus.emit(_event())

    assert [event.run_id for event in received] == ["run-1"]
    assert "RuntimeError" in caplog.text
    assert "listener broken" not in caplog.text


@pytest.mark.asyncio
async def test_subscribe_is_idempotent_and_unsubscribe_is_explicit() -> None:
    bus = AgentEventBus()
    received: list[AgentEvent] = []

    async def listener(event: AgentEvent) -> None:
        received.append(event)

    bus.subscribe(listener, tenant_id="tenant")
    bus.subscribe(listener, tenant_id="tenant")

    assert bus.listener_count == 1
    await bus.emit(_event())
    assert len(received) == 1
    assert bus.unsubscribe(listener) is True
    assert bus.unsubscribe(listener) is False
    assert bus.listener_count == 0


@pytest.mark.asyncio
async def test_listener_can_unsubscribe_during_delivery() -> None:
    bus = AgentEventBus()
    received: list[str] = []

    async def self_removing_listener(event: AgentEvent) -> None:
        received.append(event.run_id)
        bus.unsubscribe(self_removing_listener)

    bus.subscribe(self_removing_listener, session_id="tenant:session")

    await bus.emit(_event())
    await bus.emit(_event().model_copy(update={"run_id": "run-2"}))

    assert received == ["run-1"]


def test_unscoped_listener_requires_explicit_trusted_global_access() -> None:
    bus = AgentEventBus()

    async def listener(event: AgentEvent) -> None:
        return None

    with pytest.raises(ValueError, match="tenant_id oder session_id"):
        bus.subscribe(listener)


@pytest.mark.asyncio
async def test_tenant_scope_filters_events_before_delivery() -> None:
    bus = AgentEventBus()
    received: list[str] = []

    async def listener(event: AgentEvent) -> None:
        received.append(event.tenant_id)

    bus.subscribe(listener, tenant_id="other-tenant")
    await bus.emit(_event())

    assert received == []


@pytest.mark.asyncio
async def test_slow_listener_times_out_without_blocking_healthy_listener(caplog) -> None:
    bus = AgentEventBus(listener_timeout_seconds=0.01)
    received: list[str] = []

    async def hanging_listener(event: AgentEvent) -> None:
        await asyncio.Event().wait()

    async def healthy_listener(event: AgentEvent) -> None:
        received.append(event.run_id)

    bus.subscribe(hanging_listener, allow_all_tenants=True)
    bus.subscribe(healthy_listener, allow_all_tenants=True)

    with caplog.at_level(logging.WARNING, logger="ninko.agent_events"):
        await asyncio.wait_for(bus.emit(_event()), timeout=0.2)

    assert received == ["run-1"]
    assert "TimeoutError" in caplog.text


@pytest.mark.asyncio
async def test_each_listener_receives_an_independent_event_copy() -> None:
    bus = AgentEventBus()
    mutated = asyncio.Event()
    observed: list[dict] = []

    async def mutating_listener(event: AgentEvent) -> None:
        event.data["status"] = "tampered"
        mutated.set()

    async def observing_listener(event: AgentEvent) -> None:
        await mutated.wait()
        observed.append(event.data)

    bus.subscribe(mutating_listener, allow_all_tenants=True)
    bus.subscribe(observing_listener, allow_all_tenants=True)
    original = _event().model_copy(update={"data": {"status": "original"}})

    await bus.emit(original)

    assert observed == [{"status": "original"}]
    assert original.data == {"status": "original"}


@pytest.mark.asyncio
async def test_emit_delivers_to_all_listeners_concurrently() -> None:
    bus = AgentEventBus()
    started: set[str] = set()
    all_started = asyncio.Event()
    release = asyncio.Event()

    def make_listener(name: str):
        async def listener(event: AgentEvent) -> None:
            started.add(name)
            if len(started) == 2:
                all_started.set()
            await release.wait()

        return listener

    bus.subscribe(make_listener("first"), allow_all_tenants=True)
    bus.subscribe(make_listener("second"), allow_all_tenants=True)

    emit_task = asyncio.create_task(bus.emit(_event()))
    try:
        await asyncio.wait_for(all_started.wait(), timeout=1)
    finally:
        release.set()
        await emit_task

    assert started == {"first", "second"}


@pytest.mark.asyncio
async def test_status_emitter_bridges_sanitized_tool_lifecycle() -> None:
    from agents.base_agent import _StatusEmitter

    events: list[AgentEvent] = []
    tool_result_received = asyncio.Event()

    async def listener(event: AgentEvent) -> None:
        events.append(event)
        if event.type == AgentEventType.TOOL_RESULT:
            tool_result_received.set()

    on_agent_event(listener, session_id="tenant:session")
    emitter = _StatusEmitter("tenant:session", "Kubernetes")
    registry = MagicMock()
    registry.is_readonly.return_value = True
    try:
        with (
            patch("agents.base_agent.status_bus.emit_event", new=AsyncMock()),
            patch("agents.base_agent.emit_tool_event", new=AsyncMock()),
            patch("agents.base_agent.get_tool_registry", return_value=registry),
        ):
            await emitter.on_tool_start(
                {"name": "get_pods"},
                '{"namespace":"default","token":"secret"}',
                run_id="tool-run-1",
                parent_run_id="agent-run-1",
            )
            await emitter.on_tool_end(
                "2 pods",
                name="get_pods",
                run_id="tool-run-1",
                parent_run_id="agent-run-1",
            )
            await asyncio.wait_for(tool_result_received.wait(), timeout=1)
    finally:
        remove_agent_event_listener(listener)

    assert [event.type for event in events] == [
        AgentEventType.TOOL_CALL,
        AgentEventType.TOOL_RESULT,
    ]
    assert {event.run_id for event in events} == {"tool-run-1"}
    assert {event.parent_run_id for event in events} == {"agent-run-1"}
    assert events[0].data["args"]["token"] == "***"


@pytest.mark.asyncio
async def test_status_emitter_closes_tool_lifecycle_on_error() -> None:
    from agents.base_agent import _StatusEmitter

    events: list[AgentEvent] = []

    async def listener(event: AgentEvent) -> None:
        events.append(event)

    on_agent_event(listener, session_id="tenant:session")
    emitter = _StatusEmitter("tenant:session", "Kubernetes")
    registry = MagicMock()
    registry.is_readonly.return_value = True
    context_token = set_agent_run_id("logical-agent-run")
    try:
        with (
            patch("agents.base_agent.status_bus.emit_event", new=AsyncMock()),
            patch("agents.base_agent.emit_tool_event", new=AsyncMock()),
            patch("agents.base_agent.get_tool_registry", return_value=registry),
        ):
            await emitter.on_tool_start(
                {"name": "get_pods"},
                '{"token":"secret"}',
                run_id="tool-error-run",
                parent_run_id="provider-run",
            )
            await emitter.on_tool_error(
                RuntimeError("token=secret"),
                name="get_pods",
                run_id="tool-error-run",
                parent_run_id="provider-run",
            )
    finally:
        reset_agent_run_id(context_token)
        remove_agent_event_listener(listener)

    assert [event.type for event in events] == [
        AgentEventType.TOOL_CALL,
        AgentEventType.TOOL_RESULT,
    ]
    assert {event.parent_run_id for event in events} == {"logical-agent-run"}
    assert events[-1].data["error"] == "token=***"
    assert "secret" not in str(events[-1].data)
    assert emitter._tool_start_times == {}
    assert emitter._tool_args == {}
