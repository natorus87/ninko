"""
DeerFlow-inspired middleware features.

1. LoopDetectionMiddleware – Hash-based repetition detection
2. DanglingToolCallMiddleware – Repair interrupted tool calls
3. GuardrailMiddleware – Pre-Tool-Call authorization
4. LLMErrorHandlingMiddleware – Sophisticated error classification
"""

from __future__ import annotations

import hashlib
import logging
from collections import deque
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

logger = logging.getLogger(__name__)


class LoopDetectionMiddleware(BaseMiddleware):
    name = "loop_detection"
    priority = 420

    def __init__(self, max_history: int = 5, similarity_threshold: float = 0.8):
        self._max_history = max_history
        self._threshold = similarity_threshold
        self._response_hashes: dict[str, deque[str]] = {}

    def _hash_content(self, content: str) -> str:
        normalized = " ".join(content.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        if not ctx.response or not ctx.session_id:
            return

        content_hash = self._hash_content(ctx.response)

        if ctx.session_id not in self._response_hashes:
            self._response_hashes[ctx.session_id] = deque(maxlen=self._max_history)

        history = self._response_hashes[ctx.session_id]

        if content_hash in history:
            logger.warning(
                "Loop detected for session %s: repeated response hash %s",
                ctx.session_id,
                content_hash,
            )
            ctx.response = (
                "Ich habe eine sehr ähnliche Antwort bereits gegeben. "
                "Bitte formuliere deine Frage anders oder starte ein neues Thema."
            )

        history.append(content_hash)


class DanglingToolCallMiddleware(BaseMiddleware):
    name = "dangling_tool_call"
    priority = 425

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        if not ctx.result:
            return

        messages = ctx.result.get("messages", [])
        if not messages:
            return

        last_msg = messages[-1]

        if isinstance(last_msg, AIMessage) and hasattr(last_msg, "tool_calls"):
            tool_calls = last_msg.tool_calls or []
            if tool_calls:
                tool_names = [tc.get("name", "unknown") for tc in tool_calls]
                logger.warning(
                    "Dangling tool calls detected in session %s: %s — AI ended with tool_calls but no ToolMessage",
                    ctx.session_id,
                    tool_names,
                )

                ai_msgs = [m for m in messages if isinstance(m, AIMessage)]
                tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]

                if len(ai_msgs) > len(tool_msgs):
                    ctx.response = (
                        f"Tool-Aufrufe ({', '.join(tool_names)}) wurden nicht abgeschlossen. "
                        "Bitte versuche es erneut."
                    )


class GuardrailMiddleware(BaseMiddleware):
    name = "guardrail"
    priority = 390

    BLOCKED_PATTERNS = [
        "rm -rf /",
        "DROP DATABASE",
        "DROP TABLE",
        "DELETE FROM users",
        ":(){ :|:& };:",
        "mkfs.",
        "dd if=/dev/zero",
    ]

    def __init__(self, custom_patterns: list[str] | None = None):
        if custom_patterns:
            self.BLOCKED_PATTERNS = list(self.BLOCKED_PATTERNS) + custom_patterns

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        message_lower = ctx.message.lower()

        for pattern in self.BLOCKED_PATTERNS:
            if pattern.lower() in message_lower:
                logger.warning(
                    "Guardrail blocked pattern '%s' in session %s",
                    pattern,
                    ctx.session_id,
                )
                return MiddlewareResult(
                    short_circuit=True,
                    response=f"⚠️ Die Anfrage enthält ein blockiertes Muster ({pattern}). "
                    "Aus Sicherheitsgründen wurde die Verarbeitung abgebrochen.",
                )

        return MiddlewareResult()


class LLMErrorHandlingMiddleware(BaseMiddleware):
    name = "llm_error_handling"
    priority = 430

    ERROR_CLASSIFICATIONS = {
        "timeout": {
            "patterns": ["timeout", "timed out", "deadline exceeded"],
            "response": "Die Anfrage hat zu lange gedauert. Bitte versuche es mit einer kürzeren Frage erneut.",
            "retry": True,
        },
        "rate_limit": {
            "patterns": ["rate limit", "too many requests", "429"],
            "response": "Das KI-Modell ist ausgelastet. Bitte warte einen Moment und versuche es erneut.",
            "retry": True,
        },
        "model_unavailable": {
            "patterns": ["model unloaded", "model not found", "connection refused"],
            "response": "Das KI-Modell ist gerade nicht verfügbar. Bitte prüfe die LLM-Konfiguration.",
            "retry": False,
        },
        "context_overflow": {
            "patterns": ["context length", "token limit", "maximum context"],
            "response": "Die Anfrage ist zu lang. Bitte teile sie in kleinere Fragen auf.",
            "retry": False,
        },
        "authentication": {
            "patterns": ["unauthorized", "api key", "authentication"],
            "response": "Authentifizierungsfehler beim KI-Modell. Bitte prüfe die API-Konfiguration.",
            "retry": False,
        },
    }

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    def classify_error(self, error: str) -> dict[str, Any]:
        error_lower = error.lower()
        for classification, config in self.ERROR_CLASSIFICATIONS.items():
            for pattern in config["patterns"]:
                if pattern in error_lower:
                    return {
                        "type": classification,
                        "response": config["response"],
                        "retry": config["retry"],
                    }
        return {
            "type": "unknown",
            "response": "Ein unbekannter Fehler ist aufgetreten. Bitte versuche es erneut.",
            "retry": True,
        }
