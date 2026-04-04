"""Discord module."""

from .manifest import module_manifest, check_discord_health
from .agent import DiscordAgent

agent = DiscordAgent()
router = None

__all__ = ["module_manifest", "agent", "router", "check_discord_health"]
