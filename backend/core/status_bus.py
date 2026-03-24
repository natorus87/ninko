"""
Ninko Status Bus – Per-Session asyncio Queue für Live-Status-Updates.
Wird vom Orchestrator/Agent beschrieben, vom SSE-Endpoint gelesen.
"""

from __future__ import annotations

import asyncio
import logging
from contextvars import ContextVar

logger = logging.getLogger("ninko.core.status_bus")

# session_id → asyncio.Queue
_queues: dict[str, asyncio.Queue] = {}

# Async-sicherer Context-Variable: aktuelle session_id im laufenden Task
_session_id_var: ContextVar[str] = ContextVar("ninko_session_id", default="")


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
