"""System-level middleware: LLM initialization and context management."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class LLMProviderMiddleware(BaseMiddleware):
    name = "llm_provider"
    priority = 10

    def __init__(self, get_llm: Any, get_llm_generation: Any, create_react_agent: Any):
        self._get_llm = get_llm
        self._get_llm_generation = get_llm_generation
        self._create_react_agent = create_react_agent
        self._agent_cache: dict[str, Any] = {}

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        current_gen = self._get_llm_generation()
        cached_gen = ctx.extra.get("_llm_generation")

        if cached_gen != current_gen:
            old_agent = ctx.agent
            if old_agent and hasattr(old_agent, "aclose"):
                try:
                    await old_agent.aclose()
                except Exception as exc:
                    logger.debug(
                        "LLM-Agent cleanup fehlgeschlagen (ignoriert): %s", exc
                    )

            from core.tool_error_handling import wrap_tools_with_sanitizer

            ctx.llm = self._get_llm()
            # Sanitizer-Patching nach LLM-Rebuild auffrischen (idempotent durch Guard)
            wrap_tools_with_sanitizer(ctx.active_tools or [])
            ctx.agent = self._create_react_agent(
                model=ctx.llm, tools=ctx.active_tools or []
            )
            ctx.extra["_llm_generation"] = current_gen
            logger.info(
                "Agent '%s': LLM nach Provider-Wechsel neu initialisiert.",
                ctx.agent_name,
            )

        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        pass
