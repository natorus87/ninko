"""
Nextcloud Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.nextcloud.agent")


class NextcloudAgent(BaseAgent):
    """Agent for Nextcloud management."""

    name = "nextcloud"
    description = "Manages files and users in Nextcloud."

    system_prompt = """
You are the Nextcloud agent. You can manage files, folders, shares, and users in Nextcloud.

Capabilities:
- List and search files
- Create folders
- Upload and delete files
- Create shares
- List and manage users
- View storage usage

When asked to perform an action, always confirm first unless the user explicitly confirms.
"""

    def __init__(self) -> None:
        super().__init__()


from .tools import (
    list_nextcloud_files,
    search_nextcloud_files,
    list_nextcloud_users,
    get_nextcloud_user,
    list_nextcloud_shares,
    get_nextcloud_storage,
    create_nextcloud_folder,
    upload_nextcloud_file,
    delete_nextcloud_file,
    create_nextcloud_share,
    create_nextcloud_user,
)

agent = NextcloudAgent()
agent.register_tool(list_nextcloud_files)
agent.register_tool(search_nextcloud_files)
agent.register_tool(list_nextcloud_users)
agent.register_tool(get_nextcloud_user)
agent.register_tool(list_nextcloud_shares)
agent.register_tool(get_nextcloud_storage)
agent.register_tool(create_nextcloud_folder)
agent.register_tool(upload_nextcloud_file)
agent.register_tool(delete_nextcloud_file)
agent.register_tool(create_nextcloud_share)
agent.register_tool(create_nextcloud_user)
