"""
Ninko Scheduler Agent – Autonome Aufgabenplanung mit Cron-Ausdrücken.
Führt geplante Aufgaben über den Orchestrator aus und pusht Ergebnisse via PubSub.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from croniter import croniter

from core.redis_client import get_redis

# Lock to prevent concurrent R-M-W races on the shared tasks list
_tasks_lock = asyncio.Lock()

if TYPE_CHECKING:
    from agents.orchestrator import OrchestratorAgent
    from core.module_registry import ModuleRegistry

logger = logging.getLogger("ninko.agents.scheduler")

REDIS_KEY_TASKS = "ninko:scheduler:tasks"
REDIS_KEY_LOG_PREFIX = "ninko:scheduler:log:"
MAX_LOG_ENTRIES = 50
CHECK_INTERVAL_SECONDS = 30


class SchedulerAgent:
    """
    Background-Agent für geplante Aufgaben.
    Prüft alle 30 Sekunden ob Tasks fällig sind und führt sie über
    den OrchestratorAgent aus.
    """

    def __init__(
        self,
        registry: "ModuleRegistry",
        orchestrator: "OrchestratorAgent",
    ) -> None:
        self.registry = registry
        self.orchestrator = orchestrator
        self._redis = get_redis()
        self._running = False
        self._task: asyncio.Task | None = None

    # ── Lifecycle ──────────────────────────────────────

    async def start_loop(self) -> None:
        """Startet die Scheduler-Schleife als Background-Task."""
        self._running = True
        logger.info(
            "Scheduler-Agent gestartet (Intervall: %ds)",
            CHECK_INTERVAL_SECONDS,
        )

        while self._running:
            try:
                await self._check_and_run()
            except Exception as exc:
                logger.error("Scheduler-Cycle Fehler: %s", exc, exc_info=True)

            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stoppt die Scheduler-Schleife."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("Scheduler-Agent gestoppt.")

    # ── Core Logic ─────────────────────────────────────

    async def _check_and_run(self) -> None:
        """Prüft welche Tasks fällig sind und führt sie aus."""
        tasks = await self.get_all_tasks()
        now = datetime.now(timezone.utc)

        for task in tasks:
            if not task.get("enabled", True):
                continue

            next_run_str = task.get("next_run")
            if not next_run_str:
                # Erstmalig: next_run berechnen
                await self._update_next_run(task)
                continue

            next_run = datetime.fromisoformat(next_run_str)
            if now >= next_run:
                logger.info(
                    "Task '%s' (%s) ist fällig – wird ausgeführt.",
                    task["name"],
                    task["id"],
                )
                await self._execute_task(task)

    async def _execute_task(self, task: dict) -> dict:
        """Führt einen einzelnen Task über den Orchestrator oder die WorkflowEngine aus."""
        task_id = task["id"]
        start_time = time.monotonic()
        workflow_id = task.get("workflow_id")

        agent_id = task.get("agent_id")

        try:
            response_text = ""
            module_used = None

            if workflow_id:
                # Workflow ausführen
                from core.workflow_engine import WorkflowEngine
                wf_raw = await self._redis.connection.get("ninko:workflows")
                workflows = json.loads(wf_raw) if wf_raw else []
                wf = next((w for w in workflows if w["id"] == workflow_id), None)
                if not wf:
                    raise ValueError(f"Workflow '{workflow_id}' nicht gefunden.")

                run_id = str(uuid.uuid4())
                logger.info("Starte Workflow '%s' für Task '%s' (Run: %s)", workflow_id, task["name"], run_id)

                engine = WorkflowEngine(self._redis, self.orchestrator)
                await engine.execute(wf, run_id)

                # Ergebnis aus Redis lesen
                runs_raw = await self._redis.connection.get(f"ninko:workflow:runs:{workflow_id}")
                runs = json.loads(runs_raw) if runs_raw else []
                run_result = next((r for r in runs if r["id"] == run_id), {})
                status = run_result.get("status", "error")
                response_text = f"Workflow {status.upper()}"
                if status == "succeeded":
                    response_text += ": Alle Schritte erfolgreich abgeschlossen."
                else:
                    response_text += f": {run_result.get('error', 'Unbekannter Fehler')}"
                module_used = "workflow"

            elif agent_id:
                # Dynamischen Agenten aus dem Pool aufrufen
                from core.agent_pool import get_agent_pool
                pool = get_agent_pool()
                agent, agent_name = pool.get_agent_by_id(agent_id)
                if agent is None:
                    raise ValueError(f"Agent '{agent_id}' nicht im Pool gefunden.")

                logger.info("Starte Agent '%s' (%s) für Task '%s'", agent_name, agent_id, task["name"])
                response_text, _ = await agent.invoke(
                    message=task.get("prompt", "Führe deine Aufgabe aus."),
                    chat_history=None,
                )
                module_used = f"agent:{agent_name}"

            else:
                # Orchestrator ausführen (Prompt)
                response_text, module_used, _ = await self.orchestrator.route(
                    message=task["prompt"],
                    chat_history=None,
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)

            log_entry = {
                "task_id": task_id,
                "task_name": task["name"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "ok" if (workflow_id and status == "succeeded") or (not workflow_id) else "error",
                "module_used": module_used,
                "prompt": task.get("prompt", ""),
                "workflow_id": workflow_id,
                "agent_id": agent_id,
                "response": response_text[:2000],  # Limit für Redis
                "duration_ms": duration_ms,
            }

            # Task-Metadata aktualisieren
            await self._update_after_execution(task, log_entry["status"])

            # Log speichern
            await self._store_log(task_id, log_entry)

            # Event via WebSocket pushen
            await self._redis.publish_event({
                "type": "task_executed",
                "task_id": task_id,
                "task_name": task["name"],
                "status": log_entry["status"],
                "module_used": module_used,
                "duration_ms": duration_ms,
                "response_preview": response_text[:200],
                "timestamp": log_entry["timestamp"],
            })

            logger.info(
                "Task '%s' ausgeführt (%dms, Typ: %s)",
                task["name"],
                duration_ms,
                "Workflow" if workflow_id else (module_used or "direkt"),
            )
            return log_entry

        except Exception as exc:
            duration_ms = int((time.monotonic() - start_time) * 1000)

            log_entry = {
                "task_id": task_id,
                "task_name": task["name"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "module_used": "workflow" if workflow_id else (f"agent:{agent_id}" if agent_id else None),
                "prompt": task.get("prompt", ""),
                "workflow_id": workflow_id,
                "agent_id": agent_id,
                "response": str(exc)[:2000],
                "duration_ms": duration_ms,
            }

            await self._update_after_execution(task, "error")
            await self._store_log(task_id, log_entry)

            await self._redis.publish_event({
                "type": "task_executed",
                "task_id": task_id,
                "task_name": task["name"],
                "status": "error",
                "error": str(exc)[:200],
                "timestamp": log_entry["timestamp"],
            })

            logger.error(
                "Task '%s' fehlgeschlagen: %s", task["name"], exc
            )
            return log_entry

    # ── Task CRUD ──────────────────────────────────────

    async def get_all_tasks(self) -> list[dict]:
        """Alle Tasks aus Redis laden."""
        raw = await self._redis.connection.get(REDIS_KEY_TASKS)
        if not raw:
            return []
        return json.loads(raw)

    async def get_task(self, task_id: str) -> dict | None:
        """Einzelnen Task laden."""
        tasks = await self.get_all_tasks()
        return next((t for t in tasks if t["id"] == task_id), None)

    async def create_task(self, data: dict) -> dict:
        """Neuen Task erstellen."""
        # Cron validieren
        if not croniter.is_valid(data["cron"]):
            raise ValueError(f"Ungültiger Cron-Ausdruck: {data['cron']}")

        async with _tasks_lock:
            tasks = await self.get_all_tasks()

            task = {
                "id": str(uuid.uuid4()),
                "name": data["name"],
                "cron": data["cron"],
                "prompt": data.get("prompt", ""),
                "workflow_id": data.get("workflow_id"),
                "agent_id": data.get("agent_id"),
                "target_module": data.get("target_module"),
                "enabled": data.get("enabled", True),
                "last_run": None,
                "next_run": None,
                "last_result": None,
            }

            # next_run berechnen
            cron = croniter(task["cron"], datetime.now(timezone.utc))
            task["next_run"] = cron.get_next(datetime).isoformat()

            tasks.append(task)
            await self._save_tasks(tasks)

        logger.info("Task erstellt: '%s' (Cron: %s)", task["name"], task["cron"])
        return task

    async def update_task(self, task_id: str, data: dict) -> dict | None:
        """Task aktualisieren."""
        async with _tasks_lock:
            tasks = await self.get_all_tasks()
            task = next((t for t in tasks if t["id"] == task_id), None)
            if not task:
                return None

            if "cron" in data and data["cron"]:
                if not croniter.is_valid(data["cron"]):
                    raise ValueError(f"Ungültiger Cron-Ausdruck: {data['cron']}")
                task["cron"] = data["cron"]
                # next_run neu berechnen
                cron = croniter(task["cron"], datetime.now(timezone.utc))
                task["next_run"] = cron.get_next(datetime).isoformat()

            for key in ("name", "prompt", "target_module", "enabled", "agent_id", "workflow_id"):
                if key in data and data[key] is not None:
                    task[key] = data[key]

            await self._save_tasks(tasks)
        return task

    async def delete_task(self, task_id: str) -> bool:
        """Task löschen."""
        async with _tasks_lock:
            tasks = await self.get_all_tasks()
            original_len = len(tasks)
            tasks = [t for t in tasks if t["id"] != task_id]

            if len(tasks) == original_len:
                return False

            await self._save_tasks(tasks)

        # Logs löschen (außerhalb des Locks, kein gemeinsamer State)
        await self._redis.connection.delete(f"{REDIS_KEY_LOG_PREFIX}{task_id}")
        logger.info("Task gelöscht: %s", task_id)
        return True

    async def toggle_task(self, task_id: str) -> dict | None:
        """Task aktivieren/deaktivieren."""
        async with _tasks_lock:
            tasks = await self.get_all_tasks()
            task = next((t for t in tasks if t["id"] == task_id), None)
            if not task:
                return None

            task["enabled"] = not task["enabled"]
            await self._save_tasks(tasks)
        return task

    async def run_task_now(self, task_id: str) -> dict | None:
        """Task sofort manuell ausführen."""
        task = await self.get_task(task_id)
        if not task:
            return None
        return await self._execute_task(task)

    # ── Logs ───────────────────────────────────────────

    async def get_task_logs(self, task_id: str, limit: int = 20) -> list[dict]:
        """Ausführungs-Logs eines Tasks laden."""
        key = f"{REDIS_KEY_LOG_PREFIX}{task_id}"
        raw_entries = await self._redis.connection.lrange(key, 0, limit - 1)
        return [json.loads(entry) for entry in raw_entries]

    # ── Helpers ────────────────────────────────────────

    async def _save_tasks(self, tasks: list[dict]) -> None:
        """Task-Liste in Redis speichern."""
        await self._redis.connection.set(REDIS_KEY_TASKS, json.dumps(tasks, default=str))

    async def _update_next_run(self, task: dict) -> None:
        """next_run für einen Task berechnen und speichern."""
        async with _tasks_lock:
            tasks = await self.get_all_tasks()
            for t in tasks:
                if t["id"] == task["id"]:
                    cron = croniter(t["cron"], datetime.now(timezone.utc))
                    t["next_run"] = cron.get_next(datetime).isoformat()
                    break
            await self._save_tasks(tasks)

    async def _update_after_execution(self, task: dict, status: str) -> None:
        """Task-Metadata nach Ausführung aktualisieren."""
        async with _tasks_lock:
            tasks = await self.get_all_tasks()
            for t in tasks:
                if t["id"] == task["id"]:
                    t["last_run"] = datetime.now(timezone.utc).isoformat()
                    t["last_result"] = status
                    cron = croniter(t["cron"], datetime.now(timezone.utc))
                    t["next_run"] = cron.get_next(datetime).isoformat()
                    break
            await self._save_tasks(tasks)

    async def _store_log(self, task_id: str, log_entry: dict) -> None:
        """Ausführungs-Log in Redis speichern (LIFO, max 50)."""
        key = f"{REDIS_KEY_LOG_PREFIX}{task_id}"
        await self._redis.connection.lpush(key, json.dumps(log_entry, default=str))
        await self._redis.connection.ltrim(key, 0, MAX_LOG_ENTRIES - 1)
