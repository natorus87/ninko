"""Task 13 — zusaetzliche Permission-/Tenant-Isolations-Tests fuer Security Core,
die ueber die bereits in Task 1-12 abgedeckten Faelle hinausgehen:

- RBAC-Rollen-Matrix fuer /api/security/* (generischer api_security_policy.py-
  Fallback, keine Aenderung an der geteilten Datei noetig — hier nur verifiziert).
- Tenant-Isolation fuer ScanRun/Finding (Target war bereits in Task 1 abgedeckt).
- STRUKTURELLE Durchsetzung statt Prompt-Text: dynamische Security-Agenten
  (inkl. Remediation Agent) duerfen NIE execute_cli_command gebunden bekommen —
  "der Prompt ist keine Sicherheitsgrenze" gilt auch fuer die eigenen Tests.
- Secret-Nichtoffenlegung: credentials_reference ist nur ein Verweis, nie ein
  Rohwert, structurell im Modell verankert.
"""

from __future__ import annotations

import pytest

from core.agent_pool import DynamicAgentPool, _CLI_CAPABLE_MODULES
from core.api_security_policy import extract_module_id_from_path, required_role_for_request
from core.auth import ROLE_READ, ROLE_WRITE
from modules.security.models import Finding, ScanRun, Severity

pytestmark = pytest.mark.unit


# ── RBAC-Rollen-Matrix fuer /api/security/* ──────────────────────────────


def test_security_is_not_a_core_api_prefix():
    """'security' darf NICHT in CORE_API_PREFIXES stehen — sonst greift die
    granulare module_permissions-Logik nicht mehr fuer dieses Modul."""
    assert extract_module_id_from_path("/api/security/targets") == "security"


@pytest.mark.parametrize(
    "method,path,expected",
    [
        ("GET", "/api/security/targets", ROLE_READ),
        ("GET", "/api/security/findings", ROLE_READ),
        ("GET", "/api/security/runs", ROLE_READ),
        ("GET", "/api/security/scanners", ROLE_READ),
        ("POST", "/api/security/targets", ROLE_WRITE),
        ("PATCH", "/api/security/targets/t1", ROLE_WRITE),
        ("DELETE", "/api/security/targets/t1", ROLE_WRITE),
        ("POST", "/api/security/runs", ROLE_WRITE),
        ("POST", "/api/security/runs/r1/approve", ROLE_WRITE),
        ("POST", "/api/security/runs/r1/cancel", ROLE_WRITE),
        ("PATCH", "/api/security/findings/f1", ROLE_WRITE),
        ("POST", "/api/security/workflows/container_image_audit/run", ROLE_WRITE),
    ],
)
def test_security_routes_require_expected_role(method, path, expected):
    assert required_role_for_request(path, method) == expected


def test_security_scan_start_cannot_be_called_by_unauthenticated_request():
    """Kein GET-Sonderfall, keine Public-Path-Ausnahme fuer Security — jede
    Mutation braucht mindestens ROLE_WRITE, nie None."""
    assert required_role_for_request("/api/security/runs", "POST") is not None


# ── Tenant-Isolation: ScanRun/Finding (Target bereits in Task 1 getestet) ──


@pytest.fixture
def security_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import core.config as core_config

    core_config._settings = None
    from modules.security import db as security_db_module

    security_db_module._db_path = None
    security_db_module._init_event = None
    yield security_db_module
    security_db_module._db_path = None
    security_db_module._init_event = None
    core_config._settings = None


@pytest.mark.asyncio
async def test_scan_run_tenant_isolation(security_db):
    run = ScanRun(target_id="t1", scanner_id="trivy", profile_id="passive", tenant_id="tenant-a")
    await security_db.create_scan_run(run)

    assert await security_db.get_scan_run(run.id, tenant_id="tenant-a") is not None
    assert await security_db.get_scan_run(run.id, tenant_id="tenant-b") is None
    assert await security_db.get_scan_run(run.id, tenant_id="") is None


@pytest.mark.asyncio
async def test_list_scan_runs_does_not_leak_across_tenants(security_db):
    run_a = ScanRun(target_id="t1", scanner_id="trivy", profile_id="passive", tenant_id="tenant-a")
    run_b = ScanRun(target_id="t1", scanner_id="trivy", profile_id="passive", tenant_id="tenant-b")
    await security_db.create_scan_run(run_a)
    await security_db.create_scan_run(run_b)

    tenant_a_runs = await security_db.list_scan_runs(tenant_id="tenant-a")
    assert [r.id for r in tenant_a_runs] == [run_a.id]


@pytest.mark.asyncio
async def test_finding_tenant_isolation(security_db):
    finding = Finding(
        scan_run_id="r1", target_id="t1", fingerprint="fp1", scanner_id="trivy",
        title="X", severity=Severity.HIGH, original_severity=Severity.HIGH, tenant_id="tenant-a",
    )
    stored, _ = await security_db.upsert_finding(finding)

    assert await security_db.get_finding(stored.id, tenant_id="tenant-a") is not None
    assert await security_db.get_finding(stored.id, tenant_id="tenant-b") is None


