from __future__ import annotations

import importlib.util
from pathlib import Path

import httpx
import pytest

from core.auth import reset_current_tenant_id, set_current_tenant_id
from core.connections import ConnectionManager


MANIFEST_PATH = (
    Path(__file__).resolve().parents[1] / "modules_catalog" / "tasmota" / "manifest.py"
)
SPEC = importlib.util.spec_from_file_location("tasmota_manifest_for_test", MANIFEST_PATH)
assert SPEC is not None
tasmota_manifest = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(tasmota_manifest)


class _FakeResponse:
    status_code = 200


class _FakeAsyncClient:
    seen_urls: list[str] = []

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def get(self, url: str) -> _FakeResponse:
        self.seen_urls.append(url)
        return _FakeResponse()


def test_connection_manager_prefers_auth_tenant_context() -> None:
    token = set_current_tenant_id("customer-a")
    try:
        assert ConnectionManager._effective_tenant_id() == "customer-a"
    finally:
        reset_current_tenant_id(token)


@pytest.mark.asyncio
async def test_tasmota_health_uses_env_fallback_and_normalizes_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeAsyncClient.seen_urls = []

    async def no_default_connection(module_id: str, tenant_id: str = "") -> None:
        return None

    monkeypatch.setenv("TASMOTA_HOST", "http://tasmota-01.local/")
    monkeypatch.setattr(
        "core.connections.ConnectionManager.get_default_connection",
        no_default_connection,
    )
    monkeypatch.setattr(tasmota_manifest.httpx, "AsyncClient", _FakeAsyncClient)

    result = await tasmota_manifest.check_tasmota_health()

    assert result["status"] == "ok"
    assert "env" in result["detail"]
    assert _FakeAsyncClient.seen_urls == [
        "http://tasmota-01.local/cm?cmnd=Status"
    ]


@pytest.mark.asyncio
async def test_tasmota_health_returns_controlled_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingAsyncClient(_FakeAsyncClient):
        async def get(self, url: str) -> _FakeResponse:
            raise httpx.ConnectError("connection failed")

    async def no_default_connection(module_id: str, tenant_id: str = "") -> None:
        return None

    monkeypatch.setenv("TASMOTA_HOST", "tasmota-01.local")
    monkeypatch.setattr(
        "core.connections.ConnectionManager.get_default_connection",
        no_default_connection,
    )
    monkeypatch.setattr(tasmota_manifest.httpx, "AsyncClient", FailingAsyncClient)

    result = await tasmota_manifest.check_tasmota_health()

    assert result == {"status": "error", "detail": "connection failed"}
