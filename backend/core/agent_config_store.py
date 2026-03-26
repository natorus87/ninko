"""
AgentConfigStore — persistiert per-Agent Settings in Redis.
Nutzt einen Hash-Key: ninko:agent_configs
  Field: agent_id
  Value: JSON-String, z.B. '{"safeguard_enabled": true}'

Kein Schema-Migration nötig — Redis-Hash wächst dynamisch.
"""

import json
import logging

logger = logging.getLogger("ninko.core.agent_config_store")

REDIS_KEY = "ninko:agent_configs"


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

    async def set_config(self, agent_id: str, key: str, value) -> None:
        from core.redis_client import get_redis
        config = await self.get_config(agent_id)
        config[key] = value
        redis = get_redis()
        await redis.connection.hset(REDIS_KEY, agent_id, json.dumps(config))

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
