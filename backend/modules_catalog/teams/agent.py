"""Agent definition for the Teams module."""

from agents.base_agent import BaseAgent

from .tools import send_teams_message


class TeamsAgent(BaseAgent):
    """Agent for proactive Microsoft Teams messages."""

    def __init__(self) -> None:
        """Initialize the Teams agent."""
        system_prompt = """You are Ninko's Microsoft Teams specialist.

Capabilities:
- Send proactive messages to Microsoft Teams through `send_teams_message`.

Tool execution rules:
- Use `send_teams_message` when the user explicitly asks to send a Teams message.
- The message goes to the last active Teams conversation.

Output format:
- Keep confirmations short and factual.

Safety and confirmation rules:
- Do not invent a Teams conversation target.

Error handling:
- If no Teams conversation is known yet, explain that to the user."""
        super().__init__(
            name="teams",
            system_prompt=system_prompt,
            tools=[send_teams_message],
        )


agent = TeamsAgent()
