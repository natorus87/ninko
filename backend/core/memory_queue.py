"""
Debounced Memory Queue – Batch-Processing für Memory-Updates.

Verhindert Task-Flood bei schnellen Chats, indem Memory-Updates
gesammelt und erst nach einer Debounce-Periode verarbeitet werden.

Pattern (DeerFlow-inspired):
    MemoryQueue.add(session_id, messages)
    # → Wartet debounce_seconds Sekunden
    # → Verarbeitet alle queued Messages zusammen
    # → LLM Fact Extraction + Speicherung
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger("ninko.memory_queue")


class MemoryQueue:
    """Queue for batching memory updates with debouncing.

    Instead of updating memory after every message, this queue collects
    updates and processes them together after a debounce period.

    Attributes:
        debounce_seconds: Seconds to wait before processing queued updates.
        max_batch_size: Maximum messages to process in one batch.
    """

    def __init__(
        self,
        *,
        debounce_seconds: float = 30.0,
        max_batch_size: int = 50,
    ) -> None:
        self.debounce_seconds = debounce_seconds
        self.max_batch_size = max_batch_size
        self._queue: dict[str, list[dict[str, Any]]] = {}
        self._queue_ts: dict[str, float] = {}  # session_id → first queued time
        self._lock = asyncio.Lock()
        self._processor_task: asyncio.Task[None] | None = None
        self._started = False

    def add(self, session_id: str, messages: list[dict[str, Any]]) -> None:
        """Add messages to the queue for a session.

        Args:
            session_id: Session identifier.
            messages: List of message dicts to process for memory.
        """
        if not messages:
            return

        if session_id not in self._queue:
            self._queue[session_id] = []
            self._queue_ts[session_id] = time.monotonic()

        self._queue[session_id].extend(messages)
        if len(self._queue[session_id]) > self.max_batch_size:
            self._queue[session_id] = self._queue[session_id][-self.max_batch_size :]

        logger.debug(
            "Memory queue add: session=%s count=%d total=%d",
            session_id[:8],
            len(messages),
            len(self._queue[session_id]),
        )

    async def _process_session(self, session_id: str) -> None:
        """Process queued messages for a single session.

        Args:
            session_id: Session to process.
        """
        messages = self._queue.pop(session_id, [])
        if not messages:
            return

        ts = self._queue_ts.pop(session_id, 0)
        wait_time = time.monotonic() - ts

        logger.debug(
            "Processing memory batch: session=%s count=%d waited=%.1fs",
            session_id[:8],
            len(messages),
            wait_time,
        )

        try:
            from core.memory import get_memory

            memory = get_memory()
            if memory is None:
                logger.debug("Memory not available, skipping batch")
                return

            for msg in messages:
                await memory.store(
                    content=msg.get("content", ""),
                    metadata={
                        "session_id": session_id,
                        "type": msg.get("type", "fact"),
                    },
                    category=msg.get("type", "fact"),
                )
        except Exception as exc:
            logger.warning("Memory batch processing failed: %s", exc)

    async def _process_loop(self) -> None:
        """Background loop that processes queued sessions."""
        while True:
            await asyncio.sleep(1.0)

            now = time.monotonic()
            ready_sessions = []

            async with self._lock:
                for session_id, ts in list(self._queue_ts.items()):
                    elapsed = now - ts
                    if elapsed >= self.debounce_seconds:
                        ready_sessions.append(session_id)

            for session_id in ready_sessions:
                await self._process_session(session_id)

    def start(self) -> None:
        """Start the background processor task."""
        if self._started:
            return
        self._started = True
        self._processor_task = asyncio.create_task(self._process_loop())
        logger.info(
            "MemoryQueue processor started (debounce=%.1fs)", self.debounce_seconds
        )

    async def stop(self) -> None:
        """Stop the processor and flush remaining queue."""
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            for session_id in list(self._queue.keys()):
                await self._process_session(session_id)

        logger.info("MemoryQueue processor stopped")

    def get_queue_size(self) -> int:
        """Return total number of queued messages."""
        return sum(len(msgs) for msgs in self._queue.values())

    def get_session_count(self) -> int:
        """Return number of sessions in queue."""
        return len(self._queue)


_memory_queue: MemoryQueue | None = None


def get_memory_queue() -> MemoryQueue:
    """Get the global MemoryQueue instance."""
    global _memory_queue
    if _memory_queue is None:
        _memory_queue = MemoryQueue()
        _memory_queue.start()
    return _memory_queue
