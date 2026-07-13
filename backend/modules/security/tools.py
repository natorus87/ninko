"""Security Core — Agent-Tools.

Streng typisierte Werkzeuge fuer den Security Orchestrator Agent. Kein Tool
nimmt freien Shell-Text entgegen — Scanner-Aufrufe laufen ausschliesslich
ueber scan_service.start_scan(), das Policy Engine + Scanner Registry +
K8sJobExecutor durchsetzt.
"""

from __future__ import annotations

from langchain_core.tools import tool

from core.auth import get_current_tenant_id
from core.tool_schema import ToolResponse

from . import db
from .enrichment import enrich_finding
from .models import FindingStatus, Severity, TriggerType
from .policy import PolicyViolation
from .scan_service import resume_after_approval, start_scan
from .workflows import SECURITY_WORKFLOWS, run_security_workflow


def _tenant_id() -> str:
    """Liest den Tenant der aktuellen Anfrage aus demselben Contextvar, den auch
    main.py pro Request setzt (siehe core.auth.set_current_tenant_id) — das
    generische Ninko-Muster, um innerhalb eines @tool ohne HTTP-Request-Objekt
    an den Tenant zu kommen (siehe core_tools.py/script_tools.py/connections.py).
    Ohne das wuerden alle Security-Tools mit tenant_id="" gegen die DB laufen und
    damit jedes ueber die UI (tenant_id="default") angelegte Target/Finding/Run
    unsichtbar bleiben."""
    return get_current_tenant_id() or "default"


TOOL_REGISTRY_DEFAULTS = {"required_bins": (), "required_envs": ()}
TOOL_REGISTRY_OVERRIDES = {
    "security_target_resolve": {"readonly": True},
    "security_scan_status": {"readonly": True},
    "security_findings_list": {"readonly": True},
    "security_workflow_list": {"readonly": True},
    "security_report_generate": {"readonly": True},
    "security_scan_start": {"tier": "WRITE_SYSTEM"},
    "security_scan_approve": {"tier": "WRITE_SYSTEM"},
    "security_workflow_run": {"tier": "WRITE_SYSTEM"},
    "security_finding_update": {"tier": "WRITE_DATA"},
    "security_finding_enrich": {"tier": "WRITE_DATA"},
    "security_remediation_propose": {"tier": "WRITE_DATA"},
}


@tool
async def security_target_resolve(name_or_id: str = "") -> str:
    """List all configured security scan targets, or resolve one exact target by
    name or ID. Use this before starting a scan to find the correct target_id."""
    targets = await db.list_targets(tenant_id=_tenant_id())
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
            tenant_id=_tenant_id(),
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
        run = await resume_after_approval(scan_run_id, tenant_id=_tenant_id())
    except PolicyViolation as exc:
        return str(ToolResponse.fail(str(exc)))
    return str(ToolResponse.ok(run.model_dump(mode="json")))


@tool
async def security_scan_status(scan_run_id: str) -> str:
    """Get the current status of a security scan run (queued, running, completed,
    waiting_for_approval, failed, etc.)."""
    run = await db.get_scan_run(scan_run_id, tenant_id=_tenant_id())
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
        tenant_id=_tenant_id(),
    )
    return str(ToolResponse.ok([f.model_dump(mode="json") for f in findings]))


@tool
async def security_workflow_list() -> str:
    """List available security audit workflows (kubernetes_full_audit,
    container_image_audit, external_service_audit, git_repository_audit,
    ai_platform_audit) with their supported target types."""
    return str(ToolResponse.ok([
        {
            "id": wf.id, "name": wf.name, "description": wf.description,
            "target_types": [t.value for t in wf.target_types],
            "scanners": wf.preferred_scanner_ids,
        }
        for wf in SECURITY_WORKFLOWS.values()
    ]))


