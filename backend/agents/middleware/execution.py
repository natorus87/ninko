"""Execution middleware: safeguard and agent invocation."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, ToolMessage

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_DEFAULT_AGENT_TIMEOUT_SECS = 1800


def _get_timeout() -> int:
    """Lädt den Agent-Timeout aus der Config mit robustem Fallback."""
    try:
        from core.config import get_settings

        timeout = int(get_settings().AGENT_TIMEOUT_SECONDS)
        return timeout if timeout > 0 else _DEFAULT_AGENT_TIMEOUT_SECS
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_AGENT_TIMEOUT_SECS


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
        run_config: dict = {"recursion_limit": 10000}

        if ctx.session_id and self._callbacks_factory:
            run_config["callbacks"] = [
                self._callbacks_factory(ctx.session_id, ctx.agent_name)
            ]

        jit_agent = ctx.jit_agent or ctx.agent

        try:
            if ctx.use_safeguard and self._get_lock and self._run_sg:
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
                    ctx.response = raw_result
                    ctx.early_return = True
                    return
                ctx.result = raw_result
            else:
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
        except asyncio.TimeoutError:
            logger.warning("Agent '%s' Timeout nach %ds.", ctx.agent_name, timeout)
            ctx.response = (
                "Die Anfrage hat zu lange gedauert und wurde abgebrochen. "
                "Bitte versuche es mit einer spezifischeren Frage erneut."
            )
            ctx.early_return = True
        except Exception as exc:
            exc_str = str(exc)
            if (
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
                    exc_str[:300],
                )
                ctx.response = (
                    "Fehler: Bei der Verarbeitung ist ein interner Fehler aufgetreten. "
                    "Bitte versuche es erneut oder präzisiere die Anfrage."
                )
            logger.error("Agent '%s' Fehler: %s", ctx.agent_name, exc, exc_info=True)
            ctx.early_return = True
