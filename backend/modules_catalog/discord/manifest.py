"""Discord module manifest and health check."""

from __future__ import annotations

from core.module_registry import ModuleManifest


module_manifest = ModuleManifest(
    name="discord",
    display_name="Discord",
    description=(
        "Discord bot: manage Discord servers, channels, members, and messages."
    ),
    version="1.1.1",
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
    dashboard_tab={"id": "discord", "label": "Discord", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z"/><path d="M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z"/></svg>'},
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
