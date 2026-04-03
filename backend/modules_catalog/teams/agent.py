"""
Agent definition for the Teams module.
"""

from agents.base_agent import BaseAgent, _t
from .tools import send_teams_message


class TeamsAgent(BaseAgent):
    """
    Agent for Microsoft Teams — can proactively send messages
    to the last known conversation (e.g. on request from another agent).
    """

    def __init__(self):
        system_prompt = _t(
            "Du bist der Microsoft Teams Spezialist von Ninko. "
            "Nutze send_teams_message um proaktive Nachrichten in Teams zu senden. "
            "Die Nachricht geht in die zuletzt aktive Teams-Konversation. "
            "Falls noch keine Konversation bekannt ist, erkläre das dem Nutzer.",
            "You are the Microsoft Teams specialist of Ninko. "
            "Use send_teams_message to send proactive messages in Teams. "
            "The message goes to the last active Teams conversation. "
            "If no conversation is known yet, explain this to the user.",
        )
        super().__init__(
            name="teams",
            system_prompt=system_prompt,
            tools=[send_teams_message],
        )


agent = TeamsAgent()
