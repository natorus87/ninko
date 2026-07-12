"""Security Core — Scanner-Adapter-Interface.

Jeder Scanner wird ueber einen typisierten Adapter angebunden. Kein Scanner
wird je ueber einen vom LLM erzeugten freien Shell-String aufgerufen: Adapter
bauen einen `ExecutionSpec` mit einem Argument-Array (`command`), niemals
einen konkatenierten Shell-String — das macht Command Injection strukturell
unmoeglich, nicht nur durch Escaping.

Ausfuehrung erfolgt ausschliesslich ueber einen Executor (siehe executor.py,
K8sJobExecutor), der den ExecutionSpec entgegennimmt. Adapter selbst starten
niemals direkt einen Subprocess.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from .models import ScanProfile, SecurityTarget, Severity


class ValidationResult(BaseModel):
    """Ergebnis der Vorab-Validierung eines Scan-Vorhabens."""

    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NetworkPolicy(BaseModel):
    """Erlaubte ausgehende Netzwerkziele fuer den Scan-Job (Default: nichts erlaubt)."""

    model_config = ConfigDict(extra="forbid")

    mode: str = "target_only"  # "none" | "target_only" | "egress_allowlist"
    allowlist: list[str] = Field(default_factory=list)


class VolumeMount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    mount_path: str
    read_only: bool = True


class ExecutionSpec(BaseModel):
    """Vollstaendig validierte, deterministisch aus Adapter-Logik gebaute Job-Spezifikation.

    `command` ist immer ein Argument-Array (execve-Semantik), niemals ein
    Shell-String. `env` enthaelt nur explizit erlaubte Variablen — keine
    Secrets im Klartext (nur `secret_refs`, die der Executor zur Laufzeit aus
    dem Vault aufloest und als Env/Datei injiziert).
    """

    model_config = ConfigDict(extra="forbid")

    scanner_id: str
    container_image: str  # inkl. Tag oder Digest, z.B. aquasec/trivy:0.55.0
    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)
    secret_refs: list[str] = Field(default_factory=list)
    resource_limits: dict[str, str] = Field(
        default_factory=lambda: {"cpu": "500m", "memory": "512Mi"}
    )
    timeout_s: float = 300.0
    network_policy: NetworkPolicy = Field(default_factory=NetworkPolicy)
    volumes: list[VolumeMount] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    service_account: str = "ninko-security-scanner"
    output_paths: list[str] = Field(default_factory=list)
    max_output_bytes: int = 5_000_000

    def assert_no_shell_string(self) -> None:
        """Verteidigungslinie: command darf niemals ein einzelnes Shell-String-Element sein."""
        if len(self.command) == 1 and any(ch in self.command[0] for ch in (";", "|", "&&", "$(", "`")):
            raise ValueError(
                "ExecutionSpec.command sieht wie ein Shell-String aus — "
                "Argument-Array erforderlich, kein konkateniertes Kommando."
            )


class ScannerExecutionResult(BaseModel):
    """Rohes, unveraendertes Ergebnis eines Scanner-Laufs (vor dem Parsing)."""

    model_config = ConfigDict(extra="forbid")

    scanner_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    duration_s: float = 0.0
    job_name: str = ""
    scanner_version: str = ""


class NormalizedFinding(BaseModel):
    """Scanner-neutrales Zwischenformat — wird von db.upsert_finding in ein
    persistiertes Finding inkl. Fingerprint/ID/Timestamps ueberfuehrt.
    """

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    title: str
    description: str = ""
    severity: Severity
    confidence: float = 1.0
    category: str = ""
    cve: str | None = None
    cwe: str | None = None
    cvss: float | None = None
    resource_type: str = ""
    resource_identifier: str = ""
    location: str = ""
    remediation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class SecurityScannerAdapter(Protocol):
    """Vertrag, den jeder Scanner-Adapter erfuellen muss."""

    scanner_id: str

    def validate_target(
        self, target: SecurityTarget, profile: ScanProfile, parameters: dict[str, Any]
    ) -> ValidationResult:
        """Prueft, ob dieser Scanner fuer Target-Typ, Profil und Parameter zulaessig ist.

        Muss rein und ohne Seiteneffekt sein (kein Netzwerk-/Dateisystemzugriff).
        """
        ...

    def build_execution_spec(
        self, target: SecurityTarget, profile: ScanProfile, parameters: dict[str, Any]
    ) -> ExecutionSpec:
        """Baut die vollstaendige, validierte ExecutionSpec. Muss nur aus
        registrierten Konstanten, validierten Parametern und dem Target-Locator
        zusammensetzen — keine vom LLM diktierten Freitext-Flags uebernehmen,
        ohne sie gegen eine Allowlist zu pruefen.
        """
        ...

    async def execute(
        self, execution_spec: ExecutionSpec, context: "SecurityExecutionContext"
    ) -> ScannerExecutionResult:
        """Delegiert an context.executor — Adapter starten nie selbst einen Prozess."""
        ...

    def parse_results(self, result: ScannerExecutionResult) -> list[NormalizedFinding]:
        """Parst die rohe Scanner-Ausgabe in normalisierte Findings.

        Darf bei Parse-Fehlern nicht stillschweigend leere Liste zurueckgeben —
        wirft ValueError, damit der Run als FAILED/PARTIALLY_COMPLETED markiert wird.
        """
        ...


class SecurityExecutionContext(BaseModel):
    """Laufzeitkontext, den ein Adapter beim Ausfuehren erhaelt."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    scan_run_id: str
    tenant_id: str = ""
    requested_by: str = ""
    executor: Any = None  # ScanExecutor-Instanz, siehe executor.py (Any wg. Protocol+Pydantic)
