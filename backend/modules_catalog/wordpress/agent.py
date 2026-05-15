"""WordPress management specialist agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    activate_plugin,
    create_category,
    create_page,
    create_post,
    create_tag,
    deactivate_plugin,
    delete_page,
    delete_plugin,
    delete_post,
    get_current_user,
    get_page,
    get_post,
    get_site_info,
    get_site_settings,
    get_updates_info,
    install_plugin,
    list_categories,
    list_media,
    list_pages,
    list_plugins,
    list_posts,
    list_tags,
    list_users,
    search_plugins,
    update_page,
    update_plugin,
    update_post,
    update_site_settings,
)

WORDPRESS_SYSTEM_PROMPT = """You are Ninko's WordPress specialist.

Capabilities:
- Check WordPress site info, settings, and updates.
- Manage plugins: list, search, install, activate, deactivate, update, delete.
- Manage pages and posts: list, create, edit, and delete.
- Manage categories, tags, users, settings, and media.

Tool execution rules:
- When asked to create, change, or delete something, act through the tools.
- Never explain manual dashboard steps as a substitute for tool execution.
- Use `update_page` for pages, `update_post` for posts, and `create_page` for pages.
- Accept HTML content for pages and posts.
- Use plugin slugs in `folder/file` format, such as `akismet/akismet`.
- Create pages and posts as `draft` by default, not `publish`.

Output format:
- Keep answers concise, usually no more than 8 lines.
- For lists (Plugins, Pages, Posts, Users, Media): ALWAYS use Markdown tables.
- Example: | Name | Status | Version |
- NEVER return raw JSON or Python repr as the final answer.

Safety and confirmation rules:
- Always ask for confirmation before destructive actions.
- Destructive actions include plugin deletion and forced page or post deletion.
- You cannot install, change, or design themes; say so briefly for redesign requests.

Error handling:
- If a tool fails, explain the concrete WordPress REST API, permission, or slug issue."""


class WordPressAgent(BaseAgent):
    """WordPress specialist with all WordPress management tools."""

    def __init__(self) -> None:
        """Initialize the WordPress agent."""
        super().__init__(
            name="wordpress",
            system_prompt=WORDPRESS_SYSTEM_PROMPT,
            tools=[
                get_site_info,
                get_updates_info,
                list_plugins,
                search_plugins,
                install_plugin,
                activate_plugin,
                deactivate_plugin,
                update_plugin,
                delete_plugin,
                list_pages,
                get_page,
                create_page,
                update_page,
                delete_page,
                list_posts,
                get_post,
                create_post,
                update_post,
                delete_post,
                list_categories,
                create_category,
                list_tags,
                create_tag,
                list_users,
                get_current_user,
                get_site_settings,
                update_site_settings,
                list_media,
            ],
        )

    def _select_tools_for_request(self, message: str) -> object:  # type: ignore[override]
        """WordPress always keeps all tools available; JIT filtering is disabled."""
        return self.tools
