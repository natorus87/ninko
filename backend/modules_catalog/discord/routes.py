"""Discord module — FastAPI routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .tools import (
    get_discord_guild_info,
    list_discord_channels,
    list_discord_members,
    send_discord_message,
    create_discord_channel,
    get_discord_channel_messages,
    search_discord_messages,
    delete_discord_channel,
)

router = APIRouter(tags=["discord"])


class ApiResponse(BaseModel):
    status: str
    data: dict | list | str | None = None
    error: str | None = None


@router.get("/status")
async def get_status(connection_id: str = "") -> ApiResponse:
    """Get Discord bot and server status."""
    try:
        info = await get_discord_guild_info(connection_id)
        if "error" in info:
            return ApiResponse(status="error", error=info["error"])
        return ApiResponse(status="ok", data=info)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))


@router.get("/channels")
async def get_channels(connection_id: str = "") -> ApiResponse:
    """Get all channels in the Discord server."""
    try:
        channels = await list_discord_channels(connection_id)
        return ApiResponse(status="ok", data=channels)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))


@router.get("/members")
async def get_members(connection_id: str = "", limit: int = 100) -> ApiResponse:
    """Get server members."""
    try:
        members = await list_discord_members(connection_id, limit)
        return ApiResponse(status="ok", data=members)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))


@router.post("/message")
async def send_message(
    channel_id: str, content: str, connection_id: str = ""
) -> ApiResponse:
    """Send a message to a Discord channel."""
    try:
        result = await send_discord_message(channel_id, content, connection_id)
        return ApiResponse(status="ok", data={"result": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))


@router.post("/channel")
async def create_channel(
    name: str, channel_type: str = "text", topic: str = "", connection_id: str = ""
) -> ApiResponse:
    """Create a new Discord channel."""
    try:
        result = await create_discord_channel(name, channel_type, topic, connection_id)
        return ApiResponse(status="ok", data={"result": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))


@router.get("/messages/{channel_id}")
async def get_messages(
    channel_id: str, limit: int = 10, connection_id: str = ""
) -> ApiResponse:
    """Get messages from a channel."""
    try:
        messages = await get_discord_channel_messages(channel_id, limit, connection_id)
        return ApiResponse(status="ok", data=messages)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))


@router.get("/search/{channel_id}")
async def search_messages(
    channel_id: str, query: str, limit: int = 10, connection_id: str = ""
) -> ApiResponse:
    """Search messages in a channel."""
    try:
        messages = await search_discord_messages(
            channel_id, query, limit, connection_id
        )
        return ApiResponse(status="ok", data=messages)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))


@router.delete("/channel/{channel_id}")
async def delete_channel(channel_id: str, connection_id: str = "") -> ApiResponse:
    """Delete a Discord channel."""
    try:
        result = await delete_discord_channel(channel_id, connection_id)
        return ApiResponse(status="ok", data={"result": result})
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return ApiResponse(status="error", error=str(exc))
