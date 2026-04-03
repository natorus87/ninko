"""
Netgear Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.netgear.agent")


class NetgearAgent(BaseAgent):
    """Agent for Netgear network device management."""

    name = "netgear"
    description = "Manages Netgear switches and routers."

    system_prompt = """
You are the Netgear network device agent. You can manage Netgear switches, routers, and access points.

Capabilities:
- Get system information
- List ports and status
- Get port statistics
- List VLANs
- List ARP table
- List LLDP neighbors
- Enable/disable ports
- Reboot device

When asked to perform an action, always confirm first unless the user explicitly confirms.
When there is uncertainty, ask the user to confirm before proceeding.
"""

    def __init__(self):
        super().__init__()


from .tools import (
    get_netgear_sysinfo,
    list_netgear_ports,
    list_netgear_vlans,
    get_netgear_port_stats,
    list_netgear_arp,
    list_netgear_lldp,
    enable_netgear_port,
    disable_netgear_port,
    reboot_netgear,
)

agent = NetgearAgent()
agent.register_tool(get_netgear_sysinfo)
agent.register_tool(list_netgear_ports)
agent.register_tool(list_netgear_vlans)
agent.register_tool(get_netgear_port_stats)
agent.register_tool(list_netgear_arp)
agent.register_tool(list_netgear_lldp)
agent.register_tool(enable_netgear_port)
agent.register_tool(disable_netgear_port)
agent.register_tool(reboot_netgear)
