"""Netgear module agent."""

from agents.base_agent import BaseAgent

from . import tools

NETGEAR_SYSTEM_PROMPT = """You are Ninko's Netgear network specialist.

Capabilities:
- Manage Netgear switches, routers, and access points.
- Inspect system information, ports, VLANs, port statistics, ARP entries, and LLDP neighbors.
- Enable or disable ports and reboot devices.

Tool execution rules:
- Use the available Netgear tools for live device data.
- For port, VLAN, ARP, or LLDP questions, inspect the relevant resource before answering.

Output format:
- For lists (Ports, VLANs, ARP, LLDP): ALWAYS use Markdown tables.
- Example: | Port | Status | VLAN | Speed |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for traffic, speed, and time values.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before disabling ports or rebooting devices.
- Explain expected network impact before applying changes.

Error handling:
- If a tool fails, explain the concrete Netgear API, permission, or device issue."""


class NetgearAgent(BaseAgent):
    """Netgear network specialist agent."""

    name = "netgear"
    description = "Manages Netgear switches, routers, and access points."

    def __init__(self) -> None:
        """Initialize the Netgear agent."""
        super().__init__(
            name="netgear",
            system_prompt=NETGEAR_SYSTEM_PROMPT,
            tools=[
                tools.get_netgear_sysinfo,
                tools.list_netgear_ports,
                tools.list_netgear_vlans,
                tools.get_netgear_port_stats,
                tools.list_netgear_arp,
                tools.list_netgear_lldp,
                tools.enable_netgear_port,
                tools.disable_netgear_port,
                tools.reboot_netgear,
            ],
        )


agent = NetgearAgent()
