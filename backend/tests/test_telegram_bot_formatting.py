"""Regression tests for Telegram bot response cleanup helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_BOT_PATH = Path(__file__).resolve().parents[1] / "modules_catalog" / "telegram" / "bot.py"

_STUB_NAMES = (
    "core",
    "core.redis_client",
    "agents",
    "agents.base_agent",
    "core.safeguard",
    "fastapi",
    "telegram_bot.formatter",
    "telegram_bot",
)


def _install_stubs() -> None:
    """Inject minimal stub modules so the bot module can be loaded without
    booting FastAPI/Redis/LLM. The originals are saved on the
    ``_telegram_bot_orig_modules`` dict for the fixture to restore later."""
    if "core" not in sys.modules:
        sys.modules["core"] = types.ModuleType("core")
    if "core.redis_client" not in sys.modules:
        rc = types.ModuleType("core.redis_client")
        rc.get_redis = lambda: None
        sys.modules["core.redis_client"] = rc
    if "agents" not in sys.modules:
        sys.modules["agents"] = types.ModuleType("agents")
    if "agents.base_agent" not in sys.modules:
        ba = types.ModuleType("agents.base_agent")
        ba._t = lambda de, en=None, **_: de
        ba._TOOL_SAFEGUARD_SENTINEL = "__TOOL_SAFEGUARD__"
        sys.modules["agents.base_agent"] = ba
    if "core.safeguard" not in sys.modules:
        sg = types.ModuleType("core.safeguard")
        sg.SAFEGUARD_PENDING_KEY = "ninko:safeguard_pending:{session_id}"
        sys.modules["core.safeguard"] = sg
    if "fastapi" not in sys.modules:
        fa = types.ModuleType("fastapi")
        fa.FastAPI = type("FastAPI", (), {})
        sys.modules["fastapi"] = fa
    if "telegram_bot.formatter" not in sys.modules:
        fmt = types.ModuleType("telegram_bot.formatter")
        fmt.format_for_telegram = lambda text: text
        sys.modules["telegram_bot.formatter"] = fmt


@pytest.fixture
def telegram_bot():
    """Load the telegram bot module behind minimal stubs and yield it. The
    fixture saves the prior ``sys.modules`` entries for any modules it has to
    add so they are restored on teardown — keeping the stubs out of other
    test files that share the same interpreter."""
    _install_stubs()
    original_bot = sys.modules.get("telegram_bot")
    spec = importlib.util.spec_from_file_location(
        "telegram_bot",
        _BOT_PATH,
        submodule_search_locations=[str(_BOT_PATH.parent)],
    )
    assert spec and spec.loader
    bot = importlib.util.module_from_spec(spec)
    sys.modules["telegram_bot"] = bot
    spec.loader.exec_module(bot)
    try:
        yield bot
    finally:
        if original_bot is None:
            sys.modules.pop("telegram_bot", None)
        else:
            sys.modules["telegram_bot"] = original_bot


def test_strip_pipeline_headers_removes_module_footer(telegram_bot) -> None:
    response = "Cluster sieht gesund aus.\n\n_via kubernetes_"

    assert telegram_bot._strip_pipeline_headers(response) == "Cluster sieht gesund aus."


def test_plain_preview_text_removes_markdown_and_footer(telegram_bot) -> None:
    response = "**Proxmox Status**\n\n| `VMID` | **Name** |\n| --- | --- |\n| 100 | pve |\n\n_via proxmox_"

    preview = telegram_bot._plain_preview_text(response)

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
async def test_callback_confirm_yes_consumes_pending_atomically(
    telegram_bot, monkeypatch
) -> None:
    session_id = "telegram_123"
    fake_redis = _FakeRedis(
        {"ninko:safeguard_pending:telegram_123": "find tasmota devices"}
    )
    monkeypatch.setattr(telegram_bot, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _FakeAsyncClient)

    app = types.SimpleNamespace(
        state=types.SimpleNamespace(
            orchestrator=types.SimpleNamespace(
                route=AsyncMock(
                    return_value=(
                        "done",
                        "fritzbox",
                        False,
                        {"compaction_summary": None, "routing_confidence": 0.9, "tier_used": 1},
                    )
                )
            )
        )
    )
    bot = telegram_bot.TelegramBot(app)
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
async def test_callback_confirm_yes_ignores_stale_button(
    telegram_bot, monkeypatch
) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(telegram_bot, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _FakeAsyncClient)

    app = types.SimpleNamespace(state=types.SimpleNamespace(orchestrator=types.SimpleNamespace()))
    bot = telegram_bot.TelegramBot(app)
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
