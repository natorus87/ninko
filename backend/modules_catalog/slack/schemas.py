"""
Slack Module — Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Optional


class SlackChannel(BaseModel):
    """Slack channel."""

    id: str
    name: str
    is_channel: bool = True
    is_private: bool = False
    is_archived: bool = False
    member_count: int = 0


class SlackUser(BaseModel):
    """Slack user."""

    id: str
    name: str
    real_name: Optional[str] = None
    display_name: Optional[str] = None
    is_workflow_bot: bool = False
    is_app_user: bool = False
    is_online: bool = False


class SlackMessage(BaseModel):
    """Slack message."""

    channel: str
    ts: str
    user: str
    text: str


class SlackActionResponse(BaseModel):
    """Response to a Slack action."""

    action: str
    target: str
    status: str
    detail: str = ""
