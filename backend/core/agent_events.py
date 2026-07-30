"""Async event bus for typed agent execution events."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from threading import RLock

from schemas.execution import AgentEvent

logger = logging.getLogger("ninko.agent_events")

AgentEventListener = Callable[[AgentEvent], Awaitable[None]]
AgentEventSink = Callable[[AgentEvent], Awaitable[object]]
_PERSISTENCE_TIMEOUT_SECONDS = 0.25
_PERSISTENCE_BACKOFF_SECONDS = 5.0
_agent_run_id_var: ContextVar[str] = ContextVar("ninko_agent_run_id", default="")


def tenant_id_from_session(session_id: str) -> str:
    """Derive the lowercase tenant from ``<tenant>:<session>``.

    Session IDs without a non-empty tenant prefix belong to ``"default"``.
    """
    normalized = (session_id or "").strip()
    if ":" not in normalized:
        return "default"
    return normalized.split(":", 1)[0].strip().lower() or "default"


def set_agent_run_id(run_id: str) -> Token[str]:
    """Set the logical parent run for callbacks spawned in this async context.

    The returned token must be passed to :func:`reset_agent_run_id` in a
    ``finally`` block so a reused task cannot retain the completed run.
    """
    return _agent_run_id_var.set(run_id)


def reset_agent_run_id(token: Token[str]) -> None:
    """Restore the previous logical agent run context."""
    _agent_run_id_var.reset(token)


def get_agent_run_id() -> str:
    """Return the logical agent run ID visible to nested tool callbacks."""
    return _agent_run_id_var.get()


@dataclass(frozen=True)
class _Subscription:
    listener: AgentEventListener
    tenant_id: str | None
    session_id: str | None

    def accepts(self, event: AgentEvent) -> bool:
        if self.tenant_id is not None and event.tenant_id != self.tenant_id:
            return False
        return self.session_id is None or event.session_id == self.session_id


class AgentEventBus:
    """Process-local, non-durable fan-out bus for scoped async listeners.

    Matching listeners run concurrently on independent event copies. Delivery
    waits for every listener to finish or time out; listener failures are
    logged without their exception messages and never propagate to emitters.
    """

    def __init__(self, *, listener_timeout_seconds: float = 1.0) -> None:
        """Create a bus with a positive per-listener delivery timeout.

        Raises:
            ValueError: If ``listener_timeout_seconds`` is not positive.
        """
        if listener_timeout_seconds <= 0:
            raise ValueError("listener_timeout_seconds muss größer als 0 sein")
        self._listener_timeout_seconds = listener_timeout_seconds
        self._subscriptions: list[_Subscription] = []
        self._lock = RLock()

    def subscribe(
        self,
        listener: AgentEventListener,
        *,
        tenant_id: str | None = None,
        session_id: str | None = None,
        allow_all_tenants: bool = False,
    ) -> AgentEventListener:
        """Register a scoped listener once and return it for decorator use.

        At least one tenant or session scope is required. Set
        ``allow_all_tenants`` only for trusted internal listeners. When both
        scopes are provided, an event must match both. Tenant IDs are
        normalized to lowercase while session IDs remain case-sensitive.

        Repeating the same listener and scope is idempotent.

        Raises:
            ValueError: If the registration is unscoped and global delivery
                was not explicitly allowed.
        """
        normalized_tenant = tenant_id.strip().lower() if tenant_id else None
        normalized_session = session_id.strip() if session_id else None
        if not normalized_tenant and not normalized_session and not allow_all_tenants:
            raise ValueError(
                "AgentEvent Listener benötigen tenant_id oder session_id; "
                "globale interne Listener müssen allow_all_tenants=True setzen"
            )
        subscription = _Subscription(
            listener=listener,
            tenant_id=normalized_tenant,
            session_id=normalized_session,
        )
        with self._lock:
            if subscription not in self._subscriptions:
                self._subscriptions.append(subscription)
        return listener

    def unsubscribe(self, listener: AgentEventListener) -> bool:
        """Remove all scopes for this listener object and report any match."""
        with self._lock:
            original_count = len(self._subscriptions)
            self._subscriptions = [
                subscription
                for subscription in self._subscriptions
                if subscription.listener is not listener
            ]
            if len(self._subscriptions) == original_count:
                return False
            return True

    def clear(self) -> None:
        """Remove all listeners, primarily for process shutdown and tests."""
        with self._lock:
            self._subscriptions.clear()

    @property
    def listener_count(self) -> int:
        """Return the number of distinct listener-and-scope subscriptions."""
        with self._lock:
            return len(self._subscriptions)

    async def emit(self, event: AgentEvent) -> None:
        """Deliver copies concurrently to all matching listeners.

        This awaits every delivery or timeout. Listener exceptions and
        timeouts are logged and isolated from the emitter.
        """
        with self._lock:
            subscriptions = tuple(
                subscription
                for subscription in self._subscriptions
                if subscription.accepts(event)
            )
        if not subscriptions:
            return

        async def invoke(subscription: _Subscription) -> None:
            listener_event = event.model_copy(deep=True)
            await subscription.listener(listener_event)

        results = await asyncio.gather(
            *(
                asyncio.wait_for(
                    invoke(subscription),
                    timeout=self._listener_timeout_seconds,
                )
                for subscription in subscriptions
            ),
            return_exceptions=True,
        )
        for subscription, result in zip(subscriptions, results, strict=True):
            if isinstance(result, BaseException):
                logger.warning(
                    "AgentEvent Listener %s fehlgeschlagen (%s)",
                    getattr(
                        subscription.listener,
                        "__name__",
                        type(subscription.listener).__name__,
                    ),
                    type(result).__name__,
                )


_default_bus = AgentEventBus()
_persistence_sink: AgentEventSink | None = None
_persistence_unavailable_until = 0.0


def configure_agent_event_persistence(sink: AgentEventSink | None) -> None:
    """Configure the durable sink used before process-local fan-out."""
    global _persistence_sink, _persistence_unavailable_until
    _persistence_sink = sink
    _persistence_unavailable_until = 0.0


async def emit_agent_event(event: AgentEvent) -> None:
    """Persist an event when configured, then fan it out process-locally.

    Persistence has a 250-ms budget and a five-second failure backoff, avoiding
    cumulative latency during an outage. Storage failures are logged without
    event payloads and do not interrupt agent execution or live listeners.
    """
    global _persistence_unavailable_until
    if (
        _persistence_sink is not None
        and time.monotonic() >= _persistence_unavailable_until
    ):
        try:
            await asyncio.wait_for(
                _persistence_sink(event),
                timeout=_PERSISTENCE_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            _persistence_unavailable_until = (
                time.monotonic() + _PERSISTENCE_BACKOFF_SECONDS
            )
            logger.warning("AgentEvent-Persistenz Zeitlimit überschritten")
        except Exception as exc:
            _persistence_unavailable_until = (
                time.monotonic() + _PERSISTENCE_BACKOFF_SECONDS
            )
            logger.warning(
                "AgentEvent-Persistenz fehlgeschlagen (%s)",
                type(exc).__name__,
            )
    await _default_bus.emit(event)


def on_agent_event(
    listener: AgentEventListener | None = None,
    *,
    tenant_id: str | None = None,
    session_id: str | None = None,
    allow_all_tenants: bool = False,
) -> AgentEventListener | Callable[[AgentEventListener], AgentEventListener]:
    """Register on the default bus, directly or as a decorator.

    The same scope contract as :meth:`AgentEventBus.subscribe` applies:
    callers must provide a tenant or session, unless a trusted internal
    listener explicitly opts into all tenants.
    """
    def register(fn: AgentEventListener) -> AgentEventListener:
        return _default_bus.subscribe(
            fn,
            tenant_id=tenant_id,
            session_id=session_id,
            allow_all_tenants=allow_all_tenants,
        )

    return register if listener is None else register(listener)


def remove_agent_event_listener(listener: AgentEventListener) -> bool:
    """Remove a listener from the default bus."""
    return _default_bus.unsubscribe(listener)


def get_agent_event_listener_count() -> int:
    """Return the number of listeners on the default bus."""
    return _default_bus.listener_count


def clear_agent_event_listeners() -> None:
    """Remove all listeners from the default bus."""
    _default_bus.clear()
