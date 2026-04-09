"""
Ninko Event System – Observable Tool-Usage Events.

Erlaubt Listener-Registration für Tool-Events (Audit Trail, Cost Tracking, etc.).
Thread-safe, async-first Design.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger("ninko.events")


@dataclass
class ToolEvent:
    """
    Ein Tool-Aufruf-Event für Audit und Observability.

    Attributes:
        agent_name: Name des aufrufenden Agenten
        tool_name: Name des aufgerufenen Tools
        args: Argumente des Tool-Calls (serialisierbar)
        session_id: Session-ID für Korrelation
        timestamp: ISO-8601 Zeitstempel (UTC)
        duration_ms: Ausführungszeit in Millisekunden
        result_size: Größe des Results in Zeichen (für Cost-Tracking)
        error: Fehlermeldung falls vorhanden
        is_readonly: Ob das Tool als read-only klassifiziert ist
    """

    agent_name: str
    tool_name: str
    args: dict[str, Any]
    session_id: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_ms: float = 0.0
    result_size: int = 0
    error: str | None = None
    is_readonly: bool = False


# Type alias für Event-Listener
ToolEventListener = Callable[[ToolEvent], Awaitable[None]]

# Thread-safe Listener-Liste
_listeners: list[ToolEventListener] = []
_listener_lock = asyncio.Lock()


async def emit_tool_event(event: ToolEvent) -> None:
    """
    Emittiert ein ToolEvent an alle registrierten Listener.

    Exceptions in Listenern werden gefangen und geloggt –
    ein fehlerhafter Listener blockiert nicht andere.
    """
    async with _listener_lock:
        listeners = _listeners.copy()

    for fn in listeners:
        try:
            await fn(event)
        except Exception as exc:
            logger.warning(
                "ToolEvent Listener fehlgeschlagen: %s: %s", fn.__name__, exc
            )


def on_tool_event(fn: ToolEventListener) -> ToolEventListener:
    """
    Dekorator: Registriert eine Async-Funktion als ToolEvent-Listener.

    Example:
        @on_tool_event
        async def my_audit_handler(event: ToolEvent) -> None:
            await persist_to_db(event)
    """
    _listeners.append(fn)
    logger.debug("ToolEvent Listener registriert: %s", fn.__name__)
    return fn


def remove_tool_event_listener(fn: ToolEventListener) -> bool:
    """
    Entfernt einen registrierten Listener.

    Returns:
        True wenn der Listener gefunden und entfernt wurde.
    """
    if fn in _listeners:
        _listeners.remove(fn)
        logger.debug("ToolEvent Listener entfernt: %s", fn.__name__)
        return True
    return False


def get_listener_count() -> int:
    """Gibt die Anzahl registrierter Listener zurück."""
    return len(_listeners)


def clear_all_listeners() -> None:
    """Entfernt ALLE Listener (nützlich für Tests)."""
    _listeners.clear()
    logger.debug("Alle ToolEvent Listener entfernt")
