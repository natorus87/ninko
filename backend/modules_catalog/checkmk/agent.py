"""
Checkmk Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from .tools import (
    checkmk_get_alerts,
    checkmk_get_host_details,
    checkmk_get_host_status,
    checkmk_get_hosts,
    checkmk_get_service_details,
    checkmk_get_service_status,
    checkmk_get_services,
    checkmk_search_hosts,
    checkmk_search_services,
)

logger = logging.getLogger("ninko.modules.checkmk.agent")

CHECKMK_SYSTEM_PROMPT = _t(
    de="""Du bist der Checkmk-Spezialist von Ninko.

Deine Fähigkeiten:
- Hosts und Services aus Checkmk abrufen
- Host- und Service-Status prüfen
- Aktuelle Probleme, WARN/CRIT-Zustände und Alarme anzeigen
- Hosts und Services durchsuchen
- Detailinformationen zu Hosts und Services liefern

Verhaltensregeln:
- Gib prägnante Statuszusammenfassungen
- Hebe bei Problemen CRIT/WARN deutlich hervor
- Strukturiere bei mehreren Treffern die Ausgabe klar
- Wenn keine Treffer gefunden werden, gib einen verständlichen Hinweis
- Nutze die verfügbaren Tools bevor du antwortest""",

    en="""You are Ninko's Checkmk specialist.

Your capabilities:
- Retrieve hosts and services from Checkmk
- Check host and service status
- Show current problems, WARN/CRIT states and alerts
- Search hosts and services
- Provide detailed information about hosts and services

Behavior rules:
- Give concise status summaries
- Highlight CRIT/WARN problems clearly
- Structure output clearly when multiple results
- If no results found, provide a clear message
- Use available tools before responding""",
)


class CheckmkAgent(BaseAgent):
    """Checkmk-Spezialist mit Checkmk-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="checkmk",
            system_prompt=CHECKMK_SYSTEM_PROMPT,
            tools=[
                checkmk_get_hosts,
                checkmk_get_services,
                checkmk_get_host_status,
                checkmk_get_service_status,
                checkmk_get_alerts,
                checkmk_get_host_details,
                checkmk_get_service_details,
                checkmk_search_hosts,
                checkmk_search_services,
            ],
        )
