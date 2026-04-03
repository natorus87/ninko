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

When asked to perform an action, always confirm first unless the user explicitly confirms.
When there is uncertainty, ask the user to confirm before proceeding.
"""

    def __init__(self):
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
