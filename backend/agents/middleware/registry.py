"""
Middleware registry with strict ordering enforcement.

The registry ensures:
    1. Middleware executes in priority order (ascending)
    2. No duplicate names
    3. Pipeline short-circuits correctly
"""

from __future__ import annotations

import logging
from typing import Sequence

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

logger = logging.getLogger(__name__)


class MiddlewareRegistry:
    """
    Manages middleware pipeline with priority-based ordering.

    Usage:
        registry = MiddlewareRegistry()
        registry.add(LLMProviderMiddleware())
        registry.add(ContextMiddleware())
        registry.add(SoulInjectionMiddleware())

        # Execute pipeline
        ctx = MiddlewareContext(message="Hello", ...)
        result = await registry.run_pre(ctx)
        # ... LLM call ...
        await registry.run_post(ctx)
    """

    def __init__(self) -> None:
        self._middleware: list[BaseMiddleware] = []
        self._sorted = True

    def add(self, middleware: BaseMiddleware) -> "MiddlewareRegistry":
        """Add middleware to the pipeline. Returns self for chaining."""
        # Check for duplicate names
        existing_names = {m.name for m in self._middleware}
        if middleware.name in existing_names:
            raise ValueError(
                f"Middleware with name {middleware.name!r} already registered"
            )

        self._middleware.append(middleware)
        self._sorted = False
        logger.debug("Registered middleware: %s", middleware)
        return self

    def remove(self, name: str) -> None:
        """Remove middleware by name."""
        self._middleware = [m for m in self._middleware if m.name != name]

    def get(self, name: str) -> BaseMiddleware | None:
        """Get middleware by name."""
        for m in self._middleware:
            if m.name == name:
                return m
        return None

    @property
    def middleware(self) -> Sequence[BaseMiddleware]:
        """Get middleware in execution order."""
        if not self._sorted:
            self._middleware.sort(key=lambda m: m.priority)
            self._sorted = True
        return self._middleware

    async def run_pre(self, ctx: MiddlewareContext) -> MiddlewareResult | None:
        """
        Execute all pre_process hooks in priority order.

        Returns:
            MiddlewareResult if pipeline was short-circuited, None otherwise.
        """
        for mw in self.middleware:
            if ctx.early_return:
                logger.debug(
                    "Pipeline short-circuited before %s (priority=%d)",
                    mw.name,
                    mw.priority,
                )
                break

            logger.debug("Running pre_process: %s (priority=%d)", mw.name, mw.priority)
            result = await mw.pre_process(ctx)

            if result and result.short_circuit:
                ctx.early_return = True
                ctx.early_return_response = result.response
                logger.info(
                    "Pipeline short-circuited by %s: %s…",
                    mw.name,
                    result.response[:80],
                )
                return result

        return None

    async def run_post(self, ctx: MiddlewareContext) -> None:
        """Execute all post_process hooks in priority order."""
        for mw in self.middleware:
            logger.debug("Running post_process: %s (priority=%d)", mw.name, mw.priority)
            await mw.post_process(ctx)

    def __len__(self) -> int:
        return len(self._middleware)

    def __repr__(self) -> str:
        names = [m.name for m in self.middleware]
        return f"MiddlewareRegistry({names})"
