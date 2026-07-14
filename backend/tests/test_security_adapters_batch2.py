"""Unit-Tests fuer die 8 restlichen MVP-Scanner-Adapter (Task 7):
Gitleaks, Checkov, Kubescape, KubeLinter, Nmap, Nuclei, testssl.sh, Garak.

Live gegen einen echten Cluster verifiziert: Trivy (Task 4), Gitleaks
(Init-Container-Pattern, siehe project_security_core.md). Die restlichen
Adapter sind hier nur mit konstruierten Fixture-Daten getestet — Kubescape
und Garak haben dokumentierte Schema-Unsicherheiten (siehe deren Modul-
Docstrings).
"""

from __future__ import annotations

import json

import pytest

from modules.security.models import ScanProfile, ScanProfileKind, SecurityTarget, Severity, TargetType
from modules.security.scanner_adapter import ScannerExecutionResult

pytestmark = pytest.mark.unit


def _result(stdout: str, exit_code: int = 0) -> ScannerExecutionResult:
    return ScannerExecutionResult(scanner_id="x", exit_code=exit_code, stdout=stdout)


def _profile(kind=ScanProfileKind.PASSIVE, allowed=None) -> ScanProfile:
    return ScanProfile(id=kind.value, name=kind.value, kind=kind, allowed_scanner_ids=allowed or [])


# ══════════════════════════════ Gitleaks ═══════════════════════════════


class TestGitleaksAdapter:
    def _target(self, **kw):
        defaults = {"name": "repo", "target_type": TargetType.GIT_REPOSITORY, "locator": "https://example.com/r.git"}
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_validate_rejects_non_git_target(self):
        from modules.security.adapters.gitleaks import GitleaksAdapter

        target = self._target(target_type=TargetType.URL, locator="https://example.com")
        result = GitleaksAdapter().validate_target(target, _profile(), {})
        assert result.valid is False

    def test_validate_rejects_bad_url_scheme(self):
        from modules.security.adapters.gitleaks import GitleaksAdapter

        target = self._target(locator="ftp://example.com/r.git")
        result = GitleaksAdapter().validate_target(target, _profile(), {})
        assert result.valid is False

    def test_build_spec_has_git_clone_init_container(self):
        from modules.security.adapters.gitleaks import GitleaksAdapter

        spec = GitleaksAdapter().build_execution_spec(self._target(), _profile(), {})
        assert len(spec.init_containers) == 1
        assert spec.init_containers[0].command[0] == "git"
        assert spec.command[0] == "gitleaks"
        spec.assert_no_shell_string()

    def test_parse_maps_leak_fields_and_never_stores_raw_secret(self):
        from modules.security.adapters.gitleaks import GitleaksAdapter

        leaks = [{
            "RuleID": "aws-access-key", "File": "config.py", "StartLine": 12,
            "Commit": "abc123", "Author": "alice", "Date": "2026-01-01",
            "Fingerprint": "fp1", "Secret": "AKIA_SUPER_SECRET_VALUE",
        }]
        findings = GitleaksAdapter().parse_results(_result("banner\n" + json.dumps(leaks)))
        assert len(findings) == 1
        f = findings[0]
        assert f.rule_id == "aws-access-key"
        assert f.severity == Severity.HIGH
        assert "AKIA_SUPER_SECRET_VALUE" not in f.description
        assert "AKIA_SUPER_SECRET_VALUE" not in str(f.metadata)

    def test_parse_raises_on_no_json_array(self):
        from modules.security.adapters.gitleaks import GitleaksAdapter

        with pytest.raises(ValueError):
            GitleaksAdapter().parse_results(_result("no leaks found, no array here"))


# ══════════════════════════════ Checkov ════════════════════════════════


