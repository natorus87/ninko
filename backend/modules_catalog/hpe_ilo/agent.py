"""
HPE iLO Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.hpe_ilo.agent")


class HpeIloAgent(BaseAgent):
    """Agent for HPE iLO management."""

    name = "hpe_ilo"
    description = "Manages HPE servers via iLO4/iLO5 REST API."

    system_prompt = """
You are the HPE iLO agent. You can query and control HPE servers via the iLO REST API.
You support both iLO4 and iLO5.

Capabilities:
- Read iLO firmware version, license, and manager info
- Read server model, serial number, power state, health
- Read thermal sensors and fan speeds
- Read power supply status
- Read iLO network config (IP, MAC)
- Read event logs
- Power on/off servers
- Reset iLO
- Press boot button for BIOS/EFI next boot

When asked to perform an action, always confirm first unless the user explicitly confirms.
When there is uncertainty, ask the user to confirm the action before proceeding.
"""

    def __init__(self):
        super().__init__()


from .tools import (
    get_ilo_info,
    get_server_info,
    get_server_thermal,
    get_server_power,
    get_ilo_nics,
    get_ilo_eventlog,
    server_power_on,
    server_power_off,
    server_reset_ilo,
    server_press_boot_button,
)

agent = HpeIloAgent()
agent.register_tool(get_ilo_info)
agent.register_tool(get_server_info)
agent.register_tool(get_server_thermal)
agent.register_tool(get_server_power)
agent.register_tool(get_ilo_nics)
agent.register_tool(get_ilo_eventlog)
agent.register_tool(server_power_on)
agent.register_tool(server_power_off)
agent.register_tool(server_reset_ilo)
agent.register_tool(server_press_boot_button)
