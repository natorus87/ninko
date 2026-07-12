"""Security Core — Domain-Modell.

Pydantic-Modelle fuer SecurityTarget, ScannerDefinition, ScanProfile, ScanRun,
Finding und FindingEnrichment. Original-Finding und KI-Enrichment sind bewusst
getrennte Modelle (nie vermischen — siehe FindingEnrichment).
"""

from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def _now() -> float:
    return time.time()


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Enums ──────────────────────────────────────────────────────────────


class TargetType(str, Enum):
    HOSTNAME = "hostname"
    IP_ADDRESS = "ip_address"
    CIDR = "cidr"
    URL = "url"
    API_ENDPOINT = "api_endpoint"
    GIT_REPOSITORY = "git_repository"
    CONTAINER_IMAGE = "container_image"
    KUBERNETES_CLUSTER = "kubernetes_cluster"
    KUBERNETES_NAMESPACE = "kubernetes_namespace"
    KUBERNETES_RESOURCE = "kubernetes_resource"
    HELM_CHART = "helm_chart"
    TERRAFORM_REPOSITORY = "terraform_repository"
    FILESYSTEM_PATH = "filesystem_path"
    SSH_HOST = "ssh_host"
    TLS_ENDPOINT = "tls_endpoint"
    LLM_ENDPOINT = "llm_endpoint"
    OPENAI_COMPATIBLE_API = "openai_compatible_api"
    LITELLM_GATEWAY = "litellm_gateway"
    VLLM_ENDPOINT = "vllm_endpoint"
    OPEN_WEBUI_INSTANCE = "open_webui_instance"


class ScanProfileKind(str, Enum):
    PASSIVE = "passive"
    STANDARD = "standard"
    INTRUSIVE = "intrusive"


class ScannerCategory(str, Enum):
    CONTAINER_SUPPLY_CHAIN = "container_supply_chain"
    KUBERNETES = "kubernetes"
    IAC = "iac"
    SECRET_SCANNING = "secret_scanning"
    NETWORK = "network"
    WEB = "web"
    HOST = "host"
    AI_LLM = "ai_llm"


class TriggerType(str, Enum):
    MANUAL = "manual"
    CRON = "cron"
    INTERVAL = "interval"
    WEBHOOK = "webhook"
    REPOSITORY_EVENT = "repository_event"
    IMAGE_PUSH = "image_push"
    DEPLOYMENT_EVENT = "deployment_event"
    KUBERNETES_EVENT = "kubernetes_event"
    CI_CD_EVENT = "ci_cd_event"


class ScanRunStatus(str, Enum):
    QUEUED = "queued"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    RUNNING = "running"
    PARSING = "parsing"
    ENRICHING = "enriching"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    POLICY_BLOCKED = "policy_blocked"


TERMINAL_SCAN_RUN_STATUSES = frozenset({
    ScanRunStatus.COMPLETED,
    ScanRunStatus.PARTIALLY_COMPLETED,
    ScanRunStatus.FAILED,
    ScanRunStatus.CANCELLED,
    ScanRunStatus.TIMED_OUT,
    ScanRunStatus.POLICY_BLOCKED,
})


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class FindingStatus(str, Enum):
    NEW = "new"
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    IN_PROGRESS = "in_progress"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"
    RISK_ACCEPTED = "risk_accepted"
    REOPENED = "reopened"


# ── SecurityTarget ─────────────────────────────────────────────────────


class SecurityTarget(BaseModel):
    """Ein zulaessiges Scan-Ziel. Secrets/Credentials nur als Referenz, nie inline."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=_new_id)
    name: str
    target_type: TargetType
    locator: str
    environment: str = "production"
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    allowed_scanners: list[str] = Field(default_factory=list)
    allowed_profiles: list[ScanProfileKind] = Field(default_factory=list)
    scope_constraints: dict = Field(default_factory=dict)
    credentials_reference: str | None = None
    network_zone: str = "unspecified"
    tenant_id: str = ""
    created_at: float = Field(default_factory=_now)
    updated_at: float = Field(default_factory=_now)


# ── ScannerDefinition ──────────────────────────────────────────────────


class RetryPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_retries: int = 0
    backoff_base: float = 2.0


class ScannerDefinition(BaseModel):
    """Statische Metadaten eines registrierten Scanners (kein DB-Eintrag)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    name: str
    description: str = ""
    category: ScannerCategory
    container_image: str
    version: str = "latest"
    input_schema: dict = Field(default_factory=dict)
    output_format: str = "json"
    parser: str = ""
    required_capabilities: list[str] = Field(default_factory=list)
    required_mounts: list[str] = Field(default_factory=list)
    required_network_access: bool = False
    default_timeout: float = 300.0
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    risk_level: ScanProfileKind = ScanProfileKind.PASSIVE
    supports_active_scan: bool = False
    supports_authenticated_scan: bool = False
    requires_confirmation: bool = False
    supported_target_types: list[TargetType] = Field(default_factory=list)
    enabled: bool = True


