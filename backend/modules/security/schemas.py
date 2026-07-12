"""Security Core — API Request-Schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .models import ScanProfileKind, TargetType


class TargetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(..., min_length=1, max_length=200)
    target_type: TargetType
    locator: str = Field(..., min_length=1, max_length=2000)
    environment: str = "production"
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    allowed_scanners: list[str] = Field(default_factory=list)
    allowed_profiles: list[ScanProfileKind] = Field(default_factory=list)
    scope_constraints: dict = Field(default_factory=dict)
    credentials_reference: str | None = None
    network_zone: str = "unspecified"


class TargetUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = None
    environment: str | None = None
    owner: str | None = None
    tags: list[str] | None = None
    enabled: bool | None = None
    allowed_scanners: list[str] | None = None
    allowed_profiles: list[ScanProfileKind] | None = None
    scope_constraints: dict | None = None
    credentials_reference: str | None = None
    network_zone: str | None = None


class ScanRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_id: str
    scanner_id: str
    profile_id: str = "passive"
    parameters: dict = Field(default_factory=dict)


class WorkflowRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_id: str


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool


class FindingStatusUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: str
    remediation: str | None = None
