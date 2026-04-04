"""
Slack Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.slack.agent")


class SlackAgent(BaseAgent):
    """Agent for Slack workspace management."""

    name = "slack"
    description = "Manages Slack workspace via Slack API."

    system_prompt = """
You are the Slack agent. You can manage channels, messages, and users in a Slack workspace.

Capabilities:
- List channels
- List users
- Read channel message history
- Search messages
- Send messages to channels
- Send direct messages
- Upload files
- Create channels
- Invite users to channels

When asked to perform an action, always confirm first unless the user explicitly confirms.
"""

    def __init__(self) -> None:
        super().__init__()


from .tools import (
    list_slack_channels,
    list_slack_users,
    get_slack_channel_history,
    search_slack_messages,
    send_slack_message,
    send_slack_dm,
    upload_slack_file,
    create_slack_channel,
    invite_user_to_channel,
)

agent = SlackAgent()
agent.register_tool(list_slack_channels)
agent.register_tool(list_slack_users)
agent.register_tool(get_slack_channel_history)
agent.register_tool(search_slack_messages)
agent.register_tool(send_slack_message)
agent.register_tool(send_slack_dm)
agent.register_tool(upload_slack_file)
agent.register_tool(create_slack_channel)
agent.register_tool(invite_user_to_channel)
