"""
Redis Distributed Lock – Für K8s Multi-Instance Deployments.

In K8s-Umgebungen läuft jede Backend-Instanz als separater Pod mit eigenem Speicher.
asyncio.Lock() funktioniert nur pro-Prozess, nicht pro-Cluster.

Dieses Modul implementiert ein verteiltes Lock mit Redis SET NX PX:
- Atomic acquire (SET NX PX)
- Automatic expiry (PX)
- Safe release (Lua script für atomic check-and-delete)

Verwendung:
    lock = RedisLock("my-resource", ttl_ms=5000)
    async with lock:
        # kritischer Bereich
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from redis.exceptions import RedisError

from core.redis_client import get_redis

logger = logging.getLogger("ninko.distlock")


class RedisLockError(Exception):
    """Base exception for RedisLock errors."""


class LockNotAcquiredError(RedisLockError):
    """Raised when lock cannot be acquired (timeout exceeded)."""


class RedisLock:
    """Distributed lock using Redis SET NX PX.

    Attributes:
        key: Redis key for this lock
        ttl_ms: Lock expiry time in milliseconds (auto-release)
        retry_interval_ms: How often to retry acquisition
        max_wait_ms: Maximum time to wait for lock
    """

    _RELEASE_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    def __init__(
        self,
        key: str,
        *,
        ttl_ms: int = 5000,
        retry_interval_ms: int = 50,
        max_wait_ms: int = 30000,
    ) -> None:
        self.key = f"lock:{key}"
        self.ttl_ms = ttl_ms
        self.retry_interval_ms = retry_interval_ms
        self.max_wait_ms = max_wait_ms
        self._owner_id = uuid.uuid4().hex
        self._released = False

    async def acquire(self) -> bool:
        """Acquire the lock.

        Returns:
            True if lock acquired, False if max_wait_ms exceeded.

        Raises:
            RedisLockError: On Redis connection errors.
        """
        redis = get_redis()
        deadline = time.monotonic() + (self.max_wait_ms / 1000)

        while time.monotonic() < deadline:
            try:
                acquired = await redis.connection.set(
                    self.key,
                    self._owner_id,
                    nx=True,  # Only set if not exists
                    px=self.ttl_ms,  # Expiry in milliseconds
                )
                if acquired:
                    logger.debug(
                        "Lock acquired: %s (owner=%s, ttl=%dms)",
                        self.key,
                        self._owner_id,
                        self.ttl_ms,
                    )
                    return True
            except RedisError as exc:
                logger.warning("Redis lock acquire error (key=%s): %s", self.key, exc)
                raise RedisLockError(f"Failed to acquire lock: {exc}") from exc

            await asyncio.sleep(self.retry_interval_ms / 1000)

        logger.debug(
            "Lock acquisition timeout: %s (waited %dms)", self.key, self.max_wait_ms
        )
        return False

    async def release(self) -> bool:
        """Release the lock (only if we own it).

        Uses Lua script for atomic check-and-delete to prevent
        releasing a lock owned by another process.

        Returns:
            True if lock was released, False if we didn't own it.
        """
        if self._released:
            return True

        try:
            redis = get_redis()
            result = await redis.connection.eval(
                self._RELEASE_SCRIPT,
                1,  # number of keys
                self.key,  # KEYS[1]
                self._owner_id,  # ARGV[1]
            )
            self._released = True
            if result:
                logger.debug("Lock released: %s (owner=%s)", self.key, self._owner_id)
                return True
            logger.debug("Lock release failed (not owner or expired): %s", self.key)
            return False
        except RedisError as exc:
            logger.warning("Redis lock release error (key=%s): %s", self.key, exc)
            return False

    async def extend(self, additional_ms: int) -> bool:
        """Extend lock TTL (only if we own it).

        Args:
            additional_ms: Additional time in milliseconds.

        Returns:
            True if extended, False if not owned or Redis error.
        """
        try:
            redis = get_redis()
            # Only extend if we still own it
            current = await redis.connection.get(self.key)
            if current == self._owner_id:
                await redis.connection.pexpire(self.key, additional_ms)
                logger.debug("Lock extended: %s (+%dms)", self.key, additional_ms)
                return True
            return False
        except RedisError as exc:
            logger.warning("Redis lock extend error (key=%s): %s", self.key, exc)
            return False

    @asynccontextmanager
    async def holding(self) -> AsyncIterator[bool]:
        """Context manager for lock acquisition.

        Yields:
            True if lock was acquired, False if timeout exceeded.

        Example:
            lock = RedisLock("my-resource", ttl_ms=5000)
            async with lock.holding() as acquired:
                if acquired:
                    # do work
                else:
                    # handle timeout
        """
        acquired = await self.acquire()
        try:
            yield acquired
        finally:
            if acquired:
                await self.release()


class RedisLockManager:
    """Manages multiple RedisLock instances with automatic cleanup.

    Prevents creating duplicate locks for the same key and handles
    cleanup of expired locks.
    """

    def __init__(self) -> None:
        self._locks: dict[str, RedisLock] = {}
        self._locks_ts: dict[str, float] = {}  # creation timestamp
        self._cleanup_interval_ms = 60000  # 1 minute
        self._cleanup_task: asyncio.Task[None] | None = None
        self._started = False

    def get_lock(self, key: str, **kwargs) -> RedisLock:
        """Get or create a lock for the given key.

        Args:
            key: Lock key (will be prefixed with "lock:")
            **kwargs: Passed to RedisLock constructor

        Returns:
            RedisLock instance for this key.
        """
        if key not in self._locks:
            self._locks[key] = RedisLock(key, **kwargs)
            self._locks_ts[key] = time.monotonic()
        return self._locks[key]

    async def acquire(self, key: str, **kwargs) -> bool:
        """Acquire a lock, creating it if needed.

        Args:
            key: Lock key
            **kwargs: Passed to RedisLock

        Returns:
            True if acquired.
        """
        lock = self.get_lock(key, **kwargs)
        return await lock.acquire()

    @asynccontextmanager
    async def hold(self, key: str, **kwargs) -> AsyncIterator[bool]:
        """Context manager for holding a lock.

        Args:
            key: Lock key
            **kwargs: Passed to RedisLock

        Yields:
            True if lock acquired.
        """
        lock = self.get_lock(key, **kwargs)
        async with lock.holding() as acquired:
            yield acquired

    async def cleanup_expired(self) -> None:
        """Remove expired lock references from memory."""
        now = time.monotonic()
        expired_keys = [k for k, ts in list(self._locks_ts.items()) if now - ts > 300]
        for k in expired_keys:
            self._locks.pop(k, None)
            self._locks_ts.pop(k, None)

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task."""
        if self._started:
            return
        self._started = True

        async def _cleanup_loop() -> None:
            while True:
                await asyncio.sleep(self._cleanup_interval_ms / 1000)
                try:
                    await self.cleanup_expired()
                except Exception as exc:
                    logger.warning("Lock cleanup error: %s", exc)

        self._cleanup_task = asyncio.create_task(_cleanup_loop())
        logger.info("RedisLockManager cleanup task started")

    async def stop(self) -> None:
        """Stop cleanup task and release all locks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        self._locks.clear()
        self._locks_ts.clear()
        logger.info("RedisLockManager stopped")


# Singleton instance
_lock_manager: RedisLockManager | None = None


def get_lock_manager() -> RedisLockManager:
    """Get the global lock manager instance."""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = RedisLockManager()
    return _lock_manager
