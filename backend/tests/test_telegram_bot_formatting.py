"""Regression tests for Telegram bot response cleanup helpers."""

from __future__ import annotations

import asyncio
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
    try:
        __import__("agents.base_agent")
    except ImportError:
        if "agents" not in sys.modules:
            sys.modules["agents"] = types.ModuleType("agents")
        ba = types.ModuleType("agents.base_agent")
        ba._t = lambda de, en=None, **_: de
        ba._TOOL_SAFEGUARD_SENTINEL = "__TOOL_SAFEGUARD__"
        sys.modules["agents.base_agent"] = ba
    if "core" not in sys.modules:
        sys.modules["core"] = types.ModuleType("core")
    if "core.redis_client" not in sys.modules:
        rc = types.ModuleType("core.redis_client")
        rc.get_redis = lambda: None
        sys.modules["core.redis_client"] = rc
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
    original_modules = {name: sys.modules.get(name) for name in _STUB_NAMES}
    _install_stubs()
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
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
                if "." in name:
                    parent_name, attr = name.rsplit(".", 1)
                    parent = sys.modules.get(parent_name)
                    if parent is not None and hasattr(parent, attr):
                        delattr(parent, attr)
            else:
                sys.modules[name] = module
                if "." in name:
                    parent_name, attr = name.rsplit(".", 1)
                    parent = sys.modules.get(parent_name)
                    if parent is not None:
                        setattr(parent, attr, module)


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


def test_clean_final_response_removes_agent_retry_meta(telegram_bot) -> None:
    response = (
        "1. I will call get_cluster_status with the correct connection_id.\n"
        "2. I will NOT repeat the call if it fails.\n"
        "3. I will report the error clearly.\n\n"
        "Let's try once more with the correct connection_id.\n"
        "⚠️ 7 consecutive tool errors. My previous approach is wrong.\n\n"
        "Der Kubernetes-Cluster ist gesund.\n\n"
        "| Metrik | Wert |\n"
        "| --- | --- |\n"
        "| Nodes | 1 |\n"
    )

    cleaned = telegram_bot._clean_final_response(response)

    assert "I will call" not in cleaned
    assert "consecutive tool errors" not in cleaned
    assert "Let's try" not in cleaned
    assert "Der Kubernetes-Cluster ist gesund." in cleaned
    assert "| Nodes | 1 |" in cleaned


def test_telegram_command_menu_includes_operational_commands(telegram_bot) -> None:
    commands = {item["command"] for item in telegram_bot._telegram_commands()}

    assert {"start", "help", "status", "chatid", "pair", "clear", "reset"} <= commands


@pytest.mark.asyncio
async def test_streaming_preview_filters_meta_and_returns_route_meta(
    telegram_bot, monkeypatch
) -> None:
    class _FakeOrchestrator:
        async def route(self, **kwargs):
            callback = kwargs.get("token_callback")
            if callback:
                await callback("1. I will call get_cluster_status.\n")
                await callback("⚠️ 7 consecutive tool errors.\n")
                await callback("Der Kubernetes-Cluster ist gesund.")
            return (
                "Der Kubernetes-Cluster ist gesund.",
                "kubernetes",
                False,
                {"routing_confidence": 1.0},
            )

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    bot = telegram_bot.TelegramBot(app)
    bot._send_preview_message = AsyncMock(return_value=42)
    bot._edit_message = AsyncMock(return_value=True)

    response, module, did_compact, route_meta, preview_id = await bot._route_with_live_preview(
        orchestrator=_FakeOrchestrator(),
        token="token",
        chat_id=123,
        message_id=7,
        contextualized_text="Wie ist der Status von Kubernetes?",
        history=[],
        session_id="telegram_123",
    )

    assert response == "Der Kubernetes-Cluster ist gesund."
    assert module == "kubernetes"
    assert did_compact is False
    assert route_meta == {"routing_confidence": 1.0}
    assert preview_id == 42
    edited_texts = [call.args[3] for call in bot._edit_message.await_args_list]
    assert edited_texts
    assert all("I will call" not in text for text in edited_texts)
    assert all("consecutive tool errors" not in text for text in edited_texts)
    assert any("Der Kubernetes-Cluster ist gesund" in text for text in edited_texts)


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
    is_closed = False

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


def _install_connection_stub(monkeypatch, conn) -> None:
    """Stub core.connections so handle_update can fetch the default connection."""
    cm_module = types.ModuleType("core.connections")

    class _ConnectionManager:
        @staticmethod
        async def get_default_connection(module_name: str):
            return conn

    cm_module.ConnectionManager = _ConnectionManager
    monkeypatch.setitem(sys.modules, "core.connections", cm_module)


