"""Common agent protocol and adapters for Ninko's legacy execution APIs."""

from __future__ import annotations

from typing import Any, Protocol, cast, runtime_checkable

from schemas.execution import AgentFinishReason, AgentRequest, AgentResponse

TOOL_APPROVAL_SENTINEL = "__TOOL_SAFEGUARD__"
APPROVAL_REQUIRED_MESSAGE = (
    "Ausführung abgebrochen: Die Aktion benötigt eine interaktive Bestätigung."
)
_LEGACY_ERROR_PREFIXES = ("fehler:", "error:", "erreur", "❌")


def _finish_reason_from_legacy_text(response_text: str) -> AgentFinishReason:
    normalized = (response_text or "").strip().lower()
    if response_text.startswith(TOOL_APPROVAL_SENTINEL):
        return AgentFinishReason.APPROVAL_REQUIRED
    if normalized.startswith(_LEGACY_ERROR_PREFIXES):
        return AgentFinishReason.FAILED
    return AgentFinishReason.COMPLETED


class InvokableAgent(Protocol):
    """Legacy Ninko agent surface consumed by ``InvokeAgentAdapter``."""

    async def invoke(
        self,
        message: str,
        chat_history: list[dict[str, Any]] | None = None,
        session_id: str = "",
        confirmed: bool = False,
    ) -> tuple[str, bool]:
        """Return response text and compaction state."""
        ...


class RoutingAgent(Protocol):
    """Legacy orchestrator surface consumed by ``OrchestratorAgentAdapter``."""

    async def route(
        self,
        message: str,
        chat_history: list[dict[str, Any]] | None = None,
        session_id: str = "",
        confirmed: bool = False,
        force_module: str | None = None,
    ) -> tuple[str, str | None, bool, dict[str, Any]]:
        """Return response text, module, compaction state, and routing metadata."""
        ...


@runtime_checkable
class AgentProtocol(Protocol):
    """Minimal structural contract shared by local and remote agents."""

    id: str
    name: str
    description: str

    async def run(self, request: AgentRequest) -> AgentResponse:
        """Execute one non-streaming request."""
        ...


def _is_native_agent(agent: Any) -> bool:
    return (
        callable(getattr(agent, "run", None))
        and isinstance(getattr(agent, "id", None), str)
        and isinstance(getattr(agent, "name", None), str)
        and isinstance(getattr(agent, "description", None), str)
    )


class InvokeAgentAdapter:
    """Expose a legacy ``BaseAgent.invoke`` implementation as ``AgentProtocol``."""

    def __init__(
        self,
        agent: InvokableAgent,
        *,
        agent_id: str,
        name: str,
        description: str = "",
    ) -> None:
        self._agent = agent
        self.id = agent_id
        self.name = name
        self.description = description

    async def run(self, request: AgentRequest) -> AgentResponse:
        response_text, did_compact = await self._agent.invoke(
            message=request.message,
            chat_history=request.chat_history,
            session_id=request.session_id,
            confirmed=request.confirmed,
        )
        compaction_summary = None
        summary_getter = getattr(self._agent, "get_last_compaction_summary", None)
        if did_compact and callable(summary_getter):
            summary = summary_getter()
            if isinstance(summary, str):
                compaction_summary = summary
        return AgentResponse(
            text=response_text,
            agent_id=self.id,
            agent_name=self.name,
            did_compact=did_compact,
            compaction_summary=compaction_summary,
            finish_reason=_finish_reason_from_legacy_text(response_text),
        )


class OrchestratorAgentAdapter:
    """Expose ``OrchestratorAgent.route`` as the common agent protocol."""

    def __init__(
        self,
        orchestrator: RoutingAgent,
        *,
        agent_id: str = "orchestrator",
        name: str = "Orchestrator",
        description: str = "",
    ) -> None:
        self._orchestrator = orchestrator
        self.id = agent_id
        self.name = name
        self.description = description

    async def run(self, request: AgentRequest) -> AgentResponse:
        response_text, module, did_compact, routing_meta = await self._orchestrator.route(
            message=request.message,
            chat_history=request.chat_history,
            session_id=request.session_id,
            confirmed=request.confirmed,
            force_module=request.target,
        )
        return AgentResponse(
            text=response_text,
            agent_id=self.id,
            agent_name=self.name,
            module=module,
            did_compact=did_compact,
            compaction_summary=routing_meta.get("compaction_summary"),
            routing_confidence=routing_meta.get("routing_confidence"),
            tier_used=routing_meta.get("tier_used"),
            finish_reason=_finish_reason_from_legacy_text(response_text),
            metadata={
                key: value
                for key, value in routing_meta.items()
                if key
                not in {
                    "compaction_summary",
                    "routing_confidence",
                    "tier_used",
                }
            },
        )


def as_agent_protocol(
    agent: Any,
    *,
    agent_id: str,
    name: str,
    description: str = "",
) -> AgentProtocol:
    """Return a native protocol agent or adapt a legacy ``invoke`` agent."""
    if _is_native_agent(agent):
        return cast(AgentProtocol, agent)
    return InvokeAgentAdapter(
        agent,
        agent_id=agent_id,
        name=name,
        description=description,
    )


def as_orchestrator_protocol(
    orchestrator: Any,
    *,
    agent_id: str = "orchestrator",
    name: str = "Orchestrator",
    description: str = "",
) -> AgentProtocol:
    """Return a native protocol orchestrator or adapt its legacy ``route`` API."""
    if _is_native_agent(orchestrator):
        return cast(AgentProtocol, orchestrator)
    return OrchestratorAgentAdapter(
        orchestrator,
        agent_id=agent_id,
        name=name,
        description=description,
    )
