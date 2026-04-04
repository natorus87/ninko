"""Discord module — ModuleManifest and health check."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ModuleManifest(BaseModel):
    name: str = "discord"
    version: str = "1.0.0"
    description: str = (
        "Discord bot integration for messaging, channels, and server management"
    )
    author: str = "Ninko"
    routing_keywords: list[str] = [
        "discord",
        "server",
        "chat",
        "bot",
        "text",
        "nachricht",
    ]
    api_prefix: str = "/discord"
    dashboard_tab: bool = True
    requires_connection: bool = True


module_manifest = ModuleManifest()


async def check_discord_health(connection_id: str = "") -> dict:
    """Check if Discord bot is connected and responsive."""
    from .tools import get_discord_guild_info

    try:
        info = await get_discord_guild_info(connection_id)
        if "error" in info:
            return {"status": "unhealthy", "detail": info.get("error")}
        return {"status": "healthy", "detail": "Bot connected"}
    except Exception as e:
        return {"status": "unhealthy", "detail": str(e)}
