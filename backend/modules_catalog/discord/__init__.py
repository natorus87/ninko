"""Discord module."""

from .manifest import module_manifest, check_discord_health
from .agent import DiscordAgent
from .routes import router

agent = DiscordAgent()

__all__ = ["module_manifest", "agent", "router", "check_discord_health"]
