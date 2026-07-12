"""Security Core — Scan-Orchestrierung.

Verbindet Policy Engine, Scanner Registry, K8sJobExecutor und Persistenz zu
einem vollstaendigen Scan-Flow. Wird von tools.py (Agent), routes.py (API)
und spaeter von Workflow-Steps (Task 8) genutzt — daher als eigenstaendiger
Service statt in tools.py dupliziert.

Ablauf: Target laden -> Policy validieren -> ScanRun anlegen -> ggf. Approval
anfordern und pausieren -> Adapter ausfuehren -> Ergebnisse normalisieren ->
Findings upserten (Dedupe/Reopen/Resolve-when-absent) -> ScanRun abschliessen.
"""

from __future__ import annotations

import logging
import time

from . import db
from .fingerprint import compute_fingerprint
from .models import Finding, ScanRun, ScanRunStatus, SecurityTarget, TriggerType
from .policy import PolicyViolation, create_approval_request, is_approved, validate_scan_request
from .scanner_adapter import SecurityExecutionContext
from .scanner_registry import get_scan_profile, get_scanner_registry

logger = logging.getLogger("ninko.modules.security.scan_service")


async def start_scan(
    *,
    target_id: str,
    scanner_id: str,
    profile_id: str,
    parameters: dict | None = None,
    requested_by: str = "",
    trigger_type: TriggerType = TriggerType.MANUAL,
    tenant_id: str = "",
    agent_capabilities: list[str] | None = None,
    denied_capabilities: list[str] | None = None,
) -> ScanRun:
    """Startet einen Scan. Wirft PolicyViolation, wenn irgendeine Regel verletzt
    wird (Target unbekannt, Scanner/Profil nicht erlaubt, Scope verletzt, fehlende
    Capability). Bei intrusive Profilen wird der Run auf WAITING_FOR_APPROVAL
    gesetzt und NICHT ausgefuehrt, bis `resume_after_approval` aufgerufen wird.
    """
    target = await db.get_target(target_id, tenant_id=tenant_id)
    if target is None:
        raise PolicyViolation(f"Unbekanntes Security-Target: {target_id}")

    profile_kind = get_scan_profile(profile_id).kind.value
    decision = validate_scan_request(
        target=target,
        scanner_id=scanner_id,
        profile_id=profile_id,
        trigger_type=trigger_type,
        agent_capabilities=agent_capabilities,
        denied_capabilities=denied_capabilities,
        required_capability=f"security.scan.execute.{profile_kind}",
    )

    run = ScanRun(
        target_id=target_id,
        scanner_id=scanner_id,
        profile_id=profile_id,
        requested_by=requested_by,
        trigger_type=trigger_type,
        tenant_id=tenant_id,
        parameters=parameters or {},
        scope_snapshot=target.model_dump(mode="json"),
        status=ScanRunStatus.WAITING_FOR_APPROVAL if decision.requires_approval else ScanRunStatus.QUEUED,
    )
    await db.create_scan_run(run)

    if decision.requires_approval:
        await create_approval_request(
            scan_run_id=run.id, target=target, scanner_id=scanner_id, profile_id=profile_id,
            requested_by=requested_by,
        )
        logger.info("Scan-Run %s wartet auf Freigabe (intrusive Profil %s)", run.id, profile_id)
        return run

    return await _execute_scan(run, target)


async def resume_after_approval(run_id: str, *, tenant_id: str = "") -> ScanRun:
    """Setzt einen freigegebenen Scan-Run fort. Wirft PolicyViolation, wenn keine
    gueltige (nicht abgelaufene) Freigabe vorliegt."""
    run = await db.get_scan_run(run_id, tenant_id=tenant_id)
    if run is None:
        raise PolicyViolation(f"Unbekannter Scan-Run: {run_id}")
    if run.status != ScanRunStatus.WAITING_FOR_APPROVAL:
        raise PolicyViolation(f"Scan-Run {run_id} wartet nicht auf Freigabe (Status: {run.status.value}).")
    if not await is_approved(run_id):
        raise PolicyViolation(f"Scan-Run {run_id} ist nicht (mehr) freigegeben.")

    target = await db.get_target(run.target_id, tenant_id=tenant_id)
    if target is None:
        raise PolicyViolation(f"Target {run.target_id} existiert nicht mehr.")

    await db.update_scan_run(run.id, status=ScanRunStatus.APPROVED.value, tenant_id=tenant_id)
    run = await db.get_scan_run(run.id, tenant_id=tenant_id)
    return await _execute_scan(run, target)


