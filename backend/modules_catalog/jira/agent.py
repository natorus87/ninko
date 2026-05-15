"""Jira specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    create_jira_issue,
    get_jira_boards,
    get_jira_issue,
    get_jira_issue_counts,
    get_jira_issue_transitions,
    get_jira_issues,
    get_jira_priorities,
    get_jira_project,
    get_jira_projects,
    get_jira_sprint,
    get_jira_sprints,
    search_jira,
    transition_jira_issue,
    update_jira_issue,
)

logger = logging.getLogger("ninko.modules.jira.agent")

SYSTEM_PROMPT = """You are Ninko's Jira specialist.

Capabilities:
- List projects and get details
- Retrieve, create, and update issues
- Show boards and sprints
- Search issues using JQL
- Get and perform issue transitions
- Get priorities
- Get issue summaries

Tool execution rules:
- Use available Jira tools before answering live Jira questions.
- Use JQL search when the user asks for filtered or cross-project issue lists.
- Use transition tools when the user asks to move an issue through workflow states.

Output format:
- For lists (Issues, Projects, Boards, Sprints): ALWAYS use Markdown tables
- Example: | Key | Summary | Status | Assignee | |-----|---------|--------|---------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for numbers
- Color-code status and priority when helpful

Behavior rules:
- Be precise and helpful
- Present important information in a structured way

Safety and confirmation rules:
- Do not perform destructive actions without confirmation.

Error handling:
- If a tool fails, explain the concrete problem and suggest the next useful Jira action."""


class JiraAgent(BaseAgent):
    """Jira specialist with Jira tools."""

    def __init__(self) -> None:
        """Initialize the Jira agent."""
        super().__init__(
            name="jira",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_jira_projects,
                get_jira_project,
                get_jira_issues,
                get_jira_issue,
                create_jira_issue,
                update_jira_issue,
                get_jira_boards,
                get_jira_sprints,
                get_jira_sprint,
                search_jira,
                get_jira_issue_transitions,
                transition_jira_issue,
                get_jira_priorities,
                get_jira_issue_counts,
            ],
        )
