"""
Ninko Safeguard Profiles API — CRUD für Safeguard-Profile.

Routen:
    GET    /api/safeguard/profiles              — alle Profile
    POST   /api/safeguard/profiles              — Custom-Profil erstellen
    GET    /api/safeguard/profiles/{id}         — einzelnes Profil
    PUT    /api/safeguard/profiles/{id}         — Custom-Profil aktualisieren
    DELETE /api/safeguard/profiles/{id}         — Custom-Profil löschen
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

logger = logging.getLogger("ninko.api.safeguard_profiles")
router = APIRouter(prefix="/api/safeguard/profiles", tags=["Safeguard Profiles"])

# Erlaubte Zeichen für Profil-IDs (slug-Format)
_ID_RE = re.compile(r"^[a-z0-9_\-]{1,64}$")


class ProfileCreateRequest(BaseModel):
    id:                      str
    name:                    str
    check_user_messages:     bool        = True
    check_tool_calls:        bool        = True
    confirm_categories:      list[str]   = ["DESTRUCTIVE", "STATE_CHANGING"]
    detect_prompt_injection: bool        = False
    fail_open:               bool        = False

    @field_validator("id")
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError("Profil-ID darf nur Kleinbuchstaben, Zahlen, _ und - enthalten (max 64 Zeichen).")
        return v

    @field_validator("confirm_categories")
    @classmethod
    def validate_categories(cls, v: list[str]) -> list[str]:
        valid = {"SAFE", "DESTRUCTIVE", "STATE_CHANGING", "PROMPT_INJECTION"}
        for cat in v:
            if cat not in valid:
                raise ValueError(f"Ungültige Kategorie: '{cat}'. Erlaubt: {valid}")
        return v


class ProfileUpdateRequest(BaseModel):
    name:                    str | None  = None
    check_user_messages:     bool | None = None
    check_tool_calls:        bool | None = None
    confirm_categories:      list[str] | None = None
    detect_prompt_injection: bool | None = None
    fail_open:               bool | None = None

    @field_validator("confirm_categories")
    @classmethod
    def validate_categories(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return v
        valid = {"SAFE", "DESTRUCTIVE", "STATE_CHANGING", "PROMPT_INJECTION"}
        for cat in v:
            if cat not in valid:
                raise ValueError(f"Ungültige Kategorie: '{cat}'. Erlaubt: {valid}")
        return v


def _get_profile_store(request: Request):
    sg = getattr(request.app.state, "safeguard", None)
    if sg is None:
        raise HTTPException(status_code=503, detail="Safeguard nicht initialisiert.")
    if sg.profile_store is None:
        raise HTTPException(status_code=503, detail="SafeguardProfileStore nicht verfügbar.")
    return sg.profile_store


# ─── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("")
async def list_profiles(request: Request) -> list[dict]:
    """Alle Profile (Built-in + Custom) auflisten."""
    profile_store = _get_profile_store(request)
    return await profile_store.list_profiles()


@router.post("", status_code=201)
async def create_profile(body: ProfileCreateRequest, request: Request) -> dict:
    """Neues Custom-Profil erstellen."""
    from core.safeguard import SafeguardProfile, _BUILTIN_PROFILES

    profile_store = _get_profile_store(request)

    # Darf Built-in-ID nicht verwenden
    if body.id in _BUILTIN_PROFILES:
        raise HTTPException(
            status_code=409,
            detail=f"ID '{body.id}' ist für ein Built-in Profil reserviert.",
        )

    # Darf nicht bereits existieren
    existing = await profile_store.get_profile(body.id)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Profil '{body.id}' existiert bereits.",
        )

    profile = SafeguardProfile(
        id                      = body.id,
        name                    = body.name,
        builtin                 = False,
        check_user_messages     = body.check_user_messages,
        check_tool_calls        = body.check_tool_calls,
        confirm_categories      = body.confirm_categories,
        detect_prompt_injection = body.detect_prompt_injection,
        fail_open               = body.fail_open,
    )
    await profile_store.save_profile(profile)
    return profile.to_dict()


@router.get("/{profile_id}")
async def get_profile(profile_id: str, request: Request) -> dict:
    """Einzelnes Profil abrufen."""
    profile_store = _get_profile_store(request)
    profile = await profile_store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profil '{profile_id}' nicht gefunden.")
    return profile.to_dict()


@router.put("/{profile_id}")
async def update_profile(
    profile_id: str,
    body: ProfileUpdateRequest,
    request: Request,
) -> dict:
    """Custom-Profil aktualisieren. Built-in Profile sind unveränderlich."""
    from core.safeguard import _BUILTIN_PROFILES

    if profile_id in _BUILTIN_PROFILES:
        raise HTTPException(
            status_code=403,
            detail=f"Built-in Profil '{profile_id}' kann nicht geändert werden.",
        )

    profile_store = _get_profile_store(request)
    profile = await profile_store.get_profile(profile_id)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"Profil '{profile_id}' nicht gefunden.")

    # Felder patchen (nur übermittelte Werte)
    if body.name is not None:
        profile.name = body.name
    if body.check_user_messages is not None:
        profile.check_user_messages = body.check_user_messages
    if body.check_tool_calls is not None:
        profile.check_tool_calls = body.check_tool_calls
    if body.confirm_categories is not None:
        profile.confirm_categories = body.confirm_categories
    if body.detect_prompt_injection is not None:
        profile.detect_prompt_injection = body.detect_prompt_injection
    if body.fail_open is not None:
        profile.fail_open = body.fail_open

    await profile_store.save_profile(profile)
    return profile.to_dict()


@router.delete("/{profile_id}", status_code=204, response_model=None)
async def delete_profile(profile_id: str, request: Request) -> None:
    """Custom-Profil löschen. Built-in Profile sind geschützt."""
    profile_store = _get_profile_store(request)
    try:
        await profile_store.delete_profile(profile_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
