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
    security_finding_update,
    security_findings_list,
    security_scan_start,
    security_scan_status,
    security_target_resolve,
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
