"""HTTP-Level-Tests fuer /api/security/* (Task 10) — echter FastAPI TestClient,
kein Mocking der Route-Funktionen selbst. Auth ist in Tests via
API_AUTH_ENABLED=false deaktiviert (conftest.py) -> resolve_request_auth()
liefert einen fixen Admin-Kontext.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.security.models import ScannerCategory, ScannerDefinition, TargetType
from modules.security.routes import router
from modules.security.scanner_registry import ScannerRegistry

pytestmark = pytest.mark.unit


class _FakeAdapter:
    def __init__(self, scanner_id):
        self.scanner_id = scanner_id

    def validate_target(self, target, profile, parameters):
        from modules.security.scanner_adapter import ValidationResult

        return ValidationResult(valid=True)

    def build_execution_spec(self, target, profile, parameters):
        from modules.security.scanner_adapter import ExecutionSpec

        return ExecutionSpec(scanner_id=self.scanner_id, container_image="fake:1", command=["fake"])

    async def execute(self, execution_spec, context):
        from modules.security.scanner_adapter import ScannerExecutionResult

        return ScannerExecutionResult(scanner_id=self.scanner_id, exit_code=0, stdout="{}")

    def parse_results(self, result):
        return []


@pytest.fixture
def fake_registry(monkeypatch):
    registry = ScannerRegistry()
    registry.register(
        ScannerDefinition(
            id="trivy", name="Trivy", category=ScannerCategory.CONTAINER_SUPPLY_CHAIN,
            container_image="fake:1", supported_target_types=[TargetType.CONTAINER_IMAGE],
        ),
        _FakeAdapter("trivy"),
    )
    monkeypatch.setattr("modules.security.routes.get_scanner_registry", lambda: registry)
    monkeypatch.setattr("modules.security.policy.get_scanner_registry", lambda: registry)
    monkeypatch.setattr("modules.security.scan_service.get_scanner_registry", lambda: registry)
    monkeypatch.setattr("modules.security.workflows.get_scanner_registry", lambda: registry)
    yield registry


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


@pytest.fixture
def client(fake_registry, security_db):
    app = FastAPI()
    app.include_router(router, prefix="/api/security")
    with TestClient(app) as c:
        yield c


# ── Targets ────────────────────────────────────────────────────────────


def test_create_and_get_target(client):
    resp = client.post("/api/security/targets", json={
        "name": "prod-image", "target_type": "container_image", "locator": "registry.local/foo:1.0",
    })
    assert resp.status_code == 201
    target_id = resp.json()["id"]

    resp2 = client.get(f"/api/security/targets/{target_id}")
    assert resp2.status_code == 200
    assert resp2.json()["name"] == "prod-image"


def test_get_unknown_target_404(client):
    resp = client.get("/api/security/targets/does-not-exist")
    assert resp.status_code == 404


def test_list_targets_returns_created(client):
    client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    })
    resp = client.get("/api/security/targets")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_update_target_patches_fields(client):
    created = client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    }).json()
    resp = client.patch(f"/api/security/targets/{created['id']}", json={"owner": "alice"})
    assert resp.status_code == 200
    assert resp.json()["owner"] == "alice"
    assert resp.json()["name"] == "t1"  # unveraendert


def test_update_unknown_target_404(client):
    resp = client.patch("/api/security/targets/does-not-exist", json={"owner": "alice"})
    assert resp.status_code == 404


def test_delete_target(client):
    created = client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    }).json()
    resp = client.delete(f"/api/security/targets/{created['id']}")
    assert resp.status_code == 200
    assert client.get(f"/api/security/targets/{created['id']}").status_code == 404


def test_create_target_rejects_invalid_body(client):
    resp = client.post("/api/security/targets", json={"name": "t1"})  # target_type/locator fehlen
    assert resp.status_code == 422


# ── Scanners/Profiles/Workflows (read-only) ──────────────────────────────


def test_list_scanners(client):
    resp = client.get("/api/security/scanners")
    assert resp.status_code == 200
    assert any(s["id"] == "trivy" for s in resp.json())


def test_list_profiles(client):
    resp = client.get("/api/security/profiles")
    assert resp.status_code == 200
    ids = {p["id"] for p in resp.json()}
    assert {"passive", "standard", "intrusive"} <= ids


def test_list_workflows(client):
    resp = client.get("/api/security/workflows")
    assert resp.status_code == 200
    assert len(resp.json()) == 5


# ── Runs ───────────────────────────────────────────────────────────────


def test_create_run_returns_202_and_queued_status(client):
    target = client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    }).json()
    resp = client.post("/api/security/runs", json={
        "target_id": target["id"], "scanner_id": "trivy", "profile_id": "passive",
    })
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"


def test_create_run_unknown_target_returns_422(client):
    resp = client.post("/api/security/runs", json={
        "target_id": "does-not-exist", "scanner_id": "trivy", "profile_id": "passive",
    })
    assert resp.status_code == 422


def test_get_run_after_creation(client):
    target = client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    }).json()
    created = client.post("/api/security/runs", json={
        "target_id": target["id"], "scanner_id": "trivy", "profile_id": "passive",
    }).json()
    resp = client.get(f"/api/security/runs/{created['id']}")
    assert resp.status_code == 200
    # Background-Task lief synchron im TestClient bis hier durch.
    assert resp.json()["status"] in ("completed", "queued", "running")


def test_get_unknown_run_404(client):
    resp = client.get("/api/security/runs/does-not-exist")
    assert resp.status_code == 404


def test_cancel_already_completed_run_returns_422(client):
    """TestClient fuehrt BackgroundTasks synchron vor Rueckgabe der Kontrolle aus
    (via ASGITransport) — der Run ist zum Zeitpunkt von /cancel bereits 'completed',
    ein Abbruch ist dann korrekt nicht mehr moeglich."""
    target = client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    }).json()
    created = client.post("/api/security/runs", json={
        "target_id": target["id"], "scanner_id": "trivy", "profile_id": "passive",
    }).json()
    resp = client.post(f"/api/security/runs/{created['id']}/cancel")
    assert resp.status_code == 422


def test_cancel_unknown_run_404(client):
    resp = client.post("/api/security/runs/does-not-exist/cancel")
    assert resp.status_code == 404


# ── Findings ───────────────────────────────────────────────────────────


def test_list_findings_invalid_severity_422(client):
    resp = client.get("/api/security/findings", params={"severity": "not-a-severity"})
    assert resp.status_code == 422


def test_get_unknown_finding_404(client):
    resp = client.get("/api/security/findings/does-not-exist")
    assert resp.status_code == 404


def test_update_unknown_finding_404(client):
    resp = client.patch("/api/security/findings/does-not-exist", json={"status": "resolved"})
    assert resp.status_code == 404


def test_update_finding_invalid_status_422(client):
    resp = client.patch("/api/security/findings/f1", json={"status": "not-a-status"})
    assert resp.status_code == 422


# ── Workflow-Run-Endpoint ────────────────────────────────────────────────


def test_run_workflow_unknown_target_404(client):
    resp = client.post(
        "/api/security/workflows/container_image_audit/run", json={"target_id": "does-not-exist"}
    )
    assert resp.status_code == 404


def test_run_workflow_success(client):
    target = client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    }).json()
    resp = client.post(
        "/api/security/workflows/container_image_audit/run", json={"target_id": target["id"]}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["workflow_id"] == "container_image_audit"
    assert data["steps"][0]["scanner_id"] == "trivy"


def test_run_unknown_workflow_422(client):
    target = client.post("/api/security/targets", json={
        "name": "t1", "target_type": "container_image", "locator": "img:1",
    }).json()
    resp = client.post(
        "/api/security/workflows/does-not-exist/run", json={"target_id": target["id"]}
    )
    assert resp.status_code == 422
