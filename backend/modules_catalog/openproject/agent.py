"""OpenProject module agent."""

from agents.base_agent import BaseAgent

from . import tools

OPENPROJECT_SYSTEM_PROMPT = """You are Ninko's OpenProject specialist.

Capabilities:
- Manage projects, work packages, users, and time entries in OpenProject.
- List and inspect projects and work packages.
- Create and update work packages and log time entries.

Tool execution rules:
- Use the available OpenProject tools for live project data.
- For work package or project detail questions, inspect the relevant item before answering.

Output format:
- For lists (Projects, Work Packages, Users, Time Entries): ALWAYS use Markdown tables.
- Example: | ID | Subject | Status | Assignee |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for time values.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before changing work packages or logging time on behalf of a user.

Error handling:
- If a tool fails, explain the concrete OpenProject API, permission, or object issue."""


class OpenProjectAgent(BaseAgent):
    """OpenProject specialist agent."""

    name = "openproject"
    description = "Manages projects, work packages, users, and time entries."

    def __init__(self) -> None:
        """Initialize the OpenProject agent."""
        super().__init__(
            name="openproject",
            system_prompt=OPENPROJECT_SYSTEM_PROMPT,
            tools=[
                tools.list_openproject_projects,
                tools.get_openproject_project,
                tools.list_openproject_work_packages,
                tools.get_openproject_work_package,
                tools.list_openproject_users,
                tools.list_openproject_time_entries,
                tools.create_openproject_work_package,
                tools.update_openproject_work_package,
                tools.log_openproject_time,
            ],
        )


agent = OpenProjectAgent()
