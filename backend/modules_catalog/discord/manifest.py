"""Discord module manifest and health check."""

from __future__ import annotations

from core.module_registry import ModuleManifest


module_manifest = ModuleManifest(
    name="discord",
    display_name="Discord",
    description="Discord Bot – Server, Channels, Members und Messages verwalten.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="DISCORD_",
    required_secrets=["DISCORD_BOT_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "discord",
        "discord server",
        "discord channel",
        "discord bot",
        "discord nachricht",
    ],
    api_prefix="/api/discord",
    dashboard_tab={"id": "discord", "label": "Discord", "icon": "💬"},
)


async def check_discord_health(connection_id: str = "") -> dict:
    """Check if Discord bot is connected and responsive."""
    from .tools import get_discord_guild_info

    try:
        info = await get_discord_guild_info(connection_id)
        if "error" in info:
            return {"status": "unhealthy", "detail": info.get("error")}
        return {"status": "healthy", "detail": "Bot connected"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "unhealthy", "detail": str(exc)}
