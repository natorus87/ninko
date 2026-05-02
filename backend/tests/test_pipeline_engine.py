"""
Tests für die neue PipelineEngine.

Abgedeckte Szenarien:
  1. Single-Step Modul-Aufruf (Erfolg)
  2. Multi-Step sequenzielle Pipeline (Erfolg)
  3. Pipeline mit Notification-Step (telegram)
  4. Fehlgeschlagener Step → Retry → Erfolg
  5. LLM-Planner liefert ungültiges JSON → deterministischer Fallback
  6. LLM-Planner liefert unbekanntes Tool/Modul → verworfen
  7. SafeGuard requires_confirmation → Step übersprungen ohne auto_confirm
  8. Pipeline läuft nach auto_confirm weiter
  9. Utility-Modul nicht explizit erwähnt → verworfen
 10. Kein Fallback in freien ReAct-Modus bei Pipeline-Fehler

Alle Tests sind Unit-Tests ohne echte Netzwerkaufrufe (Mocking via unittest.mock).
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.pipeline_engine import (
    PipelineEngine,
    PipelineStep,
    PipelineStatus,
    StepStatus,
    StepType,
    RetryPolicy,
    _build_execution_groups,
    get_pipeline_engine,
)
from core.pipeline_events import (
    PipelineEvent,
    PipelineEventType,
    emit_pipeline_event,
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


# ── Test 7: SafeGuard requires_confirmation → Step übersprungen ───────────────


@pytest.mark.asyncio
async def test_confirmation_required_skips_step_without_auto_confirm():
    """Step mit requires_confirmation=True wird ohne auto_confirm übersprungen."""
    step = make_step("kubernetes", "Lösche alle Pods", requires_confirmation=True)
    engine = PipelineEngine()

    events_captured: list[PipelineEvent] = []

    async def capture(event: PipelineEvent):
        events_captured.append(event)

    on_pipeline_event(capture)
    try:
        with (
            patch.object(engine, "_get_module_agent", return_value=make_mock_agent()),
            patch("core.status_bus.emit", new=AsyncMock()),
        ):
            result = await engine.execute([step], session_id="test-session-7", auto_confirm=False)
    finally:
        remove_pipeline_listener(capture)

    assert result.steps[0].status == StepStatus.SKIPPED
    event_types = [e.type for e in events_captured]
    assert PipelineEventType.CONFIRMATION_REQUIRED in event_types


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
    with pytest.raises(Exception):
        PipelineStep.from_dict({"module": "", "task": "irgendwas"})


# ── Test 13: Singleton get_pipeline_engine ───────────────────────────────────


def test_get_pipeline_engine_singleton():
    """get_pipeline_engine() gibt immer dieselbe Instanz zurück."""
    engine1 = get_pipeline_engine()
    engine2 = get_pipeline_engine()
    assert engine1 is engine2