class TestCheckovAdapter:
    def _target(self, **kw):
        defaults = {"name": "iac", "target_type": TargetType.GIT_REPOSITORY, "locator": "https://example.com/r.git"}
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_build_spec_uses_argument_array(self):
        from modules.security.adapters.checkov import CheckovAdapter

        spec = CheckovAdapter().build_execution_spec(self._target(), _profile(), {})
        spec.assert_no_shell_string()
        assert spec.command[0] == "checkov"

    def test_parse_single_framework_dict(self):
        from modules.security.adapters.checkov import CheckovAdapter

        data = {
            "check_type": "terraform",
            "results": {"failed_checks": [{
                "check_id": "CKV_AWS_1", "check_name": "Ensure bucket is encrypted",
                "file_path": "/main.tf", "file_line_range": [10, 15],
                "resource": "aws_s3_bucket.data", "severity": "HIGH", "guideline": "https://example.com/fix",
            }]},
        }
        findings = CheckovAdapter().parse_results(_result(json.dumps(data)))
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert findings[0].location == "/main.tf:10"

    def test_parse_multi_framework_list(self):
        from modules.security.adapters.checkov import CheckovAdapter

        data = [
            {"check_type": "terraform", "results": {"failed_checks": [
                {"check_id": "CKV_1", "check_name": "A", "file_path": "a.tf", "resource": "r1"}
            ]}},
            {"check_type": "dockerfile", "results": {"failed_checks": [
                {"check_id": "CKV_2", "check_name": "B", "file_path": "Dockerfile", "resource": "r2"}
            ]}},
        ]
        findings = CheckovAdapter().parse_results(_result(json.dumps(data)))
        assert len(findings) == 2

    def test_parse_missing_severity_defaults_to_medium(self):
        from modules.security.adapters.checkov import CheckovAdapter

        data = {"results": {"failed_checks": [{"check_id": "X", "check_name": "Y", "resource": "r"}]}}
        findings = CheckovAdapter().parse_results(_result(json.dumps(data)))
        assert findings[0].severity == Severity.MEDIUM

    def test_parse_raises_on_invalid_json(self):
        from modules.security.adapters.checkov import CheckovAdapter

        with pytest.raises(ValueError):
            CheckovAdapter().parse_results(_result("totally not json"))


# ══════════════════════════════ Kubescape ══════════════════════════════


class TestKubescapeAdapter:
    def _target(self, **kw):
        defaults = {
            "name": "ns", "target_type": TargetType.KUBERNETES_NAMESPACE, "locator": "ai-platform",
            "credentials_reference": "kubeconfig-prod",
        }
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_validate_requires_credentials_reference(self):
        from modules.security.adapters.kubescape import KubescapeAdapter

        target = self._target(credentials_reference=None)
        result = KubescapeAdapter().validate_target(target, _profile(), {})
        assert result.valid is False
        assert any("credentials_reference" in e for e in result.errors)

    def test_build_spec_mounts_kubeconfig_secret(self):
        from modules.security.adapters.kubescape import KubescapeAdapter

        spec = KubescapeAdapter().build_execution_spec(self._target(), _profile(), {})
        assert spec.secret_refs == ["kubeconfig-prod"]
        assert "/secrets/kubeconfig-prod/kubeconfig" in spec.command
        spec.assert_no_shell_string()

    def test_build_spec_rejects_invalid_framework(self):
        from modules.security.adapters.kubescape import KubescapeAdapter

        with pytest.raises(ValueError):
            KubescapeAdapter().build_execution_spec(self._target(), _profile(), {"framework": "bogus"})

    def test_parse_extracts_failed_controls_only(self):
        from modules.security.adapters.kubescape import KubescapeAdapter

        data = {
            "summaryDetails": {"controls": {
                "C-0001": {"name": "Disallow privileged", "status": {"status": "failed"}, "scoreFactor": "high"},
                "C-0002": {"name": "Passed control", "status": {"status": "passed"}},
            }}
        }
        findings = KubescapeAdapter().parse_results(_result(json.dumps(data)))
        assert len(findings) == 1
        assert findings[0].rule_id == "C-0001"
        assert findings[0].severity == Severity.HIGH

    def test_parse_raises_on_no_json_object(self):
        from modules.security.adapters.kubescape import KubescapeAdapter

        with pytest.raises(ValueError):
            KubescapeAdapter().parse_results(_result("no json here"))


