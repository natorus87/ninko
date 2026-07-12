"""Security Core — SQLite-Persistenz fuer Targets, ScanRuns, Findings, Enrichments.

Erstes Ninko-Modul mit einem "offiziellen" relationalen Schema fuer Domain-
Daten (analog zum bestehenden message_hub/db.py-Pattern, aber ueber
core.config.get_settings().DATA_DIR statt eines hartkodierten Pfads).

Kein ORM, kein Alembic (in Ninko nicht etabliert) — Schema-Aenderungen laufen
ueber `_ensure_db()`-idempotente `CREATE TABLE IF NOT EXISTS` + manuelle
`ALTER TABLE`-Guards, falls spaeter Spalten hinzukommen.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import aiosqlite

from .fingerprint import compute_fingerprint
from .models import (
    Finding,
    FindingEnrichment,
    FindingStatus,
    ScanRun,
    ScanRunStatus,
    SecurityTarget,
    Severity,
    TargetType,
    TriggerType,
)

logger = logging.getLogger("ninko.modules.security.db")

_db_lock = asyncio.Lock()
_init_event: asyncio.Event | None = None
_db_path: Path | None = None


def _resolve_db_path() -> Path:
    global _db_path
    if _db_path is not None:
        return _db_path
    from core.config import get_settings

    _db_path = Path(get_settings().DATA_DIR) / "security.db"
    return _db_path


async def _ensure_db() -> None:
    """Race-sichere, idempotente Schema-Initialisierung."""
    global _init_event

    if _init_event is None:
        async with _db_lock:
            if _init_event is None:
                _init_event = asyncio.Event()
            else:
                await _init_event.wait()
                return

    if _init_event.is_set():
        return

    db_path = _resolve_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(db_path)) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_targets (
                id                   TEXT PRIMARY KEY,
                tenant_id            TEXT NOT NULL DEFAULT '',
                name                 TEXT NOT NULL,
                target_type          TEXT NOT NULL,
                locator              TEXT NOT NULL,
                environment          TEXT NOT NULL DEFAULT 'production',
                owner                TEXT NOT NULL DEFAULT '',
                tags                 TEXT NOT NULL DEFAULT '[]',
                enabled              INTEGER NOT NULL DEFAULT 1,
                allowed_scanners     TEXT NOT NULL DEFAULT '[]',
                allowed_profiles     TEXT NOT NULL DEFAULT '[]',
                scope_constraints    TEXT NOT NULL DEFAULT '{}',
                credentials_reference TEXT,
                network_zone         TEXT NOT NULL DEFAULT 'unspecified',
                created_at           REAL NOT NULL,
                updated_at           REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_targets_tenant ON security_targets (tenant_id, enabled)"
        )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_scan_runs (
                id                  TEXT PRIMARY KEY,
                tenant_id           TEXT NOT NULL DEFAULT '',
                security_job_id     TEXT,
                workflow_run_id     TEXT,
                agent_run_id        TEXT,
                target_id           TEXT NOT NULL,
                scanner_id          TEXT NOT NULL,
                profile_id          TEXT NOT NULL,
                requested_by        TEXT NOT NULL DEFAULT '',
                trigger_type        TEXT NOT NULL DEFAULT 'manual',
                status              TEXT NOT NULL DEFAULT 'queued',
                started_at          REAL,
                completed_at        REAL,
                timeout_at          REAL,
                parameters          TEXT NOT NULL DEFAULT '{}',
                scope_snapshot      TEXT NOT NULL DEFAULT '{}',
                permission_snapshot TEXT NOT NULL DEFAULT '{}',
                scanner_version     TEXT NOT NULL DEFAULT '',
                raw_artifact_refs   TEXT NOT NULL DEFAULT '[]',
                finding_count       INTEGER NOT NULL DEFAULT 0,
                error               TEXT,
                audit_context       TEXT NOT NULL DEFAULT '{}',
                created_at          REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_target ON security_scan_runs (target_id, created_at)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_runs_status ON security_scan_runs (tenant_id, status)"
        )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_findings (
                id                   TEXT PRIMARY KEY,
                tenant_id            TEXT NOT NULL DEFAULT '',
                scan_run_id          TEXT NOT NULL,
                target_id            TEXT NOT NULL,
                fingerprint          TEXT NOT NULL,
                scanner_id           TEXT NOT NULL,
                scanner_finding_id   TEXT NOT NULL DEFAULT '',
                title                TEXT NOT NULL,
                description          TEXT NOT NULL DEFAULT '',
                severity             TEXT NOT NULL,
                original_severity    TEXT NOT NULL,
                confidence           REAL NOT NULL DEFAULT 1.0,
                category             TEXT NOT NULL DEFAULT '',
                cve                  TEXT,
                cwe                  TEXT,
                cvss                 REAL,
                resource_type        TEXT NOT NULL DEFAULT '',
                resource_identifier  TEXT NOT NULL DEFAULT '',
                location             TEXT NOT NULL DEFAULT '',
                evidence_refs        TEXT NOT NULL DEFAULT '[]',
                first_seen_at        REAL NOT NULL,
                last_seen_at         REAL NOT NULL,
                occurrence_count     INTEGER NOT NULL DEFAULT 1,
                status               TEXT NOT NULL DEFAULT 'new',
                false_positive       INTEGER NOT NULL DEFAULT 0,
                risk_accepted        INTEGER NOT NULL DEFAULT 0,
                remediation          TEXT,
                metadata             TEXT NOT NULL DEFAULT '{}',
                UNIQUE(tenant_id, fingerprint)
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_findings_scan_run ON security_findings (scan_run_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_findings_target_status "
            "ON security_findings (tenant_id, target_id, status)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_findings_severity ON security_findings (tenant_id, severity, status)"
        )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS security_finding_enrichments (
                id                          TEXT PRIMARY KEY,
                finding_id                  TEXT NOT NULL,
                model                       TEXT NOT NULL,
                model_version               TEXT NOT NULL DEFAULT '',
                prompt_version              TEXT NOT NULL DEFAULT 'v1',
                input_hash                  TEXT NOT NULL DEFAULT '',
                effective_severity          TEXT NOT NULL,
                exploitability              TEXT NOT NULL DEFAULT 'unknown',
                business_impact             TEXT NOT NULL DEFAULT '',
                confidence                  REAL NOT NULL,
                summary                     TEXT NOT NULL DEFAULT '',
                correlation_ids             TEXT NOT NULL DEFAULT '[]',
                false_positive_probability  REAL NOT NULL,
                remediation_proposal        TEXT,
                patch_proposal              TEXT,
                requires_human_review       INTEGER NOT NULL DEFAULT 1,
                validation_status           TEXT NOT NULL DEFAULT 'valid',
                created_at                  REAL NOT NULL
            )
        """)
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_enrichments_finding ON security_finding_enrichments (finding_id)"
        )

        await db.commit()

    _init_event.set()
    logger.info("Security Core DB bereit: %s", db_path)


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


