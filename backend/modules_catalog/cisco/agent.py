"""
Cisco Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.cisco.agent")


class CiscoAgent(BaseAgent):
    """Agent for Cisco network device management."""

    name = "cisco"
    description = "Manages Cisco switches and routers."

    system_prompt = """
You are the Cisco network device agent. You can manage Cisco switches, routers, and Nexus devices.

Capabilities:
- Get device information
- List interfaces and their status
- Get interface details
- List VLANs
- List routes
- List MAC address table
- View PoE status
- Enable/disable interfaces
- Create VLANs
- Set port VLAN membership

Output Format for Overviews (ALWAYS):
- For lists (Interfaces, VLANs, Routes, MAC Addresses): ALWAYS use Markdown tables
- Example: | Interface | Status | VLAN | PoE | |---------|--------|------|-----|
- NEVER use bullet lists, plain text, or JSON
- Always include units for numbers
- Color-code status (up/down) when helpful

Behavior rules:
- For interface enable/disable ALWAYS confirm first
- For VLAN create/delete ALWAYS confirm first
- On errors: explain the problem and suggest solutions
- Always respond in the user's language
"""

    def __init__(self) -> None:
        super().__init__()


from .tools import (
    get_cisco_device_info,
    list_cisco_interfaces,
    get_cisco_interface_details,
    list_cisco_vlans,
    list_cisco_routes,
    list_cisco_mac_addresses,
    get_cisco_poe_status,
    enable_cisco_interface,
    disable_cisco_interface,
    create_cisco_vlan,
    set_cisco_interface_vlan,
)

agent = CiscoAgent()
agent.register_tool(get_cisco_device_info)
agent.register_tool(list_cisco_interfaces)
agent.register_tool(get_cisco_interface_details)
agent.register_tool(list_cisco_vlans)
agent.register_tool(list_cisco_routes)
agent.register_tool(list_cisco_mac_addresses)
agent.register_tool(get_cisco_poe_status)
agent.register_tool(enable_cisco_interface)
agent.register_tool(disable_cisco_interface)
agent.register_tool(create_cisco_vlan)
agent.register_tool(set_cisco_interface_vlan)
