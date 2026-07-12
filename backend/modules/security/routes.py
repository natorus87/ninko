"""Security Core — FastAPI-Router.

Mounted unter /api/security (via manifest.api_prefix, siehe module_registry.py).
RBAC laeuft ueber den generischen Fallback in core/api_security_policy.py
(ROLE_WRITE fuer Mutationen, ROLE_READ fuer GET) — keine Aenderung an dieser
geteilten Datei noetig, "security" ist kein CORE_API_PREFIX.

Scan-Erstellung nutzt queue_scan() + BackgroundTasks statt start_scan(): ein
HTTP-Request darf nicht bis zum Scan-Timeout (mehrere Minuten) blockieren.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from core.auth import auth_tenant_id, resolve_request_auth

from . import db
from .models import FindingStatus, Severity, TriggerType
from .policy import PolicyViolation, decide_approval
from .scan_service import execute_queued_run, queue_scan, resume_after_approval
from .scanner_registry import BUILTIN_SCAN_PROFILES, get_scanner_registry
from .schemas import (
    ApprovalDecisionRequest,
    FindingStatusUpdateRequest,
    ScanRunCreateRequest,
    TargetCreateRequest,
    TargetUpdateRequest,
    WorkflowRunCreateRequest,
)
from .workflows import SECURITY_WORKFLOWS, run_security_workflow

logger = logging.getLogger("ninko.modules.security.routes")
router = APIRouter()


def _auth(request: Request) -> tuple[str, str]:
    """Gibt (tenant_id, username) fuer die aktuelle Anfrage zurueck."""
    ctx = resolve_request_auth(request)
    return auth_tenant_id(ctx), (ctx or {}).get("username", "")


def _http_error_from_policy(exc: PolicyViolation, *, not_found: bool = False) -> HTTPException:
    status = 404 if not_found else 422
    return HTTPException(status_code=status, detail=str(exc))


# ── Scanners & Profiles (read-only, statisch) ────────────────────────────


@router.get("/scanners")
async def list_scanners() -> list[dict]:
    definitions = get_scanner_registry().list_definitions()
    return [d.model_dump(mode="json") for d in definitions]


@router.get("/profiles")
async def list_profiles() -> list[dict]:
    return [p.model_dump(mode="json") for p in BUILTIN_SCAN_PROFILES.values()]


@router.get("/workflows")
async def list_workflows() -> list[dict]:
    return [
        {
            "id": wf.id, "name": wf.name, "description": wf.description,
            "target_types": [t.value for t in wf.target_types],
            "scanners": wf.preferred_scanner_ids,
        }
        for wf in SECURITY_WORKFLOWS.values()
    ]


# ── Targets ────────────────────────────────────────────────────────────


@router.get("/targets")
async def list_targets(request: Request, enabled_only: bool = False) -> list[dict]:
    tenant_id, _ = _auth(request)
    targets = await db.list_targets(tenant_id=tenant_id, enabled_only=enabled_only)
    return [t.model_dump(mode="json") for t in targets]


@router.post("/targets", status_code=201)
async def create_target(body: TargetCreateRequest, request: Request) -> dict:
    tenant_id, _ = _auth(request)
    from .models import SecurityTarget

    target = SecurityTarget(**body.model_dump(), tenant_id=tenant_id)
    created = await db.create_target(target)
    return created.model_dump(mode="json")


@router.get("/targets/{target_id}")
async def get_target(target_id: str, request: Request) -> dict:
    tenant_id, _ = _auth(request)
    target = await db.get_target(target_id, tenant_id=tenant_id)
    if target is None:
        raise HTTPException(404, f"Target {target_id} nicht gefunden.")
    return target.model_dump(mode="json")


@router.patch("/targets/{target_id}")
async def update_target(target_id: str, body: TargetUpdateRequest, request: Request) -> dict:
    tenant_id, _ = _auth(request)
    fields = body.model_dump(exclude_unset=True)
    try:
        updated = await db.update_target(target_id, tenant_id=tenant_id, **fields)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if updated is None:
        raise HTTPException(404, f"Target {target_id} nicht gefunden.")
    return updated.model_dump(mode="json")


@router.delete("/targets/{target_id}")
async def delete_target(target_id: str, request: Request) -> dict:
    tenant_id, _ = _auth(request)
    deleted = await db.delete_target(target_id, tenant_id=tenant_id)
    if not deleted:
        raise HTTPException(404, f"Target {target_id} nicht gefunden.")
    return {"id": target_id, "deleted": True}


# ── Scan Runs ──────────────────────────────────────────────────────────


@router.get("/runs")
async def list_runs(
    request: Request, target_id: str = "", status: str = "", limit: int = 50
) -> list[dict]:
    tenant_id, _ = _auth(request)
    from .models import ScanRunStatus

    try:
        st = ScanRunStatus(status) if status else None
    except ValueError as exc:
        raise HTTPException(422, f"Ungueltiger Status: {status}") from exc
    runs = await db.list_scan_runs(tenant_id=tenant_id, target_id=target_id or None, status=st, limit=limit)
    return [r.model_dump(mode="json") for r in runs]


@router.post("/runs", status_code=202)
async def create_run(body: ScanRunCreateRequest, background_tasks: BackgroundTasks, request: Request) -> dict:
    tenant_id, username = _auth(request)
    try:
        run = await queue_scan(
            target_id=body.target_id, scanner_id=body.scanner_id, profile_id=body.profile_id,
            parameters=body.parameters, requested_by=username, trigger_type=TriggerType.MANUAL,
            tenant_id=tenant_id,
        )
    except PolicyViolation as exc:
        raise _http_error_from_policy(exc) from exc

    from .models import ScanRunStatus

    if run.status == ScanRunStatus.QUEUED:
        background_tasks.add_task(execute_queued_run, run.id, tenant_id=tenant_id)
    return run.model_dump(mode="json")


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict:
    tenant_id, _ = _auth(request)
    run = await db.get_scan_run(run_id, tenant_id=tenant_id)
    if run is None:
        raise HTTPException(404, f"Scan-Run {run_id} nicht gefunden.")
    return run.model_dump(mode="json")


@router.post("/runs/{run_id}/approve")
async def approve_run(
    run_id: str, body: ApprovalDecisionRequest, background_tasks: BackgroundTasks, request: Request
) -> dict:
    tenant_id, username = _auth(request)
    try:
        await decide_approval(run_id, approved=body.approved, decided_by=username)
    except PolicyViolation as exc:
        raise _http_error_from_policy(exc, not_found=True) from exc

    if not body.approved:
        run = await db.get_scan_run(run_id, tenant_id=tenant_id)
        return run.model_dump(mode="json") if run else {"id": run_id, "status": "rejected"}

    # Freigabe erteilt: Ausfuehrung im Hintergrund starten, nicht den Request blockieren.
    background_tasks.add_task(resume_after_approval, run_id, tenant_id=tenant_id)
    run = await db.get_scan_run(run_id, tenant_id=tenant_id)
    return run.model_dump(mode="json") if run else {"id": run_id, "status": "approved"}


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request) -> dict:
    """Bricht einen QUEUED oder WAITING_FOR_APPROVAL Run ab. Ein bereits laufender
    Scan (RUNNING) kann in diesem MVP nicht unterbrochen werden — der K8s-Job
    laeuft bis zu seinem eigenen Timeout weiter, wird aber nicht mehr als
    Ergebnis uebernommen (siehe bekannte Limitationen)."""
    tenant_id, _ = _auth(request)
    from .models import ScanRunStatus

    run = await db.get_scan_run(run_id, tenant_id=tenant_id)
    if run is None:
        raise HTTPException(404, f"Scan-Run {run_id} nicht gefunden.")
    if run.status not in (ScanRunStatus.QUEUED, ScanRunStatus.WAITING_FOR_APPROVAL):
        raise HTTPException(422, f"Scan-Run {run_id} kann im Status {run.status.value} nicht abgebrochen werden.")
    updated = await db.update_scan_run(run_id, status=ScanRunStatus.CANCELLED.value, tenant_id=tenant_id)
    return updated.model_dump(mode="json")


# ── Workflow Runs ──────────────────────────────────────────────────────


@router.post("/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, body: WorkflowRunCreateRequest, request: Request) -> dict:
    """Startet einen Audit-Workflow. Laeuft (noch) synchron im Request — jeder
    Scan-Schritt selbst nutzt intern start_scan() (Tool-/Scheduler-Pfad), nicht
    queue_scan(); bei mehreren Scannern kann das mehrere Minuten dauern. Fuer
    lange Workflows die Chat-Oberflaeche oder einen geplanten Job nutzen."""
    tenant_id, username = _auth(request)
    target = await db.get_target(body.target_id, tenant_id=tenant_id)
    if target is None:
        raise HTTPException(404, f"Target {body.target_id} nicht gefunden.")
    try:
        result = await run_security_workflow(
            workflow_id, target=target, requested_by=username, trigger_type=TriggerType.MANUAL,
            tenant_id=tenant_id,
        )
    except (PolicyViolation, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc

    return {
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
    }


# ── Findings ───────────────────────────────────────────────────────────


@router.get("/findings")
async def list_findings(
    request: Request, target_id: str = "", scan_run_id: str = "", severity: str = "",
    status: str = "", scanner_id: str = "", limit: int = 200,
) -> list[dict]:
    tenant_id, _ = _auth(request)
    try:
        sev = Severity(severity) if severity else None
        st = FindingStatus(status) if status else None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    findings = await db.list_findings(
        tenant_id=tenant_id, target_id=target_id or None, scan_run_id=scan_run_id or None,
        severity=sev, status=st, scanner_id=scanner_id or None, limit=limit,
    )
    return [f.model_dump(mode="json") for f in findings]


@router.get("/findings/{finding_id}")
async def get_finding(finding_id: str, request: Request) -> dict:
    tenant_id, _ = _auth(request)
    finding = await db.get_finding(finding_id, tenant_id=tenant_id)
    if finding is None:
        raise HTTPException(404, f"Finding {finding_id} nicht gefunden.")
    enrichments = await db.list_enrichments(finding_id)
    payload = finding.model_dump(mode="json")
    payload["enrichments"] = [e.model_dump(mode="json") for e in enrichments]
    return payload


@router.patch("/findings/{finding_id}")
async def update_finding_status(finding_id: str, body: FindingStatusUpdateRequest, request: Request) -> dict:
    tenant_id, _ = _auth(request)
    try:
        new_status = FindingStatus(body.status)
    except ValueError as exc:
        raise HTTPException(422, f"Ungueltiger Status: {body.status}") from exc
    updated = await db.set_finding_status(
        finding_id, new_status, tenant_id=tenant_id, remediation=body.remediation
    )
    if updated is None:
        raise HTTPException(404, f"Finding {finding_id} nicht gefunden.")
    return updated.model_dump(mode="json")
