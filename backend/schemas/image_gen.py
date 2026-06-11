"""
Ninko Image Generation Schemas.

Pydantic-Modelle für die /api/settings/image-provider und /api/images/* Endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel


# ── Request ───────────────────────────────────────────────────────────────────


class ImageProviderConfig(BaseModel):
    """Request: Image-Provider-Konfiguration (PUT)."""

    backend: str = ""
    api_key: str = ""
    model: str = ""


class ImageGenerateRequest(BaseModel):
    """Request: Bild generieren (POST /api/images/generate)."""

    prompt: str
    size: str = "1024x1024"


# ── Response ──────────────────────────────────────────────────────────────────


class ImageProviderInfo(BaseModel):
    """Response: Aktuelle Image-Provider-Konfiguration (GET)."""

    backend: str = ""
    api_key: str = ""
    api_key_masked: str = ""
    model: str = ""


class ImageProviderUpdateResponse(BaseModel):
    """Response: Update der Image-Provider-Konfiguration (PUT)."""

    status: str
    backend: str
    model: str


class ImageGenerateResponse(BaseModel):
    """Response: Erzeugtes Bild (POST /api/images/generate)."""

    status: str
    image_id: str
    filename: str
    url: str
    backend: str
    model: str
    size_bytes: int


__all__ = [
    "ImageProviderConfig",
    "ImageGenerateRequest",
    "ImageProviderInfo",
    "ImageProviderUpdateResponse",
    "ImageGenerateResponse",
]
