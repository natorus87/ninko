"""Trivy-Adapter — Container Image Scanning (Passive)."""

from __future__ import annotations

import json

from ..models import ScanProfile, ScannerCategory, ScannerDefinition, ScanProfileKind, SecurityTarget, Severity, TargetType
from ..scanner_adapter import (
    ExecutionSpec,
    NetworkPolicy,
    NormalizedFinding,
    ScannerExecutionResult,
    SecurityExecutionContext,
    ValidationResult,
)

_ALLOWED_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})

_SEVERITY_MAP: dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL,
    "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM,
    "LOW": Severity.LOW,
    "UNKNOWN": Severity.INFO,
}

TRIVY_DEFINITION = ScannerDefinition(
    id="trivy",
    name="Trivy",
    description="Container-Image-, Filesystem- und SBOM-Scanner (Aqua Security). Passiv, read-only.",
    category=ScannerCategory.CONTAINER_SUPPLY_CHAIN,
    container_image="aquasec/trivy:0.55.2",
    version="0.55.2",
    output_format="json",
    parser="trivy_json",
    required_capabilities=[],
    required_mounts=[],
    required_network_access=True,  # Image-Pull + Vulnerability-DB-Download
    default_timeout=300.0,
    risk_level=ScanProfileKind.PASSIVE,
    supports_active_scan=False,
    supports_authenticated_scan=False,
    requires_confirmation=False,
    supported_target_types=[TargetType.CONTAINER_IMAGE],
    enabled=True,
)


class TrivyAdapter:
    scanner_id = "trivy"

    def validate_target(
        self, target: SecurityTarget, profile: ScanProfile, parameters: dict
    ) -> ValidationResult:
        errors: list[str] = []
        if target.target_type != TargetType.CONTAINER_IMAGE:
            errors.append(f"Trivy unterstuetzt target_type {target.target_type.value} nicht (nur container_image).")
        if not target.locator or any(ch.isspace() for ch in target.locator):
            errors.append("Locator muss eine gueltige Image-Referenz ohne Leerzeichen sein.")
        severity_filter = (parameters or {}).get("severity_filter")
        if severity_filter:
            invalid = set(severity_filter) - _ALLOWED_SEVERITIES
            if invalid:
                errors.append(f"Ungueltige severity_filter-Werte: {sorted(invalid)}")
        return ValidationResult(valid=not errors, errors=errors)

    def build_execution_spec(
        self, target: SecurityTarget, profile: ScanProfile, parameters: dict
    ) -> ExecutionSpec:
        severity_filter = (parameters or {}).get("severity_filter") or sorted(_ALLOWED_SEVERITIES)
        invalid = set(severity_filter) - _ALLOWED_SEVERITIES
        if invalid:
            raise ValueError(f"Ungueltige severity_filter-Werte: {sorted(invalid)}")

        command = [
            "trivy", "image",
            "--format", "json",
            "--scanners", "vuln",
            "--severity", ",".join(sorted(severity_filter)),
            "--cache-dir", "/tmp/trivy-cache",
            "--quiet",
            target.locator,
        ]

        return ExecutionSpec(
            scanner_id=self.scanner_id,
            container_image=TRIVY_DEFINITION.container_image,
            command=command,
            env={"TRIVY_TIMEOUT": "4m"},
            resource_limits={"cpu": "1", "memory": "1Gi"},
            timeout_s=TRIVY_DEFINITION.default_timeout,
            # Trivy braucht Zugriff auf beliebige Registries + die Aqua Vulnerability-DB —
            # kein statisches CIDR-Allowlist moeglich, daher explizit offenes Egress
            # (mode="open", NICHT egress_allowlist mit leerer Liste — das waere jetzt
            # Deny-all, siehe executor.py). Scope-Durchsetzung fuer das TARGET (welches
            # Image ueberhaupt gescannt werden darf) laeuft ueber policy.py.
            network_policy=NetworkPolicy(mode="open", allowlist=[]),
            max_output_bytes=5_000_000,
        )

    async def execute(
        self, execution_spec: ExecutionSpec, context: SecurityExecutionContext
    ) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Trivy-Output ist kein gueltiges JSON: {exc}") from exc

        findings: list[NormalizedFinding] = []
        for res in data.get("Results") or []:
            target_label = res.get("Target", "")
            for vuln in res.get("Vulnerabilities") or []:
                vuln_id = vuln.get("VulnerabilityID", "UNKNOWN")
                severity = _SEVERITY_MAP.get((vuln.get("Severity") or "").upper(), Severity.INFO)
                cvss_score = None
                for vendor_scores in (vuln.get("CVSS") or {}).values():
                    if isinstance(vendor_scores, dict) and "V3Score" in vendor_scores:
                        cvss_score = vendor_scores["V3Score"]
                        break
                fixed_version = vuln.get("FixedVersion")

                findings.append(
                    NormalizedFinding(
                        rule_id=vuln_id,
                        title=vuln.get("Title") or vuln_id,
                        description=(vuln.get("Description") or "")[:2000],
                        severity=severity,
                        confidence=1.0,
                        category="vulnerability",
                        cve=vuln_id if vuln_id.startswith("CVE-") else None,
                        cvss=cvss_score,
                        resource_type="package",
                        resource_identifier=vuln.get("PkgName", ""),
                        location=target_label,
                        remediation=f"Update auf Version {fixed_version}" if fixed_version else None,
                        metadata={
                            "installed_version": vuln.get("InstalledVersion"),
                            "fixed_version": fixed_version,
                        },
                    )
                )
        return findings
