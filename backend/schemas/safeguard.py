"""
Ninko – Pydantic-Response-Modelle für Safeguard-Endpoints.

Bündelt alle Schemas für:
  - routes_safeguard.py          (Status, Toggle, Profile-Assignment)
  - routes_safeguard_audit.py    (Audit-Log, Metrics)
  - routes_safeguard_profiles.py (Profile-CRUD)

Diese Datei enthält ausschließlich Response-Modelle. Request-Body-Modelle
(z. B. ProfileCreateRequest, ProfileUpdateRequest) bleiben in den jeweiligen
Route-Dateien, da sie Felder-Validierung mit field_validator benötigen.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ─── Profile-Payload (DRY: gleiche Form wie SafeguardProfile.to_dict()) ────────

class SafeguardProfilePayload(BaseModel):
    """Ein Safeguard-Profil in serialisierter Form (matches to_dict())."""
    id: str
    name: str
    builtin: bool = True
    check_user_messages: bool = True
    check_tool_calls: bool = True
    confirm_categories: list[str] = Field(
        default_factory=lambda: ["DESTRUCTIVE", "STATE_CHANGING"]
    )
    detect_prompt_injection: bool = False
    fail_open: bool = False
    auto_mode: bool = False
    auto_mode_policy: str = ""


# ─── routes_safeguard.py ──────────────────────────────────────────────────────

class SafeguardStatusResponse(BaseModel):
    """Globaler Safeguard-Status (GET /api/safeguard/status)."""
    enabled: bool
    profile_id: str


class SafeguardEnableResponse(BaseModel):
    """Antwort nach enable() (POST /api/safeguard/enable)."""
    safeguard: str = "enabled"
    profile_id: str


class SafeguardDisableResponse(BaseModel):
    """Antwort nach disable() (POST /api/safeguard/disable)."""
    safeguard: str = "disabled"
    profile_id: str = "disabled"


class SafeguardActiveProfileResponse(BaseModel):
    """Aktives globales Profil inkl. Konfiguration (GET /api/safeguard/active)."""
    profile_id: str
    profile: Optional[SafeguardProfilePayload] = None


class SafeguardSetActiveProfileResponse(BaseModel):
    """Antwort nach Setzen des globalen Profils (POST /api/safeguard/active)."""
    profile_id: str


class SafeguardChatProfileResponse(BaseModel):
    """Aufgelöstes Chat-Profil (GET/POST /api/safeguard/chats/{id}/profile)."""
    session_id: str
    profile_id: str
    source: str  # "global" | "chat"


class SafeguardClearChatProfileResponse(BaseModel):
    """Antwort nach Löschen des Chat-Profils (DELETE .../chats/{id}/profile)."""
    session_id: str
    cleared: bool = True


class SafeguardAgentProfileResponse(BaseModel):
    """Aufgelöstes Agent-Profil (GET/POST /api/safeguard/agents/{id}/profile)."""
    agent_id: str
    profile_id: str
    source: str  # "global" | "agent"


class SafeguardClearAgentProfileResponse(BaseModel):
    """Antwort nach Löschen des Agent-Profils (DELETE .../agents/{id}/profile)."""
    agent_id: str
    cleared: bool = True


class SafeguardAgentStatusResponse(BaseModel):
    """Per-Agent Safeguard-Status (backward-compat, GET .../agents/{id})."""
    agent_id: str
    safeguard_enabled: bool
    profile_id: str
    source: str


class SafeguardAgentToggleResponse(BaseModel):
    """Antwort nach enable/disable für Agent (POST .../agents/{id}/enable|disable)."""
    agent_id: str
    safeguard: str  # "enabled" | "disabled"


class SafeguardAgentPolicyResponse(BaseModel):
    """Custom classifier policy für Agent (GET .../agents/{id}/policy)."""
    agent_id: str
    policy: str
    has_custom_policy: bool


class SafeguardAgentPolicySetResponse(BaseModel):
    """Antwort nach Setzen der Policy (POST .../agents/{id}/policy)."""
    agent_id: str
    policy_set: bool = True


class SafeguardAgentPolicyClearedResponse(BaseModel):
    """Antwort nach Löschen der Policy (DELETE .../agents/{id}/policy)."""
    agent_id: str
    policy_cleared: bool = True


# ─── routes_safeguard_audit.py ────────────────────────────────────────────────

class SafeguardAuditEntry(BaseModel):
    """Ein einzelner Audit-Log-Eintrag (Freiform-Dict aus Redis)."""
    timestamp: Optional[float] = None
    action: Optional[str] = None
    category: Optional[str] = None
    text: Optional[str] = None
    session_id: Optional[str] = None
    agent_id: Optional[str] = None
    tool_name: Optional[str] = None
    outcome: Optional[str] = None
    rationale: Optional[str] = None
    profile_id: Optional[str] = None


class SafeguardAuditListResponse(BaseModel):
    """Audit-Log mit Filtern (GET /api/safeguard/audit)."""
    entries: list[dict] = Field(default_factory=list)
    total: int = 0


class SafeguardAuditClearResponse(BaseModel):
    """Antwort nach Löschen des Audit-Logs (DELETE /api/safeguard/audit)."""
    cleared: bool = True


class SafeguardMetricsResponse(BaseModel):
    """Latency-Metriken (GET /api/safeguard/audit/metrics)."""
    p50_ms: float = 0
    p95_ms: float = 0
    p99_ms: float = 0
    path_breakdown: dict[str, int] = Field(default_factory=dict)
    total_checks: int = 0


# ─── routes_safeguard_profiles.py ─────────────────────────────────────────────

# Nutzt SafeguardProfilePayload von oben als Listen-/Einzel-Element.

class SafeguardProfileDeleteResponse(BaseModel):
    """Antwort nach Löschen (DELETE, status_code=204: response_model=None überschreibt)."""
    deleted: bool = True
    id: str
