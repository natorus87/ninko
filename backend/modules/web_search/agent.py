from agents.base_agent import BaseAgent
from modules.web_search.tools import perform_web_search

WEB_SEARCH_SYSTEM_PROMPT = """
Du bist ein Web-Research-Agent. Deine Aufgabe ist es,
mithilfe des bereitgestellten Tools das Internet nach aktuellen Informationen zu durchsuchen.

WICHTIGE REGEL: Rufe `perform_web_search` GENAU EINMAL auf. Werte danach die Ergebnisse aus
und antworte direkt. Suche NICHT mehrfach nach Varianten der gleichen Frage.

Lies die Suchergebnisse und generiere eine präzise Antwort auf Basis der gefundenen Inhalte.
Gib immer die Quelle (URL) an, auf die du dich beziehst.
"""

class WebSearchAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(
            name="web_search",
            system_prompt=WEB_SEARCH_SYSTEM_PROMPT,
            tools=[perform_web_search]
        )
