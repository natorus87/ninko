"""testssl.sh-Adapter — TLS-Konfigurationspruefung ohne aktive Exploitation (Passive)."""

from __future__ import annotations

import json

from ..models import ScannerCategory, ScannerDefinition, ScanProfileKind, Severity, TargetType
from ..scanner_adapter import (
    ExecutionSpec,
    NetworkPolicy,
    NormalizedFinding,
    ScannerExecutionResult,
    ValidationResult,
)

TESTSSL_DEFINITION = ScannerDefinition(
    id="testssl",
    name="testssl.sh",
    description="TLS/SSL-Konfigurationspruefung (Protokollversionen, Cipher Suites, Zertifikate).",
    category=ScannerCategory.NETWORK,
    container_image="drwetter/testssl.sh:3.2",
    version="3.2",
    output_format="json",
    parser="testssl_json",
    required_network_access=True,
    default_timeout=300.0,
    risk_level=ScanProfileKind.PASSIVE,
    supported_target_types=[TargetType.TLS_ENDPOINT, TargetType.URL, TargetType.HOSTNAME],
    enabled=True,
)

_RELEVANT_SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
_SEVERITY_MAP: dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL, "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW,
}


class TestSSLAdapter:
    scanner_id = "testssl"

    def validate_target(self, target, profile, parameters) -> ValidationResult:
        errors = []
        if target.target_type not in (TargetType.TLS_ENDPOINT, TargetType.URL, TargetType.HOSTNAME):
            errors.append("testssl.sh unterstuetzt nur tls_endpoint/url/hostname.")
        return ValidationResult(valid=not errors, errors=errors)

    def build_execution_spec(self, target, profile, parameters) -> ExecutionSpec:
        return ExecutionSpec(
            scanner_id=self.scanner_id,
            container_image=TESTSSL_DEFINITION.container_image,
            command=["--quiet", "--jsonfile", "/dev/stdout", "--warnings", "batch", target.locator],
            resource_limits={"cpu": "500m", "memory": "512Mi"},
            timeout_s=TESTSSL_DEFINITION.default_timeout,
            network_policy=NetworkPolicy(mode="target_only", allowlist=[]),
            max_output_bytes=5_000_000,
        )

    async def execute(self, execution_spec: ExecutionSpec, context) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        stdout = result.stdout
        start = stdout.find("[")
        if start == -1:
            raise ValueError("testssl.sh-Output enthaelt kein JSON-Array.")
        try:
            entries = json.loads(stdout[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"testssl.sh-Output ist kein gueltiges JSON: {exc}") from exc

        findings: list[NormalizedFinding] = []
        for entry in entries:
            severity_raw = (entry.get("severity") or "").upper()
            if severity_raw not in _RELEVANT_SEVERITIES:
                continue  # OK/INFO/DEBUG/WARN sind kein Finding, nur Rauschen
            severity = _SEVERITY_MAP.get(severity_raw, Severity.LOW)
            check_id = entry.get("id", "unknown-check")

            findings.append(
                NormalizedFinding(
                    rule_id=check_id,
                    title=f"TLS finding: {check_id}",
                    description=entry.get("finding", ""),
                    severity=severity,
                    category="tls_configuration",
                    cve=entry.get("cve") or None,
                    cwe=entry.get("cwe") or None,
                    resource_type="tls_endpoint",
                    resource_identifier=f"{entry.get('ip', '')}:{entry.get('port', '')}",
                    location=entry.get("ip", ""),
                )
            )
        return findings
