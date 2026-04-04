"""
Ninko Auth API.

Supports:
- Login/logout/me
- RBAC management (users, groups, roles, module permissions)
"""

from __future__ import annotations

import hashlib
import secrets
import re
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.auth import (
    ROLE_ADMIN,
    create_api_access_token,
    create_session_token,
    resolve_request_auth,
    resolve_request_role,
)
from core.config import get_settings
from core.rbac import RbacStore, hash_password

router = APIRouter(prefix="/api/auth", tags=["Auth"])
rbac_store = RbacStore()

_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{2,64}$")


def _assert_admin(request: Request) -> None:
    role = resolve_request_role(request)
    if role != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required.")


def _validate_id(identifier: str, field_name: str) -> str:
    clean = (identifier or "").strip()
    if not _ID_RE.match(clean):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field_name}. Use 2-64 chars [a-zA-Z0-9_-].",
        )
    return clean


def _sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": user.get("username", ""),
        "tenant_id": user.get("tenant_id", "default"),
        "active": bool(user.get("active", True)),
        "must_change_password": bool(user.get("must_change_password", False)),
        "roles": list(user.get("roles") or []),
        "groups": list(user.get("groups") or []),
        "custom_settings": user.get("custom_settings", {}) if isinstance(user.get("custom_settings"), dict) else {},
        "created_at": user.get("created_at", ""),
        "updated_at": user.get("updated_at", ""),
    }


def _sanitize_api_token_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(entry.get("id", "")),
        "name": str(entry.get("name", "")),
        "created_at": str(entry.get("created_at", "")),
        "expires_at": str(entry.get("expires_at", "")),
        "created_by": str(entry.get("created_by", "")),
        "last_used_at": str(entry.get("last_used_at", "")),
        "revoked": bool(entry.get("revoked", False)),
        "revoked_at": str(entry.get("revoked_at", "")),
    }


class LoginRequest(BaseModel):
    username: str
    password: str


class RolePermission(BaseModel):
    read: bool = False
    write: bool = False


class RoleCreateRequest(BaseModel):
    role_id: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    base_role: str = Field(default="read", pattern="^(read|write|admin)$")
    module_permissions: dict[str, RolePermission] = Field(default_factory=dict)


class RoleUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    base_role: str | None = Field(default=None, pattern="^(read|write|admin)$")
    module_permissions: dict[str, RolePermission] | None = None


class GroupCreateRequest(BaseModel):
    group_id: str = Field(min_length=2, max_length=64)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    roles: list[str] = Field(default_factory=list)


class GroupUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    roles: list[str] | None = None
    users: list[str] | None = None


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=256)
    tenant_id: str = Field(default="default", min_length=1, max_length=64)
    active: bool = True
    roles: list[str] = Field(default_factory=list)
    groups: list[str] = Field(default_factory=list)


class UserUpdateRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=1, max_length=64)
    active: bool | None = None
    roles: list[str] | None = None
    groups: list[str] | None = None


class UserPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=256)


class ChangeOwnPasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class ApiTokenCreateRequest(BaseModel):
    name: str = Field(default="api-token", min_length=1, max_length=120)
    expires_hours: int = Field(default=24 * 30, ge=1, le=24 * 365)


class UserCustomSettingsRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


def _should_set_secure_cookie(request: Request, cfg_secure: bool) -> bool:
    """
    Enable Secure cookies only when requested by config and request is HTTPS.
    Accept X-Forwarded-Proto for reverse proxy termination (Traefik/nginx).
    """
    if not cfg_secure:
        return False
    proto_hdr = (request.headers.get("x-forwarded-proto") or "").split(",", 1)[0].strip().lower()
    is_https = request.url.scheme == "https" or proto_hdr == "https"
    return is_https