async def _execute_scan(run: ScanRun, target: SecurityTarget) -> ScanRun:
    registry = get_scanner_registry()
    adapter = registry.get_adapter(run.scanner_id)
    profile = get_scan_profile(run.profile_id)

    validation = adapter.validate_target(target, profile, run.parameters)
    if not validation.valid:
        await db.update_scan_run(
            run.id, status=ScanRunStatus.POLICY_BLOCKED.value,
            error="; ".join(validation.errors), completed_at=time.time(), tenant_id=run.tenant_id,
        )
        return await db.get_scan_run(run.id, tenant_id=run.tenant_id)

    await db.update_scan_run(
        run.id, status=ScanRunStatus.RUNNING.value, started_at=time.time(), tenant_id=run.tenant_id
    )

    from .executor import ScanExecutionError, ScanTimeoutError, get_executor

    try:
        spec = adapter.build_execution_spec(target, profile, run.parameters)
        context = SecurityExecutionContext(
            scan_run_id=run.id, tenant_id=run.tenant_id, requested_by=run.requested_by,
            executor=get_executor(),
        )
        result = await adapter.execute(spec, context)
    except ScanTimeoutError as exc:
        await db.update_scan_run(
            run.id, status=ScanRunStatus.TIMED_OUT.value, error=str(exc),
            completed_at=time.time(), tenant_id=run.tenant_id,
        )
        return await db.get_scan_run(run.id, tenant_id=run.tenant_id)
    except ScanExecutionError as exc:
        await db.update_scan_run(
            run.id, status=ScanRunStatus.FAILED.value, error=str(exc),
            completed_at=time.time(), tenant_id=run.tenant_id,
        )
        return await db.get_scan_run(run.id, tenant_id=run.tenant_id)

    await db.update_scan_run(
        run.id, status=ScanRunStatus.PARSING.value, scanner_version=result.scanner_version,
        tenant_id=run.tenant_id,
    )

    try:
        normalized = adapter.parse_results(result)
    except ValueError as exc:
        await db.update_scan_run(
            run.id, status=ScanRunStatus.FAILED.value, error=f"Parse-Fehler: {exc}",
            completed_at=time.time(), tenant_id=run.tenant_id,
        )
        return await db.get_scan_run(run.id, tenant_id=run.tenant_id)

    seen_ids: set[str] = set()
    now = time.time()
    for nf in normalized:
        fingerprint = compute_fingerprint(
            scanner_id=run.scanner_id, target_id=target.id, rule_id=nf.rule_id,
            resource_identifier=nf.resource_identifier, location=nf.location, cve=nf.cve, cwe=nf.cwe,
        )
        finding = Finding(
            scan_run_id=run.id, target_id=target.id, fingerprint=fingerprint, scanner_id=run.scanner_id,
            scanner_finding_id=nf.rule_id, title=nf.title, description=nf.description,
            severity=nf.severity, original_severity=nf.severity, confidence=nf.confidence,
            category=nf.category, cve=nf.cve, cwe=nf.cwe, cvss=nf.cvss, resource_type=nf.resource_type,
            resource_identifier=nf.resource_identifier, location=nf.location, remediation=nf.remediation,
            metadata=nf.metadata, tenant_id=run.tenant_id, first_seen_at=now, last_seen_at=now,
        )
        stored, _created = await db.upsert_finding(finding)
        seen_ids.add(stored.id)

    await db.mark_absent_findings_resolved(
        run.id, seen_ids, target_id=target.id, scanner_id=run.scanner_id, tenant_id=run.tenant_id,
    )

    final_status = ScanRunStatus.COMPLETED if result.exit_code == 0 else ScanRunStatus.PARTIALLY_COMPLETED
    await db.update_scan_run(
        run.id, status=final_status.value, completed_at=time.time(),
        finding_count=len(normalized), tenant_id=run.tenant_id,
    )
    logger.info(
        "Scan-Run %s abgeschlossen: status=%s findings=%d", run.id, final_status.value, len(normalized)
    )
    return await db.get_scan_run(run.id, tenant_id=run.tenant_id)
