"""
Simple in-memory token bucket rate limiter for API requests.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict


class InMemoryRateLimiter:
    def __init__(self, per_minute: int, burst: int) -> None:
        self.per_minute = max(1, int(per_minute))
        self.capacity = max(1, int(burst))
        self.refill_per_sec = self.per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def allow(self, key: str) -> tuple[bool, int]:
        """
        Returns (allowed, retry_after_seconds).
        """
        now = time.monotonic()
        async with self._locks[key]:
            tokens, last = self._buckets.get(key, (float(self.capacity), now))
            elapsed = max(0.0, now - last)
            tokens = min(float(self.capacity), tokens + elapsed * self.refill_per_sec)

            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now)
                return True, 0

            needed = 1.0 - tokens
            retry_after = max(1, int(needed / self.refill_per_sec))
            self._buckets[key] = (tokens, now)
            return False, retry_after