@router.post("/login")
async def login(body: LoginRequest, response: Response, request: Request) -> dict:
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Auth is disabled.")

    username = body.username.strip()
    password = body.password
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required.")

    # 1) Try RBAC users first
    user = await rbac_store.authenticate_user(username, password)
    if user is not None:
        effective = await rbac_store.build_effective_permissions(username)
        if not effective:
            raise HTTPException(status_code=403, detail="No effective permissions for this user.")

        token = create_session_token(
            username,
            role=str(effective["base_role"]),
            tenant_id=str(effective.get("tenant_id", "default")),
            module_permissions=effective["module_permissions"],
            password_change_required=bool(user.get("must_change_password", False)),
        )
        response.set_cookie(
            key=cfg.SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=_should_set_secure_cookie(request, cfg.SESSION_COOKIE_SECURE),
            samesite="lax",
            max_age=max(1, int(cfg.SESSION_TTL_HOURS)) * 3600,
            path="/",
        )
        return {
            "authenticated": True,
            "role": effective["base_role"],
            "username": username,
            "roles": effective["role_ids"],
            "groups": effective["group_ids"],
            "tenant_id": effective.get("tenant_id", "default"),
            "password_change_required": bool(user.get("must_change_password", False)),
        }

    raise HTTPException(status_code=401, detail="Invalid credentials.")


@router.post("/logout")
async def logout(response: Response) -> dict:
    cfg = get_settings()
    response.delete_cookie(
        key=cfg.SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
    )
    return {"authenticated": False}


@router.get("/me")
async def me(request: Request) -> dict:
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        return {
            "authenticated": True,
            "role": "admin",
            "username": cfg.ADMIN_USERNAME,
            "auth_enabled": False,
            "roles": ["role_admin"],
            "groups": ["group_admins"],
            "module_permissions": {"*": {"read": True, "write": True}},
            "tenant_id": "default",
            "password_change_required": False,
        }

    auth_ctx = resolve_request_auth(request)
    if not auth_ctx:
        return {"authenticated": False, "auth_enabled": True}

    username = str(auth_ctx.get("username", "")).strip()
    effective = await rbac_store.build_effective_permissions(username)
    if effective:
        return {
            "authenticated": True,
            "auth_enabled": True,
            "username": username,
            "role": effective["base_role"],
            "roles": effective["role_ids"],
            "groups": effective["group_ids"],
            "module_permissions": effective["module_permissions"],
            "tenant_id": effective.get("tenant_id", "default"),
            "password_change_required": bool(effective.get("password_change_required", False)),
        }

    return {
        "authenticated": True,
        "auth_enabled": True,
        "username": username,
        "role": auth_ctx.get("role", "read"),
        "roles": [],
        "groups": [],
        "module_permissions": auth_ctx.get("module_permissions", {}),
        "tenant_id": auth_ctx.get("tenant_id", "default"),
        "password_change_required": bool(auth_ctx.get("password_change_required", False)),
    }


@router.post("/change-password")
async def change_own_password(body: ChangeOwnPasswordRequest, request: Request, response: Response) -> dict:
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Auth is disabled.")

    auth_ctx = resolve_request_auth(request)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    if str(auth_ctx.get("auth_source", "")) != "session":
        raise HTTPException(status_code=403, detail="Password change requires session authentication.")

    username = str(auth_ctx.get("username", "")).strip()
    if not username:
        raise HTTPException(status_code=401, detail="Invalid session.")
    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="New password must be different.")

    user = await rbac_store.authenticate_user(username, body.current_password)
    if user is None:
        raise HTTPException(status_code=400, detail="Current password is invalid.")

    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    user_entry = users.get(username)
    if not isinstance(user_entry, dict):
        raise HTTPException(status_code=404, detail="User not found.")

    user_entry["password_hash"] = hash_password(body.new_password)
    user_entry["must_change_password"] = False
    user_entry["updated_at"] = state["updated_at"]
    await rbac_store.save(state)

    # Session sofort auf "Passwort gewechselt" aktualisieren, damit die Security-Middleware
    # nicht weiter mit `password_change_required=true` blockiert.
    effective = await rbac_store.build_effective_permissions(username)
    if effective:
        token = create_session_token(
            username,
            role=str(effective["base_role"]),
            tenant_id=str(effective.get("tenant_id", "default")),
            module_permissions=effective["module_permissions"],
            password_change_required=False,
        )
        cfg = get_settings()
        response.set_cookie(
            key=cfg.SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=_should_set_secure_cookie(request, cfg.SESSION_COOKIE_SECURE),
            samesite="lax",
            max_age=max(1, int(cfg.SESSION_TTL_HOURS)) * 3600,
            path="/",
        )

    return {"status": "updated", "username": username}


