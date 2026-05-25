"""
Ninko Secrets API – CRUD für Vault/SQLite Secrets Store.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request

from schemas.secret import (
    SecretSetRequest,
    SecretSetResponse,
    SecretListResponse,
    SecretDeleteResponse,
    VaultHealthResponse,
    SECRET_KEY_PATTERN,
)
from core.auth import ROLE_ADMIN, resolve_request_auth_async
from core.vault import get_vault

logger = logging.getLogger("ninko.api.secrets")
_SECRET_KEY_RE = re.compile(SECRET_KEY_PATTERN)


async def require_admin(request: Request) -> None:
    auth_ctx = await resolve_request_auth_async(request)
    if not auth_ctx or auth_ctx.get("role") != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Admin role required.")


router = APIRouter(
    prefix="/api/secrets",
    tags=["Secrets"],
    dependencies=[Depends(require_admin)],
)


def _validate_secret_key(key: str) -> str:
    clean = (key or "").strip()
    if not _SECRET_KEY_RE.fullmatch(clean):
        raise HTTPException(
            status_code=400,
            detail=(
                "Ungültiger Secret-Key. Erlaubt: 1-128 Zeichen, "
                "beginnend alphanumerisch, danach nur [A-Za-z0-9_.:-]."
            ),
        )
    return clean


@router.get("/", response_model=SecretListResponse)
async def list_secrets() -> SecretListResponse:
    """Listet alle gespeicherten Secret-Keys auf (ohne Werte!)."""
    vault = get_vault()
    keys = await vault.list_secrets()
    return SecretListResponse(
        keys=keys,
        backend=vault.backend_type,
        total=len(keys),
    )


@router.post("/", response_model=SecretSetResponse)
async def set_secret(body: SecretSetRequest) -> SecretSetResponse:
    """Speichert oder aktualisiert ein Secret."""
    vault = get_vault()
    await vault.set_secret(key=body.key, value=body.value)
    logger.info("Secret gesetzt: %s", body.key)
    return SecretSetResponse(key=body.key, status="ok")


@router.get("/{key}")
async def get_secret(key: str) -> dict:
    """
    Liest ein Secret. Gibt nur eine Existenzprüfung zurück –
    Werte werden aus Sicherheitsgründen nicht über die API exponiert.
    """
    key = _validate_secret_key(key)
    vault = get_vault()
    value = await vault.get_secret(key)
    return {
        "key": key,
        "exists": value is not None,
        "backend": vault.backend_type,
    }


@router.delete("/{key}", response_model=SecretDeleteResponse)
async def delete_secret(key: str) -> SecretDeleteResponse:
    """Löscht ein Secret."""
    key = _validate_secret_key(key)
    vault = get_vault()
    deleted = await vault.delete_secret(key)
    return SecretDeleteResponse(key=key, deleted=deleted)


@router.get("/health/check", response_model=VaultHealthResponse)
async def vault_health() -> VaultHealthResponse:
    """Prüft den Health-Status des Secrets-Backends."""
    vault = get_vault()
    health = await vault.health_check()
    return VaultHealthResponse(
        backend=vault.backend_type,
        status=health.get("status", "unknown"),
        detail=health.get("detail", ""),
    )
