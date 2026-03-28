"""
Agent Definition für das Teams Modul.
"""

from agents.base_agent import BaseAgent
from .tools import send_teams_message


class TeamsAgent(BaseAgent):
    """
    Agent für Microsoft Teams – kann proaktiv Nachrichten in die letzte bekannte
    Konversation senden (z.B. auf Anfrage eines anderen Agenten).
    """

    def __init__(self):
        system_prompt = (
            "Du bist der Microsoft Teams Spezialist von Ninko. "
            "Nutze send_teams_message um proaktive Nachrichten in Teams zu senden. "
            "Die Nachricht geht in die zuletzt aktive Teams-Konversation. "
            "Falls noch keine Konversation bekannt ist, erkläre das dem Nutzer."
        )
        super().__init__(
            name="teams",
            system_prompt=system_prompt,
            tools=[send_teams_message],
        )


agent = TeamsAgent()