@router.post("/bootstrap")
async def bootstrap_admin(body: LoginRequest, request: Request) -> dict:
    """
    Create/repair the bootstrap admin user inside RBAC storage.
    Allowed when:
    - auth is disabled, or
    - caller is already admin.
    """
    cfg = get_settings()
    if cfg.API_AUTH_ENABLED:
        _assert_admin(request)

    username = _validate_id(body.username, "username")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 chars.")

    await rbac_store.bootstrap_admin_if_needed(username, body.password)
    return {"status": "ok", "username": username}


@router.get("/users")
async def list_users(request: Request) -> dict:
    _assert_admin(request)
    state = await rbac_store.load()
    users = [_sanitize_user(u) for u in state["users"].values() if isinstance(u, dict)]
    users.sort(key=lambda x: x["username"])
    return {"users": users, "count": len(users)}


@router.post("/users")
async def create_user(body: UserCreateRequest, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(body.username, "username")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 chars.")

    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    roles: dict[str, dict[str, Any]] = state["roles"]
    groups: dict[str, dict[str, Any]] = state["groups"]

    if username in users:
        raise HTTPException(status_code=409, detail="User already exists.")

    for rid in body.roles:
        if rid not in roles:
            raise HTTPException(status_code=400, detail=f"Unknown role: {rid}")
    for gid in body.groups:
        if gid not in groups:
            raise HTTPException(status_code=400, detail=f"Unknown group: {gid}")

    users[username] = {
        "username": username,
        "tenant_id": body.tenant_id.strip() or "default",
        "password_hash": hash_password(body.password),
        "active": body.active,
        "must_change_password": False,
        "roles": sorted(set(body.roles)),
        "groups": sorted(set(body.groups)),
        "custom_settings": {},
        "api_tokens": [],
        "created_at": state["updated_at"],
        "updated_at": state["updated_at"],
    }

    for gid in body.groups:
        group = groups.get(gid)
        if isinstance(group, dict):
            member_set = set(group.get("users") or [])
            member_set.add(username)
            group["users"] = sorted(member_set)

    await rbac_store.save(state)
    return {"status": "created", "user": _sanitize_user(users[username])}


@router.put("/users/{username}")
async def update_user(username: str, body: UserUpdateRequest, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    roles: dict[str, dict[str, Any]] = state["roles"]
    groups: dict[str, dict[str, Any]] = state["groups"]

    user = users.get(username)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="User not found.")

    if body.roles is not None:
        for rid in body.roles:
            if rid not in roles:
                raise HTTPException(status_code=400, detail=f"Unknown role: {rid}")
        user["roles"] = sorted(set(body.roles))

    if body.groups is not None:
        for gid in body.groups:
            if gid not in groups:
                raise HTTPException(status_code=400, detail=f"Unknown group: {gid}")

        # Remove from all groups first
        for group in groups.values():
            if isinstance(group, dict):
                members = set(group.get("users") or [])
                if username in members:
                    members.remove(username)
                group["users"] = sorted(members)

        for gid in body.groups:
            group = groups.get(gid)
            if isinstance(group, dict):
                members = set(group.get("users") or [])
                members.add(username)
                group["users"] = sorted(members)
        user["groups"] = sorted(set(body.groups))

    if body.active is not None:
        user["active"] = body.active
    if body.tenant_id is not None:
        user["tenant_id"] = body.tenant_id.strip() or "default"
    if not isinstance(user.get("custom_settings"), dict):
        user["custom_settings"] = {}
    if not isinstance(user.get("api_tokens"), list):
        user["api_tokens"] = []

    user["updated_at"] = state["updated_at"]
    await rbac_store.save(state)
    return {"status": "updated", "user": _sanitize_user(user)}


@router.put("/users/{username}/password")
async def set_user_password(username: str, body: UserPasswordRequest, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 chars.")

    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    user = users.get(username)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="User not found.")

    user["password_hash"] = hash_password(body.password)
    user["must_change_password"] = False
    user["updated_at"] = state["updated_at"]
    await rbac_store.save(state)
    return {"status": "updated", "username": username}


@router.delete("/users/{username}")
async def delete_user(username: str, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    groups: dict[str, dict[str, Any]] = state["groups"]

    if username not in users:
        raise HTTPException(status_code=404, detail="User not found.")

    users.pop(username, None)
    for group in groups.values():
        if isinstance(group, dict):
            members = set(group.get("users") or [])
            if username in members:
                members.remove(username)
            group["users"] = sorted(members)

    await rbac_store.save(state)
    return {"status": "deleted", "username": username}


@router.get("/users/{username}/settings")
async def get_user_custom_settings(username: str, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    state = await rbac_store.load()
    user = state["users"].get(username)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="User not found.")
    settings = user.get("custom_settings", {})
    if not isinstance(settings, dict):
        settings = {}
    return {"username": username, "settings": settings}


@router.put("/users/{username}/settings")
async def update_user_custom_settings(username: str, body: UserCustomSettingsRequest, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    user = users.get(username)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="User not found.")
    user["custom_settings"] = body.settings if isinstance(body.settings, dict) else {}
    user["updated_at"] = state["updated_at"]
    await rbac_store.save(state)
    return {"status": "updated", "username": username, "settings": user["custom_settings"]}


@router.get("/users/{username}/api-tokens")
async def list_user_api_tokens(username: str, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    state = await rbac_store.load()
    user = state["users"].get(username)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="User not found.")
    tokens = user.get("api_tokens", [])
    if not isinstance(tokens, list):
        tokens = []
    sanitized = [_sanitize_api_token_entry(t) for t in tokens if isinstance(t, dict)]
    sanitized.sort(key=lambda t: t.get("created_at", ""), reverse=True)
    return {"username": username, "tokens": sanitized, "count": len(sanitized)}


@router.post("/users/{username}/api-tokens")
async def create_user_api_token(username: str, body: ApiTokenCreateRequest, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    user = users.get(username)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="User not found.")
    if not bool(user.get("active", True)):
        raise HTTPException(status_code=400, detail="Cannot create API token for inactive user.")

    effective = await rbac_store.build_effective_permissions(username)
    if not effective:
        raise HTTPException(status_code=400, detail="No effective permissions for this user.")

    raw_token = create_api_access_token(
        username,
        role=str(effective["base_role"]),
        tenant_id=str(effective.get("tenant_id", "default")),
        module_permissions=effective["module_permissions"],
        expires_hours=body.expires_hours,
    )
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    token_id = secrets.token_hex(8)
    auth_ctx = resolve_request_auth(request) or {}
    created_by = str(auth_ctx.get("username", "admin"))
    expires_at = time.strftime(
        "%Y-%m-%dT%H:%M:%SZ",
        time.gmtime(time.time() + int(body.expires_hours) * 3600),
    )

    token_entry = {
        "id": token_id,
        "name": body.name.strip() or "api-token",
        "token_hash": token_hash,
        "created_at": state["updated_at"],
        "expires_at": expires_at,
        "created_by": created_by,
        "last_used_at": "",
        "revoked": False,
        "revoked_at": "",
    }
    tokens = user.get("api_tokens")
    if not isinstance(tokens, list):
        tokens = []
    tokens.append(token_entry)
    user["api_tokens"] = tokens
    user["updated_at"] = state["updated_at"]
    await rbac_store.save(state)

    return {
        "status": "created",
        "username": username,
        "token": raw_token,
        "token_meta": _sanitize_api_token_entry(token_entry),
        "warning": "Store this token securely. It is shown only once.",
    }


@router.delete("/users/{username}/api-tokens/{token_id}")
async def revoke_user_api_token(username: str, token_id: str, request: Request) -> dict:
    _assert_admin(request)
    username = _validate_id(username, "username")
    token_id = _validate_id(token_id, "token_id")
    state = await rbac_store.load()
    users: dict[str, dict[str, Any]] = state["users"]
    user = users.get(username)
    if not isinstance(user, dict):
        raise HTTPException(status_code=404, detail="User not found.")
    tokens = user.get("api_tokens")
    if not isinstance(tokens, list):
        tokens = []

    found = None
    for t in tokens:
        if isinstance(t, dict) and str(t.get("id", "")) == token_id:
            found = t
            break
    if not found:
        raise HTTPException(status_code=404, detail="Token not found.")

    found["revoked"] = True
    found["revoked_at"] = state["updated_at"]
    user["updated_at"] = state["updated_at"]
    await rbac_store.save(state)
    return {"status": "revoked", "username": username, "token_id": token_id}


@router.get("/roles")
async def list_roles(request: Request) -> dict:
    _assert_admin(request)
    state = await rbac_store.load()
    roles = [r for r in state["roles"].values() if isinstance(r, dict)]
    roles.sort(key=lambda r: str(r.get("id", "")))
    return {"roles": roles, "count": len(roles)}


@router.post("/roles")
async def create_role(body: RoleCreateRequest, request: Request) -> dict:
    _assert_admin(request)
    role_id = _validate_id(body.role_id, "role_id")
    state = await rbac_store.load()
    roles: dict[str, dict[str, Any]] = state["roles"]
    if role_id in roles:
        raise HTTPException(status_code=409, detail="Role already exists.")

    module_permissions = {
        k.strip().lower().replace("-", "_"): {"read": bool(v.read), "write": bool(v.write)}
        for k, v in body.module_permissions.items()
        if k.strip()
    }
    roles[role_id] = {
        "id": role_id,
        "name": body.name.strip(),
        "description": body.description.strip(),
        "base_role": body.base_role,
        "module_permissions": module_permissions or {"*": {"read": True, "write": body.base_role != "read"}},
    }
    await rbac_store.save(state)
    return {"status": "created", "role": roles[role_id]}


@router.put("/roles/{role_id}")
async def update_role(role_id: str, body: RoleUpdateRequest, request: Request) -> dict:
    _assert_admin(request)
    role_id = _validate_id(role_id, "role_id")
    state = await rbac_store.load()
    roles: dict[str, dict[str, Any]] = state["roles"]
    role = roles.get(role_id)
    if not isinstance(role, dict):
        raise HTTPException(status_code=404, detail="Role not found.")

    if body.name is not None:
        role["name"] = body.name.strip()
    if body.description is not None:
        role["description"] = body.description.strip()
    if body.base_role is not None:
        role["base_role"] = body.base_role
    if body.module_permissions is not None:
        role["module_permissions"] = {
            k.strip().lower().replace("-", "_"): {"read": bool(v.read), "write": bool(v.write)}
            for k, v in body.module_permissions.items()
            if k.strip()
        }

    await rbac_store.save(state)
    return {"status": "updated", "role": role}


@router.delete("/roles/{role_id}")
async def delete_role(role_id: str, request: Request) -> dict:
    _assert_admin(request)
    role_id = _validate_id(role_id, "role_id")
    if role_id == "role_admin":
        raise HTTPException(status_code=400, detail="Built-in role_admin cannot be deleted.")

    state = await rbac_store.load()
    roles: dict[str, dict[str, Any]] = state["roles"]
    users: dict[str, dict[str, Any]] = state["users"]
    groups: dict[str, dict[str, Any]] = state["groups"]
    if role_id not in roles:
        raise HTTPException(status_code=404, detail="Role not found.")

    roles.pop(role_id, None)
    for user in users.values():
        if isinstance(user, dict):
            user["roles"] = [r for r in (user.get("roles") or []) if r != role_id]
    for group in groups.values():
        if isinstance(group, dict):
            group["roles"] = [r for r in (group.get("roles") or []) if r != role_id]

    await rbac_store.save(state)
    return {"status": "deleted", "role_id": role_id}


@router.get("/groups")
async def list_groups(request: Request) -> dict:
    _assert_admin(request)
    state = await rbac_store.load()
    groups = [g for g in state["groups"].values() if isinstance(g, dict)]
    groups.sort(key=lambda g: str(g.get("id", "")))
    return {"groups": groups, "count": len(groups)}


@router.get("/modules/available")
async def list_available_modules(request: Request) -> dict:
    _assert_admin(request)
    registry = getattr(request.app.state, "registry", None)
    if registry is None:
        return {"modules": [], "count": 0}

    modules = []
    for mod in registry.get_registered_modules().values():
        modules.append(
            {
                "id": mod.manifest.name,
                "display_name": mod.manifest.display_name,
                "api_prefix": mod.manifest.api_prefix,
                "description": mod.manifest.description,
            }
        )
    modules.sort(key=lambda m: m["id"])
    return {"modules": modules, "count": len(modules)}


@router.post("/groups")
async def create_group(body: GroupCreateRequest, request: Request) -> dict:
    _assert_admin(request)
    group_id = _validate_id(body.group_id, "group_id")
    state = await rbac_store.load()
    groups: dict[str, dict[str, Any]] = state["groups"]
    roles: dict[str, dict[str, Any]] = state["roles"]
    if group_id in groups:
        raise HTTPException(status_code=409, detail="Group already exists.")
    for rid in body.roles:
        if rid not in roles:
            raise HTTPException(status_code=400, detail=f"Unknown role: {rid}")

    groups[group_id] = {
        "id": group_id,
        "name": body.name.strip(),
        "description": body.description.strip(),
        "roles": sorted(set(body.roles)),
        "users": [],
    }
    await rbac_store.save(state)
    return {"status": "created", "group": groups[group_id]}


@router.put("/groups/{group_id}")
async def update_group(group_id: str, body: GroupUpdateRequest, request: Request) -> dict:
    _assert_admin(request)
    group_id = _validate_id(group_id, "group_id")
    state = await rbac_store.load()
    groups: dict[str, dict[str, Any]] = state["groups"]
    roles: dict[str, dict[str, Any]] = state["roles"]
    users: dict[str, dict[str, Any]] = state["users"]
    group = groups.get(group_id)
    if not isinstance(group, dict):
        raise HTTPException(status_code=404, detail="Group not found.")

    if body.name is not None:
        group["name"] = body.name.strip()
    if body.description is not None:
        group["description"] = body.description.strip()
    if body.roles is not None:
        for rid in body.roles:
            if rid not in roles:
                raise HTTPException(status_code=400, detail=f"Unknown role: {rid}")
        group["roles"] = sorted(set(body.roles))
    if body.users is not None:
        for username in body.users:
            if username not in users:
                raise HTTPException(status_code=400, detail=f"Unknown user: {username}")

        # Remove group from all users first
        for user in users.values():
            if isinstance(user, dict):
                group_ids = set(user.get("groups") or [])
                if group_id in group_ids:
                    group_ids.remove(group_id)
                user["groups"] = sorted(group_ids)

        # Add group to selected users
        for username in body.users:
            user = users.get(username)
            if isinstance(user, dict):
                group_ids = set(user.get("groups") or [])
                group_ids.add(group_id)
                user["groups"] = sorted(group_ids)
        group["users"] = sorted(set(body.users))

    await rbac_store.save(state)
    return {"status": "updated", "group": group}


@router.delete("/groups/{group_id}")
async def delete_group(group_id: str, request: Request) -> dict:
    _assert_admin(request)
    group_id = _validate_id(group_id, "group_id")
    if group_id == "group_admins":
        raise HTTPException(status_code=400, detail="Built-in group_admins cannot be deleted.")

    state = await rbac_store.load()
    groups: dict[str, dict[str, Any]] = state["groups"]
    users: dict[str, dict[str, Any]] = state["users"]
    if group_id not in groups:
        raise HTTPException(status_code=404, detail="Group not found.")

    groups.pop(group_id, None)
    for user in users.values():
        if isinstance(user, dict):
            user["groups"] = [g for g in (user.get("groups") or []) if g != group_id]

    await rbac_store.save(state)
    return {"status": "deleted", "group_id": group_id}
