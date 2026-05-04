"""Validation that agent responses match required tool execution."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from langchain_core.messages import AIMessage, ToolMessage

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RequiredToolRule:
    """A deterministic rule describing which tool must run for a request."""

    name: str
    agent_name: str
    message_patterns: tuple[re.Pattern[str], ...]
    required_tools: frozenset[str]
    reason: str

    def matches(self, ctx: MiddlewareContext) -> bool:
        if ctx.agent_name != self.agent_name:
            return False
        return all(pattern.search(ctx.message) for pattern in self.message_patterns)


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


_REQUIRED_TOOL_RULES: tuple[RequiredToolRule, ...] = (
    RequiredToolRule(
        name="licium_existing_notes_ingest",
        agent_name="licium",
        message_patterns=(
            _rx(r"\b(bestehend(?:e|en)?\s+notizen|existing\s+notes|alle\s+notizen)\b"),
            _rx(r"\b(ingest\w*|import\w*)\b"),
            _rx(r"\b(ninko[-\s]?wiki|wiki)\b"),
        ),
        required_tools=frozenset({"ingest_existing_licium_notes"}),
        reason="Bestehende Licium-Notizen sollten deterministisch ins Ninko-Wiki importiert werden.",
    ),
)

_FUTURE_COMMITMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    _rx(r"\bich\s+(erstelle|richte|lege|importiere|ingestiere|aktualisiere|schreibe)\s+jetzt\b"),
    _rx(
        r"\bich\s+werde\s+(jetzt\s+)?(?:.{0,50}\s+)?"
        r"(erstellen|einrichten|anlegen|importieren|ingestieren|aktualisieren)\b"
    ),
    _rx(r"\bals\s+n[äa]chstes\s+(erstelle|richte|lege|importiere|ingestiere|aktualisiere)\b"),
    _rx(r"\bi\s+will\s+(now\s+)?(create|set up|import|ingest|update|write)\b"),
)

_WRITE_TOOL_PREFIXES = (
    "create_",
    "update_",
    "delete_",
    "setup_",
    "append_",
    "ingest_",
    "run_",
    "execute_",
)


class ToolCompletionValidationMiddleware(BaseMiddleware):
    """Prevent false completion when required tool calls did not happen."""

    name = "tool_completion_validation"
    priority = 505

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        if not ctx.result or not ctx.response:
            return

        executed_tools = self._executed_tools(ctx)
        missing_reasons = self._missing_required_tools(ctx, executed_tools)
        if missing_reasons:
            ctx.response = self._blocked_response(missing_reasons, executed_tools)
            logger.warning(
                "Tool completion validation blocked response: agent=%s session=%s missing=%s executed=%s",
                ctx.agent_name,
                ctx.session_id,
                missing_reasons,
                sorted(executed_tools),
            )
            return

        if self._looks_like_unexecuted_commitment(ctx.response) and self._had_tool_activity(ctx):
            write_tools = {tool for tool in executed_tools if tool.startswith(_WRITE_TOOL_PREFIXES)}
            if not write_tools:
                ctx.response = (
                    "Die Ausführung wurde nicht als abgeschlossen gewertet: Der Agent hat einen "
                    "nächsten Schritt angekündigt, aber keinen passenden Schreib-/Setup-Toolcall "
                    "ausgeführt. Bitte erneut versuchen oder die Aufgabe konkreter formulieren."
                )
                logger.warning(
                    "Future-action response blocked without write tool: agent=%s session=%s executed=%s",
                    ctx.agent_name,
                    ctx.session_id,
                    sorted(executed_tools),
                )

    def _missing_required_tools(
        self,
        ctx: MiddlewareContext,
        executed_tools: set[str],
    ) -> list[str]:
        missing: list[str] = []
        for rule in _REQUIRED_TOOL_RULES:
            if not rule.matches(ctx):
                continue
            missing_tools = sorted(rule.required_tools - executed_tools)
            if missing_tools:
                missing.append(f"{rule.name}: {', '.join(missing_tools)} — {rule.reason}")
        return missing

    def _executed_tools(self, ctx: MiddlewareContext) -> set[str]:
        tools: set[str] = set()
        tool_names_by_call_id: dict[str, str] = {}
        for message in ctx.result.get("messages", []):
            if isinstance(message, AIMessage):
                for tool_call in getattr(message, "tool_calls", []) or []:
                    if not isinstance(tool_call, dict):
                        continue
                    call_id = tool_call.get("id")
                    name = tool_call.get("name")
                    if call_id and name:
                        tool_names_by_call_id[str(call_id)] = str(name)
            if isinstance(message, ToolMessage):
                name = getattr(message, "name", None)
                if name:
                    tools.add(str(name))
                    continue
                call_id = getattr(message, "tool_call_id", None)
                if call_id and str(call_id) in tool_names_by_call_id:
                    tools.add(tool_names_by_call_id[str(call_id)])
        return tools

    def _had_tool_activity(self, ctx: MiddlewareContext) -> bool:
        for message in ctx.result.get("messages", []):
            if isinstance(message, ToolMessage):
                return True
            if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
                return True
        return False

    def _looks_like_unexecuted_commitment(self, response: str) -> bool:
        return any(pattern.search(response) for pattern in _FUTURE_COMMITMENT_PATTERNS)

    def _blocked_response(self, missing_reasons: list[str], executed_tools: set[str]) -> str:
        lines = [
            "Die Aufgabe wurde nicht als abgeschlossen gewertet.",
            "",
            "Fehlende Pflicht-Ausführung:",
            *[f"- {reason}" for reason in missing_reasons],
        ]
        if executed_tools:
            lines.extend(["", "Tatsächlich ausgeführte Tools:", f"- {', '.join(sorted(executed_tools))}"])
        return "\n".join(lines)
