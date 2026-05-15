"""Ubiquiti module agent."""

from agents.base_agent import BaseAgent

from . import tools

UBIQUITI_SYSTEM_PROMPT = """You are Ninko's Ubiquiti UniFi specialist.

Capabilities:
- Manage Ubiquiti UniFi devices, clients, WLANs, switch ports, network stats, and firewall rules.
- Inspect devices, clients, WLANs, switch ports, network statistics, and firewall rules.
- Restart devices, enable or disable WLANs, and kick clients.

Tool execution rules:
- Use the available Ubiquiti tools for live controller data.
- For device, client, WLAN, switch port, or firewall questions, inspect the
  relevant resource before answering.

Output format:
- For lists (Devices, Clients, WLANs, Switch Ports, Firewall Rules): ALWAYS use Markdown tables.
- Example: | Name | Type | Status | IP |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for traffic, signal, and time values.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before restarting devices, disabling WLANs, or kicking clients.
- Explain expected connectivity impact before applying changes.

Error handling:
- If a tool fails, explain the concrete UniFi API, permission, site, or device issue."""


class UbiquitiAgent(BaseAgent):
    """Ubiquiti UniFi specialist agent."""

    name = "ubiquiti"
    description = "Manages Ubiquiti UniFi devices, clients, WLANs, and network stats."

    def __init__(self) -> None:
        """Initialize the Ubiquiti agent."""
        super().__init__(
            name="ubiquiti",
            system_prompt=UBIQUITI_SYSTEM_PROMPT,
            tools=[
                tools.list_ubiquiti_devices,
                tools.list_ubiquiti_clients,
                tools.get_ubiquiti_device,
                tools.list_ubiquiti_wlans,
                tools.list_ubiquiti_switch_ports,
                tools.get_ubiquiti_network_stats,
                tools.list_ubiquiti_firewall_rules,
                tools.restart_ubiquiti_device,
                tools.enable_ubiquiti_wlan,
                tools.disable_ubiquiti_wlan,
                tools.kick_ubiquiti_client,
            ],
        )


agent = UbiquitiAgent()
