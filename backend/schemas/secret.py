"""
Ninko Secret Schemas – Pydantic-Modelle für Secrets API.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

SECRET_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"


class SecretSetRequest(BaseModel):
    """Anfrage zum Setzen eines Secrets."""

    key: str = Field(
        ...,
        min_length=1,
        max_length=128,
        pattern=SECRET_KEY_PATTERN,
    )
    value: str = Field(..., min_length=1)


class SecretSetResponse(BaseModel):
    """Antwort nach Secret-Speicherung."""

    key: str
    status: str = "ok"


class SecretListResponse(BaseModel):
    """Liste aller Secret-Keys."""

    keys: list[str]
    backend: str  # "vault" | "sqlite"
    total: int


class SecretDeleteResponse(BaseModel):
    """Antwort nach Secret-Löschung."""

    key: str
    deleted: bool


class VaultHealthResponse(BaseModel):
    """Health-Status des Secrets-Backends."""

    backend: str
    status: str
    detail: str = ""
