"""
Ninko Redis Client – Working Memory, PubSub-Events, Cache.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import RedisError

from core.config import get_settings

logger = logging.getLogger("ninko.redis")


class RedisClient:
    """Async Redis Client für Ninko."""

    EVENTS_CHANNEL = "ninko:events"
    CHAT_HISTORY_PREFIX = "ninko:chat:"
    CACHE_PREFIX = "ninko:cache:"

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

    async def hgetall_paginated(self, key: str, page_size: int = 100) -> dict:
        """Holt alle Einträge aus einem Redis Hash mit HSCAN-Pagination.

        HSCAN iteriert über große Hashes ohne sie komplett in den RAM zu laden.
        Bessere Performance als hgetall() bei 1000+ Einträgen.

        Args:
            key: Redis Hash-Key
            page_size: Anzahl der Einträge pro Scan-Iteration (default: 100)

        Returns:
            Vollständiger dict mit allen Hash-Einträgen
        """
        result = {}
        cursor = 0

        while True:
            cursor, partial = await self._redis.hscan(key, cursor, count=page_size)
            result.update(partial)
            if cursor == 0:
                break

        return result

    # ── Chat-History (Working Memory) ──────────────────
    async def store_chat_message(
        self, session_id: str, role: str, content: str, max_messages: int = 100
    ) -> None:
        """Speichert eine Chat-Nachricht in der Working Memory.

        Args:
            session_id: Session-Identifikator
            role: Nachrichtenrolle (user, assistant, system_compaction, etc.)
            content: Nachrichteninhalt
            max_messages: Maximum Anzahl der gespeicherten Nachrichten (default=100, alte werden gelöscht)
        """
        key = f"{self.CHAT_HISTORY_PREFIX}{session_id}"
        message = json.dumps({"role": role, "content": content})
        await self._redis.rpush(key, message)
        await self._redis.ltrim(key, -max_messages, -1)
        settings = get_settings()
        chat_history_ttl = getattr(settings, 'CHAT_HISTORY_TTL_SECONDS', 86400)
        await self._redis.expire(key, chat_history_ttl)

    async def get_chat_history(self, session_id: str, limit: int = 100) -> list[dict]:
        """Gibt die Chat-History einer Session zurück (maximal die neuesten `limit` Nachrichten).

        Args:
            session_id: Session-Identifikator
            limit: Maximum Anzahl der zurückzugebenden Nachrichten (neueste zuerst), default=100

        Returns:
            Liste der Chat-Nachrichten, begrenzt auf die letzten `limit` Einträge
        """
        key = f"{self.CHAT_HISTORY_PREFIX}{session_id}"
        raw = await self._redis.lrange(key, -limit, -1)
        return [json.loads(msg) for msg in raw]

    async def clear_chat_history(self, session_id: str) -> None:
        """Löscht die Chat-History einer Session."""
        key = f"{self.CHAT_HISTORY_PREFIX}{session_id}"
        await self._redis.delete(key)

    # ── Session-Owner (IDOR-Mitigation) ──────────────────
    SESSION_OWNER_PREFIX = "ninko:session_owner:"

    def _session_owner_key(self, session_id: str) -> str:
        return f"{self.SESSION_OWNER_PREFIX}{session_id}"

    async def set_session_owner(self, session_id: str, owner: str) -> None:
        """Markiert eine Session mit ihrem Eigentümer (Username). Verhindert IDOR (CWE-639).

        TTL entspricht CHAT_HISTORY_TTL_SECONDS, sodass der Owner-Eintrag
        automatisch mit der Session verfällt.
        """
        key = self._session_owner_key(session_id)
        settings = get_settings()
        ttl = getattr(settings, "CHAT_HISTORY_TTL_SECONDS", 86400)
        # Atomar: SET key value EX ttl — verhindert verwaiste Keys ohne TTL,
        # falls der Task zwischen SET und EXPIRE gecancelt wird.
        await self._redis.set(key, owner, ex=ttl)

    async def get_session_owner(self, session_id: str) -> str | None:
        """Gibt den Owner (Username) einer Session zurück, oder None wenn nicht gesetzt."""
        return await self._redis.get(self._session_owner_key(session_id))

    async def clear_session_owner(self, session_id: str) -> None:
        """Entfernt den Owner-Eintrag (z. B. beim Session-Delete)."""
        await self._redis.delete(self._session_owner_key(session_id))

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
    UI_HISTORY_KEY = "ninko:ui:history"

    def _ui_history_key(self, tenant_id: str = "default") -> str:
        t = (tenant_id or "default").strip().lower().replace(" ", "_")
        return f"{self.UI_HISTORY_KEY}:{t or 'default'}"

    async def ui_history_save(self, conversation: dict, *, tenant_id: str = "default") -> None:
        """Speichert oder aktualisiert einen Konversationseintrag dauerhaft."""
        conv_id = conversation.get("id")
        if not conv_id:
            return
        await self._redis.hset(self._ui_history_key(tenant_id), conv_id, json.dumps(conversation))

    async def ui_history_get_all(self, *, tenant_id: str = "default") -> list[dict]:
        """Gibt alle gespeicherten Konversationen zurück (sortiert nach updatedAt desc).

        Nutzt hgetall_paginated() für effiziente Pagination bei vielen Einträgen.
        """
        raw = await self.hgetall_paginated(self._ui_history_key(tenant_id))
        entries = []

        for value in raw.values():
            try:
                entries.append(json.loads(value))
            except (json.JSONDecodeError, ValueError):
                # Malformed entry — skip silently
                continue

        entries.sort(key=lambda e: e.get("updatedAt", 0), reverse=True)
        return entries

    async def ui_history_delete(self, conv_id: str, *, tenant_id: str = "default") -> None:
        """Löscht einen Konversationseintrag."""
        await self._redis.hdel(self._ui_history_key(tenant_id), conv_id)

    async def ui_history_clear_all(self, *, tenant_id: str = "default") -> None:
        """Löscht den Chatverlauf eines Tenants, außer angepinnten Einträgen."""
        key = self._ui_history_key(tenant_id)
        raw = await self.hgetall_paginated(key)
        unpinned_ids = []
        for conv_id, value in raw.items():
            try:
                conversation = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                unpinned_ids.append(conv_id)  # malformed entry — purge it too
                continue
            if not conversation.get("pinned"):
                unpinned_ids.append(conv_id)
        if unpinned_ids:
            await self._redis.hdel(key, *unpinned_ids)

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
        except (RedisError, OSError) as exc:
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
