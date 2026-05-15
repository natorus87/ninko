"""Microsoft Entra module agent."""

from agents.base_agent import BaseAgent

from . import tools

MICROSOFT_ENTRA_SYSTEM_PROMPT = """You are Ninko's Microsoft Entra specialist.

Capabilities:
- Manage users, groups, applications, and devices in Microsoft Entra ID.
- Search and inspect users, group memberships, applications, and registered devices.
- Create users and groups, disable users, reset passwords, and add users to groups.

Tool execution rules:
- Use the available Microsoft Graph tools for live tenant data.
- For detail questions, inspect the specific user, group, application, or device before answering.

Output format:
- For lists (Users, Groups, Applications, Devices): ALWAYS use Markdown tables.
- Example: | Name | UPN | Status | Type |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for numbers.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before disabling users, resetting passwords, or changing group membership.
- Never reveal generated passwords unless a tool explicitly returns them for the admin flow.

Error handling:
- If a tool fails, explain the concrete Graph API, permission, or tenant issue."""


class MicrosoftEntraAgent(BaseAgent):
    """Microsoft Entra specialist agent."""

    name = "microsoft_entra"
    description = "Manages Microsoft Entra ID users, groups, applications, and devices."

    def __init__(self) -> None:
        """Initialize the Microsoft Entra agent."""
        super().__init__(
            name="microsoft_entra",
            system_prompt=MICROSOFT_ENTRA_SYSTEM_PROMPT,
            tools=[
                tools.list_entra_users,
                tools.search_entra_user,
                tools.get_user_details,
                tools.list_entra_groups,
                tools.get_group_members,
                tools.list_entra_applications,
                tools.list_entra_devices,
                tools.create_entra_user,
                tools.disable_entra_user,
                tools.reset_entra_user_password,
                tools.create_entra_group,
                tools.add_user_to_group,
            ],
        )


agent = MicrosoftEntraAgent()