# ── Targets ────────────────────────────────────────────────────────────


async def create_target(target: SecurityTarget) -> SecurityTarget:
    await _ensure_db()
    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        await db.execute(
            """INSERT INTO security_targets
               (id, tenant_id, name, target_type, locator, environment, owner, tags,
                enabled, allowed_scanners, allowed_profiles, scope_constraints,
                credentials_reference, network_zone, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                target.id,
                target.tenant_id,
                target.name,
                target.target_type.value,
                target.locator,
                target.environment,
                target.owner,
                _dumps(target.tags),
                int(target.enabled),
                _dumps(target.allowed_scanners),
                _dumps([p.value for p in target.allowed_profiles]),
                _dumps(target.scope_constraints),
                target.credentials_reference,
                target.network_zone,
                target.created_at,
                target.updated_at,
            ),
        )
        await db.commit()
    return target


async def get_target(target_id: str, *, tenant_id: str = "") -> SecurityTarget | None:
    await _ensure_db()
    async with aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM security_targets WHERE id = ? AND tenant_id = ?", (target_id, tenant_id)
        )
        row = await cur.fetchone()
        return _row_to_target(row) if row else None


async def list_targets(*, tenant_id: str = "", enabled_only: bool = False) -> list[SecurityTarget]:
    await _ensure_db()
    async with aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        sql = "SELECT * FROM security_targets WHERE tenant_id = ?"
        params: list[Any] = [tenant_id]
        if enabled_only:
            sql += " AND enabled = 1"
        sql += " ORDER BY created_at DESC"
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
        return [_row_to_target(r) for r in rows]


async def delete_target(target_id: str, *, tenant_id: str = "") -> bool:
    await _ensure_db()
    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        cur = await db.execute(
            "DELETE FROM security_targets WHERE id = ? AND tenant_id = ?", (target_id, tenant_id)
        )
        await db.commit()
        return cur.rowcount > 0


def _row_to_target(row: aiosqlite.Row) -> SecurityTarget:
    return SecurityTarget(
        id=row["id"],
        tenant_id=row["tenant_id"],
        name=row["name"],
        target_type=TargetType(row["target_type"]),
        locator=row["locator"],
        environment=row["environment"],
        owner=row["owner"],
        tags=_loads(row["tags"], []),
        enabled=bool(row["enabled"]),
        allowed_scanners=_loads(row["allowed_scanners"], []),
        allowed_profiles=_loads(row["allowed_profiles"], []),
        scope_constraints=_loads(row["scope_constraints"], {}),
        credentials_reference=row["credentials_reference"],
        network_zone=row["network_zone"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


# ── ScanRuns ───────────────────────────────────────────────────────────


async def create_scan_run(run: ScanRun) -> ScanRun:
    await _ensure_db()
    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        await db.execute(
            """INSERT INTO security_scan_runs
               (id, tenant_id, security_job_id, workflow_run_id, agent_run_id, target_id,
                scanner_id, profile_id, requested_by, trigger_type, status, started_at,
                completed_at, timeout_at, parameters, scope_snapshot, permission_snapshot,
                scanner_version, raw_artifact_refs, finding_count, error, audit_context, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id,
                run.tenant_id,
                run.security_job_id,
                run.workflow_run_id,
                run.agent_run_id,
                run.target_id,
                run.scanner_id,
                run.profile_id,
                run.requested_by,
                run.trigger_type.value,
                run.status.value,
                run.started_at,
                run.completed_at,
                run.timeout_at,
                _dumps(run.parameters),
                _dumps(run.scope_snapshot),
                _dumps(run.permission_snapshot),
                run.scanner_version,
                _dumps(run.raw_artifact_refs),
                run.finding_count,
                run.error,
                _dumps(run.audit_context),
                run.created_at,
            ),
        )
        await db.commit()
    return run


