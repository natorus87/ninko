"""
MikroTik Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.mikrotik.agent")


class MikrotikAgent(BaseAgent):
    """Agent for MikroTik RouterOS management."""

    name = "mikrotik"
    description = "Manages MikroTik RouterOS devices."

    system_prompt = """
You are the MikroTik agent. You can manage MikroTik RouterOS devices including switches, routers, and wireless access points.

Capabilities:
- Get device identity and system info
- List interfaces and status
- Get interface statistics
- List routing table
- List DHCP leases
- List firewall rules
- List queues
- List wireless clients
- Enable/disable interfaces
- Reboot router
- Create firewall rules
- Add IP addresses

Output Format for Overviews (ALWAYS):
- For lists (Interfaces, Routes, DHCP Leases, Firewall Rules, Queues, Wireless Clients): ALWAYS use Markdown tables
- Example: | Interface | Status | RX | TX | |---------|--------|----|----|
- NEVER use bullet lists, plain text, or JSON
- Always include units for traffic (bps, Mbps)
- Color-code status when helpful

Behavior rules:
- For interface enable/disable ALWAYS confirm first
- For router reboot ALWAYS confirm first
- For firewall rule create/delete ALWAYS confirm first
- On errors: explain the problem and suggest solutions
- Always respond in the user's language
"""

    def __init__(self) -> None:
        super().__init__()


from .tools import (
    get_mikrotik_identity,
    list_mikrotik_interfaces,
    get_mikrotik_interface_stats,
    list_mikrotik_routes,
    list_mikrotik_dhcp_leases,
    list_mikrotik_firewall_rules,
    list_mikrotik_queues,
    list_mikrotik_wireless_clients,
    enable_mikrotik_interface,
    disable_mikrotik_interface,
    reboot_mikrotik,
    create_mikrotik_firewall_rule,
    add_mikrotik_ip_address,
)

agent = MikrotikAgent()
agent.register_tool(get_mikrotik_identity)
agent.register_tool(list_mikrotik_interfaces)
agent.register_tool(get_mikrotik_interface_stats)
agent.register_tool(list_mikrotik_routes)
agent.register_tool(list_mikrotik_dhcp_leases)
agent.register_tool(list_mikrotik_firewall_rules)
agent.register_tool(list_mikrotik_queues)
agent.register_tool(list_mikrotik_wireless_clients)
agent.register_tool(enable_mikrotik_interface)
agent.register_tool(disable_mikrotik_interface)
agent.register_tool(reboot_mikrotik)
agent.register_tool(create_mikrotik_firewall_rule)
agent.register_tool(add_mikrotik_ip_address)
