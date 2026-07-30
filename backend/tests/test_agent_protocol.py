"""Unit tests for the common agent execution contract."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from core.agent_protocol import (
    TOOL_APPROVAL_SENTINEL,
    AgentProtocol,
    InvokeAgentAdapter,
    OrchestratorAgentAdapter,
    as_agent_protocol,
)
from schemas.execution import (
    AgentEvent,
    AgentEventType,
    AgentFinishReason,
    AgentRequest,
    AgentResponse,
)


def test_agent_request_rejects_blank_message() -> None:
    with pytest.raises(ValidationError, match="message darf nicht leer sein"):
        AgentRequest(message="   ")


def test_agent_event_serializes_stable_discriminator() -> None:
    event = AgentEvent(
        type=AgentEventType.STATUS,
        tenant_id="tenant",
        session_id="tenant:session",
        run_id="run-1",
        agent_id="agent-1",
        data={"phase": "routing"},
    )

    payload = event.model_dump(mode="json")

    assert payload["type"] == "status"
    assert payload["event_id"]
    assert payload["timestamp"].endswith(("Z", "+00:00"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", ""),
        ("tenant_id", " "),
        ("session_id", ""),
        ("run_id", " "),
        ("agent_id", ""),
    ],
)
def test_agent_event_rejects_blank_identity_fields(
    field: str,
    value: str,
) -> None:
    payload = {
        "event_id": "event-1",
        "type": AgentEventType.STARTED,
        "tenant_id": "tenant",
        "session_id": "tenant:session",
        "run_id": "run-1",
        "agent_id": "agent-1",
    }
    payload[field] = value

    with pytest.raises(ValidationError, match="nicht leer"):
        AgentEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("event_id", "e" * 129),
        ("tenant_id", "t" * 129),
        ("session_id", "s" * 513),
        ("run_id", "r" * 257),
        ("parent_run_id", "p" * 257),
        ("agent_id", "a" * 129),
    ],
)
def test_agent_event_rejects_oversized_identity_fields(
    field: str,
    value: str,
) -> None:
    payload = {
        "event_id": "event-1",
        "type": AgentEventType.STARTED,
        "tenant_id": "tenant",
        "session_id": "tenant:session",
        "run_id": "run-1",
        "parent_run_id": None,
        "agent_id": "agent-1",
    }
    payload[field] = value

    with pytest.raises(ValidationError):
        AgentEvent.model_validate(payload)


@pytest.mark.asyncio
async def test_invoke_adapter_maps_legacy_tuple_to_response() -> None:
    legacy_agent = MagicMock()
    legacy_agent.invoke = AsyncMock(return_value=("Fertig.", True))
    legacy_agent.get_last_compaction_summary.return_value = "Verdichteter Kontext"
    adapter = InvokeAgentAdapter(
        legacy_agent,
        agent_id="agent-1",
        name="Test Agent",
        description="Test",
    )

    assert isinstance(adapter, AgentProtocol)

    response = await adapter.run(
        AgentRequest(
            message="Prüfe den Status",
            chat_history=[{"role": "user", "content": "Vorher"}],
            session_id="tenant:session",
            confirmed=True,
        )
    )

    assert response.text == "Fertig."
    assert response.agent_id == "agent-1"
    assert response.did_compact is True
    assert response.compaction_summary == "Verdichteter Kontext"
    legacy_agent.invoke.assert_awaited_once_with(
        message="Prüfe den Status",
        chat_history=[{"role": "user", "content": "Vorher"}],
        session_id="tenant:session",
        confirmed=True,
    )
    legacy_agent.get_last_compaction_summary.assert_called_once_with()


@pytest.mark.asyncio
async def test_invoke_adapter_preserves_agent_errors() -> None:
    legacy_agent = AsyncMock()
    legacy_agent.invoke.side_effect = RuntimeError("Provider nicht erreichbar")
    adapter = InvokeAgentAdapter(
        legacy_agent,
        agent_id="agent-1",
        name="Test Agent",
    )

    with pytest.raises(RuntimeError, match="Provider nicht erreichbar"):
        await adapter.run(AgentRequest(message="Prüfe den Status"))


@pytest.mark.asyncio
async def test_invoke_adapter_maps_approval_sentinel() -> None:
    legacy_agent = AsyncMock()
    legacy_agent.invoke.return_value = (
        f'{TOOL_APPROVAL_SENTINEL}{{"tool_name":"restart_server"}}',
        False,
    )
    adapter = InvokeAgentAdapter(
        legacy_agent,
        agent_id="agent-1",
        name="Test Agent",
    )

    response = await adapter.run(AgentRequest(message="Starte den Server neu"))

    assert response.finish_reason == AgentFinishReason.APPROVAL_REQUIRED


def test_as_agent_protocol_preserves_native_agent() -> None:
    class NativeAgent:
        id = "native-1"
        name = "Native"
        description = "Already uses the common contract"

        async def run(self, request: AgentRequest) -> AgentResponse:
            return AgentResponse(
                text=request.message,
                agent_id=self.id,
                agent_name=self.name,
            )

    native_agent = NativeAgent()

    assert as_agent_protocol(native_agent, agent_id="legacy", name="Legacy") is native_agent


@pytest.mark.asyncio
async def test_orchestrator_adapter_maps_routing_metadata() -> None:
    orchestrator = AsyncMock()
    orchestrator.route.return_value = (
        "Drei Pods laufen.",
        "kubernetes",
        False,
        {
            "compaction_summary": "Kurzfassung",
            "routing_confidence": 0.92,
            "tier_used": 2,
            "cache_hit": True,
        },
    )
    adapter = OrchestratorAgentAdapter(orchestrator)

    response = await adapter.run(
        AgentRequest(
            message="Zeige Pods",
            session_id="tenant:session",
            target=" kubernetes ",
        )
    )

    assert response.module == "kubernetes"
    assert response.compaction_summary == "Kurzfassung"
    assert response.routing_confidence == 0.92
    assert response.tier_used == 2
    assert response.metadata == {"cache_hit": True}
    orchestrator.route.assert_awaited_once_with(
        message="Zeige Pods",
        chat_history=[],
        session_id="tenant:session",
        confirmed=False,
        force_module="kubernetes",
    )
