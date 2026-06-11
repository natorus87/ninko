"""
Auth API response/request schemas.

Shared Pydantic models used by `backend/api/routes_auth.py` for `response_model=`.
Request models that are endpoint-specific live in `routes_auth.py` itself to keep
local validation logic (e.g. password complexity) close to the endpoint.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Generic / shared fragments
# ---------------------------------------------------------------------------


class StatusResponse(BaseModel):
    """Generic single-field status payload used by mutation endpoints."""

    status: str
    username: Optional[str] = None


class AuthenticatedResponse(BaseModel):
    """Base shape of the login/logout endpoints."""

    authenticated: bool


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------


class SanitizedUser(BaseModel):
    """Subset of the RBAC user record that is safe to return to clients."""

    username: str
    tenant_id: str = "default"
    active: bool = True
    must_change_password: bool = False
    roles: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    custom_settings: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


class UserCreateResponse(BaseModel):
    status: str
    user: SanitizedUser


class UserUpdateResponse(BaseModel):
    status: str
    user: SanitizedUser


class UserListResponse(BaseModel):
    users: list[SanitizedUser]
    count: int


class UserDeleteResponse(BaseModel):
    status: str
    username: str


class UserSetPasswordResponse(BaseModel):
    status: str
    username: str


class UserSettingsResponse(BaseModel):
    username: str
    settings: dict[str, Any] = Field(default_factory=dict)


class UserSettingsUpdateResponse(BaseModel):
    status: str
    username: str
    settings: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Login / session / password
# ---------------------------------------------------------------------------


class LoginResponse(BaseModel):
    """Payload returned from `POST /api/auth/login`."""

    authenticated: bool = True
    role: str
    username: str
    roles: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    tenant_id: str = "default"
    password_change_required: bool = False


class LogoutResponse(BaseModel):
    authenticated: bool = False


class MeResponse(BaseModel):
    """Payload returned from `GET /api/auth/me`.

    When auth is disabled we still return a "logged in as admin" shape, so all
    fields are optional and only populated when relevant.
    """

    authenticated: bool
    auth_enabled: bool = True
    username: Optional[str] = None
    role: Optional[str] = None
    roles: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)
    module_permissions: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = "default"
    password_change_required: bool = False


class ChangePasswordResponse(BaseModel):
    status: str
    username: str


class BootstrapResponse(BaseModel):
    status: str
    username: str


# ---------------------------------------------------------------------------
# API tokens
# ---------------------------------------------------------------------------


class SanitizedApiToken(BaseModel):
    id: str
    name: str
    created_at: str = ""
    expires_at: str = ""
    created_by: str = ""
    last_used_at: str = ""
    revoked: bool = False
    revoked_at: str = ""


class ApiTokenListResponse(BaseModel):
    username: str
    tokens: list[SanitizedApiToken]
    count: int


class ApiTokenCreateResponse(BaseModel):
    """Returns the raw token exactly once. Includes a UI-facing warning string."""

    status: str
    username: str
    token: str
    token_meta: SanitizedApiToken
    warning: str


class RevokeTokenResponse(BaseModel):
    status: str
    username: str
    token_id: str


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


class RoleEntry(BaseModel):
    """One role entry as stored in the RBAC state."""

    id: str
    name: str
    description: str = ""
    base_role: str = "read"
    module_permissions: dict[str, dict[str, bool]] = Field(default_factory=dict)


class RoleListResponse(BaseModel):
    roles: list[RoleEntry]
    count: int


class RoleCreateResponse(BaseModel):
    status: str
    role: RoleEntry


class RoleUpdateResponse(BaseModel):
    status: str
    role: RoleEntry


class RoleDeleteResponse(BaseModel):
    status: str
    role_id: str


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


class GroupEntry(BaseModel):
    id: str
    name: str
    description: str = ""
    roles: list[str] = Field(default_factory=list)
    users: list[str] = Field(default_factory=list)


class GroupListResponse(BaseModel):
    groups: list[GroupEntry]
    count: int


class GroupCreateResponse(BaseModel):
    status: str
    group: GroupEntry


class GroupUpdateResponse(BaseModel):
    status: str
    group: GroupEntry


class GroupDeleteResponse(BaseModel):
    status: str
    group_id: str


# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------


class AvailableModule(BaseModel):
    id: str
    display_name: str = ""
    api_prefix: str = ""
    description: str = ""


class ModulesAvailableResponse(BaseModel):
    modules: list[AvailableModule]
    count: int
