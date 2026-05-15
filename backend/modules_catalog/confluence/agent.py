"""Confluence specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    create_confluence_blog_post,
    create_confluence_page,
    get_confluence_blog_posts,
    get_confluence_labels,
    get_confluence_page,
    get_confluence_page_history,
    get_confluence_pages,
    get_confluence_space,
    get_confluence_spaces,
    search_confluence,
    update_confluence_page,
)

logger = logging.getLogger("ninko.modules.confluence.agent")

SYSTEM_PROMPT = """You are Ninko's Confluence specialist.

Capabilities:
- List spaces and get details
- Retrieve, create, and update pages
- Retrieve and create blog posts
- Search content using CQL
- Retrieve labels
- Show page history

Tool execution rules:
- Use available Confluence tools before answering live Confluence questions.
- Use CQL search when the user asks for content across spaces.
- Present important information in a structured way.

Output format:
- For lists (Pages, Spaces, Blogs, Comments): ALWAYS use Markdown tables
- Example: | Title | Space | Modified |
- NEVER use bullet lists, plain text, or JSON
- Always include units for numbers
- Color-code status when helpful

Behavior rules:
- Be precise and helpful

Safety and confirmation rules:
- Do not perform destructive actions without confirmation.

Error handling:
- If a tool fails, explain the concrete problem and suggest the next useful Confluence action."""


class ConfluenceAgent(BaseAgent):
    """Confluence specialist with Confluence tools."""

    def __init__(self) -> None:
        """Initialize the Confluence agent."""
        super().__init__(
            name="confluence",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_confluence_spaces,
                get_confluence_space,
                get_confluence_pages,
                get_confluence_page,
                create_confluence_page,
                update_confluence_page,
                get_confluence_blog_posts,
                create_confluence_blog_post,
                search_confluence,
                get_confluence_labels,
                get_confluence_page_history,
            ],
        )
