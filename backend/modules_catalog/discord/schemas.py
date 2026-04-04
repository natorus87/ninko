"""Discord module — Pydantic schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class DiscordConnection(BaseModel):
    bot_token: str = Field(..., description="Discord bot token")
    guild_id: Optional[str] = Field(None, description="Discord server (guild) ID")
    channel_id: Optional[str] = Field(None, description="Default channel for messages")


class SendDiscordMessageRequest(BaseModel):
    channel_id: str = Field(..., description="Channel ID to send message to")
    content: str = Field(..., description="Message content")
    connection_id: str = ""


class CreateDiscordChannelRequest(BaseModel):
    name: str = Field(..., description="Channel name")
    channel_type: str = Field("text", description="Channel type: text, voice, category")
    topic: Optional[str] = Field(None, description="Channel topic/description")
    connection_id: str = ""


class DiscordMessageSearchRequest(BaseModel):
    channel_id: str = Field(..., description="Channel to search in")
    query: str = Field(..., description="Search query")
    limit: int = Field(10, description="Max results")
    connection_id: str = ""
