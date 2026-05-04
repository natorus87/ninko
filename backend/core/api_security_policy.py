"""
Central API authorization policy for Ninko.

This module intentionally has no application startup side effects so the
security matrix can be unit-tested without importing the FastAPI app.
"""

from __future__ import annotations

from core.auth import ROLE_ADMIN, ROLE_READ, ROLE_WRITE


PUBLIC_API_PATHS = {
    "/api/auth/login",
    "/api/auth/logout",
    "/api/auth/me",
    "/api/auth/change-password",
}

PUBLIC_GET_PATHS = {
    "/api/themes/active",
    "/api/settings/branding",
    "/api/settings/modules",
    "/api/plugins/check-updates",
}

CORE_API_PREFIXES = {
    "auth",
    "themes",
    "modules",
    "memory",
    "secrets",
    "settings",
    "ws",
    "safeguard",
    "scheduler",
    "plugins",
    "connections",
    "agents",
    "alerts",
    "audit",
    "workflows",
    "logs",
    "transcription",
    "tts",
    "image-gen",
    "skills",
    "operations",
    "chat",
    "images",
    "knowledge-graph",
    "metrics",
    "subagent",
}


def required_role_for_request(path: str, method: str) -> str | None:
    """Return the minimum role required for an HTTP request path."""
    if path == "/health":
        return None

    if not path.startswith("/api/"):
        return None

    method_u = method.upper()
    if path in PUBLIC_API_PATHS:
        return None
    if method_u == "GET" and (
        path in PUBLIC_GET_PATHS or path.startswith("/api/settings/branding/assets/")
    ):
        return None
    if path.startswith("/api/auth/"):
        return ROLE_ADMIN

    is_mutating = method_u in {"POST", "PUT", "PATCH", "DELETE"}

    if path.startswith("/api/secrets"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/logs"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/ws"):
        return ROLE_READ
    if path.startswith("/api/plugins"):
        if method_u == "GET" and path == "/api/plugins/check-updates":
            return None
        return ROLE_ADMIN
    if path.startswith("/api/safeguard"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/settings"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/connections"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/themes"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/agents"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/workflows"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/memory"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/modules"):
        return ROLE_READ

    return ROLE_WRITE if is_mutating else ROLE_READ


def extract_module_id_from_path(path: str) -> str | None:
    """Return the module id for module API routes, excluding core API prefixes."""
    if not path.startswith("/api/"):
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    first = parts[1].strip().lower()
    if first in CORE_API_PREFIXES:
        return None
    return first
