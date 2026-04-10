"""
OpenProject Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.openproject.agent")

_SYSTEM_PROMPT = """
You are the OpenProject agent. You can manage projects, work packages (tasks), time entries, and users in OpenProject.

Capabilities:
- List and search projects
- List work packages (tasks, bugs)
- Create and update work packages
- List and manage users
- Log time entries
- View project details

When asked to perform an action, always confirm first unless the user explicitly confirms.
"""

from .tools import (
    list_openproject_projects,
    get_openproject_project,
    list_openproject_work_packages,
    get_openproject_work_package,
    list_openproject_users,
    list_openproject_time_entries,
    create_openproject_work_package,
    update_openproject_work_package,
    log_openproject_time,
)


class OpenProjectAgent(BaseAgent):
    """Agent for OpenProject management."""

    def __init__(self) -> None:
        super().__init__(
            name="openproject",
            system_prompt=_SYSTEM_PROMPT,
            tools=[
                list_openproject_projects,
                get_openproject_project,
                list_openproject_work_packages,
                get_openproject_work_package,
                list_openproject_users,
                list_openproject_time_entries,
                create_openproject_work_package,
                update_openproject_work_package,
                log_openproject_time,
            ],
        )


agent = OpenProjectAgent()