@pytest.mark.asyncio
async def test_list_findings_does_not_leak_across_tenants(security_db):
    fp_a = Finding(
        scan_run_id="r1", target_id="t1", fingerprint="fp-a", scanner_id="trivy",
        title="A", severity=Severity.HIGH, original_severity=Severity.HIGH, tenant_id="tenant-a",
    )
    fp_b = Finding(
        scan_run_id="r1", target_id="t1", fingerprint="fp-b", scanner_id="trivy",
        title="B", severity=Severity.HIGH, original_severity=Severity.HIGH, tenant_id="tenant-b",
    )
    await security_db.upsert_finding(fp_a)
    await security_db.upsert_finding(fp_b)

    tenant_a_findings = await security_db.list_findings(tenant_id="tenant-a")
    assert [f.title for f in tenant_a_findings] == ["A"]


@pytest.mark.asyncio
async def test_set_finding_status_cannot_cross_tenant(security_db):
    from modules.security.models import FindingStatus

    finding = Finding(
        scan_run_id="r1", target_id="t1", fingerprint="fp1", scanner_id="trivy",
        title="X", severity=Severity.HIGH, original_severity=Severity.HIGH, tenant_id="tenant-a",
    )
    stored, _ = await security_db.upsert_finding(finding)

    result = await security_db.set_finding_status(stored.id, FindingStatus.RESOLVED, tenant_id="tenant-b")
    assert result is None  # falscher Tenant -> kein Treffer, keine Aenderung

    unchanged = await security_db.get_finding(stored.id, tenant_id="tenant-a")
    assert unchanged.status == FindingStatus.NEW


# ── Strukturelle Durchsetzung: Security-Agenten bekommen nie CLI-Zugriff ──


def test_security_not_in_cli_capable_modules():
    """execute_cli_command wird dynamischen Agenten nur gegeben, wenn eines
    ihrer module_names in _CLI_CAPABLE_MODULES steht. 'security' darf dort
    NIE auftauchen — Scans laufen ausschliesslich ueber typisierte Scanner-
    Adapter, nie ueber freien Shell-Zugriff (Auftragsprinzip)."""
    assert "security" not in _CLI_CAPABLE_MODULES


def test_dynamic_security_agent_never_gets_cli_tool():
    """Reproduziert exakt, was DynamicAgentPool._instantiate() fuer ein
    Security-Agent-Profil an Tools zusammenstellt — echte Funktionspruefung,
    nicht nur eine Behauptung im System-Prompt."""
    tools = DynamicAgentPool._get_dynamic_tools({"module_names": ["security"]})
    tool_names = {getattr(t, "name", getattr(t, "__name__", str(t))) for t in tools}
    assert "execute_cli_command" not in tool_names


def test_dynamic_agent_without_module_names_also_gets_no_cli_tool():
    tools = DynamicAgentPool._get_dynamic_tools({})
    tool_names = {getattr(t, "name", getattr(t, "__name__", str(t))) for t in tools}
    assert "execute_cli_command" not in tool_names


# ── Secret-Nichtoffenlegung ────────────────────────────────────────────────


def test_security_target_model_has_no_raw_secret_field():
    """Strukturelle Garantie: SecurityTarget kann gar keinen Rohwert fuer
    Zugangsdaten speichern, nur eine Referenz — 'credentials_reference' ist
    das einzige zugangsdatenbezogene Feld, und kein anderes Feld traegt einen
    Namen, der auf einen Rohwert (Passwort/Secret/Token/Key) hindeutet."""
    from modules.security.models import SecurityTarget

    field_names = set(SecurityTarget.model_fields.keys())
    assert "credentials_reference" in field_names
    other_fields = field_names - {"credentials_reference"}
    secret_like = {f for f in other_fields if any(k in f.lower() for k in ("password", "secret", "token", "apikey"))}
    assert secret_like == set(), f"Verdaechtige Rohwert-Felder gefunden: {secret_like}"


@pytest.mark.asyncio
async def test_target_round_trip_never_expands_credentials_reference(security_db):
    """Ein gespeichertes Target liefert credentials_reference unveraendert als
    reinen Verweis-String zurueck — nie aufgeloest, nie mit echtem Secret-Inhalt
    angereichert (das waere ein Leck in DB-Zeilen/API-Responses)."""
    from modules.security.models import SecurityTarget, TargetType

    target = SecurityTarget(
        name="prod-cluster", target_type=TargetType.KUBERNETES_NAMESPACE, locator="ai-platform",
        credentials_reference="kubeconfig-prod-secret-name", tenant_id="t1",
    )
    await security_db.create_target(target)
    fetched = await security_db.get_target(target.id, tenant_id="t1")
    assert fetched.credentials_reference == "kubeconfig-prod-secret-name"
    assert len(fetched.credentials_reference) < 100  # ist ein Name/Verweis, kein Blob
