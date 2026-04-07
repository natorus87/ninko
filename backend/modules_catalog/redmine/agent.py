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
    get_redmine_user_hours_report,
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
- Tickets/Issues abrufen, erstellen und aktualisieren (mit Filter für assigned_to_id)
- Benutzer auflisten und IDs zuordnen
- Time Entries abrufen und loggen
- Benutzerstunden-Report: get_redmine_user_hours_report für Monatsauswertungen (pagination, summiert automatisch)
- Issue-Status und Prioritäten abrufen
- Nach Tickets suchen
- Issue-Zusammenfassungen (offen/geschlossen)
- AlphaNodes HRM API-Endpunkte lesen/schreiben (Attendances, Kapazitäten, Feiertage)
- AlphaNodes Reporting API-Endpunkte lesen/schreiben (Budgets, Time Logs)

Wichtige Regeln:
- Für "Stunden im Monat": NUTZE get_redmine_user_hours_report
  - Format: user_id="32", from_date="2026-03-01", to_date="2026-03-31"
  - Rückgabe: total_hours, entry_count, entries (Liste mit date, hours, project, issue_id)
  - Antworte mit: "X Stunden (N Einträge)" + formatierte Liste
- Keine Emojis, prägnante Antworten
- Wenn User "Tickets dazu" möchte: Zeige die entries-Liste aus dem Report""",
    en="""You are Ninko's Redmine specialist.

Your capabilities:
- List projects and get details
- Retrieve, create, and update tickets/issues (with assigned_to_id filter)
- List users and map IDs
- Retrieve and log time entries
- User hours report: get_redmine_user_hours_report for monthly reports (auto-pagination, sums correctly)
- Get issue statuses and priorities
- Search for tickets
- Get issue summaries (open/closed)
- Read/write AlphaNodes HRM API endpoints (attendances, capacities, holidays)
- Read/write AlphaNodes Reporting API endpoints (budgets, time logs)

Important rules:
- For "hours in month" questions: USE get_redmine_user_hours_report (not get_redmine_time_entries)
  - This tool auto-paginates through ALL entries and sums correctly
  - Format: from_date="2026-03-01", to_date="2026-03-31"
- For "tickets by user X": Use get_redmine_issues with assigned_to_id
- Be concise and factual, no emojis
- Only give the raw sum, no repetitive explanations""",
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
                get_redmine_user_hours_report,
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
