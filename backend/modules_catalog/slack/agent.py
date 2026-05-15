"""Slack module agent."""

from agents.base_agent import BaseAgent

from . import tools

SLACK_SYSTEM_PROMPT = """You are Ninko's Slack specialist.

Capabilities:
- Manage Slack channels, users, messages, direct messages, and file uploads.
- List channels and users, inspect channel history, and search messages.
- Send channel messages, send direct messages, upload files, create channels, and invite users.

Tool execution rules:
- Use the available Slack tools for live workspace data.
- For message history or search questions, query Slack before answering.

Output format:
- For lists (Channels, Users, Messages): ALWAYS use Markdown tables.
- Example: | Channel | Members | Topic | Updated |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for counts and time values.

Safety and confirmation rules:
- Ask for confirmation before sending messages, direct messages, uploading files, or inviting users.
- Treat private channel content and direct messages as sensitive.

Error handling:
- If a tool fails, explain the concrete Slack API, permission, channel, or user issue."""


class SlackAgent(BaseAgent):
    """Slack specialist agent."""

    name = "slack"
    description = "Manages Slack channels, users, messages, and files."

    def __init__(self) -> None:
        """Initialize the Slack agent."""
        super().__init__(
            name="slack",
            system_prompt=SLACK_SYSTEM_PROMPT,
            tools=[
                tools.list_slack_channels,
                tools.list_slack_users,
                tools.get_slack_channel_history,
                tools.search_slack_messages,
                tools.send_slack_message,
                tools.send_slack_dm,
                tools.upload_slack_file,
                tools.create_slack_channel,
                tools.invite_user_to_channel,
            ],
        )


agent = SlackAgent()
