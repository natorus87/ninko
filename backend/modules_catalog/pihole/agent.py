"""Pi-hole module — specialist agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    add_cname_record,
    add_custom_dns_record,
    add_domain_to_list,
    delete_dhcp_lease,
    dismiss_system_message,
    flush_dns_cache,
    flush_logs,
    flush_network_table,
    get_blocklists,
    get_cname_records,
    get_custom_dns_records,
    get_dhcp_leases,
    get_pihole_summary,
    get_pihole_system,
    get_query_log,
    get_system_messages,
    get_top_clients,
    get_top_domains,
    remove_cname_record,
    remove_custom_dns_record,
    remove_domain_from_list,
    toggle_blocking,
    update_gravity,
)

PIHOLE_SYSTEM_PROMPT = """You are Ninko's Pi-hole DNS specialist.

Capabilities:
- DNS statistics: blocked queries, clients, top domains
- Query log: view and analyze recent DNS queries
- Blocking control: enable/disable DNS blocking (with optional time limit)
- Domain management: add domains to white-/blacklist
- Blocklists: view configured adlists
- System info: Pi-hole version, gravity status, uptime

Tool execution rules:
- ALWAYS call the appropriate tool; do not describe what you would do.
- For blocking changes (`toggle_blocking`): call immediately, then explain the impact.
- For domain list changes: call `add_domain_to_list` or `remove_domain_from_list`, then confirm.
- For DNS issues, first check Pi-hole status and system messages, then analyze query logs.

Output format:
- For lists (Queries, Clients, Domains, Blocklists): ALWAYS use Markdown tables
- Example: | Domain | Count | Last Query | |-------|-------|------------|
- NEVER use bullet lists, plain text, or JSON
- Always include units for numbers
- Color-code status when helpful

Behavior rules:
- Display statistics clearly with numbers and percentages
- For gravity updates or flush commands, mention the expected effect.
- Check blocking, forwarding, CNAME, and local DNS state before suggesting changes.

Safety and confirmation rules:
- Suggest white-/blacklist adjustments and apply them directly only if the user confirms.

Error handling:
- If Pi-hole is not configured, point the user to the module settings."""


class PiholeAgent(BaseAgent):
    """Pi-hole DNS specialist with Pi-hole tools."""

    def __init__(self) -> None:
        """Initialize the Pi-hole agent."""
        super().__init__(
            name="pihole",
            system_prompt=PIHOLE_SYSTEM_PROMPT,
            tools=[
                get_pihole_summary,
                get_query_log,
                get_top_domains,
                get_top_clients,
                toggle_blocking,
                get_blocklists,
                add_domain_to_list,
                remove_domain_from_list,
                get_pihole_system,
                get_custom_dns_records,
                add_custom_dns_record,
                remove_custom_dns_record,
                get_cname_records,
                add_cname_record,
                remove_cname_record,
                get_dhcp_leases,
                delete_dhcp_lease,
                update_gravity,
                flush_dns_cache,
                flush_logs,
                flush_network_table,
                get_system_messages,
                dismiss_system_message,
            ],
        )
