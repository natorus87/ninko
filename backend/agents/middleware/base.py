"""
Base middleware abstraction for agent invocations.

Middleware follows a pipeline pattern:
    pre_process(context) → executes BEFORE the LLM call
    post_process(context, result) → executes AFTER the LLM call

Each middleware can:
    - Modify the context (messages, system prompt, tools)
    - Short-circuit the pipeline (return early response)
    - Perform side effects (logging, metrics, memory storage)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


@dataclass
class MiddlewareContext:
    """
    Shared context passed through the middleware pipeline.

    Mutated by middleware in pre_process() and consumed in post_process().
    """

    # --- Input ---
    message: str = ""
    chat_history: list[dict] = field(default_factory=list)
    session_id: str = ""
    confirmed: bool = False
    agent_name: str = ""

    # --- System Prompt (built incrementally) ---
    system_prompt: str = ""
    final_system_prompt: str = ""

    # --- Messages (built by MessageBuilderMiddleware) ---
    messages: list["BaseMessage"] = field(default_factory=list)
    trimmed_history: list[dict] = field(default_factory=list)

    # --- Tools ---
    active_tools: list[Any] = field(default_factory=list)

    # --- LLM ---
    llm: Any = None
    agent: Any = None

    # --- Execution ---
    run_config: dict = field(default_factory=dict)
    use_safeguard: bool = False
    jit_agent: Any = None

    # --- Output (populated in post_process) ---
    response: str = ""
    did_compact: bool = False
    result: dict = field(default_factory=dict)
    raw_result: Any = None

    # --- Short-circuit flag ---
    early_return: bool = False
    early_return_response: str = ""

    extra: dict[str, Any] = field(default_factory=dict)

    stream_generator: Any = None

    wants_stream: bool = False

    cancellation_check: Any = None

    token_callback: Any = None


@dataclass
class MiddlewareResult:
    """Result returned by middleware hooks."""

    # Whether to short-circuit the pipeline
    short_circuit: bool = False
    # Response to return if short_circuit=True
    response: str = ""


class BaseMiddleware(ABC):
    """
    Abstract base class for agent middleware.

    Subclasses must implement at least one of:
        - pre_process()  — runs BEFORE the LLM call
        - post_process() — runs AFTER the LLM call

    Class attributes:
        name:     Human-readable name for logging
        priority: Execution order (lower = earlier). Range: 0-1000.
                  0-99:   System-level (LLM init, context)
                  100-199: Prompt enrichment (soul, skills, RAG)
                  200-299: Message building
                  300-399: Tool selection
                  400-499: Execution (safeguard, agent run)
                  500-599: Post-processing (response extraction, memory)
                  900-999: Cleanup, metrics, logging
    """

    name: str = "base"
    priority: int = 500

    @abstractmethod
    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """
        Pre-processing hook. Runs BEFORE the LLM call.

        Returns:
            MiddlewareResult with short_circuit=True to abort pipeline early.
        """
        ...

    async def post_process(self, ctx: MiddlewareContext) -> None:
        """
        Post-processing hook. Runs AFTER the LLM call.

        Default implementation does nothing.
        """
        pass

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name={self.name!r} priority={self.priority}>"
        )
