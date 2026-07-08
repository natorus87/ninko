"""
Ninko Scheduler Agent – Autonome Aufgabenplanung mit Cron-Ausdrücken.
Führt geplante Aufgaben über den Orchestrator aus und pusht Ergebnisse via PubSub.

Hinweis Multi-Replica: Der Scheduler-Loop läuft pro Prozess; Doppellauf-Schutz
(_running_task_ids) und _tasks_lock sind In-Memory. Bei mehr als einer
Backend-Replica würde jeder Task pro Replica feuern — dann wären Leader-
Election bzw. verteilte Locks (core/distributed_lock.py) nötig.
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

# Modul-globale Instanz – wird von main.py beim Start gesetzt
_global_scheduler: "SchedulerAgent | None" = None


def set_scheduler_agent(agent: "SchedulerAgent") -> None:
    """Setzt die globale Scheduler-Instanz (wird in main.py aufgerufen)."""
    global _global_scheduler
    _global_scheduler = agent


def get_scheduler_agent() -> "SchedulerAgent | None":
    """Gibt die globale Scheduler-Instanz zurück."""
    return _global_scheduler

if TYPE_CHECKING:
    from agents.orchestrator import OrchestratorAgent
    from core.module_registry import ModuleRegistry

logger = logging.getLogger("ninko.agents.scheduler")

_SCHEDULER_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    OSError,
    json.JSONDecodeError,
    asyncio.TimeoutError,
)

_ERROR_RESPONSE_PREFIXES = ("fehler:", "error:", "erreur", "❌")


def _response_indicates_error(response_text: str) -> bool:
    """Heuristik: erkennt Fehler-Antwortstrings von Agent/Orchestrator.

    Verhindert, dass inhaltliche Fehlermeldungen als Task-Status 'ok' geloggt werden.
    """
    stripped = (response_text or "").strip().lower()
    return stripped.startswith(_ERROR_RESPONSE_PREFIXES)


def _task_tenant(task: dict) -> str:
    """Tenant eines Tasks (Legacy-Tasks ohne tenant_id → 'default')."""
    return (task.get("tenant_id") or "default").strip().lower() or "default"


REDIS_KEY_TASKS = "ninko:scheduler:tasks"
REDIS_KEY_LOG_PREFIX = "ninko:scheduler:log:"
MAX_LOG_ENTRIES = 50
CHECK_INTERVAL_SECONDS = 30
# Obergrenze pro Task-Ausführung. Verhindert, dass ein hängender LLM-/Workflow-Call
# den seriellen _check_and_run-Zyklus (und damit alle anderen fälligen Tasks) blockiert.
TASK_EXECUTION_TIMEOUT_SECONDS = 600


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
        # Verhindert Doppelläufe desselben Tasks (Scheduler-Zyklus vs. run_task_now)
        self._running_task_ids: set[str] = set()
        # Referenzen auf manuell gestartete Hintergrund-Runs (run_task_now)
        self._bg_manual_runs: set[asyncio.Task] = set()

    # ── Lifecycle ──────────────────────────────────────

    async def start_loop(self) -> None:
        """Startet die Scheduler-Schleife als Background-Task."""
        self._running = True
        # Eigene Task-Referenz merken, damit stop() den Loop tatsächlich canceln kann.
        self._task = asyncio.current_task()
        logger.info(
            "Scheduler-Agent gestartet (Intervall: %ds)",
            CHECK_INTERVAL_SECONDS,
        )

        while self._running:
            try:
                await self._check_and_run()
            except _SCHEDULER_EXCEPTIONS as exc:
                logger.error("Scheduler-Cycle Fehler: %s", exc, exc_info=True)
            except Exception as exc:
                # Fängt alles Unerwartete (AttributeError, Provider-/LangGraph-Fehler),
                # damit die Schleife nicht stirbt und alle Cron-Tasks bis zum
                # Backend-Neustart stillstehen. Analog zum MonitorAgent.
                logger.exception("Scheduler-Cycle unerwarteter Fehler: %s", exc)

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
                await self._run_task_guarded(task)

    async def _run_task_guarded(self, task: dict) -> dict | None:
        """Führt einen Task mit Doppellauf-Schutz und hartem Timeout aus.

        Verhindert, dass derselbe Task parallel läuft (Zyklus vs. run_task_now) und
        dass ein hängender Lauf den seriellen Scheduler-Zyklus blockiert.
        """
        task_id = task["id"]
        if task_id in self._running_task_ids:
            logger.warning(
                "Task '%s' (%s) läuft bereits – Doppellauf übersprungen.",
                task.get("name"),
                task_id,
            )
            return None
        self._running_task_ids.add(task_id)
        try:
            return await asyncio.wait_for(
                self._execute_task(task),
                timeout=TASK_EXECUTION_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.error(
                "Task '%s' (%s) Timeout nach %ds – abgebrochen.",
                task.get("name"),
                task_id,
                TASK_EXECUTION_TIMEOUT_SECONDS,
            )
            # next_run trotzdem fortschreiben, sonst feuert der überfällige Task
            # in jedem Zyklus erneut.
            try:
                await self._update_after_execution(task, "error")
            except _SCHEDULER_EXCEPTIONS as exc:
                logger.warning(
                    "next_run-Update nach Timeout fehlgeschlagen (%s): %s", task_id, exc
                )
            return None
        finally:
            self._running_task_ids.discard(task_id)

    async def _execute_task(self, task: dict) -> dict:
        """Führt einen einzelnen Task über den Orchestrator oder die WorkflowEngine aus."""
        task_id = task["id"]
        start_time = time.monotonic()
        workflow_id = task.get("workflow_id")

        agent_id = task.get("agent_id")
        tenant_id = _task_tenant(task)

        # Session-Kontext für Tools/Pool setzen: _current_tenant_id() und der
        # Agent-Pool leiten den Tenant aus der status_bus-Session-ID ab.
        from core import status_bus

        status_bus.set_session_id(f"{tenant_id}:scheduler-{task_id}")

        try:
            response_text = ""
            module_used = None
            exec_status = "ok"

            if workflow_id:
                # Workflow ausführen — Storage ist tenant-scoped
                # (ninko:workflows:<tenant>, IDs "tenant::public").
                from core.workflow_engine import WorkflowEngine, _tenant_key

                wf_key = _tenant_key("ninko:workflows", tenant_id)
                wf_raw = await self._redis.connection.get(wf_key)
                workflows = json.loads(wf_raw) if wf_raw else []
                scoped_wf_id = f"{tenant_id}::{workflow_id}"
                wf = next(
                    (
                        w
                        for w in workflows
                        if w.get("id") in (workflow_id, scoped_wf_id)
                    ),
                    None,
                )
                if not wf:
                    raise ValueError(f"Workflow '{workflow_id}' nicht gefunden.")

                run_id = str(uuid.uuid4())
                logger.info("Starte Workflow '%s' für Task '%s' (Run: %s)", workflow_id, task["name"], run_id)

                engine = WorkflowEngine(self._redis, self.orchestrator)
                await engine.execute(wf, run_id, triggered_by="schedule")

                # Ergebnis aus Redis lesen (tenant-scoped Runs-Key)
                runs_key = f"{_tenant_key('ninko:workflow:runs:', tenant_id)}{wf['id']}"
                runs_raw = await self._redis.connection.get(runs_key)
                runs = json.loads(runs_raw) if runs_raw else []
                run_result = next((r for r in runs if r["id"] == run_id), {})
                status = run_result.get("status", "error")
                response_text = f"Workflow {status.upper()}"
                if status == "succeeded":
                    response_text += ": Alle Schritte erfolgreich abgeschlossen."
                else:
                    response_text += f": {run_result.get('error', 'Unbekannter Fehler')}"
                module_used = "workflow"
                exec_status = "ok" if status == "succeeded" else "error"

            elif agent_id:
                # Dynamischen Agenten aus dem Pool aufrufen
                from core.agent_pool import get_agent_pool
                pool = get_agent_pool()
                # Tasks mit tenant_id laufen tenant-strikt (Session-Kontext oben
                # gesetzt). Cross-tenant nur noch als Fallback für Legacy-Tasks
                # ohne tenant_id.
                allow_cross = "tenant_id" not in task
                agent, agent_name = pool.get_agent_by_id(agent_id, allow_cross_tenant=allow_cross)
                if agent is None:
                    raise ValueError(f"Agent '{agent_id}' nicht im Pool gefunden.")

                logger.info("Starte Agent '%s' (%s) für Task '%s'", agent_name, agent_id, task["name"])
                response_text, _ = await agent.invoke(
                    message=task.get("prompt", "Führe deine Aufgabe aus."),
                    chat_history=None,
                )
                module_used = f"agent:{agent_name}"
                exec_status = "error" if _response_indicates_error(response_text) else "ok"

            else:
                # Orchestrator ausführen (Prompt)
                response_text, module_used, _, _ = await self.orchestrator.route(
                    message=task["prompt"],
                    chat_history=None,
                )
                exec_status = "error" if _response_indicates_error(response_text) else "ok"

            duration_ms = int((time.monotonic() - start_time) * 1000)

            log_entry = {
                "task_id": task_id,
                "task_name": task["name"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": exec_status,
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

        except _SCHEDULER_EXCEPTIONS as exc:
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
                "tenant_id": (data.get("tenant_id") or "default").strip().lower() or "default",
                "source": data.get("source"),
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
        """Task sofort im Hintergrund starten (blockiert den Aufrufer nicht).

        Das Ergebnis kommt asynchron über das WS-Event 'task_executed' und
        die Task-Logs. Gibt {"status": "started"|"already_running"} zurück.
        """
        task = await self.get_task(task_id)
        if not task:
            return None
        if task["id"] in self._running_task_ids:
            return {"task_id": task_id, "status": "already_running"}

        bg_task = asyncio.create_task(self._run_task_guarded(task))
        self._bg_manual_runs.add(bg_task)

        def _on_done(done: asyncio.Task) -> None:
            self._bg_manual_runs.discard(done)
            try:
                exc = done.exception()
            except asyncio.CancelledError:
                return
            if exc:
                logger.exception("Manueller Task-Run abgestürzt: %s", exc)

        bg_task.add_done_callback(_on_done)
        return {"task_id": task_id, "status": "started"}

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
