"""
Jira Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from .tools import (
    get_jira_projects,
    get_jira_project,
    get_jira_issues,
    get_jira_issue,
    create_jira_issue,
    update_jira_issue,
    get_jira_boards,
    get_jira_sprints,
    get_jira_sprint,
    search_jira,
    get_jira_issue_transitions,
    transition_jira_issue,
    get_jira_priorities,
    get_jira_issue_counts,
)

logger = logging.getLogger("ninko.modules.jira.agent")

SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos Jira-Spezialist.

Deine Fähigkeiten:
- Projekte auflisten und Details abrufen
- Issues (Tickets) abrufen, erstellen und aktualisieren
- Boards und Sprints anzeigen
- Issues mit JQL suchen
- Issue-Transitions abrufen und durchführen
- Prioritäten abrufen
- Issue-Zusammenfassungen

Verhaltensregeln:
- Sei präzise und hilfreich
- Nutze die verfügbaren Tools, bevor du antwortest
- Zeige dem User wichtige Informationen strukturiert
- Wenn ein Tool fehlschlägt, erkläre das Problem

Sicherheit:
- Führe keine destruktiven Aktionen ohne Bestätigung""",
    en="""You are Ninko's Jira specialist.

Your capabilities:
- List projects and get details
- Retrieve, create, and update issues
- Show boards and sprints
- Search issues using JQL
- Get and perform issue transitions
- Get priorities
- Get issue summaries

Output Format for Overviews (ALWAYS):
- For lists (Issues, Projects, Boards, Sprints): ALWAYS use Markdown tables
- Example: | Key | Summary | Status | Assignee | |-----|---------|--------|---------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for numbers
- Color-code status and priority when helpful

Behavior rules:
- Be precise and helpful
- Use available tools before responding
- Present important information in a structured way
- If a tool fails, explain the problem

Safety:
- Do not perform destructive actions without confirmation""",
)


class JiraAgent(BaseAgent):
    """Jira-Spezialist mit den Jira-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="jira",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_jira_projects,
                get_jira_project,
                get_jira_issues,
                get_jira_issue,
                create_jira_issue,
                update_jira_issue,
                get_jira_boards,
                get_jira_sprints,
                get_jira_sprint,
                search_jira,
                get_jira_issue_transitions,
                transition_jira_issue,
                get_jira_priorities,
                get_jira_issue_counts,
            ],
        )
