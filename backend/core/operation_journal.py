"""
Operation Journal for state-changing and destructive actions.

Stores transaction-style operation entries in Redis so operators can:
- trace pending/confirmed/executed operations
- attach rollback notes and restore hints
- document rollback execution
"""

from __future__ import annotations

import json
import time
import uuid

from core.redis_client import get_redis

_STATUS_PENDING = "pending_confirmation"
_STATUS_CONFIRMED = "confirmed"
_STATUS_EXECUTED = "executed"
_STATUS_FAILED = "failed"
_STATUS_ROLLED_BACK = "rolled_back"

_TX_HASH_PREFIX = "ninko:ops:tx:"
_TX_INDEX_KEY = "ninko:ops:tx:index"
_TX_SESSION_PENDING_PREFIX = "ninko:ops:pending:"
_MAX_TX_INDEX = 5000
_TX_TTL_SECONDS = 60 * 60 * 24 * 14  # 14 days


class OperationJournal:
    """Redis-backed transaction journal for risky operations."""

    async def create_pending(
        self,
        *,
        session_id: str,
        text: str,
        category: str,
        rationale: str,
        source: str,
        module: str | None = None,
        tool_name: str | None = None,
    ) -> str:
        tx_id = uuid.uuid4().hex
        now = time.time()
        entry = {
            "id": tx_id,
            "timestamp": now,
            "updated_at": now,
            "status": _STATUS_PENDING,
            "session_id": session_id,
            "source": source,
            "category": category,
            "module": module or "",
            "tool_name": tool_name or "",
            "text": text[:2000],
            "rationale": rationale[:600],
            "rollback_required": "true" if category == "DESTRUCTIVE" else "false",
            "rollback_hint": (
                "Create snapshot/backup before execution and document restore command."
            ),
            "rollback_notes": "",
            "result_summary": "",
            "error": "",
        }
        await self._store(entry)
        redis = get_redis()
        await redis.connection.set(
            f"{_TX_SESSION_PENDING_PREFIX}{session_id}", tx_id, ex=60 * 60 * 24
        )
        return tx_id

    async def get_pending_for_session(self, session_id: str) -> str | None:
        redis = get_redis()
        tx_id = await redis.connection.get(f"{_TX_SESSION_PENDING_PREFIX}{session_id}")
        return tx_id or None

    async def clear_pending_for_session(self, session_id: str) -> None:
        redis = get_redis()
        await redis.connection.delete(f"{_TX_SESSION_PENDING_PREFIX}{session_id}")

    async def mark_confirmed(self, tx_id: str) -> None:
        await self._update(tx_id, {"status": _STATUS_CONFIRMED})

    async def mark_executed(self, tx_id: str, *, module: str | None, summary: str) -> None:
        await self._update(
            tx_id,
            {
                "status": _STATUS_EXECUTED,
                "module": module or "",
                "result_summary": (summary or "")[:1200],
            },
        )

    async def mark_failed(self, tx_id: str, *, error: str) -> None:
        await self._update(
            tx_id,
            {
                "status": _STATUS_FAILED,
                "error": (error or "")[:1200],
            },
        )

    async def add_rollback_note(self, tx_id: str, note: str) -> None:
        data = await self.get(tx_id)
        old = data.get("rollback_notes", "") if data else ""
        merged = f"{old}\n{note}".strip() if old else note.strip()
        await self._update(tx_id, {"rollback_notes": merged[:4000]})

    async def mark_rolled_back(self, tx_id: str, note: str = "") -> None:
        patch = {"status": _STATUS_ROLLED_BACK}
        if note.strip():
            patch["rollback_notes"] = note.strip()[:4000]
        await self._update(tx_id, patch)

    async def get(self, tx_id: str) -> dict:
        redis = get_redis()
        raw = await redis.connection.hgetall(f"{_TX_HASH_PREFIX}{tx_id}")
        if not raw:
            return {}
        return raw

    async def list(
        self,
        *,
        limit: int = 100,
        status: str = "",
        session_id: str = "",
        category: str = "",
    ) -> list[dict]:
        redis = get_redis()
        ids = await redis.connection.lrange(_TX_INDEX_KEY, 0, max(0, limit * 4 - 1))
        out: list[dict] = []
        for tx_id in ids:
            item = await self.get(tx_id)
            if not item:
                continue
            if status and item.get("status") != status:
                continue
            if session_id and item.get("session_id") != session_id:
                continue
            if category and item.get("category") != category:
                continue
            out.append(item)
            if len(out) >= limit:
                break
        return out

    async def _store(self, entry: dict) -> None:
        redis = get_redis()
        tx_id = entry["id"]
        tx_key = f"{_TX_HASH_PREFIX}{tx_id}"
        await redis.connection.hset(tx_key, mapping=entry)
        await redis.connection.expire(tx_key, _TX_TTL_SECONDS)
        pipe = redis.connection.pipeline()
        pipe.lpush(_TX_INDEX_KEY, tx_id)
        pipe.ltrim(_TX_INDEX_KEY, 0, _MAX_TX_INDEX - 1)
        pipe.expire(_TX_INDEX_KEY, _TX_TTL_SECONDS)
        await pipe.execute()

    async def _update(self, tx_id: str, patch: dict) -> None:
        redis = get_redis()
        tx_key = f"{_TX_HASH_PREFIX}{tx_id}"
        exists = await redis.connection.exists(tx_key)
        if not exists:
            return
        mapping = {**patch, "updated_at": str(time.time())}
        await redis.connection.hset(tx_key, mapping=mapping)
        await redis.connection.expire(tx_key, _TX_TTL_SECONDS)


_operation_journal: OperationJournal | None = None


def get_operation_journal() -> OperationJournal:
    global _operation_journal
    if _operation_journal is None:
        _operation_journal = OperationJournal()
    return _operation_journal
