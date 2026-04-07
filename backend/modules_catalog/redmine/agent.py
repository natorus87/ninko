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
    call_redmine_hrm_api,
    call_redmine_reporting_api,
    get_redmine_hrm_attendances,
    create_redmine_hrm_attendance,
    get_redmine_hrm_attendance,
    get_redmine_hrm_user_capacity,
    get_redmine_hrm_holidays,
    get_redmine_reporting_budgets,
    get_redmine_project_budgets,
    get_redmine_reporting_time_logs,
)

logger = logging.getLogger("ninko.modules.redmine.agent")

SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos Redmine-Spezialist.

Deine Fähigkeiten:
- Projekte auflisten und Details abrufen
- Tickets/Issues abrufen, erstellen und aktualisieren
- Benutzer auflisten und IDs zuordnen
- Time Entries (Zeiterfassung) abrufen und loggen
- Issue-Status und Prioritäten abrufen
- Nach Tickets suchen
- Issue-Zusammenfassungen (offen/geschlossen)
- AlphaNodes HRM API-Endpunkte lesen/schreiben (Attendances, Kapazitäten, Feiertage)
- AlphaNodes Reporting API-Endpunkte lesen/schreiben (Budgets, Time Logs)

Antwortstil:
- Antworte prägnant und sachlich
- Keine Emojis, keine Dekorationen
- Keine Wiederholungen derselben Information
- Bei Listen: Tabellarische Übersicht ohne Floskeln
- Bei Zahlen: Nur die Zahl, keine Umschreibungen (z.B. "28 Stunden" statt "exakt 28 Stunden im Monat verteilt")

Wichtig:
- Nutze die Tools, bevor du antwortest
- Für Zeiterfassung: Nutze get_redmine_time_entries mit user_id Filter
- Für Monatsauswertungen: Summiere die Stunden pro Tag und gib die Gesamtsumme an
- Keine destruktiven Aktionen ohne Bestätigung""",
    en="""You are Ninko's Redmine specialist.

Your capabilities:
- List projects and get details
- Retrieve, create, and update tickets/issues
- List users and map IDs
- Retrieve and log time entries
- Get issue statuses and priorities
- Search for tickets
- Get issue summaries (open/closed)
- Read/write AlphaNodes HRM API endpoints (attendances, capacities, holidays)
- Read/write AlphaNodes Reporting API endpoints (budgets, time logs)

Response style:
- Be concise and factual
- No emojis, no decorations
- No repetition of the same information
- For lists: Tabular overview without filler text
- For numbers: Just the number, no circumscriptions

Important:
- Use tools before responding
- For time tracking: Use get_redmine_time_entries with user_id filter
- For monthly reports: Sum hours per day and give the total
- No destructive actions without confirmation""",
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
                call_redmine_hrm_api,
                call_redmine_reporting_api,
                get_redmine_hrm_attendances,
                create_redmine_hrm_attendance,
                get_redmine_hrm_attendance,
                get_redmine_hrm_user_capacity,
                get_redmine_hrm_holidays,
                get_redmine_reporting_budgets,
                get_redmine_project_budgets,
                get_redmine_reporting_time_logs,
            ],
        )
