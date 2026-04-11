"""
Tool Error Handling Middleware – GraphBubbleUp Preservation.

Konvertiert Tool-Exceptions zu strukturierten Error-ToolMessages,
damit der LangGraph sie graceful behandelt statt abzustürzen.

Pattern (DeerFlow-inspired):
    error_msg = await tool_error_to_message(tool_name, tool_args, exception)
    return ErrorToolMessage(content=error_msg)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("ninko.tool_error_middleware")


def format_tool_error(tool_name: str, exc: Exception) -> str:
    """Format a tool exception as user-friendly error message.

    Args:
        tool_name: Tool that raised the error.
        exc: The exception.

    Returns:
        Formatted error message for the user.
    """
    error_type = type(exc).__name__
    error_msg = str(exc)

    if not error_msg:
        return f"Error: {tool_name} failed with {error_type}"

    return f"Error in {tool_name}: {error_msg}"


async def safe_tool_invoke(
    tool_fn: Any,
    tool_input: dict[str, Any],
    *,
    tool_name: str = "unknown",
) -> str:
    """Invoke a tool function with error handling.

    Catches exceptions and returns error messages instead of raising.

    Args:
        tool_fn: The tool function to invoke (sync or async).
        tool_input: Arguments to pass to the tool.
        tool_name: Name for error messages.

    Returns:
        Result string or error message string.
    """
    try:
        import asyncio

        if asyncio.iscoroutinefunction(tool_fn):
            return await tool_fn(tool_input)
        return tool_fn(tool_input)
    except Exception as exc:
        logger.warning("Tool '%s' error: %s", tool_name, exc)
        return format_tool_error(tool_name, exc)


class ToolErrorHandler:
    """Handles tool errors and converts them to ToolMessage format.

    Can be used as a mixin or wrapper for agents that need
    tool error handling.
    """

    async def handle_tool_error(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        exception: Exception,
    ) -> dict[str, Any]:
        """Convert a tool exception to error message dict.

        Args:
            tool_name: Name of the tool that failed.
            tool_args: Arguments passed to the tool.
            exception: The exception that was raised.

        Returns:
            Error dict with content and status for ToolMessage.
        """
        error_content = format_tool_error(tool_name, exception)
        logger.debug("Tool error handled: %s - %s", tool_name, error_content)

        return {
            "content": error_content,
            "status": "error",
            "tool_name": tool_name,
        }

    async def invoke_tool_safe(
        self,
        tool_fn: Any,
        tool_args: dict[str, Any],
        *,
        tool_name: str = "unknown",
    ) -> dict[str, Any]:
        """Invoke a tool with error handling, return dict format.

        Args:
            tool_fn: Tool function to invoke.
            tool_args: Arguments for the tool.
            tool_name: Tool name for error messages.

        Returns:
            Dict with content (result or error) and status.
        """
        try:
            import asyncio

            if asyncio.iscoroutinefunction(tool_fn):
                result = await tool_fn(tool_args)
            else:
                result = tool_fn(tool_args)

            return {
                "content": str(result) if result else "",
                "status": "ok",
                "tool_name": tool_name,
            }
        except Exception as exc:
            return await self.handle_tool_error(tool_name, tool_args, exc)
