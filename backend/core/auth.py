"""
Ninko API authentication helpers.

Role model:
- admin: full access
- write: read + write (except admin-only operations)
- read: read-only on protected endpoints
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import Request
from fastapi import WebSocket

from core.config import get_settings


ROLE_ADMIN = "admin"
ROLE_WRITE = "write"
ROLE_READ = "read"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(value: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).digest()
    return _b64url_encode(sig)


def create_admin_session_token(username: str) -> str:
    cfg = get_settings()
    now = int(time.time())
    payload = {
        "sub": username,
        "role": ROLE_ADMIN,
        "iat": now,
        "exp": now + max(1, int(cfg.SESSION_TTL_HOURS)) * 3600,
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
    except Exception:
        return None

    exp = int(payload.get("exp", 0))
    if exp <= int(time.time()):
        return None
    return payload


def verify_admin_credentials(username: str, password: str) -> bool:
    cfg = get_settings()
    expected_user = cfg.ADMIN_USERNAME or "admin"
    expected_pass = cfg.ADMIN_PASSWORD or ""
    if not expected_pass:
        return False
    return hmac.compare_digest(username, expected_user) and hmac.compare_digest(password, expected_pass)


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
    header_key = websocket.headers.get("X-API-Key", "").strip()
    if header_key:
        return header_key
    return websocket.query_params.get("api_key", "").strip()


def _extract_session_from_websocket(websocket: WebSocket) -> str:
    cfg = get_settings()
    cookie_val = websocket.cookies.get(cfg.SESSION_COOKIE_NAME, "").strip()
    if cookie_val:
        return cookie_val
    return websocket.query_params.get("session", "").strip()


def resolve_request_role(request: Request) -> str | None:
    """Resolve caller role from API key headers or session cookie."""
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        return ROLE_ADMIN

    key = _extract_key_from_request(request)
    if key:
        if cfg.API_KEY_ADMIN and key == cfg.API_KEY_ADMIN:
            return ROLE_ADMIN
        if cfg.API_KEY_WRITE and key == cfg.API_KEY_WRITE:
            return ROLE_WRITE
        if cfg.API_KEY_READ and key == cfg.API_KEY_READ:
            return ROLE_READ

    session_token = _extract_session_from_request(request)
    if session_token:
        payload = _parse_session_token(session_token)
        if payload:
            return payload.get("role", ROLE_READ)
    return None


def resolve_websocket_role(websocket: WebSocket) -> str | None:
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        return ROLE_ADMIN

    key = _extract_key_from_websocket(websocket)
    if key:
        if cfg.API_KEY_ADMIN and key == cfg.API_KEY_ADMIN:
            return ROLE_ADMIN
        if cfg.API_KEY_WRITE and key == cfg.API_KEY_WRITE:
            return ROLE_WRITE
        if cfg.API_KEY_READ and key == cfg.API_KEY_READ:
            return ROLE_READ

    session_token = _extract_session_from_websocket(websocket)
    if session_token:
        payload = _parse_session_token(session_token)
        if payload:
            return payload.get("role", ROLE_READ)
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
