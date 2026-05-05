"""Helpers for constructing evidence traces."""

from __future__ import annotations

import json
import logging

from core.evidence.schemas import ConstellationResult, EvidenceTrace, FieldResolution

logger = logging.getLogger("ninko.evidence")

_EVIDENCE_KEY_PREFIX = "ninko:audit:evidence"
_EVIDENCE_MAX_PER_DAY = 10_000
_EVIDENCE_RETENTION_DAYS = 7


def build_evidence_trace(
    session_id: str,
    turn_id: str,
    resolutions: list[FieldResolution],
    constellation: ConstellationResult,
    escalation_reason: str | None = None,
) -> EvidenceTrace:
    """Build a ready/not-ready EvidenceTrace from resolver and validator output."""
    unresolved = [
        resolution.term
        for resolution in resolutions
        if resolution.confidence == "unresolved"
    ]
    reason = escalation_reason
    if unresolved and reason is None:
        reason = "Unresolved semantic terms: " + ", ".join(unresolved)
    ready = not reason and not constellation.contradictions and constellation.confidence >= 0.6
    return EvidenceTrace(
        session_id=session_id,
        turn_id=turn_id,
        resolutions=resolutions,
        constellation=constellation,
        ready_for_synthesis=ready,
        escalation_reason=reason,
    )


async def persist_evidence_trace(trace: EvidenceTrace) -> None:
    """Persistiert einen EvidenceTrace in Redis (fire-and-forget).

    Key-Schema: ninko:audit:evidence:YYYY-MM-DD
    TTL: 7 Tage, max 10k Einträge/Tag (identisch zum Tool-Audit-Pattern).
    """
    try:
        from datetime import datetime, timezone
        from core.redis_client import get_redis

        redis = get_redis()
        if redis is None:
            logger.debug("Redis nicht verfügbar – EvidenceTrace nicht persistiert")
            return

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{_EVIDENCE_KEY_PREFIX}:{date_str}"

        payload = json.dumps(trace.model_dump(), default=str)
        pipe = redis.connection.pipeline()
        pipe.lpush(key, payload)
        pipe.ltrim(key, 0, _EVIDENCE_MAX_PER_DAY - 1)
        pipe.expire(key, _EVIDENCE_RETENTION_DAYS * 86400)
        await pipe.execute()

        logger.debug("EvidenceTrace persistiert: session=%s turn=%s", trace.session_id, trace.turn_id)
    except Exception as exc:
        logger.debug("EvidenceTrace-Persistenz fehlgeschlagen: %s", exc)
