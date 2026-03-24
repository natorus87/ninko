"""
Kumio Redis Client – Working Memory, PubSub-Events, Cache.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis

from core.config import get_settings

logger = logging.getLogger("kumio.redis")


class RedisClient:
    """Async Redis Client für Kumio."""

    EVENTS_CHANNEL = "kumio:events"
    CHAT_HISTORY_PREFIX = "kumio:chat:"
    CACHE_PREFIX = "kumio:cache:"

    def __init__(self) -> None:
        settings = get_settings()
        self._redis = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            encoding="utf-8",
        )
        self._pubsub: aioredis.client.PubSub | None = None
        logger.info("Redis Client initialisiert: %s", settings.REDIS_URL)

    @property
    def connection(self) -> aioredis.Redis:
        """Gibt die Redis-Connection zurück."""
        return self._redis

    # ── Chat-History (Working Memory) ──────────────────
    async def store_chat_message(
        self, session_id: str, role: str, content: str, max_messages: int = 50
    ) -> None:
        """Speichert eine Chat-Nachricht in der Working Memory."""
        key = f"{self.CHAT_HISTORY_PREFIX}{session_id}"
        message = json.dumps({"role": role, "content": content})
        await self._redis.rpush(key, message)
        await self._redis.ltrim(key, -max_messages, -1)
        await self._redis.expire(key, 86400)  # 24h TTL

    async def get_chat_history(self, session_id: str) -> list[dict]:
        """Gibt die Chat-History einer Session zurück."""
        key = f"{self.CHAT_HISTORY_PREFIX}{session_id}"
        raw = await self._redis.lrange(key, 0, -1)
        return [json.loads(msg) for msg in raw]

    async def clear_chat_history(self, session_id: str) -> None:
        """Löscht die Chat-History einer Session."""
        key = f"{self.CHAT_HISTORY_PREFIX}{session_id}"
        await self._redis.delete(key)

    # ── PubSub Events ──────────────────────────────────
    async def publish_event(self, event: dict) -> None:
        """Publisht ein Event auf dem Events-Channel."""
        await self._redis.publish(self.EVENTS_CHANNEL, json.dumps(event))
        logger.debug("Event veröffentlicht: %s", event.get("event_type", "unknown"))

    async def subscribe_events(self) -> aioredis.client.PubSub:
        """Erstellt ein PubSub-Subscription für Events."""
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(self.EVENTS_CHANNEL)
        logger.info("PubSub-Subscription erstellt: %s", self.EVENTS_CHANNEL)
        return pubsub

    # ── UI Chat History (persistent, geräteübergreifend) ──
    UI_HISTORY_KEY = "kumio:ui:history"

    async def ui_history_save(self, conversation: dict) -> None:
        """Speichert oder aktualisiert einen Konversationseintrag dauerhaft."""
        conv_id = conversation.get("id")
        if not conv_id:
            return
        await self._redis.hset(self.UI_HISTORY_KEY, conv_id, json.dumps(conversation))

    async def ui_history_get_all(self) -> list[dict]:
        """Gibt alle gespeicherten Konversationen zurück (sortiert nach updatedAt desc)."""
        raw = await self._redis.hgetall(self.UI_HISTORY_KEY)
        entries = [json.loads(v) for v in raw.values()]
        entries.sort(key=lambda e: e.get("updatedAt", 0), reverse=True)
        return entries

    async def ui_history_delete(self, conv_id: str) -> None:
        """Löscht einen Konversationseintrag."""
        await self._redis.hdel(self.UI_HISTORY_KEY, conv_id)

    # ── Cache ──────────────────────────────────────────
    async def cache_set(self, key: str, value: Any, ttl: int = 300) -> None:
        """Setzt einen Cache-Eintrag mit TTL (Standard: 5 Min)."""
        cache_key = f"{self.CACHE_PREFIX}{key}"
        await self._redis.set(cache_key, json.dumps(value), ex=ttl)

    async def cache_get(self, key: str) -> Any | None:
        """Gibt einen Cache-Eintrag zurück oder None."""
        cache_key = f"{self.CACHE_PREFIX}{key}"
        raw = await self._redis.get(cache_key)
        if raw is not None:
            return json.loads(raw)
        return None

    async def cache_delete(self, key: str) -> None:
        """Löscht einen Cache-Eintrag."""
        cache_key = f"{self.CACHE_PREFIX}{key}"
        await self._redis.delete(cache_key)

    # ── Health ─────────────────────────────────────────
    async def health_check(self) -> dict:
        """Prüft die Redis-Verbindung."""
        try:
            pong = await self._redis.ping()
            return {"status": "ok", "detail": f"PONG={pong}"}
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}

    # ── Cleanup ────────────────────────────────────────
    async def close(self) -> None:
        """Schließt die Redis-Verbindung."""
        await self._redis.aclose()
        logger.info("Redis-Verbindung geschlossen.")


# Singleton
_redis_client: RedisClient | None = None


def get_redis() -> RedisClient:
    """Gibt die globale Redis-Instanz zurück (lazy init)."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
