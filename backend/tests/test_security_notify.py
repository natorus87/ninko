"""Unit-Tests fuer Notification-Fanout (Task 12)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from modules.security.models import Finding, FindingStatus, ScanRun, Severity
from modules.security.notify import notify_scan_completed

pytestmark = pytest.mark.unit


def _run(**kw) -> ScanRun:
    defaults = {"target_id": "target-1", "scanner_id": "trivy", "profile_id": "passive"}
    defaults.update(kw)
    return ScanRun(**defaults)


def _finding(severity, status=FindingStatus.NEW, **kw) -> Finding:
    defaults = {
        "scan_run_id": "run-1", "target_id": "target-1", "fingerprint": "fp", "scanner_id": "trivy",
        "title": "X", "severity": severity, "original_severity": severity, "status": status,
    }
    defaults.update(kw)
    return Finding(**defaults)


def _mock_alert_manager():
    mgr = AsyncMock()
    mgr.should_notify = AsyncMock(return_value=True)
    mgr.record = AsyncMock(return_value={})
    mgr.record_notification = AsyncMock(return_value={})
    return mgr


@pytest.mark.asyncio
async def test_no_relevant_findings_never_calls_alert_manager():
    findings = [_finding(Severity.LOW), _finding(Severity.INFO)]
    with patch("modules.security.notify.get_alert_manager") as mock_get_mgr:
        result = await notify_scan_completed(_run(), findings)
    assert result.should_notify is False
    mock_get_mgr.assert_not_called()


@pytest.mark.asyncio
async def test_critical_finding_triggers_notification_when_not_in_cooldown():
    mgr = _mock_alert_manager()
    findings = [_finding(Severity.CRITICAL)]
    with patch("modules.security.notify.get_alert_manager", return_value=mgr):
        result = await notify_scan_completed(_run(), findings)
    assert result.should_notify is True
    assert result.critical_count == 1
    mgr.record_notification.assert_awaited_once()


@pytest.mark.asyncio
async def test_cooldown_suppresses_notification_but_still_records_state():
    mgr = _mock_alert_manager()
    mgr.should_notify = AsyncMock(return_value=False)
    findings = [_finding(Severity.HIGH)]
    with patch("modules.security.notify.get_alert_manager", return_value=mgr):
        result = await notify_scan_completed(_run(), findings)
    assert result.should_notify is False
    mgr.record.assert_awaited_once()  # State wird trotzdem aktualisiert
    mgr.record_notification.assert_not_awaited()  # aber keine Notification "verbraucht"


@pytest.mark.asyncio
async def test_resolved_and_false_positive_findings_are_excluded():
    findings = [
        _finding(Severity.CRITICAL, status=FindingStatus.RESOLVED),
        _finding(Severity.CRITICAL, status=FindingStatus.FALSE_POSITIVE),
        _finding(Severity.CRITICAL, status=FindingStatus.RISK_ACCEPTED),
    ]
    with patch("modules.security.notify.get_alert_manager") as mock_get_mgr:
        result = await notify_scan_completed(_run(), findings)
    assert result.should_notify is False
    mock_get_mgr.assert_not_called()


@pytest.mark.asyncio
async def test_medium_and_low_severity_never_trigger_notification():
    findings = [_finding(Severity.MEDIUM), _finding(Severity.LOW)]
    with patch("modules.security.notify.get_alert_manager") as mock_get_mgr:
        result = await notify_scan_completed(_run(), findings)
    assert result.should_notify is False
    mock_get_mgr.assert_not_called()


@pytest.mark.asyncio
async def test_summary_mentions_counts_and_scanner():
    mgr = _mock_alert_manager()
    findings = [_finding(Severity.CRITICAL), _finding(Severity.CRITICAL), _finding(Severity.HIGH)]
    with patch("modules.security.notify.get_alert_manager", return_value=mgr):
        result = await notify_scan_completed(_run(scanner_id="nuclei"), findings)
    assert result.critical_count == 2
    assert result.high_count == 1
    assert "nuclei" in result.summary


@pytest.mark.asyncio
async def test_alert_id_scoped_to_target_and_scanner():
    mgr = _mock_alert_manager()
    findings = [_finding(Severity.CRITICAL)]
    with patch("modules.security.notify.get_alert_manager", return_value=mgr):
        await notify_scan_completed(_run(target_id="t-42", scanner_id="trivy"), findings)
    call_args = mgr.record.call_args
    alert_id = call_args[0][0]
    assert alert_id == "security:t-42:trivy"
