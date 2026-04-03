"""
Microsoft Intune Module — BaseAgent implementation.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

logger = logging.getLogger("ninko.modules.microsoft_intune.agent")


class MicrosoftIntuneAgent(BaseAgent):
    """Agent for Microsoft Intune MDM management."""

    name = "microsoft_intune"
    description = "Manages mobile devices via Microsoft Intune MDM."

    system_prompt = """
You are the Microsoft Intune agent. You can manage mobile devices via Microsoft Intune (Endpoint Manager).

Capabilities:
- List managed devices (iOS, Android, Windows, macOS)
- Get device details and compliance status
- List configuration policies
- List compliance policies
- List managed applications
- Wipe devices (factory reset)
- Retire devices (remove from management)
- Sync devices (trigger check-in)
- Locate devices

When asked to perform a destructive action (wipe), always confirm first and warn about data loss.
When there is uncertainty, ask the user to confirm before proceeding.
"""

    def __init__(self):
        super().__init__()


from .tools import (
    list_intune_devices,
    get_intune_device,
    list_intune_policies,
    list_intune_compliance_policies,
    list_intune_apps,
    get_intune_device_compliance,
    wipe_intune_device,
    retire_intune_device,
    sync_intune_device,
    locate_intune_device,
)

agent = MicrosoftIntuneAgent()
agent.register_tool(list_intune_devices)
agent.register_tool(get_intune_device)
agent.register_tool(list_intune_policies)
agent.register_tool(list_intune_compliance_policies)
agent.register_tool(list_intune_apps)
agent.register_tool(get_intune_device_compliance)
agent.register_tool(wipe_intune_device)
agent.register_tool(retire_intune_device)
agent.register_tool(sync_intune_device)
agent.register_tool(locate_intune_device)
