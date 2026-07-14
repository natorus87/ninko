"""Security Core — 5 MVP Audit-Workflows.

Kein neuer WorkflowEngine-Node-Typ. Der Node-Dispatch in core/workflow_engine.py
ist ein fester if/elif-Block ohne Extension-Point, und der Datenfluss zwischen
Nodes ist ein globales variables-Dict mit reiner String-Interpolation
(core/workflow_engine.py:_interpolate) — fuer strukturierte Findings-Ketten
(Resolve -> Scope-Validate -> Scan -> Parse -> Normalize -> Dedupe -> Report)
ungeeignet und ein invasiver Eingriff in eine von allen Workflows geteilte
Datei. Stattdessen: jeder Security-Workflow ist EIN bestehender `agent`-Node
(config.agent_id="security"), dessen Prompt run_security_workflow() ausloest.
Die eigentliche Mehrfach-Scanner-Orchestrierung passiert HIER in Python mit
strukturierten Objekten, nicht in der Engine. Siehe project_security_core.md
fuer die vollstaendige Abwaegung.

Jeder Workflow ist eine kuratierte, nach Prioritaet geordnete Scanner-Liste.
Zur Laufzeit werden nur Scanner ausgefuehrt, die (a) registriert sind, (b) den
Target-Typ unterstuetzen und (c) — falls gesetzt — in target.allowed_scanners
stehen. Inkompatible Scanner werden übersprungen (nicht als Fehler behandelt),
mit Begruendung im Ergebnis.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .models import ScanRun, SecurityTarget, TargetType, TriggerType
from .policy import PolicyViolation
from .scan_service import start_scan
from .scanner_registry import BUILTIN_SCAN_PROFILES, get_scanner_registry

logger = logging.getLogger("ninko.modules.security.workflows")


@dataclass(frozen=True)
class SecurityWorkflowDefinition:
    id: str
    name: str
    description: str
    target_types: list[TargetType]
    preferred_scanner_ids: list[str]


SECURITY_WORKFLOWS: dict[str, SecurityWorkflowDefinition] = {
    "kubernetes_full_audit": SecurityWorkflowDefinition(
        id="kubernetes_full_audit",
        name="Kubernetes Full Audit",
        description=(
            "Kubescape-Scan (NSA-Framework) gegen einen Kubernetes-Cluster oder -Namespace. "
            "MVP-Scope: nur Kubescape, da KubeLinter in dieser Phase als Git-Repository-Linter "
            "implementiert ist (siehe git_repository_audit) und kube-bench/Trivy-Kubernetes "
            "noch nicht als Adapter existieren."
        ),
        target_types=[TargetType.KUBERNETES_NAMESPACE, TargetType.KUBERNETES_CLUSTER],
        preferred_scanner_ids=["kubescape"],
    ),
    "container_image_audit": SecurityWorkflowDefinition(
        id="container_image_audit",
        name="Container Image Audit",
        description=(
            "Trivy-Vulnerability-Scan gegen ein Container-Image. "
            "MVP-Scope: Grype/Syft-SBOM-Merge ist Folgearbeit."
        ),
        target_types=[TargetType.CONTAINER_IMAGE],
        preferred_scanner_ids=["trivy"],
    ),
    "external_service_audit": SecurityWorkflowDefinition(
        id="external_service_audit",
        name="External Service Audit",
        description=(
            "Nmap-Service-Discovery, TLS-Konfigurationspruefung (testssl.sh) und Nuclei-Safe-"
            "Templates gegen einen erlaubten Host. Alle drei Scanner laufen gegen dasselbe "
            "Target — praezise Weiterreichung nur der von Nmap entdeckten offenen Ports an "
            "testssl/Nuclei ist Folgearbeit."
        ),
        target_types=[TargetType.IP_ADDRESS, TargetType.HOSTNAME, TargetType.CIDR],
        preferred_scanner_ids=["nmap", "testssl", "nuclei"],
    ),
    "git_repository_audit": SecurityWorkflowDefinition(
        id="git_repository_audit",
        name="Git Repository Audit",
        description=(
            "Gitleaks-Secret-Scan, Checkov-IaC-Scan und KubeLinter-Manifest-Lint gegen ein "
            "Git-Repository."
        ),
        target_types=[TargetType.GIT_REPOSITORY],
        preferred_scanner_ids=["gitleaks", "checkov", "kubelinter"],
    ),
    "ai_platform_audit": SecurityWorkflowDefinition(
        id="ai_platform_audit",
        name="AI Platform Audit",
        description=(
            "Garak-Sicherheitsprobing (Prompt Injection, Leakage) gegen einen LLM- oder "
            "OpenAI-kompatiblen Endpoint. Intrusiv — benoetigt explizite menschliche Freigabe "
            "vor der Ausfuehrung (WAITING_FOR_APPROVAL)."
        ),
        target_types=[
            TargetType.LLM_ENDPOINT, TargetType.OPENAI_COMPATIBLE_API,
            TargetType.LITELLM_GATEWAY, TargetType.VLLM_ENDPOINT, TargetType.OPEN_WEBUI_INSTANCE,
        ],
        preferred_scanner_ids=["garak"],
    ),
}


@dataclass
class WorkflowStepResult:
    scanner_id: str
    run: ScanRun | None = None
    skipped_reason: str | None = None


@dataclass
class SecurityWorkflowResult:
    workflow_id: str
    target_id: str
    steps: list[WorkflowStepResult] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0

    @property
    def total_findings(self) -> int:
        return sum(s.run.finding_count for s in self.steps if s.run is not None)

    @property
    def executed_scanner_ids(self) -> list[str]:
        return [s.scanner_id for s in self.steps if s.run is not None]

    @property
    def skipped_scanner_ids(self) -> list[str]:
        return [s.scanner_id for s in self.steps if s.run is None]


def _pick_profile_for_scanner(scanner_id: str) -> str:
    """Waehlt das am wenigsten intrusive Profil, in dem der Scanner registriert ist —
    Workflows sind standardmaessig nicht-intrusiv; nur Scanner, die AUSSCHLIESSLICH
    im intrusive-Profil stehen (z.B. Garak), loesen den Approval-Gate aus."""
    for profile_id in ("passive", "standard", "intrusive"):
        if scanner_id in BUILTIN_SCAN_PROFILES[profile_id].allowed_scanner_ids:
            return profile_id
    raise ValueError(f"Scanner {scanner_id!r} ist in keinem Scan-Profil registriert.")


def get_workflow(workflow_id: str) -> SecurityWorkflowDefinition:
    workflow = SECURITY_WORKFLOWS.get(workflow_id)
    if workflow is None:
        raise ValueError(
            f"Unbekannter Security-Workflow: {workflow_id!r}. Verfuegbar: {sorted(SECURITY_WORKFLOWS)}"
        )
    return workflow


async def run_security_workflow(
    workflow_id: str,
    *,
    target: SecurityTarget,
    requested_by: str = "",
    trigger_type: TriggerType = TriggerType.MANUAL,
    tenant_id: str = "",
) -> SecurityWorkflowResult:
    """Fuehrt alle zum Target passenden Scanner eines Workflows sequenziell aus.

    Wirft PolicyViolation, wenn der Target-Typ vom Workflow grundsaetzlich nicht
    unterstuetzt wird (fail-fast). Einzelne inkompatible/nicht-erlaubte Scanner
    innerhalb eines ansonsten passenden Workflows werden uebersprungen, nicht
    als Fehler behandelt — ein Repository ohne IaC-Dateien soll nicht den
    gesamten Git-Repository-Audit scheitern lassen, nur weil Checkov nichts
    Relevantes findet (das entscheidet ohnehin scan_service, nicht hier).
    """
    workflow = get_workflow(workflow_id)
    if target.target_type not in workflow.target_types:
        raise PolicyViolation(
            f"Workflow {workflow_id!r} unterstuetzt Target-Typ {target.target_type.value!r} nicht "
            f"(erwartet: {[t.value for t in workflow.target_types]})."
        )

    registry = get_scanner_registry()
    started_at = time.time()
    steps: list[WorkflowStepResult] = []

    for scanner_id in workflow.preferred_scanner_ids:
        if not registry.is_registered(scanner_id):
            steps.append(WorkflowStepResult(scanner_id, skipped_reason="Scanner nicht registriert"))
            continue

        definition = registry.get_definition(scanner_id)
        if target.target_type not in definition.supported_target_types:
            steps.append(WorkflowStepResult(
                scanner_id, skipped_reason=f"Scanner unterstuetzt Target-Typ {target.target_type.value} nicht"
            ))
            continue
        if target.allowed_scanners and scanner_id not in target.allowed_scanners:
            steps.append(WorkflowStepResult(scanner_id, skipped_reason="Nicht in target.allowed_scanners"))
            continue

        try:
            profile_id = _pick_profile_for_scanner(scanner_id)
        except ValueError as exc:
            steps.append(WorkflowStepResult(scanner_id, skipped_reason=str(exc)))
            continue

        try:
            run = await start_scan(
                target_id=target.id, scanner_id=scanner_id, profile_id=profile_id,
                requested_by=requested_by, trigger_type=trigger_type, tenant_id=tenant_id,
            )
        except PolicyViolation as exc:
            steps.append(WorkflowStepResult(scanner_id, skipped_reason=str(exc)))
            continue

        steps.append(WorkflowStepResult(scanner_id, run=run))

    if not any(s.run is not None for s in steps):
        logger.warning(
            "Security-Workflow %s: kein Scanner ausfuehrbar fuer Target %s (%s)",
            workflow_id, target.id, [s.skipped_reason for s in steps],
        )

    return SecurityWorkflowResult(
        workflow_id=workflow_id, target_id=target.id, steps=steps,
        started_at=started_at, completed_at=time.time(),
    )
