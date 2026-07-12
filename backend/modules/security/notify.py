"""Security Core — Notification-Fanout.

Nutzt AlertStateManager (core.alert_state) fuer Dedupe-/Cooldown-Bookkeeping —
dieselbe Infrastruktur, die Ninko bereits fuer Infra-Alerts (Kubernetes,
Proxmox, ...) nutzt. Verhindert Benachrichtigungs-Spam: pro (Target, Scanner)
hoechstens eine Notification innerhalb des Cooldown-Fensters, auch wenn
derselbe Scan wiederholt (z.B. per Scheduler) laeuft — neue Findings im
selben Cooldown-Fenster werden im Alert-State aktualisiert, lösen aber keine
weitere Benachrichtigung aus.

BEKANNTE MVP-LIMITATION: Der eigentliche Versand ueber konkrete Kanaele
(Telegram/E-Mail/Teams/...) ist NICHT automatisch verdrahtet — Ninko hat
aktuell keine generische Kanal-Praeferenz-Registry ("sende an alle
konfigurierten Kanaele" existiert nicht, siehe project_ninko_arch.md).
notify_scan_completed() liefert einen strukturierten Hinweis (should_notify +
Zusammenfassung), den der Security Orchestrator Agent oder ein Workflow-
Schritt gezielt an einen vom Nutzer genannten Kanal weiterreichen kann
(security_notify_channel-Tool, delegiert an call_module_agent).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from core.alert_state import get_alert_manager

from .models import Finding, FindingStatus, ScanRun, Severity

logger = logging.getLogger("ninko.modules.security.notify")

_NOTIFY_SEVERITIES = (Severity.CRITICAL, Severity.HIGH)
_SUPPRESSED_STATUSES = (FindingStatus.FALSE_POSITIVE, FindingStatus.RISK_ACCEPTED, FindingStatus.RESOLVED)


@dataclass
class ScanNotificationResult:
    should_notify: bool
    summary: str
    critical_count: int
    high_count: int


async def notify_scan_completed(run: ScanRun, findings: list[Finding]) -> ScanNotificationResult:
    """Bewertet, ob ueber diesen Scan-Run benachrichtigt werden soll (neue,
    nicht unterdrueckte critical/high Findings), unter Dedupe/Cooldown via
    AlertStateManager. Sendet selbst NICHTS — siehe Modul-Docstring."""
    relevant = [
        f for f in findings
        if f.severity in _NOTIFY_SEVERITIES and f.status not in _SUPPRESSED_STATUSES
    ]
    if not relevant:
        return ScanNotificationResult(should_notify=False, summary="", critical_count=0, high_count=0)

    critical_count = sum(1 for f in relevant if f.severity == Severity.CRITICAL)
    high_count = sum(1 for f in relevant if f.severity == Severity.HIGH)
    summary = (
        f"Security-Scan ({run.scanner_id}) auf Target {run.target_id}: "
        f"{critical_count} critical, {high_count} high Finding(s)."
    )

    alert_id = f"security:{run.target_id}:{run.scanner_id}"
    mgr = get_alert_manager()
    should_notify = await mgr.should_notify(alert_id)
    await mgr.record(
        alert_id,
        module="security",
        severity="critical" if critical_count else "warning",
        summary=summary,
        resource=run.target_id,
    )
    if should_notify:
        await mgr.record_notification(alert_id)
    else:
        # Kein Notify-Slot verbraucht (should_notify war bereits False) — nichts freizugeben.
        logger.info("Security-Notification fuer %s unterdrueckt (Cooldown aktiv).", alert_id)

    return ScanNotificationResult(
        should_notify=should_notify, summary=summary, critical_count=critical_count, high_count=high_count,
    )
