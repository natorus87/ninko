"""
Message Hub — Pydantic-Schemas für Routing-Einträge und Channel-Konfiguration.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class PermissionCap(str, Enum):
    """
    5-Level Permission Tier für externe Channel-Requests.

    Externe Requests werden auf diesen Tier gecapped — kein WRITE_SYSTEM/ADMIN
    von außen ohne explizite Konfiguration.
    """

    READONLY = "READONLY"
    COMMUNICATE = "COMMUNICATE"
    WRITE_DATA = "WRITE_DATA"
    WRITE_SYSTEM = "WRITE_SYSTEM"
    ADMIN = "ADMIN"


# Mapping von PermissionCap → Safeguard-Profil-ID
PERMISSION_TO_SAFEGUARD_PROFILE: dict[PermissionCap, str] = {
    PermissionCap.READONLY: "strict",
    PermissionCap.COMMUNICATE: "moderate",
    PermissionCap.WRITE_DATA: "user_only",
    PermissionCap.WRITE_SYSTEM: "llm_only",
    PermissionCap.ADMIN: "disabled",
}

ChannelType = Literal["telegram", "discord", "email"]


class RouteEntry(BaseModel):
    """Ein Routing-Eintrag: mappt (channel_type, channel_id) auf eine Ninko-Session."""

    id: str
    channel_type: ChannelType
    channel_id: str = Field(description="Chat-ID (Telegram), Channel-ID (Discord) oder E-Mail-Adresse")
    session_id: str = Field(description="Ninko Session-ID für diesen Channel")
    permission_cap: PermissionCap = Field(
        default=PermissionCap.WRITE_DATA,
        description="Maximaler erlaubter Tool-Tier für externe Requests",
    )
    label: str = Field(default="", description="Lesbarer Name für diesen Eintrag")
    enabled: bool = True
    created_at: float = 0.0


class RouteCreate(BaseModel):
    """Request-Body zum Anlegen eines Routing-Eintrags."""

    channel_type: ChannelType
    channel_id: str
    session_id: str
    permission_cap: PermissionCap = PermissionCap.WRITE_DATA
    label: str = ""
    enabled: bool = True


class RouteUpdate(BaseModel):
    """Request-Body zum Aktualisieren eines Routing-Eintrags."""

    session_id: str | None = None
    permission_cap: PermissionCap | None = None
    label: str | None = None
    enabled: bool | None = None


class WorkerStatus(BaseModel):
    """Status eines Background-Workers."""

    channel_type: str
    running: bool
    restart_count: int
    last_error: str | None
    next_retry_in: float | None


class HubStatus(BaseModel):
    """Gesamtstatus des Message Hub."""

    workers: list[WorkerStatus]
    route_count: int
    active_route_count: int
