"""Integrationstests fuer scan_service.py (Task 4): voller Scan-Flow mit
Fake-Adapter (kein echter K8s-Call), isolierter SQLite-DB, gemocktem Redis.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from modules.security.executor import ScanExecutionError, ScanTimeoutError
from modules.security.models import (
    ScanProfileKind,
    ScannerCategory,
    ScannerDefinition,
    ScanRunStatus,
    SecurityTarget,
    Severity,
    TargetType,
)
from modules.security.policy import PolicyViolation
from modules.security.scanner_adapter import NormalizedFinding, ScannerExecutionResult, ValidationResult
from modules.security.scanner_registry import ScannerRegistry

pytestmark = pytest.mark.unit


class _FakeAdapter:
    """Vollstaendig kontrollierbarer Fake-Adapter fuer Integrationstests."""

    def __init__(self, scanner_id: str, *, findings=None, raise_on_execute=None, invalid_target=False,
                 raw_stdout: str | None = None):
        self.scanner_id = scanner_id
        self._findings = findings or []
        self._raise_on_execute = raise_on_execute
        self._invalid_target = invalid_target
        self._raw_stdout = raw_stdout
        self.execute_called = False

    def validate_target(self, target, profile, parameters):
        if self._invalid_target:
            return ValidationResult(valid=False, errors=["fake validation error"])
        return ValidationResult(valid=True)

    def build_execution_spec(self, target, profile, parameters):
        from modules.security.scanner_adapter import ExecutionSpec

        return ExecutionSpec(scanner_id=self.scanner_id, container_image="fake:1", command=["fake", "scan"])

    async def execute(self, execution_spec, context):
        self.execute_called = True
        if self._raise_on_execute:
            raise self._raise_on_execute
        return ScannerExecutionResult(scanner_id=self.scanner_id, exit_code=0, stdout=self._raw_stdout or "{}")

    def parse_results(self, result):
        if self._raw_stdout is not None and self._raw_stdout != "{}":
            raise ValueError("simulierter Parse-Fehler")
        return self._findings


def _target(**overrides) -> SecurityTarget:
    defaults = {"name": "test-image", "target_type": TargetType.CONTAINER_IMAGE, "locator": "registry.local/foo:1.0"}
    defaults.update(overrides)
    return SecurityTarget(**defaults)


def _definition(scanner_id: str, target_types=None) -> ScannerDefinition:
    return ScannerDefinition(
        id=scanner_id, name=scanner_id, category=ScannerCategory.CONTAINER_SUPPLY_CHAIN,
        container_image="fake:1", supported_target_types=target_types or [TargetType.CONTAINER_IMAGE],
    )


@pytest.fixture
def fake_registry(monkeypatch):
    """Isolierte ScannerRegistry, in scan_service UND policy gepatcht."""
    registry = ScannerRegistry()

    def _patch(scanner_id, adapter, target_types=None):
        registry.register(_definition(scanner_id, target_types), adapter)

    monkeypatch.setattr("modules.security.scan_service.get_scanner_registry", lambda: registry)
    monkeypatch.setattr("modules.security.policy.get_scanner_registry", lambda: registry)
    yield _patch, registry


@pytest.fixture
def security_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import core.config as core_config

    core_config._settings = None
    from modules.security import db as security_db_module

    security_db_module._db_path = None
    security_db_module._init_event = None
    yield security_db_module
    security_db_module._db_path = None
    security_db_module._init_event = None
    core_config._settings = None


@pytest.fixture
def redis_patch(mock_redis):
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        yield mock_redis


# ── start_scan: Fehlerfaelle ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_scan_unknown_target_raises(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    with pytest.raises(PolicyViolation, match="Unbekanntes Security-Target"):
        await start_scan(target_id="does-not-exist", scanner_id="trivy", profile_id="passive")


@pytest.mark.asyncio
async def test_start_scan_unknown_scanner_raises(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan
    from modules.security.scanner_registry import UnknownScannerError

    target = await security_db.create_target(_target())
    with pytest.raises(UnknownScannerError):
        await start_scan(target_id=target.id, scanner_id="does-not-exist", profile_id="passive")


# ── start_scan: erfolgreicher Passive-Flow ────────────────────────────────


@pytest.mark.asyncio
async def test_start_scan_passive_completes_and_persists_findings(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, registry = fake_registry
    adapter = _FakeAdapter(
        "trivy",
        findings=[
            NormalizedFinding(rule_id="CVE-1", title="X", severity=Severity.HIGH, resource_identifier="libfoo"),
        ],
    )
    patch_fn("trivy", adapter)
    target = await security_db.create_target(_target())

    run = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive", requested_by="alice")

    assert run.status == ScanRunStatus.COMPLETED
    assert run.finding_count == 1
    assert adapter.execute_called is True

    findings = await security_db.list_findings(target_id=target.id)
    assert len(findings) == 1
    assert findings[0].severity == Severity.HIGH
    assert findings[0].original_severity == Severity.HIGH


@pytest.mark.asyncio
async def test_start_scan_intrusive_pauses_for_approval_and_does_not_execute(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, registry = fake_registry
    adapter = _FakeAdapter("nuclei", findings=[])
    definition = ScannerDefinition(
        id="nuclei", name="nuclei", category=ScannerCategory.WEB, container_image="fake:1",
        risk_level=ScanProfileKind.INTRUSIVE, supported_target_types=[TargetType.URL],
    )
    registry.register(definition, adapter)

    target = await security_db.create_target(
        SecurityTarget(name="web", target_type=TargetType.URL, locator="https://example.com")
    )

    run = await start_scan(target_id=target.id, scanner_id="nuclei", profile_id="intrusive", requested_by="alice")

    assert run.status == ScanRunStatus.WAITING_FOR_APPROVAL
    assert adapter.execute_called is False
    redis_patch.connection.set.assert_called_once()  # Approval-Request wurde angelegt


@pytest.mark.asyncio
async def test_start_scan_rejects_wrong_target_type(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, _ = fake_registry
    patch_fn("trivy", _FakeAdapter("trivy"))
    target = await security_db.create_target(
        SecurityTarget(name="web", target_type=TargetType.URL, locator="https://example.com")
    )
    with pytest.raises(PolicyViolation, match="unterstuetzt"):
        await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")


# ── resume_after_approval ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resume_after_approval_without_approval_raises(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import resume_after_approval, start_scan

    patch_fn, registry = fake_registry
    definition = ScannerDefinition(
        id="nuclei", name="nuclei", category=ScannerCategory.WEB, container_image="fake:1",
        risk_level=ScanProfileKind.INTRUSIVE, supported_target_types=[TargetType.URL],
    )
    registry.register(definition, _FakeAdapter("nuclei"))
    target = await security_db.create_target(
        SecurityTarget(name="web", target_type=TargetType.URL, locator="https://example.com")
    )
    run = await start_scan(target_id=target.id, scanner_id="nuclei", profile_id="intrusive")

    redis_patch.connection.get.return_value = None  # keine Freigabe erteilt
    with pytest.raises(PolicyViolation):
        await resume_after_approval(run.id)


@pytest.mark.asyncio
async def test_resume_after_approval_executes_once_approved(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import resume_after_approval, start_scan

    patch_fn, registry = fake_registry
    adapter = _FakeAdapter(
        "nuclei", findings=[NormalizedFinding(rule_id="R1", title="X", severity=Severity.MEDIUM)]
    )
    definition = ScannerDefinition(
        id="nuclei", name="nuclei", category=ScannerCategory.WEB, container_image="fake:1",
        risk_level=ScanProfileKind.INTRUSIVE, supported_target_types=[TargetType.URL],
    )
    registry.register(definition, adapter)
    target = await security_db.create_target(
        SecurityTarget(name="web", target_type=TargetType.URL, locator="https://example.com")
    )
    run = await start_scan(target_id=target.id, scanner_id="nuclei", profile_id="intrusive")

    import json
    import time

    approved_payload = {
        "approval_id": "a1", "scan_run_id": run.id, "target_id": target.id, "scanner_id": "nuclei",
        "profile_id": "intrusive", "scope_summary": "x", "requested_by": "alice",
        "requested_at": time.time(), "expires_at": time.time() + 900, "status": "approved",
        "decided_by": "bob", "decided_at": time.time(),
    }
    redis_patch.connection.get.return_value = json.dumps(approved_payload)

    completed = await resume_after_approval(run.id)
    assert completed.status == ScanRunStatus.COMPLETED
    assert adapter.execute_called is True


# ── Fehlerpfade waehrend Ausfuehrung ────────────────────────────────────


@pytest.mark.asyncio
async def test_start_scan_policy_blocked_when_adapter_rejects_target(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, _ = fake_registry
    patch_fn("trivy", _FakeAdapter("trivy", invalid_target=True))
    target = await security_db.create_target(_target())

    run = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run.status == ScanRunStatus.POLICY_BLOCKED
    assert "fake validation error" in run.error


@pytest.mark.asyncio
async def test_start_scan_timeout_marks_run_timed_out(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, _ = fake_registry
    patch_fn("trivy", _FakeAdapter("trivy", raise_on_execute=ScanTimeoutError("timeout")))
    target = await security_db.create_target(_target())

    run = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run.status == ScanRunStatus.TIMED_OUT


@pytest.mark.asyncio
async def test_start_scan_execution_error_marks_run_failed(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, _ = fake_registry
    patch_fn("trivy", _FakeAdapter("trivy", raise_on_execute=ScanExecutionError("boom")))
    target = await security_db.create_target(_target())

    run = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run.status == ScanRunStatus.FAILED
    assert "boom" in run.error


@pytest.mark.asyncio
async def test_start_scan_parse_error_marks_run_failed(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, _ = fake_registry
    patch_fn("trivy", _FakeAdapter("trivy", raw_stdout="not-empty-triggers-fake-parse-error"))
    target = await security_db.create_target(_target())

    run = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run.status == ScanRunStatus.FAILED
    assert "Parse-Fehler" in run.error


# ── Dedupe/Resolve-when-absent ueber zwei Runs ────────────────────────────


@pytest.mark.asyncio
async def test_second_scan_resolves_findings_absent_in_new_run(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import start_scan

    patch_fn, registry = fake_registry
    target = await security_db.create_target(_target())

    adapter1 = _FakeAdapter(
        "trivy",
        findings=[
            NormalizedFinding(rule_id="CVE-1", title="A", severity=Severity.HIGH, resource_identifier="libfoo"),
            NormalizedFinding(rule_id="CVE-2", title="B", severity=Severity.LOW, resource_identifier="libbar"),
        ],
    )
    patch_fn("trivy", adapter1)
    run1 = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run1.finding_count == 2

    # Zweiter Run findet nur noch CVE-1 -> CVE-2 muss resolved werden.
    adapter2 = _FakeAdapter(
        "trivy",
        findings=[NormalizedFinding(rule_id="CVE-1", title="A", severity=Severity.HIGH, resource_identifier="libfoo")],
    )
    registry._adapters["trivy"] = adapter2
    run2 = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run2.status == ScanRunStatus.COMPLETED

    findings = await security_db.list_findings(target_id=target.id)
    from modules.security.models import FindingStatus

    cve2 = next(f for f in findings if f.scanner_finding_id == "CVE-2")
    assert cve2.status == FindingStatus.RESOLVED
    cve1 = next(f for f in findings if f.scanner_finding_id == "CVE-1")
    assert cve1.status == FindingStatus.NEW
    assert cve1.occurrence_count == 2


# ── queue_scan / execute_queued_run (Task 10: Background-Task-Split) ──────


@pytest.mark.asyncio
async def test_queue_scan_creates_run_without_executing(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import queue_scan

    patch_fn, _ = fake_registry
    adapter = _FakeAdapter("trivy", findings=[])
    patch_fn("trivy", adapter)
    target = await security_db.create_target(_target())

    run = await queue_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run.status == ScanRunStatus.QUEUED
    assert adapter.execute_called is False


@pytest.mark.asyncio
async def test_execute_queued_run_runs_the_scan(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import execute_queued_run, queue_scan

    patch_fn, _ = fake_registry
    adapter = _FakeAdapter("trivy", findings=[])
    patch_fn("trivy", adapter)
    target = await security_db.create_target(_target())

    queued = await queue_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert adapter.execute_called is False

    completed = await execute_queued_run(queued.id)
    assert completed.status == ScanRunStatus.COMPLETED
    assert adapter.execute_called is True


@pytest.mark.asyncio
async def test_execute_queued_run_rejects_unknown_run(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import execute_queued_run

    with pytest.raises(PolicyViolation, match="Unbekannter Scan-Run"):
        await execute_queued_run("does-not-exist")


@pytest.mark.asyncio
async def test_execute_queued_run_rejects_already_executed_run(fake_registry, security_db, redis_patch):
    from modules.security.scan_service import execute_queued_run, queue_scan

    patch_fn, _ = fake_registry
    patch_fn("trivy", _FakeAdapter("trivy", findings=[]))
    target = await security_db.create_target(_target())

    queued = await queue_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    await execute_queued_run(queued.id)

    with pytest.raises(PolicyViolation, match="nicht QUEUED"):
        await execute_queued_run(queued.id)


@pytest.mark.asyncio
async def test_start_scan_still_fully_synchronous_after_refactor(fake_registry, security_db, redis_patch):
    """Regressionsschutz: start_scan() (Tool-/Scheduler-Pfad) muss weiterhin in
    einem einzigen await Ergebnis+Ausfuehrung liefern."""
    from modules.security.scan_service import start_scan

    patch_fn, _ = fake_registry
    adapter = _FakeAdapter("trivy", findings=[])
    patch_fn("trivy", adapter)
    target = await security_db.create_target(_target())

    run = await start_scan(target_id=target.id, scanner_id="trivy", profile_id="passive")
    assert run.status == ScanRunStatus.COMPLETED
    assert adapter.execute_called is True
