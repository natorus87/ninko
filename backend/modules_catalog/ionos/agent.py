"""IONOS DNS specialist agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    add_ionos_record,
    delete_ionos_record,
    get_ionos_records,
    get_ionos_zones,
    update_ionos_record,
)

IONOS_SYSTEM_PROMPT = """You are Ninko's IONOS DNS specialist.

Capabilities:
- List zones: Show all IONOS DNS zones and their IDs.
- View records: Read all DNS records of a specific zone.
- Manage records: Create, update, or delete DNS records.

Tool execution rules:
- To edit records, you always need the IONOS zone ID (`zoneId`).
- When the user asks about a domain, first find the matching zone ID.

Output format:
- For lists (Zones, Records): ALWAYS use Markdown tables
- Example: | Name | Type | TTL | Content | |------|-----|-----|--------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for TTL
- Color-code record types when helpful

Safety and confirmation rules:
- Confirm changes to DNS records (create/update/delete) clearly.
- Only delete records if the user explicitly requests deletion.

Error handling:
- If the API returns an error, explain that the API key may be missing or invalid."""


class IonosAgent(BaseAgent):
    """IONOS DNS specialist with API tools."""

    def __init__(self) -> None:
        """Initialize the IONOS agent."""
        super().__init__(
            name="ionos",
            system_prompt=IONOS_SYSTEM_PROMPT,
            tools=[
                get_ionos_zones,
                get_ionos_records,
                add_ionos_record,
                update_ionos_record,
                delete_ionos_record,
            ],
        )
