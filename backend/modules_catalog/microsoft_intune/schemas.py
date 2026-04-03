"""
Microsoft Intune Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class IntuneDevice(BaseModel):
    """Managed device in Intune."""

    id: str
    device_name: str
    device_type: str
    os_version: str
    enrolled_datetime: str
    last_sync_datetime: str
    user_display_name: Optional[str] = None
    compliance_status: str = "unknown"
    is_managed: bool = False


class IntunePolicy(BaseModel):
    """Configuration policy."""

    id: str
    name: str
    description: Optional[str] = None
    platform: str
    type: str
    modified_datetime: str


class IntuneApp(BaseModel):
    """Managed application."""

    id: str
    display_name: str
    publisher: Optional[str] = None
    app_store_url: Optional[str] = None
    installs_count: int = 0


class IntuneCompliancePolicy(BaseModel):
    """Compliance policy."""

    id: str
    name: str
    description: Optional[str] = None
    platform: str
    created_datetime: str


class IntuneActionResponse(BaseModel):
    """Response to an Intune action."""

    action: str
    target: str
    status: str
    detail: str = ""
