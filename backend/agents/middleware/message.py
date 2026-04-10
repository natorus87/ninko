"""Message building middleware: converts trimmed history to LangChain messages."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class MessageBuilderMiddleware(BaseMiddleware):
    name = "message_builder"
    priority = 200

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        messages: list[BaseMessage] = [SystemMessage(content=ctx.final_system_prompt)]

        for msg in ctx.trimmed_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            elif role not in ("system", "system_compaction", "tool"):
                logger.warning(
                    "Unbekannte Message-Rolle '%s' nach Compaction — übersprungen.",
                    role,
                )

        messages.append(HumanMessage(content=ctx.message))
        ctx.messages = messages
        return MiddlewareResult()
