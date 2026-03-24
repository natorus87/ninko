"""
Telegram Agent – empfängt Anfragen, die Telegram-Nachrichten versenden sollen.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from modules.telegram.tools import send_telegram_message

SYSTEM_PROMPT = """Du bist der Telegram-Agent von Kumio.
Deine Aufgabe: Telegram-Nachrichten an Benutzer senden, wenn sie darum bitten.

Nutze das Tool `send_telegram_message` um Nachrichten zu versenden.
Wenn keine Chat-ID angegeben wird, nutzt das Tool automatisch die Standard-Chat-ID aus den Einstellungen.

Bestätige dem User NICHT extra nach dem Senden – die Blitz-Reaktion (⚡) in Telegram reicht als visuelles Feedback. Reagiere nur bei Fehlern."""

agent = BaseAgent(
    name="telegram",
    system_prompt=SYSTEM_PROMPT,
    tools=[send_telegram_message],
)
