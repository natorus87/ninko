"""
Template Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from modules._template.tools import beispiel_tool, lade_daten

logger = logging.getLogger("ninko.modules.template.agent")

# System-Prompt mit _t(de, en) für Mehrsprachigkeit.
# NICHT "Antworte immer auf Deutsch" hardcoden — base_agent.py injiziert
# automatisch die Sprachanweisung aus der LANGUAGE-Konfiguration.
TEMPLATE_SYSTEM_PROMPT = _t(
    de="""Du bist der Template-Spezialist von Ninko.

Deine Fähigkeiten:
- TODO: Beschreibe hier die Fähigkeiten des Moduls

Verhaltensregeln:
- Sei präzise und hilfreich
- Nutze die dir zur Verfügung stehenden Tools, bevor du antwortest
- Wenn ein Tool fehlschlägt, erkläre dem User das Problem

Sicherheit:
- Führe keine destruktiven Aktionen ohne Bestätigung aus""",

    en="""You are Ninko's Template specialist.

Your capabilities:
- TODO: Describe the module's capabilities here

Behavior rules:
- Be precise and helpful
- Use the available tools before responding
- If a tool fails, explain the problem to the user

Safety:
- Do not perform destructive actions without confirmation""",
)


class TemplateAgent(BaseAgent):
    """Template-Spezialist mit den Template-Tools."""

    def __init__(self) -> None:
        super().__init__(
            # Name MUSS dem manifest.name entsprechen
            name="template",
            system_prompt=TEMPLATE_SYSTEM_PROMPT,
            tools=[beispiel_tool, lade_daten],
        )
