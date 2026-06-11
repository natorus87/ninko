"""
Ninko TTS Schemas.

Pydantic-Modelle für die /api/tts/* Endpoints.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Request ───────────────────────────────────────────────────────────────────


class SynthesizeRequest(BaseModel):
    """Request: Text-zu-WAV (POST /api/tts/synthesize)."""

    text: str
    lang: Optional[str] = None
    voice: Optional[str] = None


class DownloadRequest(BaseModel):
    """Request: Stimme herunterladen (POST /api/tts/voices/download)."""

    lang: str
    voice: str


# ── Response ──────────────────────────────────────────────────────────────────


class VoiceEntry(BaseModel):
    """Response: Einzelne installierte Stimme (GET /api/tts/voices)."""

    name: str
    lang: str
    quality: str


class VoiceCatalogEntry(BaseModel):
    """Response: Katalog-Eintrag inkl. Installationsstatus (GET /api/tts/voices/catalog)."""

    name: str
    lang: str
    quality: str
    installed: bool


class PiperVersionResponse(BaseModel):
    """Response: Lokale und neueste Piper-Version (GET /api/tts/piper/version)."""

    binary: str
    local_version: str
    latest_tag: str
    latest_version: str
    update_available: bool
    github_error: str = ""


class VoiceDownloadResponse(BaseModel):
    """Response: Stimmen-Download (POST /api/tts/voices/download)."""

    status: str
    lang: str
    voice: str


class VoiceDeleteResponse(BaseModel):
    """Response: Stimme löschen (DELETE /api/tts/voices/{lang}/{voice})."""

    status: str
    lang: str
    voice: str


__all__ = [
    "SynthesizeRequest",
    "DownloadRequest",
    "VoiceEntry",
    "VoiceCatalogEntry",
    "PiperVersionResponse",
    "VoiceDownloadResponse",
    "VoiceDeleteResponse",
]
