"""Execution middleware: safeguard and agent invocation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from core import status_bus
from core.redaction import redact_text
from core.streaming import SSEStreamGenerator

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_AGENT_TIMEOUT_SECS = 1800
_DEFAULT_AGENT_RECURSION_LIMIT = 80


def _redact_exception_text(value: object, *, limit: int = 300) -> str:
    return redact_text(str(value), limit=limit)


def _get_timeout() -> int:
    """Lädt den Agent-Timeout aus der Config mit robustem Fallback."""
    try:
        from core.config import get_settings

        timeout = int(get_settings().AGENT_TIMEOUT_SECONDS)
        return timeout if timeout > 0 else _DEFAULT_AGENT_TIMEOUT_SECS
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_AGENT_TIMEOUT_SECS


def _get_recursion_limit() -> int:
    """Loads the LangGraph recursion limit with a bounded fallback."""
    try:
        from core.config import get_settings

        limit = int(get_settings().AGENT_RECURSION_LIMIT)
        return limit if limit > 0 else _DEFAULT_AGENT_RECURSION_LIMIT
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_AGENT_RECURSION_LIMIT


async def _stream_and_accumulate(
    agent,
    input_data: dict,
    config: dict,
    cancellation_check: Any,
    token_callback: Any = None,
) -> tuple[list[str], dict]:
    """Runs astream_events, accumulates tokens and returns (tokens, final_result)."""
    tokens: list[str] = []
    result = {}
    try:
        streamer = SSEStreamGenerator(
            agent,
            input_data,
            config=config,
            cancellation_check=cancellation_check,
        )
        async for token in streamer.stream():
            tokens.append(token)
            if token_callback:
                await token_callback(token)

    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "stream_and_accumulate error: %s",
            type(exc).__name__,
            exc_info=False,
        )
        raise

    return tokens, result


class AgentExecutionMiddleware(BaseMiddleware):
    name = "agent_execution"
    priority = 410

    def __init__(
        self,
        safeguard: Any = None,
        get_safeguard_session_lock: Any = None,
        run_with_safeguard: Any = None,
        paused_agents: dict[str, Any] | None = None,
        paused_agents_ts: dict[str, float] | None = None,
        paused_ttl_secs: float = 300.0,
        callbacks_factory: Any = None,
    ):
        self._safeguard = safeguard
        self._get_lock = get_safeguard_session_lock
        self._run_sg = run_with_safeguard
        self._paused = paused_agents if paused_agents is not None else {}
        self._paused_ts = paused_agents_ts if paused_agents_ts is not None else {}
        self._paused_ttl = paused_ttl_secs
        self._callbacks_factory = callbacks_factory

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        import time as _time

        use_sg = (
            self._safeguard is not None
            and self._safeguard.enabled
            and not ctx.confirmed
            and bool(ctx.session_id)
            and bool(ctx.active_tools)
        )
        ctx.use_safeguard = use_sg

        if not use_sg:
            await status_bus.emit_trace(
                ctx.session_id,
                phase="safeguard",
                label="Tool-SafeGuard übersprungen",
                detail="Kein Tool-SafeGuard-Lauf nötig für diesen Agentenaufruf.",
                data={
                    "agent": ctx.agent_name,
                    "tool_count": len(ctx.active_tools),
                    "confirmed": ctx.confirmed,
                },
            )
            return MiddlewareResult()

        now_mono = _time.monotonic()
        expired = [
            sid
            for sid, ts in self._paused_ts.items()
            if now_mono - ts > self._paused_ttl
        ]
        for sid in expired:
            self._paused.pop(sid, None)
            self._paused_ts.pop(sid, None)

        if ctx.session_id in self._paused:
            ctx.early_return = True
            ctx.early_return_response = (
                "Für diese Session gibt es bereits eine ausstehende Tool-Bestätigung. "
                "Bestätige zuerst den offenen Schritt (confirmed=true)."
            )
            return MiddlewareResult(
                short_circuit=True, response=ctx.early_return_response
            )

        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        timeout = _get_timeout()
        recursion_limit = _get_recursion_limit()
        run_config: dict = {"recursion_limit": recursion_limit}

        if ctx.session_id and self._callbacks_factory:
            run_config["callbacks"] = [
                self._callbacks_factory(ctx.session_id, ctx.agent_name)
            ]

        jit_agent = ctx.jit_agent or ctx.agent

        try:
            if ctx.use_safeguard and self._get_lock and self._run_sg:
                await status_bus.emit_trace(
                    ctx.session_id,
                    phase="safeguard",
                    label="Tool-SafeGuard prüft Agentenlauf",
                    detail=f"Agent: {ctx.agent_name}",
                    data={"agent": ctx.agent_name, "tool_count": len(ctx.active_tools)},
                    status="running",
                )
                logger.debug(
                    "AgentExecutionMiddleware: safeguard run start agent=%s session=%s tools=%d",
                    ctx.agent_name,
                    ctx.session_id,
                    len(ctx.active_tools),
                )
                async with self._get_lock(ctx.session_id):
                    raw_result = await self._run_sg(
                        ctx.messages, ctx.active_tools, run_config, ctx.session_id
                    )
                logger.debug(
                    "AgentExecutionMiddleware: safeguard run end agent=%s session=%s result_type=%s",
                    ctx.agent_name,
                    ctx.session_id,
                    type(raw_result).__name__,
                )
                if isinstance(raw_result, str):
                    await status_bus.emit_trace(
                        ctx.session_id,
                        phase="safeguard",
                        label="Tool-SafeGuard wartet auf Bestätigung",
                        detail=f"Agent: {ctx.agent_name}",
                        data={"agent": ctx.agent_name},
                    )
                    ctx.response = raw_result
                    ctx.early_return = True
                    return
                ctx.result = raw_result
                await status_bus.emit_trace(
                    ctx.session_id,
                    phase="safeguard",
                    label="Tool-SafeGuard freigegeben",
                    detail=f"Agent: {ctx.agent_name}",
                    data={"agent": ctx.agent_name},
                )
            else:
                if ctx.wants_stream and not ctx.active_tools:
                    await status_bus.emit_trace(
                        ctx.session_id,
                        phase="agent",
                        label="Antwort-Streaming gestartet",
                        detail=f"Agent: {ctx.agent_name}",
                        data={"agent": ctx.agent_name},
                        status="running",
                    )
                    logger.debug(
                        "AgentExecutionMiddleware: streaming mode agent=%s session=%s",
                        ctx.agent_name,
                        ctx.session_id,
                    )
                    tokens, _ = await _stream_and_accumulate(
                        jit_agent,
                        {"messages": ctx.messages},
                        run_config,
                        ctx.cancellation_check,
                        ctx.token_callback,
                    )
                    ctx.response = "".join(tokens)
                    ctx.stream_generator = None
                    await status_bus.emit_trace(
                        ctx.session_id,
                        phase="agent",
                        label="Antwort-Streaming abgeschlossen",
                        detail=f"Agent: {ctx.agent_name}",
                        data={"agent": ctx.agent_name, "token_chunks": len(tokens)},
                    )
                else:
                    await status_bus.emit_trace(
                        ctx.session_id,
                        phase="agent",
                        label="Agentenlauf gestartet",
                        detail=f"Agent: {ctx.agent_name}",
                        data={
                            "agent": ctx.agent_name,
                            "tool_count": len(ctx.active_tools),
                            "safeguard": ctx.use_safeguard,
                        },
                        status="running",
                    )
                    logger.debug(
                        "AgentExecutionMiddleware: ainvoke start agent=%s session=%s tools=%d safeguard=%s",
                        ctx.agent_name,
                        ctx.session_id,
                        len(ctx.active_tools),
                        ctx.use_safeguard,
                    )
                    ctx.result = await asyncio.wait_for(
                        jit_agent.ainvoke({"messages": ctx.messages}, config=run_config),
                        timeout=timeout,
                    )
                    logger.debug(
                        "AgentExecutionMiddleware: ainvoke end agent=%s session=%s result_type=%s",
                        ctx.agent_name,
                        ctx.session_id,
                        type(ctx.result).__name__,
                    )
                    await status_bus.emit_trace(
                        ctx.session_id,
                        phase="agent",
                        label="Agentenlauf abgeschlossen",
                        detail=f"Agent: {ctx.agent_name}",
                        data={"agent": ctx.agent_name, "result_type": type(ctx.result).__name__},
                    )
        except asyncio.TimeoutError:
            logger.warning("Agent '%s' Timeout nach %ds.", ctx.agent_name, timeout)
            await status_bus.emit_trace(
                ctx.session_id,
                phase="agent",
                label="Agentenlauf abgebrochen",
                detail=f"Timeout nach {timeout}s",
                data={"agent": ctx.agent_name, "timeout_seconds": timeout},
                status="error",
            )
            ctx.response = (
                "Die Anfrage hat zu lange gedauert und wurde abgebrochen. "
                "Bitte versuche es mit einer spezifischeren Frage erneut."
            )
            ctx.early_return = True
        except Exception as exc:
            exc_str = str(exc)
            if "Recursion limit" in exc_str or "recursion_limit" in exc_str:
                logger.warning(
                    "Agent '%s' wegen Recursion-Limit (%d) abgebrochen.",
                    ctx.agent_name,
                    recursion_limit,
                )
                ctx.response = (
                    "Der Agent hat wiederholt dieselben Schritte ausgeführt und wurde "
                    "abgebrochen. Bitte versuche es mit einer spezifischeren Frage erneut."
                )
            elif (
                "Model unloaded" in exc_str
                or "No models loaded" in exc_str
                or "no models loaded" in exc_str.lower()
            ):
                ctx.response = (
                    "Fehler: Das KI-Modell ist gerade nicht verfügbar (nicht geladen). "
                    "Bitte prüfe den aktiven LLM-Provider und lade dort ein Modell "
                    "oder wechsle auf einen funktionierenden Provider."
                )
            else:
                logger.warning(
                    "Agent '%s' Fehler wird gegenüber User sanitisiert. raw_error=%s",
                    ctx.agent_name,
                    _redact_exception_text(exc),
                )
                ctx.response = (
                    "Fehler: Bei der Verarbeitung ist ein interner Fehler aufgetreten. "
                    "Bitte versuche es erneut oder präzisiere die Anfrage."
                )
            logger.error(
                "Agent '%s' Fehler: %s",
                ctx.agent_name,
                type(exc).__name__,
                exc_info=False,
            )
            await status_bus.emit_trace(
                ctx.session_id,
                phase="agent",
                label="Agentenlauf fehlgeschlagen",
                detail=type(exc).__name__,
                data={"agent": ctx.agent_name},
                status="error",
            )
            ctx.early_return = True
