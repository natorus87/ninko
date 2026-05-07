"""
Redis-backed token bucket rate limiter for API requests.
Atomic operations via Lua script — safe for multi-worker deployments.
"""

from __future__ import annotations

import asyncio
import time


# Lua script for atomic token bucket
# Returns: [allowed (0/1), retry_after (int)]
_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_per_sec = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = 1

-- Get current bucket state
local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1])
local last_refill = tonumber(bucket[2])

-- Initialize if missing
if tokens == nil then
    tokens = capacity
    last_refill = now
end

-- Refill tokens based on elapsed time
local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + elapsed * refill_per_sec)

-- Check if request can proceed
if tokens >= requested then
    tokens = tokens - requested
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    return {1, 0}
else
    local needed = requested - tokens
    local retry_after = math.ceil(needed / refill_per_sec)
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    return {0, retry_after}
end
"""


class RedisRateLimiter:
    """Redis-backed token bucket rate limiter — shared state across workers."""

    _SCRIPT_SHA: str | None = None

    def __init__(self, per_minute: int, burst: int) -> None:
        self.per_minute = max(1, int(per_minute))
        self.capacity = max(1, int(burst))
        self.refill_per_sec = self.per_minute / 60.0
        self._script_lock = asyncio.Lock()
        self._fallback: InMemoryRateLimiter | None = None

    async def _get_script_sha(self, redis) -> str:
        if RedisRateLimiter._SCRIPT_SHA is None:
            async with self._script_lock:
                if RedisRateLimiter._SCRIPT_SHA is None:
                    RedisRateLimiter._SCRIPT_SHA = await redis.connection.script_load(
                        _TOKEN_BUCKET_LUA
                    )
        sha = RedisRateLimiter._SCRIPT_SHA
        assert sha is not None
        return sha

    async def allow(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds). Falls Redis down → fail-open."""
        try:
            from core.redis_client import get_redis

            redis = get_redis()
            now = time.time()
            script_sha = await self._get_script_sha(redis)

            try:
                result = await redis.connection.evalsha(
                    script_sha,
                    1,
                    f"ninko:rate_limit:{key}",
                    str(self.capacity),
                    str(self.refill_per_sec),
                    str(now),
                )
            except Exception as exc:
                if "NOSCRIPT" in str(exc):
                    RedisRateLimiter._SCRIPT_SHA = None
                    script_sha = await self._get_script_sha(redis)
                    result = await redis.connection.evalsha(
                        script_sha,
                        1,
                        f"ninko:rate_limit:{key}",
                        str(self.capacity),
                        str(self.refill_per_sec),
                        str(now),
                    )
                else:
                    raise

            allowed, retry_after = int(result[0]), int(result[1])
            return (allowed == 1), retry_after

        except Exception:
            if self._fallback is None:
                self._fallback = InMemoryRateLimiter(self.per_minute, self.capacity)
            return await self._fallback.allow(key)


class InMemoryRateLimiter:
    """In-memory fallback used only when Redis is unavailable."""

    _BUCKET_TTL_SECS = 3600.0
    _CLEANUP_INTERVAL = 300

    def __init__(self, per_minute: int, burst: int) -> None:
        self.per_minute = max(1, int(per_minute))
        self.capacity = max(1, int(burst))
        self.refill_per_sec = self.per_minute / 60.0
        self._buckets: dict[str, tuple[float, float]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_cleanup: float = time.monotonic()

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _maybe_cleanup(self, now: float) -> None:
        if now - self._last_cleanup < self._CLEANUP_INTERVAL:
            return
        self._last_cleanup = now
        expired_keys = [
            key for key, (_, last) in self._buckets.items() if now - last > self._BUCKET_TTL_SECS
        ]
        for key in expired_keys:
            self._buckets.pop(key, None)
            self._locks.pop(key, None)

    async def allow(self, key: str) -> tuple[bool, int]:
        now = time.monotonic()
        self._maybe_cleanup(now)
        async with self._get_lock(key):
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
