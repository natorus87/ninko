"""
Lenovo XClarity Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.lenovo_xclarity.agent")


class LenovoXClarityAgent(BaseAgent):
    """Agent for Lenovo XClarity management."""

    name = "lenovo_xclarity"
    description = (
        "Manages Lenovo ThinkSystem/ThinkBlade servers via XClarity Administrator."
    )

    system_prompt = """
You are the Lenovo XClarity agent. You can manage ThinkSystem and ThinkBlade servers via XClarity Administrator.

Capabilities:
- List managed servers
- Get server details
- List chassis and storage enclosures
- View server health and alerts
- List events
- View firmware versions
- Power on/off/restart servers
- Identify servers (blink LED)

When asked to perform an action, always confirm first unless the user explicitly confirms.
When there is uncertainty, ask the user to confirm before proceeding.
"""

    def __init__(self) -> None:
        super().__init__()


from .tools import (
    list_xclarity_servers,
    get_xclarity_server_details,
    list_xclarity_chassis,
    list_xclarity_storage,
    get_xclarity_server_health,
    list_xclarity_events,
    get_xclarity_firmware,
    power_on_xclarity_server,
    power_off_xclarity_server,
    restart_xclarity_server,
    identify_xclarity_server,
)

agent = LenovoXClarityAgent()
agent.register_tool(list_xclarity_servers)
agent.register_tool(get_xclarity_server_details)
agent.register_tool(list_xclarity_chassis)
agent.register_tool(list_xclarity_storage)
agent.register_tool(get_xclarity_server_health)
agent.register_tool(list_xclarity_events)
agent.register_tool(get_xclarity_firmware)
agent.register_tool(power_on_xclarity_server)
agent.register_tool(power_off_xclarity_server)
agent.register_tool(restart_xclarity_server)
agent.register_tool(identify_xclarity_server)
