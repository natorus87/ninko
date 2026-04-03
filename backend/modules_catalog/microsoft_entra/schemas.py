"""
Microsoft Entra Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class EntraUser(BaseModel):
    """Microsoft Entra user."""

    id: str
    display_name: str
    user_principal_name: str
    mail: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    account_enabled: bool = True
    user_type: Optional[str] = None


class EntraGroup(BaseModel):
    """Microsoft Entra group."""

    id: str
    display_name: str
    description: Optional[str] = None
    mail_enabled: bool = False
    security_enabled: bool = True
    group_types: list[str] = []


class EntraApplication(BaseModel):
    """Azure AD application."""

    id: str
    display_name: str
    app_id: str
    publisher_domain: Optional[str] = None
    password_credentials: list[dict] = []


class EntraServicePrincipal(BaseModel):
    """Service principal."""

    id: str
    app_display_name: str
    app_id: str
    account_enabled: bool = True


class EntraDevice(BaseModel):
    """Registered device."""

    id: str
    display_name: str
    device_id: str
    operating_system: Optional[str] = None
    trust_type: Optional[str] = None
    is_compliant: bool = False


class EntraActionResponse(BaseModel):
    """Response to an Entra action."""

    action: str
    target: str
    status: str
    detail: str = ""
