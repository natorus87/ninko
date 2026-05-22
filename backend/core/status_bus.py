"""
Ninko Status Bus – Per-Session asyncio Queue für Live-Status-Updates.
Wird vom Orchestrator/Agent beschrieben, vom SSE-Endpoint gelesen.
"""

from __future__ import annotations

import asyncio
import logging
import json
import re
from typing import Any
from contextvars import ContextVar

logger = logging.getLogger("ninko.core.status_bus")

# session_id → asyncio.Queue
_queues: dict[str, asyncio.Queue] = {}

# Async-sicherer Context-Variable: aktuelle session_id im laufenden Task
_session_id_var: ContextVar[str] = ContextVar("ninko_session_id", default="")

_SENSITIVE_KEYS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "bearer",
    "auth",
    "private",
    "credential",
)


def _redact_text(value: str, limit: int = 1200) -> str:
    """Redacts obvious secret assignments before sending status data to clients."""
    text = value[:limit]
    for key in _SENSITIVE_KEYS:
        text = re.sub(
            rf'("{key}"\s*:\s*)"[^"]+"',
            r'\1"***"',
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            rf"({key}\s*[=:]\s*)[^\s,;]{{1,200}}",
            r"\1***",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _sanitize_value(value: Any, *, depth: int = 0) -> Any:
    """Keeps trace payloads small and safe enough for the live UI."""
    if depth > 5:
        return "..."
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item, depth=depth + 1) for item in list(value)[:25]]
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            safe_key = str(key)[:120]
            if any(s in safe_key.lower() for s in _SENSITIVE_KEYS):
                cleaned[safe_key] = "***"
            else:
                cleaned[safe_key] = _sanitize_value(item, depth=depth + 1)
        return cleaned
    try:
        return _redact_text(json.dumps(value, ensure_ascii=False, default=str))
    except TypeError:
        return _redact_text(str(value))


def set_session_id(session_id: str) -> None:
    """Setzt die aktuelle Session-ID im asyncio-Kontext (für Unter-Tasks propagiert)."""
    _session_id_var.set(session_id)


def get_session_id() -> str:
    """Gibt die aktuelle Session-ID zurück (aus dem asyncio-Kontext)."""
    return _session_id_var.get()


def get_queue(session_id: str) -> asyncio.Queue:
    """Gibt die Queue für eine Session zurück; erstellt sie wenn nötig."""
    if session_id not in _queues:
        _queues[session_id] = asyncio.Queue(maxsize=200)
    return _queues[session_id]


async def emit(session_id: str, text: str) -> None:
    """Sendet eine Status-Nachricht an die Queue der Session."""
    if not session_id:
        return
    q = get_queue(session_id)
    try:
        q.put_nowait({"type": "status", "text": text})
    except asyncio.QueueFull:
        pass


async def emit_event(session_id: str, event: dict) -> None:
    """Sendet ein strukturiertes Event an die Queue der Session (beliebiger type)."""
    if not session_id:
        return
    q = get_queue(session_id)
    try:
        q.put_nowait(event)
    except asyncio.QueueFull:
        pass


async def emit_trace(
    session_id: str,
    *,
    phase: str,
    label: str,
    detail: str = "",
    data: dict | None = None,
    status: str = "done",
) -> None:
    """Sends one observable execution-trace event to the live status stream.

    Trace events are not chain-of-thought. They describe concrete system
    boundaries and decisions that Ninko can observe: routing mode, selected
    agent/module, context handling, LLM call boundaries, and sanitized inputs.
    """
    if not session_id:
        return
    await emit_event(
        session_id,
        {
            "type": "trace_event",
            "phase": phase,
            "label": label,
            "detail": _redact_text(detail, 600) if detail else "",
            "data": _sanitize_value(data or {}),
            "status": status,
        },
    )


async def done(session_id: str) -> None:
    """Signalisiert dem SSE-Consumer, dass die Verarbeitung abgeschlossen ist."""
    if not session_id:
        return
    q = _queues.get(session_id)
    if q:
        try:
            q.put_nowait({"type": "done"})
        except asyncio.QueueFull:
            pass


def cleanup(session_id: str) -> None:
    """Entfernt die Queue nach Abschluss."""
    _queues.pop(session_id, None)
