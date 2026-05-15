"""Cisco module agent."""

from agents.base_agent import BaseAgent

from . import tools

CISCO_SYSTEM_PROMPT = """You are Ninko's Cisco network specialist.

Capabilities:
- Manage Cisco IOS and IOS-XE devices.
- Inspect device information, interfaces, VLANs, routes, MAC addresses, and PoE status.
- Enable or disable interfaces, create VLANs, and assign interface VLANs.

Tool execution rules:
- Use the available Cisco tools for live device data.
- For interface, VLAN, route, or PoE questions, inspect the relevant resource before answering.

Output format:
- For lists (Interfaces, VLANs, Routes, MAC Addresses): ALWAYS use Markdown tables.
- Example: | Interface | Status | VLAN | Description |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for numbers.
- Color-code operational status when helpful.

Safety and confirmation rules:
- Ask for confirmation before changing interface state, VLAN membership, or VLAN definitions.
- Explain the expected network impact before applying changes.

Error handling:
- If a tool fails, explain the concrete Cisco device, API, permission, or command issue."""


class CiscoAgent(BaseAgent):
    """Cisco network specialist agent."""

    name = "cisco"
    description = "Manages Cisco IOS/IOS-XE devices."

    def __init__(self) -> None:
        """Initialize the Cisco agent."""
        super().__init__(
            name="cisco",
            system_prompt=CISCO_SYSTEM_PROMPT,
            tools=[
                tools.get_cisco_device_info,
                tools.list_cisco_interfaces,
                tools.get_cisco_interface_details,
                tools.list_cisco_vlans,
                tools.list_cisco_routes,
                tools.list_cisco_mac_addresses,
                tools.get_cisco_poe_status,
                tools.enable_cisco_interface,
                tools.disable_cisco_interface,
                tools.create_cisco_vlan,
                tools.set_cisco_interface_vlan,
            ],
        )


agent = CiscoAgent()