# ══════════════════════════════ KubeLinter ═════════════════════════════


class TestKubeLinterAdapter:
    def _target(self, **kw):
        defaults = {"name": "manifests", "target_type": TargetType.GIT_REPOSITORY, "locator": "https://x.com/r.git"}
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_build_spec_uses_git_clone_init_container(self):
        from modules.security.adapters.kubelinter import KubeLinterAdapter

        spec = KubeLinterAdapter().build_execution_spec(self._target(), _profile(), {})
        assert len(spec.init_containers) == 1
        spec.assert_no_shell_string()

    def test_parse_no_lint_errors_returns_empty(self):
        from modules.security.adapters.kubelinter import KubeLinterAdapter

        findings = KubeLinterAdapter().parse_results(_result("no lint errors found!"))
        assert findings == []

    def test_parse_maps_report_fields(self):
        from modules.security.adapters.kubelinter import KubeLinterAdapter

        data = {"Reports": [{
            "Check": "no-read-only-root-fs",
            "Diagnostic": {"Message": "container does not have a read-only root filesystem"},
            "Remediation": "Set readOnlyRootFilesystem: true",
            "Object": {"K8sObject": {
                "GroupVersionKind": {"Kind": "Deployment"}, "Name": "web", "Namespace": "default",
            }},
        }]}
        findings = KubeLinterAdapter().parse_results(_result(json.dumps(data)))
        assert len(findings) == 1
        assert findings[0].resource_type == "Deployment"
        assert findings[0].location == "default"

    def test_parse_raises_on_garbage_when_no_success_marker(self):
        from modules.security.adapters.kubelinter import KubeLinterAdapter

        with pytest.raises(ValueError):
            KubeLinterAdapter().parse_results(_result("totally unexpected garbage output"))


# ══════════════════════════════ Nmap ═══════════════════════════════════


class TestNmapAdapter:
    def _target(self, **kw):
        defaults = {"name": "host", "target_type": TargetType.IP_ADDRESS, "locator": "10.0.0.5"}
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_validate_rejects_out_of_range_top_ports(self):
        from modules.security.adapters.nmap import NmapAdapter

        result = NmapAdapter().validate_target(self._target(), _profile(), {"top_ports": 5000})
        assert result.valid is False

    def test_build_spec_default_uses_connect_scan_no_capabilities(self):
        from modules.security.adapters.nmap import NmapAdapter

        spec = NmapAdapter().build_execution_spec(self._target(), _profile(), {})
        assert "-sT" in spec.command
        assert spec.capabilities == []
        spec.assert_no_shell_string()

    def test_build_spec_syn_scan_requires_net_raw_capability(self):
        from modules.security.adapters.nmap import NmapAdapter

        spec = NmapAdapter().build_execution_spec(self._target(), _profile(), {"syn_scan": True})
        assert "-sS" in spec.command
        assert spec.capabilities == ["NET_RAW"]

    def test_build_spec_derives_cidr_allowlist_from_ip_target(self):
        from modules.security.adapters.nmap import NmapAdapter

        spec = NmapAdapter().build_execution_spec(self._target(), _profile(), {})
        assert spec.network_policy.allowlist == ["10.0.0.5/32"]

    def test_build_spec_resolves_hostname_target_to_egress_allowlist(self):
        """Regressionstest: vor dem Fix bekam ein HOSTNAME-Target (im Gegensatz
        zu IP/CIDR) IMMER ein leeres allowlist -> mode='egress_allowlist', was
        durch den executor.py-Fix zu Deny-all geworden waere und den Scan seines
        eigenen Ziels beraubt haette. Jetzt wird der Hostname zur Laufzeit
        aufgeloest und bekommt eine echte Allowlist."""
        from modules.security.adapters.nmap import NmapAdapter

        target = self._target(target_type=TargetType.HOSTNAME, locator="localhost")
        spec = NmapAdapter().build_execution_spec(target, _profile(), {})
        assert spec.network_policy.mode == "target_only"
        assert spec.network_policy.allowlist

    def test_parse_xml_extracts_open_ports_only(self):
        from modules.security.adapters.nmap import NmapAdapter

        xml_output = """<?xml version="1.0"?>
<nmaprun>
  <host>
    <address addr="10.0.0.5" addrtype="ipv4"/>
    <ports>
      <port protocol="tcp" portid="22"><state state="open"/><service name="ssh"/></port>
      <port protocol="tcp" portid="81"><state state="closed"/><service name="http"/></port>
    </ports>
  </host>
</nmaprun>"""
        findings = NmapAdapter().parse_results(_result(xml_output))
        assert len(findings) == 1
        assert findings[0].resource_identifier == "22/tcp"
        assert findings[0].severity == Severity.INFO

    def test_parse_raises_on_invalid_xml(self):
        from modules.security.adapters.nmap import NmapAdapter

        with pytest.raises(ValueError):
            NmapAdapter().parse_results(_result("<not><valid"))


