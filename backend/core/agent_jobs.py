"""
Ninko – Agent-Jobs: Einmalige Hintergrund-Ausführung dynamischer Agenten.

Ein Job führt einen Custom-Agenten aus dem DynamicAgentPool genau einmal mit
einem Prompt aus — ohne Chat-Session und ohne persistierten Cron-Task.
Gestartet via API (POST /api/agents/{id}/run) oder Orchestrator-Tool
(run_agent_job). Ergebnis kommt asynchron: Redis-Event 'agent_job_finished'
plus abfragbarer Job-Status.

Hinweis Multi-Replica: Laufende asyncio-Tasks liegen in-memory — ein Cancel
auf einer anderen Replica erreicht den Lauf nicht. Für >1 Replica wären
verteilte Job-Ownership-Locks (core/distributed_lock.py) nötig.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("ninko.agent_jobs")

REDIS_KEY_JOB_PREFIX = "ninko:agent:job"
REDIS_KEY_JOB_INDEX_PREFIX = "ninko:agent:jobs:index"
JOB_TTL_SECONDS = 604800  # 7 Tage
MAX_JOBS_PER_AGENT = 50
JOB_TIMEOUT_SECONDS = 600  # analog Scheduler-Task-Timeout
MAX_RESULT_CHARS = 12000

_TERMINAL_STATUSES = ("succeeded", "failed", "cancelled")

# Fehlerheuristik analog agents/scheduler_agent.py
_ERROR_RESPONSE_PREFIXES = ("fehler:", "error:", "erreur", "❌")


def _normalize_tenant(tenant_id: str) -> str:
    return (tenant_id or "default").strip().lower().replace(" ", "_") or "default"


def _job_key(tenant_id: str, job_id: str) -> str:
    return f"{REDIS_KEY_JOB_PREFIX}:{_normalize_tenant(tenant_id)}:{job_id}"


def _index_key(tenant_id: str, agent_id: str) -> str:
    return f"{REDIS_KEY_JOB_INDEX_PREFIX}:{_normalize_tenant(tenant_id)}:{agent_id}"


def _response_indicates_error(response_text: str) -> bool:
    stripped = (response_text or "").strip().lower()
    return stripped.startswith(_ERROR_RESPONSE_PREFIXES)


class AgentJobManager:
    """Verwaltet einmalige Agent-Ausführungen als Hintergrund-Jobs."""

    def __init__(self) -> None:
        from core.redis_client import get_redis

        self._redis = get_redis()
        # Laufende asyncio-Tasks pro job_id (für Cancel); nur in diesem Prozess
        self._running: dict[str, asyncio.Task] = {}

    # ── Start ──────────────────────────────────────────

    async def start_job(
        self,
        *,
        tenant_id: str,
        agent_id: str,
        prompt: str,
        triggered_by: str = "api",
    ) -> dict:
        """Startet einen Agent-Job im Hintergrund und gibt den Job-Eintrag zurück.

        Raises ValueError, wenn der Agent im Tenant nicht existiert.
        """
        tenant = _normalize_tenant(tenant_id)
        job_id = str(uuid.uuid4())

        # Session-Kontext setzen, damit Pool-Lookup und Tools tenant-korrekt laufen
        from core import status_bus

        status_bus.set_session_id(f"{tenant}:job-{job_id}")

        from core.agent_pool import get_agent_pool

        pool = get_agent_pool()
        agent, agent_name = pool.get_agent_by_id(agent_id)
        if agent is None:
            raise ValueError(f"Agent '{agent_id}' nicht im Pool gefunden.")

        now = datetime.now(timezone.utc).isoformat()
        job = {
            "id": job_id,
            "tenant_id": tenant,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "prompt": prompt,
            "status": "pending",
            "result": None,
            "error": None,
            "triggered_by": triggered_by,
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "duration_ms": None,
        }
        await self._persist(job)
        await self._redis.connection.lpush(_index_key(tenant, agent_id), job_id)
        await self._redis.connection.ltrim(
            _index_key(tenant, agent_id), 0, MAX_JOBS_PER_AGENT - 1
        )

        bg_task = asyncio.create_task(self._run_job(job, agent))
        self._running[job_id] = bg_task

        def _on_done(done: asyncio.Task) -> None:
            self._running.pop(job_id, None)
            try:
                exc = done.exception()
            except asyncio.CancelledError:
                return
            if exc:
                logger.exception("Agent-Job %s abgestürzt: %s", job_id, exc)

        bg_task.add_done_callback(_on_done)
        logger.info(
            "Agent-Job gestartet: %s (Agent '%s', tenant=%s, via %s)",
            job_id,
            agent_name,
            tenant,
            triggered_by,
        )
        return job

    # ── Ausführung ─────────────────────────────────────

    async def _run_job(self, job: dict, agent) -> None:
        from core import status_bus

        job_id = job["id"]
        tenant = job["tenant_id"]
        # create_task kopiert den Kontext des Aufrufers — Session-ID hier erneut
        # setzen, damit Tools im Agenten tenant-korrekt arbeiten.
        status_bus.set_session_id(f"{tenant}:job-{job_id}")

        start = time.monotonic()
        job["status"] = "running"
        job["started_at"] = datetime.now(timezone.utc).isoformat()
        await self._persist(job)

        try:
            response_text, _ = await asyncio.wait_for(
                agent.invoke(message=job["prompt"], chat_history=None),
                timeout=JOB_TIMEOUT_SECONDS,
            )
            if _response_indicates_error(response_text):
                job["status"] = "failed"
                job["error"] = (response_text or "")[:MAX_RESULT_CHARS]
            else:
                job["status"] = "succeeded"
            job["result"] = (response_text or "")[:MAX_RESULT_CHARS]

        except asyncio.TimeoutError:
            job["status"] = "failed"
            job["error"] = f"Timeout nach {JOB_TIMEOUT_SECONDS}s."
            logger.error("Agent-Job %s Timeout nach %ds.", job_id, JOB_TIMEOUT_SECONDS)

        except asyncio.CancelledError:
            job["status"] = "cancelled"
            job["error"] = "Job wurde abgebrochen."
            await self._finalize(job, start)
            raise

        except Exception as exc:
            job["status"] = "failed"
            job["error"] = str(exc)[:1000]
            logger.error("Agent-Job %s fehlgeschlagen: %s", job_id, exc)

        await self._finalize(job, start)

    async def _finalize(self, job: dict, start_monotonic: float) -> None:
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        job["duration_ms"] = int((time.monotonic() - start_monotonic) * 1000)
        await self._persist(job)

        try:
            await self._redis.publish_event(
                {
                    "type": "agent_job_finished",
                    "job_id": job["id"],
                    "agent_id": job["agent_id"],
                    "agent_name": job["agent_name"],
                    "tenant_id": job["tenant_id"],
                    "status": job["status"],
                    "duration_ms": job["duration_ms"],
                    "response_preview": (job.get("result") or job.get("error") or "")[:200],
                    "timestamp": job["finished_at"],
                }
            )
        except Exception as exc:
            logger.warning("agent_job_finished-Event konnte nicht publiziert werden: %s", exc)

        logger.info(
            "Agent-Job %s abgeschlossen: %s (%dms)",
            job["id"],
            job["status"],
            job["duration_ms"] or 0,
        )

    # ── Abfragen ───────────────────────────────────────

    async def get_job(self, tenant_id: str, job_id: str) -> dict | None:
        raw = await self._redis.connection.get(_job_key(tenant_id, job_id))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Agent-Job '%s' enthält ungültiges JSON.", job_id)
            return None

    async def list_jobs(self, tenant_id: str, agent_id: str, limit: int = 20) -> list[dict]:
        limit = min(max(1, limit), MAX_JOBS_PER_AGENT)
        raw_ids = await self._redis.connection.lrange(
            _index_key(tenant_id, agent_id), 0, limit - 1
        )
        jobs: list[dict] = []
        for raw_id in raw_ids:
            job_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else raw_id
            job = await self.get_job(tenant_id, job_id)
            if job:  # abgelaufene (TTL) Job-Keys still herausfiltern
                jobs.append(job)
        return jobs

    # ── Cancel ─────────────────────────────────────────

    async def cancel_job(self, tenant_id: str, job_id: str) -> dict:
        """Bricht einen laufenden/wartenden Job ab.

        Raises ValueError, wenn der Job unbekannt oder bereits beendet ist.
        """
        job = await self.get_job(tenant_id, job_id)
        if job is None:
            raise ValueError(f"Job '{job_id}' nicht gefunden.")
        if job["status"] in _TERMINAL_STATUSES:
            raise ValueError(f"Job '{job_id}' ist bereits beendet ({job['status']}).")

        running = self._running.get(job_id)
        if running is not None:
            running.cancel()
            # _run_job persistiert den cancelled-Status im CancelledError-Pfad
            return {**job, "status": "cancelled"}

        # pending ohne laufenden Task (z.B. nach Prozess-Neustart) → direkt markieren
        job["status"] = "cancelled"
        job["error"] = "Job wurde abgebrochen."
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        await self._persist(job)
        return job

    # ── Helpers ────────────────────────────────────────

    async def _persist(self, job: dict) -> None:
        await self._redis.connection.set(
            _job_key(job["tenant_id"], job["id"]),
            json.dumps(job, default=str),
            ex=JOB_TTL_SECONDS,
        )


_manager: AgentJobManager | None = None


def get_agent_job_manager() -> AgentJobManager:
    """Singleton-Zugriff auf den AgentJobManager."""
    global _manager
    if _manager is None:
        _manager = AgentJobManager()
    return _manager
