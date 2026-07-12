"""Unit-Tests fuer die 5 Security-Audit-Workflows (Task 8)."""

from __future__ import annotations

import pytest

from modules.security.models import (
    ScannerCategory, ScannerDefinition, ScanRunStatus, SecurityTarget, Severity, TargetType,
)
from modules.security.policy import PolicyViolation
from modules.security.scanner_adapter import NormalizedFinding, ScannerExecutionResult, ValidationResult
from modules.security.scanner_registry import ScannerRegistry
from modules.security.workflows import SECURITY_WORKFLOWS, get_workflow, run_security_workflow

pytestmark = pytest.mark.unit


class _FakeAdapter:
    def __init__(self, scanner_id, findings=None):
        self.scanner_id = scanner_id
        self._findings = findings or []
        self.execute_called = False

    def validate_target(self, target, profile, parameters):
        return ValidationResult(valid=True)

    def build_execution_spec(self, target, profile, parameters):
        from modules.security.scanner_adapter import ExecutionSpec

        return ExecutionSpec(scanner_id=self.scanner_id, container_image="fake:1", command=["fake"])

    async def execute(self, execution_spec, context):
        self.execute_called = True
        return ScannerExecutionResult(scanner_id=self.scanner_id, exit_code=0, stdout="{}")

    def parse_results(self, result):
        return self._findings


def _definition(scanner_id, target_types, category=ScannerCategory.CONTAINER_SUPPLY_CHAIN):
    return ScannerDefinition(
        id=scanner_id, name=scanner_id, category=category, container_image="fake:1",
        supported_target_types=target_types,
    )


@pytest.fixture
def fake_registry(monkeypatch):
    registry = ScannerRegistry()
    monkeypatch.setattr("modules.security.workflows.get_scanner_registry", lambda: registry)
    monkeypatch.setattr("modules.security.policy.get_scanner_registry", lambda: registry)
    monkeypatch.setattr("modules.security.scan_service.get_scanner_registry", lambda: registry)
    yield registry


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


def _target(**kw):
    defaults = {"name": "t", "target_type": TargetType.CONTAINER_IMAGE, "locator": "img:1"}
    defaults.update(kw)
    return SecurityTarget(**defaults)


# ── Statische Workflow-Definitionen ──────────────────────────────────────


def test_five_workflows_defined():
    assert len(SECURITY_WORKFLOWS) == 5


def test_get_workflow_unknown_raises():
    with pytest.raises(ValueError):
        get_workflow("does-not-exist")


def test_get_workflow_returns_matching_definition():
    wf = get_workflow("container_image_audit")
    assert wf.id == "container_image_audit"
    assert TargetType.CONTAINER_IMAGE in wf.target_types


def test_ai_platform_audit_only_uses_garak_intrusive():
    wf = get_workflow("ai_platform_audit")
    assert wf.preferred_scanner_ids == ["garak"]


# ── run_security_workflow ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_rejects_incompatible_target_type(fake_registry, security_db):
    target = await security_db.create_target(
        SecurityTarget(name="t", target_type=TargetType.URL, locator="https://example.com")
    )
    with pytest.raises(PolicyViolation):
        await run_security_workflow("container_image_audit", target=target)


@pytest.mark.asyncio
async def test_workflow_runs_single_compatible_scanner(fake_registry, security_db):
    adapter = _FakeAdapter("trivy", findings=[])
    fake_registry.register(_definition("trivy", [TargetType.CONTAINER_IMAGE]), adapter)
    target = await security_db.create_target(_target())

    result = await run_security_workflow("container_image_audit", target=target)
    assert result.executed_scanner_ids == ["trivy"]
    assert result.skipped_scanner_ids == []
    assert adapter.execute_called is True


@pytest.mark.asyncio
async def test_workflow_skips_unregistered_scanner(fake_registry, security_db):
    target = await security_db.create_target(_target())
    result = await run_security_workflow("container_image_audit", target=target)
    assert result.executed_scanner_ids == []
    assert result.steps[0].skipped_reason == "Scanner nicht registriert"


@pytest.mark.asyncio
async def test_workflow_skips_scanner_outside_target_allowlist(fake_registry, security_db):
    fake_registry.register(
        _definition("gitleaks", [TargetType.GIT_REPOSITORY], ScannerCategory.SECRET_SCANNING),
        _FakeAdapter("gitleaks"),
    )
    fake_registry.register(
        _definition("checkov", [TargetType.GIT_REPOSITORY], ScannerCategory.IAC), _FakeAdapter("checkov")
    )
    fake_registry.register(
        _definition("kubelinter", [TargetType.GIT_REPOSITORY], ScannerCategory.KUBERNETES),
        _FakeAdapter("kubelinter"),
    )
    target = await security_db.create_target(
        SecurityTarget(
            name="repo", target_type=TargetType.GIT_REPOSITORY, locator="https://x.com/r.git",
            allowed_scanners=["gitleaks"],  # nur gitleaks erlaubt, checkov/kubelinter nicht
        )
    )
    result = await run_security_workflow("git_repository_audit", target=target)
    assert result.executed_scanner_ids == ["gitleaks"]
    assert set(result.skipped_scanner_ids) == {"checkov", "kubelinter"}


@pytest.mark.asyncio
async def test_workflow_multi_scanner_runs_all_compatible(fake_registry, security_db):
    for sid in ("nmap", "testssl", "nuclei"):
        fake_registry.register(
            _definition(sid, [TargetType.HOSTNAME], ScannerCategory.NETWORK), _FakeAdapter(sid)
        )
    target = await security_db.create_target(
        SecurityTarget(name="host", target_type=TargetType.HOSTNAME, locator="example.com")
    )
    result = await run_security_workflow("external_service_audit", target=target)
    assert set(result.executed_scanner_ids) == {"nmap", "testssl", "nuclei"}


@pytest.mark.asyncio
async def test_workflow_total_findings_aggregates_across_steps(fake_registry, security_db):
    fake_registry.register(
        _definition("trivy", [TargetType.CONTAINER_IMAGE]),
        _FakeAdapter("trivy", findings=[
            NormalizedFinding(rule_id="CVE-1", title="A", severity=Severity.HIGH),
        ]),
    )
    target = await security_db.create_target(_target())
    result = await run_security_workflow("container_image_audit", target=target)
    assert result.total_findings == 1


@pytest.mark.asyncio
async def test_workflow_intrusive_scanner_pauses_for_approval(fake_registry, security_db, mock_redis):
    from unittest.mock import patch

    fake_registry.register(
        _definition("garak", [TargetType.OPENAI_COMPATIBLE_API], ScannerCategory.AI_LLM),
        _FakeAdapter("garak"),
    )
    target = await security_db.create_target(
        SecurityTarget(name="llm", target_type=TargetType.OPENAI_COMPATIBLE_API, locator="http://litellm:4000")
    )

    with patch("core.redis_client.get_redis", return_value=mock_redis):
        result = await run_security_workflow("ai_platform_audit", target=target)

    assert result.executed_scanner_ids == ["garak"]
    run = result.steps[0].run
    assert run.status == ScanRunStatus.WAITING_FOR_APPROVAL
