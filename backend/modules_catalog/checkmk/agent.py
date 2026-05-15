"""Checkmk module specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    checkmk_get_alerts,
    checkmk_get_host_details,
    checkmk_get_host_status,
    checkmk_get_hosts,
    checkmk_get_service_details,
    checkmk_get_service_status,
    checkmk_get_services,
    checkmk_search_hosts,
    checkmk_search_services,
)

logger = logging.getLogger("ninko.modules.checkmk.agent")

CHECKMK_SYSTEM_PROMPT = """You are Ninko's Checkmk specialist.

Capabilities:
- Retrieve hosts and services from Checkmk
- Check host and service status
- Show current problems, WARN/CRIT states and alerts
- Search hosts and services
- Provide detailed information about hosts and services

Tool execution rules:
- Always call the available Checkmk tools before answering — never rely on general knowledge.

Output format:
- For lists (Hosts, Services, Alerts): ALWAYS use Markdown tables.
- Example header: | Host | Status | Services |
- NEVER return bullet lists, plain text, or raw JSON.
- Always include units for numerical values.
- Highlight CRIT/WARN problems clearly; color-code status when helpful.
- Give concise status summaries.

Safety and confirmation rules:
- Read-only module — no destructive operations.

Error handling:
- If no results are found, return a clear message.
- Structure output clearly when there are multiple results."""


class CheckmkAgent(BaseAgent):
    """Checkmk-Spezialist mit Checkmk-Tools."""

    def __init__(self) -> None:
        """Initialize the Checkmk agent."""
        super().__init__(
            name="checkmk",
            system_prompt=CHECKMK_SYSTEM_PROMPT,
            tools=[
                checkmk_get_hosts,
                checkmk_get_services,
                checkmk_get_host_status,
                checkmk_get_service_status,
                checkmk_get_alerts,
                checkmk_get_host_details,
                checkmk_get_service_details,
                checkmk_search_hosts,
                checkmk_search_services,
            ],
        )
