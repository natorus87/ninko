"""
Ninko – Typed Pipeline Engine.

Ersetzt den fragilen run_pipeline()-String-Stack durch eine typisierte,
fehlertolerante Engine mit Pydantic-Schemas, per-Step-Retry, deterministischer
Topologie, strukturierten Events und Redis-Checkpoints.

Architektur-Ziel:
  - LLM entscheidet NICHT mehr, ob Steps ausgeführt werden
  - Alle Inputs/Outputs sind typisiert (PipelineStep / StepResult)
  - Jeder Step hat eine RetryPolicy (backoff, max_retries)
  - Events werden bei jeder Zustandsänderung emittiert
  - SafeGuard-Bestätigung ist per Step konfigurierbar
  - Der bestehende run_pipeline()-Tool delegiert vollständig an diese Engine
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from enum import Enum

# Recoverable exceptions for non-critical pipeline operations (e.g. persist
# compaction summary). Schwere Fehler hier dürfen den Step nicht abbrechen.
_PIPELINE_RECOVERABLE_EXCEPTIONS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    OSError,
    ConnectionError,
    TimeoutError,
)
from typing import Any

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("ninko.pipeline_engine")


def _is_safeguard_sentinel(response: Any) -> bool:
    """True, wenn ein Sub-Agent-Return das Tool-Safeguard-Pause-Sentinel ist."""
    try:
        from agents.base_agent import _TOOL_SAFEGUARD_SENTINEL
    except ImportError:
        return False
    return isinstance(response, str) and response.startswith(_TOOL_SAFEGUARD_SENTINEL)


async def _release_paused_subagent(session_id: str) -> None:
    """Räumt einen innerhalb eines Pipeline-Steps pausierten Sub-Agenten auf.

    Ohne diesen Cleanup blockiert der `_paused_sg_agents`-Eintrag alle weiteren
    Invokes der Session bis zum TTL (~300s), obwohl es keinen Resume-Pfad gibt.
    """
    try:
        from agents.base_agent import _paused_sg_agents, _paused_sg_agents_ts
        _paused_sg_agents.pop(session_id, None)
        _paused_sg_agents_ts.pop(session_id, None)
    except ImportError:
        pass
    try:
        from core.redis_client import get_redis
        await get_redis().connection.delete(
            f"ninko:safeguard_tool_pending:{session_id}"
        )
    except _PIPELINE_RECOVERABLE_EXCEPTIONS as exc:
        logger.debug("Pending-Key Cleanup nach Pipeline-Sentinel fehlgeschlagen: %s", exc)


# ── Enumerations ───────────────────────────────────────────────────────────────


class StepType(str, Enum):
    """Semantischer Typ eines Pipeline-Steps – steuert Status-Messages und Logging."""

    READ = "read"
    SEARCH = "search"
    ANALYZE = "analyze"
    EXECUTE = "execute"
    NOTIFY = "notify"
    SUMMARIZE = "summarize"
    CONFIRM = "confirm"
    MODULE_CALL = "module_call"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    AWAITING_CONFIRMATION = "awaiting_confirmation"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"  # mindestens ein Step fehlgeschlagen, Rest OK


# ── Retry-Konfiguration ────────────────────────────────────────────────────────


class RetryPolicy(BaseModel):
    """Retry-Verhalten für einen Pipeline-Step."""

    max_retries: int = Field(default=2, ge=0, le=5)
    base_delay_s: float = Field(default=1.0, ge=0.0, le=30.0)
    exponential: bool = True
    retry_on_timeout: bool = True

    def delay_for(self, attempt: int) -> float:
        """Berechnet die Wartezeit vor dem n-ten Wiederholungsversuch."""
        if self.exponential:
            return self.base_delay_s * (2 ** attempt)
        return self.base_delay_s


_DEFAULT_RETRY = RetryPolicy()
_NO_RETRY = RetryPolicy(max_retries=0)


# ── Pipeline-Schritt-Schema ────────────────────────────────────────────────────


class PipelineStep(BaseModel):
    """Typisierter Pipeline-Schritt mit vollständigem Kontext."""

    step_id: str = Field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")
    type: StepType = StepType.MODULE_CALL
    module: str
    task: str
    depends_on: list[int] = Field(default_factory=list)
    requires_confirmation: bool = False
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_s: float = Field(default=120.0, gt=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("module")
    @classmethod
    def module_must_be_set(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("module darf nicht leer sein")
        return v

    @field_validator("task")
    @classmethod
    def task_must_be_set(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("task darf nicht leer sein")
        return v

    @classmethod
    def from_dict(cls, d: dict) -> "PipelineStep":
        """Erstellt einen PipelineStep aus einem rohen dict (z.B. aus LLM-Planner-Output)."""
        depends_on = d.get("depends_on")
        if depends_on is None:
            depends_on = []
        elif not isinstance(depends_on, list):
            depends_on = []
        return cls(
            module=str(d.get("module", "")).strip(),
            task=str(d.get("task", "")).strip(),
            depends_on=[int(i) for i in depends_on if isinstance(i, (int, float))],
            requires_confirmation=bool(d.get("requires_confirmation", False)),
            type=StepType(d["type"]) if "type" in d and d["type"] in StepType._value2member_map_ else StepType.MODULE_CALL,
        )


class StepResult(BaseModel):
    """Ergebnis eines ausgeführten Pipeline-Steps."""

    step_id: str
    step_index: int
    module: str
    status: StepStatus
    result: str = ""
    error: str | None = None
    duration_ms: float = 0.0
    retries_used: int = 0
    started_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None


class PipelineResult(BaseModel):
    """Gesamtergebnis einer Pipeline-Ausführung."""

    pipeline_id: str
    session_id: str
    status: PipelineStatus
    steps: list[StepResult] = Field(default_factory=list)
    summary: str = ""
    total_duration_ms: float = 0.0
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None
    error: str | None = None

    def successful_results(self) -> list[str]:
        """Alle erfolgreichen Step-Ergebnisse in Reihenfolge."""
        return [s.result for s in self.steps if s.status == StepStatus.COMPLETED]

    def to_markdown(self) -> str:
        """Formatiert das Ergebnis als Markdown für die Chat-Antwort."""
        lines: list[str] = []
        for _i, step in enumerate(self.steps):
            if step.status == StepStatus.COMPLETED:
                lines.append(f"**{step.module}:**\n{step.result}")
            elif step.status == StepStatus.FAILED:
                lines.append(f"**{step.module} – Fehler:**\n{step.error or 'Unbekannter Fehler'}")
            elif step.status == StepStatus.SKIPPED:
                lines.append(f"**{step.module}:** Übersprungen.")
        return "\n\n".join(lines) if lines else self.summary


# ── Topologische Sortierhilfe ──────────────────────────────────────────────────


def _build_execution_groups(steps: list[PipelineStep]) -> list[list[int]]:
    """
    Topologische Sortierung der Steps anhand ihrer depends_on-Listen.

    Gibt Gruppen zurück, die sicher parallel ausgeführt werden können.
    Falls ein Zyklus entdeckt wird → sequenzieller Fallback.
    """
    n = len(steps)
    in_degree: list[int] = [0] * n
    dependents: list[list[int]] = [[] for _ in range(n)]

    for i, step in enumerate(steps):
        for dep in step.depends_on:
            if dep == i:
                continue
            if not (0 <= dep < n):
                logger.warning(
                    "Step %d '%s' hat ungültige depends_on=%d (gültig: 0..%d) – Abhängigkeit wird ignoriert",
                    i,
                    getattr(step, "step_id", "?"),
                    dep,
                    n - 1,
                )
                continue
            in_degree[i] += 1
            dependents[dep].append(i)

    has_explicit_deps = any(s.depends_on for s in steps)
    if not has_explicit_deps:
        return [[i] for i in range(n)]

    groups: list[list[int]] = []
    ready = [i for i in range(n) if in_degree[i] == 0]
    visited = 0
    while ready:
        groups.append(ready)
        visited += len(ready)
        next_ready: list[int] = []
        for idx in ready:
            for dep in dependents[idx]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    next_ready.append(dep)
        ready = next_ready

    if visited < n:
        logger.warning("Pipeline depends_on enthält Zyklen – Fallback auf sequenziell.")
        return [[i] for i in range(n)]

    return groups


# ── Pipeline Engine ────────────────────────────────────────────────────────────


class PipelineEngine:
    """
    Typisierte, fehlertolerante Pipeline-Ausführungsmaschine.

    Ersetzt den fragilen String-basierten run_pipeline()-Stack.
    Alle Steps sind Pydantic-validiert, jeder Step hat Retry-Logik,
    strukturierte Events werden emittiert, Checkpoints gehen nach Redis.
    """

    def __init__(self) -> None:
        self._registry_cache: dict[str, Any] | None = None

    async def execute(
        self,
        steps: list[PipelineStep],
        session_id: str,
        pipeline_id: str | None = None,
        *,
        auto_confirm: bool = False,
        skip_on_error: bool = False,
        confirmed_indices: set[int] | None = None,
        completed_results: dict[int, StepResult] | None = None,
    ) -> PipelineResult:
        """
        Führt eine validierte Step-Liste aus.

        Args:
            steps: Typisierte Pipeline-Schritte (bereits validiert)
            session_id: Session-ID für Events und Status-Bus
            pipeline_id: Optionale ID (wird generiert falls None). Wenn ein Checkpoint
                für diese ID existiert, wird die Pipeline fortgesetzt (Resume-Modus)
            auto_confirm: Bestätigung für gefährliche Steps automatisch erteilen
            skip_on_error: Fehlgeschlagene Steps überspringen statt Pipeline abbrechen

        Pre-Flight Confirmation:
            Wenn auto_confirm=False und irgendein Step requires_confirmation=True hat,
            wird die Pipeline VOR dem ersten Step pausiert (PipelineStatus.AWAITING_CONFIRMATION),
            ein op_journal-Pending-Entry wird erstellt und ein Checkpoint gespeichert.
            Fortsetzung via resume(pipeline_id, session_id).
        """
        from core.pipeline_events import emit_pipeline_event, PipelineEvent

        pipeline_id = pipeline_id or f"pipe_{uuid.uuid4().hex[:12]}"
        start_time = time.monotonic()
        confirmed = set(confirmed_indices or set())
        step_results: dict[int, StepResult] = dict(completed_results or {})

        # Pre-Flight Confirmation Gate: pausiere vor dem ersten NOCH NICHT bestätigten
        # requires_confirmation-Step. Jeder solche Step wird einzeln bestätigt
        # (step-weiser Resume akkumuliert confirmed_indices) — eine Bestätigung
        # autorisiert NICHT die ganze Pipeline. Bei auto_confirm=True komplett übersprungen.
        if not auto_confirm and not confirmed:
            awaiting_idx = next(
                (
                    i for i, s in enumerate(steps)
                    if s.requires_confirmation
                ),
                None,
            )
            if awaiting_idx is not None:
                return await self._pause_for_confirmation(
                    steps, session_id, pipeline_id, awaiting_idx,
                    confirmed_indices=confirmed,
                )

        result = PipelineResult(
            pipeline_id=pipeline_id,
            session_id=session_id,
            status=PipelineStatus.RUNNING,
        )
        if step_results:
            result.steps.extend(
                step_results[i] for i in sorted(step_results)
            )

        # Initialer Checkpoint mit Steps (für späteres Resume)
        await self._checkpoint(pipeline_id, session_id, result, steps=steps)

        await emit_pipeline_event(PipelineEvent.pipeline_created(
            pipeline_id=pipeline_id,
            session_id=session_id,
            step_count=len(steps),
        ))

        # Topologische Gruppen für parallele Ausführung
        groups = _build_execution_groups(steps)
        pause_before_idx = None
        if not auto_confirm and confirmed:
            pause_before_idx = next(
                (
                    i for i, s in enumerate(steps)
                    if s.requires_confirmation and i not in confirmed
                ),
                None,
            )

        try:
            for group in groups:
                if pause_before_idx is not None and pause_before_idx in group:
                    return await self._pause_for_confirmation(
                        steps,
                        session_id,
                        pipeline_id,
                        pause_before_idx,
                        confirmed_indices=confirmed,
                        prior_result=result,
                    )

                pending_group = [i for i in group if i not in step_results]
                if not pending_group:
                    continue

                if len(pending_group) == 1:
                    idx = pending_group[0]
                    sr = await self._execute_step(
                        steps[idx], idx, step_results, session_id,
                        auto_confirm=auto_confirm or idx in confirmed,
                    )
                    step_results[idx] = sr
                    result.steps.append(sr)
                else:
                    # Parallele Ausführung innerhalb einer Gruppe.
                    # return_exceptions=True: Exceptions werden als Werte zurückgegeben,
                    # nicht propagiert – jeder Step wird einzeln ausgewertet.
                    raw_group_results = await asyncio.gather(
                        *[
                            self._execute_step(
                                steps[i], i, step_results, session_id,
                                auto_confirm=auto_confirm or i in confirmed,
                            )
                            for i in pending_group
                        ],
                        return_exceptions=True,
                    )
                    for i, raw_sr in zip(pending_group, raw_group_results, strict=False):
                        if isinstance(raw_sr, BaseException):
                            sr = StepResult(
                                step_id=steps[i].step_id,
                                step_index=i,
                                module=steps[i].module,
                                status=StepStatus.FAILED,
                                error=str(raw_sr),
                            )
                            logger.error(
                                "Pipeline paralleler Step %d ('%s') Exception: %s",
                                i + 1, steps[i].module, raw_sr,
                            )
                        else:
                            sr = raw_sr
                        step_results[i] = sr
                        result.steps.append(sr)

                # Nach jeder Gruppe: Checkpoint in Redis
                await self._checkpoint(pipeline_id, session_id, result)

                # Fehler-Propagation: Wenn Step fehlschlug und kein skip_on_error
                last_group_results = [step_results[i] for i in pending_group]
                failed = [sr for sr in last_group_results if sr.status == StepStatus.FAILED]
                if failed and not skip_on_error:
                    logger.warning(
                        "Pipeline '%s' abgebrochen: %d Step(s) in Gruppe fehlgeschlagen.",
                        pipeline_id,
                        len(failed),
                    )
                    result.error = f"Step fehlgeschlagen: {failed[0].error}"
                    break  # Status wird nach der Schleife einmalig gesetzt

        except asyncio.CancelledError:
            # CancelledError ist BaseException, nicht Exception (Python 3.8+).
            # Muss explizit behandelt werden, sonst bleibt die Pipeline
            # geisterhaft als RUNNING in Redis hängen.
            logger.info("Pipeline '%s' abgebrochen (Client-Disconnect/Cancel).", pipeline_id)
            result.status = PipelineStatus.FAILED
            result.error = "Abgebrochen"
            try:
                await self._checkpoint(pipeline_id, session_id, result)
            except _PIPELINE_RECOVERABLE_EXCEPTIONS as ckpt_exc:
                logger.debug("Final-Checkpoint nach Cancel fehlgeschlagen: %s", ckpt_exc)
            await emit_pipeline_event(PipelineEvent.pipeline_failed(
                pipeline_id=pipeline_id, session_id=session_id, error="cancelled",
            ))
            raise

        except Exception as exc:
            logger.error("Pipeline '%s' unerwarteter Fehler: %s", pipeline_id, exc, exc_info=True)
            result.status = PipelineStatus.FAILED
            result.error = str(exc)

        # Status nach der Schleife einmalig bestimmen (verhindert redundante Überschreibungen)
        if result.status == PipelineStatus.RUNNING:
            any_failed = any(sr.status == StepStatus.FAILED for sr in result.steps)
            all_completed = all(
                sr.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                for sr in result.steps
            )
            if any_failed:
                result.status = PipelineStatus.PARTIAL
            elif all_completed:
                result.status = PipelineStatus.COMPLETED
            else:
                result.status = PipelineStatus.PARTIAL

        result.completed_at = datetime.now(timezone.utc).isoformat()
        result.total_duration_ms = (time.monotonic() - start_time) * 1000

        await emit_pipeline_event(
            PipelineEvent.pipeline_completed(pipeline_id, session_id, result.status.value)
            if result.status in (PipelineStatus.COMPLETED, PipelineStatus.PARTIAL)
            else PipelineEvent.pipeline_failed(pipeline_id, session_id, result.error or "")
        )

        await self._checkpoint(pipeline_id, session_id, result)
        return result

    async def _execute_step(
        self,
        step: PipelineStep,
        idx: int,
        prior_results: dict[int, StepResult],
        session_id: str,
        *,
        auto_confirm: bool = False,
    ) -> StepResult:
        """Führt einen einzelnen Step mit Retry-Logik aus."""
        from core.pipeline_events import emit_pipeline_event, PipelineEvent
        from core import status_bus

        sr = StepResult(
            step_id=step.step_id,
            step_index=idx,
            module=step.module,
            status=StepStatus.RUNNING,
        )

        await emit_pipeline_event(PipelineEvent.step_started(
            step_id=step.step_id,
            session_id=session_id,
            module=step.module,
            idx=idx,
        ))

        # Task mit Kontext aus Abhängigkeiten anreichern
        full_task = self._build_task_with_context(step, idx, prior_results)

        # Modulagent laden
        agent = self._get_module_agent(step.module)
        if agent is None:
            sr.status = StepStatus.FAILED
            sr.error = f"Modul '{step.module}' nicht gefunden in der Registry."
            await emit_pipeline_event(PipelineEvent.step_failed(
                step_id=step.step_id,
                session_id=session_id,
                module=step.module,
                error=sr.error,
            ))
            return sr

        # Status-Message an UI
        await status_bus.emit(session_id, f"Pipeline: {step.module} ({idx + 1})…")

        # Retry-Loop
        last_error: str | None = None
        step_start = time.monotonic()
        for attempt in range(step.retry_policy.max_retries + 1):
            if attempt > 0:
                delay = step.retry_policy.delay_for(attempt - 1)
                logger.info(
                    "Pipeline Step %d/%s Wiederholungsversuch %d/%d (Wartezeit: %.1fs)…",
                    idx + 1,
                    step.module,
                    attempt,
                    step.retry_policy.max_retries,
                    delay,
                )
                await asyncio.sleep(delay)

            try:
                response, _did_compact = await asyncio.wait_for(
                    agent.invoke(
                        message=full_task,
                        session_id=session_id,
                        confirmed=auto_confirm,
                    ),
                    timeout=step.timeout_s,
                )
                # Der Sub-Agent hat vor einem gefährlichen Tool pausiert und den
                # Safeguard-Sentinel zurückgegeben. In einer Pipeline gibt es keinen
                # interaktiven Resume-Pfad — der Sentinel würde sonst roh in den
                # Output leaken und der pausierte Agent die Session ~300s blockieren.
                # Daher: pausierten Zustand bereinigen und Step sauber abbrechen.
                if _is_safeguard_sentinel(response):
                    await _release_paused_subagent(session_id)
                    sr.status = StepStatus.FAILED
                    sr.error = (
                        "Schritt benötigt eine Tool-Bestätigung, die in einer "
                        "automatischen Pipeline nicht eingeholt werden kann. "
                        "Führe die Aktion einzeln (nicht als Pipeline) aus."
                    )
                    sr.retries_used = attempt
                    sr.duration_ms = (time.monotonic() - step_start) * 1000
                    await emit_pipeline_event(PipelineEvent.step_failed(
                        step_id=step.step_id,
                        session_id=session_id,
                        module=step.module,
                        error=sr.error,
                    ))
                    return sr
                sr.result = str(response)
                sr.status = StepStatus.COMPLETED
                sr.retries_used = attempt
                sr.duration_ms = (time.monotonic() - step_start) * 1000
                sr.completed_at = datetime.now(timezone.utc).isoformat()
                # Compaction-Summary persistieren, sonst geht sie zwischen
                # Pipeline-Steps verloren und der nächste Step sieht den
                # ungekürzten Context → Token-Limit-Überschreitung.
                if _did_compact and hasattr(agent, "get_last_compaction_summary"):
                    _summary = agent.get_last_compaction_summary()
                    if _summary:
                        try:
                            from core.redis_client import get_redis

                            await get_redis().store_chat_message(
                                session_id=session_id,
                                role="system_compaction",
                                content=_summary,
                            )
                        except _PIPELINE_RECOVERABLE_EXCEPTIONS as exc:
                            logger.debug(
                                "Compaction-Summary konnte nicht persistiert werden: %s",
                                exc,
                            )
                await emit_pipeline_event(PipelineEvent.step_completed(
                    step_id=step.step_id,
                    session_id=session_id,
                    module=step.module,
                    duration_ms=sr.duration_ms,
                ))
                return sr

            except asyncio.TimeoutError:
                last_error = f"Timeout nach {step.timeout_s:.0f}s"
                logger.warning(
                    "Pipeline Step %d/%s Timeout (Versuch %d)",
                    idx + 1, step.module, attempt + 1,
                )
                if not step.retry_policy.retry_on_timeout:
                    break

            except Exception as exc:
                last_error = str(exc)
                logger.warning(
                    "Pipeline Step %d/%s Fehler (Versuch %d): %s",
                    idx + 1, step.module, attempt + 1, exc,
                )

        # Alle Versuche fehlgeschlagen
        sr.status = StepStatus.FAILED
        sr.error = last_error or "Unbekannter Fehler"
        sr.duration_ms = (time.monotonic() - step_start) * 1000
        sr.completed_at = datetime.now(timezone.utc).isoformat()
        sr.retries_used = step.retry_policy.max_retries

        await emit_pipeline_event(PipelineEvent.step_failed(
            step_id=step.step_id,
            session_id=session_id,
            module=step.module,
            error=sr.error,
        ))
        return sr

    def _build_task_with_context(
        self,
        step: PipelineStep,
        idx: int,
        prior_results: dict[int, StepResult],
    ) -> str:
        """Reichert den Task-String mit Ergebnissen aus Abhängigkeits-Steps an."""
        task = step.task
        dependency_indices = step.depends_on or sorted(i for i in prior_results if i < idx)
        dep_parts: list[str] = []
        for dep_idx in dependency_indices:
            if dep_idx in prior_results and prior_results[dep_idx].result and prior_results[dep_idx].status == StepStatus.COMPLETED:
                dep_parts.append(f"[{prior_results[dep_idx].module}]: {prior_results[dep_idx].result}")
        if dep_parts:
            task += "\n\nVorherige Ergebnisse als Kontext:\n" + "\n\n".join(dep_parts)
        return task

    def _get_module_agent(self, module: str):
        """Lädt den Agent für ein Modul aus der Registry."""
        try:
            from agents.orchestrator import get_orchestrator
            orch = get_orchestrator()
            if orch is None:
                return None
            return orch.registry.get_agent(module)
        except Exception as exc:
            logger.warning("Konnte Agent für Modul '%s' nicht laden: %s", module, exc)
            return None

    async def _checkpoint(
        self,
        pipeline_id: str,
        session_id: str,
        result: PipelineResult,
        steps: list[PipelineStep] | None = None,
        confirmed_indices: set[int] | None = None,
    ) -> None:
        """Schreibt einen Checkpoint in Redis für Resume-Support.

        Bei nachfolgenden Updates werden die originalen Steps aus dem bestehenden
        Checkpoint übernommen (read-modify-write), damit resume() sie rekonstruieren kann.
        """
        try:
            import json
            from core.redis_client import get_redis
            key = f"ninko:pipeline:checkpoint:{pipeline_id}"
            payload: dict[str, Any] = {}
            existing_raw = await get_redis().connection.get(key)
            if existing_raw:
                try:
                    payload = json.loads(existing_raw)
                    if not isinstance(payload, dict):
                        payload = {}
                except Exception:
                    payload = {}
            payload["result"] = result.model_dump()
            payload["session_id"] = session_id
            if steps is not None:
                payload["steps"] = [s.model_dump() for s in steps]
            if confirmed_indices is not None:
                payload["confirmed_indices"] = sorted(confirmed_indices)
            await get_redis().connection.set(key, json.dumps(payload), ex=3600)
        except Exception as exc:
            logger.debug("Checkpoint für Pipeline '%s' fehlgeschlagen: %s", pipeline_id, exc)

    async def _load_checkpoint(self, pipeline_id: str) -> dict[str, Any]:
        """Lädt den Checkpoint einer Pipeline aus Redis. Gibt {} zurück wenn nicht vorhanden."""
        try:
            import json
            from core.redis_client import get_redis
            raw = await get_redis().connection.get(f"ninko:pipeline:checkpoint:{pipeline_id}")
            if not raw:
                return {}
            try:
                data = json.loads(raw)
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}
        except Exception as exc:
            logger.debug("Checkpoint-Load für Pipeline '%s' fehlgeschlagen: %s", pipeline_id, exc)
            return {}

    async def _has_checkpoint(self, pipeline_id: str) -> bool:
        return bool(await self._load_checkpoint(pipeline_id))

    async def _pause_for_confirmation(
        self,
        steps: list[PipelineStep],
        session_id: str,
        pipeline_id: str,
        step_idx: int,
        confirmed_indices: set[int] | None = None,
        prior_result: PipelineResult | None = None,
    ) -> PipelineResult:
        """Pausiert die Pipeline VOR der Ausführung und erstellt einen Pending-Confirmation-Eintrag."""
        from core.pipeline_events import emit_pipeline_event, PipelineEvent
        from core.operation_journal import get_operation_journal

        first_step = steps[step_idx]
        result = prior_result or PipelineResult(
            pipeline_id=pipeline_id,
            session_id=session_id,
            status=PipelineStatus.AWAITING_CONFIRMATION,
        )
        result.status = PipelineStatus.AWAITING_CONFIRMATION
        result.steps.append(StepResult(
            step_id=first_step.step_id,
            step_index=step_idx,
            module=first_step.module,
            status=StepStatus.AWAITING_CONFIRMATION,
            error=f"Bestätigung erforderlich: {first_step.module}",
        ))

        op_journal = get_operation_journal()
        await op_journal.create_pending(
            session_id=session_id,
            text=(
                f"Pipeline '{pipeline_id}' wartet auf Bestätigung für "
                f"Step {step_idx + 1}/{len(steps)}: {first_step.module} – "
                f"{first_step.task[:200]}"
            ),
            category="STATE_CHANGING",
            rationale=f"Pipeline-Step '{first_step.module}' verlangt explizite Bestätigung",
            source="pipeline_safeguard",
            module=first_step.module,
            metadata={
                "pipeline_id": pipeline_id,
                "step_count": len(steps),
                "awaiting_step_index": step_idx,
            },
        )

        await self._checkpoint(
            pipeline_id, session_id, result, steps=steps,
            confirmed_indices=confirmed_indices or set(),
        )

        await emit_pipeline_event(PipelineEvent.pipeline_awaiting_confirmation(
            pipeline_id=pipeline_id,
            session_id=session_id,
            step_id=first_step.step_id,
            module=first_step.module,
            step_count=len(steps),
        ))

        logger.info(
            "Pipeline '%s' pausiert vor Step %d/%d (%s) – User-Bestätigung erforderlich.",
            pipeline_id, step_idx + 1, len(steps), first_step.module,
        )
        return result

    async def resume(
        self,
        pipeline_id: str,
        session_id: str,
        *,
        auto_confirm: bool = False,
    ) -> PipelineResult:
        """Setzt eine pausierte Pipeline nach User-Bestätigung fort.

        Step-weise: bestätigt NUR den zuletzt wartenden Step (akkumuliert in
        confirmed_indices im Checkpoint) und ruft execute() erneut auf. Enthält die
        Pipeline weitere requires_confirmation-Steps, pausiert sie erneut
        (Status AWAITING_CONFIRMATION) — eine Bestätigung autorisiert nie die
        gesamte Pipeline.

        auto_confirm=True erzwingt (rückwärtskompatibel) die Ausführung aller Steps
        ohne weiteres Gate — nur für vertrauenswürdige/Test-Kontexte.
        """
        from core.pipeline_events import emit_pipeline_event, PipelineEvent

        checkpoint = await self._load_checkpoint(pipeline_id)
        if not checkpoint:
            raise ValueError(f"Kein Checkpoint für Pipeline '{pipeline_id}'")
        steps_raw = checkpoint.get("steps", [])
        if not steps_raw:
            raise ValueError(
                f"Checkpoint für Pipeline '{pipeline_id}' enthält keine Steps "
                f"(zu alt oder von älterer Engine-Version erstellt)"
            )
        try:
            steps = [PipelineStep.model_validate(s) for s in steps_raw]
        except Exception as exc:
            raise ValueError(f"Checkpoint-Steps für Pipeline '{pipeline_id}' ungültig: {exc}") from exc

        # Bisher bestätigte Indizes + den nun bestätigten wartenden Step übernehmen.
        confirmed = set(checkpoint.get("confirmed_indices", []) or [])
        awaiting = checkpoint.get("result", {}).get("steps", [])
        for sr in awaiting:
            if sr.get("status") == StepStatus.AWAITING_CONFIRMATION.value:
                confirmed.add(int(sr.get("step_index", -1)))
        confirmed.discard(-1)
        completed_results: dict[int, StepResult] = {}
        for sr in awaiting:
            try:
                step_result = StepResult.model_validate(sr)
            except Exception:
                continue
            if step_result.status in (StepStatus.COMPLETED, StepStatus.SKIPPED):
                completed_results[step_result.step_index] = step_result

        await emit_pipeline_event(PipelineEvent.pipeline_resumed(pipeline_id, session_id))
        return await self.execute(
            steps, session_id, pipeline_id=pipeline_id,
            auto_confirm=auto_confirm, confirmed_indices=confirmed,
            completed_results=completed_results,
        )

    # ── Validation-Hilfsmethoden ─────────────────────────────────────────────

    @staticmethod
    def validate_steps_from_dicts(
        raw_steps: list[dict],
        valid_module_names: set[str],
        utility_modules: frozenset[str] | None = None,
        utility_mentioned: set[str] | None = None,
        core_always_modules: frozenset[str] | None = None,
        max_steps: int = 6,
    ) -> list[PipelineStep]:
        """
        Validiert eine Liste von rohen Step-Dicts gegen die Registry.

        - Unbekannte Module werden verworfen
        - Utility-Module ohne explizite Erwähnung werden verworfen
        - Leere module/task-Felder werden verworfen
        - Maximal max_steps Schritte

        Returns: Liste valider PipelineStep-Objekte
        """
        utility_modules = utility_modules or frozenset()
        utility_mentioned = utility_mentioned or set()
        core_always_modules = core_always_modules or frozenset()

        valid: list[PipelineStep] = []
        for raw in raw_steps:
            try:
                step = PipelineStep.from_dict(raw)
            except (ValueError, Exception) as exc:
                logger.warning("PipelineStep Validierungsfehler: %s – Step verworfen", exc)
                continue

            if step.module not in valid_module_names:
                logger.warning("Unbekanntes Modul '%s' – Step verworfen", step.module)
                continue

            if (
                step.module in utility_modules
                and step.module not in utility_mentioned
                and step.module not in core_always_modules
            ):
                logger.warning(
                    "Utility-Modul '%s' nicht explizit erwähnt – Step verworfen",
                    step.module,
                )
                continue

            valid.append(step)
            if len(valid) >= max_steps:
                break

        return valid


# ── Singleton ──────────────────────────────────────────────────────────────────

_engine: PipelineEngine | None = None


def get_pipeline_engine() -> PipelineEngine:
    """Gibt die globale PipelineEngine-Instanz zurück (lazy init)."""
    global _engine
    if _engine is None:
        _engine = PipelineEngine()
    return _engine
