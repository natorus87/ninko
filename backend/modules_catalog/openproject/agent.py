"""
OpenProject Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.openproject.agent")


class OpenProjectAgent(BaseAgent):
    """Agent for OpenProject management."""

    name = "openproject"
    description = "Manages projects and tasks in OpenProject."

    system_prompt = """
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

    def __init__(self):
        super().__init__()


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

agent = OpenProjectAgent()
agent.register_tool(list_openproject_projects)
agent.register_tool(get_openproject_project)
agent.register_tool(list_openproject_work_packages)
agent.register_tool(get_openproject_work_package)
agent.register_tool(list_openproject_users)
agent.register_tool(list_openproject_time_entries)
agent.register_tool(create_openproject_work_package)
agent.register_tool(update_openproject_work_package)
agent.register_tool(log_openproject_time)
