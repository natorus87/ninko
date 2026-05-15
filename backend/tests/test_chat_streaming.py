"""
Tests fuer den Streaming-Pfad von POST /api/chat/ (Phase 5 des Streaming-Plans).

Decken folgende Spezifikationspunkte ab:

- JSON-Pfad bleibt unveraendert kompatibel (Content-Type application/json).
- Streaming-Pfad sendet `start`, mehrere `token`, genau ein `final`.
- `final.meta` enthaelt `context_budget`, `compacted`, `routing_confidence`, `safeguard`.
- Client-Abbruch cancelt die Backend-Task und schreibt keine Assistant-History.
- Confirmation-required (Safeguard) sendet keine Tokens vor `final`.
- Tool-Sentinel sendet keine Antwort-Tokens vor Confirm-Prompt.
- Zwei parallele Requests in derselben Session vermischen keine Frames.

Tests laufen ohne echten Server: ein minimales FastAPI-App-Setup mit dem
`routes_chat`-Router und gemockten Modul-Level-Abhaengigkeiten.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


pytestmark = pytest.mark.asyncio


# ── Helpers ────────────────────────────────────────────────────────────────────


def _parse_sse_frames(raw: str) -> list[dict]:
    """Zerlegt SSE-Rohdaten in eine Liste von Frame-Dicts."""
    frames: list[dict] = []
    for line in raw.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[len("data: "):].strip()
        if not payload:
            continue
        frames.append(json.loads(payload))
    return frames


async def _collect_streaming_response(client: AsyncClient, body: dict, **kwargs) -> list[dict]:
    """POST mit SSE-Header und sammelt alle Frames."""
    async with client.stream(
        "POST",
        "/api/chat/",
        headers={"Accept": "text/event-stream", "Content-Type": "application/json"},
        json=body,
        **kwargs,
    ) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        raw = ""
        async for chunk in response.aiter_text():
            raw += chunk
    return _parse_sse_frames(raw)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_redis() -> MagicMock:
    redis = MagicMock()
    redis.get_chat_history = AsyncMock(return_value=[])
    redis.store_chat_message = AsyncMock()
    redis.connection = MagicMock()
    redis.connection.get = AsyncMock(return_value=None)
    redis.connection.set = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def fake_ctx_mgr() -> MagicMock:
    mgr = MagicMock()
    mgr.get_budget_info = MagicMock(
        return_value={"used_tokens": 100, "max_tokens": 4000, "percent": 2.5}
    )
    return mgr


@pytest.fixture
def fake_op_journal() -> MagicMock:
    journal = MagicMock()
    journal.get_pending_for_session = AsyncMock(return_value=None)
    journal.mark_confirmed = AsyncMock()
    journal.create_pending = AsyncMock(return_value="tx-test-id")
    journal.mark_executed = AsyncMock()
    journal.clear_pending_for_session = AsyncMock()
    return journal


@pytest.fixture
def fake_telemetry() -> MagicMock:
    telem = MagicMock()
    telem.check_and_record_correction = AsyncMock(return_value=False)
    telem.record_auto_routing = AsyncMock()
    telem.get_correction_examples = AsyncMock(return_value=[])
    return telem


@pytest.fixture
def fake_orchestrator() -> MagicMock:
    """Defaultverhalten: liefert eine einfache Textantwort, kein Compaction."""
    orch = MagicMock()
    orch._last_routing_confidence = 0.9
    orch._last_tier_used = 1
    orch._last_compaction_summary = None
    orch.resume_tool_execution = AsyncMock(return_value=("resumed text", False))
    orch.route = AsyncMock(return_value=("Hello world response.", "test_module", False))
    return orch


@pytest.fixture
def app(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis: MagicMock,
    fake_ctx_mgr: MagicMock,
    fake_op_journal: MagicMock,
    fake_telemetry: MagicMock,
    fake_orchestrator: MagicMock,
) -> FastAPI:
    """Minimales FastAPI-App-Setup mit dem chat-Router und allen Mocks."""
    from api import routes_chat
    from core import status_bus as _status_bus

    # Modul-Level-Abhaengigkeiten patchen
    monkeypatch.setattr(routes_chat, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(routes_chat, "get_context_manager", lambda: fake_ctx_mgr)
    monkeypatch.setattr(routes_chat, "get_operation_journal", lambda: fake_op_journal)
    monkeypatch.setattr(routes_chat, "get_routing_telemetry", lambda: fake_telemetry)

    # Auth umgehen → tenant_id "default"
    monkeypatch.setattr(
        routes_chat,
        "resolve_request_auth",
        lambda request: {"tenant_id": "default", "username": "test"},
    )
    monkeypatch.setattr(routes_chat, "auth_tenant_id", lambda ctx: "default")

    # status_bus.done darf nicht blockieren oder Redis fordern
    async def _noop_done(_session_id: str) -> None:
        return None

    monkeypatch.setattr(_status_bus, "done", _noop_done)
    monkeypatch.setattr(routes_chat.status_bus, "done", _noop_done)

    app = FastAPI()
    app.include_router(routes_chat.router)
    app.state.orchestrator = fake_orchestrator
    app.state.safeguard = None
    return app


@pytest_asyncio.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ── Tests ──────────────────────────────────────────────────────────────────────


async def test_json_path_unchanged(client: AsyncClient, fake_redis: MagicMock) -> None:
    """Ohne Accept: text/event-stream bleibt der JSON-Pfad voll kompatibel."""
    response = await client.post(
        "/api/chat/",
        json={"message": "hi", "session_id": "json-1"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    assert body["response"] == "Hello world response."
    assert body["module_used"] == "test_module"
    assert body["session_id"] == "json-1"
    assert body["confirmation_required"] is False
    # Assistant-History wurde geschrieben
    roles_written = [
        kwargs["role"]
        for _args, kwargs in fake_redis.store_chat_message.await_args_list
    ]
    assert "user" in roles_written and "assistant" in roles_written


async def test_streaming_emits_start_tokens_and_single_final(
    client: AsyncClient, fake_orchestrator: MagicMock
) -> None:
    """Streaming sendet `start`, mehrere `token`, genau ein `final`."""
    # Antwort lang genug fuer Chunking (chunk_size=30 in routes_chat)
    fake_orchestrator.route = AsyncMock(
        return_value=("A" * 75, "test_module", False)
    )
    frames = await _collect_streaming_response(
        client, {"message": "hi", "session_id": "stream-1"}
    )
    types = [f["type"] for f in frames]
    assert types[0] == "start"
    assert types.count("token") >= 2
    assert types.count("final") == 1
    assert types[-1] == "final"

    # Konsistente IDs ueber alle Frames
    request_ids = {f["request_id"] for f in frames}
    message_ids = {f["message_id"] for f in frames}
    assert len(request_ids) == 1
    assert len(message_ids) == 1


async def test_final_meta_contains_required_fields(
    client: AsyncClient, fake_orchestrator: MagicMock
) -> None:
    """`final.meta` enthaelt context_budget, compacted, routing_confidence, safeguard."""
    fake_orchestrator._last_routing_confidence = 0.42
    frames = await _collect_streaming_response(
        client, {"message": "hi", "session_id": "stream-meta"}
    )
    final = next(f for f in frames if f["type"] == "final")
    meta = final["meta"]
    assert "context_budget" in meta
    assert "compacted" in meta
    assert "routing_confidence" in meta
    assert "safeguard" in meta
    assert meta["routing_confidence"] == 0.42
    assert meta["compacted"] is False
    assert meta["context_budget"] is not None
    assert final["response"] == "Hello world response."


async def test_client_disconnect_writes_no_assistant_history(
    monkeypatch: pytest.MonkeyPatch,
    fake_redis: MagicMock,
    fake_ctx_mgr: MagicMock,
    fake_op_journal: MagicMock,
    fake_telemetry: MagicMock,
    fake_orchestrator: MagicMock,
) -> None:
    """
    Bei Client-Abbruch wird keine Assistant-History geschrieben und der Generator
    sendet ein `cancelled`-Frame.

    httpx ASGITransport simuliert keinen echten http.disconnect, deshalb wird der
    Generator direkt aufgerufen — mit gemocktem Request, dessen is_disconnected()
    nach kurzer Zeit True liefert.
    """
    from api import routes_chat
    from core import status_bus as _status_bus
    from schemas.chat import ChatRequest

    monkeypatch.setattr(routes_chat, "get_redis", lambda: fake_redis)
    monkeypatch.setattr(routes_chat, "get_context_manager", lambda: fake_ctx_mgr)
    monkeypatch.setattr(routes_chat, "get_operation_journal", lambda: fake_op_journal)
    monkeypatch.setattr(routes_chat, "get_routing_telemetry", lambda: fake_telemetry)

    async def _noop_done(_session_id: str) -> None:
        return None

    monkeypatch.setattr(_status_bus, "done", _noop_done)
    monkeypatch.setattr(routes_chat.status_bus, "done", _noop_done)

    # route() blockt; is_disconnected liefert sofort True, sodass der
    # Generator-Loop direkt in den CancelledError-Pfad faellt.
    async def blocking_route(*_a: Any, **_kw: Any) -> tuple[str, str | None, bool]:
        await asyncio.sleep(60.0)
        return ("never", None, False)

    fake_orchestrator.route = AsyncMock(side_effect=blocking_route)

    fake_request = MagicMock()
    fake_request.app = MagicMock()
    fake_request.app.state = MagicMock()
    fake_request.app.state.orchestrator = fake_orchestrator
    fake_request.app.state.safeguard = None

    async def _is_disconnected_true() -> bool:
        return True

    fake_request.is_disconnected = _is_disconnected_true

    body = ChatRequest(message="long-running", session_id="cancel-1")

    gen = routes_chat._stream_safe_generate(
        fake_request, body, "default:cancel-1", "req-1", "msg-1"
    )

    try:
        # Erstes Yield ist das cancelled-Frame (kommt aus dem except-Block).
        raw_cancelled = await asyncio.wait_for(gen.__anext__(), timeout=5.0)
        frames = _parse_sse_frames(raw_cancelled)

        # Danach raisst der Generator den CancelledError ueber den `raise` re-throw.
        with pytest.raises((asyncio.CancelledError, StopAsyncIteration)):
            await asyncio.wait_for(gen.__anext__(), timeout=5.0)
    finally:
        # Generator sauber schliessen, damit alle Hintergrund-Tasks (route_task)
        # gecancelled werden.
        await gen.aclose()
        # Verbleibende Tasks aufraeumen
        for task in list(asyncio.all_tasks()):
            if task is not asyncio.current_task() and not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, BaseException):
                    pass

    types = [f["type"] for f in frames]
    assert "cancelled" in types, f"Kein cancelled-Frame: {types}"
    assert "final" not in types, f"Final-Frame trotz Abbruch: {types}"

    roles_written = [
        call.kwargs.get("role")
        for call in fake_redis.store_chat_message.await_args_list
    ]
    assert "assistant" not in roles_written, (
        f"Assistant-History bei Abbruch geschrieben: {roles_written}"
    )

    # Assistant-History wurde NICHT geschrieben
    roles_written = [
        call.kwargs.get("role")
        for call in fake_redis.store_chat_message.await_args_list
    ]
    assert "assistant" not in roles_written, (
        f"Assistant-History bei Abbruch geschrieben: {roles_written}"
    )


async def test_safeguard_confirmation_sends_no_tokens_before_final(
    app: FastAPI, fake_orchestrator: MagicMock
) -> None:
    """SafeGuard-Confirmation darf keine Tokens vor `final` senden."""
    # Mock Safeguard mit Confirmation-Required
    fake_sg_result = MagicMock()
    fake_sg_result.requires_confirmation = True
    fake_sg_result.category = MagicMock()
    fake_sg_result.category.value = "DESTRUCTIVE"

    # Importiere ActionCategory um den Enum-Vergleich in routes_chat zu treffen
    from core.safeguard import ActionCategory

    fake_sg_result.category = ActionCategory.DESTRUCTIVE
    fake_sg_result.rationale = "Test rationale"
    fake_sg_result.auto_decided = False
    fake_sg_result.auto_decision = None
    fake_sg_result.to_dict = MagicMock(
        return_value={"category": "DESTRUCTIVE", "rationale": "Test rationale"}
    )

    safeguard = MagicMock()
    safeguard.check = AsyncMock(return_value=fake_sg_result)
    safeguard._audit_log = AsyncMock()
    app.state.safeguard = safeguard

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        frames = await _collect_streaming_response(
            ac, {"message": "rm -rf /", "session_id": "sg-1"}
        )

    types = [f["type"] for f in frames]
    # Vor dem final darf nur start stehen, kein einziges token
    final_idx = types.index("final")
    assert "token" not in types[:final_idx], f"Tokens vor final: {types[:final_idx]}"
    final = frames[final_idx]
    assert final["meta"]["confirmation_required"] is True
    assert final["meta"]["safeguard"]["category"] == "DESTRUCTIVE"
    # Orchestrator darf nie aufgerufen worden sein bei Confirmation-Pfad
    fake_orchestrator.route.assert_not_awaited()


async def test_tool_sentinel_sends_no_tokens_before_final(
    client: AsyncClient, fake_orchestrator: MagicMock
) -> None:
    """Tool-Safeguard-Sentinel sendet keine Antwort-Tokens vor `final`."""
    from agents.base_agent import _TOOL_SAFEGUARD_SENTINEL

    sentinel_payload = json.dumps(
        {"tool_name": "kubectl_delete", "category": "DESTRUCTIVE", "rationale": "rm pods"}
    )
    fake_orchestrator.route = AsyncMock(
        return_value=(_TOOL_SAFEGUARD_SENTINEL + sentinel_payload, "kubernetes", False)
    )

    frames = await _collect_streaming_response(
        client, {"message": "delete pods", "session_id": "tool-sentinel-1"}
    )

    types = [f["type"] for f in frames]
    final_idx = types.index("final")
    # Tokens duerfen vor final auftauchen wenn der Sentinel als Text gestreamt wurde —
    # routes_chat _stream_safe_generate puffert den Live-Stream aber im Orchestrator-
    # Pfad solange route() nicht selbst Tokens emittiert; in diesem Test gibt der
    # Mock-Orchestrator keinen Live-Token aus, sodass kein Pre-Final-Token erwartet wird.
    assert "token" not in types[:final_idx], f"Tokens vor Sentinel-final: {types[:final_idx]}"
    final = frames[final_idx]
    assert final["meta"]["confirmation_required"] is True
    assert final["meta"]["safeguard"]["tool_name"] == "kubectl_delete"
    assert final["response"] == ""


async def test_parallel_requests_do_not_mix_frames(
    client: AsyncClient, fake_orchestrator: MagicMock
) -> None:
    """Zwei parallele Requests in derselben Session vermischen keine Frames."""
    call_counter = {"n": 0}

    async def per_call_route(
        message: str, *_args: Any, **_kw: Any
    ) -> tuple[str, str | None, bool]:
        call_counter["n"] += 1
        n = call_counter["n"]
        await asyncio.sleep(0.05)  # kleine Verzoegerung fuer Interleaving
        return (f"response-{n}-for-{message}", f"module-{n}", False)

    fake_orchestrator.route = AsyncMock(side_effect=per_call_route)

    async def one_run(msg: str) -> list[dict]:
        return await _collect_streaming_response(
            client, {"message": msg, "session_id": "shared-session"}
        )

    frames_a, frames_b = await asyncio.gather(one_run("alpha"), one_run("beta"))

    def check_one_stream(frames: list[dict]) -> None:
        request_ids = {f["request_id"] for f in frames}
        message_ids = {f["message_id"] for f in frames}
        assert len(request_ids) == 1, f"Mehrere request_ids: {request_ids}"
        assert len(message_ids) == 1, f"Mehrere message_ids: {message_ids}"
        types = [f["type"] for f in frames]
        assert types[0] == "start"
        assert types.count("final") == 1

    check_one_stream(frames_a)
    check_one_stream(frames_b)

    # Beide Streams haben unterschiedliche IDs
    rid_a = frames_a[0]["request_id"]
    rid_b = frames_b[0]["request_id"]
    assert rid_a != rid_b

    # Antworten haengen am richtigen Stream
    final_a = next(f for f in frames_a if f["type"] == "final")
    final_b = next(f for f in frames_b if f["type"] == "final")
    assert "alpha" in final_a["response"]
    assert "beta" in final_b["response"]
