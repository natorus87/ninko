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

_AGENT_TIMEOUT_SECS = 600


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
        self._paused = paused_agents or {}
        self._paused_ts = paused_agents_ts or {}
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
        timeout = _AGENT_TIMEOUT_SECS
        run_config: dict = {"recursion_limit": 10000}

        if ctx.session_id and self._callbacks_factory:
            run_config["callbacks"] = [
                self._callbacks_factory(ctx.session_id, ctx.agent_name)
            ]

        jit_agent = ctx.jit_agent or ctx.agent

        try:
            if ctx.use_safeguard and self._get_lock and self._run_sg:
                async with self._get_lock(ctx.session_id):
                    raw_result = await self._run_sg(
                        ctx.messages, ctx.active_tools, run_config, ctx.session_id
                    )
                if isinstance(raw_result, str):
                    ctx.response = raw_result
                    ctx.early_return = True
                    return
                ctx.result = raw_result
            else:
                ctx.result = await asyncio.wait_for(
                    jit_agent.ainvoke({"messages": ctx.messages}, config=run_config),
                    timeout=timeout,
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
            if "Model unloaded" in exc_str:
                ctx.response = (
                    "Fehler: Das KI-Modell ist gerade nicht verfügbar (nicht geladen). "
                    "Bitte prüfe LM Studio und lade das Modell neu."
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
