"""MikroTik module agent."""

from agents.base_agent import BaseAgent

from . import tools

MIKROTIK_SYSTEM_PROMPT = """You are Ninko's MikroTik RouterOS specialist.

Capabilities:
- Manage MikroTik routers, switches, and wireless access points.
- Inspect identity, interfaces, stats, routes, DHCP leases, firewall rules,
  queues, and wireless clients.
- Enable or disable interfaces, reboot devices, create firewall rules, and add IP addresses.

Tool execution rules:
- Use the available MikroTik tools for live RouterOS data.
- For interface, route, firewall, queue, or wireless questions, inspect the
  relevant resource before answering.

Output format:
- For lists (Interfaces, Routes, DHCP Leases, Firewall Rules, Queues,
  Wireless Clients): ALWAYS use Markdown tables.
- Example: | Interface | Status | RX | TX |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for traffic, rates, and time values.
- Color-code status when helpful.

Safety and confirmation rules:
- Ask for confirmation before disabling interfaces, rebooting devices,
  changing firewall rules, or adding IP addresses.
- Explain expected network impact before applying changes.

Error handling:
- If a tool fails, explain the concrete RouterOS API, permission, or device issue."""


class MikrotikAgent(BaseAgent):
    """MikroTik RouterOS specialist agent."""

    name = "mikrotik"
    description = "Manages MikroTik RouterOS devices."

    def __init__(self) -> None:
        """Initialize the MikroTik agent."""
        super().__init__(
            name="mikrotik",
            system_prompt=MIKROTIK_SYSTEM_PROMPT,
            tools=[
                tools.get_mikrotik_identity,
                tools.list_mikrotik_interfaces,
                tools.get_mikrotik_interface_stats,
                tools.list_mikrotik_routes,
                tools.list_mikrotik_dhcp_leases,
                tools.list_mikrotik_firewall_rules,
                tools.list_mikrotik_queues,
                tools.list_mikrotik_wireless_clients,
                tools.enable_mikrotik_interface,
                tools.disable_mikrotik_interface,
                tools.reboot_mikrotik,
                tools.create_mikrotik_firewall_rule,
                tools.add_mikrotik_ip_address,
            ],
        )


agent = MikrotikAgent()
