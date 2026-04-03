"""
Ninko Auth API.

Single-admin login via session cookie.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from core.auth import create_admin_session_token, resolve_request_role, verify_admin_credentials
from core.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginRequest, response: Response) -> dict:
    cfg = get_settings()
    if not cfg.API_AUTH_ENABLED:
        raise HTTPException(status_code=400, detail="Auth is disabled.")
    if not cfg.ADMIN_PASSWORD:
        raise HTTPException(status_code=503, detail="Admin password is not configured.")

    if not verify_admin_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    token = create_admin_session_token(body.username)
    response.set_cookie(
        key=cfg.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=cfg.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=max(1, int(cfg.SESSION_TTL_HOURS)) * 3600,
        path="/",
    )
    return {"authenticated": True, "role": "admin", "username": body.username}


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
        return {"authenticated": True, "role": "admin", "username": cfg.ADMIN_USERNAME, "auth_enabled": False}

    role = resolve_request_role(request)
    if role is None:
        return {"authenticated": False, "auth_enabled": True}
    return {"authenticated": True, "role": role, "username": cfg.ADMIN_USERNAME, "auth_enabled": True}
