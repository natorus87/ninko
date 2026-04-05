"""
Redis-backed registry for ad-hoc core tasks.

The first rollout focuses on long-running CLI jobs executed as background
subprocesses. Metadata and output are persisted in Redis, while live asyncio
objects remain in memory.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from core.redis_client import get_redis

logger = logging.getLogger("ninko.core.task_registry")

TASKS_KEY = "ninko:core:tasks"
MAX_OUTPUT_CHARS = 12000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class LiveTaskHandle:
    task: asyncio.Task
    process: asyncio.subprocess.Process | None = None


class TaskRegistry:
    """Registry for background CLI tasks."""

    def __init__(self) -> None:
        self._live: dict[str, LiveTaskHandle] = {}
        self._lock = asyncio.Lock()

    async def list_tasks(self) -> list[dict]:
        redis = get_redis()
        raw = await redis.connection.hgetall(TASKS_KEY)
        tasks = [json.loads(value) for value in raw.values()]
        tasks.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return tasks

    async def get_task(self, task_id: str) -> dict | None:
        redis = get_redis()
        raw = await redis.connection.hget(TASKS_KEY, task_id)
        return json.loads(raw) if raw else None

    async def create_cli_task(self, command: str, description: str = "") -> dict:
        task_id = str(uuid.uuid4())
        payload = {
            "id": task_id,
            "type": "cli_command",
            "command": command,
            "description": description,
            "status": "created",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "started_at": None,
            "finished_at": None,
            "returncode": None,
            "output": "",
            "error": "",
        }
        await self._save(payload)
        return payload

    async def start_cli_task(
        self,
        task_id: str,
        args: list[str],
    ) -> None:
        async with self._lock:
            if task_id in self._live:
                raise ValueError(f"Task '{task_id}' is already running.")

            runner = asyncio.create_task(self._run_cli_task(task_id, args))
            self._live[task_id] = LiveTaskHandle(task=runner)
            runner.add_done_callback(
                lambda done: asyncio.create_task(self._finalize_handle(task_id, done))
            )

    async def stop_task(self, task_id: str) -> dict:
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")
        if task.get("status") in {"completed", "failed", "stopped"}:
            raise ValueError(
                f"Task '{task_id}' is already in terminal state '{task['status']}'."
            )

        handle = self._live.get(task_id)
        if handle and handle.process and handle.process.returncode is None:
            handle.process.terminate()
            with contextlib.suppress(ProcessLookupError, asyncio.TimeoutError):
                await asyncio.wait_for(handle.process.wait(), timeout=5)

        if handle and not handle.task.done():
            handle.task.cancel()

        task["status"] = "stopped"
        task["finished_at"] = _now_iso()
        task["updated_at"] = _now_iso()
        await self._save(task)
        return task

    async def task_output(self, task_id: str) -> str:
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")
        output = task.get("output", "")
        error = task.get("error", "")
        if error:
            return f"{output}\n\nSTDERR:\n{error}".strip()
        return output

    async def _run_cli_task(self, task_id: str, args: list[str]) -> None:
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task '{task_id}' not found.")

        task["status"] = "running"
        task["started_at"] = _now_iso()
        task["updated_at"] = _now_iso()
        await self._save(task)

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async with self._lock:
            handle = self._live.get(task_id)
            if handle:
                handle.process = process

        try:
            stdout, stderr = await process.communicate()
            task["status"] = "completed" if process.returncode == 0 else "failed"
            task["returncode"] = process.returncode
            task["output"] = (stdout or b"").decode("utf-8", errors="replace")[
                :MAX_OUTPUT_CHARS
            ].strip()
            task["error"] = (stderr or b"").decode("utf-8", errors="replace")[
                :MAX_OUTPUT_CHARS
            ].strip()
        except asyncio.CancelledError:
            logger.info("Background task '%s' cancelled.", task_id)
            raise
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            task["status"] = "failed"
            task["error"] = str(exc)
            logger.error("Background task '%s' failed: %s", task_id, exc)
        finally:
            task["finished_at"] = _now_iso()
            task["updated_at"] = _now_iso()
            await self._save(task)

    async def _finalize_handle(self, task_id: str, done: asyncio.Task) -> None:
        with contextlib.suppress(asyncio.CancelledError, RuntimeError, ValueError, OSError):
            await done
        async with self._lock:
            self._live.pop(task_id, None)

    async def _save(self, payload: dict) -> None:
        redis = get_redis()
        await redis.connection.hset(TASKS_KEY, payload["id"], json.dumps(payload))


_global_task_registry: TaskRegistry | None = None


def get_task_registry() -> TaskRegistry:
    global _global_task_registry
    if _global_task_registry is None:
        _global_task_registry = TaskRegistry()
    return _global_task_registry