async def update_scan_run(run_id: str, *, tenant_id: str = "", **fields: Any) -> ScanRun | None:
    """Aktualisiert benannte Felder eines ScanRun. Nur Modell-Felder erlaubt."""
    await _ensure_db()
    allowed = {
        "status",
        "started_at",
        "completed_at",
        "timeout_at",
        "scanner_version",
        "raw_artifact_refs",
        "finding_count",
        "error",
        "audit_context",
        "permission_snapshot",
        "workflow_run_id",
        "agent_run_id",
    }
    invalid = set(fields) - allowed
    if invalid:
        raise ValueError(f"Unbekannte ScanRun-Felder: {sorted(invalid)}")
    if not fields:
        return await get_scan_run(run_id, tenant_id=tenant_id)

    set_clauses = []
    values: list[Any] = []
    for key, value in fields.items():
        set_clauses.append(f"{key} = ?")
        if key == "status" and isinstance(value, ScanRunStatus):
            value = value.value
        elif key in ("raw_artifact_refs", "audit_context") and not isinstance(value, str):
            value = _dumps(value)
        values.append(value)
    values.extend([run_id, tenant_id])

    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        await db.execute(
            f"UPDATE security_scan_runs SET {', '.join(set_clauses)} WHERE id = ? AND tenant_id = ?",
            values,
        )
        await db.commit()
        cur = await db.execute(
            "SELECT * FROM security_scan_runs WHERE id = ? AND tenant_id = ?", (run_id, tenant_id)
        )
        row = await cur.fetchone()
        return _row_to_scan_run(row) if row else None


