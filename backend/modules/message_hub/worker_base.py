"""
Message Hub — Abstract Background Worker mit Exponential Backoff.

Jeder Channel-Worker erbt von dieser Klasse und implementiert:
  - async run_once()   → eine "Polling/IDLE"-Iteration
  - channel_type: str  → 'telegram' | 'discord' | 'email'
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("ninko.modules.message_hub.worker")

# Backoff-Konfiguration
_BACKOFF_BASE = 1.0       # Startverzögerung in Sekunden
_BACKOFF_MULTIPLIER = 2.0 # Faktor pro Fehlschlag
_BACKOFF_MAX = 300.0      # Max. Wartezeit (5 Minuten)
_STABLE_RUN_THRESHOLD = 60.0  # Laufzeit ab der Backoff zurückgesetzt wird


class ChannelWorker(ABC):
    """
    Abstrakte Basis für alle Message-Hub-Channel-Worker.

    Startet als asyncio.Task und überwacht sich selbst:
    Bei Fehlern → Exponential Backoff → automatischer Neustart.
    """

    channel_type: str  # muss von Subklassen gesetzt werden

    def __init__(self, app: "FastAPI") -> None:
        self.app = app
        self.running = False
        self.configured = True  # Subklassen setzen auf False wenn keine Verbindung konfiguriert
        self._task: asyncio.Task | None = None
        self._restart_count = 0
        self._last_error: str | None = None
        self._next_retry_at: float | None = None
        self._current_backoff = _BACKOFF_BASE

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Startet den Worker als Hintergrund-Task."""
        if self.running:
            logger.warning("%s-Worker läuft bereits", self.channel_type)
            return
        self.running = True
        self._task = asyncio.create_task(
            self._loop(), name=f"msg_hub_{self.channel_type}"
        )
        logger.info("%s-Worker gestartet", self.channel_type)

    async def stop(self) -> None:
        """Stoppt den Worker graceful."""
        self.running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
        logger.info("%s-Worker gestoppt", self.channel_type)

    # ── Main Loop ─────────────────────────────────────────────────────

    async def _loop(self) -> None:
        """Supervisor-Loop mit Exponential Backoff bei Fehlern."""
        try:
            while self.running:
                time.monotonic()
                try:
                    await self.run_once()
                    # Erfolgreiche Iteration → Backoff immer zurücksetzen
                    self._current_backoff = _BACKOFF_BASE
                    self._last_error = None
                except asyncio.CancelledError:
                    break
                except Exception as exc:  # noqa: BLE001
                    self._last_error = str(exc)
                    self._restart_count += 1
                    delay = min(self._current_backoff, _BACKOFF_MAX)
                    self._current_backoff = min(
                        self._current_backoff * _BACKOFF_MULTIPLIER, _BACKOFF_MAX
                    )
                    self._next_retry_at = time.monotonic() + delay
                    logger.error(
                        "%s-Worker Fehler (Neustart #%d in %.0fs): %s",
                        self.channel_type,
                        self._restart_count,
                        delay,
                        exc,
                        exc_info=True,
                    )
                    try:
                        await asyncio.sleep(delay)
                    except asyncio.CancelledError:
                        break
                    finally:
                        self._next_retry_at = None
        finally:
            # Stellt sicher, dass running==False nach Task-Ende (auch bei Cancel)
            self.running = False

    # ── Abstract ──────────────────────────────────────────────────────

    @abstractmethod
    async def run_once(self) -> None:
        """
        Führt eine vollständige Polling/IDLE-Iteration durch.
        Muss self.running prüfen und bei False sauber beenden.
        Wirft Exception → Worker wartet mit Backoff und startet neu.
        """

    # ── Status ────────────────────────────────────────────────────────

    def status(self) -> dict:
        next_retry_in: float | None = None
        if self._next_retry_at is not None:
            remaining = self._next_retry_at - time.monotonic()
            next_retry_in = max(0.0, remaining)
        return {
            "channel_type": self.channel_type,
            "running": self.running and (
                self._task is not None and not self._task.done()
            ),
            "configured": self.configured,
            "managed_externally": False,
            "restart_count": self._restart_count,
            "last_error": self._last_error,
            "next_retry_in": next_retry_in,
        }

    # ── Shared Helper ─────────────────────────────────────────────────

    async def dispatch(
        self,
        channel_id: str,
        text: str,
        context_prefix: str = "",
        reply_fn=None,
    ) -> None:
        """
        Routing-Lookup + Orchestrator-Call + optionale Antwort.

        Args:
            channel_id:    Sender-ID (chat_id, Kanal-ID, E-Mail-Adresse)
            text:          Eingehender Text
            context_prefix: Zusätzlicher Kontext-String für das LLM
            reply_fn:      async callable(response_text) → None
        """
        from .db import lookup_route
        from core.redis_client import get_redis

        route = await lookup_route(self.channel_type, channel_id)
        if not route:
            logger.debug(
                "%s: Kein aktiver Route-Eintrag für channel_id=%s",
                self.channel_type,
                channel_id,
            )
            return

        # Safeguard-Profil setzen (Permission Cap)
        from .schemas import PERMISSION_TO_SAFEGUARD_PROFILE
        from core.safeguard_profiles import get_profile_manager

        profile_id = PERMISSION_TO_SAFEGUARD_PROFILE.get(route.permission_cap, "user_only")
        pm = get_profile_manager()
        await pm.set_chat_profile(route.session_id, profile_id)

        # Orchestrator aufrufen
        try:
            orchestrator = self.app.state.orchestrator
            redis = get_redis()
            history = await redis.get_chat_history(route.session_id)

            full_text = f"{context_prefix}\n{text}".strip() if context_prefix else text
            response_text, _, did_compact, route_meta = await orchestrator.route(
                message=full_text,
                chat_history=history,
                session_id=route.session_id,
                confirmed=False,  # Safeguard läuft immer für externe Requests
            )

            await redis.store_chat_message(
                session_id=route.session_id, role="user", content=text
            )
            await redis.store_chat_message(
                session_id=route.session_id, role="assistant", content=response_text
            )

            if did_compact:
                summary = (route_meta or {}).get("compaction_summary")
                await redis.store_chat_message(
                    session_id=route.session_id,
                    role="system_compaction",
                    content=summary or "Conversation history has been compressed.",
                )

            if reply_fn is not None:
                await reply_fn(response_text)

        except Exception as exc:
            logger.error(
                "%s: Fehler bei Dispatch für channel_id=%s session=%s: %s",
                self.channel_type,
                channel_id,
                route.session_id,
                exc,
                exc_info=True,
            )
