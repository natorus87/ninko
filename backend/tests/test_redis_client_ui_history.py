"""Regression tests for RedisClient.ui_history_clear_all().

"Clear all chat history" must keep pinned entries — verified directly
against the redis_client method since the route-level test only checks
that the right method gets called, not what it does internally.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from core.redis_client import RedisClient


def _make_client(hash_data: dict[str, str]) -> RedisClient:
    client = RedisClient.__new__(RedisClient)
    client._redis = AsyncMock()
    client.hgetall_paginated = AsyncMock(return_value=hash_data)
    return client


async def test_ui_history_clear_all_keeps_pinned_entries() -> None:
    hash_data = {
        "conv-pinned": json.dumps({"id": "conv-pinned", "pinned": True}),
        "conv-unpinned-1": json.dumps({"id": "conv-unpinned-1", "pinned": False}),
        "conv-unpinned-2": json.dumps({"id": "conv-unpinned-2"}),  # no pinned key -> falsy
    }
    client = _make_client(hash_data)

    await client.ui_history_clear_all(tenant_id="default")

    client._redis.hdel.assert_awaited_once()
    key, *deleted_ids = client._redis.hdel.await_args.args
    assert key == "ninko:ui:history:default"
    assert set(deleted_ids) == {"conv-unpinned-1", "conv-unpinned-2"}


async def test_ui_history_clear_all_purges_malformed_entries() -> None:
    hash_data = {"broken": "not-json"}
    client = _make_client(hash_data)

    await client.ui_history_clear_all(tenant_id="default")

    client._redis.hdel.assert_awaited_once_with("ninko:ui:history:default", "broken")


async def test_ui_history_clear_all_noop_when_everything_pinned() -> None:
    hash_data = {"conv-1": json.dumps({"id": "conv-1", "pinned": True})}
    client = _make_client(hash_data)

    await client.ui_history_clear_all(tenant_id="default")

    client._redis.hdel.assert_not_awaited()


async def test_ui_history_clear_all_noop_when_history_empty() -> None:
    client = _make_client({})

    await client.ui_history_clear_all(tenant_id="default")

    client._redis.hdel.assert_not_awaited()
