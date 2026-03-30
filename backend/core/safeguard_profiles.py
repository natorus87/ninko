"""
SafeguardProfileStore — persistiert Safeguard-Profile in Redis.

Redis-Schema:
    HSET ninko:safeguard:profiles <profile_id> <JSON>

Built-in Profile (id, builtin=True) werden bei jedem Start geseeded —
sie können nicht gelöscht oder überschrieben werden.

Custom Profile (builtin=False) können über die API erstellt/bearbeitet/gelöscht werden.

Migration: ninko:settings:safeguard enthält evtl. noch "true"/"false" aus der
alten Toggle-API. migrate_legacy() konvertiert das beim ersten Start zu einem
Profil-ID-String.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("ninko.core.safeguard_profiles")

REDIS_KEY_PROFILES  = "ninko:safeguard:profiles"
REDIS_KEY_ACTIVE    = "ninko:settings:safeguard"
REDIS_KEY_CHAT_PFX  = "ninko:safeguard:profile:chat:"
REDIS_KEY_AGENT_PFX = "ninko:safeguard:profile:agent:"
CHAT_PROFILE_TTL    = 86_400   # 24 h


class SafeguardProfileStore:
    """
    CRUD für Safeguard-Profile in Redis.

    Methoden:
        seed_builtins()         — Built-in Profile in Redis speichern (idempotent)
        migrate_legacy()        — "true"/"false" → "moderate"/"disabled" migrieren
        list_profiles()         → list[dict]
        get_profile(id)         → SafeguardProfile | None
        save_profile(profile)   → None (nur Custom-Profile)
        delete_profile(id)      → None (Built-ins geschützt)
    """

    async def seed_builtins(self) -> None:
        """
        Seed built-in profiles into Redis (idempotent — safe to call on every startup).
        Built-in profiles are always overwritten to ensure they stay up-to-date.
        """
        from core.redis_client import get_redis
        from core.safeguard import _BUILTIN_PROFILES

        redis = get_redis()
        for profile in _BUILTIN_PROFILES.values():
            await redis.connection.hset(
                REDIS_KEY_PROFILES,
                profile.id,
                json.dumps(profile.to_dict()),
            )
        logger.info(
            "[SafeguardProfileStore] %d Built-in Profile geseeded.", len(_BUILTIN_PROFILES)
        )

    async def migrate_legacy(self) -> str:
        """
        Konvertiert den alten Toggle-Wert ("true"/"false") zum neuen Profil-ID-Format.
        Gibt die aktive Profil-ID zurück.
        """
        from core.redis_client import get_redis

        redis = get_redis()
        raw = await redis.connection.get(REDIS_KEY_ACTIVE)
        if raw is None:
            # Kein gespeicherter Wert → Standard: "moderate"
            await redis.connection.set(REDIS_KEY_ACTIVE, "moderate")
            logger.info("[SafeguardProfileStore] Kein gespeicherter Safeguard-Status — Standard 'moderate' gesetzt.")
            return "moderate"

        value = raw if isinstance(raw, str) else raw.decode()

        if value == "true":
            await redis.connection.set(REDIS_KEY_ACTIVE, "moderate")
            logger.info("[SafeguardProfileStore] Safeguard-Migration: 'true' → 'moderate'.")
            return "moderate"

        if value == "false":
            await redis.connection.set(REDIS_KEY_ACTIVE, "disabled")
            logger.info("[SafeguardProfileStore] Safeguard-Migration: 'false' → 'disabled'.")
            return "disabled"

        # Already a profile id — validate it
        from core.safeguard import _BUILTIN_PROFILES
        if value in _BUILTIN_PROFILES:
            return value

        # Check custom profiles
        profile_raw = await redis.connection.hget(REDIS_KEY_PROFILES, value)
        if profile_raw:
            return value

        # Unknown profile id — fall back to "moderate"
        logger.warning(
            "[SafeguardProfileStore] Unbekannte Profil-ID '%s' — Fallback auf 'moderate'.", value
        )
        await redis.connection.set(REDIS_KEY_ACTIVE, "moderate")
        return "moderate"

    async def list_profiles(self) -> list[dict]:
        """Alle Profile (Built-in + Custom) zurückgeben."""
        from core.redis_client import get_redis

        redis = get_redis()
        raw_map = await redis.connection.hgetall(REDIS_KEY_PROFILES)
        profiles = []
        for _key, raw_val in raw_map.items():
            try:
                profiles.append(json.loads(
                    raw_val if isinstance(raw_val, str) else raw_val.decode()
                ))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass
        # Sort: built-ins first, then custom alphabetically
        profiles.sort(key=lambda p: (not p.get("builtin", False), p.get("name", "")))
        return profiles

    async def get_profile(self, profile_id: str) -> "SafeguardProfile | None":
        """Profil nach ID aus Redis laden."""
        from core.redis_client import get_redis
        from core.safeguard import SafeguardProfile

        redis = get_redis()
        raw = await redis.connection.hget(REDIS_KEY_PROFILES, profile_id)
        if not raw:
            return None
        try:
            data = json.loads(raw if isinstance(raw, str) else raw.decode())
            return SafeguardProfile.from_dict(data)
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError):
            return None

    async def save_profile(self, profile: "SafeguardProfile") -> None:
        """
        Custom-Profil speichern. Wirft ValueError bei Built-in-Profilen.
        """
        from core.redis_client import get_redis
        from core.safeguard import _BUILTIN_PROFILES

        if profile.id in _BUILTIN_PROFILES:
            raise ValueError(f"Built-in Profil '{profile.id}' kann nicht überschrieben werden.")
        if not profile.id or not profile.name:
            raise ValueError("Profil muss eine ID und einen Namen haben.")

        profile.builtin = False  # Sicherstellen
        redis = get_redis()
        await redis.connection.hset(
            REDIS_KEY_PROFILES,
            profile.id,
            json.dumps(profile.to_dict()),
        )
        logger.info("[SafeguardProfileStore] Profil '%s' gespeichert.", profile.id)

    async def delete_profile(self, profile_id: str) -> None:
        """
        Custom-Profil löschen. Wirft ValueError bei Built-in-Profilen.
        """
        from core.redis_client import get_redis
        from core.safeguard import _BUILTIN_PROFILES

        if profile_id in _BUILTIN_PROFILES:
            raise ValueError(f"Built-in Profil '{profile_id}' kann nicht gelöscht werden.")

        redis = get_redis()
        deleted = await redis.connection.hdel(REDIS_KEY_PROFILES, profile_id)
        if not deleted:
            raise KeyError(f"Profil '{profile_id}' nicht gefunden.")
        logger.info("[SafeguardProfileStore] Profil '%s' gelöscht.", profile_id)

    # ── Per-Chat Profile ───────────────────────────────────────────────────────

    async def set_chat_profile(self, session_id: str, profile_id: str) -> None:
        """Setzt das aktive Profil für eine Chat-Session (TTL 24h)."""
        from core.redis_client import get_redis

        redis = get_redis()
        await redis.connection.setex(
            f"{REDIS_KEY_CHAT_PFX}{session_id}",
            CHAT_PROFILE_TTL,
            profile_id,
        )

    async def get_chat_profile(self, session_id: str) -> str | None:
        """Liest das aktive Profil für eine Chat-Session."""
        from core.redis_client import get_redis

        redis = get_redis()
        raw = await redis.connection.get(f"{REDIS_KEY_CHAT_PFX}{session_id}")
        if raw:
            return raw if isinstance(raw, str) else raw.decode()
        return None

    async def clear_chat_profile(self, session_id: str) -> None:
        """Entfernt das Chat-spezifische Profil (Fallback auf globales)."""
        from core.redis_client import get_redis

        redis = get_redis()
        await redis.connection.delete(f"{REDIS_KEY_CHAT_PFX}{session_id}")
