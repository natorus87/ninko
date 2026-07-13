"""Kubescape-Adapter — Kubernetes-Cluster-Sicherheitsscans (NSA/MITRE-Frameworks, Passive).

WICHTIG: Kubescape braucht Zugriff auf die API des ZIEL-Clusters — anders als
Trivy (scannt nur eine Image-Referenz) reicht die eigene, absichtlich minimale
ninko-security-ServiceAccount-Identitaet des Scan-Jobs dafuer nicht aus.
`target.credentials_reference` MUSS auf ein bereits im ninko-security-Namespace
angelegtes Kubernetes-Secret zeigen, das eine kubeconfig-Datei enthaelt
(Schluessel 'kubeconfig'). Ninko legt dieses Secret nicht selbst an (kein
automatischer Vault-Sync in dieser Phase) — dokumentierte MVP-Limitation.

Das exakte JSON-Ausgabeschema von Kubescape wurde NICHT live gegen einen
echten Kubescape-Lauf verifiziert (siehe project_security_core.md) — die
Parsing-Logik ist defensiv (fehlende Felder -> Defaults) und gegen ein
plausibles, dokumentiertes Schema getestet, sollte aber vor Produktiveinsatz
gegen einen echten Scan-Output nachverifiziert werden.
"""

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

KUBESCAPE_DEFINITION = ScannerDefinition(
    id="kubescape",
    name="Kubescape",
    description="Kubernetes-Cluster-Sicherheitsscan gegen NSA/MITRE-Frameworks und CIS Benchmark.",
    category=ScannerCategory.KUBERNETES,
    container_image="quay.io/kubescape/kubescape:v3.0.11",
    version="3.0.11",
    output_format="json",
    parser="kubescape_json",
    required_network_access=True,  # Zugriff auf die Ziel-Cluster-API
    default_timeout=420.0,
    risk_level=ScanProfileKind.PASSIVE,
    supported_target_types=[TargetType.KUBERNETES_NAMESPACE, TargetType.KUBERNETES_CLUSTER],
    enabled=True,
)

_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL, "high": Severity.HIGH,
    "medium": Severity.MEDIUM, "low": Severity.LOW,
}


class KubescapeAdapter:
    scanner_id = "kubescape"

    def validate_target(self, target, profile, parameters) -> ValidationResult:
        errors = []
        if target.target_type not in (TargetType.KUBERNETES_NAMESPACE, TargetType.KUBERNETES_CLUSTER):
            errors.append("Kubescape unterstuetzt nur kubernetes_namespace/kubernetes_cluster.")
        if not target.credentials_reference:
            errors.append(
                "Kubescape braucht eine credentials_reference (Kubeconfig-Secret) fuer den Ziel-Cluster."
            )
        return ValidationResult(valid=not errors, errors=errors)

    def build_execution_spec(self, target, profile, parameters) -> ExecutionSpec:
        framework = (parameters or {}).get("framework", "nsa")
        if framework not in ("nsa", "mitre", "cis-v1.23-t1.0.1"):
            raise ValueError(f"Ungueltiges Kubescape-Framework: {framework}")

        command = [
            "kubescape", "scan", "framework", framework,
            "--format", "json",
            "--output", "/dev/stdout",
            "--kubeconfig", f"/secrets/{target.credentials_reference}/kubeconfig",
        ]
        if target.target_type == TargetType.KUBERNETES_NAMESPACE:
            command.extend(["--include-namespaces", target.locator])

        return ExecutionSpec(
            scanner_id=self.scanner_id,
            container_image=KUBESCAPE_DEFINITION.container_image,
            command=command,
            secret_refs=[target.credentials_reference],
            resource_limits={"cpu": "1", "memory": "1Gi"},
            timeout_s=KUBESCAPE_DEFINITION.default_timeout,
            # Ziel-Cluster-API-IP ist aus der kubeconfig-Secret-Referenz nicht statisch
            # bekannt -> explizit offenes Egress (mode="open"), kein leeres
            # egress_allowlist (das waere jetzt Deny-all, siehe executor.py).
            network_policy=NetworkPolicy(mode="open", allowlist=[]),
            max_output_bytes=10_000_000,
        )

    async def execute(self, execution_spec: ExecutionSpec, context) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        stdout = result.stdout
        start = stdout.find("{")
        if start == -1:
            raise ValueError("Kubescape-Output enthaelt kein JSON-Objekt.")
        try:
            data = json.loads(stdout[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Kubescape-Output ist kein gueltiges JSON: {exc}") from exc

        controls = ((data.get("summaryDetails") or {}).get("controls")) or {}
        findings: list[NormalizedFinding] = []
        for control_id, control in controls.items():
            status = ((control.get("status") or {}).get("status") or "").lower()
            if status != "failed":
                continue
            severity_raw = str(control.get("scoreFactor", control.get("severity", "medium"))).lower()
            severity = _SEVERITY_MAP.get(severity_raw, Severity.MEDIUM)

            findings.append(
                NormalizedFinding(
                    rule_id=control_id,
                    title=control.get("name", control_id),
                    description=control.get("description", ""),
                    severity=severity,
                    category="kubernetes_misconfiguration",
                    resource_type="kubernetes_control",
                    resource_identifier=control.get("name", control_id),
                    location=str(target_locator(data)),
                    remediation=control.get("remediation"),
                    metadata={"framework": control.get("baseScore")},
                )
            )
        return findings


def target_locator(data: dict) -> str:
    """Best-effort Cluster-/Kontext-Name aus dem Kubescape-Report fuer die location."""
    return (data.get("clusterAPIServerInfo") or {}).get("gitVersion", "cluster")
