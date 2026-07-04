"""
AgentConfigStore — persistiert per-Agent Settings in Redis.
Nutzt einen Hash-Key: ninko:agent_configs
  Field: agent_id
  Value: JSON-String, z.B. '{"safeguard_enabled": true}'

Kein Schema-Migration nötig — Redis-Hash wächst dynamisch.
"""

import asyncio
import json
import logging

logger = logging.getLogger("ninko.core.agent_config_store")

REDIS_KEY = "ninko:agent_configs"

# Serialisiert Read-Modify-Write auf dem gemeinsamen Hash, damit parallele Writes
# (z.B. set_safeguard + set_profile aus zwei Requests) sich nicht gegenseitig
# überschreiben. Prozessweit — wirkt in der Single-Process-Deployment.
_config_write_lock = asyncio.Lock()


class AgentConfigStore:
    """
    Speichert beliebige Agent-Settings als JSON in einem Redis-Hash.
    Safeguard-Status ist der erste Use Case, aber die Struktur ist
    offen für weitere per-Agent Settings (z.B. max_retries, timeout, ...).

    Redis-Schema:
        HSET ninko:agent_configs <agent_id> '{"safeguard_enabled": true}'
    """

    # ── Generic Config Get/Set ─────────────────────────────────────────────────

    async def get_config(self, agent_id: str) -> dict:
        from core.redis_client import get_redis
        redis = get_redis()
        raw = await redis.connection.hget(REDIS_KEY, agent_id)
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    async def _mutate(self, agent_id: str, mutator) -> None:
        """Atomares Read-Modify-Write auf dem Config-Hash (unter Lock)."""
        from core.redis_client import get_redis
        redis = get_redis()
        async with _config_write_lock:
            config = await self.get_config(agent_id)
            mutator(config)
            await redis.connection.hset(REDIS_KEY, agent_id, json.dumps(config))

    async def set_config(self, agent_id: str, key: str, value) -> None:
        await self._mutate(agent_id, lambda config: config.__setitem__(key, value))

    async def delete_config(self, agent_id: str) -> None:
        """Entfernt alle gespeicherten Overrides eines Agenten (bei Agent-Delete).

        Verhindert verwaiste, sicherheitsrelevante Einträge (z.B. safeguard_enabled=false).
        """
        from core.redis_client import get_redis
        redis = get_redis()
        await redis.connection.hdel(REDIS_KEY, agent_id)

    # ── Safeguard-spezifisch (convenience wrapper) ────────────────────────────

    async def get_safeguard(self, agent_id: str) -> bool | None:
        """
        None   → kein gespeicherter State, globaler Toggle gilt
        True   → Safeguard für diesen Agent explizit aktiviert
        False  → Safeguard für diesen Agent explizit deaktiviert (autonom)
        """
        config = await self.get_config(agent_id)
        return config.get("safeguard_enabled", None)

    async def set_safeguard(self, agent_id: str, enabled: bool) -> None:
        await self.set_config(agent_id, "safeguard_enabled", enabled)
        logger.info(
            "[AgentConfigStore] Agent '%s' safeguard_enabled=%s gespeichert.",
            agent_id, enabled,
        )

    # ── Safeguard-Profil (pro Agent) ──────────────────────────────────────────

    async def get_profile(self, agent_id: str) -> str | None:
        """
        None   → kein gespeichertes Profil, globales Profil gilt
        str    → Profil-ID für diesen Agent (überschreibt globales Profil)
        """
        config = await self.get_config(agent_id)
        return config.get("safeguard_profile", None)

    async def set_profile(self, agent_id: str, profile_id: str) -> None:
        await self.set_config(agent_id, "safeguard_profile", profile_id)
        logger.info(
            "[AgentConfigStore] Agent '%s' safeguard_profile='%s' gespeichert.",
            agent_id, profile_id,
        )

    async def clear_profile(self, agent_id: str) -> None:
        """Entfernt die per-Agent Profil-Überschreibung (Fallback auf globales Profil)."""
        await self._mutate(agent_id, lambda config: config.pop("safeguard_profile", None))
        logger.info("[AgentConfigStore] Agent '%s' safeguard_profile zurückgesetzt.", agent_id)

    # ── Safeguard Custom Classifier Policy (pro Agent) ────────────────────────

    async def get_classifier_policy(self, agent_id: str) -> str | None:
        """
        Returns the custom safeguard classifier policy for this agent, or None.
        The policy text is injected into the LLM classifier system prompt
        to enforce agent-specific safety rules (e.g. stricter Proxmox rules).
        """
        config = await self.get_config(agent_id)
        return config.get("safeguard_classifier_policy", None)

    async def set_classifier_policy(self, agent_id: str, policy: str) -> None:
        """Set a custom safeguard classifier policy for this agent."""
        await self.set_config(agent_id, "safeguard_classifier_policy", policy)
        logger.info(
            "[AgentConfigStore] Agent '%s' safeguard_classifier_policy updated (%d chars).",
            agent_id, len(policy),
        )

    async def clear_classifier_policy(self, agent_id: str) -> None:
        """Remove the custom classifier policy (falls back to global default)."""
        await self._mutate(
            agent_id, lambda config: config.pop("safeguard_classifier_policy", None)
        )
        logger.info("[AgentConfigStore] Agent '%s' safeguard_classifier_policy cleared.", agent_id)
