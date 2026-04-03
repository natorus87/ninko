"""
Redmine Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from .tools import (
    get_redmine_projects,
    get_redmine_project,
    get_redmine_issues,
    get_redmine_issue,
    create_redmine_issue,
    update_redmine_issue,
    get_redmine_users,
    get_redmine_time_entries,
    log_redmine_time,
    get_redmine_issue_statuses,
    get_redmine_priorities,
    search_redmine_issues,
    get_redmine_issue_counts,
)

logger = logging.getLogger("ninko.modules.redmine.agent")

SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos Redmine-Spezialist.

Deine Fähigkeiten:
- Projekte auflisten und Details abrufen
- Tickets/Issues abrufen, erstellen und aktualisieren
- Benutzer auflisten
- Time Entries abrufen und loggen
- Issue-Status und Prioritäten abrufen
- Nach Tickets suchen
- Issue-Zusammenfassungen (offen/geschlossen)

Verhaltensregeln:
- Sei präzise und hilfreich
- Nutze die verfügbaren Tools, bevor du antwortest
- Zeige dem User wichtige Informationen strukturiert
- Wenn ein Tool fehlschlägt, erkläre das Problem

Sicherheit:
- Führe keine destruktiven Aktionen ohne Bestätigung""",
    en="""You are Ninko's Redmine specialist.

Your capabilities:
- List projects and get details
- Retrieve, create, and update tickets/issues
- List users
- Retrieve and log time entries
- Get issue statuses and priorities
- Search for tickets
- Get issue summaries (open/closed)

Behavior rules:
- Be precise and helpful
- Use available tools before responding
- Present important information in a structured way
- If a tool fails, explain the problem

Safety:
- Do not perform destructive actions without confirmation""",
)


class RedmineAgent(BaseAgent):
    """Redmine-Spezialist mit den Redmine-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="redmine",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_redmine_projects,
                get_redmine_project,
                get_redmine_issues,
                get_redmine_issue,
                create_redmine_issue,
                update_redmine_issue,
                get_redmine_users,
                get_redmine_time_entries,
                log_redmine_time,
                get_redmine_issue_statuses,
                get_redmine_priorities,
                search_redmine_issues,
                get_redmine_issue_counts,
            ],
        )