@pytest.mark.asyncio
async def test_callback_confirm_tool_yes_with_compaction_stores_notice(
    telegram_bot, monkeypatch
) -> None:
    """Regression: did_compact=True crashed with NameError (route_meta undefined)."""
    fake_redis = _FakeRedis()
    monkeypatch.setattr(telegram_bot, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _FakeAsyncClient)

    app = types.SimpleNamespace(
        state=types.SimpleNamespace(
            orchestrator=types.SimpleNamespace(
                resume_tool_execution=AsyncMock(return_value=("done", True))
            )
        )
    )
    bot = telegram_bot.TelegramBot(app)
    bot._keep_typing = AsyncMock()
    bot._send = AsyncMock(return_value=True)

    await bot._handle_callback_query(
        {
            "id": "cb-1",
            "data": "confirm_tool_yes",
            "message": {"chat": {"id": 123}},
        },
        "token",
    )

    roles = [role for _, role, _ in fake_redis.messages]
    assert "assistant" in roles
    assert "system_compaction" in roles
    bot._send.assert_awaited()
    sent_text = bot._send.await_args.args[2]
    assert "❌" not in sent_text


@pytest.mark.asyncio
async def test_pair_approval_rejected_for_unauthorized_user(
    telegram_bot, monkeypatch
) -> None:
    """Regression: unauthorized users could approve their own pairing code."""
    fake_redis = _FakeRedis()
    monkeypatch.setattr(telegram_bot, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _FakeAsyncClient)
    _install_connection_stub(monkeypatch, None)  # keine Connection → dm_policy pairing

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    bot = telegram_bot.TelegramBot(app)
    bot._send = AsyncMock(return_value=True)
    bot._approve_pairing = AsyncMock(return_value=True)

    await bot.handle_update(
        {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 456},
                "text": "/pair ABC123",
            },
        },
        "token",
    )

    bot._approve_pairing.assert_not_awaited()
    bot._send.assert_awaited_once()
    denial = bot._send.await_args.args[2]
    assert "autorisiert" in denial or "authorized" in denial


@pytest.mark.asyncio
async def test_unauthorized_group_message_ignored_without_allowlist(
    telegram_bot, monkeypatch
) -> None:
    """Regression: groups without allowed_chat_ids processed unauthorized users."""
    fake_redis = _FakeRedis()
    monkeypatch.setattr(telegram_bot, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _FakeAsyncClient)
    conn = types.SimpleNamespace(config={"dm_policy": "pairing"}, vault_keys={})
    _install_connection_stub(monkeypatch, conn)

    orchestrator = types.SimpleNamespace(route=AsyncMock())
    app = types.SimpleNamespace(state=types.SimpleNamespace(orchestrator=orchestrator))
    bot = telegram_bot.TelegramBot(app)
    bot._send = AsyncMock(return_value=True)
    bot._react = AsyncMock()
    bot._keep_typing = AsyncMock()

    await bot.handle_update(
        {
            "update_id": 2,
            "message": {
                "message_id": 11,
                "chat": {"id": -100987, "type": "supergroup"},
                "from": {"id": 456},
                "text": "restart production cluster",
            },
        },
        "token",
    )

    orchestrator.route.assert_not_awaited()
    bot._send.assert_not_awaited()  # still: keine Antwort in die Gruppe


@pytest.mark.asyncio
async def test_clear_without_inflight_keeps_next_history(
    telegram_bot, monkeypatch
) -> None:
    """Regression: /clear flagged the session even without in-flight requests,
    silently dropping the history of the NEXT message."""

    class _FakeRedisWithClear(_FakeRedis):
        def __init__(self) -> None:
            super().__init__()
            self.cleared: list[str] = []

        async def clear_chat_history(self, session_id: str) -> None:
            self.cleared.append(session_id)

    fake_redis = _FakeRedisWithClear()
    monkeypatch.setattr(telegram_bot, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _FakeAsyncClient)
    conn = types.SimpleNamespace(config={"dm_policy": "open"}, vault_keys={})
    _install_connection_stub(monkeypatch, conn)

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    bot = telegram_bot.TelegramBot(app)
    bot._send = AsyncMock(return_value=True)

    await bot.handle_update(
        {
            "update_id": 3,
            "message": {
                "message_id": 12,
                "chat": {"id": 123, "type": "private"},
                "from": {"id": 456},
                "text": "/clear",
            },
        },
        "token",
    )

    assert fake_redis.cleared == ["telegram_123"]
    assert bot._cleared_sessions == set()