async def get_scan_run(run_id: str, *, tenant_id: str = "") -> ScanRun | None:
    await _ensure_db()
    async with aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM security_scan_runs WHERE id = ? AND tenant_id = ?", (run_id, tenant_id)
        )
        row = await cur.fetchone()
        return _row_to_scan_run(row) if row else None


async def list_scan_runs(
    *, tenant_id: str = "", target_id: str | None = None, status: ScanRunStatus | None = None, limit: int = 50
) -> list[ScanRun]:
    await _ensure_db()
    sql = "SELECT * FROM security_scan_runs WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if target_id:
        sql += " AND target_id = ?"
        params.append(target_id)
    if status:
        sql += " AND status = ?"
        params.append(status.value)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    async with aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
        return [_row_to_scan_run(r) for r in rows]


def _row_to_scan_run(row: aiosqlite.Row) -> ScanRun:
    return ScanRun(
        id=row["id"],
        tenant_id=row["tenant_id"],
        security_job_id=row["security_job_id"],
        workflow_run_id=row["workflow_run_id"],
        agent_run_id=row["agent_run_id"],
        target_id=row["target_id"],
        scanner_id=row["scanner_id"],
        profile_id=row["profile_id"],
        requested_by=row["requested_by"],
        trigger_type=TriggerType(row["trigger_type"]),
        status=ScanRunStatus(row["status"]),
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        timeout_at=row["timeout_at"],
        parameters=_loads(row["parameters"], {}),
        scope_snapshot=_loads(row["scope_snapshot"], {}),
        permission_snapshot=_loads(row["permission_snapshot"], {}),
        scanner_version=row["scanner_version"],
        raw_artifact_refs=_loads(row["raw_artifact_refs"], []),
        finding_count=row["finding_count"],
        error=row["error"],
        audit_context=_loads(row["audit_context"], {}),
        created_at=row["created_at"],
    )


# ── Findings ───────────────────────────────────────────────────────────


