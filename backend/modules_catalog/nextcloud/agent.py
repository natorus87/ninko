"""Nextcloud module agent."""

from agents.base_agent import BaseAgent

from . import tools

NEXTCLOUD_SYSTEM_PROMPT = """You are Ninko's Nextcloud specialist.

Capabilities:
- Manage files, users, shares, and storage in Nextcloud.
- List and search files, inspect users, list shares, and review storage usage.
- Create folders, upload files, delete files, create shares, and create users.

Tool execution rules:
- Use the available Nextcloud tools for live instance data.
- For file, share, storage, or user detail questions, inspect the relevant
  resource before answering.

Output format:
- For lists (Files, Users, Shares): ALWAYS use Markdown tables.
- Example: | Name | Type | Owner | Size |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for sizes and time values.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before deleting files or changing shares/users.
- Treat share links and account data as sensitive.

Error handling:
- If a tool fails, explain the concrete Nextcloud API, permission, or object issue."""


class NextcloudAgent(BaseAgent):
    """Nextcloud specialist agent."""

    name = "nextcloud"
    description = "Manages files, users, shares, and storage in Nextcloud."

    def __init__(self) -> None:
        """Initialize the Nextcloud agent."""
        super().__init__(
            name="nextcloud",
            system_prompt=NEXTCLOUD_SYSTEM_PROMPT,
            tools=[
                tools.list_nextcloud_files,
                tools.search_nextcloud_files,
                tools.list_nextcloud_users,
                tools.get_nextcloud_user,
                tools.list_nextcloud_shares,
                tools.get_nextcloud_storage,
                tools.create_nextcloud_folder,
                tools.upload_nextcloud_file,
                tools.delete_nextcloud_file,
                tools.create_nextcloud_share,
                tools.create_nextcloud_user,
            ],
        )


agent = NextcloudAgent()
