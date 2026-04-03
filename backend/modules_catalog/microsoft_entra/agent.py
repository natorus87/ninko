"""
Microsoft Entra Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.microsoft_entra.agent")


class MicrosoftEntraAgent(BaseAgent):
    """Agent for Microsoft Entra ID management."""

    name = "microsoft_entra"
    description = (
        "Manages Microsoft Entra ID (formerly Azure AD) via Microsoft Graph API."
    )

    system_prompt = """
You are the Microsoft Entra ID agent. You can manage users, groups, applications, and devices in Azure AD / Microsoft Entra ID via the Microsoft Graph API.

Capabilities:
- List and search users
- Get user details (including manager, device, licenses)
- Create and disable users
- Reset user passwords
- List and manage groups
- Add/remove group members
- List registered applications
- List registered devices
- Create groups

When asked to perform an action that modifies data, always confirm first unless the user explicitly confirms.
When there is uncertainty, ask the user to confirm the action before proceeding.
"""

    def __init__(self):
        super().__init__()


from .tools import (
    list_entra_users,
    search_entra_user,
    get_user_details,
    list_entra_groups,
    get_group_members,
    list_entra_applications,
    list_entra_devices,
    create_entra_user,
    disable_entra_user,
    reset_entra_user_password,
    create_entra_group,
    add_user_to_group,
)

agent = MicrosoftEntraAgent()
agent.register_tool(list_entra_users)
agent.register_tool(search_entra_user)
agent.register_tool(get_user_details)
agent.register_tool(list_entra_groups)
agent.register_tool(get_group_members)
agent.register_tool(list_entra_applications)
agent.register_tool(list_entra_devices)
agent.register_tool(create_entra_user)
agent.register_tool(disable_entra_user)
agent.register_tool(reset_entra_user_password)
agent.register_tool(create_entra_group)
agent.register_tool(add_user_to_group)
