"""Security Core — Agent-Tools.

Streng typisierte Werkzeuge fuer den Security Orchestrator Agent. Kein Tool
nimmt freien Shell-Text entgegen — Scanner-Aufrufe laufen ausschliesslich
ueber scan_service.start_scan(), das Policy Engine + Scanner Registry +
K8sJobExecutor durchsetzt.
"""

from __future__ import annotations

from langchain_core.tools import tool

from core.tool_schema import ToolResponse

from . import db
from .models import FindingStatus, Severity, TriggerType
from .policy import PolicyViolation
from .scan_service import resume_after_approval, start_scan

TOOL_REGISTRY_DEFAULTS = {"required_bins": (), "required_envs": ()}
TOOL_REGISTRY_OVERRIDES = {
    "security_target_resolve": {"readonly": True},
    "security_scan_status": {"readonly": True},
    "security_findings_list": {"readonly": True},
    "security_scan_start": {"tier": "WRITE_SYSTEM"},
    "security_scan_approve": {"tier": "WRITE_SYSTEM"},
    "security_finding_update": {"tier": "WRITE_DATA"},
}


@tool
async def security_target_resolve(name_or_id: str = "") -> str:
    """List all configured security scan targets, or resolve one exact target by
    name or ID. Use this before starting a scan to find the correct target_id."""
    targets = await db.list_targets()
    if name_or_id:
        matches = [t for t in targets if t.id == name_or_id or t.name.lower() == name_or_id.lower()]
        if not matches:
            return str(ToolResponse.fail(f"Kein Security-Target gefunden fuer: {name_or_id}"))
        return str(ToolResponse.ok(matches[0].model_dump(mode="json")))
    return str(ToolResponse.ok([t.model_dump(mode="json") for t in targets]))


@tool
async def security_scan_start(
    target_id: str, scanner_id: str, profile_id: str = "passive",
    severity_filter: list[str] | None = None, requested_by: str = "",
) -> str:
    """Start a security scan run against an existing, enabled SecurityTarget with a
    specific scanner and scan profile (passive/standard/intrusive). Intrusive
    profiles require explicit human approval before execution and can only be
    triggered manually — the run will pause in status 'waiting_for_approval'.
    Use security_target_resolve first to find a valid target_id."""
    parameters = {"severity_filter": severity_filter} if severity_filter else {}
    try:
        run = await start_scan(
            target_id=target_id, scanner_id=scanner_id, profile_id=profile_id,
            parameters=parameters, requested_by=requested_by, trigger_type=TriggerType.MANUAL,
        )
    except PolicyViolation as exc:
        return str(ToolResponse.fail(str(exc)))
    return str(ToolResponse.ok(run.model_dump(mode="json")))


@tool
async def security_scan_approve(scan_run_id: str, approved_by: str = "") -> str:
    """Resume a scan run that is waiting for human approval (intrusive profile).
    Must only be called after a human has explicitly reviewed and approved the
    scan plan via decide_approval — this tool does NOT grant the approval itself,
    it only resumes execution once approval already exists."""
    try:
        run = await resume_after_approval(scan_run_id)
    except PolicyViolation as exc:
        return str(ToolResponse.fail(str(exc)))
    return str(ToolResponse.ok(run.model_dump(mode="json")))


@tool
async def security_scan_status(scan_run_id: str) -> str:
    """Get the current status of a security scan run (queued, running, completed,
    waiting_for_approval, failed, etc.)."""
    run = await db.get_scan_run(scan_run_id)
    if run is None:
        return str(ToolResponse.fail(f"Unbekannter Scan-Run: {scan_run_id}"))
    return str(ToolResponse.ok(run.model_dump(mode="json")))


@tool
async def security_findings_list(
    target_id: str = "", scan_run_id: str = "", severity: str = "", status: str = "",
) -> str:
    """List normalized security findings, optionally filtered by target, scan run,
    severity (info/low/medium/high/critical), or status (new/active/resolved/...)."""
    try:
        sev = Severity(severity) if severity else None
        st = FindingStatus(status) if status else None
    except ValueError as exc:
        return str(ToolResponse.fail(f"Ungueltiger Filter-Wert: {exc}"))
    findings = await db.list_findings(
        target_id=target_id or None, scan_run_id=scan_run_id or None, severity=sev, status=st,
    )
    return str(ToolResponse.ok([f.model_dump(mode="json") for f in findings]))


@tool
async def security_finding_update(finding_id: str, status: str, remediation: str = "") -> str:
    """Update a finding's triage status: acknowledged, in_progress, mitigated,
    resolved, false_positive, risk_accepted, or reopened. This is a human triage
    decision — never mark a finding as resolved or false_positive automatically
    without the user explicitly confirming it."""
    try:
        new_status = FindingStatus(status)
    except ValueError:
        return str(ToolResponse.fail(f"Ungueltiger Status: {status}"))
    updated = await db.set_finding_status(finding_id, new_status, remediation=remediation or None)
    if updated is None:
        return str(ToolResponse.fail(f"Unbekanntes Finding: {finding_id}"))
    return str(ToolResponse.ok(updated.model_dump(mode="json")))
