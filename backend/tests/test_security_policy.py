"""Unit-Tests fuer die Security-Core Policy Engine (Task 3):
Scope-Validierung, Approval-Gate, SSRF-Schutz.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from modules.security.models import (
    ScanProfileKind,
    ScannerCategory,
    ScannerDefinition,
    SecurityTarget,
    TargetType,
    TriggerType,
)
from modules.security.policy import (
    PolicyViolation,
    create_approval_request,
    decide_approval,
    enforce_allowlists,
    enforce_capabilities,
    enforce_network_scope,
    enforce_trigger_policy,
    is_approved,
    validate_scan_request,
)
from modules.security.scanner_registry import ScannerRegistry

pytestmark = pytest.mark.unit


class _FakeAdapter:
    def __init__(self, scanner_id: str) -> None:
        self.scanner_id = scanner_id


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """Isolierte ScannerRegistry pro Test — kein Leck in den globalen Singleton."""
    registry = ScannerRegistry()
    trivy = ScannerDefinition(
        id="trivy",
        name="Trivy",
        category=ScannerCategory.CONTAINER_SUPPLY_CHAIN,
        container_image="aquasec/trivy:0.55.0",
        risk_level=ScanProfileKind.PASSIVE,
        supported_target_types=[TargetType.CONTAINER_IMAGE],
    )
    registry.register(trivy, _FakeAdapter("trivy"))
    nuclei = ScannerDefinition(
        id="nuclei",
        name="Nuclei",
        category=ScannerCategory.WEB,
        container_image="projectdiscovery/nuclei:latest",
        risk_level=ScanProfileKind.INTRUSIVE,
        supported_target_types=[TargetType.URL],
    )
    registry.register(nuclei, _FakeAdapter("nuclei"))
    disabled = ScannerDefinition(
        id="disabled-scanner",
        name="Disabled",
        category=ScannerCategory.HOST,
        container_image="x:1",
        enabled=False,
        supported_target_types=[TargetType.HOSTNAME],
    )
    registry.register(disabled, _FakeAdapter("disabled-scanner"))

    monkeypatch.setattr("modules.security.policy.get_scanner_registry", lambda: registry)
    yield registry


def _target(**overrides) -> SecurityTarget:
    defaults = {
        "name": "test-image",
        "target_type": TargetType.CONTAINER_IMAGE,
        "locator": "registry.local/foo:latest",
    }
    defaults.update(overrides)
    return SecurityTarget(**defaults)


# ── enforce_allowlists ────────────────────────────────────────────────────


def test_enforce_allowlists_passes_for_valid_combo():
    enforce_allowlists(_target(), "trivy", "passive")  # darf nicht werfen


def test_enforce_allowlists_rejects_disabled_target():
    target = _target(enabled=False)
    with pytest.raises(PolicyViolation, match="deaktiviert"):
        enforce_allowlists(target, "trivy", "passive")


def test_enforce_allowlists_rejects_disabled_scanner():
    with pytest.raises(PolicyViolation, match="deaktiviert"):
        enforce_allowlists(_target(target_type=TargetType.HOSTNAME, locator="host.local"), "disabled-scanner", "passive")


def test_enforce_allowlists_rejects_scanner_not_in_profile():
    with pytest.raises(PolicyViolation, match="nicht erlaubt"):
        enforce_allowlists(_target(target_type=TargetType.URL, locator="https://example.com"), "nuclei", "passive")


def test_enforce_allowlists_rejects_unsupported_target_type():
    target = _target(target_type=TargetType.URL, locator="https://example.com")
    with pytest.raises(PolicyViolation, match="unterstuetzt"):
        enforce_allowlists(target, "trivy", "passive")


def test_enforce_allowlists_rejects_scanner_outside_target_allowlist():
    target = _target(allowed_scanners=["kubescape"])
    with pytest.raises(PolicyViolation, match="nicht freigegeben"):
        enforce_allowlists(target, "trivy", "passive")


def test_enforce_allowlists_allows_scanner_in_target_allowlist():
    target = _target(allowed_scanners=["trivy", "kubescape"])
    enforce_allowlists(target, "trivy", "passive")  # darf nicht werfen


def test_enforce_allowlists_rejects_profile_outside_target_allowlist():
    target = _target(allowed_profiles=[ScanProfileKind.INTRUSIVE])
    with pytest.raises(PolicyViolation, match="nicht freigegeben"):
        enforce_allowlists(target, "trivy", "passive")


def test_enforce_allowlists_unknown_scanner_propagates():
    from modules.security.scanner_registry import UnknownScannerError

    with pytest.raises(UnknownScannerError):
        enforce_allowlists(_target(), "does-not-exist", "passive")


# ── enforce_trigger_policy ──────────────────────────────────────────────


def test_intrusive_profile_rejects_cron_trigger():
    with pytest.raises(PolicyViolation, match="manuell"):
        enforce_trigger_policy("intrusive", TriggerType.CRON)


def test_intrusive_profile_allows_manual_trigger():
    enforce_trigger_policy("intrusive", TriggerType.MANUAL)  # darf nicht werfen


def test_passive_profile_allows_cron_trigger():
    enforce_trigger_policy("passive", TriggerType.CRON)  # darf nicht werfen


# ── enforce_network_scope ─────────────────────────────────────────────────


def test_network_scope_skips_non_network_target_types():
    target = _target(target_type=TargetType.CONTAINER_IMAGE, locator="registry.local/foo:latest")
    assert enforce_network_scope(target) == []


def test_network_scope_blocks_link_local_metadata_url():
    target = SecurityTarget(
        name="metadata", target_type=TargetType.URL, locator="http://169.254.169.254/latest/meta-data"
    )
    with pytest.raises(PolicyViolation):
        enforce_network_scope(target)


def test_network_scope_blocks_link_local_ip_address_target_without_url_prefix():
    """Regressionstest: der harte Link-Local/Metadata-Block darf nicht nur fuer
    http(s)-URLs greifen — Nmap/testssl.sh adressieren Ziele als blossen
    IP_ADDRESS/HOSTNAME-Locator ohne http(s)-Praefix. Frueher wurde dieser Fall
    komplett uebersprungen (kein PolicyViolation), solange kein cidr_allowlist
    gesetzt war."""
    target = SecurityTarget(name="metadata-ip", target_type=TargetType.IP_ADDRESS, locator="169.254.169.254")
    with pytest.raises(PolicyViolation, match="Link-Local/Metadata"):
        enforce_network_scope(target)


def test_network_scope_blocks_link_local_hostname_target_without_cidr_allowlist():
    target = SecurityTarget(name="metadata-host", target_type=TargetType.HOSTNAME, locator="169.254.169.254")
    with pytest.raises(PolicyViolation, match="Link-Local/Metadata"):
        enforce_network_scope(target)


def test_network_scope_blocks_outside_cidr_allowlist():
    target = SecurityTarget(
        name="loopback-check",
        target_type=TargetType.HOSTNAME,
        locator="localhost",
        scope_constraints={"cidr_allowlist": ["10.0.0.0/8"]},
    )
    with pytest.raises(PolicyViolation, match="ausserhalb des erlaubten CIDR-Scopes"):
        enforce_network_scope(target)


def test_network_scope_allows_within_cidr_allowlist():
    target = SecurityTarget(
        name="loopback-check",
        target_type=TargetType.HOSTNAME,
        locator="localhost",
        scope_constraints={"cidr_allowlist": ["127.0.0.0/8", "::1/128"]},
    )
    enforce_network_scope(target)  # darf nicht werfen


def test_network_scope_fails_closed_on_unresolvable_host():
    target = SecurityTarget(
        name="bad-host",
        target_type=TargetType.HOSTNAME,
        locator="this-host-does-not-exist.invalid",
        scope_constraints={"cidr_allowlist": ["10.0.0.0/8"]},
    )
    with pytest.raises(PolicyViolation, match="nicht aufgeloest"):
        enforce_network_scope(target)


def test_network_scope_no_allowlist_only_net_guard_applies():
    target = SecurityTarget(name="public", target_type=TargetType.URL, locator="https://example.com")
    enforce_network_scope(target)  # darf nicht werfen (kein cidr_allowlist gesetzt)


# ── enforce_capabilities ───────────────────────────────────────────────────


def test_capabilities_denied_blocks_even_if_in_allowed_list():
    with pytest.raises(PolicyViolation, match="verboten"):
        enforce_capabilities(
            "security.scan.execute.intrusive",
            agent_capabilities=["security.scan.execute.intrusive"],
            denied_capabilities=["security.scan.execute.intrusive"],
        )


def test_capabilities_missing_required_blocks():
    with pytest.raises(PolicyViolation, match="hat die Capability"):
        enforce_capabilities(
            "security.scan.execute.intrusive", agent_capabilities=["security.scan.create"], denied_capabilities=[]
        )


def test_capabilities_empty_agent_list_means_no_restriction():
    enforce_capabilities("security.scan.execute.intrusive", agent_capabilities=[], denied_capabilities=[])


def test_capabilities_present_and_allowed_passes():
    enforce_capabilities(
        "security.scan.create", agent_capabilities=["security.scan.create"], denied_capabilities=[]
    )


# ── validate_scan_request (Integration) ────────────────────────────────────


def test_validate_scan_request_passive_does_not_require_approval():
    decision = validate_scan_request(
        target=_target(), scanner_id="trivy", profile_id="passive", trigger_type=TriggerType.CRON
    )
    assert decision.allowed is True
    assert decision.requires_approval is False


def test_validate_scan_request_intrusive_requires_approval():
    target = _target(target_type=TargetType.URL, locator="https://example.com")
    decision = validate_scan_request(
        target=target, scanner_id="nuclei", profile_id="intrusive", trigger_type=TriggerType.MANUAL
    )
    assert decision.allowed is True
    assert decision.requires_approval is True


def test_validate_scan_request_rejects_capability_violation():
    with pytest.raises(PolicyViolation):
        validate_scan_request(
            target=_target(),
            scanner_id="trivy",
            profile_id="passive",
            trigger_type=TriggerType.MANUAL,
            required_capability="security.scan.execute.intrusive",
            agent_capabilities=["security.scan.create"],
        )


# ── Approval-Gate (Redis gemockt) ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_approval_request_persists_to_redis(mock_redis):
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        request = await create_approval_request(
            scan_run_id="run-1", target=_target(), scanner_id="nuclei", profile_id="intrusive",
            requested_by="alice",
        )
    assert request.scan_run_id == "run-1"
    assert request.status == "pending"
    mock_redis.connection.set.assert_called_once()
    args, kwargs = mock_redis.connection.set.call_args
    assert args[0] == "ninko:security:approval:run-1"
    assert kwargs["ex"] == 900


@pytest.mark.asyncio
async def test_decide_approval_without_pending_request_raises(mock_redis):
    mock_redis.connection.get.return_value = None
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        with pytest.raises(PolicyViolation, match="Keine gueltige Freigabe"):
            await decide_approval("run-does-not-exist", approved=True, decided_by="bob")


@pytest.mark.asyncio
async def test_decide_approval_approves_pending_request(mock_redis):
    import time

    pending = {
        "approval_id": "a1", "scan_run_id": "run-2", "target_id": "t1", "scanner_id": "nuclei",
        "profile_id": "intrusive", "scope_summary": "x", "requested_by": "alice",
        "requested_at": time.time(), "expires_at": time.time() + 900, "status": "pending",
        "decided_by": None, "decided_at": None,
    }
    mock_redis.connection.get.return_value = json.dumps(pending)
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        decided = await decide_approval("run-2", approved=True, decided_by="bob")
    assert decided.status == "approved"
    assert decided.decided_by == "bob"


@pytest.mark.asyncio
async def test_is_approved_false_when_no_request(mock_redis):
    mock_redis.connection.get.return_value = None
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        assert await is_approved("run-none") is False


@pytest.mark.asyncio
async def test_is_approved_false_when_rejected(mock_redis):
    import time

    rejected = {
        "approval_id": "a1", "scan_run_id": "run-3", "target_id": "t1", "scanner_id": "nuclei",
        "profile_id": "intrusive", "scope_summary": "x", "requested_by": "alice",
        "requested_at": time.time(), "expires_at": time.time() + 900, "status": "rejected",
        "decided_by": "bob", "decided_at": time.time(),
    }
    mock_redis.connection.get.return_value = json.dumps(rejected)
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        assert await is_approved("run-3") is False


@pytest.mark.asyncio
async def test_is_approved_true_when_approved_and_not_expired(mock_redis):
    import time

    approved = {
        "approval_id": "a1", "scan_run_id": "run-4", "target_id": "t1", "scanner_id": "nuclei",
        "profile_id": "intrusive", "scope_summary": "x", "requested_by": "alice",
        "requested_at": time.time(), "expires_at": time.time() + 900, "status": "approved",
        "decided_by": "bob", "decided_at": time.time(),
    }
    mock_redis.connection.get.return_value = json.dumps(approved)
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        assert await is_approved("run-4") is True


@pytest.mark.asyncio
async def test_is_approved_false_when_expired(mock_redis):
    import time

    expired = {
        "approval_id": "a1", "scan_run_id": "run-5", "target_id": "t1", "scanner_id": "nuclei",
        "profile_id": "intrusive", "scope_summary": "x", "requested_by": "alice",
        "requested_at": time.time() - 1000, "expires_at": time.time() - 100, "status": "approved",
        "decided_by": "bob", "decided_at": time.time() - 100,
    }
    mock_redis.connection.get.return_value = json.dumps(expired)
    with patch("core.redis_client.get_redis", return_value=mock_redis):
        assert await is_approved("run-5") is False
