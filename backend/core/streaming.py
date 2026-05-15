"""
Streaming infrastructure for Ninko chat responses.

Provides real token-by-token streaming during LLM generation via LangGraph's
astream_events API. Used only for the final user-visible response path —
internal routing/safeguard LLMs are never streamed.

Usage:
    from core.streaming import SSEStreamGenerator

    async for token in SSEStreamGenerator(agent, messages, config).stream():
        yield token
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, AsyncGenerator, Any, Callable

if TYPE_CHECKING:
    from fastapi import Request
else:
    Request = None

logger = logging.getLogger("ninko.streaming")


class SSEStreamGenerator:
    """
    Wraps a LangGraph ReAct agent and streams tokens via astream_events.

    Only yields tokens from the final AI message (on_chat_model_stream events).
    Tool calls, intermediate steps, and internal LLM calls are filtered out.

    Usage:
        gen = SSEStreamGenerator(agent, {"messages": messages}, config)
        async for token in gen.stream():
            yield f"data: {json.dumps({'type':'token','text':token})}\n\n"
    """

    def __init__(
        self,
        agent,  # LangGraph compiled agent from create_react_agent()
        input_data: dict,
        config: dict | None = None,
        cancellation_check: Callable[[], Any] | None = None,
    ):
        """
        Args:
            agent: LangGraph compiled agent from create_react_agent()
            input_data: Input dict with "messages" key
            config: LangGraph config dict (run_id, callbacks, etc.)
            cancellation_check: async callable returning True if client disconnected
        """
        self._agent = agent
        self._input = input_data
        self._config = config or {}
        self._cancellation_check = cancellation_check

    @staticmethod
    def _is_tool_chunk(chunk: Any) -> bool:
        """True wenn der Chunk ein Tool-Call ist (kein Text-Token)."""
        if chunk is None:
            return False
        if getattr(chunk, "tool_call_chunks", None):
            return True
        additional_kwargs = getattr(chunk, "additional_kwargs", {}) or {}
        return isinstance(additional_kwargs, dict) and bool(additional_kwargs.get("tool_calls"))

    async def stream(self) -> AsyncGenerator[str, None]:
        """
        Streams tokens from the agent's astream_events.

        Yields individual tokens as strings. The caller is responsible for
        framing them as SSE frames.

        Cancellation is checked before each yield via the optional callback.
        On cancellation, the generator raises asyncio.CancelledError.
        """
        try:
            async for event in self._agent.astream_events(
                self._input,
                config=self._config,
                version="v2",
            ):
                # ── Cancellation Check ──────────────────────────────────────────
                if self._cancellation_check is not None:
                    if await self._cancellation_check():
                        raise asyncio.CancelledError("Client disconnected")

                # ── Token Events (only from chat model) ─────────────────────────
                # on_chat_model_stream: raw token from the LLM
                # on_llm_stream: alternative name in some LangChain versions
                event_type = event.get("event", "")
                if event_type not in ("on_chat_model_stream", "on_llm_stream"):
                    continue

                # Extract token from chunk
                chunk = event.get("data", {}).get("chunk", {})
                if self._is_tool_chunk(chunk):
                    continue

                # Handle different chunk formats (BaseMessage, AIMessageChunk, etc.)
                content = getattr(chunk, "content", None)
                if content is None:
                    # Fallback: try dict-style access
                    if isinstance(chunk, dict):
                        content = chunk.get("content", "")
                    else:
                        continue

                if isinstance(content, str) and content:
                    yield content
                elif isinstance(content, list):
                    # Structured content (e.g. Anthropic multi-block)
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text = block.get("text", "")
                            if text:
                                yield text

        except asyncio.CancelledError:
            logger.debug("SSEStreamGenerator: cancelled by client")
            raise
        except Exception as exc:
            logger.warning("SSEStreamGenerator error: %s", exc, exc_info=True)
            raise


class CancellationChecker:
    """
    Wraps a FastAPI Request to check if the client disconnected.

    Usage:
        checker = CancellationChecker(request)
        is_cancelled = await checker()  # returns True if disconnected
    """

    def __init__(self, request) -> None:
        self._request = request

    async def __call__(self) -> bool:
        return await self._request.is_disconnected()
