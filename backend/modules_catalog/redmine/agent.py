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
    # HRM Erweiterte Tools
    get_redmine_hrm_attendance_types,
    update_redmine_hrm_attendance,
    delete_redmine_hrm_attendance,
    get_redmine_time_entry_activities,
    get_redmine_hrm_user_report,
    create_redmine_hrm_vacation,
    create_redmine_hrm_sick_leave,
    # User Administration Tools
    create_redmine_user,
    get_redmine_user_details,
    update_redmine_user,
    delete_redmine_user,
    lock_redmine_user,
    unlock_redmine_user,
    reset_redmine_user_password,
    add_redmine_user_to_group,
    remove_redmine_user_from_group,
    get_redmine_groups,
    create_redmine_group,
    delete_redmine_group,
)

logger = logging.getLogger("ninko.modules.redmine.agent")

SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos Redmine-Spezialist.

Deine Fähigkeiten:
- Projekte auflisten und Details abrufen
- Tickets/Issues abrufen, erstellen und aktualisieren (mit Filter für assigned_to_id)
- Benutzer auflisten, erstellen, aktualisieren, deaktivieren (lock/unlock), löschen
- Benutzerdetails mit Gruppen und Mitgliedschaften abrufen
- Passwörter zurücksetzen
- Gruppen verwalten (erstellen, löschen, Benutzer hinzufügen/entfernen)
- Time Entries abrufen und loggen
- Benutzerstunden-Report: get_redmine_user_hours_report für Monatsauswertungen (pagination, summiert automatisch)
- Issue-Status und Prioritäten abrufen
- Nach Tickets suchen
- Issue-Zusammenfassungen (offen/geschlossen)
- AlphaNodes HRM API-Endpunkte lesen/schreiben (Attendances, Kapazitäten, Feiertage)
- AlphaNodes Reporting API-Endpunkte lesen/schreiben (Budgets, Time Logs)

Wichtige Regeln:
- Für "Stunden im Monat": NUTZE get_redmine_user_hours_report
  - Gibt zurück: total_hours, days_count, summary_by_day (gruppiert nach Tag), entries (max 20 Details)
  - Wenn mehr als 20 Einträge: "X Stunden über Y Tage (20 von Z Einträgen angezeigt)"
  - Zeige summary_by_day als kompakte Tabelle (Datum | Stunden | Anzahl)
  - Bei "alle anzeigen": Liste die entries (max 20), verweise auf "weitere entries verfügbar"
- Für "HRM Report/Urlaub/Krankheit": NUTZE get_redmine_hrm_user_report
- Für "Urlaub eintragen": NUTZE create_redmine_hrm_vacation
- Für "Krankheit eintragen": NUTZE create_redmine_hrm_sick_leave
- Für Benutzer-Administration: Nutze lock_redmine_user zum Sperren, unlock_redmine_user zum Entsperren
- Für Passwort-Reset: Nutze reset_redmine_user_password
- Keine Emojis, prägnante tabellarische Ausgaben""",
    en="""You are Ninko's Redmine specialist.

Your capabilities:
- List projects and get details
- Retrieve, create, update issues (with assigned_to_id filter)
- List, create, update, lock/unlock users
- Get user details with groups and memberships
- Reset passwords
- Manage groups (create, delete, add/remove users)
- Retrieve time entries
- User hours report: get_redmine_user_hours_report for monthly reports
- Get issue statuses and priorities
- Search for tickets
- Get issue summaries (open/closed)
- Read/write AlphaNodes HRM endpoints (attendances, capacities, holidays)
- Read/write AlphaNodes Reporting endpoints (budgets, time logs)

Output Format for Overviews (ALWAYS):
- For lists (Issues, Users, Projects, Groups): ALWAYS use Markdown tables
- Example: | ID | Subject | Status | Assignee | |-----|---------|--------|---------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for numbers
- Color-code status when helpful

Important rules:
- For "hours in month" questions: USE get_redmine_user_hours_report
- For "tickets by user X": Use get_redmine_issues with assigned_to_id
- For user admin: lock_redmine_user to deactivate, unlock_redmine_user to reactivate
- For password reset: reset_redmine_user_password
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
                # HRM Erweiterte Tools
                get_redmine_hrm_attendance_types,
                update_redmine_hrm_attendance,
                delete_redmine_hrm_attendance,
                get_redmine_time_entry_activities,
                get_redmine_hrm_user_report,
                create_redmine_hrm_vacation,
                create_redmine_hrm_sick_leave,
                # User Administration
                create_redmine_user,
                get_redmine_user_details,
                update_redmine_user,
                delete_redmine_user,
                lock_redmine_user,
                unlock_redmine_user,
                reset_redmine_user_password,
                add_redmine_user_to_group,
                remove_redmine_user_from_group,
                get_redmine_groups,
                create_redmine_group,
                delete_redmine_group,
            ],
        )
