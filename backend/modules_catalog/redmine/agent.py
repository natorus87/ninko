"""Redmine specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    add_redmine_user_to_group,
    call_redmine_hrm_api,
    call_redmine_reporting_api,
    create_redmine_group,
    create_redmine_hrm_attendance,
    create_redmine_hrm_sick_leave,
    create_redmine_hrm_vacation,
    create_redmine_issue,
    create_redmine_user,
    delete_redmine_group,
    delete_redmine_hrm_attendance,
    delete_redmine_user,
    get_redmine_groups,
    get_redmine_hrm_attendance,
    get_redmine_hrm_attendance_types,
    get_redmine_hrm_attendances,
    get_redmine_hrm_holidays,
    get_redmine_hrm_user_capacity,
    get_redmine_hrm_user_report,
    get_redmine_issue,
    get_redmine_issue_counts,
    get_redmine_issue_statuses,
    get_redmine_issues,
    get_redmine_priorities,
    get_redmine_project,
    get_redmine_project_budgets,
    get_redmine_projects,
    get_redmine_reporting_budgets,
    get_redmine_reporting_time_logs,
    get_redmine_time_entries,
    get_redmine_time_entry_activities,
    get_redmine_user_details,
    get_redmine_user_hours_report,
    get_redmine_users,
    lock_redmine_user,
    log_redmine_time,
    remove_redmine_user_from_group,
    reset_redmine_user_password,
    search_redmine_issues,
    unlock_redmine_user,
    update_redmine_hrm_attendance,
    update_redmine_issue,
    update_redmine_user,
)

logger = logging.getLogger("ninko.modules.redmine.agent")

SYSTEM_PROMPT = """You are Ninko's Redmine specialist.

Capabilities:
- List projects and retrieve project details.
- Retrieve, create, and update issues.
- List, create, update, lock, unlock, and delete users.
- Manage groups and user group membership.
- Retrieve and log time entries.
- Generate monthly user-hours reports.
- Read and write AlphaNodes HRM and Reporting endpoints.

Tool execution rules:
- For monthly-hours questions, use `get_redmine_user_hours_report`.
- For tickets by user, use `get_redmine_issues` with `assigned_to_id`.
- For HRM reports, vacation, or sick leave, use the dedicated HRM tools.
- For user deactivation/reactivation, use `lock_redmine_user` and `unlock_redmine_user`.
- For password resets, use `reset_redmine_user_password`.

Output format:
- For lists (Issues, Users, Projects, Groups): ALWAYS use Markdown tables.
- Example: | ID | Subject | Status | Assignee |
- NEVER return raw JSON or Python repr as the final answer.
- Be concise and factual; do not use emojis.

Safety and confirmation rules:
- Ask for confirmation before destructive user, group, or HRM changes.

Error handling:
- If a tool fails, explain the concrete Redmine API, permission, or object issue."""


class RedmineAgent(BaseAgent):
    """Redmine specialist with Redmine tools."""

    def __init__(self) -> None:
        """Initialize the Redmine agent."""
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
                get_redmine_hrm_attendance_types,
                update_redmine_hrm_attendance,
                delete_redmine_hrm_attendance,
                get_redmine_time_entry_activities,
                get_redmine_hrm_user_report,
                create_redmine_hrm_vacation,
                create_redmine_hrm_sick_leave,
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
