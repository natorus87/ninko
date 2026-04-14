"""Post-processing middleware: response extraction and memory storage."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, ToolMessage

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MEMORIZE_COOLDOWN_SECS = 120
_MEMORIZE_MIN_LENGTH = 80


class ResponseExtractionMiddleware(BaseMiddleware):
    name = "response_extraction"
    priority = 500

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        if not ctx.result:
            return

        all_msgs = ctx.result.get("messages", [])
        ai_msgs = [m for m in all_msgs if isinstance(m, AIMessage) and m.content]
        tool_msgs = [m for m in all_msgs if isinstance(m, ToolMessage) and m.content]

        # Prefer tool outputs that contain images (data URLs or markers)
        if tool_msgs:
            for msg in reversed(tool_msgs):
                tool_text = _extract_text(msg.content)
                if "data:image/" in tool_text:
                    ctx.response = tool_text
                    logger.debug(
                        "Agent '%s': using tool image output as response.",
                        ctx.agent_name,
                    )
                    return
                if "[NINKO_IMAGE:" in tool_text or "/api/images/" in tool_text:
                    ctx.response = tool_text
                    logger.debug(
                        "Agent '%s': using tool image marker as response.",
                        ctx.agent_name,
                    )
                    return

        if ai_msgs:
            raw = _extract_text(ai_msgs[-1].content)
            response = _strip_thinking(raw)
            if response:
                ctx.response = response
                logger.debug("Agent '%s' Antwort: %s…", ctx.agent_name, response[:100])
                return

        if tool_msgs:
            ctx.response = _extract_text(tool_msgs[-1].content)
            logger.debug(
                "Agent '%s': kein AI-Text, nutze letztes Tool-Ergebnis als Antwort.",
                ctx.agent_name,
            )
        else:
            ctx.response = "Keine Antwort generiert."


class MemoryStorageMiddleware(BaseMiddleware):
    name = "memory_storage"
    priority = 510

    def __init__(
        self,
        auto_memorize_fn: Any = None,
        excluded_agents: set[str] | None = None,
        cooldowns: dict[tuple[str, str], float] | None = None,
        background_tasks: set[asyncio.Task] | None = None,
    ):
        self._auto_memorize = auto_memorize_fn
        self._excluded = excluded_agents if excluded_agents is not None else set()
        self._cooldowns = cooldowns if cooldowns is not None else {}
        self._bg_tasks = (
            background_tasks if background_tasks is not None else set()
        )

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        if (
            not ctx.response
            or len(ctx.response) < _MEMORIZE_MIN_LENGTH
            or ctx.agent_name in self._excluded
            or not self._auto_memorize
        ):
            return

        now = asyncio.get_running_loop().time()
        key = (ctx.agent_name, ctx.session_id or "__no_session__")
        last = self._cooldowns.get(key, 0.0)

        if (now - last) < _MEMORIZE_COOLDOWN_SECS:
            return

        if len(self._cooldowns) > 5000:
            oldest = sorted(self._cooldowns, key=lambda k: self._cooldowns[k])
            for k in oldest[:500]:
                self._cooldowns.pop(k, None)

        self._cooldowns[key] = now
        task = asyncio.create_task(self._auto_memorize(ctx.message, ctx.response))
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def _strip_thinking(text: str) -> str:
    import re

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return cleaned
