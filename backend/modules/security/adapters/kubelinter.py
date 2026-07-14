"""KubeLinter-Adapter — statische Analyse von Kubernetes-/Helm-Manifesten in Git-Repos (Passive).

Anders als Kubescape (das gegen einen LIVE-Cluster laeuft) lintet KubeLinter
YAML-Dateien statisch — braucht daher keine Cluster-Zugangsdaten, sondern
(wie Gitleaks/Checkov) einen Git-Checkout via Init-Container.
"""

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

KUBELINTER_DEFINITION = ScannerDefinition(
    id="kubelinter",
    name="KubeLinter",
    description="Statische Analyse von Kubernetes-Manifesten und Helm-Charts in Git-Repositories.",
    category=ScannerCategory.KUBERNETES,
    container_image="stackrox/kube-linter:v0.6.8",
    version="0.6.8",
    output_format="json",
    parser="kubelinter_json",
    required_network_access=True,
    default_timeout=180.0,
    risk_level=ScanProfileKind.PASSIVE,
    supported_target_types=[TargetType.GIT_REPOSITORY],
    enabled=True,
)

_CLONE_IMAGE = "alpine/git:2.45.2"


class KubeLinterAdapter:
    scanner_id = "kubelinter"

    def validate_target(self, target, profile, parameters) -> ValidationResult:
        errors = []
        if target.target_type != TargetType.GIT_REPOSITORY:
            errors.append("KubeLinter unterstuetzt nur target_type git_repository.")
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
            container_image=KUBELINTER_DEFINITION.container_image,
            command=["kube-linter", "lint", "/workspace/repo", "--format", "json"],
            secret_refs=secret_refs,
            init_containers=[init],
            resource_limits={"cpu": "500m", "memory": "512Mi"},
            timeout_s=KUBELINTER_DEFINITION.default_timeout,
            # Init-Container klont von einer beliebigen Git-Host-URL -> explizit offenes
            # Egress (mode="open"), kein leeres egress_allowlist (das waere jetzt
            # Deny-all, siehe executor.py, und wuerde den Clone-Schritt brechen).
            network_policy=NetworkPolicy(mode="open", allowlist=[]),
            max_output_bytes=5_000_000,
        )

    async def execute(self, execution_spec: ExecutionSpec, context) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        stdout = result.stdout
        start = stdout.find("{")
        if start == -1:
            # KubeLinter meldet exit_code!=0 UND druckt "no lint errors" ohne JSON, wenn nichts gefunden wurde.
            if "no lint errors" in stdout.lower() or not stdout.strip():
                return []
            raise ValueError("KubeLinter-Output enthaelt kein JSON-Objekt.")
        try:
            data = json.loads(stdout[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"KubeLinter-Output ist kein gueltiges JSON: {exc}") from exc

        findings: list[NormalizedFinding] = []
        for report in data.get("Reports") or []:
            check = report.get("Check", "unknown-check")
            k8s_object = ((report.get("Object") or {}).get("K8sObject")) or {}
            kind = ((k8s_object.get("GroupVersionKind") or {}).get("Kind")) or "Resource"
            name = k8s_object.get("Name", "")
            namespace = k8s_object.get("Namespace", "")

            findings.append(
                NormalizedFinding(
                    rule_id=check,
                    title=f"{check}: {kind} {name}".strip(),
                    description=(report.get("Diagnostic") or {}).get("Message", ""),
                    severity=Severity.MEDIUM,
                    category="kubernetes_manifest_lint",
                    resource_type=kind,
                    resource_identifier=name,
                    location=namespace or "cluster-scoped",
                    remediation=report.get("Remediation"),
                    metadata={"check": check},
                )
            )
        return findings