@tool
async def security_workflow_run(workflow_id: str, target_id: str, requested_by: str = "") -> str:
    """Run a multi-scanner security audit workflow against a target. Runs every
    scanner in the workflow that is compatible with the target's type and
    allowed by the target's own allowlist; incompatible scanners are skipped,
    not treated as failures. Use security_workflow_list to see available
    workflows and security_target_resolve to find a valid target_id.
    Individual scan steps may pause for approval (intrusive scanners like
    Garak) — check security_scan_status on the returned run IDs."""
    tenant_id = _tenant_id()
    target = await db.get_target(target_id, tenant_id=tenant_id)
    if target is None:
        return str(ToolResponse.fail(f"Unbekanntes Security-Target: {target_id}"))
    try:
        result = await run_security_workflow(
            workflow_id, target=target, requested_by=requested_by, trigger_type=TriggerType.MANUAL,
            tenant_id=tenant_id,
        )
    except (PolicyViolation, ValueError) as exc:
        return str(ToolResponse.fail(str(exc)))

    return str(ToolResponse.ok({
        "workflow_id": result.workflow_id,
        "target_id": result.target_id,
        "total_findings": result.total_findings,
        "steps": [
            {
                "scanner_id": s.scanner_id,
                "scan_run_id": s.run.id if s.run else None,
                "status": s.run.status.value if s.run else "skipped",
                "finding_count": s.run.finding_count if s.run else 0,
                "skipped_reason": s.skipped_reason,
            }
            for s in result.steps
        ],
    }))


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
    updated = await db.set_finding_status(
        finding_id, new_status, tenant_id=_tenant_id(), remediation=remediation or None
    )
    if updated is None:
        return str(ToolResponse.fail(f"Unbekanntes Finding: {finding_id}"))
    return str(ToolResponse.ok(updated.model_dump(mode="json")))


@tool
async def security_finding_enrich(finding_id: str) -> str:
    """Ask the local LLM to assess a finding: effective severity, exploitability,
    business impact, false-positive likelihood, and remediation steps. Stored
    separately from the original finding — never overwrites scanner-reported
    data. Use this before proposing remediation for a specific finding."""
    try:
        enrichment = await enrich_finding(finding_id, tenant_id=_tenant_id())
    except ValueError as exc:
        return str(ToolResponse.fail(str(exc)))
    return str(ToolResponse.ok(enrichment.model_dump(mode="json")))


@tool
async def security_remediation_propose(finding_id: str) -> str:
    """Propose a concrete remediation (steps + optional patch) for a finding.
    This NEVER applies any change — it only drafts a proposal for human review.
    Internally runs the same LLM enrichment as security_finding_enrich and
    returns just the remediation-relevant fields."""
    try:
        enrichment = await enrich_finding(finding_id, tenant_id=_tenant_id())
    except ValueError as exc:
        return str(ToolResponse.fail(str(exc)))
    return str(ToolResponse.ok({
        "finding_id": finding_id,
        "remediation_proposal": enrichment.remediation_proposal,
        "patch_proposal": enrichment.patch_proposal,
        "requires_human_review": enrichment.requires_human_review,
        "confidence": enrichment.confidence,
    }))


@tool
async def security_report_generate(target_id: str = "", scan_run_id: str = "") -> str:
    """Generate a Markdown security report summarizing findings for a target or
    a specific scan run, grouped by severity. Read-only, nothing is persisted —
    the caller (chat/workflow) is responsible for delivering the report text."""
    if not target_id and not scan_run_id:
        return str(ToolResponse.fail("target_id oder scan_run_id ist erforderlich."))
    findings = await db.list_findings(
        target_id=target_id or None, scan_run_id=scan_run_id or None, limit=500, tenant_id=_tenant_id(),
    )
    active = [f for f in findings if f.status not in (
        FindingStatus.RESOLVED, FindingStatus.FALSE_POSITIVE, FindingStatus.RISK_ACCEPTED,
    )]

    lines = ["# Security Report", ""]
    scope = f"Target: {target_id}" if target_id else f"Scan-Run: {scan_run_id}"
    lines.append(scope)
    lines.append(f"Aktive Findings: {len(active)} von {len(findings)} insgesamt")
    lines.append("")

    for severity in (Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO):
        group = [f for f in active if f.severity == severity]
        if not group:
            continue
        lines.append(f"## {severity.value.upper()} ({len(group)})")
        for f in group:
            cve = f" ({f.cve})" if f.cve else ""
            lines.append(f"- **{f.title}**{cve} — {f.resource_identifier or f.location or 'n/a'} [{f.status.value}]")
        lines.append("")

    return str(ToolResponse.ok("\n".join(lines)))
