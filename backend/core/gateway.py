"""
Gateway Mode: embedded LangGraph runtime.

Eliminates the need for a separate LangGraph Server process by embedding
the runtime directly in the Ninko process. Runs are managed by RunManager
and streamed to clients via StreamBridge.

Architecture:
    Client → FastAPI SSE → StreamBridge → RunManager → LangGraph Agent
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunConfig:
    thread_id: str = ""
    recursion_limit: int = 10000
    stream_mode: str = "values"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Run:
    run_id: str
    thread_id: str
    status: RunStatus = RunStatus.PENDING
    agent: Any = None
    config: RunConfig = field(default_factory=RunConfig)
    messages: list[Any] = field(default_factory=list)
    result: Any = None
    error: str | None = None
    created_at: float = 0.0
    completed_at: float = 0.0
    _cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    _queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue())


class RunManager:
    """Manages embedded LangGraph runs."""

    def __init__(self, max_concurrent: int = 10):
        self._runs: dict[str, Run] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        for run in list(self._runs.values()):
            run._cancel_event.set()

    async def create_run(
        self,
        agent: Any,
        messages: list[Any],
        config: RunConfig | None = None,
    ) -> Run:
        import time as _time

        cfg = config or RunConfig()
        run_id = str(uuid.uuid4())
        thread_id = cfg.thread_id or run_id

        run = Run(
            run_id=run_id,
            thread_id=thread_id,
            agent=agent,
            config=cfg,
            messages=messages,
            created_at=_time.monotonic(),
        )

        self._runs[run_id] = run
        asyncio.create_task(self._execute_run(run))
        return run

    async def get_run(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    async def cancel_run(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run and run.status == RunStatus.RUNNING:
            run._cancel_event.set()
            run.status = RunStatus.CANCELLED
            return True
        return False

    async def stream_run(self, run_id: str) -> AsyncIterator[Any]:
        run = self._runs.get(run_id)
        if not run:
            return

        while True:
            try:
                item = await asyncio.wait_for(run._queue.get(), timeout=0.5)
                if item is None:
                    break
                yield item
            except asyncio.TimeoutError:
                if run.status in (
                    RunStatus.COMPLETED,
                    RunStatus.FAILED,
                    RunStatus.CANCELLED,
                ):
                    break

    async def _execute_run(self, run: Run) -> None:
        import time as _time

        async with self._semaphore:
            run.status = RunStatus.RUNNING

            try:
                run_config = {"recursion_limit": run.config.recursion_limit}

                if run.config.stream_mode == "values":
                    last_event = None
                    async for event in run.agent.astream(
                        {"messages": run.messages}, config=run_config
                    ):
                        last_event = event
                        if run._cancel_event.is_set():
                            run.status = RunStatus.CANCELLED
                            break
                        await run._queue.put(event)

                    run.result = last_event if not run._cancel_event.is_set() else None
                else:
                    result = await asyncio.wait_for(
                        run.agent.ainvoke(
                            {"messages": run.messages}, config=run_config
                        ),
                        timeout=600,
                    )
                    run.result = result
                    await run._queue.put(result)

                if run.status != RunStatus.CANCELLED:
                    run.status = RunStatus.COMPLETED

            except asyncio.TimeoutError:
                run.status = RunStatus.FAILED
                run.error = "Run timed out after 600s"
                logger.warning("Run %s timed out", run.run_id)

            except Exception as exc:
                run.status = RunStatus.FAILED
                run.error = str(exc)
                logger.error("Run %s failed: %s", run.run_id, exc, exc_info=True)

            finally:
                run.completed_at = _time.monotonic()
                await run._queue.put(None)

    async def _cleanup_loop(self) -> None:
        import time as _time

        while True:
            try:
                await asyncio.sleep(300)
                now = _time.monotonic()
                expired = [
                    rid
                    for rid, run in self._runs.items()
                    if run.status
                    in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED)
                    and (now - run.completed_at) > 3600
                ]
                for rid in expired:
                    del self._runs[rid]
                if expired:
                    logger.debug("Cleaned up %d expired runs", len(expired))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Run cleanup error: %s", exc)


class StreamBridge:
    """Bridges LangGraph streaming to SSE format."""

    def __init__(self, run_manager: RunManager):
        self._run_manager = run_manager

    async def sse_stream(self, run_id: str) -> AsyncIterator[str]:
        async for event in self._run_manager.stream_run(run_id):
            yield f"data: {event}\n\n"

    async def create_and_stream(
        self,
        agent: Any,
        messages: list[Any],
        config: RunConfig | None = None,
    ) -> AsyncIterator[str]:
        run = await self._run_manager.create_run(agent, messages, config)
        yield f"data: run_id={run.run_id}\n\n"

        async for event in self._run_manager.stream_run(run.run_id):
            yield f"data: {event}\n\n"


_gateway_instance: RunManager | None = None


def get_gateway() -> RunManager:
    global _gateway_instance
    if _gateway_instance is None:
        _gateway_instance = RunManager()
    return _gateway_instance
