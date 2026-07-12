"""Unit-Tests fuer die Security-Core Agent-Tools (Task 4): ToolResponse-Huelle,
PolicyViolation wird nie als Exception durchgereicht, ungueltige Enum-Werte
werden sauber abgefangen.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from modules.security.models import FindingStatus
from modules.security.policy import PolicyViolation
from modules.security.tools import (
    security_finding_enrich,
    security_finding_update,
    security_findings_list,
    security_remediation_propose,
    security_report_generate,
    security_scan_start,
    security_scan_status,
    security_target_resolve,
    security_workflow_list,
    security_workflow_run,
)

pytestmark = pytest.mark.unit


def _ok(raw: str) -> dict:
    """ToolResponse.ok(dict).__str__() ist direkt json.dumps(data) — kein Envelope."""
    assert not raw.startswith("Error:"), raw
    return json.loads(raw)


def _fail(raw: str) -> str:
    """ToolResponse.fail(msg).__str__() ist 'Error: {msg}'."""
    assert raw.startswith("Error:"), raw
    return raw


@pytest.mark.asyncio
async def test_security_target_resolve_no_match_returns_failure():
    with patch("modules.security.tools.db.list_targets", AsyncMock(return_value=[])):
        raw = await security_target_resolve.ainvoke({"name_or_id": "does-not-exist"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_scan_start_surfaces_policy_violation_as_tool_failure():
    with patch(
        "modules.security.tools.start_scan", AsyncMock(side_effect=PolicyViolation("scope verletzt"))
    ):
        raw = await security_scan_start.ainvoke(
            {"target_id": "t1", "scanner_id": "trivy", "profile_id": "passive"}
        )
    result = _fail(raw)
    assert "scope verletzt" in result


@pytest.mark.asyncio
async def test_security_scan_status_unknown_run_returns_failure():
    with patch("modules.security.tools.db.get_scan_run", AsyncMock(return_value=None)):
        raw = await security_scan_status.ainvoke({"scan_run_id": "nope"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_findings_list_invalid_severity_returns_failure():
    raw = await security_findings_list.ainvoke({"severity": "not-a-severity"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_findings_list_invalid_status_returns_failure():
    raw = await security_findings_list.ainvoke({"status": "not-a-status"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_finding_update_invalid_status_returns_failure():
    raw = await security_finding_update.ainvoke({"finding_id": "f1", "status": "not-a-status"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_finding_update_unknown_finding_returns_failure():
    with patch("modules.security.tools.db.set_finding_status", AsyncMock(return_value=None)):
        raw = await security_finding_update.ainvoke({"finding_id": "nope", "status": "resolved"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_finding_update_success_returns_updated_finding():
    from modules.security.models import Finding, Severity

    updated = Finding(
        id="f1", scan_run_id="r1", target_id="t1", fingerprint="abc", scanner_id="trivy",
        title="X", severity=Severity.HIGH, original_severity=Severity.HIGH, status=FindingStatus.RESOLVED,
    )
    with patch("modules.security.tools.db.set_finding_status", AsyncMock(return_value=updated)):
        raw = await security_finding_update.ainvoke({"finding_id": "f1", "status": "resolved"})
    data = _ok(raw)
    assert data["status"] == "resolved"


@pytest.mark.asyncio
async def test_security_workflow_list_returns_all_five():
    raw = await security_workflow_list.ainvoke({})
    data = _ok(raw)
    assert len(data) == 5
    assert {"id", "name", "description", "target_types", "scanners"} <= set(data[0].keys())


@pytest.mark.asyncio
async def test_security_workflow_run_unknown_target_returns_failure():
    with patch("modules.security.tools.db.get_target", AsyncMock(return_value=None)):
        raw = await security_workflow_run.ainvoke({"workflow_id": "container_image_audit", "target_id": "nope"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_workflow_run_policy_violation_returns_failure():
    from modules.security.models import SecurityTarget, TargetType

    target = SecurityTarget(name="t", target_type=TargetType.URL, locator="https://example.com")
    with (
        patch("modules.security.tools.db.get_target", AsyncMock(return_value=target)),
        patch(
            "modules.security.tools.run_security_workflow",
            AsyncMock(side_effect=PolicyViolation("Target-Typ passt nicht")),
        ),
    ):
        raw = await security_workflow_run.ainvoke({"workflow_id": "container_image_audit", "target_id": "t1"})
    result = _fail(raw)
    assert "Target-Typ passt nicht" in result


@pytest.mark.asyncio
async def test_security_workflow_run_success_summarizes_steps():
    from types import SimpleNamespace

    from modules.security.models import SecurityTarget, TargetType

    target = SecurityTarget(name="t", target_type=TargetType.CONTAINER_IMAGE, locator="img:1")
    fake_run = SimpleNamespace(id="run-1", status=SimpleNamespace(value="completed"), finding_count=2)
    fake_result = SimpleNamespace(
        workflow_id="container_image_audit", target_id="t1", total_findings=2,
        steps=[SimpleNamespace(scanner_id="trivy", run=fake_run, skipped_reason=None)],
    )
    with (
        patch("modules.security.tools.db.get_target", AsyncMock(return_value=target)),
        patch("modules.security.tools.run_security_workflow", AsyncMock(return_value=fake_result)),
    ):
        raw = await security_workflow_run.ainvoke({"workflow_id": "container_image_audit", "target_id": "t1"})
    data = _ok(raw)
    assert data["total_findings"] == 2
    assert data["steps"][0]["scan_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_security_finding_enrich_unknown_finding_returns_failure():
    with patch(
        "modules.security.tools.enrich_finding", AsyncMock(side_effect=ValueError("Unbekanntes Finding: nope"))
    ):
        raw = await security_finding_enrich.ainvoke({"finding_id": "nope"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_finding_enrich_success_returns_enrichment():
    from modules.security.models import FindingEnrichment, Severity

    enrichment = FindingEnrichment(
        finding_id="f1", model="test-model", effective_severity=Severity.HIGH,
        confidence=0.8, false_positive_probability=0.1,
    )
    with patch("modules.security.tools.enrich_finding", AsyncMock(return_value=enrichment)):
        raw = await security_finding_enrich.ainvoke({"finding_id": "f1"})
    data = _ok(raw)
    assert data["effective_severity"] == "high"


@pytest.mark.asyncio
async def test_security_remediation_propose_returns_only_remediation_fields():
    from modules.security.models import FindingEnrichment, Severity

    enrichment = FindingEnrichment(
        finding_id="f1", model="test-model", effective_severity=Severity.HIGH,
        confidence=0.8, false_positive_probability=0.1,
        remediation_proposal="- do X", patch_proposal="diff --git a b", requires_human_review=True,
    )
    with patch("modules.security.tools.enrich_finding", AsyncMock(return_value=enrichment)):
        raw = await security_remediation_propose.ainvoke({"finding_id": "f1"})
    data = _ok(raw)
    assert data["remediation_proposal"] == "- do X"
    assert data["patch_proposal"] == "diff --git a b"
    assert data["requires_human_review"] is True
    assert "effective_severity" not in data  # nur Remediation-relevante Felder


@pytest.mark.asyncio
async def test_security_remediation_propose_unknown_finding_returns_failure():
    with patch(
        "modules.security.tools.enrich_finding", AsyncMock(side_effect=ValueError("Unbekanntes Finding: nope"))
    ):
        raw = await security_remediation_propose.ainvoke({"finding_id": "nope"})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_report_generate_requires_scope():
    raw = await security_report_generate.ainvoke({})
    _fail(raw)


@pytest.mark.asyncio
async def test_security_report_generate_groups_by_severity():
    from modules.security.models import Finding, Severity

    findings = [
        Finding(
            scan_run_id="r1", target_id="t1", fingerprint="fp1", scanner_id="trivy",
            title="Critical bug", severity=Severity.CRITICAL, original_severity=Severity.CRITICAL,
            cve="CVE-2024-1",
        ),
        Finding(
            scan_run_id="r1", target_id="t1", fingerprint="fp2", scanner_id="trivy",
            title="Low bug", severity=Severity.LOW, original_severity=Severity.LOW,
        ),
    ]
    with patch("modules.security.tools.db.list_findings", AsyncMock(return_value=findings)):
        raw = await security_report_generate.ainvoke({"target_id": "t1"})
    assert not raw.startswith("Error:")
    assert "CRITICAL" in raw
    assert "Critical bug" in raw
    assert "CVE-2024-1" in raw
    assert "LOW" in raw
