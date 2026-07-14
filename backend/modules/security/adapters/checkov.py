"""Checkov-Adapter — IaC-Scanning in Git-Repositories (Passive)."""

from __future__ import annotations

import json

from ..models import ScannerCategory, ScannerDefinition, ScanProfileKind, Severity, TargetType
from ..scanner_adapter import (
    ExecutionSpec,
    InitContainerSpec,
    NetworkPolicy,
    NormalizedFinding,
    ScannerExecutionResult,
    ValidationResult,
)

CHECKOV_DEFINITION = ScannerDefinition(
    id="checkov",
    name="Checkov",
    description="IaC-Scanning fuer Terraform, Kubernetes, Helm und Dockerfiles.",
    category=ScannerCategory.IAC,
    container_image="bridgecrew/checkov:3.2.0",
    version="3.2.0",
    output_format="json",
    parser="checkov_json",
    required_network_access=True,
    default_timeout=300.0,
    risk_level=ScanProfileKind.PASSIVE,
    supported_target_types=[TargetType.GIT_REPOSITORY],
    enabled=True,
)

_CLONE_IMAGE = "alpine/git:2.45.2"

_SEVERITY_MAP: dict[str, Severity] = {
    "CRITICAL": Severity.CRITICAL, "HIGH": Severity.HIGH,
    "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW,
}


class CheckovAdapter:
    scanner_id = "checkov"

    def validate_target(self, target, profile, parameters) -> ValidationResult:
        errors = []
        if target.target_type != TargetType.GIT_REPOSITORY:
            errors.append("Checkov unterstuetzt nur target_type git_repository.")
        if not target.locator.startswith(("https://", "http://", "git@")):
            errors.append("Locator muss eine gueltige Git-Repository-URL sein.")
        return ValidationResult(valid=not errors, errors=errors)

    def build_execution_spec(self, target, profile, parameters) -> ExecutionSpec:
        secret_refs = [target.credentials_reference] if target.credentials_reference else []
        clone_env = {}
        if target.credentials_reference:
            clone_env["GIT_ASKPASS"] = f"/secrets/{target.credentials_reference}/askpass.sh"

        init = InitContainerSpec(
            name="git-clone",
            image=_CLONE_IMAGE,
            command=["git", "clone", "--depth", "1", target.locator, "/workspace/repo"],
            env=clone_env,
        )

        return ExecutionSpec(
            scanner_id=self.scanner_id,
            container_image=CHECKOV_DEFINITION.container_image,
            command=["checkov", "-d", "/workspace/repo", "-o", "json", "--compact", "--quiet"],
            secret_refs=secret_refs,
            init_containers=[init],
            resource_limits={"cpu": "1", "memory": "1Gi"},
            timeout_s=CHECKOV_DEFINITION.default_timeout,
            # Init-Container klont von einer beliebigen Git-Host-URL -> explizit offenes
            # Egress (mode="open"), kein leeres egress_allowlist (das waere jetzt
            # Deny-all, siehe executor.py, und wuerde den Clone-Schritt brechen).
            network_policy=NetworkPolicy(mode="open", allowlist=[]),
            max_output_bytes=5_000_000,
        )

    async def execute(self, execution_spec: ExecutionSpec, context) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        stdout = result.stdout.strip()
        start = stdout.find("{")
        start_list = stdout.find("[")
        if start_list != -1 and (start == -1 or start_list < start):
            start = start_list
        if start == -1:
            raise ValueError("Checkov-Output enthaelt kein JSON.")
        try:
            data = json.loads(stdout[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Checkov-Output ist kein gueltiges JSON: {exc}") from exc

        # Checkov gibt bei mehreren erkannten Frameworks eine LISTE von Reports zurueck,
        # bei genau einem Framework ein einzelnes Dict.
        reports = data if isinstance(data, list) else [data]

        findings: list[NormalizedFinding] = []
        for report in reports:
            failed_checks = (report.get("results") or {}).get("failed_checks") or []
            for check in failed_checks:
                severity_raw = (check.get("severity") or "MEDIUM").upper()
                severity = _SEVERITY_MAP.get(severity_raw, Severity.MEDIUM)
                file_path = check.get("file_path", "")
                line_range = check.get("file_line_range") or []
                location = f"{file_path}:{line_range[0]}" if line_range else file_path

                findings.append(
                    NormalizedFinding(
                        rule_id=check.get("check_id", "unknown-check"),
                        title=check.get("check_name", check.get("check_id", "IaC misconfiguration")),
                        description=check.get("check_name", ""),
                        severity=severity,
                        category="iac_misconfiguration",
                        resource_type=report.get("check_type", "iac_resource"),
                        resource_identifier=check.get("resource", ""),
                        location=location,
                        remediation=check.get("guideline"),
                        metadata={"check_type": report.get("check_type")},
                    )
                )
        return findings
