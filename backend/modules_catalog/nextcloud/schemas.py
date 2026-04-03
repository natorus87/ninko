"""
Nextcloud Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class NextcloudFile(BaseModel):
    """Nextcloud file/folder."""

    fileid: int
    name: str
    path: str
    type: str  # "file" or "folder"
    size: int = 0
    mimetype: str = ""
    modified: Optional[str] = None


class NextcloudShare(BaseModel):
    """Nextcloud share."""

    id: int
    path: str
    name: str
    type: str  # "link", "user", "group"
    permissions: int = 1
    share_link: Optional[str] = None


class NextcloudUser(BaseModel):
    """Nextcloud user."""

    id: str
    displayname: str
    email: Optional[str] = None
    enabled: bool = True
    quota: int = 0
    used: int = 0


class NextcloudActivity(BaseModel):
    """Nextcloud activity."""

    id: int
    type: str
    object_name: str
    message: str
    timestamp: str


class NextcloudActionResponse(BaseModel):
    """Response to a Nextcloud action."""

    action: str
    target: str
    status: str
    detail: str = ""
