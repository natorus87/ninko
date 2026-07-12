"""Gitleaks-Adapter — Secret Scanning in Git-Repositories (Passive)."""

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

GITLEAKS_DEFINITION = ScannerDefinition(
    id="gitleaks",
    name="Gitleaks",
    description="Secret-Scanning in Git-Repositories (API-Keys, Tokens, Passwoerter im Code).",
    category=ScannerCategory.SECRET_SCANNING,
    container_image="ghcr.io/gitleaks/gitleaks:v8.18.4",
    version="8.18.4",
    output_format="json",
    parser="gitleaks_json",
    required_network_access=True,
    default_timeout=300.0,
    risk_level=ScanProfileKind.PASSIVE,
    supported_target_types=[TargetType.GIT_REPOSITORY],
    enabled=True,
)

_CLONE_IMAGE = "alpine/git:2.45.2"


class GitleaksAdapter:
    scanner_id = "gitleaks"

    def validate_target(self, target, profile, parameters) -> ValidationResult:
        errors = []
        if target.target_type != TargetType.GIT_REPOSITORY:
            errors.append("Gitleaks unterstuetzt nur target_type git_repository.")
        if not target.locator.startswith(("https://", "http://", "git@")):
            errors.append("Locator muss eine gueltige Git-Repository-URL sein.")
        return ValidationResult(valid=not errors, errors=errors)

    def build_execution_spec(self, target, profile, parameters) -> ExecutionSpec:
        secret_refs = [target.credentials_reference] if target.credentials_reference else []
        clone_env = {}
        if target.credentials_reference:
            # Konvention: Secret enthaelt eine askpass.sh-Datei fuer HTTPS-Auth.
            clone_env["GIT_ASKPASS"] = f"/secrets/{target.credentials_reference}/askpass.sh"

        init = InitContainerSpec(
            name="git-clone",
            image=_CLONE_IMAGE,
            command=["git", "clone", "--depth", "1", target.locator, "/workspace/repo"],
            env=clone_env,
        )

        return ExecutionSpec(
            scanner_id=self.scanner_id,
            container_image=GITLEAKS_DEFINITION.container_image,
            command=[
                "gitleaks", "detect",
                "--source", "/workspace/repo",
                "--no-git",
                "-f", "json",
                "-r", "/dev/stdout",
                "--exit-code", "0",
            ],
            secret_refs=secret_refs,
            init_containers=[init],
            resource_limits={"cpu": "500m", "memory": "512Mi"},
            timeout_s=GITLEAKS_DEFINITION.default_timeout,
            network_policy=NetworkPolicy(mode="egress_allowlist", allowlist=[]),
            max_output_bytes=5_000_000,
        )

    async def execute(self, execution_spec: ExecutionSpec, context) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        stdout = result.stdout
        start = stdout.find("[")
        if start == -1:
            raise ValueError("Gitleaks-Output enthaelt kein JSON-Array (kein '[' gefunden).")
        try:
            leaks = json.loads(stdout[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Gitleaks-Output ist kein gueltiges JSON: {exc}") from exc

        findings: list[NormalizedFinding] = []
        for leak in leaks:
            rule_id = leak.get("RuleID", "unknown-rule")
            file_path = leak.get("File", "")
            start_line = leak.get("StartLine", "")
            # Secret-Wert NIE im Klartext speichern (nur Fingerprint/Rule/Ort) —
            # "keine Secrets im Prompt oder in Logs" (Auftrags-Sicherheitsregel).
            findings.append(
                NormalizedFinding(
                    rule_id=rule_id,
                    title=f"Leaked secret: {rule_id}",
                    description=(leak.get("Description") or rule_id),
                    severity=Severity.HIGH,
                    confidence=1.0,
                    category="leaked_secret",
                    resource_type="file",
                    resource_identifier=file_path,
                    location=f"{file_path}:{start_line}",
                    remediation="Rotate the leaked credential immediately and remove it from git history.",
                    metadata={
                        "commit": leak.get("Commit"),
                        "author": leak.get("Author"),
                        "date": leak.get("Date"),
                        "fingerprint": leak.get("Fingerprint"),
                    },
                )
            )
        return findings
