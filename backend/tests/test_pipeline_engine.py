"""
Tests für die neue PipelineEngine.

Abgedeckte Szenarien:
  1. Single-Step Modul-Aufruf (Erfolg)
  2. Multi-Step sequenzielle Pipeline (Erfolg)
  3. Pipeline mit Notification-Step (telegram)
  4. Fehlgeschlagener Step → Retry → Erfolg
  5. LLM-Planner liefert ungültiges JSON → deterministischer Fallback
  6. LLM-Planner liefert unbekanntes Tool/Modul → verworfen
  7. SafeGuard requires_confirmation → Pipeline pausiert (PLAN.md 1.4)
  7b. requires_confirmation an späterem Step → Pipeline pausiert davor
  7c. Kein requires_confirmation → keine Pause
  7d. auto_confirm=True → Pre-Flight-Gate übersprungen
  7e. Pause erzeugt op_journal Pending-Entry mit pipeline_id-Metadata
  7f. Pause speichert original-Steps im Checkpoint
  7g. resume() führt alle Steps mit auto_confirm=True aus
  7h. resume() mit unbekannter pipeline_id → ValueError
  7i. resume() überspringt Pre-Flight-Gate
  8. Pipeline läuft nach auto_confirm weiter
  9. Utility-Modul nicht explizit erwähnt → verworfen
 10. Kein Fallback in freien ReAct-Modus bei Pipeline-Fehler

Alle Tests sind Unit-Tests ohne echte Netzwerkaufrufe (Mocking via unittest.mock).
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from core.pipeline_engine import (
    PipelineEngine,
    PipelineResult,
    PipelineStep,
    PipelineStatus,
    StepStatus,
    RetryPolicy,
    _build_execution_groups,
    get_pipeline_engine,
)
from core.pipeline_events import (
    PipelineEvent,
    PipelineEventType,
    on_pipeline_event,
    remove_pipeline_listener,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_step(module: str, task: str, **kwargs) -> PipelineStep:
    return PipelineStep(module=module, task=task, **kwargs)


def make_mock_agent(response: str = "OK", raises: Exception | None = None):
    """Erstellt einen Mock-Agent der invoke() simuliert."""
    agent = MagicMock()
    if raises:
        agent.invoke = AsyncMock(side_effect=raises)
    else:
        agent.invoke = AsyncMock(return_value=(response, False))
    return agent


class FakeOperationJournal:
    def __init__(self) -> None:
        self.entries: dict[str, dict] = {}
        self.pending_by_session: dict[str, str] = {}

    async def create_pending(self, **kwargs) -> str:
        tx_id = f"tx_{len(self.entries) + 1}"
        entry = {
            "id": tx_id,
            "status": "pending_confirmation",
            "session_id": kwargs["session_id"],
            "source": kwargs["source"],
            "category": kwargs["category"],
            "module": kwargs.get("module") or "",
            "text": kwargs["text"],
            "rationale": kwargs["rationale"],
            "metadata": json.dumps(kwargs.get("metadata") or {}),
        }
        self.entries[tx_id] = entry
        self.pending_by_session[kwargs["session_id"]] = tx_id
        return tx_id

    async def get_pending_for_session(self, session_id: str) -> str | None:
        return self.pending_by_session.get(session_id)

    async def get(self, tx_id: str) -> dict:
        return self.entries.get(tx_id, {})

    async def clear_pending_for_session(self, session_id: str) -> None:
        self.pending_by_session.pop(session_id, None)


@contextmanager
def patch_engine_checkpoint(engine: PipelineEngine, store: dict[str, dict] | None = None):
    checkpoint_store = store if store is not None else {}

    async def checkpoint(
        pipeline_id: str,
        session_id: str,
        result: PipelineResult,
        *,
        steps: list[PipelineStep] | None = None,
    ) -> None:
        payload = {
            **checkpoint_store.get(pipeline_id, {}),
            "result": result.model_dump(),
            "session_id": session_id,
        }
        if steps is not None:
            payload["steps"] = [step.model_dump() for step in steps]
        checkpoint_store[pipeline_id] = payload

    async def load_checkpoint(pipeline_id: str) -> dict:
        return checkpoint_store.get(pipeline_id, {})

    async def has_checkpoint(pipeline_id: str) -> bool:
        return pipeline_id in checkpoint_store

    with (
        patch.object(engine, "_checkpoint", new=checkpoint),
        patch.object(engine, "_load_checkpoint", new=load_checkpoint),
        patch.object(engine, "_has_checkpoint", new=has_checkpoint),
    ):
        yield checkpoint_store


# ── Test 1: Single-Step Modul-Aufruf ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_single_step_success():
    """Single-Step Pipeline führt Modul erfolgreich aus."""
    step = make_step("kubernetes", "Prüfe Pod-Status im Namespace gitlab")
    engine = PipelineEngine()

    mock_agent = make_mock_agent("2 Pods running, 1 Pod pending")

    with (
        patch.object(engine, "_get_module_agent", return_value=mock_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.pipeline_engine.get_pipeline_engine", return_value=engine),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute([step], session_id="test-session-1")

    assert result.status == PipelineStatus.COMPLETED
    assert len(result.steps) == 1
    assert result.steps[0].status == StepStatus.COMPLETED
    assert "2 Pods running" in result.steps[0].result


# ── Test 2: Multi-Step sequenzielle Pipeline ──────────────────────────────────


@pytest.mark.asyncio
async def test_multi_step_sequential_success():
    """Zwei sequenzielle Steps: k8s → telegram."""
    steps = [
        make_step("kubernetes", "Prüfe Pod-Status im Namespace gitlab"),
        make_step("telegram", "Sende Status-Report"),
    ]
    engine = PipelineEngine()

    agents = {
        "kubernetes": make_mock_agent("1 Pod failing"),
        "telegram": make_mock_agent("Nachricht gesendet"),
    }

    def get_agent(module: str):
        return agents.get(module)

    with (
        patch.object(engine, "_get_module_agent", side_effect=get_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute(steps, session_id="test-session-2", auto_confirm=True)

    assert result.status == PipelineStatus.COMPLETED
    assert len(result.steps) == 2
    assert result.steps[0].status == StepStatus.COMPLETED
    assert result.steps[1].status == StepStatus.COMPLETED
    # Kontext-Propagation: telegram-Task sollte k8s-Ergebnis enthalten
    last_call = agents["telegram"].invoke.call_args
    assert "1 Pod failing" in last_call.kwargs.get("message", "")


# ── Test 3: Pipeline mit Notification-Step ────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_with_notification_step():
    """Kubernetes-Status → Analyse → Telegram-Benachrichtigung falls Problem."""
    steps = [
        make_step("kubernetes", "Prüfe alle Pods im Namespace gitlab auf Not-Ready"),
        make_step("telegram", "Sende Warnung wenn Pods nicht ready sind"),
    ]
    engine = PipelineEngine()

    agents = {
        "kubernetes": make_mock_agent("Pod 'gitlab-runner-xyz' ist NOT READY (CrashLoopBackOff)"),
        "telegram": make_mock_agent("Telegram-Nachricht erfolgreich gesendet"),
    }

    with (
        patch.object(engine, "_get_module_agent", side_effect=lambda m: agents.get(m)),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute(steps, session_id="test-session-3", auto_confirm=True)

    assert result.status == PipelineStatus.COMPLETED
    markdown = result.to_markdown()
    assert "kubernetes" in markdown.lower()
    assert "telegram" in markdown.lower()


# ── Test 4: Fehlgeschlagener Step → Retry → Erfolg ───────────────────────────


@pytest.mark.asyncio
async def test_step_retry_on_failure_then_success():
    """Step schlägt 1x fehl, dann Erfolg nach Retry."""
    call_count = 0

    async def flaky_invoke(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Temporärer Verbindungsfehler")
        return ("Erfolg nach Retry", False)

    step = make_step(
        "kubernetes",
        "Prüfe Pods",
        retry_policy=RetryPolicy(max_retries=2, base_delay_s=0.01, exponential=False),
    )
    engine = PipelineEngine()
    mock_agent = MagicMock()
    mock_agent.invoke = AsyncMock(side_effect=flaky_invoke)

    with (
        patch.object(engine, "_get_module_agent", return_value=mock_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute([step], session_id="test-session-4")

    assert result.status == PipelineStatus.COMPLETED
    assert result.steps[0].status == StepStatus.COMPLETED
    assert result.steps[0].retries_used == 1
    assert "Erfolg nach Retry" in result.steps[0].result


# ── Test 5: LLM-Planner liefert ungültiges JSON ───────────────────────────────


def test_validate_steps_rejects_invalid_json_output():
    """validate_steps_from_dicts() wirft keine Exception bei kaputter Eingabe."""
    garbage = [
        {"module": "", "task": ""},  # leer
        {"module": "bekanntes_modul", "task": ""},  # task leer
        {"no_module_key": "oops"},  # fehlendes Feld
    ]
    valid = PipelineEngine.validate_steps_from_dicts(
        garbage,
        valid_module_names={"bekanntes_modul"},
    )
    assert valid == []


# ── Test 6: LLM-Planner liefert unbekanntes Modul ────────────────────────────


def test_validate_steps_rejects_unknown_module():
    """Steps mit halluzinierten Modul-Namen werden verworfen."""
    steps_raw = [
        {"module": "kubernetes", "task": "Liste Pods auf"},
        {"module": "halluziniertes_modul_xyz", "task": "Tu irgendwas"},
        {"module": "telegram", "task": "Sende Nachricht"},
    ]
    valid = PipelineEngine.validate_steps_from_dicts(
        steps_raw,
        valid_module_names={"kubernetes", "telegram"},
    )
    assert len(valid) == 2
    assert all(s.module in {"kubernetes", "telegram"} for s in valid)


# ── Test 7: SafeGuard requires_confirmation → Pipeline pausiert ──────────────


@pytest.mark.asyncio
async def test_confirmation_required_pauses_pipeline_without_auto_confirm():
    """Pipeline mit requires_confirmation=True pausiert VOR dem ersten Step."""
    step = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    engine = PipelineEngine()

    events_captured: list[PipelineEvent] = []

    async def capture(event: PipelineEvent):
        events_captured.append(event)

    on_pipeline_event(capture)
    fake_journal = FakeOperationJournal()
    try:
        with (
            patch_engine_checkpoint(engine),
            patch("core.operation_journal.get_operation_journal", return_value=fake_journal),
            patch.object(engine, "_get_module_agent", return_value=make_mock_agent()) as get_agent,
            patch("core.status_bus.emit", new=AsyncMock()),
        ):
            result = await engine.execute([step], session_id="test-session-7", auto_confirm=False)
    finally:
        remove_pipeline_listener(capture)

    assert result.status == PipelineStatus.AWAITING_CONFIRMATION
    assert len(result.steps) == 1
    assert result.steps[0].status == StepStatus.AWAITING_CONFIRMATION
    assert result.steps[0].module == "kubernetes"
    get_agent.assert_not_called()
    event_types = [e.type for e in events_captured]
    assert PipelineEventType.PIPELINE_AWAITING_CONFIRMATION in event_types


# ── Test 7b: requires_confirmation nur an späterem Step → Pipeline pausiert ───


@pytest.mark.asyncio
async def test_confirmation_required_pauses_before_first_confirming_step():
    """Pausiert VOR dem ersten requires_confirmation=True Step; vorherige Steps laufen NICHT."""
    step1 = make_step("web_search", "Recherchiere X")
    step2 = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    step3 = make_step("telegram", "Benachrichtige")
    engine = PipelineEngine()

    events: list[PipelineEvent] = []

    async def capture(event: PipelineEvent):
        events.append(event)

    on_pipeline_event(capture)
    fake_journal = FakeOperationJournal()
    try:
        with (
            patch_engine_checkpoint(engine),
            patch("core.operation_journal.get_operation_journal", return_value=fake_journal),
            patch.object(engine, "_get_module_agent", return_value=make_mock_agent()) as get_agent,
            patch("core.status_bus.emit", new=AsyncMock()),
        ):
            result = await engine.execute(
                [step1, step2, step3], session_id="test-session-7b", auto_confirm=False,
            )
    finally:
        remove_pipeline_listener(capture)

    assert result.status == PipelineStatus.AWAITING_CONFIRMATION
    assert len(result.steps) == 1
    assert result.steps[0].module == "kubernetes"
    assert result.steps[0].step_index == 1
    get_agent.assert_not_called()
    assert PipelineEventType.PIPELINE_AWAITING_CONFIRMATION in [e.type for e in events]


# ── Test 7c: Kein requires_confirmation → keine Pause ─────────────────────────


@pytest.mark.asyncio
async def test_no_confirmation_required_runs_normally():
    """Pipeline ohne requires_confirmation läuft normal durch."""
    step = make_step("kubernetes", "Prüfe Pods")
    engine = PipelineEngine()
    mock_agent = make_mock_agent("Alles OK")

    with (
        patch.object(engine, "_get_module_agent", return_value=mock_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute([step], session_id="test-session-7c", auto_confirm=False)

    assert result.status == PipelineStatus.COMPLETED
    assert result.steps[0].status == StepStatus.COMPLETED


# ── Test 7d: Pre-Flight übersprungen wenn auto_confirm=True ─────────────────


@pytest.mark.asyncio
async def test_auto_confirm_bypasses_pre_flight_gate():
    """Mit auto_confirm=True läuft requires_confirmation-Step normal."""
    step = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    engine = PipelineEngine()
    mock_agent = make_mock_agent("Pods gelöscht")

    with (
        patch.object(engine, "_get_module_agent", return_value=mock_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute([step], session_id="test-session-7d", auto_confirm=True)

    assert result.status == PipelineStatus.COMPLETED
    assert result.steps[0].status == StepStatus.COMPLETED


# ── Test 7e: Pause erzeugt op_journal Pending-Entry mit pipeline_id-Metadata ─


@pytest.mark.asyncio
async def test_pause_creates_op_journal_pending_entry():
    """Pre-Flight-Pause erstellt op_journal-Entry mit source=pipeline_safeguard und metadata.pipeline_id."""
    step = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    engine = PipelineEngine()
    op_journal = FakeOperationJournal()

    with (
        patch_engine_checkpoint(engine),
        patch("core.operation_journal.get_operation_journal", return_value=op_journal),
        patch.object(engine, "_get_module_agent", return_value=make_mock_agent()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute(
            [step], session_id="tenant_x:session-7e", auto_confirm=False,
        )

    assert result.status == PipelineStatus.AWAITING_CONFIRMATION
    pending_tx_id = await op_journal.get_pending_for_session("tenant_x:session-7e")
    assert pending_tx_id is not None
    tx = await op_journal.get(pending_tx_id)
    assert tx.get("source") == "pipeline_safeguard"
    assert tx.get("module") == "kubernetes"
    meta = json.loads(tx.get("metadata") or "{}")
    assert meta.get("pipeline_id") == result.pipeline_id
    assert meta.get("step_count") == 1
    await op_journal.clear_pending_for_session("tenant_x:session-7e")


# ── Test 7f: Pause speichert original-Steps im Checkpoint (für resume) ────────


@pytest.mark.asyncio
async def test_pause_steps_in_checkpoint_for_resume():
    """Checkpoint enthält die original-Steps als JSON, damit resume() sie rekonstruieren kann."""
    step1 = make_step("web_search", "Recherchiere X")
    step2 = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    engine = PipelineEngine()
    fake_journal = FakeOperationJournal()
    checkpoint_store: dict[str, dict] = {}

    with (
        patch_engine_checkpoint(engine, checkpoint_store),
        patch("core.operation_journal.get_operation_journal", return_value=fake_journal),
        patch.object(engine, "_get_module_agent", return_value=make_mock_agent()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute(
            [step1, step2], session_id="test-session-7f", auto_confirm=False,
        )

    assert result.status == PipelineStatus.AWAITING_CONFIRMATION
    checkpoint = checkpoint_store[result.pipeline_id]
    assert "steps" in checkpoint
    assert len(checkpoint["steps"]) == 2
    assert checkpoint["steps"][0]["module"] == "web_search"
    assert checkpoint["steps"][1]["module"] == "kubernetes"
    assert checkpoint["steps"][1]["requires_confirmation"] is True


# ── Test 7g: resume() führt Pipeline ab Checkpoint mit auto_confirm=True aus ─


@pytest.mark.asyncio
async def test_resume_runs_remaining_steps_with_auto_confirm():
    """resume() lädt Checkpoint, führt alle Steps mit auto_confirm=True aus, kein erneuter Pause."""
    step1 = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    step2 = make_step("telegram", "Benachrichtige Admins")
    engine = PipelineEngine()

    mock_agent = make_mock_agent("OK")
    fake_journal = FakeOperationJournal()

    with (
        patch_engine_checkpoint(engine),
        patch("core.operation_journal.get_operation_journal", return_value=fake_journal),
        patch.object(engine, "_get_module_agent", return_value=mock_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        paused = await engine.execute(
            [step1, step2], session_id="test-session-7g", auto_confirm=False,
        )
        assert paused.status == PipelineStatus.AWAITING_CONFIRMATION

        result = await engine.resume(paused.pipeline_id, "test-session-7g", auto_confirm=True)

    assert result.status == PipelineStatus.COMPLETED
    assert len(result.steps) == 2
    assert all(s.status == StepStatus.COMPLETED for s in result.steps)


# ── Test 7h: resume() mit unbekannter pipeline_id → ValueError ───────────────


@pytest.mark.asyncio
async def test_resume_raises_value_error_for_unknown_pipeline():
    engine = PipelineEngine()
    with pytest.raises(ValueError, match="Kein Checkpoint"):
        await engine.resume("pipe_does_not_exist", "session-x")


# ── Test 7i: resume() überspringt Pre-Flight-Gate (is_resume=True) ───────────


@pytest.mark.asyncio
async def test_resume_bypasses_pre_flight_gate():
    """Auch wenn Steps requires_confirmation=True haben, läuft resume() durch."""
    step = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    engine = PipelineEngine()
    mock_agent = make_mock_agent("Gelöscht")
    fake_journal = FakeOperationJournal()

    with (
        patch_engine_checkpoint(engine),
        patch("core.operation_journal.get_operation_journal", return_value=fake_journal),
        patch.object(engine, "_get_module_agent", return_value=mock_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        paused = await engine.execute(
            [step], session_id="test-session-7i", auto_confirm=False,
        )
        assert paused.status == PipelineStatus.AWAITING_CONFIRMATION
        result = await engine.resume(paused.pipeline_id, "test-session-7i", auto_confirm=True)

    assert result.status == PipelineStatus.COMPLETED
    assert result.steps[0].status == StepStatus.COMPLETED


# ── Test 8: Pipeline läuft nach auto_confirm weiter ──────────────────────────


@pytest.mark.asyncio
async def test_pipeline_continues_with_auto_confirm():
    """Step mit requires_confirmation=True wird mit auto_confirm=True ausgeführt."""
    step = make_step(
        "kubernetes",
        "Starte rollendes Deployment-Restart",
        requires_confirmation=True,
    )
    engine = PipelineEngine()
    mock_agent = make_mock_agent("Restart erfolgreich")

    with (
        patch.object(engine, "_get_module_agent", return_value=mock_agent),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute([step], session_id="test-session-8", auto_confirm=True)

    assert result.steps[0].status == StepStatus.COMPLETED
    assert "Restart erfolgreich" in result.steps[0].result


# ── Test 9: Utility-Modul nicht explizit erwähnt → verworfen ─────────────────


def test_validate_steps_rejects_utility_module_not_mentioned():
    """telegram-Schritt wird verworfen, wenn nicht explizit in utility_mentioned."""
    steps_raw = [
        {"module": "kubernetes", "task": "Prüfe Pods"},
        {"module": "telegram", "task": "Sende Status"},
    ]
    valid = PipelineEngine.validate_steps_from_dicts(
        steps_raw,
        valid_module_names={"kubernetes", "telegram"},
        utility_modules=frozenset({"telegram", "email"}),
        utility_mentioned=set(),  # telegram wurde NICHT erwähnt
        core_always_modules=frozenset(),
    )
    assert len(valid) == 1
    assert valid[0].module == "kubernetes"


# ── Test 10: Kein freier ReAct-Fallback bei Pipeline-Fehler ──────────────────


@pytest.mark.asyncio
async def test_pipeline_failure_returns_structured_error_not_react():
    """Wenn alle Steps fehlschlagen, gibt engine ein PipelineResult mit PARTIAL zurück –
    kein freier ReAct-Loop, keine unbekannte Ausführung."""
    step = make_step(
        "kubernetes",
        "Führe unmögliche Aufgabe aus",
        retry_policy=RetryPolicy(max_retries=0),
    )
    engine = PipelineEngine()

    with (
        patch.object(engine, "_get_module_agent", return_value=make_mock_agent(raises=RuntimeError("Kritischer Fehler"))),
        patch("core.pipeline_events.emit_pipeline_event", new=AsyncMock()),
        patch("core.status_bus.emit", new=AsyncMock()),
    ):
        result = await engine.execute([step], session_id="test-session-10", skip_on_error=True)

    # Engine gibt strukturiertes Ergebnis zurück – kein Exception, kein ReAct
    assert result.status in (PipelineStatus.PARTIAL, PipelineStatus.FAILED)
    assert result.steps[0].status == StepStatus.FAILED
    assert "Kritischer Fehler" in (result.steps[0].error or "")
    # Wichtig: PipelineResult ist ein Pydantic-Objekt, kein String-Chaos
    assert isinstance(result.to_markdown(), str)


# ── Test 11: Topologische Sortierhilfe ───────────────────────────────────────


def test_build_execution_groups_sequential():
    """Ohne explizite depends_on → sequenzielle Gruppen."""
    steps = [
        PipelineStep(module="a", task="t"),
        PipelineStep(module="b", task="t"),
        PipelineStep(module="c", task="t"),
    ]
    groups = _build_execution_groups(steps)
    assert groups == [[0], [1], [2]]


def test_build_execution_groups_parallel():
    """Mit depends_on: steps 0+1 parallel, step 2 wartet auf beide."""
    steps = [
        PipelineStep(module="k8s", task="t", depends_on=[]),
        PipelineStep(module="pihole", task="t", depends_on=[]),
        PipelineStep(module="glpi", task="t", depends_on=[0, 1]),
    ]
    groups = _build_execution_groups(steps)
    assert len(groups) == 2
    # Gruppe 1 enthält beide unabhängigen Steps
    assert set(groups[0]) == {0, 1}
    # Gruppe 2 enthält den abhängigen Step
    assert groups[1] == [2]


# ── Test 12: PipelineStep.from_dict Validierung ───────────────────────────────


def test_pipeline_step_from_dict_valid():
    d = {"module": "kubernetes", "task": "Prüfe Pods", "depends_on": [0, 1]}
    step = PipelineStep.from_dict(d)
    assert step.module == "kubernetes"
    assert step.depends_on == [0, 1]


def test_pipeline_step_from_dict_empty_module_raises():
    with pytest.raises(ValidationError):
        PipelineStep.from_dict({"module": "", "task": "irgendwas"})


# ── Test 13: Singleton get_pipeline_engine ───────────────────────────────────


def test_get_pipeline_engine_singleton():
    """get_pipeline_engine() gibt immer dieselbe Instanz zurück."""
    engine1 = get_pipeline_engine()
    engine2 = get_pipeline_engine()
    assert engine1 is engine2


# ── Tests 14-16: Orchestrator Routing (_has_multistep_indicators) ─────────────


def _make_orch_for_routing():
    """Minimale OrchestratorAgent-Instanz für Routing-Tests (kein echter LLM)."""
    from agents.orchestrator import OrchestratorAgent

    registry = MagicMock()
    registry.list_modules.return_value = []
    registry.get_module.return_value = None
    orch = OrchestratorAgent.__new__(OrchestratorAgent)
    orch.registry = registry
    orch._routing_map = {}
    orch._routing_map_hash = ""
    return orch


def test_multistep_plain_und_with_two_qualified_modules_no_tier4():
    """Einfaches 'und' ohne Sequenzabsicht → KEIN Tier-4."""
    orch = _make_orch_for_routing()
    # licium score=3, knowledge_graph score=2 → beide qualifiziert (>=2)
    scores = {"licium": 3, "knowledge_graph": 2}
    assert orch._has_multistep_indicators(
        "Lies meine bestehenden Notizen und ingeste sie ins Ninko-Wiki", scores
    ) is False


def test_multistep_und_dann_with_two_qualified_modules_triggers_tier4():
    """Explizites 'und dann' zwischen zwei klar erkannten Modulen → Tier-4."""
    orch = _make_orch_for_routing()
    scores = {"licium": 3, "knowledge_graph": 2}
    assert orch._has_multistep_indicators(
        "Lies meine bestehenden Notizen und dann ingeste sie ins Ninko-Wiki", scores
    ) is True


def test_multistep_und_with_single_module_no_tier4():
    """Nur ein qualifiziertes Modul + 'und' → KEIN Tier-4 (Guard greift)."""
    orch = _make_orch_for_routing()
    scores = {"kubernetes": 4}
    assert orch._has_multistep_indicators(
        "Zeige alle Pods und Deployments", scores
    ) is False


def test_multistep_two_modules_no_und_no_pattern_no_tier4():
    """Zwei Modul-Treffer, aber kein 'und' und kein Sequenz-Wort → kein Tier-4."""
    orch = _make_orch_for_routing()
    scores = {"kubernetes": 2, "licium": 2}
    assert orch._has_multistep_indicators(
        "kubernetes licium status", scores
    ) is False


def test_multistep_explicit_pattern_still_works():
    """Explizites 'danach' löst Tier-4 wie bisher aus."""
    orch = _make_orch_for_routing()
    scores = {"kubernetes": 3, "telegram": 1}  # telegram ist Utility, Score>=1 reicht
    assert orch._has_multistep_indicators(
        "Prüfe alle K8s-Pods und benachrichtige mich danach per Telegram", scores
    ) is True
