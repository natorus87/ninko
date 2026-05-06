"""
Ubiquiti Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.ubiquiti.agent")


class UbiquitiAgent(BaseAgent):
    """Agent for Ubiquiti UniFi management."""

    name = "ubiquiti"
    description = "Manages Ubiquiti UniFi devices."

    system_prompt = """
You are the Ubiquiti UniFi agent. You can manage UniFi switches, routers, and access points.

Capabilities:
- List all devices (APs, switches, routers)
- List clients (wired and wireless)
- Get device details
- List wireless networks (SSIDs)
- List switch ports
- Get network traffic stats
- List firewall rules
- Restart devices
- Enable/disable WLANs
- Kick clients

Output Format for Overviews (ALWAYS):
- For lists (Devices, Clients, WLANs, Switch Ports, Firewall Rules): ALWAYS use Markdown tables
- Example: | Device | Model | Status | IP | |------|------|--------|-----|
- NEVER use bullet lists, plain text, or JSON
- Always include units for numbers
- Color-code status (online/offline) when helpful

Behavior rules:
- For device restart ALWAYS confirm first
- For WLAN disable ALWAYS confirm first (users may lose connectivity!)
- For client kick ALWAYS confirm first
- On errors: explain the problem and suggest solutions
- Always respond in the user's language
"""

    def __init__(self) -> None:
        super().__init__()


from .tools import (
    list_ubiquiti_devices,
    list_ubiquiti_clients,
    get_ubiquiti_device,
    list_ubiquiti_wlans,
    list_ubiquiti_switch_ports,
    get_ubiquiti_network_stats,
    list_ubiquiti_firewall_rules,
    restart_ubiquiti_device,
    enable_ubiquiti_wlan,
    disable_ubiquiti_wlan,
    kick_ubiquiti_client,
)

agent = UbiquitiAgent()
agent.register_tool(list_ubiquiti_devices)
agent.register_tool(list_ubiquiti_clients)
agent.register_tool(get_ubiquiti_device)
agent.register_tool(list_ubiquiti_wlans)
agent.register_tool(list_ubiquiti_switch_ports)
agent.register_tool(get_ubiquiti_network_stats)
agent.register_tool(list_ubiquiti_firewall_rules)
agent.register_tool(restart_ubiquiti_device)
agent.register_tool(enable_ubiquiti_wlan)
agent.register_tool(disable_ubiquiti_wlan)
agent.register_tool(kick_ubiquiti_client)
