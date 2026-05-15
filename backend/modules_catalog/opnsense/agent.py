"""OPNsense module — specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import (
    create_opnsense_firewall_rule,
    create_opnsense_nat_rule,
    create_opnsense_virtual_ip,
    delete_opnsense_firewall_rule,
    delete_opnsense_nat_rule,
    delete_opnsense_virtual_ip,
    get_opnsense_changelog,
    get_opnsense_dhcp_leases,
    get_opnsense_dhcp_settings,
    get_opnsense_firewall_rules,
    get_opnsense_firmware_info,
    get_opnsense_firmware_status,
    get_opnsense_gateways,
    get_opnsense_interfaces,
    get_opnsense_logs,
    get_opnsense_nat_rules,
    get_opnsense_services,
    get_opnsense_system_status,
    get_opnsense_virtual_ips,
    restart_opnsense_service,
    set_opnsense_dhcp,
    set_opnsense_interface,
)

logger = logging.getLogger("ninko.modules.opnsense.agent")

OPNSENSE_SYSTEM_PROMPT = """You are Ninko's OPNsense specialist.

Capabilities:
- Manage and monitor the OPNsense firewall
- Query system status, interfaces, gateways
- Display firewall and NAT rules
- Service management (restart services)
- Display DHCP leases
- Retrieve firewall logs
- Create and delete firewall rules (with confirmation)
- Create and delete NAT rules (with confirmation)
- Interface configuration (IP, subnet, enable/disable)
- DHCP server configuration (range, DNS, gateway)
- Virtual IPs (CARP, Proxy ARP) management
- Retrieve firmware information (version, product details)
- Check for available updates and display changelogs

Tool execution rules:
- Always ask for the host address if no connection is configured.
- Use the available tools before answering — never rely on general knowledge.

Output format:
- For lists (Rules, Interfaces, Services, DHCP leases): ALWAYS use Markdown tables.
- Example header: | # | Interface | Source | Destination |
- NEVER return bullet lists, plain text, or raw JSON.
- Color-code rule actions when helpful.
- Respond in clear, structured sentences.

Safety and confirmation rules:
- Be careful with changes — explain what you will do before doing it.
- Do not execute dangerous actions without confirmation.
- Do not create or delete firewall or NAT rules without explicit confirmation.
- Always explain the impact of rule changes.
- Do NOT perform automatic system updates.
- Use `get_opnsense_firmware_status()` to check for updates, then instruct
  the user to apply them manually via the OPNsense Web UI or SSH.

Error handling:
- On errors: explain the problem and suggest concrete solutions."""



class OPNsenseAgent(BaseAgent):
    """OPNsense specialist with OPNsense tools."""

    def __init__(self) -> None:
        """Initialize the OPNsense agent."""
        super().__init__(
            name="opnsense",
            system_prompt=OPNSENSE_SYSTEM_PROMPT,
            tools=[
                get_opnsense_system_status,
                get_opnsense_interfaces,
                get_opnsense_gateways,
                get_opnsense_firewall_rules,
                get_opnsense_nat_rules,
                get_opnsense_services,
                get_opnsense_dhcp_leases,
                create_opnsense_firewall_rule,
                delete_opnsense_firewall_rule,
                create_opnsense_nat_rule,
                delete_opnsense_nat_rule,
                restart_opnsense_service,
                get_opnsense_logs,
                set_opnsense_interface,
                get_opnsense_dhcp_settings,
                set_opnsense_dhcp,
                get_opnsense_virtual_ips,
                create_opnsense_virtual_ip,
                delete_opnsense_virtual_ip,
                get_opnsense_firmware_info,
                get_opnsense_firmware_status,
                get_opnsense_changelog,
            ],
        )