async def upsert_finding(finding: Finding) -> tuple[Finding, bool]:
    """Legt ein Finding an oder aktualisiert ein bestehendes (per Fingerprint).

    Gibt (finding, created) zurueck. Bei einem erneuten Fund werden
    last_seen_at, occurrence_count und scan_run_id aktualisiert; first_seen_at
    und der urspruengliche Status bleiben erhalten (ausser reopened-Logik,
    die der Aufrufer explizit steuert).
    """
    await _ensure_db()
    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM security_findings WHERE tenant_id = ? AND fingerprint = ?",
            (finding.tenant_id, finding.fingerprint),
        )
        existing = await cur.fetchone()

        if existing is None:
            await db.execute(
                """INSERT INTO security_findings
                   (id, tenant_id, scan_run_id, target_id, fingerprint, scanner_id,
                    scanner_finding_id, title, description, severity, original_severity,
                    confidence, category, cve, cwe, cvss, resource_type, resource_identifier,
                    location, evidence_refs, first_seen_at, last_seen_at, occurrence_count,
                    status, false_positive, risk_accepted, remediation, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    finding.id,
                    finding.tenant_id,
                    finding.scan_run_id,
                    finding.target_id,
                    finding.fingerprint,
                    finding.scanner_id,
                    finding.scanner_finding_id,
                    finding.title,
                    finding.description,
                    finding.severity.value,
                    finding.original_severity.value,
                    finding.confidence,
                    finding.category,
                    finding.cve,
                    finding.cwe,
                    finding.cvss,
                    finding.resource_type,
                    finding.resource_identifier,
                    finding.location,
                    _dumps(finding.evidence_refs),
                    finding.first_seen_at,
                    finding.last_seen_at,
                    finding.occurrence_count,
                    finding.status.value,
                    int(finding.false_positive),
                    int(finding.risk_accepted),
                    finding.remediation,
                    _dumps(finding.metadata),
                ),
            )
            await db.commit()
            return finding, True

        # Reopen-Policy: war resolved/mitigated und taucht wieder auf -> reopened.
        prev_status = FindingStatus(existing["status"])
        new_status = prev_status
        if prev_status in (FindingStatus.RESOLVED, FindingStatus.MITIGATED):
            new_status = FindingStatus.REOPENED
        elif prev_status in (FindingStatus.FALSE_POSITIVE, FindingStatus.RISK_ACCEPTED):
            new_status = prev_status  # bewusste Entscheidung bleibt erhalten, kein Auto-Ueberschreiben

        occurrence_count = existing["occurrence_count"] + 1
        await db.execute(
            """UPDATE security_findings
               SET scan_run_id = ?, last_seen_at = ?, occurrence_count = ?, status = ?,
                   severity = ?, description = ?, evidence_refs = ?, metadata = ?
               WHERE id = ?""",
            (
                finding.scan_run_id,
                finding.last_seen_at,
                occurrence_count,
                new_status.value,
                finding.severity.value,
                finding.description,
                _dumps(finding.evidence_refs),
                _dumps(finding.metadata),
                existing["id"],
            ),
        )
        await db.commit()
        updated = dict(existing)
        updated.update(
            scan_run_id=finding.scan_run_id,
            last_seen_at=finding.last_seen_at,
            occurrence_count=occurrence_count,
            status=new_status.value,
            severity=finding.severity.value,
            description=finding.description,
            evidence_refs=_dumps(finding.evidence_refs),
            metadata=_dumps(finding.metadata),
        )
        return _row_to_finding(updated), False


async def get_finding(finding_id: str, *, tenant_id: str = "") -> Finding | None:
    await _ensure_db()
    async with aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM security_findings WHERE id = ? AND tenant_id = ?", (finding_id, tenant_id)
        )
        row = await cur.fetchone()
        return _row_to_finding(row) if row else None


async def list_findings(
    *,
    tenant_id: str = "",
    target_id: str | None = None,
    scan_run_id: str | None = None,
    severity: Severity | None = None,
    status: FindingStatus | None = None,
    scanner_id: str | None = None,
    limit: int = 200,
) -> list[Finding]:
    await _ensure_db()
    sql = "SELECT * FROM security_findings WHERE tenant_id = ?"
    params: list[Any] = [tenant_id]
    if target_id:
        sql += " AND target_id = ?"
        params.append(target_id)
    if scan_run_id:
        sql += " AND scan_run_id = ?"
        params.append(scan_run_id)
    if severity:
        sql += " AND severity = ?"
        params.append(severity.value)
    if status:
        sql += " AND status = ?"
        params.append(status.value)
    if scanner_id:
        sql += " AND scanner_id = ?"
        params.append(scanner_id)
    sql += " ORDER BY last_seen_at DESC LIMIT ?"
    params.append(limit)
    async with aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
        return [_row_to_finding(r) for r in rows]


async def set_finding_status(
    finding_id: str, status: FindingStatus, *, tenant_id: str = "", remediation: str | None = None
) -> Finding | None:
    await _ensure_db()
    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        if remediation is not None:
            await db.execute(
                "UPDATE security_findings SET status = ?, remediation = ? WHERE id = ? AND tenant_id = ?",
                (status.value, remediation, finding_id, tenant_id),
            )
        else:
            await db.execute(
                "UPDATE security_findings SET status = ? WHERE id = ? AND tenant_id = ?",
                (status.value, finding_id, tenant_id),
            )
        await db.commit()
        cur = await db.execute(
            "SELECT * FROM security_findings WHERE id = ? AND tenant_id = ?", (finding_id, tenant_id)
        )
        row = await cur.fetchone()
        return _row_to_finding(row) if row else None


async def mark_absent_findings_resolved(
    scan_run_id: str, seen_finding_ids: set[str], *, tenant_id: str = "", target_id: str, scanner_id: str
) -> int:
    """Policy: Findings desselben Target+Scanner, die in diesem Run NICHT mehr
    auftraten und noch aktiv sind, werden als resolved markiert (resolve-when-absent).
    """
    await _ensure_db()
    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            """SELECT id FROM security_findings
               WHERE tenant_id = ? AND target_id = ? AND scanner_id = ?
               AND status IN ('new', 'active', 'acknowledged', 'in_progress', 'reopened')""",
            (tenant_id, target_id, scanner_id),
        )
        rows = await cur.fetchall()
        to_resolve = [r["id"] for r in rows if r["id"] not in seen_finding_ids]
        for fid in to_resolve:
            await db.execute(
                "UPDATE security_findings SET status = ? WHERE id = ?",
                (FindingStatus.RESOLVED.value, fid),
            )
        await db.commit()
        return len(to_resolve)


def _row_to_finding(row: Any) -> Finding:
    get = row.__getitem__ if not isinstance(row, dict) else row.get
    return Finding(
        id=get("id"),
        tenant_id=get("tenant_id"),
        scan_run_id=get("scan_run_id"),
        target_id=get("target_id"),
        fingerprint=get("fingerprint"),
        scanner_id=get("scanner_id"),
        scanner_finding_id=get("scanner_finding_id"),
        title=get("title"),
        description=get("description"),
        severity=Severity(get("severity")),
        original_severity=Severity(get("original_severity")),
        confidence=get("confidence"),
        category=get("category"),
        cve=get("cve"),
        cwe=get("cwe"),
        cvss=get("cvss"),
        resource_type=get("resource_type"),
        resource_identifier=get("resource_identifier"),
        location=get("location"),
        evidence_refs=_loads(get("evidence_refs"), []),
        first_seen_at=get("first_seen_at"),
        last_seen_at=get("last_seen_at"),
        occurrence_count=get("occurrence_count"),
        status=FindingStatus(get("status")),
        false_positive=bool(get("false_positive")),
        risk_accepted=bool(get("risk_accepted")),
        remediation=get("remediation"),
        metadata=_loads(get("metadata"), {}),
    )


# ── FindingEnrichments ─────────────────────────────────────────────────


async def create_enrichment(enrichment: FindingEnrichment) -> FindingEnrichment:
    await _ensure_db()
    async with _db_lock, aiosqlite.connect(str(_resolve_db_path())) as db:
        await db.execute(
            """INSERT INTO security_finding_enrichments
               (id, finding_id, model, model_version, prompt_version, input_hash,
                effective_severity, exploitability, business_impact, confidence, summary,
                correlation_ids, false_positive_probability, remediation_proposal,
                patch_proposal, requires_human_review, validation_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                enrichment.id,
                enrichment.finding_id,
                enrichment.model,
                enrichment.model_version,
                enrichment.prompt_version,
                enrichment.input_hash,
                enrichment.effective_severity.value,
                enrichment.exploitability,
                enrichment.business_impact,
                enrichment.confidence,
                enrichment.summary,
                _dumps(enrichment.correlation_ids),
                enrichment.false_positive_probability,
                enrichment.remediation_proposal,
                enrichment.patch_proposal,
                int(enrichment.requires_human_review),
                enrichment.validation_status,
                enrichment.created_at,
            ),
        )
        await db.commit()
    return enrichment