# ══════════════════════════════ Nuclei ═════════════════════════════════


class TestNucleiAdapter:
    def _target(self, **kw):
        defaults = {"name": "web", "target_type": TargetType.URL, "locator": "https://example.com"}
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_build_spec_standard_profile_excludes_intrusive_tags(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        spec = NucleiAdapter().build_execution_spec(self._target(), _profile(ScanProfileKind.STANDARD), {})
        assert "-exclude-tags" in spec.command
        spec.assert_no_shell_string()

    def test_build_spec_intrusive_profile_allows_aggressive_tags(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        spec = NucleiAdapter().build_execution_spec(self._target(), _profile(ScanProfileKind.INTRUSIVE), {})
        assert "-exclude-tags" not in spec.command
        tags_idx = spec.command.index("-tags") + 1
        assert "intrusive" in spec.command[tags_idx]

    def test_parse_jsonl_maps_severity_and_cve(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        line = json.dumps({
            "template-id": "exposed-panel", "host": "https://example.com", "matched-at": "https://example.com/admin",
            "info": {"name": "Exposed admin panel", "severity": "high", "classification": {"cve-id": ["CVE-2024-1"]}},
        })
        findings = NucleiAdapter().parse_results(_result(line + "\n"))
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert findings[0].cve == "CVE-2024-1"

    def test_parse_empty_output_success_returns_empty(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        findings = NucleiAdapter().parse_results(_result("", exit_code=0))
        assert findings == []

    def test_parse_empty_output_nonzero_exit_raises(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        with pytest.raises(ValueError):
            NucleiAdapter().parse_results(_result("", exit_code=1))

    def test_parse_raises_on_invalid_jsonl_line(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        with pytest.raises(ValueError):
            NucleiAdapter().parse_results(_result("not-json-at-all\n"))

    def test_build_spec_resolvable_target_gets_egress_allowlist(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        spec = NucleiAdapter().build_execution_spec(
            self._target(locator="http://localhost/"), _profile(), {}
        )
        assert spec.network_policy.mode == "target_only"
        assert spec.network_policy.allowlist

    def test_build_spec_unresolvable_target_falls_back_to_open(self):
        from modules.security.adapters.nuclei import NucleiAdapter

        spec = NucleiAdapter().build_execution_spec(
            self._target(locator="http://this-host-does-not-exist.invalid/"), _profile(), {}
        )
        assert spec.network_policy.mode == "open"
        assert spec.network_policy.allowlist == []


# ══════════════════════════════ testssl.sh ═════════════════════════════


class TestTestSSLAdapter:
    def _target(self, **kw):
        defaults = {"name": "tls", "target_type": TargetType.TLS_ENDPOINT, "locator": "example.com:443"}
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_build_spec_uses_argument_array(self):
        from modules.security.adapters.testssl import TestSSLAdapter

        spec = TestSSLAdapter().build_execution_spec(self._target(), _profile(), {})
        spec.assert_no_shell_string()

    def test_build_spec_resolvable_target_gets_egress_allowlist(self):
        from modules.security.adapters.testssl import TestSSLAdapter

        spec = TestSSLAdapter().build_execution_spec(
            self._target(locator="localhost:443"), _profile(), {}
        )
        assert spec.network_policy.mode == "target_only"
        assert spec.network_policy.allowlist

    def test_parse_skips_ok_and_info_severities(self):
        from modules.security.adapters.testssl import TestSSLAdapter

        entries = [
            {"id": "TLS1_2", "severity": "OK", "finding": "offered", "ip": "1.2.3.4", "port": "443"},
            {"id": "SSLv3", "severity": "HIGH", "finding": "offered (NOT ok)", "ip": "1.2.3.4", "port": "443"},
        ]
        findings = TestSSLAdapter().parse_results(_result(json.dumps(entries)))
        assert len(findings) == 1
        assert findings[0].rule_id == "SSLv3"
        assert findings[0].severity == Severity.HIGH

    def test_parse_raises_on_no_array(self):
        from modules.security.adapters.testssl import TestSSLAdapter

        with pytest.raises(ValueError):
            TestSSLAdapter().parse_results(_result("no array here"))


# ══════════════════════════════ Garak ══════════════════════════════════


class TestGarakAdapter:
    def _target(self, **kw):
        defaults = {"name": "llm", "target_type": TargetType.OPENAI_COMPATIBLE_API, "locator": "http://litellm:4000"}
        defaults.update(kw)
        return SecurityTarget(**defaults)

    def test_build_spec_rejects_invalid_probes_format(self):
        from modules.security.adapters.garak import GarakAdapter

        with pytest.raises(ValueError):
            GarakAdapter().build_execution_spec(
                self._target(), _profile(ScanProfileKind.INTRUSIVE), {"probes": "probe; rm -rf /"}
            )

    def test_build_spec_uses_argument_array(self):
        from modules.security.adapters.garak import GarakAdapter

        spec = GarakAdapter().build_execution_spec(self._target(), _profile(ScanProfileKind.INTRUSIVE), {})
        spec.assert_no_shell_string()

    def test_build_spec_unresolvable_endpoint_falls_back_to_open(self):
        """Default-Fixture-Locator 'http://litellm:4000' ist in der Test-Umgebung
        nicht aufloesbar -> explizit offenes Egress (mode='open'), niemals ein
        leeres allowlist unter target_only (das waere jetzt Deny-all)."""
        from modules.security.adapters.garak import GarakAdapter

        spec = GarakAdapter().build_execution_spec(self._target(), _profile(ScanProfileKind.INTRUSIVE), {})
        assert spec.network_policy.mode == "open"
        assert spec.network_policy.allowlist == []

    def test_build_spec_resolvable_endpoint_gets_egress_allowlist(self):
        from modules.security.adapters.garak import GarakAdapter

        spec = GarakAdapter().build_execution_spec(
            self._target(locator="http://localhost:4000"), _profile(ScanProfileKind.INTRUSIVE), {}
        )
        assert spec.network_policy.mode == "target_only"
        assert spec.network_policy.allowlist

    def test_parse_only_reports_failed_probes(self):
        from modules.security.adapters.garak import GarakAdapter

        stdout = (
            "probes.promptinject.HijackHateHumans: FAIL  ok on 3/10\n"
            "probes.leakreplay.GuardianCloze: PASS  ok on 10/10\n"
        )
        findings = GarakAdapter().parse_results(_result(stdout))
        assert len(findings) == 1
        assert findings[0].rule_id == "probes.promptinject.HijackHateHumans"
        assert findings[0].severity == Severity.HIGH  # 3/10 < 50% resistant

    def test_parse_no_matches_nonzero_exit_raises(self):
        from modules.security.adapters.garak import GarakAdapter

        with pytest.raises(ValueError):
            GarakAdapter().parse_results(_result("connection error", exit_code=1))

    def test_parse_no_matches_zero_exit_returns_empty(self):
        from modules.security.adapters.garak import GarakAdapter

        findings = GarakAdapter().parse_results(_result("nothing relevant here", exit_code=0))
        assert findings == []
