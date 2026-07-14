"""Nuclei-Adapter — Template-basiertes Vulnerability-Scanning.

Registriert in BEIDEN Profilen (standard + intrusive, siehe scanner_registry.py)
— welche Template-Kategorien laufen, haengt vom uebergebenen ScanProfile ab:
Standard nutzt nur "sichere" Tags und schliesst dos/fuzz/intrusive aus,
Intrusive erlaubt zusaetzlich aggressive Kategorien.
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
    resolve_locator_egress_allowlist,
)

NUCLEI_DEFINITION = ScannerDefinition(
    id="nuclei",
    name="Nuclei",
    description="Template-basiertes Vulnerability-Scanning fuer Web- und Netzwerk-Ziele.",
    category=ScannerCategory.WEB,
    container_image="projectdiscovery/nuclei:v3.3.5",
    version="3.3.5",
    output_format="jsonl",
    parser="nuclei_jsonl",
    required_network_access=True,
    default_timeout=300.0,
    risk_level=ScanProfileKind.STANDARD,
    supports_active_scan=True,
    requires_confirmation=True,
    supported_target_types=[TargetType.URL, TargetType.API_ENDPOINT, TargetType.HOSTNAME],
    enabled=True,
)

_SAFE_TAGS = "cve,exposure,misconfig,default-login"
_SAFE_EXCLUDE_TAGS = "dos,fuzz,intrusive"

_SEVERITY_MAP: dict[str, Severity] = {
    "critical": Severity.CRITICAL, "high": Severity.HIGH,
    "medium": Severity.MEDIUM, "low": Severity.LOW, "info": Severity.INFO,
}


class NucleiAdapter:
    scanner_id = "nuclei"

    def validate_target(self, target, profile, parameters) -> ValidationResult:
        errors = []
        if target.target_type not in (TargetType.URL, TargetType.API_ENDPOINT, TargetType.HOSTNAME):
            errors.append("Nuclei unterstuetzt nur url/api_endpoint/hostname.")
        return ValidationResult(valid=not errors, errors=errors)

    def build_execution_spec(self, target, profile, parameters) -> ExecutionSpec:
        command = ["nuclei", "-target", target.locator, "-jsonl", "-silent", "-tags", _SAFE_TAGS]
        if profile.kind == ScanProfileKind.INTRUSIVE:
            # Intrusive-Profil (Approval bereits von policy.py erzwungen, bevor dieser
            # Adapter ueberhaupt aufgerufen wird): aggressive Kategorien zulassen.
            command = ["nuclei", "-target", target.locator, "-jsonl", "-silent",
                       "-tags", f"{_SAFE_TAGS},dos,fuzz,intrusive"]
        else:
            command.extend(["-exclude-tags", _SAFE_EXCLUDE_TAGS])

        # Ziel zur Laufzeit aufloesen -> echte Egress-Allowlist statt offenem Netz.
        # Nicht aufloesbar: mode="open" (offen, explizit), niemals ein leeres
        # allowlist unter target_only (das ist jetzt Deny-all, siehe executor.py).
        allowlist = resolve_locator_egress_allowlist(target.locator)

        return ExecutionSpec(
            scanner_id=self.scanner_id,
            container_image=NUCLEI_DEFINITION.container_image,
            command=command,
            resource_limits={"cpu": "500m", "memory": "512Mi"},
            timeout_s=NUCLEI_DEFINITION.default_timeout,
            network_policy=NetworkPolicy(
                mode="target_only" if allowlist else "open", allowlist=allowlist
            ),
            max_output_bytes=5_000_000,
        )

    async def execute(self, execution_spec: ExecutionSpec, context) -> ScannerExecutionResult:
        return await context.executor.run(execution_spec, scan_run_id=context.scan_run_id)

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        findings: list[NormalizedFinding] = []
        had_any_line = False
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            had_any_line = True
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Nuclei-Output enthaelt eine ungueltige JSONL-Zeile: {exc}") from exc

            info = entry.get("info") or {}
            severity_raw = (info.get("severity") or "info").lower()
            severity = _SEVERITY_MAP.get(severity_raw, Severity.INFO)
            classification = info.get("classification") or {}
            cve_ids = classification.get("cve-id") or []
            cwe_ids = classification.get("cwe-id") or []

            findings.append(
                NormalizedFinding(
                    rule_id=entry.get("template-id", "unknown-template"),
                    title=info.get("name", entry.get("template-id", "Nuclei finding")),
                    description=info.get("description", ""),
                    severity=severity,
                    category="web_vulnerability",
                    cve=cve_ids[0] if cve_ids else None,
                    cwe=cwe_ids[0] if cwe_ids else None,
                    resource_type="http_endpoint",
                    resource_identifier=entry.get("host", ""),
                    location=entry.get("matched-at", entry.get("host", "")),
                    metadata={"matcher_name": entry.get("matcher-name")},
                )
            )
        if not had_any_line and result.exit_code != 0:
            raise ValueError(f"Nuclei beendete sich mit exit_code={result.exit_code} ohne verwertbaren Output.")
        return findings