# ── ScanProfile ────────────────────────────────────────────────────────


class ScanProfile(BaseModel):
    """Ein Scan-Profil (passive/standard/intrusive) mit erlaubten Scannern."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    name: str
    kind: ScanProfileKind
    description: str = ""
    allowed_scanner_ids: list[str] = Field(default_factory=list)

    @property
    def requires_approval(self) -> bool:
        return self.kind == ScanProfileKind.INTRUSIVE

    @property
    def allow_scheduling(self) -> bool:
        """Intrusive Profile duerfen laut Auftrag standardmaessig nicht zeitgesteuert werden."""
        return self.kind != ScanProfileKind.INTRUSIVE


# ── ScanRun ────────────────────────────────────────────────────────────


class ScanRun(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=_new_id)
    security_job_id: str | None = None
    workflow_run_id: str | None = None
    agent_run_id: str | None = None
    target_id: str
    scanner_id: str
    profile_id: str
    requested_by: str = ""
    trigger_type: TriggerType = TriggerType.MANUAL
    status: ScanRunStatus = ScanRunStatus.QUEUED
    started_at: float | None = None
    completed_at: float | None = None
    timeout_at: float | None = None
    parameters: dict = Field(default_factory=dict)
    scope_snapshot: dict = Field(default_factory=dict)
    permission_snapshot: dict = Field(default_factory=dict)
    scanner_version: str = ""
    raw_artifact_refs: list[str] = Field(default_factory=list)
    finding_count: int = 0
    error: str | None = None
    audit_context: dict = Field(default_factory=dict)
    tenant_id: str = ""
    created_at: float = Field(default_factory=_now)


# ── Finding ────────────────────────────────────────────────────────────


class Finding(BaseModel):
    """Scanner-neutral normalisiertes Finding. KI-Bewertung siehe FindingEnrichment."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=_new_id)
    scan_run_id: str
    target_id: str
    fingerprint: str
    scanner_id: str
    scanner_finding_id: str = ""
    title: str
    description: str = ""
    severity: Severity
    original_severity: Severity
    confidence: float = 1.0
    category: str = ""
    cve: str | None = None
    cwe: str | None = None
    cvss: float | None = None
    resource_type: str = ""
    resource_identifier: str = ""
    location: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    first_seen_at: float = Field(default_factory=_now)
    last_seen_at: float = Field(default_factory=_now)
    occurrence_count: int = 1
    status: FindingStatus = FindingStatus.NEW
    false_positive: bool = False
    risk_accepted: bool = False
    remediation: str | None = None
    metadata: dict = Field(default_factory=dict)
    tenant_id: str = ""


# ── FindingEnrichment ──────────────────────────────────────────────────


class FindingEnrichment(BaseModel):
    """KI-Auswertung — strikt getrennt vom Original-Finding gespeichert."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(default_factory=_new_id)
    finding_id: str
    model: str
    model_version: str = ""
    prompt_version: str = "v1"
    input_hash: str = ""
    effective_severity: Severity
    exploitability: str = "unknown"
    business_impact: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str = ""
    correlation_ids: list[str] = Field(default_factory=list)
    false_positive_probability: float = Field(ge=0.0, le=1.0)
    remediation_proposal: str | None = None
    patch_proposal: str | None = None
    requires_human_review: bool = True
    validation_status: str = "valid"
    created_at: float = Field(default_factory=_now)


class LLMFindingAssessment(BaseModel):
    """Strukturiertes LLM-Output-Schema fuer Finding-Enrichment (Validierungsgrenze)."""

    model_config = ConfigDict(extra="forbid")

    effective_severity: Severity
    confidence: float = Field(ge=0.0, le=1.0)
    exploitability: str = "unknown"
    business_impact: str = ""
    false_positive_probability: float = Field(ge=0.0, le=1.0)
    correlated_findings: list[str] = Field(default_factory=list)
    remediation_steps: list[str] = Field(default_factory=list)
    patch_proposal: str | None = None
    requires_human_review: bool = True
