"""
Ninko Routing-Telemetrie (R12) – A/B-Correction-Tracking und Soft-Learning.

Erkennt Routing-Korrekturen (force_module nach Auto-Routing mit anderem Modul)
und leitet Korrekturbeispiele an den EmbeddingRouter weiter, damit das TF-IDF-
Fallback-Ranking für ähnliche zukünftige Anfragen besser wird.

Redis-Keys:
  ninko:routing:last_auto:{session_id}  – letztes Auto-Routing-Ergebnis (TTL 30 min)
  ninko:routing:corrections:log         – Liste letzter 500 Korrekturen (LPUSH/LTRIM)
  ninko:routing:corrections:stats       – Hash "{from}→{to}" → Anzahl
  ninko:routing:correction_msgs:{module} – Liste letzter 20 Korrektur-Nachrichten
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.redis_client import RedisClient

logger = logging.getLogger(__name__)

_LAST_AUTO_PREFIX = "ninko:routing:last_auto:"
_CORRECTIONS_LOG = "ninko:routing:corrections:log"
_CORRECTIONS_STATS = "ninko:routing:corrections:stats"
_CORRECTIONS_MSGS_PREFIX = "ninko:routing:correction_msgs:"

_LAST_AUTO_TTL = 1800     # 30 Minuten
_MAX_LOG_ENTRIES = 500
_MAX_MSG_EXAMPLES = 20


class RoutingTelemetry:
    """Erfasst Auto-Routing-Ergebnisse und erkennt User-Korrekturen via force_module."""

    def __init__(self, redis: "RedisClient") -> None:
        self._redis = redis

    # ── Auto-Routing-Ergebnis speichern ──────────────────────────────────────

    async def record_auto_routing(
        self,
        session_id: str,
        module: str,
        tier: int,
        confidence: float | None,
        message: str,
    ) -> None:
        """Speichert das letzte Auto-Routing-Ergebnis dieser Session (TTL 30 min)."""
        key = f"{_LAST_AUTO_PREFIX}{session_id}"
        msg_hash = hashlib.sha256(message.encode()).hexdigest()[:16]
        data = json.dumps(
            {
                "module": module,
                "tier": tier,
                "confidence": confidence,
                "msg_hash": msg_hash,
            }
        )
        await self._redis.connection.set(key, data, ex=_LAST_AUTO_TTL)

    # ── Korrektur erkennen und speichern ─────────────────────────────────────

    async def check_and_record_correction(
        self,
        session_id: str,
        force_module: str,
        message: str,
    ) -> dict | None:
        """Prüft ob force_module das letzte Auto-Routing korrigiert.

        Gibt das Korrektur-Dict zurück oder None (kein Auto-Routing-Ergebnis
        vorhanden, oder force_module stimmt mit Auto-Routing überein).
        """
        key = f"{_LAST_AUTO_PREFIX}{session_id}"
        raw = await self._redis.connection.get(key)
        if not raw:
            return None
        await self._redis.connection.delete(key)
        try:
            last_auto = json.loads(raw)
        except json.JSONDecodeError:
            return None

        from_module = last_auto.get("module")
        if not from_module or from_module == force_module:
            return None

        msg_hash = hashlib.sha256(message.encode()).hexdigest()[:16]
        if last_auto.get("msg_hash") != msg_hash:
            return None

        correction = {
            "ts": int(time.time()),
            "session": session_id[:16],
            "from": from_module,
            "to": force_module,
            "tier": last_auto.get("tier"),
            "confidence": last_auto.get("confidence"),
            "msg_hash": msg_hash,
        }
        await self._store_correction(correction, message[:200])
        logger.info(
            "Routing-Korrektur erkannt: %s → %s (Tier %s, conf=%s)",
            from_module,
            force_module,
            last_auto.get("tier"),
            last_auto.get("confidence"),
        )
        return correction

    async def _store_correction(self, correction: dict, message_for_learning: str) -> None:
        try:
            r = self._redis.connection
            await r.lpush(_CORRECTIONS_LOG, json.dumps(correction))
            await r.ltrim(_CORRECTIONS_LOG, 0, _MAX_LOG_ENTRIES - 1)
            stats_key = f"{correction['from']}→{correction['to']}"
            await r.hincrby(_CORRECTIONS_STATS, stats_key, 1)
            msgs_key = f"{_CORRECTIONS_MSGS_PREFIX}{correction['to']}"
            await r.lpush(msgs_key, message_for_learning)
            await r.ltrim(msgs_key, 0, _MAX_MSG_EXAMPLES - 1)
        except Exception as exc:
            logger.warning("RoutingTelemetry: Korrektur konnte nicht gespeichert werden: %s", exc)

    # ── Stats-Abfrage ─────────────────────────────────────────────────────────

    async def get_stats(self) -> dict:
        """Gibt Korrektur-Statistiken zurück (für Admin-API)."""
        r = self._redis.connection
        raw_stats = await r.hgetall(_CORRECTIONS_STATS)
        by_pair = {k: int(v) for k, v in raw_stats.items()}
        log_raw = await r.lrange(_CORRECTIONS_LOG, 0, 49)
        recent = []
        for entry in log_raw:
            try:
                recent.append(json.loads(entry))
            except json.JSONDecodeError:
                pass
        return {
            "total": sum(by_pair.values()),
            "by_pair": by_pair,
            "recent": recent,
        }

    async def get_correction_examples(self, module: str) -> list[str]:
        """Gibt Nachrichten zurück, die zum Modul korrigiert wurden (für Soft-Learning)."""
        key = f"{_CORRECTIONS_MSGS_PREFIX}{module}"
        return await self._redis.connection.lrange(key, 0, _MAX_MSG_EXAMPLES - 1)

    async def reset_stats(self) -> None:
        """Setzt Korrektur-Log, Statistiken und Korrektur-Beispiele zurück (Admin-Aktion)."""
        r = self._redis.connection
        await r.delete(_CORRECTIONS_LOG, _CORRECTIONS_STATS)
        msg_keys = [key async for key in r.scan_iter(f"{_CORRECTIONS_MSGS_PREFIX}*")]
        if msg_keys:
            await r.delete(*msg_keys)


# ── Singleton ─────────────────────────────────────────────────────────────────

_telemetry: RoutingTelemetry | None = None


def get_routing_telemetry() -> RoutingTelemetry | None:
    return _telemetry


def init_routing_telemetry(redis: "RedisClient") -> RoutingTelemetry:
    global _telemetry
    _telemetry = RoutingTelemetry(redis)
    return _telemetry
