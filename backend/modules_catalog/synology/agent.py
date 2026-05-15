"""Synology NAS specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    add_user_to_group,
    change_synology_user_password,
    check_synology_updates,
    create_synology_group,
    create_synology_user,
    delete_synology_user,
    get_synology_groups,
    get_synology_network_info,
    get_synology_packages,
    get_synology_services,
    get_synology_storage,
    get_synology_system_info,
    get_synology_tasks,
    get_synology_users,
    install_synology_package,
    install_synology_update,
    reboot_synologyNAS,
    remove_user_from_group,
    restart_synology_service,
    shutdown_synologyNAS,
    uninstall_synology_package,
)

logger = logging.getLogger("ninko.modules.synology.agent")

SYSTEM_PROMPT = """You are Ninko's Synology NAS specialist.

Capabilities:
- Query system status (model, version, uptime)
- Retrieve storage information (disks, RAID, volumes)
- List installed packages
- Check service status
- Display scheduled tasks
- Check for DSM updates
- Install/uninstall packages
- Query network and user information
- Manage users and groups (create, delete, change password)
- Add/remove users from groups
- Reboot or shutdown the NAS

Tool execution rules:
- Use available Synology tools before answering live NAS questions.
- Present important information in a structured way.

Output format:
- For lists (Packages, Disks, Users, Volumes): ALWAYS use Markdown tables
- Example: | Name | Status | Size | |------|--------|------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for sizes (GB, TB, %)
- Color-code status when helpful

Behavior rules:
- Be precise and helpful
- ALWAYS ask for confirmation before risky NAS changes.

Safety and confirmation rules:
- Do not perform destructive actions without confirmation
- Shutdown/reboot requires confirm=True
- Package install/uninstall requires confirm=True
- User deletion requires confirm=True

Error handling:
- If a tool fails, explain the concrete problem and suggest the next useful check."""


class SynologyAgent(BaseAgent):
    """Synology NAS specialist with Synology tools."""

    def __init__(self) -> None:
        """Initialize the Synology agent."""
        super().__init__(
            name="synology",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_synology_system_info,
                get_synology_storage,
                get_synology_packages,
                get_synology_services,
                restart_synology_service,
                get_synology_tasks,
                check_synology_updates,
                install_synology_update,
                install_synology_package,
                uninstall_synology_package,
                get_synology_network_info,
                get_synology_users,
                get_synology_groups,
                create_synology_user,
                delete_synology_user,
                change_synology_user_password,
                create_synology_group,
                add_user_to_group,
                remove_user_from_group,
                shutdown_synologyNAS,
                reboot_synologyNAS,
            ],
        )
