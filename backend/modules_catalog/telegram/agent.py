"""
Telegram Agent — handles requests to send Telegram messages.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent, _t
from .tools import send_telegram_message

SYSTEM_PROMPT = _t(
    "Du bist der Telegram-Agent von Ninko.\n"
    "Deine Aufgabe: Telegram-Nachrichten an Benutzer senden, wenn sie darum bitten.\n\n"
    "Nutze das Tool `send_telegram_message` um Nachrichten zu versenden.\n"
    "Wenn keine Chat-ID angegeben wird, nutzt das Tool automatisch die Standard-Chat-ID aus den Einstellungen.\n\n"
    "Bestätige dem User NICHT extra nach dem Senden – die Blitz-Reaktion (⚡) in Telegram reicht als visuelles Feedback. Reagiere nur bei Fehlern.\n\n"
    "Ausgabe-Format: Structure responses clearly.",
    "You are the Telegram Agent of Ninko.\n"
    "Your task: send Telegram messages to users when they request it.\n\n"
    "Use the `send_telegram_message` tool to send messages.\n"
    "If no chat ID is provided, the tool automatically uses the default chat ID from settings.\n\n"
    "Do NOT confirm after sending — the lightning reaction (⚡) in Telegram is sufficient as visual feedback. Only react on errors.\n\n"
    "Output Format: Structure responses clearly.",
)

agent = BaseAgent(
    name="telegram",
    system_prompt=SYSTEM_PROMPT,
    tools=[send_telegram_message],
)