@pytest.mark.asyncio
async def test_poll_loop_survives_httpx_connect_error(
    telegram_bot, monkeypatch
) -> None:
    """Regression: httpx.ConnectError killed the poll loop permanently."""
    app = types.SimpleNamespace(state=types.SimpleNamespace())
    bot = telegram_bot.TelegramBot(app)
    bot.get_token = AsyncMock(return_value="token")
    monkeypatch.setattr(telegram_bot.asyncio, "sleep", AsyncMock())

    calls = {"n": 0}

    class _FlakyClient:
        is_closed = False

        async def get(self, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise telegram_bot.httpx.ConnectError("network blip")
            bot.running = False

            class _Response:
                status_code = 200

                def json(self):
                    return {"ok": True, "result": []}

            return _Response()

    bot._http = _FlakyClient()
    bot.running = True

    await bot._poll_loop()

    assert calls["n"] == 2  # zweiter Durchlauf → Loop hat den Fehler überlebt


class _RecordingAsyncClient:
    """Like _FakeAsyncClient but records every POST call for assertions."""

    is_closed = False
    calls: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args) -> None:
        pass

    async def post(self, url, json=None, **kwargs):
        type(self).calls.append((url, json or {}))

        class _Response:
            status_code = 200

            def json(self):
                return {"ok": True}

        return _Response()


@pytest.mark.asyncio
async def test_callback_query_removes_inline_keyboard(telegram_bot, monkeypatch) -> None:
    """Regression: after tapping Ja/Nein the button stayed clickable because
    only answerCallbackQuery (spinner) was called, never editMessageReplyMarkup
    (the actual keyboard)."""
    fake_redis = _FakeRedis(
        {"ninko:safeguard_pending:telegram_123": "find tasmota devices"}
    )
    monkeypatch.setattr(telegram_bot, "get_redis", lambda: fake_redis)
    _RecordingAsyncClient.calls = []
    monkeypatch.setattr(telegram_bot.httpx, "AsyncClient", _RecordingAsyncClient)

    app = types.SimpleNamespace(
        state=types.SimpleNamespace(
            orchestrator=types.SimpleNamespace(
                route=AsyncMock(return_value=("done", "fritzbox", False, {}))
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
            "message": {"chat": {"id": 123}, "message_id": 987},
        },
        "token",
    )

    edit_calls = [
        (url, payload)
        for url, payload in _RecordingAsyncClient.calls
        if url.endswith("editMessageReplyMarkup")
    ]
    assert len(edit_calls) == 1
    _, payload = edit_calls[0]
    assert payload["chat_id"] == 123
    assert payload["message_id"] == 987
    assert payload["reply_markup"] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_streaming_preview_surfaces_trace_events_not_internal_phases(
    telegram_bot, monkeypatch
) -> None:
    """Regression: the live preview only reacted to the legacy type=="status"
    event, but a real run almost exclusively emits type=="trace_event" (tool/
    agent/llm phases) — so the preview never updated between the initial
    placeholder and the final answer. Internal-wiring phases (routing/
    safeguard/...) must stay hidden, matching the web frontend's debug filter."""
    from core import status_bus

    session_id = "telegram_777"

    class _FakeOrchestrator:
        async def route(self, **kwargs):
            await status_bus.emit_trace(
                session_id, phase="tool", label="🔧 Rufe get_cluster_status auf"
            )
            await asyncio.sleep(0.4)
            await status_bus.emit_trace(
                session_id, phase="routing", label="Routing: kubernetes gewählt"
            )
            await asyncio.sleep(0.4)
            return (
                "Der Kubernetes-Cluster ist gesund.",
                "kubernetes",
                False,
                {"routing_confidence": 1.0},
            )

    app = types.SimpleNamespace(state=types.SimpleNamespace())
    bot = telegram_bot.TelegramBot(app)
    bot._send_preview_message = AsyncMock(return_value=42)
    bot._edit_message = AsyncMock(return_value=True)

    await bot._route_with_live_preview(
        orchestrator=_FakeOrchestrator(),
        token="token",
        chat_id=123,
        message_id=7,
        contextualized_text="Wie ist der Status von Kubernetes?",
        history=[],
        session_id=session_id,
    )

    edited_texts = [call.args[3] for call in bot._edit_message.await_args_list]
    assert edited_texts
    assert any("get_cluster_status" in text for text in edited_texts)
    assert all("Routing" not in text for text in edited_texts)
