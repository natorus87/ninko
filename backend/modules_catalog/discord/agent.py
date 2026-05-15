"""Discord module — specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    create_discord_channel,
    delete_discord_channel,
    get_discord_channel_messages,
    get_discord_guild_info,
    list_discord_channels,
    list_discord_members,
    search_discord_messages,
    send_discord_message,
)

logger = logging.getLogger("ninko.modules.discord.agent")

DISCORD_SYSTEM_PROMPT = """You are Ninko's Discord specialist.

Capabilities:
- Manage Discord servers and channels
- Send and receive messages
- List and manage members
- Create and delete channels
- Search messages

Tool execution rules:
- Use the available Discord tools before answering live server questions.
- Search messages when the user asks for historical Discord content.

Output format:
- For lists (Channels, Members, Messages): ALWAYS use Markdown tables
- Example: | Name | Type | Members |
- NEVER return raw JSON or Python repr as the final answer
- Always include units for numbers
- Color-code channel types when helpful

Behavior rules:
- Respond in clear, structured sentences

Safety and confirmation rules:
- Do not delete channels without explicit confirmation.

Error handling:
- On errors, explain the problem and suggest a concrete next step."""


class DiscordAgent(BaseAgent):
    """Discord specialist with Discord tools."""

    def __init__(self) -> None:
        """Initialize the Discord agent."""
        super().__init__(
            name="discord",
            system_prompt=DISCORD_SYSTEM_PROMPT,
            tools=[
                get_discord_guild_info,
                list_discord_channels,
                list_discord_members,
                send_discord_message,
                create_discord_channel,
                get_discord_channel_messages,
                search_discord_messages,
                delete_discord_channel,
            ],
        )