async def list_enrichments(finding_id: str) -> list[FindingEnrichment]:
    await _ensure_db()
    async with aiosqlite.connect(str(_resolve_db_path())) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM security_finding_enrichments WHERE finding_id = ? ORDER BY created_at DESC",
            (finding_id,),
        )
        rows = await cur.fetchall()
        return [
            FindingEnrichment(
                id=r["id"],
                finding_id=r["finding_id"],
                model=r["model"],
                model_version=r["model_version"],
                prompt_version=r["prompt_version"],
                input_hash=r["input_hash"],
                effective_severity=Severity(r["effective_severity"]),
                exploitability=r["exploitability"],
                business_impact=r["business_impact"],
                confidence=r["confidence"],
                summary=r["summary"],
                correlation_ids=_loads(r["correlation_ids"], []),
                false_positive_probability=r["false_positive_probability"],
                remediation_proposal=r["remediation_proposal"],
                patch_proposal=r["patch_proposal"],
                requires_human_review=bool(r["requires_human_review"]),
                validation_status=r["validation_status"],
                created_at=r["created_at"],
            )
            for r in rows
        ]


def build_finding_fingerprint(
    *, scanner_id: str, target_id: str, rule_id: str, resource_identifier: str = "", location: str = "",
    cve: str | None = None, cwe: str | None = None,
) -> str:
    """Re-export fuer Aufrufer, die nur db.py importieren."""
    return compute_fingerprint(
        scanner_id=scanner_id,
        target_id=target_id,
        rule_id=rule_id,
        resource_identifier=resource_identifier,
        location=location,
        cve=cve,
        cwe=cwe,
    )
