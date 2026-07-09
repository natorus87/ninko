"""
API-Tests für die Background-Settings-Endpoints in api/routes_settings.py.
Redis wird gemockt — getestet werden Defaults, Roundtrip, Validierung und Reset.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import routes_settings
from api.routes_settings import router


@pytest.fixture
def redis_mock():
    redis = MagicMock()
    redis.connection.get = AsyncMock(return_value=None)
    redis.connection.set = AsyncMock()
    return redis


@pytest.fixture
def client(redis_mock):
    app = FastAPI()
    app.include_router(router)
    with patch.object(routes_settings, "get_redis", return_value=redis_mock):
        yield TestClient(app)


def test_get_background_returns_defaults_without_redis_entry(client):
    res = client.get("/api/settings/background")
    assert res.status_code == 200
    data = res.json()
    assert data["preset"] == "default"
    assert data["tint"] == "#070b24"
    assert data["accent1"] == "#6d28d9"
    assert data["accent2"] == "#007aff"
    assert data["source"] == "default"


def test_get_background_returns_stored_values(client, redis_mock):
    stored = {"preset": "ocean", "tint": "#041526", "accent1": "#0891b2", "accent2": "#38bdf8"}
    redis_mock.connection.get = AsyncMock(return_value=json.dumps(stored))
    res = client.get("/api/settings/background")
    assert res.status_code == 200
    data = res.json()
    assert data["preset"] == "ocean"
    assert data["tint"] == "#041526"
    assert data["source"] == "redis"


def test_put_background_persists_payload(client, redis_mock):
    body = {"preset": "custom", "tint": "#101020", "accent1": "#ff0000", "accent2": "#00ff00"}
    res = client.put("/api/settings/background", json=body)
    assert res.status_code == 200
    assert res.json()["preset"] == "custom"
    redis_mock.connection.set.assert_awaited_once()
    key, raw = redis_mock.connection.set.await_args.args
    assert key == routes_settings.REDIS_KEY_BACKGROUND
    assert json.loads(raw)["accent1"] == "#ff0000"


@pytest.mark.parametrize(
    "field,value",
    [
        ("tint", "070b24"),          # ohne '#'
        ("tint", "#07b2"),           # zu kurz
        ("accent1", "#gg0000"),      # keine Hex-Zeichen
        ("accent2", "red"),          # Farbname statt Hex
        ("preset", "Bad Preset!"),   # ungültige Preset-ID
    ],
)
def test_put_background_rejects_invalid_values(client, field, value):
    body = {"preset": "custom", "tint": "#101020", "accent1": "#ff0000", "accent2": "#00ff00"}
    body[field] = value
    res = client.put("/api/settings/background", json=body)
    assert res.status_code == 422


def test_reset_background_writes_defaults(client, redis_mock):
    res = client.post("/api/settings/background/reset")
    assert res.status_code == 200
    data = res.json()
    assert data["preset"] == "default"
    assert data["tint"] == "#070b24"
    key, raw = redis_mock.connection.set.await_args.args
    assert key == routes_settings.REDIS_KEY_BACKGROUND
    assert json.loads(raw)["preset"] == "default"
