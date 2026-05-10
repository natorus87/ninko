"""
Ninko API authentication helpers.

Role model:
- admin: full access
- write: read + write (except admin-only operations)
- read: read-only on protected endpoints
"""

from __future__ import annotations

import base64
import binascii
import contextvars
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Request
from fastapi import WebSocket

from core.config import get_settings

ROLE_ADMIN = "admin"
ROLE_WRITE = "write"
ROLE_READ = "read"
_REQUEST_AUTH_CACHE_ATTR = "_ninko_auth_ctx"
_REQUEST_AUTH_CACHE_FILLED_ATTR = "_ninko_auth_ctx_resolved"

_current_tenant_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_tenant_id", default=None
)


def set_current_tenant_id(tenant_id: str | None) -> contextvars.Token:
    return _current_tenant_ctx.set(tenant_id)


def get_current_tenant_id() -> str | None:
    return _current_tenant_ctx.get()


def reset_current_tenant_id(token: contextvars.Token) -> None:
    _current_tenant_ctx.reset(token)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(value: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_session_token(
    username: str,
    *,
    role: str,
    tenant_id: str = "default",
    module_permissions: dict[str, dict[str, bool]] | None = None,
    password_change_required: bool = False,
) -> str:
    cfg = get_settings()
    now = int(time.time())
    payload = {
        "sub": username,
        "role": role,
        "tid": tenant_id or "default",
        "mods": module_permissions or {},
        "pcr": bool(password_change_required),
        "iat": now,
        "exp": now + max(1, int(cfg.SESSION_TTL_HOURS)) * 3600,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _sign(payload_b64, cfg.SESSION_SECRET)
    return f"{payload_b64}.{sig}"


def create_admin_session_token(username: str) -> str:
    return create_session_token(
        username,
        role=ROLE_ADMIN,
        tenant_id="default",
        module_permissions={"*": {"read": True, "write": True}},
        password_change_required=False,
    )


def create_api_access_token(
    username: str,
    *,
    role: str,
    tenant_id: str = "default",
    module_permissions: dict[str, dict[str, bool]] | None = None,
    expires_hours: int = 24 * 30,
) -> str:
    cfg = get_settings()
    now = int(time.time())
    payload = {
        "typ": "api",
        "sub": username,
        "role": role,
        "tid": tenant_id or "default",
        "mods": module_permissions or {},
        "iat": now,
        "exp": now + max(1, int(expires_hours)) * 3600,
    }
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = _sign(payload_b64, cfg.SESSION_SECRET)
    return f"{payload_b64}.{sig}"


def _parse_session_token(token: str) -> dict | None:
    cfg = get_settings()
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        return None

    expected = _sign(payload_b64, cfg.SESSION_SECRET)
    if not hmac.compare_digest(sig, expected):
        return None

    try:
        payload_raw = _b64url_decode(payload_b64)
        payload = json.loads(payload_raw.decode("utf-8"))
    except (
        ValueError,
        TypeError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        binascii.Error,
    ):
        return None

    exp = int(payload.get("exp", 0))
    if exp <= int(time.time()):
        return None
    return payload


def _parse_api_access_token(token: str) -> dict | None:
    payload = _parse_session_token(token)
    if not payload:
        return None
    if str(payload.get("typ", "")) != "api":
        return None
    return payload


def _session_blacklist_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"ninko:session_blacklist:{digest}"


def verify_admin_credentials(username: str, password: str) -> bool:
    cfg = get_settings()
    expected_user = cfg.ADMIN_USERNAME or "admin"
    expected_pass = cfg.ADMIN_PASSWORD or ""
    if not expected_pass:
        return False
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(
        password, expected_pass
    )


def _extract_key_from_request(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return request.headers.get("X-API-Key", "").strip()


def _extract_session_from_request(request: Request) -> str:
    cfg = get_settings()
    return request.cookies.get(cfg.SESSION_COOKIE_NAME, "").strip()


def _extract_key_from_websocket(websocket: WebSocket) -> str:
    auth_header = websocket.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return websocket.headers.get("X-API-Key", "").strip()


def _extract_session_from_websocket(websocket: WebSocket) -> str:
    cfg = get_settings()
    cookie_val = websocket.cookies.get(cfg.SESSION_COOKIE_NAME, "").strip()
    if cookie_val:
        return cookie_val
    return websocket.query_params.get("session", "").strip()


def _api_key_context(key: str) -> dict[str, Any] | None:
    cfg = get_settings()
    if cfg.API_KEY_ADMIN and key == cfg.API_KEY_ADMIN:
        return {
            "username": "api_key_admin",
            "role": ROLE_ADMIN,
            "module_permissions": {"*": {"read": True, "write": True}},
            "tenant_id": "default",
            "auth_source": "api_key",
        }
    if cfg.API_KEY_WRITE and key == cfg.API_KEY_WRITE:
        return {
            "username": "api_key_write",
            "role": ROLE_WRITE,
            "module_permissions": {"*": {"read": True, "write": True}},
            "tenant_id": "default",
            "auth_source": "api_key",
        }
    if cfg.API_KEY_READ and key == cfg.API_KEY_READ:
        return {
            "username": "api_key_read",
            "role": ROLE_READ,
            "module_permissions": {"*": {"read": True, "write": False}},
            "tenant_id": "default",
            "auth_source": "api_key",
        }
    payload = _parse_api_access_token(key)
    if payload:
        role = str(payload.get("role", ROLE_READ))
        mods = payload.get("mods", {})
        module_permissions = mods if isinstance(mods, dict) else {}
        return {
            "username": str(payload.get("sub", "")).strip() or "api_token_user",
            "role": role,
            "module_permissions": module_permissions,
            "tenant_id": str(payload.get("tid", "default")).strip() or "default",
            "auth_source": "api_token",
        }
    return None


async def _is_token_blacklisted(token: str) -> bool:
    """
    Check if a session token is on the Redis blacklist.
    Prevents CWE-613: Lack of Logout (invalidate tokens after logout).
    """
    try:
        from core.redis_client import get_redis

        redis = get_redis()
        result = await redis.connection.get(_session_blacklist_key(token))
        return result is not None
    except Exception:
        return False


def _session_context(session_token: str) -> dict[str, Any] | None:
    payload = _parse_session_token(session_token)
    if not payload:
        return None
    role = str(payload.get("role", ROLE_READ))
    mods = payload.get("mods", {})
    module_permissions = mods if isinstance(mods, dict) else {}
    return {
        "username": str(payload.get("sub", "")).strip() or "session_user",
        "role": role,
        "tenant_id": str(payload.get("tid", "default")).strip() or "default",
        "module_permissions": module_permissions,
        "password_change_required": bool(payload.get("pcr", False)),
        "auth_source": "session",
    }


def resolve_request_auth(request: Request) -> dict[str, Any] | None:
    """Resolve caller auth context from API key headers or session cookie."""
    if hasattr(request.state, _REQUEST_AUTH_CACHE_FILLED_ATTR):
        return getattr(request.state, _REQUEST_AUTH_CACHE_ATTR, None)

    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        return {
            "username": cfg.ADMIN_USERNAME or "admin",
            "role": ROLE_ADMIN,
            "module_permissions": {"*": {"read": True, "write": True}},
            "tenant_id": "default",
            "auth_source": "disabled",
        }

    key = _extract_key_from_request(request)
    if key:
        ctx = _api_key_context(key)
        if ctx:
            return ctx

    session_token = _extract_session_from_request(request)
    if session_token:
        return _session_context(session_token)
    return None


async def resolve_request_auth_async(request: Request) -> dict[str, Any] | None:
    """
    Async version of resolve_request_auth that checks session blacklist.
    Use this in async endpoints to validate session tokens against blacklist.
    """
    if hasattr(request.state, _REQUEST_AUTH_CACHE_FILLED_ATTR):
        return getattr(request.state, _REQUEST_AUTH_CACHE_ATTR, None)

    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        auth_ctx = {
            "username": cfg.ADMIN_USERNAME or "admin",
            "role": ROLE_ADMIN,
            "module_permissions": {"*": {"read": True, "write": True}},
            "tenant_id": "default",
            "auth_source": "disabled",
        }
    else:
        auth_ctx = None
        key = _extract_key_from_request(request)
        if key:
            auth_ctx = _api_key_context(key)

        if auth_ctx is None:
            session_token = _extract_session_from_request(request)
            if session_token:
                if await _is_token_blacklisted(session_token):
                    auth_ctx = None
                else:
                    auth_ctx = _session_context(session_token)

    setattr(request.state, _REQUEST_AUTH_CACHE_ATTR, auth_ctx)
    setattr(request.state, _REQUEST_AUTH_CACHE_FILLED_ATTR, True)
    return auth_ctx


def resolve_request_role(request: Request) -> str | None:
    ctx = resolve_request_auth(request)
    if not ctx:
        return None
    return str(ctx.get("role", ROLE_READ))


def resolve_websocket_role(websocket: WebSocket) -> str | None:
    """Websocket role resolver (module-level permissions are HTTP-only for now)."""
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        return ROLE_ADMIN

    key = _extract_key_from_websocket(websocket)
    if key:
        ctx = _api_key_context(key)
        if ctx:
            return str(ctx.get("role", ROLE_READ))

    session_token = _extract_session_from_websocket(websocket)
    if session_token:
        ctx = _session_context(session_token)
        if ctx:
            return str(ctx.get("role", ROLE_READ))
    return None


async def resolve_websocket_role_async(websocket: WebSocket) -> str | None:
    """Websocket role resolver that honors revoked session tokens."""
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        return ROLE_ADMIN

    key = _extract_key_from_websocket(websocket)
    if key:
        ctx = _api_key_context(key)
        if ctx:
            return str(ctx.get("role", ROLE_READ))

    session_token = _extract_session_from_websocket(websocket)
    if session_token:
        if await _is_token_blacklisted(session_token):
            return None
        ctx = _session_context(session_token)
        if ctx:
            return str(ctx.get("role", ROLE_READ))
    return None


def role_allows(required_role: str, actual_role: str | None) -> bool:
    if actual_role is None:
        return False

    order = {
        ROLE_READ: 1,
        ROLE_WRITE: 2,
        ROLE_ADMIN: 3,
    }
    return order.get(actual_role, 0) >= order.get(required_role, 999)


def module_access_allows(
    auth_ctx: dict[str, Any] | None,
    module_id: str,
    method: str,
) -> bool:
    if not auth_ctx:
        return False

    role = str(auth_ctx.get("role", ROLE_READ))
    if role == ROLE_ADMIN:
        return True

    module_permissions = auth_ctx.get("module_permissions")
    if not isinstance(module_permissions, dict):
        return role_allows(
            ROLE_WRITE if method.upper() in {"POST", "PUT", "PATCH", "DELETE"} else ROLE_READ, role
        )

    module_key = (module_id or "").strip().lower().replace("-", "_")
    wildcard = module_permissions.get("*")
    specific = module_permissions.get(module_key)
    merged = {"read": False, "write": False}
    for src in (wildcard, specific):
        if isinstance(src, dict):
            merged["read"] = merged["read"] or bool(src.get("read", False))
            merged["write"] = merged["write"] or bool(src.get("write", False))

    is_mutating = method.upper() in {"POST", "PUT", "PATCH", "DELETE"}
    return merged["write"] if is_mutating else merged["read"]


def auth_tenant_id(auth_ctx: dict[str, Any] | None) -> str:
    if not auth_ctx:
        return "default"
    tenant = str(auth_ctx.get("tenant_id", "default")).strip()
    return tenant or "default"
