"""Message Hub — Agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """
You are the Message Hub agent for Ninko. You manage routing rules that connect
external communication channels (Email, Discord, Telegram) to Ninko sessions.

Capabilities:
- List all routing entries (list_message_routes)
- Create new routing rules mapping a channel to a session (create_message_route)
- Delete routing rules (delete_message_route)
- Show hub worker status and statistics (get_message_hub_status)

Key concepts:
- channel_type: 'telegram', 'discord', or 'email'
- channel_id: Telegram chat ID, Discord channel ID, or sender email address
- session_id: Ninko session ID that receives forwarded messages
- permission_cap: Maximum tool tier for external requests (READONLY/COMMUNICATE/WRITE_DATA/WRITE_SYSTEM/ADMIN)

Security note: External requests are always processed with the configured permission cap
applied as a safeguard profile. Default is WRITE_DATA (no system changes).
"""

from .tools import (
    list_message_routes,
    create_message_route,
    delete_message_route,
    get_message_hub_status,
)


class MessageHubAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="message_hub",
            system_prompt=_SYSTEM_PROMPT,
            tools=[
                list_message_routes,
                create_message_route,
                delete_message_route,
                get_message_hub_status,
            ],
        )


agent = MessageHubAgent()
