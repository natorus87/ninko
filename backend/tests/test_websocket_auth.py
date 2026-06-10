from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import auth as auth_module


class _FakeWebSocket:
    def __init__(self, session_token: str) -> None:
        self.headers = {}
        self.cookies = {"ninko_session": session_token}
        self.query_params = {}


class _FakeTokenWebSocket:
    def __init__(self, api_token: str) -> None:
        self.headers = {"Authorization": f"Bearer {api_token}"}
        self.cookies = {}
        self.query_params = {}


@pytest.mark.asyncio
async def test_websocket_auth_rejects_blacklisted_session(monkeypatch) -> None:
    settings = SimpleNamespace(
        API_AUTH_ENABLED=True,
        SESSION_SECRET="x" * 32,
        SESSION_TTL_HOURS=24,
        SESSION_COOKIE_NAME="ninko_session",
    )
    monkeypatch.setattr(auth_module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_module, "_is_token_blacklisted", AsyncMock(return_value=True))

    token = auth_module.create_session_token("alice", role=auth_module.ROLE_READ)
    role = await auth_module.resolve_websocket_role_async(_FakeWebSocket(token))

    assert role is None


@pytest.mark.asyncio
async def test_websocket_auth_accepts_active_session(monkeypatch) -> None:
    settings = SimpleNamespace(
        API_AUTH_ENABLED=True,
        SESSION_SECRET="x" * 32,
        SESSION_TTL_HOURS=24,
        SESSION_COOKIE_NAME="ninko_session",
    )
    monkeypatch.setattr(auth_module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_module, "_is_token_blacklisted", AsyncMock(return_value=False))

    token = auth_module.create_session_token("alice", role=auth_module.ROLE_READ)
    role = await auth_module.resolve_websocket_role_async(_FakeWebSocket(token))

    assert role == auth_module.ROLE_READ


@pytest.mark.asyncio
async def test_websocket_auth_rejects_revoked_api_token(monkeypatch) -> None:
    """Regression: revoked user API tokens must not stay valid over WebSocket."""
    settings = SimpleNamespace(
        API_AUTH_ENABLED=True,
        SESSION_SECRET="x" * 32,
        SESSION_TTL_HOURS=24,
        SESSION_COOKIE_NAME="ninko_session",
        API_KEY_ADMIN="",
        API_KEY_WRITE="",
        API_KEY_READ="",
    )
    monkeypatch.setattr(auth_module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_module, "is_active_api_token", AsyncMock(return_value=False))

    token = auth_module.create_api_access_token("alice", role=auth_module.ROLE_WRITE)
    role = await auth_module.resolve_websocket_role_async(_FakeTokenWebSocket(token))

    assert role is None


@pytest.mark.asyncio
async def test_websocket_auth_accepts_active_api_token(monkeypatch) -> None:
    settings = SimpleNamespace(
        API_AUTH_ENABLED=True,
        SESSION_SECRET="x" * 32,
        SESSION_TTL_HOURS=24,
        SESSION_COOKIE_NAME="ninko_session",
        API_KEY_ADMIN="",
        API_KEY_WRITE="",
        API_KEY_READ="",
    )
    monkeypatch.setattr(auth_module, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_module, "is_active_api_token", AsyncMock(return_value=True))

    token = auth_module.create_api_access_token("alice", role=auth_module.ROLE_WRITE)
    role = await auth_module.resolve_websocket_role_async(_FakeTokenWebSocket(token))

    assert role == auth_module.ROLE_WRITE
