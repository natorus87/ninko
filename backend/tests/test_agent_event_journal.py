"""Tests for durable AgentEvent persistence and resumable SSE replay."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.routes_agents import (
    _assert_existing_session_access,
    _event_cursor,
    _stream_agent_events,
    router,
)
from core.agent_event_journal import (
    AgentEventJournal,
    JournaledAgentEvent,
    normalize_event_cursor,
)
from schemas.execution import AgentEvent, AgentEventType


def _event(
    event_type: AgentEventType = AgentEventType.STARTED,
    *,
    run_id: str = "run-1",
    parent_run_id: str | None = None,
) -> AgentEvent:
    return AgentEvent(
        type=event_type,
        tenant_id="acme",
        session_id="acme:session-1",
        run_id=run_id,
        parent_run_id=parent_run_id,
        agent_id="agent-1",
        data={"status": event_type.value},
    )


class _FakePipeline:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection
        self.commands: list[tuple[str, tuple, dict]] = []

    def xadd(self, *args, **kwargs) -> "_FakePipeline":
        self.commands.append(("xadd", args, kwargs))
        return self

    def expire(self, *args, **kwargs) -> "_FakePipeline":
        self.commands.append(("expire", args, kwargs))
        return self

    async def execute(self) -> list[object]:
        results: list[object] = []
        for command, args, kwargs in self.commands:
            if command == "xadd":
                results.append(await self.connection.xadd(*args, **kwargs))
            else:
                self.connection.expirations[args[0]] = args[1]
                results.append(True)
        return results


class _FakeConnection:
    def __init__(self) -> None:
        self.streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        self.expirations: dict[str, int] = {}

    def pipeline(self, *, transaction: bool) -> _FakePipeline:
        assert transaction is True
        return _FakePipeline(self)

    async def xadd(
        self,
        key: str,
        fields: dict[str, str],
        *,
        maxlen: int,
        approximate: bool,
    ) -> str:
        assert approximate is True
        stream = self.streams.setdefault(key, [])
        cursor = f"{len(stream) + 1}-0"
        stream.append((cursor, fields))
        del stream[:-maxlen]
        return cursor

    async def xrange(
        self,
        key: str,
        *,
        min: str,
        max: str,
        count: int,
    ) -> list[tuple[str, dict[str, str]]]:
        assert max == "+"
        after = int(min.removeprefix("(").split("-", 1)[0])
        return [
            entry
            for entry in self.streams.get(key, [])
            if int(entry[0].split("-", 1)[0]) > after
        ][:count]

    async def xrevrange(
        self,
        key: str,
        *,
        max: str,
        min: str,
        count: int,
    ) -> list[tuple[str, dict[str, str]]]:
        assert max == "+"
        assert min == "-"
        return list(reversed(self.streams.get(key, [])))[:count]

    async def xread(
        self,
        streams: dict[str, str],
        *,
        count: int,
        block: int,
    ) -> list[tuple[str, list[tuple[str, dict[str, str]]]]]:
        assert 0 < block <= 30_000
        key, after_cursor = next(iter(streams.items()))
        entries = await self.xrange(
            key,
            min=f"({after_cursor}",
            max="+",
            count=count,
        )
        return [(key, entries)] if entries else []


def _journal() -> tuple[AgentEventJournal, _FakeConnection]:
    connection = _FakeConnection()
    redis = MagicMock()
    redis.connection = connection
    return AgentEventJournal(redis, max_events=10, ttl_seconds=60), connection


@pytest.mark.asyncio
async def test_journal_appends_replays_and_hides_session_from_key() -> None:
    journal, connection = _journal()
    event = _event()

    cursor = await journal.append(event)
    replay = await journal.read_after(
        tenant_id="acme",
        session_id=event.session_id,
    )

    assert cursor == "1-0"
    assert replay == [JournaledAgentEvent(cursor="1-0", event=event)]
    key = journal.stream_key("acme", event.session_id)
    assert event.session_id not in key
    assert connection.expirations[key] == 60
    assert f"ninko:session_owner:{event.session_id}" not in connection.expirations


@pytest.mark.asyncio
async def test_journal_replay_is_strictly_after_cursor_and_session_scoped() -> None:
    journal, _ = _journal()
    first_cursor = await journal.append(_event(run_id="run-1"))
    await journal.append(_event(run_id="run-2"))
    other_session_event = _event(run_id="run-other").model_copy(
        update={"session_id": "acme:session-2"}
    )
    await journal.append(other_session_event)

    replay = await journal.read_after(
        tenant_id="acme",
        session_id="acme:session-1",
        after=first_cursor,
    )

    assert [item.event.run_id for item in replay] == ["run-2"]


@pytest.mark.asyncio
async def test_journal_returns_server_side_tail_cursor() -> None:
    journal, _ = _journal()

    assert await journal.latest_cursor(
        tenant_id="acme",
        session_id="acme:session-1",
    ) == "0-0"
    await journal.append(_event(run_id="run-1"))
    last_cursor = await journal.append(_event(run_id="run-2"))

    assert await journal.latest_cursor(
        tenant_id="acme",
        session_id="acme:session-1",
    ) == last_cursor


@pytest.mark.asyncio
async def test_journal_rejects_cross_tenant_event() -> None:
    journal, _ = _journal()
    event = _event().model_copy(update={"tenant_id": "other"})

    with pytest.raises(ValueError, match="tenant_id"):
        await journal.append(event)


@pytest.mark.asyncio
async def test_journal_skips_malformed_entries_without_payload_logging(
    caplog: pytest.LogCaptureFixture,
) -> None:
    journal, connection = _journal()
    key = journal.stream_key("acme", "acme:session-1")
    connection.streams[key] = [
        ("1-0", {"event": "secret-malformed-json"}),
        ("2-0", {"event": _event().model_dump_json()}),
    ]

    replay = await journal.read_after(
        tenant_id="acme",
        session_id="acme:session-1",
    )

    assert [item.cursor for item in replay] == ["2-0"]
    assert "secret-malformed-json" not in caplog.text


@pytest.mark.asyncio
async def test_journal_redacts_nested_secrets_and_bounds_large_payloads() -> None:
    journal, _ = _journal()
    github_token = "ghp_" + ("A" * 36)
    event = _event().model_copy(
        update={
            "data": {
                "nested": {"password": "top-secret", "value": github_token},
            }
        }
    )
    await journal.append(event)

    replay = await journal.read_after(
        tenant_id="acme",
        session_id=event.session_id,
    )

    serialized = replay[0].event.model_dump_json()
    assert "top-secret" not in serialized
    assert github_token not in serialized
    assert "***" in serialized
    assert "[REDACTED]" in serialized

    large_event = _event(run_id="large").model_copy(
        update={
            "data": {
                f"value_{index}": "x" * 3_000
                for index in range(100)
            }
        }
    )
    await journal.append(large_event)
    large_replay = await journal.read_after(
        tenant_id="acme",
        session_id=large_event.session_id,
        after=replay[0].cursor,
    )
    assert large_replay[0].event.data == {"truncated": True}


@pytest.mark.parametrize("cursor", ["", "latest", "$", "1", "1-2-3", "-1-0"])
def test_public_cursor_rejects_non_redis_ids(cursor: str) -> None:
    with pytest.raises(ValueError, match="Cursor"):
        normalize_event_cursor(cursor)


@pytest.mark.parametrize(
    "cursor",
    [
        "١-٠",
        f"{2**64}-0",
        "9" * 42,
    ],
)
def test_public_cursor_rejects_unicode_overflow_and_oversize(cursor: str) -> None:
    with pytest.raises(ValueError, match="Cursor"):
        normalize_event_cursor(cursor)


class _ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


async def _empty_event_stream(*args, **kwargs):
    if False:
        yield ""


@pytest.mark.asyncio
async def test_sse_replays_children_and_closes_on_parent_terminal() -> None:
    items = [
        JournaledAgentEvent("1-0", _event()),
        JournaledAgentEvent(
            "2-0",
            _event(
                AgentEventType.TOOL_CALL,
                run_id="tool-1",
                parent_run_id="run-1",
            ),
        ),
        JournaledAgentEvent("3-0", _event(AgentEventType.COMPLETED)),
    ]
    journal = MagicMock()
    journal.read_after = AsyncMock(return_value=items)
    journal.wait_after = AsyncMock()

    frames = [
        frame
        async for frame in _stream_agent_events(
            _ConnectedRequest(),
            journal,
            tenant_id="acme",
            session_id="acme:session-1",
            after="0-0",
            run_id="run-1",
        )
    ]

    assert [frame.splitlines()[0] for frame in frames] == [
        "id: 1-0",
        "id: 2-0",
        "id: 3-0",
    ]
    assert json.loads(frames[-1].split("data: ", 1)[1])["type"] == "completed"
    journal.wait_after.assert_not_awaited()


@pytest.mark.asyncio
async def test_sse_advances_past_unrelated_runs_without_closing_on_child_terminal() -> None:
    unrelated = JournaledAgentEvent("1-0", _event(run_id="other-run"))
    child_terminal = JournaledAgentEvent(
        "2-0",
        _event(
            AgentEventType.COMPLETED,
            run_id="tool-1",
            parent_run_id="run-1",
        ),
    )
    parent_terminal = JournaledAgentEvent(
        "3-0",
        _event(AgentEventType.COMPLETED, run_id="run-1"),
    )
    journal = MagicMock()
    journal.read_after = AsyncMock(
        side_effect=[[unrelated, child_terminal], [parent_terminal]]
    )
    journal.wait_after = AsyncMock()

    frames = [
        frame
        async for frame in _stream_agent_events(
            _ConnectedRequest(),
            journal,
            tenant_id="acme",
            session_id="acme:session-1",
            after="0-0",
            run_id="run-1",
        )
    ]

    assert [frame.splitlines()[0] for frame in frames] == [
        "id: 2-0",
        "id: 3-0",
    ]
    assert journal.read_after.await_args_list[1].kwargs["after"] == "2-0"
    journal.wait_after.assert_not_awaited()


@pytest.mark.asyncio
async def test_sse_includes_pipeline_grandchild_tool_events() -> None:
    items = [
        JournaledAgentEvent(
            "1-0",
            _event(run_id="pipeline:step", parent_run_id="pipeline"),
        ),
        JournaledAgentEvent(
            "2-0",
            _event(
                AgentEventType.TOOL_CALL,
                run_id="tool-1",
                parent_run_id="pipeline:step",
            ),
        ),
        JournaledAgentEvent(
            "3-0",
            _event(AgentEventType.COMPLETED, run_id="pipeline"),
        ),
    ]
    journal = MagicMock()
    journal.read_after = AsyncMock(return_value=items)
    journal.wait_after = AsyncMock()

    frames = [
        frame
        async for frame in _stream_agent_events(
            _ConnectedRequest(),
            journal,
            tenant_id="acme",
            session_id="acme:session-1",
            after="0-0",
            run_id="pipeline",
        )
    ]

    assert [frame.splitlines()[0] for frame in frames] == [
        "id: 1-0",
        "id: 2-0",
        "id: 3-0",
    ]


@pytest.mark.asyncio
async def test_sse_advances_past_poison_only_batch() -> None:
    journal, connection = _journal()
    key = journal.stream_key("acme", "acme:session-1")
    connection.streams[key] = [
        (f"{index}-0", {"event": "malformed"})
        for index in range(1, 101)
    ]
    connection.streams[key].append(
        ("101-0", {"event": _event(AgentEventType.COMPLETED).model_dump_json()})
    )

    frames = [
        frame
        async for frame in _stream_agent_events(
            _ConnectedRequest(),
            journal,
            tenant_id="acme",
            session_id="acme:session-1",
            after="0-0",
            run_id="run-1",
        )
    ]

    assert len(frames) == 1
    assert frames[0].startswith("id: 101-0")


@pytest.mark.asyncio
async def test_sse_propagates_cancellation_from_blocking_read() -> None:
    started = asyncio.Event()
    released = asyncio.Event()

    async def blocking_read(**kwargs) -> list[JournaledAgentEvent]:
        started.set()
        try:
            await asyncio.Future()
        finally:
            released.set()

    journal = MagicMock()
    journal.read_after = AsyncMock(return_value=[])
    journal.wait_after = AsyncMock(side_effect=blocking_read)
    generator = _stream_agent_events(
        _ConnectedRequest(),
        journal,
        tenant_id="acme",
        session_id="acme:session-1",
        after="0-0",
    )

    stream_task = asyncio.create_task(anext(generator))
    await started.wait()
    stream_task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await stream_task
    assert released.is_set()


def test_event_cursor_uses_last_event_id_unless_query_cursor_is_present() -> None:
    request = MagicMock()
    request.headers = {"last-event-id": "4-2"}

    assert _event_cursor(request, None) == "4-2"
    assert _event_cursor(request, "7-1") == "7-1"


@pytest.mark.asyncio
async def test_session_event_stream_never_claims_ownerless_session() -> None:
    request = MagicMock()
    redis = MagicMock()
    redis.get_session_owner = AsyncMock(return_value=None)

    with (
        patch(
            "api.routes_agents.resolve_request_auth",
            return_value={"username": "alice"},
        ),
        patch("api.routes_agents.get_redis", return_value=redis),
        pytest.raises(HTTPException) as raised,
    ):
        await _assert_existing_session_access(request, "acme:session-1")

    assert getattr(raised.value, "status_code", None) == 404
    redis.set_session_owner.assert_not_called()


def test_session_stream_rejects_invalid_cursor_before_opening_stream() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with (
        patch(
            "api.routes_chat._tenant_session_id",
            return_value="default:session-1",
        ),
    ):
        response = client.get(
            "/api/agents/events/stream",
            params={"session_id": "session-1", "after": "latest"},
        )

    assert response.status_code == 400


def test_session_stream_tail_uses_and_returns_server_cursor() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    journal = MagicMock()
    journal.latest_cursor = AsyncMock(return_value="17-2")

    with (
        patch(
            "api.routes_agents.resolve_request_auth",
            return_value={"username": "alice", "tenant_id": "default"},
        ),
        patch(
            "api.routes_chat._tenant_session_id",
            return_value="default:session-1",
        ),
        patch(
            "api.routes_agents._assert_existing_session_access",
            new=AsyncMock(),
        ),
        patch(
            "api.routes_agents.get_agent_event_journal",
            return_value=journal,
        ),
        patch(
            "api.routes_agents._stream_agent_events",
            side_effect=_empty_event_stream,
        ) as stream,
    ):
        response = client.get(
            "/api/agents/events/stream",
            params={"session_id": "session-1", "tail": "true"},
        )

    assert response.status_code == 200
    assert response.headers["x-agent-event-cursor"] == "17-2"
    journal.latest_cursor.assert_awaited_once_with(
        tenant_id="default",
        session_id="default:session-1",
    )
    assert stream.call_args.kwargs["after"] == "17-2"
