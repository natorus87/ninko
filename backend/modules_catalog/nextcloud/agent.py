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

Output Format for Overviews (ALWAYS):
- For lists (Files, Users, Shares, Storage): ALWAYS use Markdown tables
- Example: | Name | Size | Modified | Owner | |------|------|----------|-------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for file sizes (KB, MB, GB)
- Color-code share types when helpful

Behavior rules:
- For file/folder delete ALWAYS confirm first
- For user delete ALWAYS confirm first
- For share create with link: confirm access level
- On errors: explain the problem and suggest solutions
- Always respond in the user's language
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
