"""API tests for the UI chat-history endpoints in api/routes_chat.py.

Covers the "clear entire history" route and the pinned-entry roundtrip,
both added alongside the sidebar pin/delete-all UI feature.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import routes_chat


@pytest.fixture
def redis_mock():
    redis = MagicMock()
    redis.ui_history_get_all = AsyncMock(return_value=[])
    redis.ui_history_save = AsyncMock(return_value=True)
    redis.ui_history_delete = AsyncMock(return_value=True)
    redis.ui_history_clear_all = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def client(redis_mock, monkeypatch):
    app = FastAPI()
    app.include_router(routes_chat.router)
    monkeypatch.setattr(routes_chat, "get_redis", lambda: redis_mock)
    monkeypatch.setattr(
        routes_chat,
        "resolve_request_auth",
        lambda request: {"tenant_id": "default", "username": "test"},
    )
    monkeypatch.setattr(routes_chat, "auth_tenant_id", lambda ctx: "default")
    return TestClient(app)


def test_delete_all_ui_history_delegates_to_clear_all(client, redis_mock):
    res = client.delete("/api/chat/ui-history")

    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    redis_mock.ui_history_clear_all.assert_awaited_once_with(tenant_id="default")


def test_delete_all_ui_history_does_not_touch_single_entry_route(client, redis_mock):
    """Regression: DELETE /ui-history (no id) must not be shadowed by or
    shadow DELETE /ui-history/{conv_id} — they are distinct routes."""
    res = client.delete("/api/chat/ui-history/some-conv-id")

    assert res.status_code == 200
    redis_mock.ui_history_delete.assert_awaited_once_with("some-conv-id", tenant_id="default")
    redis_mock.ui_history_clear_all.assert_not_awaited()


def test_save_ui_history_roundtrips_pinned_flag(client, redis_mock):
    body = {
        "id": "conv-1",
        "title": "Test",
        "messages": [],
        "createdAt": 1.0,
        "updatedAt": 2.0,
        "pinned": True,
    }
    res = client.post("/api/chat/ui-history", json=body)

    assert res.status_code == 200
    redis_mock.ui_history_save.assert_awaited_once()
    saved_conversation = redis_mock.ui_history_save.await_args.args[0]
    assert saved_conversation["pinned"] is True


def test_save_ui_history_defaults_pinned_to_false(client, redis_mock):
    body = {"id": "conv-2", "title": "Test", "messages": [], "createdAt": 1.0, "updatedAt": 2.0}
    res = client.post("/api/chat/ui-history", json=body)

    assert res.status_code == 200
    saved_conversation = redis_mock.ui_history_save.await_args.args[0]
    assert saved_conversation["pinned"] is False
