"""Regression tests for Telegram bot response cleanup helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_BOT_PATH = Path(__file__).resolve().parents[1] / "modules_catalog" / "telegram" / "bot.py"

sys.modules.setdefault("core", types.ModuleType("core"))
redis_client = types.ModuleType("core.redis_client")
redis_client.get_redis = lambda: None
sys.modules["core.redis_client"] = redis_client

agents = types.ModuleType("agents")
base_agent = types.ModuleType("agents.base_agent")
base_agent._t = lambda de, en=None, **_: de
base_agent._TOOL_SAFEGUARD_SENTINEL = "__TOOL_SAFEGUARD__"
sys.modules.setdefault("agents", agents)
sys.modules["agents.base_agent"] = base_agent

safeguard = types.ModuleType("core.safeguard")
safeguard.SAFEGUARD_PENDING_KEY = "ninko:safeguard_pending:{session_id}"
sys.modules["core.safeguard"] = safeguard

fastapi = types.ModuleType("fastapi")
fastapi.FastAPI = type("FastAPI", (), {})
sys.modules["fastapi"] = fastapi

formatter = types.ModuleType("telegram_bot_formatter")
formatter.format_for_telegram = lambda text: text
sys.modules["telegram_bot.formatter"] = formatter

_SPEC = importlib.util.spec_from_file_location(
    "telegram_bot",
    _BOT_PATH,
    submodule_search_locations=[str(_BOT_PATH.parent)],
)
assert _SPEC and _SPEC.loader
_BOT = importlib.util.module_from_spec(_SPEC)
sys.modules["telegram_bot"] = _BOT
_SPEC.loader.exec_module(_BOT)
_strip_pipeline_headers = _BOT._strip_pipeline_headers
_plain_preview_text = _BOT._plain_preview_text
TelegramBot = _BOT.TelegramBot


def test_strip_pipeline_headers_removes_module_footer() -> None:
    response = "Cluster sieht gesund aus.\n\n_via kubernetes_"

    assert _strip_pipeline_headers(response) == "Cluster sieht gesund aus."


def test_plain_preview_text_removes_markdown_and_footer() -> None:
    response = "**Proxmox Status**\n\n| `VMID` | **Name** |\n| --- | --- |\n| 100 | pve |\n\n_via proxmox_"

    preview = _plain_preview_text(response)

    assert "**" not in preview
    assert "`" not in preview
    assert "_via proxmox_" not in preview
    assert "Proxmox Status" in preview


class _FakeRedisConnection:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = values or {}
        self.deleted: list[str] = []

    async def execute_command(self, command: str, key: str) -> str | None:
        assert command == "GETDEL"
        value = self.values.get(key)
        self.values.pop(key, None)
        return value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


class _FakeRedis:
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.connection = _FakeRedisConnection(values)
        self.messages: list[tuple[str, str, str]] = []

    async def get_chat_history(self, session_id: str) -> list[dict]:
        return []

    async def store_chat_message(self, *, session_id: str, role: str, content: str) -> None:
        self.messages.append((session_id, role, content))


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def post(self, *args, **kwargs):
        class _Response:
            status_code = 200

            def json(self):
                return {"ok": True}

        return _Response()


@pytest.mark.asyncio
async def test_callback_confirm_yes_consumes_pending_atomically(monkeypatch) -> None:
    session_id = "telegram_123"
    fake_redis = _FakeRedis(
        {"ninko:safeguard_pending:telegram_123": "find tasmota devices"}
    )
    monkeypatch.setattr(_BOT, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(_BOT.httpx, "AsyncClient", _FakeAsyncClient)

    app = types.SimpleNamespace(
        state=types.SimpleNamespace(
            orchestrator=types.SimpleNamespace(
                route=AsyncMock(return_value=("done", "fritzbox", False))
            )
        )
    )
    bot = TelegramBot(app)
    bot._keep_typing = AsyncMock()
    bot._send = AsyncMock(return_value=True)

    await bot._handle_callback_query(
        {
            "id": "cb-1",
            "data": "confirm_yes",
            "message": {"chat": {"id": 123}},
        },
        "token",
    )

    assert fake_redis.connection.values == {}
    app.state.orchestrator.route.assert_awaited_once()
    assert fake_redis.messages[-2:] == [
        (session_id, "user", "find tasmota devices"),
        (session_id, "assistant", "done"),
    ]


@pytest.mark.asyncio
async def test_callback_confirm_yes_ignores_stale_button(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(_BOT, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(_BOT.httpx, "AsyncClient", _FakeAsyncClient)

    app = types.SimpleNamespace(state=types.SimpleNamespace(orchestrator=types.SimpleNamespace()))
    bot = TelegramBot(app)
    bot._send = AsyncMock(return_value=True)

    await bot._handle_callback_query(
        {
            "id": "cb-1",
            "data": "confirm_yes",
            "message": {"chat": {"id": 123}},
        },
        "token",
    )

    bot._send.assert_not_awaited()
