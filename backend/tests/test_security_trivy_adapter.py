"""Unit-Tests fuer den Trivy-Adapter (Task 4)."""

from __future__ import annotations

import json

import pytest

from modules.security.adapters.trivy import TrivyAdapter
from modules.security.models import ScanProfile, ScanProfileKind, SecurityTarget, Severity, TargetType
from modules.security.scanner_adapter import ScannerExecutionResult

pytestmark = pytest.mark.unit


def _target(**overrides) -> SecurityTarget:
    defaults = {"name": "test-image", "target_type": TargetType.CONTAINER_IMAGE, "locator": "registry.local/foo:1.0"}
    defaults.update(overrides)
    return SecurityTarget(**defaults)


def _profile() -> ScanProfile:
    return ScanProfile(id="passive", name="Passive", kind=ScanProfileKind.PASSIVE, allowed_scanner_ids=["trivy"])


# ── validate_target ────────────────────────────────────────────────────


def test_validate_target_rejects_non_container_image():
    adapter = TrivyAdapter()
    target = _target(target_type=TargetType.URL, locator="https://example.com")
    result = adapter.validate_target(target, _profile(), {})
    assert result.valid is False
    assert any("container_image" in e for e in result.errors)


def test_validate_target_rejects_locator_with_whitespace():
    adapter = TrivyAdapter()
    target = _target(locator="registry.local/foo bar:1.0")
    result = adapter.validate_target(target, _profile(), {})
    assert result.valid is False


def test_validate_target_rejects_invalid_severity_filter():
    adapter = TrivyAdapter()
    result = adapter.validate_target(_target(), _profile(), {"severity_filter": ["NOT_A_SEVERITY"]})
    assert result.valid is False


def test_validate_target_accepts_valid_combo():
    adapter = TrivyAdapter()
    result = adapter.validate_target(_target(), _profile(), {"severity_filter": ["HIGH", "CRITICAL"]})
    assert result.valid is True
    assert result.errors == []


# ── build_execution_spec ──────────────────────────────────────────────────


def test_build_execution_spec_uses_argument_array_no_shell():
    adapter = TrivyAdapter()
    spec = adapter.build_execution_spec(_target(), _profile(), {})
    assert spec.command[0] == "trivy"
    spec.assert_no_shell_string()  # darf nicht werfen
    assert "registry.local/foo:1.0" in spec.command


def test_build_execution_spec_default_severity_includes_all():
    adapter = TrivyAdapter()
    spec = adapter.build_execution_spec(_target(), _profile(), {})
    sev_idx = spec.command.index("--severity") + 1
    severities = set(spec.command[sev_idx].split(","))
    assert severities == {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def test_build_execution_spec_respects_severity_filter():
    adapter = TrivyAdapter()
    spec = adapter.build_execution_spec(_target(), _profile(), {"severity_filter": ["CRITICAL"]})
    sev_idx = spec.command.index("--severity") + 1
    assert spec.command[sev_idx] == "CRITICAL"


def test_build_execution_spec_rejects_invalid_severity_filter():
    adapter = TrivyAdapter()
    with pytest.raises(ValueError):
        adapter.build_execution_spec(_target(), _profile(), {"severity_filter": ["BOGUS"]})


def test_build_execution_spec_network_policy_documents_open_egress():
    """Trivy braucht Zugriff auf beliebige Registries + die Vulnerability-DB —
    kein statisches Allowlist moeglich, daher explizit mode='open' (NICHT
    'egress_allowlist' mit leerer Liste, das ist inzwischen Deny-all, siehe
    executor.py)."""
    adapter = TrivyAdapter()
    spec = adapter.build_execution_spec(_target(), _profile(), {})
    assert spec.network_policy.mode == "open"
    assert spec.network_policy.allowlist == []


# ── parse_results ──────────────────────────────────────────────────────────


_SAMPLE_TRIVY_OUTPUT = {
    "SchemaVersion": 2,
    "ArtifactName": "registry.local/foo:1.0",
    "Results": [
        {
            "Target": "registry.local/foo:1.0 (alpine 3.20)",
            "Class": "os-pkgs",
            "Type": "alpine",
            "Vulnerabilities": [
                {
                    "VulnerabilityID": "CVE-2024-9999",
                    "PkgName": "libfoo",
                    "InstalledVersion": "1.0.0",
                    "FixedVersion": "1.0.1",
                    "Title": "libfoo: buffer overflow",
                    "Description": "A buffer overflow in libfoo allows...",
                    "Severity": "HIGH",
                    "CVSS": {"nvd": {"V3Score": 7.5}},
                },
                {
                    "VulnerabilityID": "CVE-2024-1111",
                    "PkgName": "libbar",
                    "InstalledVersion": "2.0.0",
                    "Severity": "LOW",
                },
            ],
        }
    ],
}


def _result(stdout: str, exit_code: int = 0) -> ScannerExecutionResult:
    return ScannerExecutionResult(scanner_id="trivy", exit_code=exit_code, stdout=stdout)


def test_parse_results_maps_fields_correctly():
    adapter = TrivyAdapter()
    findings = adapter.parse_results(_result(json.dumps(_SAMPLE_TRIVY_OUTPUT)))
    assert len(findings) == 2

    high = next(f for f in findings if f.rule_id == "CVE-2024-9999")
    assert high.severity == Severity.HIGH
    assert high.cve == "CVE-2024-9999"
    assert high.cvss == 7.5
    assert high.resource_identifier == "libfoo"
    assert high.remediation == "Update auf Version 1.0.1"
    assert high.metadata["fixed_version"] == "1.0.1"

    low = next(f for f in findings if f.rule_id == "CVE-2024-1111")
    assert low.severity == Severity.LOW
    assert low.remediation is None


def test_parse_results_handles_no_vulnerabilities():
    empty = {"SchemaVersion": 2, "ArtifactName": "x", "Results": [{"Target": "x", "Vulnerabilities": []}]}
    adapter = TrivyAdapter()
    findings = adapter.parse_results(_result(json.dumps(empty)))
    assert findings == []


def test_parse_results_handles_missing_results_key():
    adapter = TrivyAdapter()
    findings = adapter.parse_results(_result(json.dumps({"SchemaVersion": 2, "ArtifactName": "x"})))
    assert findings == []


def test_parse_results_raises_on_invalid_json():
    adapter = TrivyAdapter()
    with pytest.raises(ValueError, match="kein gueltiges JSON"):
        adapter.parse_results(_result("not json at all"))


def test_parse_results_non_cve_vulnerability_id_not_treated_as_cve():
    data = {
        "Results": [
            {"Target": "x", "Vulnerabilities": [{"VulnerabilityID": "GHSA-xxxx-yyyy", "Severity": "MEDIUM"}]}
        ]
    }
    adapter = TrivyAdapter()
    findings = adapter.parse_results(_result(json.dumps(data)))
    assert findings[0].cve is None
    assert findings[0].rule_id == "GHSA-xxxx-yyyy"
